'use strict';

// Pure host observations and inert native adapters only; no dispatch is sent.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { refreshPlanContext, verifiedCanaryRefreshPlan, canaryRefreshDecision,
  dispatchCanaryRefresh, refreshStableCanaries, deferSealedCanaryRefresh } = require('../maint71_merge_sync_prs');
const payloads = require('../consumer_delivery_digest');
const source = 'a'.repeat(40), base = 'b'.repeat(40), head = 'c'.repeat(40);
const id = `sha256:${'d'.repeat(64)}`;
const compiled = { plan_id: id, entries: [{ target: 'selected.js', is_directory: false,
  include_repos: [], skip_repos: [] }], removals: [] };
const request = () => refreshPlanContext({ planId: id, planScope: 'source-delta',
  scopeBaseSha: base, sourceSha: source, plan: structuredClone(compiled) });
const context = { repo: { owner: 'owner', repo: 'Workflows' },
  payload: { repository: { default_branch: 'main' } } };
const candidates = ['owner/a'];
function producer(scope = 'source-delta', extra = {}) {
  return { id: 10, head_branch: 'main', head_sha: head, status: 'completed', conclusion: 'success',
    display_title: `Maint 68 canary ${scope}  source=${source} candidates=owner/a dry=false  guard=delivery-v1`,
    refresh_plan: scope === 'source-delta' ? request() : undefined,
    delivery_digest: 'digest', ...extra };
}
function decide(runs, refreshPlan = request()) {
  return canaryRefreshDecision({ runs, sha: source, candidates, refreshPlan, deliveryDigest: 'digest' });
}
function recorder() {
  const writes = [], summaries = [];
  return { writes, summaries, withRetry: fn => fn({ rest: { actions: {
    createWorkflowDispatch: async args => { writes.push(args); return { status: 204 }; },
  } } }), core: { notice() {}, setFailed: value => assert.fail(value),
    summary: { addRaw(value) { summaries.push(value); return this; }, async write() {} } } };
}
function ready() { return { sha: source, candidates, eligible: true, state: 'unseen',
  delivery_digest: 'digest', refresh_plan: request() }; }

test('prior successful full delivery cannot complete a distinct scoped request', () => {
  assert.equal(decide([producer('full')]).eligible, true);
  assert.equal(decide([producer('full')]).producer_succeeded, false);
});
test('the exact authenticated scoped tuple deduplicates despite generated YAML whitespace', () => {
  const result = decide([producer()]);
  assert.equal(result.eligible, false); assert.equal(result.producer_succeeded, true);
});
for (const field of ['plan_id', 'scope_base_sha', 'source_commit']) test(`different native ${field} cannot satisfy the scoped tuple`, () => {
  const run = producer(); run.refresh_plan[field] = field === 'plan_id' ? `sha256:${'e'.repeat(64)}` : 'e'.repeat(40);
  assert.equal(decide([run]).eligible, true);
});
for (const scope of ['full', 'source-delta']) test(`later ${scope} success prevents reuse of an older scoped receipt`, () => {
  const earlier = producer('source-delta', { id: 1, run_started_at: '2026-10-27T20:00:00Z' });
  const overwrite = producer(scope, { id: 2, run_started_at: '2026-10-27T21:00:00Z', delivery_digest: 'other' });
  if (scope === 'source-delta') overwrite.refresh_plan.plan_id = `sha256:${'e'.repeat(64)}`;
  const result = decide([earlier, overwrite]);
  assert.equal(result.eligible, true); assert.equal(result.producer_succeeded, false);
  const restored = producer('source-delta', { id: 3, run_started_at: '2026-10-27T22:00:00Z' });
  assert.equal(decide([earlier, overwrite, restored]).producer_succeeded, true);
  overwrite.refresh_not_started = true;
  assert.equal(decide([earlier, overwrite]).producer_succeeded, true,
    'positively non-started later history cannot overwrite the delivered scope');
});
test('old full active writer globally excludes another scoped writer', () => {
  const result = decide([producer('full', { status: 'in_progress', conclusion: null })]);
  assert.equal(result.eligible, false); assert.equal(result.state, 'writer-active');
});
test('unknown scoped history holds while positively not-started history is not completion', () => {
  assert.equal(decide([producer('source-delta', { refresh_unknown: true })]).state, 'unknown');
  assert.equal(decide([producer('source-delta', { refresh_unknown: true })]).eligible, false);
  const notStarted = decide([producer('source-delta', { refresh_not_started: true })]);
  assert.equal(notStarted.eligible, true); assert.equal(notStarted.producer_succeeded, false);
});
test('scoped recovery dispatch retains exact plan/source/base and false cleanup with no repeat', async () => {
  const api = recorder(), state = ready();
  await dispatchCanaryRefresh({ ...api, context, expectedCanaries: candidates, refreshState: state, cleanupBranches: false });
  assert.deepEqual(api.writes[0].inputs, { phase: 'canary', delivery_scope: 'source-delta',
    scope_head_sha: source, scope_base_sha: base, expected_plan_id: id,
    repos: 'owner/a', dry_run: 'false', force: 'false', cleanup_branches: 'false' });
  await dispatchCanaryRefresh({ ...api, context, expectedCanaries: candidates, refreshState: state, cleanupBranches: false });
  assert.equal(api.writes.length, 1);
});
for (const [name, change] of [
  ['base', x => { x.scopeBaseSha = ''; }], ['source', x => { x.sourceSha = ''; }],
  ['plan', x => { x.planId = ''; }], ['compiled plan', x => { x.plan = { ...compiled, plan_id: 'other' }; }],
]) test(`missing scoped ${name} cannot fall back to full`, () => {
  const value = { planId: id, planScope: 'source-delta', scopeBaseSha: base, sourceSha: source, plan: compiled };
  change(value); assert.throws(() => refreshPlanContext(value));
});
function nativeHead() { return { sha: head, verification: { verified: true, reason: 'valid' },
  message: `Consumer-sync plan ID: ${id}\nPlan scope: source-delta\nScope base SHA: ${base}\nSource commit: ${source}` }; }
