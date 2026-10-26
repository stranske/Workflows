'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),vm=require('vm'),path=require('path'),{createHash}=require('crypto');
const actual=require('../verification_event');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
async function collect(change=()=>{}) {
 const original=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-original.json'));
 const request=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-request.json'));
 const bundle=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-seed-bundle.json'));
 const decision=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-decision.json'));
 const qualification={...structuredClone(require('../../../tests/fixtures/verifier_correction/integration-qualification.json')),profile_identity_sha256:'f'.repeat(64)};
 const archive=Buffer.from('inert archive authenticated only at transport boundary'),calls=[];
 const state={original,request,bundle,decision,qualification,permission:'write',files:new Map([
 ['closer-correction-seeds.json',Buffer.from(JSON.stringify(bundle))],['verification-event-manifest.json',Buffer.from(JSON.stringify(original.manifest))],
 ['evaluation.json',Buffer.from(original.result_text)],['evaluation-execution.json',Buffer.from(JSON.stringify(original.execution))]])};
 change(state);
 const methods={repos:{getCollaboratorPermissionLevel:()=>({permission:state.permission,user:{login:'authorized-actor'}})},
 pulls:{get:()=>original.pull},issues:{get:()=>original.sourceIssue,getComment:()=>original.comments[0]}};
 const github={rest:Object.fromEntries(Object.entries(methods).map(([group,rows])=>[group,Object.fromEntries(Object.entries(rows).map(([method,fn])=>[method,async args=>{calls.push([group,method,args]);return {data:fn()};}]))]))};
 const module={exports:{}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../verifier_correction_collector.js'),'utf8'),{module,Buffer,URL,require:name=>{
  if(name==='fs')return {readFileSync:()=>archive};
  if(name==='./verifier_pending_execution')return {acquireRetainedExecution:async()=>{calls.push(['origin']);if(state.originFailure)throw Error('untrusted origin');return {archive_sha256:sha(archive)};},readRetainedArchive:()=>state.files};
  return name.startsWith('./')?require(path.join(__dirname,'..',name)):require(name);
 }});
 const selector={schema:'closer-correction-selector/v1',run_id:100,run_attempt:2,artifact_id:50,request_sha256:request.request_sha256,
 verification_event:request.original_verifier.verification_event,assessment_identity:original.manifest.assessment_identity};
 const result=await module.exports.collectSubmission({github,repository:'stranske/example',actor:'authorized-actor',current:{run_id:700,run_attempt:1},
 transport:{canonicalRun:async()=>calls.push(['canonical'])},selector,request,decision,directory:'/inert',loadQualification:async()=>{if(state.qualificationFailure)throw Error('incomplete read');return state.qualification;},
 authenticateDecision:state.missingDecisionProof?null:async()=>({status:'authenticated',decision_sha256:actual.digest(state.decision),profile_identity_sha256:'f'.repeat(64)})});
 return {result,calls};
}
test('two-stage collection reproduces seed bytes and keeps future local operation/test data outside original artifact',async()=>{
 const {result,calls}=await collect();assert.equal(result.status,'admitted');assert.equal(result.collector.run_id,700);
 assert.equal(result.seed.original_operation,undefined);assert.equal(result.seed.required_tests,undefined);assert.equal(result.seed.incumbent,undefined);
 const {context_sha256,...payload}=result;assert.equal(context_sha256,actual.digest(payload));
 assert.equal(calls[0][0],'canonical');assert.ok(calls.find(row=>row[0]==='origin'));
});
test('source drift, spoofed terminal, missing seed and unauthenticated actor refuse without any effects',async()=>{
 for(const change of [s=>{s.original.sourceIssue.body='changed';},s=>{s.original.comments[0].user.id=1;},s=>{s.files.delete('closer-correction-seeds.json');},
 s=>{s.originFailure=true;},s=>{s.permission='read';}])await assert.rejects(collect(change));
});
test('empty production qualification, read uncertainty and risky classifications remain owned UNKNOWN',async()=>{
 for(const change of [s=>{s.qualification=null;},s=>{s.missingDecisionProof=true;},s=>{s.qualificationFailure=true;},s=>{s.decision.findings[0].classification='security';},
 s=>{s.decision.findings[0].classification='authority_conflict';},s=>{s.decision.findings[0].classification='unknown';}]) {
  assert.equal((await collect(change)).result.status,'owned_unknown');
 }
});
