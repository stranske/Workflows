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

async function fetchWorkflowRun({ github, owner, repo, workflowId, headSha, core }) {
  try {
    const response = await github.rest.actions.listWorkflowRuns({
      owner,
      repo,
      workflow_id: workflowId,
      head_sha: headSha || undefined,
      per_page: 10,
    });
    const runs = response?.data?.workflow_runs || [];
    if (!runs.length) {
      return null;
    }
    if (!headSha) {
      return runs[0];
    }
    const exact = runs.find((run) => run.head_sha === headSha);
    return exact || runs[0];
  } catch (error) {
    core?.warning?.(`Failed to fetch workflow runs for ${workflowId}: ${error.message}`);
    return null;
  }
}

async function queryVerifierCiResults({ github, context, core, targetSha, workflows } = {}) {
  const { owner, repo } = context.repo;
  const headSha = String(targetSha || '').trim();
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
      headSha,
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
