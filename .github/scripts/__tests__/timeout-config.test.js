'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { parseTimeoutConfig } = require('../timeout_config.js');

test('parseTimeoutConfig falls back to defaults without env or inputs', () => {
  const config = parseTimeoutConfig({ env: {}, inputs: {}, defaultMinutes: 45, extendedMultiplier: 2 });
  assert.equal(config.defaultMinutes, 45);
  assert.equal(config.extendedMinutes, 90);
  assert.equal(config.overrideMinutes, null);
  assert.equal(config.resolvedMinutes, 45);
  assert.equal(config.source, 'default');
});

test('parseTimeoutConfig reads repository defaults from env', () => {
  const env = {
    WORKFLOW_TIMEOUT_DEFAULT: '60',
    WORKFLOW_TIMEOUT_EXTENDED: '180',
  };
  const config = parseTimeoutConfig({ env, inputs: {} });
  assert.equal(config.defaultMinutes, 60);
  assert.equal(config.extendedMinutes, 180);
  assert.equal(config.overrideMinutes, null);
  assert.equal(config.resolvedMinutes, 60);
});

test('parseTimeoutConfig accepts explicit override input', () => {
  const inputs = { timeout_minutes: '120' };
  const config = parseTimeoutConfig({ env: {}, inputs, defaultMinutes: 45 });
  assert.equal(config.overrideMinutes, 120);
  assert.equal(config.resolvedMinutes, 120);
  assert.equal(config.source, 'override');
});

test('parseTimeoutConfig ignores invalid override input', () => {
  const inputs = { timeout_minutes: 'bogus' };
  const config = parseTimeoutConfig({ env: {}, inputs, defaultMinutes: 45 });
  assert.equal(config.overrideMinutes, null);
  assert.equal(config.resolvedMinutes, 45);
});

test('parseTimeoutConfig uses extended label when present', () => {
  const env = {
    WORKFLOW_TIMEOUT_DEFAULT: '30',
    WORKFLOW_TIMEOUT_EXTENDED: '90',
  };
  const config = parseTimeoutConfig({ env, labels: ['timeout:extended'] });
  assert.equal(config.label, 'timeout:extended');
  assert.equal(config.labelMinutes, 90);
  assert.equal(config.resolvedMinutes, 90);
  assert.equal(config.source, 'label');
});

test('parseTimeoutConfig prefers override over label', () => {
  const env = {
    WORKFLOW_TIMEOUT_DEFAULT: '30',
    WORKFLOW_TIMEOUT_EXTENDED: '90',
  };
  const inputs = { timeout_minutes: '120' };
  const config = parseTimeoutConfig({ env, inputs, labels: ['timeout:extended'] });
  assert.equal(config.overrideMinutes, 120);
  assert.equal(config.label, 'timeout:extended');
  assert.equal(config.resolvedMinutes, 120);
  assert.equal(config.source, 'override');
});
