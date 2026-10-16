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
