'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('path');
const {activeExecutions}=require('../verifier_correction_runtime');
const registryPath=path.join(__dirname,'../../agents/registry.yml');
test('complete native active inventory preserves unknown existing agent and queue writers, without an invented negative default',async()=>{
 const rows=[{id:20,status:'queued',path:'.github/workflows/agents-71-codex-belt-dispatcher.yml',run_attempt:1},
 {id:21,status:'queued',path:'.github/workflows/ci.yml',run_attempt:1},{id:22,status:'queued',path:'.github/workflows/reusable-codex-run.yml',run_attempt:1}];
 const transport={read:async(r,m,a)=>({total_count:a.status==='queued'?rows.length:0,workflow_runs:a.status==='queued'?rows:[]})};
 const actual=await activeExecutions({transport,current:{run_id:700,run_attempt:1},registryPath});
 assert.deepEqual(actual.map(row=>row.run_id),[20,22]);
});
test('native active-run missing fields, malformed count, duplicate IDs or transition during inventory remain UNKNOWN',async()=>{
 for(const change of [data=>{data.total_count=undefined;},data=>{delete data.workflow_runs[0].path;},
 data=>{data.workflow_runs.push(data.workflow_runs[0]);data.total_count=2;},data=>{data.workflow_runs[0].status='completed';}]) {
  const transport={read:async()=>{const data={total_count:1,workflow_runs:[{id:20,status:'queued',path:'.github/workflows/agents-70-orchestrator.yml'}]};change(data);return data;}};
  await assert.rejects(activeExecutions({transport,current:{run_id:700,run_attempt:1},registryPath}));
 }
});

test('every native nonterminal status remains an existing writer until positively reconciled',async()=>{
 for(const status of ['requested','waiting','pending','queued','in_progress']) {
  const transport={read:async(r,m,a)=>({total_count:a.status===status?1:0,
   workflow_runs:a.status===status?[{id:30,status,path:'.github/workflows/agents-70-orchestrator.yml',run_attempt:1}]:[]})};
  assert.equal((await activeExecutions({transport,current:{run_id:700,run_attempt:1},registryPath})).length,1);
 }
});

test('only a native linked run for the authenticated owned PR/head is an incumbent continuation rather than an unknown writer',async()=>{
 const ownedPull={pull:{id:88,number:'10',head_ref:'codex/issue-9',head_repository_id:1,base_repository_id:1},observed_head_sha:'b'.repeat(40)};
 const linked={id:88,number:10,head:{sha:'b'.repeat(40),ref:'codex/issue-9',repo:{id:1}},base:{repo:{id:1}}};
 for(const change of [null,row=>{row.pull_requests[0].id=89;},row=>{row.pull_requests[0].head.sha='c'.repeat(40);},row=>{row.pull_requests=[];}]) {
  const row={id:30,status:'in_progress',path:'.github/workflows/agents-keepalive-loop.yml',repository:{id:1},pull_requests:[structuredClone(linked)]};
  if(change)change(row);
  const transport={read:async(r,m,a)=>({total_count:a.status==='in_progress'?1:0,workflow_runs:a.status==='in_progress'?[row]:[]})};
  assert.equal((await activeExecutions({transport,current:{run_id:700,run_attempt:1},registryPath,ownedPull})).length,change?1:0);
 }
});


test('typed effect and continuation admission hold unsupported registry runners before any consequential callback',async()=>{
 const {requireCorrectionCodingIntake}=require('../verifier_correction_runtime');
 for(const key of ['codex','claude','cursor','muse','gemini','unknown',null]) {
  let effects=0;
  const facts={agent:{key,enabled:true}};
  const attempt=async()=>{requireCorrectionCodingIntake(facts,{registryPath});effects++;};
  if(key==='codex') {await attempt();assert.equal(effects,1);}
  else {await assert.rejects(attempt,/Owned UNKNOWN: selected coding runner/);assert.equal(effects,0);}
 }
 for(const facts of [{},{agent:{key:'codex',enabled:false}}]) {
  assert.throws(()=>requireCorrectionCodingIntake(facts,{registryPath}),/Owned UNKNOWN/);
 }
 const source=require('fs').readFileSync(path.join(__dirname,'../verifier_correction_runtime.js'),'utf8');
 assert.match(source,/requireCorrectionCodingIntake\(await native\(subject,\{\.\.\.nativeOptions,activeEffect\}\),\{registryPath\}\),correction_finding_text/);
 assert.match(source,/ledger\.read\(context\.effect_key\);return requireCorrectionCodingIntake\(await native\(\.\.\.args\),\{registryPath\}\)/);
});


