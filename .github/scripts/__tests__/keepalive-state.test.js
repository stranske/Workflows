'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  parseStateComment,
  formatStateComment,
  deepMerge,
  createKeepaliveStateManager,
  loadKeepaliveState,
} = require('../keepalive_state.js');

const buildGithubStub = ({ comments = [] } = {}) => {
  const actions = [];
  const github = {
    actions,
    rest: {
      issues: {
        listComments: async () => ({ data: comments }),
        createComment: async ({ body }) => {
          actions.push({ type: 'create', body });
          return { data: { id: 101, html_url: 'https://example.com/101' } };
        },
        updateComment: async ({ body, comment_id: commentId }) => {
          actions.push({ type: 'update', body, commentId });
          return { data: { id: commentId } };
        },
      },
    },
    paginate: async (fn, params) => {
      const result = await fn(params);
      return Array.isArray(result?.data) ? result.data : [];
    },
  };
  return github;
};

test('parseStateComment extracts JSON payload', () => {
  const body = formatStateComment({ trace: 'abc', head_sha: '123', version: 'v1' });
  const parsed = parseStateComment(body);
  assert.deepEqual(parsed, { version: 'v1', data: { trace: 'abc', head_sha: '123', version: 'v1' } });
});

test('deepMerge performs shallow + nested merge', () => {
  const merged = deepMerge({ a: 1, nested: { x: 1, y: 2 } }, { b: 2, nested: { y: 3, z: 4 } });
  assert.deepEqual(merged, { a: 1, b: 2, nested: { x: 1, y: 3, z: 4 } });
});

test('createKeepaliveStateManager creates hidden comment when missing', async () => {
  const github = buildGithubStub();
  const manager = await createKeepaliveStateManager({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 42,
    trace: 'trace-1',
    round: '3',
  });
  assert.equal(manager.state.trace, 'trace-1');
  await manager.save({ head_sha: 'abc123' });
  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'create');
  assert.match(github.actions[0].body, /keepalive-state:v1/);
  assert.match(github.actions[0].body, /"head_sha":"abc123"/);
});

test('createKeepaliveStateManager updates existing comment', async () => {
  const initialBody = formatStateComment({ trace: 'trace-1', round: '7', pr_number: 42 });
  const github = buildGithubStub({
    comments: [
      { id: 55, body: initialBody, html_url: 'https://example.com/55' },
    ],
  });
  const manager = await createKeepaliveStateManager({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 42,
    trace: 'trace-1',
    round: '7',
  });
  await manager.save({ result: { status: 'success' } });
  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'update');
  assert.equal(github.actions[0].commentId, 55);
  assert.match(github.actions[0].body, /"status":"success"/);
});

test('loadKeepaliveState returns stored payload when present', async () => {
  const storedBody = formatStateComment({ trace: 'trace-x', head_sha: 'def', version: 'v1' });
  const github = buildGithubStub({ comments: [{ id: 99, body: storedBody, html_url: 'https://example.com/99' }] });
  const result = await loadKeepaliveState({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 99,
    trace: 'trace-x',
  });
  assert.equal(result.commentId, 99);
  assert.equal(result.commentUrl, 'https://example.com/99');
  assert.equal(result.state.head_sha, 'def');
});
