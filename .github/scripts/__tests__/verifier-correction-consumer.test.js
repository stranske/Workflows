'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const {createHash} = require('crypto');
const eventTools = require('../verification_event');
const {validateRequest, receipt} = require('../verifier_correction_consumer');
const fixture = require('../../../tests/fixtures/verification_event/request_correlation.json');
const sha = value => createHash('sha256').update(value).digest('hex');
const issue = number => ({number:String(number),node_id:`I_${number}`,body_sha256:sha(`issue ${number}`)});
function request() {
  const value = {schema:'closer-correction-request/v1',
    target:{repository:fixture.decision.repo,pr:fixture.decision.pr,head_sha:fixture.decision.head_sha,
      base_sha:'c'.repeat(40),merge_sha:fixture.decision.evaluated_sha},
    source_issue:issue(1), original_verifier:{verification_event:fixture.decision.verification_event,
      run_id:'100',run_attempt:'2',comment_id:'43',comment_sha256:sha(fixture.source_comment.body),decision_sha256:eventTools.digest(fixture.decision)},
    finding:{id:'finding-1',evidence:{ref:'evaluation.json#/concerns/0',sha256:'d'.repeat(64)}},
    required_tests:[{kind:'required_test_spec',id:'test-1',finding_id:'finding-1',specification:'Assert rejected input leaves the existing issue unchanged.',
      source_evidence:{ref:'evaluation.json#/concerns/0',sha256:'d'.repeat(64)}}],
    incumbent:{issue:issue(8),owner:'owner',assignment_ref:'issue:8/assignee:owner',lineage_ref:'review:42'},
    original_operation:{hold_id:'hold',run_id:'original-run',operation_id:'operation',idempotency_key:'exact-once',
      deadline:'2030-01-01T00:00:00Z',attempt_budget:1,escalation_owner:'owner'},scope:'substantive_implementation'};
  return seal(value);
}
function seal(value) { const {request_sha256,...payload}=value;return {...payload,request_sha256:eventTools.digest(payload)}; }
const consumer={run_id:'900',run_attempt:'1'};
test('canonical digest binds every source, operation, finding and test requirement',()=>{
  assert.equal(validateRequest(request()).schema,'closer-correction-request/v1');
  for(const change of [v=>v.target.head_sha='d'.repeat(40),v=>v.finding.id='other',v=>v.required_tests[0].specification='other',v=>v.original_operation.operation_id='other']) {
    const value=request();change(value);assert.throws(()=>validateRequest(value),/digest/);
  }
});
test('typed test specs and existing selectors are data; no executable command field',()=>{
  const value=request();value.required_tests=[{kind:'existing_selector',id:'test-2',finding_id:'finding-1',source_ref:'git:head',path:'tests/test_input.py',selector:'test_rejected_input',file_sha256:'a'.repeat(64)}];
  assert.ok(validateRequest(seal(value)));
  for(const mutate of [v=>v.required_tests=[],v=>v.required_tests[0].command='touch /tmp/effect',v=>v.scope='security',v=>v.required_tests[0].path='../escape']) {
    const copy=structuredClone(value);mutate(copy);assert.throws(()=>validateRequest(seal(copy)));
  }
});
test('issue-created and dispatch-ack cannot claim actual continuation; unknown never grants retry or closure',()=>{
  const value=request();
  assert.throws(()=>receipt(value,{state:'accepted_with_exact_issue_and_actual_autopilot_run_attempt',issue:value.incumbent.issue,consumer,reason:'HTTP 204'}),/continuation/);
  for(const state of ['confirmed_not_started','outcome_unknown']) {
    const result=receipt(value,{state,issue:value.incumbent.issue,consumer,reason:'inert fixture'});
    assert.equal(result.retry_authorized,false);assert.equal(result.act_authorized,false);assert.equal(result.source_closure_authorized,false);
    assert.equal(result.continuation,null);assert.equal(result.request.original_operation.idempotency_key,'exact-once');
  }
  assert.throws(()=>receipt(value,{state:'outcome_unknown',issue:issue(9),consumer,reason:'wrong incumbent'}),/incumbent/);
});

