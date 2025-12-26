'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const { buildVerifierContext } = require('../agents_verifier_context.js');

const fixturesDir = path.join(__dirname, 'fixtures');
const prBodyFixture = fs.readFileSync(path.join(fixturesDir, 'pr-body.md'), 'utf8');
const issueBodyOpen = fs.readFileSync(path.join(fixturesDir, 'issue-body-open.md'), 'utf8');
const issueBodyClosed = fs.readFileSync(path.join(fixturesDir, 'issue-body-closed.md'), 'utf8');

const buildCore = () => {
  const outputs = {};
  const notices = [];
  const warnings = [];
  return {
    outputs,
    notices,
    warnings,
    setOutput(key, value) {
      outputs[key] = value;
    },
    notice(message) {
      notices.push(message);
    },
    warning(message) {
      warnings.push(message);
    },
  };
};

const buildGithubStub = ({
  prDetails,
  prsForSha = [],
  closingIssues = [],
  listError = null,
  graphqlError = null,
  runsByWorkflow = {},
  listWorkflowRunsHook = null,
} = {}) => ({
  rest: {
    actions: {
      async listWorkflowRuns({ workflow_id: workflowId, head_sha: headSha }) {
        if (listWorkflowRunsHook) {
          const hooked = await listWorkflowRunsHook({ workflow_id: workflowId, head_sha: headSha });
          if (hooked !== undefined) {
            return hooked;
          }
        }
        return { data: { workflow_runs: runsByWorkflow[workflowId] || [] } };
      },
    },
    pulls: {
      async get() {
        return { data: prDetails };
      },
    },
    repos: {
      async listPullRequestsAssociatedWithCommit() {
        if (listError) {
          throw listError;
        }
        return { data: prsForSha };
      },
    },
  },
  async graphql() {
    if (graphqlError) {
      throw graphqlError;
    }
    return {
      repository: {
        pullRequest: {
          closingIssuesReferences: {
            nodes: closingIssues,
          },
        },
      },
    };
  },
});

test('buildVerifierContext skips when pull request is not merged', async () => {
  const core = buildCore();
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: { pull_request: { merged: false } },
    sha: 'sha-1',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub(),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.deepEqual(result.ciResults, []);
  assert.equal(core.outputs.should_run, 'false');
  assert.ok(core.outputs.skip_reason.includes('not merged'));
});

test('buildVerifierContext skips when base branch mismatches default', async () => {
  const core = buildCore();
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 99,
        base: { ref: 'dev' },
        html_url: 'https://example.com/pr/99',
      },
    },
    sha: 'sha-2',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub(),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.pr_number, '99');
  assert.ok(core.outputs.skip_reason.includes('base ref'));
});

test('buildVerifierContext skips forked pull requests', async () => {
  const core = buildCore();
  const prDetails = {
    number: 77,
    title: 'Forked change',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/77',
    merge_commit_sha: 'merge-sha-77',
    base: {
      ref: 'main',
      repo: { full_name: 'octo/workflows', owner: { login: 'octo' } },
    },
    head: {
      sha: 'head-sha-77',
      repo: { full_name: 'forker/workflows', owner: { login: 'forker' }, fork: true },
    },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 77,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/77',
      },
    },
    sha: 'sha-77',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub({ prDetails }),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.should_run, 'false');
  assert.equal(core.outputs.pr_number, '77');
  assert.ok(core.outputs.skip_reason.includes('fork'));
});

