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

function formatIssueBody(report, options = {}) {
  const runUrl = options.runUrl || '';
  const runNumber = options.runNumber || '';
  const runLink = runUrl && runNumber ? `[Run #${runNumber}](${runUrl})` : runUrl || 'current run';

  return [
    '## Consumer Repo Drift Detected',
    '',
    'One or more consumer repos have drifted from the Workflows templates or manifest entries.',
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
    '### Notes',
    '- Files marked with `sync_mode: create_only` are excluded from this check.',
    '- Workflows-Integration-Tests is validated separately by Health 67.',
  ].join('\n');
}

function formatIssueComment(report, options = {}) {
  const runUrl = options.runUrl || '';
  const runNumber = options.runNumber || '';
  const runLink = runUrl && runNumber ? `[run #${runNumber}](${runUrl})` : runUrl || 'latest run';

  return [
    `Drift still detected in ${runLink}.`,
    '',
    `Counts: ${countsLine(report)}`,
    '',
    'Highest-impact repos:',
    ...formatRepoGaps(report, 5),
    '',
    'Follow-up:',
    ...followUpLines(report),
  ].join('\n');
}

module.exports = {
  countsLine,
  formatIssueBody,
  formatIssueComment,
  formatPrefixCounts,
  formatRepoGaps,
};
