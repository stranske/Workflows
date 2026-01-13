'use strict';

/**
 * Rate-Limit-Aware API Client with Proactive Token Switching
 * 
 * This module provides proactive rate limit checking and multi-token fallback
 * to prevent rate limit exhaustion before it happens.
 * 
 * LOW EFFORT OPTIMIZATION: Check x-ratelimit-remaining before batch operations
 * and switch tokens when approaching limits.
 */

const { checkRateLimitStatus } = require('./api-helpers');

// Default threshold: switch tokens when < 100 requests remaining
const LOW_RATE_LIMIT_THRESHOLD = 100;
const CRITICAL_RATE_LIMIT_THRESHOLD = 10;

/**
 * Get rate limit info from response headers without making additional API call
 * @param {Object} response - API response with headers
 * @returns {Object} Rate limit info
 */
function extractRateLimitFromResponse(response) {
  if (!response?.headers) {
    return { remaining: null, limit: null, reset: null };
  }
  
  const headers = response.headers;
  const remaining = parseInt(headers['x-ratelimit-remaining'], 10);
  const limit = parseInt(headers['x-ratelimit-limit'], 10);
  const reset = parseInt(headers['x-ratelimit-reset'], 10);
  
  return {
    remaining: Number.isFinite(remaining) ? remaining : null,
    limit: Number.isFinite(limit) ? limit : null,
    reset: Number.isFinite(reset) ? reset : null,
    resetTime: Number.isFinite(reset) ? new Date(reset * 1000).toISOString() : null,
  };
}

/**
 * Check if we should proactively switch tokens based on remaining rate limit
 * @param {number} remaining - Remaining API calls
 * @param {number} threshold - Threshold to trigger switch
 * @returns {boolean} True if should switch tokens
 */
function shouldSwitchToken(remaining, threshold = LOW_RATE_LIMIT_THRESHOLD) {
  if (remaining === null || remaining === undefined) {
    return false;
  }
  return remaining <= threshold;
}

/**
 * Log rate limit status with appropriate severity
 * @param {Object} core - GitHub Actions core object
 * @param {Object} rateLimitInfo - Rate limit info from headers
 * @param {string} tokenLabel - Label for the current token
 */
function logRateLimitStatus(core, rateLimitInfo, tokenLabel = 'current token') {
  const { remaining, limit, resetTime } = rateLimitInfo;
  
  if (remaining === null) {
    return; // No rate limit info available
  }
  
  const percentUsed = limit ? Math.round(((limit - remaining) / limit) * 100) : 0;
  const message = `Rate limit for ${tokenLabel}: ${remaining}/${limit} remaining (${percentUsed}% used)`;
  
  if (remaining < CRITICAL_RATE_LIMIT_THRESHOLD) {
    if (core?.error) {
      core.error(`CRITICAL: ${message}. Resets at ${resetTime}`);
    } else {
      console.error(`[CRITICAL] ${message}. Resets at ${resetTime}`);
    }
  } else if (remaining < LOW_RATE_LIMIT_THRESHOLD) {
    if (core?.warning) {
      core.warning(`${message}. Consider switching tokens. Resets at ${resetTime}`);
    } else {
      console.warn(`[WARN] ${message}. Consider switching tokens. Resets at ${resetTime}`);
    }
  } else if (core?.info) {
    core.info(message);
  }
}

/**
 * Create a client that tracks rate limits from response headers
 * and provides proactive switching recommendations
 * 
 * @param {Object} octokit - Primary Octokit instance
 * @param {Object} options - Configuration
 * @param {Object} [options.fallbackOctokit] - Fallback Octokit instance
 * @param {number} [options.threshold=100] - Threshold to trigger warnings
 * @param {Object} [options.core] - GitHub Actions core object
 * @returns {Object} Rate-limit-aware client
 */
