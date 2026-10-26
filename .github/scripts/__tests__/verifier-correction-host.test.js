'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('path');
const {digest}=require('../verification_event');
const {createFreshCollector,crossReferenceDigest}=require('../verifier_correction_host');
const {checkFreshFacts,issueIdentity}=require('../verifier_correction_effects');
async function fixture(existing=false,change=()=>{}) {
 const request=structuredClone(require('../../../tests/fixtures/verifier_correction/integration-request.json'));
 const original=require('../../../tests/fixtures/verifier_correction/integration-original.json');
 const incumbent={id:88,number:8,node_id:'I_8',title:'[Follow-up] PR #7',body:'native exact follow-up body',state:'open',labels:[{name:'follow-up'}],assignees:[{login:'owner'}]};
 if(existing) {
  request.incumbent={issue:issueIdentity(incumbent),owner:'owner',assignment_ref:'github:stranske/example/issues/8/events/1001',lineage_ref:'pending-native-cross-reference'};
  const {request_sha256,...payload}=request;request.request_sha256=digest(payload);
 }
 const state={pull:{...structuredClone(original.pull),id:7,merged_at:'2026-10-25T12:00:00Z',labels:[]},source:{...structuredClone(original.sourceIssue),id:1,labels:[]},
 incumbent,prTimeline:[],opened:existing?[incumbent]:[],changed:existing?[incumbent]:[],pulls:[],retained:{contexts:[],snapshots:[]},runs:[],
 events:[{id:1001,event:'assigned',assignee:{login:'owner'},created_at:'2026-10-25T13:00:00Z'}],
 timeline:[{event:'cross-referenced',actor:{id:23},created_at:'2026-10-25T13:01:00Z',updated_at:'2026-10-25T13:01:00Z',source:{type:'issue',issue:{id:7,node_id:'PR_7',number:7,repository:{full_name:'stranske/example'},pull_request:{url:'inert:native-pr-url'}}}}]};
 if(existing) {request.incumbent.lineage_ref=`github:stranske/example/issues/8/timeline-sha256/${crossReferenceDigest(state.timeline[0],state.pull)}`;
 const {request_sha256,...payload}=request;request.request_sha256=digest(payload);}
 change(state,request);
 const calls=[];
 const methods={pulls:{get:()=>state.pull,list:()=>state.pulls},issues:{get:a=>a.issue_number===1?state.source:state.incumbent,
 listForRepo:a=>a.state==='open'?state.opened:state.changed,listEvents:()=>state.events,listEventsForTimeline:a=>a.issue_number===7?state.prTimeline:state.timeline},
 repos:{getCollaboratorPermissionLevel:a=>({permission:'write',user:{login:a.username}})}};
 const github={graphql:async()=>{if(state.connectedError)throw Error('native association unavailable');return {node:state.connected};},rest:Object.fromEntries(Object.entries(methods).map(([resource,rows])=>[resource,Object.fromEntries(Object.entries(rows).map(([method,fn])=>[method,async args=>{
  calls.push([resource,method,args]);if(state.readError){const error=Error('unavailable native read');error.status=403;throw error;}return {data:fn(args)};
 }]))]))};
 const collect=await createFreshCollector({github,repository:'stranske/example',actor:'authorized-actor',registryPath:path.join(__dirname,'../../agents/registry.yml'),
 history:async args=>{calls.push(['history',args]);return state.retained;},observeContinuations:async()=>state.runs,policy:async()=>state.policy || 'follow-up',clock:()=>new Date('2026-10-26T00:00:00Z'),transport:{current:{run_id:700,run_attempt:1}}});
 return {state,request,calls,collect,github};
}
test('native complete no-incumbent proof derives from real merged boundary, empty inventories and enabled registry agent',async()=>{
 const f=await fixture(),facts=await f.collect(f.request);assert.equal(facts.ownership.kind,'no_incumbent');assert.equal(facts.agent.key,'codex');assert.equal(facts.agent.enabled,true);
 checkFreshFacts(f.request,facts,{ownership:facts.ownership});
 assert.equal(f.calls.find(row=>row[0]==='history')[1].since,'2026-10-25T12:00:00Z');
 assert.equal(f.calls.find(row=>row[1]==='listForRepo' && row[2].state==='all')[2].since,'2026-10-25T12:00:00Z');
});
test('existing incumbent requires genuine current assignment plus native original-PR lineage and exact issue identity',async()=>{
 const f=await fixture(true),facts=await f.collect(f.request);assert.equal(facts.ownership.kind,'existing');
 assert.deepEqual(facts.ownership.incumbent,f.request.incumbent);checkFreshFacts(f.request,facts,{ownership:facts.ownership});
});
test('agent-label/queue incumbent without native proof never becomes no-incumbent',async()=>{
 for(const mutate of [s=>{s.events=[];},s=>{s.timeline=[];},s=>{s.incumbent.assignees=[];},s=>{s.events.push({id:1003,event:'unassigned',assignee:{login:'owner'},created_at:'2026-10-25T14:00:00Z'});},
 s=>{s.timeline[0].source.issue.repository.full_name='foreign/repo';}]) {
  const f=await fixture(true,mutate);assert.equal((await f.collect(f.request)).ownership.kind,'unknown');
 }
 const fresh=await fixture(false,s=>{s.opened=[s.incumbent];s.changed=[s.incumbent];s.incumbent.assignees=[];s.incumbent.labels.push({name:'agent:codex'});});
 assert.equal((await fresh.collect(fresh.request)).ownership.kind,'unknown');
});
test('unknown retained effects, other follow-ups or active continuation cannot supply a positive absence proof',async()=>{
 for(const mutate of [s=>{s.runs=[{run_id:800,state:'in_progress'}];},
 s=>{s.retained.snapshots=[{snapshot:{records:[{effect_key:'other',kind:'intent'}]}}];},
 s=>{s.opened=[s.incumbent];s.changed=[s.incumbent];}]) {
  const f=await fixture(false,mutate);assert.equal((await f.collect(f.request)).ownership.kind,'unknown');
 }
});
test('missing/inconsistent/unbounded native inventories remain unread UNKNOWN instead of empty ownership',async()=>{
 for(const mutate of [s=>{s.readError=true;},s=>{s.pull.merged_at=null;},
 s=>{s.opened=[s.incumbent,s.incumbent];},s=>{s.opened=[s.incumbent];s.changed=[{...s.incumbent,body:'changed during scan'}];},
 s=>{s.retained=null;}]) {
  const f=await fixture(false,mutate);await assert.rejects(f.collect(f.request));
 }
});
test('native positive pause, chain depth and existing verdict policy guard remain effective',async()=>{
 for(const mutate of [s=>{s.pull.labels=[{name:'needs-human'}];},s=>{s.pull.body='<!-- follow-up-depth: 2 -->';},s=>{s.policy='needs-human';}]) {
  const f=await fixture(false,mutate),facts=await f.collect(f.request);assert.throws(()=>checkFreshFacts(f.request,facts,{ownership:facts.ownership}));
 }
});

