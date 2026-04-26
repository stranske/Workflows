const fs = require('fs');

const SUMMARY_SCHEMA = 'workflows-weekly-coverage-monitor/v1';

function cleanString(value) {
  if (value === null || value === undefined) return '';
  return String(value).trim();
}

function readJsonReport(filePath, label) {
  const cleanedPath = cleanString(filePath);
  if (!cleanedPath) {
    return {
      label,
      path: '',
      status: 'missing',
      error_message: 'report path was not configured',
      report: null,
    };
  }
  if (!fs.existsSync(cleanedPath)) {
    return {
      label,
      path: cleanedPath,
      status: 'missing',
      error_message: `report not found: ${cleanedPath}`,
      report: null,
    };
  }
  try {
    const report = JSON.parse(fs.readFileSync(cleanedPath, 'utf8'));
    return {
      label,
      path: cleanedPath,
      status: 'pass',
      error_message: '',
      report,
    };
  } catch (error) {
    return {
      label,
      path: cleanedPath,
      status: 'parse-error',
      error_message: error?.message || 'failed to parse report',
      report: null,
    };
  }
}

function normalizeStatus(value) {
  const status = cleanString(value).toLowerCase();
  return ['pass', 'warning', 'no-data', 'fail', 'missing', 'parse-error'].includes(status)
    ? status
    : 'unknown';
}

function reportBlockers(report = {}) {
  const enforcement = report.enforcement || {};
  return Array.isArray(enforcement.blockers) ? enforcement.blockers.map(cleanString).filter(Boolean) : [];
}

function policyBlockers(report = {}) {
  const enforcement = report.enforcement || {};
  return Array.isArray(enforcement.policy_blockers)
    ? enforcement.policy_blockers.map(cleanString).filter(Boolean)
    : [];
}

function normalizeMonitorArtifactSelection(selection = null) {
  if (!selection || typeof selection !== 'object' || Array.isArray(selection)) return null;
  const familyStatuses = Array.isArray(selection.terminal_priority_family_statuses)
    ? selection.terminal_priority_family_statuses
      .filter((status) => status && typeof status === 'object' && !Array.isArray(status))
      .map((status) => ({
        family: cleanString(status.family),
        status: cleanString(status.status),
        candidate_count: Number(status.candidate_count) || 0,
        selected_count: Number(status.selected_count) || 0,
      }))
      .filter((status) => status.family)
    : [];
  const missingFamilies = Array.isArray(selection.missing_terminal_priority_families)
    ? selection.missing_terminal_priority_families.map(cleanString).filter(Boolean)
    : [];
  return {
    status: cleanString(selection.status),
    candidate_terminal_artifact_count: Number(selection.candidate_terminal_artifact_count) || 0,
    selected_terminal_artifact_count: Number(selection.selected_terminal_artifact_count) || 0,
    missing_terminal_priority_families: missingFamilies,
    terminal_priority_family_statuses: familyStatuses,
  };
}

function summarizeReport(readResult) {
  const report = readResult.report || {};
  const enforcement = report.enforcement || {};
  const status = readResult.report ? normalizeStatus(report.status) : readResult.status;
  const coverageStatus = readResult.report
    ? normalizeStatus(report.coverage_status || report.status)
    : readResult.status;

  return {
    label: readResult.label,
    path: readResult.path,
    status,
    coverage_status: coverageStatus,
    mode: cleanString(report.mode || enforcement.mode),
    requested_mode: cleanString(report.requested_mode || enforcement.requested_mode),
    hard_block_active: Boolean(enforcement.hard_block_active),
    hard_block_eligible: Boolean(enforcement.hard_block_eligible),
    should_fail: Boolean(enforcement.should_fail || status === 'fail'),
    blockers: reportBlockers(report),
    policy_blockers: policyBlockers(report),
    artifact_selection: normalizeMonitorArtifactSelection(report.artifact_selection),
    read_status: readResult.status,
    error_message: cleanString(readResult.error_message),
  };
}

function overallStatus(monitors) {
  if (monitors.some((monitor) => monitor.should_fail || monitor.status === 'fail')) return 'fail';
  if (monitors.some((monitor) => ['missing', 'parse-error', 'warning', 'unknown'].includes(monitor.status))) {
    return 'warning';
  }
  if (monitors.length > 0 && monitors.every((monitor) => monitor.status === 'no-data')) return 'no-data';
  if (monitors.some((monitor) => monitor.status === 'no-data')) return 'warning';
  return 'pass';
}

function nextAction(status, monitors) {
  if (status === 'fail') return 'honor-approved-hard-block';
  if (monitors.some((monitor) => monitor.read_status !== 'pass')) return 'repair-monitor-report-input';
  if (monitors.some((monitor) => monitor.policy_blockers.length > 0)) return 'keep-warning-only-until-approved';
  if (status === 'warning') return 'inspect-monitor-warnings';
  if (status === 'no-data') return 'wait-for-telemetry';
  return 'continue-monitoring';
}

