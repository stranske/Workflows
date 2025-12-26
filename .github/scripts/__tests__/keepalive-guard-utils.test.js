'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  SKIP_MARKER,
  analyseSkipComments,
  isGateReason,
} = require('../keepalive_guard_utils');

test('isGateReason matches the explicit gate-not-green reason', () => {
  assert.equal(isGateReason('gate-not-green'), true);
});

test('isGateReason treats any gate-prefixed reason as gate-related', () => {
  assert.equal(isGateReason('gate-timeout'), true);
});

test('isGateReason returns false for non-gate reasons and empty input', () => {
  assert.equal(isGateReason('permanent-failure'), false);
  assert.equal(isGateReason(''), false);
});

test('isGateReason normalizes whitespace and casing', () => {
  assert.equal(isGateReason(' Gate-Not-Green '), true);
  assert.equal(isGateReason('GATE-DELAYED'), true);
});

test('analyseSkipComments returns zeroed state when no comments exist', () => {
  const result = analyseSkipComments([]);
  assert.deepEqual(result, {
    total: 0,
    highestCount: 0,
    gateCount: 0,
    nonGateCount: 0,
    reasons: [],
    nonGateReasons: [],
  });
});

test('analyseSkipComments counts marker-only entries and defaults highest count', () => {
  const result = analyseSkipComments([
    { body: `${SKIP_MARKER}\nKeepalive skipped.` },
  ]);

  assert.equal(result.total, 1);
  assert.equal(result.highestCount, 1);
  assert.equal(result.gateCount, 0);
  assert.equal(result.nonGateCount, 0);
  assert.deepEqual(result.reasons, []);
});

test('analyseSkipComments tracks gate skips with explicit count', () => {
  const result = analyseSkipComments([
    {
      body: `${SKIP_MARKER}\n<!-- keepalive-skip-count: 3 -->\nKeepalive 42 check skipped: gate-not-green`,
    },
  ]);

  assert.equal(result.total, 1);
  assert.equal(result.highestCount, 3);
  assert.equal(result.gateCount, 1);
  assert.equal(result.nonGateCount, 0);
  assert.deepEqual(result.reasons, ['gate-not-green']);
});

test('analyseSkipComments uses the highest explicit skip count across comments', () => {
  const result = analyseSkipComments([
    {
      body: `${SKIP_MARKER}\n<!-- keepalive-skip-count: 2 -->\nKeepalive 10 job skipped: gate-not-green`,
    },
    {
      body: `${SKIP_MARKER}\n<!-- keepalive-skip-count: 5 -->\nKeepalive 11 job skipped: dependency-missing`,
    },
  ]);

  assert.equal(result.total, 2);
  assert.equal(result.highestCount, 5);
  assert.equal(result.gateCount, 1);
  assert.equal(result.nonGateCount, 1);
  assert.deepEqual(result.reasons, ['gate-not-green', 'dependency-missing']);
});

test('analyseSkipComments defaults highestCount to total and tracks non-gate reasons', () => {
  const result = analyseSkipComments([
    {
      body: `${SKIP_MARKER}\nKeepalive 12 job skipped: dependency-missing`,
    },
    {
      body: `${SKIP_MARKER}\nKeepalive 13 job skipped: gate-not-green`,
    },
  ]);

  assert.equal(result.total, 2);
  assert.equal(result.highestCount, 2);
  assert.equal(result.gateCount, 1);
  assert.equal(result.nonGateCount, 1);
  assert.deepEqual(result.nonGateReasons, ['dependency-missing']);
});

test('analyseSkipComments ignores unrelated comments and tolerates malformed counts', () => {
  const result = analyseSkipComments([
    { body: 'Looks good to me.' },
    { body: `${SKIP_MARKER}\n<!-- keepalive-skip-count: nope -->` },
    { body: 'Keepalive 9 check skipped: gate-not-green' },
  ]);

  assert.equal(result.total, 2);
  assert.equal(result.highestCount, 2);
  assert.equal(result.gateCount, 1);
  assert.equal(result.nonGateCount, 0);
  assert.deepEqual(result.reasons, ['gate-not-green']);
});

test('analyseSkipComments handles string entries with marker and reason', () => {
  const result = analyseSkipComments([
    `${SKIP_MARKER}\nKeepalive 14 job skipped: flaky-check`,
  ]);

  assert.equal(result.total, 1);
  assert.equal(result.highestCount, 1);
  assert.equal(result.gateCount, 0);
  assert.equal(result.nonGateCount, 1);
  assert.deepEqual(result.reasons, ['flaky-check']);
});
