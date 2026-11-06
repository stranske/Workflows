'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {fetchRequiredConversationComments,fetchVerifierEvidence}=require('../../.github/scripts/agents_verifier_context');
const {requiredEvidence,buildVerificationEvent}=require('../../.github/scripts/verification_event');
const url='https://github.com/a/b/issues/677#issuecomment-6236440140';
const body='Owner decision 2026-10-17 (q-10afaa2d73683dec): historical policy revision.';
const sourceIssues=[{number:677,url:'https://github.com/a/b/issues/677',repository:'a/b'}];
const selector=[{kind:'comment',url}];
function fixture(){let calls=0;const comment={id:6236440140,html_url:url,issue_url:'https://api.github.com/repos/a/b/issues/677',user:{login:'a',id:1},body,created_at:'2026-10-17T16:14:25Z',updated_at:'2026-10-17T16:14:25Z'};const github={rest:{issues:{getComment:async args=>{calls++;assert.equal(args.comment_id,6236440140);return {data:comment};},listComments:async()=>({data:[]})},pulls:{listReviewComments:async()=>({data:[]}),listReviews:async()=>({data:[]})}}};return {github,comment,calls:()=>calls,args:{github,owner:'a',repo:'b',pullNumber:689,sourceIssues,material:selector,maxChars:1000}};}
test('selected linked-source comment retains exact text, actor and chronology without overriding policy',async()=>{
 const f=fixture(),r=await fetchRequiredConversationComments(f.args);
 assert.equal(f.calls(),1);assert.equal(r.records.length,1);assert.equal(r.records[0].body,body);
 assert.equal(r.records[0].author,'a');assert.equal(r.records[0].created_at,f.comment.created_at);
 assert.equal(r.records[0].required_material,true);assert.equal(r.records[0].operating_directive,undefined);
 assert.equal(requiredEvidence(selector,{comments:r})[0].body_sha256,r.inventory[0].body_sha256);
});
test('outside repository, unlinked thread, malformed URL and source metadata mismatch never fetch',async()=>{
 for(const changed of ['https://github.com/a/evil/issues/677#issuecomment-6236440140','https://github.com/a/b/issues/678#issuecomment-6236440140','https://evil.example/a/b/issues/677#issuecomment-6236440140',url+'?redirect=1']){
  const f=fixture(),r=await fetchRequiredConversationComments({...f.args,material:[{kind:'comment',url:changed}]});
  assert.equal(f.calls(),0);assert.equal(r.records.length,0);
 }
 const f=fixture();const r=await fetchRequiredConversationComments({...f.args,sourceIssues:[{...sourceIssues[0],repository:'a/evil'}]});assert.equal(f.calls(),0);assert.equal(r.inventory[0].status,'unavailable');
});
test('API identity, thread, actor, timestamps, body and count mismatches are explicit per-source failures',async()=>{
 for(const change of [{id:2},{html_url:url.replace('677','678')},{issue_url:'https://api.github.com/repos/a/b/issues/678'},{user:{}},{created_at:null},{created_at:'2026-10-17T16:14:25Z\nmalformed'},{updated_at:'2026-10-16T00:00:00Z'},{body:null}]){
  const f=fixture();Object.assign(f.comment,change);const r=await fetchRequiredConversationComments(f.args);assert.equal(r.records.length,0);assert.equal(r.inventory[0].reason,'required_comment_identity_invalid');
 }
 const f=fixture(),r=await fetchRequiredConversationComments({...f.args,maxChars:1});assert.equal(r.inventory[0].reason,'required_comment_character_bound');assert.equal(r.records.length,0);
});
test('transient fetch failure retains recoverable cause; a fresh collection can recover',async()=>{
 const f=fixture(),get=f.github.rest.issues.getComment;f.github.rest.issues.getComment=async()=>{throw Error('temporary API failure');};
 const failed=await fetchRequiredConversationComments(f.args);assert.equal(failed.inventory[0].status,'unavailable');assert.match(failed.inventory[0].reason,/temporary/);assert.throws(()=>requiredEvidence(selector,{comments:failed}),/absent/);
 f.github.rest.issues.getComment=get;const recovered=await fetchRequiredConversationComments(f.args);assert.equal(recovered.inventory[0].status,'included');
});
test('no selection is inert; duplicates fetch once; PR selection preserves existing conversation collector',async()=>{
 assert.deepEqual(await fetchRequiredConversationComments({material:undefined}),{records:[],inventory:[],chars:0});
 const f=fixture(),r=await fetchRequiredConversationComments({...f.args,material:[...selector,...selector]});assert.equal(f.calls(),1);assert.equal(r.records.length,1);
 const pr=await fetchRequiredConversationComments({...f.args,material:[{kind:'comment',url:'https://github.com/a/b/pull/689#issuecomment-42'}]});assert.equal(pr.inventory[0].status,'existing_pr_collection');assert.equal(f.calls(),1);
});
test('real evidence collector reserves necessary source comment before optional PR comments',async()=>{
 const saved=process.env.VERIFICATION_MATERIAL,chars=process.env.VERIFIER_EVIDENCE_COMMENT_CHARS;
 try {
  process.env.VERIFICATION_MATERIAL=JSON.stringify(selector);process.env.VERIFIER_EVIDENCE_COMMENT_CHARS='120';
  const f=fixture();f.github.rest.issues.listComments=async()=>({data:[{id:1,html_url:'https://github.com/a/b/pull/689#issuecomment-1',user:{login:'someone'},body:'optional '.repeat(100)}]});
  const evidence=await fetchVerifierEvidence({github:f.github,owner:'a',repo:'b',pullNumber:689,pullRequestBody:'original requirements',sourceIssues});
  assert.equal(evidence.comments.records[0].body,body);assert.equal(evidence.comments.records[0].truncated,undefined);
  assert.equal(evidence.comments.complete,false);assert.equal(requiredEvidence(selector,evidence).length,1);
  const args={repository:'a/b',pull:{number:689,body:'original complete requirements',head:{sha:'a'.repeat(40)},merge_commit_sha:'b'.repeat(40)},issues:[],fullDiffBytes:Buffer.from('actual code'),evidence,selectors:selector};
  const event=buildVerificationEvent(args);evidence.comments.records[0].body+=' corrected chronology';assert.notEqual(buildVerificationEvent(args).verification_event.event_id,event.verification_event.event_id);
 }finally{if(saved===undefined)delete process.env.VERIFICATION_MATERIAL;else process.env.VERIFICATION_MATERIAL=saved;if(chars===undefined)delete process.env.VERIFIER_EVIDENCE_COMMENT_CHARS;else process.env.VERIFIER_EVIDENCE_COMMENT_CHARS=chars;}
});
