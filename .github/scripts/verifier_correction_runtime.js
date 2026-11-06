'use strict';

// Trusted host wiring for the existing correction consumer; consequential calls
// remain inside the existing PR-concurrency effect job and the fenced kernel.
const {createHash}=require('crypto');
const path=require('path');
const {execFileSync}=require('child_process');
const {canonical,digest}=require('./verification_event');
const {validateRequest,nativeBody}=require('./verifier_correction_consumer');
const {seedForRequest,effectKey,createCorrectionEffectConsumer}=require('./verifier_correction_effects');
const {artifactName,correctionHistory,createArtifactLedger}=require('./verifier_correction_artifacts');
const {loadAgentRegistry}=require('./agent_registry');
const {loadReviewedQualification}=require('./verifier_correction_collector');
const {validateCorrectionDecision}=require('./verifier_correction_decision');
const {createFreshCollector,createEffectReconciler}=require('./verifier_correction_host');
const need=(value,reason)=>{if(!value)throw new Error(reason);};
const same=(a,b)=>canonical(a)===canonical(b);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
// Only this existing runner currently carries authenticated mandatory scope
// through final assemble_prompt and enforces the frozen coding policy ceiling.
// Registry routing is preserved: an unsupported owner holds, never falls back.
function requireCorrectionCodingIntake(facts,{registryPath}) {
 const registry=loadAgentRegistry({registryPath}),agent=registry.agents[facts?.agent?.key];
 need(facts?.agent?.enabled===true && agent?.enabled===true
  && agent.runner_workflow==='.github/workflows/reusable-codex-run.yml',
 'Owned UNKNOWN: selected coding runner lacks authenticated correction intake and final policy budget enforcement');
 if(facts.incumbentIssue) {
  need(Array.isArray(facts.incumbentIssue.labels),'Owned UNKNOWN: incumbent coding routing labels unavailable');
  const labels=facts.incumbentIssue.labels.map(label=>typeof label==='string'?label:label?.name);
  need(labels.every(label=>typeof label==='string'),'Owned UNKNOWN: incumbent coding routing labels incomplete');
  const normalized=labels.map(label=>label.toLowerCase());
  const agents=normalized.filter(label=>label.startsWith('agent:')
   && (label==='agent:auto' || Object.hasOwn(registry.agents,label.slice(6))));
  const runners=normalized.filter(label=>label.startsWith('runner:'));
  need(agents.length===1 && agents[0]===`agent:${facts.agent.key}`
   && runners.length<=1 && runners.every(label=>label===`runner:${facts.agent.key}`),
  'Owned UNKNOWN: fresh incumbent routing differs from authenticated supported correction runner');
 }
 return facts;
}
async function activeExecutions({transport,current,registryPath,ownedPull=null}) {
 const registry=loadAgentRegistry({registryPath});
 const runners=new Set(Object.values(registry.agents).map(agent=>path.basename(agent.runner_workflow || '')));
 const records=[],ids=new Set();
 for(const status of ['requested','waiting','pending','queued','in_progress']) {
  let total;
  for(let page=1;page<=10;page++) {
   const data=await transport.read('actions','listWorkflowRunsForRepo',{status,per_page:100,page});
   need(Array.isArray(data?.workflow_runs) && Number.isSafeInteger(data.total_count) && data.total_count>=0,'Active execution inventory unavailable');
   need(total===undefined || total===data.total_count,'Active execution inventory changed during read');total=data.total_count;
   for(const row of data.workflow_runs) {
    need(Number.isSafeInteger(row.id) && row.id>0 && !ids.has(row.id) && typeof row.path==='string'
     && row.status===status,'Ambiguous/incomplete active execution inventory');ids.add(row.id);
    if(row.id!==current.run_id && /\/.github\/workflows\//.test(`/${row.path}`)) {
     // Unknown subject in an active existing agent/queue lane is ownership
     // uncertainty, never evidence that no writer exists. The correction lane
     // itself is independently covered by its complete retained phase journal.
     const name=path.basename(row.path.split('@')[0]);
     const linked=row.pull_requests;
     const scoped=ownedPull && Array.isArray(linked) && linked.length===1 && linked[0].id===ownedPull.pull.id
      && String(linked[0].number)===ownedPull.pull.number && linked[0].head?.sha===ownedPull.observed_head_sha
      && linked[0].head?.ref===ownedPull.pull.head_ref && linked[0].head?.repo?.id===ownedPull.pull.head_repository_id
      && linked[0].base?.repo?.id===ownedPull.pull.base_repository_id && row.repository?.id===ownedPull.pull.base_repository_id;
     if(!scoped && (name.startsWith('agents-') || name.startsWith('reusable-agents') || runners.has(name))
       && name!=='agents-verify-to-new-pr.yml')records.push({run_id:row.id,run_attempt:row.run_attempt,workflow:row.path,status:row.status});
    }
   }
   const received=ids.size;
   // IDs span both status inventories; track the current page count separately.
   const count=(page-1)*100+data.workflow_runs.length;
   need(count<=total,'Active execution pagination is incomplete');
   if(count===total)break;
   need(data.workflow_runs.length===100 && page<10 && received<=2000,'Active execution inventory exceeds bound');
  }
 }
 return records;
}
async function existingVerdictPolicy({transport,request,pythonRoot}) {
 const comment=await transport.read('issues','getComment',{comment_id:Number(request.original_verifier.comment_id)});
 need(typeof comment.body==='string' && sha(comment.body)===request.original_verifier.comment_sha256,'Original verdict policy evidence changed');
 const result=JSON.parse(execFileSync('python3',['-I','-c',"import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('scripts.langchain.verdict_extract',run_name='__main__')",pythonRoot,'--summary-path','-','--policy','worst','--emit','json'],{
  cwd:pythonRoot,input:comment.body,encoding:'utf8',timeout:10000,maxBuffer:1048576,
 }));
 return result.needs_human===false && ['concerns','fail'].includes(String(result.verdict).toLowerCase())?'follow-up':'owned-unknown';
}
async function loadAdmitted({transport,selector}) {
 const loaded=await transport.load(selector,'admitted',artifactName('admitted',selector.run_id,selector.run_attempt));
 const context=JSON.parse(loaded.bytes),{context_sha256,...payload}=context;
 need(context.schema==='closer-correction-admitted/v1' && context.status==='admitted' && context.classification?.status==='admitted' && context_sha256===digest(payload),
 'Trusted collector did not admit correction');
 const request=validateRequest(context.request),seed=seedForRequest(request);
 need(typeof context.finding_text==='string' && sha(context.finding_text)===request.finding.evidence.sha256,
 'Exact original finding text is not retained with authenticated request');
 need(context.collector.repository===loaded.proof.repository && context.collector.run_id===loaded.proof.run_id
  && context.collector.run_attempt===loaded.proof.run_attempt && same(context.seed,seed) && context.effect_key===effectKey(seed),
 'Admitted collector/source identity differs');
 need(context.decision_proof?.status==='authenticated' && context.decision_proof.decision_sha256===digest(context.decision)
  && typeof context.decision_proof.profile_identity_sha256==='string'
  && context.decision_proof.profile_identity_sha256===context.qualification?.profile_identity_sha256
  && validateCorrectionDecision(context).status==='admitted','Original retained classification origin unavailable');
 return {context,proof:loaded.proof};
}
// Explicit source deployment policy, independent of role/profile/secret state.
// Pure kernel fixtures remain usable; production host factories cannot activate
// typed effects until reviewed durable subject enrollment replaces broad scans.
function requireDeployedCorrectionEffects() {
 throw Error('typed_correction_effects_not_deployed: collection-only source release');
}
async function createRuntime({github,transport,selector,current,registryPath,pythonRoot,clock=()=>new Date(),qualificationLoader=null}) {
 requireDeployedCorrectionEffects();
 const {context,proof}=await loadAdmitted({transport,selector}),request=context.request;
 await transport.canonicalRun(current.run_id,current.run_attempt,'.github/workflows/agents-verify-to-new-pr.yml');
 const pull=await transport.read('pulls','get',{pull_number:Number(request.target.pr)});
 need(pull.merged===true && typeof pull.merged_at==='string' && Number.isFinite(Date.parse(pull.merged_at)),
 'Native merged-PR correction history boundary unavailable');
 const since=pull.merged_at,history=()=>correctionHistory({transport,request,since});
 const ledger=await createArtifactLedger({transport,request,since,admittedProof:proof});
 const native=await createFreshCollector({github,repository:request.target.repository,actor:context.dispatch_actor,registryPath,
  history,observeContinuations:({ownedPull})=>activeExecutions({transport,current,registryPath,ownedPull}),policy:()=>existingVerdictPolicy({transport,request,pythonRoot}),clock,transport});
 const collectFreshFacts=async(...args)=>{
  const qualification=await (qualificationLoader?qualificationLoader(context.decision.profile):loadReviewedQualification({github,profile:context.decision.profile,clock}));
  need(validateCorrectionDecision({...context,qualification}).status==='admitted','Current production qualification no longer admits ordinary correction');
  const [subject,options={}]=args;
  const {activeIntent,...nativeOptions}=options;
  const activeEffect=activeIntent?await ledger.activeStage({record:activeIntent}):null;
  return {...requireCorrectionCodingIntake(await native(subject,{...nativeOptions,activeEffect}),{registryPath}),correction_finding_text:context.finding_text};
 };
 const metadata=await transport.read('repos','get',{});
 need(metadata.full_name?.toLowerCase()===request.target.repository && typeof metadata.default_branch==='string' && metadata.default_branch.length>0,
 'Actual continuation default branch unavailable');
 const reconcile=await createEffectReconciler({transport,request,history,since});
 const consume=createCorrectionEffectConsumer({github,defaultBranch:metadata.default_branch,clock,ledger,reconcile,collectFreshFacts,
  // This authenticates historical scope for reconciliation. Fresh eligibility,
  // ownership and policy are mandatory again before every NEW side effect.
  authenticate:async()=>({request,seed:context.seed,required_tests:request.required_tests})});
 return {consume,request,context,proof,ledger,reconcile,since};
}
module.exports={activeExecutions,existingVerdictPolicy,loadAdmitted,createRuntime,requireCorrectionCodingIntake};

