'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml'), 'utf8');
const start = source.indexOf('            function countUnchecked(text)');
const end = source.indexOf('            async function loadPullRequest', start);
const context = { ...require('../source_context.js') };
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const complete = { body: 'Closes #1061\n## Tasks\n- [x] Implementation\n## Acceptance Criteria\n- [x] Tests pass' };
const snapshot = { issueNumber: 1061, body: '- [ ] Implementation\n- [ ] Tests pass', updatedAt: '2026-11-02T00:00:00Z', failure: '' };
test('completed PR tasks drain despite unchanged source issue boxes (#4389)', () => {
  assert.equal(context.uncheckedTaskFailure(complete, snapshot), '');
});
test('reviewer-added PR task still refuses merge', () => {
  assert.match(context.uncheckedTaskFailure({ ...complete, body: complete.body + '\n- [ ] Reviewer request' }, snapshot), /unchecked tasks/);
});
test('source identity and snapshot failures still refuse merge', () => {
  assert.match(context.uncheckedTaskFailure(complete, { ...snapshot, issueNumber: 99 }), /Unable to bind/);
  assert.equal(context.uncheckedTaskFailure(complete, { ...snapshot, failure: 'API unavailable' }), 'API unavailable');
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
  assert.equal(actions.find(([kind]) => kind === 'update')[1].comment_id, 5);
  assert.match(actions[0][1], /unchecked tasks/);
  actions.length = 0;
  c.authenticatedLogin = '';
  await c.reportTaskRefusal(42, 'abc123', 'unchecked tasks');
  assert.equal(actions.some(([kind]) => kind === 'update'), false);
  assert.match(actions.find(([kind]) => kind === 'create')[1].body, /Head: abc123/);
});
