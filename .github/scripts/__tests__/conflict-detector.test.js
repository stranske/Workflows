'use strict';

/**
 * Tests for conflict_detector.js key exported functions.
 * Covers shouldIgnoreConflictFile and the isIgnoredComment behavior
 * (tested indirectly via checkCommentsForConflicts since isIgnoredComment
 * is an internal helper not listed in module.exports at :439).
 *
 * All tests use the real implementation against constructed inputs (no mocks
 * of the module under test).
 *
 * Issue: stranske/Workflows#2335
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const detector = require(path.resolve(__dirname, '..', 'conflict_detector.js'));

// ---------------------------------------------------------------------------
// shouldIgnoreConflictFile
// ---------------------------------------------------------------------------

test('shouldIgnoreConflictFile: returns true for an exact match on an ignored filename', () => {
  assert.equal(detector.shouldIgnoreConflictFile('pr_body.md'), true);
});

test('shouldIgnoreConflictFile: returns true for a path that ends with an ignored filename', () => {
  assert.equal(detector.shouldIgnoreConflictFile('some/nested/dir/pr_body.md'), true);
  assert.equal(detector.shouldIgnoreConflictFile('ci/autofix/history.json'), true);
  assert.equal(detector.shouldIgnoreConflictFile('sub/path/keepalive-metrics.ndjson'), true);
  assert.equal(detector.shouldIgnoreConflictFile('some/path/metrics-history.ndjson'), true);
});

test('shouldIgnoreConflictFile: returns false for a regular source file', () => {
  assert.equal(detector.shouldIgnoreConflictFile('src/index.js'), false);
  assert.equal(detector.shouldIgnoreConflictFile('.github/scripts/token_load_balancer.js'), false);
  assert.equal(detector.shouldIgnoreConflictFile('README.md'), false);
});

test('shouldIgnoreConflictFile: returns false for a path that only partially matches', () => {
  // "my_pr_body.md" ends in "r_body.md" not "/pr_body.md" — not an ignored path.
  assert.equal(detector.shouldIgnoreConflictFile('my_pr_body.md'), false);
  // "not-history.json" does not equal "ci/autofix/history.json" nor ends with "/history.json".
  assert.equal(detector.shouldIgnoreConflictFile('not-history.json'), false);
});

test('shouldIgnoreConflictFile: coverage-trend-history.ndjson is ignored', () => {
  assert.equal(detector.shouldIgnoreConflictFile('coverage-trend-history.ndjson'), true);
  assert.equal(detector.shouldIgnoreConflictFile('logs/coverage-trend-history.ndjson'), true);
});

test('shouldIgnoreConflictFile: residual-trend-history.ndjson is ignored', () => {
  assert.equal(detector.shouldIgnoreConflictFile('residual-trend-history.ndjson'), true);
});

test('shouldIgnoreConflictFile: IGNORED_CONFLICT_FILES list is non-empty', () => {
  assert.ok(
    Array.isArray(detector.IGNORED_CONFLICT_FILES),
    'IGNORED_CONFLICT_FILES should be an array'
  );
  assert.ok(detector.IGNORED_CONFLICT_FILES.length > 0, 'List should not be empty');
});

// ---------------------------------------------------------------------------
// isIgnoredComment behavior — tested through checkCommentsForConflicts
//
// isIgnoredComment is an internal helper (not in module.exports at :439).
// We exercise it via checkCommentsForConflicts, which calls it to filter
// comments before scanning for conflict patterns.  A bot comment containing
// a conflict marker should NOT trigger a conflict result; a human comment
// with the same marker SHOULD.
// ---------------------------------------------------------------------------

/**
 * Build a minimal stub github object whose issues.listComments returns the
 * provided list.  The function uses no other github API surface.
 */
function makeGithubStub(comments) {
  return {
    rest: {
      issues: {
        listComments: async () => ({ data: comments }),
      },
    },
  };
}

const FAKE_CONTEXT = {
  repo: { owner: 'stranske', repo: 'Workflows' },
};

// A definitive git conflict marker that CONFLICT_PATTERNS will match.
const CONFLICT_BODY = '<<<<<<< HEAD\nsome change\n=======\nother change\n>>>>>>> abc1234';

test('isIgnoredComment behavior: bot/automation comment with conflict marker does NOT trigger conflict', async () => {
  const comments = [
    {
      id: 1,
      user: { login: 'github-actions[bot]', type: 'Bot' },
      body: CONFLICT_BODY,
    },
  ];
  const result = await detector.checkCommentsForConflicts(
    makeGithubStub(comments),
    FAKE_CONTEXT,
    1
  );
  // isIgnoredComment should filter out this bot comment → no conflict detected.
  assert.equal(
    result.hasConflict,
    false,
    'Bot comment with conflict text should be ignored'
  );
});

test('isIgnoredComment behavior: human comment with conflict marker DOES trigger conflict', async () => {
  const comments = [
    {
      id: 2,
      user: { login: 'real-human', type: 'User' },
      body: CONFLICT_BODY,
    },
  ];
  const result = await detector.checkCommentsForConflicts(
    makeGithubStub(comments),
    FAKE_CONTEXT,
    1
  );
  // isIgnoredComment should NOT filter out a human comment → conflict detected.
  assert.equal(
    result.hasConflict,
    true,
    'Human comment with git conflict markers should trigger conflict detection'
  );
  assert.equal(result.source, 'pr-comments');
});

test('isIgnoredComment behavior: dependabot[bot] comment with conflict marker is ignored', async () => {
  const comments = [
    {
      id: 3,
      user: { login: 'dependabot[bot]', type: 'Bot' },
      body: CONFLICT_BODY,
    },
  ];
  const result = await detector.checkCommentsForConflicts(
    makeGithubStub(comments),
    FAKE_CONTEXT,
    1
  );
  assert.equal(result.hasConflict, false, 'dependabot[bot] is in IGNORED_COMMENT_AUTHORS');
});

test('isIgnoredComment behavior: comment with keepalive-loop-summary marker is ignored even from a User', async () => {
  const comments = [
    {
      id: 4,
      user: { login: 'some-human', type: 'User' },
      // This marker is in IGNORED_COMMENT_MARKERS, so isIgnoredComment returns true.
      body: 'keepalive-loop-summary\n' + CONFLICT_BODY,
    },
  ];
  const result = await detector.checkCommentsForConflicts(
    makeGithubStub(comments),
    FAKE_CONTEXT,
    1
  );
  assert.equal(result.hasConflict, false, 'Comment with keepalive-loop-summary marker should be ignored');
});

test('isIgnoredComment behavior: no comments yields no conflict', async () => {
  const result = await detector.checkCommentsForConflicts(
    makeGithubStub([]),
    FAKE_CONTEXT,
    1
  );
  assert.equal(result.hasConflict, false);
  assert.equal(result.source, 'pr-comments');
});

test('isIgnoredComment behavior: human comment without conflict markers is benign', async () => {
  const comments = [
    {
      id: 5,
      user: { login: 'real-human', type: 'User' },
      body: 'Looks good to me! LGTM.',
    },
  ];
  const result = await detector.checkCommentsForConflicts(
    makeGithubStub(comments),
    FAKE_CONTEXT,
    1
  );
  assert.equal(result.hasConflict, false);
});
