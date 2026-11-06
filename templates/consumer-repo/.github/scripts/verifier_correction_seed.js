'use strict';

// Original verifier evidence only. Future Closer operation/hold/test decisions
// are deliberately absent from this producer's immutable output.
const fs=require('fs');
const {createHash}=require('crypto');
const {canonical,digest,validateEvent,completedEvent}=require('./verification_event');
const {nativeBody}=require('./verifier_correction_consumer');
const {createTokenAwareRetry}=require('./github-api-with-retry');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const requireThat=(value,message)=>{if(!value)throw new Error(message);};
const commit=value=>typeof value==='string' && /^[a-f0-9]{40}$/.test(value);

function produceSeeds({manifest,decision,resultBytes,execution,comments,pull,sourceIssue,mode,runId,runAttempt}) {
  requireThat(['evaluate','compare'].includes(mode),'Unsupported correction seed mode');
  const event=validateEvent(manifest.verification_event),stem=mode==='evaluate'?'evaluation':'comparison';
  requireThat(digest(manifest.request)===event.request_sha256 && digest(manifest.material)===event.material_sha256,
    'Original event material/request mismatch');
  requireThat(decision?.schema==='verifier-corpus-decision/v1' && decision.verdict==='NON_PASS'
    && canonical(decision.verification_event)===canonical(event)
    && String(decision.run_id)===String(runId) && String(decision.run_attempt)===String(runAttempt),
  'Seed requires the actual original NON_PASS decision');
  requireThat(Buffer.isBuffer(resultBytes) && resultBytes.length>0 && resultBytes.length<=8388608,
    'Original result bytes unavailable or exceed bound');
  const output=execution?.outputs?.[`${stem}.json`];
  requireThat(execution?.schema===`workflows-verifier-${stem}-execution/v1` && execution.mode===mode
    && execution.status==='completed' && execution.decision_available===true && execution.exit_code===0
    && String(execution.repository).toLowerCase()===event.repo
    && String(execution.source_run_id)===String(runId) && String(execution.source_run_attempt)===String(runAttempt)
    && output?.sha256===sha(resultBytes) && output.bytes===resultBytes.length && output.truncated!==true
    && output.original_complete!==false && !output.retention_error_type,
  'Original execution receipt does not join the retained result');
  const sources=manifest.request.sources.filter(row=>row.kind==='issue');
  requireThat(sources.length===1 && sources[0].repository===event.repo,
    'Correction seed needs one unambiguous retained source issue');
  requireThat(sourceIssue && !sourceIssue.pull_request && String(sourceIssue.number)===sources[0].number
    && typeof sourceIssue.node_id==='string' && sourceIssue.node_id.length>0
    && sha(nativeBody(sourceIssue.body))===sources[0].body_sha256,
  'Current source issue differs from original retained source');
  requireThat(pull?.merged===true && String(pull.number)===event.pr
    && pull.head?.sha===event.head_sha && pull.merge_commit_sha===event.evaluated_sha
    && commit(pull.base?.sha) && pull.base?.repo?.full_name?.toLowerCase()===event.repo,
  'Original verifier subject differs from current merged PR');
  const eligible=[];
  for(const comment of comments) {
    if(comment.user?.id!==41898282 || comment.user?.login!=='github-actions[bot]' || comment.user?.type!=='Bot'
      || !Number.isSafeInteger(comment.id) || comment.id<1 || typeof comment.body!=='string')continue;
    const matches=[...comment.body.matchAll(/<!-- verifier-corpus-decision\/v1 (\{[^\n]+\}) -->/g)];
    if(matches.length!==1)continue;
    try {
      if(digest(JSON.parse(matches[0][1]))===digest(decision)
        && completedEvent(event,[{author:comment.user.login,url:comment.html_url,body:comment.body}],manifest.assessment_identity))eligible.push(comment);
    } catch { /* Caller text/other bot reports are not the original terminal. */ }
  }
  requireThat(eligible.length>0,'Actual original terminal comment unavailable');
  // Identical decision duplicates are not new evaluations. Select the immutable
  // lowest API comment ID deterministically; never mint an original run identity.
  eligible.sort((a,b)=>a.id-b.id);const comment=eligible[0];
  const payload=JSON.parse(resultBytes),rows=mode==='evaluate'?[payload]:payload.results;
  requireThat(Array.isArray(rows) && rows.length>0 && rows.length<=20,'Original provider result inventory unavailable');
  requireThat(canonical(rows.map(row=>row.verdict))===canonical(decision.provider_verdicts),'Original slot verdicts differ from admitted decision');
  const seeds=[];
  rows.forEach((row,providerIndex)=>{
    requireThat(row?.used_llm===true && !row.error && ['PASS','CONCERNS','FAIL'].includes(row.verdict),
      'Original result includes an unavailable or nonproduction slot');
    requireThat(Array.isArray(row.concerns) && row.concerns.length<=100,'Original raw finding list unavailable');
    row.concerns.forEach((concern,index)=>{
      requireThat(typeof concern==='string' && Buffer.byteLength(concern)>0 && Buffer.byteLength(concern)<=65536,
        'Original raw finding is not a bounded string');
      const ref=mode==='evaluate'?`evaluation.json#/concerns/${index}`:`comparison.json#/results/${providerIndex}/concerns/${index}`;
      seeds.push({schema:'closer-correction-seed/v1',target:{repository:event.repo,pr:event.pr,head_sha:event.head_sha,
        base_sha:pull.base.sha,merge_sha:event.evaluated_sha},source_issue:{number:sources[0].number,node_id:sourceIssue.node_id,body_sha256:sources[0].body_sha256},
      original_verifier:{verification_event:event,run_id:String(runId),run_attempt:String(runAttempt),comment_id:String(comment.id),
        comment_sha256:sha(comment.body),decision_sha256:digest(decision)},finding:{id:`raw-${digest({ref,sha256:sha(concern)})}`,
        evidence:{ref,sha256:sha(concern)}},scope:'substantive_implementation'});
    });
  });
  requireThat(seeds.length>0 && seeds.length<=100,'No bounded explicit original finding; collection only');
  const bundle={schema:'closer-correction-seed-bundle/v1',verification_event:event,assessment_identity:manifest.assessment_identity,
    result_sha256:sha(resultBytes),seeds};
  return {...bundle,bundle_sha256:digest(bundle)};
}

