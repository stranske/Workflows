'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {execFileSync}=require('child_process');
const {createHash}=require('crypto');
const {fetchVerifierEvidence}=require('../agents_verifier_context');
const {requiredEvidence}=require('../verification_event');
const HEAD='a'.repeat(40),MERGE='b'.repeat(40);
const archive=execFileSync('python3',['-c',"import io,zipfile,sys;b=io.BytesIO();z=zipfile.ZipFile(b,'w');z.writestr('proof.txt','complete selected proof');z.close();sys.stdout.buffer.write(b.getvalue())"]);
const digest='sha256:'+createHash('sha256').update(archive).digest('hex');
function setup(selected) {
 const calls={runs:[],lookups:[],downloads:[],lists:[]};
 const origin=id=>({id,head_sha:HEAD,path:'.github/workflows/ci.yml',repository:{id:100,full_name:'o/r'},head_repository:{id:100,full_name:'o/r'}});
 const meta=(id,run)=>({id,name:'proof',expired:false,size_in_bytes:archive.length,digest,workflow_run:{id:run,repository_id:100,head_repository_id:100,head_sha:HEAD}});
 const g={rest:{issues:{listComments:async()=>({data:[],headers:{}})},pulls:{listReviewComments:async()=>({data:[],headers:{}}),listReviews:async()=>({data:[],headers:{}})},actions:{
  getWorkflowRun:async({run_id})=>{calls.runs.push(run_id);return {data:origin(run_id)}},
  listWorkflowRunArtifacts:async({run_id,per_page})=>{calls.lists.push(run_id);return {data:{total_count:30,artifacts:Array.from({length:per_page},(_,i)=>meta(i+1,run_id))},headers:{link:'<next>; rel="next"'}}},
  getArtifact:async({artifact_id})=>{calls.lookups.push(artifact_id);const row=selected.find(row=>row.artifact_id===artifact_id);return {data:meta(artifact_id,row.run_id)}},
  downloadArtifact:async({artifact_id})=>{calls.downloads.push(artifact_id);return {data:archive}},
  listWorkflowRunsForRepo:async()=>({data:{total_count:0,workflow_runs:[]},headers:{}}),
 }}};
 return {g,calls,origin,meta};
}
async function collect(selected,change=()=>{},limits={}) {
 const saved={VERIFICATION_MATERIAL:process.env.VERIFICATION_MATERIAL,VERIFIER_EVIDENCE_RUN_LIMIT:process.env.VERIFIER_EVIDENCE_RUN_LIMIT,VERIFIER_EVIDENCE_ARTIFACT_LIMIT:process.env.VERIFIER_EVIDENCE_ARTIFACT_LIMIT};
 process.env.VERIFICATION_MATERIAL=JSON.stringify(selected);Object.assign(process.env,limits);
 const fixture=setup(selected);change(fixture);
 try {return {...fixture,evidence:await fetchVerifierEvidence({github:fixture.g,owner:'o',repo:'r',pullNumber:7,pullRequestBody:'Complete original requirements.',associatedCommitShas:[HEAD,MERGE],evaluatedSha:MERGE})};}
 finally{for(const[k,v]of Object.entries(saved))if(v===undefined)delete process.env[k];else process.env[k]=v;}
}
const selected=[{kind:'artifact_member',run_id:10,artifact_id:999,path:'proof.txt'}];
test('required ID beyond bounded first page resolves by authenticated metadata, not extra discovery',async()=>{
 const {evidence,calls}=await collect(selected);
 assert.deepEqual(calls.lookups,[999]);assert.deepEqual(calls.downloads,[999]);
 assert.equal(evidence.artifacts.complete,false);assert.ok(evidence.diagnostics.failures.some(row=>row.kind==='artifact_record'));
 assert.equal(requiredEvidence(selected,evidence)[0].raw_sha256,createHash('sha256').update('complete selected proof').digest('hex'));
});
for(const problem of ['wrongid','wrongrun','foreign','foreignheadrepo','head','missingorigin','missingdigest','tampered','expired','lookup'])test(`selected metadata ${problem} cannot provide required proof`,async()=>{
 const {evidence,calls}=await collect(selected,({g,meta,origin,calls})=>{
  if(problem==='missingorigin')g.rest.actions.getWorkflowRun=async()=>({data:{...origin(10),head_repository:null}});
  g.rest.actions.getArtifact=async({artifact_id})=>{
   calls.lookups.push(artifact_id);if(problem==='lookup')throw new Error('unavailable');const row=meta(999,10);
   if(problem==='wrongid')row.id=998;if(problem==='wrongrun')row.workflow_run.id=11;
   if(problem==='foreign')row.workflow_run.repository_id=200;if(problem==='foreignheadrepo')row.workflow_run.head_repository_id=200;
   if(problem==='head')row.workflow_run.head_sha=MERGE;if(problem==='missingdigest')delete row.digest;
   if(problem==='tampered')row.digest='sha256:'+'0'.repeat(64);if(problem==='expired')row.expired=true;
   return {data:row};
  };
 });
 assert.throws(()=>requiredEvidence(selected,evidence));
 if(problem==='tampered'){assert.deepEqual(calls.downloads,[999]);assert.equal(evidence.diagnostics.counters.archive_bytes,archive.length);assert.ok(evidence.diagnostics.failures.some(row=>row.kind==='archive_integrity'));}
 else assert.deepEqual(calls.downloads,[]);
});
test('all20 explicit selected runs survive optional run/artifact limits of one',async()=>{
 const plan=Array.from({length:20},(_,i)=>({kind:'artifact_member',run_id:i+10,artifact_id:i+1000,path:'proof.txt'}));
 const {evidence,calls}=await collect(plan,()=>{},{VERIFIER_EVIDENCE_RUN_LIMIT:'1',VERIFIER_EVIDENCE_ARTIFACT_LIMIT:'1'});
 assert.equal(calls.runs.length,20);assert.equal(calls.lookups.length,20);assert.equal(calls.downloads.length,20);assert.equal(calls.lists.length,1);
 assert.equal(requiredEvidence(plan,evidence).length,20);assert.equal(evidence.artifacts.complete,false);
});
test('no material selection keeps existing discovery bound and never invokes metadata fallback',async()=>{
 const {evidence,calls}=await collect([],({g,origin})=>{
  g.rest.actions.listWorkflowRunsForRepo=async({head_sha})=>({data:{total_count:1,workflow_runs:[{...origin(10),head_sha}]},headers:{}});
 });
 assert.deepEqual(calls.lookups,[]);assert.equal(calls.downloads.length,10);assert.equal(evidence.artifacts.complete,false);
});
