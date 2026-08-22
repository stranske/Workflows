'use strict';

const DEFAULT_PER_PAGE = 100;
const MAX_COMMENT_PAGES = 10;
const MAX_CONTROLLER_COMMENT_LENGTH = 60000;
const MAX_COLLECTED_COMMENT_OUTPUT_LENGTH = 450000;
const DEFAULT_BOT_AUTHORS = Object.freeze([
  'copilot[bot]',
  'github-actions[bot]',
  'coderabbitai[bot]',
  'chatgpt-codex-connector',
  'chatgpt-codex-connector[bot]',
]);
const DEFAULT_AGENT = 'codex';
const DEFAULT_AGENT_WORKFLOW = 'reusable-codex-run.yml';
const DISPATCH_AGENT_ASSIGNEES = Object.freeze({
  codex: Object.freeze(['chatgpt-codex-connector']),
  claude: Object.freeze(['stranske-automation-bot']),
  gemini: Object.freeze(['stranske-automation-bot']),
});

function parseCommaList(value) {
  const rawItems = Array.isArray(value) ? value : String(value ?? '').split(',');
  return rawItems.map((item) => String(item ?? '').trim()).filter(Boolean);
}

function normalizeLogin(value) {
  return String(value ?? '').trim().toLowerCase();
}

function normalizeBoolean(value, defaultValue = false) {
  if (typeof value === 'boolean') {
    return value;
  }
  if (value === undefined || value === null || value === '') {
    return defaultValue;
  }
  const normalized = String(value).trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(normalized)) {
    return true;
  }
  if (['0', 'false', 'no', 'off'].includes(normalized)) {
    return false;
  }
  return defaultValue;
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

function resolveBotAuthorSet(input, options = {}) {
  if (input instanceof Set) {
    return input;
  }
  return new Set(resolveBotAuthors(input, options).map(normalizeLogin));
}

function isBotAuthor(login, botAuthorsInput) {
  const allowed = resolveBotAuthorSet(botAuthorsInput);
  return allowed.has(normalizeLogin(login));
}

function isIgnoredPath(commentPath, ignoredPathsInput) {
  const path = String(commentPath || '');
  const ignoredPaths = parseCommaList(ignoredPathsInput);
  return ignoredPaths.some((prefix) => path.startsWith(prefix));
}

function collectUnresolvedBotComments(comments = [], options = {}) {
  const botAuthors = resolveBotAuthorSet(options.botAuthors ?? options.bot_authors);
  const skipIfHumanReplied = normalizeBoolean(
    options.skipIfHumanReplied ?? options.skip_if_human_replied,
    true,
  );
  const ignoredPaths = options.ignoredPaths ?? options.ignored_paths ?? '';
  const botComments = [];
  const processedThreads = new Set();
  const byId = new Map();
  const allComments = Array.isArray(comments) ? comments : [];
  for (const comment of Array.isArray(comments) ? comments : []) {
    if (comment?.id !== undefined && comment?.id !== null) {
      byId.set(comment.id, comment);
    }
  }

  function rootThreadId(comment) {
    let current = comment;
    const seen = new Set();
    while (current?.in_reply_to_id && !seen.has(current.id)) {
      seen.add(current.id);
      const parent = byId.get(current.in_reply_to_id);
      if (!parent) {
        return current.in_reply_to_id;
      }
      current = parent;
    }
    return current?.id ?? comment?.id;
  }

  const humanReplyByThread = new Map();
  if (skipIfHumanReplied) {
    for (const comment of allComments) {
      if (isBotAuthor(comment?.user?.login, botAuthors)) {
        continue;
      }
      const threadId = rootThreadId(comment);
      if (threadId !== comment?.id) {
        humanReplyByThread.set(threadId, true);
      }
    }
  }

  for (const comment of allComments) {
    const login = comment?.user?.login;
    if (!isBotAuthor(login, botAuthors)) {
      continue;
    }

    const commentPath = comment.path || '';
    if (isIgnoredPath(commentPath, ignoredPaths)) {
      continue;
    }

    const threadId = rootThreadId(comment);
    if (processedThreads.has(threadId)) {
      continue;
    }

    if (humanReplyByThread.get(threadId)) {
      processedThreads.add(threadId);
      continue;
    }

    processedThreads.add(threadId);
    botComments.push({
      id: comment.id,
      path: comment.path,
      line: comment.line ?? comment.original_line,
      body: comment.body,
      author: login,
      url: comment.html_url,
      diff_hunk: comment.diff_hunk,
    });
  }

  return botComments;
}

