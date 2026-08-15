'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  formatDeliveryRecord,
} = require('../sync_pr_lease_contract.js');
const {
  evaluateDeliverySeal,
} = require('../../actions/generated-delivery-seal/check.js');

const REPOSITORY = 'stranske/example';
const HEAD_SHA = 'a'.repeat(40);
const NOW = '2026-08-15T17:00:00.000Z';

function record(overrides = {}) {
  return formatDeliveryRecord({
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1',
    plan_id: 'sha256:plan',
    generation: 'plan',
    repository: REPOSITORY,
    desired_tree_hash: 'sha256:tree',
    source_commit: 'b'.repeat(40),
    head_observed_sha: HEAD_SHA,
    head_observed_at: '2026-08-15T16:00:00.000Z',
    lease_expires_at: '2026-08-16T17:00:00.000Z',
    delivery_state: 'sealed',
    review_started_at: '2026-08-15T16:30:00.000Z',
    sealed_at: '2026-08-15T16:45:00.000Z',
    sealed_head_sha: HEAD_SHA,
    ...overrides,
  });
}

function event({ branch = 'sync/workflows-candidate', body = record(), headRepo = REPOSITORY } = {}) {
  return {
    pull_request: {
      body,
      base: { repo: { full_name: REPOSITORY } },
      head: {
        ref: branch,
        sha: HEAD_SHA,
        repo: { full_name: headRepo },
      },
    },
  };
}

test('ordinary pull requests do not require a generated delivery seal', () => {
  assert.deepEqual(
    evaluateDeliverySeal(event({ branch: 'feature/example' }), REPOSITORY, NOW),
    { required: false, valid: true, reason: '' },
  );
});

test('an exact sealed head is accepted', () => {
  assert.deepEqual(
    evaluateDeliverySeal(event(), REPOSITORY, NOW),
    { required: true, valid: true, reason: 'current_unexpired' },
  );
});

test('a mutable staging delivery is rejected', () => {
  const body = record({
    delivery_state: 'staging',
    review_started_at: '',
    sealed_at: '',
    sealed_head_sha: '',
  });
  const result = evaluateDeliverySeal(event({ body }), REPOSITORY, NOW);
  assert.equal(result.required, true);
  assert.equal(result.valid, false);
  assert.equal(result.reason, 'delivery_not_sealed:staging');
});

test('a seal for a different head is rejected', () => {
  const result = evaluateDeliverySeal(
    event({ body: record({ sealed_head_sha: 'c'.repeat(40) }) }),
    REPOSITORY,
    NOW,
  );
  assert.equal(result.valid, false);
  assert.equal(result.reason, 'sealed_head_mismatch');
});

test('forked stable-delivery heads are rejected', () => {
  const result = evaluateDeliverySeal(
    event({ headRepo: 'attacker/example' }),
    REPOSITORY,
    NOW,
  );
  assert.equal(result.valid, false);
  assert.equal(result.reason, 'stable delivery must originate from the base repository');
});
