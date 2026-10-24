'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const { buildVerificationEvent, validateEvent, completedEvent, digest } = require('../../.github/scripts/verification_event.js');
const expected = require('../fixtures/verification_event/canonical.json');
const args = () => ({ repository:'stranske/Example', pull:{number:7,body:'Original complete request.',head:{sha:'a'.repeat(40)},merge_commit_sha:'b'.repeat(40)},issues:[],fullDiffBytes:Buffer.from('authentic diff\n'),evidence:{comments:{records:[]},event_history:{complete:true,records:[]},diagnostics:{archive_inventory:[]}} });
const assessment = {mode:'evaluate',provider:'anthropic',model:'',model2:'',canonical:true};
const comment = (event, override={}) => ({author:'github-actions[bot]',url:'https://github.com/stranske/example/pull/7#issuecomment-1',body:`<!-- verifier-corpus-decision/v1 ${JSON.stringify({schema:'verifier-corpus-decision/v1',repo:event.repo,pr:event.pr,head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,run_id:'10',run_attempt:'1',ci_failed:false,provider_verdicts:['CONCERNS'],verdict:'NON_PASS',verification_event:event,assessment_identity:assessment,...override})} -->`});

test('canonical fixture equals independent Python hashes',()=> {
 const result=buildVerificationEvent(args());
 assert.deepEqual(result,expected);
 assert.equal(digest(result.request),expected.verification_event.request_sha256);
});
test('same inputs and refetch noise preserve event',()=> {
 const a=args(), original=buildVerificationEvent(a);
 a.evidence.diagnostics.observed_at='tomorrow';
 a.evidence.comments.records.push({url:'incidental',body:'Optional log noise'});
 a.evidence.diagnostics.archive_inventory.push({run_id:123,archive_sha256:'x',status:'unavailable'});
 assert.deepEqual(buildVerificationEvent(a),original);
 const prior = comment(original.verification_event);a.evidence.comments.complete=true;a.evidence.comments.records=[prior];a.evidence.event_history.records=[prior];
 assert.deepEqual(buildVerificationEvent({...a,predecessorEventId:original.verification_event.event_id}).verification_event,original.verification_event);
 assert.throws(()=>buildVerificationEvent({...a,predecessorEventId:'c'.repeat(64)}),/not an authenticated/);
});
test('exact same-SHA required comment progress creates distinct material event',()=> {
 const a=args();a.selectors=[{kind:'comment',url:'https://github.com/stranske/example/pull/7#issuecomment-8'}];
 a.evidence.comments.records.push({url:a.selectors[0].url,body:'retained proof'});
 const before=buildVerificationEvent(a);
 a.evidence.comments.records[0].body='new authentic proof';
 const after=buildVerificationEvent(a);
 assert.notEqual(before.verification_event.event_id,after.verification_event.event_id);
 assert.equal(before.verification_event.request_sha256,after.verification_event.request_sha256);
});
test('missing and ambiguous necessary material cannot mint event',()=> {
 const a=args();a.selectors=[{kind:'comment',url:'https://github.com/stranske/example/pull/7#issuecomment-8'}];
 assert.throws(()=>buildVerificationEvent(a),/absent/);
 a.evidence.comments.records=[{url:'https://github.com/stranske/example/pull/7#issuecomment-8',body:'one'},{url:'https://github.com/stranske/example/pull/7#issuecomment-8',body:'two'}];
 assert.throws(()=>buildVerificationEvent(a),/ambiguous/);
});
test('archive transport noise excluded; exact retained member content matters',()=> {
 const a=args();a.selectors=[{kind:'artifact_member',run_id:4,artifact_id:5,path:'proof.txt'}];
 a.evidence.diagnostics.archive_inventory=[{run_id:4,artifact_id:5,member_inventory_complete:true,members:[{name:'proof.txt',status:'captured',raw_sha256:'d'.repeat(64)}]}];
 const before=buildVerificationEvent(a);a.evidence.diagnostics.archive_inventory[0].archive_sha256='e'.repeat(64);
 assert.deepEqual(buildVerificationEvent(a),before);
 a.evidence.diagnostics.archive_inventory[0].members[0].raw_sha256='f'.repeat(64);
 assert.notEqual(buildVerificationEvent(a).verification_event.event_id,before.verification_event.event_id);
});
test('caller expected digest is checked against actual collector content',()=> {
 const a=args();a.expected=expected.verification_event;
 assert.deepEqual(buildVerificationEvent(a).verification_event,expected.verification_event);
 a.fullDiffBytes=Buffer.from('different code');
 assert.throws(()=>buildVerificationEvent(a),/expectation differs/);
 assert.throws(()=>validateEvent({...expected.verification_event,event_id:'f'.repeat(64)}),/Invalid/);
});
test('completed NON_PASS deduplicates exact event and assessment, not missing reviewer',()=> {
 const e=expected.verification_event,c=comment(e);
 assert.equal(completedEvent(e,[c],assessment),true);
 assert.equal(completedEvent(e,[c],{...assessment,provider:'openai'}),false);
 assert.equal(completedEvent({...e,event_id:'f'.repeat(64)},[c],assessment),false);
});
test('untrusted, malformed, cross-PR and false PASS are never completed evidence',()=> {
 const e=expected.verification_event;
 for(const c of [{...comment(e),author:'human'},{...comment(e),url:'https://github.com/stranske/example/pull/8#issuecomment-1'},comment(e,{verdict:'PASS'}),comment(e,{provider_verdicts:[]}),comment(e,{verification_event:{...e,event_id:'f'.repeat(64)}})]) assert.equal(completedEvent(e,[c],assessment),false);
});
test('legacy predecessor requires authentic exact-subject terminal, not arbitrary hash',()=> {
 const a=args(),e=buildVerificationEvent(a).verification_event;
 const d={schema:'verifier-corpus-decision/v1',repo:e.repo,pr:e.pr,head_sha:e.head_sha,evaluated_sha:e.evaluated_sha,run_id:'9',run_attempt:'1',ci_failed:false,provider_verdicts:['CONCERNS'],verdict:'NON_PASS'};
 const id=digest({schema:'verification-legacy-event/v1',repo:e.repo,pr:e.pr,head_sha:e.head_sha,evaluated_sha:e.evaluated_sha,run_id:'9',run_attempt:'1'});
 a.evidence.comments={complete:true,records:[{author:'github-actions[bot]',url:'https://github.com/stranske/example/pull/7#issuecomment-9',body:`<!-- verifier-corpus-decision/v1 ${JSON.stringify(d)} -->`}]};a.evidence.event_history={complete:true,records:a.evidence.comments.records};
 assert.equal(buildVerificationEvent({...a,predecessorEventId:id}).predecessor_event_id,id);
 a.evidence.comments.records[0].author='untrusted';
 assert.throws(()=>buildVerificationEvent({...a,predecessorEventId:id}),/not an authenticated/);
});
test('authenticated required CI progress changes material; optional job summaries do not',()=> {
 const a=args();a.ciResults=[{workflow_id:'ci.yml',binding_status:'bound',head_sha:'b'.repeat(40),run_id:9,run_attempt:1,conclusion:'failure'}];
 const failed=buildVerificationEvent(a);
 a.ciResults[0].jobs_summary={optional:'changed'};a.ciResults[0].run_url='transport changed';
 assert.deepEqual(buildVerificationEvent(a),failed);
 a.ciResults[0].run_attempt=2;a.ciResults[0].conclusion='success';
 const passed=buildVerificationEvent(a);
 assert.notEqual(passed.verification_event.event_id,failed.verification_event.event_id);
 assert.equal(passed.verification_event.request_sha256,failed.verification_event.request_sha256);
});

