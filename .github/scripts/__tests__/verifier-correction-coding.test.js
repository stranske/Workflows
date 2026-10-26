'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('path'),{createHash}=require('crypto');
const {digest}=require('../verification_event');
const {seedForRequest,effectKey,issueIdentity,sourceScopeDigest}=require('../verifier_correction_effects');
const {artifactName,SPECS}=require('../verifier_correction_artifacts');
const {resolveCodingScope,resolvePullCodingScope,fitCodingText}=require('../verifier_correction_runtime');
const {codingBudgetFromVariable,validateCodingBudget,minimumCodingBudget}=require('../verifier_correction_consumer');
const clone=value=>structuredClone(value),sha=value=>createHash('sha256').update(value).digest('hex');
const pythonRoot=path.resolve(__dirname,'../../..');
function fixture(existing=false,{number=9,run=700,pr='7',sourceDigest=null,commentBody=null}={}) {
 const request=clone(require('../../../tests/fixtures/verifier_correction/integration-request.json'));
 const issue={number,node_id:`I_${number}`,body:`Complete ORIGINAL_ISSUE_${number}: retain every original requirement.`,title:'inert native issue',state:'open'};
 request.target.pr=pr;if(commentBody)request.original_verifier.comment_sha256=sha(commentBody);if(sourceDigest)request.source_issue.body_sha256=sourceDigest;
 request.required_tests.push({kind:'existing_selector',id:'selector-2',finding_id:request.finding.id,source_ref:'git:'+request.target.head_sha,path:'tests/test_exact.py',selector:'tests/test_exact.py::test_required',file_sha256:'c'.repeat(64)});
 if(existing)request.incumbent={issue:issueIdentity(issue),owner:'inert-owner',assignment_ref:`github:stranske/example/issues/${number}/events/1001`,lineage_ref:`github:stranske/example/issues/${number}/timeline/1002`};
 {const {request_sha256,...body}=request;request.request_sha256=digest(body);}
 const seed=seedForRequest(request),key=effectKey(seed),bundle=clone(require('../../../tests/fixtures/verifier_correction/integration-seed-bundle.json'));
 const decision=clone(require('../../../tests/fixtures/verifier_correction/integration-decision.json'));
 decision.findings[0].required_tests_sha256=digest(request.required_tests);
 Object.assign(decision,{request_sha256:request.request_sha256,seed_effect_key:key,source_scope_digest:sourceScopeDigest(seed)});
 const qualification={...clone(require('../../../tests/fixtures/verifier_correction/integration-qualification.json')),profile_identity_sha256:'f'.repeat(64)};
 const finding=JSON.parse(require('../../../tests/fixtures/verifier_correction/integration-original.json').result_text).concerns[0];
 const payload={coding_budget:codingBudgetFromVariable('100000',request),schema:'closer-correction-admitted/v1',status:'admitted',classification:{status:'admitted'},request,seed,effect_key:key,bundle,decision,qualification,
  finding_text:finding,decision_proof:{status:'authenticated',decision_sha256:digest(decision),profile_identity_sha256:'f'.repeat(64)},
  collector:{repository:request.target.repository,run_id:run,run_attempt:1}};
 const context={...payload,context_sha256:digest(payload)},records=[],store=new Map(),metadata=[],calls=[];
 const add=(kind,bytes,suffix='')=>{const id=store.size+run*10,name=artifactName(kind,run,1,suffix),proof={repository:request.target.repository,run_id:run,run_attempt:1,
  artifact_id:id,archive_sha256:sha(bytes),member_sha256:sha(bytes),run_created_at:'2026-10-26T00:00:00Z'};
  metadata.push({id,name,expired:false});store.set(id,{bytes:Buffer.from(bytes),proof,kind,name});};
 const append=(kind,phase,more={})=>{const row={schema:'closer-correction-effect-ledger/v1',effect_key:key,revision:records.length+1,kind,phase,
  request_sha256:request.request_sha256,consumer:{run_id:String(run),run_attempt:'1'},...more};records.push({...row,record_sha256:digest(row)});};
 if(!existing) {
  append('intent','issue_creation');
  const consumer={run_id:String(run),run_attempt:'1'},identity=issueIdentity(issue);
  append('issue_confirmed','issue_creation',{issue:identity,creation_response:{schema:'closer-correction-issue-response/v1',http_status:201,github_request_id:'inert-native-creation',
   request_sha256:request.request_sha256,effect_key:key,consumer,issue:identity,creator:{id:41898282,login:'github-actions[bot]',type:'Bot'},created_at:'2026-10-26T00:00:00Z'}});
 }
 append('intent','autopilot_dispatch');
 const rebuild=()=>{store.clear();metadata.splice(0);const {context_sha256,...body}=context;context.context_sha256=digest(body);
  add('admitted',JSON.stringify(context));for(let revision=1;revision<=records.length;revision++)add('ledger',records.slice(0,revision).map(row=>JSON.stringify(row)).join('\n'),`${key}-r${revision}`);};rebuild();
 const nativeRun={id:run,run_attempt:1,status:'completed'},jobs=[{name:SPECS.ledger.job,run_id:run,run_attempt:1,head_sha:'a'.repeat(40),status:'completed',conclusion:'success',steps:[{name:SPECS.ledger.step,status:'completed',conclusion:'success'}]}];
 const transport={repository:request.target.repository,current:{run_id:999,run_attempt:1},
  read:async(resource,method,args)=>{calls.push(['read',resource,method,args]);assert.equal(resource,'issues');assert.equal(method,'get');assert.equal(args.issue_number,number);return issue;},
  runs:async(workflow,since)=>{assert.equal(workflow,SPECS.admitted.workflow);assert.equal(since,'1970-01-01T00:00:00Z');return [nativeRun];},
  artifacts:async id=>{assert.equal(id,run);return metadata;},canonicalRun:async(id,attempt,workflow)=>{calls.push(['canonical',id,attempt,workflow]);assert.equal(id,run);assert.equal(attempt,1);return {head_sha:'a'.repeat(40)};},
  jobs:async()=>jobs,load:async(selector,kind,name)=>{calls.push(['load',kind]);const row=store.get(selector.artifact_id);assert.ok(row,'exact inert archive exists');assert.equal(row.kind,kind);assert.equal(row.name,name);
   assert.equal(metadata.find(item=>item.id===selector.artifact_id).expired,false,'expired archive cannot authenticate');return row;}};
 return {request,context,issue,records,transport,calls,rebuild,metadata,store,nativeRun,jobs,run};
}
const base='<!-- agent-activation-marker -->\nAgent worker activated.\n\n@codex start\n**Focus on this task first:** exact-incumbent-task';
for(const existing of [false,true])test(`real ${existing?'existing':'no-incumbent'} scope reaches complete final Belt activation with typed required tests`,async()=>{
 const f=fixture(existing),scope=await resolveCodingScope({transport:f.transport,issueNumber:9});
 assert.equal(scope.original_issue_body,f.issue.body);assert.equal(scope.finding_text,f.context.finding_text);assert.deepEqual(scope.required_tests,f.request.required_tests);
 const final=fitCodingText({base,scope,budget:'100000',pythonRoot});
 assert.ok(final.startsWith(base+'\n\n## Complete original issue scope\n'+f.issue.body));const rendered=JSON.parse(final.slice(final.indexOf('{')));assert.equal(rendered.finding_text,scope.finding_text);assert.deepEqual(rendered.required_tests,scope.required_tests);
 for(const required of scope.required_tests)assert.ok(final.includes(required.specification || required.selector));
 assert.ok(f.calls.some(row=>row[0]==='canonical'));assert.ok(f.calls.some(row=>row[1]==='admitted'));assert.ok(f.calls.some(row=>row[1]==='ledger'));
});
test('complete empty native history returns null and legacy activation stays exact bytes without a budget',async()=>{
 const f=fixture();f.transport.runs=async()=>[];const scope=await resolveCodingScope({transport:f.transport,issueNumber:9});assert.equal(scope,null);
 assert.equal(fitCodingText({base,scope,budget:undefined,pythonRoot}),base);
});
test('malformed context, unknown classification, expired archive and incomplete history cannot yield coding scope',async()=>{
 for(const mutate of [f=>{f.context.finding_text='Caller substitution';f.rebuild();},f=>{f.context.decision_proof.status='unknown';f.rebuild();},
  f=>{f.context.request.original_operation.deadline='2020-01-01T00:00:00Z';const {request_sha256,...body}=f.request;f.request.request_sha256=digest(body);f.rebuild();},
  f=>{f.metadata[0].expired=true;},f=>{f.nativeRun.run_attempt=0;},f=>{f.transport.runs=async()=>{throw Error('incomplete native history');};},
  f=>{f.metadata.splice(0,1);},f=>{f.metadata.push({...f.metadata[0],id:99999});},f=>{f.metadata.splice(1,1);}]) {
  const f=fixture();mutate(f);await assert.rejects(resolveCodingScope({transport:f.transport,issueNumber:9}));
 }
});
test('native no-incumbent creation proof and exact issue node/body cannot be replaced by copied markers',async()=>{
 for(const mutate of [f=>{delete f.records[1].creation_response;},f=>{f.records[1].creation_response.http_status=204;},
  f=>{f.issue.node_id='I_copied';},f=>{f.issue.body+='\nCopied marker';}]) {
  const f=fixture();mutate(f);for(const row of f.records){const {record_sha256,...body}=row;row.record_sha256=digest(body);}f.rebuild();
  await assert.rejects(resolveCodingScope({transport:f.transport,issueNumber:9}));
 }
});
test('final activation missing budget and overflow hold synchronously before any activation effect',async()=>{
 const f=fixture(),scope=await resolveCodingScope({transport:f.transport,issueNumber:9});let effects=0;
 for(const budget of [undefined,'','0','caller-unbounded','1'])assert.throws(()=>{const body=fitCodingText({base,scope,budget,pythonRoot});effects++;return body;});
 assert.equal(effects,0);
});
function crossref(pull) {return {event:'cross-referenced',actor:{id:123},created_at:'2026-10-26T00:01:00Z',
 source:{type:'issue',issue:{id:pull.id,node_id:pull.node_id,number:pull.number,repository:{full_name:'stranske/example'},pull_request:{url:'inert:native-pull'}}}};}
