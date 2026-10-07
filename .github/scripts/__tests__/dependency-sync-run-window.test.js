const assert = require('node:assert/strict');
const { test } = require('node:test');
const { collectRunWindow } = require('../dependency_sync_run_window.js');

const start = new Date('2026-10-01T00:00:00Z');
const end = new Date('2026-10-01T01:00:00Z');
function fixture(rows, calls) {
  return async ({ created, page, per_page }) => {
    calls.push({ created, page });
    const [lo, hi] = created.split('..').map(Date.parse);
    const selected = rows.filter((row) => Date.parse(row.created_at) >= lo && Date.parse(row.created_at) <= hi);
    if (page > 10) throw new Error('GitHub filtered pagination ceiling');
    return { data: { total_count: selected.length, workflow_runs: selected.slice((page - 1) * per_page, page * per_page) } };
  };
}
test('collects every page of a sparse window', async () => {
  const rows = Array.from({ length: 205 }, (_, id) => ({ id, created_at: start.toISOString() }));
  const calls = [];
  assert.equal((await collectRunWindow({ start, end, listPage: fixture(rows, calls) })).length, 205);
  assert.deepEqual(calls.map((call) => call.page), [1, 2, 3]);
});
test('splits a dense bounded window before the filtered pagination ceiling', async () => {
  const rows = Array.from({ length: 2401 }, (_, id) => ({ id, created_at: new Date(+start + id * 1000).toISOString() }));
  const calls = [];
  const result = await collectRunWindow({ start, end, listPage: fixture(rows, calls) });
  assert.equal(result.length, rows.length);
  assert.equal(new Set(result.map((row) => row.id)).size, rows.length);
  assert.ok(calls.length > 3);
  assert.ok(calls.every((call) => call.page <= 10));
});
test('retains and deduplicates inclusive split-boundary rows', async () => {
  const rows = Array.from({ length: 1001 }, (_, id) => ({ id, created_at: new Date(+start + (id % 2 ? 1800 : 1) * 1000).toISOString() }));
  const result = await collectRunWindow({ start, end, listPage: fixture(rows, []) });
  assert.equal(result.length, 1001);
});
test('an unsplittable one-second dense interval is UNKNOWN, never a complete partial list', async () => {
  const rows = Array.from({ length: 1001 }, (_, id) => ({ id, created_at: start.toISOString() }));
  await assert.rejects(collectRunWindow({ start, end: new Date(+start + 1000), listPage: fixture(rows, []) }), /cannot completely collect/);
});
test('a failed page rejects the entire collection instead of publishing partial success', async () => {
  const rows = Array.from({ length: 205 }, (_, id) => ({ id, created_at: start.toISOString() }));
  const list = fixture(rows, []);
  await assert.rejects(collectRunWindow({ start, end, listPage: (params) => {
    if (params.page === 2) throw new Error('transport unavailable');
    return list(params);
  } }), /transport unavailable/);
});

test('duplicate or missing pages cannot satisfy completeness', async () => {
  const rows = Array.from({ length: 205 }, (_, id) => ({ id, created_at: start.toISOString() }));
  const list = fixture(rows, []);
  await assert.rejects(collectRunWindow({ start, end, listPage: (params) => list({ ...params, page: 1 }) }), /incomplete workflow-run pages/);
});

test('subdivision cannot silently lose a parent-observed run', async () => {
  const rows = Array.from({ length: 1000 }, (_, id) => ({ id, created_at: new Date(+start + id * 2000).toISOString() }));
  const childList = fixture(rows, []);
  await assert.rejects(collectRunWindow({ start, end, listPage: (params) => {
    if (params.created === `${start.toISOString()}..${end.toISOString()}`) {
      return { data: { total_count: 1001, workflow_runs: [{ id: 1001, created_at: start.toISOString() }, ...rows.slice(0, 99)] } };
    }
    return childList(params);
  } }), /subdivision.*incomplete|window changed/);
});

test('same-count substitution cannot erase a parent-observed identity', async () => {
  const rows = Array.from({ length: 1001 }, (_, id) => ({ id, created_at: new Date(+start + id * 2000).toISOString() }));
  const childList = fixture(rows, []);
  await assert.rejects(collectRunWindow({ start, end, listPage: (params) => {
    if (params.created === `${start.toISOString()}..${end.toISOString()}`) {
      return { data: { total_count: 1001, workflow_runs: [{ id: 2001, created_at: start.toISOString() }, ...rows.slice(0, 99)] } };
    }
    return childList(params);
  } }), /subdivision.*incomplete|window changed/);
});

test('the actual workflow records collection failure and does not emit partial runs', async () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const source = fs.readFileSync(path.join(__dirname, '../../workflows/health-83-dependency-sync-efficiency.yml'), 'utf8');
  const begin = source.indexOf('try {\n                const runs = await collectRunWindow');
  const finish = source.indexOf('\n            }\n            fs.writeFileSync', begin);
  assert.ok(begin >= 0 && finish > begin);
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const execute = new AsyncFunction('collectRunWindow', 'windowStart', 'windowEnd', 'owner', 'name', 'api', 'withRetry', 'sourceByPr', 'workflow_runs', 'collectionFailures', source.slice(begin, finish));
  const failures = [], runs = [];
  await execute(async () => { throw new Error('missing page'); }, start, end, 'stranske', 'Workflows', {}, () => {}, new Map(), runs, failures);
  assert.deepEqual(runs, []);
  assert.deepEqual(failures, ['stranske/Workflows: workflow runs: missing page']);
});
