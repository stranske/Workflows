'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildNoChangeEvidence,
  buildNoChangeCanaryEvidence,
  mergeCampaignNoChangeEvidence,
  buildMarkdownSummary,
  buildSyncRunReport,
  summarizeResults,
} = require('../sync_run_contract');

test('buildNoChangeEvidence binds unchanged delivery repos to an immutable campaign plan', () => {
  const planId = `sha256:${'a'.repeat(64)}`;
  const sourceCommit = 'b'.repeat(40);
  const result = buildNoChangeEvidence({
    expectedRepositories: ['stranske/Ready'],
    planId,
    planScope: 'full',
    sourceCommit,
    results: [{
      repo: 'stranske/Ready', status: 'no_changes', plan_id: planId,
      plan_scope: 'full', scope_base_sha: '', source_commit: sourceCommit,
      consumer_head_sha: 'c'.repeat(40),
    }],
  });
  assert.equal(result.ok, true);
  assert.equal(result.evidence.schema, 'workflows.consumer-sync-no-change-evidence/v1');
  assert.equal(result.evidence.results[0].evidence_source, 'no-change-delivery');
  assert.equal(result.evidence.results[0].required_check_state, 'not-applicable');
  assert.equal(
    result.evidence.results[0].delivery_validation_state,
    'exact-tree-no-change',
  );
});

test('buildNoChangeEvidence fails closed on immutable mismatches and duplicate rows', () => {
  const planId = `sha256:${'a'.repeat(64)}`;
  const sourceCommit = 'b'.repeat(40);
  const base = {
    repo: 'stranske/Ready', status: 'no_changes', plan_id: planId,
    plan_scope: 'source-delta', scope_base_sha: 'c'.repeat(40),
    source_commit: sourceCommit, consumer_head_sha: 'd'.repeat(40),
  };
  const mismatch = buildNoChangeEvidence({
    expectedRepositories: ['stranske/Ready'],
    planId,
    planScope: 'source-delta',
    scopeBaseSha: 'c'.repeat(40),
    sourceCommit,
    results: [{
      ...base,
      plan_id: `sha256:${'e'.repeat(64)}`,
      plan_scope: 'full',
      scope_base_sha: 'f'.repeat(40),
      source_commit: '0'.repeat(40),
      consumer_head_sha: 'not-a-sha',
    }],
  });
  assert.equal(mismatch.ok, false);
  assert.ok(mismatch.errors.includes('no_change_delivery_plan_mismatch:stranske/Ready'));
  assert.ok(mismatch.errors.includes('no_change_delivery_scope_mismatch:stranske/Ready'));
  assert.ok(mismatch.errors.includes('no_change_delivery_scope_base_mismatch:stranske/Ready'));
  assert.ok(mismatch.errors.includes('no_change_delivery_source_mismatch:stranske/Ready'));
  assert.ok(mismatch.errors.includes('no_change_delivery_head_invalid:stranske/Ready'));

  const duplicate = buildNoChangeEvidence({
    expectedRepositories: ['stranske/Ready'],
    planId,
    planScope: 'source-delta',
    scopeBaseSha: 'c'.repeat(40),
    sourceCommit,
    results: [base, base],
  });
  assert.equal(duplicate.ok, false);
  assert.ok(duplicate.errors.includes('duplicate_no_change_delivery:stranske/Ready'));
});

