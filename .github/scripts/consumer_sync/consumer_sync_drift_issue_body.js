const ISSUE_MARKER_SCHEMA = 'consumer-sync-drift-issue/v1';
const ISSUE_MARKER_PREFIX = '<!-- consumer-sync-drift:v1 ';
const ISSUE_MARKER_RE = /<!-- consumer-sync-drift:v1 \{[\s\S]*?\} -->/;
const GENERATED_BODY_RE = /^\s*## Consumer Repo Drift Detected\b/;

function countsLine(report) {
  const counts = report && report.counts ? report.counts : {};
  return `drift=${counts.drift || 0}, missing=${counts.missing || 0}, errors=${counts.errors || 0}, obsolete=${counts.obsolete || 0}, unmeasured_create_only=${counts.unmeasured_create_only || 0}`;
}

function unmeasuredCreateOnlyTargets(report) {
  const positions = Array.isArray(report && report.unmeasured_create_only)
    ? report.unmeasured_create_only
    : [];
  return [...new Set(positions.map((position) => String(position).split(': ', 2)[1]).filter(Boolean))].sort();
}

function formatRepoGaps(report, limit = 10) {
  const gaps = Array.isArray(report && report.top_repo_gaps) ? report.top_repo_gaps : [];
  if (gaps.length === 0) {
    return ['- No per-repo gaps were reported.'];
  }
  return gaps.slice(0, limit).map((item) => {
    return `- ${item.repo}: total=${item.total || 0}, drift=${item.drift || 0}, ` +
      `missing=${item.missing || 0}, errors=${item.errors || 0}, obsolete=${item.obsolete || 0}`;
  });
}

function formatPrefixCounts(report, limit = 8) {
  const groups = report && report.path_prefix_counts ? report.path_prefix_counts : {};
  const lines = [];
  for (const category of ['drift', 'missing', 'errors', 'obsolete']) {
    const prefixes = groups[category] || {};
    const rendered = Object.entries(prefixes)
      .slice(0, limit)
      .map(([prefix, count]) => `${prefix}=${count}`)
      .join(', ');
    if (rendered) {
      lines.push(`- ${category}: ${rendered}`);
    }
  }
  return lines.length ? lines : ['- No path-prefix details were reported.'];
}

const DEFAULT_LEASE_HOURS = 36;
const MAINT_68_RUNS_URL =
  'https://github.com/stranske/Workflows/actions/workflows/maint-68-sync-consumer-repos.yml';

function parseIssueMarker(body) {
  const match = String(body || '').match(ISSUE_MARKER_RE);
  if (!match) {
    return null;
  }
  try {
    const payload = JSON.parse(match[0].slice(ISSUE_MARKER_PREFIX.length, -' -->'.length));
    return payload && payload.schema === ISSUE_MARKER_SCHEMA ? payload : null;
  } catch (error) {
    return null;
  }
}

function validTimestamp(value, nowMs) {
  const parsed = Date.parse(String(value || ''));
  return Number.isFinite(parsed) && parsed <= nowMs ? parsed : null;
}

/**
 * Split drift into what an open delivery PR already covers and what nothing covers.
 *
 * Maint 68 is the drain. A repo whose drift waits for the next Maint 68 delivery
 * (`pending_delivery`: main moved after the last delivery) counts with the covered ones.
 * Uncovered drift younger than the coverage lease is still being delivered and needs
 * nobody; only uncovered drift older than the lease is blocking. The report decides
 * both: each state carries `blocking`, and `uncovered_since` is measured from when
 * Maint 68 first delivered the current plan. Older reports without those fields fall
 * back to this issue's own marker, where a new episode starts every repo at "now".
 * Returns `measured: false` when the report has no per-repo states, so "unmeasured" can
 * never read as "zero uncovered".
 */
