'use strict';

/**
 * Bot Comment Dismiss - Auto-dismiss ignored bot review comments
 *
 * Dismisses review comments from bots (Copilot, CodeRabbit, etc.) on files
 * that should be ignored (e.g., .agents/ ledgers).
 *
 * API Wrapper: Use createTokenAwareRetry from github-api-with-retry.js
 * to create the withRetry function passed to these functions.
 * 
 * Example:
 *   const { createTokenAwareRetry } = require('./github-api-with-retry.js');
 *   const { withRetry } = await createTokenAwareRetry({ github, core });
 *   await autoDismissReviewComments({ github, withRetry, ... });
 */

const { minimatch } = require('minimatch');

const DEFAULT_IGNORED_PATTERNS = ['.agents/**'];
const DEFAULT_MAX_AGE_SECONDS = 30;

function parseCsv(value) {
  if (!value) {
    return [];
  }
  return String(value)
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function normalizeAuthors(authors) {
  return new Set((authors || []).map((author) => String(author || '').toLowerCase()).filter(Boolean));
}

function normalizePath(value) {
  return String(value || '').replace(/\\/g, '/').toLowerCase();
}

function normalizePattern(value) {
  const raw = String(value || '');
  if (!raw) {
    return null;
  }
  let normalized = '';
  for (let i = 0; i < raw.length; i += 1) {
    const char = raw[i];
    if (char === '\\') {
      const next = raw[i + 1];
      if (next && /[\\*?[\]{}()]/.test(next)) {
        normalized += `\\${next}`;
        i += 1;
        continue;
      }
      normalized += '/';
      continue;
    }
    normalized += char;
  }
  normalized = normalized.toLowerCase();
  if (normalized.endsWith('/')) {
    return `${normalized}**`;
  }
  return normalized;
}

function buildMatchers({ ignoredPaths, ignoredPatterns } = {}) {
  const patterns = [];
  for (const entry of ignoredPaths || []) {
    const normalized = normalizePattern(entry);
    if (normalized) {
      patterns.push(normalized);
    }
  }
  for (const entry of ignoredPatterns || []) {
    const normalized = normalizePattern(entry);
    if (normalized) {
      patterns.push(normalized);
    }
  }
  if (!patterns.length) {
    patterns.push(...DEFAULT_IGNORED_PATTERNS);
  }
  return patterns;
}

function shouldIgnorePath(filename, matchers) {
  const normalized = normalizePath(filename);
  if (!normalized) {
    return false;
  }
  return matchers.some((pattern) =>
    minimatch(normalized, pattern, { dot: true, nocomment: true, nonegate: true })
  );
}

function isBotAuthor(comment, botAuthors) {
  if (!comment || !comment.user || !comment.user.login) {
    return false;
  }
  return botAuthors.has(String(comment.user.login).toLowerCase());
}

function resolveCommentTimestamp(comment) {
  if (!comment) {
    return null;
  }
  return comment.updated_at || comment.updatedAt || comment.created_at || comment.createdAt || null;
}

function getArgValue(argv, name) {
  if (!Array.isArray(argv)) {
    return undefined;
  }
  for (let i = 0; i < argv.length; i += 1) {
    const entry = argv[i];
    if (entry === name) {
      if (i + 1 >= argv.length) {
        return null;
      }
      return argv[i + 1];
    }
    if (typeof entry === 'string' && entry.startsWith(`${name}=`)) {
      return entry.slice(name.length + 1);
    }
  }
  return undefined;
}

function parsePositiveInt(value, label) {
  const numberValue = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numberValue) || !Number.isInteger(numberValue) || numberValue <= 0) {
    throw new Error(`${label} must be a positive integer`);
  }
  return numberValue;
}

function parseMaxAgeSeconds({ argv, env, defaultValue = DEFAULT_MAX_AGE_SECONDS } = {}) {
  const cliValue = getArgValue(argv, '--maxAgeSeconds');
  const envValue = env ? env.MAX_AGE_SECONDS : undefined;
  let rawValue = defaultValue;

  if (cliValue !== undefined) {
    if (cliValue === null) {
      throw new Error('maxAgeSeconds must be a positive integer');
    }
    rawValue = cliValue;
  } else if (envValue !== undefined) {
    rawValue = envValue;
  }

  return parsePositiveInt(rawValue, 'maxAgeSeconds');
}

