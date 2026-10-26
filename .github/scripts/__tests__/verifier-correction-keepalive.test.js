'use strict';
// Read-only native transport fixtures; every artifact/API response is synthetic.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),{createHash}=require('crypto');
const {digest}=require('../verification_event');
const {seedForRequest,effectKey,issueIdentity,sourceScopeDigest}=require('../verifier_correction_effects');
const {artifactName,SPECS}=require('../verifier_correction_artifacts');
const {codingBudgetFromVariable}=require('../verifier_correction_consumer');
const {guardCorrectionKeepalive}=require('../verifier_correction_runtime');
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
function keepaliveFixture(existing=false) {
 const f=fixture(existing),context={repo:{owner:'stranske',repo:'example'},runId:900,runAttempt:1,eventName:'pull_request'};
 const fresh={id:100,number:10,node_id:'PR_10',state:'open',draft:false,head:{sha:'d'.repeat(40),ref:'codex/issue-9',repo:{full_name:'stranske/example'}},base:{ref:'main'},
  labels:[{name:'agent:codex'}],body:'## Tasks\n- [ ] Implement exact correction\n## Acceptance Criteria\n- [ ] Preserve required tests'};
 const native={fresh,events:[{event:'cross-referenced',actor:{id:123},created_at:'2026-10-26T00:01:00Z',source:{type:'issue',issue:{id:fresh.id,node_id:fresh.node_id,number:10,
  repository:{full_name:'stranske/example'},pull_request:{url:'inert:native-pr'}}}}]},read=f.transport.read;
 f.transport.read=async(resource,method,args)=>resource==='pulls'?native.fresh:method==='listEventsForTimeline'?native.events:read(resource,method,args);
 const pr=clone(fresh);context.payload={pull_request:pr};
 const guard=(agentKey='codex',extra={})=>guardCorrectionKeepalive({github:{},context,pr,agentKey,transport:f.transport,...extra});
 return {...f,native,pr,guard,hostContext:context};
}
for(const existing of [false,true])test(`native retained ${existing?'existing':'created'} correction scope reaches only the selected supported Codex runner`,async()=>{
 const f=keepaliveFixture(existing),scope=await f.guard();assert.equal(scope.request_sha256,f.request.request_sha256);assert.deepEqual(scope.required_tests,f.request.required_tests);
 assert.equal(scope.issue.node_id,'I_9');assert.equal(scope.original_issue_body,f.issue.body);
 assert.ok(f.calls.some(row=>row[0]==='load' && row[1]==='admitted'));assert.ok(f.calls.some(row=>row[0]==='load' && row[1]==='ledger'));
});
test('positively empty correction history preserves ordinary unsupported-agent routing as null',async()=>{
 const f=keepaliveFixture();f.transport.runs=async()=>[];assert.equal(await f.guard('claude'),null);
});
test('missing or ambiguous native history cannot masquerade as ordinary scope',async()=>{
 for(const mutate of [f=>{f.transport.runs=async()=>{throw Error('history unavailable');};},f=>{f.metadata.splice(0,1);},
  f=>{f.native.events.push(clone(f.native.events[0]));},f=>{f.native.events=null;},f=>{f.metadata[0].expired=true;}]) {
  const f=keepaliveFixture();mutate(f);await assert.rejects(f.guard());
 }
});
test('native PR identity, exact head and repository substitution cannot retain old typed admission',async()=>{
 for(const mutate of [f=>{f.pr.id=999;},f=>{f.pr.node_id='PR_copied';},f=>{f.pr.head.sha='e'.repeat(40);},
  f=>{f.native.fresh.head.repo.full_name='foreign/repo';}]) {
  const f=keepaliveFixture();mutate(f);await assert.rejects(f.guard(),/Owned UNKNOWN/);
 }
});
test('typed routing cannot auto-delegate or select unsupported/multiple/overridden runners',async()=>{
 for(const [agentKey,labels] of [['claude',['agent:claude']],['auto',['agent:auto']],['codex',[]],['codex',['agent:codex','agent:claude']],
  ['codex',['agent:codex','runner:claude']],['codex',['agent:auto','agent:codex']]]) {
  const f=keepaliveFixture();f.native.fresh.labels=labels.map(name=>({name}));await assert.rejects(f.guard(agentKey),/Owned UNKNOWN/);
 }
 const f=keepaliveFixture();f.native.fresh.labels.push({name:'runner:codex'});assert.ok(await f.guard());
});
test('selected registry runner must retain actual authenticated coding intake, without fallback',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'inert-correction-runner-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const registryPath=path.join(root,'registry.yml');fs.writeFileSync(registryPath,fs.readFileSync(path.join(pythonRoot,'.github/agents/registry.yml'),'utf8')
  .replace('runner_workflow: .github/workflows/reusable-codex-run.yml','runner_workflow: .github/workflows/reusable-claude-run.yml'));
 await assert.rejects(keepaliveFixture().guard('codex',{registryPath}),/lacks authenticated correction intake/);
});
test('a fresh native human or pause stop remains held even if initially cached labels were clear',async()=>{
 for(const name of ['needs-human','agents:paused','agents:pause','agents:auto-pilot-pause','agents:auto-pilot-failed','agents:max-runs:0']) {
  const f=keepaliveFixture();f.native.fresh.labels.push({name});await assert.rejects(f.guard(),/hold|held|pause|human|stop/i);
 }
});
test('missing or replaced native IDs cannot erase scope by making the historical join appear unrelated',async()=>{
 for(const mutate of [f=>{delete f.native.fresh.id;},f=>{delete f.native.fresh.node_id;},f=>{f.native.fresh.id=999;},f=>{f.native.fresh.node_id='PR_replaced';}]) {
  const f=keepaliveFixture();mutate(f);f.native.events=[];
  await assert.rejects(f.guard(),/identity\/head changed or unavailable/);
 }
});
function evaluatedFixture(f,{onGuard=null,verifier=''}={}) {
 const calls={guards:[],delegation:[],effects:[]},state={},cache={buildPrCacheKey:()=>'',getOrSet:({fetcher})=>fetcher(),emitMetrics(){},invalidateForWebhook(){}};
 const github={rest:{pulls:{get:async()=>({data:f.pr})},actions:{listWorkflowRuns:async()=>({data:{workflow_runs:[{id:44,head_sha:f.pr.head.sha,conclusion:'success'}]}})},
  rateLimit:{get:async()=>({data:{rate:{remaining:5000,limit:5000,reset:4102444800},resources:{core:{remaining:5000,limit:5000,reset:4102444800}}}})},
  issues:{listComments:async()=>({data:[]}),addLabels:async args=>{calls.effects.push(args);throw Error('no mutation allowed');},removeLabel:async args=>{calls.effects.push(args);throw Error('no mutation allowed');}}},
  paginate:async(fn,args)=>(await fn(args)).data};
 const module={exports:{}},baseState=require('../keepalive_state');
 const inertRequire=name=>{
  if(name==='./verifier_correction_runtime')return {guardCorrectionKeepalive:async options=>{calls.guards.push(options.agentKey);onGuard?.(calls.guards.length,f);
   return guardCorrectionKeepalive({...options,transport:f.transport});}};
  if(name==='./github-rate-limited-wrapper')return {ensureRateLimitWrapped:async({github})=>github};
  if(name==='./github-api-cache-client')return {getGithubApiCache:()=>cache};
  if(name==='./keepalive_state')return {...baseState,loadKeepaliveState:async()=>({state,commentId:0})};
  if(name==='./token_load_balancer')return null;
  if(name==='./conflict_detector')return {detectConflicts:async()=>({hasConflict:false,files:[]})};
  if(name==='./agent_delegation_policy.js')return {...require('../agent_delegation_policy'),recentInstallFailures:()=>new Set(['codex']),
   decideNextAgent:async args=>{calls.delegation.push(args);throw Error('typed correction must not delegate');}};
  return name.startsWith('./')?require(path.join(__dirname,'..',name)):require(name);
 };
 vm.runInNewContext(fs.readFileSync(path.join(pythonRoot,'.github/scripts/keepalive_loop.js'),'utf8'),{module,exports:module.exports,require:inertRequire,__dirname:path.join(pythonRoot,'.github/scripts'),
  process:{...process,env:{...process.env,CLAUDE_CODE_OAUTH_TOKEN:'inert-no-provider',CODEX_AUTH_JSON:'inert-no-provider'}},Buffer,console,setTimeout,clearTimeout,URL});
 if(verifier){f.pr.body='## Tasks\n- [x] Implementation complete\n## Acceptance Criteria\n- [x] Verify exact correction\n<!-- keepalive-config:start -->\n'+JSON.stringify({keepalive_enabled:true,verifier_agent:verifier})+'\n<!-- keepalive-config:end -->';}
 return {calls,evaluate:()=>module.exports.evaluateKeepaliveLoop({github,context:f.hostContext,core:{info(){},warning(){},debug(){},setOutput(){}}})};
}
test('actual keepalive evaluation checks native scope twice and preserves supported run without automatic delegation',async()=>{
 const f=keepaliveFixture(),e=evaluatedFixture(f),result=await e.evaluate();
 assert.equal(result.action,'run');assert.equal(result.agentType,'codex');assert.deepEqual(e.calls.guards,['codex','codex']);
 assert.deepEqual(e.calls.delegation,[]);assert.deepEqual(e.calls.effects,[]);
});
test('actual final keepalive guard catches newly relabeled ownership before returned execution',async()=>{
 const f=keepaliveFixture(),e=evaluatedFixture(f,{onGuard:count=>{if(count===2)f.native.fresh.labels=[{name:'agent:claude'}];}});
 await assert.rejects(e.evaluate(),/fresh incumbent routing differs/);assert.deepEqual(e.calls.guards,['codex','codex']);assert.deepEqual(e.calls.delegation,[]);assert.deepEqual(e.calls.effects,[]);
});
test('actual independent verifier selection cannot substitute an unsupported correction runner',async()=>{
 const f=keepaliveFixture(),e=evaluatedFixture(f,{verifier:'claude'});
 await assert.rejects(e.evaluate(),/Owned UNKNOWN/);assert.deepEqual(e.calls.guards,['codex','claude']);assert.deepEqual(e.calls.delegation,[]);assert.deepEqual(e.calls.effects,[]);
});
test('native typed coding PR must positively remain open, non-draft and have complete hold labels',async()=>{
 for(const mutate of [f=>{f.native.fresh.state='closed';},f=>{f.native.fresh.draft=true;},f=>{delete f.native.fresh.draft;},
  f=>{delete f.native.fresh.labels;},f=>{f.native.fresh.labels.push({});}]) {
  const f=keepaliveFixture();mutate(f);await assert.rejects(f.guard(),/Owned UNKNOWN/);
 }
});
test('actual final evaluation guard preserves a newly added human hold before returning runnable work',async()=>{
 const f=keepaliveFixture(),e=evaluatedFixture(f,{onGuard:count=>{if(count===2)f.native.fresh.labels.push({name:'needs-human'});}});
 await assert.rejects(e.evaluate(),/current operator hold/);assert.deepEqual(e.calls.guards,['codex','codex']);assert.deepEqual(e.calls.effects,[]);
});
test('authored final evaluation guard covers every existing execution action and review after final routing',()=>{
 const source=fs.readFileSync(path.join(pythonRoot,'.github/scripts/keepalive_loop.js'),'utf8');
 const early=source.indexOf('const correctionScope = await guardCorrectionKeepalive'),delegation=source.indexOf("if (!correctionScope && (agentRoutingMode === 'auto' || recoveringInstallFailure))"),
 final=source.indexOf('await guardCorrectionKeepalive({ github, context, pr, agentKey: resolvedAgentType })');
 assert.ok(early>0 && early<delegation);assert.ok(final>source.indexOf('const resolvedAgentType ='));
 assert.match(source,/AGENT_EXECUTION_ACTIONS = new Set\(\['run', 'fix', 'conflict'\]\)/);
 assert.match(source,/if \(AGENT_EXECUTION_ACTIONS\.has\(action\) \|\| action === 'review'\)/);
 assert.ok(final<source.indexOf('    return {\n      prNumber,\n      prRef: pr.head.ref',final));
});
