'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

function createSummary() {
  return {
    entries: [],
    written: false,
    addHeading(text) {
      this.entries.push({ type: 'heading', text });
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

function loadRunnerWithGate(stub) {
  const gatePath = require.resolve('../keepalive_gate.js');
  const runnerPath = require.resolve('../keepalive_orchestrator_gate_runner.js');
  const gateModule = require(gatePath);
  const original = gateModule.evaluateKeepaliveGate;
  gateModule.evaluateKeepaliveGate = stub;
  delete require.cache[runnerPath];
  const { runKeepaliveGate } = require(runnerPath);
  return {
    runKeepaliveGate,
    restore() {
      gateModule.evaluateKeepaliveGate = original;
      delete require.cache[runnerPath];
    },
  };
}

function createGithub(options = {}) {
  const {
    pull,
    pullError,
    runsByWorkflow = {},
    combinedStatus = { state: 'success', statuses: [] },
    comments = [],
  } = options;

  return {
    rest: {
      pulls: {
        async get() {
          if (pullError) {
            throw pullError;
          }
          return { data: pull };
        },
      },
      repos: {
        async getCombinedStatusForRef() {
          return { data: combinedStatus };
        },
      },
      actions: {
        async listWorkflowRuns({ workflow_id: workflowId }) {
          return { data: { workflow_runs: runsByWorkflow[workflowId] || [] } };
        },
      },
    },
    async paginate() {
      return comments;
    },
  };
}

function makeEnv(overrides = {}) {
  return {
    KEEPALIVE_ENABLED: 'true',
    KEEPALIVE_TRACE: 'trace-1',
    KEEPALIVE_ROUND: '2',
    KEEPALIVE_PR: '17',
    KEEPALIVE_MAX_RETRIES: '2',
    ...overrides,
  };
}

function makePullRequest(overrides = {}) {
  return {
    number: 17,
    state: 'open',
    draft: false,
    labels: [],
    head: { sha: 'abc123', ref: 'feature/keepalive' },
    ...overrides,
  };
}

function createGateResult(overrides = {}) {
  return {
    ok: true,
    pendingGate: false,
    primaryAgent: 'codex',
    runCap: 2,
    activeRuns: 1,
    activeBreakdown: { orchestrator: 1, worker: 0 },
    hasSyncRequiredLabel: false,
    headSha: 'abc123',
    lastGreenSha: 'abc123',
    ...overrides,
  };
}

test('runKeepaliveGate proceeds when keepalive gating is not required', async () => {
  const { core, outputs, summary } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  await runKeepaliveGate({
    core,
    github: createGithub(),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 99 },
    env: makeEnv({ KEEPALIVE_ENABLED: 'false' }),
  });

  assert.equal(outputs.proceed, 'true');
  assert.equal(outputs.reason, '');
  assert.ok(summary.entries.some((entry) => entry.type === 'raw'));
  restore();
});

test('runKeepaliveGate skips when PR number is missing', async () => {
  const { core, outputs, summary } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  await runKeepaliveGate({
    core,
    github: createGithub(),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 88 },
    env: makeEnv({ KEEPALIVE_PR: 'not-a-number' }),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'missing-pr-number');
  assert.equal(summary.written, true);
  restore();
});

test('runKeepaliveGate reports failure when PR fetch fails', async () => {
  const { core, outputs, warnings } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const error = new Error('no access');
  await runKeepaliveGate({
    core,
    github: createGithub({ pullError: error }),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 77 },
    env: makeEnv(),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'pr-fetch-failed');
  assert.ok(warnings.some((message) => message.includes('Unable to load PR')));
  restore();
});

test('runKeepaliveGate records gate status when workflow run is queued', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult({ runCap: 3, activeRuns: 2 });
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: ['agents:keepalive', 'agent:codex'],
  });

  await runKeepaliveGate({
    core,
    github: createGithub({
      pull: pr,
      runsByWorkflow: {
        'pr-00-gate.yml': [
          { head_sha: 'abc123', status: 'queued', conclusion: null },
        ],
      },
    }),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 66 },
    env: makeEnv(),
  });

  assert.equal(outputs.agent_alias, 'codex');
  assert.equal(outputs.run_cap, '3');
  assert.equal(outputs.active_runs, '2');
  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'gate-run-status:queued');
  restore();
});

test('runKeepaliveGate skips when keepalive is paused by label', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: ['agents:pause', 'agents:keepalive', 'agent:codex'],
  });

  await runKeepaliveGate({
    core,
    github: createGithub({
      pull: pr,
      runsByWorkflow: {
        'pr-00-gate.yml': [
          { head_sha: 'abc123', status: 'completed', conclusion: 'success' },
        ],
      },
    }),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 55 },
    env: makeEnv(),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'keepalive-paused');
  restore();
});
