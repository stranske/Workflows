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
 *
 * This module also absorbs the former `github_api_retry.js` (category-aware
 * retry: withGithubApiRetry/computeRetryDelayMs/resolveMaxRetries/
 * calculateBackoffDelay) and `api-helpers.js` (paginateWithBackoff/withBackoff/
 * checkRateLimitStatus/createRateLimitAwareClient and rate-limit reset helpers)
 * so all GitHub-API retry/pagination/backoff helpers live in one module.
 */

const { classifyError, ERROR_CATEGORIES } = require('./error_classifier');

// NOTE: `github-rate-limited-wrapper.js` requires THIS module
// (createTokenAwareRetry), so it is required lazily inside the functions that
// need it (paginateWithBackoff/checkRateLimitStatus) to avoid a circular
// require at module-load time.

const DEFAULT_BASE_DELAY_MS = 1000;
const DEFAULT_MAX_DELAY_MS = 30000;
const DEFAULT_MAX_RETRIES = 3;
const RATE_LIMIT_THRESHOLD = 500;

const DEFAULT_RETRY_LIMITS = Object.freeze({
  read: 3,
  write: 2,
  dispatch: 2,
  admin: 1,
  unknown: 1,
});

function normaliseHeaders(headers) {
  if (!headers || typeof headers !== 'object') {
    return {};
  }
  return Object.entries(headers).reduce((acc, [key, value]) => {
    acc[String(key).toLowerCase()] = value;
    return acc;
  }, {});
}

function extractRateLimitInfo(headers) {
  const remaining = parseInt(headers['x-ratelimit-remaining'], 10);
  const limit = parseInt(headers['x-ratelimit-limit'], 10);
  const reset = parseInt(headers['x-ratelimit-reset'], 10);
  return {
    remaining: Number.isFinite(remaining) ? remaining : null,
    limit: Number.isFinite(limit) ? limit : null,
    reset: Number.isFinite(reset) ? reset : null,
  };
}

function hasRateLimitHeaders(headers) {
  if (!headers || typeof headers !== 'object') {
    return false;
  }
  const rateLimitKeys = [
    'x-ratelimit-remaining',
    'x-ratelimit-limit',
    'x-ratelimit-used',
    'x-ratelimit-reset',
  ];
  return rateLimitKeys.some((key) => Object.prototype.hasOwnProperty.call(headers, key));
}

function isRateLimitError(error) {
  if (!error) {
    return false;
  }
  const status = error.status || error?.response?.status;
  if (status === 429) {
    return true;
  }
  const message = String(error.message || error?.response?.data?.message || '').toLowerCase();
  if (status === 403) {
    if (message.includes('rate limit') || message.includes('api rate limit exceeded')) {
      return true;
    }
  }
  const headers = normaliseHeaders(error?.response?.headers || error?.headers);
  const remaining = parseInt(headers['x-ratelimit-remaining'], 10);
  return Number.isFinite(remaining) && remaining <= 0;
}

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

function isIntegrationPermissionError(error) {
  if (!error) {
    return false;
  }
  const status = error.status || error?.response?.status;
  if (status !== 403 && status !== 404) {
    return false;
  }
  const message = String(error.message || error?.response?.data?.message || '').toLowerCase();
  return (
    message.includes('resource not accessible by integration') ||
    message.includes('insufficient permission') ||
    message.includes('requires higher permissions')
  );
}


const TRANSIENT_ERROR_CODES = new Set([
  'ECONNRESET',
  'ECONNREFUSED',
  'ETIMEDOUT',
  'EAI_AGAIN',
  'ENOTFOUND',
]);

const IDEMPOTENT_HTTP_METHODS = new Set([
  'GET',
  'HEAD',
  'OPTIONS',
]);

