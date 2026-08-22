'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildBotCommentDispatchComment,
  buildBotCommentsPrompt,
  collectActiveBotReviewThreads,
  collectUnresolvedBotComments,
  getBotCommentAssignees,
  listCommentsWithLimit,
  MAX_COMMENT_PAGES,
  normalizeBoolean,
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

test('bot-comment-handler parses string boolean options', () => {
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

  assert.equal(normalizeBoolean('false', true), false);
  assert.deepEqual(
    collectUnresolvedBotComments(comments, {
      botAuthors: ['copilot[bot]'],
      skipIfHumanReplied: 'false',
    }).map((comment) => comment.id),
    [1],
  );
});

test('bot-comment-handler resolves assignees from agent registry', () => {
  assert.deepEqual(getBotCommentAssignees('claude'), ['stranske-automation-bot']);
});

test('bot-comment-handler keeps active bot threads after a human reply by default', () => {
  const threads = [
    {
      id: 'PRRT_active',
      isResolved: false,
      isOutdated: false,
      path: 'src/app.py',
      line: 12,
      comments: {
        nodes: [
          {
            databaseId: 10,
            author: { login: 'chatgpt-codex-connector' },
            body: 'Cover the execution path.',
            url: 'https://example.test/thread',
          },
          {
            databaseId: 11,
            author: { login: 'maintainer' },
            body: 'Fixed on the current head.',
          },
        ],
      },
    },
    {
      id: 'PRRT_resolved',
      isResolved: true,
      isOutdated: false,
      path: 'src/old.py',
      comments: {
        nodes: [
          { databaseId: 12, author: { login: 'chatgpt-codex-connector' }, body: 'Old.' },
        ],
      },
    },
    {
      id: 'PRRT_outdated',
      isResolved: false,
      isOutdated: true,
      path: 'src/old.py',
      comments: {
        nodes: [
          { databaseId: 13, author: { login: 'chatgpt-codex-connector' }, body: 'Old.' },
        ],
      },
    },
  ];

  const result = collectActiveBotReviewThreads(threads);
  assert.deepEqual(result.map((comment) => comment.thread_id), ['PRRT_active']);
  assert.equal(result[0].replies[0].author, 'maintainer');
  assert.deepEqual(
    collectActiveBotReviewThreads(threads, { skipIfHumanReplied: true }),
    [],
  );
});

test('bot-comment prompt requires exact-thread disposition instead of generic review', () => {
  const comments = [
    {
      id: 10,
      thread_id: 'PRRT_active',
      path: 'src/app.py',
      line: 12,
      author: 'chatgpt-codex-connector',
      body: 'Cover the execution path.',
      url: 'https://example.test/thread',
      diff_hunk: '@@ -1 +1 @@',
    },
  ];
  const prompt = buildBotCommentsPrompt(comments, { headSha: 'abc123' });
  const dispatch = buildBotCommentDispatchComment({
    agent: 'codex',
    count: 1,
    comments,
    headSha: 'abc123',
  });

  for (const text of [prompt, dispatch]) {
    assert.match(text, /PRRT_active/);
    assert.match(text, /abc123/);
    assert.match(text, /generic top-level review|generic review/i);
    assert.match(text, /Never self-resolve/i);
  }
});
