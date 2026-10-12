/**
 * Tests for agent_delegation_policy.js
 *
 * These cases are intentionally narrow and focused on the route-weights policy
 * integration points used by keepalive delegation.
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const path = require('node:path');

const {
  decideNextAgent,
  loadRouteWeights,
  resolveRoundKind,
  pickAgent,
  selectAgentFromRouteWeights,
  explorationSeedFromState,
  formatDelegationSummary,
} = require('../agent_delegation_policy.js');

const routeWeightsWithExploration = require(
  path.join(__dirname, '../../../tests/fixtures/route-weights-with-exploration.json')
);

const mockRegistry = {
  default_agent: 'codex',
  agents: {
    codex: {
      required_secrets: ['CODEX_AUTH_JSON'],
      runner_workflow: '.github/workflows/reusable-codex-run.yml',
      capabilities: { pr_keepalive: true },
    },
    claude: {
      required_secrets: ['CLAUDE_CODE_OAUTH_TOKEN'],
      runner_workflow: '.github/workflows/reusable-claude-run.yml',
      capabilities: { pr_keepalive: true },
    },
    cursor: {
      required_secrets: ['CURSOR_API_KEY'],
      runner_workflow: '.github/workflows/reusable-cursor-run.yml',
      capabilities: { pr_keepalive: true },
    },
    gemini: {
      required_secrets: ['GEMINI_API_KEY'],
      runner_workflow: '.github/workflows/reusable-gemini-run.yml',
      capabilities: { pr_keepalive: true },
    },
  },
};

const mockSecrets = {
  CODEX_AUTH_JSON: true,
  CLAUDE_CODE_OAUTH_TOKEN: true,
  CURSOR_API_KEY: true,
  GEMINI_API_KEY: true,
};

const stalledStateCodex = {
  current_agent: 'codex',
  iteration: 20,
  last_switch_iteration: 10,
  effectiveness_history: [
    { iteration: 18, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 19, commits: 0, tasks: 0, gate: 'fail' },
    { iteration: 20, commits: 0, tasks: 0, gate: 'fail' },
  ],
};

const now = '2026-09-03T00:00:00Z';

const freshRouteWeights = {
  schema: 'orchestrator.route-weights/v1',
  generated_at: now,
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
  // The published export reserves agents by task type as evidence rows.
  reserve: {
    implement: [{ agent: 'claude', n_obs: 120, posterior: 0.55 }],
  },
};

test('initial selection seeds from a co-present concrete label', () => {
  const result = decideNextAgent({
    state: {},
    labels: ['agent:auto', 'agent:claude'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: freshRouteWeights,
  });

  assert.equal(result.agent, 'claude');
  assert.equal(result.reason, 'initial-selection-label');
  assert.equal(result.delegationSource, 'static');
  assert.equal(result.shouldSwitch, false);
});

test('initial selection uses route weights without a concrete label', () => {
  const result = decideNextAgent({
    state: {},
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: freshRouteWeights,
  });

  assert.equal(result.agent, 'cursor');
  assert.equal(result.reason, 'initial-selection-route-weights');
  assert.equal(result.delegationSource, 'route_weights');
  assert.equal(result.shouldSwitch, false);
});

test('initial selection falls back to the default agent without evidence', () => {
  const result = decideNextAgent({
    state: {},
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: {
      ...freshRouteWeights,
      task_types: {
        implement: {
          evidence_ok: false,
          ranking: [{ agent: 'cursor', posterior: 0.99 }],
        },
      },
    },
  });

  assert.equal(result.agent, 'codex');
  assert.equal(result.reason, 'initial-selection');
  assert.equal(result.delegationSource, 'static');
  assert.equal(result.shouldSwitch, false);
});

test('initial selection skips an unavailable concrete label', () => {
  const result = decideNextAgent({
    state: {},
    labels: ['agent:auto', 'agent:claude'],
    secrets: {
      CODEX_AUTH_JSON: true,
      CURSOR_API_KEY: true,
    },
    registry: mockRegistry,
    routeWeights: freshRouteWeights,
  });

  assert.equal(result.agent, 'cursor');
  assert.equal(result.reason, 'initial-selection-route-weights');
  assert.equal(result.delegationSource, 'route_weights');
  assert.equal(result.shouldSwitch, false);
});

test('agent:auto rejects multiple distinct concrete labels before selection', () => {
  for (const labels of [
    ['agent:auto', 'agent:codex', 'agent:claude'],
    ['agent:auto', 'agent:claude', 'agent:codex'],
  ]) {
    const result = decideNextAgent({
      state: {},
      labels,
      secrets: mockSecrets,
      registry: mockRegistry,
      routeWeights: freshRouteWeights,
    });

    assert.deepEqual(result, {
      agent: '',
      reason: 'multiple-agent-labels',
      shouldSwitch: false,
      alternatives: [],
      delegationSource: 'static',
    });
  }

  const persisted = decideNextAgent({
    state: { current_agent: 'codex', iteration: 3 },
    labels: ['agent:auto', 'agent:codex', 'agent:claude'],
    secrets: { CODEX_AUTH_JSON: true },
    registry: mockRegistry,
    routeWeights: null,
  });
  assert.equal(persisted.agent, '');
  assert.equal(persisted.reason, 'multiple-agent-labels');
});

test('agent:auto treats duplicate normalized concrete labels as one seed', () => {
  const result = decideNextAgent({
    state: {},
    labels: ['agent:auto', 'agent:claude', { name: ' Agent:Claude ' }],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: freshRouteWeights,
  });

  assert.equal(result.agent, 'claude');
  assert.equal(result.reason, 'initial-selection-label');
});

test('fixture document → evidence-ranked choice', () => {
  const result = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: freshRouteWeights,
  });

  assert.equal(result.agent, 'cursor');
  assert.equal(result.delegationSource, 'route_weights');
  assert.ok(result.reason.includes('delegation_source: route_weights'));
});

test('evidence_ok: false → static choice', () => {
  const document = {
    ...freshRouteWeights,
    task_types: {
      implement: {
        evidence_ok: false,
        ranking: [{ agent: 'cursor', posterior: 0.9 }],
      },
    },
  };

  const result = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: document,
  });

  assert.equal(result.agent, 'claude');
  assert.equal(result.delegationSource, 'static');
  assert.ok(result.reason.includes('delegation_source: static'));
});

test('evidence_ok: false keeps static preference exactly', () => {
  const staticDecision = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: null,
  });

  const document = {
    ...freshRouteWeights,
    task_types: {
      implement: {
        evidence_ok: false,
        ranking: [{ agent: 'cursor', posterior: 0.9 }],
      },
    },
  };

  const result = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: document,
  });

  assert.equal(result.agent, staticDecision.agent);
  assert.equal(result.delegationSource, staticDecision.delegationSource);
  assert.equal(result.shouldSwitch, staticDecision.shouldSwitch);
  assert.deepEqual(result.alternatives, staticDecision.alternatives);
  // reason differs by failure type (route-weights-unavailable vs route-weights-insufficient-evidence)
  // but both must indicate static delegation
  assert.ok(result.reason.includes('delegation_source: static'), `reason should indicate static: ${result.reason}`);
  assert.equal(result.previousAgent, staticDecision.previousAgent);
});

test('unreachable URL → static choice', async () => {
  const loaded = await loadRouteWeights({
    url: 'https://example.invalid/route-weights.json',
    fetchImpl: async () => {
      throw new Error('network down');
    },
    now,
  });

  assert.equal(loaded, null);

  const result = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: loaded,
  });

  assert.equal(result.agent, 'claude');
  assert.equal(result.delegationSource, 'static');
  assert.ok(result.reason.includes('delegation_source: static'));
});

test('malformed JSON → static choice', async () => {
  const loaded = await loadRouteWeights({
    url: 'https://example.test/route-weights.json',
    fetchImpl: async () => ({
      status: 200,
      json: async () => {
        throw new SyntaxError('unexpected token');
      },
    }),
    now,
  });

  assert.equal(loaded, null);

  const result = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: loaded,
  });

  assert.equal(result.agent, 'claude');
  assert.equal(result.delegationSource, 'static');
  assert.ok(result.reason.includes('delegation_source: static'));
});

test('stale generated_at → static choice', async () => {
  const staleDocument = {
    schema: 'orchestrator.route-weights/v1',
    generated_at: '2026-01-01T00:00:00Z',
    task_types: {},
  };

  const loaded = await loadRouteWeights({
    url: 'https://example.test/route-weights.json',
    fetchImpl: async () => ({
      status: 200,
      json: async () => staleDocument,
    }),
    now,
  });

  assert.equal(loaded, null);

  const result = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: loaded,
  });

  assert.equal(result.agent, 'claude');
  assert.equal(result.delegationSource, 'static');
  assert.ok(result.reason.includes('delegation_source: static'));
});

test('future-dated generated_at beyond clock skew → static choice', async () => {
  const futureDocument = {
    schema: 'orchestrator.route-weights/v1',
    generated_at: '2026-09-03T00:01:01Z',
    task_types: {},
  };

  const loaded = await loadRouteWeights({
    url: 'https://example.test/route-weights.json',
    fetchImpl: async () => ({
      status: 200,
      json: async () => futureDocument,
    }),
    now,
  });

  assert.equal(loaded, null);
});

test('reserve never chosen', async () => {
  // In this scenario the doc would rank `claude` first, but `claude` is reserved,
  // so the next eligible ranked agent should be chosen.
  const reservedClaudeRouteWeights = {
    schema: 'orchestrator.route-weights/v1',
    generated_at: now,
    task_types: {
      implement: {
        evidence_ok: true,
        ranking: [
          { agent: 'claude', posterior: 0.99 },
          { agent: 'cursor', posterior: 0.76 },
        ],
      },
    },
    reserve: {
      implement: [{ agent: 'claude', posterior: 0.99 }],
    },
  };

  const loaded = await loadRouteWeights({
    url: 'https://example.test/route-weights.json',
    fetchImpl: async () => ({
      status: 200,
      json: async () => reservedClaudeRouteWeights,
    }),
    now,
  });

  assert.deepEqual(loaded, reservedClaudeRouteWeights);

  const result = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: loaded,
  });

  assert.equal(result.agent, 'cursor');
  assert.equal(result.delegationSource, 'route_weights');
  assert.ok(result.reason.includes('delegation_source: route_weights'));
});

test('static fallback never chooses a reserved agent when weighted choices are unavailable', () => {
  const result = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: {
      schema: 'orchestrator.route-weights/v1',
      generated_at: now,
      task_types: {
        implement: {
          evidence_ok: true,
          ranking: [{ agent: 'unavailable-agent', posterior: 0.99 }],
        },
      },
      reserve: {
        implement: [{ agent: 'claude', posterior: 0.55 }],
      },
    },
  });

  assert.equal(result.agent, 'cursor');
  assert.equal(result.delegationSource, 'static');
  assert.ok(result.reason.includes('delegation_source: static'));
});

test('resolveRoundKind maps the testgen label ahead of the keepalive action state', () => {
  const result = resolveRoundKind({
    labels: ['agent:auto', 'testgen'],
    state: { last_action: 'run' },
  });

  assert.equal(result, 'testgen');
});

test('resolveRoundKind falls back to the keepalive action state without the testgen label', () => {
  const result = resolveRoundKind({
    labels: ['agent:auto', 'review'],
    state: { last_action: 'review' },
  });

  assert.equal(result, 'review');
});

test('resolveRoundKind defaults to implement with no label or action state', () => {
  const result = resolveRoundKind({ labels: [], state: {} });

  assert.equal(result, 'implement');
});

test('stalled agent never re-chosen', () => {
  const stalledCursorState = {
    ...stalledStateCodex,
    current_agent: 'cursor',
  };

  // If the policy accidentally re-chosen the stalled agent, it would select
  // `cursor` again due to ranking order below.
  const document = {
    ...freshRouteWeights,
    reserve: [],
    task_types: {
      implement: {
        evidence_ok: true,
        ranking: [
          { agent: 'cursor', posterior: 0.76 },
          { agent: 'codex', posterior: 0.67 },
        ],
      },
    },
  };

  const result = decideNextAgent({
    state: stalledCursorState,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: document,
  });

  assert.equal(result.agent, 'codex');
  assert.equal(result.delegationSource, 'route_weights');
  assert.ok(result.reason.includes('delegation_source: route_weights'));
});

test('decideNextAgent always returns delegationSource on static return paths', () => {
  const explicit = decideNextAgent({
    state: {},
    labels: ['agent:claude'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });
  assert.equal(explicit.reason, 'explicit-label');
  assert.equal(explicit.delegationSource, 'static');

  // No agent:auto and no explicit agent label → default branch.
  const defaultPath = decideNextAgent({
    state: {},
    labels: [],
    secrets: mockSecrets,
    registry: mockRegistry,
  });
  assert.equal(defaultPath.reason, 'default');
  assert.equal(defaultPath.agent, 'codex');
  assert.equal(defaultPath.delegationSource, 'static');

  const noAgents = decideNextAgent({
    state: {},
    labels: ['agent:auto'],
    secrets: {},
    registry: mockRegistry,
  });
  assert.equal(noAgents.reason, 'no-agents-available');
  assert.equal(noAgents.delegationSource, 'static');

  const initial = decideNextAgent({
    state: { iteration: 1 },
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });
  assert.equal(initial.reason, 'initial-selection');
  assert.equal(initial.delegationSource, 'static');

  const unavailable = decideNextAgent({
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
  assert.equal(unavailable.reason, 'claude-unavailable');
  assert.equal(unavailable.delegationSource, 'static');

  const effective = decideNextAgent({
    state: {
      current_agent: 'codex',
      iteration: 18,
      last_switch_iteration: 10,
      effectiveness_history: [
        { iteration: 16, commits: 1, tasks: 0, gate: 'fail' },
        { iteration: 17, commits: 0, tasks: 1, gate: 'pending' },
        { iteration: 18, commits: 1, tasks: 0, gate: 'pending' },
      ],
    },
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });
  assert.ok(effective.reason.includes('effective'));
  assert.equal(effective.delegationSource, 'static');

  const cooldown = decideNextAgent({
    state: {
      current_agent: 'codex',
      iteration: 13,
      last_switch_iteration: 10,
      effectiveness_history: [
        { iteration: 11, commits: 0, tasks: 0, gate: 'fail' },
        { iteration: 12, commits: 0, tasks: 0, gate: 'fail' },
        { iteration: 13, commits: 0, tasks: 0, gate: 'fail' },
      ],
    },
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });
  assert.ok(cooldown.reason.includes('cooldown'));
  assert.equal(cooldown.delegationSource, 'static');

  // Ineffective but not stalled (single failing round) → continue-current.
  const continueCurrent = decideNextAgent({
    state: {
      current_agent: 'codex',
      iteration: 20,
      last_switch_iteration: 10,
      effectiveness_history: [{ iteration: 20, commits: 0, tasks: 0, gate: 'fail' }],
    },
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
  });
  assert.equal(continueCurrent.reason, 'continue-current');
  assert.equal(continueCurrent.delegationSource, 'static');
});

test('stalled-no-alternatives preserves computed delegationSource', () => {
  const soloRegistry = {
    default_agent: 'codex',
    agents: {
      codex: mockRegistry.agents.codex,
    },
  };
  const soloSecrets = { CODEX_AUTH_JSON: true };

  const staticFallback = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: soloSecrets,
    registry: soloRegistry,
    routeWeights: null,
  });
  assert.equal(staticFallback.reason, 'stalled-no-alternatives (delegation_source: static (route-weights-unavailable))');
  assert.equal(staticFallback.delegationSource, 'static');
  assert.equal(staticFallback.shouldSwitch, false);
  assert.equal(staticFallback.agent, 'codex');

  // Evidence-bearing export with no eligible alternate still preserves the
  // computed static source (not a hardcoded literal bypass of the weighted result).
  const evidenceNoAlternate = decideNextAgent({
    state: stalledStateCodex,
    labels: ['agent:auto'],
    secrets: soloSecrets,
    registry: soloRegistry,
    routeWeights: {
      schema: 'orchestrator.route-weights/v1',
      generated_at: now,
      task_types: {
        implement: {
          evidence_ok: true,
          ranking: [{ agent: 'codex', posterior: 0.9, n_obs: 100 }],
        },
      },
    },
  });
  assert.equal(
    evidenceNoAlternate.reason,
    'stalled-no-alternatives (delegation_source: static (route-weights-no-eligible-agent))'
  );
  assert.equal(evidenceNoAlternate.delegationSource, 'static');
  assert.equal(evidenceNoAlternate.shouldSwitch, false);
  assert.equal(evidenceNoAlternate.agent, 'codex');
});

test('exploration branch delegates to the published challenger at the published rate and reports the policy version', () => {
  assert.equal(routeWeightsWithExploration.exploration.rate, 0.05);
  const result = decideNextAgent({
    state: { iteration: 7 },
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: routeWeightsWithExploration,
  });

  assert.equal(result.agent, 'gemini');
  assert.equal(result.delegationSource, 'route_weights_exploration');
  assert.equal(result.policy_version, 'exploration-2026-10-06');
  assert.equal(result.shouldSwitch, false);

  const summary = formatDelegationSummary({ decision: result });
  assert.match(summary, /\*\*Delegation source:\*\* route_weights_exploration/);
  assert.match(summary, /\*\*Policy version:\*\* exploration-2026-10-06/);

  // Seed 100 draws between 1% and the published 5%; seed 500 draws above 5%.
  // These fixed cases reject both always-explore and hard-coded-rate routing.
  for (const { seed, rate, agent } of [
    { seed: 100, rate: 0.05, agent: 'gemini' },
    { seed: 100, rate: 0.01, agent: 'cursor' },
    { seed: 500, rate: 0.05, agent: 'cursor' },
    { seed: 500, rate: 1, agent: 'gemini' },
    { seed: 7, rate: 0, agent: 'cursor' },
  ]) {
    const decision = decideNextAgent({
      state: { iteration: seed },
      labels: ['agent:auto'],
      secrets: mockSecrets,
      registry: mockRegistry,
      routeWeights: {
        ...routeWeightsWithExploration,
        exploration: { ...routeWeightsWithExploration.exploration, rate },
      },
    });
    assert.equal(decision.agent, agent, `seed=${seed}, rate=${rate}`);
    assert.equal(
      decision.delegationSource,
      agent === 'gemini' ? 'route_weights_exploration' : 'route_weights'
    );
    assert.equal(
      decision.policy_version,
      agent === 'gemini' ? 'exploration-2026-10-06' : undefined
    );
  }

  // Verify the published rate over a fixed population as well as individual draws.
  // A 0.3 percentage-point tolerance is over four standard deviations at 5%.
  const populationSize = 100000;
  let explorationSelections = 0;
  for (let seed = 1; seed <= populationSize; seed++) {
    const decision = pickAgent({
      taskType: 'implement',
      routeWeights: routeWeightsWithExploration,
      agents: mockRegistry.agents,
      seed,
    });
    if (decision.delegationSource === 'route_weights_exploration') {
      explorationSelections++;
      assert.equal(decision.agent, routeWeightsWithExploration.exploration.challengers.implement);
      assert.equal(decision.policy_version, routeWeightsWithExploration.exploration.policy_version);
    } else {
      assert.equal(decision.agent, 'cursor');
      assert.equal(decision.delegationSource, 'route_weights');
      assert.equal(decision.policy_version, undefined);
    }
  }
  const observedRate = explorationSelections / populationSize;
  assert.ok(
    Math.abs(observedRate - routeWeightsWithExploration.exploration.rate) < 0.003,
    `observed exploration rate ${observedRate} must match the published rate`,
  );
});

for (const policyPath of [
  '../agent_delegation_policy.js',
  '../../../templates/consumer-repo/.github/scripts/agent_delegation_policy.js',
]) {
  test(`exploration retains ranking at the exact seeded rate boundary (${policyPath})`, () => {
    const policy = require(policyPath);
    // Seed 100 has this fixed draw. Pin the boundary independently of the draw helper.
    const drawNumerator = 101522310;
    const denominator = 4294967296;
    for (const offset of [-1, 0, 1]) {
      const result = policy.pickAgent({
        taskType: 'implement',
        seed: 100,
        agents: mockRegistry.agents,
        routeWeights: {
          ...routeWeightsWithExploration,
          exploration: {
            ...routeWeightsWithExploration.exploration,
            rate: (drawNumerator + offset) / denominator,
          },
        },
      });

      const explores = offset > 0;
      assert.equal(result.agent, explores ? 'gemini' : 'cursor', `offset=${offset}`);
      assert.equal(
        result.delegationSource,
        explores ? 'route_weights_exploration' : 'route_weights',
        `offset=${offset}`
      );
      assert.equal(
        result.policy_version,
        explores ? routeWeightsWithExploration.exploration.policy_version : undefined,
        `offset=${offset}`
      );
    }
  });
}

test('exploration retains the ranking pick when the challenger is ineligible or reserved', async (t) => {
  const cases = [
    { name: 'reserved by task type', reserve: { implement: [{ agent: 'gemini' }] } },
    { name: 'reserved by legacy list', reserve: ['GEMINI'] },
    { name: 'missing prerequisites', secrets: { ...mockSecrets, GEMINI_API_KEY: false } },
    { name: 'runner absent from current tree', runnableAgents: ['codex', 'claude', 'cursor'] },
    { name: 'disabled in registry', agentConfig: { enabled: false } },
    { name: 'no runner workflow', agentConfig: { runner_workflow: '' } },
    { name: 'no keepalive capability', agentConfig: { capabilities: { pr_keepalive: false } } },
    { name: 'unknown challenger', challengers: { implement: 'unregistered-agent' } },
    { name: 'challenger missing for task type', challengers: { review: 'gemini' } },
  ];

  for (const scenario of cases) {
    await t.test(scenario.name, () => {
      const decision = decideNextAgent({
        state: { iteration: 7 },
        labels: ['agent:auto'],
        secrets: scenario.secrets || mockSecrets,
        runnableAgents: scenario.runnableAgents,
        registry: {
          ...mockRegistry,
          agents: {
            ...mockRegistry.agents,
            gemini: { ...mockRegistry.agents.gemini, ...scenario.agentConfig },
          },
        },
        routeWeights: {
          ...routeWeightsWithExploration,
          reserve: scenario.reserve || routeWeightsWithExploration.reserve,
          exploration: {
            ...routeWeightsWithExploration.exploration,
            challengers: scenario.challengers || routeWeightsWithExploration.exploration.challengers,
          },
        },
      });

      assert.equal(decision.agent, 'cursor');
      assert.equal(decision.delegationSource, 'route_weights');
      assert.equal(decision.policy_version, undefined);
    });
  }
});

test('stalled delegation propagates exploration metadata and never reselects the current challenger', () => {
  // This live PR/iteration identity produces an exploration draw below 5%.
  const state = { ...stalledStateCodex, pr_number: 3840, iteration: 99 };
  const options = {
    state,
    labels: ['agent:auto'],
    secrets: mockSecrets,
    registry: mockRegistry,
    routeWeights: routeWeightsWithExploration,
  };
  const exploration = decideNextAgent(options);
  assert.equal(exploration.agent, 'gemini');
  assert.equal(exploration.shouldSwitch, true);
  assert.equal(exploration.previousAgent, 'codex');
  assert.equal(exploration.delegationSource, 'route_weights_exploration');
  assert.equal(exploration.policy_version, 'exploration-2026-10-06');

  const ranking = decideNextAgent({ ...options, state: { ...state, current_agent: 'gemini' } });
  assert.equal(ranking.agent, 'cursor');
  assert.equal(ranking.shouldSwitch, true);
  assert.equal(ranking.delegationSource, 'route_weights');
  assert.equal(ranking.policy_version, undefined);
});

test('pickAgent CLI helper reports exploration delegation for a seeded draw', () => {
  const picked = pickAgent({
    taskType: 'implement',
    routeWeights: routeWeightsWithExploration,
    seed: 7,
  });

  assert.equal(picked.agent, 'gemini');
  assert.equal(picked.delegationSource, 'route_weights_exploration');
  assert.equal(picked.policy_version, 'exploration-2026-10-06');
});

test('exploration reports the current published policy version for each keepalive task type', () => {
  const policyVersion = 'exploration-2026-10-13';
  for (const taskType of ['implement', 'review', 'testgen']) {
    const routeWeights = {
      ...routeWeightsWithExploration,
      task_types: { [taskType]: routeWeightsWithExploration.task_types.implement },
      exploration: {
        ...routeWeightsWithExploration.exploration,
        policy_version: policyVersion,
      },
    };
    const decision = decideNextAgent({
      state: { iteration: 7 },
      labels: ['agent:auto'],
      secrets: mockSecrets,
      registry: mockRegistry,
      routeWeights,
      roundKind: taskType,
    });

    assert.equal(decision.agent, routeWeights.exploration.challengers[taskType], taskType);
    assert.equal(decision.delegationSource, 'route_weights_exploration', taskType);
    assert.equal(decision.policy_version, policyVersion, taskType);
    const summary = formatDelegationSummary({ decision });
    assert.ok(summary.includes(`**Policy version:** ${policyVersion}`), taskType);
    assert.ok(!summary.includes(routeWeightsWithExploration.exploration.policy_version), taskType);
  }
});

test('exploration selects distinct published challengers and scopes reservations to the task type', () => {
  const challengers = { implement: 'gemini', review: 'cursor', testgen: 'claude' };
  const reserve = {
    implement: [{ agent: 'claude' }],
    review: [{ agent: 'gemini' }],
    testgen: [{ agent: 'cursor' }],
  };
  const routeWeights = {
    ...routeWeightsWithExploration,
    task_types: Object.fromEntries(Object.keys(challengers).map((taskType) => [
      taskType, routeWeightsWithExploration.task_types.implement,
    ])),
    exploration: { ...routeWeightsWithExploration.exploration, challengers },
    reserve,
  };

  for (const [taskType, challenger] of Object.entries(challengers)) {
    const options = {
      state: { iteration: 7 },
      labels: ['agent:auto'],
      secrets: mockSecrets,
      registry: mockRegistry,
      routeWeights,
      roundKind: taskType,
    };
    // Each challenger is reserved for another task, which must not disqualify it here.
    const selected = decideNextAgent(options);
    assert.equal(selected.agent, challenger, taskType);
    assert.equal(selected.delegationSource, 'route_weights_exploration', taskType);
    assert.equal(selected.policy_version, routeWeights.exploration.policy_version, taskType);

    const blocked = decideNextAgent({
      ...options,
      routeWeights: {
        ...routeWeights,
        reserve: {
          ...reserve,
          [taskType]: [...reserve[taskType], { agent: challenger }],
        },
      },
    });
    assert.equal(blocked.agent, taskType === 'implement' ? 'cursor' : 'codex', taskType);
    assert.equal(blocked.delegationSource, 'route_weights', taskType);
    assert.equal(blocked.policy_version, undefined, taskType);
  }
});

test('zero seed does not force exploration for every positive rate', () => {
  const weighted = selectAgentFromRouteWeights({
    routeWeights: routeWeightsWithExploration,
    taskType: 'implement',
    currentAgent: '',
    availableAgents: ['cursor', 'codex', 'claude', 'gemini'],
    agents: mockRegistry.agents,
    seed: 0,
  });

  assert.equal(weighted.agent, 'cursor');
  assert.equal(weighted.delegationSource, 'route_weights');
  assert.equal(weighted.policy_version, undefined);
});

test('exploration seed incorporates pr_number so empty state is not shared', () => {
  assert.notEqual(explorationSeedFromState({}), explorationSeedFromState({ pr_number: 3840 }));
  assert.equal(explorationSeedFromState({ pr_number: 3840, iteration: 2 }), Math.imul(3840, 10007) + 2);
});

test('ignoring the exploration block restores ranking selection', () => {
  const withoutExploration = {
    ...routeWeightsWithExploration,
    exploration: undefined,
  };

  const weighted = selectAgentFromRouteWeights({
    routeWeights: withoutExploration,
    taskType: 'implement',
    currentAgent: '',
    availableAgents: ['cursor', 'codex', 'claude', 'gemini'],
    agents: mockRegistry.agents,
    seed: 7,
  });

  assert.equal(weighted.agent, 'cursor');
  assert.equal(weighted.delegationSource, 'route_weights');
});