async function createAutopilotRuntime({github,transport,selector,current,registryPath,pythonRoot,clock=()=>new Date(),qualificationLoader=null}) {
 requireDeployedCorrectionEffects();
 const {context,proof}=await loadAdmitted({transport,selector:selector.collector}),request=context.request;
 const pull=await transport.read('pulls','get',{pull_number:Number(request.target.pr)});
 need(pull.merged===true && typeof pull.merged_at==='string' && Number.isFinite(Date.parse(pull.merged_at)),
 'Actual merged-PR continuation history boundary unavailable');
 const since=pull.merged_at,ledger=await createArtifactLedger({transport,request,since,admittedProof:proof});
 const history=()=>correctionHistory({transport,request,since});
 const native=await createFreshCollector({github,repository:request.target.repository,actor:context.dispatch_actor,registryPath,history,
  observeContinuations:({ownedPull})=>activeExecutions({transport,current,registryPath,ownedPull}),
  policy:()=>existingVerdictPolicy({transport,request,pythonRoot}),clock,transport,
  activeContinuation:{effect_key:context.effect_key,run_id:current.run_id,run_attempt:current.run_attempt,intent:selector.intent}});
 const qualification=profile=>qualificationLoader?qualificationLoader(profile):loadReviewedQualification({github,profile,clock});
 const facts=async(...args)=>{await ledger.read(context.effect_key);return requireCorrectionCodingIntake(await native(...args),{registryPath});};
 const {authenticateContinuation,observeStartedReceipts}=require('./verifier_correction_autopilot');
 const authenticate=options=>authenticateContinuation({transport,selector,current,issueNumber:selector.issue.number,
  loadQualification:qualification,collectFreshFacts:facts,clock,...options});
 const observeLineage=async admission=>(await observeStartedReceipts({transport,request,since}))
  .filter(row=>row.receipt.lineage_key===admission.lineage_key);
 return {context,request,proof,since,ledger,authenticate,observeLineage,qualification};
}
module.exports.createAutopilotRuntime=createAutopilotRuntime;

