'use strict';

/**
 * API Helper utilities for GitHub Actions workflows
 *
 * Provides rate limit awareness and exponential backoff for API calls.
 * This module addresses Issue R-1 from WorkflowSystemBugReport.md
 */

const { withGithubApiRetry, calculateBackoffDelay } = require('./github_api_retry');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_BASE_DELAY_MS = 1000;
const DEFAULT_MAX_DELAY_MS = 30000;
const RATE_LIMIT_THRESHOLD = 500;

/**
 * Check if an error is a rate limit error (HTTP 403 with rate limit message)
 * @param {Error} error - The error to check
 * @returns {boolean} True if this is a rate limit error
 */
function isRateLimitError(error) {
  if (!error) {
    return false;
  }
  const status = error.status || error?.response?.status;
  if (status === 403) {
    const message = String(error.message || error?.response?.data?.message || '').toLowerCase();
    return message.includes('rate limit') || message.includes('ratelimit') || message.includes('api rate');
  }
  if (status === 429) {
    return true;
  }
  return false;
}

/**
 * Check if an error is a secondary rate limit (abuse detection)
 * @param {Error} error - The error to check
 * @returns {boolean} True if this is a secondary rate limit
 */
function isSecondaryRateLimitError(error) {
  if (!error) {
    return false;
  }
  const status = error.status || error?.response?.status;
  if (status !== 403) {
    return false;
  }
  const message = String(error.message || error?.response?.data?.message || '').toLowerCase();
  return message.includes('secondary rate limit') || message.includes('abuse');
}

/**
 * Sleep for a specified duration
 * @param {number} ms - Milliseconds to sleep
 * @returns {Promise<void>}
 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Extract rate limit reset time from error or response headers
 * @param {Error|Object} errorOrResponse - Error object or API response
 * @returns {number|null} Unix timestamp of reset time, or null if not found
 */
