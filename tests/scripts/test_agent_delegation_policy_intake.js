/**
 * Tests for intake agent selection in agent_delegation_policy.js
 *
 * Covers capacity-aware route-weights selection via fetchRouteWeights() and
 * chooseAgentForIntake(taskType, routeWeights, registryAgents).
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const {
  fetchRouteWeights,
  chooseAgentForIntake,
} = require('../../.github/scripts/agent_delegation_policy.js');

const now = '2026-10-16T12:00:00Z';

const mockRegistryAgents = {
  codex: {
    runner_workflow: '.github/workflows/reusable-codex-run.yml',
    capabilities: { pr_keepalive: true },
  },
  claude: {
    runner_workflow: '.github/workflows/reusable-claude-run.yml',
    capabilities: { pr_keepalive: true },
  },
  cursor: {
    runner_workflow: '.github/workflows/reusable-cursor-run.yml',
    capabilities: { pr_keepalive: true },
  },
  gemini: {
    runner_workflow: '.github/workflows/reusable-gemini-run.yml',
    capabilities: { pr_keepalive: true },
  },
  copilot: {
    runner_workflow: null,
    capabilities: { pr_keepalive: false },
  },
};

test('ok pools -> highest posterior wins', () => {
  const routeWeights = {
    schema: 'orchestrator.route-weights/v2',
    generated_at: now,
    capacity: {
      claude: { state: 'ok', window: '5h', observed_at: 1792152000 },
      cursor: { state: 'ok', window: '5h', observed_at: 1792152000 },
      codex: { state: 'ok', window: '5h', observed_at: 1792152000 },
    },
    task_types: {
      implement: {
        evidence_ok: true,
        ranking: [
          { agent: 'codex', posterior: 0.61, n_obs: 30 },
          { agent: 'claude', posterior: 0.84, n_obs: 28 },
          { agent: 'cursor', posterior: 0.72, n_obs: 25 },
        ],
      },
    },
  };

  const decision = chooseAgentForIntake('implement', routeWeights, mockRegistryAgents, { now });
  assert.equal(decision.agent, 'claude');
  assert.equal(String(decision), 'claude');
  assert.equal(decision.posterior, 0.84);
  assert.equal(decision.poolState, 'ok');
  assert.equal(decision.delegationSource, 'route_weights');

  // Pre-v2 exports without a capacity block treat all pools as ok and still pick by posterior.
  const v1Weights = {
    schema: 'orchestrator.route-weights/v1',
    generated_at: now,
    task_types: routeWeights.task_types,
  };
  const v1Decision = chooseAgentForIntake('implement', v1Weights, mockRegistryAgents, { now });
  assert.equal(v1Decision.agent, 'claude');
  assert.equal(v1Decision.posterior, 0.84);
  assert.equal(v1Decision.poolState, 'ok');
});

test('top pool shed -> next agent', () => {
  const routeWeights = {
    schema: 'orchestrator.route-weights/v2',
    generated_at: now,
    capacity: {
      claude: { state: 'shed', window: '5h', observed_at: 1792152000 },
      cursor: { state: 'ok', window: '5h', observed_at: 1792152000 },
      codex: { state: 'ok', window: '5h', observed_at: 1792152000 },
    },
    task_types: {
      implement: {
        evidence_ok: true,
        ranking: [
          { agent: 'claude', posterior: 0.88, n_obs: 35 },
          { agent: 'cursor', posterior: 0.76, n_obs: 30 },
          { agent: 'codex', posterior: 0.62, n_obs: 40 },
        ],
      },
    },
  };

  const decision = chooseAgentForIntake('implement', routeWeights, mockRegistryAgents, { now });
  assert.equal(decision.agent, 'cursor');
  assert.equal(decision.posterior, 0.76);
  assert.equal(decision.poolState, 'ok');
  assert.equal(decision.delegationSource, 'route_weights');
});

test('export stale -> static default', async () => {
  const staleWeights = {
    schema: 'orchestrator.route-weights/v2',
    generated_at: '2026-09-01T00:00:00Z',
    capacity: {
      claude: { state: 'ok' },
    },
    task_types: {
      implement: {
        evidence_ok: true,
        ranking: [
          { agent: 'claude', posterior: 0.91, n_obs: 40 },
        ],
      },
    },
  };

  const fetched = await fetchRouteWeights({
    url: 'https://example.test/route-weights.json',
    now,
    fetchImpl: async () => ({
      status: 200,
      json: async () => staleWeights,
    }),
  });
  assert.equal(fetched, null);

  const fromNull = chooseAgentForIntake('implement', fetched, mockRegistryAgents, { now });
  assert.equal(fromNull.agent, 'codex');
  assert.equal(fromNull.posterior, null);
  assert.equal(fromNull.poolState, 'static');
  assert.equal(fromNull.delegationSource, 'static');

  const fromStaleObject = chooseAgentForIntake('implement', staleWeights, mockRegistryAgents, { now });
  assert.equal(fromStaleObject.agent, 'codex');
  assert.equal(fromStaleObject.posterior, null);
  assert.equal(fromStaleObject.poolState, 'static');
  assert.equal(fromStaleObject.delegationSource, 'static');
  assert.equal(fromStaleObject.reason, 'route-weights-stale');
});

test('no runner -> skipped', () => {
  const routeWeights = {
    schema: 'orchestrator.route-weights/v2',
    generated_at: now,
    capacity: {
      copilot: { state: 'ok' },
      unregistered: { state: 'ok' },
      gemini: { state: 'ok' },
    },
    task_types: {
      implement: {
        evidence_ok: true,
        ranking: [
          { agent: 'copilot', posterior: 0.95, n_obs: 25 },
          { agent: 'unregistered', posterior: 0.9, n_obs: 25 },
          { agent: 'gemini', posterior: 0.78, n_obs: 25 },
        ],
      },
    },
  };

  const decision = chooseAgentForIntake('implement', routeWeights, mockRegistryAgents, { now });
  assert.equal(decision.agent, 'gemini');
  assert.equal(decision.posterior, 0.78);
  assert.equal(decision.poolState, 'ok');
  assert.equal(decision.delegationSource, 'route_weights');
});

test('intake workflows call chooseAgentForIntake and preserve chosen agent through bridge dispatch', () => {
  const repoRoot = path.resolve(__dirname, '../..');
  const rootWorkflow = fs.readFileSync(
    path.join(repoRoot, '.github/workflows/agents-63-issue-intake.yml'),
    'utf8'
  );
  const consumerWorkflow = fs.readFileSync(
    path.join(repoRoot, 'templates/consumer-repo/.github/workflows/agents-issue-intake.yml'),
    'utf8'
  );

  for (const workflowText of [rootWorkflow, consumerWorkflow]) {
    assert.match(workflowText, /fetchRouteWeights/);
    assert.match(workflowText, /chooseAgentForIntake\('implement',\s*routeWeights,\s*registry\.agents\)/);
    assert.match(workflowText, /core\.summary/);
  }

  assert.match(
    rootWorkflow,
    /needs\.bridge_preflight\.outputs\.agent_key\s*\|\|\s*needs\.normalize_inputs\.outputs\.bridge_agent/
  );
});
