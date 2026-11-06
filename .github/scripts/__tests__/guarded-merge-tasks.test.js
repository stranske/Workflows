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

test('completion regression rejects counting raw issue boxes and passes after restoration', async () => {
  const { c, actions, comments } = mergeScanHarness();
  const uncheckedTaskFailure = c.uncheckedTaskFailure;
  const reason = 'Refusing auto-merge: linked issue/PR has unchecked tasks.';
  // Restore the latch at its original decision point using the fetched source,
  // without changing checkbox parsing or editing the protected workflow.
  c.uncheckedTaskFailure = (pr, linkedIssueSnapshot) =>
    uncheckedTaskFailure(pr, linkedIssueSnapshot)
    || (c.countUnchecked(linkedIssueSnapshot?.body) > 0 ? reason : '');
  assert.equal(c.uncheckedTaskFailure(complete, {
    ...snapshot, body: snapshot.body.replaceAll('[ ]', '[x]'),
  }), '', 'the deliberate break must depend on the supplied source snapshot');
  const assertCompletedPrCanMerge = async () => {
    await c.runScan();
    assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
      ['output', 'merged', '[42]'],
    ]);
  };
  await assert.rejects(assertCompletedPrCanMerge, { code: 'ERR_ASSERTION' });
  assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
    ['warning', `PR #42: ${reason}`],
  ]);
  assert.equal(comments[0].body,
    `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`);
  assert.equal(actions.some(([kind]) => kind === 'merge'), false);
  assert.equal(actions.some(([kind, message]) => kind === 'info'
    && message.includes('Runtime AC merge guard passed')), false);

  c.uncheckedTaskFailure = uncheckedTaskFailure;
  actions.length = 0;
  await assertCompletedPrCanMerge();
  assert.equal(actions.some(([kind, message]) => kind === 'info'
    && message === 'Runtime AC merge guard passed for PR #42.'), true);
  const merged = actions.find(([kind]) => kind === 'merge')[1];
  assert.equal(merged.sha, 'current-head');
  assert.equal(actions.some(([kind]) => ['warning', 'create', 'update'].includes(kind)), false);
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
  const { c, actions, comments } = finalGuardHarness({
    boundaryBody: complete.body + '\n- [ ] Late reviewer request',
  });
  const reason = await c.finalMergeGuardFailure(42, 'current-head');
  assert.match(reason, /Final merge-boundary task validation failed: .*unchecked tasks/);
  assert.deepEqual(actions.filter(([kind]) => kind === 'pull'), [['pull', 1], ['pull', 2]]);
  assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
    ['warning', `PR #42: ${reason}`],
  ]);
  assert.equal(comments.length, 1);
  assert.equal(comments[0].body,
    `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`);
});

