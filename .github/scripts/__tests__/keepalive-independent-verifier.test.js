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
      independent_verifier: 'claude',
      capabilities: { pr_keepalive: true },
    },
    muse: {
      runner_workflow: 'm.yml',
      independent_verifier: 'codex',
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
    assert.equal(resolve({ agentType: 'cursor' }).agent, 'claude');
    assert.equal(resolve({ agentType: 'muse' }).agent, 'codex');
    assert.equal(resolve({ agentType: 'codex' }).agent, 'claude');
    assert.equal(resolve({ agentType: 'claude' }).agent, 'codex');
  });

  test(`a declared alternate without credentials is skipped, not chosen (${modulePath})`, () => {
    const result = resolve({
      agentType: 'cursor',
      env: { ...ALL_AUTH, HAS_CLAUDE_AUTH: 'false' },
    });
    assert.equal(result.agent, 'codex');
    assert.equal(result.source, 'first-available');
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