function collectDismissable(comments, options = {}) {
  const botAuthors = normalizeAuthors(options.botAuthors);
  const matchers = buildMatchers({
    ignoredPaths: options.ignoredPaths,
    ignoredPatterns: options.ignoredPatterns,
  });
  const maxAgeSeconds =
    typeof options.maxAgeSeconds === 'number' && Number.isFinite(options.maxAgeSeconds)
      ? options.maxAgeSeconds
      : null;
  const now = typeof options.now === 'number' && Number.isFinite(options.now) ? options.now : Date.now();

  const dismissable = [];

  for (const comment of comments || []) {
    if (!isBotAuthor(comment, botAuthors)) {
      continue;
    }
    const commentPath = comment.path || '';
    if (!shouldIgnorePath(commentPath, matchers)) {
      continue;
    }
    if (maxAgeSeconds !== null) {
      const timestamp = resolveCommentTimestamp(comment);
      const createdAt = timestamp ? Date.parse(timestamp) : NaN;
      if (!Number.isFinite(createdAt)) {
        continue;
      }
      const ageSeconds = (now - createdAt) / 1000;
      if (ageSeconds > maxAgeSeconds) {
        continue;
      }
    }
    dismissable.push({
      id: comment.id,
      path: comment.path,
      author: comment.user.login,
    });
  }

  return dismissable;
}

function formatDismissLog(entry) {
  const path = entry.path || 'unknown-path';
  const author = entry.author || 'unknown-author';
  return `Auto-dismissed review comment ${entry.id} by ${author} in ${path}`;
}

async function dismissReviewComments(options = {}) {
  const github = options.github;
  const dismissable = options.dismissable || [];
  const owner = options.owner;
  const repo = options.repo;
  const withRetry = options.withRetry || ((fn) => fn(github));
  const logger = options.logger || console;

  if (!github || !github.rest || !github.rest.pulls) {
    throw new Error('github client missing rest.pulls');
  }
  if (!owner || !repo) {
    throw new Error('owner and repo are required');
  }

  const dismissed = [];
  const failed = [];
  const logs = [];

  for (const entry of dismissable) {
    try {
      await withRetry((client) =>
        client.rest.pulls.deleteReviewComment({
          owner,
          repo,
          comment_id: entry.id,
        })
      );
      dismissed.push(entry);
      const logLine = formatDismissLog(entry);
      logs.push(logLine);
      if (logger && typeof logger.info === 'function') {
        logger.info(logLine);
      } else if (logger && typeof logger.log === 'function') {
        logger.log(logLine);
      }
    } catch (error) {
      failed.push({
        ...entry,
        error: error ? String(error.message || error) : 'unknown error',
      });
      if (logger && typeof logger.warning === 'function') {
        logger.warning(`Failed to dismiss review comment ${entry.id}: ${error?.message || error}`);
      } else if (logger && typeof logger.warn === 'function') {
        logger.warn(`Failed to dismiss review comment ${entry.id}: ${error?.message || error}`);
      }
    }
  }

  return { dismissed, failed, logs };
}

async function autoDismissReviewComments(options = {}) {
  const github = options.github;
  const owner = options.owner;
  const repo = options.repo;
  const pullNumber = options.pullNumber;
  const withRetry = options.withRetry || ((fn) => fn(github));
  const logger = options.logger || console;

  if (!github || !github.rest || !github.rest.pulls) {
    throw new Error('github client missing rest.pulls');
  }
  if (!owner || !repo) {
    throw new Error('owner and repo are required');
  }
  if (!pullNumber) {
    throw new Error('pullNumber is required');
  }

  const response = await withRetry((client) =>
    client.rest.pulls.listReviewComments({
      owner,
      repo,
      pull_number: pullNumber,
      per_page: 100,
    })
  );
  const comments = Array.isArray(response?.data) ? response.data : response || [];

  const dismissable = collectDismissable(comments, {
    ignoredPaths: options.ignoredPaths,
    ignoredPatterns: options.ignoredPatterns,
    botAuthors: options.botAuthors,
    maxAgeSeconds:
      typeof options.maxAgeSeconds === 'number' && Number.isFinite(options.maxAgeSeconds)
        ? options.maxAgeSeconds
        : null,
    now: options.now,
  });

  const result = await dismissReviewComments({
    github,
    owner,
    repo,
    dismissable,
    withRetry,
    logger,
  });

  return { dismissable, ...result };
}

function runCli(env = process.env, argv = process.argv.slice(2)) {
  const comments = env.COMMENTS_JSON ? JSON.parse(env.COMMENTS_JSON) : [];
  const ignoredPaths = parseCsv(env.IGNORED_PATHS);
  const ignoredPatterns = parseCsv(env.IGNORED_PATTERNS);
  const botAuthors = parseCsv(env.BOT_AUTHORS);
  const maxAgeSeconds = parseMaxAgeSeconds({ argv, env });
  const now = env.NOW_EPOCH_MS ? Number(env.NOW_EPOCH_MS) : undefined;

  const dismissable = collectDismissable(comments, {
    ignoredPaths,
    ignoredPatterns,
    botAuthors,
    maxAgeSeconds,
    now: Number.isFinite(now) ? now : undefined,
  });
  const logs = dismissable.map((entry) => formatDismissLog(entry));

  return { dismissable, logs, maxAgeSeconds };
}

if (require.main === module) {
  const result = runCli();
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

module.exports = {
  collectDismissable,
  autoDismissReviewComments,
  dismissReviewComments,
  formatDismissLog,
  parseMaxAgeSeconds,
  runCli,
};
