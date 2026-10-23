'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {executionBinding,reconcilePendingExecution}=require('../../.github/scripts/verifier_pending_execution.js');
const {assessmentIdentity,completedEvent}=require('../../.github/scripts/verification_event.js');
const {verification_event:event}=require('../fixtures/verification_event/canonical.json');
const assessment=assessmentIdentity({mode:'evaluate',provider:'anthropic'});
const state={schema:'verifier-event-state/v1',status:'pending',repo:event.repo,pr:event.pr,head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,verification_event:event,assessment_identity:assessment,run_id:'10',run_attempt:'1',execution_binding:executionBinding('evaluate')};
const run=()=>({id:10,run_attempt:1,status:'completed',conclusion:'cancelled',path:'.github/workflows/agents-verifier.yml',event:'workflow_dispatch',head_sha:'c'.repeat(40),repository:{full_name:event.repo},head_repository:{full_name:event.repo}});
const job=()=>({id:12,run_id:10,run_attempt:1,head_sha:'c'.repeat(40),name:'verifier / Run post-merge verifier',status:'completed',conclusion:'cancelled',steps:[{name:'Record verification event pending',number:5,status:'completed',conclusion:'success'},{name:'Run LLM evaluation',number:15,status:'completed',conclusion:'skipped'}]});
function api({runChange,jobsChange,refreshChange}={}) {
 let reads=0;
 return {rest:{actions:{getWorkflowRun:async params=>{
  assert.equal(params.run_id,10);const result=run();reads++;
  (reads>1&&refreshChange ? refreshChange : runChange)?.(result);return {data:result};
 },listJobsForWorkflowRunAttempt:async params=>{
  assert.equal(params.run_id,10);assert.equal(params.attempt_number,1);
  const result={total_count:1,jobs:[job()]};jobsChange?.(result);return {data:result,headers:{}};
 }}}};
}

test('cancelled prior run retries only with exact authoritative skipped evaluator proof',async()=> {
 const result=await reconcilePendingExecution({github:api(),event,assessment,state});
 assert.equal(result.retry_kind,'known_no_evaluation');assert.equal(result.retryable,true);
 assert.equal(result.proof.job_id,12);assert.equal(result.proof.run_attempt,'1');
 assert.equal(result.proof.evaluator_step,'Run LLM evaluation');assert.equal(result.proof.conclusion,'skipped');
 assert.equal(result.proof.event_id,event.event_id);
});

test('active, changed, foreign, missing and started prior executions never authorize retries',async()=> {
 const cases=[{runChange:r=>{r.status='in_progress';}}, {runChange:r=>{r.run_attempt=2;}},
 {runChange:r=>{r.repository.full_name='foreign/repo';}}, {runChange:r=>{r.path='.github/workflows/other.yml';}},
 {jobsChange:r=>{delete r.total_count;}}, {jobsChange:r=>{r.total_count=2;}},
 {jobsChange:r=>{r.jobs[0].run_attempt=2;}}, {jobsChange:r=>{r.jobs[0].steps.pop();}}, {jobsChange:r=>{r.jobs[0].steps[0].number=0;}},
 {jobsChange:r=>{r.jobs[0].steps[1].conclusion='cancelled';}},
 {jobsChange:r=>{r.jobs[0].steps[1].conclusion='success';}},
 {jobsChange:r=>{r.jobs[0].steps.push({name:'Run multi-provider comparison',number:20,status:'completed',conclusion:'success'});}},
 {refreshChange:r=>{r.run_attempt=2;}}, {jobsChange:r=>{r.jobs.push({...r.jobs[0]});r.total_count=2;}}];
 for(const options of cases) {
  const result=await reconcilePendingExecution({github:api(options),event,assessment,state});
  assert.equal(result.retryable,false);assert.equal(result.retry_kind,'uncertain_execution');
 }
 const legacy=await reconcilePendingExecution({github:api(),event,assessment,state:{...state,execution_binding:undefined}});
 assert.equal(legacy.retryable,false);
});

test('ignored provider/model arguments cannot create new assessment purchases',()=> {
 const base={mode:'compare',model:'primary',model2:'',canonical:true};
 assert.deepEqual(assessmentIdentity({...base,provider:'openai'}),assessmentIdentity({...base,provider:'anthropic'}));
 assert.deepEqual(assessmentIdentity({...base,provider:'auto'}),assessmentIdentity({...base,provider:'',model2:'primary'}));
 assert.deepEqual(assessmentIdentity({mode:'evaluate',provider:'github-models',model2:'ignored'}),assessmentIdentity({mode:'evaluate',provider:'auto'}));
 assert.notDeepEqual(assessmentIdentity({mode:'evaluate',provider:'anthropic'}),assessmentIdentity({mode:'evaluate',provider:'openai'}));
 const raw={...base,provider:'anthropic'};
 const decision={schema:'verifier-corpus-decision/v1',repo:event.repo,pr:event.pr,head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,run_id:'11',run_attempt:'1',ci_failed:false,verdict:'NON_PASS',provider_verdicts:['CONCERNS'],verification_event:event,assessment_identity:raw};
 const comment={author:'github-actions[bot]',url:`https://github.com/${event.repo}/pull/${event.pr}#issuecomment-1`,body:`<!-- verifier-corpus-decision/v1 ${JSON.stringify(decision)} -->`};
 assert.equal(completedEvent(event,[comment],assessmentIdentity({...base,provider:'openai'})),true);
});
