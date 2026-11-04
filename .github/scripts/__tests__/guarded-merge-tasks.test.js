'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(
  path.join(__dirname, '../../../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml'),
  'utf8',
);
const start = source.indexOf('            function countUnchecked(text)');
const end = source.indexOf('            async function loadPullRequest', start);
assert.ok(start >= 0 && end > start, 'guarded merge task helpers must exist in the template');
const context = { ...require('../source_context.js') };
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const complete = {
  body: [
    '<!-- meta:issue:1061 -->',
    'Closes #1061',
    '<!-- auto-status-summary:start -->',
    '## Automated Status Summary',
    '#### Tasks',
    '- [x] Implementation',
    '#### Acceptance Criteria',
    '- [x] Tests pass',
    '<!-- auto-status-summary:end -->',
  ].join('\n'),
};
const snapshot = { issueNumber: 1061, body: '- [ ] Implementation\n- [ ] Tests pass', updatedAt: '2026-11-02T00:00:00Z', failure: '' };
test('completed PR tasks drain despite unchanged source issue boxes (#4389)', () => {
  assert.equal(context.uncheckedTaskFailure(complete, snapshot), '');
});

test('fetched source issue stays advisory when the managed PR block is complete', async () => {
  const requests = [];
  const client = { rest: { issues: {
    get: async (args) => {
      requests.push({ ...args });
      return { data: { body: snapshot.body, updated_at: snapshot.updatedAt } };
    },
  } } };
  // These helpers resolve globals at invocation; restore them even on an assertion failure.
  Object.assign(context, { owner: 'o', repo: 'r', withRetry: (fn) => fn(client) });
  try {
    const fetched = await context.linkedIssueTaskSnapshot(complete);
    assert.deepEqual(requests, [{ owner: 'o', repo: 'r', issue_number: 1061 }]);
    assert.equal(fetched.body, snapshot.body);
    assert.equal(fetched.updatedAt, snapshot.updatedAt);
    assert.equal(context.uncheckedTaskFailure(complete, fetched), '');
  } finally {
    delete context.owner;
    delete context.repo;
    delete context.withRetry;
  }
});

for (const task of ['Implementation', 'Tests pass']) {
  test(`unchecked managed ${task} task refuses merge even when the source is complete`, () => {
    const pr = { body: complete.body.replace(`- [x] ${task}`, `- [ ] ${task}`) };
    const checkedSource = { ...snapshot, body: snapshot.body.replaceAll('[ ]', '[x]') };
    assert.match(context.uncheckedTaskFailure(pr, checkedSource), /unchecked tasks/);
  });
}

for (const checkbox of ['- [ ]', '* [ ]', '+ [ ]', '1. [ ]', '2) [ ]']) {
  for (const position of ['before', 'after']) {
    test(`reviewer task ${checkbox} ${position} the managed block refuses merge`, () => {
      const request = `${checkbox} Reviewer request\r\n`;
      const body = position === 'before' ? request + complete.body : complete.body + '\n' + request;
      assert.match(context.uncheckedTaskFailure({ body }, snapshot), /unchecked tasks/);
      assert.equal(context.uncheckedTaskFailure({ body: body.replace('[ ]', '[x]') }, snapshot), '');
    });
  }
}

test('quoted source-issue mirror does not override completed managed PR tasks', () => {
  const mirror = snapshot.body.split('\n').map((line) => `> ${line}`).join('\n');
  assert.equal(context.uncheckedTaskFailure({ body: complete.body + '\n' + mirror }, snapshot), '');
});

test('reviewer-added PR task still refuses merge', () => {
  assert.match(context.uncheckedTaskFailure({ ...complete, body: complete.body + '\n- [ ] Reviewer request' }, snapshot), /unchecked tasks/);
});
test('source identity and snapshot failures still refuse merge', () => {
  assert.match(context.uncheckedTaskFailure(complete), /Unable to bind/);
  assert.match(context.uncheckedTaskFailure(complete, { ...snapshot, issueNumber: 99 }), /Unable to bind/);
  assert.equal(context.uncheckedTaskFailure(complete, { ...snapshot, failure: 'API unavailable' }), 'API unavailable');
});

for (const unavailable of ['missing version', 'read failure']) {
  test(`source ${unavailable} still refuses a PR with complete tasks`, async () => {
    const client = { rest: { issues: { get: async () => {
      if (unavailable === 'read failure') throw new Error('API unavailable');
      return { data: { body: snapshot.body } };
    } } } };
    Object.assign(context, { owner: 'o', repo: 'r', withRetry: (fn) => fn(client) });
    try {
      const fetched = await context.linkedIssueTaskSnapshot(complete);
      assert.equal(fetched.issueNumber, 1061);
      assert.match(fetched.failure, /refusing to merge blind/);
      assert.equal(context.uncheckedTaskFailure(complete, fetched), fetched.failure);
    } finally {
      delete context.owner;
      delete context.repo;
      delete context.withRetry;
    }
  });
}

test('ambiguous source metadata cannot bypass source validation', () => {
  const pr = { body: complete.body + '\n<!-- meta:issue:99 -->' };
  assert.match(context.uncheckedTaskFailure(pr, snapshot), /Ambiguous linked issue/);
});

test('refusal receipt updates only its writer and survives unavailable identity', async () => {
  const actions = [];
  const c = {
    authenticatedLogin: 'owner', owner: 'o', repo: 'r',
    core: { warning: (message) => actions.push(['warning', message]), info: () => {} },
    github: { rest: { issues: {
      listComments() {},
      updateComment: async (args) => actions.push(['update', args]),
      createComment: async (args) => actions.push(['create', args]),
    }, users: { getAuthenticated: async () => { throw new Error('installation token'); } } } },
    withRetry: (fn) => fn(c.github),
    paginateWithRetry: async () => [
      { id: 5, user: { login: 'owner' }, body: '<!-- agents-guarded-merge-result:v1 -->' },
      { id: 6, user: { login: 'foreign' }, body: '<!-- agents-guarded-merge-result:v1 -->' },
    ],
  };
  vm.createContext(c);
  const report = source.slice(source.indexOf('            async function reportTaskRefusal'), source.indexOf('            async function loadPullRequest'));
  vm.runInContext(report, c);
  await c.reportTaskRefusal(42, 'abc123', 'unchecked tasks');
  const update = actions.find(([kind]) => kind === 'update')[1];
  assert.equal(update.comment_id, 5);
  assert.equal(update.body,
    '<!-- agents-guarded-merge-result:v1 -->\nHead: abc123\nTask precheck refused: unchecked tasks');
  assert.equal(actions[0][1], 'PR #42: unchecked tasks');
  assert.equal(actions.some(([kind]) => kind === 'create'), false);
  actions.length = 0;
  c.authenticatedLogin = '';
  await c.reportTaskRefusal(42, 'abc123', 'unchecked tasks');
  assert.equal(actions.some(([kind]) => kind === 'update'), false);
  const created = actions.find(([kind]) => kind === 'create')[1];
  assert.equal(created.issue_number, 42);
  assert.equal(created.body, update.body);
});
