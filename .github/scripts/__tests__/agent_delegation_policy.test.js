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
  // Keep clause reserved to validate "reserve exclusion" behavior elsewhere.
  reserve: ['claude'],
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
    reserve: ['claude'],
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