function nativeArgs() { return { owner: 'owner', repo: 'a', pr: { head: { sha: head } },
  record: { plan_id: id, source_commit: source, head_observed_sha: head },
  metadata: { plan_id: id, plan_scope: 'source-delta', scope_base_sha: base, source_commit: source },
  nativeHead: nativeHead(), withRetry: () => assert.fail('existing native view must be reused') }; }
test('recovery scope derives from the actual verified native head and matching current record', async () => {
  assert.deepEqual(await verifiedCanaryRefreshPlan(nativeArgs()), { plan_id: id,
    plan_scope: 'source-delta', scope_base_sha: base, source_commit: source });
});
for (const [name, change] of [
  ['unsigned native head', x => { x.nativeHead.verification.verified = false; }],
  ['changed current head', x => { x.pr.head.sha = 'f'.repeat(40); }],
  ['mutable metadata scope downgrade', x => { x.metadata.plan_scope = 'full'; }],
  ['mutable metadata base', x => { x.metadata.scope_base_sha = 'f'.repeat(40); }],
  ['duplicate immutable header', x => { x.nativeHead.message += `\nPlan scope: full`; }],
  ['record source substitution', x => { x.record.source_commit = 'f'.repeat(40); }],
]) test(`recovery remains unknown for ${name}`, async () => {
  const args = nativeArgs(); change(args); await assert.rejects(verifiedCanaryRefreshPlan(args));
});
test('scoped rendered digest retains only selected targets and policy, without a managed ignore block', () => {
  const full = { digest: 'full', files: { 'owner/a': { 'selected.js': { content: 'x', create_only: true },
    'unrelated.js': { content: 'y' }, '.gitignore': { managed_blocks: ['ignore'] } } } };
  const result = payloads.scopedDeliveryPayload(full, request());
  assert.deepEqual(Object.keys(result.files['owner/a']), ['selected.js']);
  assert.equal(result.files['owner/a']['selected.js'].create_only, true);
  assert.notEqual(result.digest, full.digest); assert.equal(Object.keys(full.files['owner/a']).length, 3);
  const other = request(); other.scope_base_sha = 'e'.repeat(40);
  assert.notEqual(result.digest, payloads.scopedDeliveryPayload(full, other).digest);
});
test('scoped rendering cannot silently omit a selected runtime file', () => {
  assert.throws(() => payloads.scopedDeliveryPayload({ files: { 'owner/a': {} } }, request()), /payload_missing/);
});
test('scoped rendering preserves directory/repository filters and excludes unrelated paths', () => {
  const value = request(); value.plan.entries = [{ target: 'dir', is_directory: true,
    include_repos: ['owner/a'], skip_repos: [] }];
  const result = payloads.scopedDeliveryPayload({ files: { 'owner/a': { 'dir/a.js': {}, 'other.js': {} },
    'owner/b': { 'dir/a.js': {} } } }, value);
  assert.deepEqual(Object.keys(result.files['owner/a']), ['dir/a.js']);
  assert.deepEqual(Object.keys(result.files['owner/b']), []);
});
function guardScript() {
  const text = fs.readFileSync(path.join(__dirname, '../../workflows/maint-68-sync-consumer-repos.yml'), 'utf8');
  assert.ok(text.indexOf('- name: Select full or exact source-delta plan') < text.indexOf('- name: Check content refresh guard'));
  return text.split('      - name: Check content refresh guard')[1].split('      - name: Authorize canary payload mutation')[0]
    .split('          script: |\n')[1].split('\n').map(line => line.replace(/^ {12}/, '')).join('\n');
}
test('actual workflow guard passes the actual compiled plan identity before admission', async () => {
  const outputs = {}, seen = [], factoryCalls = [];
  const github = {}, wrapped = async fn => fn(github);
  const fn = new (Object.getPrototypeOf(async function () {}).constructor)('require', 'process', 'core', 'github', 'context', guardScript());
  const load = name => name === 'fs' ? { readFileSync: () => JSON.stringify(compiled) }
    : name.includes('github-api-with-retry') ? { createTokenAwareRetry: async args => { factoryCalls.push(args); return { withRetry: wrapped }; } }
    : name.includes('maint71_merge_sync_prs') ? { reportCanaryRefreshDiagnostics: require('../maint71_merge_sync_prs').reportCanaryRefreshDiagnostics, readCanaryRefreshState: async args => { seen.push(args); return { eligible: true }; } }
      : { canaries: candidates.map(repo => ({ repo })) };
  const env = { PLAN_ID: id, PLAN_SCOPE: 'source-delta', SCOPE_BASE_SHA: base, SOURCE_COMMIT: source };
  const core = { notice() {}, setOutput: (key, value) => { outputs[key] = value; }, summary: { addRaw() { return this; }, async write() {} } };
  await fn(load, { env }, core, github, { ...context, runId: 1 });
  assert.equal(factoryCalls.length, 1);
  assert.equal(factoryCalls[0].github, github); assert.equal(factoryCalls[0].core, core);
  assert.deepEqual(factoryCalls[0].env, {});
  assert.equal(factoryCalls[0].tokenRegistry.isInitialized(), false);
  assert.equal(factoryCalls[0].task, 'maint68-scoped-refresh');
  assert.equal(seen[0].withRetry, wrapped);
  assert.equal(seen[0].planId, id); assert.equal(seen[0].planScope, 'source-delta');
  assert.equal(seen[0].scopeBaseSha, base); assert.equal(seen[0].sourceSha, source);
  assert.deepEqual(seen[0].plan, compiled); assert.equal(outputs.allowed, 'true');
  env.EXPECTED_PLAN_ID = `sha256:${'f'.repeat(64)}`; env.FORCE = 'true';
  await assert.rejects(fn(load, { env }, core, {}, context), /actual compiled plan/);
  assert.equal(seen.length, 1, 'a constraint mismatch cannot reach the history reader or force bypass');
  assert.equal(factoryCalls.length, 1, 'a constraint mismatch cannot initialize the API wrapper');
});
test('actual workflow guard uses the returned wrapper and holds exhausted native reads without admission', async () => {
  const outputs = {}, observations = [];
  const github = { rest: { repos: { getCommit: async () => { throw new Error('bounded native read exhausted'); } } } };
  let calls = 0;
  const wrapped = async (operation, options) => { calls++; observations.push(options); return operation(github); };
  const fn = new (Object.getPrototypeOf(async function () {}).constructor)('require', 'process', 'core', 'github', 'context', guardScript());
  const load = name => name === 'fs' ? { readFileSync: () => JSON.stringify(compiled) }
    : name.includes('github-api-with-retry') ? { createTokenAwareRetry: async () => ({ withRetry: wrapped }) }
    : name.includes('maint71_merge_sync_prs') ? require('../maint71_merge_sync_prs')
    : { canaries: candidates.map(repo => ({ repo })) };
  const core = { notice() {}, setOutput: (key, value) => { outputs[key] = value; },
    summary: { addRaw() { return this; }, async write() {} } };
  await assert.rejects(fn(load, { env: { PLAN_ID: id, PLAN_SCOPE: 'source-delta',
    SCOPE_BASE_SHA: base, SOURCE_COMMIT: source, GITHUB_RUN_ATTEMPT: '1' } }, core, github,
  { ...context, runId: 1 }), /bounded native read exhausted/);
  assert.equal(calls, 1, 'native read must pass through the returned retry wrapper');
  assert.equal(outputs.allowed, undefined, 'unknown native source cannot authorize mutation');
  assert.equal(github.rest.actions, undefined, 'the guard has no dispatch capability in this control');
});
test('scoped recovery groups preserve original plan and permit only one local writer', async () => {
  const api = recorder(), state = ready(), canary = { owner: 'owner', repo: 'a', pr: 1,
    plan_id: id, plan_scope: 'source-delta', source_commit: source, refresh_plan: request(), refresh_state: state,
    head_sha: head, check_status: 'checks_failed', mergeable_state: 'dirty',
    active_review_thread_count: 0, threads: [] };
  state.drift_key = createHash('sha256').update(`owner/a:digest:${head}`).digest('hex');
  const other = { ...canary, plan_id: `sha256:${'f'.repeat(64)}` };
  const result = await refreshStableCanaries({ ...api, context, expectedCanaries: candidates,
    enabled: true, cleanupBranches: false, canaries: [canary, other] });
  assert.equal(result.refresh_dispatched, 1); assert.equal(api.writes.length, 1);
  assert.equal(api.writes[0].inputs.delivery_scope, 'source-delta');
  assert.equal(api.writes[0].inputs.expected_plan_id, id);
  assert.equal(api.writes[0].inputs.cleanup_branches, 'false');
});
test('an unrelated sealed full-scope head remains protected; unselected absence is not deletion', async t => {
  const { formatDeliveryRecord } = require('../sync_pr_lease_contract');
  const now = Date.parse('2026-10-27T22:00:00Z');
  const record = { schema: 'sync-pr-delivery-record/v1', repository: 'owner/a', plan_id: `sha256:${'e'.repeat(64)}`,
    durable_issue_url: 'https://github.com/owner/Workflows/issues/1', generation: 'g',
    desired_tree_hash: 'tree', source_commit: base, head_observed_sha: head,
    head_observed_at: new Date(now - 1800000).toISOString(), lease_expires_at: '2099-01-01T00:00:00Z',
    delivery_state: 'sealed', sealed_head_sha: head, sealed_at: new Date(now - 1800000).toISOString(),
    review_started_at: new Date(now - 1800000).toISOString() };
  const pr = { number: 1, state: 'open', head: { sha: head, ref: 'sync/workflows-candidate' },
    body: formatDeliveryRecord(record), mergeable: true, mergeable_state: 'clean', changed_files: 1 };
  t.mock.method(payloads, 'readDeliveryPayload', async () => ({ digest: 'full', files: { 'owner/a': {
    'selected.js': { content: 'same' }, 'unrelated.js': { content: 'old' } } } }));
  const state = ready(), payload = { digest: 'scoped', files: { 'owner/a': { 'selected.js': { content: 'same' } } } };
  const withRetry = fn => fn({ rest: { pulls: { list: async () => ({ data: [pr] }), get: async () => ({ data: pr }),
    listFiles: async () => ({ data: [{ filename: 'unrelated.js' }] }) }, actions: { listWorkflowRuns: async () => ({ data: { workflow_runs: [] } }) } } });
  const result = await deferSealedCanaryRefresh({ state, payload, withRetry, now });
  assert.equal(result.eligible, false); assert.equal(result.state, 'sealed-cycle');
  assert.notEqual(result.producer_succeeded, true, 'full-scope equality cannot complete the scoped request');
});

