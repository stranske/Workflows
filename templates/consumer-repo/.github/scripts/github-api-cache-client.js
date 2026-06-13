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
    if (value == null) {
      return value;
    }
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

/**
 * Resolve a single shared GitHub API cache for a given Octokit client.
 *
 * Consolidates the three previously-divergent `getGithubApiCache` factories
 * (in keepalive_gate.js, agents_pr_meta_keepalive.js, keepalive_loop.js), each
 * of which attached its own cache under a distinct per-module sentinel, so
 * three independent caches lived on the same `github` object. This single
 * factory attaches one cache under `__githubApiCache`, so callers share it.
 *
 * @param {Object} options
 * @param {Object} [options.github] - Octokit instance (cache attached to it)
 * @param {Object} [options.core] - GitHub Actions core (for metric logging)
 * @returns {Object} The shared cache wrapper from {@link createGithubApiCache}
 */
function getGithubApiCache({ github, core } = {}) {
  if (!github) {
    return createGithubApiCache({ core });
  }
  if (github.__githubApiCache) {
    return github.__githubApiCache;
  }
  const cache = createGithubApiCache({ core });
  Object.defineProperty(github, '__githubApiCache', {
    value: cache,
    enumerable: false,
    configurable: false,
    writable: false,
  });
  return cache;
}

module.exports = {
  createGithubApiCache,
  getGithubApiCache,
  emitCacheMetrics,
};