function mergeScanHarness({ body = complete.body, finalBody = body, boundaryBody = finalBody } = {}) {
  const harness = finalGuardHarness({ finalBody: body });
  const { c, actions } = harness;
  const loadPullRequest = c.loadPullRequest;
  const listComments = c.paginateWithRetry;
  let pullReads = 0;
  const summary = {
    addHeading() {},
    addTable: (rows) => actions.push(['summary', rows]),
    write: async () => actions.push(['summary-written']),
  };
  Object.assign(c, require('../runtime_ac_merge_guard.js'), {
    context: { payload: { pull_request: { number: 42 } } },
    defaultBranch: 'main',
    placeholder: /^agents\/[a-z][a-z0-9_-]*-\d+\.md$/i,
    summary,
    reviewWindowObservations: new Map(),
    reviewObservationKey: (number, head) => `${number}@${head}`,
    primeReviewWindows: async () => {},
    reviewGuardFailure: async (number, pr) => ({ pr, failure: '' }),
    loadPullRequest: async (number) => {
      const pr = await loadPullRequest(number);
      pullReads += 1;
      // The first read establishes the head observation; the second scans tasks.
      const currentBody = pullReads <= 2 ? body : pullReads === 3 ? finalBody : boundaryBody;
      return { ...pr, body: currentBody, user: { type: 'Bot' } };
    },
    paginateWithRetry: async (method, args) => {
      if (method === c.github.rest.issues.listForRepo) {
        return [{ number: 42, pull_request: {} }];
      }
      if (method === c.github.rest.pulls.listFiles) {
        return [{ filename: 'src/implementation.js' }];
      }
      return listComments(method, args);
    },
  });
  c.core.setOutput = (name, value) => actions.push(['output', name, value]);
  c.core.setFailed = (message) => assert.fail(message);
  c.github.rest.issues.listForRepo = () => {};
  c.github.rest.issues.listLabelsOnIssue = async () => ({ data: [{ name: 'automerge' }] });
  c.github.rest.issues.removeLabel = async (args) => actions.push(['remove-label', args]);
  c.github.rest.pulls = {
    listFiles() {},
    merge: async (args) => {
      actions.push(['merge', args]);
      return { data: { merged: true } };
    },
  };
  // Exercise the shipped scan's call sites as well as its real task helpers,
  // final guard and runtime acceptance guard. No live API mutation is made.
  const scanStart = source.indexOf('            const listedIssues =');
  assert.ok(scanStart >= 0, 'guarded merge scan must exist');
  vm.runInContext(`async function runScan() {\n${source.slice(scanStart)}\n}`, c);
  return harness;
}

test('guarded scan publishes and reuses a refusal receipt before the runtime guard', async () => {
  const { c, actions, comments } = mergeScanHarness({
    body: complete.body + '\n- [ ] Reviewer request',
  });
  await c.runScan();
  await c.runScan();
  const reason = 'Refusing auto-merge: linked issue/PR has unchecked tasks.';
  assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
    ['warning', `PR #42: ${reason}`], ['warning', `PR #42: ${reason}`],
  ]);
  assert.equal(actions.filter(([kind]) => kind === 'create').length, 1);
  assert.equal(actions.filter(([kind]) => kind === 'update').length, 1);
  assert.equal(comments.length, 1);
  assert.equal(comments[0].body,
    `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`);
  assert.equal(actions.some(([kind]) => kind === 'merge'), false);
  assert.equal(actions.some(([kind, message]) =>
    kind === 'info' && message.includes('Runtime AC merge guard passed')), false);
  assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
    ['output', 'merged', '[]'], ['output', 'merged', '[]'],
  ]);
});

for (const phase of ['initial scan', 'final snapshot']) {
  test(`refusal visibility regression detects a missing publisher at the ${phase} and passes after restoration`, async () => {
    const uncheckedBody = complete.body + '\n- [ ] Reviewer request';
    const { c, actions, comments } = mergeScanHarness({
      body: phase === 'initial scan' ? uncheckedBody : complete.body,
      finalBody: uncheckedBody,
    });
    const publish = c.reportTaskRefusal;
    const reason = 'Refusing auto-merge: linked issue/PR has unchecked tasks.';
    const assertVisibleRefusal = async () => {
      await c.runScan();
      assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
        ['output', 'merged', '[]'],
      ]);
      assert.equal(actions.some(([kind]) => kind === 'merge'), false);
      assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
        ['warning', `PR #42: ${reason}`],
      ]);
      assert.equal(comments.length, 1);
      assert.equal(comments[0].body,
        `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`);
    };

    // Removing the publication must fail the visibility contract even though
    // the refusal itself still prevents merging and reaches the job summary.
    c.reportTaskRefusal = async () => {};
    try {
      await assert.rejects(assertVisibleRefusal, { code: 'ERR_ASSERTION' });
      assert.equal(comments.length, 0);
      const summaryRows = actions.find(([kind]) => kind === 'summary')[1];
      assert.deepEqual([...summaryRows[1]], phase === 'initial scan'
        ? ['#42', 'skipped', reason]
        : ['#42', 'error', `Merge failed: ${reason}`]);
    } finally {
      c.reportTaskRefusal = publish;
    }
    actions.length = 0;
    await assertVisibleRefusal();
  });
}

