'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  evaluateReviewResult,
  loadReviewResult,
} = require('../.github/scripts/keepalive_review_guard');

function computeShouldPost(filePath) {
  const { payload, readError } = loadReviewResult(filePath);
  return readError ? false : evaluateReviewResult(payload).shouldPost;
}

test('keepalive_review_guard returns false when review file is missing', () => {
  const missingPath = path.join(os.tmpdir(), 'missing-review-result.json');
  const shouldPost = computeShouldPost(missingPath);
  assert.equal(shouldPost, false);
});

test('keepalive_review_guard returns false when review JSON is invalid', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'review-guard-'));
  const filePath = path.join(dir, 'invalid.json');
  fs.writeFileSync(filePath, '{not-json', 'utf8');
  const shouldPost = computeShouldPost(filePath);
  assert.equal(shouldPost, false);
});

test('keepalive_review_guard returns false when review payload is all-empty object', () => {
  const shouldPost = evaluateReviewResult({}).shouldPost;
  assert.equal(shouldPost, false);
});
