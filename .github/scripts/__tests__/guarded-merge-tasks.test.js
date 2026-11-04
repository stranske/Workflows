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

const refusalMarker = '<!-- agents-guarded-merge-result:v1 -->';

function refusalHarness({ login = 'owner', comments = [], failAt = '' } = {}) {
  const actions = [];
  const c = {
    authenticatedLogin: login, owner: 'o', repo: 'r',
    core: {
      warning: (message) => actions.push(['warning', message]),
      info: (message) => actions.push(['info', message]),
    },
    github: { rest: { issues: {
      listComments() {},
      updateComment: async (args) => {
        actions.push(['update', args]);
        if (failAt === 'update') throw new Error('update unavailable');
        const comment = comments.find((item) => item.id === args.comment_id);
        comment.body = args.body;
      },
      createComment: async (args) => {
        actions.push(['create', args]);
        if (failAt === 'create') throw new Error('create unavailable');
        comments.push({ id: 100, user: { login: 'owner' }, body: args.body });
      },
    }, users: { getAuthenticated: async () => {
      actions.push(['identity']);
      if (failAt === 'identity') throw new Error('identity unavailable');
      return { data: { login: 'Owner' } };
    } } } },
    withRetry: (fn) => fn(c.github),
    paginateWithRetry: async (method, args) => {
      assert.equal(method, c.github.rest.issues.listComments);
      assert.deepEqual({ ...args }, { owner: 'o', repo: 'r', issue_number: 42, per_page: 100 });
      actions.push(['list']);
      if (failAt === 'list') throw new Error('list unavailable');
      return comments;
    },
  };
  vm.createContext(c);
  const report = source.slice(source.indexOf('            async function reportTaskRefusal'), source.indexOf('            async function loadPullRequest'));
  vm.runInContext(report, c);
  return { c, actions, comments };
}

test('refusal receipt updates only its writer and survives unavailable identity', async () => {
  const { c, actions } = refusalHarness({
    comments: [
      { id: 5, user: { login: 'owner' }, body: refusalMarker },
      { id: 6, user: { login: 'foreign' }, body: refusalMarker },
    ],
    failAt: 'identity',
  });
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
  assert.equal(actions.some(([kind]) => kind === 'list'), false);
});

test('a first refusal creates a receipt which later refusals reuse with the new head and reason', async () => {
  const { c, actions, comments } = refusalHarness();
  const reason = context.uncheckedTaskFailure({ body: complete.body + '\n- [ ] Reviewer request' }, snapshot);
  assert.match(reason, /unchecked tasks/);
  await c.reportTaskRefusal(42, 'first-head', reason);
  assert.equal(actions[0][0], 'warning');
  assert.equal(actions[0][1], `PR #42: ${reason}`);
  const created = actions.find(([kind]) => kind === 'create')[1];
  assert.deepEqual({ ...created }, {
    owner: 'o', repo: 'r', issue_number: 42,
    body: `${refusalMarker}\nHead: first-head\nTask precheck refused: ${reason}`,
  });

  const nextReason = 'Unable to read linked issue #1061; refusing to merge blind.';
  await c.reportTaskRefusal(42, 'second-head', nextReason);
  assert.equal(actions.filter(([kind]) => kind === 'create').length, 1);
  const updated = actions.find(([kind]) => kind === 'update')[1];
  assert.deepEqual({ ...updated }, {
    owner: 'o', repo: 'r', comment_id: 100,
    body: `${refusalMarker}\nHead: second-head\nTask precheck refused: ${nextReason}`,
  });
  assert.equal(comments.length, 1);
  assert.equal(comments[0].body, updated.body);
});

test('identity lookup finds the newest owned receipt among unrelated and foreign comments', async () => {
  const comments = [
    { id: 30, user: { login: 'owner' }, body: 'Ordinary review comment' },
    { id: 20, user: { login: 'OWNER' }, body: refusalMarker },
    { id: 40, user: { login: 'foreign' }, body: refusalMarker },
    { id: 10, user: { login: 'owner' }, body: refusalMarker },
    { id: 50, body: refusalMarker },
  ];
  const { c, actions } = refusalHarness({ login: '', comments });
  await c.reportTaskRefusal(42, 'head', 'unchecked tasks');
  const updated = actions.find(([kind]) => kind === 'update')[1];
  assert.equal(updated.comment_id, 20);
  assert.equal(actions.filter(([kind]) => kind === 'identity').length, 1);
  assert.equal(actions.some(([kind]) => kind === 'create'), false);
  for (const id of [10, 40, 50]) {
    assert.equal(comments.find((comment) => comment.id === id).body, refusalMarker);
  }
  assert.equal(comments.find((comment) => comment.id === 30).body, 'Ordinary review comment');
});

test('a foreign receipt or an ordinary owned comment does not prevent creating a refusal receipt', async () => {
  const comments = [
    { id: 5, user: { login: 'owner' }, body: 'Ordinary review comment' },
    { id: 6, user: { login: 'foreign' }, body: refusalMarker },
  ];
  const { c, actions } = refusalHarness({ comments });
  await c.reportTaskRefusal(42, 'head', 'unchecked tasks');
  assert.equal(actions.filter(([kind]) => kind === 'create').length, 1);
  assert.equal(actions.some(([kind]) => kind === 'update'), false);
  assert.equal(comments[0].body, 'Ordinary review comment');
  assert.equal(comments[1].body, refusalMarker);
});

