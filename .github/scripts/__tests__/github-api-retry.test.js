'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  computeRetryDelayMs,
  resolveMaxRetries,
  withGithubApiRetry,
} = require('../github_api_retry');

test('resolveMaxRetries uses operation-specific overrides', () => {
  const limits = { read: 4, unknown: 1 };
  assert.equal(resolveMaxRetries('read', limits), 4);
  assert.equal(resolveMaxRetries('write', limits), 1);
});

test('computeRetryDelayMs respects Retry-After header', () => {
  const delay = computeRetryDelayMs({
    error: { response: { headers: { 'Retry-After': '12' } } },
    attempt: 0,
    baseDelay: 1000,
    maxDelay: 30000,
    backoffFn: () => 5000,
  });
  assert.equal(delay, 12000);
});

test('computeRetryDelayMs uses rate limit reset when remaining is 0', () => {
  const nowMs = 1_700_000_000_000;
  const resetSeconds = Math.floor(nowMs / 1000) + 10;
  const delay = computeRetryDelayMs({
    error: { response: { headers: { 'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': String(resetSeconds) } } },
    attempt: 0,
    baseDelay: 1000,
    maxDelay: 30000,
    backoffFn: () => 5000,
    nowMs,
  });
  assert.equal(delay, 11000);
});

test('withGithubApiRetry retries transient errors then succeeds', async () => {
  let attempts = 0;
  const delays = [];
  const result = await withGithubApiRetry(
    async () => {
      attempts += 1;
      if (attempts < 3) {
        const error = new Error('Service unavailable');
        error.status = 503;
        throw error;
      }
      return 'ok';
    },
    {
      operation: 'read',
      maxRetriesByOperation: { read: 3, unknown: 0 },
      sleep: async (ms) => {
        delays.push(ms);
      },
      backoffFn: () => 1234,
    }
  );

  assert.equal(result, 'ok');
  assert.equal(attempts, 3);
  assert.deepEqual(delays, [1234, 1234]);
});

test('withGithubApiRetry does not retry non-transient errors', async () => {
  let attempts = 0;
  await assert.rejects(
    () =>
      withGithubApiRetry(
        async () => {
          attempts += 1;
          const error = new Error('Bad credentials');
          error.status = 401;
          throw error;
        },
        {
          operation: 'read',
          maxRetriesByOperation: { read: 3, unknown: 0 },
          sleep: async () => {},
          backoffFn: () => 1234,
        }
      ),
    /Bad credentials/
  );
  assert.equal(attempts, 1);
});
