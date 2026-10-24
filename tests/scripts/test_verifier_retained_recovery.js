'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('fs'), os=require('os'), path=require('path');
const {createHash}=require('crypto');
const {parseRecoverySelector,assessmentIdentity}=require('../../.github/scripts/verification_event.js');
const {acquireRetainedExecution,guardRecoveryHistory,publishRetainedReport}=require('../../.github/scripts/verifier_pending_execution.js');
const {verification_event:event}=require('../fixtures/verification_event/canonical.json');
const assessment=assessmentIdentity({mode:'evaluate',provider:'anthropic'});
const selector={run_id:10,run_attempt:1,artifact_id:30};
const sha=b=>createHash('sha256').update(b).digest('hex');
const step=(name,number,start,end)=>({name,number,status:'completed',conclusion:'success',started_at:`2026-10-24T01:00:${start}Z`,completed_at:`2026-10-24T01:00:${end}Z`});
function fixture(change=()=>{}) {
 const archive=Buffer.from('authenticated archive');
 const run={id:10,run_attempt:1,status:'completed',conclusion:'success',path:'.github/workflows/agents-verifier.yml',event:'workflow_dispatch',head_sha:'c'.repeat(40),head_branch:'main',repository:{id:9,full_name:event.repo},head_repository:{id:9,full_name:event.repo},referenced_workflows:[{path:'stranske/Workflows/.github/workflows/reusable-agents-verifier.yml@main',sha:'d'.repeat(40)}]};
 const job={id:12,run_id:10,run_attempt:1,head_sha:run.head_sha,name:'verifier / Run post-merge verifier',status:'completed',steps:[step('Checkout Workflows scripts',7,'01','03'),step('Record verification event pending',11,'04','05'),step('Run LLM evaluation',29,'06','07'),step('Retain evaluation execution evidence',42,'08','09')]};
 const artifact={id:30,name:'evaluation-results-10',expired:false,size_in_bytes:archive.length,digest:`sha256:${sha(archive)}`,created_at:'2026-10-24T01:00:08Z',workflow_run:{id:10,head_sha:run.head_sha,repository_id:9,head_repository_id:9}};
 let log=`2026-10-24T01:00:01Z repository: stranske/Workflows\n2026-10-24T01:00:01Z path: .workflows-lib\n2026-10-24T01:00:02Z [command]/usr/bin/git log -1 --format=%H\n2026-10-24T01:00:02Z ${'e'.repeat(40)}\n`;
 const data={run,job,artifact,archive,log};change(data);log=data.log;
 const github={rest:{actions:{getWorkflowRun:async()=>({data:run}),getWorkflowRunAttempt:async()=>({data:run}),listJobsForWorkflowRunAttempt:async()=>({data:{total_count:1,jobs:[job]},headers:{}}),getArtifact:async()=>({data:artifact}),downloadJobLogsForWorkflowRun:async()=>({data:log}),downloadArtifact:async()=>({data:data.archive})},repos:{get:async p=>({data:{full_name:`${p.owner}/${p.repo}`,default_branch:'main'}}),getCommit:async()=>({data:{sha:'f'.repeat(40)}}),compareCommitsWithBasehead:async p=>({data:{status:'ahead',base_commit:{sha:p.basehead.split('...')[0]},merge_base_commit:{sha:p.basehead.split('...')[0]}}}),getContent:async p=>{assert.equal(p.ref,'e'.repeat(40));return {data:{encoding:'base64',content:Buffer.from('authentic validator').toString('base64')}};}}}};
 return {github,data};
}
function inDirectory(fn) {
 const old=process.cwd(),dir=fs.mkdtempSync(path.join(os.tmpdir(),'retained-origin-'));process.chdir(dir);
 return Promise.resolve().then(()=>fn(dir)).finally(()=>{process.chdir(old);fs.rmSync(dir,{recursive:true,force:true});});
}
test('selectors reject authority-bearing digests and ambiguous coercions',()=>{
 assert.deepEqual(parseRecoverySelector(JSON.stringify(selector)),selector);
 for(const value of ['null','{}','[]',' ',JSON.stringify({...selector,sha256:'a'.repeat(64)}),JSON.stringify({...selector,run_id:'10'}),JSON.stringify({...selector,run_attempt:0})]) assert.throws(()=>parseRecoverySelector(value));
});
test('authenticated source joins attempt, job, artifact, digest and actual helper checkout',async()=>inDirectory(async dir=>{
 const {github}=fixture();const proof=await acquireRetainedExecution({github,event,assessment,selector,currentRun:20});
 assert.equal(proof.helper_sha,'e'.repeat(40));assert.equal(proof.reusable_sha,'d'.repeat(40));
 assert.equal(proof.archive_sha256,sha(Buffer.from('authenticated archive')));
 assert.equal(fs.readFileSync(path.join(dir,'verification-recovery-source.zip'),'utf8'),'authenticated archive');
}));
test('foreign, ambiguous, expired, wrong-attempt and tampered archives fail before retained authority',async()=>{
 const cases=[d=>{d.run.repository.full_name='foreign/repo';},d=>{d.run.run_attempt=2;},d=>{d.run.referenced_workflows=[];},d=>{d.job.steps[0].conclusion='failure';},d=>{d.job.steps.push({...d.job.steps[0]});},d=>{d.artifact.expired=true;},d=>{d.artifact.created_at='2026-10-24T01:00:02Z';},d=>{d.artifact.workflow_run.head_repository_id=99;},d=>{d.archive=Buffer.from('tampered');},d=>{d.log=d.log.replace('path: .workflows-lib','path: foreign');},d=>{d.log+='2026-10-24T01:00:02Z [command]/usr/bin/git log -1 --format=%H\n2026-10-24T01:00:02Z '+ 'f'.repeat(40)+'\n';}];
 for(const change of cases) await inDirectory(async dir=>{
  const {github}=fixture(change);await assert.rejects(acquireRetainedExecution({github,event,assessment,selector,currentRun:20}));
  assert.equal(fs.existsSync(path.join(dir,'verification-recovery-origin.json')),false);
 });
});
const comment=(run,extra={})=>({author:'github-actions[bot]',url:`https://github.com/${event.repo}/pull/${event.pr}#issuecomment-${run}`,body:`<!-- verifier-event-state/v1 ${JSON.stringify({schema:'verifier-event-state/v1',repo:event.repo,pr:event.pr,head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,run_id:String(run),run_attempt:'1',verification_event:event,assessment_identity:assessment,status:'pending',...extra})} -->`});
test('later/active assessments block recovery while unrelated and older roots do not',()=>{
 const args={event,assessment,sourceRun:10,sourceAttempt:1,currentRun:20,recoveryKey:'key'};
 assert.equal(guardRecoveryHistory({...args,comments:[comment(9),comment(20)]}),'ready');
 assert.throws(()=>guardRecoveryHistory({...args,comments:[comment(11)]}),/superseded/);
 assert.throws(()=>guardRecoveryHistory({...args,comments:[comment(10,{run_attempt:'2'})]}),/superseded/);
 const foreign=comment(11);foreign.author='untrusted';assert.equal(guardRecoveryHistory({...args,comments:[foreign]}),'ready');
});
test('publication reconciles uncertain single POST and exact duplicate without another write',async()=>{
 let posts=0;const comments=[];
 const origin={verification_event:event,assessment_identity:assessment,source_run_id:'10',source_run_attempt:'1',recovery_key:'key'};
 const manifest={verification_event:event,assessment_identity:assessment,request:{sources:[]}};
 const decision={schema:'verifier-corpus-decision/v1',repo:event.repo,pr:event.pr,head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,verification_event:event,assessment_identity:assessment,run_id:'20',run_attempt:'1',verdict:'PASS',provider_verdicts:['PASS'],ci_failed:false,retained_revalidation:{recovery_key:'key'}};
 const body=`<!-- verifier-corpus-decision/v1 ${JSON.stringify(decision)} -->`;
 const github={rest:{pulls:{get:async()=>({data:{merged:true,head:{sha:event.head_sha},merge_commit_sha:event.evaluated_sha}})},issues:{listComments:async()=>({data:comments,headers:{}}),createComment:async()=>{posts++;comments.push({id:5,user:{login:'github-actions[bot]'},html_url:`https://github.com/${event.repo}/pull/${event.pr}#issuecomment-5`,body});throw new Error('response lost');}}}};
 // Publication run is excluded from ordering guards during the current run,
 // so an uncertain write needs an exact marker lookup, not generic history.
 const result=await publishRetainedReport({github,manifest,origin,body,currentRun:20});
 assert.equal(result.published,true);assert.equal(posts,1);
 const again=await publishRetainedReport({github,manifest,origin,body,currentRun:21});
 assert.equal(again.duplicate,true);assert.equal(posts,1);
});

