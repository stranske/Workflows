'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

function createSummary() {
  return {
    entries: [],
    written: false,
    addHeading(text) {
      this.entries.push({ type: 'heading', text });
      return this;
    },
    addTable(rows) {
      this.entries.push({ type: 'table', rows });
      return this;
    },
    addRaw(text) {
      this.entries.push({ type: 'raw', text });
      return this;
    },
    addEOL() {
      this.entries.push({ type: 'eol' });
      return this;
    },
    async write() {
      this.written = true;
    },
  };
}

function createCore() {
  const outputs = {};
  const warnings = [];
  const summary = createSummary();
  const core = {
    summary,
    setOutput(key, value) {
      outputs[key] = value;
    },
    warning(message) {
      warnings.push(message);
    },
  };
  return { core, outputs, warnings, summary };
}

function mergeState(base, updates) {
  const next = { ...base };
  for (const [key, value] of Object.entries(updates || {})) {
    if (value && typeof value === 'object' && !Array.isArray(value) && typeof next[key] === 'object') {
      next[key] = { ...next[key], ...value };
    } else {
      next[key] = value;
    }
  }
  return next;
}

function createStateManagerStub({ initialState = {}, commentId = 0, commentUrl = '' } = {}) {
  let state = { ...initialState };
  let currentCommentId = commentId;
  let currentCommentUrl = commentUrl;
  const saves = [];

  const save = async (updates = {}) => {
    state = mergeState(state, updates);
    if (!currentCommentId) {
      currentCommentId = 901;
      currentCommentUrl = 'https://example.com/state/901';
    }
    saves.push({ updates, state: { ...state } });
    return { state: { ...state }, commentId: currentCommentId, commentUrl: currentCommentUrl };
  };

  return {
    saves,
    getManager: async () => ({
      state: { ...state },
      commentId: currentCommentId,
      commentUrl: currentCommentUrl,
      save,
    }),
  };
}

function loadRunnerWithStateManager(stubManager) {
  const statePath = require.resolve('../keepalive_state.js');
  const runnerPath = require.resolve('../keepalive_post_work.js');
  const stateModule = require(statePath);
  const original = stateModule.createKeepaliveStateManager;
  stateModule.createKeepaliveStateManager = stubManager;
  delete require.cache[runnerPath];
  const { runKeepalivePostWork } = require(runnerPath);
  return {
    runKeepalivePostWork,
    restore() {
      stateModule.createKeepaliveStateManager = original;
      delete require.cache[runnerPath];
    },
  };
}

function makeEnv(overrides = {}) {
  return {
    TRACE: 'trace-1',
    ROUND: '2',
    PR_NUMBER: '42',
    PR_BASE: 'main',
    PR_HEAD: 'feature/keepalive',
    PR_HEAD_SHA_PREV: '',
    AGENT_STATE: 'done',
    TTL_SHORT_MS: '0',
    POLL_SHORT_MS: '0',
    TTL_LONG_MS: '0',
    POLL_LONG_MS: '0',
    ...overrides,
  };
}

function makePull(overrides = {}) {
  return {
    head: { sha: 'abc123', ref: 'feature/keepalive', repo: { full_name: 'octo/demo', fork: false } },
    base: { ref: 'main', repo: { full_name: 'octo/demo' } },
    user: { login: 'octo-user' },
    ...overrides,
  };
}

function createGithubStub({ pull = makePull(), labels = [], updateBranchError } = {}) {
  const calls = {
    removeLabel: [],
    addLabels: [],
    createComment: [],
    createDispatchEvent: [],
    createWorkflowDispatch: [],
    updateBranch: [],
    reactions: [],
  };

  const github = {
    calls,
    rest: {
      pulls: {
        async get() {
          return { data: pull };
        },
        async updateBranch(payload) {
          calls.updateBranch.push(payload);
          if (updateBranchError) {
            const error = new Error(updateBranchError.message || 'update branch failed');
            if (updateBranchError.status) {
              error.status = updateBranchError.status;
            }
            throw error;
          }
          return { status: 202 };
        },
        async list() {
          return { data: [] };
        },
        async merge() {
          return { status: 200 };
        },
      },
      issues: {
        async listLabelsOnIssue() {
          return { data: labels };
        },
        async removeLabel(payload) {
          calls.removeLabel.push(payload);
          return { status: 204 };
        },
        async addLabels(payload) {
          calls.addLabels.push(payload);
          return { status: 200 };
        },
        async createComment({ body }) {
          const id = 400 + calls.createComment.length;
          const record = { id, html_url: `https://example.com/comment/${id}` };
          calls.createComment.push({ body, id });
          return { data: record };
        },
      },
      reactions: {
        async createForIssueComment(payload) {
          calls.reactions.push(payload);
          return { status: 200 };
        },
      },
      repos: {
        async createDispatchEvent(payload) {
          calls.createDispatchEvent.push(payload);
          return { status: 204 };
        },
      },
      actions: {
        async createWorkflowDispatch(payload) {
          calls.createWorkflowDispatch.push(payload);
          return { status: 204 };
        },
        async listWorkflowRuns() {
          return { data: { workflow_runs: [] } };
        },
      },
      git: {
        async deleteRef() {
          return { status: 204 };
        },
      },
    },
    async paginate() {
      return [];
    },
  };

  return github;
}

