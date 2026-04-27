const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  buildCoverageMonitorSummary,
  formatMonitorMarkdown,
  normalizeMonitorArtifactSelection,
  parseArgs,
  readJsonReport,
  SUMMARY_SCHEMA,
} = require('../coverage_monitor_summary.js');

function report(status, extra = {}) {
  return {
    schema: 'example/v1',
    status,
    coverage_status: status,
    mode: 'warning-only',
    requested_mode: 'warning-only',
    enforcement: {
      mode: 'warning-only',
      requested_mode: 'warning-only',
      hard_block_active: false,
      hard_block_eligible: false,
      should_fail: false,
      blockers: [],
      policy_blockers: [],
    },
    ...extra,
  };
}

function writeJson(dir, name, value) {
  const file = path.join(dir, name);
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  return file;
}

test('builds a pass monitor contract from warning-only preflight reports', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-monitor-'));
  const terminal = writeJson(dir, 'terminal.json', report('pass'));
  const botAuth = writeJson(dir, 'bot-auth.json', report('pass'));

  const summary = buildCoverageMonitorSummary({
    terminal_report: terminal,
    bot_auth_report: botAuth,
    generated_at: '2026-04-26T02:00:00.000Z',
  });
  const markdown = formatMonitorMarkdown(summary);

  assert.equal(summary.schema, SUMMARY_SCHEMA);
  assert.equal(summary.status, 'pass');
  assert.equal(summary.warning_only, true);
  assert.equal(summary.hard_block_active, false);
  assert.equal(summary.should_fail, false);
  assert.equal(summary.next_action, 'continue-monitoring');
  assert.deepEqual(
    summary.monitors.map((monitor) => monitor.label),
    ['terminal-disposition', 'bot-comment-auth']
  );
  assert.match(markdown, /Weekly Coverage Monitor Contract/);
  assert.match(markdown, /terminal-disposition \| pass/);
});

test('includes PR source context coverage when configured', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-monitor-'));
  const terminal = writeJson(dir, 'terminal.json', report('pass'));
  const botAuth = writeJson(dir, 'bot-auth.json', report('pass'));
  const prSource = writeJson(
    dir,
    'pr-source.json',
    report('warning', {
      schema: 'workflows-pr-source-context-coverage/v1',
      warning_count: 1,
      unknown_source_context_count: 1,
    })
  );

  const summary = buildCoverageMonitorSummary({
    terminal_report: terminal,
    bot_auth_report: botAuth,
    pr_source_context_report: prSource,
  });

  assert.equal(summary.status, 'warning');
  assert.deepEqual(
    summary.monitors.map((monitor) => monitor.label),
    ['terminal-disposition', 'bot-comment-auth', 'pr-source-context']
  );
  assert.match(formatMonitorMarkdown(summary), /pr-source-context \| warning/);
});

test('skips PR source context coverage when configured file is absent', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-monitor-'));
  const terminal = writeJson(dir, 'terminal.json', report('pass'));
  const botAuth = writeJson(dir, 'bot-auth.json', report('pass'));

  const summary = buildCoverageMonitorSummary({
    terminal_report: terminal,
    bot_auth_report: botAuth,
    pr_source_context_report: path.join(dir, 'missing-pr-source.json'),
  });

  assert.equal(summary.status, 'pass');
  assert.deepEqual(
    summary.monitors.map((monitor) => monitor.label),
    ['terminal-disposition', 'bot-comment-auth']
  );
});

test('does not include PR source context coverage by default', () => {
  const options = parseArgs([]);

  assert.equal(options.pr_source_context_report, '');
});

test('surfaces warning blockers without activating hard-block policy', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-monitor-'));
  const terminal = writeJson(
    dir,
    'terminal.json',
    report('warning', {
      enforcement: {
        mode: 'warning-only',
        requested_mode: 'hard-block',
        hard_block_active: false,
        hard_block_eligible: false,
        should_fail: false,
        blockers: ['missing-review-thread-sources'],
        policy_blockers: ['hard-block-approval-required'],
      },
      artifact_selection: {
        status: 'pass',
        candidate_terminal_artifact_count: 0,
        selected_terminal_artifact_count: 0,
        missing_terminal_priority_families: [
          'verifier-terminal-disposition',
          'review-thread-terminal-disposition',
        ],
        terminal_priority_family_statuses: [
          {
            family: 'verifier-terminal-disposition',
            status: 'missing',
            candidate_count: 0,
            selected_count: 0,
            latest_candidate: null,
            selected_artifact: null,
          },
        ],
      },
    })
  );
  const botAuth = writeJson(dir, 'bot-auth.json', report('pass'));

  const summary = buildCoverageMonitorSummary({
    terminal_report: terminal,
    bot_auth_report: botAuth,
  });

  assert.equal(summary.status, 'warning');
  assert.equal(summary.warning_only, true);
  assert.equal(summary.policy_blocker_count, 1);
  assert.equal(summary.next_action, 'keep-warning-only-until-approved');
  assert.deepEqual(summary.monitors[0].blockers, ['missing-review-thread-sources']);
  assert.deepEqual(summary.monitors[0].policy_blockers, ['hard-block-approval-required']);
  assert.deepEqual(summary.monitors[0].artifact_selection.missing_terminal_priority_families, [
    'verifier-terminal-disposition',
    'review-thread-terminal-disposition',
  ]);
  assert.deepEqual(summary.monitors[0].artifact_selection.terminal_priority_family_statuses, [
    {
      family: 'verifier-terminal-disposition',
      status: 'missing',
      candidate_count: 0,
      selected_count: 0,
    },
  ]);
  assert.match(formatMonitorMarkdown(summary), /terminal-disposition missing artifact families/);
});

