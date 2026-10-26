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
 let reads=0,attemptReads=0;
 return {rest:{actions:{getWorkflowRun:async params=>{
  assert.equal(params.run_id,10);const result=run();reads++;
  (reads>1&&refreshChange ? refreshChange : runChange)?.(result);return {data:result};
 },getWorkflowRunAttempt:async params=>{
  assert.equal(params.run_id,10);assert.equal(params.attempt_number,1);
  const result=run();attemptReads++;
  (attemptReads>1&&refreshChange ? refreshChange : runChange)?.(result);return {data:result};
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

test('authoritative reads use bounded retries and retain uncertainty on unavailable transport',async()=> {
 const github=api();
 const getRun=github.rest.actions.getWorkflowRun;
 const getJobs=github.rest.actions.listJobsForWorkflowRunAttempt;
 let runCalls=0,jobsCalls=0;
 const transient=()=>Object.assign(new Error('temporary read failure'),{status:503,request:{method:'GET'}});
 github.rest.actions.getWorkflowRun=async params=>{
  assert.equal(params.request.timeout,15000);
  if(++runCalls===1) throw transient();
  return getRun(params);
 };
 github.rest.actions.listJobsForWorkflowRunAttempt=async params=>{
  assert.equal(params.request.timeout,15000);
  if(++jobsCalls===1) throw transient();
  return getJobs(params);
 };
 const result=await reconcilePendingExecution({github,event,assessment,state});
 assert.equal(result.retry_kind,'known_no_evaluation');
 assert.equal(runCalls,3);assert.equal(jobsCalls,2);
 let refusedCalls=0;
 github.rest.actions.getWorkflowRun=async()=>{refusedCalls++;throw transient();};
 const unavailable=await reconcilePendingExecution({github,event,assessment,state});
 assert.equal(refusedCalls,3);
 assert.equal(unavailable.retryable,false);
 assert.equal(unavailable.failure_cause,'prior_execution_reconciliation_unavailable');
 assert.equal(unavailable.proof,undefined);
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

function rerunApi({latestAttempt=2,active=false,changeLatest,changeAttempt,changeJobs}={}) {
 let latestReads=0;
 return {rest:{actions:{
  getWorkflowRun:async()=>{
   const value={...run(),run_attempt:latestAttempt,...(active?{status:'in_progress',conclusion:null}:{})};
   changeLatest?.(value,++latestReads);return {data:value};
  },
  getWorkflowRunAttempt:async params=>{
   const value={...run(),run_attempt:params.attempt_number,
    ...(active&&params.attempt_number===latestAttempt?{status:'in_progress',conclusion:null}:{})};
   changeAttempt?.(value);return {data:value};
  },
  listJobsForWorkflowRunAttempt:async params=>{
   const number=params.attempt_number;
   const value={...job(),id:12+number,run_attempt:number};
   if(active&&number===latestAttempt) {
    value.status='in_progress';value.conclusion=null;
    value.steps=value.steps.map(step=>({...step,status:'queued',conclusion:null}));
   }
   changeJobs?.(value,number);
   return {data:{total_count:1,jobs:[value]},headers:{}};
  },
 }}};
}
const currentCollection={repo:event.repo,run_id:'10',run_attempt:'2',workflow_ref:`${event.repo}/.github/workflows/agents-verifier.yml@refs/heads/main`};

test('completed later skipped attempts recover original pending with separately bound provenance',async()=> {
 const original=JSON.stringify(state);
 const result=await reconcilePendingExecution({github:rerunApi(),event,assessment,state});
 assert.equal(result.retryable,true);assert.equal(result.proof.run_attempt,'1');
 assert.equal(result.proof.latest_run_attempt,'2');
 assert.equal(result.proof.subsequent_attempts[0].run_attempt,'2');
 assert.equal(result.proof.subsequent_attempts[0].conclusion,'skipped');
 assert.equal(result.proof.subsequent_attempts[0].current_execution,undefined);
 assert.equal(JSON.stringify(state),original);
});

test('only authenticated current collection exempts its own not-yet-started rerun',async()=> {
 const result=await reconcilePendingExecution({github:rerunApi({active:true}),event,assessment,state,currentExecution:currentCollection});
 assert.equal(result.retryable,true);
 assert.equal(result.proof.subsequent_attempts[0].current_execution,true);
 for(const currentExecution of [null,{...currentCollection,repo:'foreign/repo'},
  {...currentCollection,run_attempt:'3'},{...currentCollection,run_id:'11'},
  {...currentCollection,workflow_ref:`${event.repo}/.github/workflows/other.yml@main`}]) {
  const refused=await reconcilePendingExecution({github:rerunApi({active:true}),event,assessment,state,currentExecution});
  assert.equal(refused.retryable,false);
 }
});

test('newer started, unknown, competing or concurrently changing attempts never authorize replay',async()=> {
 const cases=[
  {changeJobs:(j,n)=>{if(n===2)j.steps[1].conclusion='success';}},
  {changeJobs:(j,n)=>{if(n===2)j.steps=null;}},
  {changeJobs:(j,n)=>{if(n===2)j.steps.pop();}},
  {changeJobs:(j,n)=>{if(n===2)j.steps[1].status='in_progress';}},
  {changeJobs:(j,n)=>{if(n===2)j.steps.push({name:'Run multi-provider comparison',status:'completed',conclusion:'success'});}},
  {changeLatest:(r,reads)=>{if(reads>1)r.run_attempt=3;}},
  {changeAttempt:r=>{if(r.run_attempt===2)r.repository={full_name:'foreign/repo'};}},
  {latestAttempt:11},
 ];
 for(const options of cases) {
  const result=await reconcilePendingExecution({github:rerunApi(options),event,assessment,state});
  assert.equal(result.retryable,false,JSON.stringify(options));
 }
 const exhausted=await reconcilePendingExecution({github:rerunApi(),event,assessment,state,maxPages:1});
 assert.equal(exhausted.failure_cause,'prior_attempt_jobs_incomplete');
 const selfStarted=await reconcilePendingExecution({github:rerunApi({active:true,
  changeJobs:(j,n)=>{if(n===2)j.steps[1].started_at='2026-10-23T01:00:00Z';}}),
  event,assessment,state,currentExecution:currentCollection});
 assert.equal(selfStarted.retryable,false);
 const intermediate=await reconcilePendingExecution({github:rerunApi({latestAttempt:3,active:true,
  changeJobs:(j,n)=>{if(n===2)j.steps[1].conclusion='success';}}),event,assessment,state,
  currentExecution:{...currentCollection,run_attempt:'3'}});
 assert.equal(intermediate.retryable,false);
 assert.equal(intermediate.existing_execution.run_attempt,'2');
});
