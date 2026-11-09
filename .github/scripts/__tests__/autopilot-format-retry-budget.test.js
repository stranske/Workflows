'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const budget = require('../autopilot_format_retry_budget.js');

const {
  MAX_FORMAT_RETRIES,
  CAP_MARKER,
  countRetriesSinceCap,
  decideFormatWakeup,
  renderSummary,
  renderComment,
  runFormatWakeup,
} = budget;

const ROOT = path.resolve(__dirname, '../../..');
const WORKFLOWS = [
  '.github/workflows/agents-auto-pilot.yml',
  'templates/consumer-repo/.github/workflows/agents-auto-pilot.yml',
];

let clock = 0;
const bot = (body) => ({
  body,
  created_at: `2026-11-08T00:${String(clock++).padStart(2, '0')}:00Z`,
  user: { login: 'github-actions[bot]', type: 'Bot' },
});
const human = (body) => ({
  body,
  created_at: `2026-11-08T00:${String(clock++).padStart(2, '0')}:00Z`,
  user: { login: 'someone', type: 'User' },
});
// The pre-change wakeup comment, still present on live issues.
const legacyRetry = () => bot('🤖 **Auto-pilot format retry scheduled.**\n\nCleared `agents:auto-pilot-pause` after the bounded backoff and re-dispatched the format step.');
const pausedLabels = ['agents:auto-pilot', 'agents:auto-pilot-pause', 'agent:retry'];

test('the bound is small and positive', () => {
  assert.equal(Number.isInteger(MAX_FORMAT_RETRIES), true);
  assert.ok(MAX_FORMAT_RETRIES >= 1 && MAX_FORMAT_RETRIES <= 3, `MAX_FORMAT_RETRIES=${MAX_FORMAT_RETRIES}`);
});

test('retries within the budget re-dispatch, the next one stops', () => {
  const comments = [];
  for (let i = 0; i < MAX_FORMAT_RETRIES; i += 1) {
    const decision = decideFormatWakeup({ state: 'open', labels: pausedLabels, comments });
    assert.equal(decision.action, 'retry');
    assert.equal(decision.attempt, i + 1);
    comments.push(bot(renderComment(decision)));
  }
  const exhausted = decideFormatWakeup({ state: 'open', labels: pausedLabels, comments });
  assert.equal(exhausted.action, 'cap');
  assert.equal(exhausted.used, MAX_FORMAT_RETRIES);
});

test('Orchestrator#1257 shape: six legacy retries stop immediately', () => {
  const comments = Array.from({ length: 6 }, legacyRetry);
  const decision = decideFormatWakeup({ state: 'open', labels: pausedLabels, comments });
  assert.equal(decision.action, 'cap');
  assert.equal(decision.used, 6);
});

test('a cap marker starts a fresh budget for the next arming', () => {
  const capped = decideFormatWakeup({
    state: 'open', labels: pausedLabels, comments: Array.from({ length: MAX_FORMAT_RETRIES }, legacyRetry),
  });
  const comments = [...Array.from({ length: MAX_FORMAT_RETRIES }, legacyRetry), bot(renderComment(capped))];
  assert.deepEqual(countRetriesSinceCap(comments), { used: 0, capSeen: true });
  assert.equal(decideFormatWakeup({ state: 'open', labels: pausedLabels, comments }).action, 'retry');
});

test('human comments never move the budget', () => {
  const comments = [
    ...Array.from({ length: MAX_FORMAT_RETRIES + 2 }, () => human('Auto-pilot format retry scheduled')),
    human(CAP_MARKER),
  ];
  assert.equal(countRetriesSinceCap(comments).used, 0);
  const spent = [...Array.from({ length: MAX_FORMAT_RETRIES }, legacyRetry), human(CAP_MARKER)];
  assert.equal(decideFormatWakeup({ state: 'open', labels: pausedLabels, comments: spent }).action, 'cap');
});

