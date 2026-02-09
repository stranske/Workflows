'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { collectDismissable } = require('../.github/scripts/bot-comment-dismiss');

const fixturesDir = path.join(__dirname, 'fixtures', 'bot_comment_dismiss');

function readFixture(name) {
  const filePath = path.join(fixturesDir, name);
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

describe('bot-comment-dismiss glob matching', () => {
  it('selects only intended comment paths for dismissal', () => {
    const comments = readFixture('glob-positive.json');
    const dismissable = collectDismissable(comments, {
      ignoredPaths: ['.agents/**'],
      ignoredPatterns: ['reports/**/issue-*-ledger.yml'],
      botAuthors: ['copilot[bot]'],
    });

    assert.deepStrictEqual(dismissable, [
      { id: 101, path: '.agents/issue-101-ledger.yml', author: 'copilot[bot]' },
      { id: 102, path: '.agents/nested/notes.md', author: 'copilot[bot]' },
      { id: 103, path: 'reports/2026/issue-103-ledger.yml', author: 'copilot[bot]' },
    ]);
  });

  it('does not select negative control paths', () => {
    const comments = readFixture('glob-negative.json');
    const dismissable = collectDismissable(comments, {
      ignoredPaths: ['.agents/**'],
      ignoredPatterns: ['reports/**/issue-*-ledger.yml'],
      botAuthors: ['copilot[bot]'],
    });

    assert.deepStrictEqual(dismissable, []);
  });
});

describe('bot-comment-dismiss timestamp logic', () => {
  it('uses created_at instead of updated_at when applying max age', () => {
    const tooOld = readFixture('timestamp-created-before-updated-after.json');
    const recent = readFixture('timestamp-created-and-updated-after.json');
    const now = Date.parse('2026-02-08T12:05:10.000Z');

    const dismissableOld = collectDismissable(tooOld, {
      ignoredPaths: ['.agents/**'],
      botAuthors: ['copilot[bot]'],
      maxAgeSeconds: 60,
      now,
    });
    const dismissableRecent = collectDismissable(recent, {
      ignoredPaths: ['.agents/**'],
      botAuthors: ['copilot[bot]'],
      maxAgeSeconds: 60,
      now,
    });

    assert.deepStrictEqual(dismissableOld, []);
    assert.deepStrictEqual(dismissableRecent, [
      { id: 302, path: '.agents/issue-301-ledger.yml', author: 'copilot[bot]' },
    ]);
  });
});
