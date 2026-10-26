'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {createHash}=require('crypto');
const {digest,buildVerificationEvent}=require('../verification_event');
const {produceSeeds}=require('../verifier_correction_seed');
const sha=value=>createHash('sha256').update(value).digest('hex');
function fixture(mode='evaluate') {
  const pull={number:7,body:'Closes #1',merged:true,head:{sha:'a'.repeat(40)},base:{sha:'c'.repeat(40),repo:{full_name:'stranske/Example'}},merge_commit_sha:'b'.repeat(40)};
  const sourceIssue={number:1,node_id:'I_1',body:'issue 1'};
  const assessment={mode,provider:mode==='evaluate'?'anthropic':'',model:'',model2:'',canonical:true};
  const manifest={...buildVerificationEvent({repository:'stranske/example',pull,issues:[sourceIssue],fullDiffBytes:Buffer.from('inert diff'),
    evidence:{},selectors:[],ciResults:[],assessmentIdentity:assessment}),assessment_identity:assessment};
  const row={used_llm:true,verdict:'CONCERNS',concerns:['Reject the exact invalid-input case — preserve the source issue.']};
  const result=mode==='evaluate'?row:{results:[row]};
  const resultBytes=Buffer.from(JSON.stringify(result)+'\n');
  const decision={schema:'verifier-corpus-decision/v1',repo:'stranske/example',pr:'7',head_sha:pull.head.sha,evaluated_sha:pull.merge_commit_sha,
    run_id:'100',run_attempt:'2',ci_failed:false,provider_verdicts:['CONCERNS'],verdict:'NON_PASS',verification_event:manifest.verification_event,assessment_identity:assessment};
  const comments=[{id:43,user:{id:41898282,login:'github-actions[bot]',type:'Bot'},html_url:'https://github.com/stranske/Example/pull/7#issuecomment-43',body:`<!-- verifier-corpus-decision/v1 ${JSON.stringify(decision)} -->`}];
  const stem=mode==='evaluate'?'evaluation':'comparison';
  const execution={schema:`workflows-verifier-${stem}-execution/v1`,mode,status:'completed',decision_available:true,exit_code:0,repository:'stranske/Example',source_run_id:'100',source_run_attempt:'2',outputs:{[`${stem}.json`]:{sha256:sha(resultBytes),bytes:resultBytes.length}}};
  return {manifest,decision,resultBytes,execution,comments,pull,sourceIssue,mode,runId:100,runAttempt:2};
}
test('original seed producer binds actual raw finding/source/comment/event without future IDs or test claims',()=>{
  for(const mode of ['evaluate','compare']) {
    const input=fixture(mode),bundle=produceSeeds(input),seed=bundle.seeds[0];
    assert.equal(seed.original_verifier.run_id,'100');assert.equal(seed.original_verifier.run_attempt,'2');assert.equal(seed.original_verifier.comment_id,'43');
    assert.equal(seed.finding.evidence.sha256,sha('Reject the exact invalid-input case — preserve the source issue.'));
    assert.equal(seed.finding.evidence.ref,mode==='evaluate'?'evaluation.json#/concerns/0':'comparison.json#/results/0/concerns/0');
    assert.equal(seed.source_issue.node_id,'I_1');assert.ok(!Object.hasOwn(seed,'required_tests'));assert.ok(!Object.hasOwn(seed,'original_operation'));assert.ok(!Object.hasOwn(seed,'incumbent'));
    const {bundle_sha256,...payload}=bundle;assert.equal(bundle_sha256,digest(payload));
  }
});
test('producer refuses forged comments, wrong original attempt, source drift and unjoined result bytes',()=>{
  for(const change of [f=>{f.comments[0].user.id=123;},f=>{f.sourceIssue.body='changed';},f=>{f.runAttempt=3;},
    f=>{f.resultBytes=Buffer.from('{}');},f=>{f.execution.status='result_unavailable';},f=>{f.pull.merge_commit_sha='d'.repeat(40);}]) {
    const input=fixture();change(input);assert.throws(()=>produceSeeds(input));
  }
});
test('missing or ambiguous retained source, no explicit raw findings, or unavailable slot stays collection',()=>{
  for(const change of [f=>{f.manifest.request.sources=f.manifest.request.sources.filter(row=>row.kind!=='issue');},f=>{f.manifest.request.sources.push({...f.manifest.request.sources.find(row=>row.kind==='issue'),number:'2'});},f=>{f.comments=[];}]) {
    const input=fixture();change(input);
    input.manifest.verification_event.request_sha256=digest(input.manifest.request);
    const {event_id,...basis}=input.manifest.verification_event;input.manifest.verification_event.event_id=digest(basis);
    input.comments.forEach(comment=>{comment.body=`<!-- verifier-corpus-decision/v1 ${JSON.stringify(input.decision)} -->`;});
    assert.throws(()=>produceSeeds(input),/source issue|terminal comment/);
  }
  const input=fixture(),result={used_llm:true,verdict:'CONCERNS',concerns:[]};input.resultBytes=Buffer.from(JSON.stringify(result)+'\n');input.execution.outputs['evaluation.json']={sha256:sha(input.resultBytes),bytes:input.resultBytes.length};
  assert.throws(()=>produceSeeds(input),/No bounded explicit/);
});
test('identical native terminal duplicates select original lowest immutable comment ID deterministically',()=>{
  const input=fixture();input.comments.unshift({...input.comments[0],id:99,html_url:'https://github.com/stranske/Example/pull/7#issuecomment-99'});
  assert.equal(produceSeeds(input).seeds[0].original_verifier.comment_id,'43');
});
