'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {digest}=require('../verification_event');
const {crossReferenceDigest}=require('../verifier_correction_host');
test('strict cross-reference content never accepts synthetic numeric IDs instead of native fields',()=>{
 assert.throws(()=>crossReferenceDigest({event:'cross-referenced',id:123,actor:{},created_at:'bad',source:{type:'issue',issue:{number:7,repository:{full_name:'stranske/example'},pull_request:{}}}},
 {number:7,head:{sha:'a'.repeat(40)}}),/identity unavailable/);
});

test('frozen native cross-reference v1 projection excludes mutable text and binds fresh exact source head',()=>{
 const f=require('../../../tests/fixtures/verifier_correction/native-crossref-lineage.json');
 assert.equal(crossReferenceDigest(f.event,f.pull),f.sha256);
 const changed=structuredClone(f.event);changed.source.issue.body='rewritten';changed.source.issue.labels=['changed'];
 assert.equal(crossReferenceDigest(changed,f.pull),f.sha256);
 assert.notEqual(crossReferenceDigest(changed,{...f.pull,head:{sha:'b'.repeat(40)}}),f.sha256);
});


function nativeStageHistory(f,records) {
 const {effectKey,seedForRequest}=require('../verifier_correction_effects');
 const key=effectKey(seedForRequest(f.request));
 f.state.retained.snapshots=records.map((_,index)=>({key,snapshot:{revision:index+1,records:structuredClone(records.slice(0,index+1))},
  proof:{run_id:700,run_attempt:1,artifact_id:100+index,archive_sha256:'a'.repeat(64),member_sha256:String(index).repeat(64)}}));
 const last=records.at(-1),proof=f.state.retained.snapshots.at(-1)?.proof;
 return last?{schema:'closer-correction-active-stage/v1',effect_key:key,request_sha256:f.request.request_sha256,
 phase:last.phase,record_sha256:last.record_sha256,revision:records.length,proof}:null;
}
function stageRecord(f,records,kind,phase,extra={}) {
 const {effectKey,seedForRequest}=require('../verifier_correction_effects');
 const payload={schema:'closer-correction-effect-ledger/v1',effect_key:effectKey(seedForRequest(f.request)),revision:records.length+1,
 kind,phase,request_sha256:f.request.request_sha256,consumer:{run_id:'700',run_attempt:'1'},...extra};
 return {...payload,record_sha256:digest(payload)};
}
