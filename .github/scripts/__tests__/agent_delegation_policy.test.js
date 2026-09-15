/**
 * Tests for agent_delegation_policy.js
 *
 * These cases are intentionally narrow and focused on the route-weights policy
 * integration points used by keepalive delegation.
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  decideNextAgent,
  loadRouteWeights,
  resolveRoundKind,
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
      required_secrets: ['CLAUDE_CODE_OAUTH_TOKEN'],
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

const mockSecrets = {
  CODEX_AUTH_JSON: true,
  CLAUDE_CODE_OAUTH_TOKEN: true,
  CURSOR_API_KEY: true,
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
