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
  loadRouteWeights,
  selectAgentFromRouteWeights,
  ROUTE_WEIGHT_TASK_TYPES,
} = require('../agent_delegation_policy.js');

const mockRegistry = {
  default_agent: 'codex',
  agents: {
    codex: {
    required_secrets: ['CODEX_AUTH_JSON'],
    runner_workflow: '.github/workflows/reusable-codex-run.yml',
    capabilities: { pr_keepalive: true },
    },
    claude: {
      required_secrets: ['CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_AUTH_JSON'],
    required_secrets_mode: 'any',
    runner_workflow: '.github/workflows/reusable-claude-run.yml',
    capabilities: { pr_keepalive: true },
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

test('calculateEffectiveness returns effective=true when commits made with green gate', () => {
  const history = [
    { iteration: 16, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 17, commits: 1, tasks: 0, gate: 'pass' },
    { iteration: 18, commits: 0, tasks: 0, gate: 'pending' },
  ];

  const result = calculateEffectiveness({ history, lookbackRounds: 3 });

  assert.equal(result.effective, true);
  assert.equal(result.commits, 1);
  assert.ok(result.summary.includes('1 commits'));
});

test('churn without checkbox progress is not effective', () => {
  const history = [
    { iteration: 16, commits: 1, tasks: 0, gate: 'fail' },
    { iteration: 17, commits: 1, tasks: 0, gate: 'pending' },
    { iteration: 18, commits: 1, tasks: 0, gate: 'fail' },
  ];

  const result = calculateEffectiveness({ history, lookbackRounds: 3 });

  assert.equal(result.effective, false);
  assert.equal(result.commits, 3);
  assert.equal(result.tasks, 0);
  assert.equal(result.gatePassed, false);
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

test('stalls after two zero-progress rounds', () => {
  const history = [
    { iteration: 17, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 18, commits: 0, tasks: 0, gate: 'fail' },
  ];

  const result = detectStall({ history });
  const explicitResult = detectStall({ history, threshold: 2 });

  assert.equal(result.isStalled, true);
  assert.equal(result.consecutiveRounds, 2);
  assert.equal(explicitResult.isStalled, true);
  assert.equal(explicitResult.consecutiveRounds, 2);
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
    { iteration: 18, commits: 1, tasks: 0, gate: 'pass' },
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

test('decideNextAgent replaces an unavailable persisted agent before continuation rules', () => {
  const result = decideNextAgent({
    state: {
      current_agent: 'claude',
      iteration: 18,
      last_switch_iteration: 17,
      effectiveness_history: [{ iteration: 18, commits: 1, tasks: 1, gate: 'pass' }],
    },
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    runnableAgents: ['codex'],
  });

  assert.equal(result.agent, 'codex');
  assert.equal(result.shouldSwitch, true);
  assert.equal(result.previousAgent, 'claude');
  assert.equal(result.reason, 'claude-unavailable');
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

test('decideNextAgent never selects a configured agent without a keepalive runner', () => {
  const registry = {
    default_agent: 'aider',
    agents: {
      aider: {
        enabled: true,
        required_secrets: ['AIDER_API_KEY'],
        runner_workflow: '',
        capabilities: { pr_keepalive: false },
      },
      codex: mockRegistry.agents.codex,
    },
  };
  const result = decideNextAgent({
    state: {},
    labels: ['agent:auto'],
    secrets: { AIDER_API_KEY: 'present', CODEX_AUTH_JSON: 'present' },
    registry,
  });

  assert.equal(result.agent, 'codex');
  assert.deepEqual(result.alternatives, []);
});

test('decideNextAgent respects the runners declared by the current workflow tree', () => {
  const registry = {
    default_agent: 'gemini',
    agents: {
      codex: mockRegistry.agents.codex,
      gemini: {
        required_secrets: ['GEMINI_API_KEY'],
        runner_workflow: '.github/workflows/reusable-gemini-run.yml',
        capabilities: { pr_keepalive: true },
      },
    },
  };
  const result = decideNextAgent({
    state: {},
    labels: ['agent:auto'],
    secrets: { CODEX_AUTH_JSON: 'present', GEMINI_API_KEY: 'present' },
    registry,
    runnableAgents: ['codex'],
  });

  assert.equal(result.agent, 'codex');
  assert.deepEqual(result.alternatives, []);
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

const routeWeightsRegistry = {
  default_agent: 'codex',
  agents: {
    codex: {
      required_secrets: ['CODEX_AUTH_JSON'],
      runner_workflow: '.github/workflows/reusable-codex-run.yml',
      capabilities: { pr_keepalive: true },
    },
    claude: {
      required_secrets: ['CLAUDE_CODE_OAUTH_TOKEN'],
      required_secrets_mode: 'any',
      runner_workflow: '.github/workflows/reusable-claude-run.yml',
      capabilities: { pr_keepalive: true },
    },
    cursor: {
      required_secrets: ['CURSOR_API_KEY'],
      runner_workflow: '.github/workflows/reusable-cursor-run.yml',
      capabilities: { pr_keepalive: true },
    },
  },
};

const routeWeightsSecrets = {
  CODEX_AUTH_JSON: 'present',
  CLAUDE_CODE_OAUTH_TOKEN: 'present',
  CURSOR_API_KEY: 'present',
};

const freshRouteWeights = {
  schema: 'orchestrator.route-weights/v1',
  generated_at: '2026-09-03T00:00:00Z',
  task_types: {
    implement: {
      evidence_ok: true,
      ranking: [
        { agent: 'cursor', posterior: 0.76, n_obs: 305 },
        { agent: 'codex', posterior: 0.67, n_obs: 282 },
        { agent: 'claude', posterior: 0.55, n_obs: 120 },
      ],
    },
  },
  reserve: ['claude'],
};

const stalledState = {
  current_agent: 'codex',
  iteration: 20,
  last_switch_iteration: 10,
  effectiveness_history: [
    { iteration: 18, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 19, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 20, commits: 0, tasks: 0, gate: 'fail' },
  ],
};

test('route weights choose evidence-ranked agent on stall', () => {
  const result = decideNextAgent({
    state: stalledState,
    labels: ['agent:auto'],
    secrets: routeWeightsSecrets,
    registry: routeWeightsRegistry,
    routeWeights: freshRouteWeights,
  });

  assert.equal(result.agent, 'cursor');
  assert.equal(result.delegationSource, 'route_weights');
  assert.ok(result.reason.includes('delegation_source: route_weights'));
});

test('route weights fall back to static when evidence_ok is false', () => {
  const document = {
    ...freshRouteWeights,
    task_types: {
      implement: { evidence_ok: false, ranking: [{ agent: 'cursor', posterior: 0.9 }] },
    },
  };

  const result = decideNextAgent({
    state: stalledState,
    labels: ['agent:auto'],
    secrets: routeWeightsSecrets,
    registry: routeWeightsRegistry,
    routeWeights: document,
  });

  assert.equal(result.agent, 'claude');
  assert.equal(result.delegationSource, 'static');
});

test('loadRouteWeights returns null on unreachable URL', async () => {
  const result = await loadRouteWeights({
    url: 'https://example.invalid/route-weights.json',
    fetchImpl: async () => {
      throw new Error('network down');
    },
  });

  assert.equal(result, null);
});

test('loadRouteWeights returns null on stale generated_at', async () => {
  const staleDocument = {
    schema: 'orchestrator.route-weights/v1',
    generated_at: '2026-01-01T00:00:00Z',
    task_types: {},
  };

  const result = await loadRouteWeights({
    url: 'https://example.test/route-weights.json',
    fetchImpl: async () => ({
      status: 200,
      json: async () => staleDocument,
    }),
    now: '2026-09-03T00:00:00Z',
  });

  assert.equal(result, null);
});

test('route weights never choose reserve agents', () => {
  const document = {
    ...freshRouteWeights,
    task_types: {
      implement: {
        evidence_ok: true,
        ranking: [
          { agent: 'claude', posterior: 0.99 },
          { agent: 'cursor', posterior: 0.76 },
        ],
      },
    },
    reserve: ['claude'],
  };

  const weighted = selectAgentFromRouteWeights({
    routeWeights: document,
    taskType: 'implement',
    currentAgent: 'codex',
    availableAgents: ['codex', 'claude', 'cursor'],
    agents: routeWeightsRegistry.agents,
    reserve: document.reserve,
  });

  assert.equal(weighted.agent, 'cursor');
});

test('route weights never re-choose the stalled agent', () => {
  const weighted = selectAgentFromRouteWeights({
    routeWeights: freshRouteWeights,
    taskType: 'implement',
    currentAgent: 'cursor',
    availableAgents: ['codex', 'claude', 'cursor'],
    agents: routeWeightsRegistry.agents,
    reserve: freshRouteWeights.reserve,
  });

  assert.equal(weighted.agent, 'codex');
});

test('ROUTE_WEIGHT_TASK_TYPES maps review rounds to review task type', () => {
  assert.equal(ROUTE_WEIGHT_TASK_TYPES.review, 'review');
  assert.equal(ROUTE_WEIGHT_TASK_TYPES.run, 'implement');
});
