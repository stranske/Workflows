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

function requireFixture(name) {
  const filePath = path.join(fixturesDir, name);
  assert.ok(fs.statSync(filePath, { throwIfNoEntry: false })?.isFile(), `Missing review fixture: ${name}`);
  return filePath;
}

test('should-post-review returns false when file is missing', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'missing-review-result-'));
  t.after(() => fs.rmdirSync(dir));
  const missingPath = path.join(dir, 'review-result.json');
  const line = runScript(missingPath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns false when review is null', () => {
  const filePath = requireFixture('review-null.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns false when review JSON is invalid', () => {
  const filePath = requireFixture('review-invalid.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns false when review is empty string', () => {
  const filePath = requireFixture('review-empty-string.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns false when review has only empty fields', () => {
  const filePath = requireFixture('review-all-empty.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=false');
});

test('should-post-review returns true when review has populated fields', () => {
  const filePath = requireFixture('review-populated.json');
  const line = runScript(filePath);
  assert.equal(line, 'should_post_review=true');
});
