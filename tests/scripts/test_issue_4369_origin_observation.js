'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { observe, observeSequence } = require('../../docs/evidence/issue-4369/observe-maint68');
const MAINT68 = '.github/workflows/maint-68-sync-consumer-repos.yml';
const MAINT71 = '.github/workflows/maint-71-merge-sync-prs.yml';

function inventory(count = 0) {
  const start = '2026-11-08T21:31:19Z', end = '2026-11-08T21:43:00Z';
  const rows = Array.from({ length: count }, (_, i) => ({ id: i + 1,
    created_at: start, event: 'workflow_dispatch',
    path: '.github/workflows/maint-68-sync-consumer-repos.yml',
    actor: { login: 'github-actions[bot]' }, display_title: 'auto' }));
  return { start, end, pages: Array.from({ length: Math.floor(count / 100) + 1 }, (_, i) => ({
    url: `https://api.github.com/repos/stranske/Workflows/actions/runs?per_page=100&page=${i + 1}&created=${start}..${end}`,
    body: { total_count: count, workflow_runs: rows.slice(i * 100, (i + 1) * 100) },
  })) };
}

function producerInventory(count = 0) {
  const input = inventory(count);
  input.workflow_id = 218845705;
  for (const page of input.pages) {
    page.url = page.url.replace('/actions/runs', `/actions/workflows/${input.workflow_id}/runs`);
    for (const run of page.body.workflow_runs) run.workflow_id = input.workflow_id;
  }
  return input;
}

function mergerInventory(count = 0) {
  const input = producerInventory(count);
  input.workflow_path = MAINT71;
  input.workflow_id = 221137962;
  for (const page of input.pages) {
    page.url = page.url.replace('/218845705/', `/${input.workflow_id}/`);
    for (const run of page.body.workflow_runs) {
      run.workflow_id = input.workflow_id;
      run.path = MAINT71;
    }
  }
  return input;
}

function continuation(previous, count = 0) {
  const next = inventory(count);
  next.start = previous.end;
  next.end = new Date(Date.parse(next.start) + 60000).toISOString();
  for (const page of next.pages) {
    const url = new URL(page.url);
    url.searchParams.set('created', `${next.start}..${next.end}`);
    page.url = url.href;
    for (const run of page.body.workflow_runs) run.created_at = next.start;
  }
  return next;
}

function replaceTimestamp(input, field, value) {
  if (field === 'created_at') {
    input.pages[0].body.workflow_runs[0].created_at = value;
  } else {
    input[field] = value;
    for (const page of input.pages) {
      const url = new URL(page.url);
      url.searchParams.set('created', `${input.start}..${input.end}`);
      page.url = url.href;
    }
  }
}

for (const value of [
  '2026-11-08', '2026-11-08T21:35:00', '2026-11-08T22:35:00+01:00',
  '2026-11-08T21:35:00.000001Z', '2026-11-08T24:00:00Z',
  '2026-02-30T21:35:00Z', 2026, null,
]) {
  for (const field of ['start', 'end', 'created_at']) {
    test(`refuse non-UTC, normalized or imprecise ${field}: ${JSON.stringify(value)}`, () => {
      const input = inventory(1);
      // Keep normalized invalid dates inside the interval, so an out-of-bounds
      // rejection cannot accidentally stand in for calendar validation.
      replaceTimestamp(input, 'start', '2026-01-01T00:00:00Z');
      replaceTimestamp(input, 'end', '2027-01-01T00:00:00Z');
      replaceTimestamp(input, field, value);
      assert.throws(() => observe(input), /timestamp/);
    });
  }
}

test('UTC timestamps accept explicit zero offsets, milliseconds and leap days', () => {
  for (const [start, end] of [
    ['2026-11-08T21:31:19+00:00', '2026-11-08T21:43:00+00:00'],
    ['2026-11-08T21:31:19.1Z', '2026-11-08T21:31:19.123Z'],
    ['2028-02-29T00:00:00Z', '2028-03-01T00:00:00Z'],
  ]) {
    const input = inventory(1);
    replaceTimestamp(input, 'start', start);
    replaceTimestamp(input, 'end', end);
    replaceTimestamp(input, 'created_at', start);
    const result = observe(input);
    assert.equal(result.start, start);
    assert.equal(result.end, end);
    assert.equal(result.producers.length, 1);
    assert.equal(result.chain_acceptance, false);
  }
});

test('continuous observation compares equivalent UTC boundary representations', () => {
  const first = inventory(1);
  first.pages[0].body.workflow_runs[0].created_at = first.end;
  const next = continuation(first, 1);
  replaceTimestamp(next, 'start', first.end.replace('Z', '+00:00'));
  const result = observeSequence([first, next]);
  assert.equal(result.total_count, 1);
  assert.equal(result.continuous, true);
  assert.equal(result.chain_acceptance, false);
});

