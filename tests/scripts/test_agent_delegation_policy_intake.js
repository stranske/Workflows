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
const { loadAgentRegistry } = require('../../.github/scripts/agent_registry.js');

const {
  fetchRouteWeights,
  chooseAgentForIntake,
} = require('../../.github/scripts/agent_delegation_policy.js');
const {
  formatRouteWeightsStatus: realFormatRouteWeightsStatus,
} = require('../../.github/scripts/agent_delegation_policy.js');

// A loadRouteWeightsWithStatus() result shape; executeStep overrides document/status per case.
const STUB_LOAD = {
  document: null,
  status: 'fresh',
  detail: '',
  url: 'https://example.test/rw.json',
  httpStatus: 200,
  generatedAt: '2026-11-11T13:00:00Z',
  ageMs: 5 * 3600000,
  maxAgeMs: 14 * 24 * 3600000,
  schema: 'orchestrator.route-weights/v1',
  sourceVersion: 72,
};
const STUB_FRESH_LINE = realFormatRouteWeightsStatus(STUB_LOAD);

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

for (const [copy, policy] of [
  ['source', require('../../.github/scripts/agent_delegation_policy.js')],
  ['template', require('../../templates/consumer-repo/.github/scripts/agent_delegation_policy.js')],
]) {
  test(`${copy}: top pool shed and next exhausted -> highest remaining ok agent`, async () => {
    const document = {
      schema: 'orchestrator.route-weights/v1',
      generated_at: now,
      capacity_schema: 'orchestrator.route-weights-capacity/v1',
      capacity: {
        claude: { state: 'shed' },
        cursor: { state: 'exhausted' },
        codex: { state: 'ok' },
      },
      task_types: {
        implement: {
          evidence_ok: true,
          ranking: [
            { agent: 'codex', posterior: 0.62 },
            { agent: 'claude', posterior: 0.88 },
            { agent: 'cursor', posterior: 0.76 },
          ],
        },
      },
    };
    const fetched = await policy.fetchRouteWeights({
      now,
      fetchImpl: async () => ({ status: 200, json: async () => document }),
    });
    assert.deepEqual(fetched, document);
    const decision = policy.chooseAgentForIntake('implement', fetched, mockRegistryAgents, { now });
    assert.deepEqual(decision, {
      agent: 'codex', posterior: 0.62, poolState: 'ok', pool_state: 'ok',
      delegationSource: 'route_weights', reason: 'route-weights',
    });
  });

  for (const schema of ['orchestrator.route-weights/v1', 'orchestrator.route-weights/v2']) {
    for (const [capacityName, capacity] of [
      ['absent', undefined],
      ['empty', {}],
      ['partial', { codex: { state: 'shed' } }],
    ]) {
      test(`${copy}: ${schema} ${capacityName} capacity still picks by posterior`, async () => {
        const document = {
          schema,
          generated_at: now,
          ...(capacity === undefined ? {} : { capacity }),
          task_types: {
            implement: {
              evidence_ok: true,
              // Deliberately unsorted: the static default and first row both lose.
              ranking: [
                { agent: 'codex', posterior: 0.61 },
                { agent: 'cursor', posterior: 0.72 },
                { agent: 'claude', posterior: 0.84 },
              ],
            },
          },
        };
        const fetched = await policy.fetchRouteWeights({
          now,
          fetchImpl: async () => ({ status: 200, json: async () => document }),
        });
        assert.deepEqual(fetched, document);
        const decision = policy.chooseAgentForIntake('implement', fetched, mockRegistryAgents, { now });
        assert.equal(decision.agent, 'claude');
        assert.equal(decision.posterior, 0.84);
        assert.equal(decision.poolState, 'ok');
        assert.equal(decision.delegationSource, 'route_weights');
      });
    }

    for (const state of ['shed', 'exhausted', 'unknown']) {
      test(`${copy}: ${schema} published ${state} capacity overrides ranking ok hints`, async () => {
        const document = {
          schema,
          generated_at: now,
          capacity_schema: 'orchestrator.route-weights-capacity/v1',
          capacity: {
            claude: { state, window: '5h+weekly', observed_at: 1792152000 },
            cursor: { state: 'ok', window: 'monthly', observed_at: 1792152000 },
          },
          task_types: {
            implement: {
              evidence_ok: true,
              ranking: [
                { agent: 'claude', posterior: 0.88, pool_state: 'ok' },
                { agent: 'cursor', posterior: 0.76 },
              ],
            },
          },
        };
        const fetched = await policy.fetchRouteWeights({
          now,
          fetchImpl: async () => ({ status: 200, json: async () => document }),
        });
        assert.deepEqual(fetched, document);
        const decision = policy.chooseAgentForIntake('implement', fetched, mockRegistryAgents, { now });
        assert.equal(decision.agent, 'cursor');
        assert.equal(decision.posterior, 0.76);
        assert.equal(decision.poolState, 'ok');
        assert.equal(decision.delegationSource, 'route_weights');
      });
    }
  }
}