test('new malformed authenticated target history refuses recovery but unrelated malformed history does not',()=>{
 const args={event,assessment,sourceRun:10,sourceAttempt:1,currentRun:20,recoveryKey:'key'};
 for(const mutate of [row=>{row.verification_event.event_id='f'.repeat(64);},row=>{row.assessment_identity=null;},row=>{row.run_id='unknown';},row=>{row.run_attempt='unknown';}]) {
  const input=comment(11);const row=JSON.parse(input.body.match(/ (\{.*\}) -->/)[1]);mutate(row);
  input.body=`<!-- verifier-event-state/v1 ${JSON.stringify(row)} -->`;
  assert.throws(()=>guardRecoveryHistory({...args,comments:[input]}),/malformed/);
  row.pr='999';input.body=`<!-- verifier-event-state/v1 ${JSON.stringify(row)} -->`;
  assert.equal(guardRecoveryHistory({...args,comments:[input]}),'ready');
 }
 const clipped={...comment(11),truncated:true};
 assert.throws(()=>guardRecoveryHistory({...args,comments:[clipped]}),/truncated/);
});

test('wrapper reusable and helper each require canonical merged origin with complete API proof',async()=>{
 for(const target of ['wrapper','reusable','helper','metadata','api_error']) await inDirectory(async dir=>{
  const {github,data}=fixture();
  if(target==='metadata') github.rest.repos.get=async()=>({data:{full_name:event.repo}});
  if(target==='api_error') github.rest.repos.get=async()=>{throw Object.assign(new Error('read denied'),{status:403});};
  const denied={wrapper:'c',reusable:'d',helper:'e'}[target];
  if(denied) github.rest.repos.compareCommitsWithBasehead=async p=>({data:{status:p.basehead.startsWith(denied.repeat(40))?'diverged':'ahead',base_commit:{sha:p.basehead.split('...')[0]},merge_base_commit:{sha:p.basehead.split('...')[0]}}});
  await assert.rejects(acquireRetainedExecution({github,event,assessment,selector,currentRun:20}));
  assert.equal(fs.existsSync(path.join(dir,'verification-recovery-origin.json')),false);
 });
});