test('continuous observations deduplicate an unchanged run at the inclusive boundary', () => {
  const first = inventory(1);
  first.pages[0].body.workflow_runs[0].created_at = first.end;
  const next = continuation(first, 1);
  const result = observeSequence([first, next]);
  assert.equal(result.start, first.start);
  assert.equal(result.end, next.end);
  assert.equal(result.observation_count, 2);
  assert.equal(result.total_count, 1);
  assert.equal(result.producers.length, 1);
  assert.equal(result.producers[0].automation_origin, 'UNKNOWN');
  assert.equal(result.continuous, true);
  assert.equal(result.pagination_complete, true);
  assert.equal(result.chain_acceptance, false);
});

test('continuous empty observations preserve merger identity and do not establish a chain', () => {
  const first = mergerInventory();
  const next = structuredClone(first);
  next.start = first.end;
  next.end = new Date(Date.parse(first.end) + 60000).toISOString();
  const url = new URL(next.pages[0].url);
  url.searchParams.set('created', `${next.start}..${next.end}`);
  next.pages[0].url = url.href;
  const result = observeSequence([first, next]);
  assert.equal(result.workflow_path, MAINT71);
  assert.equal(result.workflow_id, first.workflow_id);
  assert.deepEqual(result.mergers, []);
  assert.equal(result.chain_acceptance, false);
});

test('continuous observations retain distinct chronological leads without inferring causality', () => {
  const first = inventory(1);
  first.pages[0].body.workflow_runs[0].event = 'schedule';
  const next = continuation(first, 2);
  next.pages[0].body.workflow_runs[0].id = 3;
  next.pages[0].body.workflow_runs[1].path = MAINT71;
  for (const run of next.pages[0].body.workflow_runs) run.created_at = next.end;
  const result = observeSequence([first, next]);
  assert.equal(result.total_count, 3);
  assert.deepEqual(result.producers.map(run => run.id), [1, 3]);
  assert.deepEqual(result.producers.map(run => run.automation_origin), ['schedule', 'UNKNOWN']);
  assert.equal(result.chain_acceptance, false);
});

for (const [name, mutate] of [
  ['gap', x => { x[1] = continuation(continuation(x[0])); }],
  ['overlap', x => { x[1] = structuredClone(x[0]); }],
  ['reversed windows', x => { x.reverse(); }],
  ['changed workflow', x => { x[1].workflow_path = MAINT71; }],
  ['changed inventory scope', x => { x[0] = producerInventory(); }],
  ['incomplete continuation', x => { x[1].pages = []; }],
  ['missing boundary run in continuation', x => { x[1] = continuation(x[0]); }],
  ['missing boundary run in preceding window', x => { x[0] = inventory(); }],
  ['conflicting boundary event', x => { x[1].pages[0].body.workflow_runs[0].event = 'schedule'; }],
  ['conflicting boundary workflow', x => { x[1].pages[0].body.workflow_runs[0].path = MAINT71; }],
  ['conflicting boundary identity', x => { x[1].pages[0].body.workflow_runs[0].workflow_id = 1; }],
]) {
  test(`continuous observation refuses ${name}`, () => {
    const first = inventory(1);
    first.pages[0].body.workflow_runs[0].created_at = first.end;
    const input = [first, continuation(first, 1)];
    mutate(input);
    assert.throws(() => observeSequence(input), /observation|inventory/);
  });
}

test('continuous observation requires at least one complete inventory', () => {
  assert.throws(() => observeSequence([]));
  assert.throws(() => observeSequence(null));
  assert.equal(observeSequence([inventory()]).observation_count, 1);
});

test('merger observations validate empty, exact-boundary and multi-page inventories', () => {
  for (const count of [0, 100, 101]) {
    const result = observe(mergerInventory(count));
    assert.equal(result.workflow_path, MAINT71);
    assert.equal(result.workflow_id, 221137962);
    assert.equal(result.inventory_scope, 'merger');
    assert.equal(result.pagination_complete, true);
    assert.equal(result.mergers.length, count);
    assert.equal(Object.hasOwn(result, 'producers'), false);
    assert.ok(result.mergers.every(run => run.automation_origin === 'UNKNOWN'));
    assert.equal(result.chain_acceptance, false);
  }
});

for (const [name, mutate] of [
  ['unsupported workflow path', x => { x.workflow_path = '.github/workflows/maint-71-auto-fix-integration.yml'; }],
  ['non-string workflow path', x => { x.workflow_path = null; }],
  ['producer path on merger rows', x => { x.pages[0].body.workflow_runs[0].path = MAINT68; }],
  ['producer workflow identity on merger rows', x => { x.pages[0].body.workflow_runs[0].workflow_id = 218845705; }],
  ['producer inventory endpoint', x => { x.pages[0].url = x.pages[0].url.replace('/221137962/', '/218845705/'); }],
  ['filtered merger inventory', x => { x.pages[0].url += '&event=workflow_dispatch'; }],
  ['incomplete merger pagination', x => { x.pages.pop(); }],
  ['duplicate merger run', x => { x.pages[0].body.workflow_runs[1].id = 1; }],
  ['merger run outside bounds', x => { x.pages[0].body.workflow_runs[0].created_at = '2026-11-08T21:00:00Z'; }],
]) {
  test(`refuse ${name}`, () => {
    const input = mergerInventory(101);
    mutate(input);
    assert.throws(() => observe(input));
  });
}

