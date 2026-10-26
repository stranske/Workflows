'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),{createHash}=require('crypto');
const {digest}=require('../verification_event');
const {seedForRequest,effectKey,sourceScopeDigest,issueIdentity}=require('../verifier_correction_effects');
const {authenticateContinuation,recordStarted,retainRedispatch,lineageKey,retainFormatPause,validateFormatPause}=require('../verifier_correction_autopilot');
const sha=body=>createHash('sha256').update(body).digest('hex');
function fixture(existing=false) {
 const request=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-request.json')),
 seed=seedForRequest(request),key=effectKey(seed),issue={id:99,number:9,node_id:'I_9',title:'inert correction issue',body:'inert correction issue',state:'open',labels:[],assignees:[]};
 if(existing) {
  request.incumbent={issue:issueIdentity(issue),owner:'owner',assignment_ref:'github:stranske/example/issues/9/events/1001',lineage_ref:'github:stranske/example/issues/9/timeline/1002'};
  const {request_sha256,...body}=request;request.request_sha256=digest(body);issue.assignees=[{login:'owner'}];
 }
 const ownership={schema:'closer-correction-ownership/v1',kind:'no_incumbent',seed_effect_key:key,source_scope_digest:sourceScopeDigest(seed),
 observed_at:'2026-10-26T00:00:00Z',evidence_refs:['inert:complete-independent-inventory'],...(existing?{kind:'existing',incumbent:request.incumbent}:{})};
 const decision=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-decision.json'));
 decision.request_sha256=request.request_sha256;
 const qualification={...structuredClone(require('../../../tests/fixtures/verifier_correction/integration-qualification.json')),profile_identity_sha256:'f'.repeat(64)};
 const payload={schema:'closer-correction-admitted/v1',status:'admitted',request,seed,decision,qualification,
 bundle:require('../../../tests/fixtures/verifier_correction/integration-seed-bundle.json'),effect_key:key,classification:{status:'admitted'},
 decision_proof:{status:'authenticated',decision_sha256:digest(decision),profile_identity_sha256:'f'.repeat(64)},
 collector:{repository:request.target.repository,run_id:700,run_attempt:1}};
 const context={...payload,context_sha256:digest(payload)},records=[];
 const append=(kind,phase,more={})=>{const row={schema:'closer-correction-effect-ledger/v1',effect_key:key,revision:records.length+1,kind,phase,
 request_sha256:request.request_sha256,consumer:{run_id:'700',run_attempt:'1'},ownership,...more};
 if(kind==='issue_confirmed')row.creation_response={schema:'closer-correction-issue-response/v1',http_status:201,github_request_id:'inert-native-response',
  request_sha256:request.request_sha256,effect_key:key,consumer:row.consumer,issue:more.issue,creator:{id:41898282,login:'github-actions[bot]',type:'Bot'},created_at:'2026-10-26T00:00:00Z'};
 records.push({...row,record_sha256:digest(row)});};
 if(!existing) {append('intent','issue_creation');append('issue_confirmed','issue_creation',{issue:issueIdentity(issue)});}
 append('intent','autopilot_dispatch');
 const proof=id=>({repository:request.target.repository,run_id:700,run_attempt:1,artifact_id:id,archive_sha256:String(id).repeat(64),member_sha256:'e'.repeat(64)});
 const collector=proof(1),intent={...proof(2),revision:records.length},store=new Map([['admitted:1',{bytes:Buffer.from(JSON.stringify(context)),proof:collector}],
 ['ledger:2',{bytes:Buffer.from(records.map(row=>JSON.stringify(row)).join('\n')),proof:intent}]]),calls=[];
 const selector={schema:'closer-correction-continuation-selector/v1',repository:request.target.repository,collector,intent,
 request_sha256:request.request_sha256,effect_key:key,issue:issueIdentity(issue),parent_dispatch:null};
 const original=require('../../../tests/fixtures/verifier_correction/integration-original.json');
 const facts={pull:{...structuredClone(original.pull),labels:[]},sourceIssue:{...structuredClone(original.sourceIssue),labels:[]},
 incumbentIssue:issue,assignmentRef:request.incumbent.assignment_ref,lineageRef:request.incumbent.lineage_ref,chainDepth:0,verdictPolicy:'follow-up',dispatchActorPermission:'write',ownership,
 workInventory:{complete:true,continuations:[],openPullRequests:[],assignments:[],retainedEffects:[]},agent:{enabled:true,key:'codex',registry_sha256:'a'.repeat(64)}};
 const transport={current:{run_id:900,run_attempt:1},canonicalRun:async(...args)=>{calls.push(['canonical',...args]);},
 load:async(p,kind)=>{calls.push(['load',kind,p.artifact_id]);const row=store.get(`${kind}:${p.artifact_id}`);assert.ok(row,'inert exact artifact present');return row;},
 publish:async(kind,bytes)=>{const id=store.size+10,p={...proof(id),...transport.current,archive_sha256:sha(bytes),member_sha256:sha(bytes)};
 calls.push(['publish',kind]);store.set(`${kind}:${id}`,{bytes,proof:p});return p;}};
 const state={qualification,facts:{...facts,ownership:structuredClone(ownership)},prior:[]};
 const options={transport,selector,issueNumber:9,selectedStep:'optimize',current:transport.current,
 loadQualification:async()=>state.qualification,collectFreshFacts:async()=>state.facts};
 const start=async(admission,extra={})=>recordStarted({transport,admission,current:transport.current,selectedStep:admission.selected_step,
 shouldContinue:true,cyclesExceeded:false,rateLimited:false,observeLineage:async()=>state.prior,recheckAdmission:async()=>admission,
 clock:()=>new Date('2026-10-26T00:00:00Z'),...extra});
 return {options,start,state,calls,store,records,context,selector,transport,issue};
}
test('actual started receipt follows authenticated original intent and real existing workflow gates, without provider-start claim',async()=>{
 const f=fixture(),admission=await authenticateContinuation(f.options),started=await f.start(admission);
 assert.equal(started.receipt.run_id,900);assert.equal(started.receipt.run_attempt,1);
 assert.equal(started.receipt.execution_kind,'workflow_admission');assert.equal(started.receipt.provider_execution,'not_attested');
 assert.equal(started.receipt.act_authorized,false);assert.equal(started.receipt.source_closure_authorized,false);
 assert.equal(started.receipt.request_sha256,f.selector.request_sha256);assert.deepEqual(started.receipt.issue,f.selector.issue);
 assert.deepEqual(f.calls.filter(row=>row[0]==='publish').map(row=>row[1]),['started']);
});
test('issue creation, HTTP ACK, unqualified source, owned UNKNOWN and substituted intent cannot manufacture admission',async()=>{
 for(const change of [f=>{f.state.qualification.status='owned_unknown';},f=>{f.context.status='owned_unknown';},
 f=>{f.context.decision_proof=null;},f=>{f.records.at(-1).phase='issue_creation';},f=>{f.selector.issue.node_id='copy';},
 f=>{f.state.facts.ownership.kind='unknown';},f=>{f.state.facts.incumbentIssue.labels=['needs-human'];}]) {
  const f=fixture();change(f);
  // Retained transport may supply an internally corrupt object; digest/origin
  // checks must refuse rather than taking JSON truth as evidence.
  const {context_sha256,...payload}=f.context;f.context.context_sha256=digest(payload);
  for(const row of f.records){const {record_sha256,...body}=row;row.record_sha256=digest(body);}
  f.store.get('admitted:1').bytes=Buffer.from(JSON.stringify(f.context));
  f.store.get('ledger:2').bytes=Buffer.from(f.records.map(row=>JSON.stringify(row)).join('\n'));
  await assert.rejects(authenticateContinuation(f.options));assert.equal(f.calls.filter(row=>row[0]==='publish').length,0);
 }
});
test('paused/cycle-limited/rate-limited/mismatched steps and exhausted original deadline do not emit started receipt',async()=>{
 for(const extra of [{shouldContinue:false},{cyclesExceeded:true},{rateLimited:true},{selectedStep:'agent'},
 {clock:()=>new Date('2040-01-01T00:00:00Z')}]) {
  const f=fixture(),admission=await authenticateContinuation(f.options);await assert.rejects(f.start(admission,extra));
  assert.equal(f.calls.filter(row=>row[0]==='publish').length,0);
 }
});
test('started or incomplete lineage history cannot cause another admission artifact',async()=>{
 const f=fixture(),admission=await authenticateContinuation(f.options);f.state.prior=[{actual_run_id:899}];
 await assert.rejects(f.start(admission),/do not repeat/);assert.equal(f.calls.filter(row=>row[0]==='publish').length,0);
 f.state.prior=null;await assert.rejects(f.start(admission),/unknown/);
});
test('redispatch retains original collector/intent and authentic parent start; ordinary issue-body evolution retains exact node',async()=>{
 const f=fixture(),admission=await authenticateContinuation(f.options),started=await f.start(admission);
 f.issue.body='inert body after the existing optimizer';
 const child=await retainRedispatch({transport:f.transport,selector:f.selector,startedProof:started.proof,nextStep:'apply',observeIssue:async()=>f.issue});
 assert.equal(child.request_sha256,f.selector.request_sha256);assert.deepEqual(child.collector,f.selector.collector);
 assert.deepEqual(child.intent,f.selector.intent);assert.notEqual(lineageKey(child),lineageKey(f.selector));
 f.transport.current={run_id:901,run_attempt:1};
 const next=await authenticateContinuation({...f.options,current:f.transport.current,selector:child,selectedStep:'apply'});
 const result=await f.start(next);assert.equal(result.receipt.run_id,901);assert.equal(result.receipt.selected_step,'apply');
 assert.equal(result.receipt.issue.body_sha256,f.selector.issue.body_sha256);
});
test('redispatch cannot drop binding, substitute issue/node or choose a different transition',async()=>{
 for(const mutate of [f=>{f.issue.node_id='copied';},f=>{f.next='agent';},f=>{f.transport.current={run_id:999,run_attempt:1};}]) {
  const f=fixture(),admission=await authenticateContinuation(f.options),started=await f.start(admission);f.next='apply';mutate(f);
  await assert.rejects(retainRedispatch({transport:f.transport,selector:f.selector,startedProof:started.proof,nextStep:f.next,observeIssue:async()=>f.issue}));
 }
});

