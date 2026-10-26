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

test('the action emits exactly the shared seal-precondition vocabulary', () => {
  const { SEAL_PRECONDITION_REASONS } = require('../sync_pr_lease_contract.js');
  const reasons = ['', 'staging', 'reviewing'].map(delivery_state => evaluateDeliverySeal(
    event({ body: record({ delivery_state }) }), REPOSITORY, NOW,
  ).reason);
  reasons.push(evaluateDeliverySeal(event({ body: record({ sealed_head_sha: 'c'.repeat(40) }) }),
    REPOSITORY, NOW).reason);
  assert.deepEqual(reasons.sort(), Object.values(SEAL_PRECONDITION_REASONS).sort());
  assert.deepEqual(reasons, ['delivery_not_sealed:legacy', 'delivery_not_sealed:reviewing',
    'delivery_not_sealed:staging', 'sealed_head_mismatch']);
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

test('action boundary reads explicit resolved metadata after runner resets the event file', () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const path = require('node:path');
  const { spawnSync } = require('node:child_process');
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'seal-event-boundary-'));
  try {
    const initial = event({ body: record({ delivery_state: 'staging',
      lease_expires_at: new Date(Date.now() + 86400000).toISOString(),
    }) });
    initial.pull_request.number = 42;
    initial.pull_request.state = 'open';
    const fresh = structuredClone(initial.pull_request);
    fresh.body = record({
      lease_expires_at: new Date(Date.now() + 86400000).toISOString(),
    });
    const eventPath = path.join(directory, 'event.json');
    // This is what WriteWebhookPayload restores before the seal action starts.
    fs.writeFileSync(eventPath, JSON.stringify(initial));
    const checker = path.resolve(__dirname, '../../actions/generated-delivery-seal/check.js');
    const run = (resolved = '') => spawnSync(process.execPath, [checker], {
      encoding: 'utf8',
      env: { ...process.env, GITHUB_EVENT_PATH: eventPath,
        GITHUB_REPOSITORY: REPOSITORY, GITHUB_EVENT_NAME: 'pull_request',
        GATE_PR_JSON: resolved },
    });
    const stale = run();
    assert.equal(stale.status, 1);
    assert.match(stale.stdout + stale.stderr, /delivery_not_sealed:staging/);
    const accepted = run(JSON.stringify(fresh));
    assert.equal(accepted.status, 0, accepted.stderr);
    assert.match(accepted.stdout, /Exact-head generated delivery seal is valid/);
    for (const mutate of [
      p => { p.number = 43; }, p => { p.head.sha = 'c'.repeat(40); },
      p => { p.head.repo.full_name = 'other/repo'; },
      p => { p.head.ref = 'other-branch'; }, p => { p.state = 'closed'; },
    ]) {
      const wrong = structuredClone(fresh); mutate(wrong);
      const rejected = run(JSON.stringify(wrong));
      assert.notEqual(rejected.status, 0);
      assert.doesNotMatch(rejected.stdout, /seal is valid/);
    }
    const malformed = run('{private-content-do-not-echo');
    assert.notEqual(malformed.status, 0);
    assert.doesNotMatch(malformed.stdout + malformed.stderr, /private-content-do-not-echo/);
    // The runner-owned event is not edited by the action to manufacture proof.
    assert.deepEqual(JSON.parse(fs.readFileSync(eventPath, 'utf8')), initial);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