for (const failAt of ['list', 'create', 'update']) {
  test(`${failAt} failure preserves the refusal warning and reports receipt publication failure`, async () => {
    const comments = failAt === 'update'
      ? [{ id: 5, user: { login: 'owner' }, body: refusalMarker }]
      : [];
    const { c, actions } = refusalHarness({ comments, failAt });
    await assert.doesNotReject(c.reportTaskRefusal(42, 'head', 'unchecked tasks'));
    assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
      ['warning', 'PR #42: unchecked tasks'],
      ['warning', `Unable to publish task refusal for #42: ${failAt} unavailable`],
    ]);
    if (failAt !== 'create') assert.equal(actions.some(([kind]) => kind === 'create'), false);
  });
}

function finalGuardHarness({ finalBody = complete.body, boundaryBody = finalBody } = {}) {
  const harness = refusalHarness();
  const { c, actions } = harness;
  let reads = 0;
  Object.assign(c, require('../source_context.js'), {
    label: 'automerge',
    GENERATED_DELIVERY_HOLD_LABEL: 'delivery:hold',
    runtimeAcRequirement: () => ({ required: false }),
    reviewWindowObservation: async () => ({ observedAtMs: 0 }),
    reviewWindowRemainingMs: async () => 0,
    loadPullRequest: async () => {
      reads += 1;
      actions.push(['pull', reads]);
      return {
        body: reads === 1 ? finalBody : boundaryBody,
        head: { sha: 'current-head' }, base: { ref: 'main' },
        mergeable_state: 'clean', draft: false, labels: [{ name: 'automerge' }],
      };
    },
    checkStateFailure: async (head) => {
      actions.push(['checks', head]);
      return '';
    },
    activeReviewThreadFailure: async (prNumber) => {
      actions.push(['threads', prNumber]);
      return '';
    },
  });
  c.github.rest.repos = { get: async () => ({ data: { default_branch: 'main' } }) };
  c.github.rest.issues.get = async (args) => {
    actions.push(['issue', { ...args }]);
    return { data: { body: snapshot.body, updated_at: snapshot.updatedAt } };
  };
  // Run the shipped task helpers and final guard together, retaining the real
  // source snapshot fetch and refusal publisher instead of stubbing their results.
  vm.runInContext(source.slice(start, end), c);
  const guardStart = source.indexOf('            async function finalMergeGuardFailure(');
  const guardEnd = source.indexOf('            const listedIssues =', guardStart);
  assert.ok(guardStart >= 0 && guardEnd > guardStart, 'final merge guard must exist');
  vm.runInContext(source.slice(guardStart, guardEnd), c);
  return harness;
}

test('final merge guard accepts complete PR tasks with unchecked source tasks at both snapshots', async () => {
  const { c, actions } = finalGuardHarness();
  assert.equal(await c.finalMergeGuardFailure(42, 'current-head'), '');
  assert.deepEqual(actions.filter(([kind]) => kind === 'pull'), [['pull', 1], ['pull', 2]]);
  assert.deepEqual(actions.filter(([kind]) => kind === 'issue'), [
    ['issue', { owner: 'o', repo: 'r', issue_number: 1061 }],
    ['issue', { owner: 'o', repo: 'r', issue_number: 1061 }],
  ]);
  assert.deepEqual(actions.filter(([kind]) => kind === 'checks'), [
    ['checks', 'current-head'], ['checks', 'current-head'],
  ]);
  assert.deepEqual(actions.filter(([kind]) => kind === 'threads'), [
    ['threads', 42], ['threads', 42],
  ]);
  assert.equal(actions.some(([kind]) => ['warning', 'create', 'update'].includes(kind)), false);
});

test('final snapshot task refusal publishes the warning and PR receipt before returning', async () => {
  const { c, actions, comments } = finalGuardHarness({
    finalBody: complete.body + '\n- [ ] Reviewer request',
  });
  const reason = await c.finalMergeGuardFailure(42, 'current-head');
  assert.match(reason, /unchecked tasks/);
  assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
    ['warning', `PR #42: ${reason}`],
  ]);
  assert.equal(comments.length, 1);
  assert.equal(comments[0].body,
    `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`);
  assert.equal(actions.some(([kind]) => kind === 'checks'), false);
  assert.deepEqual(actions.filter(([kind]) => kind === 'pull'), [['pull', 1]]);
});

test('a reviewer task introduced only at the merge boundary still refuses merge', async () => {
  const { c, actions } = finalGuardHarness({
    boundaryBody: complete.body + '\n- [ ] Late reviewer request',
  });
  const reason = await c.finalMergeGuardFailure(42, 'current-head');
  assert.match(reason, /Final merge-boundary task validation failed: .*unchecked tasks/);
  assert.deepEqual(actions.filter(([kind]) => kind === 'pull'), [['pull', 1], ['pull', 2]]);
});
