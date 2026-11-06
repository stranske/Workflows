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
const workflow = require('node:fs').readFileSync(path.join(ROOT, '.github/workflows/maint-68-sync-consumer-repos.yml'));
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
    repos: { getContent: wrap('getContent', args => {
      const bytes = args.path === '.github/scripts/sync_run_contract.js' ? state.reportModule : state.workflow;
      return { encoding: 'base64', content: bytes.toString('base64'),
        sha: createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex') };
    }) } } };
  const retryOptions = [];
  const args = { withRetry: (fn, options) => { retryOptions.push(options); return fn(github); }, context: { repo: { owner: 'owner', repo: 'Workflows' } },
    run, defaultBranch: 'main', candidates: ['owner/b', 'owner/a'] };
  return { ...state, state, args, github, retryOptions, read: () => readScopedCanaryReceipt(args) };
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
  const full = JSON.parse(f.files['manifest.full.json']);
  f.files['manifest.json'] = f.files['manifest.full.json'];
  const scope = JSON.parse(f.files['sync-plan-scope.json']);
  Object.assign(scope, { mode: 'full', base_sha: '', plan_id: full.plan_id,
    selected_entry_count: full.entries.length, selected_removal_count: full.removals.length,
    selected_targets: [...full.entries, ...full.removals].map(row => row.target).sort() });
  const phase = JSON.parse(f.files['sync-phase-selection.json']); phase.plan_id = full.plan_id;
  f.files['sync-phase-selection.json'] = JSON.stringify(phase, Object.keys(phase).sort(), 2) + '\n';
  // Fixed producer members use recursively sorted keys.
  f.files['sync-plan-scope.json'] = JSON.stringify(scope, Object.keys(scope).sort(), 2) + '\n';
  f.rebuild();
  assert.equal((await f.read()).state, 'completed');
  const state = await refreshThroughNativeFixture(t, f);
  assert.equal(state.eligible, true); assert.equal(state.producer_succeeded, false);
});

test('native title scope cannot relabel a scoped artifact as full', async () => {
  const f = fixture(); f.run.display_title = f.run.display_title.replace('source-delta', 'full');
  assert.equal((await f.read()).state, 'unknown');
});

test('all native reads use bounded controller retry options and exhausted reads remain unknown', async () => {
  const f = fixture();
  assert.equal((await f.read()).state, 'completed');
  assert.equal(f.retryOptions.length, f.state.calls.length);
  assert.ok(f.retryOptions.length > 0);
  for (const options of f.retryOptions) {
    assert.deepEqual(options, { maxRetries: 2, initialDelay: 250, maxDelay: 1000 });
  }
  let attempts = 0;
  f.args.withRetry = async (fn, options) => {
    assert.deepEqual(options, { maxRetries: 2, initialDelay: 250, maxDelay: 1000 });
    attempts++;
    throw new Error('exhausted native read');
  };
  const result = await f.read();
  assert.equal(result.state, 'unknown');
  assert.equal(attempts, 1);
});

test('real controller wrapper retries transient native reads finitely and preserves unknown on exhaustion', async () => {
  const { createTokenAwareRetry } = require('../github-api-with-retry');
  for (const exhaust of [false, true]) {
    const f = fixture();
    const original = f.github.rest.actions.getWorkflowRunAttempt;
    let reads = 0;
    f.github.rest.actions.getWorkflowRunAttempt = async args => {
      reads++;
      if (exhaust || reads === 1) {
        const error = new Error('synthetic transient native read');
        error.status = 503;
        error.request = { method: 'GET' };
        throw error;
      }
      return original(args);
    };
    const { withRetry } = await createTokenAwareRetry({ github: f.github,
      env: {}, tokenRegistry: { isInitialized: () => false } });
    f.args.withRetry = withRetry;
    const result = await f.read();
    assert.equal(result.state, exhaust ? 'unknown' : 'completed');
    assert.equal(reads, exhaust ? 3 : 2);
    if (exhaust) assert.equal(f.state.calls.length, 0);
  }
});