test('removed follow-up label or body references cannot erase a native queued/assigned incumbent',async()=>{
 for(const nativeOnly of [false,true]) {
  const f=await fixture(false,s=>{
   s.incumbent.labels=[{name:'agent:codex'},{name:'agents:auto-pilot'}];
   if(nativeOnly) {
    s.incumbent.title='body rewritten by existing worker';s.incumbent.body='no textual PR reference';
    s.prTimeline=[{event:'cross-referenced',actor:{id:23},created_at:'2026-10-25T13:01:00Z',source:{type:'issue',issue:{id:88,node_id:'I_8',number:8,repository:{full_name:'stranske/example'}}}}];
   }
   s.opened=[s.incumbent];s.changed=[s.incumbent];
  });
  const facts=await f.collect(f.request);assert.equal(facts.ownership.kind,'unknown');assert.equal(facts.workInventory.assignments.length,1);
 }
});

test('direct original-PR corrective writers and native-linked PRs cannot disappear from no-incumbent inventory',async()=>{
 for(const nativeOnly of [false,true]) {
  const f=await fixture(false,s=>{
   s.pulls=[{id:99,number:9,node_id:'PR_9',state:'open',labels:[],assignees:[],title:nativeOnly?'rewritten title':'Follow-up PR #7',body:nativeOnly?'rewritten body':'Corrects verification finding from PR #7'}];
   if(nativeOnly)s.prTimeline=[{event:'cross-referenced',actor:{id:23},created_at:'2026-10-25T13:01:00Z',source:{type:'issue',issue:{id:99,node_id:'PR_9',number:9,pull_request:{},repository:{full_name:'stranske/example'}}}}];
  });
  const facts=await f.collect(f.request);assert.equal(facts.ownership.kind,'unknown');assert.equal(facts.workInventory.openPullRequests.length,1);
 }
});

test('heterogeneous genuine timeline shapes do not invent numeric cross-reference IDs',async()=>{
 const f=await fixture(true,s=>{s.prTimeline=[{event:'committed',sha:'a'.repeat(40),node_id:'C_fixture'}];});
 assert.equal((await f.collect(f.request)).ownership.kind,'existing');
 assert.equal(f.state.timeline[0].id,undefined);assert.match(f.request.incumbent.lineage_ref,/timeline-sha256\/[a-f0-9]{64}$/);
});

