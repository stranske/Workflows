const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  collectNdjsonFiles,
  expectedReviewThreadSources,
  formatTerminalDispositionCoverageMarkdown,
  isTerminalDispositionNdjsonFile,
  normalizeEnforcementPolicy,
  normalizeArtifactSelectionSummary,
  normalizeExpectedSource,
  readArtifactSelectionReport,
  readNdjsonFiles,
  summarizeTerminalDispositionCoverage,
} = require('../terminal_disposition_coverage.js');

test('normalizes expected review-thread sources with stable keys', () => {
  assert.deepEqual(
    normalizeExpectedSource({
      sourceType: 'Review Thread',
      sourceId: ' 42 ',
      prNumber: '42',
      reason: ' current PR ',
    }),
    {
      source_type: 'review-thread',
      source_id: '42',
      source_key: 'review-thread:42',
      pr_number: 42,
      reason: 'current PR',
    }
  );
});

test('derives expected review-thread sources from terminal PR activity', () => {
  const expected = expectedReviewThreadSources([
    {
      schema: 'workflows-terminal-disposition/v1',
      source_type: 'source-issue',
      source_id: '7',
      pr_number: 101,
      disposition: 'follow-up-created',
    },
    {
      schema: 'workflows-terminal-disposition/v1',
      source_type: 'merged-pr',
      source_id: '102',
      pr_number: 102,
      disposition: 'no-follow-up-created',
    },
  ]);

  assert.deepEqual(
    expected.map((source) => source.source_key),
    ['review-thread:101', 'review-thread:102']
  );
});

test('reports missing review-thread coverage without failing the contract', () => {
  const report = summarizeTerminalDispositionCoverage([
    {
      schema: 'workflows-terminal-disposition/v1',
      source_type: 'source-issue',
      source_id: '7',
      pr_number: 101,
      disposition: 'follow-up-created',
    },
    {
      schema: 'workflows-terminal-disposition/v1',
      source_type: 'review-thread',
      source_id: '101',
      pr_number: 101,
      disposition: 'no-unresolved-bot-comments',
    },
    {
      schema: 'workflows-terminal-disposition/v1',
      source_type: 'source-issue',
      source_id: '8',
      pr_number: 102,
      disposition: 'needs-human-verdict-policy',
    },
  ]);

  assert.equal(report.schema, 'workflows-terminal-disposition-coverage/v1');
  assert.equal(report.mode, 'warning-only');
  assert.equal(report.status, 'warning');
  assert.deepEqual(report.enforcement, {
    mode: 'warning-only',
    requested_mode: 'warning-only',
    hard_block_approved: false,
    hard_block_eligible: false,
    hard_block_active: false,
    should_fail: false,
    blockers: ['missing-review-thread-sources'],
    policy_blockers: [],
  });
  assert.equal(report.scanned_record_count, 3);
  assert.equal(report.terminal_record_count, 3);
  assert.equal(report.non_terminal_record_count, 0);
  assert.equal(report.expected_source_count, 2);
  assert.equal(report.covered_source_count, 1);
  assert.equal(report.missing_source_count, 1);
  assert.deepEqual(
    report.missing_sources.map((source) => source.source_key),
    ['review-thread:102']
  );
});

test('keeps hard blocking disabled without explicit approval', () => {
  const report = summarizeTerminalDispositionCoverage([], {
    enforcement_mode: 'hard-block',
  });

  assert.equal(report.status, 'no-data');
  assert.equal(report.mode, 'warning-only');
  assert.equal(report.requested_mode, 'hard-block');
  assert.equal(report.enforcement.hard_block_active, false);
  assert.equal(report.enforcement.should_fail, false);
  assert.deepEqual(report.enforcement.policy_blockers, ['hard-block-approval-required']);
});

test('fails only when hard blocking is requested and approved', () => {
  const report = summarizeTerminalDispositionCoverage([], {
    enforcement_mode: 'hard-block',
    hard_block_approved: 'approved',
  });
  const markdown = formatTerminalDispositionCoverageMarkdown(report);

  assert.equal(report.status, 'fail');
  assert.equal(report.coverage_status, 'no-data');
  assert.equal(report.mode, 'hard-block');
  assert.equal(report.enforcement.hard_block_active, true);
  assert.equal(report.enforcement.should_fail, true);
  assert.match(markdown, /Mode: hard-block/);
  assert.match(markdown, /Hard block active: true/);
});

