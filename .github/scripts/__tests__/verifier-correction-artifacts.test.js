'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),os=require('os'),path=require('path'),{execFileSync}=require('child_process'),{createHash}=require('crypto');
const {createArtifactTransport,artifactName}=require('../verifier_correction_artifacts');
const sha=value=>createHash('sha256').update(value).digest('hex');
function zip(member,bytes) {
 return execFileSync('python3',['-c','import io,sys,json,zipfile,base64; x=json.load(sys.stdin); b=io.BytesIO(); z=zipfile.ZipFile(b,"w"); z.writestr(x["name"],base64.b64decode(x["body"])); z.close(); sys.stdout.buffer.write(b.getvalue())'],{input:JSON.stringify({name:member,body:bytes.toString('base64')})});
}
async function fixture(t,kind='ledger') {
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'correction-proof-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const run={id:700,run_attempt:2,path:['started','redispatch','formatredispatch','createdpr'].includes(kind)?'.github/workflows/agents-auto-pilot.yml':'.github/workflows/agents-verify-to-new-pr.yml',event:'workflow_dispatch',status:'in_progress',head_sha:'f'.repeat(40),head_branch:'main',repository:{id:1,full_name:'stranske/Example'},head_repository:{id:1,full_name:'stranske/Example'},created_at:'2026-10-26T00:00:00Z'};
 const jobs=[{id:81,name:'Apply admitted correction',run_id:700,run_attempt:2,head_sha:run.head_sha,steps:[{name:'Consume admitted correction',status:'in_progress',started_at:'2026-10-26T00:00:00Z'}]},
 {id:82,name:'auto-pilot',run_id:700,run_attempt:2,head_sha:run.head_sha,steps:[{name:'Record admitted correction start',status:'in_progress',started_at:'2026-10-26T00:00:00Z'},
 {name:'Re-dispatch for next step',status:'in_progress',started_at:'2026-10-26T00:00:00Z'},
 {name:'Execute step - Create PR',status:'in_progress',started_at:'2026-10-26T00:00:00Z'}]},
 {id:83,name:'collect-correction',run_id:700,run_attempt:2,head_sha:run.head_sha,steps:[{name:'Upload admitted correction request',status:'completed',conclusion:'success',started_at:'2026-10-26T00:00:00Z',completed_at:'2026-10-26T00:02:00Z'}]}];
 jobs.push({id:84,name:'format-pause-wakeup',run_id:700,run_attempt:2,head_sha:run.head_sha,steps:[{name:'Clear pause and redispatch format step',status:'in_progress',started_at:'2026-10-26T00:00:00Z'}]});
 const metadata=[],archives=new Map();let next=10,uploads=0,loseAck=false;
 const state={run,jobs,metadata,archives,setLoseAck:value=>{loseAck=value;},get uploads(){return uploads;}};
 const methods={getWorkflowRun:async()=>run,getWorkflowRunAttempt:async()=>run,listJobsForWorkflowRunAttempt:async()=>({total_count:jobs.length,jobs}),getArtifact:async args=>metadata.find(row=>row.id===args.artifact_id),downloadArtifact:async args=>archives.get(args.artifact_id),listWorkflowRunArtifacts:async()=>({total_count:metadata.length,artifacts:metadata}),listWorkflowRuns:async()=>({total_count:1,workflow_runs:[run]})};
 const repos={get:async()=>({full_name:'stranske/Example',default_branch:'main'}),getCommit:async()=>({sha:run.head_sha}),compareCommitsWithBasehead:async()=>({status:'identical',base_commit:{sha:run.head_sha},merge_base_commit:{sha:run.head_sha}})};
 const wrap=group=>Object.fromEntries(Object.entries(group).map(([name,fn])=>[name,async args=>({data:await fn(args)})]));
 const github={rest:{actions:wrap(methods),repos:wrap(repos)}};
 const artifactClient={uploadArtifact:async(name,files)=>{uploads++;const body=fs.readFileSync(files[0]),archive=zip(path.basename(files[0]),body),id=next++;
 metadata.push({id,name,expired:false,size_in_bytes:archive.length,digest:`sha256:${sha(archive)}`,created_at:'2026-10-26T00:01:00Z',workflow_run:{id:700,head_sha:run.head_sha,repository_id:1,head_repository_id:1}});archives.set(id,archive);if(loseAck)throw Error('lost ACK after retained upload');return {id};}};
 const io=await createArtifactTransport({github,repository:'stranske/example',current:{run_id:700,run_attempt:2},artifactClient,outputDirectory:root,clock:()=>new Date('2026-10-26T00:02:00Z')});
 return {...state,state,io,methods,repos,github};
}
test('immutable checkpoint upload is positively read back through canonical run/attempt/job/archive/member proof',async t=>{
 const f=await fixture(t),bytes=Buffer.from('{"inert":"intent"}\n'),proof=await f.io.publish('ledger',bytes,`${'a'.repeat(64)}-r1`);
 assert.equal(proof.run_id,700);assert.equal(proof.run_attempt,2);assert.equal(proof.member_sha256,sha(bytes));assert.equal(f.state.uploads,1);
 const read=await f.io.load(proof,'ledger',artifactName('ledger',700,2,`${'a'.repeat(64)}-r1`));assert.ok(read.bytes.equals(bytes));
});
test('lost upload ACK permits no effect until exact immutable readback, and absent/ambiguous data remains UNKNOWN',async t=>{
 const f=await fixture(t);f.state.setLoseAck(true);const proof=await f.io.publish('ledger',Buffer.from('inert\n'),`${'a'.repeat(64)}-r1`);assert.equal(proof.artifact_id,10);
 const absent=await fixture(t);absent.github.rest.actions.listWorkflowRunArtifacts=async()=>({data:{total_count:0,artifacts:[]}});absent.state.setLoseAck(true);
 await assert.rejects(absent.io.publish('ledger',Buffer.from('inert\n'),`${'b'.repeat(64)}-r1`),/UNKNOWN/);
});
test('foreign/unmerged origin, wrong attempt/step, expiry and corrupt archives cannot authenticate checkpoints',async t=>{
 for(const change of [f=>{f.state.run.head_branch='unmerged';},f=>{f.state.run.head_repository.id=2;},f=>{f.state.metadata[0].expired=true;},
 f=>{f.state.metadata[0].digest=`sha256:${'0'.repeat(64)}`;},f=>{f.state.jobs[0].run_attempt=1;},f=>{f.state.jobs[0].steps[0].started_at='2026-10-26T00:03:00Z';}]) {
  const f=await fixture(t),proof=await f.io.publish('ledger',Buffer.from('inert\n'),`${'a'.repeat(64)}-r1`);change(f);
  await assert.rejects(f.io.load(proof,'ledger',artifactName('ledger',700,2,`${'a'.repeat(64)}-r1`)));
 }
});

