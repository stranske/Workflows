'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const WORKFLOW = [
  'jobs:',
  '  run-codex:',
  '  run-claude:',
  '  run-cursor:',
  '  run-muse:',
  '',
].join('\n');

const REGISTRY = {
  agents: {
    codex: { runner_workflow: 'c.yml', capabilities: { pr_keepalive: true } },
    claude: { runner_workflow: 'cl.yml', capabilities: { pr_keepalive: true } },
    cursor: {
      runner_workflow: 'cu.yml',
      independent_verifier: ['claude', 'codex'],
      capabilities: { pr_keepalive: true },
    },
    muse: {
      runner_workflow: 'm.yml',
      independent_verifier: ['claude', 'codex'],
      capabilities: { pr_keepalive: true },
    },
    gemini: { runner_workflow: 'g.yml', capabilities: { pr_keepalive: true } },
    aider: { runner_workflow: '', capabilities: { pr_keepalive: false } },
  },
};

const ALL_AUTH = {
  HAS_CODEX_AUTH: 'true',
  HAS_CLAUDE_AUTH: 'true',
  HAS_CURSOR_AUTH: 'true',
  HAS_MUSE_AUTH: 'true',
};

for (const modulePath of [
  '../keepalive_loop',
  '../../../templates/consumer-repo/.github/scripts/keepalive_loop',
]) {
  const { resolveIndependentVerifier } = require(modulePath);
  const resolve = (overrides) =>
    resolveIndependentVerifier({
      registry: REGISTRY,
      env: ALL_AUTH,
      workflowText: WORKFLOW,
      ...overrides,
    });

  test(`the verification step never runs on the implementing agent (${modulePath})`, () => {
    for (const agentType of ['codex', 'claude', 'cursor', 'muse']) {
      const result = resolve({ agentType });
      assert.notEqual(result.agent, agentType, `${agentType} verified itself`);
    }
    assert.equal(resolve({ agentType: 'codex' }).agent, 'claude');
    assert.equal(resolve({ agentType: 'claude' }).agent, 'codex');
  });

  test(`a less proven agent is verified by either proven agent at random (${modulePath})`, () => {
    for (const agentType of ['cursor', 'muse']) {
      assert.equal(resolve({ agentType, random: () => 0 }).agent, 'claude');
      assert.equal(resolve({ agentType, random: () => 0.99 }).agent, 'codex');
      assert.equal(resolve({ agentType, random: () => 0.5 }).source, 'registry-random');
    }
    const seen = new Set();
    for (let i = 0; i < 200; i += 1) seen.add(resolve({ agentType: 'muse' }).agent);
    assert.deepEqual([...seen].sort(), ['claude', 'codex']);
  });

  test(`random choice never lands on an agent without credentials (${modulePath})`, () => {
    for (const r of [0, 0.5, 0.99]) {
      const result = resolve({
        agentType: 'cursor',
        random: () => r,
        env: { ...ALL_AUTH, HAS_CLAUDE_AUTH: 'false' },
      });
      assert.equal(result.agent, 'codex');
    }
  });

  test(`a declared alternate without credentials is skipped, not chosen (${modulePath})`, () => {
    const result = resolve({
      agentType: 'cursor',
      env: { ...ALL_AUTH, HAS_CLAUDE_AUTH: 'false' },
    });
    assert.equal(result.agent, 'codex');
    assert.equal(result.source, 'registry');
  });

  test(`Claude OAuth alone counts as Claude credentials (${modulePath})`, () => {
    const result = resolve({
      agentType: 'muse',
      env: { HAS_MUSE_AUTH: 'true', HAS_CLAUDE_OAUTH: 'true' },
      registry: {
        agents: { ...REGISTRY.agents, muse: { ...REGISTRY.agents.muse, independent_verifier: '' } },
      },
    });
    assert.equal(result.agent, 'claude');
  });

  test(`an agent with a declared runner but no job in this workflow is not chosen (${modulePath})`, () => {
    const result = resolve({
      agentType: 'cursor',
      workflowText: '  run-codex:\n  run-cursor:\n',
      env: ALL_AUTH,
    });
    assert.equal(result.agent, 'codex');
  });

  test(`with no other usable agent the implementing agent is kept and flagged (${modulePath})`, () => {
    const result = resolve({ agentType: 'muse', env: { HAS_MUSE_AUTH: 'true' } });
    assert.equal(result.agent, 'muse');
    assert.equal(result.source, 'none-available');
  });

  test(`a repository verifier_agent overrides everything (${modulePath})`, () => {
    const result = resolve({ agentType: 'cursor', configuredVerifier: 'Muse' });
    assert.equal(result.agent, 'muse');
    assert.equal(result.source, 'config');
  });
}