for (const [copy, chooseIntake] of [
  ['source', chooseAgentForIntake],
  ['template', require('../../templates/consumer-repo/.github/scripts/agent_delegation_policy.js').chooseAgentForIntake],
]) {
  test(`${copy}: explicit false preserves insufficient-evidence reason and configured default`, () => {
    const decision = chooseIntake('implement', {
      task_types: {
        implement: {
          evidence_ok: false,
          ranking: [{ agent: 'claude', posterior: 0.91 }],
        },
      },
    }, mockRegistryAgents, { defaultAgent: 'cursor' });
    assert.deepEqual(decision, {
      agent: 'cursor', posterior: null, poolState: 'static', pool_state: 'static',
      delegationSource: 'static', reason: 'route-weights-insufficient-evidence',
    });
  });

  for (const [name, evidence] of [
    ['string "false"', { evidence_ok: 'false' }],
    ['missing', {}],
    ['boolean false', { evidence_ok: false }],
    ['null', { evidence_ok: null }],
    ['number zero', { evidence_ok: 0 }],
    ['number one', { evidence_ok: 1 }],
    ['string "true"', { evidence_ok: 'true' }],
    ['boolean true', { evidence_ok: true }],
  ]) {
    test(`${copy}: intake evidence ${name}`, () => {
      const routeWeights = {
        schema: 'orchestrator.route-weights/v2',
        generated_at: now,
        capacity: { claude: { state: 'ok' } },
        task_types: {
          implement: {
            ...evidence,
            ranking: [{ agent: 'claude', posterior: 0.91, n_obs: 40 }],
          },
        },
      };

      const decision = chooseIntake('implement', routeWeights, mockRegistryAgents, { now });
      if (name === 'boolean true') {
        assert.deepEqual(decision, {
          agent: 'claude', posterior: 0.91, poolState: 'ok', pool_state: 'ok',
          delegationSource: 'route_weights', reason: 'route-weights',
        });
      } else {
        assert.deepEqual(decision, {
          agent: 'codex', posterior: null, poolState: 'static', pool_state: 'static',
          delegationSource: 'static',
          reason: name === 'boolean false'
            ? 'route-weights-insufficient-evidence'
            : 'route-weights-evidence-not-affirmed',
        });
      }
    });
  }
}

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

test('no runner -> skipped using the shipped registry', () => {
  const registryAgents = loadAgentRegistry({
    registryPath: path.resolve(__dirname, '../../.github/agents/registry.yml'),
  }).agents;
  assert.equal(registryAgents.aider.runner_workflow, '');
  assert.ok(registryAgents.claude.runner_workflow);
  const routeWeights = {
    schema: 'orchestrator.route-weights/v2',
    generated_at: now,
    capacity: {
      aider: { state: 'ok' },
      unregistered: { state: 'ok' },
      claude: { state: 'ok' },
    },
    task_types: {
      implement: {
        evidence_ok: true,
        ranking: [
          { agent: 'aider', posterior: 0.95, n_obs: 25 },
          { agent: 'unregistered', posterior: 0.9, n_obs: 25 },
          { agent: 'claude', posterior: 0.78, n_obs: 25 },
        ],
      },
    },
  };

  const decision = chooseAgentForIntake('implement', routeWeights, registryAgents, { now });
  assert.equal(decision.agent, 'claude');
  assert.equal(decision.posterior, 0.78);
  assert.equal(decision.poolState, 'ok');
  assert.equal(decision.delegationSource, 'route_weights');
});

// Extract the complete github-script block, then execute it with isolated env/API stubs.
// Assertions below inspect outputs and failures, rather than YAML source patterns.
function stepScript(workflowPath, stepId) {
  const lines = fs.readFileSync(path.resolve(__dirname, '../..', workflowPath), 'utf8').split('\n');
  const step = lines.findIndex(line => line.trim() === `id: ${stepId}`);
  assert.ok(step >= 0);
  const start = lines.findIndex((line, index) => index > step && line.trim() === 'script: |');
  assert.ok(start > step);
  const indent = lines[start].match(/^ */)[0].length + 2;
  const body = [];
  for (const line of lines.slice(start + 1)) {
    if (line.trim() && line.search(/\S/) < indent) break;
    body.push(line.slice(indent));
  }
  return body.join('\n').replaceAll('${{ inputs.issue_number }}', '');
}

