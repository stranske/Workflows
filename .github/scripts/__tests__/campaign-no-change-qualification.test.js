'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { run, dispatchCanaryPromotion } = require('../maint71_merge_sync_prs');
const { buildCampaignCommitAuthorization, campaignAuthorizationAllowsMerge } = require('../sync_pr_merge_contract');
const retry = require('../github-api-with-retry');
const canaries = ['owner/canary1', 'owner/canary2', 'owner/canary3'];
const deliveries = Array.from({ length: 13 }, (_, i) => `owner/delivery${i + 1}`);
const source = 'a'.repeat(40), base = 'b'.repeat(40), plan = `sha256:${'c'.repeat(64)}`;
const head = repo => Buffer.from(repo).toString('hex').padEnd(40, '0').slice(0, 40);
const checked = repo => Buffer.from(`pr${repo}`).toString('hex').padEnd(40, '0').slice(0, 40);
function harness(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'campaign-nochange-'));
  const cwd = process.cwd(), originalEnv = { ...process.env };
  t.after(() => { process.chdir(cwd); for (const key of Object.keys(process.env)) if (!(key in originalEnv)) delete process.env[key];
    Object.assign(process.env, originalEnv); fs.rmSync(dir, { recursive: true, force: true }); });
  process.chdir(dir); fs.writeFileSync('canaries.json', JSON.stringify({ canaries: canaries.map(repo => ({ repo })) }));
  const state = { current: {}, checked: {}, trees: {}, reads: [], writes: [], failures: [] };
  const pr = repo => ({ number: 7, state: 'closed', merged: true, merged_at: '2026-10-28T00:00:00Z',
    merge_commit_sha: head(repo), base: { ref: 'main', sha: base, repo: { full_name: `owner/${repo}` } },
    head: { sha: checked(repo), repo: { full_name: `owner/${repo}` } } });
  const github = { rest: { users: { getAuthenticated: async () => ({ data: { login: 'owner' } }) },
    pulls: { list: async () => ({ data: [] }), get: async ({ repo }) => ({ data: pr(repo) }) },
    git: { getRef: async ({ repo }) => ({ data: { object: { sha: head(repo) } } }),
      getCommit: async ({ repo, commit_sha }) => ({ data: { sha: commit_sha,
        tree: { sha: state.trees[repo] && commit_sha === checked(repo) ? state.trees[repo] : 'd'.repeat(40) } } }) },
    checks: { listForRef: async args => { state.reads.push(args);
      const rows = args.ref === head(args.repo) ? (state.current[args.repo] || [])
        : [{ id: 7, name: 'Gate / gate', head_sha: checked(args.repo), status: 'completed',
          conclusion: state.checked[args.repo] || 'success' }];
      return { data: { total_count: rows.length, check_runs: rows } }; } },
    repos: { get: async () => ({ data: { default_branch: 'main' } }),
      getCommit: async () => ({ data: { commit: { committer: { date: '2026-10-28T00:00:00Z' } } } }),
      getContent: async () => { throw Object.assign(new Error('absent declaration'), { status: 404 }); },
      getCombinedStatusForRef: async () => ({ data: { statuses: [] } }),
      getBranchProtection: async () => ({ data: { required_status_checks: { contexts: ['Gate / gate'] } } }),
      listPullRequestsAssociatedWithCommit: async ({ repo }) => ({ data: [pr(repo)] }),
      listCommitStatusesForRef: async () => ({ data: [] }) },
    actions: { listWorkflowRuns: async () => ({ data: { workflow_runs: [] } }),
      createWorkflowDispatch: async args => { state.writes.push(args); return { status: 204 }; } },
  }, paginate: async (method, args) => {
    if (method === github.rest.pulls.list) return [];
    if (method === github.rest.checks.listForRef) return state.current[args.repo] || [];
    throw new Error('unexpected native pagination');
  } };
  const core = { notice() {}, warning() {}, setFailed: value => state.failures.push(value),
    summary: { addRaw() { return this; }, async write() {} } };
  t.mock.method(retry, 'createTokenAwareRetry', async () => null);
  t.mock.method(retry, 'withRetry', async fn => fn(github));
  t.mock.method(console, 'log', () => {});
  const rows = canaries.map(repository => ({ repo: repository, plan_id: plan, plan_scope: 'source-delta',
    scope_base_sha: base, source_commit: source, head_sha: head(repository.split('/')[1]),
    evidence_source: 'no-change-canary', required_check_state: 'success', active_review_thread_count: 0 }));
  const candidate = { schema: 'workflows.consumer-sync-canary-evidence/v1', version: 1, results: rows };
  const campaign = { schema: 'workflows.consumer-sync-no-change-evidence/v1', version: 1, results: rows };
  Object.assign(process.env, { REGISTERED_REPOS_INPUT: [...canaries, ...deliveries].join(','), REPOS_INPUT: canaries.join(','),
    OWNER_PR_PAT: 'inert-token', TRUSTED_SYNC_ACTORS: 'owner', CLEANUP_BRANCHES_INPUT: 'false', AUTO_MERGE_INPUT: 'true',
    DRY_RUN_INPUT: 'false', EXPECTED_PLAN_ID_INPUT: plan, EXPECTED_PLAN_SCOPE_INPUT: 'source-delta',
    EXPECTED_SCOPE_BASE_SHA_INPUT: base, EXPECTED_SOURCE_COMMIT_INPUT: source, CANDIDATE_EVIDENCE_AUTHORIZED: 'true',
    CONSUMER_SYNC_CANARIES_PATH: path.join(dir, 'canaries.json'), SYNC_PR_MERGE_REPORT_JSON: path.join(dir, 'report.json'),
    RESOLUTION_ONLY_INPUT: 'false', EVIDENCE_ONLY_INPUT: 'false', CAMPAIGN_COMMIT_AUTHORIZATION_JSON: '' });
  const pass = async (lane, prepare, authorization) => {
    Object.assign(process.env, { ACTIVE_SYNC_HASH_INPUT: lane, PREPARE_ONLY_INPUT: String(prepare),
      CANARY_BASELINE_EVIDENCE_JSON: lane === 'candidate' ? JSON.stringify(candidate) : '',
      CAMPAIGN_NO_CHANGE_EVIDENCE_JSON: lane === 'campaign' ? JSON.stringify(campaign) : '',
      CAMPAIGN_COMMIT_AUTHORIZATION_JSON: authorization ? JSON.stringify(authorization) : '' });
    await run({ github, core, context: { repo: { owner: 'owner', repo: 'Workflows' }, payload: {}, runId: 1, sha: source } });
    return JSON.parse(fs.readFileSync('report.json', 'utf8'));
  };
  return { state, pass, candidate, campaign, github, core };
}
test('three unchanged canaries retain native qualification through promotion, campaign prepare/commit/reentry beside thirteen delivered heads', async t => {
  const api = harness(t);
  const candidate = await api.pass('candidate', true);
  assert.equal(candidate.results.filter(row => row.status === 'evidence_recovered').length, 3);
  assert.equal((await dispatchCanaryPromotion({ report: candidate, evidence: api.candidate, expectedCanaries: canaries,
    withRetry: fn => fn(api.github), context: { repo: { owner: 'owner', repo: 'Workflows' }, payload: {} }, core: api.core })).status, 'dispatched');
  assert.equal(api.state.writes.length, 1); assert.equal(api.state.writes[0].inputs.cleanup_branches, 'false');
  const prepare = await api.pass('campaign', true);
  assert.equal(prepare.results.filter(row => row.status === 'campaign_no_change_verified').length, 3);
  // The existing prepared-delivery contract supplies the other thirteen exact heads;
  // this regression does not replace their normal review/final-Gate qualification.
  const preparedDeliveries = deliveries.map((repository, i) => ({ owner: 'owner', repo: repository.split('/')[1],
    pr: 100 + i, branch: 'sync/workflows-delivery', head_sha: head(`delivery${i}`), delivery_generation: `generation${i}`,
    plan_id: plan, source_commit: source, status: 'campaign_prepared' }));
  const authorization = buildCampaignCommitAuthorization({ report: { ...prepare,
    results: [...prepare.results, ...preparedDeliveries] }, expectedRepositories: [...canaries, ...deliveries], planId: plan, sourceCommit: source });
  assert.equal(authorization.authorized, true); assert.equal(authorization.rows.length, 16);
  assert.equal(authorization.rows.filter(row => row.no_change).length, 3);
  assert.ok(preparedDeliveries.every(result => campaignAuthorizationAllowsMerge({ authorization, result })));
  assert.equal(campaignAuthorizationAllowsMerge({ authorization, result: { ...preparedDeliveries[0], head_sha: 'f'.repeat(40) } }), false);
  const readsBefore = api.state.reads.length;
  for (const pass of [await api.pass('campaign', false, authorization), await api.pass('campaign', false, authorization)]) {
    assert.equal(pass.results.filter(row => row.status === 'campaign_no_change_verified').length, 3);
    for (const row of pass.results) { assert.equal(row.plan_id, plan); assert.equal(row.source_commit, source);
      assert.equal(row.check_provenance.kind, 'exact-merged-pr-tree'); }
  }
  assert.ok(api.state.reads.length > readsBefore, 'commit and reentry must freshly qualify, not reuse prepare proof');
  assert.equal(api.state.writes.length, 1, 'only the explicit mocked promotion was sent');
  assert.deepEqual(api.state.failures, []);
});
for (const [name, mutate] of [
  ['failed current required check', s => { s.current.canary1 = [{ id: 8, head_sha: head('canary1'), name: 'Gate / gate', status: 'completed', conclusion: 'failure' }]; }],
  ['pending current required check', s => { s.current.canary1 = [{ id: 8, head_sha: head('canary1'), name: 'Gate / gate', status: 'in_progress', conclusion: null }]; }],
  ['unknown current required check', s => { s.current.canary1 = [{ id: 8, head_sha: head('canary1'), name: 'Gate / gate', status: 'completed', conclusion: null }]; }],
  ['failed checked head', s => { s.checked.canary1 = 'failure'; }],
  ['different whole tree', s => { s.trees.canary1 = 'e'.repeat(40); }],
]) test(`campaign prepare and commit hold ${name}`, async t => {
  const api = harness(t); mutate(api.state);
  for (const prepare of [true, false]) {
    const report = await api.pass('campaign', prepare);
    const row = report.results.find(row => row.repo === 'canary1');
    assert.notEqual(row.status, 'campaign_no_change_verified');
    assert.equal(row.reason, 'campaign_no_change_required_checks_not_ready');
  }
  assert.equal(api.state.writes.length, 0);
});

test('a failure appearing after successful prepare blocks commit and re-entry', async t => {
  const api = harness(t); const prepare = await api.pass('campaign', true);
  assert.equal(prepare.results.filter(row => row.status === 'campaign_no_change_verified').length, 3);
  api.state.current.canary1 = [{ id: 9, head_sha: head('canary1'), name: 'Gate / gate',
    status: 'completed', conclusion: 'failure' }];
  for (let i = 0; i < 2; i++) {
    const report = await api.pass('campaign', false);
    assert.equal(report.results.find(row => row.repo === 'canary1').status, 'checks_failed');
  }
  assert.equal(api.state.writes.length, 0);
});
test('ordinary generated-PR final merge boundary retains its direct exact-head classifier', () => {
  const sourceText = fs.readFileSync(path.join(__dirname, '../maint71_merge_sync_prs.js'), 'utf8');
  const finalGuard = sourceText.split('// A rerun can turn Gate red')[1].split('return {')[0];
  assert.match(finalGuard, /classifyRequiredChecksForRef/);
  assert.match(finalGuard, /ref: pr.head.sha/); assert.match(finalGuard, /enforceGeneratedDeliveryGate: true/);
  assert.doesNotMatch(finalGuard, /qualifyNoChange/);
});
