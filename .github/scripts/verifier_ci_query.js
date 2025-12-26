'use strict';

const { classifyError, ERROR_CATEGORIES } = require('./error_classifier');

const DEFAULT_WORKFLOWS = [
  { workflow_name: 'Gate', workflow_id: 'pr-00-gate.yml' },
  { workflow_name: 'Selftest CI', workflow_id: 'selftest-ci.yml' },
  { workflow_name: 'PR 11 - Minimal invariant CI', workflow_id: 'pr-11-ci-smoke.yml' },
];

const DEFAULT_RETRY_DELAYS_MS = [1000, 2000, 4000];
const DEFAULT_MAX_RETRIES = DEFAULT_RETRY_DELAYS_MS.length;

function normalizeConclusion(run) {
  if (!run) {
    return 'not_found';
  }
  if (run.conclusion) {
    return run.conclusion;
  }
  if (run.status && run.status !== 'completed') {
    return run.status;
  }
  return 'unknown';
}

function getErrorCategory(error) {
  if (error && error.category) {
    return error.category;
  }
  return classifyError(error).category;
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function buildRetryError(error, category, label, attempts) {
  const message = error?.message || 'Unknown error';
  const retryError = new Error(`${label} failed after ${attempts} attempt(s): ${message}`);
  retryError.cause = error;
  retryError.category = category;
  return retryError;
}

async function withRetry(apiCall, options = {}) {
  const {
    label = 'GitHub API call',
    delays = DEFAULT_RETRY_DELAYS_MS,
    core = null,
    sleepFn = sleep,
  } = options;

  let lastError = null;
  for (let attempt = 0; attempt <= delays.length; attempt += 1) {
    try {
      return await apiCall();
    } catch (error) {
      lastError = error;
      const category = getErrorCategory(error);
      const canRetry = category === ERROR_CATEGORIES.transient && attempt < delays.length;

      if (!canRetry) {
        throw buildRetryError(error, category, label, attempt + 1);
      }

      const delayMs = delays[attempt];
      if (core?.warning) {
        core.warning(
          `Retrying ${label}; category=${category} attempt=${attempt + 1}/${delays.length + 1} delayMs=${delayMs}`
        );
      }
      await sleepFn(delayMs);
    }
  }

  throw buildRetryError(lastError || new Error('Unknown error'), ERROR_CATEGORIES.unknown, label, delays.length + 1);
}

async function fetchWorkflowRun({
  github,
  owner,
  repo,
  workflowId,
  headShas,
  core,
  retryOptions,
}) {
  const candidates = Array.isArray(headShas)
    ? headShas.map((sha) => String(sha || '').trim()).filter(Boolean)
    : [];

  try {
    if (!candidates.length) {
      const response = await withRetry(
        () =>
          github.rest.actions.listWorkflowRuns({
            owner,
            repo,
            workflow_id: workflowId,
            per_page: 10,
          }),
        { label: `listWorkflowRuns:${workflowId}`, core, ...retryOptions }
      );
      const runs = response?.data?.workflow_runs || [];
      return { run: runs[0] || null, error: null };
    }

    for (const sha of candidates) {
      const response = await withRetry(
        () =>
          github.rest.actions.listWorkflowRuns({
            owner,
            repo,
            workflow_id: workflowId,
            head_sha: sha,
            per_page: 10,
          }),
        { label: `listWorkflowRuns:${workflowId}`, core, ...retryOptions }
      );
      const runs = response?.data?.workflow_runs || [];
      if (!runs.length) {
        continue;
      }
      const exact = runs.find((run) => run.head_sha === sha);
      return { run: exact || runs[0], error: null };
    }
    return { run: null, error: null };
  } catch (error) {
    const category = getErrorCategory(error);
    core?.warning?.(
      `Failed to fetch workflow runs for ${workflowId}: ${error.message}; category=${category}`
    );
    return { run: null, error: { category, message: error.message } };
  }
}

async function queryVerifierCiResults({
  github,
  context,
  core,
  targetSha,
  targetShas,
  workflows,
  retryOptions,
} = {}) {
  const { owner, repo } = context.repo;
  const candidates = [];
  if (Array.isArray(targetShas)) {
    for (const sha of targetShas) {
      const normalized = String(sha || '').trim();
      if (normalized && !candidates.includes(normalized)) {
        candidates.push(normalized);
      }
    }
  }
  const normalizedTarget = String(targetSha || '').trim();
  if (normalizedTarget && !candidates.includes(normalizedTarget)) {
    candidates.push(normalizedTarget);
  }
  const targets = Array.isArray(workflows) && workflows.length ? workflows : DEFAULT_WORKFLOWS;
  const results = [];

  for (const target of targets) {
    const workflowId = target.workflow_id || target.workflowId;
    const workflowName = target.workflow_name || target.workflowName || workflowId || 'workflow';
    const { run, error } = await fetchWorkflowRun({
      github,
      owner,
      repo,
      workflowId,
      headShas: candidates,
      core,
      retryOptions,
    });
    const conclusion = error ? 'api_error' : normalizeConclusion(run);
    results.push({
      workflow_name: workflowName,
      conclusion,
      run_url: run?.html_url || run?.url || '',
      error_category: error?.category || '',
      error_message: error?.message || '',
    });
  }

  return results;
}

module.exports = {
  DEFAULT_WORKFLOWS,
  queryVerifierCiResults,
};