function pullFixture(f) {
 const pull={id:100,number:10,node_id:'PR_10',state:'open',draft:false,labels:[{name:'agent:codex'}],body:'Closes #9 copied marker grants nothing',head:{repo:{full_name:f.transport.repository}}},read=f.transport.read;
 const rows=[crossref(pull)];
 f.transport.read=async(resource,method,args)=>resource==='pulls'?pull:method==='listEventsForTimeline'?rows:read(resource,method,args);
 return {pull,rows};
}
test('historical native cross-reference preserves scope after closing text and current links are removed',async()=>{
 const f=fixture(),p=pullFixture(f);p.pull.body='No Closes text, marker or current closing link';
 assert.equal((await resolvePullCodingScope({transport:f.transport,pullNumber:10})).issue.node_id,f.issue.node_id);
 p.rows[0]=crossref({...p.pull,id:999,node_id:'PR_unrelated',number:99});
 assert.equal(await resolvePullCodingScope({transport:f.transport,pullNumber:10}),null);
});
test('incomplete, colliding or substituted historical native link evidence holds',async()=>{
 for(const mutate of [p=>{p.rows[0].source.issue.node_id='PR_copied';},p=>{p.rows[0].source.issue.repository.full_name='foreign/repo';},
  p=>{p.rows.push(clone(p.rows[0]));},p=>{delete p.rows[0].actor;},p=>{p.rows[0].source.issue.number=11;},p=>{p.rows.push({event:'unknown'});}]) {
  const f=fixture(),p=pullFixture(f);mutate(p);await assert.rejects(resolvePullCodingScope({transport:f.transport,pullNumber:10}));
 }
 const f=fixture();pullFixture(f);const read=f.transport.read;f.transport.read=async(r,m,a)=>m==='listEventsForTimeline'?null:read(r,m,a);
 await assert.rejects(resolvePullCodingScope({transport:f.transport,pullNumber:10}),/history incomplete/);
});
test('an otherwise coherent authenticated request cannot outlive its original deadline',async()=>{
 const f=fixture();f.request.original_operation.deadline='2020-01-01T00:00:00Z';
 const {request_sha256,...body}=f.request;f.request.request_sha256=digest(body);
 f.context.coding_budget=codingBudgetFromVariable('100000',f.request);f.context.decision.request_sha256=f.request.request_sha256;f.context.decision_proof.decision_sha256=digest(f.context.decision);
 for(const row of f.records){row.request_sha256=f.request.request_sha256;if(row.creation_response)row.creation_response.request_sha256=f.request.request_sha256;
  const {record_sha256,...record}=row;row.record_sha256=digest(record);}f.rebuild();
 await assert.rejects(resolveCodingScope({transport:f.transport,issueNumber:9}),/original deadline exhausted/);
});
test('two actual authenticated scopes historically linked to the same PR remain ambiguous',async()=>{
 const first=fixture(false),second=fixture(false,{number:11,run:701,sourceDigest:'9'.repeat(64)}),p=pullFixture(first);
 const original=first.transport,runTransport=id=>id===first.run?original:second.transport;
 const transport={...original,read:async(resource,method,args)=>resource==='pulls'?p.pull:method==='listEventsForTimeline'?[crossref(p.pull)]:
  args.issue_number===9?first.issue:second.issue,runs:async()=>[first.nativeRun,second.nativeRun],
  artifacts:async id=>runTransport(id).artifacts(id),canonicalRun:async(id,...args)=>runTransport(id).canonicalRun(id,...args),
  jobs:async(id,...args)=>runTransport(id).jobs(id,...args),load:async(selector,...args)=>runTransport(selector.run_id).load(selector,...args)};
 assert.equal((await resolveCodingScope({transport,issueNumber:9})).issue.node_id,'I_9');
 assert.equal((await resolveCodingScope({transport,issueNumber:11})).issue.node_id,'I_11');
 await assert.rejects(resolvePullCodingScope({transport,pullNumber:10}),/competing authenticated scopes/);
});
const fs=require('fs'),{execFileSync}=require('child_process');
const beltSurfaces=['.github/workflows/agents-72-codex-belt-worker.yml','templates/consumer-repo/.github/workflows/agents-72-codex-belt-worker.yml'];
function activationScript(surface=beltSurfaces[0]) {
 const text=fs.readFileSync(path.join(pythonRoot,surface),'utf8');
 const block=text.slice(text.indexOf('      - name: Post activation comment'));
 const lines=block.split('\n'),start=lines.findIndex(line=>line.trim()==='script: |')+1,body=[];
 for(const line of lines.slice(start)){if(line && !line.startsWith('            '))break;body.push(line.slice(12));}
 const values={'steps.pr.outputs.number':'10','steps.ctx.outputs.branch':'codex/issue-9','steps.mode.outputs.dry_run':'false',
  'steps.ledger_start.outputs.task_id':'task-1','steps.ledger_start.outputs.task_title':'Exact single task','steps.ctx.outputs.agent_key':'codex'};
 return body.join('\n').replace(/\$\{\{\s*(.*?)\s*\}\}/g,(_,key)=>{assert.ok(key in values,`known inert scalar ${key}`);return values[key];});
}
async function executeActivation({scope=null,budget='100000',update=false,calls=[],surface=beltSurfaces[0]}) {
 const comments=update?[{id:87,body:'<!-- agent-activation-marker --> old'}]:[];
 const issues=Object.fromEntries(['listComments','createComment','updateComment','deleteComment'].map(method=>[method,async args=>{calls.push([method,args]);return {data:{}};}]));
 const github={rest:{issues}},core={warning:message=>calls.push(['warning',message])};
 const retry={createTokenAwareRetry:async()=>({github,withRetry:fn=>fn(github),paginateWithRetry:async(fn,args)=>{calls.push(['listComments',args]);return comments;}})};
 const env=scope?{CORRECTION_CONTEXT_FILE:'/inert/correction.json',ISSUE_PR_CONTEXT_TOKEN_BUDGET:budget}:{};
 const inertRequire=name=>{
  if(name.includes('github-api-with-retry'))return retry;
  if(name==='fs')return {readFileSync:(filename,encoding)=>{assert.equal(filename,env.CORRECTION_CONTEXT_FILE);assert.equal(encoding,'utf8');return JSON.stringify(scope);}};
  if(name==='path')return {...path,resolve:filename=>path.join(pythonRoot,filename.replace(/^workflows-lib\/?/,''))};
  assert.equal(name,path.join(pythonRoot,'.github/scripts/verifier_correction_runtime'));return require(name);
 };
 const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
 await new AsyncFunction('require','github','core','context','process',activationScript(surface))(inertRequire,github,core,{repo:{owner:'stranske',repo:'example'}},{env});
 return calls;
}
const legacyActivation='<!-- agent-activation-marker -->\nAgent worker (codex) activated for branch `codex/issue-9`.\n\n@codex start\n**Focus on this task first:** `task-1` — Exact single task\n\nImplement **only** this task in your first commit.\nEnsure the code compiles and existing tests pass before moving on.\nThe keepalive loop will assign subsequent tasks after this one is complete.';
for(const surface of beltSurfaces)for(const existing of [false,true])test(`${surface}: actual Belt activation caller preserves ${existing?'incumbent':'new-issue'} scope in native ${existing?'update':'create'}Comment`,async()=>{
 const f=fixture(existing),scope=await resolveCodingScope({transport:f.transport,issueNumber:9});
 const calls=await executeActivation({scope,update:existing,surface}),writes=calls.filter(row=>['createComment','updateComment'].includes(row[0]));
 assert.equal(writes.length,1);const body=writes[0][1].body;
 assert.equal(body,fitCodingText({base:legacyActivation,scope,budget:'100000',pythonRoot}));
 assert.ok(body.includes(scope.original_issue_body));const data=JSON.parse(body.slice(body.indexOf('{')));
 assert.equal(data.finding_text,scope.finding_text);assert.deepEqual(data.required_tests,scope.required_tests);
});
for(const surface of beltSurfaces)test(`${surface}: actual Belt absent-overlay activation remains byte-identical legacy single-task prompt`,async()=>{
 const calls=await executeActivation({surface});assert.equal(calls.find(row=>row[0]==='createComment')[1].body,legacyActivation);
});
for(const surface of beltSurfaces)test(`${surface}: actual Belt activation over-budget or unconfigured scope aborts before comment inventory or trigger`,async()=>{
 const f=fixture(),scope=await resolveCodingScope({transport:f.transport,issueNumber:9});
 for(const budget of [null,'','1']){const calls=[];await assert.rejects(executeActivation({scope,budget,calls,surface}));assert.deepEqual(calls,[]);}
});
const {loadReviewedQualification}=require('../verifier_correction_collector');
const {recheckCodingAdmission}=require('../verifier_correction_runtime');
const {crossReferenceDigest}=require('../verifier_correction_host');
async function freshFixture(existing=false) {
 const original=clone(require('../../../tests/fixtures/verifier_correction/integration-original.json'));
 original.comments[0].body+='\n| Provider | Model | Verdict | Confidence |\n| anthropic | fixture | CONCERNS | 0.90 |\n';
 const f=fixture(existing,{commentBody:original.comments[0].body});
 const pull={...original.pull,id:77,node_id:'PR_7',labels:[]},source={...original.sourceIssue,labels:[]};
 f.issue.labels=[];f.issue.assignees=existing?[{login:'inert-owner'}]:[];
 const assigned={id:1001,event:'assigned',created_at:'2026-10-25T23:00:00Z',assignee:{login:'inert-owner'}},lineage=crossref(pull);
 const records=clone(require('../../../tests/fixtures/verifier_correction/role-reader-goldens.json').cases.find(row=>row.id==='qualified').records);
 records['fixture-qualified'].qualified_at=1577836800;records['fixture-qualified'].expires_at=1893456000;
 const authority=fs.readFileSync(path.join(pythonRoot,'tests/fixtures/verifier_correction/core-role-authority.txt'),'utf8');
 const state={records,ownerPermission:{permission:'write',user:{login:'inert-owner'}},permission:{permission:'write',user:{login:'inert-dispatcher'}},comment:original.comments[0],events:[assigned],timeline:[lineage],pull,source};
 const reviewedSource=()=>{
  const literal=execFileSync('python3',['-I','-c','import sys,json;print(repr(json.load(sys.stdin)))'],{input:JSON.stringify(state.records),encoding:'utf8'}).trim();
  return Buffer.from(authority.replace('ROLE_QUALIFICATIONS: dict[str, dict[str, Any]] = {}',`ROLE_QUALIFICATIONS: dict[str, dict[str, Any]] = ${literal}`));};
 const github={rest:{repos:{get:async args=>{assert.equal(`${args.owner}/${args.repo}`,'stranske/Orchestrator');return {data:{full_name:'stranske/Orchestrator',default_branch:'main'}};},
  getCommit:async args=>{assert.equal(args.ref,'main');return {data:{sha:'a'.repeat(40)}};},getContent:async args=>{assert.equal(args.path,'src/closer_role_qualification.py');assert.equal(args.ref,'a'.repeat(40));const bytes=reviewedSource();return {data:{type:'file',encoding:'base64',content:bytes.toString('base64'),sha:createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex')}};}}}};
 const clock=()=>new Date('2026-10-26T00:00:00Z'),profile={id:'synthetic-ordinary',role:'closer_interpret'};
 const qualification=await loadReviewedQualification({github,profile,clock});assert.equal(qualification.status,'qualified');
 f.context.qualification=qualification;f.context.decision.profile={...profile,qualification_ref:qualification.qualification_ref,qualification_sha256:qualification.qualification_sha256};
 if(existing)f.request.incumbent.lineage_ref=`github:stranske/example/issues/9/timeline-sha256/${crossReferenceDigest(lineage,pull)}`;
 const {request_sha256,...requestBody}=f.request;f.request.request_sha256=digest(requestBody);f.context.decision.request_sha256=f.request.request_sha256;
 f.context.coding_budget=codingBudgetFromVariable('100000',f.request);f.context.decision_proof={status:'authenticated',decision_sha256:digest(f.context.decision),profile_identity_sha256:qualification.profile_identity_sha256};f.context.dispatch_actor='inert-dispatcher';
 for(const row of f.records){row.request_sha256=f.request.request_sha256;if(row.creation_response)row.creation_response.request_sha256=f.request.request_sha256;const {record_sha256,...body}=row;row.record_sha256=digest(body);}f.rebuild();
 const read=f.transport.read;f.transport.read=async(resource,method,args)=>{
  if(resource==='pulls')return state.pull;if(resource==='repos')return args.username==='inert-owner'?state.ownerPermission:state.permission;
  if(method==='getComment')return state.comment;if(method==='listEvents')return state.events;if(method==='listEventsForTimeline')return state.timeline;
  if(args.issue_number===1)return state.source;return read(resource,method,args);
 };
 const scope=await resolveCodingScope({transport:f.transport,issueNumber:9});
 const recheck=()=>recheckCodingAdmission({github,transport:f.transport,scope,pythonRoot,clock});
 return {...f,scope,state,recheck,github,clock};
}
for(const existing of [false,true])test(`actual fixed reviewed-source reader permits fresh inert ${existing?'incumbent-native-assignment':'no-incumbent'} admission`,async()=>{
 const f=await freshFixture(existing);assert.equal((await f.recheck()).status,'admitted');
});
test('qualification revocation or reviewed empty production registry cannot inherit old admission',async()=>{
 for(const mutate of [f=>{f.state.records={};},f=>{f.state.records['fixture-qualified'].status='revoked';}]) {
  const f=await freshFixture();mutate(f);await assert.rejects(f.recheck(),/qualification unavailable or revoked/);
 }
});
test('fresh native issue/source holds, write permission loss and ownership changes stop coding after prior admission',async()=>{
 for(const mutate of [f=>f.issue.labels.push({name:'needs-human'}),f=>f.issue.labels.push({name:'agents:auto-pilot-pause'}),
  f=>f.state.source.labels.push({name:'needs-human'}),f=>f.state.pull.labels.push({name:'agents:paused'}),
  f=>{f.state.permission.permission='read';},f=>{f.state.permission.user.login='copied-actor';},
  f=>{f.issue.assignees=[{login:'unproven-owner'}];},f=>{f.state.source.body+='changed';},f=>{f.state.pull.head.sha='9'.repeat(40);}]) {
  const f=await freshFixture();mutate(f);await assert.rejects(f.recheck());
 }
});
test('existing owner requires exact latest native assignment and source PR lineage',async()=>{
 for(const mutate of [f=>{f.state.events.push({...f.state.events[0],id:1002,event:'unassigned',created_at:'2026-10-26T00:03:00Z'});},
  f=>{f.state.ownerPermission.permission='read';},f=>{f.state.timeline[0].source.issue.id=999;},f=>{f.state.events[0].created_at=undefined;},f=>{f.issue.assignees=[];}]) {
  const f=await freshFixture(true);mutate(f);await assert.rejects(f.recheck());
 }
});

test('recheck binds immutable original issue and body to real retained ledger, not mutable sidecar identity',async()=>{
 for(const existing of [false,true])for(const mutate of [f=>{f.scope.issue.node_id='I_substituted';},
  f=>{f.scope.original_issue_body='Copied body';f.scope.issue.body_sha256=sha(f.scope.original_issue_body);},
  f=>{f.scope.issue.number='99';}]) {
  const f=await freshFixture(existing);mutate(f);await assert.rejects(f.recheck(),/exact authenticated original issue/);
 }
});

test('trusted variable parser freezes exact private request/repository policy without a capacity claim',()=>{
 const f=fixture(),budget=codingBudgetFromVariable('1000',f.request);
 assert.deepEqual(validateCodingBudget(budget,f.request),{schema:'closer-correction-coding-budget/v1',source:'github-actions-vars/ISSUE_PR_CONTEXT_TOKEN_BUDGET',
  repository:f.request.target.repository,request_sha256:f.request.request_sha256,max_estimated_input_tokens:1000,native_capacity_attested:false});
 for(const raw of [undefined,null,''])assert.equal(codingBudgetFromVariable(raw,f.request),null);
 for(const raw of ['0','01','-1','1.0','1e3',' 100',true,100,'9007199254740992'])assert.throws(()=>codingBudgetFromVariable(raw,f.request));
 assert.equal(minimumCodingBudget([],f.request),null);assert.equal(minimumCodingBudget([budget,null],f.request),null);
 assert.equal(minimumCodingBudget([budget,codingBudgetFromVariable('2000',f.request)],f.request).max_estimated_input_tokens,1000);
 for(const mutation of [{repository:'foreign/repo'},{request_sha256:'0'.repeat(64)},{native_capacity_attested:true},{source:'caller'},{max_estimated_input_tokens:1.5},{extra:true}])
  assert.throws(()=>validateCodingBudget({...budget,...mutation},f.request));
});
function withBudgetAlias(f,value) {
 const original=f.transport,alias=clone(f.context);alias.collector.run_id=701;alias.coding_budget=value;
 const {context_sha256,...body}=alias;alias.context_sha256=digest(body);const bytes=Buffer.from(JSON.stringify(alias)),name=artifactName('admitted',701,1);
 const proof={repository:original.repository,run_id:701,run_attempt:1,artifact_id:9001,archive_sha256:sha(bytes),member_sha256:sha(bytes),run_created_at:'2026-10-26T01:00:00Z'};
 return {...original,runs:async(...args)=>[...await original.runs(...args),{id:701,run_attempt:1,status:'completed'}],
  artifacts:async id=>id===701?[{id:9001,name,expired:false}]:original.artifacts(id),
  canonicalRun:async(id,...args)=>id===701?{head_sha:'a'.repeat(40)}:original.canonicalRun(id,...args),
  jobs:async id=>id===701?[{name:SPECS.ledger.job,run_id:701,run_attempt:1,head_sha:'a'.repeat(40),status:'completed',conclusion:'skipped'}]:original.jobs(id),
  load:async(selector,...args)=>selector.run_id===701?{bytes,proof}:original.load(selector,...args)};
}
test('complete authenticated history applies minimum original/alias ceiling and a missing alias never defaults',async()=>{
 for(const [alias,expected] of [['200000',100000],['100',100],[null,null]]) {
  const f=fixture(),transport=withBudgetAlias(f,alias===null?null:codingBudgetFromVariable(alias,f.request));
  const scope=await resolveCodingScope({transport,issueNumber:9});assert.equal(scope.coding_budget?.max_estimated_input_tokens ?? null,expected);
  if(expected===100000)assert.ok(fitCodingText({base,scope,budget:'200000',pythonRoot}).startsWith(base));
  else assert.throws(()=>fitCodingText({base,scope,budget:'200000',pythonRoot}));
 }
});
test('fresh final admission independently rejects raised sidecar cap or changed original history cap',async()=>{
 const f=await freshFixture();f.scope.coding_budget.max_estimated_input_tokens=200000;
 await assert.rejects(f.recheck(),/coding budget changed or unavailable/);
 const lower=await freshFixture();lower.context.coding_budget=codingBudgetFromVariable('500',lower.request);lower.rebuild();
 await assert.rejects(lower.recheck(),/coding budget changed or unavailable/);
});

const {codingPolicyObservation}=require('../verifier_correction_runtime');
test('coding policy observation records exact existing configuration and minimum ceiling without execution authority',async()=>{
 const f=await freshFixture(),configuration={model:'fixture-selected',candidates:['fixture-selected','fixture-fallback'],reasoning_effort:'xhigh',sandbox:'read-only',extra_arguments:'[]'};
 await f.recheck();const before=clone(configuration),observation=codingPolicyObservation({scope:f.scope,currentBudget:'200000',configuration,current:{run_id:900,run_attempt:2}});
 assert.deepEqual(configuration,before);assert.equal(observation.selected_estimated_input_tokens,100000);
 assert.deepEqual(observation.requested_configuration,{agent:'codex',profile_id:null,model:'fixture-selected',candidates:configuration.candidates,reasoning_effort:'xhigh',sandbox:'read-only',extra_arguments:'none'});
 assert.equal(observation.request_sha256,f.scope.request_sha256);assert.equal(observation.seed_effect_key,f.scope.seed_effect_key);
 for(const flag of ['native_capacity_attested','effective_configuration_attested','provider_execution_attested','act_authorized','source_closure_authorized'])assert.equal(observation[flag],false);
 const {content_sha256,...body}=observation;assert.equal(content_sha256,digest(body));
 assert.equal(codingPolicyObservation({scope:f.scope,currentBudget:'500',configuration,current:{run_id:900,run_attempt:2}}).selected_estimated_input_tokens,500);
 for(const extra_arguments of ['--model different','["--sandbox", "danger-full-access"]','[ ]'])
  assert.throws(()=>codingPolicyObservation({scope:f.scope,currentBudget:'200000',configuration:{...configuration,extra_arguments},current:{run_id:900,run_attempt:2}}),/unbound extra arguments/);
});
function providerPreflightScript() {
 const text=fs.readFileSync(path.join(pythonRoot,'.github/workflows/reusable-codex-run.yml'),'utf8'),section=text.slice(text.indexOf('      - name: Recheck mandatory correction admission before coding'));
 const lines=section.split('\n'),at=lines.findIndex(row=>row.trim()==='script: |'),code=[];
 for(const row of lines.slice(at+1)){if(row && !row.startsWith('            '))break;code.push(row.slice(12));}
 return code.join('\n');
}
async function runProviderPreflight(f,{extra='',budget='200000',files={}}={}) {
 const env={RUNNER_TEMP:'/inert/runner',GITHUB_RUN_ATTEMPT:'2',CORRECTION_CONTEXT_FILE:'/inert/coding-scope.json',ISSUE_PR_CONTEXT_TOKEN_BUDGET:budget,
  CORRECTION_REQUESTED_MODEL:'fixture-selected',CORRECTION_MODEL_CANDIDATES:'fixture-selected fixture-fallback',CORRECTION_REQUESTED_EFFORT:'xhigh',CORRECTION_REQUESTED_SANDBOX:'read-only',CORRECTION_EXTRA_ARGUMENTS:extra};
 const inertRequire=name=>{
  if(name==='path')return {...path,join:(...parts)=>parts[0]==='/inert/runner' && parts[1]==='correction-intake'?pythonRoot:path.join(...parts)};
  if(name==='fs')return {readFileSync:filename=>{assert.equal(filename,env.CORRECTION_CONTEXT_FILE);return JSON.stringify(f.scope);},writeFileSync:(filename,body)=>{files[filename]=body;}};
  if(name.endsWith('/verifier_correction_artifacts'))return {createArtifactTransport:async()=>f.transport};
  assert.equal(name,path.join(pythonRoot,'.github/scripts/verifier_correction_runtime'));return require(name);
 };
 const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
 await new AsyncFunction('require','github','core','context','process',providerPreflightScript())(inertRequire,f.github,{},
  {runId:900,repo:{owner:'stranske',repo:'example'}},{env});return files;
}
test('actual authored pre-provider script freshly authenticates original scope and captures requested policy without model calls',async()=>{
 const f=await freshFixture();f.calls.splice(0);const files=await runProviderPreflight(f),policy=JSON.parse(files['/inert/runner/codex-correction-policy.json']);
 assert.ok(f.calls.some(row=>row[0]==='load' && row[1]==='admitted'));assert.ok(f.calls.some(row=>row[0]==='load' && row[1]==='ledger'));
 assert.deepEqual(Object.keys(files),['/inert/runner/codex-correction-policy.json']);assert.equal(files[path.join(pythonRoot,'codex-correction-policy.json')],undefined);
 assert.equal(policy.repository,f.scope.admitted_selector.repository);assert.equal(policy.request_sha256,f.scope.request_sha256);
 assert.equal(policy.selected_estimated_input_tokens,100000);assert.equal(policy.run_id,900);assert.equal(policy.run_attempt,2);
 assert.equal(policy.requested_configuration.model,'fixture-selected');assert.equal(policy.requested_configuration.reasoning_effort,'xhigh');assert.equal(policy.requested_configuration.sandbox,'read-only');
 for(const flag of ['native_capacity_attested','effective_configuration_attested','provider_execution_attested','act_authorized','source_closure_authorized'])assert.equal(policy[flag],false);
});
test('actual authored pre-provider script holds unknown CLI overrides and substituted admission before any output/provider',async()=>{
 const f=await freshFixture(),files={};await assert.rejects(runProviderPreflight(f,{extra:'--model unbound-model',files}),/unbound extra arguments/);assert.deepEqual(files,{});
 f.scope.admitted_selector.artifact_id=999999;await assert.rejects(runProviderPreflight(f,{files}));assert.deepEqual(files,{});
});