test('missing exclusion fields on issue/PR inventory cannot be interpreted as unrelated work',async()=>{
 for(const field of ['title','body','node_id','labels','assignees','number','state']) {
  const f=await fixture(false,s=>{delete s.incumbent[field];s.opened=[s.incumbent];s.changed=[s.incumbent];});
  await assert.rejects(f.collect(f.request));
 }
 const id=await fixture(false,s=>{s.incumbent.id='88';s.opened=[s.incumbent];});await assert.rejects(id.collect(id.request));
});

test('strict cross-reference content never accepts synthetic numeric IDs instead of native fields',()=>{
 assert.throws(()=>crossReferenceDigest({event:'cross-referenced',id:123,actor:{},created_at:'bad',source:{type:'issue',issue:{number:7,repository:{full_name:'stranske/example'},pull_request:{}}}},
 {number:7,head:{sha:'a'.repeat(40)}}),/identity unavailable/);
});

test('native connected association is joined through actual GraphQL node/source/subject, never fabricated REST source fields',async()=>{
 for(const kind of ['source','incumbent','wrong_subject','missing']) {
  const f=await fixture(false,s=>{
   s.pull.node_id='PR_7';s.prTimeline=[{id:1005,node_id:'EV_1005',event:'connected',created_at:'2026-10-25T13:02:00Z'}];
   s.connected={id:'EV_1005',createdAt:'2026-10-25T13:02:00Z',source:{__typename:'PullRequest',id:'PR_7',number:7,repository:{nameWithOwner:'stranske/example'}},
    subject:{__typename:'Issue',id:kind==='source'?'I_1':'I_8',number:kind==='source'?1:8,repository:{nameWithOwner:'stranske/example'}}};
   if(kind==='incumbent'){s.opened=[s.incumbent];s.changed=[s.incumbent];}
   if(kind==='wrong_subject')s.connected.source.id='PR_foreign';
   if(kind==='missing')s.connected=null;
  });
  if(['wrong_subject','missing'].includes(kind))await assert.rejects(f.collect(f.request));
  else assert.equal((await f.collect(f.request)).ownership.kind,kind==='source'?'no_incumbent':'unknown');
 }
});

test('frozen native cross-reference v1 projection excludes mutable text and binds fresh exact source head',()=>{
 const f=require('../../../tests/fixtures/verifier_correction/native-crossref-lineage.json');
 assert.equal(crossReferenceDigest(f.event,f.pull),f.sha256);
 const changed=structuredClone(f.event);changed.source.issue.body='rewritten';changed.source.issue.labels=['changed'];
 assert.equal(crossReferenceDigest(changed,f.pull),f.sha256);
 assert.notEqual(crossReferenceDigest(changed,{...f.pull,head:{sha:'b'.repeat(40)}}),f.sha256);
});


