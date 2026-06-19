'use strict';

const REPORT_SCHEMA = 'workflows-sync-pr-merge/v1';
const SYNC_BRANCH_PREFIX = 'sync/workflows-';

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
      .filter(isSyncBranchName),
  );
  const closedBranches = new Set(
    (closedPullRequests || [])
      .map((pr) => branchNameFromRef(pr?.head?.ref || pr?.headRefName || pr?.branch))
      .filter(isSyncBranchName),
  );

  return (branches || [])
    .map((branch) => branchNameFromRef(branch?.name || branch?.ref || branch))
    .filter(isSyncBranchName)
    .filter((branch) => !openBranches.has(branch))
    .filter((branch) => closedBranches.has(branch))
    .sort();
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
    ready: 0,
    dry_run_merge: 0,
    merge_blocked_runtime_ac: 0,
    merged: 0,
    merge_failed: 0,
    error: 0,
  };
  for (const result of results || []) {
    if (Object.prototype.hasOwnProperty.call(counts, result.status)) {
      counts[result.status] += 1;
    }
  }
  return counts;
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
  branchNameFromRef,
  collectDeletableSyncBranches,
  isSyncBranchName,
  normalizeSyncHash,
  syncBranchForHash,
  parseBooleanInput,
  sortSyncPrs,
  selectActiveSyncPr,
  summarizeResults,
  buildMergeReport,
  buildMarkdownSummary,
};