test('buildNoChangeCanaryEvidence binds no-diff canaries to the exact plan and head', () => {
  const planId = `sha256:${'a'.repeat(64)}`;
  const sourceCommit = 'b'.repeat(40);
  const consumerHeadSha = 'c'.repeat(40);
  const result = buildNoChangeCanaryEvidence({
    expectedCanaries: ['stranske/Ready', 'stranske/Travel'],
    planId,
    planScope: 'full',
    sourceCommit,
    results: [
      {
        repo: 'stranske/Ready',
        status: 'no_changes',
        plan_id: planId,
        plan_scope: 'full',
        scope_base_sha: '',
        source_commit: sourceCommit,
        consumer_head_sha: consumerHeadSha,
      },
      { repo: 'stranske/Travel', status: 'created_pr', plan_id: planId },
    ],
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.evidence.results, [{
    repo: 'stranske/Ready',
    plan_id: planId,
    plan_scope: 'full',
    scope_base_sha: '',
    source_commit: sourceCommit,
    head_sha: consumerHeadSha,
    evidence_source: 'no-change-canary',
    required_check_state: 'success',
    active_review_thread_count: 0,
  }]);
});

test('buildNoChangeCanaryEvidence rejects stale plan and missing head claims', () => {
  const result = buildNoChangeCanaryEvidence({
    expectedCanaries: ['stranske/Ready'],
    planId: `sha256:${'a'.repeat(64)}`,
    planScope: 'source-delta',
    scopeBaseSha: '1'.repeat(40),
    sourceCommit: '2'.repeat(40),
    results: [{
      repo: 'stranske/Ready',
      status: 'no_changes',
      plan_id: `sha256:${'f'.repeat(64)}`,
      plan_scope: 'source-delta',
      scope_base_sha: '1'.repeat(40),
      source_commit: '2'.repeat(40),
      consumer_head_sha: '',
    }],
  });

  assert.equal(result.ok, false);
  assert.ok(result.errors.includes('no_change_canary_plan_mismatch:stranske/Ready'));
  assert.ok(result.errors.includes('no_change_canary_head_invalid:stranske/Ready'));
});

test('buildNoChangeCanaryEvidence rejects duplicate and immutable scope mismatches', () => {
  const planId = `sha256:${'a'.repeat(64)}`;
  const sourceCommit = 'b'.repeat(40);
  const result = buildNoChangeCanaryEvidence({
    expectedCanaries: ['stranske/Ready'],
    planId,
    planScope: 'source-delta',
    scopeBaseSha: 'c'.repeat(40),
    sourceCommit,
    results: [
      { repo: 'stranske/Ready', status: 'no_changes', plan_id: planId, plan_scope: 'full', scope_base_sha: 'd'.repeat(40), source_commit: sourceCommit, consumer_head_sha: 'e'.repeat(40) },
      { repo: 'stranske/Ready', status: 'no_changes', plan_id: planId, plan_scope: 'source-delta', scope_base_sha: 'c'.repeat(40), source_commit: sourceCommit, consumer_head_sha: 'e'.repeat(40) },
    ],
  });

  assert.equal(result.ok, false);
  assert.ok(result.errors.includes('no_change_canary_scope_mismatch:stranske/Ready'));
  assert.ok(result.errors.includes('no_change_canary_scope_base_mismatch:stranske/Ready'));
  assert.ok(result.errors.includes('duplicate_no_change_canary:stranske/Ready'));
});

test('mergeCampaignNoChangeEvidence dedupes overlapping canary and delivery rows by repo', () => {
  const delivery = {
    schema: 'workflows.consumer-sync-no-change-evidence/v1',
    version: 1,
    results: [
      { repo: 'stranske/Ready', evidence_source: 'no-change-delivery', head_sha: 'd'.repeat(40) },
      { repo: 'stranske/Travel', evidence_source: 'no-change-delivery', head_sha: 'e'.repeat(40) },
    ],
  };
  const canaryRows = [
    { repo: 'stranske/Ready', evidence_source: 'no-change-canary', head_sha: 'c'.repeat(40) },
  ];
  const merged = mergeCampaignNoChangeEvidence(canaryRows, delivery);
  assert.equal(merged.schema, delivery.schema);
  assert.equal(merged.version, delivery.version);
  assert.equal(merged.results.length, 2);
  const ready = merged.results.find((row) => row.repo === 'stranske/Ready');
  assert.equal(ready.evidence_source, 'no-change-canary');
  assert.equal(ready.head_sha, 'c'.repeat(40));
});

test('summarizeResults counts known statuses and buckets unknown as error', () => {
  assert.deepEqual(
    summarizeResults([
      { status: 'created_pr' },
      { status: 'existing_pr' },
      { status: 'refreshed_pr' },
      { status: 'created_pr' },
      { status: 'unexpected_status' },
    ]),
    {
      no_changes: 0,
      dry_run_changes: 0,
      existing_pr: 1,
      refreshed_pr: 1,
      created_pr: 2,
      no_committed_changes: 0,
      create_pr_failed: 0,
      sync_failed: 0,
      label_failed: 0,
      error: 1,
    },
  );
});

test('buildSyncRunReport publishes the sync branch contract', () => {
  const report = buildSyncRunReport({
    generatedAt: '2026-04-25T08:00:00Z',
    targetRepos: ['stranske/Ready'],
    registeredRepos: ['stranske/Ready', 'stranske/Template'],
    templateHash: '91c0e7663c12',
    dryRun: true,
    force: false,
    run: {
      repository: 'stranske/Workflows',
      run_id: 123,
    },
    results: [
      {
        repo: 'stranske/Ready',
        status: 'dry_run_changes',
        changes_count: 7,
      },
    ],
  });

  assert.equal(report.schema, 'workflows-consumer-sync-run/v1');
  assert.equal(report.inputs.expected_branch, 'sync/workflows-91c0e7663c12');
  assert.equal(report.inputs.dry_run, true);
  assert.deepEqual(report.summary, {
    no_changes: 0,
    dry_run_changes: 1,
    existing_pr: 0,
    refreshed_pr: 0,
    created_pr: 0,
    no_committed_changes: 0,
    create_pr_failed: 0,
    sync_failed: 0,
    label_failed: 0,
    error: 0,
  });
});

test('buildMarkdownSummary names the report artifact and non-zero statuses', () => {
  const markdown = buildMarkdownSummary(
    buildSyncRunReport({
      targetRepos: ['stranske/Ready'],
      templateHash: '91c0e7663c12',
      results: [{ status: 'created_pr' }, { status: 'no_changes' }],
    }),
  );

  assert.match(markdown, /workflows-consumer-sync-run\/v1/);
  assert.match(markdown, /sync\/workflows-91c0e7663c12/);
  assert.match(markdown, /\| created_pr \| 1 \|/);
  assert.match(markdown, /consumer-sync-run-report/);
});