test('runKeepalivePostWork reports conflict when repository context is missing', async () => {
  const { core, outputs } = createCore();
  const stub = createStateManagerStub();
  const { runKeepalivePostWork, restore } = loadRunnerWithStateManager(stub.getManager);

  await runKeepalivePostWork({
    core,
    github: {},
    context: { repo: {} },
    env: makeEnv(),
  });

  assert.equal(outputs.action, 'skip');
  assert.equal(outputs.status, 'conflict');
  assert.equal(outputs.mode, 'initialisation-missing-repo');
  restore();
});

test('runKeepalivePostWork skips when agent state is not done', async () => {
  const { core, outputs } = createCore();
  const stub = createStateManagerStub();
  const { runKeepalivePostWork, restore } = loadRunnerWithStateManager(stub.getManager);
  const github = createGithubStub();

  await runKeepalivePostWork({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' } },
    env: makeEnv({ AGENT_STATE: 'running' }),
  });

  assert.equal(outputs.action, 'skip');
  assert.equal(outputs.status, 'needs_update');
  assert.equal(outputs.mode, 'skipped-agent-state');
  assert.equal(github.calls.addLabels.length, 0);
  assert.equal(github.calls.removeLabel.length, 0);
  restore();
});

test('runKeepalivePostWork removes sync label when head already advanced', async () => {
  const { core, outputs } = createCore();
  const stub = createStateManagerStub();
  const { runKeepalivePostWork, restore } = loadRunnerWithStateManager(stub.getManager);
  const github = createGithubStub({
    pull: makePull({ head: { sha: 'def456', ref: 'feature/keepalive', repo: { full_name: 'octo/demo', fork: false } } }),
    labels: [{ name: 'agents:sync-required' }],
  });

  await runKeepalivePostWork({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' } },
    env: makeEnv({ PR_HEAD_SHA_PREV: 'abc123' }),
  });

  assert.equal(outputs.action, 'skip');
  assert.equal(outputs.status, 'in_sync');
  assert.equal(outputs.changed, 'true');
  assert.equal(outputs.mode, 'already-synced');
  assert.equal(github.calls.removeLabel.length, 1);
  assert.equal(github.calls.removeLabel[0].name, 'agents:sync-required');
  restore();
});

test('runKeepalivePostWork escalates and adds sync label when sync times out', async () => {
  const { core, outputs } = createCore();
  const stub = createStateManagerStub();
  const { runKeepalivePostWork, restore } = loadRunnerWithStateManager(stub.getManager);
  const github = createGithubStub();

  await runKeepalivePostWork({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' } },
    env: makeEnv({
      DRY_RUN: 'true',
      COMMENT_ID: '1001',
      COMMENT_URL: 'https://example.com/manual',
    }),
  });

  assert.equal(outputs.action, 'escalate');
  assert.equal(outputs.status, 'needs_update');
  assert.equal(github.calls.addLabels.length, 1);
  assert.equal(github.calls.addLabels[0].labels[0], 'agents:sync-required');
  assert.ok(github.calls.createComment[0].body.includes('Keepalive: manual action needed'));
  restore();
});

test('runKeepalivePostWork reports conflict for forked PR without head repository', async () => {
  const { core, outputs } = createCore();
  const stub = createStateManagerStub();
  const { runKeepalivePostWork, restore } = loadRunnerWithStateManager(stub.getManager);
  const github = createGithubStub({
    pull: makePull({
      head: { sha: 'abc123', ref: 'feature/keepalive', repo: { fork: true } },
      base: { ref: 'main', repo: { full_name: 'octo/demo' } },
    }),
  });

  await runKeepalivePostWork({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' } },
    env: makeEnv(),
  });

  assert.equal(outputs.action, 'skip');
  assert.equal(outputs.status, 'conflict');
  assert.equal(outputs.mode, 'fork-head-repo-missing');
  assert.equal(github.calls.addLabels.length, 0);
  assert.equal(github.calls.removeLabel.length, 0);
  restore();
});