test('existing incumbent body evolves only under genuine parent proof; owner and immutable node cannot be replaced',async()=>{
 for(const replace of [null,'owner','node']) {
  const f=fixture(true),admission=await authenticateContinuation(f.options),started=await f.start(admission);
  f.issue.body='native existing incumbent body after optimization';
  const child=await retainRedispatch({transport:f.transport,selector:f.selector,startedProof:started.proof,nextStep:'apply',observeIssue:async()=>f.issue});
  f.state.facts.ownership.incumbent={...f.context.request.incumbent,issue:issueIdentity(f.issue)};
  if(replace==='owner')f.state.facts.ownership.incumbent.owner='replacement';
  if(replace==='node')f.issue.node_id='replacement';
  f.transport.current={run_id:901,run_attempt:1};
  const next={...f.options,current:f.transport.current,selector:child,selectedStep:'apply'};
  if(replace)await assert.rejects(authenticateContinuation(next));
  else assert.equal((await authenticateContinuation(next)).ownership.incumbent.issue.body_sha256,sha(f.issue.body));
 }
});

test('native auto directive remains distinct from its concrete selected step across the existing pipeline',async()=>{
 const f=fixture();let selector=f.selector;
 for(const [selectedStep,forceStep,next] of [['optimize','optimize','apply'],['apply','apply','capability-check'],['capability-check','capability-check','auto'],['create-pr','auto','auto'],['monitor-pr','auto',null]]) {
  const admission=await authenticateContinuation({...f.options,current:f.transport.current,selector,selectedStep,forceStep});
  const started=await f.start(admission);
  assert.equal(started.receipt.selected_step,selectedStep);
  if(next) {
   selector=await retainRedispatch({transport:f.transport,selector,startedProof:started.proof,nextStep:next,observeIssue:async()=>f.issue});
   f.transport.current={run_id:f.transport.current.run_id+1,run_attempt:1};
  }
 }
 const unknown=await authenticateContinuation({...f.options,current:f.transport.current,selector,selectedStep:'auto',forceStep:'auto'});
 await assert.rejects(f.start(unknown),/did not admit workflow execution/);
});

