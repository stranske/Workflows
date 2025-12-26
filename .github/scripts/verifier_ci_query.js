'use strict';

const DEFAULT_WORKFLOWS = [
  { workflow_name: 'Gate', workflow_id: 'pr-00-gate.yml' },
  { workflow_name: 'Selftest CI', workflow_id: 'selftest-ci.yml' },
  { workflow_name: 'PR 11 - Minimal invariant CI', workflow_id: 'pr-11-ci-smoke.yml' },
];

function normalizeConclusion(run) {
  if (!run) {
    return 'not_found';
  }
  return run.conclusion || run.status || 'unknown';
}

async function fetchWorkflowRun({ github, owner, repo, workflowId, headShas, core }) {
  const candidates = Array.isArray(headShas)
    ? headShas.map((sha) => String(sha || '').trim()).filter(Boolean)
    : [];

  try {
    if (!candidates.length) {
      const response = await github.rest.actions.listWorkflowRuns({
        owner,
        repo,
        workflow_id: workflowId,
        per_page: 10,
      });
      const runs = response?.data?.workflow_runs || [];
      return runs[0] || null;
    }

    for (const sha of candidates) {
      const response = await github.rest.actions.listWorkflowRuns({
        owner,
        repo,
        workflow_id: workflowId,
        head_sha: sha,
        per_page: 10,
      });
      const runs = response?.data?.workflow_runs || [];
      if (!runs.length) {
        continue;
      }
      const exact = runs.find((run) => run.head_sha === sha);
      return exact || runs[0];
    }
    return null;
  } catch (error) {
    core?.warning?.(`Failed to fetch workflow runs for ${workflowId}: ${error.message}`);
    return null;
  }
}

async function queryVerifierCiResults({
  github,
  context,
  core,
  targetSha,
  targetShas,
  workflows,
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
    const run = await fetchWorkflowRun({
      github,
      owner,
      repo,
      workflowId,
      headShas: candidates,
      core,
    });
    results.push({
      workflow_name: workflowName,
      conclusion: normalizeConclusion(run),
      run_url: run?.html_url || '',
    });
  }

  return results;
}

module.exports = {
  DEFAULT_WORKFLOWS,
  queryVerifierCiResults,
};