test('repository inventories select exact merger paths without treating chronology as causality', () => {
  const input = inventory(4);
  input.workflow_path = MAINT71;
  const rows = input.pages[0].body.workflow_runs;
  rows[0].path = rows[2].path = MAINT71;
  rows[0].created_at = input.end;
  rows[2].event = 'schedule';
  rows[3].path = '.github/workflows/maint-71-auto-fix-integration.yml';
  const result = observe(input);
  assert.equal(result.inventory_scope, 'repository');
  assert.deepEqual(result.mergers.map(run => run.id), [3, 1]);
  assert.deepEqual(result.mergers.map(run => run.automation_origin), ['schedule', 'UNKNOWN']);
  assert.equal(result.chain_acceptance, false);
  delete input.workflow_path;
  assert.deepEqual(observe(input).producers.map(run => run.id), [2]);
});

test('retained round-9 inventory observes a merger dispatch without a producer or causal proof', () => {
  const input = require('../../docs/evidence/issue-4369/runtime-4550/4558-round9-origin-inventory.json');
  const producer = observe(input);
  const merger = observe({ ...input, workflow_path: MAINT71 });
  assert.equal(producer.total_count, 182);
  assert.equal(producer.pagination_complete, true);
  assert.deepEqual(producer.producers, []);
  assert.equal(merger.pagination_complete, true);
  assert.deepEqual(merger.mergers, [{
    id: 42544857435, created_at: '2026-11-09T01:18:15Z',
    event: 'workflow_dispatch', automation_origin: 'UNKNOWN',
  }]);
  assert.equal(producer.chain_acceptance, false);
  assert.equal(merger.chain_acceptance, false);
});

test('workflow-specific inventory supports empty and paginated producer observations', () => {
  assert.equal(observe(producerInventory()).producers.length, 0);
  assert.equal(observe(inventory()).inventory_scope, 'repository');
  const result = observe(producerInventory(101));
  assert.equal(result.pagination_complete, true);
  assert.equal(result.inventory_scope, 'producer');
  assert.equal(result.workflow_id, 218845705);
  assert.equal(result.producers.length, 101);
  assert.ok(result.producers.every(run => run.automation_origin === 'UNKNOWN'));
  assert.equal(result.chain_acceptance, false);
});

for (const [name, mutate] of [
  ['missing workflow identity', x => { delete x.workflow_id; }],
  ['invalid workflow identity', x => { x.workflow_id = '218845705'; }],
  ['changed page endpoint', x => {
    x.pages[1].url = x.pages[1].url.replace('/218845705/', '/218845706/');
  }],
  ['wrong row workflow identity', x => { x.pages[0].body.workflow_runs[0].workflow_id++; }],
  ['missing row workflow identity', x => { delete x.pages[0].body.workflow_runs[0].workflow_id; }],
  ['wrong workflow path', x => { x.pages[0].body.workflow_runs[0].path = 'other.yml'; }],
  ['event-filtered producer inventory', x => { x.pages[0].url += '&event=schedule'; }],
  ['incomplete producer pagination', x => { x.pages.pop(); }],
]) {
  test(`refuse ${name}`, () => {
    const input = producerInventory(101);
    mutate(input);
    assert.throws(() => observe(input));
  });
}

test('empty inventory and exact page boundary require terminal empty pages', () => {
  assert.equal(observe(inventory()).producers.length, 0);
  assert.equal(observe(inventory(100)).producers.length, 100);
  const input = inventory(100);
  input.pages.pop();
  assert.throws(() => observe(input), /pagination/);
});

test('bot actor and auto title do not authenticate a dispatch or a complete chain', () => {
  const result = observe(inventory(1));
  assert.equal(result.producers[0].automation_origin, 'UNKNOWN');
  assert.equal(result.chain_acceptance, false);
});

test('scheduled producer is an automation lead, not a delivery-chain acceptance', () => {
  const input = inventory(1);
  input.pages[0].body.workflow_runs[0].event = 'schedule';
  const result = observe(input);
  assert.equal(result.producers[0].automation_origin, 'schedule');
  assert.equal(result.chain_acceptance, false);
});

for (const [name, mutate] of [
  ['filtered endpoint', x => { x.pages[0].url += '&event=schedule'; }],
  ['wrong repository', x => { x.pages[0].url = x.pages[0].url.replace('/Workflows/', '/other/'); }],
  ['missing page', x => { x.pages = []; }],
  ['changing total', x => { x.pages[1].body.total_count++; }],
  ['duplicate run', x => { x.pages[0].body.workflow_runs[1].id = 1; }],
  ['outside bounds', x => { x.pages[0].body.workflow_runs[0].created_at = '2026-11-08T21:00:00Z'; }],
  ['missing run', x => { x.pages[0].body.workflow_runs.pop(); }],
  ['search cap', x => { x.pages[0].body.total_count = 1000; }],
]) {
  test(`refuse ${name}`, () => {
    const input = inventory(101);
    mutate(input);
    assert.throws(() => observe(input));
  });
}
