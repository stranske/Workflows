'use strict';

const crypto = require('crypto');

const CAMPAIGN_SCHEMA = 'sync-dependabot-campaign/v1';
const CAMPAIGN_MARKER = 'sync-dependabot-campaign:v1';
const CAMPAIGN_TITLE = 'Sync/Dependabot campaign queue';
const LABEL_CAMPAIGN = 'campaign:sync-dependabot';
const LABEL_ACTIVE = 'campaign:active';
const LABEL_NEEDS_LOCAL_CODEX = 'campaign:needs-local-codex';
const SYNC_BRANCH_PREFIX = 'sync/workflows-';
const DEFAULT_MAX_ATTEMPTS = 3;
const DEFAULT_MAX_RETAINED_ITEMS = 120;
const DEFAULT_MAX_SOURCE_REVIEW_HISTORY = 80;
const MAX_ISSUE_BODY_LENGTH = 60000;
const MAX_QUEUE_ROWS = 15;
const MAX_DETAIL_ITEMS = 10;
const MAX_THREADS_PER_ITEM = 4;
const DEFAULT_BOT_AUTHORS = [
  'Copilot',
  'copilot[bot]',
  'copilot-pull-request-reviewer',
  'github-actions[bot]',
  'coderabbitai[bot]',
  'chatgpt-codex-connector[bot]',
];
const DEFAULT_IGNORED_PATHS = ['.agents/'];

const ACTIVE_STATUSES = new Set([
  'needs-local-codex',
  'local-codex-claimed',
  'retryable-error',
]);

function cleanString(value) {
  return String(value || '').trim();
}

function cleanInteger(value) {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

function cleanArray(values) {
  return Array.isArray(values) ? values.filter(Boolean) : [];
}

function normaliseLogin(value) {
  return cleanString(value).toLowerCase();
}

function labelsForPullRequest(pr = {}) {
  return cleanArray(pr.labels).map((label) =>
    typeof label === 'string' ? label : cleanString(label?.name)
  );
}

function parseCsv(value) {
  if (Array.isArray(value)) {
    return value.map(cleanString).filter(Boolean);
  }
  return cleanString(value)
    .split(',')
    .map(cleanString)
    .filter(Boolean);
}

function truncate(value, limit = 280) {
  const text = cleanString(value).replace(/\s+/g, ' ');
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, Math.max(0, limit - 3))}...`;
}

function sha256Short(value, length = 16) {
  return crypto.createHash('sha256').update(String(value)).digest('hex').slice(0, length);
}

function isSyncPullRequest(pr = {}) {
  const headRef = cleanString(pr.head?.ref || pr.headRefName || pr.headRef || pr.head_ref);
  const title = cleanString(pr.title).toLowerCase();
  const body = cleanString(pr.body);
  const labels = labelsForPullRequest(pr).map((label) => label.toLowerCase());
  return (
    headRef.startsWith(SYNC_BRANCH_PREFIX) ||
    title.startsWith('chore: sync workflow templates') ||
    labels.includes('sync') ||
    body.includes('workflows-sync-lifecycle')
  );
}

function isDependabotPullRequest(pr = {}) {
  const login = normaliseLogin(pr.user?.login || pr.author?.login || pr.author);
  const headRef = cleanString(pr.head?.ref || pr.headRefName || pr.headRef || pr.head_ref);
  return login === 'dependabot[bot]' || login === 'app/dependabot' || headRef.startsWith('dependabot/');
}

function classifyPullRequest(pr = {}) {
  if (isSyncPullRequest(pr)) {
    return 'sync';
  }
  if (isDependabotPullRequest(pr)) {
    return 'dependabot';
  }
  return '';
}

function botAuthorSet(botAuthors = DEFAULT_BOT_AUTHORS) {
  return new Set(parseCsv(botAuthors).map(normaliseLogin));
}

function pathIgnored(path, ignoredPaths = DEFAULT_IGNORED_PATHS) {
  const cleanPath = cleanString(path);
  return parseCsv(ignoredPaths).some((prefix) => cleanPath.startsWith(prefix));
}

function normaliseReviewThread(thread = {}, options = {}) {
  if (thread.isResolved === true || thread.isOutdated === true) {
    return null;
  }

  const authors = botAuthorSet(options.botAuthors);
  const comments = cleanArray(thread.comments?.nodes || thread.comments || []);
  const botComments = comments.filter((comment) =>
    authors.has(normaliseLogin(comment.author?.login || comment.user?.login))
  );

  if (!botComments.length) {
    return null;
  }

  const firstBotComment = botComments[0];
  const path = cleanString(thread.path || firstBotComment.path);
  if (pathIgnored(path, options.ignoredPaths)) {
    return null;
  }

  return {
    id: cleanString(thread.id || firstBotComment.id || firstBotComment.databaseId),
    path,
    line: cleanInteger(thread.line || firstBotComment.line || firstBotComment.originalLine),
    url: cleanString(firstBotComment.url || firstBotComment.html_url),
    author: cleanString(firstBotComment.author?.login || firstBotComment.user?.login),
    created_at: cleanString(firstBotComment.createdAt || firstBotComment.created_at),
    body_preview: truncate(firstBotComment.bodyText || firstBotComment.body || '', 160),
    comments_count: comments.length,
    bot_comments_count: botComments.length,
  };
}

function collectActiveBotThreads(reviewThreads = [], options = {}) {
  return reviewThreads
    .map((thread) => normaliseReviewThread(thread, options))
    .filter(Boolean)
    .sort((a, b) => {
      const pathCompare = a.path.localeCompare(b.path);
      if (pathCompare !== 0) {
        return pathCompare;
      }
      return (a.line || 0) - (b.line || 0);
    });
}

function buildQueueItem({
  repoFullName,
  pr,
  threads,
  classification,
  now,
  defaultOwner,
  currentSyncHash = '',
} = {}) {
  const repo = cleanString(repoFullName);
  const prNumber = cleanInteger(pr?.number);
  const headSha = cleanString(pr?.head?.sha || pr?.headSha || pr?.head_sha);
  const headRef = cleanString(pr?.head?.ref || pr?.headRefName || pr?.headRef);
  const threadIds = collectThreadIds(threads);
  const fingerprint = sha256Short(`${repo}#${prNumber}:${headSha}:${threadIds.join(',')}`, 20);
  const resolvedClassification = classification || classifyPullRequest(pr);
  const kind = `${resolvedClassification}-review-comments`;
  const sourceRepo = resolvedClassification === 'sync'
    ? `${defaultOwner || repo.split('/')[0]}/Workflows`
    : repo;
  const reviewSignature = reviewSignatureForThreads(threads);
  const sourceReviewKey = reviewSignature
    ? `${sourceRepo}:${resolvedClassification}:${reviewSignature}`
    : '';
  const preferredWorkdir =
    resolvedClassification === 'sync' ? 'Workflows' : repo.split('/').slice(-1)[0] || '';

  return {
    id: `${kind}:${repo}#${prNumber}:${fingerprint}`,
    status: 'needs-local-codex',
    kind,
    classification: resolvedClassification,
    repo,
    pr_number: prNumber,
    pr_title: cleanString(pr?.title),
    pr_url: cleanString(pr?.html_url || pr?.url),
    head_ref: headRef,
    head_sha: headSha,
    base_ref: cleanString(pr?.base?.ref || pr?.baseRefName || pr?.baseRef),
    source_repo: sourceRepo,
    preferred_workdir: preferredWorkdir,
    source_sync: sourceSyncStateFor(resolvedClassification, headRef, currentSyncHash),
    review_signature: reviewSignature,
    source_review_key: sourceReviewKey,
    review_thread_count: threads.length,
    review_comment_count: threads.reduce((sum, thread) => sum + (thread.comments_count || 0), 0),
    review_thread_ids: threadIds,
    review_threads: threads.slice(0, MAX_THREADS_PER_ITEM).map(compactReviewThread),
    first_seen_at: now,
    updated_at: now,
    attempts: 0,
    lease: null,
  };
}