// Load the actual adapter with transport-only inert mocks. There are no write
// endpoints, provider clients, labels or workflow-dispatch mocks to call.
async function collect({changeRequest=()=>{},changeFiles=()=>{},changeApi=()=>{},proofFailure=false}={}) {
  const value=request();changeRequest(value);const sealed=seal(value);
  const archive=Buffer.from('inert archive');
  const material=require('../../../tests/fixtures/verification_event/canonical.json');
  const files=new Map([['closer-correction-request.json',Buffer.from(JSON.stringify(sealed))],
    ['verification-event-manifest.json',Buffer.from(JSON.stringify({verification_event:fixture.decision.verification_event,request:material.request,material:material.material}))]]);
  changeFiles(files);
  let acquisitions=0,reads=0;
  const actualIssue=n=>({number:n,node_id:`I_${n}`,body:`issue ${n}`,state:'open',assignees:[{login:'owner'}]});
  const api={pulls:{get:async()=>({merged:true,head:{sha:value.target.head_sha},base:{sha:value.target.base_sha,repo:{full_name:value.target.repository}},merge_commit_sha:value.target.merge_sha})},
    issues:{get:async args=>actualIssue(args.issue_number),getComment:async()=>({user:{id:41898282,login:'github-actions[bot]',type:'Bot'},issue_url:'https://api.github.com/repos/stranske/example/issues/7',html_url:fixture.source_comment.url,body:fixture.source_comment.body})}};
  changeApi(api);
  const wrapped=Object.fromEntries(Object.entries(api).map(([group,methods])=>[group,Object.fromEntries(Object.entries(methods).map(([name,fn])=>[name,async args=>{reads++;return {data:await fn(args)};}]))]));
  const module={exports:{}};
  const fakeRequire=name=>name==='fs'?{readFileSync:()=>archive}:name==='./verifier_pending_execution'?{
    acquireRetainedExecution:async()=>{acquisitions++;if(proofFailure)throw Error('untrusted origin');return {archive_sha256:sha(archive),archive_bytes:archive.length};},readRetainedArchive:()=>files}:name==='./verification_event'?eventTools:name==='./github-api-with-retry'?require('../github-api-with-retry'):require(name);
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../verifier_correction_consumer.js'),'utf8'),{require:fakeRequire,module,Buffer,URL});
  const selector={schema:'closer-correction-selector/v1',run_id:100,run_attempt:2,artifact_id:50,request_sha256:sealed.request_sha256,verification_event:fixture.decision.verification_event,assessment_identity:fixture.decision.assessment_identity};
  const result=await module.exports.collectCorrection({github:{rest:wrapped},selector,currentRun:900,currentAttempt:1,directory:'/inert'});
  return {result,acquisitions,reads};
}
test('actual admission authenticates retained source before reading exact API identities and remains collection only',async()=>{
  const {result,acquisitions,reads}=await collect();
  assert.equal(acquisitions,1);assert.equal(reads,4);assert.equal(result.effect_state,'confirmed_not_started');
  assert.match(result.reason,/collection_only/);
});
test('no original trusted correction producer means no fallback to PR text or caller payload',async()=>{
  await assert.rejects(collect({changeFiles:files=>files.delete('closer-correction-request.json')}),/producer missing/);
  await assert.rejects(collect({proofFailure:true}),/untrusted origin/);
});
test('causal admission refuses original execution confusion, stale incumbent and forged comment',async()=>{
  await assert.rejects(collect({changeRequest:v=>v.original_verifier.run_id='800'}),/selector mismatch/);
  await assert.rejects(collect({changeApi:api=>api.issues.get=async()=>({number:8,node_id:'wrong',body:'issue 8'})}),/issue binding/);
  await assert.rejects(collect({changeApi:api=>api.issues.getComment=async()=>({user:{id:123},body:fixture.source_comment.body})}),/comment unauthenticated/);
});

test('frozen cross-language request fixture matches canonical request bytes',()=>{
  const frozen=require('../../../tests/fixtures/verifier_correction/request.json');
  assert.deepEqual(frozen,request());
  assert.equal(validateRequest(frozen).request_sha256,request().request_sha256);
});

test('authored collection job emits refusal receipts without entering legacy issue/dispatch job',async()=>{
  const workflow=fs.readFileSync(path.join(__dirname,'../../workflows/agents-verify-to-new-pr.yml'),'utf8');
  const job=workflow.split('  collect-correction:\n')[1].split('\n  apply-correction:')[0];
  assert.match(job,/^    if: github.event_name == 'workflow_dispatch'/m);
  assert.match(job,/contents: read\n      actions: read\n      issues: read\n      pull-requests: read/);
  assert.doesNotMatch(job,/createWorkflowDispatch|issues\.create|createComment|withRetry/);
  const block=job.split('          script: |\n')[1].split('      - name: Upload')[0];
  const script=block.split('\n').map(line=>line.startsWith('            ')?line.slice(12):line).join('\n');
  const files={};
  const requireStub=name=>name==='fs'?{mkdirSync(){},writeFileSync:(name,value)=>{files[name]=value;}}
    :name.endsWith('/verification_event')?eventTools
    :name.endsWith('/verifier_correction_consumer')?{collectCorrection:async()=>{throw Error('Trusted correction-request producer missing; collection only');}}
    :{normalizeTerminalDisposition:()=>({schema:'workflows-terminal-disposition/v1'})};
  const summary={addHeading(){return this;},addRaw(){return this;},async write(){}};
  const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
  await new AsyncFunction('require','github','core','context','process',script)(requireStub,{},
    {summary},{runId:900},{env:{CORRECTION_SELECTOR:'{}',GITHUB_RUN_ATTEMPT:'1'}});
  const ledger=JSON.parse(files['agent-metrics/verifier-followup-ledger.ndjson']);
  assert.equal(ledger.schema,'closer-correction-admission-refusal/v1');
  assert.equal(ledger.effect_state,'confirmed_not_started');assert.equal(ledger.retry_authorized,false);
  assert.equal(JSON.parse(files['agent-metrics/verifier-terminal-disposition.ndjson']).correction_receipt.receipt_sha256,ledger.receipt_sha256);
});

