'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildMarkdownSummary,
  buildDeliveryHandoff,
  buildMergeReport,
  classifyGeneratedPr,
  classifySyncPrChecks,
  collectDeletableSyncBranches,
  generatedDeliveryLane,
  isTrustedGeneratedDeliveryPr,
  isTrustedSyncPr,
  normalizeSyncHash,
  parseBooleanInput,
  selectActiveSyncPr,
  selectMergeEligibleSyncPr,
  summarizeResults,
  syncBranchForHash,
} = require('../sync_pr_merge_contract');
const { assertRuntimeAcMergeAllowed } = require('../runtime_ac_merge_guard');

const pr = (number, ref, created_at) => ({
  number,
  title: `sync ${number}`,
  created_at,
  head: { ref },
});

const checkRun = ({
  name,
  status = 'completed',
  conclusion = 'success',
  started_at = '2026-04-25T01:00:00Z',
}) => ({
  name,
  status,
  conclusion,
  started_at,
});

test('normalizeSyncHash accepts raw hashes and branch names', () => {
  assert.equal(normalizeSyncHash('5108b94a2435'), '5108b94a2435');
  assert.equal(normalizeSyncHash('sync/workflows-5108b94a2435'), '5108b94a2435');
  assert.equal(syncBranchForHash('5108b94a2435'), 'sync/workflows-5108b94a2435');
});

test('parseBooleanInput preserves explicit false values', () => {
  assert.equal(parseBooleanInput('false', true), false);
  assert.equal(parseBooleanInput(false, true), false);
  assert.equal(parseBooleanInput('0', true), false);
  assert.equal(parseBooleanInput('', true), true);
  assert.equal(parseBooleanInput(undefined, false), false);
});

test('selectActiveSyncPr falls back to newest sync PR without a target hash', () => {
  const selection = selectActiveSyncPr([
    pr(1, 'sync/workflows-old', '2026-04-25T01:00:00Z'),
    pr(2, 'sync/workflows-new', '2026-04-25T02:00:00Z'),
  ]);

  assert.equal(selection.active.number, 2);
  assert.deepEqual(selection.stale.map((item) => item.number), [1]);
  assert.equal(selection.missingExpected, false);
});

test('isTrustedSyncPr requires the configured actor and sync branch', () => {
  const trusted = { ...pr(1, 'sync/workflows-current', '2026-04-25T01:00:00Z'), user: { login: 'stranske' } };
  assert.equal(isTrustedSyncPr(trusted, ['stranske']), true);
  assert.equal(isTrustedSyncPr({ ...trusted, user: { login: 'untrusted' } }, ['stranske']), false);
});

test('generated delivery classification gives sync and dev-tool lanes identical check and review dispositions', () => {
  const record = '<!-- sync-pr-delivery-record:v1 {"schema":"sync-pr-delivery-record/v1","durable_issue_url":"https://github.com/stranske/Workflows/issues/1836","plan_id":"plan-abc","generation":"generation-1","repository":"stranske/Ready","desired_tree_hash":"tree-abc","source_commit":"source-abc","lease_expires_at":"2026-08-02T00:00:00Z","predecessor_prs":[],"successor_prs":[]} -->';
  const sync = { ...pr(1, 'sync/workflows-current', '2026-04-25T01:00:00Z'), body: record, user: { login: 'stranske' } };
  const devTool = { ...pr(2, 'deps/sync-dev-versions-20260801', '2026-04-25T01:00:00Z'), body: record, user: { login: 'stranske' } };

  assert.equal(generatedDeliveryLane(sync.head.ref), 'sync');
  assert.equal(generatedDeliveryLane(devTool.head.ref), 'dev-tool-sync');
  assert.equal(isTrustedGeneratedDeliveryPr(devTool, ['stranske']), true);
  for (const candidate of [sync, devTool]) {
    assert.equal(classifyGeneratedPr({ pr: candidate, now: '2026-08-01T00:00:00Z' }).disposition, 'current');
    assert.equal(classifyGeneratedPr({ pr: candidate, activeReviewThreadCount: 1, now: '2026-08-01T00:00:00Z' }).disposition, 'review-blocked');
    assert.equal(classifyGeneratedPr({ pr: candidate, activeReviewThreadCount: -1, now: '2026-08-01T00:00:00Z' }).next_command, 'retry-review-thread-query');
    assert.equal(classifyGeneratedPr({ pr: candidate, checkState: { status: 'checks_failed' }, now: '2026-08-01T00:00:00Z' }).disposition, 'repo-local-failure');
  }
});

