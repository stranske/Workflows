'use strict';

// Correlation on the EXISTING auto-pilot path. A started receipt attests workflow
// admission after its existing gates; it does not claim a provider has started.
const {canonical,digest}=require('./verification_event');
const {validateRequest}=require('./verifier_correction_consumer');
const {seedForRequest,effectKey,validateLedger,validateOwnership,checkFreshFacts,issueIdentity}=require('./verifier_correction_effects');
const {validateCorrectionDecision}=require('./verifier_correction_decision');
const {artifactName}=require('./verifier_correction_artifacts');
const {redispatchForceStep,normalizeForceStep,NEXT_STEPS}=require('./auto_pilot_transitions');
const same=(a,b)=>canonical(a)===canonical(b);
const need=(value,reason)=>{if(!value)throw new Error(reason);};
const exact=(value,keys)=>value && typeof value==='object' && !Array.isArray(value)
  && same(Object.keys(value).sort(),keys.split(' ').sort());
const proofIdentity=proof=>({run_id:proof.run_id,run_attempt:proof.run_attempt,artifact_id:proof.artifact_id,
 archive_sha256:proof.archive_sha256,member_sha256:proof.member_sha256});
const seal=value=>({...value,content_sha256:digest(value)});
function unseal(bytes,schema) {
 const value=JSON.parse(bytes),{content_sha256,...payload}=value;
 need(value.schema===schema && content_sha256===digest(payload),'Correction continuation content digest/schema mismatch');
 return value;
}
function lineageKey(selector) {
 return digest({schema:'closer-correction-continuation-lineage/v1',effect_key:selector.effect_key,
 request_sha256:selector.request_sha256,intent:proofIdentity(selector.intent),
 parent_dispatch:selector.parent_dispatch?proofIdentity(selector.parent_dispatch):null});
}
async function authenticateContinuation({transport,selector,issueNumber,selectedStep,forceStep=selectedStep,current,producedPull=null,loadQualification,collectFreshFacts,clock=()=>new Date()}) {
 need(exact(selector,'schema repository collector intent request_sha256 effect_key issue parent_dispatch')
   && selector.schema==='closer-correction-continuation-selector/v1','Unexpected correction continuation selector');
 need(typeof forceStep==='string' && (forceStep==='auto'
   ? selectedStep==='auto' || Object.values(NEXT_STEPS).includes(selectedStep)
   : normalizeForceStep(forceStep)===selectedStep),'Actual selected step differs from requested native directive');
 need(typeof loadQualification==='function' && typeof collectFreshFacts==='function','Trusted correction admission readers unavailable');
 await transport.canonicalRun(current.run_id,current.run_attempt,'.github/workflows/agents-auto-pilot.yml');
 const admitted=await transport.load(selector.collector,'admitted',artifactName('admitted',selector.collector.run_id,selector.collector.run_attempt));
 const context=JSON.parse(admitted.bytes),{context_sha256,...payload}=context;
 need(context.schema==='closer-correction-admitted/v1' && context.status==='admitted'
   && digest(payload)===context_sha256 && context.classification?.status==='admitted','Collector did not authenticate correction admission');
 const request=validateRequest(context.request),seed=seedForRequest(request),key=effectKey(seed);
 need(same(seed,context.seed) && context.effect_key===key && selector.effect_key===key
   && selector.repository===request.target.repository && selector.request_sha256===request.request_sha256
   && selector.issue.number===String(issueNumber),'Continuation collector/request/issue scope differs');
 need(context.collector.repository===admitted.proof.repository && context.collector.run_id===admitted.proof.run_id
   && context.collector.run_attempt===admitted.proof.run_attempt,'Collector context producer differs from actual artifact');
 const qualification=await loadQualification(context.decision?.profile);
 need(context.decision_proof?.status==='authenticated'
   && context.decision_proof.decision_sha256===digest(context.decision)
   && typeof context.decision_proof.profile_identity_sha256==='string'
   && context.decision_proof.profile_identity_sha256===qualification?.profile_identity_sha256
   && validateCorrectionDecision({...context,qualification}).status==='admitted',
 'Retained decision origin or current bounded classification qualification unavailable');
 const intent=await transport.load(selector.intent,'ledger',artifactName('ledger',selector.intent.run_id,selector.intent.run_attempt,`${key}-r${selector.intent.revision}`));
 const records=intent.bytes.toString('utf8').trim().split('\n').map(row=>JSON.parse(row));
 const journal=validateLedger({revision:selector.intent.revision,records},key),last=journal.records.at(-1);
 need(last?.kind==='intent' && last.phase==='autopilot_dispatch' && last.request_sha256===request.request_sha256
   && last.consumer.run_id===String(intent.proof.run_id) && last.consumer.run_attempt===String(intent.proof.run_attempt),
 'Actual original auto-pilot dispatch intent unavailable');
 need(clock().getTime()<Date.parse(request.original_operation.deadline),'Original requester deadline exhausted before workflow admission');
 const ownership=validateOwnership(last.ownership,seed);
 need(ownership.kind!=='unknown','Original corrective ownership is unknown');
 const retained=ownership.kind==='no_incumbent'?journal.records.find(row=>row.kind==='issue_confirmed')?.issue:request.incumbent.issue;
 need(retained && same(retained,selector.issue),'Continuation differs from immutable original issue/node/body binding');
 let currentIssue=selector.issue,ownedPull=null,formatPauseReference=null;
 if(selector.parent_dispatch===null)need(forceStep==='optimize' && selectedStep==='optimize','Initial correction continuation must enter existing optimize step');
 else {
   const parent=selector.parent_dispatch;
   need(['redispatch','formatredispatch'].includes(parent.kind),'Unknown correction redispatch producer');
   const loaded=await transport.load(parent,parent.kind,artifactName(parent.kind,parent.run_id,parent.run_attempt));
   const dispatch=unseal(loaded.bytes,'closer-correction-redispatch/v1');
   need(dispatch.request_sha256===request.request_sha256 && dispatch.effect_key===key && same(dispatch.issue,selector.issue)
     && dispatch.next_step===forceStep && same(dispatch.intent,proofIdentity(intent.proof)), 'Redispatch changed original request/issue/step');
   need(dispatch.observed_issue?.number===selector.issue.number && dispatch.observed_issue.node_id===selector.issue.node_id,
     'Redispatch cannot replace immutable issue/node');
   currentIssue=dispatch.observed_issue;
   if(parent.kind==='formatredispatch') {
    need(dispatch.owned_pause,'Exact native formatter pause proof unavailable');
    const pause=await transport.load(dispatch.owned_pause,'formatpause',artifactName('formatpause',parent.run_id,parent.run_attempt));
    const value=unseal(pause.bytes,'closer-correction-format-pause/v1');
    need(value.request_sha256===request.request_sha256 && value.effect_key===key && same(value.issue,currentIssue), 'Formatter wakeup pause scope changed');
    formatPauseReference={proof:dispatch.owned_pause,started:value.started};
   }
   if(dispatch.owned_pr)ownedPull=await loadOwnedPull({transport,proof:dispatch.owned_pr,request,issue:selector.issue});
   const started=await transport.load(dispatch.started,'started',artifactName('started',parent.run_id,parent.run_attempt));
   const start=unseal(started.bytes,'closer-correction-started/v1');
   need(start.run_id===parent.run_id && start.run_attempt===parent.run_attempt && start.effect_key===key
     && start.request_sha256===request.request_sha256 && same(start.issue,selector.issue)
     && (parent.kind==='formatredispatch'?forceStep==='format' && start.selected_step==='format'
       :redispatchForceStep(start.selected_step)===forceStep),'Actual parent started receipt does not bind redispatch');
 }
 if(producedPull) {
  need(producedPull.run_id===current.run_id && producedPull.run_attempt===current.run_attempt && selectedStep==='create-pr',
   'New owned PR proof must come from this actual create-pr execution');
  ownedPull=await loadOwnedPull({transport,proof:producedPull,request,issue:selector.issue});
 }
 const facts=await collectFreshFacts(request,{ownedPull,createdIssue:ownership.kind==='no_incumbent'?currentIssue:null});
 const fresh=validateOwnership(facts.ownership,seed);
 need(fresh.kind===ownership.kind && fresh.kind!=='unknown' && (fresh.kind!=='existing' || same(fresh.incumbent,{...ownership.incumbent,issue:currentIssue})),
 'Current correction ownership is unknown or changed');
 let ownedFormatPauseIssue=null;
 if(current.job==='format-pause-wakeup' && selector.parent_dispatch?.kind==='formatredispatch'
   && selector.parent_dispatch.run_id===current.run_id && selector.parent_dispatch.run_attempt===current.run_attempt
   && facts.incumbentIssue?.labels?.some(label=>(typeof label==='string'?label:label.name)==='agents:auto-pilot-pause')) {
   need(formatPauseReference,'Owned formatter pause reference unavailable');
   const started=await transport.load(formatPauseReference.started,'started',artifactName('started',current.run_id,current.run_attempt));
   await validateFormatPause({transport,proof:formatPauseReference.proof,selector,started:unseal(started.bytes,'closer-correction-started/v1')});
   ownedFormatPauseIssue=currentIssue;
 }
 checkFreshFacts(request,facts,{ownedFormatPauseIssue,ownership:fresh,createdIssue:ownership.kind==='no_incumbent'?currentIssue:null,
   incumbentIssue:ownership.kind==='existing'?currentIssue:null});
 const unrelated=facts.workInventory.openPullRequests.filter(pull=>!ownedPull || pull.id!==ownedPull.pull.id
   || pull.node_id!==ownedPull.pull.node_id || String(pull.number)!==ownedPull.pull.number
   || pull.head?.ref!==ownedPull.pull.head_ref || pull.base?.ref!==ownedPull.pull.base_ref
   || pull.head?.repo?.full_name?.toLowerCase()!==ownedPull.pull.head_repository
   || pull.base?.repo?.full_name?.toLowerCase()!==ownedPull.pull.base_repository
   || pull.head?.sha!==ownedPull.observed_head_sha);
 need(!unrelated.length && !facts.workInventory.continuations.length,'Competing continuation already owns correction');
 if(ownedPull)need(facts.workInventory.openPullRequests.filter(pull=>pull.id===ownedPull.pull.id).length===1,
  'Native owned PR is missing from complete current inventory');
 return {request,seed,selector,finding_text:context.finding_text,owned_pull:ownedPull,observed_issue:currentIssue,ownership:fresh,force_step:forceStep,selected_step:selectedStep,lineage_key:lineageKey(selector),collector:admitted.proof,intent:intent.proof};
}
async function recordStarted({transport,admission,current,selectedStep,shouldContinue,cyclesExceeded,rateLimited,observeLineage,recheckAdmission,clock}) {
 need(shouldContinue===true && cyclesExceeded===false && rateLimited===false
   && Object.values(NEXT_STEPS).includes(selectedStep) && selectedStep!=='done' && selectedStep===admission.selected_step,'Existing auto-pilot gates did not admit workflow execution');
 need(typeof observeLineage==='function' && typeof recheckAdmission==='function' && typeof clock==='function','Authenticated continuation history/time unavailable');
 need(clock().getTime()<Date.parse(admission.request.original_operation.deadline),'Original requester deadline exhausted');
 const prior=await observeLineage(admission);
 need(Array.isArray(prior) && prior.length===0,'Original continuation is started or its outcome is unknown; do not repeat');
 need(clock().getTime()<Date.parse(admission.request.original_operation.deadline),'Original deadline exhausted during history read');
 const payload={schema:'closer-correction-started/v1',request_sha256:admission.request.request_sha256,
 effect_key:admission.selector.effect_key,issue:admission.selector.issue,observed_issue:admission.observed_issue,lineage_key:admission.lineage_key,
 run_id:current.run_id,run_attempt:current.run_attempt,selected_step:selectedStep,collector:admission.collector,
 intent:proofIdentity(admission.intent),owned_pr:admission.owned_pull?.proof || null,parent_dispatch:admission.selector.parent_dispatch,
 execution_kind:'workflow_admission',provider_execution:'not_attested',act_authorized:false,source_closure_authorized:false};
 const receipt=seal(payload),proof=await transport.publish('started',Buffer.from(JSON.stringify(receipt)+'\n'));
 const fresh=await recheckAdmission();
 need(fresh?.lineage_key===admission.lineage_key && fresh.request?.request_sha256===admission.request.request_sha256
  && fresh.selected_step===selectedStep && clock().getTime()<Date.parse(admission.request.original_operation.deadline),
 'Workflow admission changed during retained start readback');
 need(proof.run_id===current.run_id && proof.run_attempt===current.run_attempt,'Started artifact is not the actual current execution');
 return {receipt,proof};
}
async function retainRedispatch({transport,selector,startedProof,nextStep,observeIssue,ownedPull=null,pauseProof=null,kind='redispatch'}) {
 need(['redispatch','formatredispatch'].includes(kind),'Unknown redispatch producer');
 const loaded=await transport.load(startedProof,'started',artifactName('started',startedProof.run_id,startedProof.run_attempt));
 const started=unseal(loaded.bytes,'closer-correction-started/v1');
 need(started.run_id===loaded.proof.run_id && started.run_attempt===loaded.proof.run_attempt
   && transport.current?.run_id===started.run_id && transport.current?.run_attempt===started.run_attempt
   && started.request_sha256===selector.request_sha256 && started.effect_key===selector.effect_key
   && same(started.issue,selector.issue) && (kind==='formatredispatch'?started.selected_step==='format' && nextStep==='format'
     :redispatchForceStep(started.selected_step)===nextStep),'Redispatch cannot replace original lineage or transition');
 need(typeof observeIssue==='function','Fresh redispatch issue read unavailable');
 let ownedPause=null;
 if(kind==='formatredispatch') {
  need(pauseProof,'Original native formatter pause proof unavailable');
  ownedPause=await validateFormatPause({transport,proof:pauseProof,selector,started});
 }
 const observed=issueIdentity(await observeIssue());
 if(ownedPause)need(same(observed,ownedPause),'Issue body changed after automation paused formatting');
 need(observed.number===selector.issue.number && observed.node_id===selector.issue.node_id,'Redispatch issue/node changed');
 const payload=seal({schema:'closer-correction-redispatch/v1',request_sha256:selector.request_sha256,effect_key:selector.effect_key,
 issue:selector.issue,observed_issue:observed,owned_pr:ownedPull?.proof || started.owned_pr || null,owned_pause:pauseProof,intent:started.intent,started:loaded.proof,next_step:nextStep});
 const proof=await transport.publish(kind,Buffer.from(JSON.stringify(payload)+'\n'));
 return {...selector,parent_dispatch:{kind,...proof}};
}
module.exports={authenticateContinuation,recordStarted,retainRedispatch,lineageKey,unseal};

