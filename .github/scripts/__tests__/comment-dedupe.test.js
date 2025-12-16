'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  selectMarkerComment,
  extractAnchoredMetadata,
  findAnchoredComment,
  ensureMarkerComment,
  removeMarkerComments,
  upsertAnchoredComment,
} = require('../comment-dedupe');

test('selectMarkerComment prefers marker comment', () => {
  const comments = [
    { id: 1, body: 'Irrelevant' },
    { id: 2, body: 'Gate fast-pass message' },
    { id: 3, body: 'Gate fast-pass message\n<!-- gate-docs-only -->' },
    { id: 4, body: 'Gate fast-pass message (legacy)' },
  ];
  const { target, duplicates } = selectMarkerComment(comments, {
    marker: '<!-- gate-docs-only -->',
    baseMessage: 'Gate fast-pass message',
  });
  assert.equal(target.id, 3);
  assert.deepEqual(duplicates.map(item => item.id), [2, 4]);
});

test('extractAnchoredMetadata parses pr and head', () => {
  const body = 'status\n<!-- maint-46-post-ci: pr=123 head=abc123 -->';
  const anchor = extractAnchoredMetadata(body, /<!--\s*maint-46-post-ci:([^>]*)-->/i);
  assert.equal(anchor.pr, '123');
  assert.equal(anchor.head, 'abc123');
});

test('findAnchoredComment matches anchor metadata first', () => {
  const comments = [
    { id: 1, body: 'First <!-- maint-46-post-ci: pr=1 head=aaa -->' },
    { id: 2, body: 'Second <!-- maint-46-post-ci: pr=2 head=bbb -->' },
    { id: 3, body: 'Fallback <!-- maint-46-post-ci:' },
  ];
  const anchor = { pr: '2', head: 'bbb' };
  const result = findAnchoredComment(comments, {
    anchorPattern: /<!--\s*maint-46-post-ci:([^>]*)-->/i,
    fallbackMarker: '<!-- maint-46-post-ci:',
    targetAnchor: anchor,
  });
  assert.equal(result.id, 2);

  const missingAnchor = findAnchoredComment(comments, {
    anchorPattern: /<!--\s*maint-46-post-ci:([^>]*)-->/i,
    fallbackMarker: '<!-- maint-46-post-ci:',
    targetAnchor: { pr: '9', head: 'zzz' },
  });
  assert.equal(missingAnchor.id, 1);
});

test('ensureMarkerComment updates marker comment and prunes duplicates', async () => {
  const actions = [];
  const comments = [
    { id: 1, body: 'Gate fast-pass message\n<!-- gate-docs-only -->' },
    { id: 2, body: 'Gate fast-pass message' },
  ];
  const github = {
    paginate: async () => comments,
    rest: {
      issues: {
        listComments: async () => ({ data: comments }),
        updateComment: async ({ comment_id, body }) => {
          actions.push({ type: 'update', id: comment_id, body });
        },
        createComment: async () => {
          throw new Error('createComment should not be called');
        },
        deleteComment: async ({ comment_id }) => {
          actions.push({ type: 'delete', id: comment_id });
        },
      },
    },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'test', repo: 'repo' },
    payload: { pull_request: { number: 42 } },
  };

  await ensureMarkerComment({
    github,
    context,
    core: null,
    commentBody: 'Updated message\n<!-- gate-docs-only -->',
    marker: '<!-- gate-docs-only -->',
    baseMessage: 'Gate fast-pass message',
  });

  assert.deepEqual(actions, [
    { type: 'update', id: 1, body: 'Updated message\n<!-- gate-docs-only -->' },
    { type: 'delete', id: 2 },
  ]);
});

test('removeMarkerComments deletes marker and legacy comments', async () => {
  const deleted = [];
  const comments = [
    { id: 1, body: 'Gate fast-pass message\n<!-- gate-docs-only -->' },
    { id: 2, body: 'Gate fast-pass message' },
    { id: 3, body: 'Unrelated comment' },
  ];
  const github = {
    paginate: async () => comments,
    rest: {
      issues: {
        listComments: async () => ({ data: comments }),
        deleteComment: async ({ comment_id }) => {
          deleted.push(comment_id);
        },
      },
    },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'test', repo: 'repo' },
    payload: { pull_request: { number: 42 } },
  };

  await removeMarkerComments({
    github,
    context,
    core: null,
    marker: '<!-- gate-docs-only -->',
    baseMessages: ['Gate fast-pass message'],
  });

  assert.deepEqual(deleted, [1, 2]);
});

test('upsertAnchoredComment reads body from file and infers PR from anchor', async () => {
  const updated = [];
  const created = [];
  const tmp = require('node:os').tmpdir();
  const path = require('node:path');
  const fs = require('node:fs');
  const commentPath = path.join(tmp, `maint-comment-${Date.now()}.md`);
  fs.writeFileSync(commentPath, 'status\n<!-- maint-46-post-ci: pr=99 head=abc -->\n');

  const github = {
    paginate: async () => [{ id: 1, body: 'status\n<!-- maint-46-post-ci: pr=99 head=zzz -->' }],
    rest: {
      issues: {
        listComments: async () => ({ data: [] }),
        updateComment: async payload => updated.push(payload),
        createComment: async payload => {
          created.push(payload);
          return { data: { id: 2 } };
        },
      },
    },
  };

  await upsertAnchoredComment({
    github,
    context: { repo: { owner: 'octo', repo: 'demo' } },
    core: null,
    commentPath,
    prNumber: '',
  });

  if (updated.length) {
    const [payload] = updated;
    assert.equal(payload.comment_id, 1);
  } else {
    assert.equal(created.length, 1);
    assert.equal(created[0].issue_number, 99);
  }

  fs.unlinkSync(commentPath);
});
