'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert');

const {
  autoDismissReviewComments,
  collectDismissable,
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
});
