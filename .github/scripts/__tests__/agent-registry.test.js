'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');

const {
  getAgentConfig,
  getRunnerWorkflow,
  loadAgentRegistry,
  parseRegistryYaml,
  resolveAgentFromLabels,
  resolveAgentRoutingFromLabels,
  getAgentEntries,
  getAgentPreflightConfigs,
  resolveExecutionProfile,
  validateAgentRegistry,
} = require('../agent_registry');

const REGISTRY_PATH = path.resolve(__dirname, '..', '..', 'agents', 'registry.yml');

test('parseRegistryYaml parses a basic mapping', () => {
  const value = parseRegistryYaml('version: 1\ndefault_agent: codex\nagents:\n');
  assert.equal(value.version, 1);
  assert.equal(value.default_agent, 'codex');
  assert.deepEqual(value.agents, {});
});

test('parseRegistryYaml rejects tab-indented lines', () => {
  assert.throws(
    () => {
      parseRegistryYaml('agents:\n\tcodex:\n  runner_workflow: x\n');
    },
    (error) => {
      assert.ok(error instanceof Error);
      assert.match(String(error.message), /tabs are not allowed/);
      return true;
    },
  );
});

test('loadAgentRegistry loads the repo registry file', () => {
  const registry = loadAgentRegistry({ registryPath: REGISTRY_PATH });
  assert.equal(registry.default_agent, 'codex');
  assert.ok(registry.agents);
  assert.ok(registry.agents.codex);
});

test('loadAgentRegistry accepts a registry path string', () => {
  const registry = loadAgentRegistry(REGISTRY_PATH);
  assert.equal(registry.default_agent, 'codex');
  assert.ok(registry.agents.codex);
});

test('runner helpers accept a registry path string', () => {
  assert.equal(resolveAgentFromLabels(['agent:codex'], REGISTRY_PATH), 'codex');
  assert.equal(getRunnerWorkflow('codex', REGISTRY_PATH), '.github/workflows/reusable-codex-run.yml');
});

test('resolveAgentFromLabels returns default agent when no labels present', () => {
  const agentKey = resolveAgentFromLabels([], { registryPath: REGISTRY_PATH });
  assert.equal(agentKey, 'codex');
});

test('resolveAgentFromLabels resolves agent label (string labels)', () => {
  const agentKey = resolveAgentFromLabels(['bug', 'agent:codex'], { registryPath: REGISTRY_PATH });
  assert.equal(agentKey, 'codex');
});

test('resolveAgentFromLabels resolves agent label (object labels)', () => {
  const agentKey = resolveAgentFromLabels([{ name: 'agent:codex' }], { registryPath: REGISTRY_PATH });
  assert.equal(agentKey, 'codex');
});

test('resolveAgentFromLabels is case-insensitive (string labels)', () => {
  const agentKey = resolveAgentFromLabels(['bug', 'Agent:Codex'], { registryPath: REGISTRY_PATH });
  assert.equal(agentKey, 'codex');
});

test('resolveAgentFromLabels is case-insensitive (object labels)', () => {
  const agentKey = resolveAgentFromLabels([{ name: 'AGENT:CODEX' }], { registryPath: REGISTRY_PATH });
  assert.equal(agentKey, 'codex');
});

test('resolveAgentFromLabels treats agent:auto as default agent', () => {
  const agentKey = resolveAgentFromLabels(['agent:auto'], { registryPath: REGISTRY_PATH });
  assert.equal(agentKey, 'codex');
});

