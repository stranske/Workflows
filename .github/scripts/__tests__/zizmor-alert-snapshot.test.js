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
    scorecard: null,
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

// --- Scorecard regression count (owner decision 2026-11-28) -----------------

const path = require('node:path');
const fs = require('node:fs');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const ALLOWLIST_TEXT = fs.readFileSync(
  path.join(ROOT, 'config/scorecard-dangerous-workflow-allowlist.json'),
  'utf8'
);

function scorecardAlert(number, ruleId, text, filePath, line) {
  return {
    number,
    rule: { id: ruleId, severity: 'error' },
    most_recent_instance: {
      message: { text: `${text}\nRemediation tip: something\nClick Remediation section below` },
      location: { path: filePath, start_line: line },
    },
  };
}

// The 8 DangerousWorkflow alerts open on 2026-11-28, as the API returns them.
const VERIFIED_DANGEROUS = [
  [7009, '.github/workflows/maint-auto-lock-deps.yml', 138, "score is 0: untrusted code checkout '${{ github.event.pull_request.base.sha }}'"],
  [7008, '.github/workflows/maint-auto-lock-deps.yml', 68, "score is 0: untrusted code checkout '${{ github.event.pull_request.head.sha }}'"],
  [5048, '.github/workflows/autofix.yml', 54, "score is 0: untrusted code checkout '${{ github.event.pull_request.base.sha || github.sha || github.event.repository.default_branch || github.event.workflow_run.repository.default_branch }}'"],
  [5047, '.github/workflows/agents-guard.yml', 34, "score is 0: untrusted code checkout '${{ github.event.pull_request.base.sha || github.sha || github.event.repository.default_branch || github.event.workflow_run.repository.default_branch }}'"],
  [5046, '.github/workflows/agents-bot-comment-handler.yml', 64, "score is 0: untrusted code checkout '${{ github.event.pull_request.base.sha || github.sha || github.event.repository.default_branch || github.event.workflow_run.repository.default_branch }}'"],
  [2959, '.github/workflows/agents-guard.yml', 127, "score is 0: untrusted code checkout '${{ github.event.pull_request.base.sha }}'"],
  [2957, '.github/workflows/agents-bot-comment-handler.yml', 149, "score is 0: untrusted code checkout '${{\n  github.event.pull_request.base.sha ||\n  github.event.pull_request.base.ref ||\n  github.event.repository.default_branch ||\n  github.ref_name\n}}'"],
  [2955, '.github/workflows/agents-bot-comment-handler.yml', 554, "score is 0: untrusted code checkout '${{\n  github.event.pull_request.base.sha ||\n  github.event.pull_request.base.ref ||\n  github.event.repository.default_branch ||\n  github.ref_name\n}}'"],
].map(([n, p, l, t]) => scorecardAlert(n, 'DangerousWorkflowID', t, p, l));

const NOT_COUNTED = [
  scorecardAlert(1, 'PinnedDependenciesID', 'score is 2: GitHub-owned GitHubAction not pinned by hash', '.github/workflows/a.yml', 3),
  scorecardAlert(2, 'PinnedDependenciesID', 'score is 2: pipCommand not pinned by hash', '.github/workflows/a.yml', 9),
  scorecardAlert(3, 'PinnedDependenciesID', 'score is 2: npmCommand not pinned by hash', '.github/workflows/a.yml', 10),
  scorecardAlert(4, 'TokenPermissionsID', "score is 0: topLevel 'contents' permission set to 'write'", '.github/workflows/a.yml', 1),
  // The repository's own reusable workflow at @main is by design.
  scorecardAlert(5, 'PinnedDependenciesID', 'score is 2: third-party GitHubAction not pinned by hash', '.github/workflows/own.yml', 3),
];

const FILES = {
  '.github/workflows/own.yml': ['jobs:', '  x:', '    uses: stranske/Workflows/.github/workflows/reusable-codex-run.yml@main'],
  '.github/workflows/tag.yml': ['steps:', '  - uses: peter-evans/create-pull-request@v8'],
};
const readLine = (file, line) => (FILES[file] ? FILES[file][line - 1] ?? null : null);