const {observeStartedReceipts}=require('../verifier_correction_autopilot');
function observations(f) {
 const run={id:900,run_attempt:1,status:'completed',head_sha:'a'.repeat(40)};
 f.transport.runs=async()=>[run];
 f.transport.artifacts=async id=>[...f.store.entries()].filter(([key,row])=>key.startsWith('started:') && row.proof.run_id===id)
 .map(([,row])=>({id:row.proof.artifact_id,name:`verifier-correction-started-${id}-${row.proof.run_attempt}`}));
 f.transport.jobs=async()=>[{name:'auto-pilot',run_id:900,run_attempt:1,head_sha:run.head_sha,status:'completed',conclusion:'skipped',steps:[]}];
 return run;
}
test('actual complete started artifact inventory positively reconciles native run/attempt; own receipt prevents re-admission',async()=>{
 const f=fixture(),admission=await authenticateContinuation(f.options);await f.start(admission);observations(f);
 const options={transport:f.transport,request:f.context.request,since:'2026-10-25T12:00:00Z'};
 assert.equal((await observeStartedReceipts(options))[0].receipt.run_id,900);
 await assert.rejects(f.start(admission,{observeLineage:()=>observeStartedReceipts(options)}),/do not repeat/);
});
test('missing or running historical starts are unknown unless native skipped jobs positively prove no execution',async()=>{
 const f=fixture(),run=observations(f);f.transport.current={run_id:901,run_attempt:1};
 const options={transport:f.transport,request:f.context.request,since:'2026-10-25T12:00:00Z'};
 assert.deepEqual(await observeStartedReceipts(options),[]);
 run.status='in_progress';await assert.rejects(observeStartedReceipts(options),/outcome is unknown/);
 run.status='completed';f.transport.jobs=async()=>[{name:'auto-pilot',run_id:900,run_attempt:1,head_sha:run.head_sha,status:'completed',conclusion:'failure',steps:[
  {name:'Record admitted correction start',status:'completed',conclusion:'skipped'},{name:'Execute step - Optimize',status:'completed',conclusion:'success'}]}];
 await assert.rejects(observeStartedReceipts(options),/cannot prove no execution/);
});
test('effect-side reconciler consumes original intent plus exact actual root start, never HTTP204 or issue-created alone',async()=>{
 const {createEffectReconciler}=require('../verifier_correction_host');
 const f=fixture(),admission=await authenticateContinuation(f.options),record=f.records.at(-1),intent=f.store.get('ledger:2').proof;
 observations(f);f.transport.read=async()=>f.issue;
 const retained={snapshots:[{key:f.selector.effect_key,snapshot:{revision:f.records.length,records:f.records},proof:intent}],
 contexts:[{context:f.context,proof:f.store.get('admitted:1').proof}]};
 const reconcile=await createEffectReconciler({transport:f.transport,request:f.context.request,history:async()=>retained,since:'2026-10-25T12:00:00Z'});
 const args={effect_key:f.selector.effect_key,records:f.records};
 assert.equal((await reconcile(args)).continuation,undefined);
 await f.start(admission);f.transport.current={run_id:700,run_attempt:1};
 const actual=await reconcile(args);assert.equal(actual.continuation.run_id,'900');assert.equal(actual.continuation.run_attempt,'1');
 assert.deepEqual(actual.issue,f.selector.issue);
 retained.snapshots[0].proof={...intent,artifact_id:999};await assert.rejects(reconcile(args),/substituted/);
 assert.equal(record.phase,'autopilot_dispatch');
});

