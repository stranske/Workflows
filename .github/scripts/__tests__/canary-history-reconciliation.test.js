'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const native = require('../maint71_merge_sync_prs');
const retained = require('./fixtures/legacy-canary-baseline.json');

// Projection of authenticated Nov10 reads: eight original terminal attempts,
// three merged canary heads/default trees, and three newer open deliveries.
function fixture({ openOwners = false } = {}) {
  const data = structuredClone(retained), reads = [];
  if (!openOwners) for (const row of data.baselines) { row.open = []; row.ref = null; }
  const runs = [data.producer, ...data.unknowns];
  data.producer.delivery_digest = data.payload.digest;
  const current = new Map(data.unknowns.map(row => [row.id, structuredClone(row)]));
  const request = data.producer.refresh_plan;
  const target = args => data.baselines.find(row => row.repository === `${args.owner}/${args.repo}`);
  const methods = {
    actions: {
      getWorkflowRun: args => current.get(args.run_id),
      listWorkflowRuns: args => ({ total_count: data.active?.length || 0, workflow_runs: data.active || [] }),
    },
    pulls: {
      list: args => args.state === 'open' ? target(args).open : [target(args).pr],
      get: args => target(args).pr,
    },
    repos: {
      get: args => target(args).repo,
      getCommit: args => {
        const row = target(args);
        if (args.ref === row.repo.default_branch) return row.tip;
        if (args.ref === row.head.sha) return row.head;
        return row.open_heads[args.ref];
      },
      compareCommitsWithBasehead: args => target(args).comparison,
    },
    git: {
      getTree: args => target(args).trees.find(tree => tree.sha === args.tree_sha),
      getRef: args => {
        const ref = target(args).ref;
        if (!ref) throw Object.assign(new Error('missing stable ref'), { status: 404 });
        return ref;
      },
    },
  };
  const client = { rest: Object.fromEntries(Object.entries(methods).map(([group, entries]) =>
    [group, Object.fromEntries(Object.entries(entries).map(([method, handler]) =>
      [method, async args => { reads.push({ group, method, args }); return { data: handler(args) }; }]))])) };
  const args = { withRetry: fn => fn(client), context: { repo: { owner: 'stranske', repo: 'Workflows' },
    payload: { repository: { default_branch: 'main' } } }, runs, candidates: data.scope.canaries,
  refreshPlan: request, payload: data.payload, verifyPlan: native.verifiedCanaryRefreshPlan };
  const decide = extra => native.canaryRefreshDecision({ runs, sha: request.source_commit,
    candidates: data.scope.canaries, refreshPlan: request, deliveryDigest: data.payload.digest, ...extra });
  return { data, current, reads, runs, request, args, decide, client,
    reconcile: () => native.reconcileLegacyCanaryHistory(args) };
}

function differentDefaultTree(f) {
  const row = f.data.baselines[0];
  row.tip.commit.tree.sha = 'f'.repeat(40);
  row.trees[1].sha = row.tip.commit.tree.sha;
  return row.trees[1];
}

test('later accepted current baseline covers old ambiguity without rewriting historical outcomes', async () => {
  const f = fixture();
  const before = structuredClone(f.runs);
  assert.equal(f.decide().state, 'unknown');
  const result = await f.reconcile();
  assert.equal(result.covered.length, 8, result.reason);
  assert.equal(result.blocking_count, 0);
  assert.equal(result.baselines.length, 3);
  assert.equal(f.decide().producer_succeeded, true);
  assert.equal(f.decide({ driftKey: 'e'.repeat(64) }).eligible, true);
  assert.deepEqual(f.runs, before, 'the old UNKNOWN grades and native evidence remain intact');
});

test('real newer open deliveries retain ownership after historical reconciliation', async () => {
  const f = fixture({ openOwners: true });
  const result = await f.reconcile();
  assert.equal(result.covered.length, 8, result.reason);
  assert.equal(result.owner_conflicts.length, 3);
  assert.equal(f.decide().state, 'current-delivery-owned');
  assert.equal(f.decide({ driftKey: 'e'.repeat(64) }).eligible, false);
  assert.equal(f.decide().next_action, 'follow-current-delivery-without-replacing-its-source');
});