async function retainSeeds({github,manifest,decision,mode,runId,runAttempt,directory='.'}) {
  const path=require('path'),event=validateEvent(manifest.verification_event),[owner,repo]=event.repo.split('/');
  const {withRetry}=await createTokenAwareRetry({github,env:{},tokenRegistry:{isInitialized:()=>false},task:'correction-seed-read'});
  const read=async(resource,method,args)=>(await withRetry(client=>client.rest[resource][method]({owner,repo,...args,request:{timeout:15000,retries:0}}),
    {maxRetries:2,initialDelay:250,maxDelay:1000})).data;
  const sources=manifest.request?.sources?.filter(row=>row.kind==='issue') || [];
  requireThat(sources.length===1,'Original retained source issue is ambiguous');
  const pull=await read('pulls','get',{pull_number:Number(event.pr)}),sourceIssue=await read('issues','get',{issue_number:Number(sources[0].number)});
  const comments=[];let complete=false;
  for(let page=1;page<=10;page++) {
    const rows=await read('issues','listComments',{issue_number:Number(event.pr),per_page:100,page});
    requireThat(Array.isArray(rows),'Original comment inventory unavailable');comments.push(...rows);
    if(rows.length<100){complete=true;break;}
  }
  requireThat(complete,'Original comment inventory exceeds bound');
  const stem=mode==='evaluate'?'evaluation':'comparison';
  // directory is the trusted verifier workspace, never a workflow request field.
  const result=produceSeeds({manifest,decision,resultBytes:fs.readFileSync(path.join(directory,`${stem}.json`)),
    execution:JSON.parse(fs.readFileSync(path.join(directory,`${stem}-execution.json`))),comments,pull,sourceIssue,mode,runId,runAttempt});
  fs.writeFileSync(path.join(directory,'closer-correction-seeds.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
  return result;
}
module.exports={produceSeeds,retainSeeds};
