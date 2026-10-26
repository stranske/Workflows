'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {createHash}=require('crypto');
const {digest}=require('../verification_event');
const {seedForRequest,sourceScopeDigest,effectKey,attemptEffect,createCorrectionEffectConsumer}=require('../verifier_correction_effects');
const frozen=require('../../../tests/fixtures/verifier_correction/request.json');
const consumer={run_id:'900',run_attempt:'1'};
const sha=value=>createHash('sha256').update(value).digest('hex');
function seal(value) {const {request_sha256,...payload}=value;return {...payload,request_sha256:digest(payload)};}
function fixture() {
  const request=structuredClone(frozen),key=effectKey(seedForRequest(request));
  const calls=[],rows=[];
  const ledger={async read(selected){calls.push(['read',selected]);return {revision:rows.length,records:structuredClone(rows)};},
    async append({effect_key,expected_revision,record}) {calls.push(['intent',effect_key,expected_revision]);
      if (rows.length !== expected_revision) throw Error('conflict');rows.push(structuredClone(record));return structuredClone(record);}};
  const sourceIssue={number:1,node_id:'I_1',body:'issue 1',labels:[]};
  const incumbentIssue={number:8,node_id:'I_8',body:'issue 8',state:'open',assignees:[{login:'owner'}],labels:[]};
  const facts={pull:{merged:true,head:{sha:request.target.head_sha},base:{sha:request.target.base_sha,repo:{full_name:request.target.repository}},merge_commit_sha:request.target.merge_sha,labels:[]},
    sourceIssue,incumbentIssue,chainDepth:0,verdictPolicy:'follow-up',assignmentRef:request.incumbent.assignment_ref,
    lineageRef:request.incumbent.lineage_ref,dispatchActorPermission:'write',workInventory:{complete:true,continuations:[],openPullRequests:[],assignments:[],retainedEffects:[]}};
  facts.ownership={schema:'closer-correction-ownership/v1',kind:'existing',seed_effect_key:key,source_scope_digest:sourceScopeDigest(seedForRequest(request)),observed_at:'2026-10-26T00:00:00Z',evidence_refs:['inert:complete-github-and-ledger-fixture'],incumbent:request.incumbent};
  const state={request,seed:seedForRequest(request),facts,observed:null,dispatchFailure:false};
  const deps={authenticate:async selector=>{calls.push(['authenticate',selector]);return {request:state.request,seed:state.seed,required_tests:request.required_tests};},
    collectFreshFacts:async()=>{calls.push(['fresh']);return facts;},ledger,
    reconcile:async ({effect_key})=>{calls.push(['reconcile',effect_key]);return state.observed;},
    github:{rest:{actions:{createWorkflowDispatch:async args=>{calls.push(['dispatch',args]);if(state.dispatchFailure)throw Error('lost response');return {status:204};}}}},
    defaultBranch:'main',clock:()=>new Date('2026-10-26T00:00:00Z')};
  const consume=(selector='inert-authenticated-selector')=>createCorrectionEffectConsumer(deps)(selector,consumer);
  return {request,key,calls,rows,ledger,state,deps,consume};
}
const dispatches=f=>f.calls.filter(row=>row[0]==='dispatch');
const acceptedObservation=request=>({request,issue:request.incumbent.issue,continuation:{workflow:'agents-auto-pilot.yml',run_id:'901',run_attempt:'2',request_sha256:request.request_sha256,issue_node_id:request.incumbent.issue.node_id}});
function checkReceipt(result) {
  const {receipt_sha256,...payload}=result;assert.equal(receipt_sha256,digest(payload));
  assert.equal(result.retry_authorized,false);assert.equal(result.act_authorized,false);assert.equal(result.source_closure_authorized,false);
}

