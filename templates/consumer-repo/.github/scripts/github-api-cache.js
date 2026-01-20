'use strict';

const DEFAULT_TTL_MS = 60_000;
const DEFAULT_NAMESPACE = 'github-api-cache';

function toNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.max(0, Math.floor(parsed));
}

function resolveCacheTtlMs({ ttlMs, env = process.env, defaultTtlMs = DEFAULT_TTL_MS } = {}) {
  const direct = toNumber(ttlMs);
  if (direct !== null) {
    return direct;
  }
  const envMs = toNumber(env.GITHUB_API_CACHE_TTL_MS);
  if (envMs !== null) {
    return envMs;
  }
  const envSeconds = toNumber(env.GITHUB_API_CACHE_TTL_SECONDS);
  if (envSeconds !== null) {
    return envSeconds * 1000;
  }
  return defaultTtlMs;
}

function buildCacheKey(parts) {
  if (Array.isArray(parts)) {
    return parts.map((part) => String(part ?? '')).join(':');
  }
  return String(parts ?? '');
}

function buildPrCacheKey({ owner, repo, number, resource, suffix } = {}) {
  const base = `pr:${owner}/${repo}#${number}`;
  const parts = [base];
  if (resource) {
    parts.push(resource);
  }
  if (suffix) {
    parts.push(suffix);
  }
  return buildCacheKey(parts);
}

function createInMemoryCache(options = {}) {
  const {
    ttlMs: ttlOverride,
    now = Date.now,
    namespace = DEFAULT_NAMESPACE,
  } = options;
  const defaultTtlMs = resolveCacheTtlMs({ ttlMs: ttlOverride });
  const store = new Map();
  const metrics = {
    hits: 0,
    misses: 0,
    sets: 0,
    invalidations: 0,
    expired: 0,
  };

  const fullKey = (key) => `${namespace}:${buildCacheKey(key)}`;

  const readEntry = (key, { track = true } = {}) => {
    const entry = store.get(fullKey(key));
    if (!entry) {
      if (track) {
        metrics.misses += 1;
      }
      return { hit: false, value: undefined };
    }
    if (entry.expiresAt !== null && now() >= entry.expiresAt) {
      store.delete(fullKey(key));
      if (track) {
        metrics.misses += 1;
        metrics.expired += 1;
      }
      return { hit: false, value: undefined };
    }
    if (track) {
      metrics.hits += 1;
    }
    return { hit: true, value: entry.value };
  };

  const resolveTtl = (override) => {
    const candidate = toNumber(override);
    if (candidate !== null) {
      return candidate;
    }
    return defaultTtlMs;
  };

  return {
    get(key) {
      return readEntry(key, { track: true });
    },
    peek(key) {
      return readEntry(key, { track: false });
    },
    has(key) {
      return readEntry(key, { track: false }).hit;
    },
    set(key, value, { ttlMs } = {}) {
      const ttl = resolveTtl(ttlMs);
      if (ttl <= 0) {
        store.delete(fullKey(key));
        return;
      }
      const expiresAt = ttl ? now() + ttl : null;
      store.set(fullKey(key), { value, expiresAt });
      metrics.sets += 1;
    },
    async getOrSet(key, fetcher, { ttlMs } = {}) {
      const cached = readEntry(key, { track: true });
      if (cached.hit) {
        return cached.value;
      }
      const value = await fetcher();
      this.set(key, value, { ttlMs });
      return value;
    },
    invalidate(key) {
      const removed = store.delete(fullKey(key));
      if (removed) {
        metrics.invalidations += 1;
      }
      return removed;
    },
    invalidatePrefix(prefix) {
      const fullPrefix = `${namespace}:${buildCacheKey(prefix)}`;
      let removed = 0;
      for (const key of store.keys()) {
        if (key.startsWith(fullPrefix)) {
          store.delete(key);
          removed += 1;
        }
      }
      if (removed) {
        metrics.invalidations += removed;
      }
      return removed;
    },
    clear() {
      store.clear();
    },
    metrics() {
      return { ...metrics, size: store.size, ttlMs: defaultTtlMs, namespace };
    },
  };
}

function extractPrNumbersFromEvent({ eventName, payload } = {}) {
  if (!payload) {
    return [];
  }
  const numbers = new Set();

  const directPr = payload.pull_request;
  if (directPr?.number) {
    numbers.add(Number(directPr.number));
  }

  const issue = payload.issue;
  if (issue?.number && issue.pull_request) {
    numbers.add(Number(issue.number));
  }

  const workflowRun = payload.workflow_run;
  if (Array.isArray(workflowRun?.pull_requests)) {
    for (const pr of workflowRun.pull_requests) {
      if (pr?.number) {
        numbers.add(Number(pr.number));
      }
    }
  }

  const checkSuite = payload.check_suite;
  if (Array.isArray(checkSuite?.pull_requests)) {
    for (const pr of checkSuite.pull_requests) {
      if (pr?.number) {
        numbers.add(Number(pr.number));
      }
    }
  }

  if (Array.isArray(payload.pull_requests)) {
    for (const pr of payload.pull_requests) {
      if (pr?.number) {
        numbers.add(Number(pr.number));
      }
    }
  }

  return Array.from(numbers).filter((value) => Number.isFinite(value) && value > 0);
}

function invalidateOnWebhook(cache, { eventName, payload, owner, repo, core } = {}) {
  if (!cache || typeof cache.invalidatePrefix !== 'function') {
    return { invalidated: 0, prNumbers: [] };
  }
  const prNumbers = extractPrNumbersFromEvent({ eventName, payload });
  if (!prNumbers.length || !owner || !repo) {
    return { invalidated: 0, prNumbers };
  }

  let invalidated = 0;
  for (const number of prNumbers) {
    const prefix = buildPrCacheKey({ owner, repo, number });
    invalidated += cache.invalidatePrefix(`${prefix}:`);
  }

  if (invalidated && core?.info) {
    core.info(`Invalidated ${invalidated} cache entr${invalidated === 1 ? 'y' : 'ies'} for PR(s): ${prNumbers.join(', ')}`);
  }

  return { invalidated, prNumbers };
}

module.exports = {
  DEFAULT_TTL_MS,
  buildCacheKey,
  buildPrCacheKey,
  resolveCacheTtlMs,
  createInMemoryCache,
  extractPrNumbersFromEvent,
  invalidateOnWebhook,
};
