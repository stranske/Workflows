'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { compactCanaryRefresh } = require('../sync_refresh_diagnostics');
test('diagnostic histories deduplicate without mutating decision inputs or losing unknowns', () => {
  const plan = { schema: 'workflows.consumer-sync-plan/v1', plan_id: 'sha256:plan',
    manifest_sha256: 'sha256:manifest', entries: [{ target: 'scripts/a', content: 'large' }], removals: [] };
  const runs = [{ id: 7, run_attempt: 2, head_sha: 'a'.repeat(40), updated_at: '2026-11-09T22:00:00Z',
    status: 'completed', conclusion: 'cancelled', repository: { description: 'irrelevant' },
    refresh_unknown: true, refresh_receipt: { state: 'unknown', proof: { artifact_id: 80, archive_sha256: 'abc' } },
    refresh_plan: { plan_id: plan.plan_id, source_commit: 'b'.repeat(40), plan } }];
  const original = { red: 1, drainable: 0, held_plans: [plan.plan_id],
    canaries: [{ refresh_state: { state: 'unknown', runs } }], dispatch_state: { state: 'unknown', runs } };
  const before = structuredClone(original), compact = compactCanaryRefresh(original);
  assert.deepEqual(original, before);
  assert.equal(compact.dispatch_state.state, 'unknown');
  assert.equal(compact.red, 1); assert.equal(compact.drainable, 0);
  assert.deepEqual(compact.held_plans, original.held_plans);
  assert.deepEqual(compact.canaries[0].refresh_state.runs_ref, compact.dispatch_state.runs_ref);
  assert.equal(Object.keys(compact.histories).length, 1);
  const [history] = Object.values(compact.histories);
  assert.equal(history[0].refresh_unknown, true);
  assert.deepEqual(history[0].refresh_receipt, runs[0].refresh_receipt);
  assert.equal(history[0].refresh_plan.plan.schema, 'workflows.consumer-sync-plan-reference/v1');
  assert.equal(history[0].refresh_plan.plan.plan_id, plan.plan_id);
  assert.equal(history[0].id, 7); assert.equal(history[0].run_attempt, 2);
});