test('valid authenticated request dispatches existing issue to optimize once, HTTP204 stays unknown',async()=>{
  const f=fixture(),result=await f.consume();checkReceipt(result);
  assert.equal(result.effect_state,'outcome_unknown');assert.equal(dispatches(f).length,1);
  const args=dispatches(f)[0][1];assert.equal(args.workflow_id,'agents-auto-pilot.yml');assert.equal(args.inputs.issue_number,'8');assert.equal(args.inputs.force_step,'optimize');
  assert.equal(args.inputs.correction_request_sha256,f.request.request_sha256);assert.equal(args.inputs.correction_effect_key,f.key);
  assert.ok(f.calls.findIndex(row=>row[0]==='intent') < f.calls.findIndex(row=>row[0]==='dispatch'));
  const again=await f.consume();assert.equal(again.effect_state,'outcome_unknown');assert.equal(dispatches(f).length,1);
});
test('only authenticated actual started continuation produces accepted receipt and exact duplicate reuses it',async()=>{
  const f=fixture();f.state.observed=acceptedObservation(f.request);
  const result=await f.consume();checkReceipt(result);assert.equal(result.effect_state,'accepted_with_exact_issue_and_actual_autopilot_run_attempt');
  assert.equal(result.continuation.run_id,'901');assert.equal(result.continuation.run_attempt,'2');
  const duplicate=await f.consume();checkReceipt(duplicate);assert.equal(duplicate.effect_state,result.effect_state);assert.equal(dispatches(f).length,1);
});
test('lost dispatch response is reconciled to actual run, otherwise remains unknown without retry',async()=>{
  for(const started of [true,false]) {
    const f=fixture();f.state.dispatchFailure=true;if(started)f.state.observed=acceptedObservation(f.request);
    const result=await f.consume();assert.equal(result.effect_state,started?'accepted_with_exact_issue_and_actual_autopilot_run_attempt':'outcome_unknown');
    await f.consume();assert.equal(dispatches(f).length,1);
  }
});
test('ledger/intent failures never invoke an effect; uncertain durable intent remains fenced',async()=>{
  for(const fault of ['read','before_append','after_append','bad_ack']) {
    const f=fixture();
    if(fault==='read')f.ledger.read=async()=>{throw Error('unavailable');};
    else {const append=f.ledger.append;f.ledger.append=async args=>{
      if(fault==='before_append')throw Error('unavailable');const result=await append(args);
      if(fault==='after_append')throw Error('lost ack');return {...result,record_sha256:'a'.repeat(64)};
    };}
    const result=await f.consume();checkReceipt(result);assert.equal(result.effect_state,'outcome_unknown');assert.equal(dispatches(f).length,0);
    if(f.rows.length){f.ledger.append=async()=>{throw Error('must not repeat');};await f.consume();assert.equal(dispatches(f).length,0);}
  }
});
test('deadline, chain, current assignment, source, permission and held-lane gates refuse before intent',async()=>{
  for(const change of [f=>{f.state.request=seal({...f.request,original_operation:{...f.request.original_operation,deadline:'2026-01-01T00:00:00Z'}});},
    f=>{f.state.facts.chainDepth=2;},f=>{f.state.facts.incumbentIssue.assignees=[];},f=>{f.state.facts.sourceIssue.body='changed';},
    f=>{f.state.facts.dispatchActorPermission='read';},f=>{f.state.facts.pull.labels=['needs-human'];},
    f=>{f.state.facts.assignmentRef='different';},f=>{f.state.facts.lineageRef='unproven';}]) {
    const f=fixture();change(f);const result=await f.consume();checkReceipt(result);
    assert.equal(result.effect_state,'confirmed_not_started');assert.equal(f.rows.length,0);assert.equal(dispatches(f).length,0);
  }
});
test('caller relabeling request/hold/run/idempotency cannot create a new writer for same trusted seed',async()=>{
  const f=fixture();await f.consume();
  f.state.request=seal({...f.request,original_operation:{...f.request.original_operation,hold_id:'new-hold',run_id:'new-run',operation_id:'new-op',idempotency_key:'new-key'}});
  assert.equal(effectKey(seedForRequest(f.state.request)),f.key);
  const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(dispatches(f).length,1);
});
test('different caller finding/test scope cannot pass the authenticated original seed',async()=>{
  const f=fixture(),changed=structuredClone(f.request);changed.required_tests[0].specification='unapproved requirement';f.state.request=seal(changed);
  await assert.rejects(f.consume(),/authenticated source-bound required-test decision/);assert.equal(dispatches(f).length,0);
});
test('concurrent consumers cannot pass the same durable intent revision twice',async()=>{
  const f=fixture();const results=await Promise.all([f.consume(),f.consume()]);
  assert.equal(dispatches(f).length,1);assert.equal(f.rows.length,1);for(const result of results)assert.equal(result.effect_state,'outcome_unknown');
});
test('prior uncertainty is not converted to absence by later expiry or needs-human',async()=>{
  const f=fixture();await f.consume();f.state.facts.pull.labels=['needs-human'];
  f.state.request=seal({...f.request,original_operation:{...f.request.original_operation,deadline:'2026-01-01T00:00:00Z'}});
  const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(dispatches(f).length,1);
});
test('active incumbent stays owned; no parallel dispatch and no caller-null no-incumbent bypass',async()=>{
  const f=fixture();f.state.facts.workInventory.continuations=[{run_id:'existing'}];const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(dispatches(f).length,0);
  f.state.request=seal({...f.request,incumbent:null});await assert.rejects(f.consume(),/incumbent/);assert.equal(dispatches(f).length,0);
});
test('inert create kernel fences timeout/crash and retains exact original intent, without an automatic retry',async()=>{
  for(const failure of ['lost_response','received_response']) {
    const f=fixture();let creates=0;
    const outcome=await attemptEffect({ledger:f.ledger,snapshot:{revision:0,records:[]},key:f.key,request:f.request,consumer,phase:'issue_creation',invoke:async()=>{
      creates++;if(failure==='lost_response')throw Error('server created issue then response lost');return {data:{number:9,node_id:'I_9'}};
    }});
    assert.equal(outcome.state,'outcome_unknown');assert.equal(creates,1);assert.equal(f.rows[0].phase,'issue_creation');
    // Existing intent makes the public consumer reconcile, never create/dispatch.
    const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(creates,1);assert.equal(dispatches(f).length,0);
  }
});
test('tampered authenticated ledger and mismatched started receipt are not accepted',async()=>{
  const f=fixture();await f.consume();f.rows[0].request_sha256='f'.repeat(64);
  assert.equal((await f.consume()).effect_state,'outcome_unknown');assert.equal(dispatches(f).length,1);
  const other=fixture();other.state.observed=acceptedObservation(other.request);other.state.observed.continuation.issue_node_id='wrong';
  assert.equal((await other.consume()).effect_state,'outcome_unknown');assert.equal(dispatches(other).length,1);
});

