'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { observe } = require('../../docs/evidence/issue-4369/observe-maint68');
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
