'use strict';

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

function collectDismissable(comments, options = {}) {
  const botAuthors = normalizeAuthors(options.botAuthors);
  const matchers = buildMatchers({
    ignoredPaths: options.ignoredPaths,
    ignoredPatterns: options.ignoredPatterns,
  });

  const dismissable = [];

  for (const comment of comments || []) {
    if (!isBotAuthor(comment, botAuthors)) {
      continue;
    }
    const commentPath = comment.path || '';
    if (!shouldIgnorePath(commentPath, matchers)) {
      continue;
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

function runCli(env = process.env) {
  const comments = env.COMMENTS_JSON ? JSON.parse(env.COMMENTS_JSON) : [];
  const ignoredPaths = parseCsv(env.IGNORED_PATHS);
  const ignoredPatterns = parseCsv(env.IGNORED_PATTERNS);
  const botAuthors = parseCsv(env.BOT_AUTHORS);

  const dismissable = collectDismissable(comments, {
    ignoredPaths,
    ignoredPatterns,
    botAuthors,
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
  formatDismissLog,
  runCli,
};
