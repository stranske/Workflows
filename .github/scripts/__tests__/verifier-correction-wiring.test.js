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

for(const surface of followupSurfaces) {
const followup=()=>read(surface);
const testSource=(name,fn)=>test(`${surface}: ${name}`,fn);
testSource('authored collection cannot turn caller classification truth into admission even with an eligible offline profile',async()=>{
 const f=originalCollector(),file=fileFixture(),core=coreFixture();
 f.decision.decision_proof={status:'authenticated',decision_sha256:eventTools.digest(f.decision),profile_identity_sha256:'f'.repeat(64)};
 const requireStub=name=>{
  if(name==='fs')return file.fs;
  if(name.endsWith('/verification_event'))return eventTools;
  if(name.endsWith('/verifier_correction_consumer'))return {collectCorrection:async()=>{throw Error('unexpected legacy path');}};
  if(name.endsWith('/verifier_correction_collector'))return {collectSubmission:f.collectSubmission,loadReviewedQualification:async()=>f.qualification};
  if(name.endsWith('/verifier_correction_artifacts'))return {createArtifactTransport:async()=>({canonicalRun:async()=>{}})};
  if(name.endsWith('/terminal_disposition'))return {normalizeTerminalDisposition:input=>({schema:'workflows-terminal-disposition/v1',...input})};
  throw Error(`Unexpected inert dependency ${name}`);
 };
 await run(step(followup(),'Collect authenticated correction request without effects'),requireStub,{github:f.github,core,
  env:{CORRECTION_SELECTOR:JSON.stringify(f.selector),CORRECTION_REQUEST:JSON.stringify(f.request),CORRECTION_DECISION:JSON.stringify(f.decision),GITHUB_RUN_ATTEMPT:'1'}});
 const context=JSON.parse(file.files['correction-admitted.json']);
 assert.equal(context.status,'owned_unknown');assert.equal(context.decision_proof,null);
 assert.equal(context.classification.reason,'authenticated_retained_classification_output_unavailable');
 assert.equal(core.outputs.admitted,'false');assert.equal(context.classification.act_authorized,false);assert.equal(context.classification.source_closure_authorized,false);
 assert.equal(core.outputs.pr_number,f.request.target.pr);assert.equal(f.effects.length,0);
 assert.ok(f.calls.every(([resource,method])=>!['create','createWorkflowDispatch','update','addLabels'].includes(method)));
});

testSource('oversized authored collection input refuses before a collector or effect can run',async()=>{
 const file=fileFixture();let collectorCalls=0;
 const requireStub=name=>name==='fs'?file.fs:name.endsWith('/verification_event')?eventTools:
  name.endsWith('/verifier_correction_consumer')?{collectCorrection:async()=>{collectorCalls++;}}:
  name.endsWith('/terminal_disposition')?{normalizeTerminalDisposition:input=>input}:(()=>{throw Error(`Unexpected dependency ${name}`);})();
 await run(step(followup(),'Collect authenticated correction request without effects'),requireStub,
  {env:{CORRECTION_SELECTOR:'x'.repeat(16385),GITHUB_RUN_ATTEMPT:'1'}});
 const refusal=JSON.parse(file.files['agent-metrics/verifier-followup-ledger.ndjson']);
 assert.equal(collectorCalls,0);assert.equal(refusal.effect_state,'confirmed_not_started');
 assert.equal(refusal.retry_authorized,false);assert.equal(refusal.act_authorized,false);assert.equal(refusal.source_closure_authorized,false);
});

testSource('effect job depends on real collected artifact output and uses authenticated PR scope rather than caller hold identifiers',()=>{
 const source=followup(),job=source.split('\n  apply-correction:\n')[1];assert.ok(job);
 const header=job.split('    steps:\n')[0];
 assert.match(header,/needs: \[collect-correction\]/);
 assert.match(header,/needs\.collect-correction\.outputs\.admitted == 'true'/);
 assert.match(header,/needs\.collect-correction\.outputs\.artifact_id != ''/);
 assert.match(header,/group: agents-verify-to-new-pr-\$\{\{ github\.repository \}\}-\$\{\{ needs\.collect-correction\.outputs\.pr_number \}\}/);
 assert.doesNotMatch(header,/inputs\.(?:correction_request|correction_selector)|hold_id|operation_id|idempotency/);
 assert.match(script(step(source,'Consume admitted correction')),/artifact_id:Number\(process\.env\.ADMITTED_ARTIFACT_ID\)/);
 assert.match(source,/artifact_id: \$\{\{ steps\.correction_artifact\.outputs\.artifact-id \}\}/);
});

testSource('authored consume path invokes no effect when SDK initialization is unavailable',async()=>{
 let runtimeCalls=0;
 const requireStub=name=>name==='fs'?fileFixture().fs:name==='path'?path:name.endsWith('/verification_event')?eventTools:
  name.endsWith('/verifier_correction_consumer')?require('../verifier_correction_consumer'):
  name.endsWith('/verifier_correction_artifacts')?{runtimeArtifactClient:async()=>{throw Error('SDK init unavailable');},createArtifactTransport:async()=>{throw Error('must not construct');}}:
  name.endsWith('/verifier_correction_runtime')?{createRuntime:async()=>{runtimeCalls++;throw Error('must not execute');}}:
  name.endsWith('/terminal_disposition')?{normalizeTerminalDisposition:input=>input}:(()=>{throw Error(`Unexpected dependency ${name}`);})();
 await assert.rejects(run(step(followup(),'Consume admitted correction'),requireStub,
  {env:{GITHUB_RUN_ATTEMPT:'1',RUNNER_TEMP:'/inert/temp',ADMITTED_ARTIFACT_ID:'50'}}),/SDK init unavailable/);
 assert.equal(runtimeCalls,0);
});

const executableSteps=new Map([
 ['Execute step - Format (inline)','format'],['Execute step - Optimize (inline)','optimize'],
 ['Execute step - Apply suggestions (inline)','apply'],['Execute step - Capability check & Agent','capability-check'],
 ['Execute step - Verify','verify'],['Execute step - Create PR','create-pr'],['Report - Monitoring PR','monitor-pr'],
 ['Execute step - Check Completion & Trigger Merge','check-completion'],
]);
function gateValues(selector,selected,admitted='false') {
 return {'inputs.correction_selector':selector,'steps.correction_start.outputs.admitted':admitted,
  'steps.context.outputs.should_continue':'true','steps.cycles.outputs.exceeded':'false','steps.cycles.outputs.rate_limited':'false',
  'steps.complexity_check.outputs.too_complex':'false','steps.next.outputs.next_step':selected};
}
testSource('all authored provider-capable branches require retained-start admission for typed requests',()=>{
 const source=autopilot();
 for(const [name,selected] of executableSteps) {
  const expression=condition(step(source,name));
  assert.equal(permits(expression,gateValues('inert-selector',selected)),false,`${name} blocks failed/unretained start`);
  assert.equal(permits(expression,gateValues('inert-selector',selected,'true')),selected!=='format',`${name} retains admitted branch or explicit body-preservation hold`);
  assert.equal(permits(expression,gateValues('',selected)),true,`${name} preserves absent-selector branch`);
 }
 const expression=condition(step(source,'Re-dispatch for next step'));
 assert.equal(permits(expression,gateValues('inert-selector','optimize')),false);
 assert.equal(permits(expression,gateValues('inert-selector','optimize','true')),true);
 assert.equal(permits(expression,gateValues('','optimize')),true);
});

testSource('authored admission precedes context and retained start follows actual context/cycle/selection gates',()=>{
 const source=autopilot();assert.ok(source.indexOf('- name: Authenticate correction continuation')<source.indexOf('- name: Determine context'));
 assert.ok(source.indexOf('- name: Determine next step')<source.indexOf('- name: Record admitted correction start'));
 assert.ok(source.indexOf('- name: Record admitted correction start')<source.indexOf('- name: Execute step - Format (inline)'));
 const values={...gateValues('inert-selector','optimize'),'steps.check_enabled.outputs.enabled':'true'};
 assert.equal(permits(condition(step(source,'Determine context')),values),false);
 values['steps.correction_auth.outputs.admitted']='true';assert.equal(permits(condition(step(source,'Determine context')),values),true);
 values['inputs.correction_selector']='';assert.equal(permits(condition(step(source,'Determine context')),values),true);
 const start=condition(step(source,'Record admitted correction start'));
 for(const [field,value] of [['steps.context.outputs.should_continue','false'],['steps.cycles.outputs.exceeded','true'],
  ['steps.cycles.outputs.rate_limited','true'],['steps.next.outputs.next_step','done'],['steps.next.outputs.next_step','']]) {
  assert.equal(permits(start,{...gateValues('inert-selector','optimize'),[field]:value}),false,`${field} refuses start`);
 }
});

testSource('authored retained-start readback error never emits provider admission output',async()=>{
 const request=structuredClone(require('../../../tests/fixtures/verifier_correction/request.json')),core=coreFixture();
 const admission={request,selected_step:'optimize',lineage_key:'l'.repeat(64),observed_issue:request.incumbent.issue,
  selector:{effect_key:effectKey(seedForRequest(request)),issue:request.incumbent.issue,parent_dispatch:null},
  collector:{run_id:700,run_attempt:1,artifact_id:1},intent:{run_id:700,run_attempt:1,artifact_id:2,archive_sha256:'a'.repeat(64),member_sha256:'b'.repeat(64)}};
 let publishes=0,authenticates=0;
 const transport={publish:async()=>{publishes++;throw Error('checkpoint exact readback unavailable');}};
 const requireStub=name=>name==='path'?path:name.endsWith('/verifier_correction_artifacts')?{runtimeArtifactClient:async()=>({}),createArtifactTransport:async()=>transport}:
  name.endsWith('/verifier_correction_runtime')?{createAutopilotRuntime:async()=>({authenticate:async()=>{authenticates++;return admission;},observeLineage:async()=>[]})}:
  name.endsWith('/verifier_correction_autopilot')?{recordStarted}:(()=>{throw Error(`Unexpected inert dependency ${name}`);})();
 await assert.rejects(run(step(autopilot(),'Record admitted correction start'),requireStub,{core,
  env:{WORKFLOWS_SCRIPTS_PATH:'/inert/workflows',RUNNER_TEMP:'/inert/temp',CORRECTION_SELECTOR:'{}',CORRECTION_ISSUE:'8',CORRECTION_FORCE_STEP:'optimize',
   CORRECTION_SELECTED_STEP:'optimize',CORRECTION_CONTINUE:'true',CORRECTION_EXCEEDED:'false',CORRECTION_RATE_LIMITED:'false',GITHUB_RUN_ATTEMPT:'1'}}),/checkpoint exact readback unavailable/);
 assert.equal(authenticates,1);assert.equal(publishes,1);assert.equal(core.outputs.admitted,undefined);assert.equal(core.outputs.proof,undefined);
});

testSource('new authored github-script admission/effect bodies compile as JavaScript without evaluating expression inputs',()=>{
 for(const [source,names] of [[followup(),['Collect authenticated correction request without effects','Consume admitted correction','Fence retained scoped correction effects']],
  [autopilot(),['Authenticate correction continuation','Record admitted correction start','Clear pause and redispatch format step']]]) {
  for(const name of names)assert.doesNotThrow(()=>new AsyncFunction('require','github','core','context','process','Buffer',script(step(source,name))),name);
 }
});

testSource('authored effect-host construction uncertainty emits UNKNOWN without invoking or repeating an effect',async()=>{
 const file=fileFixture(),published=[];let consumes=0;
 const transport={publish:async(kind,bytes)=>{published.push([kind,JSON.parse(bytes)]);return {run_id:900,run_attempt:1};}};
 const requireStub=name=>name==='fs'?file.fs:name==='path'?path:name.endsWith('/verification_event')?eventTools:
  name.endsWith('/verifier_correction_consumer')?require('../verifier_correction_consumer'):
  name.endsWith('/verifier_correction_artifacts')?{runtimeArtifactClient:async()=>({}),createArtifactTransport:async()=>transport}:
  name.endsWith('/verifier_correction_runtime')?{createRuntime:async()=>{throw Error('prior ledger outcome unread');},consume:async()=>{consumes++;}}:
  name.endsWith('/terminal_disposition')?{normalizeTerminalDisposition:input=>input}:(()=>{throw Error(`Unexpected inert dependency ${name}`);})();
 await run(step(followup(),'Consume admitted correction'),requireStub,
  {env:{GITHUB_RUN_ATTEMPT:'1',RUNNER_TEMP:'/inert/temp',ADMITTED_ARTIFACT_ID:'50'}});
 assert.equal(consumes,0);assert.equal(published.length,1);assert.equal(published[0][0],'receipt');
 const refusal=published[0][1];assert.equal(refusal.schema,'closer-correction-admission-refusal/v1');assert.equal(refusal.effect_state,'outcome_unknown');
 assert.equal(refusal.retry_authorized,false);assert.equal(refusal.act_authorized,false);assert.equal(refusal.source_closure_authorized,false);
 assert.equal(refusal.receipt_sha256,eventTools.digest((({receipt_sha256,...value})=>value)(refusal)));
 assert.deepEqual(JSON.parse(file.files['agent-metrics/verifier-followup-ledger.ndjson']),refusal);
});

}

