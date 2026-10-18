'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const deliveryPayload = require('../consumer_delivery_digest');
test.beforeEach(t => t.mock.method(deliveryPayload, 'readDeliveryPayload', async (sha, repos) => ({
  digest: `sha256:${sha[0].repeat(64)}`,
  files: Object.fromEntries(repos.map(repo => [repo, { 'scripts/shared.js': { content: sha[0] } }])),
})));

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const legacyPolicyDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-legacy-policy-'));
const legacyPolicyPath = path.join(legacyPolicyDir, 'policy.json');
const legacyPolicy = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../config/consumer_sync_review_policy.json'), 'utf8'));
delete legacyPolicy.generated_delivery_review;
fs.writeFileSync(legacyPolicyPath, JSON.stringify(legacyPolicy));
const originalPolicyPath = process.env.CONSUMER_SYNC_REVIEW_POLICY_PATH;
process.env.CONSUMER_SYNC_REVIEW_POLICY_PATH = legacyPolicyPath;
test.after(() => {
  if (originalPolicyPath === undefined) delete process.env.CONSUMER_SYNC_REVIEW_POLICY_PATH;
  else process.env.CONSUMER_SYNC_REVIEW_POLICY_PATH = originalPolicyPath;
  fs.rmSync(legacyPolicyDir, { recursive: true, force: true });
});
const {
  devToolBaseRefreshResult, ensureExactHeadReviewRequest, hasCompleteReviewThreadEvidence,
  parseReviewReassessmentRequest, runReviewReassessment, run, acceptanceCommentLocation,
  canaryNeedsRefresh, refreshStableCanaries, STALE_CANARY_HOURS,
  CANARY_REFRESH_DEBOUNCE_MS, CANARY_SEALED_REFRESH_WAIT_MS, deferSealedCanaryRefresh, canaryRefreshDecision, readCanaryRefreshState,
  dispatchCanaryRefresh, dispatchCanaryPromotion,
  isExpectedPresealGateFailure, legacyStatusAsCheck, requestSealedGate,
} = require('../maint71_merge_sync_prs');
const { classifySyncPrChecks } = require('../sync_pr_merge_contract');

const refreshNow = Date.parse('2026-10-17T12:00:00Z');

function sealedGateHarness(t) {
  const pr = { number: 4104, head: { ref: 'sync/workflows-candidate', sha: 'd'.repeat(40) } };
  const sealedAt = '2026-10-17T11:00:00Z';
  const run = { id: 4105, head_branch: pr.head.ref, head_sha: pr.head.sha,
    event: 'pull_request', status: 'completed', conclusion: 'failure',
    run_attempt: 1, created_at: sealedAt, run_started_at: sealedAt };
  const reads = [], reruns = [], dispatches = [], logs = [];
  const state = { runs: [run] };
  t.mock.timers.enable({ apis: ['Date'], now: refreshNow });
  t.mock.method(console, 'log', (...args) => logs.push(args.join(' ')));
  const withRetry = async callback => callback({ rest: { actions: {
    listWorkflowRuns: async params => {
      reads.push(params);
      if (state.lookupError) throw Object.assign(new Error('history denied'), { status: 403 });
      return { data: { workflow_runs: params.event === 'pull_request' ? state.runs
        : dispatches.length ? [{ ...run, event: 'workflow_dispatch', status: 'queued', created_at: new Date().toISOString() }] : [] } };
    },
    reRunWorkflowFailedJobs: async params => {
      reruns.push(params);
      if (state.rerunError) throw Object.assign(new Error('rerun denied'), { status: state.rerunError });
      return { status: 201 };
    },
    createWorkflowDispatch: async params => { dispatches.push(params); return { status: 204 }; },
  } } });
  return { args: { owner: 'stranske', repo: 'Ready', pr, sealedAt, withRetry },
    state, run, reads, reruns, dispatches, logs };
}

for (const branch of ['sync/workflows-candidate', 'sync/workflows-delivery']) {
  test(`sealed ${branch} reruns latest exact-head PR Gate once, including equality`, async t => {
    const api = sealedGateHarness(t);
    api.args.pr.head.ref = branch;
    api.state.runs = [{ ...api.run, id: 9999, head_sha: 'e'.repeat(40) },
      { ...api.run, id: 9998, event: 'workflow_dispatch' }, { ...api.run, id: 4000 }, api.run];
    assert.deepEqual(await requestSealedGate(api.args), { mode: 'rerun', status: 201, run_id: 4105 });
    assert.deepEqual(api.reruns, [{ owner: 'stranske', repo: 'Ready', run_id: 4105 }]);
    assert.ok(api.logs.includes('seal: stranske/Ready#4104 gate rerun run=4105'));
    for (const status of ['queued', 'in_progress', 'completed']) {
      api.state.runs = [{ ...api.run, run_attempt: 2, status,
        conclusion: status === 'completed' ? 'success' : null }];
      assert.deepEqual(await requestSealedGate(api.args), { mode: 'existing', run_id: 4105 });
    }
    assert.equal(api.reruns.length, 1);
    assert.equal(api.dispatches.length, 0);
  });
}

for (const status of [403, 404]) {
  test(`rerun HTTP ${status} is printed and never dispatches`, async t => {
    const api = sealedGateHarness(t);
    api.state.rerunError = status;
    assert.deepEqual(await requestSealedGate(api.args), { mode: 'failed', status, reason: 'rerun denied' });
    assert.ok(api.logs.includes(`seal: stranske/Ready#4104 gate request failed: ${status} rerun denied`));
    assert.equal(api.dispatches.length, 0);
  });
}

test('missing PR Gate uses dispatch fallback; unreadable history fails closed', async t => {
  const api = sealedGateHarness(t);
  api.state.lookupError = true;
  assert.equal((await requestSealedGate(api.args)).mode, 'failed');
  assert.equal(api.dispatches.length, 0);
  api.state.lookupError = false;
  api.state.runs = [];
  assert.deepEqual(await requestSealedGate(api.args), { mode: 'dispatch', status: 204, run_id: 4105 });
  assert.ok(api.logs.includes('seal: stranske/Ready#4104 gate dispatch fallback'));
  assert.deepEqual(await requestSealedGate(api.args), { mode: 'existing', run_id: 4105 });
  assert.equal(api.dispatches.length, 1);
});

function refreshCanary(overrides = {}) {
  return { owner: 'stranske', repo: 'Ready', pr: 12, plan_id: 'plan-4026',
    source_commit: 'a'.repeat(40), base_sha: 'b'.repeat(40), default_branch_tip_sha: 'b'.repeat(40), head_sha: 'c'.repeat(40),
    check_status: 'success', active_review_thread_count: 0,
    head_observed_at: new Date(refreshNow - 60 * 60 * 1000).toISOString(),
    ...overrides };
}

function refreshHarness(overrides = {}) {
  const dispatches = [], comments = [], summaries = [], failures = [], reads = [];
  const manifestEntries = require('../sync_pr_merge_contract').parseManifestSyncedSourceEntries(`
scripts:
  - source: .github/scripts/shared.js
    target: scripts/shared.js
workflows:
  - source: .github/workflows/gate.yml
    target: .github/workflows/consumer-gate.yml
`);
  const github = { rest: {
    pulls: { list: async () => ({ data: [] }) },
    users: { getAuthenticated: async () => ({ data: { login: 'maint71-bot' } }) },
    actions: {
      listWorkflowRuns: async () => ({ data: { workflow_runs: [] } }),
      createWorkflowDispatch: async (params) => dispatches.push(params),
      ...overrides.actions,
    },
    repos: {
      get: async () => ({ data: { default_branch: 'trunk' } }),
      getBranch: async () => ({ data: { commit: { sha: 'b'.repeat(40) } } }),
      ...overrides.repos,
      getCommit: async () => ({ data: { sha: 'a'.repeat(40) } }),
      getContent: async () => ({ data: { content: Buffer.from(JSON.stringify({
        canaries: ['stranske/Ready', 'stranske/Template'].map((repo) => ({ repo })),
      })).toString('base64') } }),
      listCommits: async (params) => { reads.push(params); return { data: [{ sha: 'a'.repeat(40) }] }; },
      listPullRequestsAssociatedWithCommit: () => {},
      listCommentsForCommit: () => {},
      createCommitComment: async (params) => comments.push({ ...params, user: { login: 'maint71-bot' } }),
    },
    issues: { listComments: () => {}, createComment: async (params) => comments.push({ ...params, user: { login: 'maint71-bot' } }) },
  }, paginate: async (method) => {
    if (method === github.rest.repos.listPullRequestsAssociatedWithCommit) {
      return overrides.prs ?? [{ number: 4020, merged_at: '2026-10-16T10:00:00Z',
        base: { repo: { full_name: 'stranske/Workflows' } } }];
    }
    return [...comments, ...(overrides.existing || [])];
  } };
  const core = { notice() {}, setFailed: (message) => failures.push(message),
    summary: { addRaw(text) { summaries.push(text); return this; }, async write() {} } };
  return { dispatches, comments, summaries, failures, reads, manifestEntries, core,
    withRetry: async (fn) => fn(github), enabled: true, now: refreshNow,
    expectedCanaries: ['stranske/Ready', 'stranske/Template'],
    context: { repo: { owner: 'stranske', repo: 'Workflows' },
      payload: { repository: { default_branch: 'main' } } } };
}

for (const [state, change] of [
  ['behind', { mergeable_state: 'behind' }],
  ['checks_failed', { check_status: 'checks_failed' }],
  ['review_blocked', { active_review_thread_count: 1 }],
  ['stale', { mergeable_state: 'dirty', head_observed_at: '2026-10-17T05:00:00Z' }],
]) {
  test(`stable canary ${state} refreshes once per plan with the right reason`, async () => {
    const api = refreshHarness();
    const canary = refreshCanary(change);
    assert.equal(canaryNeedsRefresh(canary, refreshNow), state, `missing refresh state: ${state}`);
    const result = await refreshStableCanaries({ ...api,
      canaries: [canary, { ...canary, repo: 'Template' }] });
    assert.equal(result.refresh_dispatched, 1, `missing refresh dispatch: ${state}`);
    assert.equal(api.dispatches.length, 1, state);
    assert.deepEqual(result.canaries.map((row) => row.refresh_reason), [state, state]);
    assert.deepEqual(api.dispatches[0], { owner: 'stranske', repo: 'Workflows',
      workflow_id: 'maint-68-sync-consumer-repos.yml', ref: 'main',
      inputs: { phase: 'canary', delivery_scope: 'full', scope_head_sha: 'a'.repeat(40),
        repos: 'stranske/Ready,stranske/Template', dry_run: 'false', force: 'false',
        ...(state === 'behind' ? { refresh_key: require('crypto').createHash('sha256')
          .update(`stranske/Ready:${canary.default_branch_tip_sha}:${canary.head_sha}`).digest('hex') } : {}) } });
    assert.match(api.summaries.join(''), /refresh_dispatched=1 held_plan=plan-4026/);
    assert.deepEqual(api.failures, []);
  });
}

test('all current green canaries and an empty run emit zero counts without dispatch', async () => {
  for (const canaries of [[], [refreshCanary(), refreshCanary({ repo: 'Template' })]]) {
    const api = refreshHarness();
    await refreshStableCanaries({ ...api, canaries });
    assert.equal(api.dispatches.length, 0);
    assert.ok(api.summaries.includes(
      'canaries: red=0 review_blocked=0 stale=0 refresh_dispatched=0 held_plan=none drainable=0\n'));
  }
});

test('staleness uses producer head age, with a strict six-hour boundary', () => {
  assert.equal(STALE_CANARY_HOURS, 6);
  const atBoundary = refreshCanary({ mergeable_state: 'dirty', head_observed_at: new Date(refreshNow - 6 * 3600000).toISOString() });
  assert.equal(canaryNeedsRefresh(atBoundary, refreshNow), null);
  assert.equal(canaryNeedsRefresh(atBoundary, refreshNow + 1), 'stale');
  assert.equal(canaryNeedsRefresh({ ...atBoundary, updated_at: new Date(refreshNow).toISOString() },
    refreshNow + 1), 'stale');
  assert.equal(canaryNeedsRefresh(refreshCanary({ head_observed_at: 'invalid' }), refreshNow), null);
});

test('canary refresh reasons prioritize blockers over age and retain legacy timestamp fallbacks', () => {
  const blocked = refreshCanary({ mergeable_state: 'behind', base_sha: 'b'.repeat(40), default_branch_tip_sha: 'b'.repeat(40), head_sha: 'c'.repeat(40), check_status: 'checks_failed',
    active_review_thread_count: 1, head_observed_at: '2026-10-17T05:00:00Z' });
  assert.equal(canaryNeedsRefresh(blocked, refreshNow), 'behind');
  delete blocked.mergeable_state;
  assert.equal(canaryNeedsRefresh(blocked, refreshNow), 'checks_failed');
  blocked.check_status = 'success';
  assert.equal(canaryNeedsRefresh(blocked, refreshNow), 'review_blocked');
  blocked.active_review_thread_count = 0;
  blocked.mergeable_state = 'dirty';
  assert.equal(canaryNeedsRefresh(blocked, refreshNow), 'stale');
  delete blocked.head_observed_at;
  blocked.updated_at = '2026-10-17T05:00:00Z';
  blocked.created_at = '2026-10-16T00:00:00Z';
  assert.equal(canaryNeedsRefresh(blocked, refreshNow), 'stale');
  blocked.updated_at = '2026-10-17T11:00:00Z';
  assert.equal(canaryNeedsRefresh(blocked, refreshNow), null);
  delete blocked.updated_at;
  assert.equal(canaryNeedsRefresh(blocked, refreshNow), 'stale');
  delete blocked.created_at;
  assert.equal(canaryNeedsRefresh(blocked, refreshNow), null);
});

