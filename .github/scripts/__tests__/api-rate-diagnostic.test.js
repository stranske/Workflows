'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const rateResponse = require('./fixtures/api-rate-limit-response.json');
const summaryFixture = require('./fixtures/api-rate-summary.json');
const consumerActivity = require('./fixtures/api-rate-consumer-activity.json');
const runsFixture = require('./fixtures/api-rate-runs.json');
const issueBodies = require('./fixtures/api-rate-issue-bodies.json');

const {
  normalizeRateLimitData,
  pctUsed,
  runFetchRateLimitStep,
  validateLoadSharing,
} = require('../api_rate_diagnostic/rate_limits.js');
const {
  buildSummaryFromRates,
  runAggregateStep,
  safeJson,
} = require('../api_rate_diagnostic/accumulate_history.js');
const {
  checkActionsRunsAccess,
  normalizeHeader,
} = require('../api_rate_diagnostic/access_checks.js');
const {
  collectConsumerActivity,
  parseRegisteredRepos,
  summarizeRuns,
} = require('../api_rate_diagnostic/consumer_activity.js');
const {
  criticalCoreWarnings,
  currentUtilizationWarnings,
  hasHighUsageAlert,
  renderUtilizationAnalysis,
  runAlertCheckStep,
} = require('../api_rate_diagnostic/detect_thresholds.js');
const {
  buildCurrentReport,
  buildHistoricalReport,
} = require('../api_rate_diagnostic/render_report.js');
const {
  composeHighUsageIssueBody,
  composeHighUsageUpdateBody,
  composeRepeatedFailureIssueBody,
  composeRepeatedFailureUpdateBody,
} = require('../api_rate_diagnostic/compose_issue_body.js');
const {
  filterRunsToEndDate,
  limitRunsForDisplay,
  resolveDateRange,
  resolveWorkflowIdWithFallback,
} = require('../api_rate_diagnostic/history.js');

function tempOutputFile() {
  return path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'api-rate-diagnostic-')), 'out.txt');
}

test('rate limit normalization preserves bc-style percentages for edge values', () => {
  assert.equal(pctUsed(0, 5000), '0');
  assert.equal(pctUsed(4999, 5000), '99.9');
  assert.equal(pctUsed(31, 30), '103.3');
  assert.equal(pctUsed(1, 0), '0');

  const normalized = normalizeRateLimitData(rateResponse, 'OWNER_PR_PAT');
  assert.equal(normalized.source, 'OWNER_PR_PAT');
  assert.equal(normalized.core.pct, '99.9');
  assert.equal(normalized.search.pct, '103.3');
  assert.equal(normalized.reset, '2023-11-14T22:13:20Z');
});

test('fetch rate limit step writes compact output for valid and empty snapshots', async () => {
  const okOutput = tempOutputFile();
  await runFetchRateLimitStep({
    source: 'GITHUB_TOKEN',
    displayName: 'GITHUB_TOKEN (Installation Token)',
    groupName: 'GITHUB_TOKEN Rate Limits',
    fetcher: async () => rateResponse,
    outputPath: okOutput,
  });
  const okLine = fs.readFileSync(okOutput, 'utf8').trim();
  assert.match(okLine, /^rate_json=/);
  assert.equal(JSON.parse(okLine.replace(/^rate_json=/, '')).core.pct, '99.9');

  const emptyOutput = tempOutputFile();
  await runFetchRateLimitStep({
    source: 'GH_APP',
    fetcher: async () => ({}),
    outputPath: emptyOutput,
  });
  assert.equal(fs.readFileSync(emptyOutput, 'utf8').trim(), 'rate_json={}');
});

