'use strict';

// Synthetic native responses and real compiler/ZIP bytes only. No GitHub or
// provider I/O, artifact publication, or consumer mutation occurs here.
const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const path = require('node:path');
const { readScopedCanaryReceipt } = require('../maint68_scoped_receipt');
const ROOT = path.resolve(__dirname, '../../..');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const workflow = execFileSync('git', ['show', 'HEAD:.github/workflows/maint-68-sync-consumer-repos.yml'], { cwd: ROOT });
const members = JSON.parse(execFileSync('python3', ['-c', `
import json,tempfile
from pathlib import Path
from scripts.sync_manifest_compiler import compile_manifest
from scripts.scope_consumer_sync_plan import select_plan
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory);(root/'.github').mkdir();(root/'scripts').mkdir()
 (root/'scripts/copied.js').write_text('copied\\n');(root/'scripts/other.js').write_text('other\\n')
 (root/'.github/sync-manifest.yml').write_text('version: 1\\nscripts:\\n  - source: scripts/copied.js\\n    description: café\\n  - source: scripts/other.js\\n    description: unrelated\\n')
 full=compile_manifest(root/'.github/sync-manifest.yml',repo_root=root).to_plan()
 plan,scope=select_plan(full,mode='source-delta',changed_paths=['scripts/copied.js'],base_sha='b'*40,source_commit='a'*40)
 phase={'schema':'workflows.consumer-sync-phase-selection/v1','version':1,'phase':'canary','plan_id':plan['plan_id'],'selected_repos':['owner/a','owner/b']}
 print(json.dumps({name:json.dumps(value,sort_keys=True,indent=2,ensure_ascii=True)+'\\n' for name,value in [('manifest.json',plan),('manifest.full.json',full),('sync-plan-scope.json',scope),('sync-phase-selection.json',phase)]}))
`], { cwd: ROOT, encoding: 'utf8' }));
function zip(files) {
  return execFileSync('python3', ['-c', 'import io,json,sys,zipfile; b=io.BytesIO(); z=zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED); [z.writestr(k,v) for k,v in json.load(sys.stdin).items()]; z.close(); sys.stdout.buffer.write(b.getvalue())'],
    { input: JSON.stringify(files) });
}
function fixture({ started = true } = {}) {
  const run = { id: 70, run_attempt: started ? 2 : 1, head_sha: 'c'.repeat(40), path: '.github/workflows/maint-68-sync-consumer-repos.yml',
    event: 'workflow_dispatch', head_branch: 'main', status: 'completed', conclusion: 'success',
    display_title: `Maint 68 canary source-delta  source=${'a'.repeat(40)} candidates=owner/a,owner/b dry=false  guard=delivery-v1`,
    repository: { id: 1, full_name: 'owner/Workflows' }, head_repository: { id: 1 } };
  const steps = ['Resolve immutable plan scope', 'Checkout', 'Validate immutable source reachability',
    'Authorize canary payload mutation', 'Upload plan and prospective-diff evidence'].map(name => ({ name, status: 'completed',
    conclusion: name === 'Authorize canary payload mutation' && !started ? 'skipped' : 'success',
    started_at: '2026-10-27T22:00:00Z', completed_at: '2026-10-27T22:01:00Z' }));
  const jobs = [{ id: 71, run_id: 70, head_sha: run.head_sha, name: 'Prepare sync from manifest', steps },
    ...(started ? ['owner/a', 'owner/b'].map((repo, index) => ({ id: 72 + index, run_id: 70, head_sha: run.head_sha,
      name: `Sync ${repo}`, status: 'completed', conclusion: 'success' }))
      : [{ id: 72, run_id: 70, head_sha: run.head_sha, name: 'Sync ${{ matrix.repo }}', status: 'completed', conclusion: 'skipped' }])];
  const files = { ...members }, artifact = { id: 80, name: 'sync-plan-and-prospective-diffs', expired: false,
    created_at: '2026-10-27T22:00:30Z', workflow_run: { id: 70, head_sha: run.head_sha, head_branch: 'main', repository_id: 1, head_repository_id: 1 } };
  let archive;
  const state = { files, run, jobs, artifact, workflow: Buffer.from(workflow), artifacts: [artifact], calls: [],
    rebuild() { archive = zip(files); artifact.size_in_bytes = archive.length; artifact.digest = `sha256:${sha(archive)}`; },
    corruptArchive() { archive = Buffer.from('corrupt'); } };
  state.rebuild();
  const methods = {
    getWorkflowRunAttempt: () => run, getWorkflowRun: () => run,
    listJobsForWorkflowRunAttempt: () => ({ total_count: jobs.length, jobs }),
    listWorkflowRunArtifacts: () => ({ total_count: state.artifacts.length, artifacts: state.artifacts }),
    getArtifact: () => artifact, downloadArtifact: () => archive,
  };
  const wrap = (name, fn) => async args => { state.calls.push({ name, args }); return { data: fn(args) }; };
  const github = { rest: { actions: Object.fromEntries(Object.entries(methods).map(([name, fn]) => [name, wrap(name, fn)])),
    repos: { getContent: wrap('getContent', () => ({ encoding: 'base64', content: state.workflow.toString('base64'),
      sha: createHash('sha1').update(`blob ${state.workflow.length}\0`).update(state.workflow).digest('hex') })) } } };
  const args = { withRetry: fn => fn(github), context: { repo: { owner: 'owner', repo: 'Workflows' } },
    run, defaultBranch: 'main', candidates: ['owner/b', 'owner/a'] };
  return { ...state, state, args, github, read: () => readScopedCanaryReceipt(args) };
}
test('actual compiled scoped plan and native attempt/job/archive identify a completed matching delivery', async () => {
  const f = fixture(), result = await f.read();
  assert.equal(result.state, 'completed'); assert.equal(result.plan_scope, 'source-delta');
  assert.equal(result.scope_base_sha, 'b'.repeat(40)); assert.equal(result.source_commit, 'a'.repeat(40));
  assert.equal(result.plan.entries.length, 1); assert.match(result.plan.entries[0].description, /café/);
  assert.equal(result.proof.source_identity_bound, true);
  assert.ok(f.state.calls.every(call => call.args.request.timeout === 15000 && call.args.request.retries === 0));
});
test('retained no-authorization plus skipped native consumer jobs is confirmed not started', async () => {
  const result = await fixture({ started: false }).read(); assert.equal(result.state, 'not_started');
  assert.equal(result.plan_scope, 'source-delta');
});
test('a skipped rerun cannot erase possible effects from an earlier native attempt', async () => {
  const f = fixture({ started: false }); f.run.run_attempt = 2;
  assert.equal((await f.read()).state, 'unknown');
});
for (const [name, change] of [
  ['foreign repository', f => { f.run.repository.full_name = 'foreign/Workflows'; }],
  ['forked workflow', f => { f.run.head_repository.id = 2; }],
  ['foreign workflow', f => { f.run.path = '.github/workflows/other.yml'; }],
  ['wrong artifact attempt window', f => { f.artifact.created_at = '2026-10-27T21:00:00Z'; }],
  ['artifact run substitution', f => { f.artifact.workflow_run.id = 99; }],
  ['artifact branch substitution', f => { f.artifact.workflow_run.head_branch = 'other'; }],
  ['expired artifact', f => { f.artifact.expired = true; }],
  ['ambiguous artifact', f => { f.state.artifacts.push({ ...f.artifact, id: 81 }); }],
  ['digest mismatch', f => { f.state.corruptArchive(); }],
  ['archive member missing', f => { delete f.files['manifest.full.json']; f.state.rebuild(); }],
  ['duplicate plan member', f => { f.files['manifest.json'] = f.files['manifest.json'].replace('{', '{"schema":"forged",'); f.state.rebuild(); }],
  ['plan body rebound', f => { f.files['manifest.json'] = f.files['manifest.json'].replace('café', 'changed').replace('caf\\u00e9', 'changed'); f.state.rebuild(); }],
  ['source rebound', f => { f.files['sync-plan-scope.json'] = f.files['sync-plan-scope.json'].replace('a'.repeat(40), 'd'.repeat(40)); f.state.rebuild(); }],
  ['phase plan rebound', f => { f.files['sync-phase-selection.json'] = f.files['sync-phase-selection.json'].replace(/sha256:[a-f0-9]{64}/, 'sha256:' + '0'.repeat(64)); f.state.rebuild(); }],
  ['failed consumer job', f => { f.jobs[1].conclusion = 'failure'; }],
  ['skipped consumer job after authorization', f => { f.jobs[1].conclusion = 'skipped'; }],
  ['missing consumer job', f => { f.jobs.pop(); }],
]) test(`native scoped receipt remains unknown for ${name}`, async () => {
  const f = fixture(); change(f); assert.equal((await f.read()).state, 'unknown');
});
test('expired different-source history can be excluded only with native reviewed source-binding proof', async () => {
  const f = fixture(); f.artifact.expired = true;
  let result = await f.read(); assert.equal(result.state, 'unknown'); assert.equal(result.source_commit, 'a'.repeat(40));
  assert.equal(result.proof.source_identity_bound, true);
  f.state.workflow = Buffer.from(workflow.toString().replace('Checked-out source does not match', 'changed source semantics'));
  result = await f.read(); assert.equal(result.proof.source_identity_bound, undefined); assert.equal(result.source_commit, undefined);
});
test('unrecognized source code or caller booleans cannot authenticate missing history', async () => {
  const f = fixture(); f.state.artifacts.length = 0; f.args.source_identity_bound = true;
  f.state.workflow = Buffer.from(workflow.toString().replace('Checked-out source does not match', 'changed source semantics'));
  const result = await f.read(); assert.equal(result.state, 'unknown'); assert.equal(result.proof.source_identity_bound, undefined);
});
test('an inserted post-validation checkout cannot authenticate unrelated missing history', async () => {
  const f = fixture(); f.artifact.expired = true;
  f.state.workflow = Buffer.from(workflow.toString().replace('      - name: Setup Python',
    "      - name: Replace already-validated source\n        run: git checkout different-source\n\n      - name: Setup Python"));
  assert.notDeepEqual(f.state.workflow, workflow);
  const result = await f.read(); assert.equal(result.state, 'unknown');
  assert.equal(result.proof.source_identity_bound, undefined); assert.equal(result.source_commit, undefined);
});
test('mixed skipped consumer identities cannot establish confirmed not started', async () => {
  const f = fixture({ started: false }); f.jobs[1].run_id = 999; f.jobs[1].head_sha = 'e'.repeat(40);
  assert.equal((await f.read()).state, 'unknown');
});
test('fresh native attempt revalidation cannot substitute a different run ID', async () => {
  const f = fixture(); f.github.rest.actions.getWorkflowRun = async () => ({ data: { ...f.run, id: 999 } });
  assert.equal((await f.read()).state, 'unknown');
});