test('pass line is produced by the runtime guard, not echoed from workflow source', () => {
  // github-script prints the inline script into the job log. The acceptance
  // signal has to come from executing runtime_ac_merge_guard.js, so a refused
  // run must not already contain this sentence in the workflow text.
  assert.equal(source.includes('Runtime AC merge guard passed'), false);
});

const openerBody = [
  '<!-- meta:issue:1061 -->',
  'Closes #1061',
  '<!-- auto-status-summary:start -->',
  '## Tasks',
  '- [x] CI Gate runs `test_headless_ingest_runbook_quickstart_succeeds_on_fresh_layout`',
  '- [x] Deliberate-break → revert on runbook text (per issue acceptance)',
  '- [x] Replace the quickstart in `docs/runbooks/headless_ingest.md:13-19` with a fresh-checkout command.',
  '- [x] Add `tests/docs/test_headless_ingest_runbook.py` that asserts the documented command exits 0.',
  '## Acceptance Criteria',
  '- [x] Named test: `test_headless_ingest_runbook_quickstart_succeeds_on_fresh_layout` exits 0 and writes `run.json`.',
  '- [x] Deliberate-break → revert: restore the broken fixture-only example, confirm the named test fails, then revert.',
  '<!-- auto-status-summary:end -->',
].join('\n');

test('opener shape with a fully checked PR block reaches the runtime guard log line (#4389)', async () => {
  const { c, actions } = mergeScanHarness({ body: openerBody });
  await c.runScan();
  const runtimeIndex = actions.findIndex(([kind, message]) =>
    kind === 'info' && message === 'Runtime AC merge guard passed for PR #42.');
  assert.ok(runtimeIndex >= 0, 'checked opener tasks must reach the runtime guard line');
  assert.equal(actions.some(([kind, message]) =>
    kind === 'warning' && String(message).includes('unchecked tasks')), false);
  assert.equal(actions.some(([kind]) => kind === 'merge'), true);
  assert.equal(actions.filter(([kind]) => kind === 'issue').length, 3);

  const uncheckedTaskFailure = c.uncheckedTaskFailure;
  const reason = 'Refusing auto-merge: linked issue/PR has unchecked tasks.';
  c.uncheckedTaskFailure = (pr, linkedIssueSnapshot) =>
    uncheckedTaskFailure(pr, linkedIssueSnapshot)
    || (c.countUnchecked(linkedIssueSnapshot?.body) > 0 ? reason : '');
  actions.length = 0;
  await c.runScan();
  assert.equal(actions.some(([kind, message]) =>
    kind === 'info' && message === 'Runtime AC merge guard passed for PR #42.'), false);
  assert.equal(actions.some(([kind]) => kind === 'merge'), false);
  assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
    ['warning', `PR #42: ${reason}`],
  ]);
});

test('guarded scan reaches runtime guard and exact-head merge with unchecked source tasks', async () => {
  const { c, actions } = mergeScanHarness();
  await c.runScan();
  const runtimeIndex = actions.findIndex(([kind, message]) =>
    kind === 'info' && message === 'Runtime AC merge guard passed for PR #42.');
  const mergeIndex = actions.findIndex(([kind]) => kind === 'merge');
  assert.ok(runtimeIndex >= 0, 'completed PR must reach the real runtime acceptance guard');
  assert.ok(mergeIndex > runtimeIndex, 'runtime guard must precede the merge API request');
  assert.deepEqual({ ...actions[mergeIndex][1] }, {
    owner: 'o', repo: 'r', pull_number: 42, merge_method: 'squash', sha: 'current-head',
  });
  assert.equal(actions.filter(([kind]) => kind === 'issue').length, 3,
    'source snapshots must remain bound at the initial, final and merge-boundary checks');
  assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
    ['output', 'merged', '[42]'],
  ]);
  assert.equal(actions.some(([kind]) => ['warning', 'create', 'update'].includes(kind)), false);
});

