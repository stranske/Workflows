'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { queryVerifierCiResults } = require('../verifier_ci_query.js');

const buildGithubStub = ({ runsByWorkflow = {}, errorWorkflow = null } = {}) => ({
  rest: {
    actions: {
      async listWorkflowRuns({ workflow_id: workflowId }) {
        if (errorWorkflow && workflowId === errorWorkflow) {
          throw new Error('boom');
        }
        return { data: { workflow_runs: runsByWorkflow[workflowId] || [] } };
      },
    },
  },
});

test('queryVerifierCiResults selects runs and reports conclusions', async () => {
  const github = buildGithubStub({
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'target-sha', conclusion: 'success', html_url: 'gate-url' },
      ],
      'selftest-ci.yml': [
        { head_sha: 'other-sha', conclusion: 'failure', html_url: 'old-url' },
        { head_sha: 'target-sha', status: 'in_progress', html_url: 'selftest-url' },
      ],
    },
  });
  const context = { repo: { owner: 'octo', repo: 'workflows' } };
  const workflows = [
    { workflow_name: 'Gate', workflow_id: 'pr-00-gate.yml' },
    { workflow_name: 'Selftest CI', workflow_id: 'selftest-ci.yml' },
    { workflow_name: 'PR 11', workflow_id: 'pr-11-ci-smoke.yml' },
  ];

  const results = await queryVerifierCiResults({
    github,
    context,
    targetSha: 'target-sha',
    workflows,
  });

  assert.equal(results.length, 3);
  assert.deepEqual(results[0], {
    workflow_name: 'Gate',
    conclusion: 'success',
    run_url: 'gate-url',
  });
  assert.deepEqual(results[1], {
    workflow_name: 'Selftest CI',
    conclusion: 'in_progress',
    run_url: 'selftest-url',
  });
  assert.deepEqual(results[2], {
    workflow_name: 'PR 11',
    conclusion: 'not_found',
    run_url: '',
  });
});

test('queryVerifierCiResults treats query errors as not_found', async () => {
  const github = buildGithubStub({ errorWorkflow: 'pr-00-gate.yml' });
  const context = { repo: { owner: 'octo', repo: 'workflows' } };
  const workflows = [{ workflow_name: 'Gate', workflow_id: 'pr-00-gate.yml' }];

  const results = await queryVerifierCiResults({
    github,
    context,
    targetSha: 'target-sha',
    workflows,
  });

  assert.deepEqual(results, [
    {
      workflow_name: 'Gate',
      conclusion: 'not_found',
      run_url: '',
    },
  ]);
});

test('queryVerifierCiResults uses latest run when no target SHA is provided', async () => {
  const github = buildGithubStub({
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'latest-sha', conclusion: 'success', html_url: 'gate-latest-url' },
        { head_sha: 'older-sha', conclusion: 'failure', html_url: 'gate-old-url' },
      ],
    },
  });
  const context = { repo: { owner: 'octo', repo: 'workflows' } };
  const workflows = [{ workflow_name: 'Gate', workflow_id: 'pr-00-gate.yml' }];

  const results = await queryVerifierCiResults({
    github,
    context,
    workflows,
  });

  assert.deepEqual(results, [
    {
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'gate-latest-url',
    },
  ]);
});

test('queryVerifierCiResults falls back to default workflows', async () => {
  const github = buildGithubStub({
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'default-sha', conclusion: 'success', html_url: 'gate-default-url' },
      ],
      'selftest-ci.yml': [
        { head_sha: 'default-sha', conclusion: 'failure', html_url: 'selftest-default-url' },
      ],
      'pr-11-ci-smoke.yml': [
        { head_sha: 'default-sha', conclusion: 'success', html_url: 'pr11-default-url' },
      ],
    },
  });
  const context = { repo: { owner: 'octo', repo: 'workflows' } };

  const results = await queryVerifierCiResults({
    github,
    context,
    targetSha: 'default-sha',
  });

  assert.deepEqual(results, [
    {
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'gate-default-url',
    },
    {
      workflow_name: 'Selftest CI',
      conclusion: 'failure',
      run_url: 'selftest-default-url',
    },
    {
      workflow_name: 'PR 11 - Minimal invariant CI',
      conclusion: 'success',
      run_url: 'pr11-default-url',
    },
  ]);
});
