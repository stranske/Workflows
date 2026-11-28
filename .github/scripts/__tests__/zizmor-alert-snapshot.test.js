'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildSnapshot,
  countOpenAlerts,
  parsePreviousCount,
  renderMarkdown,
} = require('../zizmor_alert_snapshot.js');

function githubReturning(alertsOrError) {
  const calls = [];
  const listAlertsForRepo = { name: 'listAlertsForRepo' };
  return {
    calls,
    github: {
      rest: { codeScanning: { listAlertsForRepo } },
      paginate: async (method, params) => {
        calls.push(params);
        assert.equal(method, listAlertsForRepo);
        if (alertsOrError instanceof Error) throw alertsOrError;
        return alertsOrError;
      },
    },
  };
}

test('counts open zizmor alerts by severity', async () => {
  const { github, calls } = githubReturning([
    { rule: { security_severity_level: 'high' } },
    { rule: { severity: 'warning' } },
    { rule: { security_severity_level: 'high' } },
  ]);
  const current = await countOpenAlerts({ github, owner: 'o', repo: 'r' });
  assert.deepEqual(current, { status: 'measured', open: 3, by_severity: { high: 2, warning: 1 } });
  assert.equal(calls[0].tool_name, 'zizmor');
  assert.equal(calls[0].state, 'open');
});

test('an API failure is "unmeasured", never zero', async () => {
  const error = new Error('Resource not accessible by integration');
  error.status = 403;
  const { github } = githubReturning(error);
  const current = await countOpenAlerts({ github, owner: 'o', repo: 'r' });
  assert.equal(current.status, 'unmeasured');
  assert.equal(current.open, undefined);
  const md = renderMarkdown(buildSnapshot({ current }));
  assert.match(md, /not counted: HTTP 403/);
  assert.doesNotMatch(md, /`0`/);
});

test('a measured zero prints "fully drained"', () => {
  const md = renderMarkdown(
    buildSnapshot({
      current: { status: 'measured', open: 0, by_severity: {} },
      previousBody: '*Open zizmor alerts:* `4`',
    })
  );
  assert.match(md, /\*Open zizmor alerts:\* `0` - fully drained/);
  assert.match(md, /falling, -4 since `4`/);
});

test('trend compares with the count printed in the previous snapshot body', () => {
  const previousBody = renderMarkdown(
    buildSnapshot({ current: { status: 'measured', open: 963, by_severity: { high: 963 } } })
  );
  assert.equal(parsePreviousCount(previousBody), 963);
  const snapshot = buildSnapshot({
    current: { status: 'measured', open: 970, by_severity: { high: 970 } },
    previousBody,
    previousAt: '2026-11-23T06:30:00Z',
  });
  assert.equal(snapshot.delta, 7);
  assert.equal(snapshot.trend, 'rising');
  assert.match(renderMarkdown(snapshot), /rising, \+7 since `963` \(snapshot of 2026-11-23T06:30:00Z\)/);
});

test('the first measurement says so instead of inventing a trend', () => {
  const snapshot = buildSnapshot({
    current: { status: 'measured', open: 5, by_severity: {} },
    previousBody: '# Repository self-check snapshot\n',
  });
  assert.equal(snapshot.previous, null);
  assert.match(renderMarkdown(snapshot), /first measurement/);
});

// --- Cohesion review round 2, B3: CodeQL and Semgrep in the same snapshot ---

test('the snapshot counts zizmor, CodeQL and Semgrep, each against its own previous count', async () => {
  const { SCANS, renderSecuritySection, snapshotAllScans } = require('../zizmor_alert_snapshot.js');
  assert.deepEqual(
    SCANS.map((scan) => scan.tool),
    ['zizmor', 'CodeQL', 'Semgrep OSS']
  );
  const openByTool = { zizmor: 3, CodeQL: 0, 'Semgrep OSS': 2 };
  const requestedTools = [];
  const listAlertsForRepo = { name: 'listAlertsForRepo' };
  const github = {
    rest: { codeScanning: { listAlertsForRepo } },
    paginate: async (_method, params) => {
      requestedTools.push(params.tool_name);
      return Array.from({ length: openByTool[params.tool_name] }, () => ({
        rule: { severity: 'warning' },
      }));
    },
  };
  const previousBody = [
    '## Security scan alerts',
    '',
    '*Open zizmor alerts:* `5`',
    '',
    '*Open Semgrep alerts:* `1`',
  ].join('\n');
  const snapshots = await snapshotAllScans({
    github,
    owner: 'o',
    repo: 'r',
    previousBody,
    previousAt: '2026-11-23T06:30:00Z',
  });
  assert.deepEqual(requestedTools, ['zizmor', 'CodeQL', 'Semgrep OSS']);
  assert.deepEqual(
    snapshots.map((s) => [s.label, s.open, s.previous, s.delta]),
    [
      ['zizmor', 3, 5, -2],
      ['CodeQL', 0, null, null],
      ['Semgrep', 2, 1, 1],
    ]
  );
  const md = renderSecuritySection(snapshots);
  assert.equal((md.match(/^## Security scan alerts$/gm) || []).length, 1);
  assert.deepEqual(
    [...md.matchAll(/^\*Open (\w+) alerts:\*/gm)].map((m) => m[1]),
    ['zizmor', 'CodeQL', 'Semgrep']
  );
  assert.match(md, /\*Open CodeQL alerts:\* `0` - fully drained/);
  assert.match(md, /\*Open Semgrep alerts:\* `2`\n\n\*Trend:\* rising, \+1 since `1`/);
  // A previous zizmor count is never read as another scan's count.
  assert.equal(snapshots[1].trend, 'first measurement');
});
