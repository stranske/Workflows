'use strict';

const fs=require('fs');
const path=require('path');
const {createHash}=require('crypto');
const {canonical,digest,validateEvent}=require('./verification_event');
const {createTokenAwareRetry}=require('./github-api-with-retry');
const {acquireRetainedExecution,readRetainedArchive}=require('./verifier_pending_execution');
const {validateRequest}=require('./verifier_correction_consumer');
const {produceSeeds}=require('./verifier_correction_seed');
const {seedForRequest,effectKey,sourceScopeDigest}=require('./verifier_correction_effects');
const {validateCorrectionDecision}=require('./verifier_correction_decision');
const sha=value=>createHash('sha256').update(value).digest('hex');
const need=(value,reason)=>{if(!value)throw new Error(reason);};
const same=(a,b)=>canonical(a)===canonical(b);

async function collectSubmission({github,transport,repository,actor,current,selector,request,decision,directory='.',loadQualification=null,authenticateDecision=null,codingBudgetVariable=null}) {
  validateRequest(request);
  const event=validateEvent(selector.verification_event);
  need(selector.schema==='closer-correction-selector/v1' && selector.request_sha256===request.request_sha256
    && event.repo===repository && request.target.repository===repository
    && same(event,request.original_verifier.verification_event),'Correction submission selector/subject mismatch');
  await transport.canonicalRun(current.run_id,current.run_attempt,'.github/workflows/agents-verify-to-new-pr.yml');
  const [owner,repo]=repository.split('/');
  const {withRetry}=await createTokenAwareRetry({github,env:{},tokenRegistry:{isInitialized:()=>false},task:'correction-submission-read'});
  const read=async(resource,method,args)=>(await withRetry(client=>client.rest[resource][method]({owner,repo,...args,request:{timeout:15000,retries:0}}),{maxRetries:2,initialDelay:250,maxDelay:1000})).data;
  need(typeof actor==='string' && actor.length>0,'Authenticated dispatch actor unavailable');
  const permission=await read('repos','getCollaboratorPermissionLevel',{username:actor});
  need(['admin','maintain','write'].includes(permission.permission) && permission.user?.login?.toLowerCase()===actor.toLowerCase(),
    'Authenticated dispatch actor lacks existing write authority');
  const origin=await acquireRetainedExecution({github,event,assessment:selector.assessment_identity,
    selector:{run_id:selector.run_id,run_attempt:selector.run_attempt,artifact_id:selector.artifact_id},
    currentRun:current.run_id,directory,pullRequestTargetOrigin:true});
  // directory is a trusted host workspace, never request/selector data.
  const archive=fs.readFileSync(path.join(directory,'verification-recovery-source.zip'));
  need(sha(archive)===origin.archive_sha256,'Original verifier archive changed after authentication');
  const files=readRetainedArchive(archive),bundle=JSON.parse(files.get('closer-correction-seeds.json') || 'null');
  need(bundle?.schema==='closer-correction-seed-bundle/v1' && Array.isArray(bundle.seeds),'Original trusted correction seed producer unavailable');
  const seed=seedForRequest(request);
  need(bundle.seeds.filter(row=>same(row,seed)).length===1,'Declared request is not one exact original raw finding');
  const manifest=JSON.parse(files.get('verification-event-manifest.json') || 'null');
  need(manifest && same(manifest.verification_event,event),'Original seed manifest mismatch');
  const [pull,sourceIssue,comment]=await Promise.all([
    read('pulls','get',{pull_number:Number(event.pr)}),read('issues','get',{issue_number:Number(request.source_issue.number)}),
    read('issues','getComment',{comment_id:Number(request.original_verifier.comment_id)}),
  ]);
  const matches=[...String(comment.body).matchAll(/<!-- verifier-corpus-decision\/v1 (\{[^\n]+\}) -->/g)];
  need(matches.length===1,'Original terminal decision comment ambiguous');
  const originalDecision=JSON.parse(matches[0][1]),mode=selector.assessment_identity.mode,stem=mode==='evaluate'?'evaluation':'comparison';
  const reproduced=produceSeeds({manifest,decision:originalDecision,resultBytes:files.get(`${stem}.json`),
    execution:JSON.parse(files.get(`${stem}-execution.json`) || 'null'),comments:[comment],pull,sourceIssue,mode,
    runId:selector.run_id,runAttempt:selector.run_attempt});
  need(same(reproduced,bundle),'Original raw finding seed does not reproduce from authenticated bytes');
  const originalOutput=JSON.parse(files.get(`${stem}.json`));
  const rawRows=mode==='evaluate'?[originalOutput]:originalOutput.results;
  const rawFindings=new Map();
  rawRows.forEach((row,providerIndex)=>row.concerns.forEach((text,index)=>rawFindings.set(
    mode==='evaluate'?`evaluation.json#/concerns/${index}`:`comparison.json#/results/${providerIndex}/concerns/${index}`,text)));
  const findingText=rawFindings.get(seed.finding.evidence.ref);
  need(typeof findingText==='string' && sha(findingText)===seed.finding.evidence.sha256,'Exact original finding text unavailable');
  // Physical existing selectors are fetched only at the exact declared immutable
  // source commit. Specification text is data, never executed as a test command.
  for(const test of request.required_tests)if(test.kind==='existing_selector') {
    need(/^git:[a-f0-9]{40}$/.test(test.source_ref)
      && [request.target.head_sha,request.target.merge_sha].includes(test.source_ref.slice(4)), 'Existing test needs exact subject commit');
    const file=await read('repos','getContent',{path:test.path,ref:test.source_ref.slice(4)});
    need(!Array.isArray(file) && file.type==='file' && file.encoding==='base64' && typeof file.content==='string'
      && sha(Buffer.from(file.content,'base64'))===test.file_sha256,'Physical required-test file hash mismatch');
  }
  let qualification=null;
  if(typeof loadQualification==='function') {
    try {qualification=await loadQualification(decision?.profile);}
    catch(error) {qualification={status:'owned_unknown',reason:String(error.message)};}
  }
  // Role eligibility is not proof that this profile produced these bytes.
  // The trusted Core retained-I/O verifier is a separate host dependency; no
  // caller JSON evidence_ref or qualification record can replace it.
  let decisionProof=null;
  if(typeof authenticateDecision==='function') {
    try {decisionProof=await authenticateDecision({decision,qualification,request,seed,bundle});}
    catch(error) {decisionProof={status:'owned_unknown',reason:String(error.message)};}
  }
  const decisionClassification=decisionProof?.status==='authenticated' && decisionProof.decision_sha256===digest(decision)
    && decisionProof.profile_identity_sha256===qualification?.profile_identity_sha256
    && typeof decisionProof.profile_identity_sha256==='string'
    ? validateCorrectionDecision({request,seed,bundle,decision,qualification})
    : {status:'owned_unknown',reason:'authenticated_retained_classification_output_unavailable',
      act_authorized:false,source_closure_authorized:false};
  const codingBudget=require('./verifier_correction_consumer').codingBudgetFromVariable(codingBudgetVariable,request);
  const classification=decisionClassification.status==='admitted' && !codingBudget
    ? {status:'owned_unknown',reason:'authenticated_coding_policy_budget_unconfigured',act_authorized:false,source_closure_authorized:false}
    : decisionClassification;
  const context={schema:'closer-correction-admitted/v1',status:classification.status,request,seed,bundle,finding_text:findingText,
    decision:decision || null,decision_proof:decisionProof,decision_classification:decisionClassification,classification,qualification,original_proof:origin,dispatch_actor:actor,dispatch_permission:permission.permission,
    collector:{repository,run_id:current.run_id,run_attempt:current.run_attempt},
    effect_key:effectKey(seed),source_scope_digest:sourceScopeDigest(seed),coding_budget:codingBudget};
  return {...context,context_sha256:digest(context)};
}
async function loadReviewedQualification({github,profile,clock=()=>new Date()}) {
  // Caller qualification_ref URLs and records are never request destinations or
  // authority. The only production source is Core's reviewed default registry.
  const owner='stranske',repo='Orchestrator',sourcePath='src/closer_role_qualification.py';
  const {withRetry}=await createTokenAwareRetry({github,env:{},tokenRegistry:{isInitialized:()=>false},task:'correction-core-qualification-read'});
  const read=async(method,args)=>(await withRetry(client=>client.rest.repos[method]({owner,repo,...args,request:{timeout:15000,retries:0}}),{maxRetries:2,initialDelay:250,maxDelay:1000})).data;
  try {
    need(profile?.role==='closer_interpret' && typeof profile.id==='string','Bounded classification profile unavailable');
    const repository=await read('get',{});
    need(repository.full_name?.toLowerCase()==='stranske/orchestrator' && repository.default_branch==='main','Reviewed qualification source/ref unavailable');
    const head=await read('getCommit',{ref:'main'});
    need(typeof head.sha==='string' && /^[a-f0-9]{40}$/.test(head.sha),'Qualification commit unavailable');
    const file=await read('getContent',{path:sourcePath,ref:head.sha});
    need(file.type==='file' && file.encoding==='base64' && typeof file.content==='string' && file.content.length<=1398104,'Qualification source blob unavailable');
    const bytes=Buffer.from(file.content,'base64');
    need(bytes.length<=1048576 && createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex')===file.sha,'Qualification Git blob integrity mismatch');
    const {execFileSync}=require('child_process');
    const result=JSON.parse(execFileSync('python3',['-I',path.join(__dirname,'verifier_correction_profile.py')],{
      input:JSON.stringify({source:bytes.toString('utf8'),profile_id:profile.id,now:clock().getTime()/1000}),encoding:'utf8',timeout:10000,maxBuffer:2097152,
    }));
    const source={repository:'stranske/Orchestrator',path:sourcePath,ref:'main',commit:head.sha,git_blob_sha:file.sha,sha256:sha(bytes)};
    if(result.status!=='qualified')return {...result,source};
    return {...result,qualification_ref:`github:stranske/Orchestrator:${sourcePath}#ROLE_QUALIFICATIONS/${result.qualification_id}`,
      qualification_sha256:digest(result.record),source};
  } catch(error) {return {status:'owned_unknown',reason:String(error.message)};}
}
module.exports={collectSubmission,loadReviewedQualification};
