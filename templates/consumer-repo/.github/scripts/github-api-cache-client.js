'use strict';

const {
  buildPrCacheKey,
  createInMemoryCache,
  invalidateOnWebhook,
  resolveCacheTtlMs,
} = require('./github-api-cache');

const DEFAULT_NAMESPACE = 'github-api';
const DEFAULT_BACKEND = 'memory';

function normaliseBackend(value) {
  return String(value ?? '').trim().toLowerCase();
}

function resolveCacheBackend({ backend, env = process.env } = {}) {
  const envValue = env?.GITHUB_API_CACHE_BACKEND;
  const candidate = normaliseBackend(backend) || normaliseBackend(envValue) || DEFAULT_BACKEND;
  if (['memory', 'in-memory', 'inmemory'].includes(candidate)) {
    return { name: 'memory', requested: candidate, unknown: false };
  }
  return { name: 'memory', requested: candidate, unknown: true };
}

function emitCacheMetrics(cache, core, label = 'GitHub API cache') {
  if (!cache || typeof cache.metrics !== 'function') {
    return null;
  }
  const metrics = cache.metrics();
  const message = [
    `${label}:`,
    `hits=${metrics.hits}`,
    `misses=${metrics.misses}`,
    `sets=${metrics.sets}`,
    `expired=${metrics.expired}`,
    `invalidations=${metrics.invalidations}`,
    `size=${metrics.size}`,
    `ttlMs=${metrics.ttlMs}`,
  ].join(' ');
  if (core?.info) {
    core.info(message);
  } else {
    console.log(message);
  }
  return metrics;
}

function createGithubApiCache(options = {}) {
  const {
    cache,
    ttlMs,
    namespace = DEFAULT_NAMESPACE,
    core = null,
    backend,
    env = process.env,
  } = options;
  const resolvedBackend = resolveCacheBackend({ backend, env });
  const defaultTtlMs = resolveCacheTtlMs({ ttlMs, env });
  let store = cache;
  if (!store) {
    if (resolvedBackend.unknown) {
      const warning = `Unknown GitHub API cache backend "${resolvedBackend.requested}". Falling back to in-memory cache.`;
      if (core?.warning) {
        core.warning(warning);
      } else {
        console.warn(warning);
      }
    }
    store = createInMemoryCache({ ttlMs: defaultTtlMs, namespace });
  }

  async function getOrSet({ key, fetcher, ttlMs: ttlOverride } = {}) {
    if (!key) {
      throw new Error('cache key is required');
    }
    if (typeof fetcher !== 'function') {
      throw new Error('cache fetcher must be a function');
    }
    const cached = store.get(key);
    if (cached.hit) {
      return cached.value;
    }
    const value = await fetcher();
    store.set(key, value, { ttlMs: ttlOverride });
    return value;
  }

  function invalidateForWebhook({ eventName, payload, owner, repo } = {}) {
    return invalidateOnWebhook(store, { eventName, payload, owner, repo, core });
  }

  return {
    cache: store,
    defaultTtlMs,
    buildPrCacheKey,
    getOrSet,
    invalidateForWebhook,
    emitMetrics: (label) => emitCacheMetrics(store, core, label),
  };
}

module.exports = {
  createGithubApiCache,
  emitCacheMetrics,
};
