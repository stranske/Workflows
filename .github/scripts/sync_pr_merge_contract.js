'use strict';

const REPORT_SCHEMA = 'workflows-sync-pr-merge/v1';
const SYNC_BRANCH_PREFIX = 'sync/workflows-';
const SYNC_CANDIDATE_BRANCH = `${SYNC_BRANCH_PREFIX}candidate`;
const SYNC_DELIVERY_BRANCH = `${SYNC_BRANCH_PREFIX}delivery`;
const DEV_TOOL_SYNC_BRANCH_PREFIX = 'deps/sync-dev-versions-';
const GENERATED_DELIVERY_BRANCH_PREFIXES = [SYNC_BRANCH_PREFIX, DEV_TOOL_SYNC_BRANCH_PREFIX];
const POST_PUSH_REVIEW_WINDOW_MS = 7 * 60 * 1000;
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

function isStableSyncBranchName(value) {
  const branch = branchNameFromRef(value);
  return branch === SYNC_CANDIDATE_BRANCH || branch === SYNC_DELIVERY_BRANCH;
}

function candidateEvidenceAllowsMutation({ branch, evidenceOnly, authorized } = {}) {
  return branchNameFromRef(branch) !== syncBranchForHash('candidate')
    || Boolean(evidenceOnly)
    || Boolean(authorized);
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

function generatedDeliveryRequiresVerifiedHead(value) {
  return generatedDeliveryLane(value) === 'sync';
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
  if (!lane) {
    return {
      disposition: 'owner-decision',
      blocker_owner: 'source',
      next_command: 'owner-decision-required',
    };
  }
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
    const failureScope = String(checkState.failure_scope || '').trim().toLowerCase();
    if (failureScope === 'shared-source' || checkState.shared_source === true) {
      return {
        disposition: 'shared-source-failure',
        blocker_owner: 'source',
        next_command: 'repair-shared-source-and-redeliver',
      };
    }
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

function evaluatePostPushReviewWindow(
  pr = {},
  now = new Date().toISOString(),
  windowMs = POST_PUSH_REVIEW_WINDOW_MS,
) {
  const headSha = String(pr?.head?.sha || '').trim();
  const observedHeadSha = String(
    pr?.head?.observed_sha || pr?.head?.observedSha || '',
  ).trim();
  const observationMatchesHead = Boolean(headSha && observedHeadSha === headSha);
  const pushTimestamps = (
    observationMatchesHead
      ? [pr?.head?.observed_at, pr?.head?.observedAt]
      : []
  )
    .map((value) => new Date(value || '').getTime())
    .filter(Number.isFinite);
  const fallbackTimestamps = [
    pr?.updated_at,
    pr?.updatedAt,
    pr?.created_at,
    pr?.createdAt,
  ]
    .map((value) => new Date(value || '').getTime())
    .filter(Number.isFinite);
  const observedAt = new Date(now).getTime();
  // A producer-recorded exact-head observation is the push-specific anchor. PR
  // updated_at also changes for body edits, labels, comments, and thread
  // resolution; using it after an exact-head observation is available would
  // restart the post-push window without a push. A mismatched/missing head
  // observation falls back conservatively to PR lifecycle timestamps.
  const timestamps = pushTimestamps.length > 0 ? pushTimestamps : fallbackTimestamps;
  if (timestamps.length === 0 || !Number.isFinite(observedAt)) {
    return {
      ready: false,
      reason: 'missing_review_window_timestamp',
      eligible_at: '',
    };
  }
  const anchor = Math.max(...timestamps);
  const eligibleAt = anchor + Number(windowMs);
  const ready = observedAt >= eligibleAt;
  return {
    ready,
    reason: ready ? 'review_window_elapsed' : 'review_window_pending',
    anchor_at: new Date(anchor).toISOString(),
    eligible_at: new Date(eligibleAt).toISOString(),
  };
}

function normalizeReviewerId(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\[bot\]$/, '');
}

function reviewerProfileForLogin(login, reviewerProfiles = []) {
  const normalizedLogin = normalizeReviewerId(login);
  return (reviewerProfiles || []).find((profile) =>
    (profile.logins || []).some((candidate) => normalizeReviewerId(candidate) === normalizedLogin),
  )?.id || '';
}

function reviewerStatusLineMatches(body = '', patterns = []) {
  const statusLines = String(body || '')
    .split(/\r?\n/)
    .map((line) => line
      .trim()
      .replace(/^(?:[>\s]*[-*#`_:]+|[>\s]*[⚠️ℹ️🚫⏭️]+)\s*/u, '')
      .toLowerCase())
    .filter(Boolean);
  return (patterns || []).some((pattern) => {
    const literal = String(pattern || '').trim().toLowerCase();
    if (!literal) return false;
    return statusLines.some((line) => (
      line === literal
      || line.startsWith(`${literal}:`)
      || line.startsWith(`${literal} -`)
      || line.startsWith(`${literal} —`)
      || line.startsWith(`${literal}.`)
      || line.startsWith(`${literal} because `)
      || line.startsWith(`${literal} due to `)
      || line.startsWith(`${literal} for `)
    ));
  });
}

function isReviewerCapacitySignal(body = '', capacityPatterns = []) {
  return reviewerStatusLineMatches(body, capacityPatterns);
}

function isReviewerNonResponseSignal(body = '', nonResponsePatterns = []) {
  return reviewerStatusLineMatches(body, nonResponsePatterns);
}

function generatedPrsForSyncSelector(prs = [], syncHash = '') {
  const normalized = normalizeSyncHash(syncHash);
  if (!normalized) return prs;
  // A sync hash names a sync/workflows-* branch. Dev-tool deliveries share
  // Maint 71 but are a separate generated lane; their presence must not turn
  // an otherwise complete workflow-delivery pass into target_missing.
  return prs.filter((pr) => generatedDeliveryLane(pr?.head?.ref) === 'sync');
}

function evaluateReviewerSettlement({
  reviewStartedAt = '',
  now = new Date().toISOString(),
  configuredReviewers = [],
  respondedReviewers = [],
  unavailableReviewers = [],
  minimumResponses = 1,
  quietPeriodMs = POST_PUSH_REVIEW_WINDOW_MS,
  maxWaitMs = 15 * 60 * 1000,
} = {}) {
  const startedAt = new Date(reviewStartedAt).getTime();
  const observedAt = new Date(now).getTime();
  if (!Number.isFinite(startedAt) || !Number.isFinite(observedAt)) {
    return { ready: false, reason: 'missing_review_started_at', eligible_at: '' };
  }
  const configured = new Set((configuredReviewers || []).map(normalizeReviewerId).filter(Boolean));
  const responded = new Set((respondedReviewers || []).map(normalizeReviewerId).filter(Boolean));
  const unavailable = new Set((unavailableReviewers || []).map(normalizeReviewerId).filter(Boolean));
  const parsedQuietPeriodMs = Number(quietPeriodMs);
  const parsedMaxWaitMs = Number(maxWaitMs);
  const parsedMinimumResponses = Number(minimumResponses);
  const safeQuietPeriodMs = Number.isFinite(parsedQuietPeriodMs) && parsedQuietPeriodMs >= 0
    ? parsedQuietPeriodMs
    : POST_PUSH_REVIEW_WINDOW_MS;
  const safeMaxWaitMs = Number.isFinite(parsedMaxWaitMs) && parsedMaxWaitMs >= 0
    ? parsedMaxWaitMs
    : 15 * 60 * 1000;
  const safeMinimumResponses = Number.isFinite(parsedMinimumResponses) && parsedMinimumResponses >= 0
    ? parsedMinimumResponses
    : 1;
  const quietEligibleAt = startedAt + safeQuietPeriodMs;
  const timeoutEligibleAt = startedAt + Math.max(safeMaxWaitMs, safeQuietPeriodMs);
  if (observedAt < quietEligibleAt) {
    return {
      ready: false,
      reason: 'review_quiet_period_pending',
      eligible_at: new Date(quietEligibleAt).toISOString(),
      responded: [...responded].sort(),
      unavailable: [...unavailable].sort(),
    };
  }
  if (responded.size >= safeMinimumResponses) {
    return {
      ready: true,
      reason: 'review_quorum_met',
      degraded: false,
      responded: [...responded].sort(),
      unavailable: [...unavailable].sort(),
    };
  }
  const everyConfiguredUnavailable = configured.size > 0
    && [...configured].every((reviewer) => unavailable.has(reviewer));
  if (everyConfiguredUnavailable) {
    return {
      ready: true,
      reason: 'review_capacity_degraded',
      degraded: true,
      responded: [...responded].sort(),
      unavailable: [...unavailable].sort(),
    };
  }
  if (observedAt >= timeoutEligibleAt) {
    return {
      ready: true,
      reason: 'review_timeout_degraded',
      degraded: true,
      responded: [...responded].sort(),
      unavailable: [...unavailable].sort(),
    };
  }
  return {
    ready: false,
    reason: 'review_quorum_pending',
    eligible_at: new Date(timeoutEligibleAt).toISOString(),
    responded: [...responded].sort(),
    unavailable: [...unavailable].sort(),
  };
}

function requiresStrictGateBranchUpdate({ pr = {}, requiredContexts = [], willMerge = false } = {}) {
  const requiredCount = requiredContexts instanceof Set
    ? requiredContexts.size
    : Array.isArray(requiredContexts)
      ? requiredContexts.length
      : 0;
  return Boolean(
    willMerge
    && requiredCount > 0
    && String(pr.mergeable_state || '').toLowerCase() === 'behind'
  );
}

function isBlockingSyncSystemFailure(status) {
  return [
    'branch_update_failed',
    'error',
    'head_commit_unverified',
    'merge_failed',
    'pr_refresh_failed',
    'stale_close_failed',
    'target_missing',
  ].includes(status);
}

function commitSignatureAllowsMerge(signature = {}) {
  return Boolean(
    signature?.isValid === true
    && signature?.state === 'VALID'
  );
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

function rulesetRefPatternMatches(pattern, branch) {
  const normalizedPattern = String(pattern || '').trim();
  const normalizedBranch = branchNameFromRef(branch);
  if (!normalizedPattern || !normalizedBranch) return false;
  if (normalizedPattern === '~ALL' || normalizedPattern === '~DEFAULT_BRANCH') return true;
  const ref = `refs/heads/${normalizedBranch}`;
  if (normalizedPattern === normalizedBranch || normalizedPattern === ref) return true;
  const globPattern = normalizedPattern.startsWith('refs/')
    ? normalizedPattern
    : `refs/heads/${normalizedPattern}`;
  const escaped = globPattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*\*/g, '\u0000')
    .replace(/\*/g, '[^/]*')
    .replace(/\?/g, '[^/]')
    .replace(/\u0000/g, '.*');
  return new RegExp(`^${escaped}$`).test(ref);
}

function requiredContextsFromRulesets(rulesets = [], branch = '') {
  const requiredContexts = new Set();
  for (const ruleset of rulesets || []) {
    if (String(ruleset?.enforcement || '').toLowerCase() !== 'active') continue;
    const refName = ruleset?.conditions?.ref_name || {};
    const excludes = Array.isArray(refName.exclude) ? refName.exclude : [];
    if (excludes.some((pattern) => rulesetRefPatternMatches(pattern, branch))) continue;
    const includes = Array.isArray(refName.include) ? refName.include : [];
    if (
      includes.length > 0 &&
      !includes.some((pattern) => rulesetRefPatternMatches(pattern, branch))
    ) {
      continue;
    }
    for (const rule of ruleset.rules || []) {
      if (rule?.type !== 'required_status_checks') continue;
      for (const check of rule?.parameters?.required_status_checks || []) {
        const contextName = String(check?.context || '').trim();
        if (contextName) requiredContexts.add(contextName);
      }
    }
  }
  return requiredContexts;
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

// Workflows-owned / template-propagated gates. Consumer app test names stay repo-local.
// Keep these identities deliberately narrow: an aggregate Gate only reports that a
// consumer required context failed; it does not identify the failed Gate leg.
const SHARED_SOURCE_CHECK_RE =
  /^(?:health\s+\d+(?:\s|$)|consumer\s+sync(?:\s|$)|sync\s+templates?(?:\s|$))/i;

function isSharedSourceFailedCheck(check = {}) {
  const name = String(check?.name || check?.context || '').trim();
  const explicitScope = String(check?.failure_scope || check?.source || '').trim().toLowerCase();
  return check?.shared_source === true ||
    explicitScope === 'shared-source' ||
    (Boolean(name) && SHARED_SOURCE_CHECK_RE.test(name));
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
    const failure_scope = failed.some(isSharedSourceFailedCheck) ? 'shared-source' : 'repo-local';
    return { status: 'checks_failed', failure_scope, failed, pending: [] };
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
    const activeLane = generatedDeliveryLane(active?.head?.ref);
    return {
      active,
      stale: active
        ? ordered.filter(
          (pr) => pr.number !== active.number
            && generatedDeliveryLane(pr?.head?.ref) === activeLane,
        )
        : [],
      expectedBranch: '',
      missingExpected: false,
    };
  }

  const active = ordered.find((pr) => pr.head && pr.head.ref === expectedBranch) || null;
  const expectedLane = generatedDeliveryLane(expectedBranch);
  return {
    active,
    stale: active
      ? ordered.filter(
        (pr) => pr.number !== active.number
          && generatedDeliveryLane(pr?.head?.ref) === expectedLane,
      )
      : [],
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

function selectLatestMergedCandidatePr(prs, trustedActors = []) {
  const mergedCandidates = (prs || []).filter(
    (pr) =>
      pr?.head?.ref === `${SYNC_BRANCH_PREFIX}candidate`
      && Boolean(pr?.merged_at || pr?.mergedAt)
      && isTrustedGeneratedDeliveryPr(pr, trustedActors),
  );
  return mergedCandidates.sort((a, b) => {
    const aTime = new Date(a.merged_at || a.mergedAt || a.updated_at || 0).getTime();
    const bTime = new Date(b.merged_at || b.mergedAt || b.updated_at || 0).getTime();
    return bTime - aTime;
  })[0] || null;
}

function validateCanaryEvidence(evidence = [], expectedRepos = []) {
  const expected = new Set((expectedRepos || []).map((repo) => String(repo || '').trim()).filter(Boolean));
  const rowsByRepo = new Map();
  const errors = [];
  for (const row of evidence || []) {
    const repo = String(row?.repo || '').trim();
    if (!expected.has(repo)) {
      errors.push(`unexpected_canary_evidence:${repo || '<missing-repo>'}`);
      continue;
    }
    if (rowsByRepo.has(repo)) {
      errors.push(`duplicate_canary_evidence:${repo}`);
      continue;
    }
    rowsByRepo.set(repo, row);
  }
  for (const repo of expected) {
    const row = rowsByRepo.get(repo);
    if (!row) {
      errors.push(`missing_canary_evidence:${repo}`);
      continue;
    }
    if (row.required_check_state !== 'success') {
      errors.push(`required_checks_not_green:${repo}`);
    }
    if (row.active_review_thread_count !== 0) {
      errors.push(`active_review_debt:${repo}`);
    }
  }
  const planIds = new Set(
    [...rowsByRepo.values()].map((row) => String(row?.plan_id || '').trim()).filter(Boolean),
  );
  if (planIds.size !== 1) {
    errors.push('missing_or_mixed_canary_plan');
  }
  return {
    ok: errors.length === 0,
    errors,
    plan_id: planIds.size === 1 ? [...planIds][0] : '',
  };
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
    candidate_evidence_required: 0,
    review_window_pending: 0,
    review_window_started: 0,
    reviewer_settlement_pending: 0,
    delivery_review_not_started: 0,
    delivery_sealed_checks_pending: 0,
    sealed_head_mismatch: 0,
    stable_base_refresh_required: 0,
    head_changed: 0,
    head_commit_unverified: 0,
    review_blocked: 0,
    ready: 0,
    dry_run_merge: 0,
    dry_run_review_start: 0,
    dry_run_seal: 0,
    merge_blocked_runtime_ac: 0,
    merged: 0,
    merge_failed: 0,
    delivery_contract_blocked: 0,
    evidence_recovered: 0,
    error: 0,
  };
  for (const result of results || []) {
    if (Object.prototype.hasOwnProperty.call(counts, result.status)) {
      counts[result.status] += 1;
    }
  }
  return counts;
}

function deriveHandoffCheckState(result = {}) {
  const explicit = String(result.check_state || '').trim();
  if (explicit) return explicit;
  const status = String(result.status || '');
  if (status === 'checks_pending') return 'checks_pending';
  if (
    status === 'candidate_evidence_required'
    || status === 'review_window_pending'
    || status === 'review_window_started'
    || status === 'reviewer_settlement_pending'
    || status === 'delivery_review_not_started'
    || status === 'delivery_sealed_checks_pending'
    || status === 'sealed_head_mismatch'
    || status === 'stable_base_refresh_required'
    || status === 'head_changed'
  ) {
    return 'checks_pending';
  }
  if (status === 'checks_failed' || status === 'head_commit_unverified') {
    return 'checks_failed';
  }
  if (
    status === 'ready'
    || status === 'dry_run_merge'
    || status === 'dry_run_seal'
    || status === 'merged'
    || status === 'review_blocked'
    || status === 'merge_blocked_runtime_ac'
  ) {
    return 'ready';
  }
  if (status === 'stale_closed' || status === 'delivery_contract_blocked') {
    return 'not-applicable';
  }
  return status || 'unknown';
}

function deriveHandoffReviewState(result = {}) {
  const explicit = String(result.review_state || '').trim();
  if (explicit) return explicit;
  const status = String(result.status || '');
  const threadCount = Number(result.active_review_thread_count);
  if (status === 'review_blocked' || (Number.isFinite(threadCount) && threadCount > 0)) {
    return 'blocked';
  }
  if (status === 'stale_closed' || status === 'delivery_contract_blocked') {
    return 'not-applicable';
  }
  return 'clear';
}

function buildDeliveryHandoff(result = {}) {
  if (!result.pr) return null;
  const status = String(result.status || '');
  // Branch-delete rows are companions to the merged row; emit one terminal handoff only.
  if (status === 'branch_deleted' || status === 'branch_delete_failed') {
    return null;
  }
  const headSha = String(result.head_sha || '');
  const deliveryGeneration = String(result.delivery_generation || '');
  if (!headSha || !deliveryGeneration) return null;

  let disposition = String(result.delivery_disposition || status || '');
  let blockerOwner = String(result.blocker_owner || '');
  let nextCommand = String(result.next_command || '');
  let checkState = deriveHandoffCheckState(result);
  let reviewState = deriveHandoffReviewState(result);

  // After a successful merge/close, rewrite pre-merge restart fields so consumers
  // do not keep seeing merge-current-delivery for an already-terminal PR.
  if (status === 'merged') {
    disposition = 'merged';
    blockerOwner = 'none';
    nextCommand = 'none';
    checkState = checkState === 'unknown' ? 'ready' : checkState;
    reviewState = reviewState === 'not-applicable' ? 'clear' : reviewState;
  } else if (status === 'stale_closed') {
    if (!disposition || disposition === 'stale_closed') {
      disposition = 'closed';
    }
    blockerOwner = 'none';
    nextCommand = 'none';
  }

  if (!disposition || !blockerOwner || !nextCommand || !checkState || !reviewState) {
    return null;
  }

  return {
    schema: 'workflows-generated-delivery-handoff/v1',
    repository: `${result.owner || ''}/${result.repo || ''}`.replace(/^\//, ''),
    pr: Number(result.pr),
    branch: branchNameFromRef(result.branch),
    head_sha: headSha,
    delivery_generation: deliveryGeneration,
    lane: generatedDeliveryLane(result.branch),
    disposition,
    blocker_owner: blockerOwner,
    next_command: nextCommand,
    check_state: checkState,
    review_state: reviewState,
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
  SYNC_CANDIDATE_BRANCH,
  SYNC_DELIVERY_BRANCH,
  DEV_TOOL_SYNC_BRANCH_PREFIX,
  GENERATED_DELIVERY_BRANCH_PREFIXES,
  branchNameFromRef,
  classifyGeneratedPr,
  classifySyncPrChecks,
  candidateEvidenceAllowsMutation,
  collectDeletableSyncBranches,
  generatedDeliveryLane,
  generatedDeliveryRequiresVerifiedHead,
  generatedPrsForSyncSelector,
  isGeneratedDeliveryBranchName,
  isStableSyncBranchName,
  isSyncBranchName,
  isTrustedGeneratedDeliveryPr,
  isTrustedSyncPr,
  isBlockingSyncSystemFailure,
  commitSignatureAllowsMerge,
  evaluatePostPushReviewWindow,
  evaluateReviewerSettlement,
  isReviewerCapacitySignal,
  isReviewerNonResponseSignal,
  normalizeReviewerId,
  reviewerProfileForLogin,
  requiresStrictGateBranchUpdate,
  normalizeSyncHash,
  syncBranchForHash,
  parseBooleanInput,
  requiredContextsFromRulesets,
  rulesetRefPatternMatches,
  selectSyncPrGatingChecks,
  sortSyncPrs,
  selectActiveSyncPr,
  selectMergeEligibleSyncPr,
  selectLatestMergedCandidatePr,
  validateCanaryEvidence,
  summarizeResults,
  buildMergeReport,
  buildDeliveryHandoff,
  buildMarkdownSummary,
};
