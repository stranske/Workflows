'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const keepaliveLoopPath = path.resolve(__dirname, '../.github/scripts/keepalive_loop.js');
const keepaliveStatePath = path.resolve(__dirname, '../.github/scripts/keepalive_state.js');
const { updateKeepaliveLoopSummary } = require(keepaliveLoopPath);
const { formatStateComment } = require(keepaliveStatePath);

// ─── Helpers ────────────────────────────────────────────────────────────────

function buildGithub(stateOverrides = {}) {
  const stateComment = {
    id: 200,
    body: formatStateComment({
      trace: 'test-trace',
      iteration: 1,
      max_iterations: 5,
      ...stateOverrides,
    }),
    html_url: 'https://example.test/200',
  };

  let capturedBody = null;
  return {
    github: {
      rest: {
        issues: {
          async listComments() {
            return { data: [stateComment] };
          },
          async updateComment(_args) {
            capturedBody = _args.body;
            return { data: { id: stateComment.id } };
          },
          async createComment() {
            return { data: { id: 300, html_url: 'https://example.test/300' } };
          },
        },
      },
      async paginate(fn, params) {
        const response = await fn(params);
        return Array.isArray(response?.data) ? response.data : [];
      },
    },
    getCapturedBody() { return capturedBody; },
  };
}

const context = { repo: { owner: 'octo', repo: 'workflows' } };
const core = { info() {}, warning() {}, setOutput() {} };

function extractState(commentBody) {
  const match = commentBody?.match(/<!-- keepalive-state:v1\s+({.*?})\s*-->/s);
  if (!match) return null;
  return JSON.parse(match[1]);
}

// ─── complete_gate_failure_rounds: only agent-execution rounds increment ─────

test('counter: wait action does NOT increment complete_gate_failure_rounds', async () => {
  const { github, getCapturedBody } = buildGithub({
    complete_gate_failure_rounds: 1,
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'wait',
      reason: 'gate-cancelled-transient',
      gateConclusion: 'cancelled',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  // Wait action should preserve but NOT increment the counter
  assert.equal(state.complete_gate_failure_rounds, 1,
    'wait action should preserve counter without incrementing');
});

test('counter: fix action DOES increment complete_gate_failure_rounds when gate failed', async () => {
  const { github, getCapturedBody } = buildGithub({
    complete_gate_failure_rounds: 1,
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'fix',
      reason: 'fix-lint',
      runResult: 'success',
      gateConclusion: 'failure',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  assert.equal(state.complete_gate_failure_rounds, 2,
    'fix action with gate failure should increment counter');
});

test('counter: stop action with gate failure still increments (workflow stopping anyway)', async () => {
  const { github, getCapturedBody } = buildGithub({
    complete_gate_failure_rounds: 2,
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'stop',
      reason: 'complete-gate-failure-max',
      gateConclusion: 'failure',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 3,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  // Counter increments whenever gate actually failed, regardless of action.
  // The stop action is the final round so the incremented value is harmless.
  assert.equal(state.complete_gate_failure_rounds, 3,
    'stop action with gate failure should increment counter');
});

test('counter: resets to 0 when gate succeeds', async () => {
  const { github, getCapturedBody } = buildGithub({
    complete_gate_failure_rounds: 2,
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'run',
      reason: 'ready',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  assert.equal(state.complete_gate_failure_rounds, 0,
    'counter should reset to 0 when gate succeeds');
});

test('counter: cancelled gate with all tasks complete preserves but does not increment', async () => {
  const { github, getCapturedBody } = buildGithub({
    complete_gate_failure_rounds: 1,
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'wait',
      reason: 'gate-cancelled-transient',
      gateConclusion: 'cancelled',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  assert.equal(state.complete_gate_failure_rounds, 1,
    'cancelled gate should preserve counter (not increment)');
});

test('counter: wait action with gate *failure* DOES increment (non-fixable scenario)', async () => {
  // This is the key bug-fix scenario: when shouldFixMode=false, evaluate
  // chooses 'wait', but the counter must still advance toward the stop
  // threshold so the PR doesn't loop forever in gate-not-success.
  const { github, getCapturedBody } = buildGithub({
    complete_gate_failure_rounds: 1,
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'wait',
      reason: 'gate-not-success',
      gateConclusion: 'failure',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  assert.equal(state.complete_gate_failure_rounds, 2,
    'wait action with gate failure should increment counter to prevent infinite loop');
});

// ─── consecutive_fix_rounds: preserved across wait/stop actions ──────────────

test('fix counter: preserved across wait actions (not reset)', async () => {
  const { github, getCapturedBody } = buildGithub({
    consecutive_fix_rounds: 1,
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'wait',
      reason: 'gate-cancelled-transient',
      gateConclusion: 'cancelled',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  assert.equal(state.consecutive_fix_rounds, 1,
    'wait action should preserve fix counter');
});

test('fix counter: incremented on fix action', async () => {
  const { github, getCapturedBody } = buildGithub({
    consecutive_fix_rounds: 1,
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'fix',
      reason: 'fix-lint',
      runResult: 'success',
      gateConclusion: 'failure',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  assert.equal(state.consecutive_fix_rounds, 2,
    'fix action should increment fix counter');
});

test('fix counter: reset on run (non-fix agent execution)', async () => {
  const { github, getCapturedBody } = buildGithub({
    consecutive_fix_rounds: 2,
    tasks: { total: 5, unchecked: 2 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'run',
      reason: 'ready',
      runResult: 'success',
      gateConclusion: 'failure',
      tasksTotal: 5,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  assert.equal(state.consecutive_fix_rounds, 0,
    'run action should reset fix counter');
});

test('fix counter: preserved across stop action', async () => {
  const { github, getCapturedBody } = buildGithub({
    consecutive_fix_rounds: 2,
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'stop',
      reason: 'complete-gate-failure-max',
      gateConclusion: 'failure',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 3,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  assert.equal(state.consecutive_fix_rounds, 2,
    'stop action should preserve fix counter');
});

// ─── Default completeGateFailureMax is now 3 ────────────────────────────────

test('default complete_gate_failure_rounds_max is 3', async () => {
  const { github, getCapturedBody } = buildGithub({
    // No explicit complete_gate_failure_rounds_max in state
    tasks: { total: 5, unchecked: 0 },
  });

  await updateKeepaliveLoopSummary({
    github, context, core,
    inputs: {
      prNumber: 100,
      action: 'fix',
      reason: 'fix-lint',
      runResult: 'success',
      gateConclusion: 'failure',
      tasksTotal: 5,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'test-trace',
    },
  });

  const state = extractState(getCapturedBody());
  assert.ok(state, 'State should be written');
  assert.equal(state.complete_gate_failure_rounds_max, 3,
    'default max should be 3 (allowing 2 fix attempts before stopping)');
});