test('deadline or ownership change during retained start readback cannot authorize provider execution',async()=>{
 for(const extra of [{recheckAdmission:async()=>{throw Error('ownership changed during upload');}},
 {recheckAdmission:async()=>({lineage_key:'different'})}]) {
  const f=fixture(),admission=await authenticateContinuation(f.options);await assert.rejects(f.start(admission,extra));
 }
 const f=fixture(),admission=await authenticateContinuation(f.options);let expired=false;
 await assert.rejects(f.start(admission,{observeLineage:async()=>{expired=true;return [];},
 clock:()=>new Date(expired?'2040-01-01T00:00:00Z':'2026-10-26T00:00:00Z')}),/deadline exhausted during history/);
 assert.equal(f.calls.filter(row=>row[0]==='publish').length,0);
});

test('native created-PR response proof preserves legitimate create-pr to monitor continuation; unrelated PR remains held',async()=>{
 const {retainCreatedPull}=require('../verifier_correction_autopilot');
 const f=fixture();let selector=f.selector;
 for(const [selectedStep,forceStep,next] of [['optimize','optimize','apply'],['apply','apply','capability-check'],['capability-check','capability-check','auto']]) {
  const admission=await authenticateContinuation({...f.options,current:f.transport.current,selector,selectedStep,forceStep}),started=await f.start(admission);
  selector=await retainRedispatch({transport:f.transport,selector,startedProof:started.proof,nextStep:next,observeIssue:async()=>f.issue});
  f.transport.current={run_id:f.transport.current.run_id+1,run_attempt:1};
 }
 const opts={...f.options,current:f.transport.current,selector,selectedStep:'create-pr',forceStep:'auto'};
 const admission=await authenticateContinuation(opts),started=await f.start(admission);
 const pull={id:88,number:10,node_id:'PR_10',title:'Native corrective PR',body:'<!-- meta:issue:9 -->\n\nCloses #9\n\nExact scoped implementation.',state:'open',labels:[],assignees:[],
  head:{sha:'b'.repeat(40),ref:'codex/issue-9',repo:{id:1,full_name:'stranske/example'}},base:{ref:'main',repo:{id:1,full_name:'stranske/example'}}};
 const proof=await retainCreatedPull({transport:f.transport,selector,startedProof:started.proof,
  response:{status:201,headers:{'x-github-request-id':'inert-native-pr-response'},data:pull}});
 f.transport.read=async(resource,method,args)=>{assert.equal(resource,'pulls');assert.equal(args.pull_number,10);return pull;};
 f.state.facts.workInventory.openPullRequests=[pull];
 const owned=await authenticateContinuation({...opts,producedPull:proof});assert.equal(owned.owned_pull.pull.id,88);
 selector=await retainRedispatch({transport:f.transport,selector,startedProof:started.proof,nextStep:'auto',ownedPull:owned.owned_pull,observeIssue:async()=>f.issue});
 f.transport.current={run_id:f.transport.current.run_id+1,run_attempt:1};
 const monitor={...f.options,current:f.transport.current,selector,selectedStep:'monitor-pr',forceStep:'auto'};
 assert.equal((await authenticateContinuation(monitor)).owned_pull.pull.id,88);
 pull.head.sha='c'.repeat(40);const updated=await authenticateContinuation(monitor);
 assert.equal(updated.owned_pull.pull.created_head_sha,'b'.repeat(40));assert.equal(updated.owned_pull.observed_head_sha,'c'.repeat(40));
 f.state.facts.workInventory.openPullRequests.push({...pull,id:89,node_id:'PR_other',number:11});
 await assert.rejects(authenticateContinuation(monitor),/Competing continuation/);
});

