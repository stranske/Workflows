'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  EMPTY_REVIEW_REASON,
  evaluateReviewResult,
  isEmptyReviewResult,
  loadReviewResult,
} = require('../keepalive_review_guard');

const writeTmp = (contents) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'keepalive-review-'));
  const filePath = path.join(dir, 'review_result.json');
  fs.writeFileSync(filePath, contents, 'utf8');
  return filePath;
};

test('isEmptyReviewResult flags null, empty string, or empty review object', () => {
  assert.equal(isEmptyReviewResult(null), true);
  assert.equal(isEmptyReviewResult(''), true);
  assert.equal(isEmptyReviewResult('   '), true);
  assert.equal(isEmptyReviewResult({ review: null }), true);
  assert.equal(isEmptyReviewResult({ review: '' }), true);
  assert.equal(isEmptyReviewResult({ review: { score: '', feedback: '', suggestions: '' } }), true);
  assert.equal(isEmptyReviewResult({ score: '', feedback: '', suggestions: '' }), true);
});

test('isEmptyReviewResult allows non-empty required fields', () => {
  assert.equal(isEmptyReviewResult({ review: { score: 7, feedback: 'ok', suggestions: '' } }), false);
  assert.equal(isEmptyReviewResult({ score: 7, feedback: 'ok', suggestions: '' }), false);
  assert.equal(isEmptyReviewResult({ review: { score: 0, feedback: 'low', suggestions: 'fix' } }), false);
});

test('evaluateReviewResult returns skip reason when empty', () => {
  const result = evaluateReviewResult({ review: { score: '', feedback: '', suggestions: '' } });
  assert.deepEqual(result, { shouldPost: false, reason: EMPTY_REVIEW_REASON });
});

test('evaluateReviewResult allows posting for populated payloads', () => {
  const result = evaluateReviewResult({ review: { score: 6, feedback: 'Progressing', suggestions: '' } });
  assert.deepEqual(result, { shouldPost: true, reason: '' });
});

test('loadReviewResult reports missing file as empty payload', () => {
  const result = loadReviewResult(path.join(os.tmpdir(), 'no-such-review.json'));
  assert.equal(result.payload, null);
  assert.equal(result.readError, 'missing-file');
});

test('loadReviewResult parses valid json', () => {
  const filePath = writeTmp(JSON.stringify({ review: { score: 5, feedback: 'ok', suggestions: '' } }));
  const result = loadReviewResult(filePath);
  assert.deepEqual(result.payload, { review: { score: 5, feedback: 'ok', suggestions: '' } });
  assert.equal(result.readError, null);
});

test('loadReviewResult handles empty file', () => {
  const filePath = writeTmp('');
  const result = loadReviewResult(filePath);
  assert.equal(result.payload, '');
  assert.equal(result.readError, null);
});

test('loadReviewResult reports invalid json', () => {
  const filePath = writeTmp('{bad json}');
  const result = loadReviewResult(filePath);
  assert.equal(result.payload, null);
  assert.ok(result.readError);
});
