'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {authenticatePredecessor,guardExistingEvent,completedEvent,digest}=require('../../.github/scripts/verification_event');
const fixture=require('../fixtures/verification_event/714_same_event_known_no_evaluation.json');
const parse=c=>JSON.parse(c.body.slice(c.body.indexOf('{'),c.body.lastIndexOf('}')+1));
const write=(c,row)=>{c.body=`<!-- ${row.schema} ${JSON.stringify(row)} -->`;};
const EVENT=parse(fixture.records.at(-1)).verification_event;
const PARENT=parse(fixture.records.at(-1)).predecessor_event_id;
const assessment=parse(fixture.records.at(-1)).assessment_identity;
const evidence=records=>({event_history:{complete:true,records}});

test('actual714 same-event no-evaluation retry authenticates its unchanged original parent',()=>{
 const records=structuredClone(fixture.records),before=structuredClone(records);
 authenticatePredecessor(EVENT,PARENT,evidence(records));
 assert.equal(guardExistingEvent(EVENT,records,assessment),'retry');
 assert.deepEqual(records,before);
 assert.equal(records.length,8);
});

for(const kind of ['pending','uncertain','false-only','missing-pending','binding','wrong-parent','omitted-parent','older-uncertain','competing-event','changed-material','conflicting-terminal']) test(`same-event retry preserves ${kind} boundary`,()=>{
 const records=structuredClone(fixture.records);let event=EVENT;
 const pending=records.at(-2),last=records.at(-1),row=parse(last);
 if(kind==='pending')records.pop();
 if(kind==='uncertain'){row.retry_kind='uncertain_execution';row.retryable=false;write(last,row);}
 if(kind==='false-only'){row.failure_cause='execution_payload_missing';write(last,row);}
 if(kind==='missing-pending')records.splice(records.length-2,1);
 if(kind==='binding'){const r=parse(pending);r.execution_binding.evaluator_step='Foreign step';write(pending,r);}
 if(kind==='wrong-parent'){row.predecessor_event_id='d'.repeat(64);write(last,row);}
 if(kind==='omitted-parent'){delete row.predecessor_event_id;write(last,row);}
 if(kind==='older-uncertain'){
   row.retry_kind='uncertain_execution';row.retryable=false;write(last,row);
   for(const old of fixture.records.slice(-2)){const c=structuredClone(old),r=parse(c);r.run_id='40151450966';write(c,r);records.push(c);}
 }
 if(kind==='competing-event'){
   const c=structuredClone(pending),r=parse(c),{event_id,...core}=EVENT;core.material_sha256='f'.repeat(64);
   r.verification_event={...core,event_id:digest(core)};r.run_id='40151450966';write(c,r);records.push(c);
 }
 if(kind==='changed-material') {const {event_id,...core}=EVENT;core.material_sha256='e'.repeat(64);event={...core,event_id:digest(core)};}
 if(kind==='conflicting-terminal'){
   const c=structuredClone(last),r=parse(c);Object.assign(r,{schema:'verifier-corpus-decision/v1',verdict:'PASS',ci_failed:false,provider_verdicts:['PASS']});write(c,r);records.push(c);
 }
 const before=structuredClone(records);
 if(kind==='pending'){
   authenticatePredecessor(event,PARENT,evidence(records));
   assert.throws(()=>guardExistingEvent(event,records,assessment),error=>error.code==='VERIFIER_PENDING_EXECUTION');
 } else assert.throws(()=>authenticatePredecessor(event,PARENT,evidence(records)));
 assert.deepEqual(records,before);
});

test('completed exact child keeps parent authentication but is normal duplicate not provider retry',()=>{
 const records=structuredClone(fixture.records),c=structuredClone(records.at(-1)),r=parse(c);
 Object.assign(r,{schema:'verifier-corpus-decision/v1',run_id:'40151450966',verdict:'PASS',ci_failed:false,provider_verdicts:['PASS']});
 delete r.status;delete r.retry_kind;delete r.retryable;delete r.failure_cause;write(c,r);records.push(c);
 const before=structuredClone(records);authenticatePredecessor(EVENT,PARENT,evidence(records));
 assert.equal(guardExistingEvent(EVENT,records,assessment),undefined);
 assert.equal(completedEvent(EVENT,records,assessment),true);
 assert.deepEqual(records,before);
});
