'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { qualifyNoChangeMergedHead } = require('../maint71_merge_sync_prs');
const merge = 'a'.repeat(40), checked = 'b'.repeat(40), tree = 'c'.repeat(40);
function fixture() {
  const repository = { full_name: 'owner/consumer' };
  const pr = { number: 7, state: 'closed', merged: true, merged_at: '2026-10-28T00:00:00Z',
    merge_commit_sha: merge, base: { ref: 'main', sha: 'd'.repeat(40), repo: repository },
    head: { sha: checked, repo: repository } };
  const state = { pr, associated: [pr], current: [], checked: [{ id: 1, name: 'Gate / gate',
    head_sha: checked, status: 'completed', conclusion: 'success' }], statuses: [],
    mergeTree: tree, checkedTree: tree, currentRef: merge, reads: [], mutations: 0 };
  const client = { rest: { checks: { listForRef: async args => {
    state.reads.push(['checks', args]);
    const rows = args.ref === merge ? state.current : state.checked;
    const page = rows.slice((args.page - 1) * 100, args.page * 100);
    return { data: { total_count: rows.length, check_runs: structuredClone(page) } };
  } }, repos: {
    listCommitStatusesForRef: async args => { state.reads.push(['statuses', args]);
      return { data: args.ref === checked && args.page === 1 ? structuredClone(state.statuses) : [] }; },
    listPullRequestsAssociatedWithCommit: async args => { state.reads.push(['associated', args]);
      return { data: structuredClone(state.associated) }; },
  }, pulls: { get: async args => { state.reads.push(['pr', args]); return { data: structuredClone(state.pr) }; } },
  git: {
    getCommit: async args => { state.reads.push(['commit', args]); return { data: {
      sha: args.commit_sha, tree: { sha: args.commit_sha === merge ? state.mergeTree : state.checkedTree } } }; },
    getRef: async args => { state.reads.push(['ref', args]); return { data: { object: { sha: state.currentRef } } }; },
  } } };
  return { state, client, run: () => qualifyNoChangeMergedHead({ withRetry: fn => fn(client),
    owner: 'owner', repo: 'consumer', branch: 'main', headSha: merge, requiredContexts: new Set(['Gate / gate']) }) };
}
test('actual native merged PR with identical whole tree supplies absent PR-only required context without fabricating status', async () => {
  const api = fixture(); const result = await api.run();
  assert.equal(result.ok, true);
  assert.deepEqual(result.proof, { kind: 'exact-merged-pr-tree', pull_number: 7,
    default_head_sha: merge, checked_head_sha: checked, tree_sha: tree, required_contexts: ['Gate / gate'] });
  assert.equal(api.state.mutations, 0);
  assert.ok(api.state.reads.some(([kind, args]) => kind === 'checks' && args.ref === checked));
  assert.equal(api.state.reads.filter(([kind]) => kind === 'pr').length, 2);
});
for (const [name, change] of [
  ['failed actual default context', s => { s.current = [{ id: 2, head_sha: merge, name: 'Gate / gate', status: 'completed', conclusion: 'failure' }]; }],
  ['pending actual default context', s => { s.current = [{ id: 2, head_sha: merge, name: 'Gate / gate', status: 'in_progress', conclusion: null }]; }],
  ['unknown actual default context', s => { s.current = [{ id: 2, head_sha: merge, name: 'Gate / gate', status: 'completed', conclusion: null }]; }],
  ['failed checked PR context', s => { s.checked[0].conclusion = 'failure'; }],
  ['pending checked PR context', s => { s.checked[0].status = 'queued'; s.checked[0].conclusion = null; }],
  ['skipped is not successful checked PR context', s => { s.checked[0].conclusion = 'skipped'; }],
  ['absent checked PR context', s => { s.checked = []; }],
  ['tree differs in any byte or file mode', s => { s.checkedTree = 'e'.repeat(40); }],
  ['unmerged PR', s => { s.pr.merged = false; }],
  ['different merge commit', s => { s.pr.merge_commit_sha = 'e'.repeat(40); }],
  ['different base branch', s => { s.pr.base.ref = 'other'; }],
  ['fork head', s => { s.pr.head.repo = { full_name: 'attacker/consumer' }; }],
  ['fork base', s => { s.pr.base.repo = { full_name: 'attacker/consumer' }; }],
  ['ambiguous merged PR inventory', s => { s.associated.push({ ...s.pr, number: 8 }); }],
  ['default ref changed', s => { s.currentRef = 'e'.repeat(40); }],
  ['stale check head', s => { s.checked[0].head_sha = 'e'.repeat(40); }],
]) test(`native no-change fallback holds ${name}`, async () => {
  const api = fixture(); change(api.state); assert.equal((await api.run()).ok, false);
});
test('legacy positive native Gate status on exact PR head is admitted', async () => {
  const api = fixture(); api.state.checked = [];
  api.state.statuses = [{ id: 2, context: 'Gate / gate', state: 'success', updated_at: '2026-10-28T00:00:00Z' }];
  assert.equal((await api.run()).ok, true);
});
test('all native check pages are required, including a failed required check on the second page', async () => {
  const api = fixture(); api.state.checked = Array.from({ length: 100 }, (_, i) => ({ id: i + 10,
    name: `other ${i}`, head_sha: checked, status: 'completed', conclusion: 'success' }));
  api.state.checked.push({ id: 200, name: 'Gate / gate', head_sha: checked, status: 'completed', conclusion: 'failure' });
  assert.equal((await api.run()).ok, false);
  assert.ok(api.state.reads.some(([kind, args]) => kind === 'checks' && args.page === 2));
});
test('partial or changing native inventory does not establish readiness', async () => {
  const api = fixture(); api.client.rest.checks.listForRef = async () => ({ data: { total_count: 2, check_runs: [] } });
  assert.equal((await api.run()).ok, false);
});
test('fresh reread prevents changed checked verdict and newly appeared default failure', async () => {
  for (const target of [merge, checked]) {
    const api = fixture(); const original = api.client.rest.checks.listForRef; let reads = 0;
    api.client.rest.checks.listForRef = async args => {
      if (args.ref === target && ++reads === 2) {
        if (target === merge) api.state.current = [{ ...api.state.checked[0], id: 3, head_sha: merge, conclusion: 'failure' }];
        else api.state.checked[0].conclusion = 'failure';
      }
      return original(args);
    };
    assert.equal((await api.run()).ok, false);
  }
});
test('fresh PR readback prevents changed merge/head linkage', async () => {
  const api = fixture(); const original = api.client.rest.pulls.get; let count = 0;
  api.client.rest.pulls.get = async args => { if (++count === 2) api.state.pr.head.sha = 'e'.repeat(40); return original(args); };
  assert.equal((await api.run()).ok, false);
});
test('native API failure stays unknown without leaking error text or issuing writes', async () => {
  const api = fixture(); api.client.rest.git.getCommit = async () => { throw new Error('SECRET arbitrary API body'); };
  assert.deepEqual(await api.run(), { ok: false, reason: 'no_change_native_read_unknown' });
});