test('uncertain creation reconciles only one exact original issue; positive issue never means autopilot accepted',async()=>{
  const {canonical}=require('../verification_event');
  const {reconcileIssueCreation}=require('../verifier_correction_effects');
  const f=fixture();await attemptEffect({ledger:f.ledger,snapshot:{revision:0,records:[]},key:f.key,request:f.request,consumer,phase:'issue_creation',invoke:async()=>{throw Error('lost create response');}});
  const intent=f.rows[0];
  const marker=`<!-- closer-correction-effect/v1 ${canonical({effect_key:f.key,request_sha256:f.request.request_sha256,consumer})} -->`;
  const actual={number:9,node_id:'I_9',body:`Exact original scoped correction\n${marker}`};
  const result=await reconcileIssueCreation({request:f.request,intent,observe:async()=>[actual]});
  assert.equal(result.issue.node_id,'I_9');assert.equal(result.effect_state,'outcome_unknown');assert.equal(result.retry_authorized,false);
  for(const rows of [[],[actual,actual],[{...actual,body:'PR #7 follow-up title/body match only'}],[{...actual,body:actual.body.replace(f.request.request_sha256,'f'.repeat(64))}]]) {
    const missing=await reconcileIssueCreation({request:f.request,intent,observe:async()=>rows});assert.equal(missing.effect_state,'outcome_unknown');assert.equal(missing.issue,null);assert.equal(missing.retry_authorized,false);
  }
  const unreadable=await reconcileIssueCreation({request:f.request,intent,observe:async()=>{throw Error('unavailable');}});
  assert.equal(unreadable.issue,null);assert.equal(unreadable.effect_state,'outcome_unknown');
  await assert.rejects(reconcileIssueCreation({request:f.request,intent:{...intent,phase:'autopilot_dispatch'},observe:async()=>[actual]}),/intent binding/);
});