function historyHarness(t, { runs = [], active = [], receipt, requestedCandidates = candidates } = {}) {
  const reads = [], writes = [], receiptReads = [];
  const native = require('../maint68_scoped_receipt');
  t.mock.method(native, 'readScopedCanaryReceipt', async args => {
    receiptReads.push(args); return typeof receipt === 'function' ? receipt(args) : receipt;
  });
  t.mock.method(payloads, 'readDeliveryPayload', async (_sha, _repos, scope) =>
    payloads.scopedDeliveryPayload({ digest: 'full', files: { 'owner/a': {
      'selected.js': { content: 'selected' }, 'unrelated.js': { content: 'unrelated' },
    } } }, scope));
  const github = { rest: { actions: {
    listWorkflowRuns: async args => { reads.push(args); return { data: { workflow_runs: args.status
      ? active.filter(row => row.status === args.status) : runs } }; },
    createWorkflowDispatch: async args => { writes.push(args); return { status: 204 }; },
  }, repos: { getCommit: async () => ({ data: { sha: source } }),
    getContent: async () => ({ data: { content: Buffer.from(JSON.stringify({ canaries: requestedCandidates.map(repo => ({ repo })) })).toString('base64') } }) },
  pulls: { list: async () => ({ data: [] }) } } };
  return { github, reads, writes, receiptReads, withRetry: fn => fn(github),
    read: extra => require('../maint71_merge_sync_prs').readCanaryRefreshState({
      withRetry: fn => fn(github), context, expectedCanaries: requestedCandidates,
      planId: id, planScope: 'source-delta', scopeBaseSha: base, sourceSha: source, plan: compiled, ...extra }) };
}
function observedReceipt(state = 'completed') { return { ...request(), state, candidates,
  proof: { source_identity_bound: true } }; }
