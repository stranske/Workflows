'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const scriptPath = path.join(__dirname, '..', '.github', 'scripts', 'should-post-review.js');
const fixturesDir = path.join(__dirname, 'fixtures', 'review_result');

function runScript(filePath) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'should-post-review-'));
  const outputPath = path.join(dir, 'github_output.txt');
  const args = [scriptPath];
  if (filePath) {
    args.push(filePath);
  }
  const result = spawnSync('node', args, {
    env: { ...process.env, GITHUB_OUTPUT: outputPath },
    encoding: 'utf8',
  });

  assert.equal(result.status, 0, result.stderr || 'script failed');

  const raw = fs.readFileSync(outputPath, 'utf8').trim();
  const lines = raw ? raw.split(/\r?\n/) : [];
  assert.equal(lines.length, 1, 'should write exactly one output line');
  return lines[0];
}

test('should-post-review returns false when file is missing', () => {
  const missingPath = path.join(os.tmpdir(), 'missing-review-result.json');
  const line = runScript(missingPath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns false when review is null', () => {
  const filePath = path.join(fixturesDir, 'review-null.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns false when review JSON is invalid', () => {
  const filePath = path.join(fixturesDir, 'review-invalid.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns false when review is empty string', () => {
  const filePath = path.join(fixturesDir, 'review-empty-string.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns false when review has only empty fields', () => {
  const filePath = path.join(fixturesDir, 'review-all-empty.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns true when review has populated fields', () => {
  const filePath = path.join(fixturesDir, 'review-populated.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=true');
});
