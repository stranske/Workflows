'use strict';

// Open zizmor code-scanning alerts, with the trend since the previous
// self-check snapshot (cohesion review A5d).
//
// health-51-zizmor uploads SARIF with continue-on-error and nothing read the
// resulting alerts, so the count could only grow unseen. The self-check now
// prints it every week next to the previous value. Three outcomes are kept
// distinct, because only one of them is good news:
//   - measured, N > 0  -> "`N` open"
//   - measured, 0      -> "`0` open - fully drained"
//   - not measured     -> "not counted: <reason>" (never shown as zero)

const COUNT_MARKER = 'Open zizmor alerts:';
const COUNT_PATTERN = /Open zizmor alerts:\*?\s*`(\d+)`/;

const passthrough = (fn) => fn();

function severityOf(alert) {
  return (
    alert?.rule?.security_severity_level ||
    alert?.rule?.severity ||
    'unknown'
  ).toLowerCase();
}

async function countOpenAlerts({ github, owner, repo, tool = 'zizmor', withRetry = passthrough }) {
  try {
    const alerts = await withRetry(() =>
      github.paginate(github.rest.codeScanning.listAlertsForRepo, {
        owner,
        repo,
        state: 'open',
        tool_name: tool,
        per_page: 100,
      })
    );
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

function parsePreviousCount(body) {
  const match = COUNT_PATTERN.exec(String(body || ''));
  return match ? Number.parseInt(match[1], 10) : null;
}

function buildSnapshot({ current, previousBody = '', previousAt = '' }) {
  const previous = parsePreviousCount(previousBody);
  const snapshot = { ...current, previous, previous_at: previousAt || null };
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

function renderMarkdown(snapshot) {
  const lines = ['## Security scan alerts', ''];
  if (snapshot.status !== 'measured') {
    lines.push(`*${COUNT_MARKER}* not counted: ${snapshot.reason || 'unknown reason'}`);
    if (snapshot.previous !== null && snapshot.previous !== undefined) {
      lines.push('', `*Previous snapshot:* \`${snapshot.previous}\``);
    }
    return `${lines.join('\n')}\n`;
  }
  const drained = snapshot.open === 0 ? ' - fully drained' : '';
  lines.push(`*${COUNT_MARKER}* \`${snapshot.open}\`${drained}`);
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
  return `${lines.join('\n')}\n`;
}

module.exports = {
  COUNT_MARKER,
  buildSnapshot,
  countOpenAlerts,
  parsePreviousCount,
  renderMarkdown,
};
