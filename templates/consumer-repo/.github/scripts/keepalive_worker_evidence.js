'use strict';

const { withRetry } = require('./github-api-with-retry.js');
const { loadAgentRegistry } = require('./agent_registry.js');

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

async function getWorkerExecutionEvidence(github, owner, repo, runId, runAttempt) {
  if (!Number.isInteger(Number(runId)) || Number(runId) <= 0 ||
      !Number.isInteger(Number(runAttempt)) || Number(runAttempt) <= 0) return 'unknown';
  try {
    const jobs = await withRetry(() => github.paginate(
      github.rest.actions.listJobsForWorkflowRunAttempt, {
      owner, repo,
      run_id: Number(runId), attempt_number: Number(runAttempt), per_page: 100,
      }), { github, maxRetries: 2, task: 'keepalive-worker-evidence' });
    return classifyWorkerExecution(jobs);
  } catch (_) {
    return 'unknown';
  }
}

module.exports = { classifyWorkerExecution, getWorkerExecutionEvidence };
