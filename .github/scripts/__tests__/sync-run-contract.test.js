'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildNoChangeCanaryEvidence,
  buildMarkdownSummary,
  buildSyncRunReport,
  summarizeResults,
} = require('../sync_run_contract');

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
