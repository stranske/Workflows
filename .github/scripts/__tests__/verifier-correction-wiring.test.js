'use strict';

// Execute the authored new github-script bodies with inert transport boundaries.
// No client, upload SDK, provider, issue, label or dispatch can reach a network.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),vm=require('vm'),{createHash}=require('crypto');
const eventTools=require('../verification_event');
const ROOT=path.resolve(__dirname,'../../..');
const read=name=>fs.readFileSync(path.join(ROOT,name),'utf8');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const sha=value=>createHash('sha256').update(value).digest('hex');

function steps(source) {
 const rows=[...source.matchAll(/^      - name: (.+)$/gm)];
 return rows.map((row,index)=>({name:row[1],body:source.slice(row.index,rows[index+1]?.index || source.length)}));
}
function step(source,name) {
 const matches=steps(source).filter(row=>row.name===name);assert.equal(matches.length,1,`one authored step: ${name}`);return matches[0];
}
function script(row) {
 const index=row.body.indexOf('          script: |\n');assert.ok(index>=0,`script exists: ${row.name}`);
 const lines=row.body.slice(index+'          script: |\n'.length).split('\n'),result=[];
 for(const line of lines) {
  if(line && !line.startsWith('            '))break;
  result.push(line.startsWith('            ')?line.slice(12):line);
 }
 return result.join('\n');
}
function coreFixture() {
 const outputs={},summary={addHeading(){return this;},addRaw(){return this;},async write(){}};
 return {outputs,summary,setOutput:(key,value)=>{outputs[key]=value;},warning(){},info(){}};
}
function originalCollector() {
 const original=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-original.json'));
 const request=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-request.json'));
 const bundle=require('../../../tests/fixtures/verifier_correction/integration-seed-bundle.json');
 const decision=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-decision.json'));
 const qualification={...require('../../../tests/fixtures/verifier_correction/integration-qualification.json'),profile_identity_sha256:'f'.repeat(64)};
 const archive=Buffer.from('synthetic original archive: authenticated at transport boundary'),calls=[],effects=[];
 const retained=new Map([['closer-correction-seeds.json',Buffer.from(JSON.stringify(bundle))],
  ['verification-event-manifest.json',Buffer.from(JSON.stringify(original.manifest))],['evaluation.json',Buffer.from(original.result_text)],
  ['evaluation-execution.json',Buffer.from(JSON.stringify(original.execution))]]);
 const module={exports:{}};
 vm.runInNewContext(read('.github/scripts/verifier_correction_collector.js'),{module,Buffer,URL,require:name=>{
  if(name==='fs')return {readFileSync:()=>archive};
  if(name==='./verifier_pending_execution')return {acquireRetainedExecution:async()=>({archive_sha256:sha(archive)}),readRetainedArchive:()=>retained};
  return name.startsWith('./')?require(path.join(__dirname,'..',name)):require(name);
 }});
 const methods={repos:{getCollaboratorPermissionLevel:()=>({permission:'write',user:{login:'authorized-actor'}})},
 pulls:{get:()=>original.pull},issues:{get:()=>original.sourceIssue,getComment:()=>original.comments[0]}};
 const github={rest:Object.fromEntries(Object.entries(methods).map(([group,rows])=>[group,new Proxy(Object.fromEntries(Object.entries(rows).map(([method,fn])=>
  [method,async args=>{calls.push([group,method,args]);return {data:fn()};}])),{get:(target,key)=>target[key] || (async args=>{effects.push([group,key,args]);throw Error('Unexpected consequential/unsupported API');})})]))};
 const selector={schema:'closer-correction-selector/v1',run_id:100,run_attempt:2,artifact_id:50,request_sha256:request.request_sha256,
  verification_event:request.original_verifier.verification_event,assessment_identity:original.manifest.assessment_identity};
 return {request,decision,qualification,selector,github,calls,effects,collectSubmission:module.exports.collectSubmission};
}


