'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const { buildVerifierContext } = require('../agents_verifier_context.js');

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

const buildGithubStub = ({ prDetails, prsForSha = [], closingIssues = [] } = {}) => ({
  rest: {
    pulls: {
      async get() {
        return { data: prDetails };
      },
    },
    repos: {
      async listPullRequestsAssociatedWithCommit() {
        return { data: prsForSha };
      },
    },
  },
  async graphql() {
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

test('buildVerifierContext writes verifier context with linked issues', async () => {
  const core = buildCore();
  const prDetails = {
    number: 321,
    title: 'Add tests',
    body: '## Scope\nTesting\n## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] ok',
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
        body: '## Tasks\n- [ ] item\n## Acceptance Criteria\n- [x] done',
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
        body: '## Acceptance Criteria\n- [ ] review',
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
