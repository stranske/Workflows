#!/usr/bin/env node

/**
 * Rate-Limited GitHub API Wrapper
 * 
 * Creates a proxy around the Octokit instance that automatically wraps
 * all API calls with token-aware retry logic. This allows existing code
 * to continue using `github.rest.*` without modification while gaining
 * rate limit resilience.
 * 
 * Usage:
 *   const { createRateLimitedGithub } = require('./github-rate-limited-wrapper.js');
 *   const github = await createRateLimitedGithub({ github: rawGithub, core });
 *   
 *   // Now all calls automatically use retry
 *   const { data } = await github.rest.issues.get({ owner, repo, issue_number });
 */

'use strict';

const { createTokenAwareRetry } = require('./github-api-with-retry.js');

/**
 * Creates a proxied Octokit instance that wraps all API calls with retry logic.
 * 
 * @param {Object} options
 * @param {Object} options.github - Original Octokit instance
 * @param {Object} options.core - GitHub Actions core for logging
 * @param {Object} options.env - Environment variables (defaults to process.env)
 * @returns {Promise<Object>} Proxied github instance with automatic retry
 */
async function createRateLimitedGithub(options = {}) {
  const { github, core, env = process.env } = options;
  
  if (!github) {
    throw new Error('createRateLimitedGithub requires a github client');
  }

  // Initialize token-aware retry
  const {
    withRetry,
    github: tokenAwareGithub,
    tokenRegistry,
    getTokenSource,
  } = await createTokenAwareRetry({
    github,
    core,
    env,
  });

  // Use the token-aware github client as base
  const baseClient = tokenAwareGithub || github;

  // Create a wrapper that retries API calls with token switching
  // The `path` is used to locate the method on the fresh client during retry
  function wrapApiMethod(path) {
    return async function wrappedMethod(...args) {
      return withRetry((client) => {
        // Navigate to the method on the (possibly fresh) client
        const pathParts = path.split('.');
        let target = client;
        for (const part of pathParts) {
          target = target?.[part];
        }
        if (typeof target !== 'function') {
          throw new Error(`Method ${path} not found on github client`);
        }
        return target.apply(client, args);
      });
    };
  }

  function createNamespaceProxy(namespace, pathPrefix) {
    return new Proxy(namespace, {
      get(target, prop) {
        const value = target[prop];
        const currentPath = pathPrefix ? `${pathPrefix}.${prop}` : prop;
        
        if (typeof value === 'function') {
          // Wrap the method with retry (path is used to find method on fresh client)
          return wrapApiMethod(currentPath);
        }
        
        if (value && typeof value === 'object') {
          // Recursively proxy nested namespaces
          return createNamespaceProxy(value, currentPath);
        }
        
        return value;
      },
    });
  }

  // Create the proxied github object
  const proxiedGithub = new Proxy(baseClient, {
    get(target, prop) {
      // Special handling for rest and graphql
      if (prop === 'rest' && target.rest) {
        return createNamespaceProxy(target.rest, 'rest');
      }
      
      if (prop === 'graphql' && typeof target.graphql === 'function') {
        return async function wrappedGraphql(...args) {
          return withRetry((client) => client.graphql(...args));
        };
      }
      
      if (prop === 'paginate' && typeof target.paginate === 'function') {
        // For paginate, wrap the entire operation
        return async function wrappedPaginate(method, params, ...rest) {
          return withRetry((client) => client.paginate(method, params, ...rest));
        };
      }
      
      // Pass through other properties
      const value = target[prop];
      if (typeof value === 'function') {
        return value.bind(target);
      }
      return value;
    },
  });

  // Attach metadata for debugging
  Object.defineProperty(proxiedGithub, '__rateLimitWrapped', {
    value: true,
    enumerable: false,
    configurable: false,
    writable: false,
  });

  Object.defineProperty(proxiedGithub, '__tokenRegistry', {
    value: tokenRegistry,
    enumerable: false,
    configurable: false,
    writable: false,
  });

  Object.defineProperty(proxiedGithub, '__getTokenSource', {
    value: getTokenSource,
    enumerable: false,
    configurable: false,
    writable: false,
  });

  return proxiedGithub;
}

/**
 * Check if a github client is already wrapped with rate limit protection.
 * 
 * @param {Object} github - Octokit instance to check
 * @returns {boolean} True if the client is wrapped
 */
function isRateLimitWrapped(github) {
  return github?.__rateLimitWrapped === true;
}

/**
 * Check if a github client is a test mock (not a real Octokit instance).
 * Real Octokit instances have internal properties like request, hooks, etc.
 * 
 * @param {Object} github - Octokit instance to check
 * @returns {boolean} True if the client appears to be a test mock
 */
function isTestMock(github) {
  if (!github) return false;
  // Real Octokit has `request` method and `hook` property
  // Simple test mocks typically just have { rest: { ... } }
  if (typeof github.request === 'function' && typeof github.hook === 'object') {
    return false;  // Likely real Octokit
  }
  // Check for explicit test mock marker
  if (github.__testMock === true) {
    return true;
  }
  // If it has rest but no request/hook, it's probably a test mock
  if (github.rest && !github.request && !github.hook) {
    return true;
  }
  return false;
}

/**
 * Ensures a github client is rate-limit wrapped. If already wrapped, returns as-is.
 * For test mocks or missing github clients, returns as-is to avoid initialization overhead/errors.
 * 
 * @param {Object} options
 * @param {Object} options.github - Octokit instance
 * @param {Object} options.core - GitHub Actions core for logging
 * @param {Object} options.env - Environment variables
 * @returns {Promise<Object>} Rate-limit wrapped github client (or original if test mock/undefined)
 */
async function ensureRateLimitWrapped(options = {}) {
  const { github, core, env = process.env } = options;
  
  // If no github client provided, return undefined (some functions don't need it)
  if (!github) {
    return github;
  }
  
  if (isRateLimitWrapped(github)) {
    core?.debug?.('GitHub client already rate-limit wrapped');
    return github;
  }
  
  // Skip wrapping for test mocks to avoid initialization overhead
  if (isTestMock(github)) {
    core?.debug?.('GitHub client appears to be a test mock, skipping rate-limit wrapping');
    return github;
  }
  
  return createRateLimitedGithub({ github, core, env });
}

/**
 * Higher-order function that wraps a function to automatically wrap the github
 * client with rate-limit protection. This reduces boilerplate in module.exports.
 * 
 * @param {Function} fn - The async function to wrap. Must accept { github, ...rest }
 * @param {Object} options - Options for the wrapper
 * @param {Object} options.env - Environment variables (defaults to process.env)
 * @returns {Function} Wrapped function with rate-limit protected github client
 * 
 * @example
 * // Instead of:
 * module.exports = {
 *   myFunction: async function({ github: rawGithub, core, ...rest }) {
 *     const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
 *     return myFunction({ github, core, ...rest });
 *   },
 * };
 * 
 * // Use:
 * module.exports = {
 *   myFunction: wrapWithRateLimitedGithub(myFunction),
 * };
 */
function wrapWithRateLimitedGithub(fn, options = {}) {
  const { env = process.env } = options;
  
  return async function wrappedFunction({ github: rawGithub, core, ...rest }) {
    let github;
    try {
      github = await ensureRateLimitWrapped({ github: rawGithub, core, env });
    } catch (error) {
      core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
      github = rawGithub;
    }
    return fn({ github, core, ...rest });
  };
}

module.exports = {
  createRateLimitedGithub,
  isRateLimitWrapped,
  isTestMock,
  ensureRateLimitWrapped,
  wrapWithRateLimitedGithub,
};
