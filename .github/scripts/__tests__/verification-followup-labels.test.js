'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { buildVerificationFollowupLabels } = require('../verification_followup_labels');

const REGISTRY_PATH = path.resolve(__dirname, '..', '..', 'agents', 'registry.yml');
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');

test('follow-up labels carry the PR agent and are never auto-pilot labels', () => {
  const labels = buildVerificationFollowupLabels([{ name: 'agent:cursor' }], {
    registryPath: REGISTRY_PATH,
  });
  assert.deepEqual(labels, ['follow-up', 'agent:cursor', 'from:cursor', 'agents:optimize']);
  assert.ok(!labels.some((l) => l.startsWith('agents:auto-pilot')));
  assert.ok(!labels.includes('from:verification'));
});

test('follow-up labels fall back to the registry default agent', () => {
  const labels = buildVerificationFollowupLabels([], { registryPath: REGISTRY_PATH });
  assert.equal(labels[0], 'follow-up');
  assert.match(labels[1], /^agent:[a-z0-9-]+$/);
  assert.equal(labels[2], `from:${labels[1].slice('agent:'.length)}`);
  assert.equal(labels[3], 'agents:optimize');
});

test('conflicting agent labels warn and fall back instead of throwing', () => {
  const warnings = [];
  const labels = buildVerificationFollowupLabels(
    [{ name: 'agent:codex' }, { name: 'agent:cursor' }],
    { registryPath: REGISTRY_PATH, warn: (m) => warnings.push(m) },
  );
  assert.equal(labels.length, 4);
  assert.equal(warnings.length, 1);
});

test('a missing registry falls back to codex', () => {
  const labels = buildVerificationFollowupLabels([], {
    registryPath: path.join(REPO_ROOT, 'does-not-exist.yml'),
  });
  assert.deepEqual(labels, ['follow-up', 'agent:codex', 'from:codex', 'agents:optimize']);
});

test('hub and v2 both build their follow-up labels through the shared helper', () => {
  const files = [
    'templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml',
    '.github/workflows/agents-verify-to-issue-v2.yml',
  ];
  for (const rel of files) {
    const text = fs.readFileSync(path.join(REPO_ROOT, rel), 'utf8');
    assert.ok(text.includes('verification_followup_labels.js'), `${rel} must require the helper`);
    assert.ok(
      text.includes('.github/scripts/verification_followup_labels.js\n'),
      `${rel} must sparse-checkout the helper`,
    );
    assert.ok(!text.includes("labels: ['agents:auto-pilot'"), `${rel} must not hard-code labels`);
  }
});
