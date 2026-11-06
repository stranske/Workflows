'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {createHash}=require('crypto');
const {execFileSync}=require('child_process');
const {comparisonBaselineBinding,extractArtifactArchiveText,fetchVerifierEvidence}=require('../agents_verifier_context');
const {validatedSelectors}=require('../verifier_gzip_assets');
const {requiredEvidence,buildVerificationEvent,digest}=require('../verification_event');
const BASE='a'.repeat(40), MERGE='b'.repeat(40), HEAD='c'.repeat(40);
const selector={kind:'artifact_member',run_id:10,artifact_id:20,path:'tmp/combined.txt',evidence_role:'comparison-baseline',compared_paths:['src/a.py']};
const run={id:10,run_attempt:1,status:'completed',event:'push',head_sha:BASE,repository:{full_name:'o/r'}};
const hash=b=>createHash('sha256').update(b).digest('hex');
function githubFixture(change) {
 const bytes=Buffer.from('real production source\n');
 const value={type:'file',path:'src/a.py',encoding:'base64',size:bytes.length,content:bytes.toString('base64'),sha:createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${bytes.length}\0`),bytes])).digest('hex')};
 return {rest:{repos:{compareCommitsWithBasehead:async()=>({data:{status:'ahead',base_commit:{sha:BASE},merge_base_commit:{sha:BASE}}}),getContent:async({ref})=>({data:change==='source' && ref===MERGE?{...value,content:Buffer.from('different').toString('base64'),size:9,sha:createHash('sha1').update(Buffer.from('blob 9\0different')).digest('hex')}:value})}}};
}
function binding(github=githubFixture(),r=run,s=selector){return comparisonBaselineBinding(github,r,{owner:'o',repo:'r',evaluatedSha:MERGE,selectors:[s]});}
test('explicit baseline authenticates exact source bytes, never current CI',async()=>{
 const result=await binding();assert.equal(result.schema,'verifier-comparison-baseline/v1');assert.equal(result.run_head_sha,BASE);assert.equal(result.evaluated_sha,MERGE);assert.equal(result.compared_sources.length,1);assert.match(result.compared_sources[0].sha256,/^[a-f0-9]{64}$/);
});
for(const change of ['foreign','pending','attempt','divergent','wrongbase','source','missing','tampered','API'])test(`baseline refuses ${change}`,async()=>{
 const g=githubFixture(change),r={...run};
 if(change==='foreign')r.repository={full_name:'other/r'};
 if(change==='pending')r.status='in_progress';
 if(change==='attempt')r.run_attempt=0;
 if(change==='divergent')g.rest.repos.compareCommitsWithBasehead=async()=>({data:{status:'diverged',base_commit:{sha:BASE},merge_base_commit:{sha:HEAD}}});
 if(change==='wrongbase')g.rest.repos.compareCommitsWithBasehead=async()=>({data:{status:'ahead',base_commit:{sha:HEAD},merge_base_commit:{sha:BASE}}});
 if(change==='missing')g.rest.repos.getContent=async()=>({data:[]});
 if(change==='tampered')g.rest.repos.getContent=async()=>({data:{type:'file',path:'src/a.py',encoding:'base64',content:'eA==',size:1,sha:BASE}});
 if(change==='API')g.rest.repos.getContent=async()=>{throw new Error('unavailable')};
 await assert.rejects(binding(g,r));
});
test('ancestry without explicit role provides no baseline permission',async()=>assert.equal(await comparisonBaselineBinding(githubFixture(),run,{owner:'o',repo:'r',evaluatedSha:MERGE,selectors:[]}),null));
for(const path of ['../escape','/absolute','wild*.txt','C:/file','one\ntwo'])test(`selector rejects unsafe path ${JSON.stringify(path)}`,()=>assert.throws(()=>validatedSelectors([{...selector,path}])));
test('baseline selection cannot carry foreign repository or caller digest overrides',()=>assert.throws(()=>validatedSelectors([{...selector,repository:'other/r',sha256:'d'.repeat(64)}])));
function archive() {return execFileSync('python3',['-c',"import sys,zipfile,io; b=io.BytesIO(); z=zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED); z.writestr('huge.json','x'*300000); z.writestr('tmp/combined.txt','a.py 10 2 80%'); z.close();sys.stdout.buffer.write(b.getvalue())"]);}
test('actual ZIP required small member bypasses oversized optional sibling but preserves gap',()=>{
 const raw=archive();
 const whole=extractArtifactArchiveText({archiveBuffer:raw,maxEntries:10,maxChars:200,maxBytes:800});assert.ok(whole.failures.includes('extraction_byte'));
 const selected=extractArtifactArchiveText({archiveBuffer:raw,maxEntries:1,maxChars:200,maxBytes:800,selectedMembers:['tmp/combined.txt']});
 assert.ok(selected.text.includes('a.py 10 2 80%'));assert.equal(selected.members[0].status,'unselected');assert.equal(selected.members[1].status,'included');assert.ok(selected.failures.includes('unselected_member'));assert.ok(!selected.failures.includes('extraction_byte'));
 const requiredLarge=extractArtifactArchiveText({archiveBuffer:raw,maxEntries:10,maxChars:200,maxBytes:800,selectedMembers:['huge.json']});assert.ok(requiredLarge.failures.includes('extraction_byte'));
 const missing=extractArtifactArchiveText({archiveBuffer:raw,maxEntries:10,maxChars:200,maxBytes:800,selectedMembers:['missing.txt']});assert.ok(missing.failures.includes('required_member_missing'));
 assert.throws(()=>extractArtifactArchiveText({archiveBuffer:Buffer.from('not zip'),maxEntries:10,maxChars:200,maxBytes:800,selectedMembers:['tmp/combined.txt']}));
});
test('selected baseline joins authenticated material; wrong target and missing proof refuse',async()=>{
 const b=await binding(),raw=Buffer.from('coverage proof');
 const evidence={diagnostics:{archive_inventory:[{run_id:10,artifact_id:20,repository:'o/r',head_sha:BASE,historical_binding:b,member_inventory_complete:true,members:[{name:selector.path,status:'included',raw_sha256:hash(raw)}]}]}};
 const result=requiredEvidence([selector],evidence,{repository:'o/r',evaluatedSha:MERGE});assert.equal(result[0].evidence_role,'comparison-baseline');assert.deepEqual(result[0].comparison_binding,b);
 const manifest=buildVerificationEvent({repository:'o/r',pull:{number:7,body:'Original authentic requirement.',head:{sha:HEAD},merge_commit_sha:MERGE},issues:[],fullDiffBytes:Buffer.from('authentic patch'),evidence,selectors:[selector],ciResults:[]});
 assert.deepEqual(manifest.material.required_evidence,result);assert.equal(manifest.verification_event.material_sha256,digest(manifest.material));assert.equal(manifest.material.required_evidence[0].comparison_binding.compared_sources[0].path,'src/a.py');
 assert.throws(()=>requiredEvidence([selector],evidence,{repository:'other/r',evaluatedSha:MERGE}));assert.throws(()=>requiredEvidence([selector],evidence,{repository:'o/r',evaluatedSha:HEAD}));
 evidence.diagnostics.archive_inventory[0].members[0].status='unselected';assert.throws(()=>requiredEvidence([selector],evidence,{repository:'o/r',evaluatedSha:MERGE}));
});

test('real collector selected baseline retains role, required proof and unselected inventory',async()=>{
 const previous=process.env.VERIFICATION_MATERIAL;
 process.env.VERIFICATION_MATERIAL=JSON.stringify([selector]);
 const g=githubFixture(),raw=archive(),downloads=[];
 g.rest.issues={listComments:async()=>({data:[],headers:{}})};
 g.rest.pulls={listReviewComments:async()=>({data:[],headers:{}}),listReviews:async()=>({data:[],headers:{}})};
 g.rest.actions={getWorkflowRun:async()=>({data:run}),
  listWorkflowRunArtifacts:async()=>({data:{total_count:2,artifacts:[{id:20,name:'selected-proof',size_in_bytes:raw.length,expired:false},{id:21,name:'huge-sibling',size_in_bytes:100000000,expired:false}]},headers:{}}),
  listWorkflowRuns:async()=>({data:{total_count:0,workflow_runs:[]},headers:{}}),
  downloadArtifact:async({artifact_id})=>{downloads.push(artifact_id);return {data:raw}}};
 try {
  const result=await fetchVerifierEvidence({github:g,owner:'o',repo:'r',pullNumber:7,pullRequestBody:'Complete original requirements retained.',associatedCommitShas:[HEAD,MERGE],evaluatedSha:MERGE});
  assert.deepEqual(downloads,[20]);assert.equal(result.body.text,'Complete original requirements retained.');
  assert.equal(result.artifacts.status,'unavailable');
  const inventory=result.diagnostics.archive_inventory;
  assert.equal(inventory[0].historical_binding.schema,'verifier-comparison-baseline/v1');
  assert.equal(inventory[1].status,'unselected');assert.ok(result.diagnostics.failures.every(row=>['unselected_member','extraction_incomplete'].includes(row.kind)));
  assert.equal(requiredEvidence([selector],result,{repository:'o/r',evaluatedSha:MERGE})[0].raw_sha256,hash(Buffer.from('a.py 10 2 80%')));
 } finally {if(previous===undefined)delete process.env.VERIFICATION_MATERIAL;else process.env.VERIFICATION_MATERIAL=previous;}
});

test('global selection gives necessary baseline priority over unselected current-head runs',async()=>{
 const previous=process.env.VERIFICATION_MATERIAL;
 process.env.VERIFICATION_MATERIAL=JSON.stringify([selector]);
 const g=githubFixture(),raw=archive(),downloads=[],runReads=[];
 g.rest.issues={listComments:async()=>({data:[],headers:{}})};
 g.rest.pulls={listReviewComments:async()=>({data:[],headers:{}}),listReviews:async()=>({data:[],headers:{}})};
 g.rest.actions={getWorkflowRun:async({run_id})=>{runReads.push(run_id);return {data:run_id===10?run:{...run,id:30,head_sha:HEAD}}},
  listWorkflowRunArtifacts:async({run_id})=>({data:{total_count:1,artifacts:run_id===10?[{id:20,name:'selected-proof',size_in_bytes:raw.length,expired:false}]:[{id:31,name:'oversized-current-optional',size_in_bytes:100000000,expired:false}]},headers:{}}),
  listWorkflowRuns:async()=>({data:{total_count:0,workflow_runs:[]},headers:{}}),
  downloadArtifact:async({artifact_id})=>{downloads.push(artifact_id);return {data:raw}}};
 try {
  const result=await fetchVerifierEvidence({github:g,owner:'o',repo:'r',pullNumber:7,
   pullRequestBody:'Evidence: https://github.com/o/r/actions/runs/30\nEvidence: https://github.com/o/r/actions/runs/10',
   associatedCommitShas:[HEAD,MERGE],evaluatedSha:MERGE});
  assert.deepEqual(runReads,[10,30]);assert.deepEqual(downloads,[20]);
  assert.equal(result.diagnostics.archive_inventory.find(row=>row.artifact_id===31).status,'unselected');
  const selected=requiredEvidence([selector],result,{repository:'o/r',evaluatedSha:MERGE})[0];
  assert.deepEqual(selected.comparison_binding.compared_sources.map(row=>row.path),['src/a.py']);
  assert.equal(selected.comparison_binding.compared_sources[0].sha256,hash(Buffer.from('real production source\n')));
 } finally {if(previous===undefined)delete process.env.VERIFICATION_MATERIAL;else process.env.VERIFICATION_MATERIAL=previous;}
});

test('selected member after many unselected siblings uses requested entry bound only',()=>{
 const raw=execFileSync('python3',['-c',"import sys,zipfile,io;b=io.BytesIO();z=zipfile.ZipFile(b,'w');[z.writestr('optional%d.txt'%i,'optional') for i in range(12)];z.writestr('proof.txt','complete selected proof');z.close();sys.stdout.buffer.write(b.getvalue())"]);
 const result=extractArtifactArchiveText({archiveBuffer:raw,maxEntries:1,maxChars:1000,maxBytes:1000,selectedMembers:['proof.txt']});
 assert.equal(result.memberInventoryComplete,true);assert.equal(result.memberCount,13);
 assert.equal(result.members.filter(row=>row.status==='unselected').length,12);
 assert.equal(result.members.at(-1).status,'included');assert.equal(result.selectedCaptureComplete,true);
 assert.deepEqual(result.failures,['unselected_member']);assert.ok(result.text.includes('complete selected proof'));
});

test('safe optional media cannot truncate complete selected text; selecting media remains unavailable',()=>{
 const raw=execFileSync('python3',['-c',"import io,zipfile,sys;b=io.BytesIO();z=zipfile.ZipFile(b,'w');z.writestr('proof.txt','complete required table');z.writestr('image.png','binary');z.close();sys.stdout.buffer.write(b.getvalue())"]);
 const text=extractArtifactArchiveText({archiveBuffer:raw,maxEntries:5,maxChars:1000,maxBytes:1000,selectedMembers:['proof.txt']});
 assert.equal(text.selectedCaptureComplete,true);assert.deepEqual(text.failures,['unrenderable_media']);assert.equal(text.members.find(row=>row.name==='image.png').status,'unsupported');assert.ok(text.text.includes('complete required table'));
 const media=extractArtifactArchiveText({archiveBuffer:raw,maxEntries:5,maxChars:1000,maxBytes:1000,selectedMembers:['image.png']});
 assert.equal(media.selectedCaptureComplete,false);assert.equal(media.members.find(row=>row.name==='image.png').status,'unsupported');
});
