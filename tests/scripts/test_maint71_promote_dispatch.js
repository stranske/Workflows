'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const {
  buildCanaryPromotionEvidence, dispatchCanaryPromotion,
  sealedPromotionHealth, reportSealedPromotionHealth, publishPromotionHealthCheck,
} = require('../../.github/scripts/maint71_merge_sync_prs');
const { formatDeliveryRecord } = require('../../.github/scripts/sync_pr_lease_contract');
const expectedCanaries = require('../../config/consumer_sync_canaries.json').canaries.map((row) => row.repo);
const planId = `sha256:${'a'.repeat(64)}`;
const sourceCommit = 'b'.repeat(40);
const now = Date.parse('2026-10-16T12:00:00Z');
const context = { repo: { owner: 'stranske', repo: 'Workflows' },
  payload: { repository: { default_branch: 'main' } } };

function fixture(status = 'campaign_prepared') {
  const rows = expectedCanaries.map((repo, index) => ({
    repo, plan_id: planId, plan_scope: 'full', scope_base_sha: '',
    source_commit: sourceCommit, head_sha: String(index + 1).repeat(40), pr: index + 1,
    evidence_source: status === 'merged' ? 'merged-candidate-recovery' : 'open-candidate',
    required_check_state: 'success', active_review_thread_count: 0,
  }));
  return { evidence: { results: rows }, expectedCanaries,
    report: { inputs: { sync_hash: 'candidate', auto_merge: true, dry_run: false },
      results: rows.map((row) => ({
        owner: row.repo.split('/')[0], repo: row.repo.split('/')[1],
        branch: 'sync/workflows-candidate', status, pr: row.pr,
        plan_id: row.plan_id, source_commit: row.source_commit, head_sha: row.head_sha,
      })) } };
}

function harness(runs = []) {
  const dispatched = [], summaries = [], reads = [];
  const client = { rest: {
    repos: { getCommit: async () => ({ data: { commit: { committer: { date: '2026-10-01T00:00:00Z' } } } }) },
    actions: {
      listWorkflowRuns: async (params) => {
        reads.push(params);
        return { data: { workflow_runs: typeof runs === 'function' ? runs(params) : runs } };
      },
      createWorkflowDispatch: async (params) => { dispatched.push(params); },
    },
  } };
  const core = { notice() {}, setOutput() {},
    summary: { addRaw(text) { summaries.push(text); return this; }, async write() {} } };
  return { dispatched, summaries, reads, client, context, core,
    withRetry: async (fn) => fn(client) };
}

function promotionRun(overrides = {}) {
  return { id: 10, event: 'workflow_dispatch', head_branch: 'main',
    display_title: `Maint 68 promote auto ${planId} ${sourceCommit}`,
    status: 'completed', conclusion: 'success', html_url: 'https://example.test/run/10', ...overrides };
}

function candidate(sealedAt = '2026-10-14T11:00:00Z', repo = expectedCanaries[0]) {
  return { number: 1, state: 'open', user: { login: 'stranske-automation-bot' },
    head: { ref: 'sync/workflows-candidate', sha: 'c'.repeat(40) },
    body: formatDeliveryRecord({
      schema: 'sync-pr-delivery-record/v1', repository: repo,
      durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
      plan_id: planId, source_commit: sourceCommit, generation: 'gen', desired_tree_hash: 'tree',
      lease_expires_at: '2026-11-01T00:00:00Z', delivery_state: 'sealed',
      sealed_at: sealedAt, sealed_head_sha: 'c'.repeat(40), review_started_at: sealedAt,
    }) };
}

for (const status of ['merged', 'campaign_prepared', 'evidence_recovered']) {
  test(`all canaries ${status} dispatch correct plan-bound evidence`, async () => {
    const args = fixture(status), api = harness();
    const built = buildCanaryPromotionEvidence(args.evidence.results, expectedCanaries);
    assert.equal(built.ok, true, built.errors.join(', '));
    // This assertion must name the missing key in the required mutation proof.
    for (const row of built.evidence.results) assert.equal(row.plan_id, planId, 'missing key: plan_id');
    assert.equal((await dispatchCanaryPromotion({ ...args, ...api })).status, 'dispatched');
    assert.equal(api.dispatched.length, 1);
    assert.deepEqual(api.dispatched[0], {
      owner: 'stranske', repo: 'Workflows', workflow_id: 'maint-68-sync-consumer-repos.yml', ref: 'main',
      inputs: { phase: 'promote', delivery_scope: 'auto', dry_run: 'false', force: 'false',
        canary_evidence_json: JSON.stringify(built.evidence) },
    });
    assert.match(api.summaries.join(''), /dispatched.*completion awaits a successful Maint 68 run/);
    assert.equal(api.reads[0].created, '>=2026-10-01T00:00:00Z');
  });
}