test('exact authenticated accepted receipts deduplicate; unknown/missing history never repeats effects',()=>{
  const {reconcileCorrection}=require('../verifier_correction_consumer');
  const value=request();
  const continuation={workflow:'agents-auto-pilot.yml',run_id:'901',run_attempt:'1',request_sha256:value.request_sha256,issue_node_id:value.incumbent.issue.node_id};
  const accepted=receipt(value,{state:'accepted_with_exact_issue_and_actual_autopilot_run_attempt',reason:'authenticated inert continuation',issue:value.incumbent.issue,continuation,consumer});
  const duplicate=reconcileCorrection(value,[accepted,accepted],consumer);
  assert.equal(duplicate.effect_state,accepted.effect_state);assert.equal(duplicate.continuation.run_id,'901');
  for(const history of [[],[receipt(value,{state:'outcome_unknown',reason:'timeout after intent',consumer})],[receipt(value,{reason:'collection only',consumer})]]) {
    const result=reconcileCorrection(value,history,consumer);
    assert.equal(result.effect_state,'outcome_unknown');assert.equal(result.retry_authorized,false);
  }
  const other=request();other.required_tests[0].specification='Another exact requirement';
  const rebound=receipt(seal(other),{reason:'same key different scope',consumer});
  assert.throws(()=>reconcileCorrection(value,[rebound],consumer),/idempotency key rebound/);
  assert.throws(()=>reconcileCorrection(value,[{...accepted,reason:'tampered'}],consumer),/corrupt/);
  const conflict=receipt(value,{state:accepted.effect_state,reason:'other run',issue:value.incumbent.issue,continuation:{...continuation,run_id:'902'},consumer});
  assert.throws(()=>reconcileCorrection(value,[accepted,conflict],consumer),/Conflicting/);
});

test('declared no-incumbent variant fabricates no issue/owner and cannot grant receipt ownership',()=>{
  const value=require('../../../tests/fixtures/verifier_correction/no-incumbent-request.json');
  assert.deepEqual(validateRequest(value).incumbent,{kind:'no_incumbent'});
  assert.throws(()=>receipt(value,{consumer,reason:'caller declaration only',issue:issue(9)}),/incumbent/);
  const corrupt=seal({...value,incumbent:{kind:'no_incumbent',owner:'invented'}});
  assert.throws(()=>validateRequest(corrupt),/incumbent/);
});

test('frozen digest/commit fields require scalar strings instead of regex-coercible arrays',()=>{
  for(const corrupt of [value=>{value.source_issue.body_sha256=[value.source_issue.body_sha256];},
    value=>{value.original_verifier.comment_sha256=[value.original_verifier.comment_sha256];},
    value=>{value.original_verifier.decision_sha256=[value.original_verifier.decision_sha256];},
    value=>{value.incumbent.issue.body_sha256=[value.incumbent.issue.body_sha256];},
    value=>{value.target.head_sha=[value.target.head_sha];}]) {
    const value=request();corrupt(value);assert.throws(()=>validateRequest(seal(value)));
  }
  const value=request();value.required_tests=[{kind:'existing_selector',id:'existing',finding_id:value.finding.id,source_ref:'git:head',path:'tests/test_input.py',selector:'test_rejected_input',file_sha256:['a'.repeat(64)]}];
  assert.throws(()=>validateRequest(seal(value)),/required-test selector/);
});

test('native API comment metadata preserves canonical repository casing without losing exact subject binding',async()=>{
  const {result}=await collect({changeApi:api=>{api.issues.getComment=async()=>({user:{id:41898282,login:'github-actions[bot]',type:'Bot'},issue_url:'https://api.github.com/repos/stranske/Example/issues/7',html_url:'https://github.com/stranske/Example/pull/7#issuecomment-43',body:fixture.source_comment.body});}});
  assert.equal(result.effect_state,'confirmed_not_started');assert.match(result.reason,/collection_only/);
  await assert.rejects(collect({changeApi:api=>{api.issues.getComment=async()=>({user:{id:41898282,login:'github-actions[bot]',type:'Bot'},issue_url:'https://api.github.com/repos/stranske/Example/issues/8',html_url:'https://github.com/stranske/Example/pull/7#issuecomment-43',body:fixture.source_comment.body});}}),/comment unauthenticated/);
});
