'use strict';

const { classifyError, ERROR_CATEGORIES } = require('./error_classifier');
const { calculateBackoffDelay } = require('./api-helpers');

const DEFAULT_RETRY_LIMITS = Object.freeze({
  read: 3,
  write: 2,
  dispatch: 2,
  admin: 1,
  unknown: 1,
});

const DEFAULT_BASE_DELAY_MS = 1000;
const DEFAULT_MAX_DELAY_MS = 30000;

function normaliseHeaders(headers) {
  if (!headers || typeof headers !== 'object') {
    return {};
  }
  return Object.entries(headers).reduce((acc, [key, value]) => {
    acc[String(key).toLowerCase()] = value;
    return acc;
  }, {});
}

function resolveMaxRetries(operation, maxRetriesByOperation) {
  if (!maxRetriesByOperation || typeof maxRetriesByOperation !== 'object') {
    return DEFAULT_RETRY_LIMITS.unknown;
  }
  if (operation && maxRetriesByOperation[operation] != null) {
    return maxRetriesByOperation[operation];
  }
  return maxRetriesByOperation.unknown ?? DEFAULT_RETRY_LIMITS.unknown;
}

function calculateWaitUntilReset(resetTimestamp, nowMs) {
  if (!Number.isFinite(resetTimestamp)) {
    return DEFAULT_BASE_DELAY_MS;
  }
  const now = Number.isFinite(nowMs) ? nowMs : Date.now();
  const resetTime = resetTimestamp * 1000;
  const waitTime = resetTime - now;
  return Math.max(1000, Math.min(waitTime + 1000, 60000));
}

function computeRetryDelayMs({
  error,
  attempt,
  baseDelay,
  maxDelay,
  backoffFn,
  nowMs,
}) {
  const headers = normaliseHeaders(error?.response?.headers || error?.headers);
  const retryAfter = parseInt(headers['retry-after'], 10);
  if (Number.isFinite(retryAfter) && retryAfter >= 0) {
    return Math.min(retryAfter * 1000, maxDelay);
  }

  const remaining = parseInt(headers['x-ratelimit-remaining'], 10);
  const reset = parseInt(headers['x-ratelimit-reset'], 10);
  if (Number.isFinite(remaining) && remaining <= 0 && Number.isFinite(reset)) {
    return Math.min(calculateWaitUntilReset(reset, nowMs), maxDelay);
  }

  return Math.min(backoffFn(attempt, baseDelay, maxDelay), maxDelay);
}

function logRetry({ core, label, operation, attempt, maxRetries, delayMs, category, message }) {
  const summary = [
    `Retrying ${label}`,
    `operation=${operation}`,
    `category=${category}`,
    `attempt=${attempt + 1}/${maxRetries + 1}`,
    `delayMs=${delayMs}`,
  ]
    .filter(Boolean)
    .join(' ');

  const detail = message ? `; error=${message}` : '';
  const full = `${summary}${detail}`;

  if (core && typeof core.warning === 'function') {
    core.warning(full);
  } else {
    console.warn(`[WARN] ${full}`);
  }
}

async function withGithubApiRetry(apiCall, options = {}) {
  const {
    operation = 'unknown',
    label = 'GitHub API call',
    maxRetriesByOperation = DEFAULT_RETRY_LIMITS,
    baseDelay = DEFAULT_BASE_DELAY_MS,
    maxDelay = DEFAULT_MAX_DELAY_MS,
    core = null,
    sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    backoffFn = calculateBackoffDelay,
  } = options;

  const maxRetries = resolveMaxRetries(operation, maxRetriesByOperation);
  let lastError = null;

  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    try {
      return await apiCall();
    } catch (error) {
      lastError = error;
      const { category, message } = classifyError(error);

      if (category !== ERROR_CATEGORIES.transient || attempt >= maxRetries) {
        throw error;
      }

      const delayMs = computeRetryDelayMs({
        error,
        attempt,
        baseDelay,
        maxDelay,
        backoffFn,
      });

      logRetry({ core, label, operation, attempt, maxRetries, delayMs, category, message });
      await sleep(delayMs);
    }
  }

  throw lastError || new Error('GitHub API call failed after retries');
}

module.exports = {
  DEFAULT_RETRY_LIMITS,
  resolveMaxRetries,
  computeRetryDelayMs,
  withGithubApiRetry,
};