function isTransientError(error) {
  if (!error) {
    return false;
  }
  const status = error.status || error?.response?.status;
  if (status && [500, 502, 503, 504].includes(status)) {
    return true;
  }
  const message = String(error.message || '').toLowerCase();
  if (message.includes('fetch failed') || message.includes('network error')) {
    return true;
  }
  // Check for transient network error codes (ECONNRESET, ETIMEDOUT, etc.).
  // Avoid accessing error.code on Octokit RequestError objects — the property
  // has a deprecated getter that emits noisy deprecation warnings.  Prefer
  // error.cause.code (Node.js fetch/network errors) and only fall back to
  // error.code when the error is NOT an Octokit HTTP error (has no .status).
  const causeCode = String(error?.cause?.code || '').toUpperCase();
  if (TRANSIENT_ERROR_CODES.has(causeCode)) {
    return true;
  }
  // Only check error.code via hasOwnProperty to avoid triggering
  // Octokit RequestError's deprecated getter (which defines .code on the
  // prototype, not as an own property).  Node.js network errors set .code
  // as an own property (e.g. ECONNRESET).
  if (!status && Object.prototype.hasOwnProperty.call(error, 'code')) {
    const code = String(error.code).toUpperCase();
    return TRANSIENT_ERROR_CODES.has(code);
  }
  return false;
}

function logWithCore(core, level, message) {
  if (core && typeof core[level] === 'function') {
    core[level](message);
    return;
  }
  const logFn = level === 'error' ? console.error : level === 'warning' ? console.warn : console.log;
  logFn(message);
}

function logTokenUsage(core, tokenSource, info, context) {
  if (!core || typeof core.debug !== 'function') {
    return;
  }

  if (info && info.remaining !== null && info.limit !== null) {
    core.debug(`Token ${tokenSource} ${context} remaining: ${info.remaining}/${info.limit}`);
    return;
  }

  core.debug(`Token ${tokenSource} ${context} usage recorded (no rate limit headers)`);
}

function resolveOctokitFactory({ github, getOctokit, Octokit }) {
  if (typeof getOctokit === 'function') {
    return getOctokit;
  }
  if (github && typeof github.getOctokit === 'function') {
    return github.getOctokit.bind(github);
  }
  // Only use github.constructor if it's a real Octokit-like class,
  // not just Object (which all plain objects have as constructor)
  if (github && typeof github.constructor === 'function' && 
      github.constructor.name !== 'Object' && github.constructor.name !== 'Array') {
    return (token) => new github.constructor({ auth: token });
  }
  if (Octokit) {
    return (token) => new Octokit({ auth: token });
  }
  return null;
}

/**
 * Exponential backoff retry wrapper for GitHub API calls
 * 
 * @param {Function} fn - Async function that makes GitHub API call
 * @param {Object} options - Retry options
 * @param {number} options.maxRetries - Maximum number of retries (default: 5)
 * @param {number} options.initialDelay - Initial delay in ms (default: 1000)
 * @param {number} options.maxDelay - Maximum delay in ms (default: 60000)
 * @param {Function} options.onRetry - Callback on retry (receives attempt, error, delay)
 * @param {Object} options.github - Octokit instance
 * @param {Object} options.core - GitHub Actions core for logging
 * @param {Object} options.tokenRegistry - Token load balancer registry
 * @param {Function} options.getOctokit - Factory for new Octokit instances
 * @param {string} options.tokenSource - Current token registry ID
 * @param {string[]} options.capabilities - Required token capabilities
 * @param {string} options.preferredType - Prefer APP or PAT
 * @param {string} options.task - Task name for specialization matching
 * @param {number} options.minRemaining - Minimum remaining calls needed
 * @param {Function} options.onTokenSwitch - Callback on token switch
 * @param {boolean} options.allowNonIdempotentRetries - Allow retries for non-idempotent methods
 * @returns {Promise<any>} - Result of the API call
 */