test('selectActiveSyncPr honors target hash instead of newest PR', () => {
  const selection = selectActiveSyncPr(
    [
      pr(1, 'sync/workflows-5108b94a2435', '2026-04-25T01:00:00Z'),
      pr(2, 'sync/workflows-later', '2026-04-25T02:00:00Z'),
    ],
    '5108b94a2435',
  );

  assert.equal(selection.active.number, 1);
  assert.equal(selection.expectedBranch, 'sync/workflows-5108b94a2435');
  assert.deepEqual(selection.stale.map((item) => item.number), [2]);
});

test('selectActiveSyncPr reports missing target without marking stale PRs', () => {
  const selection = selectActiveSyncPr(
    [pr(1, 'sync/workflows-other', '2026-04-25T01:00:00Z')],
    '5108b94a2435',
  );

  assert.equal(selection.active, null);
  assert.deepEqual(selection.stale, []);
  assert.equal(selection.missingExpected, true);
});

test('selectMergeEligibleSyncPr refuses legacy delivery attempts', () => {
  const legacy = pr(1, 'sync/workflows-current', '2026-04-25T01:00:00Z');
  assert.equal(selectMergeEligibleSyncPr([legacy]).eligibility.reason, 'missing_delivery_record');
});

test('selectMergeEligibleSyncPr rejects a PR whose head no longer matches its lease', () => {
  const leased = {
    ...pr(1, 'sync/workflows-current', '2026-04-25T01:00:00Z'),
    body: '<!-- sync-pr-delivery-record:v1 {"schema":"sync-pr-delivery-record/v1","durable_issue_url":"https://github.com/stranske/Workflows/issues/1836","plan_id":"plan-abc","generation":"template-abc","repository":"stranske/Ready","desired_tree_hash":"tree-abc","source_commit":"source-abc","lease_expires_at":"2026-08-02T00:00:00Z","predecessor_prs":[],"successor_prs":[]} -->',
  };
  assert.equal(selectMergeEligibleSyncPr([leased], {
    now: '2026-08-01T22:00:00Z',
    repository: 'stranske/Ready',
    desiredTreeHash: 'tree-other',
  }).eligibility.reason, 'desired_tree_mismatch');
});

test('buildMergeReport provides machine-readable summary counts', () => {
  const report = buildMergeReport({
    generatedAt: '2026-04-25T06:00:00Z',
    syncHash: 'sync/workflows-5108b94a2435',
    registeredRepos: ['stranske/Ready'],
    targetRepos: ['stranske/Ready'],
    autoMerge: false,
    dryRun: true,
    results: [
      { repo: 'stranske/Ready', status: 'stale_closed' },
      { repo: 'stranske/Ready', status: 'dry_run_merge' },
    ],
  });

  assert.equal(report.schema, 'workflows-sync-pr-merge/v1');
  assert.equal(report.inputs.expected_branch, 'sync/workflows-5108b94a2435');
  assert.deepEqual(report.summary, {
    no_prs: 0,
    target_missing: 0,
    stale_closed: 1,
    stale_close_failed: 0,
    branch_deleted: 0,
    branch_delete_failed: 0,
    checks_failed: 0,
    checks_pending: 0,
    review_blocked: 0,
    ready: 0,
    dry_run_merge: 1,
    merge_blocked_runtime_ac: 0,
    merged: 0,
    merge_failed: 0,
    delivery_contract_blocked: 0,
    error: 0,
  });
  assert.deepEqual(report.handoff_records, []);
});

test('buildDeliveryHandoff preserves the restart fields for a generated PR', () => {
  assert.deepEqual(buildDeliveryHandoff({
    owner: 'stranske', repo: 'Ready', pr: 11, branch: 'deps/sync-dev-versions-20260801',
    head_sha: 'abc', delivery_generation: 'g2', delivery_disposition: 'review-blocked',
    blocker_owner: 'closer', next_command: 'resolve-active-review-threads',
    status: 'review_blocked', active_review_thread_count: 2,
  }), {
    schema: 'workflows-generated-delivery-handoff/v1', repository: 'stranske/Ready', pr: 11,
    branch: 'deps/sync-dev-versions-20260801', head_sha: 'abc', delivery_generation: 'g2',
    lane: 'dev-tool-sync', disposition: 'review-blocked', blocker_owner: 'closer',
    next_command: 'resolve-active-review-threads',
    check_state: 'ready', review_state: 'blocked',
  });
});

