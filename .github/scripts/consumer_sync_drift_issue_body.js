const ISSUE_MARKER_SCHEMA = 'consumer-sync-drift-issue/v1';
const ISSUE_MARKER_PREFIX = '<!-- consumer-sync-drift:v1 ';
const ISSUE_MARKER_RE = /<!-- consumer-sync-drift:v1 \{[\s\S]*?\} -->/;
const GENERATED_BODY_RE = /^\s*## Consumer Repo Drift Detected\b/;

function countsLine(report) {
  const counts = report && report.counts ? report.counts : {};
  return `drift=${counts.drift || 0}, missing=${counts.missing || 0}, errors=${counts.errors || 0}, obsolete=${counts.obsolete || 0}`;
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

function followUpLines(report) {
  const followUp = report && report.follow_up ? report.follow_up : {};
  const lines = [];
  if (followUp.all_repos_command) {
    lines.push(`- All repos: \`${followUp.all_repos_command}\``);
  }
  if (followUp.targeted_repos_command) {
    lines.push(`- Top repos first: \`${followUp.targeted_repos_command}\``);
  }
  return lines.length ? lines : ['- Run Maint 68 Sync Consumer Repos from the Workflows repo.'];
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
  const followUp = report && report.follow_up ? report.follow_up : {};
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
    follow_up: {
      workflow: followUp.workflow || 'maint-68-sync-consumer-repos.yml',
      all_repos_command: followUp.all_repos_command || '',
      targeted_repos_command: followUp.targeted_repos_command || '',
    },
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
  const lines = [
    '## Consumer Repo Drift Detected',
    '',
    '> **Durable tracker** — see [`docs/ops/DURABLE_TRACKING_ISSUES.md`](https://github.com/stranske/Workflows/blob/main/docs/ops/DURABLE_TRACKING_ISSUES.md). The body below is regenerated each cycle by `health-68-consumer-sync-drift.yml`; auto-resolves on the next clean run.',
    '',
    isCovered
      ? 'Detected drift is covered by current, unexpired compiler-plan sync PRs; no tracker comment is needed.'
      : 'One or more consumer repos have actionable drift from the Workflows templates or manifest entries.',
    '',
    `**Check Details:** ${runLink}`,
    `**Counts:** ${countsLine(report)}`,
    '',
    '### Highest-impact repos',
    ...formatRepoGaps(report),
    '',
    '### Path prefixes',
    ...formatPrefixCounts(report),
    '',
    '### Required Actions',
    ...followUpLines(report),
    '- Review `consumer-sync-drift-report` for exact file paths.',
    '- Close this issue when Health 68 passes.',
    '',
  ];
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
    '- Files marked with `sync_mode: create_only` are excluded from this check.',
    '- Workflows-Integration-Tests is validated separately by Health 67.',
    '',
    formatIssueMarker(report, options),
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
    'Follow-up:',
    ...followUpLines(report),
  ];
  if (openSyncPrs.length > 0) {
    lines.push('', 'Open sync PRs:', ...openSyncPrs);
  }
  return lines.join('\n');
}

module.exports = {
  countsLine,
  compactMarkerPayload,
  formatOpenSyncPrs,
  formatIssueBody,
  formatIssueComment,
  formatIssueMarker,
  formatPrefixCounts,
  formatRepoGaps,
  mergeIssueBody,
};
