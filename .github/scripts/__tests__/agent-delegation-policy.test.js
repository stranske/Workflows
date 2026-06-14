/**
 * Tests for agent_delegation_policy.js
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  decideNextAgent,
  checkPrerequisites,
  calculateEffectiveness,
  detectStall,
  getExplicitAgentFromLabels,
  formatDelegationSummary,
} = require('../agent_delegation_policy.js');

const mockRegistry = {
  default_agent: 'codex',
  agents: {
    codex: {
      required_secrets: ['CODEX_AUTH_JSON'],
      runner_workflow: '.github/workflows/reusable-codex-run.yml',
    },
    claude: {
      required_secrets: ['CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_AUTH_JSON'],
      required_secrets_mode: 'any',
      runner_workflow: '.github/workflows/reusable-claude-run.yml',
    },
  },
};

const mockSecrets = {
  CODEX_AUTH_JSON: 'present',
  CLAUDE_CODE_OAUTH_TOKEN: 'present',
};

test('checkPrerequisites returns available=true when secrets present', () => {
  const result = checkPrerequisites({
    agent: 'codex',
    agentConfig: mockRegistry.agents.codex,
    secrets: mockSecrets,
  });

  assert.equal(result.available, true);
  assert.equal(result.reason, 'prerequisites-met');
});

test('checkPrerequisites returns available=false when secret missing', () => {
  const result = checkPrerequisites({
    agent: 'codex',
    agentConfig: mockRegistry.agents.codex,
    secrets: {},
  });

  assert.equal(result.available, false);
  assert.equal(result.reason, 'missing-secret-CODEX_AUTH_JSON');
});

test('checkPrerequisites returns available=false when agent disabled', () => {
  const result = checkPrerequisites({
    agent: 'gemini',
    agentConfig: {
      enabled: false,
      required_secrets: ['GEMINI_API_KEY'],
    },
    secrets: { GEMINI_API_KEY: 'present' },
  });

  assert.equal(result.available, false);
  assert.equal(result.reason, 'agent-disabled');
});

test('checkPrerequisites with mode=any returns available=true when one secret present', () => {
  const result = checkPrerequisites({
    agent: 'claude',
    agentConfig: mockRegistry.agents.claude,
    secrets: { CLAUDE_CODE_OAUTH_TOKEN: 'present' },
  });

  assert.equal(result.available, true);
  assert.equal(result.reason, 'prerequisites-met');
});

test('checkPrerequisites with mode=any returns available=true with fallback secret', () => {
  const result = checkPrerequisites({
    agent: 'claude',
    agentConfig: mockRegistry.agents.claude,
    secrets: { CLAUDE_AUTH_JSON: 'present' },
  });

  assert.equal(result.available, true);
  assert.equal(result.reason, 'prerequisites-met');
});

test('checkPrerequisites with mode=any returns available=false when no secrets present', () => {
  const result = checkPrerequisites({
    agent: 'claude',
    agentConfig: mockRegistry.agents.claude,
    secrets: {},
  });

  assert.equal(result.available, false);
});

test('calculateEffectiveness returns effective=true when commits made', () => {
  const history = [
    { iteration: 16, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 17, commits: 1, tasks: 0, gate: 'pending' },
    { iteration: 18, commits: 0, tasks: 0, gate: 'pending' },
  ];

  const result = calculateEffectiveness({ history, lookbackRounds: 3 });

  assert.equal(result.effective, true);
  assert.equal(result.commits, 1);
  assert.ok(result.summary.includes('1 commits'));
});

test('calculateEffectiveness returns effective=true when tasks completed', () => {
  const history = [
    { iteration: 16, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 17, commits: 0, tasks: 2, gate: 'pending' },
    { iteration: 18, commits: 0, tasks: 0, gate: 'pending' },
  ];

  const result = calculateEffectiveness({ history, lookbackRounds: 3 });

  assert.equal(result.effective, true);
  assert.equal(result.tasks, 2);
  assert.ok(result.summary.includes('2 tasks'));
});

// Semantics intentionally changed for #2268: a commit-less green Gate is NOT
// progress. A normal `run` dispatch only happens on a green Gate, so a stuck
// agent records gate:'pass' every round; counting that as effective made the
// stall detector unable to fire. gatePassed is still reported for visibility.
test('calculateEffectiveness does NOT count a commit-less gate pass as effective', () => {
  const history = [
    { iteration: 16, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 17, commits: 0, tasks: 0, gate: 'pass' },
    { iteration: 18, commits: 0, tasks: 0, gate: 'pending' },
  ];

  const result = calculateEffectiveness({ history, lookbackRounds: 3 });

  assert.equal(result.effective, false);
  assert.equal(result.gatePassed, true);
  assert.ok(result.summary.includes('gate passed'));
});

test('calculateEffectiveness returns effective=false when no progress', () => {
  const history = [
    { iteration: 16, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 17, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 18, commits: 0, tasks: 0, gate: 'fail' },
  ];

  const result = calculateEffectiveness({ history, lookbackRounds: 3 });

  assert.equal(result.effective, false);
  assert.equal(result.commits, 0);
  assert.equal(result.tasks, 0);
  assert.equal(result.gatePassed, false);
  assert.equal(result.summary, 'no progress');
});

test('detectStall returns isStalled=true when threshold exceeded', () => {
  const history = [
    { iteration: 16, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 17, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 18, commits: 0, tasks: 0, gate: 'fail' },
  ];

  const result = detectStall({ history, threshold: 3 });

  assert.equal(result.isStalled, true);
  assert.equal(result.consecutiveRounds, 3);
  assert.ok(result.reason.includes('3 rounds, no progress'));
});

// #2268 deliberate-break gate: a 3-round zero-commit green-gate history MUST
// produce isStalled=true. Restoring the old `|| round.gate === 'pass'` progress
// test in detectStall makes this case come back isStalled=false (the green gates
// reset the counter), proving this test catches the gate-pass-as-progress poison.
test('detectStall fires after 3 zero-commit green-gate rounds', () => {
  const history = [
    { iteration: 16, commits: 0, tasks: 0, gate: 'pass' },
    { iteration: 17, commits: 0, tasks: 0, gate: 'pass' },
    { iteration: 18, commits: 0, tasks: 0, gate: 'pass' },
  ];

  const result = detectStall({ history, threshold: 3 });

  assert.equal(result.isStalled, true);
  assert.equal(result.consecutiveRounds, 3);
});

test('detectStall returns isStalled=false when progress in last round', () => {
  const history = [
    { iteration: 16, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 17, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 18, commits: 1, tasks: 0, gate: 'fail' },
  ];

  const result = detectStall({ history, threshold: 3 });

  assert.equal(result.isStalled, false);
  assert.equal(result.reason, 'progress-detected');
});

test('getExplicitAgentFromLabels returns agent key from agent:* label', () => {
  const labels = ['bug', 'agent:codex', 'priority-high'];
  const result = getExplicitAgentFromLabels(labels, mockRegistry.agents);

  assert.equal(result, 'codex');
});

test('getExplicitAgentFromLabels handles label objects with name property', () => {
  const labels = [{ name: 'agent:claude' }, { name: 'bug' }];
  const result = getExplicitAgentFromLabels(labels, mockRegistry.agents);

  assert.equal(result, 'claude');
});

test('getExplicitAgentFromLabels returns null if no agent labels present', () => {
  const labels = ['bug', 'priority-high'];
  const result = getExplicitAgentFromLabels(labels, mockRegistry.agents);

  assert.equal(result, null);
});

test('decideNextAgent returns default agent on initial selection', () => {
  const result = decideNextAgent({
    state: { iteration: 1 },
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });

  assert.equal(result.agent, 'codex');
  assert.equal(result.reason, 'initial-selection');
  assert.equal(result.shouldSwitch, false);
});

test('decideNextAgent returns explicit agent if agent:auto not present', () => {
  const result = decideNextAgent({
    state: {},
    labels: ['agent:claude'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });

  assert.equal(result.agent, 'claude');
  assert.equal(result.reason, 'explicit-label');
  assert.equal(result.shouldSwitch, false);
});

test('decideNextAgent continues current agent if effective', () => {
  const state = {
    current_agent: 'codex',
    iteration: 18,
    last_switch_iteration: 10,
    effectiveness_history: [
      { iteration: 16, commits: 1, tasks: 0, gate: 'fail' },
      { iteration: 17, commits: 0, tasks: 1, gate: 'pending' },
      { iteration: 18, commits: 1, tasks: 0, gate: 'pending' },
    ],
  };

  const result = decideNextAgent({
    state,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });

  assert.equal(result.agent, 'codex');
  assert.ok(result.reason.includes('effective'));
  assert.equal(result.shouldSwitch, false);
});

test('decideNextAgent switches agent if stalled and not in cooldown', () => {
  const state = {
    current_agent: 'codex',
    iteration: 20,
    last_switch_iteration: 10,
    effectiveness_history: [
      { iteration: 18, commits: 0, tasks: 0, gate: 'fail' },
      { iteration: 19, commits: 0, tasks: 0, gate: 'fail' },
      { iteration: 20, commits: 0, tasks: 0, gate: 'fail' },
    ],
  };

  const result = decideNextAgent({
    state,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });

  assert.equal(result.agent, 'claude');
  assert.ok(result.reason.includes('stalled'));
  assert.equal(result.shouldSwitch, true);
  assert.equal(result.previousAgent, 'codex');
});

test('decideNextAgent does not switch if in cooldown period', () => {
  const state = {
    current_agent: 'codex',
    iteration: 13,
    last_switch_iteration: 10,
    effectiveness_history: [
      { iteration: 11, commits: 0, tasks: 0, gate: 'fail' },
      { iteration: 12, commits: 0, tasks: 0, gate: 'fail' },
      { iteration: 13, commits: 0, tasks: 0, gate: 'fail' },
    ],
  };

  const result = decideNextAgent({
    state,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });

  assert.equal(result.agent, 'codex');
  assert.ok(result.reason.includes('cooldown'));
  assert.equal(result.shouldSwitch, false);
});

test('decideNextAgent returns empty agent if no agents available', () => {
  const result = decideNextAgent({
    state: {},
    labels: ['agent:auto'],
    secrets: {},
    registry: mockRegistry,
  });

  assert.equal(result.agent, '');
  assert.equal(result.reason, 'no-agents-available');
  assert.equal(result.shouldSwitch, false);
});

test('formatDelegationSummary formats decision with metrics', () => {
  const decision = {
    agent: 'codex',
    reason: 'effective (2 commits, 1 task)',
    alternatives: ['claude'],
  };

  const effectiveness = {
    commits: 2,
    tasks: 1,
    gatePassed: false,
    summary: '2 commits, 1 task',
  };

  const state = {
    iteration: 18,
    switch_count: 0,
  };

  const summary = formatDelegationSummary({ decision, effectiveness, state });

  assert.ok(summary.includes('Agent Selection (auto mode)'));
  assert.ok(summary.includes('**Chosen:** codex'));
  assert.ok(summary.includes('Commits (last 3 rounds): 2'));
});