// Native issue identity is the lookup key. Queue inputs and PR text may help a
// caller discover that key, but can neither supply the scope nor authenticate it.
async function resolveCodingScope({transport,issueNumber=null,linkedPull=null}) {
 const {SPECS}=require('./verifier_correction_artifacts');
 const {issueIdentity}=require('./verifier_correction_effects');
 const issue=issueNumber===null?null:await transport.read('issues','get',{issue_number:issueNumber});
 if(issueNumber!==null)need(issue?.number===issueNumber && !issue.pull_request && (typeof issue.body==='string' || issue.body===null)
  && typeof issue.node_id==='string','Correction intake native issue identity unavailable');
 const matches=[];
 // Only workflow_dispatch executions of the existing correction workflow are
 // inventoried. Exhaustion, unavailable history or expired possible effects is
 // UNKNOWN; never a time-window guess that could forget an incumbent writer.
 for(const run of await transport.runs(SPECS.admitted.workflow,'1970-01-01T00:00:00Z')) {
  need(Number.isSafeInteger(run.run_attempt) && run.run_attempt>0 && run.run_attempt<=10,'Correction intake attempt history incomplete');
  const inventory=await transport.artifacts(run.id);
  for(let attempt=1;attempt<=run.run_attempt;attempt++) {
   const actual=await transport.canonicalRun(run.id,attempt,SPECS.admitted.workflow);
   const jobs=await transport.jobs(run.id,attempt),effects=jobs.filter(job=>job.name===SPECS.ledger.job);
   need(effects.length<=1,'Correction intake ambiguous effect job');
   if(!effects.length)continue;
   const job=effects[0],steps=(job.steps || []).filter(step=>step.name===SPECS.ledger.step);
   need(job.run_id===run.id && job.run_attempt===attempt && job.head_sha===actual.head_sha,'Correction intake effect provenance incomplete');
   if(job.status==='completed' && (job.conclusion==='skipped' || (steps.length===1 && steps[0].status==='completed' && steps[0].conclusion==='skipped')))continue;
   const name=artifactName('admitted',run.id,attempt),found=inventory.filter(row=>row.name===name);
   need(found.length===1,'Correction intake possible effect has missing admitted context; UNKNOWN');
   const selected={repository:transport.repository,run_id:run.id,run_attempt:attempt,artifact_id:found[0].id};
   const {context,proof}=await loadAdmitted({transport,selector:selected}),request=context.request;
   if(issueNumber!==null && request.incumbent.kind!=='no_incumbent' && request.incumbent.issue.number!==String(issueNumber))continue;
   const ledger=await createArtifactLedger({transport,request,since:'1970-01-01T00:00:00Z',admittedProof:proof});
   const journal=await ledger.read(context.effect_key);
   const identity=request.incumbent.kind==='no_incumbent'
    ?journal.records.find(row=>row.kind==='issue_confirmed')?.issue:request.incumbent.issue;
   if(!identity) {
    need(!journal.records.some(row=>row.phase==='issue_creation'),'Correction intake issue creation outcome UNKNOWN');
    continue;
   }
   if(issueNumber!==null && identity.number!==String(issueNumber))continue;
   if(linkedPull && !await nativeIssueLinksPull({transport,identity,pull:linkedPull}))continue;
   const nativeIssue=issue || await transport.read('issues','get',{issue_number:Number(identity.number)});
   need(same(identity,issueIdentity(nativeIssue)),'Correction intake original issue/node/body changed; preserve and reconcile original scope');
   need(journal.records.some(row=>row.phase==='autopilot_dispatch'),'Correction intake has no original continuation intent');
   matches.push({context,proof,identity,issue:nativeIssue});
  }
 }
 const keys=new Set(matches.map(row=>row.context.effect_key));
 need(keys.size<=1,'Correction intake competing authenticated scopes; UNKNOWN');
 if(!matches.length)return null;
 const first=matches[0];
 need(matches.every(row=>row.context.request.request_sha256===first.context.request.request_sha256),'Correction intake aliases changed original request');
 const request=first.context.request;
 const budgetLedger=await createArtifactLedger({transport,request,since:'1970-01-01T00:00:00Z',admittedProof:first.proof});
 const budgetHistory=await budgetLedger.scan();
 const codingBudget=require('./verifier_correction_consumer').minimumCodingBudget(budgetHistory.contexts
  .filter(row=>row.context.status==='admitted' && row.context.effect_key===first.context.effect_key
    && row.context.request.request_sha256===request.request_sha256).map(row=>row.context.coding_budget),request);
 need(Date.now()<Date.parse(request.original_operation.deadline),'Correction intake original deadline exhausted');
 return {schema:'closer-correction-coding-context/v1',request_sha256:request.request_sha256,
  seed_effect_key:first.context.effect_key,admitted_selector:first.proof,coding_budget:codingBudget,issue:first.identity,original_issue_body:nativeBody(first.issue.body),
  finding_text:first.context.finding_text,required_tests:request.required_tests};
}
module.exports.resolveCodingScope=resolveCodingScope;
function fitCodingText({base,scope,budget,pythonRoot}) {
 if(scope===null)return base;
 need(typeof budget==='string' && /^[1-9]\d*$/.test(budget),'correction_budget_unconfigured: final coding lane requires an explicit selected ISSUE_PR_CONTEXT_TOKEN_BUDGET');
 const script="import json,sys; sys.path.insert(0,sys.argv[1]); from scripts.langchain.issue_pr_context import ContextOptions,render_correction_context,require_complete_correction_prompt,select_correction_budget; p=json.load(sys.stdin); text=p['base']+'\\n\\n## Complete original issue scope\\n'+p['scope']['original_issue_body']+render_correction_context(p['scope']); print(require_complete_correction_prompt(text,ContextOptions(token_budget=select_correction_budget(p['scope'],p['budget']))),end='')";
 return execFileSync('python3',['-I','-c',script,pythonRoot],{cwd:pythonRoot,input:JSON.stringify({base,scope,budget}),encoding:'utf8',timeout:15000,maxBuffer:2097152});
}
module.exports.fitCodingText=fitCodingText;
async function nativeIssueLinksPull({transport,identity,pull}) {
 const {timelineIdentity}=require('./verifier_correction_host');
 let linked=false;const seen=new Set();
 for(let page=1;page<=10;page++) {
  const rows=await transport.read('issues','listEventsForTimeline',{issue_number:Number(identity.number),per_page:100,page});
  need(Array.isArray(rows) && rows.length<=100,'Correction intake native link history incomplete');
  for(const row of rows) {
   const native=timelineIdentity(row);need(!seen.has(native),'Correction intake ambiguous native link history');seen.add(native);
   if(row.event!=='cross-referenced')continue;
   const source=row.source.issue;
   if(source.id===pull.id || source.node_id===pull.node_id) {
    need(source.id===pull.id && source.node_id===pull.node_id && source.number===pull.number
     && source.repository?.full_name?.toLowerCase()===transport.repository
     && source.pull_request,'Correction intake native linked coding PR identity differs');linked=true;
   }
  }
  if(rows.length<100)return linked;
 }
 throw Error('Correction intake native link history exceeds bound; UNKNOWN');
}
function requireOpenCorrectionCodingPull(pull) {
 need(pull.state==='open' && pull.draft===false && Array.isArray(pull.labels),
 'Owned UNKNOWN: native correction coding PR closed, draft or labels unavailable');
 const labels=pull.labels.map(label=>typeof label==='string'?label:label?.name);
 need(labels.every(label=>typeof label==='string'),'Owned UNKNOWN: native correction coding PR labels incomplete');
 const blocked=new Set(['needs-human','agents:paused','agents:pause','agents:max-runs:0',
  'agents:auto-pilot-pause','agents:auto-pilot-failed']);
 need(!labels.some(label=>blocked.has(label.toLowerCase())),
 'Owned UNKNOWN: native correction coding PR has a current operator hold');
}
async function resolvePullCodingScope({transport,pullNumber}) {
 const pull=await transport.read('pulls','get',{pull_number:pullNumber});
 need(pull.number===pullNumber && Number.isSafeInteger(pull.id) && typeof pull.node_id==='string'
  && pull.head?.repo?.full_name?.toLowerCase()===transport.repository,'Correction intake native coding PR scope unavailable');
 // Complete retained issue/request/seed inventories plus historical native
 // cross-reference identity discover scope even after Closes/body edits. Native
 // linkage only joins the coding PR; it grants no effect or security authority.
 const scope=await resolveCodingScope({transport,linkedPull:pull});
 if(scope!==null)requireOpenCorrectionCodingPull(pull);
 return scope;
}
module.exports.resolvePullCodingScope=resolvePullCodingScope;