test('aggregation accumulates history-style token snapshots across pools', () => {
  const env = {
    GITHUB_TOKEN_RATE: JSON.stringify(summaryFixture.tokens.github_token),
    PAT_RATE: JSON.stringify(summaryFixture.tokens.owner_pr_pat),
    SERVICE_BOT_RATE: '{}',
    APP_RATE: JSON.stringify(summaryFixture.tokens.workflows_app),
    KEEPALIVE_APP_RATE: '',
    GH_APP_RATE: '{bad json',
  };
  assert.deepEqual(safeJson('{bad json', { fallback: true }), { fallback: true });

  const summary = buildSummaryFromRates(env, '2026-05-06T12:00:00Z');
  assert.equal(summary.total_pools, 3);
  assert.equal(summary.total_remaining, 18499);
  assert.equal(summary.total_limit, 25000);

  const outputPath = tempOutputFile();
  runAggregateStep({ env, outputPath });
  const output = fs.readFileSync(outputPath, 'utf8');
  assert.match(output, /^summary=/);
});

test('access checks report unset tokens and normalize accepted-permissions headers', async () => {
  assert.equal(normalizeHeader({ 'x-accepted-github-permissions': 'actions=read' }, 'X-Accepted-GitHub-Permissions'), 'actions=read');

  const results = await checkActionsRunsAccess({
    env: { GITHUB_REPOSITORY: 'stranske/Workflows' },
    tokens: [['GITHUB_TOKEN', 'token-a'], ['OWNER_PR_PAT', '']],
    Octokit: class {
      constructor() {
        this.request = async () => ({ status: 200, headers: { 'x-accepted-github-permissions': 'actions=read' } });
      }
    },
    createTokenAwareRetry: async ({ github }) => ({ withRetry: (fn) => fn(github) }),
  });

  assert.deepEqual(results, ['GITHUB_TOKEN: HTTP 200 | perms: actions=read', 'OWNER_PR_PAT: not set']);
});

test('consumer activity fixtures summarize multiple runs per repository', async () => {
  assert.deepEqual(parseRegisteredRepos(' stranske/a\n\nstranske/b '), ['stranske/a', 'stranske/b']);
  const summary = summarizeRuns('stranske/example-a', {
    total_count: 3,
    workflow_runs: [
      { status: 'in_progress', name: 'CI' },
      { status: 'queued', name: 'CI' },
      { status: 'completed', name: 'Release' },
    ],
  });
  assert.deepEqual(summary, consumerActivity[0]);

  const collected = await collectConsumerActivity({
    env: {
      RUN_CONSUMER_CHECKS: 'true',
      GH_TOKEN: 'token',
      REGISTERED_CONSUMER_REPOS: 'stranske/example-a',
    },
    fetcher: async () => ({
      total_count: 3,
      workflow_runs: [
        { status: 'in_progress', name: 'CI' },
        { status: 'queued', name: 'CI' },
        { status: 'completed', name: 'Release' },
      ],
    }),
  });
  assert.deepEqual(collected, consumerActivity);
});

test('threshold detection covers normal, moderate, high, alert, and critical classes', () => {
  assert.deepEqual(renderUtilizationAnalysis({ tokens: {} }), ['✅ All tokens within normal utilization (<50%)']);

  const moderate = currentUtilizationWarnings(summaryFixture);
  assert.deepEqual(moderate.map((warning) => warning.class), ['moderate']);

  const highSummary = structuredClone(summaryFixture);
  highSummary.tokens.owner_pr_pat.core.pct = '85.1';
  assert.equal(hasHighUsageAlert(highSummary), true);
  assert.deepEqual(criticalCoreWarnings(highSummary), []);

  highSummary.tokens.owner_pr_pat.core.pct = '91.0';
  assert.deepEqual(criticalCoreWarnings(highSummary), [
    '::warning::Critical API rate limit utilization detected (91.0%)',
  ]);

  const outputPath = tempOutputFile();
  assert.equal(runAlertCheckStep({ summaryJson: JSON.stringify(highSummary), outputPath }), 'true');
  assert.equal(fs.readFileSync(outputPath, 'utf8').trim(), 'alert_needed=true');
});

