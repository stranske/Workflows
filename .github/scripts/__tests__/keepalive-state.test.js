'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  parseStateComment,
  formatStateComment,
  deepMerge,
  createKeepaliveStateManager,
  loadKeepaliveState,
  calculateElapsedTime,
} = require('../keepalive_state.js');

const buildGithubStub = ({ comments = [] } = {}) => {
  const actions = [];
  const commentStore = comments.map((comment) => ({ ...comment }));
  let nextId = 101 + commentStore.length;
  const github = {
    actions,
    rest: {
      issues: {
        listComments: async () => ({ data: commentStore }),
        getComment: async ({ comment_id: commentId }) => {
          const match = commentStore.find((comment) => comment.id === commentId);
          return { data: match || { id: commentId, body: '' } };
        },
        createComment: async ({ body }) => {
          const id = nextId++;
          const record = { id, body, html_url: `https://example.com/${id}` };
          commentStore.push(record);
          actions.push({ type: 'create', body });
          return { data: { id, html_url: record.html_url } };
        },
        updateComment: async ({ body, comment_id: commentId }) => {
          const match = commentStore.find((comment) => comment.id === commentId);
          if (match) {
            match.body = body;
          } else {
            commentStore.push({ id: commentId, body, html_url: `https://example.com/${commentId}` });
          }
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

test('createKeepaliveStateManager preserves summary body when updating state', async () => {
  const initialBody = [
    '## Keepalive Summary',
    '',
    formatStateComment({ trace: 'trace-1', round: '7', pr_number: 42 }),
  ].join('\n');
  const github = buildGithubStub({
    comments: [
      { id: 77, body: initialBody, html_url: 'https://example.com/77' },
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
  assert.match(github.actions[0].body, /## Keepalive Summary/);
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
  assert.ok(Number.isFinite(Date.parse(result.state.current_iteration_at)));
});

test('parseStateComment returns empty data for malformed payload', () => {
  const body = '<!-- keepalive-state:v1 {"trace":"x", } -->';
  const parsed = parseStateComment(body);
  assert.deepEqual(parsed, { version: 'v1', data: {} });
});

test('parseStateComment returns null when marker missing', () => {
  const parsed = parseStateComment('no marker here');
  assert.equal(parsed, null);
});

test('loadKeepaliveState returns empty state when comment missing', async () => {
  const github = buildGithubStub({ comments: [] });
  const result = await loadKeepaliveState({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 88,
    trace: 'trace-y',
  });
  assert.deepEqual(result, { state: {}, commentId: 0, commentUrl: '' });
});

test('createKeepaliveStateManager returns inert manager with invalid input', async () => {
  const github = buildGithubStub();
  const manager = await createKeepaliveStateManager({
    github,
    context: { repo: { owner: '', repo: '' } },
    prNumber: 0,
    trace: 'trace-1',
    round: '1',
  });
  assert.deepEqual(manager.state, {});
  const result = await manager.save({ head_sha: 'abc' });
  assert.deepEqual(result, { state: {}, commentId: 0, commentUrl: '' });
});

test('deepMerge ignores undefined values', () => {
  const merged = deepMerge({ a: 1, nested: { x: 1 } }, { a: undefined, nested: { x: undefined, y: 2 } });
  assert.deepEqual(merged, { a: 1, nested: { x: 1, y: 2 } });
});

test('loadKeepaliveState sets first_iteration_at on first iteration', async () => {
  const storedBody = formatStateComment({ trace: 'trace-x', iteration: 1, version: 'v1' });
  const github = buildGithubStub({ comments: [{ id: 11, body: storedBody, html_url: 'https://example.com/11' }] });
  const result = await loadKeepaliveState({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 11,
    trace: 'trace-x',
  });
  assert.ok(Number.isFinite(Date.parse(result.state.current_iteration_at)));
  assert.ok(Number.isFinite(Date.parse(result.state.first_iteration_at)));
});

test('loadKeepaliveState does not set first_iteration_at after first iteration', async () => {
  const storedBody = formatStateComment({ trace: 'trace-x', iteration: 3, version: 'v1' });
  const github = buildGithubStub({ comments: [{ id: 12, body: storedBody, html_url: 'https://example.com/12' }] });
  const result = await loadKeepaliveState({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 12,
    trace: 'trace-x',
  });
  assert.ok(Number.isFinite(Date.parse(result.state.current_iteration_at)));
  assert.equal(result.state.first_iteration_at, undefined);
});

test('loadKeepaliveState does not set first_iteration_at before first iteration', async () => {
  const storedBody = formatStateComment({ trace: 'trace-x', iteration: 0, version: 'v1' });
  const github = buildGithubStub({ comments: [{ id: 13, body: storedBody, html_url: 'https://example.com/13' }] });
  const result = await loadKeepaliveState({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 13,
    trace: 'trace-x',
  });
  assert.ok(Number.isFinite(Date.parse(result.state.current_iteration_at)));
  assert.equal(result.state.first_iteration_at, undefined);
});

test('createKeepaliveStateManager stores iteration_duration on save', async () => {
  const realNow = Date.now;
  let now = 1700000000000;
  Date.now = () => now;
  try {
    const github = buildGithubStub();
    const manager = await createKeepaliveStateManager({
      github,
      context: { repo: { owner: 'o', repo: 'r' } },
      prNumber: 42,
      trace: 'trace-1',
      round: '3',
    });
    now += 65_000;
    const saved = await manager.save({});
    assert.equal(saved.state.iteration_duration, '1m 5s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime returns 0s for null and invalid values', () => {
  assert.equal(calculateElapsedTime(null), '0s');
  assert.equal(calculateElapsedTime('invalid'), '0s');
});

test('calculateElapsedTime formats elapsed time', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = new Date(now - (5 * 60 * 1000 + 23 * 1000)).toISOString();
    assert.equal(calculateElapsedTime(start), '5m 23s');
  } finally {
    Date.now = realNow;
  }
});