function compactReviewThread(thread = {}) {
  return {
    id: cleanString(thread.id),
    path: cleanString(thread.path),
    line: cleanInteger(thread.line),
    url: cleanString(thread.url),
    author: cleanString(thread.author),
    body_preview: truncate(thread.body_preview, 120),
    comments_count: Number(thread.comments_count || 0),
    bot_comments_count: Number(thread.bot_comments_count || 0),
  };
}

function collectThreadIds(threads = []) {
  return cleanArray(threads)
    .map((thread) => cleanString(thread.id))
    .filter(Boolean)
    .sort();
}

function normalizeSyncHash(value) {
  const text = cleanString(value);
  if (!text) return '';
  return text.startsWith(SYNC_BRANCH_PREFIX) ? text.slice(SYNC_BRANCH_PREFIX.length) : text;
}

function sourceSyncStateFor(classification, headRef, currentSyncHash) {
  if (classification !== 'sync') {
    return null;
  }
  const cleanHeadRef = cleanString(headRef);
  const pr_sync_hash = cleanHeadRef.startsWith(SYNC_BRANCH_PREFIX)
    ? normalizeSyncHash(cleanHeadRef)
    : '';
  const current_sync_hash = normalizeSyncHash(currentSyncHash);
  let status = 'unknown';
  if (pr_sync_hash && current_sync_hash) {
    status = pr_sync_hash === current_sync_hash ? 'current' : 'superseded';
  }
  return {
    schema: 'sync-dependabot-campaign-source-sync/v1',
    current_sync_hash,
    pr_sync_hash,
    status,
  };
}

function reviewSignatureForThreads(threads = []) {
  const entries = cleanArray(threads)
    .map((thread) => [
      cleanString(thread.path),
      truncate(thread.body_preview || thread.bodyText || thread.body || '', 200),
    ].join(':'))
    .filter((entry) => entry !== ':')
    .sort();
  return entries.length ? sha256Short(entries.join('\n'), 20) : '';
}

function sourceFixedCandidateFor(discovered = {}, finishedBySourceReviewKey = new Map()) {
  const key = cleanString(discovered.source_review_key);
  if (!key) {
    return null;
  }
  const finished = finishedBySourceReviewKey.get(key);
  if (!finished || finished.id === discovered.id) {
    return null;
  }
  return {
    matching_item_id: cleanString(finished.matching_item_id || finished.id),
    matching_pr_url: cleanString(finished.matching_pr_url || finished.pr_url),
    finished_at: cleanString(finished.finished_at),
    result_summary: truncate(finished.result_summary || finished.result?.summary, 180),
  };
}

function compactSourceReviewHistoryEntry(item = {}) {
  const sourceReviewKey = cleanString(item.source_review_key);
  if (!sourceReviewKey) {
    return null;
  }
  return {
    source_review_key: sourceReviewKey,
    review_signature: cleanString(item.review_signature),
    matching_item_id: cleanString(item.matching_item_id || item.id),
    matching_pr_url: cleanString(item.matching_pr_url || item.pr_url),
    finished_at: cleanString(item.finished_at),
    result_summary: truncate(item.result_summary || item.result?.summary, 180),
  };
}

function buildSourceReviewHistory(previousState = {}, previousItems = [], limit = DEFAULT_MAX_SOURCE_REVIEW_HISTORY) {
  const retainedHistory = cleanArray(previousState.source_review_history)
    .map(compactSourceReviewHistoryEntry)
    .filter(Boolean);
  const newlyFinished = cleanArray(previousItems)
    .filter((item) => item.status === 'local-codex-finished')
    .map(compactSourceReviewHistoryEntry)
    .filter(Boolean);
  const byKey = new Map();
  for (const entry of [...retainedHistory, ...newlyFinished]) {
    byKey.set(entry.source_review_key, entry);
  }
  return [...byKey.values()]
    .sort((a, b) => cleanString(b.finished_at).localeCompare(cleanString(a.finished_at)))
    .slice(0, Number(limit) || DEFAULT_MAX_SOURCE_REVIEW_HISTORY);
}

function isLeaseExpired(item = {}, now = new Date()) {
  const expiresAt = cleanString(item.lease?.expires_at);
  if (!expiresAt) {
    return true;
  }
  return new Date(expiresAt).getTime() <= now.getTime();
}

