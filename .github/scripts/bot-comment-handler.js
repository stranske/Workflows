'use strict';

const DEFAULT_PER_PAGE = 100;
const MAX_COMMENT_PAGES = 10;
const DEFAULT_BOT_AUTHORS = Object.freeze([
  'Copilot',
  'copilot[bot]',
  'github-actions[bot]',
  'coderabbitai[bot]',
  'chatgpt-codex-connector[bot]',
]);
const DEFAULT_AGENT = 'codex';
const DEFAULT_AGENT_WORKFLOW = 'reusable-codex-run.yml';
const DISPATCH_AGENT_ASSIGNEES = Object.freeze({
  codex: Object.freeze(['chatgpt-codex-connector']),
  claude: Object.freeze(['copilot']),
  gemini: Object.freeze(['copilot']),
});

function parseCommaList(value) {
  const rawItems = Array.isArray(value) ? value : String(value ?? '').split(',');
  return rawItems.map((item) => String(item ?? '').trim()).filter(Boolean);
}

function normalizeLogin(value) {
  return String(value ?? '').trim().toLowerCase();
}

function normalizeLabel(label) {
  if (typeof label === 'string') {
    return label.trim().toLowerCase();
  }
  if (label && typeof label === 'object' && typeof label.name === 'string') {
    return label.name.trim().toLowerCase();
  }
  return '';
}

function basename(value) {
  const text = String(value || '').trim();
  const parts = text.split('/').filter(Boolean);
  return parts.length ? parts[parts.length - 1] : text;
}

function resolveBotAuthors(input, { defaultAuthors = DEFAULT_BOT_AUTHORS } = {}) {
  const configured = parseCommaList(input);
  return configured.length ? configured : [...defaultAuthors];
}

function isBotAuthor(login, botAuthorsInput) {
  const allowed = new Set(resolveBotAuthors(botAuthorsInput).map(normalizeLogin));
  return allowed.has(normalizeLogin(login));
}

function isIgnoredPath(commentPath, ignoredPathsInput) {
  const path = String(commentPath || '');
  const ignoredPaths = parseCommaList(ignoredPathsInput);
  return ignoredPaths.some((prefix) => path.startsWith(prefix));
}

function collectUnresolvedBotComments(comments = [], options = {}) {
  const botAuthors = resolveBotAuthors(options.botAuthors ?? options.bot_authors);
  const skipIfHumanReplied = options.skipIfHumanReplied ?? options.skip_if_human_replied ?? true;
  const ignoredPaths = options.ignoredPaths ?? options.ignored_paths ?? '';
  const botComments = [];
  const processedThreads = new Set();

  for (const comment of Array.isArray(comments) ? comments : []) {
    const login = comment?.user?.login;
    if (!isBotAuthor(login, botAuthors)) {
      continue;
    }

    const commentPath = comment.path || '';
    if (isIgnoredPath(commentPath, ignoredPaths)) {
      continue;
    }

    const threadId = comment.in_reply_to_id || comment.id;
    if (processedThreads.has(threadId)) {
      continue;
    }

    if (skipIfHumanReplied) {
      const threadReplies = comments.filter((candidate) => {
        const inThread =
          candidate?.in_reply_to_id === comment.id || candidate?.in_reply_to_id === threadId;
        return inThread && !isBotAuthor(candidate?.user?.login, botAuthors);
      });
      if (threadReplies.length > 0) {
        processedThreads.add(threadId);
        continue;
      }
    }

    processedThreads.add(threadId);
    botComments.push({
      id: comment.id,
      path: comment.path,
      line: comment.line || comment.original_line,
      body: comment.body,
      author: login,
      url: comment.html_url,
      diff_hunk: comment.diff_hunk,
    });
  }

  return botComments;
}

function legacyAgentRoute(labels, defaults = {}) {
  const labelSet = new Set((Array.isArray(labels) ? labels : []).map(normalizeLabel).filter(Boolean));
  let agent = defaults.agent || DEFAULT_AGENT;
  let workflow = defaults.workflow || DEFAULT_AGENT_WORKFLOW;
  let mode = 'default';

  if (labelSet.has('agent:claude')) {
    agent = 'claude';
    workflow = 'reusable-claude-run.yml';
    mode = 'explicit';
  } else if (labelSet.has('agent:gemini')) {
    agent = 'gemini';
    workflow = 'reusable-gemini-run.yml';
    mode = 'explicit';
  } else if (labelSet.has('agent:codex')) {
    agent = 'codex';
    workflow = 'reusable-codex-run.yml';
    mode = 'explicit';
  }

  return { agent, workflow, mode };
}

