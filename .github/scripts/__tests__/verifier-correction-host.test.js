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
 history:async args=>{calls.push(['history',args]);return state.retained;},observeContinuations:async()=>state.runs,policy:async()=>state.policy || 'follow-up',clock:()=>new Date('2026-10-26T00:00:00Z')});
 return {state,request,calls,collect};
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