function coverageLedger(report, options = {}) {
  const remediation = report && report.sync_remediation ? report.sync_remediation : {};
  const leaseHours = Number(remediation.coverage_lease_hours) > 0
    ? Number(remediation.coverage_lease_hours)
    : DEFAULT_LEASE_HOURS;
  const nowMs = options.now ? Date.parse(options.now) : Date.now();
  const repoStates = remediation.repo_states;
  const globalErrors = Array.isArray(remediation.global_errors) ? remediation.global_errors : [];
  const unmeasured = (reason) => ({
    measured: false, reason, leaseHours, covered: [], uncovered: [], blocking: [], draining: [], uncoveredSince: {},
  });
  if (!repoStates || typeof repoStates !== 'object' || Array.isArray(repoStates)) {
    return unmeasured('the drift report has no per-repo remediation states');
  }
  // A comparison that failed globally (for example an empty consumer roster) compared
  // nothing; its empty or blocked states must not read as a drained fleet.
  if (globalErrors.length > 0) {
    return unmeasured(`the comparison failed: ${globalErrors.slice(0, 3).join('; ')}`);
  }
  if (Object.keys(repoStates).length === 0) {
    return unmeasured('the drift report compared no repositories');
  }
  const previous = options.previousMarker && options.previousMarker.coverage
    ? options.previousMarker.coverage.uncovered_since || {}
    : {};
  const covered = [];
  const uncovered = [];
  const uncoveredSince = {};
  for (const repo of Object.keys(repoStates).sort()) {
    const entry = repoStates[repo] || {};
    const state = String(entry.state || 'unknown');
    if (state === 'converged') {
      continue;
    }
    if (state === 'covered' || state === 'pending_delivery') {
      covered.push({ repo, pr: entry.pr || null, state });
      continue;
    }
    const sinceMs = validTimestamp(entry.uncovered_since, nowMs)
      ?? validTimestamp(previous[repo], nowMs)
      ?? nowMs;
    const since = new Date(sinceMs).toISOString();
    uncoveredSince[repo] = since;
    const ageHours = (nowMs - sinceMs) / 3600000;
    // The report's own verdict wins. Without one, a stale PR has already outlived its own
    // lease without moving: blocking at once.
    const blocking = typeof entry.blocking === 'boolean'
      ? entry.blocking
      : state === 'stale' || ageHours >= leaseHours;
    uncovered.push({
      repo,
      state,
      reason: String(entry.reason || ''),
      pr: entry.pr || null,
      since,
      ageHours,
      blocking,
    });
  }
  return {
    measured: true,
    leaseHours,
    covered,
    uncovered,
    blocking: uncovered.filter((item) => item.blocking),
    draining: uncovered.filter((item) => !item.blocking),
    uncoveredSince,
  };
}

function coverageLine(ledger) {
  if (!ledger.measured) {
    return `**Coverage:** unmeasured (${ledger.reason})`;
  }
  const pending = ledger.covered.filter((item) => item.state === 'pending_delivery').length;
  return `**Coverage:** covered by an open delivery PR: ${ledger.covered.length - pending}, ` +
    `waiting for the next Maint 68 delivery: ${pending}, ` +
    `uncovered: ${ledger.uncovered.length} ` +
    `(blocking, past the ${ledger.leaseHours}h lease: ${ledger.blocking.length}; ` +
    `draining, within the lease: ${ledger.draining.length})`;
}

function blockingActionLine(item) {
  const age = `${Math.floor(item.ageHours)}h`;
  if (item.state === 'stale' && item.pr) {
    const prLabel = item.pr.number ? `${item.repo}#${item.pr.number}` : item.repo;
    return `- \`${prLabel}\`: the delivery PR has not moved for over the lease. ` +
      'Read its checks and the Maint 71 / Maint 82 runs for it.';
  }
  if (item.state === 'blocked') {
    return `- \`${item.repo}\`: comparison blocked for ${age} (${item.reason || 'unknown reason'}). ` +
      'Read the latest Health 68 run log for this repo.';
  }
  return `- \`${item.repo}\`: drift with no delivery PR for the current plan for ${age}, ` +
    `although Maint 68 runs daily. Read its latest run for this repo: ${MAINT_68_RUNS_URL}`;
}

function requiredActionLines(ledger) {
  if (!ledger.measured) {
    return [
      `- Coverage could not be measured (${ledger.reason}). Read the \`consumer-sync-drift-report\` ` +
        'artifact and the Health 68 run log; an unmeasured comparison is a defect, not a clean fleet.',
    ];
  }
  if (ledger.blocking.length === 0) {
    return ['- None. Uncovered drift younger than the lease is still being delivered by the daily Maint 68 run.'];
  }
  return ledger.blocking.map(blockingActionLine);
}