test('canonical merged wrapper bytes remain eligible through a release-branch alias',async()=>inDirectory(async()=>{
 const {github}=fixture(data=>{data.run.head_branch='release-reviewed';});
 const proof=await acquireRetainedExecution({github,event,assessment,selector,currentRun:20});
 assert.equal(proof.source_run_head_sha,'c'.repeat(40));
}));

test('lost recovery terminal is reconciled only from authoritative skipped publication',async()=>{
 const {executionBinding,guardRetainedRecoveryHistory}=require('../../.github/scripts/verifier_pending_execution.js');
 for(const published of [false,true]) {
  const {github}=fixture(d=>{
   d.job.steps.find(step=>step.name==='Run LLM evaluation').conclusion='skipped';
   d.job.steps.push({...step('Publish retained revalidation through verifier lifecycle',43,'10','11'),conclusion:published?'success':'skipped'});
  });
  const input=comment(10,{execution_binding:{...executionBinding('evaluate'),retained_revalidation:true},retained_revalidation:{schema:'retained-revalidation/v1',recovery_key:'key'}});
  const args={github,event,assessment,comments:[input],sourceRun:1,currentRun:20,recoveryKey:'key',observations:[]};
  if(published) await assert.rejects(guardRetainedRecoveryHistory(args),/active or uncertain/);
  else {assert.equal(await guardRetainedRecoveryHistory(args),'ready');assert.equal(args.observations[0].publication_conclusion,'skipped');}
 }
});

test('same-run older attempt cannot be mistaken for current pending state',()=>{
 const args={event,assessment,sourceRun:1,currentRun:10,currentAttempt:2,recoveryKey:'key'};
 const pending=comment(10,{retained_revalidation:{schema:'retained-revalidation/v1',recovery_key:'key'}});
 assert.throws(()=>guardRecoveryHistory({...args,comments:[pending]}),error=>error.code==='VERIFIER_RECOVERY_PENDING');
 const row=JSON.parse(pending.body.match(/ (\{.*\}) -->/)[1]);
 Object.assign(row,{schema:'verifier-corpus-decision/v1',verdict:'PASS',provider_verdicts:['PASS'],ci_failed:false});
 delete row.status;
 const complete={...pending,body:`<!-- verifier-corpus-decision/v1 ${JSON.stringify(row)} -->`};
 assert.equal(guardRecoveryHistory({...args,comments:[complete]}),'duplicate');
});

