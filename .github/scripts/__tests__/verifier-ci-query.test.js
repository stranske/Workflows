'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { queryVerifierCiResults } = require('../verifier_ci_query.js');

const buildGithubStub = ({
  runsByWorkflow = {},
  errorWorkflow = null,
  listWorkflowRunsHook = null,
} = {}) => ({
  rest: {
    actions: {
      async listWorkflowRuns({ workflow_id: workflowId, head_sha: headSha }) {
        if (errorWorkflow && workflowId === errorWorkflow) {
          const error = new Error('boom');
          error.status = 404;
          throw error;
        }
        if (listWorkflowRunsHook) {
          const hooked = await listWorkflowRunsHook({ workflow_id: workflowId, head_sha: headSha });
          if (hooked !== undefined) {
            return hooked;
          }
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
    error_category: '',
    error_message: '',
  });
  assert.deepEqual(results[1], {
    workflow_name: 'Selftest CI',
    conclusion: 'in_progress',
    run_url: 'selftest-url',
    error_category: '',
    error_message: '',
  });
  assert.deepEqual(results[2], {
    workflow_name: 'PR 11',
    conclusion: 'not_found',
    run_url: '',
    error_category: '',
    error_message: '',
  });
});

test('queryVerifierCiResults supports workflowId/workflowName aliases', async () => {
  const github = buildGithubStub({
    runsByWorkflow: {
      'selftest-ci.yml': [
        { head_sha: 'alias-sha', conclusion: 'success', html_url: 'selftest-alias-url' },
      ],
    },
  });
  const context = { repo: { owner: 'octo', repo: 'workflows' } };
  const workflows = [
    { workflowId: 'selftest-ci.yml', workflowName: 'Selftest CI' },
  ];

  const results = await queryVerifierCiResults({
    github,
    context,
    targetSha: 'alias-sha',
    workflows,
  });

  assert.deepEqual(results, [
    {
      workflow_name: 'Selftest CI',
      conclusion: 'success',
      run_url: 'selftest-alias-url',
      error_category: '',
      error_message: '',
    },
  ]);
});

test('queryVerifierCiResults treats query errors as api_error', async () => {
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
      conclusion: 'api_error',
      run_url: '',
      error_category: 'resource',
      error_message: 'listWorkflowRuns:pr-00-gate.yml failed after 1 attempt(s): boom',
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
      error_category: '',
      error_message: '',
    },
  ]);
});

test('queryVerifierCiResults falls back to secondary SHA when primary has no runs', async () => {
  const headShas = [];
  const github = buildGithubStub({
    listWorkflowRunsHook: ({ head_sha: headSha }) => {
      headShas.push(headSha);
      if (headSha === 'merge-sha') {
        return { data: { workflow_runs: [] } };
      }
      if (headSha === 'head-sha') {
        return {
          data: {
            workflow_runs: [
              { head_sha: 'head-sha', conclusion: 'success', html_url: 'head-url' },
            ],
          },
        };
      }
      return { data: { workflow_runs: [] } };
    },
  });
  const context = { repo: { owner: 'octo', repo: 'workflows' } };
  const workflows = [{ workflow_name: 'Gate', workflow_id: 'pr-00-gate.yml' }];

  const results = await queryVerifierCiResults({
    github,
    context,
    targetShas: ['merge-sha', 'head-sha'],
    workflows,
  });

  assert.deepEqual(results, [
    {
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'head-url',
      error_category: '',
      error_message: '',
    },
  ]);
  assert.deepEqual(headShas, ['merge-sha', 'head-sha']);
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
      error_category: '',
      error_message: '',
    },
    {
      workflow_name: 'Selftest CI',
      conclusion: 'failure',
      run_url: 'selftest-default-url',
      error_category: '',
      error_message: '',
    },
    {
      workflow_name: 'PR 11 - Minimal invariant CI',
      conclusion: 'success',
      run_url: 'pr11-default-url',
      error_category: '',
      error_message: '',
    },
  ]);
});

test('queryVerifierCiResults uses API url when html_url is missing', async () => {
  const github = buildGithubStub({
    runsByWorkflow: {
      'pr-00-gate.yml': [{ head_sha: 'target-sha', conclusion: 'success', url: 'api-url' }],
    },
  });
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
      conclusion: 'success',
      run_url: 'api-url',
      error_category: '',
      error_message: '',
    },
  ]);
});

test('queryVerifierCiResults treats completed runs without conclusion as unknown', async () => {
  const github = buildGithubStub({
    runsByWorkflow: {
      'pr-00-gate.yml': [{ head_sha: 'target-sha', status: 'completed', html_url: 'gate-url' }],
    },
  });
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
      conclusion: 'unknown',
      run_url: 'gate-url',
      error_category: '',
      error_message: '',
    },
  ]);
});

test('queryVerifierCiResults retries transient errors and returns success', async () => {
  let attempts = 0;
  const warnings = [];
  const github = buildGithubStub({
    listWorkflowRunsHook: async () => {
      attempts += 1;
      if (attempts < 3) {
        const error = new Error('Service unavailable');
        error.status = 503;
        throw error;
      }
      return {
        data: {
          workflow_runs: [
            { head_sha: 'retry-sha', conclusion: 'success', html_url: 'retry-url' },
          ],
        },
      };
    },
  });
  const context = { repo: { owner: 'octo', repo: 'workflows' } };
  const workflows = [{ workflow_name: 'Gate', workflow_id: 'pr-00-gate.yml' }];

  const results = await queryVerifierCiResults({
    github,
    context,
    targetSha: 'retry-sha',
    workflows,
    core: { warning: (message) => warnings.push(String(message)) },
    retryOptions: { sleepFn: async () => {} },
  });

  assert.equal(attempts, 3);
  assert.equal(warnings.length, 2);
  assert.deepEqual(results, [
    {
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'retry-url',
      error_category: '',
      error_message: '',
    },
  ]);
});

test('queryVerifierCiResults returns api_error after max retries', async () => {
  let attempts = 0;
  const warnings = [];
  const github = buildGithubStub({
    listWorkflowRunsHook: async () => {
      attempts += 1;
      const error = new Error('timeout');
      error.status = 504;
      throw error;
    },
  });
  const context = { repo: { owner: 'octo', repo: 'workflows' } };
  const workflows = [{ workflow_name: 'Gate', workflow_id: 'pr-00-gate.yml' }];

  const results = await queryVerifierCiResults({
    github,
    context,
    targetSha: 'retry-sha',
    workflows,
    core: { warning: (message) => warnings.push(String(message)) },
    retryOptions: { sleepFn: async () => {} },
  });

  assert.equal(attempts, 4);
  assert.equal(warnings.length, 4);
  assert.deepEqual(results, [
    {
      workflow_name: 'Gate',
      conclusion: 'api_error',
      run_url: '',
      error_category: 'transient',
      error_message: 'listWorkflowRuns:pr-00-gate.yml failed after 4 attempt(s): timeout',
    },
  ]);
});