test('only complete exact-head staging Gate evidence suppresses the base-refresh loop', async () => {
  const head = 'a'.repeat(40);
  const runId = 123456;
  const gateStatus = { context: 'Gate / gate', state: 'failure',
    target_url: `https://github.com/stranske/Ready/actions/runs/${runId}` };
  const gate = legacyStatusAsCheck(gateStatus);
  const allChecks = [gate];
  const classification = classifySyncPrChecks({
    checkRuns: allChecks, requiredContexts: ['Gate / gate'],
  });
  const summary = { name: 'gate-summary', status: 'completed', conclusion: 'failure',
    head_sha: head, app: { slug: 'github-actions' },
    details_url: `https://github.com/stranske/Ready/actions/runs/${runId}/job/2` };
  const dualChecks = [gate, summary];
  const dualClassification = classifySyncPrChecks({
    checkRuns: dualChecks, requiredContexts: ['Gate / gate', 'gate-summary'],
  });
  assert.equal(gate.details_url, gateStatus.target_url);
  assert.equal(classification.status, 'checks_failed');
  const jobs = [
    { id: 1, name: 'classify changed paths', status: 'completed', conclusion: 'failure' },
    { id: 2, name: 'gate-summary', status: 'completed', conclusion: 'failure' },
    { id: 3, name: 'generated delivery seal', status: 'completed', conclusion: 'failure' },
  ];
  const templateJobs = [
    { id: 11, name: 'detect changed files', status: 'completed', conclusion: 'failure' },
    { id: 12, name: 'generated delivery seal', status: 'completed', conclusion: 'failure' },
    { id: 13, name: 'summary', status: 'completed', conclusion: 'failure' },
  ];
  const exactReason = 'Mutable generated delivery is not mergeable: delivery_not_sealed:staging. ' +
    'Maint 71 must seal this exact head after bounded reviewer settlement.';
  const annotations = [
    { annotation_level: 'failure', message: exactReason },
    { annotation_level: 'failure', message: 'Process completed with exit code 1.' },
    { annotation_level: 'warning', message: 'The staging label remains active.' },
  ];
  const makeRetry = ({ run = {}, jobRows = jobs, rows = annotations, count = rows.length,
    apiError = false, check = {}, log } = {}) => async (callback) => callback({
    rest: {
      actions: {
        getWorkflowRun: async () => {
          if (apiError) throw new Error('API unavailable');
          return { data: { id: runId, head_sha: head, name: 'Gate',
            path: '.github/workflows/pr-00-gate.yml', status: 'completed',
            conclusion: 'failure', ...run } };
        },
        listJobsForWorkflowRun: async () => ({ data: { jobs: jobRows } }),
        downloadJobLogsForWorkflowRun: async () => ({ data: log ?? 'Error: ' + rows.find(r => r.message?.startsWith('Mutable generated'))?.message }),
      },
      checks: {
        get: async () => ({ data: { name: 'generated delivery seal', head_sha: head,
          status: 'completed', conclusion: 'failure', app: { slug: 'github-actions' },
          output: { annotations_count: count }, ...check } }),
        listAnnotations: async () => ({ data: rows }),
      },
    },
    paginate: async (method) => method.name === 'listJobsForWorkflowRun' ? jobRows : rows,
  });
  const args = { owner: 'stranske', repo: 'Ready', headSha: head, deliveryState: 'staging',
    deliveryRecord: { delivery_state: 'staging', head_observed_sha: head },
    classification, allChecks };
  assert.equal(await isExpectedPresealGateFailure({ ...args, withRetry: makeRetry() }), true);
  assert.deepEqual(dualClassification.failed.map((check) => check.name),
    ['Gate / gate', 'gate-summary']);
  assert.equal(await isExpectedPresealGateFailure({ ...args, allChecks: dualChecks,
    classification: dualClassification, withRetry: makeRetry() }), true);
  const directOnly = classifySyncPrChecks({ checkRuns: [summary], requiredContexts: ['gate-summary'] });
  assert.equal(await isExpectedPresealGateFailure({ ...args, allChecks: [summary],
    classification: directOnly, withRetry: makeRetry() }), true, 'a direct required Gate check can supply the run binding');
  assert.equal(await isExpectedPresealGateFailure({ ...args,
    withRetry: makeRetry({ jobRows: templateJobs }) }), true);
  assert.equal(await isExpectedPresealGateFailure({ ...args,
    withRetry: makeRetry({ jobRows: jobs.map(job => job.name === 'classify changed paths'
      ? { ...job, conclusion: 'success' } : job) }) }), true);
  const sealedArgs = { ...args, deliveryState: 'sealed', deliveryRecord: {
    delivery_state: 'sealed', head_observed_sha: head, sealed_head_sha: head,
    sealed_at: '2026-10-17T12:00:00Z' } };
  assert.equal(await isExpectedPresealGateFailure({ ...sealedArgs,
    withRetry: makeRetry({ run: { created_at: '2026-10-17T11:00:00Z' } }) }), true);
  assert.equal(await isExpectedPresealGateFailure({ ...sealedArgs,
    withRetry: makeRetry({ run: { created_at: sealedArgs.deliveryRecord.sealed_at } }) }), true);
  assert.equal(await isExpectedPresealGateFailure({ ...sealedArgs,
    withRetry: makeRetry({ run: { created_at: '2026-10-17T13:00:00Z' } }) }), false);
  assert.equal(await isExpectedPresealGateFailure({ ...sealedArgs,
    withRetry: makeRetry({ run: { created_at: '2026-10-17T11:00:00Z',
      run_started_at: '2026-10-17T13:00:00Z' } }) }), false, 'a later rerun cannot reuse old creation time');
  assert.equal(await isExpectedPresealGateFailure({ ...sealedArgs,
    withRetry: makeRetry() }), false, 'unknown run time must not wake an already sealed head');
  assert.equal(canaryNeedsRefresh(refreshCanary({ check_status: 'checks_failed',
    expected_preseal_gate_hold: true }), refreshNow), null);
  assert.equal(canaryNeedsRefresh(refreshCanary({ check_status: 'checks_failed' }), refreshNow),
    'checks_failed');

  for (const withRetry of [
    makeRetry({ run: { head_sha: 'b'.repeat(40) } }),
    makeRetry({ run: { path: 'untrusted/.github/workflows/pr-00-gate.yml' } }),
    makeRetry({ jobRows: [...jobs, { id: 4, name: 'python tests', status: 'completed',
      conclusion: 'failure' }] }),
    makeRetry({ jobRows: [...templateJobs, { id: 14, name: 'python tests', status: 'completed',
      conclusion: 'failure' }] }),
    makeRetry({ jobRows: [...jobs, templateJobs[0]] }),
    makeRetry({ jobRows: [...jobs, { ...jobs[0], id: 4 }] }),
    makeRetry({ jobRows: [...jobs, { id: 4, name: 'python tests', status: 'completed',
      conclusion: 'timed_out' }] }),
    makeRetry({ jobRows: [...jobs, { id: 4, name: 'python tests', status: 'in_progress',
      conclusion: null }] }),
    makeRetry({ rows: annotations.slice(0, 1), count: 4 }),
    makeRetry({ rows: [...annotations, { annotation_level: 'failure', message: 'another error' }] }),
    makeRetry({ apiError: true }),
    makeRetry({ log: 'Error: unrelated classifier failure' }),
    makeRetry({ log: `Error: ${exactReason}\nError: also unrelated` }),
    makeRetry({ log: `Error: ${exactReason}\nTypeError: also unrelated` }),
  ]) {
    assert.equal(await isExpectedPresealGateFailure({ ...args, withRetry }), false);
  }
  for (const badSummary of [
    { ...summary, head_sha: 'b'.repeat(40) },
    { ...summary, details_url: `https://github.com/stranske/Ready/actions/runs/${runId + 1}/job/2` },
    { ...summary, details_url: `https://github.com/stranske/Other/actions/runs/${runId}/job/2` },
    { ...summary, app: { slug: 'other-app' } },
    { ...summary, conclusion: 'timed_out' },
  ]) {
    const checks = [gate, badSummary];
    const state = classifySyncPrChecks({
      checkRuns: checks, requiredContexts: ['Gate / gate', 'gate-summary'],
    });
    assert.equal(await isExpectedPresealGateFailure({ ...args, allChecks: checks,
      classification: state, withRetry: makeRetry() }), false);
  }
  const unrelated = { name: 'python tests', status: 'completed', conclusion: 'failure' };
  const extraChecks = [...dualChecks, unrelated];
  const extraState = classifySyncPrChecks({
    checkRuns: extraChecks, requiredContexts: ['Gate / gate', 'gate-summary', 'python tests'],
  });
  assert.equal(await isExpectedPresealGateFailure({ ...args, allChecks: extraChecks,
    classification: extraState, withRetry: makeRetry() }), false);
  assert.equal(await isExpectedPresealGateFailure({ ...args, allChecks: dualChecks,
    classification: dualClassification,
    withRetry: makeRetry({ rows: [{ annotation_level: 'failure', message: 'unrelated failure' }],
      count: 1 }) }), false);
  for (const targetUrl of [undefined, 'not-a-url',
    `https://github.com/another-repo/Ready/actions/runs/${runId}`]) {
    const status = { ...gateStatus };
    if (targetUrl === undefined) delete status.target_url;
    else status.target_url = targetUrl;
    const check = legacyStatusAsCheck(status);
    const checks = [check];
    const statusClassification = classifySyncPrChecks({
      checkRuns: checks, requiredContexts: ['Gate / gate'],
    });
    assert.equal(await isExpectedPresealGateFailure({ ...args,
      allChecks: checks, classification: statusClassification, withRetry: makeRetry() }), false);
  }
  assert.equal(await isExpectedPresealGateFailure({ ...args, deliveryState: 'sealed',
    withRetry: makeRetry() }), false);
  assert.equal(await isExpectedPresealGateFailure({ ...args,
    deliveryRecord: { ...args.deliveryRecord, head_observed_sha: 'b'.repeat(40) },
    withRetry: makeRetry() }), false);
  assert.equal(await isExpectedPresealGateFailure({ ...args,
    classification: { status: 'checks_failed', failed: [gate, { name: 'python', conclusion: 'failure' }] },
    withRetry: makeRetry() }), false);
});

test('overlapping blockers are counted independently and dry-run cannot mutate', async () => {
  const api = refreshHarness();
  const canary = refreshCanary({ check_status: 'checks_failed', active_review_thread_count: 1,
    head_observed_at: '2026-10-17T05:00:00Z' });
  const result = await refreshStableCanaries({ ...api, enabled: false, canaries: [canary] });
  assert.equal(result.red, 1);
  assert.equal(result.review_blocked, 1);
  assert.equal(result.stale, 1);
  assert.equal(result.canaries[0].refresh_reason, 'checks_failed');
  assert.equal(api.dispatches.length, 0);
  assert.equal(api.comments.length, 0);
});

test('active Maint 68 writer defers refresh; a failed dispatch emits zero and fails visibly', async () => {
  for (const active of [true, false]) {
    const api = refreshHarness({ actions: active ? {
      listWorkflowRuns: async () => ({ data: { workflow_runs: [
        { status: 'in_progress', display_title: 'Maint 68 promote auto plan source' },
      ] } }),
    } : { createWorkflowDispatch: async () => { throw new Error('dispatch denied'); } } });
    const result = await refreshStableCanaries({ ...api,
      canaries: [refreshCanary({ check_status: 'checks_failed' })] });
    assert.equal(result.refresh_dispatched, 0);
    assert.match(api.summaries.join(''), /red=1.*refresh_dispatched=0/);
    assert.equal(api.failures.length, active ? 0 : 1);
    if (!active) assert.match(api.failures[0], /dispatch denied/);
  }
});

test('review findings route manifest targets upstream once, including template sources', async () => {
  for (const [target, source] of [['scripts/shared.js', '.github/scripts/shared.js'],
    ['.github/workflows/consumer-gate.yml', 'templates/consumer-repo/.github/workflows/gate.yml']]) {
    const api = refreshHarness();
    const canary = refreshCanary({ active_review_thread_count: 1, threads: [
      { id: 'PRRT_4026', path: target, isResolved: false, isOutdated: false,
        comments: { nodes: [{ url: 'https://github.com/stranske/Ready/pull/12#discussion_r4026' }] } },
      { id: 'local', path: 'local.js', isResolved: false, isOutdated: false },
      { id: 'resolved', path: target, isResolved: true, isOutdated: false },
      { id: 'outdated', path: target, isResolved: false, isOutdated: true },
    ] });
    await refreshStableCanaries({ ...api, canaries: [canary] });
    await refreshStableCanaries({ ...api, canaries: [canary] });
    assert.equal(api.comments.length, 1, 'existing upstream comment must prevent a duplicate');
    assert.equal(api.comments[0].issue_number, 4020);
    assert.equal(api.comments[0].repo, 'Workflows');
    assert.equal(api.reads[0].path, source);
    assert.match(api.comments[0].body, /discussion_r4026/);
    assert.ok(api.comments[0].body.includes(source));
  }
});

test('an existing upstream comment is reused and direct commits use commit comments', async () => {
  for (const existing of [false, true]) {
    const api = refreshHarness({ prs: [], existing: existing ? [{
      user: { login: 'maint71-bot' }, body: '<!-- maint71-canary-upstream:stranske/Ready:PRRT_4026 -->',
    }] : [] });
    await refreshStableCanaries({ ...api, canaries: [refreshCanary({ active_review_thread_count: 1,
      threads: [{ id: 'PRRT_4026', path: 'scripts/shared.js', isResolved: false, isOutdated: false,
        comments: { nodes: [{ url: 'https://github.com/stranske/Ready/pull/12#discussion_r4026' }] } }],
    })] });
    assert.equal(api.comments.length, existing ? 0 : 1);
    if (!existing) assert.equal(api.comments[0].commit_sha, 'a'.repeat(40));
  }
});