test('buildVerifierContext writes verifier context with linked issues', async () => {
  const core = buildCore();
  const prDetails = {
    number: 321,
    title: 'Add tests',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/321',
    merge_commit_sha: 'merge-sha',
    base: { ref: 'main' },
    head: { sha: 'head-sha' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 321,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/321',
      },
    },
    sha: 'sha-3',
  };
  const github = buildGithubStub({
    prDetails,
    closingIssues: [
      {
        number: 456,
        title: 'Issue 456',
        body: issueBodyOpen,
        state: 'OPEN',
        url: 'https://example.com/issues/456',
      },
      {
        number: 456,
        title: 'Duplicate',
        body: '',
        state: 'OPEN',
        url: 'https://example.com/issues/456',
      },
      {
        number: 789,
        title: 'Issue 789',
        body: issueBodyClosed,
        state: 'CLOSED',
        url: 'https://example.com/issues/789',
      },
    ],
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'merge-sha', conclusion: 'success', html_url: 'https://ci/gate' },
      ],
      'selftest-ci.yml': [
        { head_sha: 'merge-sha', conclusion: 'success', html_url: 'https://ci/selftest' },
      ],
      'pr-11-ci-smoke.yml': [
        { head_sha: 'merge-sha', conclusion: 'success', html_url: 'https://ci/pr11' },
      ],
    },
  });

  const result = await buildVerifierContext({ github, context, core });
  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  const markdown = fs.readFileSync(contextPath, 'utf8');
  const ciResults = JSON.parse(core.outputs.ci_results);

  assert.equal(result.shouldRun, true);
  assert.equal(result.ciResults.length, 3);
  assert.equal(core.outputs.should_run, 'true');
  assert.equal(core.outputs.issue_numbers, JSON.stringify([456, 789]));
  assert.equal(ciResults.length, 3);
  assert.equal(ciResults[0].workflow_name, 'Gate');
  assert.equal(ciResults[0].conclusion, 'success');
  assert.ok(markdown.includes('Pull request #321'));
  assert.ok(markdown.includes('Issue #456'));
  assert.ok(markdown.includes('Issue #789'));
  assert.ok(markdown.includes('## CI Verification'));
  assert.ok(markdown.includes('Use these CI results to verify test-related criteria'));
  assert.ok(markdown.includes('| Workflow | Conclusion | Run |'));
  assert.ok(markdown.includes('| Gate | success | [run](https://ci/gate) |'));
  assert.ok(markdown.includes('| Selftest CI | success | [run](https://ci/selftest) |'));
  assert.ok(markdown.includes('| PR 11 - Minimal invariant CI | success | [run](https://ci/pr11) |'));

  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext queries CI runs with merge commit SHA', async () => {
  const core = buildCore();
  const prDetails = {
    number: 222,
    title: 'Merge commit',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/222',
    merge_commit_sha: 'merge-sha-222',
    base: { ref: 'main' },
    head: { sha: 'head-sha-222' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 222,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/222',
      },
    },
    sha: 'sha-222',
  };
  const headShas = [];
  const github = buildGithubStub({
    prDetails,
    listWorkflowRunsHook: ({ head_sha: headSha }) => {
      headShas.push(headSha);
    },
  });

  const result = await buildVerifierContext({ github, context, core });

  assert.equal(result.shouldRun, true);
  assert.ok(headShas.length > 0);
  assert.equal(headShas[0], 'merge-sha-222');
  assert.ok(headShas.includes('merge-sha-222'));

  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext selects CI results for the merge commit SHA', async () => {
  const core = buildCore();
  const prDetails = {
    number: 333,
    title: 'Merge commit selection',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/333',
    merge_commit_sha: 'merge-sha-333',
    base: { ref: 'main' },
    head: { sha: 'head-sha-333' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 333,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/333',
      },
    },
    sha: 'sha-333',
  };
  const headShas = [];
  const github = buildGithubStub({
    prDetails,
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'other-sha', conclusion: 'failure', html_url: 'https://ci/gate-old' },
        { head_sha: 'merge-sha-333', conclusion: 'success', html_url: 'https://ci/gate-merge' },
      ],
      'selftest-ci.yml': [
        { head_sha: 'merge-sha-333', conclusion: 'success', html_url: 'https://ci/selftest-merge' },
      ],
      'pr-11-ci-smoke.yml': [
        { head_sha: 'merge-sha-333', conclusion: 'success', html_url: 'https://ci/pr11-merge' },
      ],
    },
    listWorkflowRunsHook: ({ head_sha: headSha }) => {
      headShas.push(headSha);
    },
  });

  const result = await buildVerifierContext({ github, context, core });

  assert.equal(result.shouldRun, true);
  assert.ok(headShas.length > 0);
  assert.ok(headShas.every((sha) => sha === 'merge-sha-333'));
  assert.deepEqual(result.ciResults, [
    {
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'https://ci/gate-merge',
    },
    {
      workflow_name: 'Selftest CI',
      conclusion: 'success',
      run_url: 'https://ci/selftest-merge',
    },
    {
      workflow_name: 'PR 11 - Minimal invariant CI',
      conclusion: 'success',
      run_url: 'https://ci/pr11-merge',
    },
  ]);

  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext falls back to head SHA when merge runs are missing', async () => {
  const core = buildCore();
  const prDetails = {
    number: 555,
    title: 'Merge commit fallback',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/555',
    merge_commit_sha: 'merge-sha-555',
    base: { ref: 'main' },
    head: { sha: 'head-sha-555' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 555,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/555',
      },
    },
    sha: 'sha-555',
  };
  const calls = [];
  const workflowIds = ['pr-00-gate.yml', 'selftest-ci.yml', 'pr-11-ci-smoke.yml'];
  const github = buildGithubStub({
    prDetails,
    listWorkflowRunsHook: ({ workflow_id: workflowId, head_sha: headSha }) => {
      calls.push(`${workflowId}:${headSha}`);
      if (headSha === 'merge-sha-555') {
        return { data: { workflow_runs: [] } };
      }
      if (headSha === 'head-sha-555') {
        return {
          data: {
            workflow_runs: [
              {
                head_sha: 'head-sha-555',
                conclusion: 'success',
                html_url: `https://ci/${workflowId}`,
              },
            ],
          },
        };
      }
      return { data: { workflow_runs: [] } };
    },
  });

  const result = await buildVerifierContext({ github, context, core });

  assert.equal(result.shouldRun, true);
  assert.deepEqual(result.ciResults, [
    {
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'https://ci/pr-00-gate.yml',
    },
    {
      workflow_name: 'Selftest CI',
      conclusion: 'success',
      run_url: 'https://ci/selftest-ci.yml',
    },
    {
      workflow_name: 'PR 11 - Minimal invariant CI',
      conclusion: 'success',
      run_url: 'https://ci/pr-11-ci-smoke.yml',
    },
  ]);
  for (const workflowId of workflowIds) {
    assert.ok(calls.includes(`${workflowId}:merge-sha-555`));
    assert.ok(calls.includes(`${workflowId}:head-sha-555`));
  }

  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext uses merge commit SHA for push events', async () => {
  const core = buildCore();
  const prDetails = {
    number: 444,
    title: 'Push merge commit',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/444',
    merge_commit_sha: 'merge-sha-444',
    base: { ref: 'main' },
    head: { sha: 'head-sha-444' },
  };
  const context = {
    eventName: 'push',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      after: 'merge-sha-444',
      repository: { default_branch: 'main' },
    },
    sha: 'merge-sha-444',
  };
  const headShas = [];
  const github = buildGithubStub({
    prDetails,
    prsForSha: [
      {
        number: 444,
        merged_at: '2024-01-01T00:00:00Z',
        merge_commit_sha: 'merge-sha-444',
      },
    ],
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'merge-sha-444', conclusion: 'success', html_url: 'https://ci/gate-push' },
      ],
      'selftest-ci.yml': [
        {
          head_sha: 'merge-sha-444',
          conclusion: 'success',
          html_url: 'https://ci/selftest-push',
        },
      ],
      'pr-11-ci-smoke.yml': [
        { head_sha: 'merge-sha-444', conclusion: 'success', html_url: 'https://ci/pr11-push' },
      ],
    },
    listWorkflowRunsHook: ({ head_sha: headSha }) => {
      headShas.push(headSha);
    },
  });

  const result = await buildVerifierContext({ github, context, core });

  assert.equal(result.shouldRun, true);
  assert.ok(headShas.length > 0);
  assert.ok(headShas.every((sha) => sha === 'merge-sha-444'));
  assert.deepEqual(result.ciResults, [
    {
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'https://ci/gate-push',
    },
    {
      workflow_name: 'Selftest CI',
      conclusion: 'success',
      run_url: 'https://ci/selftest-push',
    },
    {
      workflow_name: 'PR 11 - Minimal invariant CI',
      conclusion: 'success',
      run_url: 'https://ci/pr11-push',
    },
  ]);

  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext skips push events without a commit SHA', async () => {
  const core = buildCore();
  const context = {
    eventName: 'push',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {},
    sha: '',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub(),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.should_run, 'false');
  assert.ok(core.outputs.skip_reason.includes('Missing commit SHA'));
});

test('buildVerifierContext skips push events with no associated PR', async () => {
  const core = buildCore();
  const context = {
    eventName: 'push',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: { after: 'sha-9' },
    sha: 'sha-9',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub({ prsForSha: [] }),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.should_run, 'false');
  assert.ok(core.outputs.skip_reason.includes('No pull request associated'));
});

test('buildVerifierContext skips push events when PR lookup fails', async () => {
  const core = buildCore();
  const context = {
    eventName: 'push',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: { after: 'sha-10' },
    sha: 'sha-10',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub({ listError: new Error('boom') }),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.should_run, 'false');
  assert.ok(core.outputs.skip_reason.includes('Unable to resolve pull request'));
  assert.equal(core.warnings.length, 1);
});
