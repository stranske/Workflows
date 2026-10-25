'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('fs');
const path=require('path');
const {terminalCorrelation}=require('../../.github/scripts/verification_event.js');
const event=require('../fixtures/verification_event/canonical.json').verification_event;
const assessment={mode:'evaluate',provider:'anthropic',model:'',model2:'',canonical:true};
const decision={schema:'verifier-corpus-decision/v1',repo:event.repo,pr:event.pr,head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,run_id:'100',run_attempt:'2',ci_failed:false,provider_verdicts:['CONCERNS'],verdict:'NON_PASS',verification_event:event,assessment_identity:assessment};
const source={author:'github-actions[bot]',url:`https://github.com/${event.repo}/pull/${event.pr}#issuecomment-43`,body:`<!-- verifier-corpus-decision/v1 ${JSON.stringify(decision)} -->`};
const manifest=()=>({verification_event:event,verification_request_basis:'e'.repeat(64),request_correlation:terminalCorrelation({event,comments:[source],assessment,basis:'e'.repeat(64),runId:'800',runAttempt:'1'})});
const workflow=fs.readFileSync(path.join(__dirname,'../../.github/workflows/reusable-agents-verifier.yml'),'utf8');
const block=workflow.split('      - name: Correlate an already completed verification event\n')[1].split('\n      - name:')[0];
const script=block.split('          script: |\n')[1].split('\n').map(line=>line.startsWith('            ')?line.slice(12):line).join('\n');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
async function execute(value){
 const posts=[];
 const requireStub=name=>name==='fs'?{readFileSync:()=>JSON.stringify(value)}:{createTokenAwareRetry:async()=>({withRetry:fn=>fn()})};
 await new AsyncFunction('require','github','core','context','process',script)(requireStub,{rest:{issues:{createComment:async args=>posts.push(args)}}},{},{runId:800,repo:{owner:'stranske',repo:'example'}},{env:{GITHUB_RUN_ATTEMPT:'1'}});
 return posts;
}
test('actual reusable workflow duplicate step publishes only inert reference with original result identity',async()=>{
 const value=manifest(),posts=await execute(value);
 assert.equal(posts.length,1);assert.equal(posts[0].issue_number,7);
 const match=posts[0].body.match(/^<!-- verifier-request-correlation\/v1 (.+) -->$/);assert.ok(match);
 assert.deepEqual(JSON.parse(match[1]),value.request_correlation);
 assert.equal(posts[0].body.includes('verifier-corpus-decision/v1'),false);
});
test('actual duplicate publication refuses mismatched basis, event or publication execution',async()=>{
 for(const corrupt of [v=>v.request_correlation.verification_request_basis='f'.repeat(64),v=>v.request_correlation.verification_event={...event,event_id:'f'.repeat(64)},v=>v.request_correlation.correlation_run_id='801']){
  const value=manifest();corrupt(value);await assert.rejects(()=>execute(value),/Invalid collector/);
 }
});

test('shared fixture binds exact canonical UTF-8 decision and string execution IDs',()=>{
 const {canonical,digest}=require('../../.github/scripts/verification_event.js');
 const fixture=require('../fixtures/verification_event/request_correlation.json');
 assert.equal(canonical(fixture.decision),fixture.canonical_decision);
 assert.equal(digest(fixture.decision),fixture.correlation.result_decision_sha256);
 for(const field of ['result_run_id','result_run_attempt','correlation_run_id','correlation_run_attempt']) assert.equal(typeof fixture.correlation[field],'string');
 assert.equal(canonical(fixture.unicode_canonical_example.value),fixture.unicode_canonical_example.canonical);
 assert.equal(digest(fixture.unicode_canonical_example.value),fixture.unicode_canonical_example.sha256);
});