for(const codingBudgetVariable of [undefined,'100000'])test(`real semantic host admission ${codingBudgetVariable?'with trusted policy budget admits':'without trusted policy budget remains held'}`,async()=>{
 const f=originalCollector(),before=JSON.stringify(f.request),proofCalls=[];
 const context=await f.collectSubmission({github:f.github,repository:'stranske/example',actor:'authorized-actor',current:{run_id:900,run_attempt:1},
  transport:{canonicalRun:async(id,attempt,workflow)=>{assert.equal(id,900);assert.equal(attempt,1);assert.equal(workflow,'.github/workflows/agents-verify-to-new-pr.yml');}},
  selector:f.selector,request:f.request,decision:f.decision,codingBudgetVariable,loadQualification:async()=>f.qualification,
  authenticateDecision:async input=>{proofCalls.push(input);return {status:'authenticated',decision_sha256:eventTools.digest(input.decision),profile_identity_sha256:f.qualification.profile_identity_sha256};}});
 assert.equal(proofCalls.length,1);assert.equal(context.decision_classification.status,'admitted');
 if(codingBudgetVariable){assert.equal(context.status,'admitted');assert.equal(context.classification.status,'admitted');assert.equal(context.coding_budget.max_estimated_input_tokens,100000);
  assert.equal(context.coding_budget.request_sha256,f.request.request_sha256);assert.equal(context.coding_budget.repository,f.request.target.repository);assert.equal(context.coding_budget.native_capacity_attested,false);}
 else {assert.equal(context.status,'owned_unknown');assert.equal(context.classification.reason,'authenticated_coding_policy_budget_unconfigured');assert.equal(context.coding_budget,null);}
 const {context_sha256,...body}=context;assert.equal(context_sha256,eventTools.digest(body));assert.equal(JSON.stringify(f.request),before);assert.equal(f.effects.length,0);
});

const retiredBeltActivation=require('../../../tests/fixtures/verifier_correction/retired-belt-and-auto-pilot-contracts.json');
const beltSurfaces=Object.keys(retiredBeltActivation.surfaces);
for(const surface of ['.github/workflows/reusable-codex-run.yml','.github/scripts/keepalive_loop.js','templates/consumer-repo/.github/scripts/keepalive_loop.js'])
 test(`${surface}: ordinary path has no correction discovery, checkout or SDK dependency`,()=>{
  assert.doesNotMatch(read(surface),/verifier_correction|resolveCodingScope|resolvePullCodingScope|createArtifactTransport|recheckCodingAdmission|guardCorrectionKeepalive|CORRECTION_CONTEXT_FILE|correction-sdk|correction-intake|\.correction-lib|closer-correction-effect\/v1/);
 });
