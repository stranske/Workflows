'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert');

const {
  collectDismissable,
  formatDismissLog,
  runCli,
} = require('../bot-comment-dismiss');

describe('bot-comment-dismiss', () => {
  it('collects bot comments in ignored paths', () => {
    const comments = [
      { id: 1, path: '.agents/issue-1-ledger.yml', user: { login: 'copilot[bot]' } },
      { id: 2, path: 'src/app.js', user: { login: 'copilot[bot]' } },
      { id: 3, path: '.agents/notes.txt', user: { login: 'coderabbitai[bot]' } },
      { id: 4, path: '.agents/issue-2-ledger.yml', user: { login: 'octocat' } },
    ];

    const dismissable = collectDismissable(comments, {
      ignoredPaths: ['.agents/'],
      botAuthors: ['copilot[bot]', 'coderabbitai[bot]'],
    });

    assert.deepStrictEqual(dismissable, [
      { id: 1, path: '.agents/issue-1-ledger.yml', author: 'copilot[bot]' },
      { id: 3, path: '.agents/notes.txt', author: 'coderabbitai[bot]' },
    ]);
  });

  it('formats log lines with author and path', () => {
    const log = formatDismissLog({ id: 42, path: '.agents/issue-9-ledger.yml', author: 'copilot[bot]' });
    assert.equal(log, 'Auto-dismissed review comment 42 by copilot[bot] in .agents/issue-9-ledger.yml');
  });

  it('runs cli with env overrides', () => {
    const env = {
      COMMENTS_JSON: JSON.stringify([
        { id: 9, path: '.agents/issue-9-ledger.yml', user: { login: 'copilot[bot]' } },
        { id: 10, path: 'src/app.js', user: { login: 'copilot[bot]' } },
      ]),
      IGNORED_PATHS: '.agents/',
      BOT_AUTHORS: 'copilot[bot]'
    };

    const result = runCli(env);

    assert.deepStrictEqual(result.dismissable, [
      { id: 9, path: '.agents/issue-9-ledger.yml', author: 'copilot[bot]' },
    ]);
    assert.deepStrictEqual(result.logs, [
      'Auto-dismissed review comment 9 by copilot[bot] in .agents/issue-9-ledger.yml',
    ]);
  });
});
