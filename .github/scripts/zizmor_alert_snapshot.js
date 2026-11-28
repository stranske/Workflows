'use strict';

// Open code-scanning alerts per scan, each with the trend since the previous
// self-check snapshot (cohesion review A5d for zizmor; round 2 B3 adds CodeQL
// and Semgrep; 2026-11-28 adds the Scorecard regression count below).
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
// regular expression is ever built from a value. Labels may hold spaces
// ("Scorecard regression").
const COUNT_LINE_PATTERN = /Open ([A-Za-z][\w -]*?) alerts:\*?\s*`(\d+)`/g;

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

// --- OpenSSF Scorecard regression count (owner decision 2026-11-28) ---------
//
// Scorecard raises ~740 alerts here; the owner chose "fix the 12, count only
// regressions". Only three classes are counted:
//   - a third-party action not pinned by a commit SHA (this repository's own
//     `stranske/Workflows/...@main` reusable calls are by design and excluded);
//   - downloadThenRun (`curl ... | sh`);
//   - DangerousWorkflow, minus the checkouts verified as safe and recorded in
//     config/scorecard-dangerous-workflow-allowlist.json.
// GitHub-owned tag pins and pip/npm hash alerts are deliberately not counted.
// Alerts are never dismissed through the API; the allowlist is the record.

const SCORECARD_LABEL = 'Scorecard regression';
const SCORECARD_TOOL = 'Scorecard';
const SCORECARD_ALLOWLIST_PATH = 'config/scorecard-dangerous-workflow-allowlist.json';
const OWN_REUSABLE_REF = 'stranske/Workflows/';

const SCORECARD_CLASS = {
  thirdParty: 'third-party action not pinned by hash',
  thirdPartyUnreadable: 'third-party action not pinned by hash (line unreadable)',
  downloadThenRun: 'downloadThenRun',
  dangerousWorkflow: 'DangerousWorkflow',
};

// The finding text before Scorecard's remediation tip, without the score
// prefix and with whitespace collapsed (multi-line expressions included).
function scorecardFinding(alert) {
  const text = String(alert?.most_recent_instance?.message?.text || alert?.message?.text || '');
  const finding = text.split(/\nRemediation tip:/)[0];
  return finding.replace(/^score is \d+:\s*/, '').replace(/\s+/g, ' ').trim();
}

function alertLocation(alert) {
  const location = alert?.most_recent_instance?.location || {};
  return { path: location.path || '', line: location.start_line || 0 };
}

function parseScorecardAllowlist(text) {
  const data = JSON.parse(text);
  const entries = Array.isArray(data?.entries) ? data.entries : null;
  if (!entries) {
    throw new Error('allowlist has no "entries" array');
  }
  for (const entry of entries) {
    if (!entry?.path || !entry?.finding || !entry?.reason || !(entry?.count >= 1)) {
      throw new Error(`allowlist entry needs path, finding, reason and count >= 1: ${JSON.stringify(entry)}`);
    }
  }
  return entries;
}

function alertCommit(alert) {
  return alert?.most_recent_instance?.commit_sha || '';
}

// Reads one line of a workflow file at the commit Scorecard analysed (the
// alert's most recent instance), so a later push cannot shift the line under
// it. Returns null when the file or line cannot be read. One API call per
// (file, commit).
function apiLineReader({ github, owner, repo }) {
  const cache = new Map();
  return async (filePath, line, ref) => {
    const key = `${ref}\n${filePath}`;
    if (!cache.has(key)) {
      cache.set(
        key,
        (async () => {
          try {
            const { data } = await github.rest.repos.getContent({
              owner,
              repo,
              path: filePath,
              ...(ref ? { ref } : {}),
            });
            if (typeof data?.content !== 'string') return null;
            return Buffer.from(data.content, data.encoding || 'base64')
              .toString('utf8')
              .split('\n');
          } catch (_error) {
            return null;
          }
        })()
      );
    }
    const lines = await cache.get(key);
    return lines && line >= 1 && line <= lines.length ? lines[line - 1] : null;
  };
}

