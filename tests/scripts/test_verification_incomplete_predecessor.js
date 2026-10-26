'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {authenticatePredecessor,buildVerificationEvent,digest}=require('../../.github/scripts/verification_event');
const fixture=require('../fixtures/verification_event/714_complete_then_no_evaluation.json');
const PARENT='e2af8d24132227fc2adbd187f95b9f9517f486900b8a52948dae6325a7ada5d8';
const parse=c=>JSON.parse(c.body.slice(c.body.indexOf('{'),c.body.lastIndexOf('}')+1));
const copy=()=>structuredClone(fixture.records);
const old=parse(fixture.records.at(-1)).verification_event;
const fresh=()=>{const {event_id,...value}=old;value.material_sha256='f'.repeat(64);return {...value,event_id:digest(value)}};
const write=(comment,value)=>{comment.body=`<!-- ${value.schema} ${JSON.stringify(value)} -->`;};
test('actual714 semantic then no-evaluation becomes linear fresh-material parent without reparenting',()=>{
 const records=copy(),before=structuredClone(records);
 const e=fresh();authenticatePredecessor(e,PARENT,{event_history:{complete:true,records}});
 const built=buildVerificationEvent({repository:fixture.repository,pull:{number:714,body:'Offline future complete collector requirement fixture.',head:{sha:e.head_sha},merge_commit_sha:e.evaluated_sha},issues:[],fullDiffBytes:Buffer.from('offline new material fixture'),evidence:{event_history:{complete:true,records}},predecessorEventId:PARENT});
 assert.equal(built.predecessor_event_id,PARENT);assert.notEqual(built.verification_event.event_id,PARENT);
 assert.equal(parse(records.at(-1)).predecessor_event_id,'e46f4a9d09a3499eeb3922a7a9db660b3b58177122ae39eb1d39823517dbc269');
 assert.deepEqual(records,before);
});
for(const change of ['pending','uncertain','false-only','missing-pending','binding','attempt','subject','untrusted','truncated','malformed','invalid-parent','newer-pending','newer-other-event','conflicting-terminal','self-parent'])test(`incomplete predecessor rejects ${change}`,()=>{
 const records=copy();let e=fresh();const pending=records.at(-2),last=records.at(-1),row=parse(last);
 if(change==='pending')records.pop();
 if(change==='uncertain'){row.retry_kind='uncertain_execution';row.retryable=false;write(last,row);}
 if(change==='false-only'){row.failure_cause='execution_payload_missing';write(last,row);}
 if(change==='missing-pending')records.splice(records.length-2,1);
 if(change==='binding'){const v=parse(pending);v.execution_binding.evaluator_step='Wrong step';write(pending,v);}
 if(change==='attempt'){const v=parse(pending);v.run_attempt='2';write(pending,v);}
 if(change==='subject'){row.repo='foreign/repo';write(last,row);}
 if(change==='untrusted')last.author='contributor';
 if(change==='truncated')last.truncated=true;
 if(change==='malformed'){row.verification_event.event_id='0'.repeat(64);write(last,row);}
 if(change==='invalid-parent'){row.predecessor_event_id='invalid';write(last,row);}
 if(change==='newer-pending'||change==='newer-other-event'){
  const newer=structuredClone(pending),value=parse(newer);value.run_id='99999999999';if(change==='newer-other-event')value.verification_event=fresh();write(newer,value);records.push(newer);
 }
 if(change==='conflicting-terminal'){
  const terminal=structuredClone(fixture.records[3]),value=parse(terminal);Object.assign(value,{run_id:row.run_id,verification_event:row.verification_event});write(terminal,value);records.push(terminal);
 }
 if(change==='self-parent')e=old;
 assert.throws(()=>authenticatePredecessor(e,PARENT,{event_history:{complete:true,records}}));
});
test('incomplete history cannot grant parent authority',()=>assert.throws(()=>authenticatePredecessor(fresh(),PARENT,{event_history:{complete:false,records:copy()}})));

test('actual714 identical pending publications deduplicate authority without deleting history',()=>{
 const records=copy(),duplicate=structuredClone(records.at(-2));duplicate.url='https://github.com/stranske/Orchestrator/pull/714#issuecomment-99999999999';records.push(duplicate);
 const before=structuredClone(records);authenticatePredecessor(fresh(),PARENT,{event_history:{complete:true,records}});assert.deepEqual(records,before);assert.equal(records.length,7);
});
test('same714 pending attempt with conflicting duplicate fields cannot establish authority',()=>{
 const records=copy(),duplicate=structuredClone(records.at(-2)),value=parse(duplicate);value.execution_binding.job_name='Different job';write(duplicate,value);records.push(duplicate);
 const before=structuredClone(records);assert.throws(()=>authenticatePredecessor(fresh(),PARENT,{event_history:{complete:true,records}}));assert.deepEqual(records,before);
});

function advisoryRecord(run) {
 const record=structuredClone(fixture.records[3]),row=parse(record);
 const e=fresh();e.material_sha256='d'.repeat(64);const {event_id,...identity}=e;e.event_id=digest(identity);
 Object.assign(row,{run_id:run,verification_event:e,assessment_identity:{...row.assessment_identity,canonical:false}});
 write(record,row);return record;
}
for(const run of ['1','99999999999'])test(`valid advisory run ${run} is neither canonical parent nor veto`,()=>{
 const records=copy(),advisory=advisoryRecord(run);records.push(advisory);const before=structuredClone(records);
 authenticatePredecessor(fresh(),PARENT,{event_history:{complete:true,records}});
 assert.throws(()=>authenticatePredecessor(fresh(),parse(advisory).verification_event.event_id,{event_history:{complete:true,records}}));
 assert.deepEqual(records,before);
});
test('malformed canonical claim is not treated as irrelevant advisory',()=>{
 const records=copy(),record=advisoryRecord('99999999999'),row=parse(record);
 row.assessment_identity.canonical=true;row.assessment_identity.mode='invalid';write(record,row);records.push(record);
 assert.throws(()=>authenticatePredecessor(fresh(),PARENT,{event_history:{complete:true,records}}));
});
test('advisory flag cannot hide malformed event identity',()=>{
 const records=copy(),record=advisoryRecord('99999999999'),row=parse(record);
 row.verification_event.event_id='0'.repeat(64);write(record,row);records.push(record);
 assert.throws(()=>authenticatePredecessor(fresh(),PARENT,{event_history:{complete:true,records}}));
});

for(const run of ['1','99999999999'])test(`valid legacy advisory run ${run} does not veto canonical successor`,()=>{
 const records=copy(),record=advisoryRecord(run),row=parse(record);delete row.verification_event;write(record,row);records.push(record);
 const before=structuredClone(records);authenticatePredecessor(fresh(),PARENT,{event_history:{complete:true,records}});assert.deepEqual(records,before);
 const legacy=digest({schema:'verification-legacy-event/v1',repo:old.repo,pr:old.pr,head_sha:old.head_sha,evaluated_sha:old.evaluated_sha,run_id:row.run_id,run_attempt:row.run_attempt});
 assert.throws(()=>authenticatePredecessor(fresh(),legacy,{event_history:{complete:true,records}}));
});
