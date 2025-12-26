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
} = {}) => ({
  rest: {
    actions: {
      async listWorkflowRuns() {
        return { data: { workflow_runs: [] } };
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
  });

  const result = await buildVerifierContext({ github, context, core });
  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  const markdown = fs.readFileSync(contextPath, 'utf8');

  assert.equal(result.shouldRun, true);
  assert.equal(core.outputs.should_run, 'true');
  assert.equal(core.outputs.issue_numbers, JSON.stringify([456, 789]));
  assert.ok(markdown.includes('Pull request #321'));
  assert.ok(markdown.includes('Issue #456'));
  assert.ok(markdown.includes('Issue #789'));

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