async function recheckCodingAdmission({github,transport,scope,pythonRoot,clock=()=>new Date()}) {
 const {issueIdentity}=require('./verifier_correction_effects');
 const {crossReferenceDigest,timelineIdentity}=require('./verifier_correction_host');
 need(scope?.admitted_selector,'Mandatory coding scope has no authenticated admission selector');
 const {context,proof}=await loadAdmitted({transport,selector:scope.admitted_selector}),request=context.request;
 need(scope.request_sha256===request.request_sha256 && scope.seed_effect_key===context.effect_key
  && scope.finding_text===context.finding_text && same(scope.required_tests,request.required_tests),
  'Mandatory coding scope differs from exact retained request/seed');
 const ledger=await createArtifactLedger({transport,request,since:'1970-01-01T00:00:00Z',admittedProof:proof});
 const journal=await ledger.read(context.effect_key);
 const history=await ledger.scan();
 const codingBudget=require('./verifier_correction_consumer').minimumCodingBudget(history.contexts
  .filter(row=>row.context.status==='admitted' && row.context.effect_key===context.effect_key
    && row.context.request.request_sha256===request.request_sha256).map(row=>row.context.coding_budget),request);
 need(codingBudget && same(codingBudget,scope.coding_budget),'Original authenticated coding budget changed or unavailable');
 const originalIssue=request.incumbent.kind==='no_incumbent'
  ?journal.records.find(row=>row.kind==='issue_confirmed')?.issue:request.incumbent.issue;
 need(originalIssue && same(originalIssue,scope.issue) && typeof scope.original_issue_body==='string'
  && sha(scope.original_issue_body)===originalIssue.body_sha256
  && journal.records.some(row=>row.phase==='autopilot_dispatch'),
  'Mandatory coding issue/body differs from exact authenticated original issue/intent');
 const qualification=await loadReviewedQualification({github,profile:context.decision.profile,clock});
 need(qualification?.profile_identity_sha256===context.decision_proof.profile_identity_sha256
  && validateCorrectionDecision({...context,qualification}).status==='admitted',
  'Current bounded classification qualification unavailable or revoked; owned_unknown');
 const pull=await transport.read('pulls','get',{pull_number:Number(request.target.pr)});
 const source=await transport.read('issues','get',{issue_number:Number(request.source_issue.number)});
 const issue=await transport.read('issues','get',{issue_number:Number(scope.issue.number)});
 const labels=row=>{
  need(Array.isArray(row?.labels) && row.labels.every(label=>typeof label?.name==='string'),'Current corrective hold labels unavailable');
  return row.labels.map(label=>label.name.toLowerCase());
 };
 const blocked=row=>labels(row).some(name=>['needs-human','agents:auto-pilot-pause','agents:auto-pilot-failed','agents:paused'].includes(name));
 need(String(pull.number)===request.target.pr && pull.merged===true && pull.head?.sha===request.target.head_sha && pull.base?.sha===request.target.base_sha
  && pull.merge_commit_sha===request.target.merge_sha && !blocked(pull),'Original corrective source PR changed or held');
 need(String(source.number)===request.source_issue.number && source.node_id===request.source_issue.node_id
  && sha(nativeBody(source.body))===request.source_issue.body_sha256 && !blocked(source),
  'Original corrective source issue changed or held');
 need(same(issueIdentity(issue),scope.issue) && nativeBody(issue.body)===scope.original_issue_body && issue.state==='open' && !blocked(issue),
  'Incumbent correction issue changed, closed or held');
 need(await existingVerdictPolicy({transport,request,pythonRoot})==='follow-up','Existing corrective policy no longer admits coding');
 need(Array.isArray(issue.assignees) && issue.assignees.every(row=>typeof row.login==='string'),'Current corrective assignment unavailable');
 need(typeof context.dispatch_actor==='string' && context.dispatch_actor.length>0,'Original authenticated corrective actor unavailable');
 const permission=await transport.read('repos','getCollaboratorPermissionLevel',{username:context.dispatch_actor});
 need(['admin','maintain','write'].includes(permission.permission) && permission.user?.login?.toLowerCase()===context.dispatch_actor?.toLowerCase(),
  'Original authenticated corrective actor no longer has write authority');
 if(request.incumbent.kind==='no_incumbent') {
  need(issue.assignees.length===0,'New correction has an unproven incumbent assignment; owned_unknown');
 } else {
  need(issue.assignees.length===1 && issue.assignees[0].login.toLowerCase()===request.incumbent.owner.toLowerCase(),
   'Original corrective owner changed');
  const ownerPermission=await transport.read('repos','getCollaboratorPermissionLevel',{username:request.incumbent.owner});
  need(['admin','maintain','write'].includes(ownerPermission.permission)
   && ownerPermission.user?.login?.toLowerCase()===request.incumbent.owner.toLowerCase(),
   'Original corrective owner no longer has write authority');
  const events=[],timeline=[];
  for(const [method,rows] of [['listEvents',events],['listEventsForTimeline',timeline]]) {
   const seen=new Set();let complete=false;
   for(let page=1;page<=10;page++) {
    const items=await transport.read('issues',method,{issue_number:Number(scope.issue.number),per_page:100,page});
    need(Array.isArray(items) && items.length<=100,'Current assignment/lineage inventory unavailable');
    for(const row of items){const key=timelineIdentity(row);need(!seen.has(key),'Current assignment/lineage inventory ambiguous');seen.add(key);rows.push(row);}
    if(items.length<100){complete=true;break;}
   }
   need(complete,'Current assignment/lineage inventory exceeds bound');
  }
  const assignments=events.filter(row=>['assigned','unassigned'].includes(row.event));
  need(assignments.every(row=>typeof row.created_at==='string' && Number.isFinite(Date.parse(row.created_at))),'Current native assignment time unavailable');
  const assigned=assignments.sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at)||b.id-a.id)[0];
  const prefix=`github:${request.target.repository}/issues/${scope.issue.number}`;
  need(assigned?.event==='assigned' && `${prefix}/events/${assigned.id}`===request.incumbent.assignment_ref
   && assigned.assignee?.login?.toLowerCase()===request.incumbent.owner.toLowerCase()
   && timeline.some(row=>row.event==='cross-referenced' && row.source.issue.id===pull.id && row.source.issue.node_id===pull.node_id && `${prefix}/timeline-sha256/${crossReferenceDigest(row,pull)}`===request.incumbent.lineage_ref),
   'Original native corrective assignment/lineage no longer matches');
 }
 need(clock().getTime()<Date.parse(request.original_operation.deadline),'Original correction deadline exhausted before coding');
 return {status:'admitted',request_sha256:request.request_sha256};
}
module.exports.recheckCodingAdmission=recheckCodingAdmission;

