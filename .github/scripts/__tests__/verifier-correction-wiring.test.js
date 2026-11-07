'use strict';

// Execute the authored new github-script bodies with inert transport boundaries.
// No client, upload SDK, provider, issue, label or dispatch can reach a network.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),vm=require('vm'),{createHash}=require('crypto');
const eventTools=require('../verification_event');
const {seedForRequest,effectKey}=require('../verifier_correction_effects');
const {recordStarted}=require('../verifier_correction_autopilot');
const ROOT=path.resolve(__dirname,'../../..');
const read=name=>fs.readFileSync(path.join(ROOT,name),'utf8');
const followupSurfaces=['.github/workflows/agents-verify-to-new-pr.yml','templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml'];
const autopilot=()=>read('templates/consumer-repo/.github/workflows/agents-auto-pilot.yml');
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
function condition(row) {
 const lines=row.body.split('\n'),at=lines.findIndex(line=>line.startsWith('        if:'));
 assert.ok(at>=0,`condition exists: ${row.name}`);
 const value=lines[at].slice('        if:'.length).trim();if(!['|','>-'].includes(value))return value;
 const result=[];for(const line of lines.slice(at+1)){if(!line.startsWith('          '))break;result.push(line.trim());}
 return result.join(' ');
}
function permits(expression,values) {
 const translated=expression.replace(/\b(?:inputs|steps|needs|github)\.[A-Za-z0-9_.-]+/g,ref=>`get(${JSON.stringify(ref)})`);
 return Boolean(new Function('get','contains','fromJSON','always',`return (${translated});`)(ref=>values[ref] ?? '',
  (array,value)=>array.includes(value),JSON.parse,()=>true));
}
function coreFixture() {
 const outputs={},summary={addHeading(){return this;},addRaw(){return this;},async write(){}};
 return {outputs,summary,setOutput:(key,value)=>{outputs[key]=value;},warning(){},info(){}};
}
function fileFixture() {const files={};return {files,fs:{mkdirSync(){},writeFileSync:(name,value)=>{files[name]=value;}}};}
async function run(row,requireStub,{github={},core=coreFixture(),env={},context={runId:900,repo:{owner:'stranske',repo:'example'},actor:'authorized-actor'}}={}) {
 await new AsyncFunction('require','github','core','context','process','Buffer',script(row))(requireStub,github,core,context,
  {env,cwd:()=>'/inert/workspace'},Buffer);
 return core;
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


// Pure unpublished interfaces remain exercised offline.
const sdkDirectory='.github/scripts/verifier_correction_artifact_sdk';
test('correction SDK package and full portable registry lock bind exact artifact version and immutable integrity',()=>{
 const pkg=JSON.parse(read(`${sdkDirectory}/package.json`)),lock=JSON.parse(read(`${sdkDirectory}/package-lock.json`));
 assert.equal(pkg.private,true);assert.deepEqual(pkg.dependencies,{'@actions/artifact':'6.3.1'});assert.equal(pkg.engines.node,'>=24');
 assert.equal(lock.lockfileVersion,3);assert.deepEqual(lock.packages[''].dependencies,pkg.dependencies);
 assert.equal(lock.packages['node_modules/@actions/artifact'].version,'6.3.1');
 const packages=Object.entries(lock.packages).filter(([name])=>name);
 assert.ok(packages.length>10,'full transitive lock retained');
 for(const [name,row] of packages) {
  assert.ok(name.startsWith('node_modules/'));assert.match(row.resolved,/^https:\/\/registry\.npmjs\.org\/[^\s]+\.tgz$/);
  assert.match(row.integrity,/^sha512-[A-Za-z0-9+/]+={0,2}$/);assert.equal(Buffer.from(row.integrity.slice(7),'base64').length,64);
  assert.equal(row.link,undefined);assert.doesNotMatch(JSON.stringify(row),/file:\/|localhost|127\.0\.0\.1|Users\/|\/tmp\//);
 }
});
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

const autopilotSurfaces=['.github/workflows/agents-auto-pilot.yml','templates/consumer-repo/.github/workflows/agents-auto-pilot.yml'];
const beltSurfaces=['.github/workflows/agents-72-codex-belt-worker.yml','templates/consumer-repo/.github/workflows/agents-72-codex-belt-worker.yml'];
for(const surface of autopilotSurfaces)test(`${surface}: reserved typed input fails before ordinary effects without loading helpers`,async()=>{
 const source=read(surface),guard=step(source,'Reject unsupported correction requests');assert.ok(source.indexOf(guard.body)<source.indexOf('- name: Mint GitHub App Token'));
 assert.doesNotMatch(guard.body,/continue-on-error/);assert.equal(permits(condition(guard),{'inputs.correction_selector':''}),false);
 for(const value of ['{}',' ','{"repository":"caller/claim"}']) {
  assert.equal(permits(condition(guard),{'inputs.correction_selector':value}),true);
  let calls=0;await assert.rejects(run(guard,()=>{calls++;throw Error('no helper may be loaded');},{github:new Proxy({},{get(){calls++;throw Error('no native effects');}})}),/correction_handoff_disabled/);assert.equal(calls,0);
 }
 assert.equal((source.match(/correction_selector/g) || []).length,2,'reserved input and refusal are the only typed workflow wiring');
});
for(const surface of [...autopilotSurfaces,...beltSurfaces,'.github/workflows/reusable-codex-run.yml','.github/scripts/keepalive_loop.js','templates/consumer-repo/.github/scripts/keepalive_loop.js'])
 test(`${surface}: ordinary path has no correction discovery, checkout or SDK dependency`,()=>{
  assert.doesNotMatch(read(surface),/verifier_correction|resolveCodingScope|resolvePullCodingScope|createArtifactTransport|recheckCodingAdmission|guardCorrectionKeepalive|CORRECTION_CONTEXT_FILE|correction-sdk|correction-intake|\.correction-lib|closer-correction-effect\/v1/);
 });
for(const surface of autopilotSurfaces)test(`${surface}: actual ordinary context ignores unrelated failed/expired correction history and mutable markers`,async()=>{
 const row=step(read(surface),'Determine context');assert.doesNotMatch(script(row),/\$\{\{\s*inputs\.issue_number/);
 const results=[];
 for(const body of ['## Tasks\n- [ ] Native ordinary task','<!-- closer-correction-effect/v1 {"caller":"untrusted"} -->\n## Tasks\n- [ ] Native ordinary task']) {
  const calls=[],core=coreFixture();core.setFailed=message=>{throw Error(message);};
  const issue={number:9,title:'Native ordinary issue',body,state:'open',labels:[{name:'agent:codex'}]};
  const issues={get:async args=>{calls.push(['get',args]);return {data:issue};},listComments:async()=>({data:[]}),listEventsForTimeline:async()=>({data:[]})};
  const github={rest:{issues,actions:new Proxy({},{get(){throw Error('unrelated expired/failed history is unavailable');}})}};
  const inertRequire=name=>{assert.ok(name.endsWith('/github-api-with-retry.js'));return {createTokenAwareRetry:async()=>({withRetry:fn=>fn(github),paginateWithRetry:async(fn,args)=>(await fn(args)).data})};};
  await run(row,inertRequire,{github,core,env:{WORKFLOWS_SCRIPTS_PATH:'/inert/trusted'},context:{runId:900,repo:{owner:'stranske',repo:'example'},eventName:'workflow_dispatch',payload:{inputs:{issue_number:"9'); throw Error('never execute'); //"}}}});
  assert.equal(calls.length,1);assert.equal(calls[0][1].issue_number,9);assert.equal(core.outputs.should_continue,'true');results.push(core.outputs);
 }
 assert.deepEqual(results[0],results[1]);assert.deepEqual(results[0],{issue_number:9,issue_title:'Native ordinary issue',issue_state:'open',should_continue:'true',has_format:'false',has_optimize:'false',has_optimizer_output:'false',has_apply:'false',has_agent:'true',has_autofix:'false',has_automerge:'false',has_verify:'false',verify_handoff_bound:'false',linked_pr:''});
});
for(const surface of autopilotSurfaces)test(`${surface}: ordinary pause/human guards and format wakeup remain intact`,async()=>{
 const source=read(surface);assert.match(script(step(source,'Determine context')),/labels\.includes\('needs-human'\)/);assert.match(script(step(source,'Determine context')),/labels\.includes\('agents:auto-pilot-pause'\)/);
 assert.equal(permits(condition(step(source,'Execute step - Format (inline)')),{'steps.next.outputs.next_step':'format'}),true);
 const calls=[],github={rest:{issues:{get:async()=>({data:{labels:[{name:'agents:auto-pilot-pause'}]}}),removeLabel:async args=>{calls.push(['remove',args]);return {data:{}};},createComment:async args=>{calls.push(['comment',args]);return {data:{}};}},
  repos:{get:async()=>({data:{default_branch:'main'}})},actions:{createWorkflowDispatch:async args=>{calls.push(['dispatch',args]);return {data:{}};}}}};
 await run(step(source,'Clear pause and redispatch format step'),name=>{assert.equal(name,'./.github/scripts/github-api-with-retry.js');return {createTokenAwareRetry:async()=>({withRetry:fn=>fn(github)})};},{github,env:{ISSUE_NUMBER:'9'}});
 assert.equal(calls.filter(([name])=>name==='remove').length,1);assert.deepEqual(calls.find(([name])=>name==='dispatch')[1].inputs,{issue_number:'9',force_step:'format'});
});
const legacyActivation='<!-- agent-activation-marker -->\nAgent worker (codex) activated for branch `codex/issue-9`.\n\n@codex start\n**Focus on this task first:** `task-1` — Exact single task\n\nImplement **only** this task in your first commit.\nEnsure the code compiles and existing tests pass before moving on.\nThe keepalive loop will assign subsequent tasks after this one is complete.';
for(const surface of beltSurfaces)test(`${surface}: actual ordinary Belt create/update payload remains exact without correction APIs`,async()=>{
 for(const update of [false,true]) {
  const calls=[],comments=update?[{id:87,body:'<!-- agent-activation-marker --> old'}]:[],issues=Object.fromEntries(['listComments','createComment','updateComment','deleteComment'].map(method=>[method,async args=>{calls.push([method,args]);return {data:{}};}]));
  const github={rest:{issues,actions:new Proxy({},{get(){throw Error('unrelated correction history unavailable');}})}};
  const values={'steps.pr.outputs.number':'10','steps.ctx.outputs.branch':'codex/issue-9','steps.mode.outputs.dry_run':'false','steps.ledger_start.outputs.task_id':'task-1','steps.ledger_start.outputs.task_title':'Exact single task','steps.ctx.outputs.agent_key':'codex'};
  const code=script(step(read(surface),'Post activation comment')).replace(/\$\{\{\s*(.*?)\s*\}\}/g,(_,key)=>{assert.ok(key in values);return values[key];});
  await new AsyncFunction('require','github','core','context','process',code)(name=>{assert.equal(name,'./.github/scripts/github-api-with-retry.js');return {createTokenAwareRetry:async()=>({github,withRetry:fn=>fn(github),paginateWithRetry:async()=>comments})};},
   github,coreFixture(),{repo:{owner:'stranske',repo:'example'}},{env:{}});
  const writes=calls.filter(([name])=>['createComment','updateComment'].includes(name));assert.equal(writes.length,1);assert.equal(writes[0][1].body,legacyActivation);assert.equal(writes[0][1].request,undefined);
  assert.equal(writes[0][0],update?'updateComment':'createComment');
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
test('Workflows-local legacy fallback IDs remain distinct from consolidated consumer dispatch',()=>{
 const root=read(autopilotSurfaces[0]),consumer=read(autopilotSurfaces[1]);
 for(const id of ['agents-pr-meta-v4.yml','agents-keepalive-loop.yml'])assert.ok(root.includes(id));
 for(const id of ['agents-pr-meta-v4.yml','agents-keepalive-loop.yml'])assert.equal(consumer.includes(id),false);
 assert.ok(consumer.includes('agents-80-pr-event-hub.yml'));assert.ok(consumer.includes('agents-81-gate-followups.yml'));
});
