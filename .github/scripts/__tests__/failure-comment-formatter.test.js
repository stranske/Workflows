'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  COMMENT_MARKER,
  formatFailureComment,
  isFailureComment,
} = require('../failure_comment_formatter.js');

test('formatFailureComment includes marker for deduplication', () => {
  const result = formatFailureComment({
    mode: 'keepalive',
    exitCode: '1',
    errorCategory: 'transient',
    errorType: 'infrastructure',
    recovery: 'Retry after a short delay.',
    summary: 'Request timed out',
    runUrl: 'https://github.com/test/repo/actions/runs/123',
  });

  assert.ok(result.includes(COMMENT_MARKER));
});

test('formatFailureComment includes all required fields', () => {
  const result = formatFailureComment({
    mode: 'autofix',
    exitCode: '2',
    errorCategory: 'auth',
    errorType: 'auth',
    recovery: 'Check credentials.',
    summary: 'Bad credentials',
    runUrl: 'https://github.com/test/repo/actions/runs/456',
  });

  assert.ok(result.includes('autofix'));
  assert.ok(result.includes('`2`'));
  assert.ok(result.includes('`auth`'));
  assert.ok(result.includes('Check credentials.'));
  assert.ok(result.includes('Bad credentials'));
  assert.ok(result.includes('[View logs]'));
});

test('formatFailureComment truncates long summaries', () => {
  const longSummary = 'x'.repeat(1000);
  const result = formatFailureComment({
    mode: 'verifier',
    exitCode: '1',
    errorCategory: 'unknown',
    errorType: 'codex',
    recovery: 'Check output.',
    summary: longSummary,
    runUrl: '',
  });

  // Should be truncated to 500 chars + "..."
  assert.ok(result.includes('x'.repeat(500)));
  assert.ok(result.includes('...'));
  assert.ok(!result.includes('x'.repeat(600)));
});

test('formatFailureComment handles missing runUrl gracefully', () => {
  const result = formatFailureComment({
    mode: 'keepalive',
    exitCode: '1',
    errorCategory: 'resource',
    errorType: 'infrastructure',
    recovery: 'Check resource.',
    summary: 'Not found',
    runUrl: '',
  });

  assert.ok(result.includes('N/A'));
});

test('formatFailureComment uses defaults for missing params', () => {
  const result = formatFailureComment({});

  assert.ok(result.includes('unknown'));
  assert.ok(result.includes('No output captured'));
  assert.ok(result.includes('Check logs for details.'));
});

test('isFailureComment returns true for comments with marker', () => {
  const body = `${COMMENT_MARKER}\n## Some content`;
  assert.equal(isFailureComment(body), true);
});

test('isFailureComment returns false for comments without marker', () => {
  const body = '## Some other comment';
  assert.equal(isFailureComment(body), false);
});

test('isFailureComment handles null and undefined', () => {
  assert.equal(isFailureComment(null), false);
  assert.equal(isFailureComment(undefined), false);
  assert.equal(isFailureComment(''), false);
});

test('formatFailureComment produces valid markdown table', () => {
  const result = formatFailureComment({
    mode: 'keepalive',
    exitCode: '1',
    errorCategory: 'logic',
    errorType: 'codex',
    recovery: 'Fix logic error.',
    summary: 'Validation failed',
    runUrl: 'https://example.com/run/789',
  });

  // Check table structure
  assert.ok(result.includes('| Field | Value |'));
  assert.ok(result.includes('|-------|-------|'));
  assert.ok(result.includes('| Exit Code |'));
  assert.ok(result.includes('| Error Category |'));
  assert.ok(result.includes('| Error Type |'));
  assert.ok(result.includes('| Run |'));
});
