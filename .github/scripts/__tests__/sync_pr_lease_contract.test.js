'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  DELIVERY_RECORD_SCHEMA,
  formatDeliveryRecord,
  parseDeliveryRecord,
  mergeEligibility,
} = require('../sync_pr_lease_contract');
const { selectMergeEligibleSyncPr } = require('../sync_pr_merge_contract');

const current = {
  schema: DELIVERY_RECORD_SCHEMA,
  durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
  plan_id: 'plan-abc',
  generation: 'template-abc',
  repository: 'stranske/Ready',
  desired_tree_hash: 'tree-abc',
  source_commit: 'source-abc',
  lease_expires_at: '2026-08-02T00:00:00Z',
  predecessor_prs: ['#10'],
  successor_prs: [],
};

test('an unexpired matching delivery record is merge eligible', () => {
  const marker = formatDeliveryRecord(current);
  const parsed = parseDeliveryRecord(`summary\n${marker}`);
  assert.deepEqual(parsed, { ...current, terminal_disposition: '' });
  assert.deepEqual(mergeEligibility(parsed, {
    now: '2026-08-01T22:00:00Z',
    planId: 'plan-abc',
    repository: 'stranske/Ready',
    desiredTreeHash: 'tree-abc',
  }), { eligible: true, reason: 'current_unexpired' });
  assert.equal(mergeEligibility({ ...parsed, lease_expires_at: '2026-08-01T21:00:00Z' }, {
    now: '2026-08-01T22:00:00Z',
  }).reason, 'lease_expired');
  assert.equal(mergeEligibility(parsed, { now: '2026-08-01T22:00:00Z', desiredTreeHash: 'other' }).reason, 'desired_tree_mismatch');
});

test('only the newest matching generation is selected for merge', () => {
  const old = {
    number: 10,
    created_at: '2026-08-01T20:00:00Z',
    head: { ref: 'sync/workflows-old' },
    body: formatDeliveryRecord({ ...current, generation: 'new', desired_tree_hash: 'tree-new' }),
  };
  const newest = {
    number: 11,
    created_at: '2026-08-01T21:00:00Z',
    head: { ref: 'sync/workflows-new' },
    body: formatDeliveryRecord({ ...current, generation: 'new', desired_tree_hash: 'tree-new' }),
  };

  const result = selectMergeEligibleSyncPr([old, newest], {
    syncHash: 'new',
    now: '2026-08-01T22:00:00Z',
    planId: 'plan-abc',
    repository: 'stranske/Ready',
    desiredTreeHash: 'tree-new',
  });

  assert.equal(result.active.number, newest.number);
  assert.deepEqual(result.stale.map((pr) => pr.number), [old.number]);
  assert.deepEqual(result.eligibility, { eligible: true, reason: 'current_unexpired' });
});

test('deliberate break: expired or terminal records cannot merge', () => {
  const now = '2026-08-01T22:00:00Z';
  assert.equal(mergeEligibility({ ...current, lease_expires_at: '2026-08-01T21:59:59Z' }, { now }).eligible, false);
  for (const terminal_disposition of ['merged', 'superseded', 'expired', 'blocked']) {
    assert.equal(mergeEligibility({ ...current, terminal_disposition }, { now }).eligible, false);
  }
});
