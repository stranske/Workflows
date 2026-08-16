'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  buildMarkdownSummary,
  buildDeliveryHandoff,
  buildMergeReport,
  candidateRefreshDecision,
  candidatePromotionDecision,
  deliveryRefreshDecision,
  candidateEvidenceAllowsMutation,
  classifyDeliveryContinuation,
  classifyGeneratedPr,
  classifySyncPrChecks,
  commitSignatureAllowsMerge,
  collectDeletableSyncBranches,
  evaluatePostPushReviewWindow,
  evaluateReviewerSettlement,
  generatedDeliveryLane,
  generatedDeliveryRequiresVerifiedHead,
  generatedPrsForSyncSelector,
  isBlockingSyncSystemFailure,
  isReviewerCapacitySignal,
  isReviewerNonResponseSignal,
  isStableSyncBranchName,
  isTrustedGeneratedDeliveryPr,
  isTrustedSyncPr,
  normalizeSyncHash,
  parseBooleanInput,
  parsePromotionEvidenceFromCommitMessage,
  requiresStrictGateBranchUpdate,
  requiredContextsFromRulesets,
  rulesetRefPatternMatches,
  selectActiveSyncPr,
  selectLatestMergedCandidatePr,
  selectMergeEligibleSyncPr,
  summarizeResults,
  syncBranchForHash,
  validateCanaryEvidence,
  validateExpectedCandidateIdentity,
  validateSourceDeltaEvidenceBinding,
} = require('../sync_pr_merge_contract');
const { assertRuntimeAcMergeAllowed } = require('../runtime_ac_merge_guard');
const {
  collectReviewerEvidence,
  legacyStatusAsCheck,
  normalizeReviewPolicy,
  parseReviewResolutionProofs,
  run,
  validateReviewResolutionProof,
} = require('../maint71_merge_sync_prs');

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

test('transient delivery holds carry a durable due time and lane', () => {
  assert.deepEqual(classifyDeliveryContinuation({
    branch: 'sync/workflows-candidate',
    status: 'review_window_pending',
    review_window_eligible_at: '2026-08-15T12:07:00Z',
  }, '2026-08-15T12:00:00Z'), {
    class: 'transient',
    lane: 'candidate',
    reason: 'review_window_pending',
    resume_after: '2026-08-15T12:07:00.000Z',
  });
  assert.equal(classifyDeliveryContinuation({
    branch: 'sync/workflows-candidate',
    status: 'review_blocked',
  }).class, 'actionable');
  assert.equal(classifyDeliveryContinuation({
    branch: 'sync/workflows-delivery',
    status: 'merged',
  }).class, 'terminal');
  assert.equal(classifyDeliveryContinuation({
    branch: 'sync/workflows-delivery',
    status: 'sealed_head_mismatch',
  }).class, 'actionable');
  assert.equal(classifyDeliveryContinuation({
    branch: 'sync/workflows-delivery',
    status: 'delivery_review_not_started',
  }, '2026-08-15T12:00:00Z').resume_after, '2026-08-15T12:10:00.000Z');
});

test('promotion requires complete exact-plan evidence and terminal candidate rows', () => {
  const expectedCanaries = ['stranske/Travel', 'stranske/Portable'];
  const evidence = {
    results: expectedCanaries.map((repo, index) => ({
      repo,
      plan_id: 'plan-abc',
      source_commit: 'source-abc',
      pr: index + 1,
      head_sha: `head-${index + 1}`,
      required_check_state: 'success',
      active_review_thread_count: 0,
    })),
  };
  const report = {
    inputs: { sync_hash: 'candidate' },
    results: expectedCanaries.map((repository, index) => {
      const [owner, repo] = repository.split('/');
      return {
        owner,
        repo,
        pr: index + 1,
        branch: 'sync/workflows-candidate',
        status: index ? 'evidence_recovered' : 'merged',
      };
    }),
  };
  assert.deepEqual(candidatePromotionDecision({ report, evidence, expectedCanaries }), {
    eligible: true,
    errors: [],
    plan_id: 'plan-abc',
  });
  report.results[0].status = 'review_window_pending';
  const blocked = candidatePromotionDecision({ report, evidence, expectedCanaries });
  assert.equal(blocked.eligible, false);
  assert.match(blocked.errors.join('\n'), /stranske\/Travel/);
});

test('candidate base drift requests a no-filter refresh and stays transient', () => {
  const result = {
    owner: 'stranske',
    repo: 'Travel',
    branch: 'sync/workflows-candidate',
    status: 'stable_base_refresh_required',
    next_command: 'dispatch-maint-68-phase-canary-no-filter',
  };
  assert.deepEqual(classifyDeliveryContinuation(result, '2026-08-15T12:00:00Z'), {
    class: 'transient',
    lane: 'candidate',
    reason: 'stable_base_refresh_required',
    resume_after: '2026-08-15T12:10:00.000Z',
  });
  assert.deepEqual(candidateRefreshDecision({
    report: {
      inputs: { sync_hash: 'candidate' },
      results: [result],
    },
  }), {
    eligible: true,
    errors: [],
    repositories: ['stranske/Travel'],
  });
  assert.equal(candidateRefreshDecision({
    report: { inputs: { sync_hash: 'delivery' }, results: [result] },
  }).eligible, false);
});

test('delivery base drift replays only signed exact-plan promotion evidence', () => {
  const expectedCanaries = ['stranske/Travel', 'stranske/Portable'];
  const evidence = {
    schema: 'workflows.consumer-sync-canary-evidence/v1',
    results: expectedCanaries.map((repo, index) => ({
      repo,
      plan_id: 'plan-abc',
      source_commit: 'source-abc',
      pr: index + 1,
      head_sha: `head-${index + 1}`,
      required_check_state: 'success',
      active_review_thread_count: 0,
    })),
  };
  const encoded = Buffer.from(JSON.stringify(evidence), 'utf8').toString('base64');
  assert.deepEqual(parsePromotionEvidenceFromCommitMessage(
    `subject\n\nCanary evidence JSON (base64): ${encoded}\n`,
  ), evidence);
  assert.equal(parsePromotionEvidenceFromCommitMessage(
    'Canary evidence JSON (base64): not-valid-base64',
  ), null);
  const decision = deliveryRefreshDecision({
    report: {
      inputs: { sync_hash: 'delivery' },
      results: [{
        owner: 'stranske',
        repo: 'Ready',
        branch: 'sync/workflows-delivery',
        plan_id: 'plan-abc',
        status: 'stable_base_refresh_required',
        next_command: 'rerun-maint-68-phase-promote-with-same-evidence',
        promotion_evidence: evidence,
      }],
    },
    expectedCanaries,
  });
  assert.equal(decision.eligible, true);
  assert.equal(decision.plan_id, 'plan-abc');
  assert.deepEqual(decision.evidence, evidence);
  assert.equal(deliveryRefreshDecision({
    report: { inputs: { sync_hash: 'candidate' }, results: [] },
    expectedCanaries,
  }).eligible, false);
});