const workflows = [
  ['.github/workflows/agents-63-issue-intake.yml', 'inspect', 'agent_key'],
  ['templates/consumer-repo/.github/workflows/agents-issue-intake.yml', 'check', 'agent'],
];

async function executeStep(workflow, { input = '', labels, failure, routeWeights } = {}) {
  const [file, id] = workflow;
  const policy = file.startsWith('templates/')
    ? require('../../templates/consumer-repo/.github/scripts/agent_delegation_policy.js')
    : { chooseAgentForIntake, formatRouteWeightsStatus: realFormatRouteWeightsStatus };
  const outputs = {};
  const warnings = [];
  const infos = [];
  const failures = [];
  const summaryTables = [];
  let summaryWrites = 0;
  let fetches = 0;
  const summary = {
    addHeading() { return this; },
    addTable(rows) { summaryTables.push(rows); return this; },
    async write() { summaryWrites += 1; },
  };
  const core = {
    summary,
    warning: message => warnings.push(message),
    info: message => infos.push(message),
    setOutput: (key, value) => { outputs[key] = value; },
    setFailed: message => failures.push(message),
  };
  const context = {
    eventName: labels ? 'issues' : 'workflow_dispatch',
    repo: { owner: 'test', repo: 'intake' },
    payload: labels ? { issue: { number: 7, labels: labels.map(name => ({ name })) } } : {},
  };
  const stubRequire = name => {
    if (name === 'fs') return { existsSync: () => false };
    if (name.endsWith('agent_registry.js')) {
      if (failure === 'require') throw new Error('module unavailable');
      return {
        loadAgentRegistry() {
          if (failure === 'registry') throw new Error('invalid registry');
          return loadAgentRegistry({
            registryPath: path.resolve(__dirname, '../../.github/agents/registry.yml'),
          });
        },
      };
    }
    if (name.endsWith('agent_delegation_policy.js')) return {
      async loadRouteWeightsWithStatus() {
        fetches += 1;
        if (failure === 'fetch') throw new Error('export unavailable');
        if (failure === 'null-export') {
          return {
            ...STUB_LOAD,
            status: 'stale',
            detail: 'older than the reader max age',
            generatedAt: '2026-10-24T12:52:52Z',
            ageMs: 437.1 * 3600000,
            sourceVersion: 69,
          };
        }
        return {
          ...STUB_LOAD,
          document: routeWeights || {
            schema: 'orchestrator.route-weights/v2',
            generated_at: new Date().toISOString(),
            task_types: { implement: { evidence_ok: true, ranking: [
              { agent: 'claude', posterior: 0.9, n_obs: 30 },
            ] } },
          },
        };
      },
      formatRouteWeightsStatus(result) {
        return policy.formatRouteWeightsStatus(result);
      },
      chooseAgentForIntake(...args) {
        if (failure === 'chooser') throw new Error('chooser error');
        return policy.chooseAgentForIntake(...args);
      },
    };
    throw new Error(`Unexpected require: ${name}`);
  };
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction('require', 'process', 'context', 'core', 'github', 'console', stepScript(file, id))(
    stubRequire, { env: { DEFAULT_AGENT: input, INPUT_ISSUE: '' } }, context, core, {}, { log() {} },
  );
  return { outputs, warnings, infos, failures, fetches, summaryTables, summaryWrites };
}

