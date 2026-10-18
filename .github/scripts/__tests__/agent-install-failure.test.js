'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const mockRegistry = { default_agent: 'codex', agents: Object.fromEntries(
  ['codex', 'claude', 'cursor', 'gemini'].map(agent => [agent, {
    runner_workflow: `.github/workflows/reusable-${agent}-run.yml`,
    capabilities: { pr_keepalive: true },
  }])) };
const mockSecrets = {};
const stalledStateCodex = { current_agent: 'codex', iteration: 20,
  last_switch_iteration: 10, effectiveness_history: [
    { commits: 0, tasks: 0, gate: 'fail' }, { commits: 0, tasks: 0, gate: 'fail' },
  ] };
const freshRouteWeights = { task_types: { implement: { evidence_ok: true,
  ranking: [{ agent: 'cursor' }, { agent: 'claude' }] } } };

for (const policyPath of ['../agent_delegation_policy.js',
  '../../../templates/consumer-repo/.github/scripts/agent_delegation_policy.js']) {
  const policy = require(policyPath);
  const nowMs = Date.parse('2026-10-18T18:00:00Z');
  const failed = (summary, extra = {}) => ({ provider: 'cursor', status: 'error',
    completed_at: new Date(nowMs - 1000).toISOString(),
    completion: { reason: 'failed' }, result: { success: false, summary }, ...extra });
  const decide = (extra = {}) => policy.decideNextAgent({
    labels: ['agent:auto'], registry: mockRegistry, secrets: mockSecrets,
    state: stalledStateCodex, routeWeights: freshRouteWeights, now: nowMs, ...extra,
  });

  test(`recent install failure skips weighted target and picks next (${policyPath})`, () => {
    const decision = decide({ completion: failed('cursor-agent: command not found') });
    assert.equal(decision.agent, 'claude');
    assert.equal(decision.shouldSwitch, true);
    assert.ok(!decision.alternatives.includes('cursor'));
  });

  test(`startup failure overrides cooldown and explicit route (${policyPath})`, () => {
    for (const labels of [['agent:auto', 'agent:cursor'], ['agent:cursor']]) {
      for (const summary of ['cursor-agent: command not found',
        'Agent CLI install/preflight failed (exit 127)',
        'Cursor CLI preflight failed: cursor-agent --version failed']) {
        const decision = decide({ labels, completion: failed(summary),
          state: { current_agent: 'cursor', iteration: 1, last_switch_iteration: 1 } });
        assert.equal(decision.agent, 'codex');
        assert.equal(decision.reason, 'cursor-install-preflight-failed');
        assert.equal(decision.previousAgent, 'cursor');
      }
    }
  });

  test(`recent failure survives another provider completion (${policyPath})`, () => {
    const decision = decide({ completion: { provider: 'codex', status: 'error',
      completed_at: new Date(nowMs).toISOString(), completion: { reason: 'failed' },
      result: { summary: 'unrelated error' },
      install_failure_receipts: [failed('cursor-agent: command not found')] } });
    assert.equal(decision.agent, 'claude');
  });

  test(`install backoff expires without head or label changes (${policyPath})`, () => {
    const completion = failed('cursor-agent: command not found', {
      completed_at: new Date(nowMs - policy.AGENT_INSTALL_FAILURE_BACKOFF_HOURS * 3600000).toISOString(),
    });
    assert.equal(decide({ completion }).agent, 'cursor');
    assert.equal(decide({ completion: failed('Fixed command not found', {
      result: { success: true, summary: 'Fixed command not found' },
      completion: { reason: 'progressed' },
    }) }).agent, 'cursor');
    assert.equal(decide({ completion: failed('unit tests failed') }).agent, 'cursor');
  });

  test(`all startup candidates unavailable refuses dispatch (${policyPath})`, () => {
    const registry = { default_agent: 'cursor', agents: { cursor: mockRegistry.agents.cursor } };
    const decision = decide({ registry, labels: ['agent:cursor'], state: {},
      completion: failed('cursor-agent: command not found') });
    assert.equal(decision.agent, '');
    assert.equal(decision.reason, 'install-failed-no-alternatives');
  });
}