test('current and historical reports preserve fixture-backed markdown sections', () => {
  const current = buildCurrentReport({
    summaryJson: JSON.stringify(summaryFixture),
    consumerActivityJson: JSON.stringify(consumerActivity),
    generated: '2026-05-06 12:00:00 UTC',
  }).join('\\n');

  assert.match(current, /# 📊 API Rate Limit Diagnostic Report/);
  assert.ok(current.includes('| OWNER_PR_PAT | 4000/5000 (80.0%)'));
  assert.ok(current.includes('- 🟡 **OWNER_PR_PAT** Core API: 80.0%'));
  assert.ok(current.includes('| stranske/example-a | 3 | 1 | 1 | CI (2) |'));

  const historical = buildHistoricalReport({
    startDate: '2026-05-05',
    endDate: '2026-05-06',
    runCount: 2,
    runs: runsFixture.slice(0, 2),
    generated: '2026-05-06 12:00:00 UTC',
    serverUrl: 'https://github.com',
    repository: 'stranske/Workflows',
  }).join('\\n');

  assert.ok(historical.includes('| Period Duration | 1 days |'));
  assert.ok(
    historical.includes(
      'Run #71 - [View Details](https://github.com/stranske/Workflows/actions/runs/101)',
    ),
  );
});

test('issue body composition is byte-stable for alert classes', () => {
  const runUrl = 'https://github.com/stranske/Workflows/actions/runs/123';
  const now = '2026-05-06 12:00:00 UTC';

  assert.equal(composeHighUsageIssueBody({ now, runUrl }), issueBodies.highUsageIssue);
  assert.equal(composeHighUsageUpdateBody({ now, runUrl }), issueBodies.highUsageUpdate);
  assert.equal(composeRepeatedFailureIssueBody({ now, runUrl }), issueBodies.repeatedFailureIssue);
  assert.equal(composeRepeatedFailureUpdateBody({ runUrl }), issueBodies.repeatedFailureUpdate);
});

test('history helpers resolve date ranges and accumulate multiple runs across bounds', () => {
  assert.deepEqual(
    resolveDateRange({
      startInput: '1w',
      endInput: '2026-05-06',
      now: new Date('2026-05-06T12:00:00Z'),
    }),
    { startDate: '2026-04-29', endDate: '2026-05-06' },
  );

  assert.deepEqual(filterRunsToEndDate(runsFixture, '2026-05-06'), runsFixture.slice(0, 2));
});

test('historical runner helpers use fallback tokens and limit display fixtures', async () => {
  const resolved = await resolveWorkflowIdWithFallback({
    primaryToken: 'primary',
    fallbackToken: 'fallback',
    fetcher: async (token) => {
      if (token === 'primary') throw new Error('denied');
      return 123;
    },
  });
  assert.deepEqual(resolved, { workflowId: 123, tokenUsed: 'fallback' });

  const runsPath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'api-rate-runs-')), 'runs.json');
  fs.writeFileSync(runsPath, JSON.stringify(runsFixture));
  const outputPath = tempOutputFile();
  assert.deepEqual(limitRunsForDisplay({ runsPath, outputPath, maxRuns: 2 }), runsFixture.slice(0, 2));
  assert.equal(fs.readFileSync(outputPath, 'utf8').trim(), 'processed_count=2');
});

test('load-sharing validation verifies task-specific pools and switching', async () => {
  const calls = [];
  const tokenBalancer = {
    async initializeTokenRegistry() {
      return [
        { id: 'KEEPALIVE_APP', type: 'APP', capabilities: ['workflow-dispatch'] },
        { id: 'OWNER_PR_PAT', type: 'PAT', capabilities: ['workflow-dispatch'] },
      ];
    },
    async getOptimalToken({ task }) {
      calls.push(task);
      if (task === 'keepalive-loop') return { source: 'KEEPALIVE_APP' };
      if (task === 'pr-creation-as-owner') return { source: 'OWNER_PR_PAT' };
      return calls.filter((call) => call === 'workflow-dispatch').length === 1
        ? { source: 'KEEPALIVE_APP', remaining: 200 }
        : { source: 'OWNER_PR_PAT', remaining: 200 };
    },
    updateTokenUsage(source, amount) {
      calls.push(`${source}:${amount}`);
    },
  };

  await validateLoadSharing({ env: { GITHUB_TOKEN: 'token' }, tokenBalancer });
  assert.ok(calls.includes('KEEPALIVE_APP:150'));
});