function resolveBotCommentAgent(labels = [], options = {}) {
  let defaultAgent = options.defaultAgent || DEFAULT_AGENT;
  let defaultWorkflow = options.defaultWorkflow || DEFAULT_AGENT_WORKFLOW;
  const registryPath = options.registryPath;

  try {
    const { loadAgentRegistry, getRunnerWorkflow } = require('./agent_registry.js');
    defaultAgent = options.defaultAgent || loadAgentRegistry({ registryPath }).default_agent || DEFAULT_AGENT;
    defaultWorkflow = basename(getRunnerWorkflow(defaultAgent, { registryPath })) || defaultWorkflow;
  } catch (_) {
    // Preserve the workflow's legacy default when the registry is unavailable.
  }

  try {
    const { resolveAgentRoutingFromLabels, getRunnerWorkflow } = require('./agent_registry.js');
    const routing = resolveAgentRoutingFromLabels(labels, { registryPath });
    const workflow = basename(getRunnerWorkflow(routing.agentKey, { registryPath })) || defaultWorkflow;
    return {
      agent: routing.agentKey,
      workflow,
      mode: routing.mode,
      requested: routing.requested,
      source: 'registry',
    };
  } catch (error) {
    return {
      ...legacyAgentRoute(labels, { agent: defaultAgent, workflow: defaultWorkflow }),
      requested: null,
      source: 'legacy-fallback',
      registry_error: error?.message || String(error),
    };
  }
}

function buildBotCommentsPrompt(comments = []) {
  const lines = [
    '# Fix Bot Review Comments',
    '',
    'Review bots have left suggestions on this PR. Address each one:',
    '',
    '## Instructions',
    '',
    '1. Read each bot comment below',
    '2. Implement the suggested fix if it improves the code',
    "3. If a suggestion is incorrect or doesn't apply, skip it and note why",
    '4. After fixing, summarize what you addressed in your commit message',
    '',
    '## Bot Comments to Address',
    '',
  ];

  for (const comment of Array.isArray(comments) ? comments : []) {
    lines.push(
      `### ${comment.path}:${comment.line ?? 'N/A'}`,
      '',
      `**From:** ${comment.author}`,
      '',
      '```',
      String(comment.body ?? ''),
      '```',
      '',
      '**Context (diff hunk):**',
      '```diff',
      String(comment.diff_hunk ?? ''),
      '```',
      '',
      '---',
      '',
    );
  }

  lines.push(
    '## After Addressing Comments',
    '',
    '- Commit your changes with message: "fix: address bot review comments"',
    '- Include which suggestions you addressed vs skipped in the commit message',
    '',
  );

  return lines.join('\n');
}

function getBotCommentAssignees(agent) {
  const key = String(agent || DEFAULT_AGENT).trim().toLowerCase();
  return [...(DISPATCH_AGENT_ASSIGNEES[key] || DISPATCH_AGENT_ASSIGNEES[DEFAULT_AGENT])];
}

function buildBotCommentDispatchComment({ agent = DEFAULT_AGENT, count = 0 } = {}) {
  const marker = '<!-- bot-comment-handler -->';
  return [
    marker,
    '## \u{1F916} Bot Comment Handler',
    '',
    `- Agent: ${agent}`,
    `- Bot comments to address: ${count}`,
    '',
    'The agent has been assigned to this PR to address the bot review comments.',
    '',
    '### Instructions for agent',
    '1. Implement suggested fixes that improve the code',
    "2. Skip suggestions that don't apply (note why in your response)",
    '',
    'The bot comment handler workflow has prepared context in the artifacts.',
  ].join('\n');
}

function normalizeTerminalDispositionRecord(input) {
  try {
    const { normalizeTerminalDisposition } = require('./terminal_disposition.js');
    return normalizeTerminalDisposition(input);
  } catch (_) {
    return input;
  }
}

function buildReviewThreadTerminalDisposition(options = {}) {
  const prNumber = options.prNumber ?? options.pr_number;
  const found = Boolean(options.found ?? options.commentsFound ?? options.comments_found);
  return normalizeTerminalDispositionRecord({
    source_type: 'review-thread',
    source_id: prNumber,
    pr_number: prNumber,
    disposition: found ? 'unresolved-bot-comments' : 'no-unresolved-bot-comments',
    reason: found
      ? 'Bot review comments remain unresolved and agent handling is eligible.'
      : 'No unresolved bot review comments matched the handler filters.',
    workflow: options.workflow,
    run_id: options.runId ?? options.run_id,
    run_attempt: options.runAttempt ?? options.run_attempt,
    artifact_name: options.artifactName ?? options.artifact_name,
    artifact_family: options.artifactFamily ?? options.artifact_family,
    actor: options.actor,
  });
}