async function withRetry(fn, options = {}) {
  const {
    maxRetries = 5,
    initialDelay = 1000,
    maxDelay = 60000,
    onRetry = null,
    github = null,
    core = null,
    tokenRegistry = null,
    getOctokit = null,
    Octokit = null,
    tokenSource = null,
    capabilities = [],
    preferredType = null,
    task = null,
    minRemaining = 100,
    onTokenSwitch = null,
    allowNonIdempotentRetries = false,
  } = options;

  let lastError;
  let currentGithub = github;
  let currentTokenSource = tokenSource;
  const octokitFactory = resolveOctokitFactory({ github, getOctokit, Octokit });

  async function switchToken(reason) {
    if (!tokenRegistry || typeof tokenRegistry.getOptimalToken !== 'function') {
      return false;
    }
    let selection;
    try {
      selection = await tokenRegistry.getOptimalToken({
        github: currentGithub || github,
        core,
        capabilities,
        preferredType,
        task,
        minRemaining,
      });
    } catch (error) {
      logWithCore(core, 'warning', `Token registry selection failed: ${error.message}`);
      return false;
    }

    if (!selection || !selection.token) {
      logWithCore(core, 'warning', 'Token registry returned no available token');
      return false;
    }

    if (!octokitFactory) {
      logWithCore(core, 'warning', 'Cannot switch tokens without an Octokit factory');
      return false;
    }

    if (selection.source === currentTokenSource && currentGithub) {
      return false;
    }

    currentGithub = octokitFactory(selection.token);
    currentTokenSource = selection.source;

    logWithCore(
      core,
      'info',
      `Switching to token ${selection.source} due to ${reason} rate limit`
    );

    if (typeof onTokenSwitch === 'function') {
      onTokenSwitch({
        github: currentGithub,
        tokenSource: currentTokenSource,
        tokenInfo: selection,
        reason,
      });
    }

    return true;
  }

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = currentGithub ? await fn(currentGithub) : await fn();

      if (tokenRegistry && currentTokenSource) {
        const headers = normaliseHeaders(response?.headers);
        const info = extractRateLimitInfo(headers);

        if (hasRateLimitHeaders(headers) && typeof tokenRegistry.updateFromHeaders === 'function') {
          tokenRegistry.updateFromHeaders(currentTokenSource, headers);
          logTokenUsage(core, currentTokenSource, info, 'response');
        } else if (typeof tokenRegistry.updateTokenUsage === 'function') {
          tokenRegistry.updateTokenUsage(currentTokenSource, 1);
          logTokenUsage(core, currentTokenSource, null, 'response');
        }
      }

      return response;
    } catch (error) {
      lastError = error;

      const rateLimitError = isRateLimitError(error);
      const secondaryRateLimit = isSecondaryRateLimitError(error);
      const integrationPermissionError = isIntegrationPermissionError(error);
      const transientError = isTransientError(error);
      const requestMethod = String(error?.request?.method || '').toUpperCase();
      const isIdempotentMethod = requestMethod
        ? IDEMPOTENT_HTTP_METHODS.has(requestMethod)
        : false;
      const allowNonIdempotent = allowNonIdempotentRetries === true;
      const shouldRetryTransient = transientError && (isIdempotentMethod || allowNonIdempotent);
      const headers = normaliseHeaders(error?.response?.headers || error?.headers);

      if (tokenRegistry && currentTokenSource) {
        const info = extractRateLimitInfo(headers);
        if (hasRateLimitHeaders(headers) && typeof tokenRegistry.updateFromHeaders === 'function') {
          tokenRegistry.updateFromHeaders(currentTokenSource, headers);
          logTokenUsage(core, currentTokenSource, info, 'error');
        } else if (typeof tokenRegistry.updateTokenUsage === 'function') {
          tokenRegistry.updateTokenUsage(currentTokenSource, 1);
          logTokenUsage(core, currentTokenSource, null, 'error');
        }
      }

      if (integrationPermissionError && task === 'gate-commit-status') {
        logWithCore(
          core,
          'warning',
          'Gate commit status update blocked by permissions; leaving existing status untouched.'
        );
        return null;
      }

      // Don't retry on non-rate-limit errors unless they're transient and safe
      if (!rateLimitError && !secondaryRateLimit && !shouldRetryTransient) {
        throw error;
      }

      // Switch tokens on primary rate limit exhaustion
      if (rateLimitError && !secondaryRateLimit) {
        const switched = await switchToken('primary');
        if (switched) {
          continue;
        }
      }

      // Don't retry if we've exhausted attempts
      if (attempt === maxRetries) {
        const retryReason = secondaryRateLimit
          ? 'secondary rate limit'
          : rateLimitError
            ? 'rate limit'
            : 'transient error';
        const errorMsg = `Max retries (${maxRetries}) reached for ${retryReason}`;
        console.error(errorMsg);
        // Surface as a GitHub Actions error annotation so the failure
        // mode is visible in run summaries, not buried in logs.
        let annotationDetails;
        if (retryReason === 'rate limit') {
          annotationDetails =
            'This indicates all available tokens are exhausted. ' +
            'Check token rotation and rate limit budgets.';
        } else if (retryReason === 'secondary rate limit') {
          annotationDetails =
            'A secondary rate limit (abuse detection) was ' +
            'repeatedly hit. Reduce concurrency or spread ' +
            'requests over a longer period.';
        } else {
          annotationDetails =
            'Repeated transient failures despite retries. ' +
            'Check network conditions and GitHub status.';
        }
        logWithCore(
          core,
          'error',
          `${errorMsg}. Token: ${currentTokenSource || 'unknown'}. ` +
          annotationDetails
        );
        throw error;
      }

      // Calculate delay with exponential backoff
      const baseDelay = secondaryRateLimit
        ? initialDelay * 2  // Secondary rate limits need longer delays
        : initialDelay;

      const delay = Math.min(
        baseDelay * Math.pow(2, attempt),
        maxDelay
      );

      // Add jitter to prevent thundering herd
      const jitter = Math.random() * 0.3 * delay;
      const actualDelay = delay + jitter;

      const retryReason = secondaryRateLimit
        ? 'secondary rate limit'
        : rateLimitError
          ? 'rate limit'
          : 'transient error';

      console.log(
        `${retryReason} (attempt ${attempt + 1}/${maxRetries + 1}). ` +
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
    (client) => client.paginate(method, params),
    { ...options, github }
  );
}

