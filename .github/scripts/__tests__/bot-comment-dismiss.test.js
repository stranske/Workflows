'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert');

const {
  collectDismissable,
  dismissReviewComments,
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

  it('dismisses comments and logs each dismissal', async () => {
    const deleted = [];
    const github = {
      rest: {
        pulls: {
          deleteReviewComment: async ({ comment_id }) => {
            deleted.push(comment_id);
          },
        },
      },
    };
    const logs = [];
    const logger = {
      info: (line) => logs.push(line),
    };

    const result = await dismissReviewComments({
      github,
      owner: 'octo',
      repo: 'repo',
      dismissable: [
        { id: 1, path: '.agents/issue-1-ledger.yml', author: 'copilot[bot]' },
        { id: 2, path: '.agents/issue-2-ledger.yml', author: 'coderabbitai[bot]' },
      ],
      logger,
    });

    assert.deepStrictEqual(deleted, [1, 2]);
    assert.deepStrictEqual(result.dismissed, [
      { id: 1, path: '.agents/issue-1-ledger.yml', author: 'copilot[bot]' },
      { id: 2, path: '.agents/issue-2-ledger.yml', author: 'coderabbitai[bot]' },
    ]);
    assert.deepStrictEqual(result.logs, [
      'Auto-dismissed review comment 1 by copilot[bot] in .agents/issue-1-ledger.yml',
      'Auto-dismissed review comment 2 by coderabbitai[bot] in .agents/issue-2-ledger.yml',
    ]);
    assert.deepStrictEqual(logs, result.logs);
  });

  it('tracks failures when dismissal fails', async () => {
    const github = {
      rest: {
        pulls: {
          deleteReviewComment: async () => {
            throw new Error('nope');
          },
        },
      },
    };

    const result = await dismissReviewComments({
      github,
      owner: 'octo',
      repo: 'repo',
      dismissable: [
        { id: 99, path: '.agents/issue-99-ledger.yml', author: 'copilot[bot]' },
      ],
      logger: { warn: () => {} },
    });

    assert.deepStrictEqual(result.dismissed, []);
    assert.equal(result.failed.length, 1);
    assert.equal(result.failed[0].id, 99);
  });
});
