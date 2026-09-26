'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

// github_api_retry.js was consolidated into github-api-with-retry.js
// (issue #2278); this suite asserts the same behavior against it.
const {
  createGithubFetchRequester,
  computeRetryDelayMs,
  resolveMaxRetries,
  withGithubApiRetry,
} = require('../github-api-with-retry');

function response({ ok, status, body }) {
  return { ok, status, text: async () => body };
}

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

test('withGithubApiRetry logs retry context', async () => {
  let attempts = 0;
  const warnings = [];

  const result = await withGithubApiRetry(
    async () => {
      attempts += 1;
      if (attempts === 1) {
        const error = new Error('Service unavailable');
        error.status = 503;
        throw error;
      }
      return 'ok';
    },
    {
      operation: 'read',
      label: 'fetch data',
      maxRetriesByOperation: { read: 1, unknown: 0 },
      sleep: async () => {},
      backoffFn: () => 1234,
      core: {
        warning: (message) => warnings.push(message),
      },
    }
  );

  assert.equal(result, 'ok');
  assert.equal(attempts, 2);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /Retrying fetch data/);
  assert.match(warnings[0], /operation=read/);
  assert.match(warnings[0], /category=transient/);
  assert.match(warnings[0], /attempt=1\/2/);
  assert.match(warnings[0], /delayMs=1234/);
});

test('fetch requester retries reads but never retries uncertain writes', async () => {
  let readAttempts = 0;
  const read = createGithubFetchRequester({
    token: 'test-token',
    apiUrl: 'https://example.invalid',
    fetchImpl: async () => {
      readAttempts += 1;
      return readAttempts === 1
        ? response({ ok: false, status: 503, body: '{"message":"retry"}' })
        : response({ ok: true, status: 200, body: '{"ok":true}' });
    },
  });
  assert.deepEqual(await read('GET', '/resource'), { ok: true });
  assert.equal(readAttempts, 2);

  let writeAttempts = 0;
  const write = createGithubFetchRequester({
    token: 'test-token',
    apiUrl: 'https://example.invalid',
    fetchImpl: async () => {
      writeAttempts += 1;
      return response({ ok: false, status: 503, body: '{"message":"uncertain"}' });
    },
  });
  await assert.rejects(() => write('PUT', '/resource', { value: 1 }), /503/);
  assert.equal(writeAttempts, 1);
});

test('fetch requester preserves status for non-JSON errors', async () => {
  const request = createGithubFetchRequester({
    token: 'test-token',
    apiUrl: 'https://example.invalid',
    fetchImpl: async () => response({ ok: false, status: 502, body: '<html>bad gateway</html>' }),
  });
  await assert.rejects(
    () => request('POST', '/resource'),
    (error) => error.status === 502 && error.response?.status === 502,
  );
});

test('fetch requester deadline remains active through response body reads', async () => {
  const request = createGithubFetchRequester({
    token: 'test-token',
    apiUrl: 'https://example.invalid',
    timeoutMs: 5,
    fetchImpl: async (_url, options) => ({
      ok: true,
      status: 200,
      text: () => new Promise((_resolve, reject) => {
        options.signal.addEventListener('abort', () => {
          const error = new Error('body read aborted');
          error.name = 'AbortError';
          reject(error);
        }, { once: true });
      }),
    }),
  });
  await assert.rejects(() => request('POST', '/resource'), /body read aborted/);
});