for (const changedField of ['body', 'updated_at']) {
  test(`advisory source tasks do not waive ${changedField} stability at the merge boundary`, async () => {
    const { c, actions } = mergeScanHarness();
    const readIssue = c.github.rest.issues.get;
    let sourceReads = 0;
    c.github.rest.issues.get = async (args) => {
      const response = await readIssue(args);
      if (++sourceReads !== 3) return response;
      return { data: {
        ...response.data,
        [changedField]: changedField === 'body'
          ? snapshot.body.replaceAll('[ ]', '[x]')
          : '2026-11-03T00:00:00Z',
      } };
    };

    await c.runScan();

    assert.equal(sourceReads, 3);
    assert.ok(actions.some(([kind, message]) => kind === 'info'
      && message === 'Runtime AC merge guard passed for PR #42.'));
    assert.equal(actions.some(([kind]) => ['merge', 'remove-label'].includes(kind)), false);
    const summaryRows = actions.find(([kind]) => kind === 'summary')[1];
    assert.deepEqual([...summaryRows[1]], [
      '#42', 'error', 'Merge failed: Linked issue changed during final merge validation.',
    ]);
    assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
      ['output', 'merged', '[]'],
    ]);
  });
}

for (const lateTask of ['managed task', 'reviewer task']) {
  test(`${lateTask} added at the last merge boundary prevents the merge API request`, async () => {
    const boundaryBody = lateTask === 'managed task'
      ? complete.body.replace('- [x] Implementation', '- [ ] Implementation')
      : complete.body + '\n- [ ] Late reviewer request';
    const { c, actions, comments } = mergeScanHarness({ boundaryBody });

    await c.runScan();

    const reason = 'Final merge-boundary task validation failed: Refusing auto-merge: linked issue/PR has unchecked tasks.';
    assert.deepEqual(actions.filter(([kind]) => kind === 'pull'), [
      ['pull', 1], ['pull', 2], ['pull', 3], ['pull', 4],
    ]);
    const runtimeIndex = actions.findIndex(([kind, message]) => kind === 'info'
      && message === 'Runtime AC merge guard passed for PR #42.');
    const warningIndex = actions.findIndex(([kind, message]) =>
      kind === 'warning' && message === `PR #42: ${reason}`);
    assert.ok(runtimeIndex >= 0, 'the initial task check must pass before the final boundary rejects the new task');
    assert.ok(warningIndex > runtimeIndex, 'the boundary refusal must be visible after the runtime guard');
    assert.equal(comments.length, 1);
    assert.equal(comments[0].body,
      `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`);
    assert.equal(actions.some(([kind]) => kind === 'merge'), false);
    const summaryRows = actions.find(([kind]) => kind === 'summary')[1];
    assert.deepEqual([...summaryRows[1]], [
      '#42', 'error', `Merge failed: ${reason}`,
    ]);
    assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
      ['output', 'merged', '[]'],
    ]);
  });
}

test('merge-boundary refusal visibility fails when the publisher is skipped and passes when restored', async () => {
  const boundaryBody = complete.body + '\n- [ ] Late reviewer request';
  const reason = 'Final merge-boundary task validation failed: Refusing auto-merge: linked issue/PR has unchecked tasks.';
  const assertVisibleBoundaryRefusal = async (c, actions, comments) => {
    await c.runScan();
    assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
      ['output', 'merged', '[]'],
    ]);
    assert.equal(actions.some(([kind]) => kind === 'merge'), false);
    assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
      ['warning', `PR #42: ${reason}`],
    ]);
    assert.equal(comments.length, 1);
    assert.equal(comments[0].body,
      `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`);
  };

  // A second scan in one harness continues the pull-read counter, so the break
  // and the restoration each load the shipped scan from a fresh fixture.
  const broken = mergeScanHarness({ boundaryBody });
  broken.c.reportTaskRefusal = async () => {};
  await assert.rejects(
    () => assertVisibleBoundaryRefusal(broken.c, broken.actions, broken.comments),
    { code: 'ERR_ASSERTION' },
  );
  assert.equal(broken.comments.length, 0);
  const summaryRows = broken.actions.find(([kind]) => kind === 'summary')[1];
  assert.deepEqual([...summaryRows[1]], ['#42', 'error', `Merge failed: ${reason}`]);
  assert.ok(broken.actions.some(([kind, message]) => kind === 'info'
    && message === 'Runtime AC merge guard passed for PR #42.'));

  const restored = mergeScanHarness({ boundaryBody });
  await assertVisibleBoundaryRefusal(restored.c, restored.actions, restored.comments);
});

