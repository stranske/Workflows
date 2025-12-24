// @ts-check
/**
 * Prompt Injection Guard
 *
 * Protects Codex agent workflows from prompt injection attacks by:
 * 1. Blocking forked PRs from triggering agent workflows
 * 2. Validating actors against allow-lists (users and bots)
 * 3. Scanning prompts for red-flag injection patterns
 * 4. Ensuring only repo collaborators can trigger sensitive automation
 */

'use strict';

// ---------------------------------------------------------------------------
// Configuration defaults
// ---------------------------------------------------------------------------

const DEFAULT_ALLOWED_BOTS = [
  'github-actions[bot]',
  'dependabot[bot]',
  'renovate[bot]',
];

// MINIMAL red-flag patterns - only catch OBVIOUS injection attempts
// Collaborators bypass content scanning entirely, so this only matters for forks/strangers
const DEFAULT_RED_FLAG_PATTERNS = [
  // Explicit injection attempts (very specific phrases)
  /ignore\s+all\s+previous\s+instructions/i,
  /disregard\s+all\s+previous/i,
  /system\s*:\s*you\s+are\s+now/i,

  // Actual leaked secrets (not the word "secret", but actual tokens)
  /\bghp_[A-Za-z0-9]{36}\b/, // GitHub personal access token
  /\bgho_[A-Za-z0-9]{36}\b/, // GitHub OAuth token  
  /\bghs_[A-Za-z0-9]{36}\b/, // GitHub app token
  /\bsk-[A-Za-z0-9]{48}\b/, // OpenAI API key pattern
];

// Label that bypasses security gate content scanning
const BYPASS_LABEL = 'security:bypass-guard';

// ---------------------------------------------------------------------------
// Fork detection
// ---------------------------------------------------------------------------

/**
 * Check if a PR is from a forked repository.
 * @param {object} pr - Pull request object from GitHub API
 * @returns {{ isFork: boolean, reason: string }}
 */
function detectFork(pr) {
  if (!pr || typeof pr !== 'object') {
    return { isFork: false, reason: 'invalid-pr-object' };
  }

  const head = pr.head || {};
  const base = pr.base || {};

  // Check if head repo is different from base repo
  if (head.repo && base.repo) {
    const headFullName = (head.repo.full_name || '').toLowerCase();
    const baseFullName = (base.repo.full_name || '').toLowerCase();

    if (headFullName && baseFullName && headFullName !== baseFullName) {
      return {
        isFork: true,
        reason: `PR head repo (${headFullName}) differs from base repo (${baseFullName})`,
      };
    }

    // Explicit fork flag
    if (head.repo.fork === true) {
      return {
        isFork: true,
        reason: `Head repository is explicitly marked as a fork`,
      };
    }
  }

  return { isFork: false, reason: '' };
}

// ---------------------------------------------------------------------------
// Actor validation
// ---------------------------------------------------------------------------

/**
 * Normalize a username for comparison.
 * @param {string} name
 * @returns {string}
 */
function normalizeUser(name) {
  return String(name || '').toLowerCase().trim();
}

/**
 * Check if an actor is in the allowed list.
 * @param {string} actor - The actor username
 * @param {object} options
 * @param {string[]} [options.allowedUsers] - Explicitly allowed users
 * @param {string[]} [options.allowedBots] - Explicitly allowed bots
 * @returns {{ allowed: boolean, reason: string }}
 */
function validateActorAllowList(actor, options = {}) {
  const normalizedActor = normalizeUser(actor);

  if (!normalizedActor) {
    return { allowed: false, reason: 'empty-actor' };
  }

  const allowedUsers = (options.allowedUsers || []).map(normalizeUser);
  const allowedBots = (options.allowedBots || DEFAULT_ALLOWED_BOTS).map(normalizeUser);

  // Check explicit user allow-list
  if (allowedUsers.length > 0 && allowedUsers.includes(normalizedActor)) {
    return { allowed: true, reason: 'user-allowlisted' };
  }

  // Check bot allow-list
  if (allowedBots.includes(normalizedActor)) {
    return { allowed: true, reason: 'bot-allowlisted' };
  }

  return {
    allowed: allowedUsers.length === 0, // If no allowlist, defer to collaborator check
    reason: allowedUsers.length === 0 ? 'no-allowlist-configured' : 'not-in-allowlist',
  };
}