function formatUncovered(ledger, limit = 20) {
  return ledger.uncovered.slice(0, limit).map((item) => {
    const kind = item.blocking ? 'blocking' : 'draining';
    return `- ${item.repo}: ${item.state}, uncovered since ${item.since} (${Math.floor(item.ageHours)}h, ${kind})`;
  });
}

function formatOpenSyncPrs(report, limit = 10) {
  const remediation = report && report.sync_remediation ? report.sync_remediation : {};
  const prs = Array.isArray(remediation.open_prs) ? remediation.open_prs : [];
  if (prs.length === 0) {
    return [];
  }
  return prs.slice(0, limit).map((item) => {
    const repo = item.repo || 'unknown';
    const number = item.number || '';
    const branch = item.branch || '';
    const url = item.url || '';
    const prLabel = number ? `${repo}#${number}` : repo;
    return `- ${prLabel}: \`${branch}\`${url ? ` (${url})` : ''}`;
  });
}

function limitedArray(value, limit) {
  return Array.isArray(value) ? value.slice(0, limit) : [];
}

function compactMarkerPayload(report, options = {}) {
  const counts = report && report.counts ? report.counts : {};
  return {
    schema: ISSUE_MARKER_SCHEMA,
    updated_at: options.updatedAt || new Date().toISOString(),
    run_id: options.runId || '',
    run_number: options.runNumber || '',
    run_url: options.runUrl || '',
    artifact: 'consumer-sync-drift-report',
    status: report && report.status ? report.status : 'unknown',
    repo_count: report && Number.isInteger(report.repo_count) ? report.repo_count : 0,
    counts: {
      drift: counts.drift || 0,
      missing: counts.missing || 0,
      errors: counts.errors || 0,
      obsolete: counts.obsolete || 0,
      unmeasured_create_only: counts.unmeasured_create_only || 0,
    },
    top_repo_gaps: limitedArray(report && report.top_repo_gaps, 10),
    path_prefix_counts: report && report.path_prefix_counts ? report.path_prefix_counts : {},
    sync_remediation: report && report.sync_remediation ? {
      state: report.sync_remediation.state || 'unknown',
      open_pr_count: report.sync_remediation.open_pr_count || 0,
      repo_count: report.sync_remediation.repo_count || 0,
      latest_open_pr: report.sync_remediation.latest_open_pr || null,
      stale_open_pr_count: report.sync_remediation.stale_open_pr_count || 0,
      open_prs: limitedArray(report.sync_remediation.open_prs, 10),
      lookup_errors: limitedArray(report.sync_remediation.lookup_errors, 10),
    } : {
      state: 'unknown',
      open_pr_count: 0,
      repo_count: 0,
      latest_open_pr: null,
      stale_open_pr_count: 0,
      open_prs: [],
      lookup_errors: [],
    },
    coverage: (() => {
      const ledger = options.ledger || coverageLedger(report, options);
      // Unmeasured is null, never 0: only a measured zero is good news.
      const count = (items) => (ledger.measured ? items.length : null);
      return {
        measured: ledger.measured,
        lease_hours: ledger.leaseHours,
        covered: count(ledger.covered),
        uncovered: count(ledger.uncovered),
        blocking: count(ledger.blocking),
        draining: count(ledger.draining),
        uncovered_since: ledger.uncoveredSince,
      };
    })(),
  };
}

function formatIssueMarker(report, options = {}) {
  return `${ISSUE_MARKER_PREFIX}${JSON.stringify(compactMarkerPayload(report, options))} -->`;
}