function codingPolicyObservation({scope,currentBudget,configuration,current}) {
 const {validateCodingBudget,codingBudgetFromVariable}=require('./verifier_correction_consumer');
 const request={target:{repository:scope.admitted_selector?.repository},request_sha256:scope.request_sha256};
 const frozen=validateCodingBudget(scope.coding_budget,request);
 const configured=codingBudgetFromVariable(currentBudget,request);
 need(configured,'Current coding policy ceiling unavailable');
 need(configuration && typeof configuration.model==='string' && /^[a-zA-Z0-9._/-]+$/.test(configuration.model)
  && Array.isArray(configuration.candidates) && configuration.candidates.length>0
  && configuration.candidates.every(value=>typeof value==='string' && /^[a-zA-Z0-9._/-]+$/.test(value))
  && configuration.candidates.includes(configuration.model),'Selected coding model configuration unavailable');
 const extra=String(configuration.extra_arguments || '').trim();
 need(extra==='' || extra==='[]','Coding configuration has unbound extra arguments; hold before provider');
 const effort=configuration.reasoning_effort || 'high';
 need(['low','medium','high','xhigh','max'].includes(effort),'Selected coding effort unavailable');
 need(['read-only','workspace-write','danger-full-access'].includes(configuration.sandbox || 'workspace-write'),
  'Selected coding sandbox unavailable');
 need(Number.isSafeInteger(current?.run_id) && current.run_id>0 && Number.isSafeInteger(current?.run_attempt)
  && current.run_attempt>0,'Current coding policy observation execution unavailable');
 const payload={schema:'closer-correction-coding-policy-observation/v1',repository:request.target.repository,
  request_sha256:request.request_sha256,seed_effect_key:scope.seed_effect_key,run_id:current.run_id,run_attempt:current.run_attempt,
  original_policy:frozen,current_policy_ceiling:configured.max_estimated_input_tokens,
  selected_estimated_input_tokens:Math.min(frozen.max_estimated_input_tokens,configured.max_estimated_input_tokens),
  configuration_source:'existing-reusable-codex-run/model-selection',
  requested_configuration:{agent:'codex',profile_id:null,model:configuration.model,candidates:configuration.candidates,
   reasoning_effort:effort,sandbox:configuration.sandbox || 'workspace-write',extra_arguments:'none'},
  native_capacity_attested:false,effective_configuration_attested:false,provider_execution_attested:false,
  act_authorized:false,source_closure_authorized:false};
 return {...payload,content_sha256:digest(payload)};
}
module.exports.codingPolicyObservation=codingPolicyObservation;