// Complete native inventory is required for a negative lineage observation. A
// A skipped correction step is ordinary-mode evidence only when the exact
// authenticated workflow source makes it so. In particular, successful context
// selection plus skipped correction auth proves the selector was absent; step
// names alone or a caller-selected run title cannot establish that implication.
async function authenticateOrdinaryAutopilot({transport,run,attempt,actual,job}) {
 const names=['Authenticate correction continuation','Determine context','Record admitted correction start'];
 const native=names.map(name=>(job.steps || []).filter(step=>step.name===name));
 need(native.every(rows=>rows.length===1),'Missing started artifact has no unambiguous ordinary-mode steps');
 const [auth,context,start]=native.map(rows=>rows[0]);
 need([auth,context,start].every(step=>step.status==='completed' && Number.isSafeInteger(step.number) && step.number>0)
  && auth.conclusion==='skipped' && context.conclusion==='success' && start.conclusion==='skipped'
  && auth.number<context.number && context.number<start.number,
 'Missing started artifact cannot establish native ordinary execution mode');
 need(actual?.id===run.id && actual.run_attempt===attempt && actual.head_sha===run.head_sha && /^[a-f0-9]{40}$/.test(actual.head_sha || ''),
 'Ordinary execution source attempt unavailable');
 const source=await transport.read('repos','getContent',{path:'.github/workflows/agents-auto-pilot.yml',ref:actual.head_sha});
 need(source?.type==='file' && source.encoding==='base64' && typeof source.content==='string' && source.content.length<=1398104,
 'Ordinary execution workflow source unavailable');
 const bytes=Buffer.from(source.content,'base64'),{createHash}=require('crypto');
 need(bytes.length<=1048576 && createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex')===source.sha,
 'Ordinary execution workflow Git blob differs');
 const text=bytes.toString('utf8'),jobs=[...text.matchAll(/^  auto-pilot:\s*$/gm)];
 need(jobs.length===1,'Ordinary execution workflow job source ambiguous');
 const jobText=text.slice(jobs[0].index).split(/\n  [A-Za-z0-9_-]+:\s*\n/)[0];
 const steps=[...jobText.matchAll(/^      - name: (.+)$/gm)];
 const expected=[['correction_auth',"steps.check_enabled.outputs.enabled == 'true' && inputs.correction_selector != ''"],
  ['context',"steps.check_enabled.outputs.enabled == 'true' && (inputs.correction_selector == '' || steps.correction_auth.outputs.admitted == 'true')"],
  ['correction_start',"inputs.correction_selector != '' && steps.context.outputs.should_continue == 'true' && steps.cycles.outputs.exceeded == 'false' && steps.cycles.outputs.rate_limited == 'false' && steps.next.outputs.next_step != '' && steps.next.outputs.next_step != 'done'"]];
 const positions=[];
 for(let index=0;index<names.length;index++) {
  const found=steps.map((step,at)=>({step,at})).filter(row=>row.step[1]===names[index]);
  need(found.length===1,'Ordinary execution source step ambiguous');
  const {step,at}=found[0],body=jobText.slice(step.index,steps[at+1]?.index || jobText.length);
  const header=body.split(/^        (?:uses|env|with|run|shell|working-directory|continue-on-error):/m)[0];
  const ids=[...header.matchAll(/^        id: (\S+)$/gm)],conditions=[...header.matchAll(/^        if: (.+)$/gm)];
  need(ids.length===1 && ids[0][1]===expected[index][0] && conditions.length===1,'Ordinary execution step guards unavailable');
  let condition=conditions[0][1].trim();
  if(condition==='>-' || condition==='|') {
   const after=header.slice(conditions[0].index+conditions[0][0].length).split('\n').slice(1),lines=[];
   for(const line of after){if(!line.startsWith('          '))break;lines.push(line.trim());}condition=lines.join(' ');
  }
  need(condition===expected[index][1],'Ordinary execution source predicate is unsupported');positions.push(at);
 }
 need(positions[0]<positions[1] && positions[1]<positions[2],'Ordinary execution source step order differs');
}