function fitJsonStringBudget(value, encodedBudget, maxChars) {
  const raw = String(value ?? '');
  if (encodedBudget <= 0 || maxChars <= 0 || !raw) {
    return '';
  }
  const bounded = raw.length > maxChars ? `${raw.slice(0, Math.max(0, maxChars - 3))}...` : raw;
  const encodedLength = (candidate) => JSON.stringify(candidate).length - 2;
  if (encodedLength(bounded) <= encodedBudget) {
    return bounded;
  }
  let low = 0;
  let high = Math.min(raw.length, maxChars);
  let result = '';
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const candidate = middle < raw.length ? `${raw.slice(0, Math.max(0, middle - 3))}...` : raw;
    if (encodedLength(candidate) <= encodedBudget) {
      result = candidate;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return result;
}

function boundBotReviewThreadPayload(
  comments = [],
  maxLength = MAX_COLLECTED_COMMENT_OUTPUT_LENGTH,
) {
  const safeMaxLength = Math.min(
    MAX_COLLECTED_COMMENT_OUTPUT_LENGTH,
    Math.max(4000, Number.parseInt(maxLength, 10) || MAX_COLLECTED_COMMENT_OUTPUT_LENGTH),
  );
  const textFields = [];
  const bounded = (Array.isArray(comments) ? comments : []).map((comment) => {
    const result = {
      id: boundControllerField(comment?.id, 200),
      thread_id: boundControllerField(comment?.thread_id, 200),
      path: boundControllerField(comment?.path, 500),
      line: comment?.line ?? null,
      body: '',
      author: boundControllerField(comment?.author, 200),
      url: boundControllerField(comment?.url, 1000),
      diff_hunk: '',
      replies: (Array.isArray(comment?.replies) ? comment.replies : []).map((reply) => ({
        author: boundControllerField(reply?.author, 200),
        body: '',
        url: boundControllerField(reply?.url, 1000),
      })),
    };
    textFields.push({ target: result, key: 'body', value: comment?.body, maxChars: 4000 });
    textFields.push({
      target: result,
      key: 'diff_hunk',
      value: comment?.diff_hunk,
      maxChars: 4000,
    });
    result.replies.forEach((reply, index) => {
      textFields.push({
        target: reply,
        key: 'body',
        value: comment.replies[index]?.body,
        maxChars: 2000,
      });
    });
    return result;
  });

  const metadataLength = JSON.stringify(bounded).length;
  if (metadataLength > safeMaxLength) {
    throw new Error(
      `Bot review-thread metadata exceeds the ${safeMaxLength}-character job-output budget`,
    );
  }
  let remaining = safeMaxLength - metadataLength;
  textFields.forEach((field, index) => {
    const remainingFields = textFields.length - index;
    const share = Math.floor(remaining / remainingFields);
    const value = fitJsonStringBudget(field.value, share, field.maxChars);
    field.target[field.key] = value;
    remaining -= JSON.stringify(value).length - 2;
  });
  if (JSON.stringify(bounded).length > safeMaxLength) {
    throw new Error(`Bot review-thread payload exceeds ${safeMaxLength} characters`);
  }
  return bounded;
}

function collectActiveBotReviewThreads(reviewThreads = [], options = {}) {
  const botAuthors = resolveBotAuthorSet(options.botAuthors ?? options.bot_authors);
  const skipIfHumanReplied = normalizeBoolean(
    options.skipIfHumanReplied ?? options.skip_if_human_replied,
    false,
  );
  const ignoredPaths = options.ignoredPaths ?? options.ignored_paths ?? '';
  const active = [];

  for (const thread of Array.isArray(reviewThreads) ? reviewThreads : []) {
    if (!thread || thread.isResolved || thread.isOutdated) {
      continue;
    }
    const comments = Array.isArray(thread.comments?.nodes)
      ? thread.comments.nodes
      : Array.isArray(thread.comments)
        ? thread.comments
        : [];
    const root = comments[0];
    const rootLogin = root?.author?.login ?? root?.user?.login;
    if (!root || !isBotAuthor(rootLogin, botAuthors)) {
      continue;
    }
    const path = thread.path || root.path || '';
    if (isIgnoredPath(path, ignoredPaths)) {
      continue;
    }
    const replies = comments.slice(1);
    if (
      skipIfHumanReplied
      && replies.some((comment) => !isBotAuthor(comment?.author?.login ?? comment?.user?.login, botAuthors))
    ) {
      continue;
    }
    active.push({
      id: root.databaseId ?? root.id,
      thread_id: thread.id,
      path,
      line: thread.line ?? root.line ?? root.originalLine ?? root.original_line,
      body: root.body,
      author: rootLogin,
      url: root.url ?? root.html_url,
      diff_hunk: root.diffHunk ?? root.diff_hunk,
      replies: replies.map((comment) => ({
        author: comment?.author?.login ?? comment?.user?.login ?? '',
        body: comment?.body ?? '',
        url: comment?.url ?? comment?.html_url ?? '',
      })),
    });
  }

  return boundBotReviewThreadPayload(active, options.maxOutputLength ?? options.max_output_length);
}

function markdownFenceFor(text, info = '') {
  const body = String(text ?? '');
  let fence = '```';
  while (body.includes(fence)) {
    fence += '`';
  }
  return `${fence}${info}\n${body}\n${fence}`;
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
    defaultAgent = options.defaultAgent || loadAgentRegistry(registryPath).default_agent || DEFAULT_AGENT;
    defaultWorkflow = basename(getRunnerWorkflow(defaultAgent, registryPath)) || defaultWorkflow;
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

function buildBotCommentsPrompt(comments = [], options = {}) {
  const headSha = String(options.headSha ?? options.head_sha ?? '').trim();
  const lines = [
    '# Fix Bot Review Comments',
    '',
    'Review bots have left active, non-outdated suggestions on this PR. Address each one:',
    '',
    ...(headSha ? [`**Exact PR head:** \`${headSha}\``, ''] : []),
    '## Instructions',
    '',
    '1. Re-read the exact PR head and every active thread below',
    '2. Implement every still-valid acceptance criterion and run deterministic validation',
    '3. If a criterion is already satisfied or invalid, make no no-op edit; ' +
      'explain the evidence in that thread',
    '4. Reply in each thread with the exact head and validation, then request ' +
      'a thread-specific reviewer disposition',
    '5. Never self-resolve a reviewer thread',
    '6. A generic top-level review or "no issues" comment is not completion ' +
      'while any listed thread remains active',
    '',
    '## Bot Comments to Address',
    '',
  ];

  for (const comment of Array.isArray(comments) ? comments : []) {
    lines.push(
      `### ${comment.thread_id || comment.id || 'unknown-thread'} — ` +
        `${comment.path}:${comment.line ?? 'N/A'}`,
      '',
      `**From:** ${comment.author}`,
      `**Thread:** ${comment.url || 'unavailable'}`,
      '',
      markdownFenceFor(comment.body),
      '',
      '**Context (diff hunk):**',
      markdownFenceFor(comment.diff_hunk, 'diff'),
      '',
    );
    if (Array.isArray(comment.replies) && comment.replies.length > 0) {
      lines.push('**Thread replies:**', '');
      comment.replies.forEach((reply) => {
        lines.push(
          `- **${reply.author || 'unknown'}** — ${reply.url || 'URL unavailable'}`,
          markdownFenceFor(reply.body),
          '',
        );
      });
    }
    lines.push('---', '');
  }

  lines.push(
    '## After Addressing Comments',
    '',
    '- Commit real changes with message: "fix: address bot review comments"',
    '- Include which thread IDs you fixed versus dispositioned and the validation evidence',
    '- Re-query the exact head and active review-thread set before reporting completion',
    '- If any listed thread remains active, report its exact ID and next authority; do not claim completion',
    '',
  );

  return lines.join('\n');
}

function getBotCommentAssignees(agent) {
  const key = String(agent || DEFAULT_AGENT).trim().toLowerCase();
  try {
    const { getAgentConfig } = require('./agent_registry.js');
    const config = getAgentConfig(key);
    const candidates = [
      config?.preflight?.assign_user,
      ...(Array.isArray(config?.readiness_candidates) ? config.readiness_candidates : []),
      ...(Array.isArray(config?.automation_logins) ? config.automation_logins : []),
    ].filter(Boolean);
    if (candidates.length) {
      return [String(candidates[0]).trim()].filter(Boolean);
    }
  } catch (_) {
    // Fall back to the legacy map when the registry is unavailable.
  }
  return [...(DISPATCH_AGENT_ASSIGNEES[key] || DISPATCH_AGENT_ASSIGNEES[DEFAULT_AGENT])];
}

function boundControllerField(value, limit) {
  const normalized = String(value ?? '').trim().replace(/\s+/g, ' ');
  return normalized.length > limit ? `${normalized.slice(0, limit - 3)}...` : normalized;
}

function buildBotCommentDispatchComments({
  agent = DEFAULT_AGENT,
  count = 0,
  comments = [],
  headSha = '',
  maxLength = MAX_CONTROLLER_COMMENT_LENGTH,
} = {}) {
  const marker = '<!-- bot-comment-handler -->';
  const safeMaxLength = Math.min(
    65000,
    Math.max(4000, Number.parseInt(maxLength, 10) || MAX_CONTROLLER_COMMENT_LENGTH),
  );
  const entries = (Array.isArray(comments) ? comments : []).map((comment) => [
    `- ${boundControllerField(comment?.thread_id || comment?.id || 'unknown-thread', 200)} — ` +
      `${boundControllerField(comment?.path || 'unknown', 260)}:${comment?.line ?? 'N/A'}`,
    `  - ${boundControllerField(comment?.url || 'URL unavailable', 500)}`,
    `  - Acceptance criterion: ${boundControllerField(comment?.body, 350) || 'No text supplied'}`,
  ].join('\n'));
  const headerReserve = 1400;
  const entryBudget = safeMaxLength - headerReserve;
  const pages = [[]];
  let pageLength = 0;
  for (const entry of entries) {
    if (pages.at(-1).length > 0 && pageLength + entry.length + 2 > entryBudget) {
      pages.push([]);
      pageLength = 0;
    }
    pages.at(-1).push(entry);
    pageLength += entry.length + 2;
  }
  const total = pages.length;
  return pages.map((page, index) => {
    const lines = [
      marker,
      `<!-- bot-comment-handler-part:${index + 1}/${total} -->`,
      '## \u{1F916} Bot Comment Handler',
      '',
      `- Agent: ${boundControllerField(agent, 100)}`,
      `- Bot comments to address: ${boundControllerField(count, 20)}`,
      `- Exact PR head: ${boundControllerField(headSha, 100) || 'unavailable'}`,
      `- Controller part: ${index + 1} of ${total}`,
      '',
      'The agent is reassigned only after every controller part is durable on the PR.',
      'Each entry links to the authoritative review thread containing its full context.',
      '',
      '### Active thread controller',
      '',
      ...page.flatMap((entry) => [entry, '']),
      '### Required outcome',
      '1. Inspect every listed active thread on the exact head.',
      '2. Implement and validate any still-valid criterion; do not make no-op edits.',
      '3. Reply with exact-head evidence and request a thread-specific reviewer disposition.',
      '4. Never self-resolve reviewer threads.',
      '5. Do not report completion while any listed thread remains active; ' +
        'a generic top-level review is insufficient.',
    ];
    const body = lines.join('\n');
    if (body.length > safeMaxLength) {
      throw new Error(
        `Bot comment controller part ${index + 1}/${total} exceeds ${safeMaxLength} characters`,
      );
    }
    return body;
  });
}

function buildBotCommentDispatchComment(options = {}) {
  const parts = buildBotCommentDispatchComments(options);
  if (parts.length !== 1) {
    throw new Error(
      'Controller context requires multiple parts; use buildBotCommentDispatchComments',
    );
  }
  return parts[0];
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
  const found = normalizeBoolean(options.found ?? options.commentsFound ?? options.comments_found);
  return normalizeTerminalDispositionRecord({
    source_type: 'review-thread',
    source_id: prNumber,
    pr_number: prNumber,
    disposition: found ? 'unresolved-bot-comments' : 'no-unresolved-bot-comments',
    reason: found
      ? 'Active, non-outdated bot review threads remain and agent handling is eligible.'
      : 'No active, non-outdated bot review threads matched the handler filters.',
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
  const reusableExpected = normalizeBoolean(
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
 * List issue conversation comments with a hard pagination upper bound.
 *
 * Callers should pass a `listFn` obtained via createTokenAwareRetry
 * (from github-api-with-retry.js) so that every page request gets
 * automatic token rotation and rate-limit back-off.
 * This helper is for `issues.listComments`, which is also used for PR
 * conversation comments. Pull-request review comment APIs use different
 * parameter names and should not be passed here.
 *
 * @param {object} options
 * @param {string} options.owner - Repository owner.
 * @param {string} options.repo  - Repository name.
 * @param {number} options.issueNumber - Issue or PR conversation number.
 * @param {function} options.listFn - issues.listComments-compatible function.
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
  MAX_CONTROLLER_COMMENT_LENGTH,
  MAX_COLLECTED_COMMENT_OUTPUT_LENGTH,
  DEFAULT_BOT_AUTHORS,
  DISPATCH_AGENT_ASSIGNEES,
  buildBotCommentDispatchComment,
  buildBotCommentDispatchComments,
  buildBotCommentsPrompt,
  buildReviewThreadTerminalDisposition,
  buildWrapperTerminalDisposition,
  boundBotReviewThreadPayload,
  collectActiveBotReviewThreads,
  collectUnresolvedBotComments,
  getBotCommentAssignees,
  isBotAuthor,
  isIgnoredPath,
  listCommentsWithLimit,
  normalizeBoolean,
  parseCommaList,
  resolveBotAuthors,
  resolveBotCommentAgent,
};