test('corrective PR linkage cannot confer source-closure authority through copied freeform text',()=>{
 const {assertPullScopeBody}=require('../verifier_correction_autopilot'),issue={number:'9'};
 assert.doesNotThrow(()=>assertPullScopeBody('<!-- meta:issue:9 -->\n\nCloses #9\n\nPreserve original PR #7 and source issue #1.',issue,'stranske/example'));
 for(const suffix of ['Closes #1','Fixes stranske/example#1','Resolves https://github.com/stranske/example/issues/1','Closes #9, #1']) {
  assert.throws(()=>assertPullScopeBody(`<!-- meta:issue:9 -->\n\nCloses #9\n\n${suffix}`,issue,'stranske/example'),/another source issue/);
 }
});


// Follow the real retained directive chain to format. Every transport operation is
// an in-memory artifact or a native GitHub-response fixture; no effect API exists.
async function formatterFixture() {
 const f=fixture(),publish=f.transport.publish;
 f.transport.publish=async(kind,bytes)=>{const proof=await publish(kind,bytes);
  proof.created_at=`2026-10-26T00:${kind==='formatpause'?'04':kind==='formatredispatch'?'34':String(f.transport.current.run_id-900).padStart(2,'0')}:00Z`;return proof;};
 let selector=f.selector;
 for(const [selectedStep,forceStep,next] of [['optimize','optimize','apply'],['apply','apply','capability-check'],['capability-check','capability-check','auto']]) {
  const admission=await authenticateContinuation({...f.options,current:f.transport.current,selector,selectedStep,forceStep}),started=await f.start(admission);
  selector=await retainRedispatch({transport:f.transport,selector,startedProof:started.proof,nextStep:next,observeIssue:async()=>f.issue});
  f.transport.current={run_id:f.transport.current.run_id+1,run_attempt:1};
 }
 const admission=await authenticateContinuation({...f.options,current:f.transport.current,selector,selectedStep:'format',forceStep:'auto'}),started=await f.start(admission);
 const events=[{id:4001,event:'labeled',label:{name:'agents:auto-pilot-pause'},created_at:'2026-10-26T00:04:00Z',
  actor:{id:41898282,login:'github-actions[bot]',type:'Bot'}}];
 f.issue.labels=['agents:auto-pilot-pause'];
 f.transport.read=async(resource,method,args)=>{assert.equal(resource,'issues');assert.equal(args.issue_number,9);
  if(method==='listEvents')return events;if(method==='get')return f.issue;throw Error('Unexpected inert read');};
 const retain=()=>retainFormatPause({transport:f.transport,selector,startedProof:started.proof,
  response:{status:200,headers:{'x-github-request-id':'inert-native-format-pause'}}});
 const child=async proof=>retainRedispatch({transport:f.transport,selector,startedProof:started.proof,nextStep:'format',kind:'formatredispatch',pauseProof:proof,observeIssue:async()=>f.issue});
 const wake=childSelector=>authenticateContinuation({...f.options,selector:childSelector,current:{...f.transport.current,job:'format-pause-wakeup'},selectedStep:'format',forceStep:'format'});
 return {...f,selector,started,events,retain,child,wake};
}
test('formatter wakeup admits only its exact native bot pause and body; ordinary continuation remains paused',async()=>{
 const f=await formatterFixture(),proof=await f.retain(),selector=await f.child(proof);
 assert.deepEqual(await validateFormatPause({transport:f.transport,proof,selector:f.selector,started:f.started.receipt}),issueIdentity(f.issue));
 const admission=await f.wake(selector);assert.equal(admission.selected_step,'format');
 await assert.rejects(authenticateContinuation({...f.options,selector,current:{run_id:904,run_attempt:1,job:'auto-pilot'},selectedStep:'format',forceStep:'format'}),/held|pause|human/i);
 f.issue.labels=[];f.events.push({...f.events[0],id:4002,event:'unlabeled',created_at:'2026-10-26T00:35:00Z'});
 assert.equal((await f.wake(selector)).selected_step,'format');
});
test('later human or bot relabel, removed pause, and body substitution cannot reuse retained formatter ownership',async()=>{
 for(const mutate of [
  f=>f.events.push({...f.events[0],id:4002,created_at:'2026-10-26T00:05:00Z',actor:{id:12,login:'human',type:'User'}}),
  f=>f.events.push({...f.events[0],id:4002,created_at:'2026-10-26T00:05:00Z'}),
  f=>f.events.push({...f.events[0],id:4002,event:'unlabeled',created_at:'2026-10-26T00:05:00Z'}),
  f=>{f.issue.body='Substituted body after native formatter pause';}]) {
  const f=await formatterFixture(),proof=await f.retain(),selector=await f.child(proof);mutate(f);
  const before=f.calls.filter(row=>row[0]==='publish').length;
  await assert.rejects(f.wake(selector));assert.equal(f.calls.filter(row=>row[0]==='publish').length,before);
 }
});
test('own formatter pause exception preserves human, source-issue and source-PR holds',async()=>{
 for(const mutate of [
  ...['needs-human','agents:auto-pilot-failed','agents:paused'].map(label=>f=>f.issue.labels.push(label)),
  f=>f.state.facts.sourceIssue.labels.push('agents:auto-pilot-pause'),
  f=>f.state.facts.pull.labels.push('agents:auto-pilot-pause')]) {
  const f=await formatterFixture(),proof=await f.retain(),selector=await f.child(proof);mutate(f);
  await assert.rejects(f.wake(selector),/held|pause|human/i);
 }
});
test('native pause capture rejects human actor, pre-start event, incomplete or ambiguous history without artifact',async()=>{
 for(const mutate of [
  f=>{f.events[0].actor={id:12,login:'human',type:'User'};},
  f=>{f.events[0].created_at='2026-10-26T00:02:59Z';},
  f=>{f.events[0].created_at=undefined;},f=>{f.events.push({...f.events[0]});},
  f=>{f.events.splice(0);},f=>{f.issue.body='Changed before native pause capture';},
  f=>{f.transport.read=async()=>{throw Error('Native event inventory unavailable');};},
  f=>{delete f.started.proof.created_at;}]) {
  const f=await formatterFixture();mutate(f);const before=f.calls.filter(row=>row[0]==='publish').length;
  await assert.rejects(f.retain());assert.equal(f.calls.filter(row=>row[0]==='publish').length,before);
 }
});

test('formatter native response failure cannot produce a retained ownership artifact',async()=>{
 for(const response of [{status:500,headers:{'x-github-request-id':'inert'}},{status:200,headers:{}},null]) {
  const f=await formatterFixture(),before=f.calls.filter(row=>row[0]==='publish').length;
  await assert.rejects(retainFormatPause({transport:f.transport,selector:f.selector,startedProof:f.started.proof,response}));
  assert.equal(f.calls.filter(row=>row[0]==='publish').length,before);
 }
});