test('same-attempt incomplete dominates pending and terminal regardless arrival order',()=> {
 const {guardExistingEvent}=require('../../.github/scripts/verification_event.js');
 const event=expected.verification_event,terminal=comment(event);
 const state=(status,retry_kind)=>({...terminal,body:`<!-- verifier-event-state/v1 ${JSON.stringify({schema:'verifier-event-state/v1',repo:event.repo,pr:event.pr,head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,run_id:'10',run_attempt:'1',verification_event:event,assessment_identity:assessment,status,retry_kind,retryable:retry_kind==='known_no_evaluation',failure_cause:'retained-original-cause'})} -->`});
 for(const kind of ['known_no_evaluation','recover_existing_evaluation','uncertain_execution']) {
  const incomplete=state('incomplete',kind),pending=state('pending');
  for(const rows of [[terminal,incomplete,pending],[pending,incomplete,terminal],[incomplete,terminal,pending]]) assert.throws(()=>guardExistingEvent(event,rows,assessment),/incomplete/);
 }
 assert.equal(guardExistingEvent(event,[state('incomplete','known_no_evaluation')],assessment),'retry');
 assert.throws(()=>guardExistingEvent(event,[state('pending')],assessment),/pending/);
 assert.doesNotThrow(()=>guardExistingEvent(event,[terminal,state('pending')],assessment));
 assert.doesNotThrow(()=>guardExistingEvent(event,[state('incomplete','uncertain_execution')],{...assessment,provider:'other'}));
});


test('unselected gzip transport progress preserves event while required content changes it',()=>{
 const a=args(),original=buildVerificationEvent(a);
 const row={source:'docs/verification/proof.log.gz',status:'unavailable',necessity:'unknown'};
 a.evidence.gzip_assets=[row];assert.deepEqual(buildVerificationEvent(a),original);
 Object.assign(row,{status:'captured',git_blob_sha:'c'.repeat(40),raw_sha256:'d'.repeat(64),text_sha256:'e'.repeat(64)});
 assert.deepEqual(buildVerificationEvent(a),original);
 row.necessity='required';a.selectors=[{kind:'git_blob',path:row.source}];
 const selected=buildVerificationEvent(a);
 row.text_sha256='f'.repeat(64);
 assert.notEqual(buildVerificationEvent(a).verification_event.event_id,selected.verification_event.event_id);
 row.status='unavailable';assert.throws(()=>buildVerificationEvent(a),/unavailable/);
});
