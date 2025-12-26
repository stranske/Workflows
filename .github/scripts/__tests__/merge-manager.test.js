'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  evaluatePullRequest,
  upsertDecisionComment,
  syncCiStatusLabel,
} = require('../merge_manager.js');

function createCore() {
  const outputs = {};
  const warnings = [];
  return {
    core: {
      setOutput(key, value) {
        outputs[key] = value;
      },
      warning(message) {
        warnings.push(message);
      },
    },
    outputs,
    warnings,
  };
}

function makeAllowlistResponse(payload) {
  const content = Buffer.from(JSON.stringify(payload), 'utf8').toString('base64');
  return { data: { encoding: 'base64', content } };
}

function createGithubStub({
  pr,
  files = [],
  allowlist = { patterns: [] },
  checks = { total_count: 0, check_runs: [] },
  statuses = { total_count: 0, statuses: [] },
  comments = [],
  removeLabelError,
} = {}) {
  const calls = {
    deleteComment: [],
    updateComment: [],
    createComment: [],
    addLabels: [],
    removeLabel: [],
  };

  const github = {
    calls,
    rest: {
      pulls: {
        async get() {
          return { data: pr };
        },
        async listFiles() {
          return { data: files };
        },
      },
      repos: {
        async getContent() {
          return makeAllowlistResponse(allowlist);
        },
        async getCombinedStatusForRef() {
          return { data: statuses };
        },
      },
      checks: {
        async listForRef() {
          return { data: checks };
        },
      },
      issues: {
        async listComments() {
          return { data: comments };
        },
        async deleteComment(payload) {
          calls.deleteComment.push(payload);
          return { status: 204 };
        },
        async updateComment(payload) {
          calls.updateComment.push(payload);
          return { status: 200 };
        },
        async createComment(payload) {
          calls.createComment.push(payload);
          return { data: { id: 500 } };
        },
        async addLabels(payload) {
          calls.addLabels.push(payload);
          return { status: 200 };
        },
        async removeLabel(payload) {
          calls.removeLabel.push(payload);
          if (removeLabelError) {
            const error = new Error(removeLabelError.message || 'remove label failed');
            if (removeLabelError.status) {
              error.status = removeLabelError.status;
            }
            throw error;
          }
          return { status: 200 };
        },
      },
    },
    async paginate(fn, params) {
      const response = await fn(params);
      return response?.data || [];
    },
  };

  return github;
}

function makePullRequest(overrides = {}) {
  return {
    number: 7,
    draft: false,
    labels: [],
    head: { sha: 'head-sha' },
    base: { sha: 'base-sha' },
    ...overrides,
  };
}

test('evaluatePullRequest marks eligible PRs for auto approval', async () => {
  const { core, outputs } = createCore();
  const github = createGithubStub({
    pr: makePullRequest({
      labels: [
        { name: 'automerge' },
        { name: 'from:codex' },
        { name: 'risk:low' },
        { name: 'ci:green' },
      ],
    }),
    files: [{ filename: 'docs/guide.md', changes: 5 }],
    allowlist: { patterns: ['docs/**'], max_lines_changed: 10 },
    checks: { total_count: 1, check_runs: [{ status: 'completed', conclusion: 'success' }] },
    statuses: { total_count: 1, statuses: [{ state: 'success' }] },
  });

  await evaluatePullRequest({
    github,
    core,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    config: {},
  });

  assert.equal(outputs.safe, 'true');
  assert.equal(outputs.should_auto_approve, 'true');
  assert.equal(outputs.should_run, 'true');
});

test('evaluatePullRequest flags allowlist mismatches as unsafe', async () => {
  const { core, outputs } = createCore();
  const github = createGithubStub({
    pr: makePullRequest({
      labels: [
        { name: 'automerge' },
        { name: 'from:codex' },
        { name: 'risk:low' },
      ],
    }),
    files: [{ filename: 'src/index.js', changes: 12 }],
    allowlist: { patterns: ['docs/**'], max_lines_changed: 50 },
  });

  await evaluatePullRequest({
    github,
    core,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    config: {},
  });

  assert.equal(outputs.allowlist_ok, 'false');
  assert.equal(outputs.safe, 'false');
  assert.equal(outputs.should_auto_approve, 'false');
});