const legacyActivation='<!-- agent-activation-marker -->\nAgent worker (codex) activated for branch `codex/issue-9`.\n\n@codex start\n**Focus on this task first:** `task-1` — Exact single task\n\nImplement **only** this task in your first commit.\nEnsure the code compiles and existing tests pass before moving on.\nThe keepalive loop will assign subsequent tasks after this one is complete.';
for(const surface of beltSurfaces)test(`${surface}: actual ordinary Belt create/update payload remains exact without correction APIs`,async()=>{
 for(const update of [false,true]) {
  const calls=[],comments=update?[{id:87,body:'<!-- agent-activation-marker --> old'}]:[],issues=Object.fromEntries(['listComments','createComment','updateComment','deleteComment'].map(method=>[method,async args=>{calls.push([method,args]);return {data:{}};}]));
  const github={rest:{issues,actions:new Proxy({},{get(){throw Error('unrelated correction history unavailable');}})}};
  const values={'steps.pr.outputs.number':'10','steps.ctx.outputs.branch':'codex/issue-9','steps.mode.outputs.dry_run':'false','steps.ledger_start.outputs.task_id':'task-1','steps.ctx.outputs.agent_key':'codex'};
  const activation=step(retiredBeltActivation.surfaces[surface].step,'Post activation comment');
  assert.match(activation.body,/^          BELT_TASK_TITLE: \$\{\{ steps\.ledger_start\.outputs\.task_title \}\}$/m);
  const code=script(activation).replace(/\$\{\{\s*(.*?)\s*\}\}/g,(_,key)=>{assert.ok(key in values);return values[key];});
  await new AsyncFunction('require','github','core','context','process',code)(name=>{assert.equal(name,'./.github/scripts/github-api-with-retry.js');return {createTokenAwareRetry:async()=>({github,withRetry:fn=>fn(github),paginateWithRetry:async()=>comments})};},
   github,coreFixture(),{repo:{owner:'stranske',repo:'example'}},{env:{BELT_TASK_TITLE:'Exact single task'}});
  const writes=calls.filter(([name])=>['createComment','updateComment'].includes(name));assert.equal(writes.length,1);assert.equal(writes[0][1].body,legacyActivation);assert.equal(writes[0][1].request,undefined);
  assert.equal(writes[0][0],update?'updateComment':'createComment');
  assert.equal(writes[0][1][update?'comment_id':'issue_number'],update?87:10);
 }
});
function runBody(row) {
 const lines=row.body.split('\n'),at=lines.findIndex(line=>line==='        run: |');assert.ok(at>=0);const result=[];
 for(const line of lines.slice(at+1)){if(line && !line.startsWith('          '))break;result.push(line.slice(10));}return result.join('\n');
}
test('actual ordinary reusable runner assembly keeps existing argv and complete legacy prompt without correction checkout or history',t=>{
 const os=require('os'),{execFileSync}=require('child_process'),root=fs.mkdtempSync(path.join(os.tmpdir(),'inert-ordinary-runner-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.symlinkSync(ROOT,path.join(root,'.workflows-lib'));fs.mkdirSync(path.join(root,'.github/codex'),{recursive:true});fs.mkdirSync(path.join(root,'bin'));
 fs.writeFileSync(path.join(root,'.github/codex/AGENT_INSTRUCTIONS.md'),'LEGACY_INSTRUCTIONS\n');fs.writeFileSync(path.join(root,'base.md'),'LEGACY_BASE\n');fs.writeFileSync(path.join(root,'AGENTS.md'),'LEGACY_REPOSITORY\n');
 const python=execFileSync('python3',['-c','import sys;print(sys.executable)'],{encoding:'utf8'}).trim();
 fs.writeFileSync(path.join(root,'bin/python'),'#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGV_CAPTURE"\nexec "$REAL_PYTHON" "$@"\n',{mode:0o755});
 execFileSync('/bin/bash',['--noprofile','--norc','-e','-u','-o','pipefail','-c',runBody(step(read('.github/workflows/reusable-codex-run.yml'),'Assemble prompt'))],{
  cwd:root,env:{HOME:root,BASH_ENV:'/dev/null',ENV:'/dev/null',PATH:`${path.join(root,'bin')}:/usr/bin:/bin`,REAL_PYTHON:python,ARGV_CAPTURE:path.join(root,'argv'),
   GITHUB_WORKSPACE:root,GITHUB_OUTPUT:path.join(root,'outputs'),BASE_PROMPT:'base.md',APPENDIX:'LEGACY_APPENDIX',MODE:'fix',PR_NUMBER:'9'}});
 assert.deepEqual(fs.readFileSync(path.join(root,'argv'),'utf8').trim().split('\n'),['-m','scripts.runner_lib','assemble-prompt','--provider','codex','--base-prompt','base.md','--appendix','LEGACY_APPENDIX','--mode','fix','--pr-number','9','--task-appendix-file','/tmp/keepalive-artifacts/task-appendix.txt']);
 assert.equal(fs.readFileSync(path.join(root,'codex-prompt-9.md'),'utf8'),'LEGACY_INSTRUCTIONS\n---\n\n## Task Prompt\nLEGACY_BASE\n\n## Run context\nLEGACY_APPENDIX\n\n## Repository Guidance\nLEGACY_REPOSITORY\n');
});
