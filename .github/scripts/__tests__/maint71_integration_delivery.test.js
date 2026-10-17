'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { prepareIntegrationDelivery } = require('../maint71_merge_sync_prs');
const { replaceDeliveryRecord } = require('../sync_pr_lease_contract');

function fixture() {
  const record = { schema: 'sync-pr-delivery-record/v1', delivery_state: 'staging',
    repository: 'owner/repo', durable_issue_url: 'https://github.com/owner/source/issues/1',
    source_commit: 'b'.repeat(40), plan_id: 'fixed-plan', generation: 'generation',
    head_observed_sha: 'a'.repeat(40), head_observed_at: '2026-10-16T00:00:00Z',
    desired_tree_hash: 'tree', lease_expires_at: '2099-01-01T00:00:00Z' };
  const pr = { state: 'open', draft: false, auto_merge: null,
    head: { sha: record.head_observed_sha }, body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->` };
  return { record, pr };
}

test('integration preparation requests no reviewer and does not assert passing CI', async () => {
  const { pr, record } = fixture();
  let seals = 0;
  await prepareIntegrationDelivery({ pr, record, hold: async () => pr, seal: async (args) => {
    seals++;
    assert.equal(args.settlement.reason, 'integration_checks_required');
    assert.deepEqual(args.settlement.responded, []);
    assert.equal(args.record.source_commit, record.source_commit);
    assert.equal(args.pr.head.sha, pr.head.sha);
    assert.equal(args.record.delivery_state, 'staging');
    return { body: args.pr.body };
  } });
  assert.equal(seals, 1);
});

test('integration preparation refuses changed head, source, plan, ownership state or readiness', async () => {
  for (const mutate of [
    p => { p.head.sha = 'c'.repeat(40); },
    p => { p.body = replaceDeliveryRecord(p.body, { source_commit: 'c'.repeat(40) }); },
    p => { p.body = replaceDeliveryRecord(p.body, { plan_id: 'other' }); },
    p => { p.body = replaceDeliveryRecord(p.body, { delivery_state: 'sealed', review_started_at: '2026-10-16T00:00:00Z', sealed_at: '2026-10-16T00:01:00Z', sealed_head_sha: p.head.sha }); },
    p => { p.draft = true; }, p => { p.auto_merge = {}; }, p => { p.state = 'closed'; },
  ]) {
    const { pr, record } = fixture(); const current = structuredClone(pr); mutate(current);
    await assert.rejects(prepareIntegrationDelivery({ pr, record, hold: async () => current,
      seal: async () => assert.fail('changed delivery must never seal') }), /changed/);
  }
});

test('dry run cannot change delivery and unbound payload cannot enter preparation', async () => {
  const { pr, record } = fixture();
  const args = { pr, record, dryRun: true,
    hold: async () => assert.fail('dry run must not mutate'), seal: async () => assert.fail('dry run must not seal') };
  assert.equal((await prepareIntegrationDelivery(args)).dryRun, true);
  record.source_commit = '';
  await assert.rejects(prepareIntegrationDelivery(args), /bound source/);
});

test('sealed delivery explicitly dispatches Gate on the PR branch with PR context', async () => {
  const { requestSealedGate } = require('../maint71_merge_sync_prs');
  const calls = [];
  const client = { rest: { actions: { createWorkflowDispatch: async args => { calls.push(args); return { status: 204 }; } } } };
  const args = { owner: 'owner', repo: 'repo', pr: { number: 42,
    head: { ref: 'sync/workflows-delivery', sha: 'a'.repeat(40) } },
    withRetry: callback => callback(client) };
  assert.deepEqual(await requestSealedGate(args), { mode: 'dispatch', status: 204 });
  assert.deepEqual(calls, [{ owner: 'owner', repo: 'repo', workflow_id: 'pr-00-gate.yml',
    ref: 'sync/workflows-delivery', inputs: { pr_number: '42' } }]);
  client.rest.actions.createWorkflowDispatch = async () => { throw new Error('dispatch denied'); };
  await assert.rejects(requestSealedGate(args), /dispatch denied/);
  await assert.rejects(requestSealedGate({ ...args, pr: { number: 42 } }), /head ref/);
});

for (const status of [422, 404]) {
  test(`legacy Gate HTTP ${status} falls back to labels and integration cycle continues`, async () => {
    const { requestSealedGate } = require('../maint71_merge_sync_prs');
    const { buildMergeReport, buildMarkdownSummary } = require('../sync_pr_merge_contract');
    const labels = [];
    const dispatches = [];
    const client = { rest: {
      actions: { createWorkflowDispatch: async args => {
        dispatches.push(args.repo);
        if (args.repo === 'legacy') throw Object.assign(new Error('legacy dispatch'), { status });
        return { status: 204 };
      } },
      issues: { addLabels: async args => { labels.push(args); } },
    } };
    const results = [];
    for (const repo of ['legacy', 'modern']) {
      const { pr, record } = fixture();
      pr.number = 42;
      pr.head.ref = 'sync/workflows-delivery';
      const sealed = await prepareIntegrationDelivery({ pr, record, hold: async () => pr,
        seal: async () => ({ gateRequest: await requestSealedGate({
          owner: 'owner', repo, pr, withRetry: callback => callback(client),
        }) }),
      });
      results.push({ repository: `owner/${repo}`, status: 'delivery_sealed_checks_pending',
        gate_request: sealed.gateRequest });
    }
    assert.deepEqual(dispatches, ['legacy', 'modern']);
    assert.deepEqual(labels, [{ owner: 'owner', repo: 'legacy', issue_number: 42,
      labels: ['sync:delivery-ready'] }]);
    assert.deepEqual(results.map(row => row.gate_request), [
      { mode: 'label-fallback', status }, { mode: 'dispatch', status: 204 },
    ]);
    const report = buildMergeReport({ results });
    assert.equal(report.summary.gate_label_fallback, 1);
    assert.equal(report.summary.delivery_sealed_checks_pending, 2);
    assert.match(buildMarkdownSummary(report), /gate_label_fallback \| 1/);
  });
}