function nativeStageHistory(f,records) {
 const {effectKey,seedForRequest}=require('../verifier_correction_effects');
 const key=effectKey(seedForRequest(f.request));
 f.state.retained.snapshots=records.map((_,index)=>({key,snapshot:{revision:index+1,records:structuredClone(records.slice(0,index+1))},
  proof:{run_id:700,run_attempt:1,artifact_id:100+index,archive_sha256:'a'.repeat(64),member_sha256:String(index).repeat(64)}}));
 const last=records.at(-1),proof=f.state.retained.snapshots.at(-1)?.proof;
 return last?{schema:'closer-correction-active-stage/v1',effect_key:key,request_sha256:f.request.request_sha256,
 phase:last.phase,record_sha256:last.record_sha256,revision:records.length,proof}:null;
}
function stageRecord(f,records,kind,phase,extra={}) {
 const {effectKey,seedForRequest}=require('../verifier_correction_effects');
 const payload={schema:'closer-correction-effect-ledger/v1',effect_key:effectKey(seedForRequest(f.request)),revision:records.length+1,
 kind,phase,request_sha256:f.request.request_sha256,consumer:{run_id:'700',run_attempt:'1'},...extra};
 return {...payload,record_sha256:digest(payload)};
}
test('only exact current native stage is exempt from no-incumbent starting work; old, forged and forked stages stay unknown',async()=>{
 const f=await fixture(),records=[];records.push(stageRecord(f,records,'intent','issue_creation'));
 const activeEffect=nativeStageHistory(f,records);
 assert.equal((await f.collect(f.request)).ownership.kind,'unknown');
 const fresh=await f.collect(f.request,{activeEffect});assert.equal(fresh.ownership.kind,'no_incumbent');
 assert.deepEqual(fresh.workInventory.retainedEffects,[]);checkFreshFacts(f.request,fresh,{ownership:fresh.ownership});
 for(const change of [a=>{a.proof.run_id=701;},a=>{a.record_sha256='f'.repeat(64);},a=>{a.revision=2;},a=>{a.phase='autopilot_dispatch';},a=>{delete a.proof;}]) {
  const wrong=structuredClone(activeEffect);change(wrong);await assert.rejects(f.collect(f.request,{activeEffect:wrong}));
 }
 f.state.retained.snapshots.push(structuredClone(f.state.retained.snapshots[0]));
 await assert.rejects(f.collect(f.request,{activeEffect}),/ambiguous|forked/);
});
test('native no-incumbent consumer passes its just-retained create and dispatch gates once, then uncertain dispatch never repeats',async()=>{
 const {createCorrectionEffectConsumer,seedForRequest}=require('../verifier_correction_effects');
 const f=await fixture(),records=[],effects={issues:0,dispatches:0},consumer={run_id:'700',run_attempt:'1'};
 let latestActive=null;
 const ledger={read:async()=>({revision:records.length,records:structuredClone(records)}),append:async args=>{
  assert.equal(args.expected_revision,records.length);records.push(args.record);latestActive=nativeStageHistory(f,records);return args.record;
 },continuationSelector:async({issue})=>({request_sha256:f.request.request_sha256,effect_key:records.at(-1).effect_key,issue})};
 f.github.rest.issues.create=async payload=>{
  effects.issues++;f.state.incumbent={id:99,number:9,node_id:'I_9',title:payload.title,body:payload.body,labels:payload.labels,
   state:'open',html_url:'https://github.com/stranske/example/issues/9',assignees:[],user:{id:41898282,login:'github-actions[bot]',type:'Bot'},created_at:'2026-10-26T00:00:00Z'};
  f.state.opened=[f.state.incumbent];f.state.changed=[f.state.incumbent];
  return {status:201,data:f.state.incumbent,headers:{'x-github-request-id':'inert-native-create'}};
 };
 f.github.rest.actions={createWorkflowDispatch:async()=>{effects.dispatches++;return {status:204};}};
 const fresh=async(request,options={})=>{
  const activeEffect=options.activeIntent?latestActive:null;
  if(activeEffect)assert.equal(activeEffect.record_sha256,options.activeIntent.record_sha256);
  return f.collect(request,{...options,activeEffect});
 };
 const consume=createCorrectionEffectConsumer({github:f.github,ledger,defaultBranch:'main',clock:()=>new Date('2026-10-26T00:00:00Z'),
 authenticate:async()=>({request:f.request,seed:seedForRequest(f.request),required_tests:f.request.required_tests}),collectFreshFacts:fresh,
 reconcile:async()=>({issues:effects.issues?[f.state.incumbent]:[]})});
 const first=await consume(f.request,consumer);assert.equal(first.effect_state,'outcome_unknown');assert.deepEqual(effects,{issues:1,dispatches:1},JSON.stringify(first));
 assert.deepEqual(records.map(row=>[row.kind,row.phase]),[['intent','issue_creation'],['issue_confirmed','issue_creation'],['intent','autopilot_dispatch']]);
 const next=await consume(f.request,consumer);assert.equal(next.effect_state,'outcome_unknown');assert.deepEqual(effects,{issues:1,dispatches:1});
});


test('nullable native source/PR and incumbent bodies preserve exact empty digest and chain-depth checks',async()=>{
 const {nativeBody}=require('../verifier_correction_consumer'),{createHash}=require('crypto');
 const empty=createHash('sha256').update('').digest('hex');
 assert.equal(nativeBody(null),'');assert.equal(nativeBody(''),'');
 for(const value of [undefined,false,0,{}])assert.throws(()=>nativeBody(value),/body unavailable/);
 for(const existing of [false,true]) {
  const f=await fixture(existing,(state,request)=>{
   state.pull.body=null;state.source.body=null;request.source_issue.body_sha256=empty;
   if(existing){state.incumbent.body=null;request.incumbent.issue.body_sha256=empty;}
   const {request_sha256,...payload}=request;request.request_sha256=digest(payload);
  });
  const facts=await f.collect(f.request);assert.equal(facts.chainDepth,0);
  assert.equal(facts.ownership.kind,existing?'existing':'no_incumbent');
  checkFreshFacts(f.request,facts,{ownership:facts.ownership});
  assert.equal(issueIdentity(facts.sourceIssue).body_sha256,empty);
 }
});