// missing receipt never means absence when a prior execution could have started.
async function observeStartedReceipts({transport,request,since}) {
 const key=effectKey(seedForRequest(request)),results=[];
 const runs=await transport.runs('.github/workflows/agents-auto-pilot.yml',since);
 for(const run of runs) {
  need(Number.isSafeInteger(run.run_attempt) && run.run_attempt>0 && run.run_attempt<=10,'Auto-pilot attempt history exceeds bound');
  await transport.canonicalRun(run.id,run.run_attempt,'.github/workflows/agents-auto-pilot.yml');
  const inventory=await transport.artifacts(run.id);
  for(let attempt=1;attempt<=run.run_attempt;attempt++) {
   const name=artifactName('started',run.id,attempt),matches=inventory.filter(row=>row.name===name);
   need(matches.length<=1,'Ambiguous actual auto-pilot started artifacts');
   const actual=await transport.canonicalRun(run.id,attempt,'.github/workflows/agents-auto-pilot.yml');
   if(!matches.length && run.id===transport.current?.run_id && attempt===transport.current?.run_attempt)continue;
   if(!matches.length) {
    const jobs=await transport.jobs(run.id,attempt),main=jobs.filter(job=>job.name==='auto-pilot');
    need(run.status==='completed' && main.length===1 && main[0].status==='completed'
     && main[0].run_id===run.id && main[0].run_attempt===attempt && main[0].head_sha===run.head_sha,'Prior auto-pilot outcome is unknown');
    const start=(main[0].steps || []).filter(step=>step.name==='Record admitted correction start');
    const execution=(main[0].steps || []).filter(step=>step.name.startsWith('Execute step -'));
    const notStarted=main[0].conclusion==='skipped' || (start.length===1 && start[0].status==='completed' && start[0].conclusion==='skipped'
      && execution.length>0 && execution.every(step=>step.status==='completed' && step.conclusion==='skipped'));
    if(!notStarted)await authenticateOrdinaryAutopilot({transport,run,attempt,actual,job:main[0]});
    continue;
   }
   const loaded=await transport.load({repository:request.target.repository,run_id:run.id,run_attempt:attempt,artifact_id:matches[0].id},'started',name);
   const receipt=unseal(loaded.bytes,'closer-correction-started/v1');
   need(receipt.run_id===run.id && receipt.run_attempt===attempt && receipt.execution_kind==='workflow_admission'
    && receipt.provider_execution==='not_attested' && receipt.act_authorized===false && receipt.source_closure_authorized===false,
    'Started artifact misstates actual workflow admission');
   if(receipt.effect_key===key) {
    need(receipt.request_sha256===request.request_sha256,'Original request rebound in continuation history');
    results.push({receipt,proof:loaded.proof});
   }
  }
 }
 return results;
}
module.exports.observeStartedReceipts=observeStartedReceipts;