test('evaluatePullRequest reports CI failures as blocking', async () => {
  const { core, outputs } = createCore();
  const github = createGithubStub({
    pr: makePullRequest({
      labels: [
        { name: 'automerge' },
        { name: 'from:codex' },
        { name: 'risk:low' },
      ],
    }),
    files: [{ filename: 'docs/guide.md', changes: 4 }],
    allowlist: { patterns: ['docs/**'], max_lines_changed: 10 },
    checks: { total_count: 1, check_runs: [{ status: 'completed', conclusion: 'failure' }] },
    statuses: { total_count: 0, statuses: [] },
  });

  await evaluatePullRequest({
    github,
    core,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    config: {},
  });

  assert.equal(outputs.ci_ready, 'false');
  assert.equal(outputs.ci_failing, 'true');
  assert.equal(outputs.label_gate_ok, 'false');
});

test('evaluatePullRequest enforces max_lines_changed limits', async () => {
  const { core, outputs } = createCore();
  const github = createGithubStub({
    pr: makePullRequest({
      labels: [
        { name: 'automerge' },
        { name: 'from:codex' },
        { name: 'risk:low' },
      ],
    }),
    files: [{ filename: 'docs/guide.md', changes: 25 }],
    allowlist: { patterns: ['docs/**'], max_lines_changed: 5 },
  });

  await evaluatePullRequest({
    github,
    core,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    config: {},
  });

  assert.equal(outputs.size_ok, 'false');
  assert.equal(outputs.safe, 'false');
});

test('upsertDecisionComment deletes existing decision comments when body is empty', async () => {
  const marker = '<!-- decision -->';
  const github = createGithubStub({
    pr: makePullRequest(),
    comments: [{ id: 101, body: `Status update\n${marker}` }],
  });

  const result = await upsertDecisionComment({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    marker,
    body: '',
  });

  assert.equal(result, 'deleted');
  assert.equal(github.calls.deleteComment.length, 1);
  assert.equal(github.calls.deleteComment[0].comment_id, 101);
});

test('upsertDecisionComment creates a new decision comment when none exists', async () => {
  const marker = '<!-- decision -->';
  const body = `Status update\n${marker}`;
  const github = createGithubStub({
    pr: makePullRequest(),
    comments: [{ id: 55, body: 'Regular comment.' }],
  });

  const result = await upsertDecisionComment({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    marker,
    body,
  });

  assert.equal(result, 'created');
  assert.equal(github.calls.createComment.length, 1);
  assert.equal(github.calls.createComment[0].body, body);
});

test('upsertDecisionComment returns unchanged when the comment body matches', async () => {
  const marker = '<!-- decision -->';
  const body = `Status update\n${marker}`;
  const github = createGithubStub({
    pr: makePullRequest(),
    comments: [{ id: 101, body }],
  });

  const result = await upsertDecisionComment({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    marker,
    body,
  });

  assert.equal(result, 'unchanged');
  assert.equal(github.calls.updateComment.length, 0);
});

test('syncCiStatusLabel removes the CI label when no longer desired', async () => {
  const github = createGithubStub({ pr: makePullRequest() });

  const result = await syncCiStatusLabel({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    labelName: 'ci:green',
    desired: false,
    present: true,
  });

  assert.equal(result, 'removed');
  assert.equal(github.calls.removeLabel.length, 1);
  assert.equal(github.calls.removeLabel[0].name, 'ci:green');
});

test('syncCiStatusLabel adds the CI label when desired but missing', async () => {
  const github = createGithubStub({ pr: makePullRequest() });

  const result = await syncCiStatusLabel({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    labelName: 'ci:green',
    desired: true,
    present: false,
  });

  assert.equal(result, 'added');
  assert.equal(github.calls.addLabels.length, 1);
  assert.equal(github.calls.addLabels[0].labels[0], 'ci:green');
});

test('syncCiStatusLabel reports missing when label removal 404s', async () => {
  const github = createGithubStub({
    pr: makePullRequest(),
    removeLabelError: { status: 404 },
  });

  const result = await syncCiStatusLabel({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 7,
    labelName: 'ci:green',
    desired: false,
    present: true,
  });

  assert.equal(result, 'missing');
  assert.equal(github.calls.removeLabel.length, 1);
});