for (const scope of ['full', 'source-delta']) test(`actual collector retains later authenticated ${scope} as an overwrite barrier`, async t => {
  const old = producer('source-delta', { id: 1, run_started_at: '2026-10-27T20:00:00Z' });
  const later = producer(scope, { id: 2, run_started_at: '2026-10-27T21:00:00Z' });
  const api = historyHarness(t, { runs: [old, later], receipt: ({ run }) => {
    if (run.id === 1) return observedReceipt();
    return { ...observedReceipt(), plan_scope: scope,
      plan_id: `sha256:${'e'.repeat(64)}`, scope_base_sha: scope === 'full' ? '' : base,
      plan: { ...compiled, plan_id: `sha256:${'e'.repeat(64)}` } };
  } });
  const state = await api.read();
  assert.equal(api.receiptReads.length, 2, 'full and different-plan history must reach native authentication');
  assert.equal(state.eligible, true); assert.equal(state.producer_succeeded, false);
  assert.equal(api.writes.length, 0);
});
for (const conclusion of ['failure', 'cancelled']) test(`expired positively other-source ${conclusion} invalidates older scoped completion without global hold`, async t => {
  const old = producer('source-delta', { id: 1, run_started_at: '2026-10-27T20:00:00Z' });
  const other = producer('source-delta', { id: 2, conclusion, run_started_at: '2026-10-27T21:00:00Z',
    display_title: producer().display_title.replace(source, 'e'.repeat(40)) });
  const runs = [old, other];
  const api = historyHarness(t, { runs, receipt: ({ run }) => run.id === 2
    ? { state: 'unknown', reason: 'native_scope_artifact_expired', source_commit: 'e'.repeat(40),
      proof: { source_identity_bound: true } } : observedReceipt() });
  const state = await api.read();
  assert.equal(state.eligible, true); assert.equal(state.producer_succeeded, false);
  assert.notEqual(state.state, 'unknown', 'other-source uncertainty is an overwrite barrier, not a global request hold');
  runs.push(producer('source-delta', { id: 3, run_started_at: '2026-10-27T22:00:00Z' }));
  const restored = await api.read();
  assert.equal(restored.eligible, false); assert.equal(restored.producer_succeeded, true);
  assert.equal(api.writes.length, 0);
});
for (const subset of ['owner/a', 'owner/unrelated']) test(`actual collector treats ${subset} native unknown history as an overlap-only barrier`, async t => {
  const fleet = ['owner/a', 'owner/b'];
  const old = producer('source-delta', { id: 1, run_started_at: '2026-10-27T20:00:00Z',
    display_title: producer().display_title.replace('candidates=owner/a', 'candidates=owner/a,owner/b') });
  const other = producer('source-delta', { id: 2, conclusion: 'failure', run_started_at: '2026-10-27T21:00:00Z',
    display_title: producer().display_title.replace(source, 'e'.repeat(40)).replace('candidates=owner/a', `candidates=${subset}`) });
  const api = historyHarness(t, { runs: [old, other], requestedCandidates: fleet, receipt: ({ run }) => run.id === 2
    ? { state: 'unknown', reason: 'native_scope_artifact_expired', source_commit: 'e'.repeat(40),
      proof: { source_identity_bound: true } } : { ...observedReceipt(), candidates: fleet } });
  const state = await api.read();
  assert.equal(state.eligible, subset === 'owner/a');
  assert.equal(state.producer_succeeded, subset !== 'owner/a');
  assert.notEqual(state.state, 'unknown'); assert.equal(api.writes.length, 0);
});
test('a subset completion cannot satisfy an exact fleet request', () => {
  const subset = producer();
  const state = canaryRefreshDecision({ runs: [subset], sha: source,
    candidates: ['owner/a', 'owner/b'], refreshPlan: request(), deliveryDigest: 'digest' });
  assert.equal(state.eligible, true); assert.equal(state.producer_succeeded, false);
});
test('current scoped rerun cannot erase a prior attempt by ignoring its whole run ID', async t => {
  const run = producer('source-delta', { id: 70, run_attempt: 2, status: 'in_progress', conclusion: null });
  const api = historyHarness(t, { runs: [run], active: [run], receipt: observedReceipt() });
  const state = await api.read({ ignoreRunId: 70, ignoreRunAttempt: 2 });
  assert.equal(state.eligible, false); assert.equal(state.state, 'unknown');
  assert.equal(api.receiptReads.length, 0, 'latest current attempt cannot stand in for prior attempts');
});
test('historical rerun latest not-started does not erase unknown prior attempt effects', async t => {
  const api = historyHarness(t, { runs: [producer('source-delta', { run_attempt: 2 })], receipt: observedReceipt('not_started') });
  const state = await api.read(); assert.equal(state.eligible, false); assert.equal(state.state, 'unknown');
});
test('native current first attempt remains self-excluded before its own authorization step', async t => {
  const run = producer('source-delta', { id: 70, run_attempt: 1, status: 'in_progress', conclusion: null });
  const api = historyHarness(t, { runs: [run], active: [run] });
  assert.equal((await api.read({ ignoreRunId: 70, ignoreRunAttempt: 1 })).eligible, true);
  await assert.rejects(api.read({ ignoreRunId: 70 }), /current_attempt_unknown/);
});
test('actual collector retains global old full writer exclusion for a scoped plan', async t => {
  const run = producer('full', { status: 'queued', conclusion: null });
  const api = historyHarness(t, { active: [run] });
  const state = await api.read(); assert.equal(state.eligible, false); assert.equal(state.state, 'writer-active');
});
function reportFixture(t, { scope = 'source-delta' } = {}) {
  const record = { schema: 'sync-pr-delivery-record/v1', repository: 'owner/a', plan_id: id,
    durable_issue_url: 'https://owner.invalid/1', generation: 'g', desired_tree_hash: 'tree',
    source_commit: source, head_observed_sha: head, head_observed_at: '2026-10-27T22:00:00Z',
    lease_expires_at: '2099-01-01T00:00:00Z', delivery_state: 'staging' };
  const metadata = { consumer_repo: 'owner/a', sync_phase: 'canary', plan_id: id, plan_scope: scope,
    source_commit: source, scope_base_sha: scope === 'source-delta' ? base : '' };
  const { formatDeliveryRecord } = require('../sync_pr_lease_contract');
  const pr = { number: 4, state: 'open', draft: false, user: { login: 'stranske' },
    head: { sha: head, ref: 'sync/workflows-candidate', repo: { full_name: 'owner/a' } },
    base: { repo: { full_name: 'owner/a', default_branch: 'main' } }, mergeable_state: 'dirty',
    body: `<!-- workflows-consumer-sync:v1 ${JSON.stringify(metadata)} -->\n${formatDeliveryRecord(record)}` };
  const api = historyHarness(t, { runs: [producer()], receipt: observedReceipt() });
  api.github.rest.pulls.get = async () => ({ data: pr });
  const commitView = nativeHead();
  if (scope === 'full') commitView.message = commitView.message.replace('Plan scope: source-delta', 'Plan scope: full').replace(`Scope base SHA: ${base}`, 'Scope base SHA: full');
  api.github.rest.repos.getCommit = async args => ({ data: args.repo === 'a'
    ? { sha: commitView.sha, commit: { verification: commitView.verification, message: commitView.message } }
    : { sha: source } });
  const row = { owner: 'owner', repo: 'a', pr: 4, head_sha: head, plan_id: id, plan_scope: scope,
    scope_base_sha: scope === 'source-delta' ? base : '', source_commit: source,
    status: 'stable_base_refresh_required', next_command: 'dispatch-maint-68-phase-canary-no-filter' };
  const report = { inputs: { cleanup_branches: false }, results: [row] };
  const core = recorder().core;
  return { ...api, pr, row, report, commitView, call: () => require('../maint71_merge_sync_prs').dispatchCandidateRefreshFromReport({
    withRetry: api.withRetry, context, core, report, expectedCanaries: candidates, trustedActors: ['stranske'] }) };
}
test('actual report caller freshly binds the native scoped head and retains original scope through recovery', async t => {
  const f = reportFixture(t); await f.call();
  assert.equal(f.writes.length, 1); assert.equal(f.writes[0].inputs.delivery_scope, 'source-delta');
  assert.equal(f.writes[0].inputs.scope_base_sha, base); assert.equal(f.writes[0].inputs.scope_head_sha, source);
  assert.equal(f.writes[0].inputs.expected_plan_id, id); assert.equal(f.writes[0].inputs.cleanup_branches, 'false');
  assert.match(f.writes[0].inputs.refresh_key, /^[a-f0-9]{64}$/);
});
for (const [name, change] of [
  ['raw scope downgrade', f => { f.row.plan_scope = 'full'; }],
  ['raw scope missing', f => { delete f.row.plan_scope; }],
  ['fresh actor changed', f => { f.pr.user.login = 'untrusted'; }],
  ['fresh branch changed', f => { f.pr.head.ref = 'feature'; }],
  ['fresh head changed', f => { f.pr.head.sha = 'f'.repeat(40); }],
  ['fresh head unsigned', f => { f.commitView.verification.verified = false; }],
  ['raw source changed', f => { f.row.source_commit = 'f'.repeat(40); }],
]) test(`report caller refuses ${name} before any dispatch`, async t => {
  const f = reportFixture(t); change(f); await assert.rejects(f.call()); assert.equal(f.writes.length, 0);
});
test('a genuine verified full-scope report retains the ordinary full recovery route', async t => {
  const f = reportFixture(t, { scope: 'full' }); await f.call();
  assert.equal(f.writes.length, 1); assert.equal(f.writes[0].inputs.delivery_scope, 'full');
  assert.equal(f.writes[0].inputs.cleanup_branches, 'false');
});
for (const field of ['scope_base_sha', 'source_commit']) test(`same compiled plan ID with different verified ${field} is held instead of selecting the first scope`, async () => {
  const writes = [], failures = [], api = recorder(); api.core.setFailed = reason => failures.push(reason);
  const first = { owner: 'owner', repo: 'a', pr: 1, plan_id: id, plan_scope: 'source-delta', source_commit: source,
    refresh_plan: request(), head_sha: head, check_status: 'checks_failed', mergeable_state: 'dirty', active_review_thread_count: 0 };
  const other = { ...first, refresh_plan: { ...request(), [field]: 'f'.repeat(40) } };
  const result = await refreshStableCanaries({ ...api, context, expectedCanaries: candidates, enabled: true,
    cleanupBranches: false, canaries: [first, other] });
  writes.push(...api.writes); assert.equal(writes.length, 0); assert.equal(result.refresh_dispatched, 0);
  assert.ok(failures.some(reason => reason.includes('missing_or_mixed')));
});
test('actual Maint71 workflow caller uses the native report adapter rather than defaulting to full', async () => {
  const workflow = fs.readFileSync(path.join(__dirname, '../../workflows/maint-71-merge-sync-prs.yml'), 'utf8');
  const block = workflow.split('      - name: Refresh stale candidate bases')[1].split('      - name: Refresh stale delivery bases')[0];
  const script = block.split('          script: |\n')[1].split('\n').map(line => line.replace(/^ {12}/, '')).join('\n');
  const calls = [], report = { inputs: { cleanup_branches: false }, results: [] };
  const load = name => name === 'fs' ? { readFileSync: filename => JSON.stringify(filename.includes('report') ? report : { canaries: [{ repo: 'owner/a' }] }) }
    : name.includes('github-api-with-retry') ? { createTokenAwareRetry: async () => ({ withRetry() {} }) }
      : name.includes('sync_pr_merge_contract') ? { candidateRefreshDecision: () => ({ eligible: true }) }
        : { dispatchCandidateRefreshFromReport: async args => calls.push(args) };
  await new (Object.getPrototypeOf(async function () {}).constructor)('require', 'process', 'github', 'core', 'context', script)(
    load, { env: { TRUSTED_SYNC_ACTORS: 'stranske' } }, {}, {}, context);
  assert.equal(calls.length, 1); assert.deepEqual(calls[0].report, report);
  assert.deepEqual(calls[0].trustedActors, ['stranske']); assert.deepEqual(calls[0].expectedCanaries, ['owner/a']);
});