test('buildDeliveryHandoff rewrites terminal merge outcomes', () => {
  assert.deepEqual(buildDeliveryHandoff({
    owner: 'stranske', repo: 'Ready', pr: 11, branch: 'sync/workflows-abc',
    head_sha: 'abc', delivery_generation: 'g2', delivery_disposition: 'current',
    blocker_owner: 'maint-71', next_command: 'merge-current-delivery',
    status: 'merged',
  }), {
    schema: 'workflows-generated-delivery-handoff/v1', repository: 'stranske/Ready', pr: 11,
    branch: 'sync/workflows-abc', head_sha: 'abc', delivery_generation: 'g2',
    lane: 'sync', disposition: 'merged', blocker_owner: 'none', next_command: 'none',
    check_state: 'ready', review_state: 'clear',
  });
  assert.equal(buildDeliveryHandoff({
    owner: 'stranske', repo: 'Ready', pr: 11, branch: 'sync/workflows-abc',
    head_sha: 'abc', delivery_generation: 'g2', status: 'branch_deleted',
  }), null);
});

test('buildDeliveryHandoff rejects results that lack required restart fields', () => {
  assert.equal(buildDeliveryHandoff({ owner: 'stranske', repo: 'Ready', pr: 11, branch: 'sync/workflows-current' }), null);
});

test('collectDeletableSyncBranches keeps open PR branches and non-sync branches', () => {
  const branches = [
    { name: 'sync/workflows-old' },
    { name: 'sync/workflows-open' },
    { name: 'deps/sync-dev-versions-123' },
    { name: 'feature/manual-work' },
  ];
  const openPullRequests = [pr(10, 'sync/workflows-open', '2026-05-01T00:00:00Z')];
  const closedPullRequests = [
    pr(9, 'sync/workflows-old', '2026-04-30T00:00:00Z'),
    pr(8, 'feature/manual-work', '2026-04-29T00:00:00Z'),
  ];

  assert.deepEqual(
    collectDeletableSyncBranches({ branches, openPullRequests, closedPullRequests }),
    ['sync/workflows-old'],
  );
});

test('classifySyncPrChecks ignores non-required failing checks when required contexts pass', () => {
  const result = classifySyncPrChecks({
    requiredContexts: ['Gate / gate'],
    fallbackDenylist: ['Detect keepalive'],
    checkRuns: [
      checkRun({ name: 'Gate / gate', conclusion: 'success' }),
      checkRun({ name: 'Resolve Context', conclusion: 'failure' }),
    ],
  });

  assert.equal(result.status, 'ready');
  assert.deepEqual(result.failed, []);
  assert.deepEqual(result.pending, []);
});

test('classifySyncPrChecks fails when a required check fails', () => {
  const result = classifySyncPrChecks({
    requiredContexts: new Set(['Gate / gate']),
    checkRuns: [
      checkRun({ name: 'Gate / gate', conclusion: 'failure' }),
      checkRun({ name: 'Resolve Context', conclusion: 'failure' }),
    ],
  });

  assert.equal(result.status, 'checks_failed');
  assert.deepEqual(result.failed.map((check) => check.name), ['Gate / gate']);
  assert.deepEqual(result.pending, []);
});

test('classifySyncPrChecks uses the latest check run per name', () => {
  const result = classifySyncPrChecks({
    requiredContexts: ['Gate / gate'],
    checkRuns: [
      checkRun({
        name: 'Gate / gate',
        conclusion: 'failure',
        started_at: '2026-04-25T01:00:00Z',
      }),
      checkRun({
        name: 'Gate / gate',
        conclusion: 'success',
        started_at: '2026-04-25T02:00:00Z',
      }),
    ],
  });

  assert.equal(result.status, 'ready');
  assert.deepEqual(result.failed, []);
});

test('classifySyncPrChecks reports pending when a required check is in progress', () => {
  const result = classifySyncPrChecks({
    requiredContexts: ['Gate / gate'],
    checkRuns: [
      checkRun({
        name: 'Gate / gate',
        status: 'in_progress',
        conclusion: null,
      }),
      checkRun({ name: 'Resolve Context', conclusion: 'failure' }),
    ],
  });

  assert.equal(result.status, 'checks_pending');
  assert.deepEqual(result.failed, []);
  assert.deepEqual(result.pending.map((check) => check.name), ['Gate / gate']);
});