function mergeCampaignState(previousState = {}, discoveredItems = [], nowValue, options = {}) {
  const now = cleanString(nowValue) || new Date().toISOString();
  const nowDate = new Date(now);
  const maxAttempts = Number(options.maxAttempts || DEFAULT_MAX_ATTEMPTS);
  const previousItems = cleanArray(previousState.items);
  const previousById = new Map(previousItems.map((item) => [item.id, item]));
  const discoveredById = new Map(discoveredItems.map((item) => [item.id, item]));
  const sourceReviewHistory = buildSourceReviewHistory(
    previousState,
    previousItems,
    options.maxSourceReviewHistory || DEFAULT_MAX_SOURCE_REVIEW_HISTORY
  );
  const finishedBySourceReviewKey = new Map(
    sourceReviewHistory.map((item) => [cleanString(item.source_review_key), item])
  );
  const failedRepos = new Set(parseCsv(options.failedRepos));
  const nextItems = [];

  for (const discovered of discoveredItems) {
    const previous = previousById.get(discovered.id);
    const sourceFixedCandidate = sourceFixedCandidateFor(discovered, finishedBySourceReviewKey);
    if (!previous) {
      nextItems.push({
        ...discovered,
        status: discovered.status || 'needs-local-codex',
        first_seen_at: discovered.first_seen_at || now,
        updated_at: now,
        attempts: Number(discovered.attempts || 0),
        lease: null,
        source_fixed_candidate: sourceFixedCandidate,
      });
      continue;
    }

    let status = previous.status || 'needs-local-codex';
    let lease = previous.lease || null;
    const attempts = Number(previous.attempts || 0);

    if (status === 'local-codex-claimed' && isLeaseExpired(previous, nowDate)) {
      status = 'needs-local-codex';
      lease = null;
    } else if (status === 'retryable-error') {
      status = attempts >= maxAttempts ? 'blocked' : 'needs-local-codex';
      lease = null;
    }

    nextItems.push({
      ...previous,
      ...discovered,
      status,
      first_seen_at: previous.first_seen_at || discovered.first_seen_at || now,
      updated_at: now,
      attempts,
      lease: status === 'local-codex-claimed' ? lease : null,
      result: previous.result || null,
      source_fixed_candidate: sourceFixedCandidate || previous.source_fixed_candidate || null,
    });
  }

  for (const previous of previousItems) {
    if (discoveredById.has(previous.id)) {
      continue;
    }
    if (ACTIVE_STATUSES.has(previous.status) && failedRepos.has(previous.repo)) {
      nextItems.push({
        ...previous,
        preserved_after_scan_error_at: now,
        updated_at: now,
      });
    } else if (ACTIVE_STATUSES.has(previous.status)) {
      nextItems.push({
        ...previous,
        status: 'stale',
        lease: null,
        stale_at: previous.stale_at || now,
        updated_at: now,
      });
    } else {
      nextItems.push(previous);
    }
  }

  const items = pruneItems(nextItems, options.maxRetainedItems || DEFAULT_MAX_RETAINED_ITEMS);
  return {
    schema: CAMPAIGN_SCHEMA,
    updated_at: now,
    run_id: cleanString(options.runId || previousState.run_id),
    controller: 'maint-82-sync-dependabot-campaign',
    stats: buildStats(items, discoveredItems, options),
    source_review_history: sourceReviewHistory,
    items,
  };
}

function pruneItems(items, limit) {
  const active = items.filter((item) => ACTIVE_STATUSES.has(item.status));
  const inactive = items
    .filter((item) => !ACTIVE_STATUSES.has(item.status))
    .sort((a, b) => cleanString(b.updated_at).localeCompare(cleanString(a.updated_at)));
  return [...active, ...inactive].slice(0, limit);
}

function isSourceFixedCandidate(item = {}) {
  return Boolean(item && item.source_fixed_candidate);
}

function isSupersededSyncCandidate(item = {}) {
  return item.classification === 'sync' && cleanString(item.source_sync?.status) === 'superseded';
}

function isActionableLocalCodexItem(item = {}) {
  return item.status === 'needs-local-codex' &&
    !isSourceFixedCandidate(item) &&
    !isSupersededSyncCandidate(item);
}

function isVisibleQueueItem(item = {}) {
  return isActionableLocalCodexItem(item) || item.status === 'local-codex-claimed';
}

function localCodexQueueState(item = {}) {
  const status = cleanString(item.status) || 'unknown';
  if (status === 'needs-local-codex') {
    if (isSourceFixedCandidate(item)) return 'source-fixed-candidate';
    if (isSupersededSyncCandidate(item)) return 'superseded-sync-candidate';
    return 'actionable';
  }
  if (status === 'local-codex-claimed') return 'claimed';
  if (status === 'local-codex-finished') return 'finished';
  if (status === 'blocked') return 'blocked';
  if (status === 'stale') return 'stale';
  return status;
}

function localCodexQueueStateCounts(items = []) {
  return cleanArray(items).reduce((counts, item) => {
    const state = localCodexQueueState(item);
    counts[state] = (counts[state] || 0) + 1;
    return counts;
  }, {});
}

function buildStats(items, discoveredItems, options = {}) {
  const statusCounts = items.reduce((counts, item) => {
    counts[item.status] = (counts[item.status] || 0) + 1;
    return counts;
  }, {});
  const sourceFixedCandidateCount = items.filter(isSourceFixedCandidate).length;
  const supersededSyncCandidateCount = items
    .filter((item) => isSupersededSyncCandidate(item) && !isSourceFixedCandidate(item))
    .length;
  const actionableLocalCodexCount = items.filter(isActionableLocalCodexItem).length;
  return {
    repos_requested: Number(options.reposRequested || 0),
    repos_checked: Number(options.reposChecked || 0),
    repos_failed: Number(options.reposFailed || 0),
    sync_prs_open: Number(options.syncPrsOpen || 0),
    dependabot_prs_open: Number(options.dependabotPrsOpen || 0),
    discovered_review_items: discoveredItems.length,
    active_review_threads: discoveredItems.reduce(
      (sum, item) => sum + Number(item.review_thread_count || 0),
      0,
    ),
    items_needing_local_codex: actionableLocalCodexCount,
    items_actionable_local_codex: actionableLocalCodexCount,
    items_source_fixed_candidates: sourceFixedCandidateCount,
    items_superseded_sync_candidates: supersededSyncCandidateCount,
    items_claimed: statusCounts['local-codex-claimed'] || 0,
    items_finished: statusCounts['local-codex-finished'] || 0,
    items_blocked: statusCounts.blocked || 0,
    status_counts: statusCounts,
    local_codex_queue_state_counts: localCodexQueueStateCounts(items),
  };
}

function deriveItemStats(items = []) {
  const queueItems = cleanArray(items);
  const statusCounts = queueItems.reduce((counts, item) => {
    counts[item.status] = (counts[item.status] || 0) + 1;
    return counts;
  }, {});
  const sourceFixedCandidateCount = queueItems.filter(isSourceFixedCandidate).length;
  const supersededSyncCandidateCount = queueItems
    .filter((item) => isSupersededSyncCandidate(item) && !isSourceFixedCandidate(item))
    .length;
  const actionableLocalCodexCount = queueItems.filter(isActionableLocalCodexItem).length;
  return {
    items_needing_local_codex: actionableLocalCodexCount,
    items_actionable_local_codex: actionableLocalCodexCount,
    items_source_fixed_candidates: sourceFixedCandidateCount,
    items_superseded_sync_candidates: supersededSyncCandidateCount,
    items_claimed: statusCounts['local-codex-claimed'] || 0,
    items_finished: statusCounts['local-codex-finished'] || 0,
    items_blocked: statusCounts.blocked || 0,
    status_counts: statusCounts,
    local_codex_queue_state_counts: localCodexQueueStateCounts(queueItems),
  };
}