function collectTokenSecrets(env = {}) {
  const keys = [
    'SERVICE_BOT_PAT',
    'ACTIONS_BOT_PAT',
    'OWNER_PR_PAT',
    'AGENTS_AUTOMATION_PAT',
    'TOKEN_ROTATION_JSON',
    'TOKEN_ROTATION_ENV_KEYS',
    'TOKEN_ROTATION_KEYS',
    'PAT_1',
    'PAT_2',
    'PAT_3',
    'WORKFLOWS_APP_ID',
    'WORKFLOWS_APP_PRIVATE_KEY',
    'KEEPALIVE_APP_ID',
    'KEEPALIVE_APP_PRIVATE_KEY',
    'GH_APP_ID',
    'GH_APP_PRIVATE_KEY',
    'APP_1_ID',
    'APP_1_PRIVATE_KEY',
    'APP_2_ID',
    'APP_2_PRIVATE_KEY',
  ];

  const dynamicKeysRaw = env.TOKEN_ROTATION_ENV_KEYS || env.TOKEN_ROTATION_KEYS || '';
  const dynamicKeys = dynamicKeysRaw
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
  const allKeys = Array.from(new Set([...keys, ...dynamicKeys]));

  return allKeys.reduce((acc, key) => {
    if (env[key]) {
      acc[key] = env[key];
    }
    return acc;
  }, {});
}

/**
 * Create a token-aware retry wrapper that initializes the load balancer
 * using secrets from the environment.
 *
 * @param {Object} options
 * @param {Object} options.github - Octokit instance
 * @param {Object} options.core - GitHub Actions core for logging
 * @param {Object} options.env - Environment variables (defaults to process.env)
 * @param {Object} options.tokenRegistry - Optional token registry override
 * @param {Function} options.getOctokit - Optional Octokit factory
 * @param {Object} options.Octokit - Optional Octokit constructor
 * @returns {Promise<Object>} { github, withRetry, paginateWithRetry, tokenRegistry }
 */
