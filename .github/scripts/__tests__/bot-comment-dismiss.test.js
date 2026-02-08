'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert');

const {
  autoDismissReviewComments,
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
        {
          id: 9,
          path: '.agents/issue-9-ledger.yml',
          user: { login: 'copilot[bot]' },
          created_at: '2026-02-08T12:00:00.000Z',
        },
        {
          id: 10,
          path: 'src/app.js',
          user: { login: 'copilot[bot]' },
          created_at: '2026-02-08T12:00:00.000Z',
        },
      ]),
      IGNORED_PATHS: '.agents/',
      BOT_AUTHORS: 'copilot[bot]',
      MAX_AGE_SECONDS: '30',
      NOW_EPOCH_MS: String(Date.parse('2026-02-08T12:00:20.000Z')),
    };

    const result = runCli(env);

    assert.deepStrictEqual(result.dismissable, [
      { id: 9, path: '.agents/issue-9-ledger.yml', author: 'copilot[bot]' },
    ]);
    assert.deepStrictEqual(result.logs, [
      'Auto-dismissed review comment 9 by copilot[bot] in .agents/issue-9-ledger.yml',
    ]);
  });

  it('uses default max age of 30 seconds when not provided', () => {
    const env = {
      COMMENTS_JSON: JSON.stringify([
        {
          id: 21,
          path: '.agents/issue-21-ledger.yml',
          user: { login: 'copilot[bot]' },
          created_at: '2026-02-08T12:00:00.000Z',
        },
        {
          id: 22,
          path: '.agents/issue-22-ledger.yml',
          user: { login: 'copilot[bot]' },
          created_at: '2026-02-08T12:00:40.000Z',
        },
      ]),
      IGNORED_PATHS: '.agents/',
      BOT_AUTHORS: 'copilot[bot]',
      NOW_EPOCH_MS: String(Date.parse('2026-02-08T12:01:00.000Z')),
    };

    const result = runCli(env);

    assert.deepStrictEqual(result.dismissable, [
      { id: 22, path: '.agents/issue-22-ledger.yml', author: 'copilot[bot]' },
    ]);
  });

  it('filters out ignored-path comments older than max age', () => {
    const dismissable = collectDismissable(
      [
        {
          id: 11,
          path: '.agents/issue-11-ledger.yml',
          user: { login: 'copilot[bot]' },
          created_at: '2026-02-08T12:00:00.000Z',
        },
        {
          id: 12,
          path: '.agents/issue-12-ledger.yml',
          user: { login: 'copilot[bot]' },
          created_at: '2026-02-08T12:00:40.000Z',
        },
      ],
      {
        ignoredPaths: ['.agents/'],
        botAuthors: ['copilot[bot]'],
        maxAgeSeconds: 30,
        now: Date.parse('2026-02-08T12:01:00.000Z'),
      }
    );

    assert.deepStrictEqual(dismissable, [
      { id: 12, path: '.agents/issue-12-ledger.yml', author: 'copilot[bot]' },
    ]);
  });

  it('accepts GraphQL-style createdAt timestamps', () => {
    const dismissable = collectDismissable(
      [
        {
          id: 31,
          path: '.agents/issue-31-ledger.yml',
          user: { login: 'copilot[bot]' },
          createdAt: '2026-02-08T12:00:50.000Z',
        },
      ],
      {
        ignoredPaths: ['.agents/'],
        botAuthors: ['copilot[bot]'],
        maxAgeSeconds: 30,
        now: Date.parse('2026-02-08T12:01:10.000Z'),
      }
    );

    assert.deepStrictEqual(dismissable, [
      { id: 31, path: '.agents/issue-31-ledger.yml', author: 'copilot[bot]' },
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

  it('lists review comments and auto-dismisses ignored-path bot comments', async () => {
    const deleted = [];
    const github = {
      rest: {
        pulls: {
          listReviewComments: async () => ({
            data: [
              {
                id: 7,
                path: '.agents/issue-7-ledger.yml',
                user: { login: 'copilot[bot]' },
                created_at: '2026-02-08T12:00:10.000Z',
              },
              {
                id: 8,
                path: 'src/app.js',
                user: { login: 'copilot[bot]' },
                created_at: '2026-02-08T12:00:10.000Z',
              },
            ],
          }),
          deleteReviewComment: async ({ comment_id }) => {
            deleted.push(comment_id);
          },
        },
      },
    };

    const result = await autoDismissReviewComments({
      github,
      owner: 'octo',
      repo: 'repo',
      pullNumber: 123,
      ignoredPaths: ['.agents/'],
      botAuthors: ['copilot[bot]'],
      maxAgeSeconds: 30,
      now: Date.parse('2026-02-08T12:00:20.000Z'),
    });

    assert.deepStrictEqual(result.dismissable, [
      { id: 7, path: '.agents/issue-7-ledger.yml', author: 'copilot[bot]' },
    ]);
    assert.deepStrictEqual(deleted, [7]);
  });

  it('does not dismiss non-ignored comments in mixed reviews', async () => {
    const deleted = [];
    const github = {
      rest: {
        pulls: {
          listReviewComments: async () => ({
            data: [
              {
                id: 41,
                path: '.agents/issue-41-ledger.yml',
                user: { login: 'copilot[bot]' },
                created_at: '2026-02-08T12:00:10.000Z',
              },
              {
                id: 42,
                path: 'src/app.js',
                user: { login: 'copilot[bot]' },
                created_at: '2026-02-08T12:00:10.000Z',
              },
              {
                id: 43,
                path: '.agents/notes.txt',
                user: { login: 'octocat' },
                created_at: '2026-02-08T12:00:10.000Z',
              },
            ],
          }),
          deleteReviewComment: async ({ comment_id }) => {
            deleted.push(comment_id);
          },
        },
      },
    };
    const logs = [];
    const logger = { info: (line) => logs.push(line) };

    const result = await autoDismissReviewComments({
      github,
      owner: 'octo',
      repo: 'repo',
      pullNumber: 321,
      ignoredPaths: ['.agents/'],
      botAuthors: ['copilot[bot]'],
      maxAgeSeconds: 30,
      now: Date.parse('2026-02-08T12:00:20.000Z'),
      logger,
    });

    assert.deepStrictEqual(result.dismissable, [
      { id: 41, path: '.agents/issue-41-ledger.yml', author: 'copilot[bot]' },
    ]);
    assert.deepStrictEqual(deleted, [41]);
    assert.deepStrictEqual(logs, [
      'Auto-dismissed review comment 41 by copilot[bot] in .agents/issue-41-ledger.yml',
    ]);
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
