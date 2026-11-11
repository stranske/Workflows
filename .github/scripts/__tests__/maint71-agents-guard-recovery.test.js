'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const native = require('../maint71_merge_sync_prs');
const { CONTEXT, agentsGuardNeedsRecovery, agentsGuardNeedsInspection,
  agentsGuardRefusalHandoff } = require('../maint71_agents_guard_recovery');
const real = require('./fixtures/ready-jobless-guard.json');

function fixture() {
  const data = structuredClone(real), writes = [], reads = [], comments = [];
  const original = () => data.runs.workflow_runs.find(run => run.event === 'pull_request');
  const sdk = { pulls: { get: () => structuredClone(data.pr) }, actions: {
    listWorkflowRuns: () => structuredClone(data.runs),
    getWorkflowRun: () => structuredClone(original()),
    listJobsForWorkflowRunAttempt: () => data.jobs,
    reRunWorkflow: args => { writes.push({ action: 'rerun', args }); return { status: 201 }; },
  }, repos: { getCommit: () => data.commit, listCommitStatusesForRef: () => data.statuses || [] },
  issues: { listComments: () => structuredClone(comments), createComment: args => {
    writes.push({ action: 'claim', args });
    const comment = { id: 100 + comments.length, user: { login: 'stranske' }, body: args.body };
    comments.push(comment); return structuredClone(comment);
  } } };
  const client = { rest: Object.fromEntries(Object.entries(sdk).map(([group, methods]) =>
    [group, Object.fromEntries(Object.entries(methods).map(([method, fn]) =>
      [method, async args => { reads.push({ group, method, args }); const value = await fn(args);
        return method === 'reRunWorkflow' ? value : { data: value }; }]))])) };
  const options = [];
  const args = { owner: 'stranske', repo: 'Ready', pr: structuredClone(data.pr),
    withRetry: (fn, opts) => { options.push(opts); return fn(client); },
    context: { repo: { owner: 'stranske', repo: 'Workflows' }, runId: 999999 } };
  return { data, sdk, client, reads, writes, comments, args, options, original,
    run: extra => native.recoverCancelledAgentsGuard({ ...args, ...extra }) };
}

test('authentic Ready jobless cancellation selects only its original ordinary event', async () => {
  const f = fixture();
  const result = await f.run();
  assert.equal(result.mode, 'requested', JSON.stringify(result));
  assert.equal(result.run_id, 42761394324);
  assert.equal(result.run_attempt, 1);
  assert.deepEqual(f.writes.map(row => row.action), ['claim', 'rerun']);
  assert.deepEqual(f.writes[1].args, { owner: 'stranske', repo: 'Ready', run_id: 42761394324 });
  assert.equal(f.options.filter(option => option?.maxRetries === 0).length, 2);
});

test('a fresh observation with a durable claim never repeats an accepted rerun', async () => {
  const f = fixture(); await f.run();
  const report = await f.run();
  assert.equal(report.mode, 'wait');
  assert.equal(report.reason, 'guard_rerun_claim_retained');
  assert.equal(f.writes.filter(row => row.action === 'rerun').length, 1);
});

test('uncertain rerun keeps its durable claim and reads original state without another POST', async () => {
  const f = fixture();
  f.sdk.actions.reRunWorkflow = () => { throw new Error('connection lost'); };
  // Replace the transport method, retaining the real claim behavior.
  const originalRetry = f.args.withRetry;
  f.args.withRetry = (fn, opts) => originalRetry(client => {
    client.rest.actions.reRunWorkflow = async args => {
      f.writes.push({ action: 'rerun', args }); throw new Error('connection lost');
    }; return fn(client);
  }, opts);
  assert.equal((await f.run()).mode, 'wait');
  assert.equal((await f.run()).reason, 'guard_rerun_claim_retained');
  assert.equal(f.writes.filter(row => row.action === 'rerun').length, 1);
});

test('real qualified result clears recovery by readback without rewriting a receipt', async () => {
  const f = fixture(); await f.run();
  const run = f.original(); run.run_attempt = 2; run.conclusion = 'success';
  run.run_started_at = '2026-11-10T08:20:00Z';
  f.data.statuses = [{ context: CONTEXT, description: '[guard-pr:677] passed', state: 'success',
    target_url: run.html_url, updated_at: '2026-11-10T08:21:00Z' }];
  const report = await f.run();
  assert.equal(report.mode, 'existing'); assert.equal(report.qualified_pass, true);
  assert.equal(f.writes.filter(row => row.action === 'rerun').length, 1);
});

test('actual jobless input dry run performs no mutation', async () => {
  const f = fixture(); assert.equal((await f.run({ dryRunMode: true })).mode, 'would-rerun');
  assert.equal(f.writes.length, 0);
});

for (const [name, change] of [
  ['changed head', f => { f.data.pr.head.sha = 'a'.repeat(40); }],
  ['foreign head repository', f => { f.data.pr.head.repo.full_name = 'other/Ready'; }],
  ['unsealed delivery', f => { f.data.pr.body = f.data.pr.body.replace('"delivery_state":"sealed"', '"delivery_state":"reviewing"'); }],
  ['unverified head', f => { f.data.commit.commit.verification.verified = false; }],
  ['wrong original association', f => { f.original().pull_requests = [{ number: 999 }]; }],
  ['foreign original repository', f => { f.original().head_repository.id++; }],
  ['non-jobless original', f => { f.data.jobs = { total_count: 1, jobs: [{ id: 1 }] }; }],
  ['missing job inventory', f => { f.data.jobs = { jobs: [] }; }],
  ['only target events', f => { f.data.runs.workflow_runs = f.data.runs.workflow_runs.filter(r => r.event !== 'pull_request'); f.data.runs.total_count--; }],
  ['truncated run inventory', f => { f.data.runs.total_count++; }],
  ['real failed original', f => { f.original().conclusion = 'failure'; }],
  ['security-held original', f => { f.original().conclusion = 'action_required'; }],
  ['repeated cancellation', f => { f.original().run_attempt = 3; }],
  ['wrong native writer', f => { f.args.context.repo.repo = 'Other'; }],
]) test(`no rerun for ${name}`, async () => {
  const f = fixture(); change(f); const result = await f.run();
  assert.notEqual(result.mode, 'requested'); assert.equal(f.writes.length, 0, JSON.stringify(result));
});