async function createTokenAwareRetry(options = {}) {
  const {
    github,
    core = null,
    env = process.env,
    tokenRegistry = null,
    getOctokit = null,
    Octokit = null,
    capabilities = [],
    preferredType = null,
    task = null,
    minRemaining = 100,
    githubToken = null,
  } = options;

  if (!github) {
    throw new Error('createTokenAwareRetry requires a github client');
  }

  const registry = tokenRegistry || require('./token_load_balancer');
  const secrets = collectTokenSecrets(env || {});
  const resolvedGithubToken = githubToken || env?.GITHUB_TOKEN || env?.GH_TOKEN || '';
  const hasTokenInputs =
    Boolean(resolvedGithubToken) ||
    Object.values(secrets).some((value) => Boolean(value));

  let registryInitialized = false;
  if (registry && typeof registry.isInitialized === 'function' && registry.isInitialized()) {
    registryInitialized = true;
  }

  if (
    hasTokenInputs &&
    !registryInitialized &&
    registry &&
    typeof registry.initializeTokenRegistry === 'function'
  ) {
    try {
      await registry.initializeTokenRegistry({
        secrets,
        github,
        core,
        githubToken: resolvedGithubToken,
      });
      registryInitialized = true;
    } catch (error) {
      logWithCore(core, 'warning', `Token registry initialization failed: ${error.message}`);
    }
  }

  let currentGithub = github;
  let currentTokenSource = null;
  const octokitFactory = resolveOctokitFactory({ github, getOctokit, Octokit });

  if (registryInitialized && octokitFactory && typeof registry.getOptimalToken === 'function') {
    try {
      const selection = await registry.getOptimalToken({
        github,
        core,
        capabilities,
        preferredType,
        task,
        minRemaining,
      });
      if (selection?.token) {
        currentGithub = octokitFactory(selection.token);
        currentTokenSource = selection.source;
      }
    } catch (error) {
      logWithCore(core, 'warning', `Token registry selection failed: ${error.message}`);
    }
  }

  const onTokenSwitch = ({ github: nextGithub, tokenSource: nextSource }) => {
    currentGithub = nextGithub;
    currentTokenSource = nextSource;
  };

  return {
    github: currentGithub,
    tokenRegistry: registryInitialized ? registry : null,
    getTokenSource: () => currentTokenSource,
    withRetry: (fn, overrideOptions = {}) => withRetry(fn, {
      github: currentGithub,
      core,
      tokenRegistry: registryInitialized ? registry : null,
      getOctokit: octokitFactory,
      capabilities,
      preferredType,
      task,
      minRemaining,
      tokenSource: currentTokenSource,
      onTokenSwitch,
      ...overrideOptions,
    }),
    paginateWithRetry: (method, params, overrideOptions = {}) => paginateWithRetry(
      currentGithub,
      method,
      params,
      {
        core,
        tokenRegistry: registryInitialized ? registry : null,
        getOctokit: octokitFactory,
        capabilities,
        preferredType,
        task,
        minRemaining,
        tokenSource: currentTokenSource,
        onTokenSwitch,
        ...overrideOptions,
      }
    ),
  };
}

// ===========================================================================
// Category-aware retry (absorbed from former github_api_retry.js)
// ===========================================================================

/**
 * Calculate delay with exponential backoff and jitter.
 * @param {number} attempt - Current attempt number (0-indexed)
 * @param {number} baseDelay - Base delay in milliseconds
 * @param {number} maxDelay - Maximum delay in milliseconds
 * @returns {number} Calculated delay with jitter
 */
