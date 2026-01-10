'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { calculateElapsedTime } = require('../.github/scripts/keepalive_state.js');

test('calculateElapsedTime returns 0s for null input', () => {
  assert.equal(calculateElapsedTime(null), '0s');
});

test('calculateElapsedTime returns 0s for invalid date strings', () => {
  assert.equal(calculateElapsedTime('invalid'), '0s');
});

test('calculateElapsedTime formats minutes and seconds', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = new Date(now - (5 * 60 * 1000 + 23 * 1000)).toISOString();
    assert.equal(calculateElapsedTime(start), '5m 23s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime handles edge cases', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const futureStart = new Date(now + 60 * 1000).toISOString();
    assert.equal(calculateElapsedTime(futureStart), '0s');
    const start = new Date(now - (2 * 3600 * 1000 + 3 * 60 * 1000 + 4 * 1000)).toISOString();
    assert.equal(calculateElapsedTime(start), '2h 3m 4s');
  } finally {
    Date.now = realNow;
  }
});