test('incomplete existing-work/label evidence or invalid consumer identity cannot reach dispatch',async()=>{
  for(const change of [f=>{delete f.state.facts.workInventory;},f=>{f.state.facts.workInventory.complete=false;},f=>{delete f.state.facts.sourceIssue.labels;}]) {
    const f=fixture();change(f);const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(dispatches(f).length,0);assert.equal(f.rows.length,0);
  }
  const open=fixture();open.state.facts.workInventory.openPullRequests=[{number:10}];
  assert.equal((await open.consume()).effect_state,'outcome_unknown');assert.equal(dispatches(open).length,0);
  const invalid=fixture();await assert.rejects(createCorrectionEffectConsumer(invalid.deps)('selector',{run_id:'invalid',run_attempt:'1'}),/consumer execution/);
  assert.equal(dispatches(invalid).length,0);assert.equal(invalid.rows.length,0);
});
test('deadline that expires during fresh collection prevents the first dispatch',async()=>{
  const f=fixture();let clocks=0;f.deps.clock=()=>new Date(clocks++===0?'2026-10-26T00:00:00Z':'2031-01-01T00:00:00Z');
  const result=await f.consume();assert.equal(result.effect_state,'confirmed_not_started');assert.equal(dispatches(f).length,0);assert.equal(f.rows.length,0);
});

test('a malformed prior started receipt cannot erase uncertainty or cause another dispatch',async()=>{
  const f=fixture();await f.consume();f.state.observed=acceptedObservation(f.request);f.state.observed.continuation.issue_node_id='wrong';
  const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(dispatches(f).length,1);
});
test('expiry during durable intent retention cannot call the dispatch endpoint',async()=>{
  const f=fixture();const append=f.ledger.append;f.ledger.append=async args=>{const stored=await append(args);f.deps.clock=()=>new Date('2031-01-01T00:00:00Z');return stored;};
  // The dependency is captured at factory creation, so mutate the clock's
  // observed time instead of substituting an unrelated clock implementation.
  let expired=false;f.deps.clock=()=>new Date(expired?'2031-01-01T00:00:00Z':'2026-10-26T00:00:00Z');
  f.ledger.append=async args=>{const stored=await append(args);expired=true;return stored;};
  const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(dispatches(f).length,0);assert.equal(f.rows.length,1);
  await f.consume();assert.equal(dispatches(f).length,0);
});

function noIncumbentFixture() {
  const f=fixture();f.state.request=structuredClone(require('../../../tests/fixtures/verifier_correction/no-incumbent-request.json'));
  f.state.seed=seedForRequest(f.state.request);f.state.facts.incumbentIssue=null;
  f.state.facts.agent={key:'codex',enabled:true,registry_sha256:'c'.repeat(64)};
  const {incumbent,...scope}=f.state.facts.ownership;f.state.facts.ownership={...scope,kind:'no_incumbent'};
  f.state.created=null;f.state.creationObservable=true;f.state.started=false;f.state.createFailure=false;
  f.deps.collectFreshFacts=async (request,{createdIssue}={})=>{
    f.calls.push(['fresh']);f.state.facts.incumbentIssue=createdIssue?f.state.created:null;return f.state.facts;
  };
  f.deps.github.rest.issues={create:async args=>{
    f.calls.push(['create',args]);f.state.created={number:9,node_id:'I_9',body:args.body,state:'open',labels:args.labels,assignees:[]};
    if(f.state.createFailure)throw Error('server created issue; response lost');return {data:f.state.created};
  }};
  f.deps.reconcile=async ({effect_key})=>{
    f.calls.push(['reconcile',effect_key]);const result={issues:f.state.creationObservable && f.state.created?[f.state.created]:[]};
    if(f.state.started && dispatches(f).length)Object.assign(result,{request:f.state.request,
      issue:{number:'9',node_id:'I_9',body_sha256:sha(f.state.created.body)},continuation:{workflow:'agents-auto-pilot.yml',run_id:'902',run_attempt:'3',request_sha256:f.state.request.request_sha256,issue_node_id:'I_9'}});
    return result;
  };
  return f;
}
const creates=f=>f.calls.filter(row=>row[0]==='create');

