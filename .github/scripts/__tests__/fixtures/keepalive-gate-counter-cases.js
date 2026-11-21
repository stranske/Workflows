'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { updateKeepaliveLoopSummary } = require('../../keepalive_loop.js');
const { formatStateComment, parseStateComment } = require('../../keepalive_state.js');
const { buildGithubStub, buildContext, buildCore } = require('./keepalive-loop-test-context.js');

for (const { scenario, round, prior, expected, trusted = true } of [
  {
    scenario: 'cancelled Gate preserves both counters during wait',
    round: { action: 'wait', gateConclusion: 'cancelled', reason: 'gate-cancelled-transient' },
    prior: [1, 1], expected: [1, 1],
  },
  {
    scenario: 'failed Gate advances the complete-task counter during wait',
    round: { action: 'wait', gateConclusion: 'failure', reason: 'gate-not-success' },
    prior: [1, 1], expected: [2, 1],
  },
  {
    scenario: 'failed Gate and fix advance both counters',
    round: { action: 'fix', gateConclusion: 'failure', reason: 'fix-lint', runResult: 'success' },
    prior: [1, 1], expected: [2, 2],
  },
  {
    scenario: 'failed Gate advances the complete-task counter during stop',
    round: { action: 'stop', gateConclusion: 'failure', reason: 'complete-gate-failure-max' },
    prior: [2, 2], expected: [3, 2],
  },
  {
    scenario: 'successful Gate and run reset both counters',
    round: { action: 'run', gateConclusion: 'success', reason: 'ready', runResult: 'success' },
    prior: [2, 2], expected: [0, 0],
  },
  {
    scenario: 'run with tasks remaining resets both counters',
    round: { action: 'run', gateConclusion: 'failure', reason: 'ready', runResult: 'success', tasksUnchecked: 2 },
    prior: [2, 2], expected: [0, 0],
  },
  {
    scenario: 'unattributed summary cannot supply prior counters',
    round: { action: 'wait', gateConclusion: 'failure', reason: 'gate-not-success' },
    prior: [1, 2], expected: [1, 0], trusted: false,
  },
]) {
  test(`updateKeepaliveLoopSummary persists counters: ${scenario}`, async () => {
    const trace = 'gate-counter';
    const tasksUnchecked = round.tasksUnchecked ?? 0;
    const existing = {
      id: 200,
      body: formatStateComment({
        trace,
        iteration: 1,
        max_iterations: 5,
        tasks: { total: 5, unchecked: tasksUnchecked },
        complete_gate_failure_rounds: prior[0],
        consecutive_fix_rounds: prior[1],
      }),
    };
    if (!trusted) existing.user = undefined;
    const github = buildGithubStub({ comments: [existing] });
    await updateKeepaliveLoopSummary({
      github,
      context: buildContext(100),
      core: buildCore(),
      inputs: {
        prNumber: 100,
        trace,
        tasksTotal: 5,
        tasksUnchecked,
        keepaliveEnabled: true,
        iteration: 2,
        maxIterations: 5,
        ...round,
      },
    });

    const summary = github.actions.findLast((entry) =>
      ['update', 'create'].includes(entry.type) && parseStateComment(entry.body));
    assert.ok(summary, 'the keepalive state marker was persisted');
    assert.equal(summary.type, trusted ? 'update' : 'create');
    if (trusted) assert.equal(summary.commentId, existing.id);
    const { data } = parseStateComment(summary.body);
    assert.deepEqual([data.complete_gate_failure_rounds, data.consecutive_fix_rounds], expected);
    assert.equal(data.complete_gate_failure_rounds_max, 3);
  });
}