test('native refusal diagnostics retain only bounded allowlisted primitives and do not change unknown admission', async t => {
  const run = producer('source-delta', { run_attempt: 1 });
  const api = historyHarness(t, { runs: [run], receipt: { state: 'unknown',
    reason: 'native_scope_artifact_absent_or_ambiguous', source_commit: source,
    plan_id: id, plan_scope: 'source-delta', scope_base_sha: base,
    proof: { source_identity_bound: false, artifact_id: 3, raw: 'SECRET_PAYLOAD' },
    secret: 'SECRET_PAYLOAD' } });
  const state = await api.read();
  const { canaryRefreshDiagnostics, reportCanaryRefreshDiagnostics } = require('../maint71_merge_sync_prs');
  const diagnostic = canaryRefreshDiagnostics(state);
  assert.equal(state.eligible, false); assert.equal(diagnostic.state, 'unknown');
  assert.equal(diagnostic.blocking_receipt.run_id, run.id);
  assert.equal(diagnostic.blocking_receipt.run_attempt, 1);
  assert.equal(diagnostic.blocking_receipt.reason_code, 'native_scope_artifact_absent_or_ambiguous');
  assert.equal(diagnostic.blocking_receipt.plan_id, id);
  assert.equal(diagnostic.inventory.unknown, 1); assert.equal(diagnostic.inventory.native_receipts, 1);
  const notices = [], summaries = [];
  await reportCanaryRefreshDiagnostics({ state, core: { notice: value => notices.push(value),
    summary: { addRaw(value) { summaries.push(value); return this; }, async write() {} } } });
  assert.match(notices[0], /canary-refresh-diagnostics:/);
  assert.match(summaries[0], /native_scope_artifact_absent_or_ambiguous/);
  assert.doesNotMatch(JSON.stringify({ diagnostic, notices, summaries }), /SECRET_PAYLOAD/);
  assert.equal(api.writes.length, 0);
});
test('arbitrary native API error text is never logged; bounded inventory and recovery report share diagnostics', async () => {
  const { refreshReceiptDiagnostic, canaryRefreshDiagnostics, dispatchCanaryRefresh } = require('../maint71_merge_sync_prs');
  const receipt = refreshReceiptDiagnostic({ id: 1, run_attempt: 1, head_sha: head }, {
    state: 'unknown', reason: 'Bearer SECRET_PAYLOAD\n<script>', source_commit: 'SECRET_PAYLOAD',
    proof: { artifact_id: 'SECRET_PAYLOAD' } });
  assert.equal(receipt.reason_code, 'native_scope_read_failed');
  assert.doesNotMatch(JSON.stringify(receipt), /SECRET_PAYLOAD/);
  const runs = Array.from({ length: 20 }, (_, i) => ({ id: i + 1, refresh_unknown: true,
    refresh_receipt: { ...receipt, run_id: i + 1 } }));
  const state = { ...ready(), runs, run_id: 1, state: 'unknown', eligible: false };
  const diagnostic = canaryRefreshDiagnostics(state);
  assert.equal(diagnostic.refusals.length, 8); assert.equal(diagnostic.omitted_refusals, 12);
  const api = recorder(); await dispatchCanaryRefresh({ ...api, context, expectedCanaries: candidates, refreshState: state });
  assert.equal(api.writes.length, 0); assert.match(api.summaries.join(''), /native_scope_read_failed/);
});
test('noncanonical native plan preserves its refusal reason and UNKNOWN hold', async () => {
  const helper = require('../maint71_merge_sync_prs');
  const run = producer('source-delta', { run_attempt: 1, refresh_unknown: true });
  run.refresh_receipt = helper.refreshReceiptDiagnostic(run, {
    state: 'unknown', reason: 'noncanonical_native_plan_json' });
  assert.equal(run.refresh_receipt.state, 'unknown');
  assert.equal(run.refresh_receipt.reason_code, 'noncanonical_native_plan_json');
  const state = { ...ready(), runs: [run], eligible: false, state: 'unknown', run_id: run.id };
  const api = recorder();
  await helper.dispatchCanaryRefresh({ ...api, context, expectedCanaries: candidates, refreshState: state });
  assert.equal(api.writes.length, 0);
  assert.match(api.summaries.join(''), /noncanonical_native_plan_json/);
});
test('parsed but uncertain effect disposition receives an explicit diagnostic code', () => {
  const { refreshReceiptDiagnostic } = require('../maint71_merge_sync_prs');
  assert.equal(refreshReceiptDiagnostic(producer(), { state: 'unknown' }).reason_code,
    'native_scope_effect_disposition_unknown');
});