function validateCampaignState(state = {}) {
  const stats = state.stats || {};
  const derived = deriveItemStats(state.items);
  const blockers = [];
  const fields = [
    'items_needing_local_codex',
    'items_actionable_local_codex',
    'items_source_fixed_candidates',
    'items_superseded_sync_candidates',
    'items_claimed',
    'items_finished',
    'items_blocked',
  ];
  for (const field of fields) {
    if (Number(stats[field] || 0) !== Number(derived[field] || 0)) {
      blockers.push(`stats-mismatch-${field}`);
    }
  }

  const observedStatuses = new Set([
    ...Object.keys(stats.status_counts || {}),
    ...Object.keys(derived.status_counts || {}),
  ]);
  for (const status of observedStatuses) {
    if (Number(stats.status_counts?.[status] || 0) !== Number(derived.status_counts?.[status] || 0)) {
      blockers.push(`status-count-mismatch-${status}`);
    }
  }

  const observedQueueStates = new Set([
    ...Object.keys(stats.local_codex_queue_state_counts || {}),
    ...Object.keys(derived.local_codex_queue_state_counts || {}),
  ]);
  for (const queueState of observedQueueStates) {
    const actual = Number(stats.local_codex_queue_state_counts?.[queueState] || 0);
    const expected = Number(derived.local_codex_queue_state_counts?.[queueState] || 0);
    if (actual !== expected) {
      blockers.push(`local-codex-queue-state-count-mismatch-${queueState}`);
    }
  }

  return {
    schema: 'sync-dependabot-campaign-validation/v1',
    status: blockers.length > 0 ? 'warning' : 'pass',
    blockers,
    derived_item_stats: derived,
  };
}

function formatCampaignMarker(state) {
  const safeJson = JSON.stringify(compactStateForMarker(state)).replace(/--/g, '\\u002d\\u002d');
  return `<!-- ${CAMPAIGN_MARKER} ${safeJson} -->`;
}

function compactStateForMarker(state = {}) {
  const stats = state.stats || {};
  return {
    schema: state.schema || CAMPAIGN_SCHEMA,
    updated_at: cleanString(state.updated_at),
    run_id: cleanString(state.run_id),
    controller: cleanString(state.controller),
    stats: {
      ...stats,
      local_codex_queue_state_counts:
        stats.local_codex_queue_state_counts || localCodexQueueStateCounts(state.items),
    },
    validation: state.validation || null,
    source_review_history: cleanArray(state.source_review_history)
      .map(compactSourceReviewHistoryEntry)
      .filter(Boolean),
    items: cleanArray(state.items).map(compactQueueItemForMarker),
  };
}

function compactQueueItemForMarker(item = {}) {
  const queueState = localCodexQueueState(item);
  const compact = {
    id: cleanString(item.id),
    status: cleanString(item.status),
    kind: cleanString(item.kind),
    classification: cleanString(item.classification),
    repo: cleanString(item.repo),
    pr_number: cleanInteger(item.pr_number),
    pr_title: truncate(item.pr_title, 80),
    pr_url: cleanString(item.pr_url),
    head_ref: cleanString(item.head_ref),
    head_sha: truncate(item.head_sha, 40),
    base_ref: cleanString(item.base_ref),
    source_repo: cleanString(item.source_repo),
    preferred_workdir: cleanString(item.preferred_workdir),
    source_sync: item.source_sync
      ? {
          schema: cleanString(item.source_sync.schema),
          current_sync_hash: cleanString(item.source_sync.current_sync_hash),
          pr_sync_hash: cleanString(item.source_sync.pr_sync_hash),
          status: cleanString(item.source_sync.status),
        }
      : null,
    review_signature: cleanString(item.review_signature),
    source_review_key: cleanString(item.source_review_key),
    source_fixed_candidate: item.source_fixed_candidate
      ? {
          matching_item_id: cleanString(item.source_fixed_candidate.matching_item_id),
          matching_pr_url: cleanString(item.source_fixed_candidate.matching_pr_url),
          finished_at: cleanString(item.source_fixed_candidate.finished_at),
          result_summary: truncate(item.source_fixed_candidate.result_summary, 160),
        }
      : null,
    review_thread_count: Number(item.review_thread_count || 0),
    review_comment_count: Number(item.review_comment_count || 0),
    first_seen_at: cleanString(item.first_seen_at),
    updated_at: cleanString(item.updated_at),
    claimed_at: cleanString(item.claimed_at),
    finished_at: cleanString(item.finished_at),
    stale_at: cleanString(item.stale_at),
    attempts: Number(item.attempts || 0),
    lease: item.lease
      ? {
          owner: cleanString(item.lease.owner),
          expires_at: cleanString(item.lease.expires_at),
        }
      : null,
    result: item.result
      ? {
          exit_code: item.result.exit_code,
          error: truncate(item.result.error, 160),
          log_path: item.result.log_path,
          last_message_path: item.result.last_message_path,
          summary: truncate(item.result.summary, 300),
          workdir: item.result.workdir,
        }
      : null,
    review_threads: cleanArray(item.review_threads).slice(0, 1).map((thread) => ({
      id: cleanString(thread.id),
      path: cleanString(thread.path),
      line: cleanInteger(thread.line),
      url: cleanString(thread.url),
      author: cleanString(thread.author),
      body_preview: truncate(thread.body_preview, 80),
    })),
  };
  if (queueState === 'source-fixed-candidate' || queueState === 'superseded-sync-candidate') {
    compact.local_codex_queue_state = queueState;
    compact.local_codex_actionable = false;
  }
  return compact;
}

function parseCampaignMarker(body) {
  const match = String(body || '').match(/<!--\s*sync-dependabot-campaign:v1\s+([\s\S]*?)\s*-->/);
  if (!match) {
    return null;
  }
  try {
    const parsed = JSON.parse(match[1].trim());
    return parsed && parsed.schema === CAMPAIGN_SCHEMA ? parsed : null;
  } catch {
    return null;
  }
}

function replaceCampaignMarker(body, state) {
  const marker = formatCampaignMarker(state);
  const source = String(body || '');
  if (source.match(/<!--\s*sync-dependabot-campaign:v1\s+[\s\S]*?\s*-->/)) {
    return source.replace(/<!--\s*sync-dependabot-campaign:v1\s+[\s\S]*?\s*-->/, marker);
  }
  return `${source.trim()}\n\n${marker}`.trim();
}