test('passes approved hard blocking when coverage has no blockers', () => {
  const report = summarizeTerminalDispositionCoverage(
    [
      {
        schema: 'workflows-terminal-disposition/v1',
        source_type: 'source-issue',
        source_id: '7',
        pr_number: 101,
        disposition: 'follow-up-created',
      },
      {
        schema: 'workflows-terminal-disposition/v1',
        source_type: 'review-thread',
        source_id: '101',
        pr_number: 101,
        disposition: 'no-unresolved-bot-comments',
      },
    ],
    {
      enforcement_mode: 'hard-block',
      hard_block_approved: true,
    }
  );

  assert.equal(report.status, 'pass');
  assert.equal(report.mode, 'hard-block');
  assert.equal(report.enforcement.hard_block_eligible, true);
  assert.equal(report.enforcement.should_fail, false);
});

test('normalizes the terminal coverage enforcement policy', () => {
  assert.deepEqual(normalizeEnforcementPolicy({ mode: 'enforce', hard_block_approved: 'yes' }), {
    schema: 'workflows-terminal-disposition-enforcement-policy/v1',
    requested_mode: 'hard-block',
    effective_mode: 'hard-block',
    default_mode: 'warning-only',
    hard_block_approved: true,
    policy_blockers: [],
  });
  assert.deepEqual(normalizeEnforcementPolicy({ mode: 'hard-block' }).policy_blockers, [
    'hard-block-approval-required',
  ]);
});

test('formats markdown for observed and missing sources', () => {
  const report = summarizeTerminalDispositionCoverage([
    {
      schema: 'workflows-terminal-disposition/v1',
      source_type: 'source-issue',
      source_id: '7',
      pr_number: 101,
      disposition: 'follow-up-created',
    },
  ]);
  const markdown = formatTerminalDispositionCoverageMarkdown(report);

  assert.match(markdown, /warning-only/);
  assert.match(markdown, /review-thread:101/);
  assert.match(markdown, /source-issue:7/);
  assert.match(markdown, /follow-up-created \(1\)/);
});

test('reads ndjson files and counts parse errors', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'terminal-coverage-'));
  const file = path.join(dir, 'records.ndjson');
  fs.writeFileSync(
    file,
    [
      JSON.stringify({
        schema: 'workflows-terminal-disposition/v1',
        source_type: 'review-thread',
        source_id: '1',
        disposition: 'no-unresolved-bot-comments',
      }),
      '{"broken"',
      '[]',
      '',
    ].join('\n'),
    'utf8'
  );

  const result = readNdjsonFiles([file]);

  assert.equal(result.records.length, 1);
  assert.equal(result.parse_errors, 2);
  assert.equal(result.file_count, 1);
});

test('warns when terminal files contain no terminal disposition records', () => {
  const report = summarizeTerminalDispositionCoverage(
    [
      {
        schema: 'workflows-keepalive-metrics/v1',
        source_type: 'review-thread',
        source_id: '1',
      },
    ],
    {
      input_file_count: 1,
      input_files: ['artifacts/review-thread-terminal-disposition-1/review-thread-terminal-disposition.ndjson'],
    }
  );
  const markdown = formatTerminalDispositionCoverageMarkdown(report);

  assert.equal(report.status, 'warning');
  assert.equal(report.input_file_count, 1);
  assert.equal(report.terminal_record_count, 0);
  assert.equal(report.non_terminal_record_count, 1);
  assert.match(markdown, /Input files: 1/);
  assert.match(markdown, /did not contain valid terminal disposition records/);
});

