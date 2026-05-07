'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  collectUnresolvedBotComments,
  listCommentsWithLimit,
  MAX_COMMENT_PAGES,
} = require('../.github/scripts/bot-comment-handler');

test('bot-comment-handler enforces pagination upper bound', async () => {
  let calls = 0;
  const listFn = async () => {
    calls += 1;
    return { data: [{ id: calls }] };
  };

  await listCommentsWithLimit({
    owner: 'octo',
    repo: 'repo',
    issueNumber: 123,
    perPage: 1,
    maxPages: MAX_COMMENT_PAGES,
    listFn,
  });

  assert.ok(calls <= MAX_COMMENT_PAGES);
  assert.equal(calls, MAX_COMMENT_PAGES);
});

test('bot-comment-handler suppresses bot thread when a human replied', () => {
  const comments = [
    {
      id: 1,
      user: { login: 'copilot[bot]' },
      path: 'src/app.py',
      body: 'Please change this.',
    },
    {
      id: 2,
      in_reply_to_id: 1,
      user: { login: 'maintainer' },
      path: 'src/app.py',
      body: 'Handled separately.',
    },
  ];

  assert.deepEqual(
    collectUnresolvedBotComments(comments, { botAuthors: ['copilot[bot]'] }),
    [],
  );
});