test('active Guard writer remains protected', async () => {
  const f = fixture(); f.data.runs.workflow_runs[0].status = 'queued';
  assert.equal((await f.run()).mode, 'wait'); assert.equal(f.writes.length, 0);
});

test('changed original attempt after claim does not rerun or release the claim', async () => {
  const f = fixture(); const original = f.args.withRetry;
  f.args.withRetry = (fn, opts) => original(client => {
    client.rest.actions.getWorkflowRun = async () => ({ data: { ...f.original(), run_attempt: 2 } });
    return fn(client);
  }, opts);
  assert.equal((await f.run()).mode, 'unknown');
  assert.deepEqual(f.writes.map(row => row.action), ['claim']);
});

test('missing qualified status never turns an ordinary success into PASS or rerun authority', async () => {
  const f = fixture(); f.original().conclusion = 'success';
  assert.equal((await f.run()).reason, 'guard_success_without_current_qualified_pass');
  assert.equal(f.writes.length, 0);
});

test('only the exact Guard context activates recovery', () => {
  assert.equal(agentsGuardNeedsRecovery({ pending: [{ name: CONTEXT }] }), true);
  assert.equal(agentsGuardNeedsRecovery({ declared_contexts: { never_started: [CONTEXT] } }), true);
  assert.equal(agentsGuardNeedsRecovery({ failed: [{ name: 'guard' }] }), false);
  assert.equal(agentsGuardNeedsRecovery({ failed: [{ name: 'Gate / gate' }] }), false);
});

test('refusal repair hint does not replace independent check or review blockers', () => {
  const recovery = { mode: 'refused', next_command: 'repair-workflow-admission' };
  const onlyGuard = { pending: [{ name: CONTEXT }] };
  assert.equal(agentsGuardRefusalHandoff(onlyGuard, recovery), recovery.next_command);
  assert.equal(agentsGuardRefusalHandoff(onlyGuard, recovery, true), null);
  assert.equal(agentsGuardRefusalHandoff({ ...onlyGuard, failed: [{ name: 'production tests' }] }, recovery), null);
});

test('real Gate-only protection and target-event Guard success still select original-event inspection', () => {
  const input = require('./fixtures/ready-unqualified-guard-selection.json');
  const checks = [...input.checks, ...input.statuses.map(native.legacyStatusAsCheck)];
  const classification = require('../sync_pr_merge_contract').classifySyncPrChecks({
    checkRuns: checks, requiredContexts: input.required_contexts });
  assert.equal(classification.status, 'ready');
  assert.equal(agentsGuardNeedsRecovery(classification), false);
  assert.equal(agentsGuardNeedsInspection(classification, checks), true);
});

for (const dryRun of [true, false]) test(`native Guard-only script pins the owner client (dry=${dryRun})`, async () => {
  const fs = require('node:fs'), path = require('node:path');
  const workflow = fs.readFileSync(path.join(__dirname, '../../workflows/maint-71-merge-sync-prs.yml'), 'utf8');
  assert.match(workflow, /github\.event\.action != 'maint71-review-reassessment' && inputs\.agents_guard_recovery_json == ''/);
  assert.match(workflow, /inputs\.agents_guard_recovery_json != '' && github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /group: \$\{\{ inputs\.agents_guard_recovery_json == '' && github\.event\.action == 'maint71-review-reassessment'/);
  const script = workflow.split('      - name: Recover original jobless Guard events')[1]
    .split('      - name: Upload Guard recovery result')[0].split('          script: |\n')[1]
    .split('\n').map(line => line.replace(/^ {12}/, '')).join('\n');
  const f = fixture(); let report;
  const load = name => name === 'fs' ? { mkdirSync() {}, writeFileSync(_name, body) { report = JSON.parse(body); } }
    : name.includes('github-api-with-retry') ? {
      createTokenAwareRetry: async () => ({ withRetry: async () => { throw new Error('wrong-scoped pool client'); } }),
      withRetry: (fn, options) => { assert.equal(options.github, f.client); return f.args.withRetry(fn, options); },
    }
      : native;
  const fn = new (Object.getPrototypeOf(async function () {}).constructor)('require', 'process', 'github', 'context', 'core', script);
  await fn(load, { env: { GUARD_RECOVERY_TARGETS: JSON.stringify([{ repository: 'stranske/Ready', pr: 677,
    head_sha: f.data.pr.head.sha }]), GUARD_RECOVERY_DRY_RUN: String(dryRun), OWNER_PR_PAT: 'test-owner' } }, f.client, f.args.context, { notice() {} });
  assert.equal(report.results[0].mode, dryRun ? 'would-rerun' : 'requested');
  assert.equal(report.requests, dryRun ? 0 : 1);
  assert.equal(f.writes.filter(row => row.action === 'rerun').length, dryRun ? 0 : 1);
});