const {digest}=require('../verification_event');
const {seedForRequest,effectKey}=require('../verifier_correction_effects');
const {correctionHistory,createArtifactLedger}=require('../verifier_correction_artifacts');
async function admitted(t) {
 const f=await fixture(t),request=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-request.json'));
 const seed=seedForRequest(request),payload={schema:'closer-correction-admitted/v1',status:'admitted',request,seed,effect_key:effectKey(seed),
 collector:{repository:request.target.repository,run_id:700,run_attempt:2},decision:{findings:[{classification:'ordinary_substantive'}]}};
 const context={...payload,context_sha256:digest(payload)},proof=await f.io.publish('admitted',Buffer.from(JSON.stringify(context)));
 // Prior attempt completed without an effect job execution. The current attempt
 // is independently authenticated through its retained context and checkpoints.
 f.state.run.status='completed';
 const original=f.github.rest.actions.listJobsForWorkflowRunAttempt;
 f.github.rest.actions.listJobsForWorkflowRunAttempt=async args=>args.attempt_number===1?{data:{total_count:1,jobs:[{
 id:80,name:'Apply admitted correction',run_id:700,run_attempt:1,head_sha:f.state.run.head_sha,status:'completed',conclusion:'skipped',steps:[]}]}}:original(args);
 const getAttempt=f.github.rest.actions.getWorkflowRunAttempt;
 f.github.rest.actions.getWorkflowRunAttempt=async args=>{const data=(await getAttempt(args)).data;return {data:{...data,run_attempt:args.attempt_number}};};
 return {...f,request,context,proof};
}
function intent(f,revision=1) {
 const payload={schema:'closer-correction-effect-ledger/v1',effect_key:f.context.effect_key,revision,kind:'intent',phase:'autopilot_dispatch',
 request_sha256:f.request.request_sha256,consumer:{run_id:'700',run_attempt:'2'}};
 return {...payload,record_sha256:digest(payload)};
}
test('real immutable transport ledger confirms exact contiguous journal before exposing dispatch selector',async t=>{
 const f=await admitted(t),ledger=await createArtifactLedger({transport:f.io,request:f.request,since:'2026-10-26T00:00:00Z',admittedProof:f.proof});
 assert.deepEqual(await ledger.read(f.context.effect_key),{revision:0,records:[]});
 const record=intent(f);await ledger.append({effect_key:f.context.effect_key,expected_revision:0,record});
 assert.deepEqual(await ledger.read(f.context.effect_key),{revision:1,records:[record]});
 const issue={number:'9',node_id:'I_9',body_sha256:'b'.repeat(64)},selector=await ledger.continuationSelector({issue});
 assert.equal(selector.collector.artifact_id,f.proof.artifact_id);assert.equal(selector.intent.revision,1);
 assert.equal(selector.intent.member_sha256,sha(Buffer.from(JSON.stringify(record)+'\n')));assert.deepEqual(selector.issue,issue);
 await assert.rejects(ledger.append({effect_key:f.context.effect_key,expected_revision:0,record}),/revision conflict/);
});
test('expired/missing checkpoints, duplicate revisions and unknown prior attempts never imply empty history',async t=>{
 for(const mutate of [
 f=>{f.state.run.status='in_progress';},
 f=>{f.state.metadata.find(row=>row.name.includes('-admitted-')).expired=true;},
 f=>{const row=f.state.metadata.find(row=>row.name.includes('-ledger-'));f.state.metadata.push({...row,id:99});},
 f=>{f.state.metadata.find(row=>row.name.includes('-ledger-')).expired=true;},
 ]) {
  const f=await admitted(t),ledger=await createArtifactLedger({transport:f.io,request:f.request,since:'2026-10-26T00:00:00Z',admittedProof:f.proof});
  await ledger.append({effect_key:f.context.effect_key,expected_revision:0,record:intent(f)});mutate(f);
  await assert.rejects(ledger.read(f.context.effect_key));
 }
});
test('caller aliases cannot replace first original deadline or budget through a new request digest',async t=>{
 const f=await admitted(t),request=structuredClone(f.request);request.original_operation.hold_id='alias';
 const {request_sha256,...payload}=request;request.request_sha256=digest(payload);
 const ledger=await createArtifactLedger({transport:f.io,request,since:'2026-10-26T00:00:00Z',admittedProof:f.proof});
 await assert.rejects(ledger.read(f.context.effect_key),/Original request\/limits rebound/);
});
test('foreign run-title exclusion cannot skip canonical workflow authentication',async t=>{
 const f=await admitted(t);f.state.run.display_title='Correction PR 8';f.state.run.head_branch='unreviewed';
 await assert.rejects(correctionHistory({transport:f.io,request:f.request,since:'2026-10-26T00:00:00Z'}),/trusted default-branch/);
});