function markdownLink(label, url) {
  const cleanLabel = cleanString(label).replace(/\|/g, '\\|') || '-';
  const cleanUrl = cleanString(url);
  return cleanUrl ? `[${cleanLabel}](${cleanUrl})` : cleanLabel;
}

function formatCampaignBody(state) {
  const stats = state.stats || {};
  const queueItems = cleanArray(state.items)
    .filter(isVisibleQueueItem)
    .slice(0, MAX_QUEUE_ROWS);
  const rows = queueItems.length
    ? queueItems.map((item) => (
        `| ${item.status} | ${markdownLink(`${item.repo}#${item.pr_number}`, item.pr_url)} | ` +
        `${item.classification} | ${item.review_thread_count || 0} | ${truncate(item.pr_title, 80)} |`
      ))
    : ['| - | - | - | - | No local Codex work is queued. |'];

  const lines = [
    '# Sync/Dependabot Campaign Queue',
    '',
    'Remote GitHub Actions owns discovery for sync-generated and Dependabot PR rounds. Local Codex should only claim items from this issue when `needs-local-codex` work is queued.',
    '',
    '## Summary',
    '',
    `- Updated: ${state.updated_at}`,
    `- Repos checked: ${stats.repos_checked || 0}/${stats.repos_requested || 0}`,
    `- Open sync PRs: ${stats.sync_prs_open || 0}`,
    `- Open Dependabot PRs: ${stats.dependabot_prs_open || 0}`,
    `- Active review threads queued: ${stats.active_review_threads || 0}`,
    `- Items needing local Codex: ${stats.items_needing_local_codex || 0}`,
    `- Actionable local Codex items: ${stats.items_actionable_local_codex || 0}`,
    `- Source-fixed candidates: ${stats.items_source_fixed_candidates || 0}`,
    `- Superseded sync candidates: ${stats.items_superseded_sync_candidates || 0}`,
    '',
    '## Local Queue',
    '',
    '| Status | PR | Kind | Threads | Title |',
    '| --- | --- | --- | ---: | --- |',
    ...rows,
    '',
    '<details><summary>Queue item details</summary>',
    '',
    ...formatItemDetails(state.items),
    '',
    '</details>',
    '',
    '<details><summary>Source-fixed candidates</summary>',
    '',
    ...formatSourceFixedCandidateDetails(state.items),
    '',
    '</details>',
    '',
    '<details><summary>Superseded sync candidates</summary>',
    '',
    ...formatSupersededSyncCandidateDetails(state.items),
    '',
    '</details>',
    '',
    formatCampaignMarker(state),
  ];
  const body = lines.join('\n');
  if (body.length <= MAX_ISSUE_BODY_LENGTH) {
    return body;
  }
  return formatCompactCampaignBody(state);
}

function formatItemDetails(items = []) {
  const lines = [];
  const detailItems = cleanArray(items)
    .filter((item) => !isSourceFixedCandidate(item) && !isSupersededSyncCandidate(item));
  for (const item of detailItems.slice(0, MAX_DETAIL_ITEMS)) {
    lines.push(`### ${item.status}: ${item.repo}#${item.pr_number}`);
    lines.push('');
    lines.push(`- Kind: ${item.kind}`);
    lines.push(`- Source repo: ${item.source_repo || '-'}`);
    lines.push(`- Preferred local workdir: ${item.preferred_workdir || '-'}`);
    lines.push(`- Head: \`${item.head_ref || '-'}\` ${item.head_sha ? `(${item.head_sha.slice(0, 12)})` : ''}`);
    if (item.source_sync) {
      lines.push(
        `- Source sync state: ${item.source_sync.status || 'unknown'} ` +
          `(PR ${item.source_sync.pr_sync_hash || '-'} / current ${item.source_sync.current_sync_hash || '-'})`
      );
    }
    lines.push(`- Attempts: ${item.attempts || 0}`);
    if (item.source_fixed_candidate) {
      const candidate = item.source_fixed_candidate;
      lines.push(
        `- Prior source-fix match: ${markdownLink(candidate.matching_item_id, candidate.matching_pr_url)} ` +
          `${candidate.finished_at ? `(${candidate.finished_at})` : ''}`
      );
      if (candidate.result_summary) {
        lines.push(`- Prior source-fix summary: ${truncate(candidate.result_summary, 180)}`);
      }
    }
    for (const thread of cleanArray(item.review_threads).slice(0, 2)) {
      const location = `${thread.path || '-'}${thread.line ? `:${thread.line}` : ''}`;
      lines.push(`  - ${markdownLink(location, thread.url)} (${thread.author || 'bot'}): ${truncate(thread.body_preview, 120)}`);
    }
    lines.push('');
  }
  const remaining = Math.max(0, detailItems.length - MAX_DETAIL_ITEMS);
  if (remaining > 0) {
    lines.push(`Additional retained items omitted from the rendered issue body: ${remaining}.`);
  }
  return lines.length ? lines : ['No retained queue items.'];
}

function formatSourceFixedCandidateDetails(items = []) {
  const lines = [];
  const candidates = cleanArray(items).filter(isSourceFixedCandidate);
  for (const item of candidates.slice(0, MAX_DETAIL_ITEMS)) {
    const candidate = item.source_fixed_candidate || {};
    lines.push(`### ${item.repo}#${item.pr_number}`);
    lines.push('');
    lines.push(`- Status: ${item.status}`);
    lines.push(`- Source repo: ${item.source_repo || '-'}`);
    lines.push(
      `- Prior source-fix match: ${markdownLink(candidate.matching_item_id, candidate.matching_pr_url)} ` +
        `${candidate.finished_at ? `(${candidate.finished_at})` : ''}`
    );
    if (candidate.result_summary) {
      lines.push(`- Prior source-fix summary: ${truncate(candidate.result_summary, 180)}`);
    }
    for (const thread of cleanArray(item.review_threads).slice(0, 2)) {
      const location = `${thread.path || '-'}${thread.line ? `:${thread.line}` : ''}`;
      lines.push(`  - ${markdownLink(location, thread.url)} (${thread.author || 'bot'}): ${truncate(thread.body_preview, 120)}`);
    }
    lines.push('');
  }
  const remaining = Math.max(0, candidates.length - MAX_DETAIL_ITEMS);
  if (remaining > 0) {
    lines.push(`Additional source-fixed candidates omitted from the rendered issue body: ${remaining}.`);
  }
  return lines.length ? lines : ['No source-fixed candidates retained.'];
}