test('resolveAgentRoutingFromLabels returns mode=auto for agent:auto', () => {
  const routing = resolveAgentRoutingFromLabels(['agent:auto'], { registryPath: REGISTRY_PATH });
  assert.equal(routing.mode, 'auto');
  assert.equal(routing.agentKey, 'codex');
  assert.equal(routing.requested, 'auto');
});
test('resolveAgentRoutingFromLabels returns mode=default when no agent labels present', () => {
  const routing = resolveAgentRoutingFromLabels(['bug'], { registryPath: REGISTRY_PATH });
  assert.equal(routing.mode, 'default');
  assert.equal(routing.agentKey, 'codex');
  assert.equal(routing.requested, null);
});
test('resolveAgentRoutingFromLabels returns mode=explicit for agent:codex', () => {
  const routing = resolveAgentRoutingFromLabels(['agent:codex'], { registryPath: REGISTRY_PATH });
  assert.equal(routing.mode, 'explicit');
  assert.equal(routing.agentKey, 'codex');
  assert.equal(routing.requested, 'codex');
});
test('resolveAgentRoutingFromLabels rejects mixing agent:auto with explicit agent', () => {
  assert.throws(
    () => {
      resolveAgentRoutingFromLabels(['agent:auto', 'agent:codex'], { registryPath: REGISTRY_PATH });
    },
    (error) => {
      assert.ok(error instanceof Error);
      assert.match(String(error.message), /Multiple agent labels present/);
      return true;
    },
  );
});

test('resolveAgentRoutingFromLabels rejects multiple explicit agent labels (string labels)', () => {
  assert.throws(
    () => {
      resolveAgentRoutingFromLabels(['agent:codex', 'agent:claude'], { registryPath: REGISTRY_PATH });
    },
    (error) => {
      assert.ok(error instanceof Error);
      assert.match(String(error.message), /Multiple agent labels present/);
      return true;
    },
  );
});

test('resolveAgentRoutingFromLabels rejects multiple explicit agent labels (object labels, case-insensitive)', () => {
  assert.throws(
    () => {
      resolveAgentRoutingFromLabels(
        [{ name: 'Agent:Codex' }, { name: 'AGENT:CLAUDE' }],
        { registryPath: REGISTRY_PATH },
      );
    },
    (error) => {
      assert.ok(error instanceof Error);
      assert.match(String(error.message), /Multiple agent labels present/);
      return true;
    },
  );
});

test('getAgentConfig returns config for codex', () => {
  const config = getAgentConfig('codex', { registryPath: REGISTRY_PATH });
  assert.equal(config.branch_prefix, 'codex/issue-');
  assert.deepEqual(config.capacity, { window: '5h', limit: 1 });
  assert.equal(config.ui_mentions_allowed, false);
  assert.ok(config.capabilities);
});

test('getRunnerWorkflow returns configured workflow path', () => {
  const workflow = getRunnerWorkflow('codex', { registryPath: REGISTRY_PATH });
  assert.equal(workflow, '.github/workflows/reusable-codex-run.yml');
});

test('getAgentEntries returns key/config pairs for each agent', () => {
  const entries = getAgentEntries({ registryPath: REGISTRY_PATH });
  assert.ok(Array.isArray(entries));
  assert.ok(entries.length >= 2);
  const codexEntry = entries.find((entry) => entry.key === 'codex');
  assert.ok(codexEntry);
  assert.equal(codexEntry.config.branch_prefix, 'codex/issue-');
});

test('getAgentPreflightConfigs honors enabled flag and readiness fallback', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-registry-'));
  const tmpPath = path.join(tmpDir, 'registry.yml');
  fs.writeFileSync(
    tmpPath,
    [
      'version: 1',
      'default_agent: codex',
      'agents:',
      '  enabled:',
      '    capacity:',
      '      window: daily',
      '      limit: 1',
      '    readiness_candidates:',
      '      - fallback-user',
      '    preflight:',
      '      command_phrase: ping',
      '  disabled:',
      '    capacity:',
      '      window: daily',
      '      limit: 1',
      '    preflight:',
      '      assign_user: disabled-user',
      '      enabled: false',
    ].join('\n'),
  );

  const configs = getAgentPreflightConfigs({ registryPath: tmpPath });
  assert.equal(configs.length, 1);
  assert.equal(configs[0].key, 'enabled');
  assert.equal(configs[0].assign_user, 'fallback-user');
  assert.equal(configs[0].command_phrase, 'ping');

  const configsWithDisabled = getAgentPreflightConfigs({ registryPath: tmpPath, includeDisabled: true });
  assert.equal(configsWithDisabled.length, 2);
  assert.equal(configsWithDisabled[1].key, 'disabled');
  assert.equal(configsWithDisabled[1].assign_user, 'disabled-user');
});