async function assertExecutorCanaryRefresh(t, state) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `maint71-${state}-canary-`));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const repository = require('../../../config/consumer_sync_canaries.json').canaries[0].repo;
  const [owner, repo] = repository.split('/');
  const head = 'd'.repeat(40), source = 'c'.repeat(40), plan = `sha256:${'a'.repeat(64)}`;
  t.mock.timers.enable({ apis: ['Date'], now: refreshNow });
  const ageMinutes = ['stale', 'aged_green'].includes(state) ? (STALE_CANARY_HOURS + 1) * 60 : 20;
  const observed = new Date(refreshNow - ageMinutes * 60 * 1000).toISOString();
  const reviewStarted = state === 'seal_review_wait' ? new Date(refreshNow - 60000).toISOString() : observed;
  const { formatDeliveryRecord } = require('../sync_pr_lease_contract');
  const sealRecovery = state.startsWith('seal_') && state !== 'seal_drained';
  const reviewRecovery = state.startsWith('seal_review_');
  const alreadySealed = state.startsWith('seal_already_');
  const delivery = state === 'seal_already_delivery';
  const olderGreen = state === 'seal_already_green';
  const dispatchError = state.endsWith('_422') ? 422 : state.endsWith('_404') ? 404 : null;
  const preseal = !olderGreen && (sealRecovery || ['preseal_gate', 'preseal_gate_dual', 'producer_success_staging'].includes(state));
  const producerSucceeded = state.startsWith('producer_success');
  const presealDual = !olderGreen && (state === 'preseal_gate_dual' || sealRecovery);
  const sealMessage = 'Mutable generated delivery is not mergeable: ' +
    (sealRecovery ? 'sealed_head_mismatch' : 'delivery_not_sealed:staging') +
    '. Maint 71 must seal this exact head after bounded reviewer settlement.';
  const candidate = { number: 4026, title: 'chore: sync workflow templates',
    state: 'open', draft: false, auto_merge: null, user: { login: 'stranske' },
    mergeable: state !== 'stale',
    mergeable_state: ['behind', 'producer_success_behind', 'seal_already_behind'].includes(state) ? 'behind' : state === 'stale' ? 'dirty' : 'clean',
    head: { ref: delivery ? 'sync/workflows-delivery' : 'sync/workflows-candidate', sha: head }, base: { ref: 'main', sha: 'b'.repeat(40) },
    created_at: observed, updated_at: observed,
    body: `<!-- workflows-consumer-sync:v1 ${JSON.stringify({
      schema: 'workflows-consumer-sync-pr/v1', consumer_repo: repository,
      plan_id: plan, plan_scope: 'full', source_commit: source, source_sha: source,
      template_hash: 'generation', sync_phase: delivery ? 'promote' : 'canary',
    })} -->\n` + formatDeliveryRecord({
      schema: 'sync-pr-delivery-record/v1', repository, plan_id: plan,
      durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
      generation: 'generation', desired_tree_hash: 'tree', source_commit: source,
      head_observed_sha: head, head_observed_at: observed,
      lease_expires_at: '2099-01-01T00:00:00Z', delivery_state: reviewRecovery ? 'reviewing' : sealRecovery ? 'sealed' : preseal ? 'staging' : 'sealed',
      sealed_at: observed, sealed_head_sha: sealRecovery && !alreadySealed ? 'f'.repeat(40) : head, review_started_at: reviewStarted,
    }) };
  const reruns = [], dispatches = [], updates = [], summaries = [], failures = [], merges = [], tipReads = [];
  const gateReads = [], labelWrites = [];
  const github = { rest: {
    users: { getAuthenticated: async () => ({ data: { login: 'maint71-bot' } }) },
    pulls: {
      list: async params => ({ data: params.repo === repo && params.state === 'open' ? [structuredClone(candidate)] : [] }),
      listFiles: async () => ({ data: [{ filename: 'scripts/shared.js' }] }), get: async () => ({ data: structuredClone(candidate) }),
      update: async (params) => {
        assert.ok(params.body, 'refresh must never close or update the stable branch');
        updates.push(params); candidate.body = params.body;
        return { data: structuredClone(candidate) };
      },
      updateBranch: async () => assert.fail('stable canary must never call pulls.updateBranch'),
      merge: async (params) => {
        assert.ok(['aged_green', 'seal_drained'].includes(state), `${state} canary must never merge`);
        merges.push(params); return { data: { merged: true } };
      },
    },
    git: { getRef: async () => ({ data: { object: { sha: head } } }), getCommit: async () => ({ data: { tree: { sha: 'tree' } } }),
      deleteRef: async () => {},
    },
    repos: {
      get: async () => ({ data: { default_branch: 'main' } }),
      getBranch: async (params) => {
        tipReads.push(params);
        return { data: { commit: { sha: 'e'.repeat(40) } } };
      },
      getCombinedStatusForRef: async () => ({ data: { statuses: preseal ? [{
        context: 'Gate / gate', state: 'failure',
        target_url: `https://github.com/${owner}/${repo}/actions/runs/4027`,
        updated_at: observed, description: 'Path classification failed',
      }] : [] } }),
      getBranchProtection: async () => ({ data: { required_status_checks: {
        contexts: presealDual ? ['Gate / gate', 'gate-summary', ...(sealRecovery ? ['generated delivery seal', 'classify changed paths'] : []),
          ...(state === 'seal_real_failure' ? ['production tests'] : [])] : ['Gate / gate'],
      } } }),
      getCommit: async ({ ref }) => ({ data: { sha: ref === 'main' && !producerSucceeded ? 'a'.repeat(40) : source, commit: { committer: { date: observed } } } }),
      getContent: async ({ path: filePath }) => {
        if (filePath === 'config/consumer_sync_canaries.json') return { data: { content:
          Buffer.from(JSON.stringify(require('../../../config/consumer_sync_canaries.json'))).toString('base64') } };
        throw Object.assign(new Error('not declared'), { status: 404 });
      },
      createDispatchEvent: async () => {},
    },
    checks: {
      listForRef: () => {},
      get: async () => ({ data: { name: 'generated delivery seal', head_sha: head,
        status: 'completed', conclusion: 'failure', app: { slug: 'github-actions' },
        output: { annotations_count: 2 } } }),
      listAnnotations: async () => ({ data: [
        { annotation_level: 'failure', message: 'Mutable generated delivery is not mergeable: ' +
          'delivery_not_sealed:staging. Maint 71 must seal this exact head after bounded reviewer settlement.' },
        { annotation_level: 'failure', message: 'Process completed with exit code 1.' },
      ] }),
    },
    issues: { addLabels: async (params) => labelWrites.push(params), removeLabel: async () => {},
      listLabelsOnIssue: async () => ({ data: [] }),
      listComments: async () => ({ data: [{ id: 71, user: { login: 'maint71-bot' },
        created_at: reviewStarted, body: '@codex review\n<!-- maint71-review-request:v1 ' +
          JSON.stringify({ plan_id: plan, generation: 'generation', head_sha: head, reviewer: 'codex' }) + ' -->',
      }] }),
    },
    actions: {
      listWorkflowRuns: async (params) => {
        if (params.workflow_id === 'pr-00-gate.yml') {
          gateReads.push(params);
          const requested = dispatches.some(d => d.workflow_id === 'pr-00-gate.yml');
          return { data: { workflow_runs: [{ id: requested ? 4104 : 4027,
            event: requested ? 'workflow_dispatch' : 'pull_request', status: 'completed', conclusion: 'failure',
            head_sha: head, head_branch: candidate.head.ref,
            created_at: alreadySealed && !requested
              ? new Date(Date.parse(observed) - 60000).toISOString()
              : new Date(refreshNow).toISOString() }] } };
        }
        return { data: { workflow_runs: producerSucceeded ? [{
        ...producerRun(), head_sha: source, display_title: `Maint 68 canary full source=${source} candidates=* dry=false`,
      }] : [] } };
      },
      reRunWorkflowFailedJobs: async params => {
        reruns.push(params);
        if (dispatchError) throw Object.assign(new Error('consumer Gate unavailable'), { status: dispatchError });
        return { status: 201 };
      },
      createWorkflowDispatch: async (params) => {
        dispatches.push(params);
        if (params.workflow_id === 'pr-00-gate.yml' && dispatchError) {
          throw Object.assign(new Error('consumer Gate unavailable'), { status: dispatchError });
        }
        return { status: 204 };
      },
      getWorkflowRun: async () => ({ data: { id: 4027, head_sha: head, name: state === 'producer_success_staging' ? 'Unrecognized Gate' : 'Gate',
        path: '.github/workflows/pr-00-gate.yml', created_at: observed, status: 'completed', conclusion: 'failure' } }),
      downloadJobLogsForWorkflowRun: async () => ({ data: 'Error: ' + sealMessage }),
      listJobsForWorkflowRun: () => {},
    },
  }, paginate: async (method, params) => {
    if (method === github.rest.pulls.list) return state !== 'no_change' && params.state === 'open' && params.repo === repo
      ? [structuredClone(candidate)] : [];
    if (method === github.rest.checks.listForRef && presealDual) return [
      ...(sealRecovery ? ['generated delivery seal', 'classify changed paths'].map(name => ({
        name, status: 'completed', conclusion: 'failure', head_sha: head, app: { slug: 'github-actions' },
        details_url: `https://github.com/${owner}/${repo}/actions/runs/4027/job/3` })) : []),
      ...(state === 'seal_real_failure' ? [{ name: 'production tests', status: 'completed', conclusion: 'failure' }] : []),
      { name: 'gate-summary', status: 'completed', conclusion: 'failure', head_sha: head,
        app: { slug: 'github-actions' },
        details_url: `https://github.com/${owner}/${repo}/actions/runs/4027/job/2` },
    ];
    if (method === github.rest.checks.listForRef) return preseal ? [] : [
      { name: 'Gate / gate', status: 'completed',
        conclusion: ['checks_failed', 'producer_success_red'].includes(state) ? 'failure' : 'success' },
    ];
    if (method === github.rest.actions.listJobsForWorkflowRun) return [
      { id: 1, name: 'classify changed paths', status: 'completed', conclusion: 'failure' },
      { id: 2, name: 'gate-summary', status: 'completed', conclusion: 'failure' },
      { id: 3, name: 'generated delivery seal', status: 'completed', conclusion: 'failure' },
    ];
    if (method === github.rest.checks.listAnnotations) return [
      { annotation_level: 'failure', message: sealMessage },
      { annotation_level: 'failure', message: 'Process completed with exit code 1.' },
    ];
    throw new Error('unexpected pagination');
  }, graphql: async () => ({ repository: {
    object: { signature: { isValid: true, state: 'VALID', wasSignedByGitHub: true } },
    pullRequest: { state: 'OPEN', headRefOid: head, body: candidate.body,
    createdAt: observed, updatedAt: observed,
    comments: { pageInfo: { hasNextPage: false }, nodes: [] },
    reviews: { pageInfo: { hasNextPage: false }, nodes: [] },
    reviewThreads: { pageInfo: { hasNextPage: false }, nodes: ['review_blocked', 'seal_review_threads'].includes(state) ? [
      { id: 'PRRT_executor', path: 'consumer-owned.js', isResolved: false, isOutdated: false,
        comments: { pageInfo: { hasNextPage: false }, nodes: [] } },
    ] : [] },
  } } }) };
  const retryHelpers = require('../github-api-with-retry');
  t.mock.method(retryHelpers, 'createTokenAwareRetry', async () => null);
  t.mock.method(retryHelpers, 'withRetry', async (fn) => fn(github));
  const logs = [];
  t.mock.method(console, 'log', (...args) => logs.push(args.join(' ')));
  const env = { REGISTERED_REPOS_INPUT: repository, REPOS_INPUT: repository,
    OWNER_PR_PAT: 'test-owner-token', TRUSTED_SYNC_ACTORS: 'stranske',
    CLEANUP_BRANCHES_INPUT: 'false', AUTO_MERGE_INPUT: 'true', DRY_RUN_INPUT: 'false',
    ACTIVE_SYNC_HASH_INPUT: delivery ? 'delivery' : 'candidate', EXPECTED_PLAN_ID_INPUT: plan,
    EXPECTED_SOURCE_COMMIT_INPUT: source, EXPECTED_PLAN_SCOPE_INPUT: 'full',
    SYNC_PR_MERGE_REPORT_JSON: path.join(dir, 'report.json'),
    EVIDENCE_ONLY_INPUT: 'false', RESOLUTION_ONLY_INPUT: 'false',
    CANARY_BASELINE_EVIDENCE_JSON: state === 'no_change' ? JSON.stringify({
      schema: 'workflows.consumer-sync-canary-evidence/v1', version: 1,
      results: [{ repo: repository, plan_id: plan, plan_scope: 'full', scope_base_sha: '',
        source_commit: source, head_sha: head, evidence_source: 'no-change-canary',
        required_check_state: 'success', active_review_thread_count: 0 }],
    }) : '',
    CANDIDATE_EVIDENCE_AUTHORIZED: 'true',
    PREPARE_ONLY_INPUT: ['aged_green', 'seal_drained'].includes(state) ? 'false' : 'true',
    ...(preseal || olderGreen ? { DRY_RUN_INPUT: sealRecovery ? 'false' : 'true', CONSUMER_SYNC_REVIEW_POLICY_PATH:
      reviewRecovery ? legacyPolicyPath : path.resolve(__dirname, '../../../config/consumer_sync_review_policy.json') } : {}),
    ...(state === 'seal_drained' ? { CONSUMER_SYNC_REVIEW_POLICY_PATH: path.resolve(__dirname, '../../../config/consumer_sync_review_policy.json') } : {}) };
  const original = Object.fromEntries(Object.keys(env).map((key) => [key, process.env[key]]));
  t.after(() => {
    for (const [key, value] of Object.entries(original)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  });
  Object.assign(process.env, env);
  await run({ github, context: { repo: { owner: 'stranske', repo: 'Workflows' }, payload: {},
    eventName: 'workflow_dispatch', runId: 4026 }, core: {
    notice() {}, warning() {}, setFailed: (message) => failures.push(message),
    summary: { addRaw(text) { summaries.push(text); return this; }, async write() {} },
  } });
  const report = JSON.parse(fs.readFileSync(env.SYNC_PR_MERGE_REPORT_JSON, 'utf8'));
  assert.equal(tipReads.length, candidate.mergeable_state === 'behind' ? 1 : 0,
    'executor and final refresh pass share one live read, only for behind canaries');
  if (tipReads.length) {
    assert.deepEqual(tipReads[0], { owner, repo, branch: 'main' });
    assert.equal(dispatches[0].inputs.refresh_key, require('crypto').createHash('sha256')
      .update(`${repository}:${'e'.repeat(40)}:${head}`).digest('hex'));
  }
  assert.deepEqual(failures, [], JSON.stringify(report.results));
  const row = report.results.find((row) => row.owner === owner && row.repo === repo
    && (!['aged_green', 'seal_drained'].includes(state) || row.status === 'merged'));
  if (state === 'no_change') {
    assert.equal(row.status, 'evidence_recovered');
    assert.equal(row.plan_id, plan, 'no-change report must retain plan identity');
    assert.equal(row.source_commit, source, 'no-change report must retain source identity');
    assert.equal(row.head_sha, head, 'no-change report must retain exact head');
    const evidence = JSON.parse(fs.readFileSync('artifacts/sync-canary-evidence.json', 'utf8'));
    assert.equal((await dispatchCanaryPromotion({ report, evidence, expectedCanaries: [repository],
      withRetry: async (fn) => fn(github), context: { repo: { owner: 'stranske', repo: 'Workflows' }, payload: {} },
      core: { notice() {}, summary: { addRaw() { return this; }, async write() {} } },
    })).status, 'dispatched');
    assert.equal(dispatches.length, 1);
    assert.equal(dispatches[0].inputs.phase, 'promote');
    return;
  }
  if (state === 'producer_success_behind') {
    assert.equal(row.status, 'stable_base_refresh_required');
    assert.equal(row.refresh_reason, 'behind');
    assert.equal(dispatches.length, 1, 'a pre-drift producer must not latch behind forever');
    assert.match(dispatches[0].inputs.refresh_key, /^[a-f0-9]{64}$/);
    assert.equal(merges.length, 0);
    return;
  }
  if (producerSucceeded) {
    assert.equal(row.status, 'checks_failed', JSON.stringify(report.results));
    assert.equal(dispatches.length, 0, 'a successful producer must not create another canary');
    assert.equal(updates.length, 0, 'producer success must preserve the existing lifecycle');
    assert.equal(merges.length, 0, 'producer success must not authorize failed consumer checks');
    return;
  }
  if (['seal_review_wait', 'seal_review_threads'].includes(state)) {
    assert.equal(report.canary_refresh.drainable, Number(state === 'seal_review_wait'));
    assert.equal(row.status, state === 'seal_review_wait' ? 'reviewer_settlement_pending' : 'stable_base_refresh_required', JSON.stringify(report.results));
    assert.equal(reruns.length, 0, 'restaged or unsettled head must not rerun Gate');
    assert.equal(updates.filter(({body}) => require('../sync_pr_lease_contract').parseDeliveryRecord(body)?.delivery_state === 'sealed').length, 0);
    assert.equal(merges.length, 0);
    if (state === 'seal_review_wait') assert.ok(summaries.includes(`seal: ${repository}#4026 pending(seal_pending)\n`));
    return;
  }
  if (state === 'seal_already_behind') {
    assert.equal(row.status, 'stable_base_refresh_required');
    assert.equal(reruns.length, 0, 'an exact sealed head about to restage must never rerun');
    assert.equal(require('../sync_pr_lease_contract').parseDeliveryRecord(candidate.body).delivery_state, 'staging');
    return;
  }
  if (sealRecovery) {
    const blocked = state === 'seal_real_failure';
    assert.equal(row.status, blocked ? 'checks_failed' : 'delivery_sealed_checks_pending', JSON.stringify(report.results));
    assert.equal(row.delivery_disposition, blocked ? 'repo-local-failure' : 'awaiting-sealed-gate');
    const sealWrites = updates.filter(({body}) => require('../sync_pr_lease_contract').parseDeliveryRecord(body)?.delivery_state === 'sealed');
    assert.equal(sealWrites.length, blocked || alreadySealed ? 0 : 1, 'seal exact head once');
    if (sealWrites.length) assert.equal(require('../sync_pr_lease_contract')
      .parseDeliveryRecord(sealWrites[0].body).review_evidence.delivery_digest, `sha256:${source[0].repeat(64)}`);
    if (!blocked) {
      if (!olderGreen) {
        assert.equal(row.seal_pending, true);
        assert.equal(row.check_status, 'seal_pending');
        assert.equal(row.raw_check_status, 'checks_failed');
      }
      assert.equal(row.gate_request.mode, dispatchError ? 'failed' : 'rerun');
      assert.deepEqual(reruns, [{ owner, repo, run_id: 4027 }]);
      assert.equal(dispatches.length, 0);
      if (dispatchError) {
        assert.equal(row.gate_request.status, dispatchError);
        assert.ok(logs.includes(`seal: ${repository}#4026 gate request failed: ${dispatchError} consumer Gate unavailable`));
      } else {
        assert.equal(row.gate_request.run_id, 4027);
        assert.ok(logs.includes(`seal: ${repository}#4026 gate rerun run=4027`));
      }
      if (!delivery) assert.ok(summaries.includes(`seal: ${repository}#4026 sealed\n`));
    } else {
      assert.ok(summaries.some(s => s.includes('blocked(Gate / gate,') && s.includes('production tests')));
    }
    assert.equal(merges.length, 0);
    if (state === 'seal_already_current') {
      for (const status of ['in_progress', 'completed']) {
        github.rest.actions.listWorkflowRuns = async () => ({ data: { workflow_runs: [{
          id: 4027, event: 'pull_request', head_sha: head, status, run_attempt: 2,
          conclusion: status === 'completed' ? 'success' : null,
          run_started_at: new Date(refreshNow).toISOString(),
        }] } });
        await run({ github, context: { repo: { owner: 'stranske', repo: 'Workflows' }, payload: {},
          eventName: 'workflow_dispatch', runId: 4026 }, core: {
          notice() {}, warning() {}, setFailed: message => failures.push(message),
          summary: { addRaw() { return this; }, async write() {} },
        } });
        assert.equal(reruns.length, 1, 'second Maint 71 pass must not rerun an active or succeeded attempt');
      }
    }
    assert.equal(report.canary_refresh.red, Number(blocked));
    assert.equal(report.canary_refresh.drainable, Number(!blocked && !olderGreen && !delivery));
    return;
  }
  if (preseal) {
    assert.equal(row.status, 'dry_run_seal', JSON.stringify(report.results));
    assert.equal(report.canary_refresh.refresh_dispatched, 0);
    assert.equal(updates.length, 0, 'the dry-run staging exception must not mutate the PR');
    assert.equal(dispatches.length, 0);
    return;
  }
  if (['aged_green', 'seal_drained'].includes(state)) {
    assert.equal(row.status, 'merged', JSON.stringify(report.results));
    assert.equal(merges.length, 1);
    assert.equal(merges[0].sha, head);
    if (state === 'seal_drained') {
      const evidence = JSON.parse(fs.readFileSync('artifacts/sync-canary-evidence.json', 'utf8'));
      const promotion = await dispatchCanaryPromotion({ report, evidence, expectedCanaries: [repository],
        withRetry: async fn => fn(github), context: { repo: { owner: 'stranske', repo: 'Workflows' }, payload: {} },
        core: { notice() {}, summary: { addRaw() { return this; }, async write() {} } } });
      assert.equal(promotion.status, 'dispatched');
      assert.equal(dispatches.length, 1);
      assert.equal(dispatches[0].inputs.phase, 'promote');
      assert.ok(summaries.includes('canaries: red=0 review_blocked=0 stale=0 refresh_dispatched=0 held_plan=none drainable=0\n'));
      return;
    }
    assert.equal(dispatches.length, 0);
    assert.equal(updates.length, 0);
    assert.equal(report.canary_refresh.stale, 0);
    assert.equal(report.canary_refresh.refresh_dispatched, 0);
    assert.ok(summaries.includes('canaries: red=0 review_blocked=0 stale=0 refresh_dispatched=0 held_plan=none drainable=0\n'));
    return;
  }
  if (state === 'checks_failed') {
    assert.equal(row.status, 'checks_failed');
    assert.equal(row.delivery_disposition, 'repo-local-failure');
    assert.equal(updates.length, 0);
    assert.equal(dispatches.length, 1);
    return;
  }
  assert.equal(row.status, 'stable_base_refresh_required', JSON.stringify(report.results));
  assert.equal(row.next_command, 'rerun-after-maint-68-canary-refresh');
  assert.equal(row.refresh_reason, state);
  assert.equal(dispatches.length, 1);
  assert.equal(report.canary_refresh.refresh_dispatched, 1);
  assert.equal(require('../sync_pr_merge_contract').candidateRefreshDecision({ report }).eligible,
    false, 'legacy workflow refresh must not duplicate the executor dispatch for missing siblings');
  assert.equal(updates.length, 1);
  assert.equal(candidate.head.sha, head);
  assert.ok(summaries.some((line) => line ===
    `canaries: red=${Number(state === 'checks_failed')} ` +
    `review_blocked=${Number(state === 'review_blocked')} ` +
    `stale=${Number(state === 'stale')} refresh_dispatched=1 held_plan=${plan} drainable=0\n`));
}