const autopilotSurfaces=['.github/workflows/agents-auto-pilot.yml','templates/consumer-repo/.github/workflows/agents-auto-pilot.yml'];
for(const surface of autopilotSurfaces)test(`${surface}: Determine context consumes issue_number as payload data, preserving numeric legacy input`,async()=>{
 const row=step(read(surface),'Determine context'),code=script(row);
 assert.ok(code.includes('context.payload.inputs?.issue_number'));
 assert.doesNotMatch(code,/\$\{\{\s*inputs\.issue_number\s*\}\}/);
 for(const [input,expected] of [['9',9],["9'); throw new Error('CALLER_TEXT_EXECUTED'); //",9],["'); throw new Error('CALLER_TEXT_EXECUTED'); //",null]]) {
  const calls=[],failures=[],core=coreFixture();core.setFailed=value=>failures.push(value);
  const github={rest:{issues:{get:async args=>{calls.push(args);return {data:{number:9,title:'Native ordinary issue',state:'open',body:'Original issue body',labels:[{name:'agents:auto-pilot-pause'}]}};}}}};
  const inertRequire=name=>{
   if(name.endsWith('/github-api-with-retry.js'))return {createTokenAwareRetry:async()=>({withRetry:fn=>fn(github),paginateWithRetry:async()=>[]})};
   if(name==='path')return path;
   if(name.endsWith('/verifier_correction_artifacts'))return {createArtifactTransport:async()=>({})};
   if(name.endsWith('/verifier_correction_runtime'))return {resolveCodingScope:async({issueNumber})=>{assert.equal(issueNumber,9);return null;}};
   throw Error(`Unexpected context dependency ${name}`);
  };
  await run(row,inertRequire,{github,core,env:{WORKFLOWS_SCRIPTS_PATH:'/inert/trusted',GITHUB_RUN_ATTEMPT:'1'},
   context:{eventName:'workflow_dispatch',payload:{inputs:{issue_number:input}},runId:900,repo:{owner:'stranske',repo:'example'}}});
  if(expected===null){assert.equal(calls.length,0);assert.deepEqual(failures,['Could not determine issue number']);}
  else {assert.equal(calls.length,1);assert.equal(calls[0].issue_number,expected);assert.equal(core.outputs.should_continue,'false');assert.equal(core.outputs.reason,'paused');assert.deepEqual(failures,[]);}
 }
});

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
function runBody(row) {
 const lines=row.body.split('\n'),at=lines.findIndex(line=>line==='        run: |');assert.ok(at>=0,`shell script ${row.name}`);const result=[];
 for(const line of lines.slice(at+1)){if(line && !line.startsWith('          '))break;result.push(line.slice(10));}
 return result.join('\n');
}
const sdkSteps=[...followupSurfaces.map(surface=>[surface,'Install existing Actions artifact SDK']),
 ...autopilotSurfaces.flatMap(surface=>[[surface,'Install correction artifact SDK'],[surface,'Install formatter correlation artifact SDK']])];