for (const phase of ['initial scan', 'final snapshot']) {
  test(`ambiguous source introduced at the ${phase} publishes an owned refusal without fetching an arbitrary issue`, async () => {
    const ambiguousBody = complete.body + '\n<!-- meta:issue:99 -->';
    const { c, actions, comments } = mergeScanHarness({
      body: phase === 'initial scan' ? ambiguousBody : complete.body,
      finalBody: ambiguousBody,
    });
    comments.push(
      { id: 100, user: { login: 'owner' }, body: refusalMarker },
      { id: 101, user: { login: 'reviewer' }, body: refusalMarker },
    );

    await c.runScan();

    const reason = 'Ambiguous linked issue references; refusing to merge blind.';
    assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
      ['warning', `PR #42: ${reason}`],
    ]);
    assert.deepEqual(actions.filter(([kind]) => kind === 'update').map(([, args]) => ({ ...args })), [{
      owner: 'o', repo: 'r', comment_id: 100,
      body: `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`,
    }]);
    assert.equal(comments.length, 2);
    assert.equal(comments[1].body, refusalMarker);
    assert.equal(actions.filter(([kind]) => kind === 'issue').length,
      phase === 'initial scan' ? 0 : 1,
      'ambiguous metadata must not select an arbitrary source issue');
    assert.equal(actions.some(([kind]) => ['create', 'merge', 'remove-label'].includes(kind)), false);
    assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
      ['output', 'merged', '[]'],
    ]);
  });

  for (const failure of ['read failure', 'missing version']) {
    test(`source ${failure} at the ${phase} warns and updates its owned refusal receipt`, async () => {
      const { c, actions, comments } = mergeScanHarness();
      const previousBody = `${refusalMarker}\nHead: previous-head\nTask precheck refused: previous reason`;
      comments.push(
        { id: 100, user: { login: 'owner' }, body: previousBody },
        { id: 101, user: { login: 'reviewer' }, body: previousBody },
      );
      const readIssue = c.github.rest.issues.get;
      const refusalRead = phase === 'initial scan' ? 1 : 2;
      let sourceReads = 0;
      c.github.rest.issues.get = async (args) => {
        const response = await readIssue(args);
        if (++sourceReads !== refusalRead) return response;
        if (failure === 'read failure') throw new Error('issue unavailable');
        return { data: { body: response.data.body } };
      };

      await c.runScan();

      const reason = failure === 'read failure'
        ? 'Unable to read linked issue #1061; refusing to merge blind: issue unavailable'
        : 'Linked issue #1061 has no version; refusing to merge blind.';
      assert.equal(sourceReads, refusalRead);
      assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
        ['warning', `PR #42: ${reason}`],
      ]);
      const updates = actions.filter(([kind]) => kind === 'update');
      assert.equal(updates.length, 1);
      assert.deepEqual({ ...updates[0][1] }, {
        owner: 'o', repo: 'r', comment_id: 100,
        body: `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`,
      });
      assert.equal(comments.length, 2);
      assert.equal(comments[0].body, updates[0][1].body);
      assert.equal(comments[1].body, previousBody);
      assert.equal(actions.some(([kind]) => ['create', 'merge', 'remove-label'].includes(kind)), false);
      assert.equal(actions.some(([kind, message]) => kind === 'info'
        && message === 'Runtime AC merge guard passed for PR #42.'), phase === 'final snapshot');
      const summaryRows = actions.find(([kind]) => kind === 'summary')[1];
      assert.deepEqual([...summaryRows[1]], phase === 'initial scan'
        ? ['#42', 'skipped', reason]
        : ['#42', 'error', `Merge failed: ${reason}`]);
      assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
        ['output', 'merged', '[]'],
      ]);
    });
  }
}