test('trusted no-incumbent request creates one exact issue, retains it, dispatches existing optimize and accepts actual run',async()=>{
  const f=noIncumbentFixture();f.state.started=true;const result=await f.consume();checkReceipt(result);
  assert.equal(result.effect_state,'accepted_with_exact_issue_and_actual_autopilot_run_attempt');
  assert.equal(result.issue.node_id,'I_9');assert.equal(result.continuation.run_attempt,'3');assert.equal(result.ownership.kind,'no_incumbent');
  assert.equal(result.request_sha256,f.state.request.request_sha256);assert.deepEqual(result.request.incumbent,{kind:'no_incumbent'});
  assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,1);
  assert.deepEqual(f.rows.map(row=>[row.kind,row.phase]),[['intent','issue_creation'],['issue_confirmed','issue_creation'],['intent','autopilot_dispatch']]);
  assert.ok(f.rows.every(row=>row.effect_key===f.key));assert.equal(f.rows[1].issue.node_id,'I_9');
  assert.equal(dispatches(f)[0][1].inputs.issue_number,'9');assert.ok(!creates(f)[0][1].labels.includes('agents:auto-pilot'));
  await f.consume();assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,1);
});
test('unknown ownership and incomplete no-incumbent inventories never create or dispatch',async()=>{
  for(const change of [f=>{f.state.facts.ownership.kind='unknown';},f=>{f.state.facts.workInventory.complete=false;},
    f=>{f.state.facts.workInventory.assignments=[{owner:'other'}];},f=>{f.state.facts.workInventory.retainedEffects=[{state:'starting'}];},
    f=>{f.state.facts.ownership.seed_effect_key='f'.repeat(64);},f=>{f.state.facts.agent.enabled=false;}]) {
    const f=noIncumbentFixture();change(f);const result=await f.consume();checkReceipt(result);
    assert.ok(['confirmed_not_started','outcome_unknown'].includes(result.effect_state));assert.equal(creates(f).length,0);assert.equal(dispatches(f).length,0);
  }
});
test('lost create response with positive exact reconciliation never creates a replacement issue',async()=>{
  const f=noIncumbentFixture();f.state.createFailure=true;f.state.started=true;
  const result=await f.consume();checkReceipt(result);assert.equal(result.effect_state,'accepted_with_exact_issue_and_actual_autopilot_run_attempt');
  assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,1);await f.consume();assert.equal(creates(f).length,1);
});
test('uncertain creation remains unknown across restart, then exact positive issue resumes only first dispatch',async()=>{
  const f=noIncumbentFixture();f.state.createFailure=true;f.state.creationObservable=false;
  assert.equal((await f.consume()).effect_state,'outcome_unknown');assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,0);
  await f.consume();assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,0);
  f.state.creationObservable=true;f.state.started=true;const result=await f.consume();checkReceipt(result);
  assert.equal(result.effect_state,'accepted_with_exact_issue_and_actual_autopilot_run_attempt');assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,1);
});
test('uncertain dispatch after successful creation never repeats either stage',async()=>{
  const f=noIncumbentFixture();f.state.dispatchFailure=true;
  assert.equal((await f.consume()).effect_state,'outcome_unknown');await f.consume();assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,1);
  f.state.started=true;const accepted=await f.consume();assert.equal(accepted.effect_state,'accepted_with_exact_issue_and_actual_autopilot_run_attempt');
  assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,1);
});
test('lost created-issue retention acknowledgment prevents dispatch until exact retained identity reconciles',async()=>{
  const f=noIncumbentFixture(),append=f.ledger.append;let lose=true;
  f.ledger.append=async args=>{const stored=await append(args);if(args.record.kind==='issue_confirmed' && lose){lose=false;throw Error('lost retention ack');}return stored;};
  const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,0);
  f.state.started=true;assert.equal((await f.consume()).effect_state,'accepted_with_exact_issue_and_actual_autopilot_run_attempt');assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,1);
});
test('declared existing/no-incumbent conflicts do not become new ownership authority',async()=>{
  const f=noIncumbentFixture();f.state.request=f.request;f.state.seed=seedForRequest(f.request);
  assert.equal((await f.consume()).effect_state,'confirmed_not_started');assert.equal(creates(f).length,0);
  const existing=fixture();existing.state.request=structuredClone(require('../../../tests/fixtures/verifier_correction/no-incumbent-request.json'));existing.state.seed=seedForRequest(existing.state.request);
  assert.equal((await existing.consume()).effect_state,'confirmed_not_started');assert.equal(dispatches(existing).length,0);
});