test('deleted prior checkpoint history cannot become revision zero; only positively skipped historical effects are empty',async t=>{
 for(const conclusion of ['failure','success','skipped']) {
  const f=await admitted(t);f.io.current={run_id:701,run_attempt:1};
  const job=f.state.jobs.find(row=>row.name==='Apply admitted correction');job.status='completed';job.conclusion=conclusion;
  const ledger=await createArtifactLedger({transport:f.io,request:f.request,since:'2026-10-26T00:00:00Z',admittedProof:f.proof});
  if(conclusion==='skipped')assert.deepEqual(await ledger.read(f.context.effect_key),{revision:0,records:[]});
  else await assert.rejects(ledger.read(f.context.effect_key),/missing checkpoints/);
 }
});

test('even the active attempt cannot forget a checkpoint it already confirmed',async t=>{
 const f=await admitted(t),ledger=await createArtifactLedger({transport:f.io,request:f.request,since:'2026-10-26T00:00:00Z',admittedProof:f.proof});
 await ledger.append({effect_key:f.context.effect_key,expected_revision:0,record:intent(f)});
 f.state.metadata.splice(f.state.metadata.findIndex(row=>row.name.includes('-ledger-')),1);
 await assert.rejects(ledger.read(f.context.effect_key),/history disappeared/);
});

test('missing/malformed or server-out-of-scope run timestamps cannot silently erase history',async t=>{
 for(const value of [undefined,'invalid','2020-01-01T00:00:00Z']) {
  const f=await fixture(t);f.state.run.created_at=value;
  await assert.rejects(f.io.runs('.github/workflows/agents-verify-to-new-pr.yml','2026-10-26T00:00:00Z'),/creation time/);
 }
});

test('canonical live precursor intents can be read by the child; started admission still requires completed producer step',async t=>{
 for(const kind of ['ledger','redispatch','formatredispatch','createdpr','started']) {
  const f=await fixture(t,kind),suffix=kind==='ledger'?`${'a'.repeat(64)}-r1`:'',proof=await f.io.publish(kind,Buffer.from('inert immutable precursor\n'),suffix);
  const child=await createArtifactTransport({github:f.github,repository:'stranske/example',current:{run_id:701,run_attempt:1},clock:()=>new Date('2026-10-26T00:02:00Z')});
  const read=()=>child.load(proof,kind,artifactName(kind,700,2,suffix));
  if(kind==='started')await assert.rejects(read(),/did not establish evidence/);
  else assert.equal((await read()).proof.member_sha256,proof.member_sha256);
 }
});