// Read-only native lookup at the independent keepalive dispatch boundary. A
// missing/ambiguous history is not absence; neither labels nor queue JSON can
// claim that a PR has no retained mandatory correction scope.
async function guardCorrectionKeepalive({github,context,pr,agentKey,transport=null,registryPath}) {
 const repository=`${context.repo.owner}/${context.repo.repo}`.toLowerCase();
 if(!transport) {
  const {createArtifactTransport}=require('./verifier_correction_artifacts');
  transport=await createArtifactTransport({github,repository,current:{run_id:context.runId,
   run_attempt:Number(context.runAttempt || process.env.GITHUB_RUN_ATTEMPT)}});
 }
 const fresh=await transport.read('pulls','get',{pull_number:pr.number});
 need(fresh.number===pr.number && Number.isSafeInteger(fresh.id) && fresh.id>0
  && typeof fresh.node_id==='string' && fresh.node_id.length>0 && fresh.id===pr.id && fresh.node_id===pr.node_id
  && typeof fresh.head?.sha==='string' && fresh.head.sha.length>0 && fresh.head.sha===pr.head?.sha,
 'Owned UNKNOWN: native correction keepalive PR identity/head changed or unavailable');
 const scope=await resolveCodingScope({transport,linkedPull:fresh});
 if(scope===null)return null;
 need(/^[a-f0-9]{40}$/.test(fresh.head.sha) && fresh.head.repo?.full_name?.toLowerCase()===repository,
 'Owned UNKNOWN: native correction keepalive source repository/head unavailable');
 requireOpenCorrectionCodingPull(fresh);
 const registry=loadAgentRegistry({registryPath});
 requireCorrectionCodingIntake({agent:{key:agentKey,enabled:registry.agents[agentKey]?.enabled===true},
  incumbentIssue:{labels:fresh.labels}},{registryPath});
 return scope;
}
module.exports.guardCorrectionKeepalive=guardCorrectionKeepalive;