test('loadAgentRegistry exposes live and disabled planned-agent capacity blocks', () => {
  const registry = loadAgentRegistry({ registryPath: REGISTRY_PATH });
  assert.equal(registry.agents.gemini.enabled, true);
  assert.equal(registry.agents.aider.enabled, false);
  assert.deepEqual(registry.agents.gemini.capacity, { window: 'daily', limit: 1 });
  assert.deepEqual(registry.agents.aider.capacity, { window: 'daily', limit: 1 });
});

test('resolveExecutionProfile returns registry-backed codex model contract', () => {
  const profile = resolveExecutionProfile('codex-default', { registryPath: REGISTRY_PATH });
  assert.equal(profile.id, 'codex-default');
  assert.equal(profile.agent, 'codex');
  assert.equal(profile.model, 'gpt-5.5');
  assert.equal(profile.fallback_model, 'gpt-5.4');
  assert.equal(profile.runner, 'reusable-codex-run');
});

test('resolveExecutionProfile exposes the explicit Sol Terra Luna trial profiles', () => {
  const expected = {
    'codex-5.6-sol-high': ['gpt-5.6-sol', 'gpt-5.5'],
    'codex-5.6-terra-high': ['gpt-5.6-terra', 'gpt-5.5'],
    'codex-5.6-luna-high': ['gpt-5.6-luna', 'gpt-5.5'],
  };
  for (const [profileId, [model, fallback]] of Object.entries(expected)) {
    const profile = resolveExecutionProfile(profileId, { registryPath: REGISTRY_PATH });
    assert.equal(profile.agent, 'codex');
    assert.equal(profile.model, model);
    assert.equal(profile.fallback_model, fallback);
    assert.equal(profile.runner, 'reusable-codex-run');
    assert.equal(profile.capacity_pool, 'codex-standard');
    assert.equal(profile.lifecycle, 'trial');
  }
});

test('resolveExecutionProfile rejects unknown profiles before worker execution', () => {
  assert.throws(
    () => resolveExecutionProfile('does-not-exist', { registryPath: REGISTRY_PATH }),
    /Unknown execution profile: does-not-exist/,
  );
});

test('validateAgentRegistry rejects unknown execution profile model ids', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-registry-models-'));
  const modelRegistryPath = path.join(tmpDir, 'model_registry.json');
  fs.writeFileSync(
    modelRegistryPath,
    JSON.stringify({ models: [{ model_id: 'gpt-known' }] }),
  );

  assert.throws(
    () => {
      validateAgentRegistry(
        {
          agents: {
            codex: {
              capacity: { window: '5h', limit: 1 },
            },
          },
          execution_profiles: {
            'codex-default': {
              agent: 'codex',
              model: 'gpt-typo',
              fallback_model: 'gpt-known',
              runner: 'reusable-codex-run',
              capacity_pool: 'codex-standard',
              safety: 'standard',
              lifecycle: 'active',
            },
          },
        },
        { modelRegistryPath },
      );
    },
    /unknown model: gpt-typo/,
  );
});

test('validateAgentRegistry rejects invalid capacity entries', () => {
  assert.throws(
    () => {
      validateAgentRegistry({
        agents: {
          codex: {
            capacity: { window: 'bogus', limit: 1 },
          },
        },
      });
    },
    /capacity\.window must be one of/,
  );

  assert.throws(
    () => {
      validateAgentRegistry({
        agents: {
          codex: {
            capacity: { window: '5h', limit: 0 },
          },
        },
      });
    },
    /capacity\.limit must be a positive integer/,
  );
});

test('validateAgentRegistry rejects profiles with unknown agents', () => {
  assert.throws(
    () => {
      validateAgentRegistry({
        agents: {
          codex: {
            capacity: { window: '5h', limit: 1 },
          },
        },
        execution_profiles: {
          bogus: {
            agent: 'missing-agent',
            model: 'gpt-5.5',
            runner: 'reusable-codex-run',
            capacity_pool: 'codex-standard',
            safety: 'standard',
            lifecycle: 'active',
          },
        },
      });
    },
    /references unknown agent/,
  );
});
