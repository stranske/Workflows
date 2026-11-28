'use strict';

// Open code-scanning alerts per scan, each with the trend since the previous
// self-check snapshot (cohesion review A5d for zizmor; round 2 B3 adds CodeQL
// and Semgrep).
//
// The security scans upload SARIF with continue-on-error and nothing read the
// resulting alerts, so the counts could only grow unseen. The self-check now
// prints each count every week next to the previous value. Three outcomes are
// kept distinct, because only one of them is good news:
//   - measured, N > 0  -> "`N` open"
//   - measured, 0      -> "`0` open - fully drained"
//   - not measured     -> "not counted: <reason>" (never shown as zero)

// `label` is what the snapshot prints; `tool` is the code-scanning tool name
// the API filters on (the SARIF driver name, e.g. Semgrep uploads as
// "Semgrep OSS").
const SCANS = [
  { label: 'zizmor', tool: 'zizmor' },
  { label: 'CodeQL', tool: 'CodeQL' },
  { label: 'Semgrep', tool: 'Semgrep OSS' },
];

function countMarker(label = 'zizmor') {
  return `Open ${label} alerts:`;
}

// One static pattern for every scan; the label is compared as a string, so no
// regular expression is ever built from a value.
const COUNT_LINE_PATTERN = /Open (\S+) alerts:\*?\s*`(\d+)`/g;

const COUNT_MARKER = countMarker('zizmor');

// Callers pass the paginateWithRetry returned by createTokenAwareRetry
// (github-api-with-retry.js); the default only serves unit tests.

function severityOf(alert) {
  return (
    alert?.rule?.security_severity_level ||
    alert?.rule?.severity ||
    'unknown'
  ).toLowerCase();
}

async function countOpenAlerts({
  github,
  owner,
  repo,
  tool = 'zizmor',
  paginateWithRetry = (method, params) => github.paginate(method, params),
}) {
  try {
    const alerts = await paginateWithRetry(github.rest.codeScanning.listAlertsForRepo, {
      owner,
      repo,
      state: 'open',
      tool_name: tool,
      per_page: 100,
    });
    const bySeverity = {};
    for (const alert of alerts || []) {
      const severity = severityOf(alert);
      bySeverity[severity] = (bySeverity[severity] || 0) + 1;
    }
    return { status: 'measured', open: (alerts || []).length, by_severity: bySeverity };
  } catch (error) {
    const status = error?.status ?? error?.response?.status;
    const message = error?.message || String(error);
    return { status: 'unmeasured', reason: status ? `HTTP ${status}: ${message}` : message };
  }
}

function parsePreviousCount(body, label = 'zizmor') {
  for (const match of String(body || '').matchAll(COUNT_LINE_PATTERN)) {
    if (match[1] === label) {
      return Number.parseInt(match[2], 10);
    }
  }
  return null;
}

function buildSnapshot({ current, previousBody = '', previousAt = '', label = 'zizmor' }) {
  const previous = parsePreviousCount(previousBody, label);
  const snapshot = { ...current, label, previous, previous_at: previousAt || null };
  if (current.status !== 'measured') {
    snapshot.trend = 'unknown';
    snapshot.delta = null;
    return snapshot;
  }
  if (previous === null) {
    snapshot.trend = 'first measurement';
    snapshot.delta = null;
    return snapshot;
  }
  snapshot.delta = current.open - previous;
  snapshot.trend = snapshot.delta > 0 ? 'rising' : snapshot.delta < 0 ? 'falling' : 'flat';
  return snapshot;
}

// The lines for one scan, without the section heading.
function renderScanLines(snapshot) {
  const marker = countMarker(snapshot.label || 'zizmor');
  const lines = [];
  if (snapshot.status !== 'measured') {
    lines.push(`*${marker}* not counted: ${snapshot.reason || 'unknown reason'}`);
    if (snapshot.previous !== null && snapshot.previous !== undefined) {
      lines.push('', `*Previous snapshot:* \`${snapshot.previous}\``);
    }
    return lines;
  }
  const drained = snapshot.open === 0 ? ' - fully drained' : '';
  lines.push(`*${marker}* \`${snapshot.open}\`${drained}`);
  if (snapshot.previous === null || snapshot.previous === undefined) {
    lines.push('', '*Trend:* first measurement (no earlier snapshot carried a count)');
  } else {
    const sign = snapshot.delta > 0 ? '+' : '';
    const since = snapshot.previous_at ? ` (snapshot of ${snapshot.previous_at})` : '';
    lines.push(
      '',
      `*Trend:* ${snapshot.trend}, ${sign}${snapshot.delta} since \`${snapshot.previous}\`${since}`
    );
  }
  const severities = Object.entries(snapshot.by_severity || {}).sort((a, b) =>
    a[0].localeCompare(b[0])
  );
  if (severities.length > 0) {
    lines.push('', `*By severity:* ${severities.map(([k, v]) => `${k} ${v}`).join(', ')}`);
  }
  return lines;
}

function renderMarkdown(snapshot) {
  return renderSecuritySection([snapshot]);
}

// One "Security scan alerts" section holding every scan, in the given order.
function renderSecuritySection(snapshots) {
  const lines = ['## Security scan alerts'];
  for (const snapshot of snapshots) {
    lines.push('', ...renderScanLines(snapshot));
  }
  return `${lines.join('\n')}\n`;
}

// Count every scan in SCANS against the previous snapshot body.
async function snapshotAllScans({
  github,
  owner,
  repo,
  paginateWithRetry,
  previousBody = '',
  previousAt = '',
  scans = SCANS,
}) {
  const snapshots = [];
  for (const scan of scans) {
    const current = await countOpenAlerts({ github, owner, repo, tool: scan.tool, paginateWithRetry });
    snapshots.push(buildSnapshot({ current, previousBody, previousAt, label: scan.label }));
  }
  return snapshots;
}

module.exports = {
  COUNT_MARKER,
  SCANS,
  buildSnapshot,
  countMarker,
  countOpenAlerts,
  parsePreviousCount,
  renderMarkdown,
  renderSecuritySection,
  snapshotAllScans,
};
