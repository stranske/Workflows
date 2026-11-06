'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),{createHash}=require('crypto');
const {loadReviewedQualification}=require('../verifier_correction_collector');
const source=fs.readFileSync(path.join(__dirname,'../../../tests/fixtures/verifier_correction/core-role-authority.txt'));
function fixture() {
 const calls=[],state={source,sha:createHash('sha1').update(`blob ${source.length}\0`).update(source).digest('hex'),branch:'main',repo:'stranske/Orchestrator'};
 const methods={get:()=>({full_name:state.repo,default_branch:state.branch}),getCommit:()=>({sha:'a'.repeat(40)}),
 getContent:()=>({type:'file',encoding:'base64',content:state.source.toString('base64'),sha:state.sha})};
 const github={rest:{repos:Object.fromEntries(Object.entries(methods).map(([name,fn])=>[name,async args=>{calls.push({name,args});return {data:fn()};}]))}};
 return {github,calls,state,profile:{id:'synthetic-ordinary',role:'closer_interpret',qualification_ref:'https://untrusted.invalid/registry',records:{spoof:true}}};
}
test('production source is fixed reviewed main at exact Git commit/blob; caller registry URLs are never fetched',async()=>{
 const f=fixture(),result=await loadReviewedQualification(f);assert.equal(result.status,'owned_unknown');assert.match(result.reason,/missing or ambiguous/);
 assert.equal(result.source.repository,'stranske/Orchestrator');assert.equal(result.source.commit,'a'.repeat(40));
 assert.deepEqual(f.calls.map(row=>row.name),['get','getCommit','getContent']);
 for(const {args} of f.calls)assert.equal(`${args.owner}/${args.repo}`,'stranske/Orchestrator');
 assert.equal(f.calls[1].args.ref,'main');assert.equal(f.calls[2].args.ref,'a'.repeat(40));
 assert.equal(f.calls[2].args.path,'src/closer_role_qualification.py');
});
test('wrong reviewed branch, blob bytes, foreign repository and unsupported reader stay UNKNOWN',async()=>{
 for(const change of [f=>{f.state.branch='unreviewed';},f=>{f.state.repo='attacker/Orchestrator';},f=>{f.state.sha='b'.repeat(40);},
 f=>{f.state.source=Buffer.from('raise RuntimeError("never execute")\nROLE_QUALIFICATIONS={}\n');f.state.sha=createHash('sha1').update(`blob ${f.state.source.length}\0`).update(f.state.source).digest('hex');}]) {
  const f=fixture();change(f);assert.equal((await loadReviewedQualification(f)).status,'owned_unknown');
 }
});
test('missing bounded classification identity cannot trigger a source lookup',async()=>{
 const f=fixture();f.profile.role='strong_criterion_adjudication';assert.equal((await loadReviewedQualification(f)).status,'owned_unknown');assert.equal(f.calls.length,0);
});