test('summarizes terminal artifact selector inputs in coverage report', () => {
  const report = summarizeTerminalDispositionCoverage([], {
    artifact_selection_report: {
      schema: 'workflows-weekly-metrics-artifact-selection/v1',
      status: 'pass',
      candidate_family_counts: {
        'keepalive-metrics': 2,
        'verifier-terminal-disposition': 3,
        'review-thread-terminal-disposition': 1,
      },
      selected_family_counts: {
        'keepalive-metrics': 1,
        'verifier-terminal-disposition': 2,
      },
      selected_artifacts: [
        { id: 10, name: 'verifier-terminal-disposition-123', family: 'verifier-terminal-disposition' },
        { id: 11, name: 'keepalive-metrics', family: 'keepalive-metrics' },
      ],
    },
  });
  const markdown = formatTerminalDispositionCoverageMarkdown(report);

  assert.equal(report.status, 'warning');
  assert.deepEqual(report.artifact_selection, {
    schema: 'workflows-weekly-metrics-artifact-selection/v1',
    status: 'pass',
    error_message: '',
    candidate_terminal_artifact_count: 4,
    selected_terminal_artifact_count: 2,
    selected_terminal_artifacts: [
      { id: 10, name: 'verifier-terminal-disposition-123', family: 'verifier-terminal-disposition' },
    ],
  });
  assert.match(markdown, /Artifact selector status: pass/);
  assert.match(markdown, /Terminal artifacts selected: 2/);
  assert.match(markdown, /Terminal artifacts candidates: 4/);
});

test('warns when selected terminal artifacts do not produce input files', () => {
  const report = summarizeTerminalDispositionCoverage([], {
    artifact_selection_report: {
      schema: 'workflows-weekly-metrics-artifact-selection/v1',
      status: 'pass',
      candidate_family_counts: {
        'verifier-terminal-disposition': 1,
      },
      selected_family_counts: {
        'verifier-terminal-disposition': 1,
      },
      selected_artifacts: [
        { id: 10, name: 'verifier-terminal-disposition-123', family: 'verifier-terminal-disposition' },
      ],
    },
    input_file_count: 0,
  });
  const markdown = formatTerminalDispositionCoverageMarkdown(report);

  assert.equal(report.status, 'warning');
  assert.equal(report.terminal_artifact_input_mismatch, true);
  assert.deepEqual(report.enforcement.blockers, [
    'no-terminal-disposition-records',
    'selected-terminal-artifacts-without-input-files',
  ]);
  assert.match(markdown, /Terminal artifact input mismatch/);
});

test('warns when configured artifact selection report is missing', () => {
  const report = summarizeTerminalDispositionCoverage([], {
    artifact_selection_report: readArtifactSelectionReport('/tmp/does-not-exist-terminal-selection.json'),
  });

  assert.equal(report.status, 'warning');
  assert.equal(report.artifact_selection.status, 'missing');
  assert.match(report.artifact_selection.error_message, /not found/);
});

test('normalizes artifact selection reports without selected family counts', () => {
  assert.deepEqual(
    normalizeArtifactSelectionSummary({
      status: 'pass',
      candidate_family_counts: {
        'review-thread-terminal-disposition': 1,
      },
      selected_artifacts: [
        { id: 42, name: 'review-thread-terminal-disposition-77' },
        { id: 43, name: 'agents-verifier-metrics' },
      ],
    }),
    {
      schema: 'workflows-weekly-metrics-artifact-selection/v1',
      status: 'pass',
      error_message: '',
      candidate_terminal_artifact_count: 1,
      selected_terminal_artifact_count: 1,
      selected_terminal_artifacts: [
        { id: 42, name: 'review-thread-terminal-disposition-77', family: 'review-thread-terminal-disposition' },
      ],
    }
  );
});

test('collects only terminal disposition ndjson files from metrics artifacts', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'terminal-coverage-'));
  const terminalDir = path.join(dir, 'review-thread-terminal-disposition-123', 'agent-metrics');
  const keepaliveDir = path.join(dir, 'keepalive-metrics');
  fs.mkdirSync(terminalDir, { recursive: true });
  fs.mkdirSync(keepaliveDir, { recursive: true });
  const reviewThreadFile = path.join(terminalDir, 'review-thread-terminal-disposition.ndjson');
  const verifierFile = path.join(terminalDir, 'verifier-terminal-disposition.ndjson');
  const keepaliveFile = path.join(keepaliveDir, 'keepalive.ndjson');
  fs.writeFileSync(reviewThreadFile, '{}\n', 'utf8');
  fs.writeFileSync(verifierFile, '{}\n', 'utf8');
  fs.writeFileSync(keepaliveFile, '{"metric":"keepalive"}\n', 'utf8');

  assert.equal(isTerminalDispositionNdjsonFile(reviewThreadFile), true);
  assert.equal(isTerminalDispositionNdjsonFile(keepaliveFile), false);
  assert.deepEqual(collectNdjsonFiles(dir), [reviewThreadFile, verifierFile].sort());
});