test('production history collector reconciles retained UNKNOWNs and preserves current owners', async t => {
  const f = fixture({ openOwners: true });
  const receipt = require('../maint68_scoped_receipt');
  const payloads = require('../consumer_delivery_digest');
  t.mock.method(receipt, 'readScopedCanaryReceipt', async ({ run }) =>
    run.id === f.data.producer.id ? { ...f.request, state: 'completed',
      candidates: f.args.candidates, proof: { source_identity_bound: true } } : { state: 'unknown' });
  t.mock.method(payloads, 'readDeliveryPayload', async () => f.data.payload);
  const getCommit = f.client.rest.repos.getCommit;
  f.client.rest.repos.getCommit = args => args.repo === 'Workflows'
    ? { data: { sha: f.request.source_commit } } : getCommit(args);
  f.client.rest.repos.getContent = async () => ({ data: { content: Buffer.from(JSON.stringify({
    canaries: f.args.candidates.map(repo => ({ repo })),
  })).toString('base64') } });
  f.client.rest.actions.listWorkflowRuns = async args => ({ data: args.status
    ? { total_count: 0, workflow_runs: [] } : { workflow_runs: f.runs } });
  const state = await native.readCanaryRefreshState({ ...f.args,
    expectedCanaries: f.args.candidates, sourceSha: f.request.source_commit,
    planId: f.request.plan_id, planScope: f.request.plan_scope,
    scopeBaseSha: f.request.scope_base_sha, plan: f.request.plan });
  assert.equal(state.history_reconciliation.covered.length, 8, state.history_reconciliation.reason);
  assert.equal(state.state, 'current-delivery-owned');
  assert.equal(state.eligible, false);
  assert.equal(state.runs.filter(run => run.refresh_unknown).length, 8);
});

for (const [name, change] of [
  ['rerun original', f => { f.current.get(f.data.unknowns[0].id).run_attempt++; }],
  ['active original', f => { f.current.get(f.data.unknowns[0].id).status = 'in_progress'; }],
  ['foreign original', f => { f.current.get(f.data.unknowns[0].id).head_repository.id++; }],
  ['newer unknown effect', f => {
    f.runs[1].updated_at = '2026-11-11T00:00:00Z';
    f.current.get(f.runs[1].id).updated_at = f.runs[1].updated_at;
  }],
  ['unverified baseline', f => { f.data.baselines[0].head.commit.verification.verified = false; }],
  ['untrusted baseline author', f => { f.data.baselines[0].pr.user.login = 'untrusted'; }],
  ['missing native producer', f => { f.data.producer.refresh_receipt.state = 'unknown'; }],
  ['baseline did not deliver selected files', f => { f.data.producer.refresh_plan.plan.entries = []; }],
  ['baseline excluded a selected repository', f => {
    for (const entry of f.data.producer.refresh_plan.plan.entries) entry.skip_repos = [f.args.candidates[0]];
  }],
  ['baseline only preserved existing selected files', f => {
    for (const entry of f.data.producer.refresh_plan.plan.entries) entry.sync_mode = 'create_only';
  }],
  ['changed selected file', f => { differentDefaultTree(f).tree[0].sha = 'e'.repeat(40); }],
  ['retired selected file', f => { differentDefaultTree(f).tree.shift(); }],
  ['changed selected mode', f => { differentDefaultTree(f).tree[0].mode = '100755'; }],
  ['truncated tree', f => { differentDefaultTree(f).truncated = true; }],
  ['unrelated default history', f => { f.data.baselines[0].comparison.merge_base_commit.sha = 'e'.repeat(40); }],
]) test(`baseline cannot cover ${name}`, async () => {
  const f = fixture(); change(f);
  const result = await f.reconcile();
  assert.equal(result.covered.length, 0);
  assert.equal(f.decide().eligible, false);
  assert.equal(f.decide().state, 'unknown');
});

test('a newly active native writer wins even after all historical baseline reads pass', async () => {
  const f = fixture();
  f.data.active = [{ ...f.data.producer, id: 99999, status: 'queued', conclusion: null }];
  assert.equal((await f.reconcile()).covered.length, 0);
  assert.equal(f.decide().state, 'queued');
  assert.equal(f.decide().eligible, false);
});

test('failed refresh of an admission observation invalidates the prior observation', async () => {
  const f = fixture();
  assert.equal((await f.reconcile()).covered.length, 8);
  assert.equal(f.decide().producer_succeeded, true);
  differentDefaultTree(f).truncated = true;
  assert.equal((await f.reconcile()).covered.length, 0);
  assert.equal(f.decide().state, 'unknown');
});

test('JSON, copied rows and another scope cannot reuse process-local admission authority', async () => {
  const f = fixture(); await f.reconcile();
  const copied = structuredClone(f.runs);
  for (const row of copied) row.historical_baseline_covered = true;
  assert.equal(f.decide({ runs: copied }).state, 'unknown');
  assert.equal(f.decide({ deliveryDigest: 'another payload' }).state, 'unknown');
  f.current.get(f.runs[1].id).updated_at = '2026-11-11T00:00:00Z';
  f.runs[1].updated_at = '2026-11-11T00:00:00Z';
  assert.equal(f.decide().state, 'unknown');
});

test('default or stable-ref movement during reconciliation refuses the stale observation', async () => {
  const f = fixture(); let reads = 0;
  const original = f.args.withRetry;
  f.args.withRetry = async fn => {
    const result = await original(fn);
    if (f.reads.at(-1)?.method === 'getCommit' && f.reads.at(-1).args.ref === 'main') {
      reads++;
      if (reads === 4) return { data: { ...result.data, sha: 'e'.repeat(40) } };
    }
    return result;
  };
  assert.equal((await f.reconcile()).covered.length, 0);
  assert.equal(f.decide().state, 'unknown');
});