async function countWith(alerts, overrides = {}) {
  const { countScorecardRegressions } = require('../zizmor_alert_snapshot.js');
  const calls = [];
  const listAlertsForRepo = { name: 'listAlertsForRepo' };
  const github = {
    rest: { codeScanning: { listAlertsForRepo } },
    paginate: async (_method, params) => {
      calls.push(params);
      if (alerts instanceof Error) throw alerts;
      return alerts;
    },
  };
  const current = await countScorecardRegressions({
    github,
    owner: 'o',
    repo: 'r',
    readLine,
    allowlistText: ALLOWLIST_TEXT,
    ...overrides,
  });
  return { current, calls };
}

test('Scorecard: the drained state counts exactly 0 and prints "none open"', async () => {
  const { SCORECARD_LABEL } = require('../zizmor_alert_snapshot.js');
  const { current, calls } = await countWith([...VERIFIED_DANGEROUS, ...NOT_COUNTED]);
  assert.equal(calls[0].tool_name, 'Scorecard');
  assert.equal(calls[0].state, 'open');
  assert.equal(current.status, 'measured');
  assert.equal(current.open, 0);
  assert.equal(current.scanned, 13);
  const md = renderMarkdown(
    buildSnapshot({
      current,
      label: SCORECARD_LABEL,
      previousBody: '*Open Scorecard regression alerts:* `12`',
    })
  );
  assert.match(md, /\*Open Scorecard regression alerts:\* `0` - none open/);
  assert.match(md, /falling, -12 since `12`/);
});

test('Scorecard: each regression class is counted, with where it is', async () => {
  const { SCORECARD_CLASS } = require('../zizmor_alert_snapshot.js');
  const regressions = [
    scorecardAlert(10, 'PinnedDependenciesID', 'score is 2: third-party GitHubAction not pinned by hash', '.github/workflows/tag.yml', 2),
    scorecardAlert(11, 'PinnedDependenciesID', 'score is 2: downloadThenRun not pinned by hash', '.github/workflows/x.yml', 7),
    // A new dangerous checkout in a file that already has allowlisted ones.
    scorecardAlert(12, 'DangerousWorkflowID', "score is 0: untrusted code checkout '${{ github.event.pull_request.head.sha }}'", '.github/workflows/agents-guard.yml', 200),
    // A third copy of a finding the allowlist covers twice.
    scorecardAlert(13, 'DangerousWorkflowID', VERIFIED_DANGEROUS[7].most_recent_instance.message.text.split('\nRemediation')[0], '.github/workflows/agents-bot-comment-handler.yml', 700),
    // A third-party alert whose line cannot be read is counted, never assumed own.
    scorecardAlert(14, 'PinnedDependenciesID', 'score is 2: third-party GitHubAction not pinned by hash', '.github/workflows/gone.yml', 5),
  ];
  const { current } = await countWith([...VERIFIED_DANGEROUS, ...NOT_COUNTED, ...regressions]);
  assert.equal(current.open, 5);
  assert.deepEqual(current.by_class, {
    [SCORECARD_CLASS.thirdParty]: 1,
    [SCORECARD_CLASS.downloadThenRun]: 1,
    [SCORECARD_CLASS.dangerousWorkflow]: 2,
    [SCORECARD_CLASS.thirdPartyUnreadable]: 1,
  });
  const md = renderMarkdown(buildSnapshot({ current, label: 'Scorecard regression' }));
  assert.match(md, /\*Open Scorecard regression alerts:\* `5`\n/);
  assert.match(md, /`\.github\/workflows\/tag\.yml:2`/);
  assert.match(md, /DangerousWorkflow 2/);
});

test('Scorecard: an unreadable allowlist or API failure is "not counted", never zero', async () => {
  const bad = await countWith([], { allowlistText: '{"entries": "nope"}' });
  assert.equal(bad.current.status, 'unmeasured');
  assert.match(bad.current.reason, /scorecard-dangerous-workflow-allowlist\.json/);
  const error = new Error('Resource not accessible by integration');
  error.status = 403;
  const failed = await countWith(error);
  assert.equal(failed.current.status, 'unmeasured');
  for (const current of [bad.current, failed.current]) {
    const md = renderMarkdown(buildSnapshot({ current, label: 'Scorecard regression' }));
    assert.match(md, /\*Open Scorecard regression alerts:\* not counted: /);
    assert.doesNotMatch(md, /`0`/);
    assert.doesNotMatch(md, /none open/);
  }
});

