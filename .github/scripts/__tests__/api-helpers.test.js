'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { calculateBackoffDelay, withBackoff, paginateWithBackoff } = require('../api-helpers');

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

test('withBackoff retries transient errors (not just rate limits)', async () => {
  let attempts = 0;
  const result = await withBackoff(
    async () => {
      attempts += 1;
      if (attempts < 3) {
        const error = new Error('Service temporarily unavailable');
        error.status = 503;
        throw error;
      }
      return { data: 'success' };
    },
    { maxRetries: 3 }
  );
  
  assert.equal(attempts, 3);
  assert.deepEqual(result, { data: 'success' });
});

test('paginateWithBackoff retries transient errors', async () => {
  let attempts = 0;
  const mockGithub = {
    paginate: async (method, params) => {
      attempts += 1;
      if (attempts < 2) {
        const error = new Error('Network timeout');
        error.status = 504;
        throw error;
      }
      return [{ id: 1 }, { id: 2 }];
    },
  };
  
  const mockMethod = 'mockMethod';
  const result = await paginateWithBackoff(
    mockGithub,
    mockMethod,
    { page: 1 },
    { maxRetries: 3 }
  );
  
  assert.equal(attempts, 2);
  assert.deepEqual(result, [{ id: 1 }, { id: 2 }]);
});