function buildCoverageMonitorSummary(options = {}) {
  const terminal = summarizeReport(readJsonReport(options.terminal_report, 'terminal-disposition'));
  const botAuth = summarizeReport(readJsonReport(options.bot_auth_report, 'bot-comment-auth'));
  const monitors = [terminal, botAuth];
  if (cleanString(options.pr_source_context_report)) {
    monitors.push(
      summarizeReport(readJsonReport(options.pr_source_context_report, 'pr-source-context'))
    );
  }
  const status = overallStatus(monitors);
  const hardBlockActive = monitors.some((monitor) => monitor.hard_block_active);
  const shouldFail = monitors.some((monitor) => monitor.should_fail);
  const policyBlockerCount = monitors.reduce(
    (total, monitor) => total + monitor.policy_blockers.length,
    0
  );

  return {
    schema: SUMMARY_SCHEMA,
    status,
    generated_at: cleanString(options.generated_at) || new Date().toISOString(),
    hard_block_active: hardBlockActive,
    should_fail: shouldFail,
    warning_only: !hardBlockActive,
    policy_blocker_count: policyBlockerCount,
    next_action: nextAction(status, monitors),
    monitors,
  };
}

function formatMonitorMarkdown(summary) {
  const lines = [
    '## Weekly Coverage Monitor Contract',
    '',
    `- Schema: ${summary.schema}`,
    `- Status: ${summary.status}`,
    `- Warning-only: ${summary.warning_only}`,
    `- Hard block active: ${summary.hard_block_active}`,
    `- Should fail: ${summary.should_fail}`,
    `- Policy blockers: ${summary.policy_blocker_count}`,
    `- Next action: ${summary.next_action}`,
    '',
    '| Monitor | Status | Coverage | Mode | Hard block | Blockers |',
    '|---------|--------|----------|------|------------|----------|',
  ];

  for (const monitor of summary.monitors) {
    const blockers = [
      ...monitor.blockers,
      ...monitor.policy_blockers.map((blocker) => `policy:${blocker}`),
      monitor.error_message,
    ].filter(Boolean);
    lines.push(
      [
        monitor.label,
        monitor.status,
        monitor.coverage_status,
        monitor.mode || 'unknown',
        monitor.hard_block_active ? 'active' : 'inactive',
        blockers.join(', ') || 'none',
      ].join(' | ').replace(/^/, '| ').replace(/$/, ' |')
    );
  }

  for (const monitor of summary.monitors) {
    const missingFamilies = monitor.artifact_selection?.missing_terminal_priority_families || [];
    if (missingFamilies.length > 0) {
      lines.push(`- ${monitor.label} missing artifact families: ${missingFamilies.join(', ')}`);
    }
  }

  return `${lines.join('\n')}\n`;
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    terminal_report:
      process.env.COVERAGE_MONITOR_TERMINAL_JSON || 'terminal-disposition-coverage.json',
    bot_auth_report:
      process.env.COVERAGE_MONITOR_BOT_AUTH_JSON || 'bot-comment-auth-coverage-summary.json',
    pr_source_context_report:
      process.env.COVERAGE_MONITOR_PR_SOURCE_CONTEXT_JSON || 'pr-source-context-coverage.json',
    output_json:
      process.env.COVERAGE_MONITOR_SUMMARY_JSON || 'coverage-monitor-summary.json',
    output_md:
      process.env.COVERAGE_MONITOR_SUMMARY_MD || 'coverage-monitor-summary.md',
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === '--terminal-report') {
      options.terminal_report = next;
      index += 1;
    } else if (arg === '--bot-auth-report') {
      options.bot_auth_report = next;
      index += 1;
    } else if (arg === '--pr-source-context-report') {
      options.pr_source_context_report = next;
      index += 1;
    } else if (arg === '--output-json') {
      options.output_json = next;
      index += 1;
    } else if (arg === '--output-md') {
      options.output_md = next;
      index += 1;
    }
  }

  return options;
}

function main() {
  const options = parseArgs();
  const summary = buildCoverageMonitorSummary(options);
  const markdown = formatMonitorMarkdown(summary);
  fs.writeFileSync(options.output_json, `${JSON.stringify(summary, null, 2)}\n`);
  fs.writeFileSync(options.output_md, markdown);
  process.stdout.write(markdown);
}

if (require.main === module) {
  main();
}

module.exports = {
  SUMMARY_SCHEMA,
  buildCoverageMonitorSummary,
  formatMonitorMarkdown,
  normalizeMonitorArtifactSelection,
  parseArgs,
  readJsonReport,
};
