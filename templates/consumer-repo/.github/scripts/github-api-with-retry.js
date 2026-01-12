#!/usr/bin/env node

/**
 * GitHub API Retry Wrapper
 * 
 * Wraps Octokit API calls with exponential backoff retry logic for rate limit errors.
 * This prevents workflows from failing when hitting GitHub API rate limits.
 * 
 * Usage in github-script actions:
 *   const { withRetry } = require('./.github/scripts/github-api-with-retry.js');
 *   const data = await withRetry(() => github.rest.issues.get({...}));
 */

/**
 * Exponential backoff retry wrapper for GitHub API calls
 * 
 * @param {Function} fn - Async function that makes GitHub API call
 * @param {Object} options - Retry options
 * @param {number} options.maxRetries - Maximum number of retries (default: 5)
 * @param {number} options.initialDelay - Initial delay in ms (default: 1000)
 * @param {number} options.maxDelay - Maximum delay in ms (default: 60000)
 * @param {Function} options.onRetry - Callback on retry (receives attempt, error, delay)
 * @returns {Promise<any>} - Result of the API call
 */
async function withRetry(fn, options = {}) {
  const {
    maxRetries = 5,
    initialDelay = 1000,
    maxDelay = 60000,
    onRetry = null
  } = options;

  let lastError;
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      
      // Check if it's a rate limit error
      const isRateLimit = 
        error.status === 403 &&
        (error.message?.includes('rate limit') ||
         error.message?.includes('API rate limit exceeded'));
      
      // Check if it's a secondary rate limit (abuse detection)
      const isSecondaryRateLimit =
        error.status === 403 &&
        error.message?.includes('secondary rate limit');
      
      // Don't retry on non-rate-limit errors
      if (!isRateLimit && !isSecondaryRateLimit) {
        throw error;
      }
      
      // Don't retry if we've exhausted attempts
      if (attempt === maxRetries) {
        console.error(`Max retries (${maxRetries}) reached for rate limit error`);
        throw error;
      }
      
      // Calculate delay with exponential backoff
      const baseDelay = isSecondaryRateLimit 
        ? initialDelay * 2  // Secondary rate limits need longer delays
        : initialDelay;
      
      const delay = Math.min(
        baseDelay * Math.pow(2, attempt),
        maxDelay
      );
      
      // Add jitter to prevent thundering herd
      const jitter = Math.random() * 0.3 * delay;
      const actualDelay = delay + jitter;
      
      console.log(
        `Rate limit hit (attempt ${attempt + 1}/${maxRetries + 1}). ` +
        `Retrying in ${Math.round(actualDelay / 1000)}s...`
      );
      
      if (onRetry) {
        onRetry(attempt + 1, error, actualDelay);
      }
      
      await sleep(actualDelay);
    }
  }
  
  throw lastError;
}

/**
 * Sleep for specified milliseconds
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Wrap paginate calls with retry logic
 * 
 * @param {Object} github - Octokit instance
 * @param {Function} method - Octokit method to paginate
 * @param {Object} params - Parameters for the API call
 * @param {Object} options - Retry options (same as withRetry)
 * @returns {Promise<Array>} - Paginated results
 */
async function paginateWithRetry(github, method, params, options = {}) {
  return withRetry(
    () => github.paginate(method, params),
    options
  );
}

module.exports = {
  withRetry,
  paginateWithRetry,
  sleep
};
