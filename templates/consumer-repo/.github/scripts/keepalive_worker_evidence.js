'use strict';

const { withRetry } = require('./github-api-with-retry.js');
const { loadAgentRegistry, parseRegistryYaml } = require('./agent_registry.js');

// Only an exact originating attempt can prove that its worker did not start.
// A missing or incomplete jobs response is unknown, never a safe refund.
function workerNames(registry) {
  const agents = registry?.agents || {};
  return Object.entries(agents)
    .filter(([, config]) => config?.capabilities?.pr_keepalive === true && config?.enabled !== false)
    .map(([key, config]) => {
      const title = key.charAt(0).toUpperCase() + key.slice(1);
      return {
        job: String(config.keepalive_worker_job || `Keepalive next task (${title})`),
        step: String(config.keepalive_worker_step || `Run ${title}`),
      };
    });
}

function classifyWorkerExecution(jobs, registry = loadAgentRegistry()) {
  if (!Array.isArray(jobs)) return 'unknown';
  const names = workerNames(registry);
  const workers = jobs.flatMap((job) => names
    .filter(({ job: expected }) => String(job?.name || '') === expected ||
      String(job?.name || '').startsWith(`${expected} /`))
    .map(({ step }) => ({ job, step })));
  if (workers.length === 0) return 'unknown';
  for (const { job, step } of workers) {
    if (job.status !== 'completed') return 'unknown';
    if (job.conclusion === 'skipped') continue;
    const steps = job.steps;
    if (!Array.isArray(steps)) return 'unknown';
    const workerStep = steps.find((item) => String(item?.name || '') === step);
    if (!workerStep) return 'unknown';
    if (workerStep.status !== 'completed') return 'unknown';
    if (workerStep.conclusion !== 'skipped') return 'started';
  }
  return 'not-started';
}

async function getWorkerExecutionEvidence(github, owner, repo, runId, runAttempt, runHeadSha) {
  if (!Number.isInteger(Number(runId)) || Number(runId) <= 0 ||
      !Number.isInteger(Number(runAttempt)) || Number(runAttempt) <= 0 ||
      !/^[0-9a-f]{40}$/.test(String(runHeadSha || ''))) return 'unknown';
  try {
    const registryResponse = await withRetry((client) => client.rest.repos.getContent({
      owner, repo, path: '.github/agents/registry.yml', ref: runHeadSha,
    }), { github, maxRetries: 2, task: 'keepalive-origin-registry' });
    const registryFile = registryResponse?.data;
    if (registryFile?.type !== 'file' || registryFile?.encoding !== 'base64') return 'unknown';
    const registry = parseRegistryYaml(Buffer.from(
      String(registryFile.content || '').replace(/\s/g, ''), 'base64',
    ).toString('utf8'));
    if (!registry?.agents || typeof registry.agents !== 'object') return 'unknown';
    const jobs = await withRetry(() => github.paginate(
      github.rest.actions.listJobsForWorkflowRunAttempt, {
      owner, repo,
      run_id: Number(runId), attempt_number: Number(runAttempt), per_page: 100,
      }), { github, maxRetries: 2, task: 'keepalive-worker-evidence' });
    return classifyWorkerExecution(jobs, registry);
  } catch (_) {
    return 'unknown';
  }
}

// A cancelled attempt that never created a job prepared no authority receipt and marked no
// keepalive state running: every such write happens inside a job. This is the ONLY unknown
// that the reporter may treat as not applicable. The proof is exact and positive:
//   - the attempt API returns the same run id, attempt number and head SHA;
//   - that attempt is completed with conclusion 'cancelled';
//   - the complete jobs listing for that attempt is an empty array.
// A job of any kind, any other conclusion, a mismatch, or an API error is 'unproven', and
// the reporter keeps failing closed. Burst label events cancel pending agents-81 runs this
// way: 10 of 10 sampled cancelled agents-81 runs in Manager-Database had 0 jobs (2026-11-28).
function classifyCancelledBeforeStart(attempt, jobs, { runId, runAttempt, runHeadSha }) {
  if (!attempt || typeof attempt !== 'object') return 'unproven';
  if (Number(attempt.id) !== Number(runId) ||
      Number(attempt.run_attempt) !== Number(runAttempt) ||
      String(attempt.head_sha || '') !== String(runHeadSha || '')) return 'unproven';
  if (attempt.status !== 'completed' || attempt.conclusion !== 'cancelled') return 'unproven';
  if (!Array.isArray(jobs) || jobs.length !== 0) return 'unproven';
  return 'cancelled-before-start';
}

async function getCancelledBeforeStartEvidence(github, owner, repo, runId, runAttempt, runHeadSha) {
  if (!Number.isInteger(Number(runId)) || Number(runId) <= 0 ||
      !Number.isInteger(Number(runAttempt)) || Number(runAttempt) <= 0 ||
      !/^[0-9a-f]{40}$/.test(String(runHeadSha || ''))) return 'unproven';
  try {
    const attemptResponse = await withRetry((client) => client.request(
      'GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}',
      { owner, repo, run_id: Number(runId), attempt_number: Number(runAttempt) },
    ), { github, maxRetries: 2, task: 'keepalive-origin-attempt' });
    const jobs = await withRetry(() => github.paginate(
      github.rest.actions.listJobsForWorkflowRunAttempt, {
        owner, repo,
        run_id: Number(runId), attempt_number: Number(runAttempt), per_page: 100,
      }), { github, maxRetries: 2, task: 'keepalive-origin-jobs' });
    return classifyCancelledBeforeStart(attemptResponse?.data, jobs,
      { runId, runAttempt, runHeadSha });
  } catch (_) {
    return 'unproven';
  }
}

module.exports = {
  classifyCancelledBeforeStart,
  classifyWorkerExecution,
  getCancelledBeforeStartEvidence,
  getWorkerExecutionEvidence,
};