test('concurrent no-incumbent consumers cannot create two issues or dispatch a second continuation',async()=>{
  const f=noIncumbentFixture();const results=await Promise.all(Array.from({length:10},()=>f.consume()));
  assert.equal(creates(f).length,1);assert.equal(dispatches(f).length,1);
  assert.equal(f.rows.filter(row=>row.kind==='intent' && row.phase==='issue_creation').length,1);
  assert.equal(f.rows.filter(row=>row.kind==='intent' && row.phase==='autopilot_dispatch').length,1);
  for(const result of results)assert.equal(result.effect_state,'outcome_unknown');
});
test('effect kernel refuses an already-fenced fixed stage even when called with a newer ledger revision',async()=>{
  const f=fixture();let invoked=0;
  const args={ledger:f.ledger,key:f.key,request:f.request,consumer,phase:'autopilot_dispatch',invoke:async()=>{invoked++;}};
  await attemptEffect({...args,snapshot:{revision:0,records:[]}});
  const again=await attemptEffect({...args,snapshot:await f.ledger.read(f.key)});
  assert.equal(invoked,1);assert.equal(again.state,'outcome_unknown');assert.equal(f.rows.length,1);
});

test('frozen shared no-incumbent seed/ownership/receipt fixtures retain original request digest',()=>{
  const {receipt}=require('../verifier_correction_consumer');
  const request=require('../../../tests/fixtures/verifier_correction/no-incumbent-request.json');
  const seed=require('../../../tests/fixtures/verifier_correction/seed.json');
  const ownership=require('../../../tests/fixtures/verifier_correction/no-incumbent-ownership.json');
  const frozen=require('../../../tests/fixtures/verifier_correction/accepted-no-incumbent-receipt.json');
  assert.deepEqual(seed,seedForRequest(request));assert.ok(!Object.hasOwn(seed,'required_tests'));
  assert.equal(ownership.seed_effect_key,effectKey(seed));assert.equal(ownership.source_scope_digest,sourceScopeDigest(seed));
  const actual=receipt(request,{state:frozen.effect_state,reason:frozen.reason,issue:frozen.issue,continuation:frozen.continuation,consumer:frozen.consumer,ownership});
  assert.deepEqual(actual,frozen);assert.equal(frozen.request_sha256,request.request_sha256);checkReceipt(actual);
});
test('unread no-incumbent facts are unknown and cannot create an issue',async()=>{
  const f=noIncumbentFixture();f.deps.collectFreshFacts=async()=>{throw Error('incomplete GitHub page');};
  const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(creates(f).length,0);assert.equal(dispatches(f).length,0);
});