test('Scorecard: last week\'s count is read back from the snapshot body', () => {
  const { SCORECARD_LABEL } = require('../zizmor_alert_snapshot.js');
  const body = renderMarkdown(
    buildSnapshot({ current: { status: 'measured', open: 3, by_class: {} }, label: SCORECARD_LABEL })
  );
  assert.equal(parsePreviousCount(body, SCORECARD_LABEL), 3);
  assert.equal(parsePreviousCount(body, 'zizmor'), null);
});

test('Scorecard: snapshotAllScans adds the regression line after the three scans', async () => {
  const { renderSecuritySection, snapshotAllScans } = require('../zizmor_alert_snapshot.js');
  const listAlertsForRepo = { name: 'listAlertsForRepo' };
  const github = {
    rest: { codeScanning: { listAlertsForRepo } },
    paginate: async (_method, params) => (params.tool_name === 'Scorecard' ? VERIFIED_DANGEROUS : []),
  };
  const snapshots = await snapshotAllScans({
    github,
    owner: 'o',
    repo: 'r',
    scorecard: { readLine, allowlistText: ALLOWLIST_TEXT },
  });
  assert.deepEqual(
    snapshots.map((s) => [s.label, s.open]),
    [['zizmor', 0], ['CodeQL', 0], ['Semgrep', 0], ['Scorecard regression', 0]]
  );
  assert.match(renderSecuritySection(snapshots), /\*Open Scorecard regression alerts:\* `0` - none open/);
});

test('Scorecard: every allowlisted checkout still exists in the named workflow', () => {
  const { parseScorecardAllowlist } = require('../zizmor_alert_snapshot.js');
  for (const entry of parseScorecardAllowlist(ALLOWLIST_TEXT)) {
    const text = fs.readFileSync(path.join(ROOT, entry.path), 'utf8');
    assert.ok(text.includes('actions/checkout'), entry.path);
    assert.ok(entry.reason.length > 40, `${entry.path} needs a real reason`);
  }
});

test('Scorecard: action lines are read at the commit Scorecard analysed, not the checkout', async () => {
  const { countScorecardRegressions } = require('../zizmor_alert_snapshot.js');
  const contentCalls = [];
  const filesAt = {
    'abc123\n.github/workflows/own.yml': 'jobs:\n  x:\n    uses: stranske/Workflows/.github/workflows/r.yml@main\n',
    'abc123\n.github/workflows/tag.yml': 'steps:\n  - uses: peter-evans/create-pull-request@v8\n',
  };
  const listAlertsForRepo = { name: 'listAlertsForRepo' };
  const github = {
    rest: {
      codeScanning: { listAlertsForRepo },
      repos: {
        getContent: async (params) => {
          contentCalls.push(params);
          const text = filesAt[`${params.ref}\n${params.path}`];
          if (text === undefined) {
            const error = new Error('Not Found');
            error.status = 404;
            throw error;
          }
          return { data: { content: Buffer.from(text).toString('base64'), encoding: 'base64' } };
        },
      },
    },
    paginate: async () =>
      [
        ['.github/workflows/own.yml', 3],
        ['.github/workflows/own.yml', 3],
        ['.github/workflows/tag.yml', 2],
        ['.github/workflows/missing.yml', 4],
      ].map(([file, line], i) => {
        const alert = scorecardAlert(i, 'PinnedDependenciesID', 'score is 2: third-party GitHubAction not pinned by hash', file, line);
        alert.most_recent_instance.commit_sha = 'abc123';
        return alert;
      }),
  };
  const current = await countScorecardRegressions({
    github,
    owner: 'o',
    repo: 'r',
    allowlistText: ALLOWLIST_TEXT,
  });
  assert.deepEqual(current.alerts.map((a) => a.path), [
    '.github/workflows/tag.yml',
    '.github/workflows/missing.yml',
  ]);
  assert.ok(contentCalls.every((call) => call.ref === 'abc123'));
  // One call per file and commit, however many alerts share it.
  assert.equal(contentCalls.length, 3);
});