test('actual Maint68 guard emits structured blocking diagnostics while refusing mutation', async () => {
  const helper = require('../maint71_merge_sync_prs');
  const run = producer('source-delta', { run_attempt: 1, refresh_unknown: true });
  run.refresh_receipt = helper.refreshReceiptDiagnostic(run, { state: 'unknown',
    reason: 'native_scope_phase_binding', source_commit: source, proof: { source_identity_bound: true } });
  const state = { ...ready(), eligible: false, state: 'unknown', run_id: run.id, runs: [run] };
  const outputs = {}, notices = [], summaries = [];
  const core = { notice: value => notices.push(value), setOutput: (key, value) => { outputs[key] = value; },
    summary: { addRaw(value) { summaries.push(value); return this; }, async write() {} } };
  const load = name => name === 'fs' ? { readFileSync: () => JSON.stringify(compiled) }
    : name.includes('github-api-with-retry') ? { createTokenAwareRetry: async () => ({ withRetry: () => assert.fail('no native IO needed') }) }
    : name.includes('maint71_merge_sync_prs') ? { ...helper, readCanaryRefreshState: async () => state }
    : { canaries: candidates.map(repo => ({ repo })) };
  const fn = new (Object.getPrototypeOf(async function () {}).constructor)('require', 'process', 'core', 'github', 'context', guardScript());
  await fn(load, { env: { PLAN_ID: id, PLAN_SCOPE: 'source-delta', SCOPE_BASE_SHA: base, SOURCE_COMMIT: source } }, core, {}, context);
  assert.equal(outputs.allowed, 'false');
  assert.ok(notices.some(value => value.includes('"reason_code":"native_scope_phase_binding"')));
  assert.ok(summaries.some(value => value.includes('"run_attempt":1')));
});