test('publication marks possible effect before POST, never for failed preflight',async()=>{
 const origin={verification_event:event,assessment_identity:assessment,source_run_id:'10',source_run_attempt:'1',recovery_key:'key'};
 const manifest={verification_event:event,assessment_identity:assessment,request:{sources:[]}};
 const decision={schema:'verifier-corpus-decision/v1',repo:event.repo,pr:event.pr,head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,verification_event:event,assessment_identity:assessment,run_id:'20',run_attempt:'1',verdict:'PASS',provider_verdicts:['PASS'],ci_failed:false,retained_revalidation:{recovery_key:'key'}};
 const body=`<!-- verifier-corpus-decision/v1 ${JSON.stringify(decision)} -->`;
 for(const changed of [false,true]) {
  let marked=false,posts=0;
  const github={rest:{pulls:{get:async()=>({data:{merged:true,head:{sha:changed?'f'.repeat(40):event.head_sha},merge_commit_sha:event.evaluated_sha}})},issues:{listComments:async()=>({data:[],headers:{}}),createComment:async()=>{assert.equal(marked,true);posts++;return {data:{id:5}};}}}};
  const action=()=>publishRetainedReport({github,manifest,origin,body,currentRun:20,onPostAttempt:()=>{marked=true;}});
  if(changed) {await assert.rejects(action(),/revision changed/);assert.equal(marked,false);assert.equal(posts,0);}
  else {await action();assert.equal(posts,1);}
 }
});

test('same-run recovery retry can reconcile older skipped POST while current publisher is pre-POST',async()=>{
 const {executionBinding,guardRetainedRecoveryHistory}=require('../../.github/scripts/verifier_pending_execution.js');
 const {github,data}=fixture(d=>{
  d.job.steps.find(step=>step.name==='Run LLM evaluation').conclusion='skipped';
  d.job.steps.push({...step('Publish retained revalidation through verifier lifecycle',43,'10','11'),conclusion:'skipped'});
 });
 const prior=structuredClone(data.run);
 const latest={...prior,run_attempt:2,status:'in_progress',conclusion:null};
 const oldJob=structuredClone(data.job);
 const currentJob={...structuredClone(oldJob),id:13,run_attempt:2,status:'in_progress'};
 Object.assign(currentJob.steps.at(-1),{status:'in_progress',conclusion:null,completed_at:null});
 github.rest.actions.getWorkflowRun=async()=>({data:latest});
 github.rest.actions.getWorkflowRunAttempt=async p=>({data:p.attempt_number===1?prior:latest});
 github.rest.actions.listJobsForWorkflowRunAttempt=async p=>({data:{total_count:1,jobs:[p.attempt_number===1?oldJob:currentJob]},headers:{}});
 const old=comment(10,{execution_binding:{...executionBinding('evaluate'),retained_revalidation:true},retained_revalidation:{schema:'retained-revalidation/v1',recovery_key:'key'}});
 const result=await guardRetainedRecoveryHistory({github,event,assessment,comments:[old],sourceRun:1,currentRun:10,currentAttempt:2,recoveryKey:'key',currentExecution:{run_id:'10',run_attempt:'2',repo:event.repo,workflow_ref:`${event.repo}/.github/workflows/agents-verifier.yml@main`,phase:'pre_publication'}});
 assert.equal(result,'ready');
});

test('confirmed admitted POST with incomplete lifecycle can finish without model replay',()=>{
 const args={event,assessment,sourceRun:1,currentRun:20,recoveryKey:'key'};
 const retained={schema:'retained-revalidation/v1',recovery_key:'key',provider_generation_performed:false};
 const pending=comment(10,{retained_revalidation:retained});
 const row=JSON.parse(pending.body.match(/ (\{.*\}) -->/)[1]);
 Object.assign(row,{schema:'verifier-corpus-decision/v1',verdict:'PASS',provider_verdicts:['PASS'],ci_failed:false,result_admission:{schema:'verifier-result-admission/v1',mode:'evaluate',payload_sha256:'a'.repeat(64),execution_receipt_sha256:'b'.repeat(64)}});delete row.status;
 const complete={...pending,body:`<!-- verifier-corpus-decision/v1 ${JSON.stringify(row)} -->`};
 const incomplete=comment(10,{status:'incomplete',retry_kind:'uncertain_execution',retryable:false,failure_cause:'retained_revalidation_publication_uncertain',retained_revalidation:{...retained,publication_effect:'uncertain'}});
 const history=[pending,complete,incomplete],before=JSON.stringify(history);
 assert.equal(guardRecoveryHistory({...args,comments:history}),'ready');
 assert.throws(()=>guardRecoveryHistory({...args,comments:[pending,incomplete]}),/superseded/);
 const fresh={...complete,body:complete.body.replace('"run_id":"10"','"run_id":"21"')};
 assert.equal(guardRecoveryHistory({...args,currentRun:22,comments:[...history,fresh]}),'duplicate');
 assert.equal(JSON.stringify(history),before);
});