function pullIdentity(pull,issue) {
 need(Number.isSafeInteger(pull?.id) && pull.id>0 && Number.isSafeInteger(pull.number) && pull.number>0
  && typeof pull.node_id==='string' && pull.node_id.length>0 && typeof pull.head?.sha==='string' && /^[a-f0-9]{40}$/.test(pull.head.sha)
  && typeof pull.head.ref==='string' && pull.head.ref.length>0 && typeof pull.base?.ref==='string' && pull.base.ref.length>0
  && Number.isSafeInteger(pull.head.repo?.id) && pull.head.repo.id>0 && Number.isSafeInteger(pull.base.repo?.id) && pull.base.repo.id>0
  && typeof pull.head.repo?.full_name==='string' && typeof pull.base.repo?.full_name==='string', 'Native corrective PR identity incomplete');
 return {id:pull.id,number:String(pull.number),node_id:pull.node_id,created_head_sha:pull.head.sha,head_ref:pull.head.ref,
 head_repository_id:pull.head.repo.id,base_repository_id:pull.base.repo.id,
 head_repository:pull.head.repo.full_name.toLowerCase(),base_repository:pull.base.repo.full_name.toLowerCase(),base_ref:pull.base.ref,
 issue_node_id:issue.node_id};
}
async function retainCreatedPull({transport,selector,startedProof,response}) {
 const loaded=await transport.load(startedProof,'started',artifactName('started',startedProof.run_id,startedProof.run_attempt));
 const started=unseal(loaded.bytes,'closer-correction-started/v1');
 need(started.selected_step==='create-pr' && started.run_id===transport.current?.run_id && started.run_attempt===transport.current?.run_attempt
  && started.request_sha256===selector.request_sha256 && started.effect_key===selector.effect_key && same(started.issue,selector.issue),
 'Native PR response is not this admitted create-pr execution');
 need(response?.status===201 && typeof response.headers?.['x-github-request-id']==='string' && response.headers['x-github-request-id'].length>0,'Original native PR creation response unavailable');
 assertPullScopeBody(response.data.body,selector.issue,selector.repository);
 const pull=pullIdentity(response.data,selector.issue);
 need(pull.head_repository===selector.repository && pull.base_repository===selector.repository,'Native corrective PR repository differs');
 const value=seal({schema:'closer-correction-created-pr/v1',request_sha256:selector.request_sha256,effect_key:selector.effect_key,
 issue:selector.issue,pull,run_id:transport.current.run_id,run_attempt:transport.current.run_attempt,
 http_status:201,github_request_id:response.headers['x-github-request-id'],started:loaded.proof});
 return transport.publish('createdpr',Buffer.from(JSON.stringify(value)+'\n'));
}
async function loadOwnedPull({transport,proof,request,issue}) {
 const loaded=await transport.load(proof,'createdpr',artifactName('createdpr',proof.run_id,proof.run_attempt));
 const value=unseal(loaded.bytes,'closer-correction-created-pr/v1');
 need(value.request_sha256===request.request_sha256 && value.effect_key===effectKey(seedForRequest(request)) && same(value.issue,issue)
  && value.run_id===loaded.proof.run_id && value.run_attempt===loaded.proof.run_attempt && value.http_status===201
  && typeof value.github_request_id==='string' && value.github_request_id.length>0,'Native owned PR response scope differs');
 const started=await transport.load(value.started,'started',artifactName('started',value.run_id,value.run_attempt));
 const parent=unseal(started.bytes,'closer-correction-started/v1');
 need(parent.run_id===value.run_id && parent.run_attempt===value.run_attempt && parent.selected_step==='create-pr'
  && parent.request_sha256===request.request_sha256 && same(parent.issue,issue),'Native owned PR producer/start differs');
 const actual=await transport.read('pulls','get',{pull_number:Number(value.pull.number)});
 const observed=pullIdentity(actual,issue),{created_head_sha,...identity}=observed;
 const {created_head_sha:originalHead,...originalIdentity}=value.pull;
 need(same(identity,originalIdentity) && typeof originalHead==='string' && /^[a-f0-9]{40}$/.test(originalHead),
  'Owned corrective PR changed immutable node/repository/branch scope');
 assertPullScopeBody(actual.body,issue,request.target.repository);
 return {proof:loaded.proof,pull:value.pull,observed_head_sha:created_head_sha};
}
module.exports.pullIdentity=pullIdentity;
module.exports.retainCreatedPull=retainCreatedPull;
module.exports.loadOwnedPull=loadOwnedPull;

