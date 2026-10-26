'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('path');
const {activeExecutions}=require('../verifier_correction_runtime');
const registryPath=path.join(__dirname,'../../agents/registry.yml');
test('complete native active inventory preserves unknown existing agent and queue writers, without an invented negative default',async()=>{
 const rows=[{id:20,status:'queued',path:'.github/workflows/agents-71-codex-belt-dispatcher.yml',run_attempt:1},
 {id:21,status:'queued',path:'.github/workflows/ci.yml',run_attempt:1},{id:22,status:'queued',path:'.github/workflows/reusable-codex-run.yml',run_attempt:1}];
 const transport={read:async(r,m,a)=>({total_count:a.status==='queued'?rows.length:0,workflow_runs:a.status==='queued'?rows:[]})};
 const actual=await activeExecutions({transport,current:{run_id:700,run_attempt:1},registryPath});
 assert.deepEqual(actual.map(row=>row.run_id),[20,22]);
});
test('native active-run missing fields, malformed count, duplicate IDs or transition during inventory remain UNKNOWN',async()=>{
 for(const change of [data=>{data.total_count=undefined;},data=>{delete data.workflow_runs[0].path;},
 data=>{data.workflow_runs.push(data.workflow_runs[0]);data.total_count=2;},data=>{data.workflow_runs[0].status='completed';}]) {
  const transport={read:async()=>{const data={total_count:1,workflow_runs:[{id:20,status:'queued',path:'.github/workflows/agents-70-orchestrator.yml'}]};change(data);return data;}};
  await assert.rejects(activeExecutions({transport,current:{run_id:700,run_attempt:1},registryPath}));
 }
});

test('every native nonterminal status remains an existing writer until positively reconciled',async()=>{
 for(const status of ['requested','waiting','pending','queued','in_progress']) {
  const transport={read:async(r,m,a)=>({total_count:a.status===status?1:0,
   workflow_runs:a.status===status?[{id:30,status,path:'.github/workflows/agents-70-orchestrator.yml',run_attempt:1}]:[]})};
  assert.equal((await activeExecutions({transport,current:{run_id:700,run_attempt:1},registryPath})).length,1);
 }
});

test('only a native linked run for the authenticated owned PR/head is an incumbent continuation rather than an unknown writer',async()=>{
 const ownedPull={pull:{id:88,number:'10',head_ref:'codex/issue-9',head_repository_id:1,base_repository_id:1},observed_head_sha:'b'.repeat(40)};
 const linked={id:88,number:10,head:{sha:'b'.repeat(40),ref:'codex/issue-9',repo:{id:1}},base:{repo:{id:1}}};
 for(const change of [null,row=>{row.pull_requests[0].id=89;},row=>{row.pull_requests[0].head.sha='c'.repeat(40);},row=>{row.pull_requests=[];}]) {
  const row={id:30,status:'in_progress',path:'.github/workflows/agents-keepalive-loop.yml',repository:{id:1},pull_requests:[structuredClone(linked)]};
  if(change)change(row);
  const transport={read:async(r,m,a)=>({total_count:a.status==='in_progress'?1:0,workflow_runs:a.status==='in_progress'?[row]:[]})};
  assert.equal((await activeExecutions({transport,current:{run_id:700,run_attempt:1},registryPath,ownedPull})).length,change?1:0);
 }
});
