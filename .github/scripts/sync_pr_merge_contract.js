'use strict';

const REPORT_SCHEMA = 'workflows-sync-pr-merge/v1';
const SYNC_BRANCH_PREFIX = 'sync/workflows-';
const DEV_TOOL_SYNC_BRANCH_PREFIX = 'deps/sync-dev-versions-';
const GENERATED_DELIVERY_BRANCH_PREFIXES = [SYNC_BRANCH_PREFIX, DEV_TOOL_SYNC_BRANCH_PREFIX];
const { parseDeliveryRecord, mergeEligibility } = require('./sync_pr_lease_contract');

function normalizeSyncHash(value) {
  const raw = String(value || '').trim();
  if (!raw) {
    return '';
  }
  return raw.startsWith(SYNC_BRANCH_PREFIX) ? raw.slice(SYNC_BRANCH_PREFIX.length) : raw;
}

function syncBranchForHash(syncHash) {
  const normalized = normalizeSyncHash(syncHash);
  return normalized ? `${SYNC_BRANCH_PREFIX}${normalized}` : '';
}

function branchNameFromRef(value) {
  return String(value || '')
    .trim()
    .replace(/^refs\/heads\//, '')
    .replace(/^heads\//, '');
}

function isSyncBranchName(value) {
  return branchNameFromRef(value).startsWith(SYNC_BRANCH_PREFIX);
}

function generatedDeliveryLane(value) {
  const branch = branchNameFromRef(value);
  if (branch.startsWith(SYNC_BRANCH_PREFIX)) return 'sync';
  if (branch.startsWith(DEV_TOOL_SYNC_BRANCH_PREFIX)) return 'dev-tool-sync';
  return '';
}

function isGeneratedDeliveryBranchName(value) {
  return Boolean(generatedDeliveryLane(value));
}

function isTrustedSyncPr(pr, trustedActors = []) {
  const actor = String(pr?.user?.login || '').trim();
  return isSyncBranchName(pr?.head?.ref) && new Set(trustedActors).has(actor);
}

function isTrustedGeneratedDeliveryPr(pr, trustedActors = []) {
  const actor = String(pr?.user?.login || '').trim();
  return isGeneratedDeliveryBranchName(pr?.head?.ref) && new Set(trustedActors).has(actor);
}

function classifyGeneratedPr({ pr = {}, checkState = {}, activeReviewThreadCount = 0, now } = {}) {
  const record = parseDeliveryRecord(pr.body || '');
  const lane = generatedDeliveryLane(pr?.head?.ref || pr?.headRefName);
  if (!lane) return { disposition: 'owner-decision', blocker_owner: 'source', next_command: '' };
  if (!record) return {
    disposition: 'owner-decision',
    blocker_owner: 'source',
    next_command: 'attach-or-infer-delivery-record',
  };
  const eligibility = mergeEligibility(record, { now });
  if (eligibility.reason === 'lease_expired') {
    return { disposition: 'expired', blocker_owner: 'maint-71', next_command: 'close-expired-delivery' };
  }
  if (!eligibility.eligible) {
    return { disposition: 'superseded', blocker_owner: 'maint-71', next_command: 'close-or-refresh-delivery' };
  }
  const reviewThreadCount = Number(activeReviewThreadCount);
  if (!Number.isFinite(reviewThreadCount) || reviewThreadCount < 0) {
    return { disposition: 'review-blocked', blocker_owner: 'closer', next_command: 'retry-review-thread-query' };
  }
  if (reviewThreadCount > 0) {
    return { disposition: 'review-blocked', blocker_owner: 'closer', next_command: 'resolve-active-review-threads' };
  }
  if (checkState.status === 'checks_pending') {
    return { disposition: 'awaiting-checks', blocker_owner: 'ci', next_command: 'await-required-checks' };
  }
  if (checkState.status === 'checks_failed') {
    return { disposition: 'repo-local-failure', blocker_owner: 'repo', next_command: 'repair-required-checks' };
  }
  return { disposition: 'current', blocker_owner: 'maint-71', next_command: 'merge-current-delivery' };
}

function parseBooleanInput(value, defaultValue = false) {
  if (value === undefined || value === null || String(value).trim() === '') {
    return Boolean(defaultValue);
  }
  const normalized = String(value).trim().toLowerCase();
  if (['true', '1', 'yes', 'y'].includes(normalized)) {
    return true;
  }
  if (['false', '0', 'no', 'n'].includes(normalized)) {
    return false;
  }
  return Boolean(defaultValue);
}

function collectDeletableSyncBranches({
  branches = [],
  openPullRequests = [],
  closedPullRequests = [],
} = {}) {
  const openBranches = new Set(
    (openPullRequests || [])
      .map((pr) => branchNameFromRef(pr?.head?.ref || pr?.headRefName || pr?.branch))
      .filter(isGeneratedDeliveryBranchName),
  );
  const closedBranches = new Set(
    (closedPullRequests || [])
      .map((pr) => branchNameFromRef(pr?.head?.ref || pr?.headRefName || pr?.branch))
      .filter(isGeneratedDeliveryBranchName),
  );

  return (branches || [])
    .map((branch) => branchNameFromRef(branch?.name || branch?.ref || branch))
    .filter(isGeneratedDeliveryBranchName)
    .filter((branch) => !openBranches.has(branch))
    .filter((branch) => closedBranches.has(branch))
    .sort();
}

function normalizeStringSet(values) {
  if (!values) {
    return new Set();
  }
  const items = values instanceof Set ? [...values] : values;
  if (!Array.isArray(items)) {
    return new Set();
  }
  return new Set(items.map((value) => String(value || '').trim()).filter(Boolean));
}

function checkRunTimestamp(check) {
  const timestamp = new Date(
    check?.started_at || check?.completed_at || check?.created_at || 0,
  ).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function latestCheckRunsByName(checkRuns = []) {
  const orderedChecks = [...(checkRuns || [])].sort(
    (a, b) => checkRunTimestamp(b) - checkRunTimestamp(a),
  );
  const latestChecksByName = new Map();
  for (const check of orderedChecks) {
    const name = String(check?.name || '').trim();
    if (name && !latestChecksByName.has(name)) {
      latestChecksByName.set(name, check);
    }
  }
  return [...latestChecksByName.values()];
}

function isFallbackDeniedCheck(checkName, fallbackDenylist) {
  return [...fallbackDenylist].some((deniedName) => checkName.includes(deniedName));
}

function selectSyncPrGatingChecks({
  checkRuns = [],
  requiredContexts = [],
  fallbackDenylist = [],
} = {}) {
  const requiredContextSet = normalizeStringSet(requiredContexts);
  const fallbackDenylistSet = normalizeStringSet(fallbackDenylist);
  const latestChecks = latestCheckRunsByName(checkRuns);
  return requiredContextSet.size > 0
    ? latestChecks.filter((check) => requiredContextSet.has(String(check?.name || '').trim()))
    : latestChecks.filter(
        (check) => !isFallbackDeniedCheck(String(check?.name || ''), fallbackDenylistSet),
      );
}

function classifySyncPrChecks({
  checkRuns = [],
  requiredContexts = [],
  fallbackDenylist = [],
} = {}) {
  const gatingChecks = selectSyncPrGatingChecks({
    checkRuns,
    requiredContexts,
    fallbackDenylist,
  });
  const allowedConclusions = new Set(['success', 'skipped', 'neutral']);
  const failed = gatingChecks.filter((check) => {
    if (check?.status !== 'completed') {
      return false;
    }
    return !allowedConclusions.has(String(check?.conclusion || '').toLowerCase());
  });
  const pending = gatingChecks.filter((check) => check?.status !== 'completed');

  if (failed.length > 0) {
    return { status: 'checks_failed', failed, pending: [] };
  }
  if (pending.length > 0) {
    return { status: 'checks_pending', failed: [], pending };
  }
  return { status: 'ready', failed: [], pending: [] };
}

function sortSyncPrs(prs) {
  return [...(prs || [])].sort((a, b) => {
    const aTime = new Date(a.created_at || a.createdAt || 0).getTime();
    const bTime = new Date(b.created_at || b.createdAt || 0).getTime();
    return aTime - bTime;
  });
}

function selectActiveSyncPr(prs, syncHash = '') {
  const ordered = sortSyncPrs(prs);
  const expectedBranch = syncBranchForHash(syncHash);
  if (!expectedBranch) {
    const active = ordered[ordered.length - 1] || null;
    return {
      active,
      stale: active ? ordered.filter((pr) => pr.number !== active.number) : [],
      expectedBranch: '',
      missingExpected: false,
    };
  }

  const active = ordered.find((pr) => pr.head && pr.head.ref === expectedBranch) || null;
  return {
    active,
    stale: active ? ordered.filter((pr) => pr.number !== active.number) : [],
    expectedBranch,
    missingExpected: !active,
  };
}

function selectMergeEligibleSyncPr(
  prs,
  { syncHash = '', now, planId = '', repository = '', desiredTreeHash = '' } = {},
) {
  const selection = selectActiveSyncPr(prs, syncHash);
  if (!selection.active) return { ...selection, eligibility: null };
  const record = parseDeliveryRecord(selection.active.body || '');
  const eligibility = record
    ? mergeEligibility(record, { now, planId, repository, desiredTreeHash })
    : { eligible: false, reason: 'missing_delivery_record' };
  return { ...selection, deliveryRecord: record, eligibility };
}

function summarizeResults(results) {
  const counts = {
    no_prs: 0,
    target_missing: 0,
    stale_closed: 0,
    stale_close_failed: 0,
    branch_deleted: 0,
    branch_delete_failed: 0,
    checks_failed: 0,
    checks_pending: 0,
    review_blocked: 0,
    ready: 0,
    dry_run_merge: 0,
    merge_blocked_runtime_ac: 0,
    merged: 0,
    merge_failed: 0,
    delivery_contract_blocked: 0,
    error: 0,
  };
  for (const result of results || []) {
    if (Object.prototype.hasOwnProperty.call(counts, result.status)) {
      counts[result.status] += 1;
    }
  }
  return counts;
}

function buildDeliveryHandoff(result = {}) {
  if (!result.pr) return null;
  const headSha = String(result.head_sha || '');
  const deliveryGeneration = String(result.delivery_generation || '');
  if (!headSha || !deliveryGeneration) return null;
  return {
    schema: 'workflows-generated-delivery-handoff/v1',
    repository: `${result.owner || ''}/${result.repo || ''}`.replace(/^\//, ''),
    pr: Number(result.pr),
    branch: branchNameFromRef(result.branch),
    head_sha: headSha,
    delivery_generation: deliveryGeneration,
    lane: generatedDeliveryLane(result.branch),
    disposition: String(result.delivery_disposition || result.status || ''),
    blocker_owner: String(result.blocker_owner || ''),
    next_command: String(result.next_command || ''),
  };
}

function buildMergeReport({
  results = [],
  registeredRepos = [],
  targetRepos = [],
  autoMerge = true,
  dryRun = false,
  syncHash = '',
  run = {},
  generatedAt = new Date().toISOString(),
} = {}) {
  const normalizedSyncHash = normalizeSyncHash(syncHash);
  return {
    schema: REPORT_SCHEMA,
    generated_at: generatedAt,
    run,
    inputs: {
      repos: targetRepos,
      registered_repos: registeredRepos,
      auto_merge: Boolean(autoMerge),
      dry_run: Boolean(dryRun),
      sync_hash: normalizedSyncHash,
      expected_branch: syncBranchForHash(normalizedSyncHash),
    },
    summary: summarizeResults(results),
    results,
    handoff_records: (results || []).map(buildDeliveryHandoff).filter(Boolean),
  };
}

function buildMarkdownSummary(report) {
  const summary = report.summary || {};
  const inputs = report.inputs || {};
  const lines = [
    '### Sync PR Merge Summary',
    '',
    `Schema: \`${report.schema || REPORT_SCHEMA}\``,
    `Processed repos: ${Array.isArray(inputs.repos) ? inputs.repos.length : 0}`,
    `Auto-merge: ${inputs.auto_merge ? 'true' : 'false'}`,
    `Dry run: ${inputs.dry_run ? 'true' : 'false'}`,
  ];
  if (inputs.expected_branch) {
    lines.push(`Expected branch: \`${inputs.expected_branch}\``);
  }
  lines.push(
    '',
    '| Status | Count |',
    '| --- | ---: |',
  );
  for (const [status, count] of Object.entries(summary)) {
    if (count) {
      lines.push(`| ${status} | ${count} |`);
    }
  }
  lines.push('', 'Artifact: `sync-pr-merge-report`');
  return `${lines.join('\n')}\n`;
}

module.exports = {
  REPORT_SCHEMA,
  SYNC_BRANCH_PREFIX,
  DEV_TOOL_SYNC_BRANCH_PREFIX,
  GENERATED_DELIVERY_BRANCH_PREFIXES,
  branchNameFromRef,
  classifyGeneratedPr,
  classifySyncPrChecks,
  collectDeletableSyncBranches,
  generatedDeliveryLane,
  isGeneratedDeliveryBranchName,
  isSyncBranchName,
  isTrustedGeneratedDeliveryPr,
  isTrustedSyncPr,
  normalizeSyncHash,
  syncBranchForHash,
  parseBooleanInput,
  selectSyncPrGatingChecks,
  sortSyncPrs,
  selectActiveSyncPr,
  selectMergeEligibleSyncPr,
  summarizeResults,
  buildMergeReport,
  buildDeliveryHandoff,
  buildMarkdownSummary,
};
