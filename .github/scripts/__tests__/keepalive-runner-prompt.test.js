'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  resolveKeepalivePromptContext,
  resolvePromptCheckboxCounts,
} = require(path.join(__dirname, '../../../scripts/keepalive-runner.js'));

test('resolveKeepalivePromptContext prioritizes ci-failure labels', () => {
  const result = resolveKeepalivePromptContext({
    labels: ['ci-failure'],
    checkboxCounts: { total: 2, unchecked: 0 },
    options: {},
  });

  assert.equal(result.action, 'fix');
  assert.equal(result.reason, 'ci-failure');
  assert.equal(result.scenario, 'ci-failure');
});

test('resolveKeepalivePromptContext treats ci failure label variants as failures', () => {
  const result = resolveKeepalivePromptContext({
    labels: ['ci_failed'],
    checkboxCounts: { total: 2, unchecked: 1 },
    options: {},
  });

  assert.equal(result.action, 'fix');
  assert.equal(result.reason, 'ci-failure');
  assert.equal(result.scenario, 'ci-failure');
});

test('resolveKeepalivePromptContext respects explicit scenario overrides', () => {
  const result = resolveKeepalivePromptContext({
    labels: ['ci-failure'],
    checkboxCounts: { total: 2, unchecked: 0 },
    options: { keepalive_prompt_scenario: 'manual-override' },
  });

  assert.equal(result.action, 'fix');
  assert.equal(result.reason, 'ci-failure');
  assert.equal(result.scenario, 'manual-override');
});

test('resolveKeepalivePromptContext routes to verification when tasks are complete', () => {
  const result = resolveKeepalivePromptContext({
    labels: ['agents:keepalive'],
    checkboxCounts: { total: 2, unchecked: 0 },
    options: {},
  });

  assert.equal(result.action, 'verify');
  assert.equal(result.reason, 'verify-acceptance');
  assert.equal(result.scenario, 'verification');
});

test('resolveKeepalivePromptContext keeps default behavior when tasks remain', () => {
  const result = resolveKeepalivePromptContext({
    labels: ['agents:keepalive'],
    checkboxCounts: { total: 3, unchecked: 1 },
    options: {},
  });

  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'ready');
});

test('resolvePromptCheckboxCounts prefers latest checklist when it has outstanding work', () => {
  const scopeCounts = { total: 2, unchecked: 0 };
  const latestChecklist = { total: 3, unchecked: 1 };
  const counts = resolvePromptCheckboxCounts(scopeCounts, latestChecklist);
  const result = resolveKeepalivePromptContext({
    labels: ['agents:keepalive'],
    checkboxCounts: counts,
    options: {},
  });

  assert.deepEqual(counts, { total: 3, unchecked: 1 });
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'ready');
});

test('resolvePromptCheckboxCounts falls back to scope counts without a checklist', () => {
  const scopeCounts = { total: 2, unchecked: 0 };
  const counts = resolvePromptCheckboxCounts(scopeCounts);
  const result = resolveKeepalivePromptContext({
    labels: ['agents:keepalive'],
    checkboxCounts: counts,
    options: {},
  });

  assert.deepEqual(counts, scopeCounts);
  assert.equal(result.action, 'verify');
  assert.equal(result.reason, 'verify-acceptance');
});
