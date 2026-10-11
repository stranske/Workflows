const { test } = require('node:test');
const assert = require('node:assert/strict');
const { findFleetArtifact } = require('../langsmith-fleet-artifacts.js');
const name = 'langsmith-fleet.ndjson';
const item = (id, extra={}) => ({id, name, expired:false, created_at:'2026-10-11', ...extra});
function fixture(list, run=async()=>({data:{path:'trusted.yml'}})) {
  const calls=[], warnings=[];
  return {calls,warnings,options:{owner:'o',repo:'r',name,
    trustedWorkflowPaths:new Set(['trusted.yml']),core:{warning:s=>warnings.push(s)},
    withRetry:fn=>fn(),github:{rest:{actions:{listArtifactsForRepo:async p=>{calls.push(p);return list(p);},getWorkflowRun:run}}}}};
}
test('large repository uses server-side exact name and never scans unrelated records', async()=>{
 const f=fixture(async p=>{assert.equal(p.name,name);return {data:{total_count:1,artifacts:[item(1)]}};});
 assert.equal((await findFleetArtifact(f.options)).id,1);assert.equal(f.calls.length,1);
});
test('exact artifact wins even when a newer suffix exists',async()=>{
 const f=fixture(async()=>({data:{total_count:1,artifacts:[item(1)]}}));
 assert.equal((await findFleetArtifact(f.options)).id,1);
});
test('expired exact artifacts do not hide a trusted suffix; untrusted and absent runs skipped',async()=>{
 const f=fixture(async p=>({data:{total_count:4,artifacts:p.name?[item(1,{expired:true})]:[
 item(2,{name:'bad-'+name,workflow_run:{id:2}}),item(3,{name:'norun-'+name}),
 item(4,{name:'good-'+name,workflow_run:{id:4}}),item(5,{name:'expired-'+name,expired:true})]}}),
 async p=>({data:{path:p.run_id===4?'trusted.yml':'untrusted.yml'}}));
 assert.equal((await findFleetArtifact(f.options)).id,4);
});
test('500 reduces page size without retrying the identical request',async()=>{
 const f=fixture(async p=>{if(p.per_page>1)throw Object.assign(new Error('500'),{status:500});
 return {data:{total_count:1,artifacts:[item(1)]}};});
 assert.equal((await findFleetArtifact(f.options)).id,1);assert.deepEqual(f.calls.map(p=>p.per_page),[30,10,1]);
});
test('reduced later page retains offset and does not skip records',async()=>{
 const f=fixture(async p=>{if(p.page===1)return {data:{total_count:31,artifacts:Array.from({length:30},()=>item(0,{expired:true}))}};
 if(p.per_page===30)throw Object.assign(new Error('500'),{status:500});
 assert.equal(p.page,4);return {data:{total_count:31,artifacts:[item(9)]}};});
 assert.equal((await findFleetArtifact(f.options)).id,9);
});
test('authorization errors fail immediately',async()=>{
 const f=fixture(async()=>{throw Object.assign(new Error('forbidden'),{status:403});});
 await assert.rejects(findFleetArtifact(f.options),/forbidden/);assert.equal(f.calls.length,1);
});
test('listing budget exhaustion is UNKNOWN, not a missing-artifact success',async()=>{
 const f=fixture(async()=>({data:{total_count:31260,artifacts:Array.from({length:30},()=>item(0,{expired:true}))}}));
 await assert.rejects(findFleetArtifact({...f.options,maxRequests:2}),/UNKNOWN/);assert.equal(f.calls.length,2);
});
test('no artifacts returns null after two bounded empty listings',async()=>{
 const f=fixture(async()=>({data:{total_count:0,artifacts:[]}}));
 assert.equal(await findFleetArtifact(f.options),null);assert.equal(f.calls.length,2);
});
