'use strict';

const ERROR_CATEGORIES = Object.freeze({
  transient: 'transient',
  auth: 'auth',
  resource: 'resource',
  logic: 'logic',
  unknown: 'unknown',
});

const RECOVERY_ACTIONS = Object.freeze({
  [ERROR_CATEGORIES.transient]: 'Retry after a short delay; check network or rate limits if repeats.',
  [ERROR_CATEGORIES.auth]: 'Verify credentials, token scopes, and permissions for the repository.',
  [ERROR_CATEGORIES.resource]: 'Confirm the referenced resource exists (repo, PR, branch, workflow, or file).',
  [ERROR_CATEGORIES.logic]: 'Review request inputs and workflow logic for invalid or conflicting data.',
  [ERROR_CATEGORIES.unknown]: 'Capture logs and context; retry once and escalate if the issue persists.',
});

const TRANSIENT_PATTERNS = [
  'rate limit',
  'rate-limited',
  'ratelimit',
  'secondary rate',
  'too many requests',
  'abuse detection',
  'timeout',
  'request timeout',
  'timeout exceeded',
  'timed out',
  'etimedout',
  'econnreset',
  'econnrefused',
  'connection reset',
  'connection aborted',
  'socket hang up',
  'network',
  'enotfound',
  'temporarily unavailable',
  'temporary failure',
  'service unavailable',
  'bad gateway',
  'gateway timeout',
  'eai_again',
  // Git workspace state issues - agent encountered unexpected changes
  'unexpected changes',
  'untracked',
  '.workflows-lib is modified',
  'codex-session',
  'existing changes',
  'how would you like me to proceed',
];

const AUTH_PATTERNS = [
  'bad credentials',
  'unauthorized',
  'requires authentication',
  'not authorized',
  'forbidden',
  'permission denied',
  'access denied',
  'insufficient scopes',
  'insufficient permission',
  'token expired',
  'expired token',
  'missing token',
  'authentication',
  'invalid token',
];

const RESOURCE_PATTERNS = [
  'not found',
  'does not exist',
  'unknown repository',
  'no such repository',
  'repository not found',
  'workflow not found',
  'branch not found',
  'ref not found',
  'no such issue',
  'unknown issue',
  'no such',
  'gone',
  'missing',
  'reference not found',
];

const LOGIC_PATTERNS = [
  'validation failed',
  'unprocessable',
  'unprocessable entity',
  'invalid',
  'bad request',
  'invalid request',
  'conflict',
  'already exists',
  'duplicate',
  'missing required',
  'required field',
  'cannot be blank',
  'failed to validate',
  'failed to parse',
  'unexpected token',
];

function normaliseMessage(error) {
  const rawParts = [
    error?.message,
    error?.code,
    error?.response?.data?.message,
    error?.response?.data?.error,
    error?.response?.statusText,
  ];
  const nestedErrors = error?.response?.data?.errors;
  if (Array.isArray(nestedErrors)) {
    for (const entry of nestedErrors) {
      if (!entry) {
        continue;
      }
      if (typeof entry === 'string') {
        rawParts.push(entry);
      } else if (typeof entry === 'object') {
        rawParts.push(entry.message, entry.code);
      }
    }
  }
  const message = rawParts.filter(Boolean).join(' ');
  return String(message).trim().toLowerCase();
}

function getStatusCode(error) {
  const status = error?.status ?? error?.response?.status;
  return Number.isFinite(status) ? status : null;
}

function matchesPattern(message, patterns) {
  return patterns.some((pattern) => message.includes(pattern));
}

function classifyByStatus(status, message) {
  if (status === 401) {
    return ERROR_CATEGORIES.auth;
  }
  if (status === 403) {
    if (matchesPattern(message, TRANSIENT_PATTERNS)) {
      return ERROR_CATEGORIES.transient;
    }
    if (matchesPattern(message, AUTH_PATTERNS)) {
      return ERROR_CATEGORIES.auth;
    }
    return ERROR_CATEGORIES.auth;
  }
  if (status === 404 || status === 410) {
    return ERROR_CATEGORIES.resource;
  }
  if (status === 408) {
    return ERROR_CATEGORIES.transient;
  }
  if (status === 429 || (status >= 500 && status <= 599)) {
    return ERROR_CATEGORIES.transient;
  }
  if (status === 400 || status === 409 || status === 422) {
    return ERROR_CATEGORIES.logic;
  }
  if (status === 412) {
    return ERROR_CATEGORIES.logic;
  }
  return null;
}

function classifyByMessage(message) {
  if (!message) {
    return null;
  }
  if (matchesPattern(message, TRANSIENT_PATTERNS)) {
    return ERROR_CATEGORIES.transient;
  }
  if (matchesPattern(message, AUTH_PATTERNS)) {
    return ERROR_CATEGORIES.auth;
  }
  if (matchesPattern(message, RESOURCE_PATTERNS)) {
    return ERROR_CATEGORIES.resource;
  }
  if (matchesPattern(message, LOGIC_PATTERNS)) {
    return ERROR_CATEGORIES.logic;
  }
  return null;
}

function classifyError(error) {
  const message = normaliseMessage(error);
  const preview = message ? message.slice(0, 50) : 'unknown';
  if (process.env.RUNNER_DEBUG === '1') {
    // eslint-disable-next-line no-console
    console.log(`[error_classifier] Classifying error: ${preview}`);
  }
  const status = getStatusCode(error);

  const statusCategory = status ? classifyByStatus(status, message) : null;
  const messageCategory = classifyByMessage(message);

  const category = statusCategory || messageCategory || ERROR_CATEGORIES.unknown;

  return {
    category,
    status,
    message,
    recovery: RECOVERY_ACTIONS[category] || RECOVERY_ACTIONS[ERROR_CATEGORIES.unknown],
  };
}

function suggestRecoveryAction(category) {
  return RECOVERY_ACTIONS[category] || RECOVERY_ACTIONS[ERROR_CATEGORIES.unknown];
}

module.exports = {
  ERROR_CATEGORIES,
  classifyError,
  suggestRecoveryAction,
};