test('one canary missing holds dispatch and records why', async () => {
  const args = fixture(), api = harness();
  args.evidence.results.pop();
  const result = await dispatchCanaryPromotion({ ...args, ...api });
  assert.equal(result.status, 'held');
  assert.match(result.errors.join(','), /missing_canary_evidence/);
  assert.equal(api.dispatched.length, 0);
  assert.equal(api.reads.length, 0);
});

test('every row must carry plan_id and the same immutable source', async () => {
  for (const change of [
    (rows) => { delete rows[1].plan_id; },
    (rows) => { rows[1].plan_id = 'other'; },
    (rows) => { delete rows[1].source_commit; },
    (rows) => { rows[1].source_commit = 'd'.repeat(40); },
    (rows) => { rows[1].required_check_state = 'failure'; },
    (rows) => { rows[1].active_review_thread_count = 1; },
    (rows) => { rows.push(rows[0]); },
  ]) {
    const args = fixture(), api = harness();
    change(args.evidence.results);
    assert.equal((await dispatchCanaryPromotion({ ...args, ...api })).status, 'held');
    assert.equal(api.dispatched.length, 0);
  }
});

for (const invalidPlanId of [42, true, ['plan'], { plan: 'plan' }]) {
  test(`non-string plan_id ${JSON.stringify(invalidPlanId)} holds dispatch before API calls`, async () => {
    const args = fixture(), api = harness();
    for (const row of args.evidence.results) row.plan_id = invalidPlanId;
    const built = buildCanaryPromotionEvidence(args.evidence.results, expectedCanaries);
    assert.equal(built.ok, false, 'plan_id must be a string as required by the Maint 68 jq filter');
    for (const repo of expectedCanaries) {
      assert.ok(built.errors.includes(`invalid_plan_id:${repo}`));
    }
    const result = await dispatchCanaryPromotion({ ...args, ...api });
    assert.equal(result.status, 'held');
    assert.match(result.errors.join(','), /invalid_plan_id/);
    assert.equal(api.dispatched.length, 0);
    assert.equal(api.reads.length, 0);
  });
}

test('unprepared, changed merged identity, and disabled mutation cannot dispatch', async () => {
  for (const change of [
    (args) => { args.report.results[0].status = 'checks_pending'; },
    (args) => { args.report.results[0].status = 'merged'; args.report.results[0].head_sha = 'changed'; },
    (args) => { args.report.inputs.dry_run = true; },
    (args) => { args.report.inputs.auto_merge = false; },
  ]) {
    const args = fixture(), api = harness();
    change(args);
    assert.equal((await dispatchCanaryPromotion({ ...args, ...api })).status, 'held');
    assert.equal(api.dispatched.length, 0);
  }
});

for (const [run, status] of [
  [promotionRun(), 'already-promoted'],
  [promotionRun({ status: 'queued', conclusion: null }), 'waiting'],
  [promotionRun({ status: 'waiting', conclusion: null }), 'waiting'],
  [promotionRun({ conclusion: 'failure' }), 'dispatched'],
  [promotionRun({ display_title: `Maint 68 promote auto other ${sourceCommit}` }), 'dispatched'],
  [promotionRun({ head_branch: 'untrusted-branch' }), 'dispatched'],
]) {
  test(`promotion ${run.status}/${run.conclusion}/${run.head_branch}/${run.display_title} -> ${status}`, async () => {
    const api = harness([run]);
    assert.equal((await dispatchCanaryPromotion({ ...fixture(), ...api })).status, status);
    assert.equal(api.dispatched.length, status === 'dispatched' ? 1 : 0);
    assert.ok(api.summaries.length);
  });
}

