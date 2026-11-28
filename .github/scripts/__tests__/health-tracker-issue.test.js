'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  TRACKER_LABEL,
  TRACKER_TITLE,
  pickTracker,
  recordTrackerFailure,
} = require('../health_tracker_issue.js');

function fakeGithub(issues) {
  const calls = [];
  const github = {
    rest: {
      issues: {
        listForRepo: async (params) => {
          calls.push(['list', params]);
          return { data: issues };
        },
        create: async (params) => {
          calls.push(['create', params]);
          return { data: { number: 900 } };
        },
        update: async (params) => {
          calls.push(['update', params]);
          return { data: {} };
        },
        createComment: async (params) => {
          calls.push(['comment', params]);
          return { data: {} };
        },
      },
    },
  };
  return { github, calls };
}

const writes = (calls) => calls.filter(([kind]) => kind !== 'list');

test('a failure with no tracker issue creates exactly one issue', async () => {
  const { github, calls } = fakeGithub([]);
  const result = await recordTrackerFailure({
    github, owner: 'o', repo: 'r', source: 'Health 41 Repo Health', detail: 'drift', runUrl: 'u',
  });
  assert.deepEqual(result, { action: 'created', number: 900 });
  assert.equal(writes(calls).length, 1);
  const [, params] = writes(calls)[0];
  assert.equal(params.title, TRACKER_TITLE);
  assert.deepEqual(params.labels, [TRACKER_LABEL]);
  assert.match(params.body, /Health 41 Repo Health failed/);
  assert.match(params.body, /drift/);
  assert.equal(calls[0][1].labels, TRACKER_LABEL);
});

test('a failure with an open tracker issue adds exactly one comment', async () => {
  const { github, calls } = fakeGithub([
    { number: 7, title: TRACKER_TITLE, state: 'open', labels: [{ name: TRACKER_LABEL }] },
  ]);
  const result = await recordTrackerFailure({ github, owner: 'o', repo: 'r', source: 'S' });
  assert.deepEqual(result, { action: 'commented', number: 7 });
  assert.deepEqual(writes(calls).map(([kind]) => kind), ['comment']);
  assert.match(writes(calls)[0][1].body, /No failure detail was captured/);
});

test('a failure with a closed tracker issue reopens it and comments once', async () => {
  const { github, calls } = fakeGithub([
    { number: 3, title: TRACKER_TITLE, state: 'closed', labels: ['other'] },
    { number: 5, title: TRACKER_TITLE, state: 'closed', labels: [] },
  ]);
  const result = await recordTrackerFailure({ github, owner: 'o', repo: 'r', source: 'S' });
  assert.deepEqual(result, { action: 'reopened', number: 5 });
  assert.deepEqual(writes(calls).map(([kind]) => kind), ['update', 'comment']);
  assert.equal(writes(calls)[0][1].state, 'open');
  assert.deepEqual(writes(calls)[0][1].labels, [TRACKER_LABEL]);
});

test('pickTracker ignores the snapshot issue, pull requests, and prefix matches', () => {
  const issues = [
    { number: 1, title: '[health] repository self-check', state: 'open' },
    { number: 2, title: `${TRACKER_TITLE} (old)`, state: 'open' },
    { number: 4, title: TRACKER_TITLE, state: 'open', pull_request: {} },
  ];
  assert.equal(pickTracker(issues), null);
});

test('source is required', async () => {
  const { github } = fakeGithub([]);
  await assert.rejects(() => recordTrackerFailure({ github, owner: 'o', repo: 'r' }), /source/);
});