test('native positive bootstrap no-start records disposition without inventing a scoped plan', async t => {
  const api = historyHarness(t, { runs: [producer('source-delta', { run_attempt: 1, refresh_plan: undefined })],
    receipt: { state: 'not_started', reason: 'native_scope_bootstrap_not_started',
      proof: { run_id: 10, run_attempt: 1 } } });
  const state = await api.read();
  assert.equal(state.eligible, true); assert.equal(state.producer_succeeded, false);
  const run = state.runs.find(row => row.id === 10);
  assert.equal(run.refresh_not_started, true); assert.equal(run.refresh_plan, undefined);
  const diagnostic = require('../maint71_merge_sync_prs').canaryRefreshDiagnostics(state);
  assert.equal(diagnostic.inventory.confirmed_not_started, 1);
  assert.equal(run.refresh_receipt.reason_code, 'native_scope_bootstrap_not_started');
  assert.equal(api.writes.length, 0);
});

test('API refusal diagnostic preserves only fixed operation and bounded status without secret-bearing error data', () => {
  const { refreshReceiptDiagnostic } = require('../maint71_merge_sync_prs');
  const native = { state: 'unknown', reason: 'GET https://private/SECRET_TOKEN returned403',
    proof: { last_read: 'actions.getArtifact', http_status: 403,
      request: { headers: { authorization: 'Bearer SECRET_TOKEN' } } } };
  const result = refreshReceiptDiagnostic({ id: 1, run_attempt: 1 }, native);
  assert.equal(result.reason_code, 'native_scope_read_failed');
  assert.equal(result.last_read, 'actions.getArtifact'); assert.equal(result.http_status, 403);
  assert.doesNotMatch(JSON.stringify(result), /SECRET_TOKEN|authorization|private/);
  for (const status of [99, 600, 403.5, '403', null]) {
    const invalid = refreshReceiptDiagnostic({}, { ...native,
      proof: { last_read: 'actions.getArtifact?token=SECRET_TOKEN', http_status: status } });
    assert.equal(invalid.last_read, undefined); assert.equal(invalid.http_status, undefined);
    assert.doesNotMatch(JSON.stringify(invalid), /SECRET_TOKEN/);
  }
});
