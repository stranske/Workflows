'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert');

const { createGithubApiCache } = require('../github-api-cache-client');
const { buildPrCacheKey, createInMemoryCache } = require('../github-api-cache');

describe('github-api-cache-client', () => {
  it('reuses cached values within TTL', async () => {
    let now = 0;
    const cache = createInMemoryCache({ ttlMs: 1000, now: () => now, namespace: 'test' });
    const apiCache = createGithubApiCache({ cache });
    let calls = 0;

    const key = buildPrCacheKey({
      owner: 'octo',
      repo: 'repo',
      number: 42,
      resource: 'pulls.get',
    });

    const fetcher = async () => {
      calls += 1;
      return { ok: true };
    };

    const first = await apiCache.getOrSet({ key, fetcher });
    const second = await apiCache.getOrSet({ key, fetcher });

    assert.deepStrictEqual(first, { ok: true });
    assert.deepStrictEqual(second, { ok: true });
    assert.strictEqual(calls, 1);
  });

  it('invalidates cached entries by webhook context', () => {
    const cache = createInMemoryCache({ ttlMs: 5000, namespace: 'test' });
    const apiCache = createGithubApiCache({ cache });
    const key = buildPrCacheKey({
      owner: 'octo',
      repo: 'repo',
      number: 7,
      resource: 'pulls.get',
    });

    cache.set(key, { number: 7 });
    const result = apiCache.invalidateForWebhook({
      eventName: 'pull_request',
      payload: { pull_request: { number: 7 } },
      owner: 'octo',
      repo: 'repo',
    });

    assert.strictEqual(result.invalidated, 1);
    assert.strictEqual(cache.has(key), false);
  });

  it('returns cache metrics when emitting', () => {
    const cache = createInMemoryCache({ ttlMs: 1000, namespace: 'test' });
    const apiCache = createGithubApiCache({
      cache,
      core: { info: () => {} },
    });

    cache.set('alpha', 'value');
    cache.get('alpha');
    const metrics = apiCache.emitMetrics('test-cache');

    assert.ok(metrics);
    assert.strictEqual(metrics.hits, 1);
    assert.strictEqual(metrics.sets, 1);
  });
});