/**
 * Check if an actor is a repository collaborator.
 * @param {object} params
 * @param {object} params.github - GitHub API client
 * @param {object} params.context - GitHub Actions context
 * @param {string} params.actor - The actor username
 * @returns {Promise<{ isCollaborator: boolean, permission: string, reason: string }>}
 */
async function checkCollaborator({ github, context, actor }) {
  if (!actor) {
    return { isCollaborator: false, permission: '', reason: 'empty-actor' };
  }

  try {
    const { data } = await github.rest.repos.getCollaboratorPermissionLevel({
      owner: context.repo.owner,
      repo: context.repo.repo,
      username: actor,
    });

    const permission = data.permission || '';
    const hasWriteAccess = ['admin', 'maintain', 'write'].includes(permission);

    return {
      isCollaborator: hasWriteAccess,
      permission,
      reason: hasWriteAccess ? 'collaborator-with-write-access' : `insufficient-permission-${permission}`,
    };
  } catch (error) {
    const status = error?.status || error?.response?.status;
    if (status === 404) {
      return { isCollaborator: false, permission: '', reason: 'not-a-collaborator' };
    }
    return { isCollaborator: false, permission: '', reason: `api-error-${error.message}` };
  }
}

// ---------------------------------------------------------------------------
// Red-flag content scanning
// ---------------------------------------------------------------------------

/**
 * Scan content for red-flag injection patterns.
 * @param {string} content - Content to scan
 * @param {object} [options]
 * @param {RegExp[]} [options.patterns] - Custom patterns to use
 * @param {RegExp[]} [options.additionalPatterns] - Additional patterns to add
 * @returns {{ flagged: boolean, matches: Array<{ pattern: string, match: string, index: number }> }}
 */
function scanForRedFlags(content, options = {}) {
  const text = String(content || '');
  const patterns = options.patterns || DEFAULT_RED_FLAG_PATTERNS;
  const additionalPatterns = options.additionalPatterns || [];
  const allPatterns = [...patterns, ...additionalPatterns];

  const matches = [];

  for (const pattern of allPatterns) {
    const match = text.match(pattern);
    if (match) {
      matches.push({
        pattern: pattern.source,
        match: match[0].substring(0, 100), // Truncate for safety
        index: match.index || 0,
      });
    }
  }

  return {
    flagged: matches.length > 0,
    matches,
  };
}

/**
 * Sanitize content by removing potentially dangerous patterns.
 * This creates a "clean" version for logging/display, not for execution.
 * @param {string} content
 * @returns {string}
 */
function sanitizeForDisplay(content) {
  let sanitized = String(content || '');

  // Remove HTML comments
  sanitized = sanitized.replace(/<!--[\s\S]*?-->/g, '[HTML_COMMENT_REMOVED]');

  // Remove zero-width characters
  sanitized = sanitized.replace(/[\u200B-\u200D\uFEFF\u2060-\u2064\u00AD]/g, '');

  // Mask potential secrets (simple patterns)
  sanitized = sanitized.replace(/\b(ghp_|gho_|ghs_|sk-)[A-Za-z0-9]{20,}/g, '[SECRET_MASKED]');

  // Truncate very long base64-like strings
  sanitized = sanitized.replace(/[A-Za-z0-9+/]{100,}={0,2}/g, '[BASE64_TRUNCATED]');

  return sanitized;
}

// ---------------------------------------------------------------------------
// Comprehensive guard evaluation
// ---------------------------------------------------------------------------