test('fresh existing and newly-created incumbent routing cannot override source Codex selection to an unsupported runner',()=>{
 const {requireCorrectionCodingIntake}=require('../verifier_correction_runtime');
 for(const labels of [['agent:claude'],['agent:codex','runner:claude'],['agent:auto'],
  ['agent:codex','runner:codex','runner:claude'],['agent:codex','agent:claude'],[],null]) {
  const facts={agent:{key:'codex',enabled:true},incumbentIssue:{labels}};
  assert.throws(()=>requireCorrectionCodingIntake(facts,{registryPath}),/Owned UNKNOWN/);
 }
 for(const labels of [['agent:codex'],[{name:'agent:codex'},{name:'runner:codex'}]]) {
  const facts={agent:{key:'codex',enabled:true},incumbentIssue:{labels}};
  assert.equal(requireCorrectionCodingIntake(facts,{registryPath}),facts);
 }
});


test('actual effect runtime factory binds native transport into fresh host before any stage can be admitted',async()=>{
 const fs=require('fs'),vm=require('vm'),actualArtifacts=require('../verifier_correction_artifacts');
 const {digest}=require('../verification_event'),{seedForRequest,effectKey}=require('../verifier_correction_effects');
 const request=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-request.json'));
 const decision=require('../../../tests/fixtures/verifier_correction/integration-decision.json');
 const qualification={...require('../../../tests/fixtures/verifier_correction/integration-qualification.json'),profile_identity_sha256:'f'.repeat(64)};
 const original=require('../../../tests/fixtures/verifier_correction/integration-original.json'),seed=seedForRequest(request);
 const collector={repository:request.target.repository,run_id:700,run_attempt:1},proof={...collector,artifact_id:1};
 const payload={schema:'closer-correction-admitted/v1',status:'admitted',classification:{status:'admitted'},request,seed,effect_key:effectKey(seed),
  finding_text:JSON.parse(original.result_text).concerns[0],collector,decision,qualification,
  bundle:require('../../../tests/fixtures/verifier_correction/integration-seed-bundle.json'),
  decision_proof:{status:'authenticated',decision_sha256:digest(decision),profile_identity_sha256:'f'.repeat(64)}};
 const transport={current:{run_id:700,run_attempt:1},canonicalRun:async()=>{},
  load:async()=>({bytes:Buffer.from(JSON.stringify({...payload,context_sha256:digest(payload)})),proof}),
  read:async()=>({...original.pull,merged:true,merged_at:'2026-10-25T12:00:00Z'})};
 const module={exports:{}};let nativeConstruction=0;
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../verifier_correction_runtime.js'),'utf8'),{module,Buffer,require:name=>{
  if(name==='./verifier_correction_artifacts')return {...actualArtifacts,createArtifactLedger:async()=>({})};
  if(name==='./verifier_correction_host')return {createFreshCollector:async args=>{
   nativeConstruction++;assert.equal(args.transport,transport);throw Error('native-host-binding-confirmed');
  }};
  return name.startsWith('./')?require(path.join(__dirname,'..',name)):require(name);
 }});
 await assert.rejects(module.exports.createRuntime({github:{},transport,selector:proof,current:transport.current,registryPath,pythonRoot:'.'}),/native-host-binding-confirmed/);
 assert.equal(nativeConstruction,1);
});