function createProactiveRateLimitClient(octokit, options = {}) {
  const {
    fallbackOctokit = null,
    threshold = LOW_RATE_LIMIT_THRESHOLD,
    core = null,
  } = options;
  
  let currentClient = octokit;
  let usingFallback = false;
  let lastRateLimitInfo = { remaining: null, limit: null, reset: null };
  
  /**
   * Track rate limit from any response
   */
  function trackRateLimit(response, clientLabel) {
    const info = extractRateLimitFromResponse(response);
    if (info.remaining !== null) {
      lastRateLimitInfo = info;
      logRateLimitStatus(core, info, clientLabel);
    }
    return info;
  }
  
  /**
   * Switch to fallback token if available
   */
  function switchToFallback() {
    if (fallbackOctokit && !usingFallback) {
      if (core?.warning) {
        core.warning('Switching to fallback token due to low rate limit');
      } else {
        console.warn('[WARN] Switching to fallback token due to low rate limit');
      }
      currentClient = fallbackOctokit;
      usingFallback = true;
      return true;
    }
    return false;
  }
  
  /**
   * Wrap an API call with rate limit tracking and proactive switching
   */
  async function withRateLimitTracking(apiCallFn, callLabel = 'API call') {
    // Check if we should proactively switch before making the call
    if (shouldSwitchToken(lastRateLimitInfo.remaining, threshold) && !usingFallback) {
      switchToFallback();
    }
    
    const clientLabel = usingFallback ? 'fallback token' : 'primary token';
    
    try {
      const result = await apiCallFn(currentClient);
      trackRateLimit(result, clientLabel);
      return result;
    } catch (error) {
      // Check if this is a rate limit error and we have fallback
      if (error.status === 403 || error.status === 429) {
        trackRateLimit(error.response || error, clientLabel);
        
        if (!usingFallback && switchToFallback()) {
          // Retry with fallback
          if (core?.info) {
            core.info(`Retrying ${callLabel} with fallback token`);
          }
          const result = await apiCallFn(currentClient);
          trackRateLimit(result, 'fallback token');
          return result;
        }
      }
      throw error;
    }
  }
  
  /**
   * Pre-flight check before batch operations
   * Returns true if safe to proceed, false if should wait or switch
   */
  async function preflight(estimatedCalls = 10) {
    const status = await checkRateLimitStatus(currentClient, { threshold, core });
    
    if (status.remaining !== -1 && status.remaining < estimatedCalls) {
      if (core?.warning) {
        core.warning(
          `Pre-flight check: ${status.remaining} remaining, need ~${estimatedCalls}. ` +
          `Consider waiting ${Math.ceil(status.waitTimeMs / 1000)}s or switching tokens.`
        );
      }
      
      // Try switching to fallback
      if (!usingFallback && switchToFallback()) {
        return true; // Switched, safe to proceed
      }
      
      return false; // Not enough quota and no fallback
    }
    
    return true;
  }
  
  return {
    withRateLimitTracking,
    preflight,
    switchToFallback,
    get currentClient() { return currentClient; },
    get usingFallback() { return usingFallback; },
    get lastRateLimitInfo() { return lastRateLimitInfo; },
    trackRateLimit,
  };
}

/**
 * Utility to batch GraphQL queries for efficiency
 * Instead of multiple REST calls, combine into single GraphQL query
 * 
 * @param {Object} octokit - Octokit instance with graphql
 * @param {string} query - GraphQL query string
 * @param {Object} variables - Query variables
 * @returns {Promise<Object>} Query result
 */
async function batchedGraphQL(octokit, query, variables = {}) {
  return octokit.graphql(query, variables);
}

/**
 * Example: Fetch PR data with single GraphQL call instead of multiple REST calls
 * 
 * @param {Object} octokit - Octokit instance
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {number} prNumber - PR number
 * @returns {Promise<Object>} PR data including body, labels, files, and reviews
 */
async function fetchPRDataBatched(octokit, owner, repo, prNumber) {
  const query = `
    query($owner: String!, $repo: String!, $prNumber: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
          number
          title
          body
          state
          author {
            login
          }
          labels(first: 20) {
            nodes {
              name
              color
            }
          }
          files(first: 100) {
            nodes {
              path
              additions
              deletions
            }
          }
          reviews(first: 50) {
            nodes {
              state
              author {
                login
              }
              submittedAt
            }
          }
          commits(last: 1) {
            nodes {
              commit {
                oid
                message
              }
            }
          }
        }
      }
    }
  `;
  
  const result = await batchedGraphQL(octokit, query, { owner, repo, prNumber });
  return result.repository.pullRequest;
}

module.exports = {
  // Core utilities
  extractRateLimitFromResponse,
  shouldSwitchToken,
  logRateLimitStatus,
  
  // Client factory
  createProactiveRateLimitClient,
  
  // GraphQL batching
  batchedGraphQL,
  fetchPRDataBatched,
  
  // Constants
  LOW_RATE_LIMIT_THRESHOLD,
  CRITICAL_RATE_LIMIT_THRESHOLD,
};