function assertPullScopeBody(body,issue,repository) {
 need(typeof body==='string' && body.startsWith(`<!-- meta:issue:${issue.number} -->\n\nCloses #${issue.number}\n`),
  'Corrective PR must retain exact incumbent issue linkage');
 const clauses=[...body.matchAll(/\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*([^\n]+)/gi)];
 for(const clause of clauses)for(const ref of clause[1].matchAll(/(?:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)?#[1-9]\d*|https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/issues\/[1-9]\d*/g)) {
  const token=ref[0].toLowerCase();
  need(token===`#${issue.number}` || token===`${repository}#${issue.number}`
   || token===`https://github.com/${repository}/issues/${issue.number}`,
  'Correction handoff does not authorize closing another source issue');
 }
}
module.exports.assertPullScopeBody=assertPullScopeBody;

async function latestPauseEvent(transport,issueNumber) {
 const events=[],ids=new Set();let complete=false;
 for(let page=1;page<=10;page++) {
  const rows=await transport.read('issues','listEvents',{issue_number:Number(issueNumber),per_page:100,page});
  need(Array.isArray(rows) && rows.length<=100,'Native formatter pause event inventory unavailable');
  for(const row of rows) {need(Number.isSafeInteger(row.id) && row.id>0 && !ids.has(row.id),'Ambiguous formatter pause event inventory');ids.add(row.id);events.push(row);}
  if(rows.length<100){complete=true;break;}
 }
 need(complete,'Formatter pause history exceeds bound');
 const changes=events.filter(row=>['labeled','unlabeled'].includes(row.event) && row.label?.name==='agents:auto-pilot-pause');
 need(changes.every(row=>typeof row.created_at==='string' && Number.isFinite(Date.parse(row.created_at))),'Native pause event time unavailable');
 changes.sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at)||a.id-b.id);
 return changes.at(-1);
}
async function retainFormatPause({transport,selector,startedProof,response}) {
 const loaded=await transport.load(startedProof,'started',artifactName('started',startedProof.run_id,startedProof.run_attempt));
 const started=unseal(loaded.bytes,'closer-correction-started/v1');
 need(started.selected_step==='format' && started.run_id===transport.current?.run_id && started.run_attempt===transport.current?.run_attempt
  && started.request_sha256===selector.request_sha256 && same(started.issue,selector.issue)
  && response?.status===200 && typeof response.headers?.['x-github-request-id']==='string' && response.headers['x-github-request-id'].length>0, 'Actual native formatter pause operation unavailable');
 const event=await latestPauseEvent(transport,selector.issue.number),issue=await transport.read('issues','get',{issue_number:Number(selector.issue.number)});
 need(event?.event==='labeled' && event.actor?.id===41898282 && event.actor.login==='github-actions[bot]' && event.actor.type==='Bot'
  && Date.parse(event.created_at)>=Date.parse(loaded.proof.created_at) && same(issueIdentity(issue),started.observed_issue),
 'Formatter pause is not this exact native automation-owned event/body');
 const value=seal({schema:'closer-correction-format-pause/v1',request_sha256:selector.request_sha256,effect_key:selector.effect_key,
 issue:started.observed_issue,started:loaded.proof,event_id:event.id,event_created_at:event.created_at,
 github_request_id:response.headers['x-github-request-id'],run_id:transport.current.run_id,run_attempt:transport.current.run_attempt});
 return transport.publish('formatpause',Buffer.from(JSON.stringify(value)+'\n'));
}
async function validateFormatPause({transport,proof,selector,started}) {
 const loaded=await transport.load(proof,'formatpause',artifactName('formatpause',proof.run_id,proof.run_attempt));
 const pause=unseal(loaded.bytes,'closer-correction-format-pause/v1');
 const event=await latestPauseEvent(transport,selector.issue.number);
 need(pause.run_id===started.run_id && pause.run_attempt===started.run_attempt && pause.request_sha256===selector.request_sha256
  && pause.effect_key===selector.effect_key && same(pause.issue,started.observed_issue)
  && typeof pause.github_request_id==='string' && pause.github_request_id.length>0
  && event?.event==='labeled' && event.id===pause.event_id && event.created_at===pause.event_created_at
  && event.actor?.id===41898282 && event.actor.login==='github-actions[bot]' && event.actor.type==='Bot',
 'Native formatter pause was released, replaced or changed ownership');
 return pause.issue;
}
module.exports.retainFormatPause=retainFormatPause;
module.exports.validateFormatPause=validateFormatPause;