for (const workflow of workflows) {
  const [file, , output] = workflow;
  test(`${file}: empty input preserves the chooser default`, async () => {
    const result = await executeStep(workflow);
    assert.equal(result.outputs[output], 'claude');
    assert.equal(result.fetches, 1);
    assert.deepEqual(result.failures, []);
    assert.deepEqual(result.warnings, []);
    assert.equal(result.summaryWrites, 1);
    assert.deepEqual(result.summaryTables[0][1], ['claude', '0.9', 'ok', 'claude', STUB_FRESH_LINE]);
    assert.deepEqual(result.infos.filter(line => line.startsWith('route-weights:')), [STUB_FRESH_LINE]);
  });

  for (const state of ['ok', 'shed', 'exhausted']) {
    test(`${file}: ${state} top pool selects and summarizes the eligible default`, async () => {
      const result = await executeStep(workflow, {
        input: '  ',
        routeWeights: {
          schema: 'orchestrator.route-weights/v1',
          generated_at: new Date().toISOString(),
          capacity_schema: 'orchestrator.route-weights-capacity/v1',
          capacity: { codex: { state }, claude: { state: 'ok' } },
          task_types: { implement: { evidence_ok: true, ranking: [
            { agent: 'claude', posterior: 0.8 },
            { agent: 'codex', posterior: 0.95 },
          ] } },
        },
      });
      const selected = state === 'ok' ? 'codex' : 'claude';
      const posterior = state === 'ok' ? '0.95' : '0.8';
      assert.equal(result.outputs[output], selected);
      assert.equal(result.fetches, 1);
      assert.deepEqual(result.failures, []);
      assert.deepEqual(result.warnings, []);
      assert.equal(result.summaryWrites, 1);
      assert.deepEqual(result.summaryTables[0][1], [selected, posterior, 'ok', selected, STUB_FRESH_LINE]);
    });
  }

  test(`${file}: explicit input bypasses the chooser`, async () => {
    const result = await executeStep(workflow, { input: 'claude', failure: 'require' });
    assert.equal(result.outputs[output], 'claude');
    assert.equal(result.fetches, 0);
    assert.deepEqual(result.warnings, []);
    assert.match(result.summaryTables[0][1][4], /^route-weights: not consulted/);
  });

  test(`${file}: a stale export names its status and age in the fallback warning`, async () => {
    const result = await executeStep(workflow, { failure: 'null-export' });
    assert.equal(result.outputs[output], 'codex');
    assert.equal(result.warnings.length, 1);
    assert.match(
      result.warnings[0],
      /using static default codex: route-weights: stale \(older than the reader max age, age 437\.1h > max 336\.0h, generated_at=2026-10-24T12:52:52Z/,
    );
  });

  for (const failure of ['require', 'registry', 'fetch', 'null-export', 'chooser']) {
    test(`${file}: ${failure} failure warns and retains static default`, async () => {
      const result = await executeStep(workflow, { failure });
      assert.equal(result.outputs[output], 'codex');
      assert.equal(result.warnings.length, 1);
      assert.match(result.warnings[0], /using static default codex/);
      assert.deepEqual(result.failures, []);
    });
  }

  test(`${file}: agent:auto remains a routing label`, async () => {
    const result = await executeStep(workflow, { labels: ['agent:auto'] });
    assert.equal(result.outputs[output], 'auto');
    assert.deepEqual(result.failures, []);
  });
}

test('root preflight still requires exactly one agent label', async () => {
  for (const labels of [[], ['agent:claude', 'agent:gemini'], ['agent:auto', 'agent:codex']]) {
    const result = await executeStep(workflows[0], { labels });
    assert.equal(result.failures.length, 1);
    assert.match(result.failures[0], /Expected exactly one agent:\* label/);
    assert.equal(result.outputs.agent_key, undefined);
  }
});

test('root bridge dispatch retains normalized bridge input precedence', () => {
  const text = fs.readFileSync(path.resolve(__dirname, '../../.github/workflows/agents-63-issue-intake.yml'), 'utf8');
  const job = text.slice(text.indexOf('\n  agent_bridge:'));
  const expression = job.split('agent: >-')[1].split('${{')[1].split('}}')[0];
  const dispatch = new Function('needs', `return (${expression});`);
  const needs = {
    normalize_inputs: { outputs: { bridge_agent: 'claude' } },
    bridge_preflight: { outputs: { agent_key: 'gemini' } },
  };
  assert.equal(dispatch(needs), 'claude');
  needs.normalize_inputs.outputs.bridge_agent = '';
  assert.equal(dispatch(needs), 'gemini');
});

for (const agent of ['muse', 'gemini']) {
  test(`preflight-disabled ${agent} cannot win intake using the shipped registry`, () => {
    const agents = loadAgentRegistry({
      registryPath: path.resolve(__dirname, '../../.github/agents/registry.yml'),
    }).agents;
    assert.equal(agents[agent].preflight.enabled, false);
    assert.ok(agents[agent].runner_workflow);
    assert.equal(agents.claude.preflight.enabled, true);
    const weights = {
      schema: 'orchestrator.route-weights/v2', generated_at: now,
      task_types: { implement: { evidence_ok: true, ranking: [
        { agent, posterior: 0.99, n_obs: 30 },
        { agent: 'claude', posterior: 0.80, n_obs: 30 },
      ] } },
    };
    const selected = chooseAgentForIntake('implement', weights, agents, { now });
    assert.equal(selected.agent, 'claude');
    assert.equal(selected.delegationSource, 'route_weights');
    weights.task_types.implement.ranking.pop();
    const fallback = chooseAgentForIntake('implement', weights, agents, { now });
    assert.equal(fallback.agent, 'codex');
    assert.equal(fallback.delegationSource, 'static');
  });
}