function buildWrapperTerminalDisposition(options = {}) {
  const env = options.env || process.env;
  const reusableExpected = Boolean(
    options.reusableExpected ?? options.reusable_invocation_expected,
  );
  const prNumber = Number.parseInt(String(options.prNumber ?? options.pr_number ?? ''), 10) || null;
  const runId = String(options.runId ?? options.run_id ?? env.GITHUB_RUN_ID ?? '');
  return normalizeTerminalDispositionRecord({
    source_type: 'review-thread',
    source_id: prNumber || runId || 'unknown',
    pr_number: prNumber,
    disposition: reusableExpected ? 'reusable-invocation-expected' : 'wrapper-skipped',
    reason: reusableExpected
      ? 'Wrapper resolved an eligible PR and invoked the reusable bot-comment handler.'
      : (options.skipReason ?? options.skip_reason ?? 'Wrapper did not find eligible bot-comment work.'),
    workflow: options.workflow ?? env.GITHUB_WORKFLOW ?? '',
    run_id: runId,
    run_attempt: options.runAttempt ?? options.run_attempt ?? env.GITHUB_RUN_ATTEMPT ?? '',
    artifact_name:
      options.artifactName ?? options.artifact_name ?? `review-thread-terminal-disposition-${runId}`,
    artifact_family: options.artifactFamily ?? options.artifact_family ?? 'review-thread-terminal-disposition',
    actor: options.actor ?? env.GITHUB_ACTOR ?? '',
    needs_human: false,
    dispatch_outcome: reusableExpected ? 'reusable-expected' : 'wrapper-skipped',
  });
}

/**
 * List PR/issue comments with a hard pagination upper bound.
 *
 * Callers should pass a `listFn` obtained via createTokenAwareRetry
 * (from github-api-with-retry.js) so that every page request gets
 * automatic token rotation and rate-limit back-off.
 *
 * @param {object} options
 * @param {string} options.owner - Repository owner.
 * @param {string} options.repo  - Repository name.
 * @param {number} options.issueNumber - PR or issue number.
 * @param {function} options.listFn - Paginated list function (required).
 * @param {number} [options.perPage=100]  - Items per page.
 * @param {number} [options.maxPages=10]  - Hard upper bound on pages fetched.
 * @returns {Promise<object[]>} Collected comments.
 */
async function listCommentsWithLimit(options = {}) {
  const owner = options.owner;
  const repo = options.repo;
  const issueNumber = options.issueNumber;
  const perPage =
    typeof options.perPage === 'number' && Number.isFinite(options.perPage)
      ? options.perPage
      : DEFAULT_PER_PAGE;
  const maxPages =
    typeof options.maxPages === 'number' && Number.isFinite(options.maxPages)
      ? options.maxPages
      : MAX_COMMENT_PAGES;
  const listFn = options.listFn;

  if (!listFn) {
    throw new Error('listFn is required (use createTokenAwareRetry to wrap the API client)');
  }
  if (!owner || !repo) {
    throw new Error('owner and repo are required');
  }
  if (!issueNumber) {
    throw new Error('issueNumber is required');
  }

  const comments = [];
  for (let page = 1; page <= maxPages; page += 1) {
    const response = await listFn({
      owner,
      repo,
      issue_number: issueNumber,
      per_page: perPage,
      page,
    });
    const pageData = Array.isArray(response?.data) ? response.data : response || [];
    comments.push(...pageData);
    if (pageData.length < perPage) {
      break;
    }
  }

  return comments;
}

module.exports = {
  DEFAULT_PER_PAGE,
  MAX_COMMENT_PAGES,
  DEFAULT_BOT_AUTHORS,
  DISPATCH_AGENT_ASSIGNEES,
  buildBotCommentDispatchComment,
  buildBotCommentsPrompt,
  buildReviewThreadTerminalDisposition,
  buildWrapperTerminalDisposition,
  collectUnresolvedBotComments,
  getBotCommentAssignees,
  isBotAuthor,
  isIgnoredPath,
  listCommentsWithLimit,
  parseCommaList,
  resolveBotAuthors,
  resolveBotCommentAgent,
};