function formatSupersededSyncCandidateDetails(items = []) {
  const lines = [];
  const candidates = cleanArray(items)
    .filter((item) => isSupersededSyncCandidate(item) && !isSourceFixedCandidate(item));
  for (const item of candidates.slice(0, MAX_DETAIL_ITEMS)) {
    lines.push(`### ${item.repo}#${item.pr_number}`);
    lines.push('');
    lines.push(`- Status: ${item.status}`);
    lines.push(`- Source repo: ${item.source_repo || '-'}`);
    lines.push(
      `- Source sync state: ${item.source_sync.status || 'unknown'} ` +
        `(PR ${item.source_sync.pr_sync_hash || '-'} / current ${item.source_sync.current_sync_hash || '-'})`
    );
    for (const thread of cleanArray(item.review_threads).slice(0, 2)) {
      const location = `${thread.path || '-'}${thread.line ? `:${thread.line}` : ''}`;
      lines.push(`  - ${markdownLink(location, thread.url)} (${thread.author || 'bot'}): ${truncate(thread.body_preview, 120)}`);
    }
    lines.push('');
  }
  const remaining = Math.max(0, candidates.length - MAX_DETAIL_ITEMS);
  if (remaining > 0) {
    lines.push(`Additional superseded sync candidates omitted from the rendered issue body: ${remaining}.`);
  }
  return lines.length ? lines : ['No superseded sync candidates retained.'];
}

function formatCompactCampaignBody(state) {
  const stats = state.stats || {};
  const queueItems = cleanArray(state.items)
    .filter(isVisibleQueueItem)
    .slice(0, 10);
  const rows = queueItems.length
    ? queueItems.map((item) => (
        `| ${item.status} | ${markdownLink(`${item.repo}#${item.pr_number}`, item.pr_url)} | ` +
        `${item.review_thread_count || 0} |`
      ))
    : ['| - | - | - |'];
  return [
    '# Sync/Dependabot Campaign Queue',
    '',
    'Remote discovery found more review-thread work than fits in a full GitHub issue body. The marker below retains the compact machine-readable queue for the local watcher.',
    '',
    `- Updated: ${state.updated_at}`,
    `- Repos checked: ${stats.repos_checked || 0}/${stats.repos_requested || 0}`,
    `- Open sync PRs: ${stats.sync_prs_open || 0}`,
    `- Open Dependabot PRs: ${stats.dependabot_prs_open || 0}`,
    `- Active review threads queued: ${stats.active_review_threads || 0}`,
    `- Items needing local Codex: ${stats.items_needing_local_codex || 0}`,
    `- Actionable local Codex items: ${stats.items_actionable_local_codex || 0}`,
    `- Source-fixed candidates: ${stats.items_source_fixed_candidates || 0}`,
    `- Superseded sync candidates: ${stats.items_superseded_sync_candidates || 0}`,
    '',
    '| Status | PR | Threads |',
    '| --- | --- | ---: |',
    ...rows,
    '',
    formatCampaignMarker(state),
  ].join('\n');
}

function normaliseRepoEntry(entry, defaultOwner) {
  const clean = cleanString(entry);
  if (!clean) {
    return null;
  }
  if (clean.includes('/')) {
    const [owner, repo] = clean.split('/');
    return { owner, repo, fullName: `${owner}/${repo}` };
  }
  return { owner: defaultOwner, repo: clean, fullName: `${defaultOwner}/${clean}` };
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function createCampaignRetry({ github, core } = {}) {
  try {
    const { createTokenAwareRetry } = require('./github-api-with-retry.js');
    return await createTokenAwareRetry({
      github,
      core,
      env: process.env,
      task: 'maint-82-sync-dependabot-campaign',
      capabilities: ['issues:write', 'pull-requests:read'],
      minRemaining: 100,
    });
  } catch (error) {
    log(core, 'warning', `Token-aware retry setup failed; using default client: ${error.message}`);
    return {
      github,
      withRetry: (fn) => fn(github),
    };
  }
}

async function callWithRetry(fn, label, core, maxRetries = 3, withRetry = null, github = null) {
  if (typeof withRetry === 'function') {
    return withRetry(
      (client) => fn(client || github),
      {
        maxRetries,
        onRetry: (attempt, error, delay) => {
          log(core, 'warning', `${label} failed with ${error.status || error.message}; retrying in ${delay}ms`);
        },
      },
    );
  }

  let lastError = null;
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    try {
      return await fn(github);
    } catch (error) {
      lastError = error;
      const status = error.status || error?.response?.status;
      const retryable = status === 429 || [500, 502, 503, 504].includes(status);
      if (!retryable || attempt === maxRetries) {
        throw error;
      }
      const delay = Math.min(30000, 1000 * (2 ** attempt));
      log(core, 'warning', `${label} failed with ${status || error.message}; retrying in ${delay}ms`);
      await sleep(delay);
    }
  }
  throw lastError;
}

async function paginateWithRetry({ github, core, withRetry, method, params, label }) {
  return callWithRetry(
    (client) => {
      const api = client || github;
      if (!api || typeof api.paginate !== 'function') {
        throw new Error(`${label} requires github.paginate`);
      }
      const endpoint = typeof method === 'function' ? method(api) : method;
      return api.paginate(endpoint, params);
    },
    label,
    core,
    3,
    withRetry,
    github,
  );
}

async function fetchReviewThreads(github, owner, repo, number, core, withRetry = null) {
  const query = `
    query($owner: String!, $repo: String!, $number: Int!, $after: String) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
          reviewThreads(first: 100, after: $after) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              isResolved
              isOutdated
              path
              line
              comments(first: 25) {
                nodes {
                  id
                  databaseId
                  url
                  body
                  bodyText
                  createdAt
                  author {
                    login
                  }
                }
              }
            }
          }
        }
      }
    }
  `;
  let after = null;
  const threads = [];
  do {
    const data = await callWithRetry(
      (client) => client.graphql(query, { owner, repo, number, after }),
      `${owner}/${repo}#${number} reviewThreads`,
      core,
      3,
      withRetry,
      github,
    );
    const connection = data?.repository?.pullRequest?.reviewThreads;
    threads.push(...cleanArray(connection?.nodes));
    after = connection?.pageInfo?.hasNextPage ? connection.pageInfo.endCursor : null;
  } while (after);
  return threads;
}