// Returns the counted class of one alert, or null when it is not counted.
// `allowance` is a Map of "path\nfinding" -> remaining allowed count; it is
// decremented, so an allowlist entry never covers more alerts than it names.
async function classifyScorecardAlert(alert, { readLine, allowance }) {
  const ruleId = alert?.rule?.id || '';
  const finding = scorecardFinding(alert);
  const { path, line } = alertLocation(alert);
  if (ruleId === 'PinnedDependenciesID') {
    if (finding.startsWith('third-party GitHubAction not pinned by hash')) {
      const source = await readLine(path, line, alertCommit(alert));
      if (source === null || source === undefined) {
        return SCORECARD_CLASS.thirdPartyUnreadable;
      }
      return source.includes(OWN_REUSABLE_REF) ? null : SCORECARD_CLASS.thirdParty;
    }
    if (finding.startsWith('downloadThenRun')) {
      return SCORECARD_CLASS.downloadThenRun;
    }
    return null;
  }
  if (ruleId === 'DangerousWorkflowID') {
    const key = `${path}\n${finding}`;
    const remaining = allowance.get(key) || 0;
    if (remaining > 0) {
      allowance.set(key, remaining - 1);
      return null;
    }
    return SCORECARD_CLASS.dangerousWorkflow;
  }
  return null;
}

async function countScorecardRegressions({
  github,
  owner,
  repo,
  paginateWithRetry = (method, params) => github.paginate(method, params),
  readLine,
  allowlistText,
}) {
  const lineAt = readLine || apiLineReader({ github, owner, repo });
  let entries;
  try {
    const text =
      allowlistText === undefined
        ? require('fs').readFileSync(SCORECARD_ALLOWLIST_PATH, 'utf8')
        : allowlistText;
    entries = parseScorecardAllowlist(text);
  } catch (error) {
    return {
      status: 'unmeasured',
      reason: `could not read ${SCORECARD_ALLOWLIST_PATH}: ${error?.message || error}`,
    };
  }
  let alerts;
  try {
    alerts = await paginateWithRetry(github.rest.codeScanning.listAlertsForRepo, {
      owner,
      repo,
      state: 'open',
      tool_name: SCORECARD_TOOL,
      per_page: 100,
    });
  } catch (error) {
    const status = error?.status ?? error?.response?.status;
    const message = error?.message || String(error);
    return { status: 'unmeasured', reason: status ? `HTTP ${status}: ${message}` : message };
  }
  const allowance = new Map();
  for (const entry of entries) {
    const key = `${entry.path}\n${String(entry.finding).replace(/\s+/g, ' ').trim()}`;
    allowance.set(key, (allowance.get(key) || 0) + entry.count);
  }
  const byClass = {};
  const counted = [];
  for (const alert of alerts || []) {
    const cls = await classifyScorecardAlert(alert, { readLine: lineAt, allowance });
    if (cls) {
      byClass[cls] = (byClass[cls] || 0) + 1;
      const { path, line } = alertLocation(alert);
      counted.push({ number: alert?.number ?? null, class: cls, path, line });
    }
  }
  return {
    status: 'measured',
    open: counted.length,
    by_class: byClass,
    alerts: counted,
    scanned: (alerts || []).length,
  };
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
  const zeroText = snapshot.label === SCORECARD_LABEL ? ' - none open' : ' - fully drained';
  const drained = snapshot.open === 0 ? zeroText : '';
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
  const classes = Object.entries(snapshot.by_class || {}).sort((a, b) => a[0].localeCompare(b[0]));
  if (classes.length > 0) {
    lines.push('', `*By class:* ${classes.map(([k, v]) => `${k} ${v}`).join(', ')}`);
    const where = (snapshot.alerts || [])
      .slice(0, 20)
      .map((a) => `\`${a.path}:${a.line}\``)
      .join(', ');
    if (where) {
      lines.push('', `*Where:* ${where}`);
    }
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
  scorecard = {},
}) {
  const snapshots = [];
  for (const scan of scans) {
    const current = await countOpenAlerts({ github, owner, repo, tool: scan.tool, paginateWithRetry });
    snapshots.push(buildSnapshot({ current, previousBody, previousAt, label: scan.label }));
  }
  if (scorecard !== null) {
    const current = await countScorecardRegressions({
      github,
      owner,
      repo,
      paginateWithRetry,
      ...scorecard,
    });
    snapshots.push(buildSnapshot({ current, previousBody, previousAt, label: SCORECARD_LABEL }));
  }
  return snapshots;
}

module.exports = {
  COUNT_MARKER,
  SCANS,
  SCORECARD_ALLOWLIST_PATH,
  SCORECARD_CLASS,
  SCORECARD_LABEL,
  buildSnapshot,
  classifyScorecardAlert,
  countScorecardRegressions,
  parseScorecardAllowlist,
  scorecardFinding,
  apiLineReader,
  countMarker,
  countOpenAlerts,
  parsePreviousCount,
  renderMarkdown,
  renderSecuritySection,
  snapshotAllScans,
};