/**
 * Evaluate all prompt injection guards for a PR.
 * @param {object} params
 * @param {object} params.github - GitHub API client
 * @param {object} params.context - GitHub Actions context
 * @param {object} params.pr - Pull request object
 * @param {string} params.actor - The actor triggering the workflow
 * @param {string} [params.promptContent] - Optional prompt content to scan
 * @param {object} [params.config] - Configuration options
 * @param {string[]} [params.config.allowedUsers] - Explicitly allowed users
 * @param {string[]} [params.config.allowedBots] - Explicitly allowed bots
 * @param {boolean} [params.config.requireCollaborator] - Require collaborator status (default: true)
 * @param {boolean} [params.config.blockForks] - Block forked PRs (default: true)
 * @param {boolean} [params.config.scanContent] - Scan content for red flags (default: true)
 * @param {object} [params.core] - GitHub Actions core for logging
 * @returns {Promise<{
 *   allowed: boolean,
 *   blocked: boolean,
 *   reason: string,
 *   details: {
 *     fork: { isFork: boolean, reason: string },
 *     actor: { allowed: boolean, reason: string },
 *     collaborator: { isCollaborator: boolean, permission: string, reason: string },
 *     content: { flagged: boolean, matches: Array<{ pattern: string, match: string, index: number }> }
 *   }
 * }>}
 */
async function evaluatePromptInjectionGuard({
  github,
  context,
  pr,
  actor,
  promptContent = '',
  config = {},
  core,
}) {
  const blockForks = config.blockForks !== false;
  const requireCollaborator = config.requireCollaborator !== false;
  const scanContent = config.scanContent !== false;

  const details = {
    fork: { isFork: false, reason: '' },
    actor: { allowed: true, reason: '' },
    collaborator: { isCollaborator: false, permission: '', reason: '' },
    content: { flagged: false, matches: [] },
  };

  // 1. Fork detection
  if (blockForks && pr) {
    details.fork = detectFork(pr);
    if (details.fork.isFork) {
      if (core) core.warning(`Blocked: PR is from a fork - ${details.fork.reason}`);
      return {
        allowed: false,
        blocked: true,
        reason: 'fork-pr-blocked',
        details,
      };
    }
  }

  // 2. Actor allow-list check
  details.actor = validateActorAllowList(actor, {
    allowedUsers: config.allowedUsers,
    allowedBots: config.allowedBots,
  });

  // 3. Collaborator check (if required and not already allowed)
  if (requireCollaborator && !details.actor.allowed) {
    details.collaborator = await checkCollaborator({ github, context, actor });

    if (!details.collaborator.isCollaborator) {
      if (core) core.warning(`Blocked: Actor ${actor} is not a collaborator - ${details.collaborator.reason}`);
      return {
        allowed: false,
        blocked: true,
        reason: 'non-collaborator-blocked',
        details,
      };
    }
  }

  // 4. Check for bypass label
  const prLabels = (pr?.labels || []).map(l => (typeof l === 'string' ? l : l.name || '').toLowerCase());
  const hasBypassLabel = prLabels.includes(BYPASS_LABEL.toLowerCase());
  if (hasBypassLabel) {
    if (core) core.info(`Security gate bypassed via ${BYPASS_LABEL} label`);
    return {
      allowed: true,
      blocked: false,
      reason: 'bypass-label',
      details,
    };
  }

  // 5. Content red-flag scanning - SKIP for collaborators (they're trusted)
  const isCollaborator = details.actor.allowed || details.collaborator.isCollaborator;
  if (scanContent && promptContent && !isCollaborator) {
    details.content = scanForRedFlags(promptContent);

    if (details.content.flagged) {
      if (core) {
        core.warning(`Blocked: Prompt content contains red-flag patterns`);
        for (const match of details.content.matches) {
          core.warning(`  - Pattern: ${match.pattern.substring(0, 50)}... Match: ${match.match}`);
        }
      }
      return {
        allowed: false,
        blocked: true,
        reason: 'red-flag-content-detected',
        details,
      };
    }
  }

  // All checks passed
  const finalAllowed = details.actor.allowed || details.collaborator.isCollaborator;
  return {
    allowed: finalAllowed,
    blocked: !finalAllowed,
    reason: finalAllowed ? 'all-checks-passed' : 'actor-not-authorized',
    details,
  };
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = {
  // Core functions
  detectFork,
  validateActorAllowList,
  checkCollaborator,
  scanForRedFlags,
  sanitizeForDisplay,
  evaluatePromptInjectionGuard,

  // Constants for testing/customization
  DEFAULT_ALLOWED_BOTS,
  DEFAULT_RED_FLAG_PATTERNS,
  BYPASS_LABEL,
};