test('closed, disarmed and PR-linked issues clear the pause without a retry', () => {
  assert.equal(decideFormatWakeup({ state: 'closed', labels: pausedLabels, comments: [] }).reason, 'issue-closed');
  assert.equal(
    decideFormatWakeup({ state: 'open', labels: ['agents:auto-pilot-pause'], comments: [] }).reason,
    'auto-pilot-disarmed',
  );
  const linked = decideFormatWakeup({ state: 'open', labels: pausedLabels, comments: [], linkedOpenPrs: [1260] });
  assert.equal(linked.action, 'clear');
  assert.equal(linked.reason, 'linked-open-pr');
  assert.match(renderComment(linked), /#1260/);
});

test('an unknown linked-PR lookup does not stop a retry, and the budget still bounds it', () => {
  assert.equal(decideFormatWakeup({ state: 'open', labels: pausedLabels, comments: [], linkedOpenPrs: null }).action, 'retry');
  const spent = Array.from({ length: MAX_FORMAT_RETRIES }, legacyRetry);
  assert.equal(decideFormatWakeup({ state: 'open', labels: pausedLabels, comments: spent, linkedOpenPrs: null }).action, 'cap');
});

test('every state prints blocking and drainable counts, including fully drained', () => {
  const retry = decideFormatWakeup({ state: 'open', labels: pausedLabels, comments: [] });
  assert.match(renderSummary(retry), /blocking 1 \(pause\), drainable 1/);
  assert.match(renderSummary(retry), new RegExp(`retry 1/${MAX_FORMAT_RETRIES}`));

  const spent = Array.from({ length: MAX_FORMAT_RETRIES }, legacyRetry);
  const cap = decideFormatWakeup({ state: 'open', labels: pausedLabels, comments: spent });
  assert.match(renderSummary(cap), /exhausted; blocking 1 \(pause\), drainable 1: opener-core/);

  const held = decideFormatWakeup({ state: 'open', labels: [...pausedLabels, 'needs-human'], comments: spent });
  assert.match(renderSummary(held), /drainable 0 by opener-core: held by needs-human/);

  const cleared = decideFormatWakeup({ state: 'closed', labels: pausedLabels, comments: spent });
  assert.match(renderSummary(cleared), /blocking 0, drainable 0: fully drained/);
  const skipped = decideFormatWakeup({ state: 'open', labels: ['agents:auto-pilot'], comments: [] });
  assert.equal(skipped.action, 'skip');
  assert.match(renderSummary(skipped), /blocking 0, drainable 0: fully drained/);
});

test('the cap comment carries the marker opener-core needs and never counts as a retry', () => {
  const spent = Array.from({ length: MAX_FORMAT_RETRIES }, legacyRetry);
  const body = renderComment(decideFormatWakeup({ state: 'open', labels: pausedLabels, comments: spent }));
  assert.ok(body.includes(CAP_MARKER));
  // opener-core blocked_reason(): a paused issue is drainable only with a `format-guard:` comment.
  assert.ok(body.includes('format-guard:'));
  // agents-issue-format-guard.yml parses `format-guard:<12 hex>` fingerprints and the exact
  // `format-guard:attempt-cap` reset; this marker must be neither.
  assert.equal(/<!-- format-guard:([0-9a-f]{12})(?::attempt:\d+)? -->/.test(body), false);
  assert.equal(body.includes('format-guard:attempt-cap'), false);
  assert.equal(body.includes(budget.RETRY_PHRASE), false);
  assert.equal(body.includes(budget.RETRY_MARKER_PREFIX), false);
});

function fakeClient(issue, comments, { prs = [], graphqlError = null } = {}) {
  const calls = [];
  const client = {
    rest: {
      issues: {
        get: async () => ({ data: issue }),
        listComments: Symbol('listComments'),
        removeLabel: async (args) => { calls.push(['removeLabel', args.name]); },
        createComment: async (args) => { calls.push(['comment', args.body]); },
      },
      repos: { get: async () => ({ data: { default_branch: 'main' } }) },
      actions: {
        createWorkflowDispatch: async (args) => { calls.push(['dispatch', args.inputs]); },
      },
    },
    paginate: async () => comments,
    graphql: async () => {
      if (graphqlError) throw graphqlError;
      return { repository: { issue: { closedByPullRequestsReferences: { nodes: prs } } } };
    },
  };
  return { withRetry: (fn) => fn(client), calls };
}

const run = (fake, dispatch) => runFormatWakeup({
  withRetry: fake.withRetry, core: { info() {}, warning() {} }, owner: 'stranske', repo: 'Orchestrator', issueNumber: 1257, dispatch,
});

test('runner: exhausted budget comments once and never dispatches or clears the pause', async () => {
  const fake = fakeClient({ state: 'open', labels: pausedLabels.map((name) => ({ name })) }, Array.from({ length: 6 }, legacyRetry));
  const decision = await run(fake, false);
  assert.equal(decision.action, 'cap');
  assert.equal(fake.calls.filter(([kind]) => kind === 'comment').length, 1);
  assert.equal(fake.calls.filter(([kind]) => kind === 'dispatch').length, 0);
  assert.equal(fake.calls.filter(([kind]) => kind === 'removeLabel').length, 0);
});

test('runner: pre-backoff phase decides without side effects; post-backoff dispatches format', async () => {
  const fake = fakeClient({ state: 'open', labels: pausedLabels.map((name) => ({ name })) }, []);
  assert.equal((await run(fake, false)).action, 'retry');
  assert.deepEqual(fake.calls, []);
  await run(fake, true);
  assert.deepEqual(fake.calls.map(([kind]) => kind), ['removeLabel', 'dispatch', 'comment']);
  assert.deepEqual(fake.calls[1][1], { issue_number: '1257', force_step: 'format' });
});

test('runner: an open linked PR clears the pause instead of re-dispatching', async () => {
  const fake = fakeClient(
    { state: 'open', labels: pausedLabels.map((name) => ({ name })) }, [],
    { prs: [{ number: 1262, state: 'OPEN' }, { number: 1260, state: 'CLOSED' }] },
  );
  const decision = await run(fake, true);
  assert.equal(decision.reason, 'linked-open-pr');
  assert.deepEqual(decision.linkedOpenPrs, [1262]);
  assert.deepEqual(fake.calls.map(([kind]) => kind), ['removeLabel', 'comment']);
});

test('runner: a failed linked-PR lookup is unknown, not a stop', async () => {
  const fake = fakeClient({ state: 'open', labels: pausedLabels.map((name) => ({ name })) }, [], { graphqlError: new Error('boom') });
  const decision = await run(fake, true);
  assert.equal(decision.action, 'retry');
  assert.equal(decision.linkedOpenPrs, null);
});

test('both auto-pilot workflows gate the backoff and redispatch on the budget module', () => {
  for (const rel of WORKFLOWS) {
    const text = fs.readFileSync(path.join(ROOT, rel), 'utf8');
    const job = text.slice(text.indexOf('  format-pause-wakeup:\n'));
    assert.ok(job.includes('repository: stranske/Workflows'), rel);
    assert.ok(job.includes('.github/scripts/autopilot_format_retry_budget.js'), rel);
    assert.equal((job.match(/require\('\.\/workflows-lib\/\.github\/scripts\/autopilot_format_retry_budget\.js'\)/g) || []).length, 2, rel);
    assert.ok(job.includes('dispatch: false'), rel);
    assert.ok(job.includes('dispatch: true'), rel);
    assert.equal((job.match(/if: steps\.budget\.outputs\.retry == 'true'/g) || []).length, 2, `${rel}: sleep and redispatch must both be gated`);
    // The unbounded path must not come back: no inline dispatch or pause removal in the job.
    assert.equal(job.includes('createWorkflowDispatch'), false, rel);
    assert.equal(job.includes('removeLabel'), false, rel);
  }
  const [root, consumer] = WORKFLOWS.map((rel) => {
    const text = fs.readFileSync(path.join(ROOT, rel), 'utf8');
    return text.slice(text.indexOf('  format-pause-wakeup:\n'));
  });
  assert.equal(root, consumer);
});
