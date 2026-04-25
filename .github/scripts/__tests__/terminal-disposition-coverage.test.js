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

  assert.equal(report.status, 'no-data');
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