function calculateBackoffDelay(attempt, baseDelay = DEFAULT_BASE_DELAY_MS, maxDelay = DEFAULT_MAX_DELAY_MS) {
  const exponentialDelay = baseDelay * Math.pow(2, attempt);
  const cappedDelay = Math.min(exponentialDelay, maxDelay);
  const jitter = cappedDelay * 0.25 * (Math.random() * 2 - 1);
  return Math.round(cappedDelay + jitter);
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

function computeRetryDelayMs({ error, attempt, baseDelay, maxDelay, backoffFn, nowMs }) {
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

/**
 * Retry a GitHub API call only for transient (error_classifier) categories,
 * with category-aware backoff (Retry-After / rate-limit reset / exponential).
 */
async function withGithubApiRetry(apiCall, options = {}) {
  const {
    operation = 'unknown',
    label = 'GitHub API call',
    maxRetriesByOperation = DEFAULT_RETRY_LIMITS,
    baseDelay = DEFAULT_BASE_DELAY_MS,
    maxDelay = DEFAULT_MAX_DELAY_MS,
    core = null,
    sleep: sleepFn = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
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
      await sleepFn(delayMs);
    }
  }

  throw lastError || new Error('GitHub API call failed after retries');
}

// ===========================================================================
// Rate-limit-aware pagination/backoff helpers (absorbed from former
// api-helpers.js). paginateWithBackoff/checkRateLimitStatus wrap the client
// with ensureRateLimitWrapped, lazily required to avoid a circular dependency.
// ===========================================================================

/**
 * Extract rate limit reset time from error or response headers.
 * @param {Error|Object} errorOrResponse
 * @returns {number|null} Unix timestamp of reset time, or null if not found
 */
function extractRateLimitReset(errorOrResponse) {
  if (!errorOrResponse) {
    return null;
  }
  const headers = errorOrResponse?.response?.headers || errorOrResponse?.headers || {};
  const resetHeader = headers['x-ratelimit-reset'] || headers['X-RateLimit-Reset'];
  if (resetHeader) {
    const parsed = parseInt(resetHeader, 10);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
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
 * github.paginate with exponential backoff on transient/rate-limit errors.
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
    // Lazy require breaks the github-rate-limited-wrapper <-> this-module cycle.
    const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');
    client = await ensureRateLimitWrapped({ github, core, env });
  } catch (error) {
    client = github;
  }

  return withGithubApiRetry(
    () => client.paginate(method, params),
    {
      operation: 'read',
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
 * Single (non-paginated) API call with exponential backoff.
 */
async function withBackoff(apiCall, options = {}) {
  const {
    maxRetries = DEFAULT_MAX_RETRIES,
    baseDelay = DEFAULT_BASE_DELAY_MS,
    maxDelay = DEFAULT_MAX_DELAY_MS,
    core = null,
  } = options;

  return withGithubApiRetry(apiCall, {
    operation: 'read',
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
 * Check current rate limit status and report whether it's safe to proceed.
 */
async function checkRateLimitStatus(github, options = {}) {
  const { threshold = RATE_LIMIT_THRESHOLD, core = null, env = process.env } = options;

  let client = github;
  try {
    // Lazy require breaks the github-rate-limited-wrapper <-> this-module cycle.
    const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');
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
      logWithCore(
        core,
        'warning',
        `Rate limit low: ${remaining}/${limit} remaining (${percentUsed}% used). ` +
          `Threshold: ${threshold}. Resets at ${status.resetTime}`
      );
    } else {
      logWithCore(core, 'info', `Rate limit OK: ${remaining}/${limit} remaining (${percentUsed}% used)`);
    }

    return status;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logWithCore(core, 'warning', `Failed to check rate limit: ${message}`);

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
 * Create a rate-limit-aware wrapper around an Octokit instance.
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
    paginate: (method, params, opts = {}) =>
      paginateWithBackoff(github, method, params, { ...defaultOptions, ...opts }),
    checkRateLimit: (opts = {}) => checkRateLimitStatus(github, { ...defaultOptions, ...opts }),
    withBackoff: (apiCall, opts = {}) => withBackoff(apiCall, { ...defaultOptions, ...opts }),
    raw: github,
  };
}

module.exports = {
  isRateLimitError,
  isSecondaryRateLimitError,
  withRetry,
  paginateWithRetry,
  createTokenAwareRetry,
  sleep,
  // Category-aware retry (former github_api_retry.js)
  DEFAULT_RETRY_LIMITS,
  calculateBackoffDelay,
  resolveMaxRetries,
  calculateWaitUntilReset,
  computeRetryDelayMs,
  withGithubApiRetry,
  // Rate-limit-aware pagination/backoff (former api-helpers.js)
  paginateWithBackoff,
  withBackoff,
  checkRateLimitStatus,
  createRateLimitAwareClient,
  extractRateLimitReset,
  DEFAULT_MAX_RETRIES,
  DEFAULT_BASE_DELAY_MS,
  DEFAULT_MAX_DELAY_MS,
  RATE_LIMIT_THRESHOLD,
};
