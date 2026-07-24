'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  TRIED_PREFIX,
  decideStallRotation,
  eligibleAgents,
  currentAgentFromLabels,
  triedAgentsFromLabels,
} = require('../agent_stall_rotation');

// Registry mirroring the shape of .github/agents/registry.yml: codex/claude are
// belt+keepalive; cursor/gemini keepalive-only; aider disabled.
const REGISTRY = {
  default_agent: 'codex',
  agents: {
    codex: {
      required_secrets: ['CODEX_AUTH_JSON'],
      capabilities: { belt: true, pr_keepalive: true },
    },
    claude: {
      required_secrets: ['CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDE_AUTH_JSON'],
      required_secrets_mode: 'any',
      capabilities: { belt: true, pr_keepalive: true },
    },
    cursor: { required_secrets: ['CURSOR_API_KEY'], capabilities: { pr_keepalive: true, belt: false } },
    gemini: { enabled: true, required_secrets: ['GEMINI_API_KEY'], capabilities: { pr_keepalive: true } },
    aider: { enabled: false, required_secrets: ['OPENAI_API_KEY'], capabilities: {} },
  },
};

const label = (name) => ({ name });

test('eligibleAgents is capability-gated and skips disabled agents', () => {
  assert.deepEqual(eligibleAgents({ registry: REGISTRY, capability: 'belt' }), ['codex', 'claude']);
  assert.deepEqual(eligibleAgents({ registry: REGISTRY, capability: 'pr_keepalive' }), [
    'codex',
    'claude',
    'cursor',
    'gemini',
  ]);
});

test('eligibleAgents honors required secrets (all vs any)', () => {
  const secrets = { CODEX_AUTH_JSON: '1', CLAUDE_AUTH_JSON: '1', GEMINI_API_KEY: '1' };
  // cursor excluded (no CURSOR_API_KEY); claude included via "any" mode.
  assert.deepEqual(
    eligibleAgents({ registry: REGISTRY, capability: 'pr_keepalive', secrets }),
    ['codex', 'claude', 'gemini']
  );
});

test('belt stall rotates codex -> claude, then exhausts to needs-human', () => {
  const first = decideStallRotation({
    registry: REGISTRY,
    capability: 'belt',
    labels: [label('agent:codex'), label('agents:auto-pilot')],
  });
  assert.equal(first.rotate, true);
  assert.equal(first.nextAgent, 'claude');
  assert.equal(first.triedMarker, `${TRIED_PREFIX}codex`);

  // After codex is marked tried and we are now on claude, claude stalls too -> exhausted.
  const second = decideStallRotation({
    registry: REGISTRY,
    capability: 'belt',
    labels: [label('agent:claude'), label(`${TRIED_PREFIX}codex`)],
  });
  assert.equal(second.rotate, false);
  assert.equal(second.reason, 'all-eligible-agents-tried');
});

test('monitor-pr stall rotates across the fuller keepalive set (codex->claude->cursor->gemini)', () => {
  let labels = [label('agent:codex')];
  const order = [];
  for (let i = 0; i < 5; i += 1) {
    const decision = decideStallRotation({ registry: REGISTRY, capability: 'pr_keepalive', labels });
    if (!decision.rotate) {
      order.push('STOP');
      break;
    }
    order.push(decision.nextAgent);
    // simulate the workflow applying the labels for the next round
    labels = [label(`agent:${decision.nextAgent}`), label(decision.triedMarker), ...labels.filter((l) => l.name.startsWith(TRIED_PREFIX))];
  }
  assert.deepEqual(order, ['claude', 'cursor', 'gemini', 'STOP']);
});

test('deliberate-break guard: an already-all-tried issue never rotates (escalates)', () => {
  const decision = decideStallRotation({
    registry: REGISTRY,
    capability: 'belt',
    labels: [label('agent:claude'), label(`${TRIED_PREFIX}codex`), label(`${TRIED_PREFIX}claude`)],
  });
  assert.equal(decision.rotate, false);
});

test('no eligible agents (missing secrets) escalates rather than looping', () => {
  const decision = decideStallRotation({
    registry: REGISTRY,
    capability: 'belt',
    labels: [label('agent:codex')],
    secrets: {}, // nothing present
  });
  assert.equal(decision.rotate, false);
  assert.equal(decision.reason, 'no-eligible-agents');
});

test('label helpers parse current + tried agents', () => {
  const labels = [label('agent:cursor'), label(`${TRIED_PREFIX}codex`), label('agents:auto-pilot')];
  assert.equal(currentAgentFromLabels(labels, ['codex', 'claude', 'cursor', 'gemini']), 'cursor');
  assert.deepEqual([...triedAgentsFromLabels(labels)], ['codex']);
});

test('falls back to registry default_agent as the current agent when unlabeled', () => {
  const decision = decideStallRotation({
    registry: REGISTRY,
    capability: 'belt',
    labels: [label('agents:auto-pilot')],
  });
  // default is codex -> tried; next belt agent is claude.
  assert.equal(decision.currentAgent, 'codex');
  assert.equal(decision.nextAgent, 'claude');
});