for (const state of ['behind', 'checks_failed', 'review_blocked', 'stale']) {
  test(`executor refreshes a ${state} stable canary before early exits and preserves the head`,
    async (t) => assertExecutorCanaryRefresh(t, state));
}

for (const state of ['seal_mismatch', 'seal_real_failure', 'seal_already_current', 'seal_already_delivery', 'seal_already_behind', 'seal_already_green', 'seal_already_422', 'seal_already_404', 'seal_review_settled', 'seal_review_wait', 'seal_review_threads', 'seal_drained']) {
  test(`seal recovery ${state} preserves real check blockers`, async (t) => assertExecutorCanaryRefresh(t, state));
}

test('exact pre-seal Gate failure advances only to the existing seal lifecycle', async (t) =>
  assertExecutorCanaryRefresh(t, 'preseal_gate'));

test('branch-protected gate-summary and legacy Gate failure share the pre-seal hold', async (t) =>
  assertExecutorCanaryRefresh(t, 'preseal_gate_dual'));

test('executor merges a green mergeable seven-hour canary without refreshing',
  async (t) => assertExecutorCanaryRefresh(t, 'aged_green'));

test('distinct held plans share one full candidate-set dispatch for the main SHA', async () => {
  const api = refreshHarness();
  const rows = ['plan-A', 'plan-B', 'plan-A', 'plan-B'].map((plan_id, index) =>
    refreshCanary({ repo: `Repo${index}`, plan_id, check_status: 'checks_failed' }));
  const result = await refreshStableCanaries({ ...api, canaries: rows });
  assert.equal(api.dispatches.length, 1);
  assert.equal(result.refresh_dispatched, 1);
  assert.deepEqual(result.held_plans, ['plan-A', 'plan-B']);
});

test('an untrusted marker cannot suppress upstream routing', async () => {
  const api = refreshHarness({ existing: [{ user: { login: 'someone-else' },
    body: '<!-- maint71-canary-upstream:stranske/Ready:PRRT_4026 -->' }] });
  await refreshStableCanaries({ ...api, canaries: [refreshCanary({ active_review_thread_count: 1,
    threads: [{ id: 'PRRT_4026', path: 'scripts/shared.js', isResolved: false, isOutdated: false,
      comments: { nodes: [{ url: 'https://github.com/stranske/Ready/pull/12#discussion_r4026' }] } }],
  })] });
  assert.equal(api.comments.length, 1);
});

test('Maint 68 verified unchanged-tree run resets producer observation without changing lifecycle', () => {
  const workflow = fs.readFileSync(path.join(__dirname, '../../workflows/maint-68-sync-consumer-repos.yml'), 'utf8');
  const start = workflow.indexOf('          desired_tree_hash=$(git write-tree)');
  const end = workflow.indexOf('          elif [ -n "$existing_pr" ]', start);
  assert.ok(start >= 0 && end > start);
  const script = `set -eu
    git() { echo tree; }
    date() { echo 2026-10-17T12:00:00Z; }
    existing_pr=12 existing_refreshable=true existing_base=base base_sha=base
    existing_tree=tree existing_verified=true existing_lifecycle_initialized=true
    existing_head=unchanged head_observed_sha=unchanged head_observed_at=2026-10-17T05:00:00Z
    delivery_state=sealed review_started_at=prior sealed_at=prior sealed_head_sha=unchanged
    ${workflow.slice(start, end)}
    fi
    echo "RESULT:$head_observed_sha:$head_observed_at:$delivery_state:$sealed_at:$matching_existing"
  `;
  const output = require('node:child_process').execFileSync('bash', ['-c', script], { encoding: 'utf8' });
  assert.match(output, /RESULT:unchanged:2026-10-17T12:00:00Z:sealed:prior:true/);
});

test('native proof comments are read from the consumer while independent proof comments stay in Workflows', () => {
  const consumer = { owner: 'stranske', repo: 'Ready' };
  const source = { owner: 'stranske', repo: 'Workflows' };
  assert.deepEqual(acceptanceCommentLocation({ acceptance_mode: 'native-conversation-disposition' }, consumer, source), consumer);
  assert.deepEqual(acceptanceCommentLocation({ acceptance_mode: 'independent-verification' }, consumer, source), source);
});

test('failed reviewer retry is exact-head, terminal-only, once per binding and request-only', async (t) => {
  const request = { schema: 'maint71-review-reassessment/v1',
    repository: 'stranske/Ready', pr: 592, head_sha: 'a'.repeat(40),
    thread_id: 'PRRT_retry', plan_id: 'plan-1', generation: 'gen-1',
    source_commit: 'b'.repeat(40), originating_reviewer: 'codex' };
  const record = { schema: 'sync-pr-delivery-record/v1', repository: request.repository,
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: request.plan_id, generation: request.generation, desired_tree_hash: 'tree-1',
    source_commit: request.source_commit, head_observed_sha: request.head_sha,
    head_observed_at: '2026-09-24T22:00:00Z',
    lease_expires_at: '2099-01-01T00:00:00Z' };
  const canonical = JSON.stringify(request);
  const prior = { fullDatabaseId: '12', author: { login: 'stranske' },
    createdAt: '2026-09-24T22:00:00Z',
    body: '<!-- maint71-review-reassessment:v1 ' + canonical + ' -->' };
  const nodes = [{ fullDatabaseId: '11', author: { login: 'chatgpt-codex-connector' },
    body: 'Preserve required evidence' }, prior];
  const failedRow = '| 📝 **Code Review** | ⚠️ **Failed** <relative-time datetime="2026-09-24T22:01:00Z">2026-09-24T22:01:00Z</relative-time> | `aaaaaaa` | Manual request |';
  const summary = { user: { login: 'chatgpt-codex-connector[bot]' },
    updated_at: '2026-09-24T22:01:01Z',
    body: '<!-- codex-pull-request-review-summary -->\n| Review | Status | Commit | Review trigger |\n| --- | --- | --- | --- |\n' + failedRow };
  let summaries = [summary], resolvedSha = request.head_sha, posts = 0;
  let paginationRace = false, siblingComplete = true, commitRace = '';
  const pr = { state: 'open', draft: false, auto_merge: null,
    user: { login: 'stranske-automation-bot' },
    head: { ref: 'sync/workflows-candidate', sha: request.head_sha },
    body: '<!-- sync-pr-delivery-record:v1 ' + JSON.stringify(record) + ' -->' };
  const github = { paginate: async () => {
    if (paginationRace) pr.head.sha = 'c'.repeat(40);
    return structuredClone(summaries);
  }, rest: {
    users: { getAuthenticated: async () => ({ data: { login: 'stranske' } }) },
    pulls: {
      get: async () => ({ data: pr }),
      createReplyForReviewComment: async ({ body }) => {
        posts++;
        const posted = { id: 13, body, created_at: '2026-09-24T22:02:00Z',
          html_url: 'https://github.com/stranske/Ready/pull/592#discussion_r13',
          user: { login: 'stranske' } };
        nodes.push({ fullDatabaseId: '13', author: posted.user, body,
          createdAt: posted.created_at, url: posted.html_url });
        return { data: posted };
      },
    },
    issues: { listComments: () => {} },
    repos: { getCommit: async () => {
      if (commitRace === 'edited-completion') summary.body = summary.body.replace('Failed', 'Completed');
      if (commitRace === 'posted-completion') summaries.push({
        user: { login: 'chatgpt-codex-connector' }, created_at: '2026-09-24T22:01:30Z',
        body: "Codex Review: Didn't find any major issues." });
      return { data: { sha: resolvedSha } };
    } },
  }, graphql: async () => ({ repository: { pullRequest: { reviewThreads: {
    pageInfo: { hasNextPage: false }, nodes: [{ id: request.thread_id,
      isResolved: false, isOutdated: false,
      comments: { pageInfo: { hasNextPage: false }, nodes } }, {
        id: 'PRRT_sibling', isResolved: false, isOutdated: false,
        comments: { pageInfo: { hasNextPage: !siblingComplete }, nodes: [] },
      }],
  } } } }) };
  const args = { context: { eventName: 'repository_dispatch', ref: 'refs/heads/main',
    payload: { action: 'maint71-review-reassessment' }, actor: 'stranske' },
    withRetry: (fn) => fn(github),
    rawRequest: JSON.stringify({ ...request, request_stage: 'retry' }),
    registeredRepos: [request.repository],
    policyPath: path.join(__dirname, '..', '..', '..', 'config', 'consumer_sync_review_policy.json') };
  const temporaryPolicy = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-retry-transport-'));
  t.after(() => fs.rmSync(temporaryPolicy, { recursive: true, force: true }));
  const policy = JSON.parse(fs.readFileSync(args.policyPath, 'utf8'));
  const codexProfile = policy.reviewers.find((item) => item.id === 'codex');
  codexProfile.reassessment_task_transport = 'pr-conversation';
  codexProfile.reassessment_task_comment = '@codex please answer this specific finding';
  args.policyPath = path.join(temporaryPolicy, 'policy.json');
  fs.writeFileSync(args.policyPath, JSON.stringify(policy));
  for (const defect of ['missing-summary', 'duplicate-summary', 'forged-summary', 'pending',
    'completed', 'wrong-head', 'ambiguous-commit', 'stale-failure', 'future-failure',
    'stale-update', 'multiple-rows', 'missing-prior', 'duplicate-prior', 'changed-head',
    'subsequent-completion', 'explicit-acceptance', 'explicit-rejection',
    'partial-sibling', 'indented-running-row', 'pagination-head-race',
    'edited-completion', 'posted-completion']) {
    const savedBody = summary.body, savedUpdate = summary.updated_at;
    summaries = [summary]; resolvedSha = request.head_sha;
    if (defect === 'missing-summary') summaries = [];
    if (defect === 'duplicate-summary') summaries.push({ ...summary });
    if (defect === 'forged-summary') summary.user.login = 'untrusted';
    if (defect === 'pending') summary.body = savedBody.replace('Failed', 'Running');
    if (defect === 'completed') summary.body = savedBody.replace('Failed', 'Completed');
    if (defect === 'wrong-head') summary.body = savedBody.replace('aaaaaaa', 'ccccccc');
    if (defect === 'ambiguous-commit') resolvedSha = 'c'.repeat(40);
    if (defect === 'stale-failure') summary.body = savedBody.replaceAll('22:01:00', '21:59:00');
    if (defect === 'future-failure') summary.body = savedBody.replaceAll('2026-09-24', '2099-09-24');
    if (defect === 'stale-update') summary.updated_at = '2026-09-24T22:00:30Z';
    if (defect === 'multiple-rows') summary.body += '\n' + failedRow;
    if (defect === 'missing-prior') nodes.pop();
    if (defect === 'duplicate-prior') nodes.push({ ...prior });
    if (defect === 'changed-head') pr.head.sha = 'c'.repeat(40);
    if (defect === 'subsequent-completion') summaries.push({
      user: { login: 'chatgpt-codex-connector' }, created_at: '2026-09-24T22:01:30Z',
      body: "Codex Review: Didn't find any major issues." });
    if (['explicit-acceptance', 'explicit-rejection'].includes(defect)) nodes.push({
      fullDatabaseId: '14', author: { login: 'chatgpt-codex-connector' },
      createdAt: '2026-09-24T22:01:30Z', commit: { oid: request.head_sha },
      body: defect === 'explicit-acceptance'
        ? `ACCEPT <!-- sync-review-accepted:${request.head_sha} -->` : 'REJECT: still invalid',
    });
    if (defect === 'partial-sibling') siblingComplete = false;
    if (defect === 'indented-running-row') summary.body += '\n  | Code Review | Running | `aaaaaaa` | Manual request |';
    if (defect === 'pagination-head-race') paginationRace = true;
    if (['edited-completion', 'posted-completion'].includes(defect)) commitRace = defect;
    await assert.rejects(runReviewReassessment(args), /retry|delivery changed/i, defect);
    assert.equal(posts, 0, defect);
    summary.body = savedBody; summary.updated_at = savedUpdate;
    summary.user.login = 'chatgpt-codex-connector[bot]'; pr.head.sha = request.head_sha;
    paginationRace = false; siblingComplete = true; commitRace = '';
    if (['explicit-acceptance', 'explicit-rejection'].includes(defect)) nodes.pop();
    if (defect === 'missing-prior') nodes.push(prior);
    if (defect === 'duplicate-prior') nodes.pop();
  }
  for (const body of ['I cannot ACCEPT or REJECT this yet',
    '> Reply ACCEPT or REJECT in this thread',
    `The request asks for <!-- sync-review-accepted:${request.head_sha} -->`]) {
    summaries = [summary]; resolvedSha = request.head_sha;
    nodes.push({ fullDatabaseId: '14', author: { login: 'chatgpt-codex-connector' },
      createdAt: '2026-09-24T22:01:30Z', commit: { oid: request.head_sha }, body });
    const permitted = await runReviewReassessment(args);
    assert.equal(permitted.status, 'review_blocked_reassessment_requested', body);
    assert.equal(posts, 1, body);
    // Reset the independent fixture; each scenario starts without a retry marker.
    nodes.pop(); nodes.pop(); posts = 0;
  }
  summaries = [summary]; resolvedSha = request.head_sha;
  const first = await runReviewReassessment(args);
  assert.equal(first.status, 'review_blocked_reassessment_requested');
  assert.equal(first.task_status, undefined, 'retry must skip the initial conversation transport');
  assert.equal(posts, 1);
  assert.match(nodes.at(-1).body, /maint71-review-retry:v1/);
  assert.match(nodes.at(-1).body, /No unrelated edits, resolution or merge actions/);
  summaries = []; // Recovery must reuse the durable request after summary updates.
  const second = await runReviewReassessment(args);
  assert.equal(second.status, 'review_blocked_reassessment_reused');
  assert.equal(posts, 1);
});


