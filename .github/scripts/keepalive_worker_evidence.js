'use strict';

const { withRetry } = require('./github-api-with-retry.js');

// Only an exact originating attempt can prove that its worker did not start.
// A missing or incomplete jobs response is unknown, never a safe refund.
const WORKER_STEPS = new Set(['Run Codex', 'Run Claude', 'Run Cursor', 'Run Gemini']);
const WORKER_JOBS = /Keepalive next task \((?:Codex|Claude|Cursor|Gemini)\)/;

function classifyWorkerExecution(jobs) {
  if (!Array.isArray(jobs)) return 'unknown';
  const workers = jobs.filter((job) => WORKER_JOBS.test(String(job?.name || '')));
  if (workers.length === 0) return 'unknown';
  for (const job of workers) {
    if (job.status !== 'completed') return 'unknown';
    if (job.conclusion === 'skipped') continue;
    const steps = job.steps;
    if (!Array.isArray(steps)) return 'unknown';
    const workerStep = steps.find((step) => WORKER_STEPS.has(String(step?.name || '')));
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
      run_id: Number(runId), run_attempt: Number(runAttempt), per_page: 100,
      }), { github, maxRetries: 2, task: 'keepalive-worker-evidence' });
    return classifyWorkerExecution(jobs);
  } catch (_) {
    return 'unknown';
  }
}

module.exports = { classifyWorkerExecution, getWorkerExecutionEvidence };
