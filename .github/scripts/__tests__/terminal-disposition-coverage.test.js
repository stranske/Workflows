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
  normalizeExpectedSource,
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
  assert.equal(report.terminal_record_count, 3);
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
