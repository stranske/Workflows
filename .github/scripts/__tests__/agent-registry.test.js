'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  getAgentConfig,
  getRunnerWorkflow,
  loadAgentRegistry,
  parseRegistryYaml,
  resolveAgentFromLabels,
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

test('getAgentConfig returns config for codex', () => {
  const config = getAgentConfig('codex', { registryPath: REGISTRY_PATH });
  assert.equal(config.branch_prefix, 'codex/issue-');
  assert.equal(config.ui_mentions_allowed, false);
  assert.ok(config.capabilities);
});

test('getRunnerWorkflow returns configured workflow path', () => {
  const workflow = getRunnerWorkflow('codex', { registryPath: REGISTRY_PATH });
  assert.equal(workflow, '.github/workflows/reusable-codex-run.yml');
});
