'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert');

const {
  autoDismissReviewComments,
  collectDismissable,
  formatDismissLog,
  runCli,
} = require('../../../.github/scripts/bot-comment-dismiss');

describe('bot-comment-dismiss glob matching', () => {
  it('matches nested paths under .agents/**', () => {
    const dismissable = collectDismissable(
      [
        { id: 1, path: '.agents/a/b/c.yml', user: { login: 'copilot[bot]' } },
        { id: 2, path: 'src/agents/file.ts', user: { login: 'copilot[bot]' } },
      ],
      {
        ignoredPaths: ['.agents/**'],
        botAuthors: ['copilot[bot]'],
      }
    );

    assert.deepStrictEqual(dismissable, [
      { id: 1, path: '.agents/a/b/c.yml', author: 'copilot[bot]' },
    ]);
  });

  it('does not dismiss non-matching paths', () => {
    const dismissable = collectDismissable(
      [
        { id: 3, path: 'src/agents/file.ts', user: { login: 'copilot[bot]' } },
      ],
      {
        ignoredPaths: ['.agents/**'],
        botAuthors: ['copilot[bot]'],
      }
    );

    assert.deepStrictEqual(dismissable, []);
  });

  it('dismisses only ignored-path comments in mixed reviews', async () => {
    const deleted = [];
    const github = {
      rest: {
        pulls: {
          listReviewComments: async () => ({
            data: [
              {
                id: 11,
                path: '.agents/issue-test-ledger.yml',
                user: { login: 'copilot[bot]' },
                created_at: '2026-02-08T12:00:10.000Z',
              },
              {
                id: 12,
                path: 'src/app.ts',
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
      ignoredPaths: ['.agents/**'],
      botAuthors: ['copilot[bot]'],
      maxAgeSeconds: 60,
      now: Date.parse('2026-02-08T12:00:30.000Z'),
    });

    assert.deepStrictEqual(result.dismissable, [
      { id: 11, path: '.agents/issue-test-ledger.yml', author: 'copilot[bot]' },
    ]);
    assert.deepStrictEqual(deleted, [11]);
  });

  it('skips old ignored-path comments when maxAgeSeconds is set', async () => {
    const deleted = [];
    const github = {
      rest: {
        pulls: {
          listReviewComments: async () => ({
            data: [
              {
                id: 21,
                path: '.agents/old-ledger.yml',
                user: { login: 'copilot[bot]' },
                created_at: '2026-02-08T12:00:00.000Z',
              },
              {
                id: 22,
                path: '.agents/new-ledger.yml',
                user: { login: 'copilot[bot]' },
                created_at: '2026-02-08T12:00:50.000Z',
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
      ignoredPaths: ['.agents/**'],
      botAuthors: ['copilot[bot]'],
      maxAgeSeconds: 30,
      now: Date.parse('2026-02-08T12:01:00.000Z'),
    });

    assert.deepStrictEqual(result.dismissable, [
      { id: 22, path: '.agents/new-ledger.yml', author: 'copilot[bot]' },
    ]);
    assert.deepStrictEqual(deleted, [22]);
  });

  it('returns a structured log entry for each dismissal', async () => {
    const deleted = [];
    const github = {
      rest: {
        pulls: {
          listReviewComments: async () => ({
            data: [
              {
                id: 31,
                path: '.agents/issue-test-ledger.yml',
                user: { login: 'copilot[bot]' },
                created_at: '2026-02-08T12:00:10.000Z',
              },
              {
                id: 32,
                path: 'src/app.ts',
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
      ignoredPaths: ['.agents/**'],
      botAuthors: ['copilot[bot]'],
      maxAgeSeconds: 60,
      now: Date.parse('2026-02-08T12:00:30.000Z'),
    });

    assert.deepStrictEqual(deleted, [31]);
    assert.deepStrictEqual(result.logs, [
      formatDismissLog({
        id: 31,
        path: '.agents/issue-test-ledger.yml',
        author: 'copilot[bot]',
      }),
    ]);
  });
});

describe('bot-comment-dismiss maxAgeSeconds parsing', () => {
  it('uses the CLI maxAgeSeconds when provided', () => {
    const result = runCli(
      { COMMENTS_JSON: '[]' },
      ['--maxAgeSeconds', '3600']
    );

    assert.strictEqual(result.maxAgeSeconds, 3600);
  });

  it('prefers CLI maxAgeSeconds over environment value', () => {
    const result = runCli(
      { COMMENTS_JSON: '[]', MAX_AGE_SECONDS: '10' },
      ['--maxAgeSeconds', '20']
    );

    assert.strictEqual(result.maxAgeSeconds, 20);
  });

  it('defaults maxAgeSeconds when not provided', () => {
    const result = runCli({ COMMENTS_JSON: '[]' }, []);

    assert.strictEqual(result.maxAgeSeconds, 30);
  });

  it('rejects invalid maxAgeSeconds values', () => {
    assert.throws(
      () => runCli({ COMMENTS_JSON: '[]', MAX_AGE_SECONDS: 'abc' }, []),
      /maxAgeSeconds/i
    );
    assert.throws(
      () => runCli({ COMMENTS_JSON: '[]' }, ['--maxAgeSeconds', '-1']),
      /maxAgeSeconds/i
    );
    assert.throws(
      () => runCli({ COMMENTS_JSON: '[]' }, ['--maxAgeSeconds', '0']),
      /maxAgeSeconds/i
    );
  });
});

describe('bot-comment-dismiss timestamp selection', () => {
  const baseOptions = {
    ignoredPaths: ['.agents/**'],
    botAuthors: ['copilot[bot]'],
    maxAgeSeconds: 30,
    now: Date.parse('2026-02-08T12:01:00.000Z'),
  };

  it('uses created_at when present', () => {
    const dismissable = collectDismissable(
      [
        {
          id: 41,
          path: '.agents/created-at.yml',
          user: { login: 'copilot[bot]' },
          created_at: '2026-02-08T12:00:45.000Z',
        },
      ],
      baseOptions
    );

    assert.deepStrictEqual(dismissable, [
      { id: 41, path: '.agents/created-at.yml', author: 'copilot[bot]' },
    ]);
  });

  it('uses createdAt when present', () => {
    const dismissable = collectDismissable(
      [
        {
          id: 42,
          path: '.agents/created-at-camel.yml',
          user: { login: 'copilot[bot]' },
          createdAt: '2026-02-08T12:00:50.000Z',
        },
      ],
      baseOptions
    );

    assert.deepStrictEqual(dismissable, [
      { id: 42, path: '.agents/created-at-camel.yml', author: 'copilot[bot]' },
    ]);
  });

  it('uses updated_at when present', () => {
    const dismissable = collectDismissable(
      [
        {
          id: 43,
          path: '.agents/updated-at.yml',
          user: { login: 'copilot[bot]' },
          updated_at: '2026-02-08T12:00:55.000Z',
        },
      ],
      baseOptions
    );

    assert.deepStrictEqual(dismissable, [
      { id: 43, path: '.agents/updated-at.yml', author: 'copilot[bot]' },
    ]);
  });

  it('uses updatedAt when present', () => {
    const dismissable = collectDismissable(
      [
        {
          id: 44,
          path: '.agents/updated-at-camel.yml',
          user: { login: 'copilot[bot]' },
          updatedAt: '2026-02-08T12:00:58.000Z',
        },
      ],
      baseOptions
    );

    assert.deepStrictEqual(dismissable, [
      { id: 44, path: '.agents/updated-at-camel.yml', author: 'copilot[bot]' },
    ]);
  });

  it('prefers updated timestamps over created timestamps when both exist', () => {
    const dismissable = collectDismissable(
      [
        {
          id: 45,
          path: '.agents/both-timestamps.yml',
          user: { login: 'copilot[bot]' },
          created_at: '2026-02-08T11:59:00.000Z',
          updated_at: '2026-02-08T12:00:50.000Z',
        },
      ],
      baseOptions
    );

    assert.deepStrictEqual(dismissable, [
      { id: 45, path: '.agents/both-timestamps.yml', author: 'copilot[bot]' },
    ]);
  });
});