test('review resolution proof is exact-head, source-linked, and actor-bound', () => {
  const proof = {
    schema: 'workflows-sync-review-resolution/v1',
    repository: 'stranske/Portable',
    pr: 22,
    thread_id: 'PRRT_thread',
    head_sha: 'head-abc',
    source_fix_sha: 'a'.repeat(40),
    evidence_url: 'https://github.com/stranske/Workflows/pull/3091',
    reason: 'The current generated contract contains the merged source guard.',
  };
  assert.deepEqual(parseReviewResolutionProofs(JSON.stringify({ proofs: [proof] })), [proof]);
  assert.throws(
    () => parseReviewResolutionProofs('{not-json'),
    /review resolution proof is not valid JSON/,
  );
  assert.deepEqual(validateReviewResolutionProof(proof, {
    owner: 'stranske',
    repo: 'Portable',
    prNumber: 22,
    headSha: 'head-abc',
    actor: 'stranske-automation-bot',
    trustedActors: ['stranske-automation-bot'],
  }), { ok: true, errors: [] });
  assert.equal(validateReviewResolutionProof({
    ...proof,
    evidence_url: 'https://github.com/stranske/Workflows/pull/not-a-number',
  }, {
    owner: 'stranske',
    repo: 'Portable',
    prNumber: 22,
    headSha: 'head-abc',
    actor: 'stranske-automation-bot',
    trustedActors: ['stranske-automation-bot'],
  }).ok, false);
  const changedHead = validateReviewResolutionProof(proof, {
    owner: 'stranske',
    repo: 'Portable',
    prNumber: 22,
    headSha: 'head-new',
    actor: 'stranske-automation-bot',
    trustedActors: ['stranske-automation-bot'],
  });
  assert.equal(changedHead.ok, false);
  assert.ok(changedHead.errors.includes('head_mismatch'));
});