async function discoverRepoWork({
  github,
  core,
  repoEntry,
  now,
  defaultOwner,
  botAuthors,
  ignoredPaths,
  withRetry = null,
  currentSyncHash = '',
}) {
  const { owner, repo, fullName } = repoEntry;
  const result = {
    repo: fullName,
    items: [],
    syncPrsOpen: 0,
    dependabotPrsOpen: 0,
  };

  const prs = cleanArray(await paginateWithRetry({
    github,
    core,
    withRetry,
    method: (client) => client.rest.pulls.list,
    params: { owner, repo, state: 'open', per_page: 100 },
    label: `${fullName} open pulls`,
  }));

  for (const pr of prs) {
    const classification = classifyPullRequest(pr);
    if (classification === 'sync') {
      result.syncPrsOpen += 1;
    } else if (classification === 'dependabot') {
      result.dependabotPrsOpen += 1;
    } else {
      continue;
    }

    const reviewThreads = await fetchReviewThreads(github, owner, repo, pr.number, core, withRetry);
    const activeThreads = collectActiveBotThreads(reviewThreads, { botAuthors, ignoredPaths });
    if (!activeThreads.length) {
      continue;
    }
    result.items.push(buildQueueItem({
      repoFullName: fullName,
      pr,
      threads: activeThreads,
      classification,
      now,
      defaultOwner,
      currentSyncHash,
    }));
  }

  return result;
}

async function findCampaignIssue(github, owner, repo, core, withRetry = null) {
  const issues = cleanArray(await paginateWithRetry({
    github,
    core,
    withRetry,
    method: (client) => client.rest.issues.listForRepo,
    params: { owner, repo, state: 'open', per_page: 100 },
    label: `${owner}/${repo} campaign issue list`,
  }));
  const candidates = issues.filter((issue) =>
    !issue.pull_request && cleanString(issue.title).startsWith(CAMPAIGN_TITLE)
  );

  for (const issue of candidates) {
    const fullIssue = await callWithRetry(
      (client) => client.rest.issues.get({ owner, repo, issue_number: issue.number }),
      `${owner}/${repo}#${issue.number}`,
      core,
      3,
      withRetry,
      github,
    );
    if (parseCampaignMarker(fullIssue.data.body)) {
      return fullIssue.data;
    }
  }

  return null;
}

async function ensureLabel(github, owner, repo, name, color, description, core, withRetry = null) {
  try {
    await callWithRetry(
      (client) => client.rest.issues.getLabel({ owner, repo, name }),
      `${owner}/${repo} label ${name}`,
      core,
      1,
      withRetry,
      github,
    );
  } catch (error) {
    if ((error.status || error?.response?.status) !== 404) {
      throw error;
    }
    await callWithRetry(
      (client) => client.rest.issues.createLabel({ owner, repo, name, color, description }),
      `${owner}/${repo} create label ${name}`,
      core,
      1,
      withRetry,
      github,
    );
  }
}

async function applyCampaignLabels(github, owner, repo, issueNumber, needsLocalCodex, core, withRetry = null) {
  await ensureLabel(github, owner, repo, LABEL_CAMPAIGN, '0e8a16', 'Sync/Dependabot campaign queue', core, withRetry);
  await ensureLabel(github, owner, repo, LABEL_ACTIVE, '1d76db', 'Active campaign controller issue', core, withRetry);
  await ensureLabel(
    github,
    owner,
    repo,
    LABEL_NEEDS_LOCAL_CODEX,
    'b60205',
    'Local Codex watcher should claim queued work',
    core,
    withRetry,
  );

  const labels = [LABEL_CAMPAIGN, LABEL_ACTIVE];
  if (needsLocalCodex) {
    labels.push(LABEL_NEEDS_LOCAL_CODEX);
  }
  await callWithRetry(
    (client) => client.rest.issues.addLabels({ owner, repo, issue_number: issueNumber, labels }),
    `${owner}/${repo}#${issueNumber} add campaign labels`,
    core,
    1,
    withRetry,
    github,
  );

  if (!needsLocalCodex) {
    try {
      await callWithRetry(
        (client) => client.rest.issues.removeLabel({
          owner,
          repo,
          issue_number: issueNumber,
          name: LABEL_NEEDS_LOCAL_CODEX,
        }),
        `${owner}/${repo}#${issueNumber} remove needs-local label`,
        core,
        1,
        withRetry,
        github,
      );
    } catch (error) {
      if ((error.status || error?.response?.status) !== 404) {
        throw error;
      }
    }
  }
}

function log(core, level, message) {
  if (core && typeof core[level] === 'function') {
    core[level](message);
    return;
  }
  if (level === 'warning') {
    console.warn(message);
  } else if (level === 'error') {
    console.error(message);
  } else {
    console.log(message);
  }
}

function verboseDryRunLoggingEnabled(env = process.env) {
  return (
    cleanString(env.ACTIONS_STEP_DEBUG).toLowerCase() === 'true' ||
    cleanString(env.RUNNER_DEBUG) === '1' ||
    cleanString(env.SYNC_DEPENDABOT_CAMPAIGN_DEBUG_BODY).toLowerCase() === 'true'
  );
}

function formatDryRunSummary(state = {}) {
  const stats = state.stats || {};
  return [
    '[dry-run] Campaign issue update suppressed from logs.',
    `repos_checked=${stats.repos_checked || 0}/${stats.repos_requested || 0}`,
    `repos_failed=${stats.repos_failed || 0}`,
    `sync_prs_open=${stats.sync_prs_open || 0}`,
    `dependabot_prs_open=${stats.dependabot_prs_open || 0}`,
    `items_needing_local_codex=${stats.items_needing_local_codex || 0}`,
  ].join(' ');
}

function formatCampaignRunSummaryMarkdown(state = {}, issue = null) {
  const stats = state.stats || {};
  const errors = cleanArray(state.errors);
  const validation = state.validation || validateCampaignState(state);
  const lines = [
    '## Sync/Dependabot Campaign Run',
    '',
    `- Schema: ${state.schema || CAMPAIGN_SCHEMA}`,
    `- Updated: ${cleanString(state.updated_at) || '-'}`,
    `- Run ID: ${cleanString(state.run_id) || '-'}`,
    `- Controller: ${cleanString(state.controller) || 'maint-82-sync-dependabot-campaign'}`,
    `- Campaign issue: ${cleanString(issue?.html_url || issue?.url) || '-'}`,
    `- Repos checked: ${stats.repos_checked || 0}/${stats.repos_requested || 0}`,
    `- Repos failed: ${stats.repos_failed || 0}`,
    `- Open sync PRs: ${stats.sync_prs_open || 0}`,
    `- Open Dependabot PRs: ${stats.dependabot_prs_open || 0}`,
    `- Active review threads queued: ${stats.active_review_threads || 0}`,
    `- Items needing local Codex: ${stats.items_needing_local_codex || 0}`,
    `- Actionable local Codex items: ${stats.items_actionable_local_codex || 0}`,
    `- Source-fixed candidates: ${stats.items_source_fixed_candidates || 0}`,
    `- Superseded sync candidates: ${stats.items_superseded_sync_candidates || 0}`,
    `- Items claimed: ${stats.items_claimed || 0}`,
    `- Items blocked: ${stats.items_blocked || 0}`,
    `- State validation: ${validation.status}`,
  ];

  if (validation.blockers?.length > 0) {
    lines.push(`- Validation blockers: ${validation.blockers.join(', ')}`);
  }

  if (errors.length > 0) {
    lines.push('', '### Scan Errors', '');
    for (const error of errors.slice(0, 10)) {
      lines.push(`- ${cleanString(error.repo) || '-'}: ${truncate(error.error, 180)}`);
    }
  }

  return `${lines.join('\n')}\n`;
}