test('parsed receipts report an explicit predicate when native effect disposition is unknown', async () => {
  const f = fixture(); f.run.conclusion = 'cancelled';
  const result = await f.read();
  assert.equal(result.state, 'unknown');
  assert.equal(result.reason, 'native_scope_effect_disposition_unknown');
  assert.equal(result.proof.run_id, f.run.id);
  assert.equal(result.proof.run_attempt, f.run.run_attempt);
});


const HISTORICAL_PRODUCERS = [
  'd52252dab8a2322021b39a68651592c4e212cdbb98e807750e5db75c00b99235',
  'e24c6413cf57f7e1c3ff536cc581164044afb74aa11fd048caf5b96f099313e9',
  '5684f184111d02e8c9ee270d47c9f59c593da686b9155360ae6eba3f18348579',
];
const REPORT_MODULE = '10d28ca1485d2e3cf8630b915d3964c7f7103983511e2088a1135bc5e79ead46';
function historicalBytes(hash, suffix='yml') {
  const bytes = require('node:zlib').gunzipSync(require('node:fs').readFileSync(
    path.join(ROOT,'tests/fixtures/scoped_refresh_native_producers',`${hash}.${suffix}.gz`)), {maxOutputLength:150000});
  assert.equal(sha(bytes),hash); return bytes;
}
for (const hash of HISTORICAL_PRODUCERS) test(`reviewed complete historical producer ${hash.slice(0,12)} binds only source identity`, async () => {
  const f=fixture(); f.state.workflow=historicalBytes(hash); f.artifact.expired=true;
  const result=await f.read();
  assert.equal(result.state,'unknown'); assert.equal(result.source_commit,'a'.repeat(40));
  assert.equal(result.proof.source_identity_bound,true);
  assert.equal(result.reason,'native_scope_artifact_identity_mismatch');
});
for (const hash of HISTORICAL_PRODUCERS) test(`native schedule uses exact reviewed shape ${hash.slice(0,12)}`, async () => {
  const f=fixture();f.state.workflow=historicalBytes(hash);f.run.event='schedule';f.artifact.expired=true;
  const guard=hash===HISTORICAL_PRODUCERS[2]?'':' guard=delivery-v1';
  f.run.display_title=`Maint 68 canary auto source=${f.run.head_sha} candidates=* dry=false${guard}`;
  const result=await f.read();assert.equal(result.state,'unknown');
  assert.equal(result.source_commit,f.run.head_sha);assert.equal(result.proof.source_identity_bound,true);
});
for (const [name,change] of [
  ['noncanonical mode',f=>{f.run.display_title=f.run.display_title.replace('canary auto','canary full');}],
  ['caller source',f=>{f.run.display_title=f.run.display_title.replace(f.run.head_sha,'d'.repeat(40));}],
  ['caller candidates',f=>{f.run.display_title=f.run.display_title.replace('candidates=*','candidates=owner/a');}],
  ['caller drift',f=>{f.run.display_title+=' drift='+'d'.repeat(64);}],
  ['wrong guard',f=>{f.run.display_title=f.run.display_title.replace(' guard=delivery-v1','');}],
  ['unreviewed producer',f=>{f.state.workflow=Buffer.concat([f.state.workflow,Buffer.from('\n# changed producer\n')]);}],
]) test(`scheduled identity refuses ${name}`,async()=>{
  const f=fixture();f.state.workflow=historicalBytes(HISTORICAL_PRODUCERS[0]);f.run.event='schedule';
  f.run.display_title=`Maint 68 canary auto source=${f.run.head_sha} candidates=* dry=false guard=delivery-v1`;
  change(f);const result=await f.read();assert.equal(result.state,'unknown');
  assert.equal(result.proof.source_identity_bound,undefined);
});
function bootstrapFixture() {
  const f=fixture();f.run.head_sha='67829b6145644352661b56f5251344cf952d0a64';f.run.run_attempt=1;f.run.conclusion='cancelled';
  f.state.workflow=historicalBytes(HISTORICAL_PRODUCERS[0]);f.state.reportModule=historicalBytes(REPORT_MODULE,'js');
  const names=['Prepare sync from manifest','Validate sync files','Sync ${{ matrix.repo }}',
    'Start generated delivery reconciliation','Create failure issue','Generate summary'];
  f.jobs.splice(0,f.jobs.length,...names.map((name,index)=>({id:71+index,run_id:f.run.id,head_sha:f.run.head_sha,
    name,status:'completed',conclusion:'cancelled',runner_id:index===0?0:null,runner_name:index===0?'':null,steps:[]})));
  f.jobs.at(-1).runner_id=123;f.jobs.at(-1).runner_name='GitHub Actions 123';
  f.jobs.at(-1).steps=[['Set up job','success'],['Checkout','success'],['Download sync result artifacts','success'],
    ['Build sync run report','success'],['Generate summary','success'],['Setup promotion health API client','cancelled'],
    ['Report sealed plans awaiting promotion','skipped'],['Upload sync run report','skipped'],
    ['Post Checkout','skipped'],['Complete job',null]].map(([name,conclusion])=>({name,conclusion}));
  f.state.artifacts.length=0;return f;
}
test('reviewed native bootstrap cancellation proves no consumer start without fabricating a tuple',async()=>{
  const f=bootstrapFixture(),result=await f.read();
  assert.equal(result.state,'not_started');assert.equal(result.reason,'native_scope_bootstrap_not_started');
  assert.equal(result.proof.bootstrap_not_started,true);assert.equal(result.proof.report_module_sha256,REPORT_MODULE);
  assert.equal(result.plan_id,undefined);assert.equal(result.source_commit,undefined);
});
for (const [name,change] of [
  ['missing prepare runner',f=>{delete f.jobs[0].runner_id;}],
  ['null prepare runner',f=>{f.jobs[0].runner_id=null;}],
  ['assigned prepare runner',f=>{f.jobs[0].runner_id=42;}],
  ['missing steps',f=>{delete f.jobs[0].steps;}],
  ['executed prepare step',f=>{f.jobs[0].steps=[{name:'Set up job',conclusion:'success'}];}],
  ['earlier attempt',f=>{f.run.run_attempt=2;}],
  ['missing effect job',f=>{f.jobs.splice(2,1);}],
  ['duplicate effect job',f=>{f.jobs.push({...f.jobs[2],id:99});}],
  ['unknown job',f=>{f.jobs[2].name='Unknown effect';}],
  ['native job identity mismatch',f=>{f.jobs[2].run_id=999;}],
  ['executed effect',f=>{f.jobs[2].steps=[{name:'Checkout',conclusion:'success'}];}],
  ['successful effect',f=>{f.jobs[2].conclusion='success';}],
  ['running effect',f=>{f.jobs[2].status='in_progress';}],
  ['summary effect',f=>{f.jobs.at(-1).steps[6].conclusion='success';}],
  ['missing summary effect status',f=>{f.jobs.at(-1).steps.splice(6,1);}],
  ['extra summary execution',f=>{f.jobs.at(-1).steps.push({name:'Unexpected execution',conclusion:'success'});}],
  ['different setup status',f=>{f.jobs.at(-1).steps[5].conclusion='success';}],
  ['different native source tree',f=>{f.run.head_sha='d'.repeat(40);for(const job of f.jobs)job.head_sha=f.run.head_sha;}],
  ['unexpected retained artifact',f=>{f.state.artifacts.push(f.artifact);}],
  ['unreviewed producer',f=>{f.state.workflow=Buffer.concat([f.state.workflow,Buffer.from('\n# changed workflow\n')]);}],
  ['unreviewed summary module',f=>{f.state.reportModule=Buffer.concat([f.state.reportModule,Buffer.from('\n// changed module\n')]);}],
]) test(`bootstrap evidence retains UNKNOWN for ${name}`,async()=>{
  const f=bootstrapFixture();change(f);assert.equal((await f.read()).state,'unknown');
});
test('bootstrap no-start requires fresh unchanged native attempt',async()=>{
  const f=bootstrapFixture();f.github.rest.actions.getWorkflowRun=async()=>({data:{...f.run,run_attempt:2}});
  assert.equal((await f.read()).state,'unknown');
});


test('native read refusal retains bounded operation and HTTP status for safe diagnostics',async()=>{
  const f=fixture();f.args.withRetry=async()=>{const error=new Error('private native error token-must-not-log');error.status=403;throw error;};
  const result=await f.read();assert.equal(result.state,'unknown');
  assert.equal(result.proof.last_read,'actions.getWorkflowRunAttempt');assert.equal(result.proof.http_status,403);
});
