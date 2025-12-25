'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { calculateBackoffDelay } = require('../api-helpers');

function withStubbedRandom(value, fn) {
  const originalRandom = Math.random;
  Math.random = () => value;
  try {
    fn();
  } finally {
    Math.random = originalRandom;
  }
}

test('calculateBackoffDelay applies positive jitter within expected range', () => {
  withStubbedRandom(1, () => {
    const delay = calculateBackoffDelay(1, 1000, 30000);
    assert.equal(delay, 2500);
  });
});

test('calculateBackoffDelay applies negative jitter within expected range', () => {
  withStubbedRandom(0, () => {
    const delay = calculateBackoffDelay(1, 1000, 30000);
    assert.equal(delay, 1500);
  });
});