test('copied exact marker cannot replace a durably retained created issue on resume or acceptance',async()=>{
  const f=noIncumbentFixture(),append=f.ledger.append;let stop=true;
  f.ledger.append=async args=>{const result=await append(args);if(args.record.kind==='issue_confirmed' && stop){stop=false;throw Error('stop after durable I_9 retention');}return result;};
  assert.equal((await f.consume()).effect_state,'outcome_unknown');assert.equal(f.rows[1].issue.node_id,'I_9');assert.equal(dispatches(f).length,0);
  // Same original marker/body, different issue number/node: cannot substitute.
  f.state.created={...f.state.created,number:10,node_id:'I_10'};
  const resumed=await f.consume();assert.equal(resumed.effect_state,'outcome_unknown');assert.equal(resumed.issue.node_id,'I_9');assert.equal(dispatches(f).length,0);assert.equal(creates(f).length,1);
  f.deps.reconcile=async()=>({request:f.state.request,issues:[f.state.created],issue:{number:'10',node_id:'I_10',body_sha256:sha(f.state.created.body)},continuation:{workflow:'agents-auto-pilot.yml',run_id:'999',run_attempt:'1',request_sha256:f.state.request.request_sha256,issue_node_id:'I_10'}});
  assert.equal((await f.consume()).effect_state,'outcome_unknown');assert.equal(dispatches(f).length,0);
});
test('conflicting durable issue confirmations remain unknown without dispatch',async()=>{
  const f=noIncumbentFixture(),append=f.ledger.append;let stop=true;
  f.ledger.append=async args=>{const stored=await append(args);if(args.record.kind==='issue_confirmed' && stop){stop=false;throw Error('stop after retention');}return stored;};
  await f.consume();const payload={...f.rows[1],revision:3,issue:{...f.rows[1].issue,node_id:'I_10',number:'10'}};delete payload.record_sha256;
  f.rows.push({...payload,record_sha256:digest(payload)});
  assert.equal((await f.consume()).effect_state,'outcome_unknown');assert.equal(dispatches(f).length,0);
});

test('registry digest arrays and non-string ownership timestamps cannot authorize no-incumbent effects',async()=>{
  const f=noIncumbentFixture();f.state.facts.agent.registry_sha256=['c'.repeat(64)];
  assert.equal((await f.consume()).effect_state,'confirmed_not_started');assert.equal(creates(f).length,0);
  const timestamp=noIncumbentFixture();timestamp.state.facts.ownership.observed_at=['2026-10-26T00:00:00Z'];
  assert.equal((await timestamp.consume()).effect_state,'outcome_unknown');assert.equal(creates(timestamp).length,0);
});

test('oversized ownership evidence refuses before effects instead of failing receipt construction afterward',async()=>{
  const f=noIncumbentFixture();f.state.facts.ownership.evidence_refs=['x'.repeat(4097)];
  const result=await f.consume();assert.equal(result.effect_state,'outcome_unknown');assert.equal(creates(f).length,0);assert.equal(dispatches(f).length,0);
});

test('shared API wrapper makes one consequential attempt on transient server failures',async()=>{
  const create=noIncumbentFixture();create.state.creationObservable=false;
  create.deps.github.rest.issues.create=async args=>{assert.equal(args.request.retries,0);create.calls.push(['create']);const error=new Error('lost 503 create response');error.status=503;error.request={method:'POST'};throw error;};
  assert.equal((await create.consume()).effect_state,'outcome_unknown');assert.equal(creates(create).length,1);await create.consume();assert.equal(creates(create).length,1);
  const dispatch=fixture();dispatch.deps.github.rest.actions.createWorkflowDispatch=async args=>{assert.equal(args.request.retries,0);dispatch.calls.push(['dispatch']);const error=new Error('lost 503 dispatch response');error.status=503;error.request={method:'POST'};throw error;};
  assert.equal((await dispatch.consume()).effect_state,'outcome_unknown');assert.equal(dispatches(dispatch).length,1);await dispatch.consume();assert.equal(dispatches(dispatch).length,1);
});