test('normalizes monitor artifact selection detail for summaries', () => {
  assert.deepEqual(
    normalizeMonitorArtifactSelection({
      status: 'pass',
      candidate_terminal_artifact_count: 4,
      selected_terminal_artifact_count: 2,
      missing_terminal_priority_families: ['review-thread-terminal-disposition'],
      terminal_priority_family_statuses: [
        {
          family: 'review-thread-terminal-disposition',
          status: 'missing',
          candidate_count: 0,
          selected_count: 0,
          latest_candidate: { name: 'ignored' },
        },
      ],
    }),
    {
      status: 'pass',
      candidate_terminal_artifact_count: 4,
      selected_terminal_artifact_count: 2,
      missing_terminal_priority_families: ['review-thread-terminal-disposition'],
      terminal_priority_family_statuses: [
        {
          family: 'review-thread-terminal-disposition',
          status: 'missing',
          candidate_count: 0,
          selected_count: 0,
        },
      ],
    }
  );
});

test('marks approved hard-block failures as fail but leaves failure enforcement to callers', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-monitor-'));
  const terminal = writeJson(
    dir,
    'terminal.json',
    report('fail', {
      coverage_status: 'warning',
      mode: 'hard-block',
      requested_mode: 'hard-block',
      enforcement: {
        mode: 'hard-block',
        requested_mode: 'hard-block',
        hard_block_active: true,
        hard_block_eligible: true,
        should_fail: true,
        blockers: ['missing-review-thread-sources'],
        policy_blockers: [],
      },
    })
  );
  const botAuth = writeJson(dir, 'bot-auth.json', report('pass'));

  const summary = buildCoverageMonitorSummary({
    terminal_report: terminal,
    bot_auth_report: botAuth,
  });

  assert.equal(summary.status, 'fail');
  assert.equal(summary.hard_block_active, true);
  assert.equal(summary.should_fail, true);
  assert.equal(summary.next_action, 'honor-approved-hard-block');
});

test('reports missing and parse-error inputs as repairable monitor warnings', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-monitor-'));
  const invalid = path.join(dir, 'invalid.json');
  fs.writeFileSync(invalid, '{"broken"', 'utf8');

  const summary = buildCoverageMonitorSummary({
    terminal_report: path.join(dir, 'missing.json'),
    bot_auth_report: invalid,
  });

  assert.equal(readJsonReport(path.join(dir, 'missing.json'), 'terminal').status, 'missing');
  assert.equal(summary.status, 'warning');
  assert.equal(summary.next_action, 'repair-monitor-report-input');
  assert.equal(summary.monitors[0].status, 'missing');
  assert.equal(summary.monitors[1].status, 'parse-error');
});

test('treats unknown monitor status as a warning', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-monitor-'));
  const terminal = writeJson(dir, 'terminal.json', report('mystery'));
  const botAuth = writeJson(dir, 'bot-auth.json', report('pass'));

  const summary = buildCoverageMonitorSummary({
    terminal_report: terminal,
    bot_auth_report: botAuth,
  });

  assert.equal(summary.status, 'warning');
  assert.equal(summary.monitors[0].status, 'unknown');
  assert.equal(summary.next_action, 'inspect-monitor-warnings');
});

test('parses CLI paths and writes summary artifacts without failing warning states', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-monitor-cli-'));
  const terminal = writeJson(dir, 'terminal.json', report('warning'));
  const botAuth = writeJson(dir, 'bot-auth.json', report('pass'));
  const outputJson = path.join(dir, 'summary.json');
  const outputMd = path.join(dir, 'summary.md');

  const options = parseArgs([
    '--terminal-report',
    terminal,
    '--bot-auth-report',
    botAuth,
    '--pr-source-context-report',
    path.join(dir, 'pr-source.json'),
    '--output-json',
    outputJson,
    '--output-md',
    outputMd,
  ]);

  assert.equal(options.terminal_report, terminal);
  assert.equal(options.bot_auth_report, botAuth);
  assert.equal(options.pr_source_context_report, path.join(dir, 'pr-source.json'));
  const result = spawnSync(
    process.execPath,
    [
      path.join(__dirname, '..', 'coverage_monitor_summary.js'),
      '--terminal-report',
      terminal,
      '--bot-auth-report',
      botAuth,
      '--pr-source-context-report',
      '',
      '--output-json',
      outputJson,
      '--output-md',
      outputMd,
    ],
    { encoding: 'utf8' }
  );

  assert.equal(result.status, 0);
  assert.match(result.stdout, /^## Weekly Coverage Monitor Contract/);
  const summary = JSON.parse(fs.readFileSync(outputJson, 'utf8'));
  assert.equal(summary.status, 'warning');
  assert.equal(fs.readFileSync(outputMd, 'utf8'), result.stdout);
});