for (const phase of ['initial scan', 'final snapshot']) {
  test(`failed refusal receipt update at the ${phase} preserves warnings and blocks merge`, async () => {
    const uncheckedBody = complete.body + '\n- [ ] Reviewer request';
    const { c, actions, comments } = mergeScanHarness({
      body: phase === 'initial scan' ? uncheckedBody : complete.body,
      finalBody: uncheckedBody,
    });
    const previousBody = `${refusalMarker}\nHead: previous-head\nTask precheck refused: previous reason`;
    comments.push({ id: 100, user: { login: 'owner' }, body: previousBody });
    c.github.rest.issues.updateComment = async (args) => {
      actions.push(['update-failed', args]);
      throw new Error('comments unavailable');
    };

    await c.runScan();

    const reason = 'Refusing auto-merge: linked issue/PR has unchecked tasks.';
    assert.deepEqual(actions.filter(([kind]) => kind === 'warning'), [
      ['warning', `PR #42: ${reason}`],
      ['warning', 'Unable to publish task refusal for #42: comments unavailable'],
    ]);
    const update = actions.filter(([kind]) => kind === 'update-failed');
    assert.equal(update.length, 1);
    assert.deepEqual({ ...update[0][1] }, {
      owner: 'o', repo: 'r', comment_id: 100,
      body: `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`,
    });
    assert.equal(comments.length, 1);
    assert.equal(comments[0].body, previousBody);
    assert.equal(actions.some(([kind]) => ['create', 'merge'].includes(kind)), false);
    assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
      ['output', 'merged', '[]'],
    ]);
  });
}

for (const publicationFails of [false, true]) {
  test(`task added after the initial scan stays visible and blocks merge when receipt publication ${publicationFails ? 'fails' : 'succeeds'}`, async () => {
    const { c, actions, comments } = mergeScanHarness({
      finalBody: complete.body + '\n- [ ] Late reviewer request',
    });
    if (publicationFails) {
      c.github.rest.issues.createComment = async () => {
        actions.push(['create-failed']);
        throw new Error('comments unavailable');
      };
    }

    await c.runScan();

    const reason = 'Refusing auto-merge: linked issue/PR has unchecked tasks.';
    const runtimeIndex = actions.findIndex(([kind, message]) =>
      kind === 'info' && message === 'Runtime AC merge guard passed for PR #42.');
    const warningIndex = actions.findIndex(([kind, message]) =>
      kind === 'warning' && message === `PR #42: ${reason}`);
    assert.ok(runtimeIndex >= 0, 'the initial task check must pass');
    assert.ok(warningIndex > runtimeIndex, 'the final task check must publish its refusal');
    assert.deepEqual(actions.filter(([kind]) => kind === 'pull'), [
      ['pull', 1], ['pull', 2], ['pull', 3],
    ]);
    assert.equal(actions.some(([kind]) => kind === 'merge'), false);
    const summaryRows = actions.find(([kind]) => kind === 'summary')[1];
    assert.deepEqual([...summaryRows[1]], ['#42', 'error', `Merge failed: ${reason}`]);
    assert.deepEqual(actions.filter(([kind]) => kind === 'output'), [
      ['output', 'merged', '[]'],
    ]);

    if (publicationFails) {
      assert.equal(comments.length, 0);
      assert.ok(actions.some(([kind, message]) => kind === 'warning'
        && message === 'Unable to publish task refusal for #42: comments unavailable'));
      assert.equal(actions.filter(([kind]) => kind === 'create-failed').length, 1);
    } else {
      assert.equal(comments.length, 1);
      assert.equal(comments[0].body,
        `${refusalMarker}\nHead: current-head\nTask precheck refused: ${reason}`);
    }
  });
}