function extractRateLimitReset(errorOrResponse) {
  if (!errorOrResponse) {
    return null;
  }

  // Check response headers
  const headers = errorOrResponse?.response?.headers || errorOrResponse?.headers || {};
  const resetHeader = headers['x-ratelimit-reset'] || headers['X-RateLimit-Reset'];
  if (resetHeader) {
    const parsed = parseInt(resetHeader, 10);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  // Check Retry-After header (for secondary rate limits)
  const retryAfter = headers['retry-after'] || headers['Retry-After'];
  if (retryAfter) {
    const seconds = parseInt(retryAfter, 10);
    if (Number.isFinite(seconds)) {
      return Math.floor(Date.now() / 1000) + seconds;
    }
  }

  return null;
}

/**
 * Calculate wait time until rate limit reset
 * @param {number} resetTimestamp - Unix timestamp when rate limit resets
 * @returns {number} Milliseconds to wait (minimum 1000ms)
 */
function calculateWaitUntilReset(resetTimestamp) {
  if (!resetTimestamp) {
    return DEFAULT_BASE_DELAY_MS;
  }
  const now = Date.now();
  const resetTime = resetTimestamp * 1000; // Convert to milliseconds
  const waitTime = resetTime - now;
  // Minimum wait of 1 second, maximum of 60 seconds
  return Math.max(1000, Math.min(waitTime + 1000, 60000));
}

/**
 * Log helper that works with or without core
 * @param {Object|null} core - GitHub Actions core object (optional)
 * @param {'info'|'warning'|'error'} level - Log level
 * @param {string} message - Message to log
 */
function log(core, level, message) {
  if (core && typeof core[level] === 'function') {
    core[level](message);
  } else {
    const logFn = level === 'error' ? console.error : level === 'warning' ? console.warn : console.log;
    logFn(`[${level.toUpperCase()}] ${message}`);
  }
}

/**
 * Wrapper for github.paginate with exponential backoff on rate limit errors
 *
 * @param {Object} github - Octokit instance
 * @param {Function} method - API method to paginate (e.g., github.rest.issues.listComments)
 * @param {Object} params - Parameters for the API call
 * @param {Object} options - Configuration options
 * @param {number} [options.maxRetries=3] - Maximum number of retry attempts
 * @param {number} [options.baseDelay=1000] - Base delay in milliseconds for backoff
 * @param {number} [options.maxDelay=30000] - Maximum delay in milliseconds
 * @param {Object} [options.core=null] - GitHub Actions core object for logging
 * @returns {Promise<Array>} Paginated results
 * @throws {Error} When all retries are exhausted
 */
async function paginateWithBackoff(github, method, params, options = {}) {
  const {
    maxRetries = DEFAULT_MAX_RETRIES,
    baseDelay = DEFAULT_BASE_DELAY_MS,
    maxDelay = DEFAULT_MAX_DELAY_MS,
    core = null,
    env = process.env,
  } = options;

  let client = github;
  try {
    client = await ensureRateLimitWrapped({ github, core, env });
  } catch (error) {
    client = github;
  }

  // Use withGithubApiRetry for comprehensive transient error handling
  return withGithubApiRetry(
    () => client.paginate(method, params),
    {
      operation: 'read', // Pagination is typically a read operation
      label: 'GitHub API pagination',
      maxRetriesByOperation: {
        read: maxRetries,
        write: maxRetries,
        dispatch: maxRetries,
        admin: maxRetries,
        unknown: maxRetries,
      },
      baseDelay,
      maxDelay,
      core,
      backoffFn: calculateBackoffDelay,
    }
  );
}

/**
 * Wrapper for single API calls (non-paginated) with exponential backoff
 *
 * @param {Function} apiCall - Async function that makes the API call
 * @param {Object} options - Configuration options
 * @param {number} [options.maxRetries=3] - Maximum number of retry attempts
 * @param {number} [options.baseDelay=1000] - Base delay in milliseconds for backoff
 * @param {number} [options.maxDelay=30000] - Maximum delay in milliseconds
 * @param {Object} [options.core=null] - GitHub Actions core object for logging
 * @returns {Promise<any>} API call result
 * @throws {Error} When all retries are exhausted
 */
async function withBackoff(apiCall, options = {}) {
  const {
    maxRetries = DEFAULT_MAX_RETRIES,
    baseDelay = DEFAULT_BASE_DELAY_MS,
    maxDelay = DEFAULT_MAX_DELAY_MS,
    core = null,
  } = options;

  // Use withGithubApiRetry for comprehensive transient error handling
  return withGithubApiRetry(apiCall, {
    operation: 'read', // Default to read operation
    label: 'GitHub API call',
    maxRetriesByOperation: {
      read: maxRetries,
      write: maxRetries,
      dispatch: maxRetries,
      admin: maxRetries,
      unknown: maxRetries,
    },
    baseDelay,
    maxDelay,
    core,
    backoffFn: calculateBackoffDelay,
  });
}

/**
 * Check current rate limit status and return whether it's safe to proceed
 *
 * @param {Object} github - Octokit instance
 * @param {Object} options - Configuration options
 * @param {number} [options.threshold=500] - Minimum remaining requests required
 * @param {Object} [options.core=null] - GitHub Actions core object for logging
 * @returns {Promise<Object>} Rate limit status
 */
async function checkRateLimitStatus(github, options = {}) {
  const { threshold = RATE_LIMIT_THRESHOLD, core = null, env = process.env } = options;

  let client = github;
  try {
    client = await ensureRateLimitWrapped({ github, core, env });
  } catch (error) {
    client = github;
  }

  try {
    const { data: rateLimit } = await client.rest.rateLimit.get();
    const coreLimit = rateLimit?.resources?.core || {};
    const remaining = coreLimit.remaining || 0;
    const limit = coreLimit.limit || 5000;
    const resetTimestamp = coreLimit.reset || 0;
    const resetTime = new Date(resetTimestamp * 1000);

    const safe = remaining >= threshold;
    const percentUsed = limit > 0 ? Math.round(((limit - remaining) / limit) * 100) : 0;

    const status = {
      safe,
      remaining,
      limit,
      threshold,
      percentUsed,
      resetTimestamp,
      resetTime: resetTime.toISOString(),
      waitTimeMs: safe ? 0 : calculateWaitUntilReset(resetTimestamp),
    };

    if (!safe) {
      log(
        core,
        'warning',
        `Rate limit low: ${remaining}/${limit} remaining (${percentUsed}% used). ` +
          `Threshold: ${threshold}. Resets at ${status.resetTime}`
      );
    } else {
      log(core, 'info', `Rate limit OK: ${remaining}/${limit} remaining (${percentUsed}% used)`);
    }

    return status;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    log(core, 'warning', `Failed to check rate limit: ${message}`);

    // Return safe=true on error to avoid blocking workflows unnecessarily
    return {
      safe: true,
      remaining: -1,
      limit: -1,
      threshold,
      percentUsed: -1,
      resetTimestamp: 0,
      resetTime: '',
      waitTimeMs: 0,
      error: message,
    };
  }
}

/**
 * Create a rate-limit-aware wrapper around an Octokit instance
 * This creates proxy methods that automatically apply backoff
 *
 * @param {Object} github - Octokit instance
 * @param {Object} options - Default options for all calls
 * @returns {Object} Wrapped methods
 */
function createRateLimitAwareClient(github, options = {}) {
  const defaultOptions = {
    maxRetries: DEFAULT_MAX_RETRIES,
    baseDelay: DEFAULT_BASE_DELAY_MS,
    maxDelay: DEFAULT_MAX_DELAY_MS,
    core: null,
    ...options,
  };

  return {
    /**
     * Paginate with automatic backoff
     */
    paginate: (method, params, opts = {}) =>
      paginateWithBackoff(github, method, params, { ...defaultOptions, ...opts }),

    /**
     * Check rate limit status
     */
    checkRateLimit: (opts = {}) => checkRateLimitStatus(github, { ...defaultOptions, ...opts }),

    /**
     * Wrap any API call with backoff
     */
    withBackoff: (apiCall, opts = {}) => withBackoff(apiCall, { ...defaultOptions, ...opts }),

    /**
     * Access to raw github client for non-wrapped calls
     */
    raw: github,
  };
}

module.exports = {
  // Core functions
  isRateLimitError,
  isSecondaryRateLimitError,
  sleep,
  extractRateLimitReset,
  calculateWaitUntilReset,

  // Main utilities
  paginateWithBackoff,
  withBackoff,
  checkRateLimitStatus,
  createRateLimitAwareClient,

  // Constants
  DEFAULT_MAX_RETRIES,
  DEFAULT_BASE_DELAY_MS,
  DEFAULT_MAX_DELAY_MS,
  RATE_LIMIT_THRESHOLD,
};