test('classifySyncPrChecks falls back to denylist when required contexts are empty', () => {
  const fallbackDenylist = ['Detect keepalive'];
  const denylistedOnly = classifySyncPrChecks({
    requiredContexts: [],
    fallbackDenylist,
    checkRuns: [
      checkRun({ name: 'Gate / gate', conclusion: 'success' }),
      checkRun({ name: 'Detect keepalive activation', conclusion: 'failure' }),
    ],
  });

  assert.equal(denylistedOnly.status, 'ready');

  const nonDenylistedFailure = classifySyncPrChecks({
    requiredContexts: [],
    fallbackDenylist,
    checkRuns: [
      checkRun({ name: 'Gate / gate', conclusion: 'success' }),
      checkRun({ name: 'Record autofix metrics', conclusion: 'failure' }),
    ],
  });

  assert.equal(nonDenylistedFailure.status, 'checks_failed');
  assert.deepEqual(nonDenylistedFailure.failed.map((check) => check.name), [
    'Record autofix metrics',
  ]);
});

test('runtime-AC sync PRs are blocked while ordinary sync PRs still merge', async () => {
  const syncPrs = [
    {
      owner: 'stranske',
      repo: 'Ready',
      pr: pr(201, 'sync/workflows-plain', '2026-04-25T01:00:00Z'),
      labels: [{ name: 'consumer-sync' }],
    },
    {
      owner: 'stranske',
      repo: 'Counter_Risk',
      pr: pr(202, 'sync/workflows-runtime-ac', '2026-04-25T01:05:00Z'),
      labels: [{ name: 'consumer-sync' }, { name: 'acceptance-criteria' }],
    },
  ];
  const passingChecks = [checkRun({ name: 'Gate / gate', conclusion: 'success' })];
  const mergeCalls = [];
  const results = [];

  for (const fixture of syncPrs) {
    const classification = classifySyncPrChecks({
      requiredContexts: ['Gate / gate'],
      checkRuns: passingChecks,
    });
    assert.equal(classification.status, 'ready');

    try {
      await assertRuntimeAcMergeAllowed({
        owner: fixture.owner,
        repo: fixture.repo,
        prNumber: fixture.pr.number,
        labels: fixture.labels,
        source: 'maint-71-merge-sync-prs',
      });
    } catch (error) {
      results.push({
        owner: fixture.owner,
        repo: fixture.repo,
        pr: fixture.pr.number,
        branch: fixture.pr.head.ref,
        status: 'merge_blocked_runtime_ac',
        error: error.message,
      });
      continue;
    }

    mergeCalls.push({
      owner: fixture.owner,
      repo: fixture.repo,
      pull_number: fixture.pr.number,
    });
    results.push({
      owner: fixture.owner,
      repo: fixture.repo,
      pr: fixture.pr.number,
      branch: fixture.pr.head.ref,
      status: 'merged',
    });
  }

  assert.deepEqual(mergeCalls, [
    {
      owner: 'stranske',
      repo: 'Ready',
      pull_number: 201,
    },
  ]);
  assert.equal(results.find((result) => result.pr === 201).status, 'merged');
  assert.equal(results.find((result) => result.pr === 202).status, 'merge_blocked_runtime_ac');
  assert.match(
    results.find((result) => result.pr === 202).error,
    /require local Orchestrator runtime acceptance checks/,
  );

  const report = buildMergeReport({
    results,
    registeredRepos: ['stranske/Ready', 'stranske/Counter_Risk'],
    targetRepos: ['stranske/Ready', 'stranske/Counter_Risk'],
    autoMerge: true,
    dryRun: false,
    generatedAt: '2026-04-25T06:00:00Z',
  });
  const markdown = buildMarkdownSummary(report);

  assert.equal(report.summary.merged, 1);
  assert.equal(report.summary.merge_blocked_runtime_ac, 1);
  assert.match(markdown, /\| merged \| 1 \|/);
  assert.match(markdown, /\| merge_blocked_runtime_ac \| 1 \|/);
});

test('buildMarkdownSummary includes non-zero statuses and artifact name', () => {
  const markdown = buildMarkdownSummary({
    schema: 'workflows-sync-pr-merge/v1',
    inputs: {
      repos: ['stranske/Ready'],
      auto_merge: true,
      dry_run: false,
      expected_branch: 'sync/workflows-5108b94a2435',
    },
    summary: summarizeResults([
      { status: 'merged' },
      { status: 'checks_pending' },
      { status: 'merge_blocked_runtime_ac' },
    ]),
  });

  assert.match(markdown, /Expected branch: `sync\/workflows-5108b94a2435`/);
  assert.match(markdown, /\| merged \| 1 \|/);
  assert.match(markdown, /\| merge_blocked_runtime_ac \| 1 \|/);
  assert.match(markdown, /sync-pr-merge-report/);
});
