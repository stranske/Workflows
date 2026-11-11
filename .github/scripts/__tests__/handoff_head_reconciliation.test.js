'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const campaign = require('../sync_dependency_campaign');

function fixture() {
  const retained = {
    schema: campaign.DELIVERY_HANDOFF_SCHEMA, repository: 'stranske/Ready', pr: 667,
    branch: 'deps/sync-dev-versions-91791b44e525', head_sha: 'a'.repeat(40),
    delivery_generation: '91791b44e525', lane: 'dev-tool-sync',
    plan_id: 'dev-tool-91791b44e525', plan_scope: 'full', source_commit: 'c'.repeat(40),
    disposition: 'awaiting-base-refresh', blocker_owner: 'maint-52', next_command: 'dispatch-maint-52-scoped',
    check_state: 'checks_pending', review_state: 'clear',
    continuation: { class: 'transient', lane: 'dev-tool', reason: 'dev_tool_base_refresh_required',
      key: 'old-key', resume_after: '2026-11-08T07:00:00Z' },
  };
  const pr = { state: 'open', draft: false, user: { login: 'stranske' }, mergeable_state: 'blocked',
    head: { sha: 'b'.repeat(40), ref: retained.branch, repo: { full_name: retained.repository } },
    base: { sha: 'd'.repeat(40), repo: { full_name: retained.repository } } };
  const client = { rest: { pulls: { get: async () => ({ data: pr }) } } };
  const run = () => campaign.reconcileClosedDeliveryHandoffs([retained], [], client, op => op(client));
  return { retained, pr, run };
}

test('replacement generated head requests current-head reconciliation without adopting its identity', async () => {
  const f = fixture(), before = JSON.stringify(f.retained);
  const result = await f.run();
  assert.equal(result.reassessments.length, 1);
  assert.deepEqual(result.blockedKeys, ['stranske/Ready#667']);
  assert.deepEqual(result.records, []);
  assert.equal(JSON.stringify(f.retained), before);
  const request = result.reassessments[0];
  assert.equal(request.head_sha, f.pr.head.sha);
  assert.equal(request.immutable_handoff, undefined);
  assert.deepEqual(campaign.selectMaint71ContinuationRepos(request, [], ['stranske/Ready', 'stranske/Template']), ['stranske/Ready']);
});

for (const [name, change] of [
  ['fork head', f => { f.pr.head.repo.full_name = 'someone/Ready'; }],
  ['foreign base', f => { f.pr.base.repo.full_name = 'someone/Ready'; }],
  ['untrusted author', f => { f.pr.user.login = 'someone'; }],
  ['draft', f => { f.pr.draft = true; }],
  ['unknown base', f => { delete f.pr.base.sha; }],
  ['changed branch', f => { f.pr.head.ref += '-other'; }],
  ['frozen full-sync lane', f => { f.retained.lane = 'consumer-sync'; }],
]) test(`${name} remains blocked without a wake request`, async () => {
  const f = fixture(); change(f);
  const result = await f.run();
  assert.equal(result.reassessments.length, 0);
  assert.deepEqual(result.records, []);
});

test('stable head needs no reassessment', async () => {
  const f = fixture(); f.pr.head.sha = f.retained.head_sha;
  const result = await f.run();
  assert.deepEqual(result.reassessments, []);
  assert.deepEqual(result.blockedKeys, []);
});

test('intent and acknowledgment survive marker persistence and run-history eviction', async () => {
  const f = fixture(), result = await f.run(), request = result.reassessments[0];
  const queued = campaign.mergeHandoffReassessments([], result.reassessments, result.blockedKeys);
  const run = { id: 123, run_attempt: 1, status: 'completed', conclusion: 'success',
    repository: { full_name: 'stranske/Workflows' }, head_branch: 'main',
    path: '.github/workflows/maint-71-merge-sync-prs.yml', event: 'workflow_dispatch',
    updated_at: '2026-11-08T07:00:00Z', display_title: `Merge Sync PRs [dev-tool]\n${request.continuation_key}` };
  const acks = campaign.mergeContinuationAcknowledgments([], [run], queued);
  const restored = campaign.parseCampaignMarker(campaign.formatCampaignMarker({
    schema: campaign.CAMPAIGN_SCHEMA, handoff_reassessments: queued, continuation_acknowledgments: acks, items: [],
  }));
  assert.deepEqual(restored.handoff_reassessments, queued);
  assert.equal(campaign.mergeContinuationAcknowledgments(restored.continuation_acknowledgments, [], queued).length, 1);
  assert.equal(campaign.mergeHandoffReassessments(queued, [], result.blockedKeys).length, 1);
  assert.equal(campaign.mergeHandoffReassessments(queued, [], []).length, 0);
});

test('material head/base/check readiness changes replace the intent key', async () => {
  const f = fixture();
  const first = (await f.run()).reassessments[0];
  f.pr.mergeable_state = 'clean';
  const ready = (await f.run()).reassessments[0];
  assert.notEqual(ready.continuation_key, first.continuation_key);
  f.pr.base.sha = 'e'.repeat(40);
  assert.notEqual((await f.run()).reassessments[0].continuation_key, ready.continuation_key);
});