async function refreshThroughNativeFixture(t, f, sourceSha = 'a'.repeat(40)) {
  const { readCanaryRefreshState } = require('../maint71_merge_sync_prs');
  const renderer = require('../consumer_delivery_digest');
  const nativeContent = f.github.rest.repos.getContent;
  f.github.rest.repos.getCommit = async () => ({ data: { sha: sourceSha } });
  f.github.rest.repos.getContent = async args => args.path === 'config/consumer_sync_canaries.json'
    ? { data: { content: Buffer.from(JSON.stringify({ canaries: [{ repo: 'owner/a' }, { repo: 'owner/b' }] })).toString('base64') } }
    : nativeContent(args);
  f.github.rest.actions.listWorkflowRuns = async args => ({ data: { workflow_runs: args.status ? [] : [f.run] } });
  f.github.rest.pulls = { list: async () => ({ data: [] }) };
  f.args.context.payload = { repository: { default_branch: 'main' } };
  const plan = JSON.parse(members['manifest.json']);
  const files = Object.fromEntries(['owner/a', 'owner/b'].map(repo => [repo, {
    'scripts/copied.js': { content: 'e'.repeat(64), executable: false, create_only: false },
    'scripts/other.js': { content: 'f'.repeat(64), executable: false, create_only: false },
  }]));
  t.mock.method(renderer, 'readDeliveryPayload', async (_sha, _repos, request) =>
    renderer.scopedDeliveryPayload({ digest: `sha256:${'d'.repeat(64)}`, files }, request));
  return readCanaryRefreshState({ withRetry: f.args.withRetry, context: f.args.context,
    expectedCanaries: f.args.candidates, sourceSha, planId: plan.plan_id, planScope: 'source-delta',
    scopeBaseSha: 'b'.repeat(40), plan });
}
test('actual refresh collector deduplicates the authenticated completed same scoped plan', async t => {
  const state = await refreshThroughNativeFixture(t, fixture());
  assert.equal(state.eligible, false); assert.equal(state.producer_succeeded, true);
});
test('actual refresh collector admits the native confirmed-not-started same scoped request', async t => {
  const state = await refreshThroughNativeFixture(t, fixture({ started: false }));
  assert.equal(state.eligible, true); assert.equal(state.producer_succeeded, false);
});
test('actual refresh collector holds unknown same-source history instead of repeating it', async t => {
  const f = fixture(); f.artifact.expired = true;
  const state = await refreshThroughNativeFixture(t, f);
  assert.equal(state.eligible, false); assert.equal(state.state, 'unknown');
});
test('actual refresh collector positively excludes authenticated different-source missing history', async t => {
  const f = fixture(); f.artifact.expired = true;
  const state = await refreshThroughNativeFixture(t, f, 'd'.repeat(40));
  assert.equal(state.eligible, true);
});
test('actual refresh collector cannot mistake prior full delivery for the requested scoped shipment', async t => {
  const f = fixture(); f.run.display_title = f.run.display_title.replace('source-delta', 'full');
  const state = await refreshThroughNativeFixture(t, f);
  assert.equal(state.eligible, true); assert.equal(state.producer_succeeded, false);
});