function formatIssueBody(report, options = {}) {
  const runUrl = options.runUrl || '';
  const runNumber = options.runNumber || '';
  const runLink = runUrl && runNumber ? `[Run #${runNumber}](${runUrl})` : runUrl || 'current run';
  const openSyncPrs = formatOpenSyncPrs(report);

  const remediation = report && report.sync_remediation ? report.sync_remediation : {};
  const isCovered = report && report.status === 'covered';
  const ledger = coverageLedger(report, options);
  const markerOptions = { ...options, ledger };
  const uncoveredLines = formatUncovered(ledger);
  const lines = [
    '## Consumer Repo Drift Detected',
    '',
    '> **Transient alert** — Health 68 refreshes this issue while drift is actionable and closes it automatically on the next clean run.',
    '',
    isCovered
      ? 'Detected drift is covered by current, unexpired compiler-plan sync PRs; no alert comment is needed.'
      : 'One or more consumer repos have actionable drift from the Workflows templates or manifest entries.',
    '',
    `**Check Details:** ${runLink}`,
    `**Counts:** ${countsLine(report)}`,
    coverageLine(ledger),
    '',
    '### Highest-impact repos',
    ...formatRepoGaps(report),
    '',
    '### Path prefixes',
    ...formatPrefixCounts(report),
    '',
    '### Required Actions',
    ...requiredActionLines(ledger),
    '',
    '- Exact file paths are in the `consumer-sync-drift-report` artifact.',
    '- Health 68 closes this issue automatically after a clean or fully covered comparison.',
    '',
  ];
  if (uncoveredLines.length > 0) {
    lines.splice(lines.indexOf('### Required Actions'), 0, '### Uncovered repos', ...uncoveredLines, '');
  }
  if (remediation.expected_branch) {
    lines.splice(lines.indexOf('### Required Actions'), 0,
      '### Remediation state',
      `- Current plan branch: \`${remediation.expected_branch}\``,
      `- Coverage lease: ${remediation.coverage_lease_hours || 0} hours`,
      '');
  }
  if (openSyncPrs.length > 0) {
    lines.push(
      '### Open sync PRs',
      ...openSyncPrs,
      '',
    );
  }
  lines.push(
    '### Notes',
    `- Files marked with \`sync_mode: create_only\` are excluded from drift classification; ${report && report.counts ? report.counts.unmeasured_create_only || 0 : 0} positions are not measured (${unmeasuredCreateOnlyTargets(report).join(', ') || 'no affected targets'}).`,
    '- Workflows-Integration-Tests is validated separately by Health 67.',
    '',
    formatIssueMarker(report, markerOptions),
  );
  return lines.join('\n');
}

function mergeIssueBody(existingBody, report, options = {}) {
  const body = existingBody || '';
  const nextBody = formatIssueBody(report, options);
  const marker = formatIssueMarker(report, options);
  if (!body.trim() || GENERATED_BODY_RE.test(body)) {
    return nextBody;
  }
  if (ISSUE_MARKER_RE.test(body)) {
    return body.replace(ISSUE_MARKER_RE, marker);
  }
  return `${body.trimEnd()}\n\n${marker}`;
}

function formatIssueComment(report, options = {}) {
  if (report && report.status === 'covered') {
    return '';
  }
  const ledger = coverageLedger(report, options);
  if (ledger.measured && ledger.blocking.length === 0) {
    // Nothing needs a person; the refreshed body already carries the counts.
    return '';
  }
  const runUrl = options.runUrl || '';
  const runNumber = options.runNumber || '';
  const runLink = runUrl && runNumber ? `[run #${runNumber}](${runUrl})` : runUrl || 'latest run';
  const openSyncPrs = formatOpenSyncPrs(report, 5);

  const lines = [
    `Drift still detected in ${runLink}.`,
    '',
    `Counts: ${countsLine(report)}`,
    '',
    'Highest-impact repos:',
    ...formatRepoGaps(report, 5),
    '',
    coverageLine(ledger).replace(/\*\*/g, ''),
    '',
    'Required actions:',
    ...requiredActionLines(ledger),
  ];
  if (openSyncPrs.length > 0) {
    lines.push('', 'Open sync PRs:', ...openSyncPrs);
  }
  return lines.join('\n');
}

module.exports = {
  countsLine,
  coverageLedger,
  coverageLine,
  parseIssueMarker,
  compactMarkerPayload,
  formatOpenSyncPrs,
  formatIssueBody,
  formatIssueComment,
  formatIssueMarker,
  formatPrefixCounts,
  formatRepoGaps,
  mergeIssueBody,
};
