'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('crypto');
const sha=b=>createHash('sha256').update(b).digest('hex');
const step=(name,number,start,end)=>({name,number,status:'completed',conclusion:'success',started_at:`2026-10-24T01:00:${start}Z`,completed_at:`2026-10-24T01:00:${end}Z`});
function retainedExecutionFixture(event,change=()=>{}) {
 const archive=Buffer.from('authenticated archive');
 const run={id:10,run_attempt:1,status:'completed',conclusion:'success',path:'.github/workflows/agents-verifier.yml',event:'workflow_dispatch',head_sha:'c'.repeat(40),head_branch:'main',repository:{id:9,full_name:event.repo},head_repository:{id:9,full_name:event.repo},referenced_workflows:[{path:'stranske/Workflows/.github/workflows/reusable-agents-verifier.yml@main',sha:'d'.repeat(40)}]};
 const job={id:12,run_id:10,run_attempt:1,head_sha:run.head_sha,name:'verifier / Run post-merge verifier',status:'completed',steps:[step('Checkout Workflows scripts',7,'01','03'),step('Record verification event pending',11,'04','05'),step('Run LLM evaluation',29,'06','07'),step('Retain evaluation execution evidence',42,'08','09')]};
 const artifact={id:30,name:'evaluation-results-10',expired:false,size_in_bytes:archive.length,digest:`sha256:${sha(archive)}`,created_at:'2026-10-24T01:00:08Z',workflow_run:{id:10,head_sha:run.head_sha,repository_id:9,head_repository_id:9}};
 let log=`2026-10-24T01:00:01Z repository: stranske/Workflows\n2026-10-24T01:00:01Z path: .workflows-lib\n2026-10-24T01:00:02Z [command]/usr/bin/git log -1 --format=%H\n2026-10-24T01:00:02Z ${'e'.repeat(40)}\n`;
 const data={run,job,artifact,archive,log};change(data);log=data.log;
 const github={rest:{actions:{getWorkflowRun:async()=>({data:run}),getWorkflowRunAttempt:async()=>({data:run}),listJobsForWorkflowRunAttempt:async()=>({data:{total_count:1,jobs:[job]},headers:{}}),getArtifact:async()=>({data:artifact}),downloadJobLogsForWorkflowRun:async()=>({data:log}),downloadArtifact:async()=>({data:data.archive})},repos:{get:async p=>({data:{full_name:`${p.owner}/${p.repo}`,default_branch:'main'}}),getCommit:async()=>({data:{sha:'f'.repeat(40)}}),compareCommitsWithBasehead:async p=>({data:{status:'ahead',base_commit:{sha:p.basehead.split('...')[0]},merge_base_commit:{sha:p.basehead.split('...')[0]}}}),getContent:async p=>{assert.equal(p.ref,'e'.repeat(40));return {data:{encoding:'base64',content:Buffer.from('authentic validator').toString('base64')}};}}}};
 return {github,data};
}
module.exports={retainedExecutionFixture,step};
