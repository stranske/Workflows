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

const { buildIgnoredPathMatchers, shouldIgnorePath } = require('./pr-context-graphql');

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

function buildMatchers({ ignoredPaths, ignoredPatterns } = {}) {
  const env = {
    PR_CONTEXT_IGNORED_PATHS: ignoredPaths && ignoredPaths.length ? ignoredPaths.join(',') : undefined,
    PR_CONTEXT_IGNORED_PATTERNS: ignoredPatterns && ignoredPatterns.length ? ignoredPatterns.join(',') : undefined,
  };
  return buildIgnoredPathMatchers(env);
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
  return (
    comment.created_at ||
    comment.createdAt ||
    comment.updated_at ||
    comment.updatedAt ||
    null
  );
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
  const withRetry = options.withRetry || ((fn) => fn());
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
      await withRetry(() =>
        github.rest.pulls.deleteReviewComment({
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
  const withRetry = options.withRetry || ((fn) => fn());
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

  const response = await withRetry(() =>
    github.rest.pulls.listReviewComments({
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

function runCli(env = process.env) {
  const comments = env.COMMENTS_JSON ? JSON.parse(env.COMMENTS_JSON) : [];
  const ignoredPaths = parseCsv(env.IGNORED_PATHS);
  const ignoredPatterns = parseCsv(env.IGNORED_PATTERNS);
  const botAuthors = parseCsv(env.BOT_AUTHORS);
  const maxAgeSeconds = env.MAX_AGE_SECONDS ? Number(env.MAX_AGE_SECONDS) : 30;
  const now = env.NOW_EPOCH_MS ? Number(env.NOW_EPOCH_MS) : undefined;

  const dismissable = collectDismissable(comments, {
    ignoredPaths,
    ignoredPatterns,
    botAuthors,
    maxAgeSeconds: Number.isFinite(maxAgeSeconds) ? maxAgeSeconds : null,
    now: Number.isFinite(now) ? now : undefined,
  });
  const logs = dismissable.map((entry) => formatDismissLog(entry));

  return { dismissable, logs };
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
  runCli,
};