test('behind leased dev-tool delivery routes to producer before branch update', () => {
  const context = {
    owner: 'stranske', repo: 'Ready', pr: 591,
    branch: 'deps/sync-dev-versions-1234', delivery_lane: 'dev-tool-sync',
    head_sha: 'a'.repeat(40), plan_id: 'plan-1',
    source_commit: 'b'.repeat(40), delivery_generation: 'generation-1',
  };
  assert.deepEqual(devToolBaseRefreshResult(context), {
    ...context, delivery_disposition: 'awaiting-base-refresh',
    blocker_owner: 'maint-52', next_command: 'dispatch-maint-52-scoped',
    status: 'dev_tool_base_refresh_required',
  });
  assert.equal(devToolBaseRefreshResult({ ...context, delivery_lane: 'sync' }), null);
  const source = fs.readFileSync(path.join(__dirname, '..', 'maint71_merge_sync_prs.js'), 'utf8');
  assert.match(source, /if \(devToolRefresh\) \{\s*results\.push\(devToolRefresh\);\s*continue;\s*\}\s*await withRetry\(\(client\) => client\.rest\.pulls\.updateBranch/s);
});

test('review reassessment parser accepts only exact versioned identities', () => {
  const request = {
    schema: 'maint71-review-reassessment/v1', repository: 'stranske/Ready', pr: 592,
    head_sha: 'a'.repeat(40), thread_id: 'PRRT_test', plan_id: 'plan-1',
    generation: 'gen-1', source_commit: 'b'.repeat(40),
    originating_reviewer: 'codex',
  };
  assert.deepEqual(parseReviewReassessmentRequest(JSON.stringify(request)), request);
  assert.throws(() => parseReviewReassessmentRequest(JSON.stringify({ ...request, extra: true })),
    /missing or extra fields/);
  assert.throws(() => parseReviewReassessmentRequest(JSON.stringify({ ...request, head_sha: 'bad' })),
    /invalid identity/);
  assert.throws(() => parseReviewReassessmentRequest(JSON.stringify({ ...request, request_stage: 'unknown' })),
    /invalid identity/);
});

test('source-owned reviewer reassessment supports stable generated lanes without merge authority', async () => {
  const request = {
    schema: 'maint71-review-reassessment/v1', repository: 'stranske/Ready', pr: 592,
    head_sha: 'a'.repeat(40), thread_id: 'PRRT_test', plan_id: 'plan-1',
    generation: 'gen-1', source_commit: 'b'.repeat(40),
    originating_reviewer: 'codex',
  };
  const record = {
    schema: 'sync-pr-delivery-record/v1', repository: request.repository,
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: request.plan_id, generation: request.generation,
    desired_tree_hash: 'tree-1',
    source_commit: request.source_commit, head_observed_sha: request.head_sha,
    head_observed_at: '2026-09-24T22:00:00Z',
    lease_expires_at: '2099-01-01T00:00:00Z',
  };
  const pr = {
    state: 'open', draft: false, auto_merge: null,
    user: { login: 'stranske-automation-bot' },
    head: { ref: 'deps/sync-dev-versions-test', sha: request.head_sha },
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
  };
  const thread = {
    id: request.thread_id, isResolved: false, isOutdated: false,
    comments: { pageInfo: { hasNextPage: false }, nodes: [
      { fullDatabaseId: '4294967297', author: { login: 'chatgpt-codex-connector[bot]' }, body: 'Please fix' },
    ] },
  };
  const comments = [];
  const tasks = [];
  let taskPosts = 0;
  let posts = 0;
  let merges = 0;
  let resolutions = 0;
  const github = {
    paginate: async () => tasks,
    rest: {
      pulls: {
        get: async () => ({ data: pr }),
        merge: async () => { merges++; },
        createReplyForReviewComment: async ({ body, comment_id }) => {
          assert.equal(comment_id, thread.comments.nodes[0].fullDatabaseId);
          posts++;
          const comment = { id: posts, body, created_at: '2026-09-24T22:00:00Z',
            html_url: `https://github.com/stranske/Ready/pull/592#discussion_r${posts}`,
            user: { login: 'stranske' } };
          comments.push(comment);
          return { data: comment };
        },
      },
      users: { getAuthenticated: async () => ({ data: { login: 'stranske' } }) },
      issues: {
        listComments: async () => { throw new Error('must inspect the original thread'); },
        createComment: async ({ body }) => {
          taskPosts++;
          const task = { id: taskPosts, body, created_at: '2026-09-24T22:02:00Z',
            html_url: `https://github.com/stranske/Ready/pull/592#issuecomment-${taskPosts}`,
            user: { login: 'stranske' } };
          tasks.push(task);
          return { data: task };
        },
      },
    },
    graphql: async (query) => {
      if (/\bmutation\b/.test(query)) resolutions++;
      return { repository: { pullRequest: {
        reviewThreads: { pageInfo: { hasNextPage: false }, nodes: [{
          ...thread, comments: { ...thread.comments, nodes: [
            ...thread.comments.nodes,
            ...comments.map((comment) => ({
              fullDatabaseId: String(comment.id), body: comment.body, author: comment.user,
              createdAt: comment.created_at, url: comment.html_url,
            })),
          ] },
        }] },
      } } };
    },
  };
  const args = { context: { eventName: 'repository_dispatch', ref: 'refs/heads/main',
    payload: { action: 'maint71-review-reassessment' }, actor: 'stranske' },
    withRetry: (fn) => fn(github), rawRequest: JSON.stringify(request),
    registeredRepos: [request.repository],
    policyPath: path.join(__dirname, '..', '..', '..', 'config', 'consumer_sync_review_policy.json') };
  const first = await runReviewReassessment(args);
  assert.equal(first.status, 'review_blocked_reassessment_requested');
  assert.equal(first.request_url, comments[0].html_url);
  assert.match(comments[0].body, /@codex please reassess this specific finding/);
  assert.match(comments[0].body, /PRRT_test/);
  assert.match(comments[0].body,
    new RegExp(`<!-- sync-review-accepted:${request.head_sha} -->`));
  const second = await runReviewReassessment(args);
  assert.equal(second.status, 'review_blocked_reassessment_reused');
  assert.equal(second.writer, 'stranske');
  assert.equal(posts, 1);
  assert.equal(taskPosts, 0, 'default reassessment cannot dispatch a top-level task');
  const reordered = Object.fromEntries(Object.entries(request).reverse());
  const reorderedRetry = await runReviewReassessment({
    ...args, rawRequest: JSON.stringify(reordered),
  });
  assert.equal(reorderedRetry.status, 'review_blocked_reassessment_reused');
  assert.equal(posts, 1, 'field ordering must not bypass idempotency');
  const originalGraphql = github.graphql;
  let raceReads = 0;
  github.graphql = async (query) => {
    const result = await originalGraphql(query);
    if (++raceReads === 1) {
      result.repository.pullRequest.reviewThreads.nodes[0].comments.nodes =
        [...thread.comments.nodes];
    }
    return result;
  };
  const racedRetry = await runReviewReassessment(args);
  assert.equal(racedRetry.status, 'review_blocked_reassessment_reused');
  assert.equal(posts, 1, 'a request appearing on the second read must suppress POST');
  github.graphql = originalGraphql;
  for (const branch of ['sync/workflows-candidate', 'sync/workflows-delivery']) {
    pr.head.ref = branch;
    comments.length = 0;
    const postsBeforeBranch = posts;
    const workflowSync = await runReviewReassessment(args);
    assert.equal(workflowSync.status, 'review_blocked_reassessment_requested');
    assert.equal(posts, postsBeforeBranch + 1);
    assert.equal(comments.length, 1);
    assert.match(comments[0].body, /@codex please reassess this specific finding/);
    assert.equal(merges, 0);
    assert.equal(resolutions, 0);
  }
  pr.head.ref = 'sync/workflows-untrusted';
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.head.ref = 'deps/sync-dev-versions-test';
  pr.head.sha = 'c'.repeat(40);
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.head.sha = request.head_sha;
  pr.body = `<!-- sync-pr-delivery-record:v1 ${JSON.stringify({
    ...record, plan_id: 'other-plan',
  })} -->`;
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.body = `<!-- sync-pr-delivery-record:v1 ${JSON.stringify({
    ...record, lease_expires_at: '2000-01-01T00:00:00Z',
  })} -->`;
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.body = `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`;
  await assert.rejects(runReviewReassessment({
    ...args,
    rawRequest: JSON.stringify({ ...request, thread_id: 'PRRT_missing' }),
  }), /absent or incomplete/);
  thread.comments.nodes[0].author.login = 'coderabbitai[bot]';
  await assert.rejects(runReviewReassessment(args), /origin does not match/);
  thread.comments.nodes[0].author.login = 'chatgpt-codex-connector[bot]';
  thread.isResolved = true;
  await assert.rejects(runReviewReassessment(args), /absent or incomplete/);
  thread.isResolved = false;
  const originalId = thread.comments.nodes[0].fullDatabaseId;
  delete thread.comments.nodes[0].fullDatabaseId;
  comments.length = 0;
  await assert.rejects(runReviewReassessment(args), /verified original comment ID/);
  thread.comments.nodes[0].fullDatabaseId = '9007199254740993';
  await runReviewReassessment(args);
  assert.match(comments[0].body, /No unrelated edits/);
  thread.comments.nodes[0].fullDatabaseId = originalId;
  comments[0].user.login = 'untrusted';
  await runReviewReassessment(args);
  assert.equal(posts, 5, 'an untrusted marker is not a prior request');
  const dispositionArgs = { ...args,
    rawRequest: JSON.stringify({ ...request, request_stage: 'disposition' }) };
  await assert.rejects(runReviewReassessment(dispositionArgs), /completed originating review/);
  const completed = { fullDatabaseId: '9000000001',
    author: { login: 'chatgpt-codex-connector' },
    commit: { oid: request.head_sha }, createdAt: '2026-09-24T22:01:00Z',
    body: "Codex Review: Didn't find any major issues.",
    url: 'https://github.com/stranske/Ready/pull/592#discussion_r9000000001' };
  thread.comments.nodes.push(completed);
  completed.commit.oid = 'c'.repeat(40);
  await assert.rejects(runReviewReassessment(dispositionArgs), /completed originating review/);
  completed.commit.oid = request.head_sha;
  completed.author.login = 'coderabbitai';
  await assert.rejects(runReviewReassessment(dispositionArgs), /completed originating review/);
  completed.author.login = 'chatgpt-codex-connector';
  let siblingTruncated = true;
  github.graphql = async (query) => {
    const result = await originalGraphql(query);
    const nodes = result.repository.pullRequest.reviewThreads.nodes;
    nodes[0].comments.nodes = nodes[0].comments.nodes.filter((item) =>
      item.fullDatabaseId !== completed.fullDatabaseId);
    nodes.push({ id: 'PRRT_sibling', isResolved: false, isOutdated: false,
      comments: { pageInfo: { hasNextPage: siblingTruncated }, nodes: [completed] } });
    return result;
  };
  await assert.rejects(runReviewReassessment(dispositionArgs), /inventory is incomplete/);
  siblingTruncated = false;
  const disposition = await runReviewReassessment(dispositionArgs);
  assert.equal(disposition.status, 'review_blocked_reassessment_requested');
  assert.match(comments.at(-1).body, /@codex address that feedback/);
  assert.match(comments.at(-1).body, /disposition-only task/);
  assert.match(comments.at(-1).body, /maint71-review-disposition:v1/);
  assert.equal(disposition.task_status, 'disposition_task_requested');
  assert.equal(taskPosts, 1);
  assert.match(tasks[0].body, /^@codex answer this specific finding on exact head/);
  assert.match(tasks[0].body, /maint71-disposition-task:v1 [a-f0-9]{64}/);
  assert.doesNotMatch(tasks[0].body, /review/i, 'cloud task entry must not repeat review-command text');
  assert.match(tasks[0].body, /A top-level answer cannot authorize disposition/);
  assert.ok(tasks[0].body.includes(comments.at(-1).html_url));
  const postsAfterDisposition = posts;
  const reusedTask = await runReviewReassessment(dispositionArgs);
  assert.equal(posts, postsAfterDisposition, 'disposition stage is independently idempotent');
  assert.equal(taskPosts, 1, 'already-posted inline request reuses the task bridge');
  assert.equal(reusedTask.task_status, 'disposition_task_reused');
  tasks[0].user = { login: 'untrusted' };
  await runReviewReassessment(dispositionArgs);
  assert.equal(taskPosts, 2, 'forged marker cannot suppress authenticated task');
  assert.equal(posts, postsAfterDisposition, 'bridge recovery never reposts inline request');
  tasks.push({ ...tasks[1], id: 100 });
  await assert.rejects(runReviewReassessment(dispositionArgs), /Duplicate bound disposition task/);
  tasks.pop();
  const originalPaginate = github.paginate;
  github.paginate = async () => null;
  await assert.rejects(runReviewReassessment(dispositionArgs), /task inventory is incomplete/);
  github.paginate = originalPaginate;
  tasks.length = 0;
  const tasksBeforeRace = taskPosts;
  github.paginate = async () => {
    pr.head.sha = 'e'.repeat(40);
    return [];
  };
  await assert.rejects(runReviewReassessment(dispositionArgs), /delivery changed or lease is invalid/);
  assert.equal(taskPosts, tasksBeforeRace, 'head changed during task inventory must prevent POST');
  pr.head.sha = request.head_sha;
  github.paginate = originalPaginate;
  const siblingGraphql = github.graphql;
  let bridgeReads = 0;
  github.graphql = async (query) => {
    const result = await siblingGraphql(query);
    if (++bridgeReads === 3) {
      const currentThread = result.repository.pullRequest.reviewThreads.nodes[0];
      currentThread.comments.nodes = currentThread.comments.nodes.filter((item) =>
        !String(item.body).includes('maint71-review-disposition:v1'));
    }
    return result;
  };
  await assert.rejects(runReviewReassessment(dispositionArgs), /in-thread disposition request changed/);
  assert.equal(taskPosts, tasksBeforeRace, 'deleted bound request must prevent task POST');
  github.graphql = siblingGraphql;
  const originalCreateTask = github.rest.issues.createComment;
  let uncertainTaskPosts = 0;
  github.rest.issues.createComment = async () => {
    uncertainTaskPosts++;
    throw new Error('connection reset after task write');
  };
  await assert.rejects(runReviewReassessment(dispositionArgs), /task POST uncertain/);
  assert.equal(uncertainTaskPosts, 1, 'ambiguous task POST must not be retried');
  github.rest.issues.createComment = originalCreateTask;
  github.graphql = originalGraphql;
  thread.comments.nodes.pop();
  comments.length = 0;
  await runReviewReassessment(args);
  github.paginate = async () => [...tasks, { user: { login: completed.author.login },
    body: `${completed.body}\n\n**Reviewed commit:** \`${request.head_sha.slice(0, 10)}\``,
    created_at: completed.createdAt }];
  github.rest.repos = { getCommit: async () => ({ data: { sha: 'c'.repeat(40) } }) };
  await assert.rejects(runReviewReassessment(dispositionArgs), /completed originating review/);
  github.rest.repos.getCommit = async () => ({ data: { sha: request.head_sha } });
  const topLevel = await runReviewReassessment(dispositionArgs);
  assert.equal(topLevel.status, 'review_blocked_reassessment_requested');
  github.paginate = async () => [];
  comments.length = 0;
  github.rest.pulls.createReplyForReviewComment = async () => {
    posts++;
    throw new Error('connection reset after write');
  };
  await assert.rejects(runReviewReassessment(args), /POST uncertain; inspect exact marker/);
  await assert.rejects(runReviewReassessment({ ...args,
    context: { ...args.context, ref: 'refs/heads/untrusted' } }), /trusted main-branch/);
  assert.equal(merges, 0, 'request-only reassessment must never merge');
  assert.equal(resolutions, 0, 'request-only reassessment must never resolve a thread');
});

test('exact-head reviewer request is durable, trusted, and idempotent', async () => {
  const headSha = 'd'.repeat(40);
  const record = {
    schema: 'sync-pr-delivery-record/v1',
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: `sha256:${'a'.repeat(64)}`, generation: 'gen-1',
    repository: 'stranske/Ready', desired_tree_hash: 'tree',
    source_commit: 'c'.repeat(40), head_observed_sha: headSha,
    head_observed_at: '2026-09-24T00:00:00Z',
    lease_expires_at: '2099-01-01T00:00:00Z', delivery_state: 'staging',
  };
  const pr = { number: 10, head: { sha: headSha } };
  const comments = [];
  let posts = 0;
  const github = { rest: {
    users: { getAuthenticated: async () => ({ data: { login: 'stranske' } }) },
    pulls: { get: async () => ({ data: {
      state: 'open', draft: false, auto_merge: null, head: { sha: headSha },
      body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
    } }) },
    issues: {
      listComments: async () => ({ data: comments }),
      createComment: async ({ body }) => {
        posts++;
        const comment = { id: posts, body, created_at: '2026-09-24T01:00:00Z',
          user: { login: 'stranske' } };
        comments.push(comment);
        return { data: comment };
      },
    },
  } };
  const args = { owner: 'stranske', repo: 'Ready', pr, record,
    reviewerProfiles: [{ id: 'codex', request_comment: '@codex review' }],
    trustedActors: ['stranske'], withRetry: (fn) => fn(github) };
  const first = await ensureExactHeadReviewRequest(args);
  assert.equal(first.reused, false);
  assert.equal(first.requestedAt, '2026-09-24T01:00:00Z');
  assert.equal(first.draft, false);
  assert.equal(first.autoMerge, false);
  assert.match(comments[0].body, /@codex review/);
  assert.match(comments[0].body, new RegExp(headSha));
  const retry = await ensureExactHeadReviewRequest(args);
  assert.equal(retry.reused, true);
  assert.equal(retry.id, first.id);
  assert.equal(posts, 1);
  let readinessReads = 0;
  github.rest.pulls.get = async () => ({ data: {
    state: 'open', draft: ++readinessReads > 1,
    auto_merge: readinessReads > 1 ? { enabled_at: '2026-09-24T01:00:00Z' } : null,
    head: { sha: headSha },
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
  } });
  const unready = await ensureExactHeadReviewRequest({ ...args, allowUnready: true });
  assert.equal(readinessReads, 2, 'readiness must be rechecked after comment pagination');
  assert.equal(unready.draft, true);
  assert.equal(unready.autoMerge, true);
  readinessReads = 0;
  github.rest.pulls.get = async () => ({ data: {
    state: 'open', draft: false, auto_merge: null,
    head: { sha: ++readinessReads > 1 ? 'rotated-head' : headSha },
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
  } });
  await assert.rejects(ensureExactHeadReviewRequest({ ...args, allowUnready: true }),
    /changed before exact-head/);
  github.rest.pulls.get = async () => ({ data: {
    state: 'open', draft: false, auto_merge: null, head: { sha: headSha },
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
  } });
  comments[0].user.login = 'untrusted';
  await ensureExactHeadReviewRequest(args);
  assert.equal(posts, 2, 'a forged marker must not authorize review settlement');
  comments[1].body = comments[1].body.replace('@codex review', 'review not requested');
  await ensureExactHeadReviewRequest(args);
  assert.equal(posts, 3, 'a marker without the configured request command must not count');
  github.rest.issues.listComments = async () => ({ data: null });
  await assert.rejects(ensureExactHeadReviewRequest(args), /Incomplete review-request comments/);
  github.rest.issues.listComments = async () => ({ data: comments });
  pr.head.sha = 'e'.repeat(40);
  await assert.rejects(ensureExactHeadReviewRequest(args), /changed before exact-head/);
});

test('review-thread evidence fails closed on missing, partial, or paginated responses', () => {
  const complete = {
    pageInfo: { hasNextPage: false },
    nodes: [{ isResolved: true, isOutdated: false }],
  };
  assert.equal(hasCompleteReviewThreadEvidence(complete), true);
  assert.equal(hasCompleteReviewThreadEvidence(null), false);
  assert.equal(hasCompleteReviewThreadEvidence({ ...complete, nodes: null }), false);
  assert.equal(hasCompleteReviewThreadEvidence({ ...complete, pageInfo: null }), false);
  assert.equal(hasCompleteReviewThreadEvidence({ ...complete, pageInfo: { hasNextPage: true } }), false);
  assert.equal(hasCompleteReviewThreadEvidence({ ...complete, nodes: [{}] }), false);
});

test('review GraphQL reads rotate separately while mutations remain owner-pinned', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'maint71_merge_sync_prs.js'), 'utf8');
  assert.match(source, /const withRetry = \(fn, options = \{\}\) => retryHelpers\.withRetry/);
  assert.match(source, /task: 'maint71-review-thread-read'/);
  assert.match(source, /preferredSource: 'SERVICE_BOT_PAT'/);
  assert.match(source, /rateResource: 'graphql'/);
  assert.match(source, /const data = await withReviewReadRetry\(\(client\) => client\.graphql\(/);
  assert.match(source, /withRetry: withReviewReadRetry,/);
  assert.match(source, /if \(reviewerEvidence\.truncated\) \{/);
  assert.match(source, /reason: 'reviewer_evidence_incomplete'/);
  assert.doesNotMatch(source, /await github\.graphql\(/);
  assert.match(source, /reason: 'review_thread_query_incomplete'/);
  assert.match(source, /sha: pr\.head\.sha/);
});

async function reportSelection(t, { syncHash, withRecord }) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-selection-'));
  t.after(() => fs.rmSync(tempDir, { recursive: true, force: true }));
  const reportPath = path.join(tempDir, 'report.json');
  const repository = 'stranske/Travel-Plan-Permission';
  const headSha = 'd'.repeat(40);
  const sourceCommit = 'c'.repeat(40);
  const observedAt = new Date().toISOString();
  const metadata = {
    schema: 'workflows-consumer-sync-pr/v1', consumer_repo: repository,
    plan_id: `sha256:${'a'.repeat(64)}`, plan_scope: 'full',
    source_commit: sourceCommit, source_sha: sourceCommit,
    template_hash: 'candidate-generation', sync_phase: 'canary',
  };
  const record = {
    schema: 'sync-pr-delivery-record/v1',
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: metadata.plan_id, generation: 'record-generation', repository,
    desired_tree_hash: 'tree-abc', source_commit: sourceCommit,
    head_observed_sha: headSha, head_observed_at: observedAt,
    lease_expires_at: '2099-08-14T00:00:00Z', predecessor_prs: [], successor_prs: [],
  };
  const candidate = {
    number: 1480, title: 'chore: sync workflow templates',
    body: `<!-- workflows-consumer-sync:v1 ${JSON.stringify(metadata)} -->` +
      (withRecord ? `\n<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->` : ''),
    created_at: observedAt, updated_at: observedAt, state: 'open',
    base: { ref: 'main' }, head: { ref: 'sync/workflows-candidate', sha: headSha },
    user: { login: 'stranske' },
  };
  // Expose read methods only: an unexpected mutation fails the test.
  const github = {
    paginate: async (_method, params) => params.state === 'open' ? [candidate] : [],
    rest: {
      pulls: { list: async () => ({ data: [candidate] }), get: async () => ({ data: candidate }) },
      git: { getCommit: async () => ({ data: { tree: { sha: 'tree-abc' } } }) },
    },
  };
  const logs = [];
  const failures = [];
  const warnings = [];
  t.mock.method(console, 'log', (...args) => logs.push(args.join(' ')));
  const retryHelpers = require('../github-api-with-retry.js');
  t.mock.method(retryHelpers, 'createTokenAwareRetry', async () => null);
  const core = {
    notice: () => {}, warning: (message) => warnings.push(message),
    setFailed: (message) => failures.push(message),
    summary: { addRaw: () => ({ write: async () => {} }) },
  };
  const env = {
    REGISTERED_REPOS_INPUT: repository, REPOS_INPUT: repository,
    CLEANUP_BRANCHES_INPUT: 'false', DRY_RUN_INPUT: 'true', AUTO_MERGE_INPUT: 'false',
    ACTIVE_SYNC_HASH_INPUT: syncHash, SYNC_HASH_INPUT: '',
    EXPECTED_PLAN_ID_INPUT: '', EXPECTED_PLAN_SCOPE_INPUT: '',
    EXPECTED_SCOPE_BASE_SHA_INPUT: '', EXPECTED_SOURCE_COMMIT_INPUT: '',
    OWNER_PR_PAT: 'test-owner-token', TRUSTED_SYNC_ACTORS: 'stranske',
    SYNC_PR_MERGE_REPORT_JSON: reportPath,
  };
  const originalEnv = Object.fromEntries(Object.keys(env).map((key) => [key, process.env[key]]));
  const originalCwd = process.cwd();
  try {
    Object.assign(process.env, env);
    process.chdir(tempDir);
    await run({
      github, core,
      context: { eventName: 'workflow_dispatch',
        repo: { owner: 'stranske', repo: 'Workflows' }, payload: {},
        runId: 71, runNumber: 71, workflow: 'Maint 71',
        ref: 'refs/heads/main', sha: sourceCommit },
    });
    assert.deepEqual(failures, []);
    assert.deepEqual(warnings, []);
    return { report: JSON.parse(fs.readFileSync(reportPath, 'utf8')), logs: logs.join('\n') };
  } finally {
    process.chdir(originalCwd);
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test('Maint 71 reports no_active_sync_pr when a valid candidate does not match the active hash', async (t) => {
  const { report, logs } = await reportSelection(t, { syncHash: 'expected-hash', withRecord: true });
  assert.equal(report.results.length, 1);
  const row = report.results[0];
  assert.equal(row.status, 'target_missing');
  assert.equal(row.delivery_reason, 'no_active_sync_pr');
  assert.equal(row.expected_branch, 'sync/workflows-expected-hash');
  assert.equal(row.active_sync_hash, 'expected-hash');
  assert.equal(row.open_sync_prs[0].number, 1480);
  assert.match(logs, /no_active_sync_pr \(expected sync\/workflows-expected-hash, active hash 'expected-hash'\)/);
  assert.doesNotMatch(logs, /missing_delivery_record/);
  assert.deepEqual(report.handoff_records, []);
});

test('Maint 71 reports missing_delivery_record for a selected candidate with no record', async (t) => {
  const { report, logs } = await reportSelection(t, { syncHash: '', withRecord: false });
  assert.equal(report.results.length, 1);
  assert.equal(report.results[0].status, 'delivery_contract_blocked');
  assert.equal(report.results[0].pr, 1480);
  assert.equal(report.results[0].delivery_reason, 'missing_delivery_record');
  assert.match(logs, /Delivery contract blocks merge: missing_delivery_record/);
  assert.doesNotMatch(logs, /no_active_sync_pr/);
  assert.deepEqual(report.handoff_records, []);
});

test('Maint 71 empty-hash dispatch still selects a candidate with a valid delivery record', async (t) => {
  const { report, logs } = await reportSelection(t, { syncHash: '', withRecord: true });
  assert.equal(report.results.length, 1);
  assert.equal(report.results[0].status, 'review_window_pending');
  assert.equal(report.results[0].pr, 1480);
  assert.doesNotMatch(JSON.stringify(report), /no_active_sync_pr|missing_delivery_record/);
  assert.doesNotMatch(logs, /no_active_sync_pr|missing_delivery_record/);
});


test('initial reviewer conversation task recovers an unanswered inline request once without merge authority', async () => {
  const request = { schema: 'maint71-review-reassessment/v1', repository: 'stranske/Ready', pr: 592,
    head_sha: 'a'.repeat(40), thread_id: 'PRRT_conversation', plan_id: 'plan-1',
    generation: 'gen-1', source_commit: 'b'.repeat(40), originating_reviewer: 'coderabbit' };
  const record = { schema: 'sync-pr-delivery-record/v1', repository: request.repository,
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836', plan_id: request.plan_id,
    generation: request.generation, source_commit: request.source_commit, desired_tree_hash: 'tree-1',
    lease_expires_at: '2099-01-01T00:00:00Z' };
  const prior = { fullDatabaseId: '22', author: { login: 'stranske' },
    createdAt: '2026-10-11T22:00:00Z', url: 'https://github.com/stranske/Ready/pull/592#discussion_r22',
    body: '<!-- maint71-review-reassessment:v1 ' + JSON.stringify(request) + ' -->' };
  const thread = { id: request.thread_id, isResolved: false, isOutdated: false,
    comments: { pageInfo: { hasNextPage: false }, nodes: [
      { fullDatabaseId: '21', author: { login: 'coderabbitai' }, body: 'Check the dependency group',
        commit: { oid: request.head_sha } }, prior] } };
  const pr = { state: 'open', draft: false, auto_merge: null, user: { login: 'stranske-automation-bot' },
    head: { ref: 'deps/sync-dev-versions-test', sha: request.head_sha },
    body: '<!-- sync-pr-delivery-record:v1 ' + JSON.stringify(record) + ' -->' };
  const tasks = [];
  let posts = 0, race = false, answerRace = false, pages = 0;
  const github = { paginate: async () => {
    if ((race || answerRace) && ++pages === 2) {
      if (race) pr.head.sha = 'c'.repeat(40);
      if (answerRace) thread.comments.nodes.push({ fullDatabaseId: '24', author: { login: 'coderabbitai' },
        createdAt: '2026-10-14T00:02:00Z', url: 'https://github.com/stranske/Ready/pull/592#discussion_r24',
        body: 'REJECT: evidence remains incomplete', commit: { oid: request.head_sha } });
    }
    return structuredClone(tasks);
  }, rest: {
    users: { getAuthenticated: async () => ({ data: { login: 'stranske' } }) },
    pulls: { get: async () => ({ data: structuredClone(pr) }),
      createReplyForReviewComment: async () => { throw new Error('must reuse the existing inline authority'); },
      merge: async () => { throw new Error('request-only task cannot merge'); } },
    issues: { createComment: async ({ body }) => {
      posts++;
      const item = { id: 100 + posts, user: { login: 'stranske' }, body,
        created_at: '2026-10-14T00:00:00Z',
        html_url: 'https://github.com/stranske/Ready/pull/592#issuecomment-' + (100 + posts) };
      tasks.push(item); return { data: item };
    } },
  }, graphql: async (query) => {
    assert.doesNotMatch(query, /resolveReviewThread/);
    return { repository: { pullRequest: { reviewThreads: {
      pageInfo: { hasNextPage: false }, nodes: [structuredClone(thread)] } } } };
  } };
  const args = { context: { eventName: 'repository_dispatch', ref: 'refs/heads/main', actor: 'stranske',
    payload: { action: 'maint71-review-reassessment' } }, withRetry: async (fn) => fn(github),
    rawRequest: JSON.stringify(request), registeredRepos: [request.repository],
    policyPath: path.join(__dirname, '../../../config/consumer_sync_review_policy.json') };
  const first = await runReviewReassessment(args);
  assert.equal(first.task_status, 'reassessment_task_requested');
  assert.equal(posts, 1);
  assert.match(tasks[0].body, /@coderabbitai please answer this specific finding/);
  assert.match(tasks[0].body, /discussion_r22/);
  assert.match(tasks[0].body, /No file edits/);
  assert.doesNotMatch(tasks[0].body, /full review/);
  const again = await runReviewReassessment(args);
  assert.equal(again.task_status, 'reassessment_task_reused');
  assert.equal(posts, 1);
  pr.head.sha = 'c'.repeat(40);
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.head.sha = request.head_sha;
  pr.body = '<!-- sync-pr-delivery-record:v1 ' + JSON.stringify({ ...record,
    lease_expires_at: '2000-01-01T00:00:00Z' }) + ' -->';
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.body = '<!-- sync-pr-delivery-record:v1 ' + JSON.stringify(record) + ' -->';
  tasks.length = 0;
  const answered = { fullDatabaseId: '23', author: { login: 'coderabbitai' },
    createdAt: '2026-10-14T00:01:00Z', url: 'https://github.com/stranske/Ready/pull/592#discussion_r23',
    body: `ACCEPT <!-- sync-review-accepted:${request.head_sha} -->`, commit: { oid: request.head_sha } };
  thread.comments.nodes.push(answered);
  const suppressed = await runReviewReassessment(args);
  assert.equal(suppressed.task_status, 'reassessment_task_suppressed_reviewer_answered');
  assert.equal(posts, 1, 'an exact-head originating reviewer answer suppresses task POST');
  thread.comments.nodes.pop();
  for (const control of [
    { ...answered, body: `> ACCEPT <!-- sync-review-accepted:${request.head_sha} -->` },
    { ...answered, author: { login: 'other-reviewer' } },
    { ...answered, createdAt: '2026-10-11T21:00:00Z' },
    { ...answered, commit: { oid: 'c'.repeat(40) } },
  ]) {
    tasks.length = 0;
    thread.comments.nodes.push(control);
    const delivered = await runReviewReassessment(args);
    assert.equal(delivered.task_status, 'reassessment_task_requested');
    thread.comments.nodes.pop();
  }
  tasks.length = 0; answerRace = true; pages = 0;
  const racedAnswer = await runReviewReassessment(args);
  assert.equal(racedAnswer.task_status, 'reassessment_task_suppressed_reviewer_answered');
  assert.equal(posts, 5, 'a response discovered during task pagination suppresses POST');
  thread.comments.nodes.pop(); answerRace = false;
  tasks.length = 0; race = true; pages = 0;
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  assert.equal(posts, 5, 'changed head during task discovery must suppress POST');
});

test('native conversation task marker is consumable by the consumer-bound verifier and REJECT reuses it', async () => {
  const { validateNativeConversationDisposition } = require('../maint71_finding_verification');
  const request = { schema: 'maint71-review-reassessment/v1', repository: 'stranske/Ready', pr: 9,
    head_sha: 'a'.repeat(40), thread_id: 'PRRT_native_e2e', plan_id: 'plan', generation: 'gen',
    source_commit: 'b'.repeat(40), originating_reviewer: 'coderabbit', request_stage: 'conversation-disposition' };
  const record = { schema: 'sync-pr-delivery-record/v1', repository: request.repository,
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836', plan_id: 'plan', generation: 'gen',
    source_commit: request.source_commit, desired_tree_hash: 'tree', lease_expires_at: '2099-01-01T00:00:00Z' };
  const origin = { fullDatabaseId: '41', author: { login: 'coderabbitai' }, body: 'Native finding', commit: { oid: request.head_sha } };
  // A v1 task from the same finding is historical evidence, not a reusable v2 task.
  const nodes = [origin], tasks = [{ id: 40, user: { login: 'stranske' }, author: { login: 'stranske' },
    body: '<!-- maint71-native-conversation-disposition:v1 ' + 'f'.repeat(64) + ' -->',
    created_at: '2026-10-14T02:59:00Z', createdAt: '2026-10-14T02:59:00Z',
    html_url: 'https://github.com/stranske/Ready/pull/9#issuecomment-40' }]; let replies = 0, taskPosts = 0, commentReads = [];
  const pr = { state: 'open', draft: false, auto_merge: null, user: { login: 'stranske-automation-bot' },
    head: { ref: 'sync/workflows-candidate', sha: request.head_sha }, body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->` };
  const github = { paginate: async () => structuredClone(tasks), rest: {
    users: { getAuthenticated: async () => ({ data: { login: 'stranske' } }) },
    pulls: { get: async () => ({ data: structuredClone(pr) }), createReplyForReviewComment: async ({ body }) => {
      replies++; const item = { id: 42, fullDatabaseId: '42', author: { login: 'stranske' }, user: { login: 'stranske' }, body,
        createdAt: '2026-10-14T03:00:00Z', created_at: '2026-10-14T03:00:00Z', url: 'https://api.github.com/repos/stranske/Ready/pulls/comments/42', html_url: 'https://github.com/stranske/Ready/pull/9#discussion_r42' };
      nodes.push({ ...item, url: item.html_url }); return { data: item };
    } },
    issues: { createComment: async ({ body }) => { taskPosts++; const item = { id: 43, user: { login: 'stranske' }, author: { login: 'stranske' }, body,
      created_at: '2026-10-14T03:01:00Z', createdAt: '2026-10-14T03:01:00Z', html_url: 'https://github.com/stranske/Ready/pull/9#issuecomment-43' }; tasks.push(item); return { data: item }; },
      getComment: async ({ owner, repo }) => { commentReads.push(`${owner}/${repo}`); return { data: {} }; } },
  }, graphql: async () => ({ repository: { pullRequest: { reviewThreads: { pageInfo: { hasNextPage: false }, nodes: [{ id: request.thread_id, isResolved: false, isOutdated: false, comments: { pageInfo: { hasNextPage: false }, nodes: structuredClone(nodes) } }] } } } }) };
  const policyPath = path.join(os.tmpdir(), `native-policy-${Date.now()}.json`); const policy = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../config/consumer_sync_review_policy.json'), 'utf8')); fs.writeFileSync(policyPath, JSON.stringify(policy));
  const args = { context: { eventName: 'repository_dispatch', ref: 'refs/heads/main', actor: 'stranske', payload: { action: 'maint71-review-reassessment' } }, withRetry: (fn) => fn(github), rawRequest: JSON.stringify(request), registeredRepos: [request.repository], policyPath };
  const result = await runReviewReassessment(args); assert.equal(replies, 1); assert.equal(taskPosts, 1);
  const v2Task = tasks.find((item) => /maint71-native-conversation-disposition:v2 [a-f0-9]{64}/.test(item.body));
  assert.ok(v2Task, 'a v1 task cannot satisfy a v2 request');
  assert.match(v2Task.body, /ordinary PR conversation reply is sufficient; an inline reply is not required/);
  assert.match(v2Task.body, /If the finding is not satisfied, reply with that exact @stranske line followed by standalone REJECT and concrete evidence; do not include an acceptance token or protocol marker/);
  assert.match(v2Task.body, /exactly equal to @stranske/);
  const marker = v2Task.body.match(/<!-- maint71-native-conversation-disposition:v2 [a-f0-9]{64} -->/)[0];
  const answer = { user: { login: 'coderabbitai' }, html_url: 'https://github.com/stranske/Ready/pull/9#issuecomment-44', created_at: '2026-10-14T03:02:00Z', body: `@stranske\nACCEPT\n<!-- sync-review-accepted:${request.head_sha} -->\n${marker}` };
  const verify = validateNativeConversationDisposition({ proof: { ...request, reviewer_acceptance_url: answer.html_url }, record,
    thread: { isResolved: false, comments: { nodes } }, threads: { pageInfo: { hasNextPage: false }, nodes: [{ comments: { pageInfo: { hasNextPage: false }, nodes } }] }, comment: answer, policy, reviewerProfiles: policy.reviewers, topLevelComments: { complete: true, nodes: tasks }, now: Date.parse('2026-10-14T03:03:00Z') });
  assert.equal(verify.ok, true); tasks.push({ user: { login: 'coderabbitai' }, author: { login: 'coderabbitai' }, body: `REJECT\n${marker}`, created_at: '2026-10-14T03:02:30Z' });
  await runReviewReassessment(args); assert.equal(taskPosts, 1); assert.equal(replies, 1); assert.equal(result.task_status, 'native-conversation-disposition_task_requested'); assert.deepEqual(commentReads, []); fs.rmSync(policyPath, { force: true });
});

function producerRun(overrides = {}) {
  return { id: 4068, event: 'workflow_dispatch', head_branch: 'main', head_sha: 'a'.repeat(40),
    display_title: `Maint 68 canary full source=${'a'.repeat(40)} candidates=stranske/Ready,stranske/Template dry=false`,
    status: 'completed', conclusion: 'success', created_at: new Date(refreshNow).toISOString(),
    ...overrides };
}

test('successful canary for SHA X suppresses the next refresh for SHA X', async () => {
  const api = refreshHarness({ actions: {
    listWorkflowRuns: async () => ({ data: { workflow_runs: [producerRun()] } }),
  } });
  const result = await refreshStableCanaries({ ...api,
    canaries: [refreshCanary({ check_status: 'checks_failed' })] });
  assert.equal(result.refresh_dispatched, 0, 'same-SHA successful canary must not dispatch again');
  assert.equal(api.dispatches.length, 0, 'same-SHA successful canary must not dispatch again');
  assert.match(api.summaries.join(''), /refresh: skipped \(delivery digest sha256:a{64} unchanged since a{40}\)/);
  assert.match(api.summaries.join(''), new RegExp(`debounce_ms=${CANARY_REFRESH_DEBOUNCE_MS}`));
});

test('new main SHA dispatches exactly once across held plans and subsequent observations', async () => {
  let runs = [producerRun({ head_sha: 'b'.repeat(40),
    display_title: producerRun().display_title.replace('a'.repeat(40), 'b'.repeat(40)) })];
  const api = refreshHarness({ actions: {
    listWorkflowRuns: async () => ({ data: { workflow_runs: runs } }),
  } });
  const canaries = [refreshCanary({ check_status: 'checks_failed' }),
    refreshCanary({ repo: 'Template', plan_id: 'another-plan', check_status: 'checks_failed' })];
  await refreshStableCanaries({ ...api, canaries });
  assert.equal(api.dispatches.length, 1);
  assert.equal(api.dispatches[0].inputs.scope_head_sha, 'a'.repeat(40));
  runs = [producerRun({ status: 'queued', conclusion: null }), ...runs];
  await refreshStableCanaries({ ...api, canaries });
  assert.equal(api.dispatches.length, 1, 'in-flight same-SHA run must debounce the next observer');
});

test('refresh identity includes the sorted candidate set, scope, source, branch and dry-run state', () => {
  const decide = (runs) => canaryRefreshDecision({ runs, sha: 'a'.repeat(40),
    candidates: ['stranske/Template', 'stranske/Ready'], now: refreshNow });
  assert.equal(decide([producerRun()]).eligible, false);
  assert.equal(decide([producerRun({ display_title: producerRun().display_title.replace(
    'stranske/Ready,stranske/Template', 'stranske/Template,stranske/Ready') })]).eligible, false);
  // A no-filter producer uses the configured set at the exact source SHA.
  assert.equal(decide([producerRun({ display_title: producerRun().display_title.replace(
    'stranske/Ready,stranske/Template', '*') })]).eligible, false);
  for (const run of [
    producerRun({ display_title: producerRun().display_title.replace(',stranske/Template', '') }),
    producerRun({ display_title: producerRun().display_title.replace('canary full', 'canary source-delta') }),
    producerRun({ display_title: producerRun().display_title.replace('dry=false', 'dry=true') }),
    producerRun({ display_title: producerRun().display_title.replace('a'.repeat(40), 'b'.repeat(40)) }),
    producerRun({ head_branch: 'feature' }),
  ]) assert.equal(decide([run]).eligible, true, run.display_title);
  assert.equal(decide([producerRun({ created_at: '2020-01-01T00:00:00Z' })]).eligible, false,
    'successful immutable evidence must not expire into another refresh');
  const failure = producerRun({ conclusion: 'failure',
    created_at: new Date(refreshNow - CANARY_REFRESH_DEBOUNCE_MS).toISOString() });
  assert.equal(decide([failure]).eligible, true);
  failure.created_at = new Date(refreshNow - CANARY_REFRESH_DEBOUNCE_MS + 1).toISOString();
  assert.equal(decide([failure]).eligible, false);
});

test('unreadable or truncated history and changed main configuration fail closed', async () => {
  for (const truncated of [false, true]) {
    const pages = [];
    const api = refreshHarness({ actions: { listWorkflowRuns: async ({ status, page }) => {
      if (page) pages.push(page);
      return { data: { workflow_runs: truncated
        ? status ? [] : Array(100).fill(producerRun({ conclusion: 'failure' })) : null } };
    } } });
    await assert.rejects(readCanaryRefreshState(api), truncated ? /history_truncated/ : /history_unreadable/);
    if (truncated) assert.deepEqual(pages, [1,2,3,4,5,6,7,8,9,10]);
    assert.equal(api.dispatches.length, 0);
  }
  const api = refreshHarness();
  await assert.rejects(readCanaryRefreshState({ ...api, expectedCanaries: ['stranske/Ready'] }),
    /configuration_changed/);
});

test('successful canary beyond page one still debounces refresh', async () => {
  const api = refreshHarness({ actions: { listWorkflowRuns: async ({ page, status }) => ({ data: {
    workflow_runs: status ? [] : page === 1
      ? Array(100).fill(producerRun({ conclusion: 'failure', created_at: '2020-01-01T00:00:00Z' }))
      : [producerRun()],
  } }) } });
  assert.equal((await readCanaryRefreshState(api)).state, 'success');
  assert.equal(api.dispatches.length, 0);
});

test('green exact-head evidence dispatches promote once and reports blocking and drainable quantities', async () => {
  const api = refreshHarness(), candidates = api.expectedCanaries;
  const evidence = { results: candidates.map((repo, i) => ({
    repo, plan_id: 'plan-green', source_commit: 'a'.repeat(40), head_sha: String(i + 1).repeat(40),
    plan_scope: 'full', scope_base_sha: '', evidence_source: 'no-change-canary',
    required_check_state: 'success', active_review_thread_count: 0,
  })) };
  const report = { inputs: { sync_hash: 'candidate', auto_merge: true, dry_run: false },
    results: evidence.results.map((row) => ({
      owner: row.repo.split('/')[0], repo: row.repo.split('/')[1], branch: 'sync/workflows-candidate',
      status: 'evidence_recovered', plan_id: row.plan_id, source_commit: row.source_commit, head_sha: row.head_sha,
    })) };
  // Promotion history is tied to the source date, rather than the retry window.
  const github = { rest: { repos: { getCommit: async () => ({ data: {
    commit: { committer: { date: '2026-10-17T00:00:00Z' } },
  } }) }, actions: {
    listWorkflowRuns: async () => ({ data: { workflow_runs: api.dispatches.length ? [{
      ...producerRun({ status: 'queued', conclusion: null }),
      display_title: `Maint 68 promote auto plan-green ${'a'.repeat(40)}`,
    }] : [] } }),
    createWorkflowDispatch: async (params) => api.dispatches.push(params),
  } } };
  const args = { report, evidence, ...api, withRetry: async (fn) => fn(github) };
  assert.equal((await dispatchCanaryPromotion(args)).status, 'dispatched');
  assert.equal((await dispatchCanaryPromotion(args)).status, 'waiting');
  assert.equal(api.dispatches.length, 1);
  assert.equal(api.dispatches[0].inputs.phase, 'promote');
  assert.match(api.summaries.join(''), /promote: blocked none; canaries green 2\/2; drainable 2/);
  const missing = { ...evidence, results: evidence.results.slice(0, 1) };
  assert.equal((await dispatchCanaryPromotion({ ...args, evidence: missing })).status, 'held');
  assert.match(api.summaries.join(''), /promote: blocked held: .*; canaries green 1\/2; drainable 1/);
});

for (const state of ['producer_success_red', 'producer_success_staging']) {
  test(`executor preserves lifecycle after ${state} without weakening consumer Gate`,
    async (t) => assertExecutorCanaryRefresh(t, state));
}

test('live no-change recovery preserves immutable report identity and reaches promotion',
  async (t) => assertExecutorCanaryRefresh(t, 'no_change'));

test('debounced successful producer still routes active manifest review debt upstream', async () => {
  const api = refreshHarness({ actions: {
    listWorkflowRuns: async () => ({ data: { workflow_runs: [producerRun()] } }),
  } });
  const state = await readCanaryRefreshState(api);
  const canary = refreshCanary({ refresh_state: state, active_review_thread_count: 1,
    threads: [{ id: 'PRRT_success', path: 'scripts/shared.js', isResolved: false, isOutdated: false,
      comments: { nodes: [{ url: 'https://github.com/stranske/Ready/pull/12#discussion_success' }] } }],
  });
  const result = await refreshStableCanaries({ ...api, refreshState: state, canaries: [canary] });
  assert.equal(result.refresh_dispatched, 0);
  assert.equal(result.review_blocked, 1);
  assert.equal(api.comments.length, 1, 'debounce must not lose source-owned review findings');
  assert.match(api.comments[0].body, /PRRT_success/);
});

test('an active promotion cannot erase prior producer success and restage its canaries', () => {
  const state = canaryRefreshDecision({ sha: 'a'.repeat(40),
    candidates: ['stranske/Ready', 'stranske/Template'], now: refreshNow,
    runs: [producerRun(), producerRun({ id: 4069, status: 'queued', conclusion: null,
      display_title: 'Maint 68 promote auto plan source' })],
  });
  assert.equal(state.eligible, false);
  assert.equal(state.state, 'writer-active');
  assert.equal(state.producer_succeeded, true);
  assert.equal(canaryNeedsRefresh(refreshCanary({ check_status: 'checks_failed',
    refresh_state: state }), refreshNow), null);
});


test('live default-branch drift re-arms once while the PR base and head stay fixed', async () => {
  let tip = 'b'.repeat(40);
  const head = 'c'.repeat(40);
  const keyFor = (value) => require('crypto').createHash('sha256')
    .update(`stranske/Ready:${value}:${head}`).digest('hex');
  const success = (key) => producerRun({
    display_title: `${producerRun().display_title} drift=${key}`,
  });
  let runs = [success(keyFor(tip))];
  const reads = [];
  const api = refreshHarness({
    repos: { getBranch: async (params) => {
      reads.push(params);
      return { data: { commit: { sha: tip } } };
    } },
    actions: { listWorkflowRuns: async () => ({ data: { workflow_runs: runs } }) },
  });
  const canary = refreshCanary({ mergeable_state: 'behind', base_sha: 'b'.repeat(40) });
  const refresh = () => refreshStableCanaries({ ...api, canaries: [canary] });
  await refresh();
  await refresh();
  assert.equal(api.dispatches.length, 0, 'success for T1 suppresses unchanged live tip');
  tip = 'd'.repeat(40);
  await refresh();
  assert.equal(api.dispatches.length, 1, 'new live tip T2 dispatches exactly once');
  assert.equal(api.dispatches[0].inputs.refresh_key, keyFor(tip));
  runs = [success(keyFor(tip))];
  await refresh();
  await refresh();
  assert.equal(api.dispatches.length, 1, 'success for T2 suppresses all repeats');
  assert.equal(canary.base_sha, 'b'.repeat(40), 'PR recorded base never moved');
  assert.equal(canary.head_sha, head, 'PR head never moved');
  assert.equal(reads.length, 5, 'one live branch read per behind canary per run');
  assert.ok(reads.every((row) => row.branch === 'trunk' && row.repo === 'Ready'));
  const consumerTipCache = new Map();
  await refreshStableCanaries({ ...api, consumerTipCache, canaries: [canary, { ...canary }] });
  assert.equal(reads.length, 6, 'multiple rows for a repo share a run-scoped read');
  await refreshStableCanaries({ ...api, canaries: [refreshCanary()] });
  assert.equal(reads.length, 6, 'healthy canary needs no live tip read');
  canary.head_sha = 'e'.repeat(40);
  runs = [producerRun({ status: 'queued', conclusion: null })];
  await refresh();
  assert.equal(api.dispatches.length, 1, 'active writer holds a new head identity');
  runs = [producerRun({ conclusion: 'failure' })];
  await refresh();
  assert.equal(api.dispatches.length, 1, 'recent failure holds a new head identity');
  runs = [success(keyFor(tip))];
  await refresh();
  assert.equal(api.dispatches.length, 2, 'new head re-arms independently of live tip');
});


test('executor refreshes a behind canary after same-source producer success',
  async (t) => assertExecutorCanaryRefresh(t, 'producer_success_behind'));

for (const failure of ['unreadable', 'invalid']) {
  test(`behind canary with ${failure} live tip fails closed and caches failure`, async () => {
    let reads = 0;
    const api = refreshHarness({ repos: { getBranch: async () => {
      reads++;
      if (failure === 'unreadable') throw new Error('branch unavailable');
      return { data: { commit: { sha: 'invalid' } } };
    } } });
    const canary = refreshCanary({ mergeable_state: 'behind' });
    const result = await refreshStableCanaries({ ...api, canaries: [canary, { ...canary }] });
    assert.equal(reads, 1);
    assert.equal(api.dispatches.length, 0);
    assert.equal(result.errors.length, 2);
    assert.ok(result.errors.every((error) => error.startsWith('canary_refresh_tip_unreadable:')));
    assert.equal(api.failures.length, 2);
  });
}

test('fallback receipt rejects old, wrong-head, wrong-branch and wrong-event runs', async t => {
  const api = sealedGateHarness(t);
  const client = { rest: { actions: {
    listWorkflowRuns: async ({ event }) => ({ data: { workflow_runs: event === 'pull_request' ? [] : [
      { ...api.run, event: 'workflow_dispatch', created_at: '2026-10-17T10:00:00Z' },
      { ...api.run, event: 'workflow_dispatch', head_sha: 'e'.repeat(40) },
      { ...api.run, event: 'workflow_dispatch', head_branch: 'main' },
      { ...api.run, created_at: new Date().toISOString() },
    ] } }),
    createWorkflowDispatch: async () => ({ status: 204 }),
  } } };
  const result = await requestSealedGate({ ...api.args, sealedAt: undefined,
    withRetry: callback => callback(client) });
  assert.equal(result.run_id, null);
  assert.match(result.reason, /not observed/);
  assert.ok(api.logs.every(line => !line.includes('gate requested run=')));
});

test('completed evaluation after the seal is not rerun even when it failed', async t => {
  const api = sealedGateHarness(t);
  api.state.runs = [{ ...api.run, run_started_at: '2026-10-17T11:01:00Z' }];
  assert.deepEqual(await requestSealedGate(api.args), { mode: 'existing', run_id: 4105 });
  assert.equal(api.reruns.length, 0);
});

test('main moves with unchanged rendered delivery digest: no canary regeneration', async t => {
  t.mock.method(deliveryPayload, 'readDeliveryPayload', async (sha, repos) => ({
    digest: `sha256:${'f'.repeat(64)}`, files: Object.fromEntries(repos.map(repo => [repo, {}])),
  }));
  const oldSource = 'b'.repeat(40);
  const api = refreshHarness({ actions: { listWorkflowRuns: async () => ({ data: {
    workflow_runs: [producerRun({ head_sha: oldSource,
      display_title: producerRun().display_title.replace('a'.repeat(40), oldSource) })],
  } }) } });
  const result = await refreshStableCanaries({ ...api,
    canaries: [refreshCanary({ source_commit: oldSource, check_status: 'checks_failed' })] });
  assert.equal(result.refresh_dispatched, 0, 'unchanged digest must preserve the in-flight canary');
  assert.equal(api.dispatches.length, 0);
  assert.match(api.summaries.join(''), /delivery digest sha256:f{64} unchanged since b{40}/);
});

function sealedRefreshFixture(t) {
  const repository = 'stranske/Ready', oldSource = 'b'.repeat(40), head = 'c'.repeat(40);
  const { formatDeliveryRecord, parseDeliveryRecord } = require('../sync_pr_lease_contract');
  const record = { repository, durable_issue_url: 'https://github.com/stranske/Workflows/issues/4110',
    plan_id: 'old-plan', generation: 'old-generation', desired_tree_hash: 'old-tree',
    source_commit: oldSource, head_observed_sha: head,
    head_observed_at: new Date(refreshNow - 30 * 60000).toISOString(),
    delivery_state: 'sealed', sealed_head_sha: head,
    sealed_at: new Date(refreshNow - 30 * 60000).toISOString(),
    review_started_at: new Date(refreshNow - 40 * 60000).toISOString(),
    lease_expires_at: '2099-01-01T00:00:00Z' };
  const pr = { number: 12, state: 'open', head: { ref: 'sync/workflows-candidate', sha: head },
    body: formatDeliveryRecord(record), changed_files: 1 };
  const gate = { id: 4110, event: 'pull_request', head_sha: head, status: 'in_progress',
    created_at: new Date(refreshNow - 10 * 60000).toISOString(), run_attempt: 2 };
  const api = refreshHarness();
  const state = () => ({ sha: 'a'.repeat(40), candidates: [repository], eligible: true,
    delivery_digest: `sha256:${'a'.repeat(64)}` });
  const payload = { digest: state().delivery_digest, files: { [repository]: {
    'new-file.js': { content: 'new' }, 'reviewed.js': { content: 'stable' },
  } } };
  t.mock.method(deliveryPayload, 'readDeliveryPayload', async () => ({
    digest: `sha256:${'b'.repeat(64)}`, files: { [repository]: {
      'new-file.js': { content: 'old' }, 'reviewed.js': { content: 'stable' },
    } },
  }));
  const files = [{ filename: 'reviewed.js' }];
  const withRetry = async fn => fn({ rest: {
    pulls: { list: async () => ({ data: pr.state === 'open' ? [pr] : [] }),
      get: async () => ({ data: pr }), listFiles: async () => ({ data: files }) },
    actions: { listWorkflowRuns: async () => ({ data: { workflow_runs: [gate] } }),
      createWorkflowDispatch: async params => api.dispatches.push(params) },
  } });
  return { api, pr, record, gate, files, payload, state, withRetry, parseDeliveryRecord,
    decide: async (now = refreshNow) => deferSealedCanaryRefresh({ state: state(), payload, withRetry, now }) };
}

test('changed delivered file while sealed queues refresh, then applies after merge or bounded wait', async t => {
  const f = sealedRefreshFixture(t);
  const body = f.pr.body;
  const queued = await f.decide();
  assert.equal(queued.eligible, false);
  assert.match(queued.queue_reason, /sealed cycle stranske\/Ready@c{40}/);
  await dispatchCanaryRefresh({ ...f.api, withRetry: f.withRetry, refreshState: queued });
  assert.equal(f.api.dispatches.length, 0);
  assert.equal(f.pr.body, body, 'queueing must not restage, rewrite the source, or invalidate the seal');
  assert.equal(f.parseDeliveryRecord(f.pr.body).sealed_head_sha, f.pr.head.sha);
  for (const terminal of ['merged', 'failed', 'expired']) {
    f.pr.state = terminal === 'merged' ? 'closed' : 'open';
    f.gate.status = terminal === 'failed' ? 'completed' : 'in_progress';
    f.gate.conclusion = terminal === 'failed' ? 'failure' : null;
    const now = terminal === 'expired' ? Date.parse(f.record.sealed_at) + CANARY_SEALED_REFRESH_WAIT_MS : refreshNow;
    const ready = await f.decide(now);
    assert.equal(ready.eligible, true, terminal);
    await dispatchCanaryRefresh({ ...f.api, withRetry: f.withRetry, refreshState: ready, now });
  }
  assert.equal(f.api.dispatches.length, 3);
  assert.match(f.api.summaries.join(''), /refresh: queued/);
});

test('overlap with the canary diff refreshes immediately, including renamed/deleted targets', async t => {
  const f = sealedRefreshFixture(t);
  for (const row of [{ filename: 'new-file.js' },
    { filename: 'reviewed.js', previous_filename: 'new-file.js' }]) {
    f.files[0] = row;
    assert.equal((await f.decide()).eligible, true);
  }
  f.payload.files['stranske/Ready'] = { 'reviewed.js': { content: 'stable' } };
  f.files[0] = { filename: 'new-file.js' };
  assert.equal((await f.decide()).eligible, true);
});

test('identical digest across SHAs preserves the exact-head seal even beyond the queue bound', async t => {
  const f = sealedRefreshFixture(t);
  t.mock.method(deliveryPayload, 'readDeliveryPayload', async () => f.payload);
  const body = f.pr.body;
  const state = await f.decide(refreshNow + CANARY_SEALED_REFRESH_WAIT_MS * 3);
  assert.equal(state.eligible, false);
  assert.equal(state.producer_succeeded, true);
  assert.equal(state.unchanged_since, f.record.source_commit);
  assert.equal(f.pr.body, body);
  assert.equal(f.parseDeliveryRecord(f.pr.body).sealed_head_sha, f.pr.head.sha);
});

test('pre-seal Gate failure does not release a queued refresh; unreadable diff fails closed', async t => {
  const f = sealedRefreshFixture(t);
  f.gate.status = 'completed'; f.gate.conclusion = 'failure';
  f.gate.created_at = f.record.sealed_at; f.gate.run_attempt = 1;
  assert.equal((await f.decide()).eligible, false);
  f.pr.changed_files = 2;
  await assert.rejects(f.decide(), /diff_incomplete/);
});

test('a historical identical payload cannot suppress redelivery after a different payload won', () => {
  const old = producerRun({ id: 1, delivery_digest: `sha256:${'a'.repeat(64)}` });
  const newer = producerRun({ id: 2, head_sha: 'b'.repeat(40), delivery_digest: `sha256:${'b'.repeat(64)}`,
    display_title: producerRun().display_title.replace('a'.repeat(40), 'b'.repeat(40)) });
  assert.equal(canaryRefreshDecision({ sha: 'c'.repeat(40), candidates: ['stranske/Ready', 'stranske/Template'],
    deliveryDigest: old.delivery_digest, runs: [newer, old], now: refreshNow }).eligible, true);
});

test('producer success after a queued refresh is not a delivered-digest receipt', async () => {
  const api = refreshHarness();
  const guarded = producerRun({ display_title: `${producerRun().display_title} guard=delivery-v1` });
  const reads = [];
  const withRetry = async fn => fn({ rest: {
    repos: { getCommit: async () => ({ data: { sha: 'a'.repeat(40) } }),
      getContent: async () => ({ data: { content: Buffer.from(JSON.stringify({
        canaries: api.expectedCanaries.map(repo => ({ repo })),
      })).toString('base64') } }) },
    pulls: { list: async () => ({ data: [] }) },
    actions: { listWorkflowRuns: async ({ status }) => ({ data: { workflow_runs: status ? [] : [guarded] } }),
      listJobsForWorkflowRun: () => {} },
  }, paginate: async (method, params) => { reads.push(params); return [
    { steps: [{ name: 'Authorize canary payload mutation', conclusion: 'skipped' }] },
  ]; } });
  assert.equal((await readCanaryRefreshState({ ...api, withRetry })).eligible, true);
  assert.equal(reads.length, 1);
});


test('pinned payload receipt survives main moving between refresh decision and workflow dispatch', async () => {
  const api = refreshHarness({ actions: { listWorkflowRuns: async () => ({ data: {
    workflow_runs: [producerRun({ head_sha: 'b'.repeat(40) })],
  } }) } });
  const state = await readCanaryRefreshState(api);
  assert.equal(state.producer_succeeded, true);
  assert.equal(state.eligible, false);
  assert.equal(state.unchanged_since, 'a'.repeat(40));
});