for(const [surface,name] of sdkSteps)test(`${surface}: ${name} executes locked npm ci using both exact retained files`,t=>{
 const {execFileSync}=require('child_process'),os=require('os'),root=fs.mkdtempSync(path.join(os.tmpdir(),'inert-correction-sdk-test-'));
 t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const body=runBody(step(read(surface),name)),scriptCommands=body.split('\n').filter(line=>/^\s*npm\b/.test(line));
 assert.deepEqual(scriptCommands,['npm ci --prefix "$RUNNER_TEMP/correction-sdk" --ignore-scripts --no-audit --no-fund']);
 assert.doesNotMatch(body,/@actions\/artifact(?:@|\s)|npm\s+(?:install|i\b|exec)|npx\b/);
 const source=path.join(root,surface.includes('auto-pilot')?'workflows-lib':'.',sdkDirectory);fs.mkdirSync(source,{recursive:true});
 for(const file of ['package.json','package-lock.json'])fs.copyFileSync(path.join(ROOT,sdkDirectory,file),path.join(source,file));
 const bin=path.join(root,'inert-bin');fs.mkdirSync(bin);const trace=path.join(root,'npm-argv.json');
 fs.writeFileSync(path.join(bin,'npm'),'#!/bin/sh\nprintf "%s\\n" "$@" > "$INERT_NPM_TRACE"\n',{mode:0o755});
 const runnerTemp=path.join(root,'runner-temp');
 execFileSync('/bin/bash',['--noprofile','--norc','-e','-u','-o','pipefail','-c',body],{cwd:root,env:{HOME:root,BASH_ENV:'/dev/null',ENV:'/dev/null',PATH:`${bin}:/usr/bin:/bin`,RUNNER_TEMP:runnerTemp,INERT_NPM_TRACE:trace}});
 assert.deepEqual(fs.readFileSync(trace,'utf8').trim().split('\n'),['ci','--prefix',path.join(runnerTemp,'correction-sdk'),'--ignore-scripts','--no-audit','--no-fund']);
 for(const file of ['package.json','package-lock.json'])assert.deepEqual(fs.readFileSync(path.join(runnerTemp,'correction-sdk',file)),fs.readFileSync(path.join(ROOT,sdkDirectory,file)));
});