async function runCampaign({
  github,
  context,
  core = console,
  repos = [],
  dryRun = false,
  maxRepos = 0,
  botAuthors = DEFAULT_BOT_AUTHORS,
  ignoredPaths = DEFAULT_IGNORED_PATHS,
  currentSyncHash = '',
  now = new Date().toISOString(),
} = {}) {
  if (!github || !context?.repo) {
    throw new Error('runCampaign requires github and context.repo');
  }

  const retryHelpers = await createCampaignRetry({ github, core });
  const api = retryHelpers.github || github;
  const withRetry = retryHelpers.withRetry;
  const campaignOwner = context.repo.owner;
  const campaignRepo = context.repo.repo;
  const repoEntries = parseCsv(repos)
    .map((entry) => normaliseRepoEntry(entry, campaignOwner))
    .filter(Boolean);
  const limitedRepoEntries = Number(maxRepos) > 0 ? repoEntries.slice(0, Number(maxRepos)) : repoEntries;

  let campaignIssue = await findCampaignIssue(api, campaignOwner, campaignRepo, core, withRetry);
  let previousState = parseCampaignMarker(campaignIssue?.body) || {};
  const discoveredItems = [];
  const errors = [];
  let syncPrsOpen = 0;
  let dependabotPrsOpen = 0;

  for (const repoEntry of limitedRepoEntries) {
    log(core, 'info', `Discovering campaign work in ${repoEntry.fullName}`);
    try {
      const result = await discoverRepoWork({
        github: api,
        core,
        repoEntry,
        now,
        defaultOwner: campaignOwner,
        botAuthors,
        ignoredPaths,
        withRetry,
        currentSyncHash,
      });
      discoveredItems.push(...result.items);
      syncPrsOpen += result.syncPrsOpen;
      dependabotPrsOpen += result.dependabotPrsOpen;
    } catch (error) {
      errors.push({ repo: repoEntry.fullName, error: error.message });
      log(core, 'warning', `Failed to inspect ${repoEntry.fullName}: ${error.message}`);
    }
  }

  const state = mergeCampaignState(previousState, discoveredItems, now, {
    runId: context.runId || context.run_id,
    reposRequested: repoEntries.length,
    reposChecked: limitedRepoEntries.length - errors.length,
    reposFailed: errors.length,
    syncPrsOpen,
    dependabotPrsOpen,
    failedRepos: errors.map((error) => error.repo),
  });
  if (errors.length) {
    state.errors = errors.slice(0, 20);
  }
  state.validation = validateCampaignState(state);

  const body = formatCampaignBody(state);
  const needsLocalCodex = Number(state.stats.items_needing_local_codex || 0) > 0;

  if (dryRun) {
    log(core, 'info', formatDryRunSummary(state));
    if (verboseDryRunLoggingEnabled()) {
      log(core, 'info', '[dry-run] Campaign issue body preview:');
      log(core, 'info', body);
    }
  } else if (campaignIssue?.number) {
    const updated = await callWithRetry(
      (client) => client.rest.issues.update({
        owner: campaignOwner,
        repo: campaignRepo,
        issue_number: campaignIssue.number,
        title: CAMPAIGN_TITLE,
        body,
      }),
      `${campaignOwner}/${campaignRepo}#${campaignIssue.number} update campaign issue`,
      core,
      3,
      withRetry,
      api,
    );
    campaignIssue = updated.data;
    await applyCampaignLabels(api, campaignOwner, campaignRepo, campaignIssue.number, needsLocalCodex, core, withRetry);
  } else {
    const created = await callWithRetry(
      (client) => client.rest.issues.create({
        owner: campaignOwner,
        repo: campaignRepo,
        title: CAMPAIGN_TITLE,
        body,
      }),
      `${campaignOwner}/${campaignRepo} create campaign issue`,
      core,
      3,
      withRetry,
      api,
    );
    campaignIssue = created.data;
    await applyCampaignLabels(api, campaignOwner, campaignRepo, campaignIssue.number, needsLocalCodex, core, withRetry);
  }

  if (core && typeof core.setOutput === 'function') {
    core.setOutput('needs_local_codex', needsLocalCodex ? 'true' : 'false');
    core.setOutput('items_needing_local_codex', String(state.stats.items_needing_local_codex || 0));
    core.setOutput('items_actionable_local_codex', String(state.stats.items_actionable_local_codex || 0));
    core.setOutput('items_source_fixed_candidates', String(state.stats.items_source_fixed_candidates || 0));
    core.setOutput('items_superseded_sync_candidates', String(state.stats.items_superseded_sync_candidates || 0));
    core.setOutput('campaign_issue_url', campaignIssue?.html_url || '');
  }

  return { state, issue: campaignIssue, body };
}

module.exports = {
  CAMPAIGN_SCHEMA,
  CAMPAIGN_MARKER,
  CAMPAIGN_TITLE,
  LABEL_CAMPAIGN,
  LABEL_ACTIVE,
  LABEL_NEEDS_LOCAL_CODEX,
  DEFAULT_BOT_AUTHORS,
  collectActiveBotThreads,
  buildQueueItem,
  classifyPullRequest,
  discoverRepoWork,
  findCampaignIssue,
  formatCampaignBody,
  formatCampaignMarker,
  formatCampaignRunSummaryMarkdown,
  formatDryRunSummary,
  isDependabotPullRequest,
  isSyncPullRequest,
  mergeCampaignState,
  paginateWithRetry,
  parseCampaignMarker,
  replaceCampaignMarker,
  runCampaign,
  validateCampaignState,
  verboseDryRunLoggingEnabled,
};