test('maint71 run writes reports and records a no-PR result with fake action clients', async () => {
  const originalCwd = process.cwd();
  const originalEnv = {
    REGISTERED_REPOS_INPUT: process.env.REGISTERED_REPOS_INPUT,
    CLEANUP_BRANCHES_INPUT: process.env.CLEANUP_BRANCHES_INPUT,
    DRY_RUN_INPUT: process.env.DRY_RUN_INPUT,
    AUTO_MERGE_INPUT: process.env.AUTO_MERGE_INPUT,
    OWNER_PR_PAT: process.env.OWNER_PR_PAT,
    SYNC_PR_MERGE_REPORT_JSON: process.env.SYNC_PR_MERGE_REPORT_JSON,
  };
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-run-'));
  const reportPath = path.join(tempDir, 'reports', 'merge-report.json');
  const summaries = [];
  const failures = [];
  const paginateCalls = [];
  const github = {
    paginate: async (method, params) => {
      paginateCalls.push({ method, params });
      return [];
    },
    rest: {
      pulls: { list: () => {} },
      repos: { createDispatchEvent: () => {} },
    },
  };
  const core = {
    addRaw: () => ({ write: async () => {} }),
    notice: (message) => summaries.push(message),
    setFailed: (message) => failures.push(message),
    warning: (message) => summaries.push(message),
    summary: { addRaw: () => ({ write: async () => {} }) },
  };

  try {
    process.chdir(tempDir);
    process.env.REGISTERED_REPOS_INPUT = 'stranske/Ready';
    process.env.CLEANUP_BRANCHES_INPUT = 'false';
    process.env.DRY_RUN_INPUT = 'true';
    process.env.AUTO_MERGE_INPUT = 'false';
    process.env.OWNER_PR_PAT = 'test-owner-token';
    process.env.SYNC_PR_MERGE_REPORT_JSON = reportPath;

    await run({
      github,
      core,
      context: {
        repo: { owner: 'stranske', repo: 'Workflows' },
        payload: {},
        runId: 1,
        runNumber: 1,
        workflow: 'Maint 71',
        ref: 'refs/heads/main',
        sha: 'abc',
      },
    });

    const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    assert.equal(paginateCalls.length, 1);
    assert.equal(paginateCalls[0].params.repo, 'Ready');
    assert.equal(report.summary.no_prs, 1);
    assert.equal(fs.existsSync(path.join(tempDir, 'artifacts', 'sync-canary-evidence.json')), true);
    assert.deepEqual(failures, []);
  } finally {
    process.chdir(originalCwd);
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('maint71 fails closed before cross-repository API calls without OWNER_PR_PAT', async () => {
  const originalOwnerPat = process.env.OWNER_PR_PAT;
  try {
    delete process.env.OWNER_PR_PAT;
    await assert.rejects(
      run({
        github: {},
        core: { warning: () => {} },
        context: {
          repo: { owner: 'stranske', repo: 'Workflows' },
          payload: {},
        },
      }),
      /Maint 71 requires OWNER_PR_PAT/,
    );
  } finally {
    if (originalOwnerPat === undefined) delete process.env.OWNER_PR_PAT;
    else process.env.OWNER_PR_PAT = originalOwnerPat;
  }
});

test('maint71 accepts no-change canary evidence only while the exact base head is current', async () => {
  const originalCwd = process.cwd();
  const envKeys = [
    'REGISTERED_REPOS_INPUT',
    'CLEANUP_BRANCHES_INPUT',
    'DRY_RUN_INPUT',
    'AUTO_MERGE_INPUT',
    'EVIDENCE_ONLY_INPUT',
    'ACTIVE_SYNC_HASH_INPUT',
    'EXPECTED_PLAN_ID_INPUT',
    'EXPECTED_PLAN_SCOPE_INPUT',
    'EXPECTED_SCOPE_BASE_SHA_INPUT',
    'EXPECTED_SOURCE_COMMIT_INPUT',
    'CANARY_BASELINE_EVIDENCE_JSON',
    'OWNER_PR_PAT',
    'CONSUMER_SYNC_CANARIES_PATH',
    'TRUSTED_SYNC_ACTORS',
    'SYNC_PR_MERGE_REPORT_JSON',
  ];
  const originalEnv = Object.fromEntries(envKeys.map((key) => [key, process.env[key]]));
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-no-change-'));
  const reportPath = path.join(tempDir, 'artifacts', 'merge-report.json');
  const canaryConfigPath = path.join(tempDir, 'consumer-sync-canaries.json');
  const repoName = 'stranske/Travel-Plan-Permission';
  const planId = `sha256:${'a'.repeat(64)}`;
  const sourceCommit = 'b'.repeat(40);
  const headSha = 'c'.repeat(40);
  fs.writeFileSync(
    canaryConfigPath,
    JSON.stringify({ canaries: [{ repo: repoName }] }),
  );
  const baseline = {
    schema: 'workflows.consumer-sync-canary-evidence/v1',
    version: 1,
    results: [{
      repo: repoName,
      plan_id: planId,
      plan_scope: 'full',
      scope_base_sha: '',
      source_commit: sourceCommit,
      head_sha: headSha,
      evidence_source: 'no-change-canary',
      required_check_state: 'success',
      active_review_thread_count: 0,
    }],
  };
  let checkConclusion = 'success';
  let requiredContexts = ['Gate / gate'];
  const github = {
    paginate: async (_method, params) => (
      params.ref === headSha
        ? [{ name: 'Gate / gate', status: 'completed', conclusion: checkConclusion }]
        : []
    ),
    rest: {
      pulls: { list: () => {} },
      checks: { listForRef: () => {} },
      repos: {
        get: async () => ({ data: { default_branch: 'main' } }),
        getBranchProtection: async () => ({
          data: { required_status_checks: { contexts: requiredContexts, checks: [] } },
        }),
        getRepoRulesets: async () => ({ data: [] }),
        getCombinedStatusForRef: async () => ({ data: { statuses: [] } }),
        createDispatchEvent: async () => ({}),
      },
      git: {
        getRef: async () => ({ data: { object: { sha: headSha } } }),
      },
    },
  };
  const failures = [];
  const core = {
    notice: () => {},
    setFailed: (message) => failures.push(message),
    warning: () => {},
    summary: { addRaw: () => ({ write: async () => {} }) },
  };

  try {
    process.chdir(tempDir);
    process.env.REGISTERED_REPOS_INPUT = repoName;
    process.env.CLEANUP_BRANCHES_INPUT = 'false';
    process.env.DRY_RUN_INPUT = 'true';
    process.env.AUTO_MERGE_INPUT = 'false';
    process.env.EVIDENCE_ONLY_INPUT = 'true';
    process.env.ACTIVE_SYNC_HASH_INPUT = 'candidate';
    process.env.EXPECTED_PLAN_ID_INPUT = planId;
    process.env.EXPECTED_PLAN_SCOPE_INPUT = 'full';
    process.env.EXPECTED_SCOPE_BASE_SHA_INPUT = '';
    process.env.EXPECTED_SOURCE_COMMIT_INPUT = sourceCommit;
    process.env.CANARY_BASELINE_EVIDENCE_JSON = JSON.stringify(baseline);
    process.env.OWNER_PR_PAT = 'test-owner-token';
    process.env.CONSUMER_SYNC_CANARIES_PATH = canaryConfigPath;
    process.env.TRUSTED_SYNC_ACTORS = 'stranske';
    process.env.SYNC_PR_MERGE_REPORT_JSON = reportPath;

    await run({
      github,
      core,
      context: {
        repo: { owner: 'stranske', repo: 'Workflows' },
        payload: {},
        runId: 3,
        runNumber: 3,
        workflow: 'Maint 71',
        ref: 'refs/heads/main',
        sha: sourceCommit,
      },
    });

    const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    const evidence = JSON.parse(
      fs.readFileSync(path.join(tempDir, 'artifacts', 'sync-canary-evidence.json'), 'utf8'),
    );
    assert.equal(report.summary.evidence_recovered, 1);
    assert.equal(report.results[0].branch, 'sync/workflows-candidate');
    assert.equal(evidence.results[0].head_sha, headSha);
    assert.equal(evidence.results[0].evidence_source, 'no-change-canary');
    assert.deepEqual(failures, []);

    checkConclusion = 'failure';
    await run({
      github,
      core,
      context: {
        repo: { owner: 'stranske', repo: 'Workflows' },
        payload: {},
        runId: 4,
        runNumber: 4,
        workflow: 'Maint 71',
        ref: 'refs/heads/main',
        sha: sourceCommit,
      },
    });
    const redReport = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    assert.equal(redReport.summary.checks_failed, 1);
    assert.match(failures.at(-1), /Canary evidence is incomplete or unsafe/);

    checkConclusion = 'success';
    requiredContexts = [];
    await run({
      github,
      core,
      context: {
        repo: { owner: 'stranske', repo: 'Workflows' },
        payload: {},
        runId: 5,
        runNumber: 5,
        workflow: 'Maint 71',
        ref: 'refs/heads/main',
        sha: sourceCommit,
      },
    });
    const unconfiguredReport = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    assert.equal(unconfiguredReport.summary.checks_failed, 1);
    assert.equal(
      unconfiguredReport.results[0].reason,
      'no_change_canary_required_checks_unconfigured',
    );
  } finally {
    process.chdir(originalCwd);
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('maint71 recovers exact-head evidence from an already-merged candidate PR', async () => {
  const originalCwd = process.cwd();
  const envKeys = [
    'REGISTERED_REPOS_INPUT',
    'CLEANUP_BRANCHES_INPUT',
    'DRY_RUN_INPUT',
    'AUTO_MERGE_INPUT',
    'EVIDENCE_ONLY_INPUT',
    'ACTIVE_SYNC_HASH_INPUT',
    'EXPECTED_PLAN_ID_INPUT',
    'EXPECTED_PLAN_SCOPE_INPUT',
    'EXPECTED_SCOPE_BASE_SHA_INPUT',
    'EXPECTED_SOURCE_COMMIT_INPUT',
    'OWNER_PR_PAT',
    'CONSUMER_SYNC_CANARIES_PATH',
    'TRUSTED_SYNC_ACTORS',
    'SYNC_PR_MERGE_REPORT_JSON',
  ];
  const originalEnv = Object.fromEntries(envKeys.map((key) => [key, process.env[key]]));
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-recovery-'));
  const reportPath = path.join(tempDir, 'artifacts', 'merge-report.json');
  const canaryConfigPath = path.join(tempDir, 'consumer-sync-canaries.json');
  fs.writeFileSync(
    canaryConfigPath,
    JSON.stringify({ canaries: [{ repo: 'stranske/Travel-Plan-Permission' }] }),
  );
  const marker = '<!-- workflows-consumer-sync:v1 {"schema":"workflows-consumer-sync-pr/v1","consumer_repo":"stranske/Travel-Plan-Permission","plan_id":"plan-abc","sync_phase":"canary"} -->';
  const delivery = '<!-- sync-pr-delivery-record:v1 {"schema":"sync-pr-delivery-record/v1","durable_issue_url":"https://github.com/stranske/Workflows/issues/1836","plan_id":"plan-abc","generation":"candidate-1","repository":"stranske/Travel-Plan-Permission","desired_tree_hash":"tree-abc","source_commit":"source-abc","lease_expires_at":"2099-08-14T00:00:00Z","predecessor_prs":[],"successor_prs":[]} -->';
  const mergedCandidate = {
    number: 1427,
    title: 'chore: sync workflow templates',
    body: `${marker}\n${delivery}`,
    created_at: '2026-08-11T05:22:39Z',
    updated_at: '2026-08-11T07:31:00Z',
    merged_at: '2026-08-11T07:31:00Z',
    base: { ref: 'main' },
    head: { ref: 'sync/workflows-candidate', sha: 'head-abc' },
    user: { login: 'stranske' },
  };
  const unrelatedOpenDelivery = {
    ...mergedCandidate,
    number: 1428,
    merged_at: null,
    head: { ref: 'deps/sync-dev-versions-other', sha: 'head-other' },
  };
  const github = {
    paginate: async (_method, params) => {
      if (params.state === 'open') return [unrelatedOpenDelivery];
      if (params.state === 'closed') return [mergedCandidate];
      if (params.ref === 'head-abc') {
        return [
          { name: 'Gate / gate', status: 'completed', conclusion: 'success' },
          {
            name: 'Record autofix dispatch completion',
            status: 'completed',
            conclusion: 'cancelled',
          },
          { name: 'Resolve Context', status: 'completed', conclusion: 'cancelled' },
        ];
      }
      return [];
    },
    graphql: async () => ({
      repository: {
        object: {
          signature: { isValid: true, state: 'VALID', wasSignedByGitHub: true },
        },
        pullRequest: {
          state: 'MERGED',
          mergedAt: mergedCandidate.merged_at,
          headRefOid: mergedCandidate.head.sha,
          body: mergedCandidate.body,
          createdAt: mergedCandidate.created_at,
          updatedAt: mergedCandidate.updated_at,
          reviewThreads: { pageInfo: { hasNextPage: false }, nodes: [] },
        },
      },
    }),
    rest: {
      pulls: {
        list: () => {},
        get: async () => ({ data: mergedCandidate }),
      },
      checks: { listForRef: () => {} },
      git: { getCommit: async () => ({ data: { tree: { sha: 'tree-abc' } } }) },
      repos: {
        getBranchProtection: async () => {
          const error = new Error('Resource not accessible by integration');
          error.status = 403;
          throw error;
        },
        getRepoRulesets: async () => ({
          data: [{ id: 7928264, name: 'Main', enforcement: 'active' }],
        }),
        getRepoRuleset: async () => ({
          data: {
            id: 7928264,
            enforcement: 'active',
            conditions: { ref_name: { include: ['~DEFAULT_BRANCH'], exclude: [] } },
            rules: [{
              type: 'required_status_checks',
              parameters: { required_status_checks: [{ context: 'Gate / gate' }] },
            }],
          },
        }),
        getCombinedStatusForRef: async () => ({ data: { statuses: [] } }),
        createDispatchEvent: async () => ({}),
      },
    },
  };
  const failures = [];
  const core = {
    addRaw: () => ({ write: async () => {} }),
    notice: () => {},
    setFailed: (message) => failures.push(message),
    warning: () => {},
    summary: { addRaw: () => ({ write: async () => {} }) },
  };

  try {
    process.chdir(tempDir);
    process.env.REGISTERED_REPOS_INPUT =
      'stranske/Travel-Plan-Permission,stranske/Collab-Admin';
    process.env.CLEANUP_BRANCHES_INPUT = 'false';
    process.env.DRY_RUN_INPUT = 'true';
    process.env.AUTO_MERGE_INPUT = 'false';
    process.env.ACTIVE_SYNC_HASH_INPUT = 'candidate';
    process.env.EXPECTED_PLAN_ID_INPUT = 'plan-abc';
    process.env.EXPECTED_PLAN_SCOPE_INPUT = 'full';
    process.env.EXPECTED_SCOPE_BASE_SHA_INPUT = '';
    process.env.EXPECTED_SOURCE_COMMIT_INPUT = 'source-abc';
    process.env.OWNER_PR_PAT = 'test-owner-token';
    process.env.EVIDENCE_ONLY_INPUT = 'true';
    process.env.CONSUMER_SYNC_CANARIES_PATH = canaryConfigPath;
    process.env.TRUSTED_SYNC_ACTORS = 'stranske';
    process.env.SYNC_PR_MERGE_REPORT_JSON = reportPath;

    await run({
      github,
      core,
      context: {
        repo: { owner: 'stranske', repo: 'Workflows' },
        payload: {},
        runId: 2,
        runNumber: 2,
        workflow: 'Maint 71',
        ref: 'refs/heads/main',
        sha: 'source-abc',
      },
    });

    const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    const evidence = JSON.parse(
      fs.readFileSync(path.join(tempDir, 'artifacts', 'sync-canary-evidence.json'), 'utf8'),
    );
    assert.equal(report.summary.evidence_recovered, 1);
    assert.deepEqual(report.inputs.repos, ['stranske/Travel-Plan-Permission']);
    assert.equal(evidence.results[0].pr, 1427);
    assert.equal(evidence.results[0].head_sha, 'head-abc');
    assert.equal(evidence.results[0].evidence_source, 'merged-candidate-recovery');
    assert.deepEqual(failures, []);
  } finally {
    process.chdir(originalCwd);
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('normalizeSyncHash accepts raw hashes and branch names', () => {
  assert.equal(normalizeSyncHash('5108b94a2435'), '5108b94a2435');
  assert.equal(normalizeSyncHash('sync/workflows-5108b94a2435'), '5108b94a2435');
  assert.equal(normalizeSyncHash('sync/workflows-candidate'), 'candidate');
  assert.equal(syncBranchForHash('5108b94a2435'), 'sync/workflows-5108b94a2435');
  assert.equal(syncBranchForHash('candidate'), 'sync/workflows-candidate');
});

test('selectLatestMergedCandidatePr recovers only the newest trusted merged candidate', () => {
  const candidate = (
    number,
    mergedAt,
    actor = 'stranske',
    planId = 'plan-current',
    sourceCommit = 'source-current',
  ) => ({
    ...pr(number, 'sync/workflows-candidate', '2026-08-11T01:00:00Z'),
    merged_at: mergedAt,
    head: { ref: 'sync/workflows-candidate', sha: `head-${number}` },
    user: { login: actor },
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify({
      schema: 'sync-pr-delivery-record/v1',
      durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
      plan_id: planId,
      generation: `candidate-${number}`,
      repository: 'stranske/Ready',
      desired_tree_hash: `tree-${number}`,
      source_commit: sourceCommit,
      lease_expires_at: '2099-08-14T00:00:00Z',
      predecessor_prs: [],
      successor_prs: [],
    })} -->`,
  });
  const selected = selectLatestMergedCandidatePr([
    candidate(1, '2026-08-11T02:00:00Z'),
    candidate(2, '2026-08-11T03:00:00Z'),
    candidate(3, '2026-08-11T04:00:00Z', 'untrusted'),
    candidate(5, '2026-08-11T05:00:00Z', 'stranske', 'plan-stale', 'source-stale'),
    { ...candidate(4, null), merged_at: null },
  ], ['stranske'], {
    planId: 'plan-current',
    sourceCommit: 'source-current',
  });

  assert.equal(selected.number, 2);
  assert.equal(selectLatestMergedCandidatePr([
    candidate(5, '2026-08-11T05:00:00Z', 'stranske', 'plan-stale', 'source-stale'),
  ], ['stranske'], {
    planId: 'plan-current',
    sourceCommit: 'source-current',
  }), null);
});

test('validateExpectedCandidateIdentity binds open candidates to every immutable input', () => {
  const expected = {
    expectedPlanId: 'plan-current',
    expectedPlanScope: 'source-delta',
    expectedScopeBaseSha: 'a'.repeat(40),
    expectedSourceCommit: 'b'.repeat(40),
    repository: 'stranske/Ready',
  };
  const metadata = {
    consumer_repo: 'stranske/Ready',
    plan_id: 'plan-current',
    plan_scope: 'source-delta',
    scope_base_sha: 'a'.repeat(40),
    source_sha: 'b'.repeat(40),
    source_commit: 'b'.repeat(40),
  };
  const deliveryRecord = {
    repository: 'stranske/Ready',
    plan_id: 'plan-current',
    source_commit: 'b'.repeat(40),
  };
  assert.deepEqual(validateExpectedCandidateIdentity({
    metadata,
    deliveryRecord,
    ...expected,
  }), { ok: true, errors: [] });

  const stale = validateExpectedCandidateIdentity({
    metadata: { ...metadata, source_commit: 'c'.repeat(40) },
    deliveryRecord: { ...deliveryRecord, plan_id: 'plan-stale' },
    ...expected,
  });
  assert.equal(stale.ok, false);
  assert.deepEqual(stale.errors, [
    'delivery_plan_id_mismatch',
    'metadata_source_commit_mismatch',
  ]);
});

test('validateCanaryEvidence fails closed on missing, mixed, red, or reviewed canaries', () => {
  const expected = ['stranske/A', 'stranske/B'];
  const valid = [
    { repo: 'stranske/A', plan_id: 'plan-1', required_check_state: 'success', active_review_thread_count: 0 },
    { repo: 'stranske/B', plan_id: 'plan-1', required_check_state: 'success', active_review_thread_count: 0 },
  ];
  assert.deepEqual(validateCanaryEvidence(valid, expected), {
    ok: true,
    errors: [],
    plan_id: 'plan-1',
    plan_scope: 'full',
    scope_base_sha: '',
    source_commit: '',
  });

  const invalid = validateCanaryEvidence([
    { ...valid[0], required_check_state: 'checks_failed' },
    { ...valid[1], plan_id: 'plan-2', active_review_thread_count: 1 },
  ], expected);
  assert.equal(invalid.ok, false);
  assert.ok(invalid.errors.includes('required_checks_not_green:stranske/A'));
  assert.ok(invalid.errors.includes('active_review_debt:stranske/B'));
  assert.ok(invalid.errors.includes('missing_or_mixed_canary_plan'));
});

test('validateCanaryEvidence preserves one immutable source-delta range', () => {
  const expected = ['stranske/A', 'stranske/B'];
  const base = '1'.repeat(40);
  const head = '2'.repeat(40);
  const valid = expected.map((repo) => ({
    repo,
    plan_id: 'plan-1',
    plan_scope: 'source-delta',
    scope_base_sha: base,
    source_commit: head,
    required_check_state: 'success',
    active_review_thread_count: 0,
  }));

  assert.deepEqual(validateCanaryEvidence(valid, expected), {
    ok: true,
    errors: [],
    plan_id: 'plan-1',
    plan_scope: 'source-delta',
    scope_base_sha: base,
    source_commit: head,
  });
  const mixed = validateCanaryEvidence(
    [valid[0], { ...valid[1], source_commit: '3'.repeat(40) }],
    expected,
  );
  assert.equal(mixed.ok, false);
  assert.ok(mixed.errors.includes('missing_or_mixed_canary_source_commit'));
  const missingBase = validateCanaryEvidence(
    [valid[0], { ...valid[1], scope_base_sha: '' }],
    expected,
  );
  assert.equal(missingBase.ok, false);
  assert.ok(missingBase.errors.includes('missing_or_mixed_canary_scope_base'));
  const missingSource = validateCanaryEvidence(
    [valid[0], { ...valid[1], source_commit: '' }],
    expected,
  );
  assert.equal(missingSource.ok, false);
  assert.ok(missingSource.errors.includes('missing_or_mixed_canary_source_commit'));
  const malformed = validateCanaryEvidence(
    valid.map((row) => ({ ...row, scope_base_sha: 'not-a-commit' })),
    expected,
  );
  assert.equal(malformed.ok, false);
  assert.ok(malformed.errors.includes('invalid_canary_scope_base'));
});

test('source-delta evidence is bound to the immutable generated commit message', () => {
  const planId = `sha256:${'a'.repeat(64)}`;
  const base = '1'.repeat(40);
  const head = '2'.repeat(40);
  const metadata = {
    plan_id: planId,
    plan_scope: 'source-delta',
    scope_base_sha: base,
    source_commit: head,
  };
  const deliveryRecord = { plan_id: planId, source_commit: head };
  const commitMessage = [
    'chore: sync workflow templates from Workflows repo',
    '',
    `Consumer-sync plan ID: ${planId}`,
    'Plan scope: source-delta',
    `Scope base SHA: ${base}`,
    `Source commit: ${head}`,
  ].join('\n');

  assert.deepEqual(
    validateSourceDeltaEvidenceBinding({ metadata, deliveryRecord, commitMessage }),
    { ok: true, errors: [] },
  );
  const tampered = validateSourceDeltaEvidenceBinding({
    metadata: { ...metadata, source_commit: '3'.repeat(40) },
    deliveryRecord,
    commitMessage,
  });
  assert.equal(tampered.ok, false);
  assert.ok(tampered.errors.includes('source_delta_commit_record_mismatch'));
  assert.ok(tampered.errors.includes('source_delta_source_commit_mismatch'));
});

test('parseBooleanInput preserves explicit false values', () => {
  assert.equal(parseBooleanInput('false', true), false);
  assert.equal(parseBooleanInput(false, true), false);
  assert.equal(parseBooleanInput('0', true), false);
  assert.equal(parseBooleanInput('', true), true);
  assert.equal(parseBooleanInput(undefined, false), false);
});

test('post-push review window fails closed until seven full minutes elapse', () => {
  const prState = {
    created_at: '2026-08-11T13:00:00Z',
    updated_at: '2026-08-11T13:02:00Z',
  };
  assert.deepEqual(
    evaluatePostPushReviewWindow(prState, '2026-08-11T13:08:59Z'),
    {
      ready: false,
      reason: 'review_window_pending',
      anchor_at: '2026-08-11T13:02:00.000Z',
      eligible_at: '2026-08-11T13:09:00.000Z',
    },
  );
  assert.equal(
    evaluatePostPushReviewWindow(prState, '2026-08-11T13:09:00Z').ready,
    true,
  );
  assert.equal(evaluatePostPushReviewWindow({}, '2026-08-11T13:09:00Z').ready, false);

  const exactHeadWithLaterReviewActivity = evaluatePostPushReviewWindow({
    head: {
      sha: 'head-abc',
      observed_sha: 'head-abc',
      observed_at: '2026-08-11T12:00:00Z',
    },
    updated_at: '2026-08-11T13:08:00Z',
  }, '2026-08-11T12:07:00Z');
  assert.equal(exactHeadWithLaterReviewActivity.ready, true);
  assert.equal(exactHeadWithLaterReviewActivity.anchor_at, '2026-08-11T12:00:00.000Z');

  const mismatchedHeadObservation = evaluatePostPushReviewWindow({
    head: {
      sha: 'head-new',
      observed_sha: 'head-old',
      observed_at: '2026-08-11T12:00:00Z',
    },
    updated_at: '2026-08-11T13:08:00Z',
  }, '2026-08-11T13:14:59Z');
  assert.equal(mismatchedHeadObservation.ready, false);
  assert.equal(mismatchedHeadObservation.anchor_at, '2026-08-11T13:08:00.000Z');
});

test('reviewer settlement never requires every configured reviewer', () => {
  const base = {
    reviewStartedAt: '2026-08-11T13:00:00Z',
    configuredReviewers: ['copilot', 'codex', 'coderabbit'],
    minimumResponses: 1,
    quietPeriodMs: 7 * 60 * 1000,
    maxWaitMs: 15 * 60 * 1000,
  };
  assert.equal(evaluateReviewerSettlement({
    ...base,
    now: '2026-08-11T13:08:00Z',
    respondedReviewers: ['copilot'],
  }).reason, 'review_quorum_met');
  assert.equal(evaluateReviewerSettlement({
    ...base,
    now: '2026-08-11T13:08:00Z',
    unavailableReviewers: ['copilot', 'codex', 'coderabbit'],
  }).reason, 'review_capacity_degraded');
  assert.equal(evaluateReviewerSettlement({
    ...base,
    now: '2026-08-11T13:16:00Z',
  }).reason, 'review_timeout_degraded');
  assert.equal(evaluateReviewerSettlement({
    ...base,
    now: '2026-08-11T13:06:59Z',
    respondedReviewers: ['copilot'],
  }).ready, false);
  assert.deepEqual(evaluateReviewerSettlement({
    ...base,
    now: '2026-08-11T13:08:00Z',
  }), {
    ready: false,
    reason: 'review_quorum_pending',
    eligible_at: '2026-08-11T13:15:00.000Z',
    responded: [],
    unavailable: [],
  });
  assert.equal(evaluateReviewerSettlement({
    ...base,
    now: '2026-08-11T13:08:00Z',
    quietPeriodMs: Number.NaN,
    maxWaitMs: Number.NaN,
    minimumResponses: Number.NaN,
  }).reason, 'review_quorum_pending');
  assert.equal(
    isReviewerCapacitySignal('Reviewer unavailable: quota exceeded', ['reviewer unavailable']),
    true,
  );
  assert.equal(
    isReviewerCapacitySignal('Review rate-limit exceeded', ['review rate-limit exceeded']),
    true,
  );
  assert.equal(isReviewerCapacitySignal('Please add rate-limit handling.', ['review rate-limit']), false);
  assert.equal(isReviewerNonResponseSignal('Review skipped: excluded by label', ['review skipped']), true);
});

test('review policy normalizes invalid numeric values to finite defaults', () => {
  const policy = normalizeReviewPolicy({
    minimum_responses: 'invalid',
    quiet_period_minutes: Number.NaN,
    maximum_wait_minutes: -1,
    reviewers: 'invalid',
    capacity_patterns: null,
  });
  assert.equal(policy.minimum_responses, 1);
  assert.equal(policy.quiet_period_minutes, 7);
  assert.equal(policy.maximum_wait_minutes, 15);
  assert.deepEqual(policy.reviewers, []);
  assert.deepEqual(policy.capacity_patterns, []);
  assert.deepEqual(policy.non_response_patterns, []);
});

test('reviewer evidence query retries and fails closed when GraphQL is unavailable', async () => {
  const warnings = [];
  let retryCalls = 0;
  const result = await collectReviewerEvidence({
    owner: 'stranske',
    repo: 'Ready',
    number: 99,
    reviewStartedAt: '2026-08-11T13:00:00Z',
    withRetry: async (operation) => {
      retryCalls += 1;
      return operation({
        graphql: async () => {
          throw new Error('rate limited');
        },
      });
    },
    core: { warning: (message) => warnings.push(message) },
  });
  assert.equal(retryCalls, 1);
  assert.deepEqual(result, { responded: [], unavailable: [], truncated: true });
  assert.match(warnings[0], /Unable to read reviewer evidence/);
});

test('legacy reviewer status preserves its timestamp and satisfies reviewer evidence', async () => {
  const check = legacyStatusAsCheck({
    context: 'CodeRabbit',
    state: 'success',
    created_at: '2026-08-11T13:07:30Z',
    updated_at: '2026-08-11T13:08:00Z',
  });
  assert.deepEqual(check, {
    name: 'CodeRabbit',
    status: 'completed',
    conclusion: 'success',
    completed_at: '2026-08-11T13:08:00Z',
    summary: '',
  });

  const evidence = await collectReviewerEvidence({
    owner: 'stranske',
    repo: 'Ready',
    number: 99,
    reviewStartedAt: '2026-08-11T13:07:00Z',
    checkRuns: [check],
    reviewerProfiles: [{ id: 'coderabbit', check_names: ['CodeRabbit'] }],
    withRetry: async (operation) => operation({
      graphql: async () => ({
        repository: {
          pullRequest: {
            comments: { nodes: [], pageInfo: { hasNextPage: false } },
            reviews: { nodes: [], pageInfo: { hasNextPage: false } },
            reviewThreads: { nodes: [], pageInfo: { hasNextPage: false } },
          },
        },
      }),
    }),
    core: { warning: () => {} },
  });
  assert.deepEqual(evidence, {
    responded: ['coderabbit'],
    unavailable: [],
    truncated: false,
  });
});

test('reviewer evidence does not count explicit skipped-review status as a response', async () => {
  const check = legacyStatusAsCheck({
    context: 'CodeRabbit',
    state: 'success',
    description: 'Review skipped: excluded by label configuration',
    updated_at: '2026-08-11T13:08:00Z',
  });
  const evidence = await collectReviewerEvidence({
    owner: 'stranske',
    repo: 'Ready',
    number: 99,
    reviewStartedAt: '2026-08-11T13:07:00Z',
    checkRuns: [check],
    reviewerProfiles: [{ id: 'coderabbit', check_names: ['CodeRabbit'] }],
    reviewerNonResponsePatterns: ['review skipped', 'excluded by label'],
    withRetry: async (operation) => operation({
      graphql: async () => ({
        repository: {
          pullRequest: {
            comments: { nodes: [], pageInfo: { hasNextPage: false } },
            reviews: { nodes: [], pageInfo: { hasNextPage: false } },
            reviewThreads: { nodes: [], pageInfo: { hasNextPage: false } },
          },
        },
      }),
    }),
    core: { warning: () => {} },
  });
  assert.deepEqual(evidence, {
    responded: [],
    unavailable: ['coderabbit'],
    truncated: false,
  });
});

test('reviewer evidence counts a completed negative verdict with substantive output', async () => {
  const evidence = await collectReviewerEvidence({
    owner: 'stranske',
    repo: 'Ready',
    number: 99,
    reviewStartedAt: '2026-08-11T13:07:00Z',
    checkRuns: [{
      name: 'CodeRabbit',
      status: 'completed',
      conclusion: 'failure',
      completed_at: '2026-08-11T13:08:00Z',
      output: { summary: 'Found a blocking workflow regression.' },
    }],
    reviewerProfiles: [{ id: 'coderabbit', check_names: ['CodeRabbit'] }],
    reviewerNonResponsePatterns: ['review skipped'],
    withRetry: async (operation) => operation({
      graphql: async () => ({
        repository: {
          pullRequest: {
            comments: { nodes: [], pageInfo: { hasNextPage: false } },
            reviews: { nodes: [], pageInfo: { hasNextPage: false } },
            reviewThreads: { nodes: [], pageInfo: { hasNextPage: false } },
          },
        },
      }),
    }),
    core: { warning: () => {} },
  });
  assert.deepEqual(evidence, {
    responded: ['coderabbit'],
    unavailable: [],
    truncated: false,
  });
});

test('reviewer evidence preserves a response across a later capacity signal', async () => {
  const evidence = await collectReviewerEvidence({
    owner: 'stranske',
    repo: 'Ready',
    number: 99,
    reviewStartedAt: '2026-08-11T13:07:00Z',
    checkRuns: [{
      name: 'CodeRabbit',
      status: 'completed',
      conclusion: 'success',
      completed_at: '2026-08-11T13:09:00Z',
      summary: 'Review skipped because the reviewer quota is exhausted.',
    }],
    reviewerProfiles: [{
      id: 'coderabbit',
      logins: ['coderabbitai'],
      check_names: ['CodeRabbit'],
    }],
    reviewerCapacityPatterns: ['quota'],
    reviewerNonResponsePatterns: ['review skipped'],
    withRetry: async (operation) => operation({
      graphql: async () => ({
        repository: {
          pullRequest: {
            comments: {
              nodes: [{
                body: 'Reviewed the delivery and found no actionable problems.',
                createdAt: '2026-08-11T13:08:00Z',
                author: { login: 'coderabbitai' },
              }],
              pageInfo: { hasNextPage: false },
            },
            reviews: { nodes: [], pageInfo: { hasNextPage: false } },
            reviewThreads: { nodes: [], pageInfo: { hasNextPage: false } },
          },
        },
      }),
    }),
    core: { warning: () => {} },
  });
  assert.deepEqual(evidence, {
    responded: ['coderabbit'],
    unavailable: [],
    truncated: false,
  });
});

test('review non-response policy does not match generic feature availability prose', () => {
  const policy = JSON.parse(fs.readFileSync(
    path.join(__dirname, '../../../config/consumer_sync_review_policy.json'),
    'utf8',
  ));
  assert.equal(
    isReviewerNonResponseSignal(
      'The optional test feature is not enabled in this repository.',
      policy.non_response_patterns,
    ),
    false,
  );
  assert.equal(
    isReviewerNonResponseSignal('Automated review is disabled.', policy.non_response_patterns),
    false,
  );
  assert.equal(
    isReviewerNonResponseSignal('Review is disabled for this repository.', policy.non_response_patterns),
    true,
  );
  assert.equal(
    isReviewerNonResponseSignal(
      'This migration was not reviewed for backward compatibility, so add coverage.',
      policy.non_response_patterns,
    ),
    false,
  );
  assert.equal(
    isReviewerNonResponseSignal(
      '### Review skipped: excluded by label configuration',
      policy.non_response_patterns,
    ),
    true,
  );
  assert.equal(
    isReviewerNonResponseSignal(
      'Review was not performed due to repository settings.',
      policy.non_response_patterns,
    ),
    true,
  );
  assert.equal(
    isReviewerCapacitySignal('Review rate limited', policy.capacity_patterns),
    true,
  );
  assert.equal(
    isReviewerCapacitySignal(
      'Found a quota accounting regression; add coverage before merge.',
      policy.capacity_patterns,
    ),
    false,
  );
});

test('a sync selector ignores dev-tool deliveries instead of reporting a missing sync target', () => {
  const generated = [
    pr(1, 'deps/sync-dev-versions-wave', '2026-08-11T13:00:00Z'),
    pr(2, 'sync/workflows-delivery', '2026-08-11T13:01:00Z'),
  ];
  assert.deepEqual(
    generatedPrsForSyncSelector(generated, 'delivery').map((item) => item.number),
    [2],
  );
  assert.deepEqual(generatedPrsForSyncSelector(generated.slice(0, 1), 'delivery'), []);
  assert.equal(generatedPrsForSyncSelector(generated).length, 2);
});

test('the dev-tool selector cannot be hidden by a newer workflow-sync PR', () => {
  const devTool = pr(1, 'deps/sync-dev-versions-wave', '2026-08-15T00:00:00Z');
  const candidate = pr(2, 'sync/workflows-candidate', '2026-08-15T01:00:00Z');
  assert.deepEqual(generatedPrsForSyncSelector([devTool, candidate], 'dev-tool'), [devTool]);
  const selection = selectActiveSyncPr([devTool, candidate], 'dev-tool');
  assert.equal(selection.active.number, 1);
  assert.equal(selection.missingExpected, false);
});

test('stable delivery branches and strict branch-update failures are recognized', () => {
  assert.equal(isStableSyncBranchName('sync/workflows-candidate'), true);
  assert.equal(isStableSyncBranchName('sync/workflows-delivery'), true);
  assert.equal(isStableSyncBranchName('sync/workflows-deadbeef'), false);
  assert.equal(requiresStrictGateBranchUpdate({
    pr: { mergeable_state: 'behind' },
    requiredContexts: new Set(['Gate / gate']),
    willMerge: true,
  }), true);
  assert.equal(isBlockingSyncSystemFailure('pr_refresh_failed'), true);
  assert.equal(isBlockingSyncSystemFailure('head_commit_unverified'), true);
  assert.equal(isBlockingSyncSystemFailure('delivery_promotion_evidence_missing'), true);
});

test('workflow sync delivery merge requires a valid cryptographic signature', () => {
  assert.equal(commitSignatureAllowsMerge({
    isValid: true,
    state: 'VALID',
    wasSignedByGitHub: true,
  }), true);
  assert.equal(commitSignatureAllowsMerge({
    isValid: false,
    state: 'UNSIGNED',
    wasSignedByGitHub: false,
  }), false);
  assert.equal(commitSignatureAllowsMerge({
    isValid: true,
    state: 'VALID',
    wasSignedByGitHub: false,
  }), true);
});

test('only the workflow-sync lane requires a verified generated head', () => {
  assert.equal(generatedDeliveryRequiresVerifiedHead('sync/workflows-candidate'), true);
  assert.equal(generatedDeliveryRequiresVerifiedHead('sync/workflows-delivery'), true);
  assert.equal(generatedDeliveryRequiresVerifiedHead('deps/sync-dev-versions-20260811'), false);
  assert.equal(generatedDeliveryRequiresVerifiedHead('feature/manual-change'), false);
});

test('strict required checks update behind branches before a generated merge', () => {
  assert.equal(requiresStrictGateBranchUpdate({
    pr: { mergeable_state: 'behind' },
    requiredContexts: new Set(['Gate / gate']),
    willMerge: true,
  }), true);
  assert.equal(requiresStrictGateBranchUpdate({
    pr: { mergeable_state: 'clean' },
    requiredContexts: ['Gate / gate'],
    willMerge: true,
  }), false);
  assert.equal(requiresStrictGateBranchUpdate({
    pr: { mergeable_state: 'behind' },
    requiredContexts: [],
    willMerge: true,
  }), false);
  assert.equal(requiresStrictGateBranchUpdate({
    pr: { mergeable_state: 'behind' },
    requiredContexts: ['Gate / gate'],
    willMerge: false,
  }), false);
});

test('branch-update failures are blocking sync-system failures', () => {
  for (const status of [
    'branch_update_failed',
    'error',
    'merge_failed',
    'pr_refresh_failed',
    'stale_close_failed',
    'target_missing',
  ]) {
    assert.equal(isBlockingSyncSystemFailure(status), true);
  }
  assert.equal(isBlockingSyncSystemFailure('checks_failed'), false);
});

test('candidate mutation requires the evidence pass authorization', () => {
  assert.equal(candidateEvidenceAllowsMutation({
    branch: 'sync/workflows-candidate',
    evidenceOnly: false,
    authorized: false,
  }), false);
  assert.equal(candidateEvidenceAllowsMutation({
    branch: 'sync/workflows-candidate',
    evidenceOnly: true,
    authorized: false,
  }), true);
  assert.equal(candidateEvidenceAllowsMutation({
    branch: 'sync/workflows-candidate',
    evidenceOnly: false,
    authorized: true,
  }), true);
  assert.equal(candidateEvidenceAllowsMutation({
    branch: 'sync/workflows-deadbeef',
    evidenceOnly: false,
    authorized: false,
  }), true);
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
    assert.equal(
      classifyGeneratedPr({
        pr: candidate,
        checkState: { status: 'checks_failed', failure_scope: 'shared-source' },
        now: '2026-08-01T00:00:00Z',
      }).disposition,
      'shared-source-failure',
    );
  }

  const sharedHealth = classifySyncPrChecks({
    checkRuns: [checkRun({ name: 'Health 40 Sweep', conclusion: 'failure' })],
    requiredContexts: ['Health 40 Sweep'],
  });
  assert.equal(sharedHealth.status, 'checks_failed');
  assert.equal(sharedHealth.failure_scope, 'shared-source');
  assert.equal(
    classifyGeneratedPr({ pr: sync, checkState: sharedHealth, now: '2026-08-01T00:00:00Z' }).disposition,
    'shared-source-failure',
  );

  const aggregateGate = classifySyncPrChecks({
    checkRuns: [checkRun({ name: 'Gate / gate', conclusion: 'failure' })],
    requiredContexts: ['Gate / gate'],
  });
  assert.equal(aggregateGate.failure_scope, 'repo-local');

  const localWorkflowCheck = classifySyncPrChecks({
    checkRuns: [checkRun({ name: 'workflow integration tests', conclusion: 'failure' })],
    requiredContexts: ['workflow integration tests'],
  });
  assert.equal(localWorkflowCheck.failure_scope, 'repo-local');

  const explicitlyShared = classifySyncPrChecks({
    checkRuns: [{ ...checkRun({ name: 'Gate / gate', conclusion: 'failure' }), shared_source: true }],
    requiredContexts: ['Gate / gate'],
  });
  assert.equal(explicitlyShared.failure_scope, 'shared-source');

  const localFail = classifySyncPrChecks({
    checkRuns: [checkRun({ name: 'unit-tests', conclusion: 'failure' })],
    requiredContexts: ['unit-tests'],
  });
  assert.equal(localFail.failure_scope, 'repo-local');
  assert.equal(
    classifyGeneratedPr({ pr: sync, checkState: localFail, now: '2026-08-01T00:00:00Z' }).disposition,
    'repo-local-failure',
  );
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

test('selectActiveSyncPr can target the stable canary candidate branch', () => {
  const selection = selectActiveSyncPr(
    [
      pr(1, 'sync/workflows-candidate', '2026-04-25T01:00:00Z'),
      pr(2, 'sync/workflows-old-wave', '2026-04-25T02:00:00Z'),
    ],
    'candidate',
  );

  assert.equal(selection.active.number, 1);
  assert.equal(selection.expectedBranch, 'sync/workflows-candidate');
  assert.deepEqual(selection.stale.map((item) => item.number), [2]);
});

test('selectActiveSyncPr never marks another generated-delivery lane stale', () => {
  const selection = selectActiveSyncPr(
    [
      pr(1, 'sync/workflows-candidate', '2026-04-25T01:00:00Z'),
      pr(2, 'sync/workflows-old-wave', '2026-04-25T02:00:00Z'),
      pr(3, 'deps/sync-dev-versions-wave', '2026-04-25T03:00:00Z'),
    ],
    'candidate',
  );

  assert.equal(selection.active.number, 1);
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
    candidate_evidence_required: 0,
    review_window_pending: 0,
    review_window_started: 0,
    reviewer_settlement_pending: 0,
    delivery_review_not_started: 0,
    delivery_sealed_checks_pending: 0,
    delivery_promotion_evidence_missing: 0,
    sealed_head_mismatch: 0,
    stable_base_refresh_required: 0,
    head_changed: 0,
    head_commit_unverified: 0,
    review_blocked: 0,
    ready: 0,
    dry_run_merge: 1,
    dry_run_review_start: 0,
    dry_run_seal: 0,
    merge_blocked_runtime_ac: 0,
    merged: 0,
    merge_failed: 0,
    delivery_contract_blocked: 0,
    evidence_recovered: 0,
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
  }, '2026-08-15T12:00:00Z'), {
    schema: 'workflows-generated-delivery-handoff/v1', repository: 'stranske/Ready', pr: 11,
    branch: 'deps/sync-dev-versions-20260801', head_sha: 'abc', delivery_generation: 'g2',
    lane: 'dev-tool-sync', disposition: 'review-blocked', blocker_owner: 'closer',
    next_command: 'resolve-active-review-threads',
    check_state: 'ready', review_state: 'blocked',
    continuation: {
      class: 'actionable', lane: 'dev-tool', reason: 'review_blocked', resume_after: '',
    },
    observed_at: '2026-08-15T12:00:00Z',
  });
});

test('buildDeliveryHandoff rewrites terminal merge outcomes', () => {
  assert.deepEqual(buildDeliveryHandoff({
    owner: 'stranske', repo: 'Ready', pr: 11, branch: 'sync/workflows-abc',
    head_sha: 'abc', delivery_generation: 'g2', delivery_disposition: 'current',
    blocker_owner: 'maint-71', next_command: 'merge-current-delivery',
    status: 'merged',
  }, '2026-08-15T12:00:00Z'), {
    schema: 'workflows-generated-delivery-handoff/v1', repository: 'stranske/Ready', pr: 11,
    branch: 'sync/workflows-abc', head_sha: 'abc', delivery_generation: 'g2',
    lane: 'sync', disposition: 'merged', blocker_owner: 'none', next_command: 'none',
    check_state: 'ready', review_state: 'clear',
    continuation: { class: 'terminal', lane: '', reason: 'merged', resume_after: '' },
    observed_at: '2026-08-15T12:00:00Z',
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

test('requiredContextsFromRulesets selects active rules for the target branch', () => {
  const rulesets = [
    {
      enforcement: 'active',
      conditions: { ref_name: { include: ['~DEFAULT_BRANCH'], exclude: [] } },
      rules: [{
        type: 'required_status_checks',
        parameters: { required_status_checks: [{ context: 'Gate / gate' }] },
      }],
    },
    {
      enforcement: 'active',
      conditions: { ref_name: { include: ['refs/heads/release/*'], exclude: [] } },
      rules: [{
        type: 'required_status_checks',
        parameters: { required_status_checks: [{ context: 'release gate' }] },
      }],
    },
    {
      enforcement: 'evaluate',
      conditions: { ref_name: { include: ['~ALL'], exclude: [] } },
      rules: [{
        type: 'required_status_checks',
        parameters: { required_status_checks: [{ context: 'advisory' }] },
      }],
    },
  ];

  assert.equal(rulesetRefPatternMatches('refs/heads/release/*', 'main'), false);
  assert.deepEqual([...requiredContextsFromRulesets(rulesets, 'main')], ['Gate / gate']);
  assert.deepEqual([...requiredContextsFromRulesets([], 'main')], []);
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