test('final provider preflight records actual model-selection/input env before the existing default-success Run Codex step',()=>{
 const source=read('.github/workflows/reusable-codex-run.yml'),preflight=step(source,'Recheck mandatory correction admission before coding'),provider=step(source,'Run Codex');
 assert.ok(source.indexOf(preflight.body)<source.indexOf(provider.body));assert.match(condition(preflight),/env\.CORRECTION_CONTEXT_FILE != ''/);
 assert.doesNotMatch(preflight.body,/continue-on-error/);assert.doesNotMatch(provider.body,/if:\s*(?:always\(|failure\()/);
 for(const [env,value] of [['CORRECTION_REQUESTED_MODEL','steps.codex_model.outputs.model'],['CORRECTION_MODEL_CANDIDATES','steps.codex_model.outputs.candidates'],
  ['CORRECTION_REQUESTED_EFFORT','inputs.codex_reasoning_effort'],['CORRECTION_REQUESTED_SANDBOX','inputs.sandbox'],['CORRECTION_EXTRA_ARGUMENTS','inputs.codex_args']])
  assert.ok(preflight.body.includes(`${env}: \${{ ${value} }}`),`actual existing selection source ${env}`);
 const code=script(preflight);assert.ok(code.indexOf('await recheckCodingAdmission')<code.indexOf('codingPolicyObservation({'));
 assert.match(code,/scope=JSON\.parse\(fs\.readFileSync\(process\.env\.CORRECTION_CONTEXT_FILE/);
 assert.match(code,/fs\.writeFileSync\(path\.join\(process\.env\.RUNNER_TEMP,'codex-correction-policy\.json'\)/);
 const retained=step(source,'Upload correction coding policy observation').body;assert.match(retained,/uses: actions\/upload-artifact@[a-f0-9]{40}/);assert.ok(retained.includes('path: ${{ runner.temp }}/codex-correction-policy.json'));
 const oldOutput=step(source,'Upload Codex output').body;assert.doesNotMatch(oldOutput,/codex-correction-policy/);assert.match(oldOutput,/path: \|\n            codex-output\*\.md\n            codex-session\*\.jsonl\n            codex-analysis\*\.json\n/);
 assert.doesNotThrow(()=>new AsyncFunction('require','github','core','context','process',code));
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
for(const surface of followupSurfaces)test(`${surface}: collector budget is supplied only from trusted Actions variable env`,()=>{
 const row=step(read(surface),'Collect authenticated correction request without effects');
 assert.ok(row.body.includes('CORRECTION_CODING_BUDGET: ${{ vars.ISSUE_PR_CONTEXT_TOKEN_BUDGET }}'));
 assert.match(script(row),/codingBudgetVariable:process\.env\.CORRECTION_CODING_BUDGET/);
 assert.doesNotMatch(script(row),/codingBudgetVariable:(?:request|decision|selector|JSON\.parse)/);
 const source=read(surface),applyHeader=source.split('\n  apply-correction:\n')[1].split('    steps:\n')[0];
 assert.match(applyHeader,/outputs\.admitted == 'true'/);
});