test('dispatch API failure propagates; no false success summary', async () => {
  const api = harness();
  api.client.rest.actions.createWorkflowDispatch = async () => { throw new Error('dispatch denied'); };
  await assert.rejects(dispatchCanaryPromotion({ ...fixture(), ...api }), /dispatch denied/);
  assert.equal(api.summaries.length, 0);
});

test('workflow-run history is paginated and fails closed at GitHub search cap', async () => {
  const other = promotionRun({ conclusion: 'failure' });
  const api = harness(({ page }) => page === 1 ? Array(100).fill(other) : [promotionRun()]);
  assert.equal((await dispatchCanaryPromotion({ ...fixture(), ...api })).status, 'already-promoted');
  assert.equal(api.reads.length, 2);
  const truncated = harness(() => Array(100).fill(other));
  await assert.rejects(dispatchCanaryPromotion({ ...fixture(), ...truncated }), /history_truncated/);
  assert.equal(truncated.dispatched.length, 0);
});

test('snapshot expected jq keys and run the actual Maint 68 evidence parser', () => {
  const built = buildCanaryPromotionEvidence(fixture().evidence.results, expectedCanaries);
  assert.deepEqual(Object.keys(built.evidence.results[0]).sort(), [
    'active_review_thread_count', 'evidence_source', 'head_sha', 'plan_id', 'plan_scope',
    'pr', 'repo', 'required_check_state', 'scope_base_sha', 'source_commit',
  ]);
  const workflow = fs.readFileSync('.github/workflows/maint-68-sync-consumer-repos.yml', 'utf8');
  const shell = workflow.split('      - name: Resolve immutable plan scope')[1]
    .split('        run: |\n')[1].split('\n      - name: Checkout')[0]
    .split('\n').map((line) => line.slice(10)).join('\n');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-jq-'));
  try {
    const parse = (evidence) => spawnSync('bash', ['-c', shell], { encoding: 'utf8', env: {
      ...process.env, REQUESTED_SCOPE: 'auto', INPUT_BASE_SHA: '', INPUT_HEAD_SHA: '',
      REQUESTED_PHASE: 'promote', CANARY_EVIDENCE_JSON: JSON.stringify(evidence),
      GITHUB_OUTPUT: path.join(dir, 'output'), GITHUB_SHA: 'e'.repeat(40),
    } });
    for (const evidence of [built.evidence, built.evidence.results]) {
      const result = parse(evidence);
      assert.equal(result.status, 0, result.stderr + result.stdout);
      assert.match(result.stdout, /Plan scope: full/);
      assert.match(result.stdout, new RegExp(`Source commit: ${sourceCommit}`));
    }
    const delta = structuredClone(built.evidence);
    for (const row of delta.results) { row.plan_scope = 'source-delta'; row.scope_base_sha = 'f'.repeat(40); }
    const result = parse(delta);
    assert.equal(result.status, 0, result.stderr + result.stdout);
    assert.match(result.stdout, /Plan scope: source-delta/);
    const missing = structuredClone(built.evidence);
    delete missing.results[1].plan_id;
    assert.notEqual(parse(missing).status, 0, 'jq must reject missing key: plan_id');
    for (const invalidPlanId of [42, true, ['plan'], { plan: 'plan' }]) {
      const invalid = structuredClone(built.evidence);
      for (const row of invalid.results) row.plan_id = invalidPlanId;
      const rejected = parse(invalid);
      assert.notEqual(rejected.status, 0, 'jq must reject non-string plan_id');
      assert.match(rejected.stdout + rejected.stderr, /Promotion evidence missing or mixed plan_id/);
    }
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('health deduplicates a plan and fails only beyond 48 h; successful exact promotion clears it', () => {
  const candidates = expectedCanaries.map((repo) => candidate('2026-10-14T11:00:00Z', repo));
  const health = sealedPromotionHealth({ candidates, now });
  assert.equal(health.overdue, true);
  assert.equal(health.line, 'plans sealed awaiting promotion: 1, oldest: 49.0 h');
  assert.equal(sealedPromotionHealth({ candidates, now: now - 3600000 }).overdue, false);
  for (const run of [promotionRun({ conclusion: 'failure' }), promotionRun({ status: 'in_progress' }),
    promotionRun({ display_title: `Maint 68 promote auto ${planId} ${'e'.repeat(40)}` })]) {
    assert.equal(sealedPromotionHealth({ candidates, runs: [run], now }).overdue, true);
  }
  assert.equal(sealedPromotionHealth({ candidates, runs: [promotionRun()], now }).line,
    'plans sealed awaiting promotion: 0, oldest: n/a');
});

test('health observes current trusted candidates, ignores superseded and untrusted attempts', async () => {
  const api = harness([promotionRun()]), calls = [];
  api.client.rest.pulls = { list: async (params) => {
    calls.push(params);
    return { data: [candidate('2026-10-14T11:00:00Z', `${params.owner}/${params.repo}`),
      { ...candidate(), state: 'closed', merged_at: null },
      { ...candidate(), user: { login: 'untrusted' } }] };
  } };
  const health = await reportSealedPromotionHealth({ ...api, expectedCanaries, now });
  assert.equal(health.pending.length, 0);
  assert.equal(calls.length, expectedCanaries.length);
  assert.match(api.summaries.join(''), /plans sealed awaiting promotion: 0/);
});

test('health API failures cannot produce a measured zero', async () => {
  const api = harness();
  api.client.rest.pulls = { list: async () => { throw new Error('read denied'); } };
  await assert.rejects(reportSealedPromotionHealth({ ...api, expectedCanaries, now }), /read denied/);
  assert.equal(api.summaries.length, 0);
});

test('health-71 fails independently so an overdue recovery promotion can succeed', async () => {
  const checks = [];
  const github = { rest: { checks: { create: async (params) => { checks.push(params); } } } };
  const runContext = { ...context, sha: sourceCommit, runId: 123, runAttempt: 1 };
  for (const [health, conclusion] of [
    [{ overdue: false, line: 'plans sealed awaiting promotion: 0, oldest: n/a' }, 'success'],
    [{ overdue: true, line: 'plans sealed awaiting promotion: 1, oldest: 49.0 h' }, 'failure'],
    [{ state: 'unknown', line: 'plans sealed awaiting promotion: UNKNOWN' }, 'failure'],
    [undefined, 'failure'],
  ]) {
    // A failed check is a returned API result, not an exception or setFailed on
    // the promotion job: the recovery run can therefore earn its success receipt.
    await publishPromotionHealthCheck({ github, context: runContext, health });
    assert.equal(checks.at(-1).conclusion, conclusion);
    assert.equal(checks.at(-1).name, 'health-71');
    assert.equal(checks.at(-1).head_sha, sourceCommit);
    assert.equal(checks.at(-1).status, 'completed');
  }
  const workflow = fs.readFileSync('.github/workflows/maint-68-sync-consumer-repos.yml', 'utf8');
  const summaryJob = workflow.split('  summary:\n')[1].split('  continue-delivery:\n')[0];
  assert.match(summaryJob, /checks: write/);
  assert.match(summaryJob, /github-token: \$\{\{ github.token \}\}/);
  assert.match(summaryJob, /await publishPromotionHealthCheck\(\{ github, context, health \}\)/);
});

test('live-verified no-change canary evidence remains eligible without a PR', async () => {
  const args = fixture(), api = harness();
  args.evidence.results[0].evidence_source = 'no-change-canary';
  delete args.evidence.results[0].pr;
  args.report.results[0].status = 'evidence_recovered';
  delete args.report.results[0].pr;
  assert.equal((await dispatchCanaryPromotion({ ...args, ...api })).status, 'dispatched');
  assert.equal(JSON.parse(api.dispatched[0].inputs.canary_evidence_json).results[0].evidence_source,
    'no-change-canary');
});

test('source-delta dispatch preserves the exact range in every evidence row', async () => {
  const args = fixture(), api = harness();
  for (const row of args.evidence.results) {
    row.plan_scope = 'source-delta';
    row.scope_base_sha = 'f'.repeat(40);
  }
  assert.equal((await dispatchCanaryPromotion({ ...args, ...api })).status, 'dispatched');
  const dispatched = JSON.parse(api.dispatched[0].inputs.canary_evidence_json);
  for (const row of dispatched.results) {
    assert.equal(row.plan_scope, 'source-delta');
    assert.equal(row.scope_base_sha, 'f'.repeat(40));
    assert.equal(row.source_commit, sourceCommit);
  }
});
