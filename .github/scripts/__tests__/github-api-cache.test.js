'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert');

const {
  buildPrCacheKey,
  createInMemoryCache,
  invalidateOnWebhook,
} = require('../github-api-cache');

describe('github-api-cache', () => {
  it('tracks hits and misses for cached entries', () => {
    let now = 1_000;
    const cache = createInMemoryCache({ ttlMs: 5_000, now: () => now, namespace: 'test' });

    const miss = cache.get('alpha');
    assert.strictEqual(miss.hit, false);

    cache.set('alpha', { ok: true });
    const hit = cache.get('alpha');
    assert.strictEqual(hit.hit, true);
    assert.deepStrictEqual(hit.value, { ok: true });

    const metrics = cache.metrics();
    assert.strictEqual(metrics.hits, 1);
    assert.strictEqual(metrics.misses, 1);
  });

  it('expires cached entries after TTL', () => {
    let now = 0;
    const cache = createInMemoryCache({ ttlMs: 1_000, now: () => now, namespace: 'test' });

    cache.set('expiring', 'value');
    now = 2_000;

    const expired = cache.get('expiring');
    assert.strictEqual(expired.hit, false);

    const metrics = cache.metrics();
    assert.strictEqual(metrics.expired, 1);
  });

  it('invalidates PR cache entries on webhook events', () => {
    let now = 10;
    const cache = createInMemoryCache({ ttlMs: 5_000, now: () => now, namespace: 'test' });
    const owner = 'octo';
    const repo = 'repo';

    const prKey = buildPrCacheKey({ owner, repo, number: 42, resource: 'pulls.get' });
    const filesKey = buildPrCacheKey({ owner, repo, number: 42, resource: 'pulls.listFiles' });
    const otherKey = buildPrCacheKey({ owner, repo, number: 43, resource: 'pulls.get' });

    cache.set(prKey, { number: 42 });
    cache.set(filesKey, { files: [] });
    cache.set(otherKey, { number: 43 });

    const result = invalidateOnWebhook(cache, {
      eventName: 'pull_request',
      payload: { pull_request: { number: 42 } },
      owner,
      repo,
    });

    assert.strictEqual(result.invalidated, 2);
    assert.strictEqual(cache.has(prKey), false);
    assert.strictEqual(cache.has(filesKey), false);
    assert.strictEqual(cache.has(otherKey), true);
  });
});
