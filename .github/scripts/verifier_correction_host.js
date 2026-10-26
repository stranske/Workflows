'use strict';

// Fresh native facts for this one existing follow-up lane. No request boolean,
// empty search response, or caller-assigned owner can synthesize no-incumbent.
const fs=require('fs');
const {createHash}=require('crypto');
const {canonical,digest}=require('./verification_event');
const {createTokenAwareRetry}=require('./github-api-with-retry');
const {seedForRequest,effectKey,sourceScopeDigest,issueIdentity}=require('./verifier_correction_effects');
const {nativeBody}=require('./verifier_correction_consumer');
const {loadAgentRegistry,resolveAgentFromLabels}=require('./agent_registry');
const need=(value,reason)=>{if(!value)throw new Error(reason);};
const same=(a,b)=>canonical(a)===canonical(b);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const labels=row=>{
 need(Array.isArray(row?.labels),'Fresh native labels unavailable');
 return row.labels.map(label=>typeof label==='string'?label:label.name);
};
const assigned=row=>{
 need(Array.isArray(row?.assignees) && row.assignees.every(user=>typeof user.login==='string'),'Native assignment inventory unavailable');
 return row.assignees;
};
function timelineIdentity(row) {
 need(row && typeof row.event==='string','Native timeline event type unavailable');
 if(row.event==='committed') {
  need(typeof row.sha==='string' && /^[a-f0-9]{40}$/.test(row.sha) && typeof row.node_id==='string' && row.node_id.length>0,
   'Native committed timeline identity unavailable');
  return `committed:${row.sha}:${row.node_id}`;
 }
 if(row.event==='cross-referenced') {
  const source=row.source?.issue;
  need(Number.isSafeInteger(row.actor?.id) && row.actor.id>0 && typeof row.created_at==='string'
   && Number.isFinite(Date.parse(row.created_at)) && row.source.type==='issue'
   && Number.isSafeInteger(source?.id) && source.id>0 && typeof source.node_id==='string' && source.node_id.length>0,
   'Native cross-reference timeline identity unavailable');
  return `cross-referenced:${digest({actor_id:row.actor.id,created_at:row.created_at,source_issue_id:source.id,source_node_id:source.node_id})}`;
 }
 if(Number.isSafeInteger(row.id) && row.id>0)return `event:${row.event}:${row.id}`;
 throw Error('Unsupported native timeline event identity; UNKNOWN');
}
function crossReferenceProjection(row,pull) {
 timelineIdentity(row);
 need(row.event==='cross-referenced' && typeof row.source.issue.repository?.full_name==='string'
  && row.source.issue.number===pull.number && row.source.issue.pull_request
  && typeof pull.head?.sha==='string' && /^[a-f0-9]{40}$/.test(pull.head.sha), 'Exact native source PR lineage unavailable');
 return {schema:'closer-correction-native-crossref/v1',event:row.event,actor_id:row.actor.id,created_at:row.created_at,source_issue_id:row.source.issue.id,
  source_node_id:row.source.issue.node_id,source_repository:row.source.issue.repository.full_name.toLowerCase(),
  source_pr:String(row.source.issue.number),source_head_sha:pull.head.sha};
}
function crossReferenceDigest(row,pull) {return digest(crossReferenceProjection(row,pull));}
function validateSubjectRow(row) {
 need(Number.isSafeInteger(row.number) && row.number>0 && typeof row.node_id==='string' && row.node_id.length>0
  && typeof row.title==='string' && (typeof row.body==='string' || row.body===null)
  && ['open','closed'].includes(row.state),'Native issue/PR exclusion content is incomplete');
 need(labels(row).every(label=>typeof label==='string' && label.length>0),'Native issue/PR label inventory is incomplete');
 assigned(row);
}
function chainDepth(...rows) {
 let depth=0;
 for(const row of rows) {
  const body=nativeBody(row.body);
  const values=[...body.matchAll(/<!--\s*follow-up-depth:\s*(\d+)\s*-->/g)].map(match=>Number(match[1]));
  need(values.every(Number.isSafeInteger),'Follow-up chain depth invalid');
  depth=Math.max(depth,...values);
  if(labels(row).includes('follow-up'))depth=Math.max(depth,1);
 }
 return depth;
}
async function createFreshCollector({github,repository,actor,registryPath,history,observeContinuations,policy,clock,transport=null,activeContinuation=null}) {
 need(typeof actor==='string' && actor.length>0 && typeof registryPath==='string'
  && [history,observeContinuations,policy,clock].every(fn=>typeof fn==='function'),'Trusted fresh collector dependencies unavailable');
 const [owner,repo]=repository.split('/');
 const {withRetry}=await createTokenAwareRetry({github,env:{},tokenRegistry:{isInitialized:()=>false},task:'correction-native-fresh-facts'});
 const read=async(resource,method,args)=>(await withRetry(client=>client.rest[resource][method]({owner,repo,...args,request:{timeout:15000,retries:0}}),
 {maxRetries:2,initialDelay:250,maxDelay:1000})).data;
 const pages=async(resource,method,args)=>{
  const rows=[],ids=new Set();
  for(let page=1;page<=10;page++) {
   const batch=await read(resource,method,{...args,page,per_page:100});
   need(Array.isArray(batch) && batch.length<=100,'Native corrective inventory unavailable');
   for(const row of batch) {
    const id=method==='listEventsForTimeline'?timelineIdentity(row):row.id;
    need((method==='listEventsForTimeline'?typeof id==='string':Number.isSafeInteger(id) && id>0) && !ids.has(id),'Ambiguous native corrective inventory');
    if(method==='listForRepo' || (resource==='pulls' && method==='list'))validateSubjectRow(row);
    if(method==='listEvents') {
     need(typeof row.event==='string','Native issue event type unavailable');
     if(['assigned','unassigned'].includes(row.event))need(typeof row.assignee?.login==='string'
      && typeof row.created_at==='string' && Number.isFinite(Date.parse(row.created_at)),'Native assignment event is incomplete');
    }
    ids.add(id);rows.push(row);
   }
   if(batch.length<100)return rows;
  }
  throw Error('Native corrective inventory exceeds bound; UNKNOWN');
 };
 const connectedReference=async(event,pull)=>{
  need(typeof event.node_id==='string' && event.node_id.length>0 && typeof event.created_at==='string'
   && Number.isFinite(Date.parse(event.created_at)) && typeof pull.node_id==='string','Native connected association identity unavailable');
  const query=`query CorrectionConnected($id:ID!) { node(id:$id) { ... on ConnectedEvent { id createdAt
    source { __typename ... on Issue { id number repository { nameWithOwner } } ... on PullRequest { id number repository { nameWithOwner } } }
    subject { __typename ... on Issue { id number repository { nameWithOwner } } ... on PullRequest { id number repository { nameWithOwner } } }
  } } }`;
  const data=await withRetry(client=>client.graphql(query,{id:event.node_id,request:{timeout:15000,retries:0}}),
   {maxRetries:2,initialDelay:250,maxDelay:1000});
  const node=data.node;
  need(node?.id===event.node_id && typeof node.createdAt==='string' && Date.parse(node.createdAt)===Date.parse(event.created_at),'Native connected event join changed');
  const target=item=>item?.__typename==='PullRequest' && item.id===pull.node_id && item.number===pull.number
   && item.repository?.nameWithOwner?.toLowerCase()===repository;
  need(target(node.source)!==target(node.subject),'Native connected association does not bind exact source PR');
  const other=target(node.source)?node.subject:node.source;
  need(['Issue','PullRequest'].includes(other?.__typename) && typeof other.id==='string' && other.id.length>0
   && Number.isSafeInteger(other.number) && other.number>0 && typeof other.repository?.nameWithOwner==='string',
   'Native connected issue/PR association is incomplete');
  return {number:other.number,node_id:other.id,repository:{full_name:other.repository.nameWithOwner},
   ...(other.__typename==='PullRequest'?{pull_request:{}}:{})};
 };
 return async function collect(request,{createdIssue=null,ownedPull=null,activeEffect=null}={}) {
  need(request.target.repository===repository,'Fresh collector repository scope changed');
  const seed=seedForRequest(request),key=effectKey(seed);
  const [pull,sourceIssue,permission]=await Promise.all([
   read('pulls','get',{pull_number:Number(request.target.pr)}),read('issues','get',{issue_number:Number(request.source_issue.number)}),
   read('repos','getCollaboratorPermissionLevel',{username:actor}),
  ]);
  need(typeof pull.merged_at==='string' && Number.isFinite(Date.parse(pull.merged_at)), 'Authenticated merged-PR history boundary unavailable');
  // A correction effect for this exact merged PR cannot precede its native
  // merged_at. Using the newest verifier run's time could hide older aliases.
  const [opened,changed,openPulls,prTimeline,retained,continuations,verdictPolicy]=await Promise.all([
   pages('issues','listForRepo',{state:'open',sort:'created',direction:'desc'}),
   pages('issues','listForRepo',{state:'all',since:pull.merged_at,sort:'created',direction:'desc'}),
   pages('pulls','list',{state:'open',sort:'created',direction:'desc'}),
   pages('issues','listEventsForTimeline',{issue_number:Number(request.target.pr)}),
   history({since:pull.merged_at,request}),observeContinuations({since:pull.merged_at,request,activeContinuation,ownedPull}),policy({request,pull,sourceIssue}),
  ]);
  need(Array.isArray(retained?.contexts) && Array.isArray(retained?.snapshots) && Array.isArray(continuations),'Complete retained effects/run inventory unavailable');
  const merged=new Map();
  for(const row of [...changed,...opened]) {
   if(merged.has(row.number))need(same(merged.get(row.number),row),'Native corrective facts changed during inventory');
   merged.set(row.number,row);
  }
  const linkedIssues=new Set(),linkedPulls=new Set();
  for(const event of prTimeline)if(['cross-referenced','connected'].includes(event.event)) {
   const linked=event.event==='connected'?await connectedReference(event,pull):event.source?.issue;
   need(linked && Number.isSafeInteger(linked.number) && typeof linked.repository?.full_name==='string',
    'Native PR-linked issue inventory is incomplete');
   if(linked.repository.full_name.toLowerCase()===repository && linked.number===sourceIssue.number && !linked.pull_request)
    need(linked.node_id===sourceIssue.node_id,'Native connected source issue/node changed');
   if(linked.repository.full_name.toLowerCase()===repository && linked.pull_request)linkedPulls.add(linked.number);
   if(linked.repository.full_name.toLowerCase()===repository && !linked.pull_request && linked.number!==sourceIssue.number) {
    linkedIssues.add(linked.number);
    if(!merged.has(linked.number)) {
     const actual=await read('issues','get',{issue_number:linked.number});validateSubjectRow(actual);
     need(actual.node_id===linked.node_id && actual.number===linked.number,'Native linked issue/node changed');
     merged.set(linked.number,actual);
    } else need(merged.get(linked.number).node_id===linked.node_id,'Native linked inventory/node conflicts');
   }
  }
  const prReference=new RegExp(`\\bPR\\s*#${request.target.pr}\\b`,'i');
  const candidates=[...merged.values()].filter(row=>!row.pull_request && row.number!==sourceIssue.number
   && (linkedIssues.has(row.number) || prReference.test(`${row.title}\n${row.body}`) || String(row.body).includes(key)));
  let incumbentIssue=null,assignmentRef=null,lineageRef=null,kind='unknown';
  const declaredNew=request.incumbent.kind==='no_incumbent';
  const selected=createdIssue || (!declaredNew?request.incumbent.issue:null);
  if(selected)incumbentIssue=await read('issues','get',{issue_number:Number(selected.number)});
  const competing=candidates.filter(row=>!selected || row.number!==Number(selected.number));
  const previous=retained.snapshots.flatMap(row=>row.snapshot.records);
  const otherEffects=previous.filter(row=>row.effect_key!==key);
  const ownEffects=previous.filter(row=>row.effect_key===key);
  need(!retained.contexts.some(row=>row.context.decision?.findings?.some(f=>['security','authority_conflict'].includes(f.classification))),
   'Retained qualified-owner hold cannot enter ordinary corrective lane');
  let currentStage=null;
  if(activeEffect) {
   need(activeEffect.schema==='closer-correction-active-stage/v1' && activeEffect.effect_key===key
    && activeEffect.request_sha256===request.request_sha256 && ['issue_creation','autopilot_dispatch'].includes(activeEffect.phase),
    'Private active stage scope differs');
   const matches=retained.snapshots.filter(row=>{
    const proof=row.proof,last=row.snapshot.records.at(-1);
    return proof && activeEffect.proof && ['run_id','run_attempt','artifact_id','archive_sha256','member_sha256']
     .every(field=>proof[field]===activeEffect.proof[field])
     && proof.run_id===transport?.current?.run_id && proof.run_attempt===transport?.current?.run_attempt
     && row.snapshot.revision===activeEffect.revision && last?.revision===activeEffect.revision
     && last.kind==='intent' && last.phase===activeEffect.phase && last.record_sha256===activeEffect.record_sha256
     && last.effect_key===key && last.request_sha256===request.request_sha256
     && last.consumer?.run_id===String(transport.current.run_id) && last.consumer?.run_attempt===String(transport.current.run_attempt);
   });
   need(matches.length===1,'Private active stage native checkpoint unavailable/ambiguous');
   const snapshot=matches[0].snapshot;
   const scoped=retained.snapshots.filter(row=>row.snapshot.records.some(record=>record.effect_key===key));
   need(scoped.length===snapshot.revision && new Set(scoped.map(row=>row.snapshot.revision)).size===snapshot.revision
    && scoped.every(row=>row.snapshot.revision>=1 && row.snapshot.revision<=snapshot.revision
     && same(row.snapshot.records,snapshot.records.slice(0,row.snapshot.revision))),
    'Active stage checkpoint history is missing/forked/stale');
   currentStage={phase:activeEffect.phase,records:snapshot.records};
  }
  if(declaredNew) {
   const exactCreated=createdIssue && incumbentIssue && same(issueIdentity(incumbentIssue),createdIssue)
    && ownEffects.some(row=>row.kind==='intent' && row.phase==='issue_creation' && row.request_sha256===request.request_sha256);
   const active=activeContinuation;
   const ownDispatch=active && active.effect_key===key && active.run_id===transport?.current?.run_id
    && active.run_attempt===transport?.current?.run_attempt && retained.snapshots.some(row=>{
     const proof=row.proof,last=row.snapshot.records.at(-1);
     return proof && active.intent && ['run_id','run_attempt','artifact_id','archive_sha256','member_sha256']
      .every(field=>proof[field]===active.intent[field]) && last?.kind==='intent' && last.phase==='autopilot_dispatch'
      && last.effect_key===key && last.request_sha256===request.request_sha256;
    });
   const activeCreation=currentStage?.phase==='issue_creation' && !createdIssue && currentStage.records.length===1;
   const activeDispatch=currentStage?.phase==='autopilot_dispatch' && exactCreated
    && currentStage.records.length===3 && currentStage.records[0].kind==='intent'
    && currentStage.records[0].phase==='issue_creation' && currentStage.records[1].kind==='issue_confirmed'
    && same(currentStage.records[1].issue,createdIssue);
   const safeOwn=(!ownEffects.length || activeCreation
     || (exactCreated && (activeDispatch || ownDispatch || !ownEffects.some(row=>row.phase==='autopilot_dispatch'))))
    && (!incumbentIssue || assigned(incumbentIssue).length===0);
   if(!competing.length && (!createdIssue || candidates.some(row=>row.number===incumbentIssue?.number && row.node_id===incumbentIssue.node_id))
    && candidates.every(row=>exactCreated && row.number===incumbentIssue.number)
    && safeOwn && !otherEffects.length && !continuations.length)kind='no_incumbent';
  } else if(incumbentIssue && candidates.some(row=>row.number===incumbentIssue.number && row.node_id===incumbentIssue.node_id)
   && !competing.length && !otherEffects.length) {
   // This is the existing assignee-backed path only. Agent-label/queue ownership
   // without genuine native assignment+lineage remains UNKNOWN, never none.
   const events=await pages('issues','listEvents',{issue_number:incumbentIssue.number});
   const timeline=await pages('issues','listEventsForTimeline',{issue_number:incumbentIssue.number});
   const prefix=`github:${repository}/issues/${incumbentIssue.number}`;
   const currentAssignees=assigned(incumbentIssue);
   const currentOwner=currentAssignees.length===1 && currentAssignees.find(person=>person.login===request.incumbent.owner);
   const ownerEvents=events.filter(event=>['assigned','unassigned'].includes(event.event) && event.assignee?.login===request.incumbent.owner);
   ownerEvents.sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at)||a.id-b.id);
   const event=ownerEvents.at(-1);
   need(ownerEvents.every(row=>typeof row.created_at==='string' && Number.isFinite(Date.parse(row.created_at))), 'Assignment event history time unavailable');
   const chain=timeline.filter(row=>row.event==='cross-referenced' && row.source?.issue?.number===Number(request.target.pr)
    && row.source.issue.repository?.full_name?.toLowerCase()===repository && row.source.issue.pull_request);
   if(currentOwner && event?.event==='assigned' && `${prefix}/events/${event.id}`===request.incumbent.assignment_ref
    && chain.some(row=>`${prefix}/timeline-sha256/${crossReferenceDigest(row,pull)}`===request.incumbent.lineage_ref)) {
    const ownerPermission=await read('repos','getCollaboratorPermissionLevel',{username:request.incumbent.owner});
    if(['write','maintain','admin'].includes(ownerPermission.permission)
      && ownerPermission.user?.login===request.incumbent.owner) {
     kind='existing';assignmentRef=request.incumbent.assignment_ref;lineageRef=request.incumbent.lineage_ref;
    }
   }
  }
  const current=clock();need(current instanceof Date && Number.isFinite(current.getTime()),'Fresh observation time unavailable');
  const ownership={schema:'closer-correction-ownership/v1',kind,seed_effect_key:key,source_scope_digest:sourceScopeDigest(seed),observed_at:current.toISOString(),
   evidence_refs:[`github:${repository}/pulls/${pull.number}`,`github:${repository}/issues/${sourceIssue.number}`,
    `github:${repository}/issues?state=open+updated-since:${pull.merged_at}`,'actions:complete-correction-ledger-and-continuation-inventory'],
   ...(kind==='existing'?{incumbent:{...request.incumbent,issue:issueIdentity(incumbentIssue)}}:{})};
  const registryBytes=fs.readFileSync(registryPath),registry=loadAgentRegistry({registryPath});
  const agentKey=resolveAgentFromLabels(pull.labels,{registryPath}),agent=registry.agents[agentKey];
  const linkedNumbers=[Number(request.target.pr),sourceIssue.number,...candidates.map(row=>row.number),...(incumbentIssue?[incumbentIssue.number]:[])];
  const linked=new RegExp(`(?:#|/issues/)(?:${linkedNumbers.join('|')})\\b`);
  const workInventory={complete:true,continuations,openPullRequests:openPulls.filter(row=>linkedPulls.has(row.number) || linked.test(`${row.title}\n${row.body}`)),
   assignments:candidates.flatMap(row=>assigned(row).map(user=>({issue:row.number,owner:user.login}))),
   retainedEffects:otherEffects.length?otherEffects.map(row=>({effect_key:row.effect_key,state:'unknown'})):
    (ownEffects.length && !(currentStage?.phase==='issue_creation' && kind==='no_incumbent')?[{effect_key:key,state:createdIssue?'issue_confirmed':'unknown',issue:createdIssue}]:[])};
  if(ownership.kind==='no_incumbent' && (workInventory.openPullRequests.some(row=>!ownedPull || row.id!==ownedPull.pull.id || row.node_id!==ownedPull.pull.node_id
      || row.head?.sha!==ownedPull.observed_head_sha) || workInventory.assignments.length
    || (incumbentIssue && labels(incumbentIssue).some(label=>label.startsWith('agent:') && !['agent:retry','agent:rate-limited','agent:needs-attention'].includes(label) && label!==`agent:${agentKey}`)))) {
    ownership.kind='unknown';
  }
  return {pull,sourceIssue,incumbentIssue,ownership,assignmentRef,lineageRef,chainDepth:chainDepth(pull,sourceIssue),verdictPolicy,
   dispatchActorPermission:permission.user?.login?.toLowerCase()===actor.toLowerCase()?permission.permission:null,workInventory,
   agent:{key:agentKey,enabled:agent?.enabled===true,registry_sha256:sha(registryBytes)}};
 };
}
module.exports={createFreshCollector,chainDepth,timelineIdentity,crossReferenceDigest,crossReferenceProjection};

async function createEffectReconciler({transport,request,history,since}) {
 const {validateLedger}=require('./verifier_correction_effects');
 const {observeStartedReceipts}=require('./verifier_correction_autopilot');
 const key=effectKey(seedForRequest(request));
 need(typeof history==='function' && typeof since==='string' && Number.isFinite(Date.parse(since)),'Complete causal reconciliation dependencies unavailable');
 return async function reconcile({effect_key,records}) {
  need(effect_key===key,'Reconciliation changed trusted seed scope');
  validateLedger({revision:records.length,records},key);
  const creation=records.find(row=>row.kind==='intent' && row.phase==='issue_creation'),issues=[];
  if(creation) {
   const confirmed=records.find(row=>row.kind==='issue_confirmed');
   // Searchable marker text is never an attestation of which POST created an
   // issue. Without the retained native response, uncertain creation stays held.
   if(confirmed) {
    const row=await transport.read('issues','get',{issue_number:Number(confirmed.issue.number)});
    validateSubjectRow(row);
    if(!row.pull_request && same(issueIdentity(row),confirmed.issue))issues.push(row);
   }
  }
  const dispatch=records.find(row=>row.kind==='intent' && row.phase==='autopilot_dispatch');
  if(!dispatch)return {issues};
  const retained=await history({since,request});
  const snapshots=retained.snapshots.filter(row=>row.key===key && row.snapshot.revision===dispatch.revision
   && row.snapshot.records.at(-1).record_sha256===dispatch.record_sha256);
  need(snapshots.length===1,'Exact original retained dispatch intent proof unavailable');
  const intent=snapshots[0].proof;
  const contexts=retained.contexts.filter(row=>row.context.effect_key===key && row.context.request.request_sha256===request.request_sha256
   && String(row.proof.run_id)===dispatch.consumer.run_id && String(row.proof.run_attempt)===dispatch.consumer.run_attempt);
  need(contexts.length===1,'Exact original admitted collector context unavailable');
  const known=records.find(row=>row.kind==='issue_confirmed')?.issue || request.incumbent.issue;
  need(known,'Actual continuation has no immutable incumbent issue binding');
  const sameProof=(a,b)=>a && b && ['run_id','run_attempt','artifact_id','archive_sha256','member_sha256'].every(field=>a[field]===b[field]);
  const roots=(await observeStartedReceipts({transport,request,since})).filter(row=>row.receipt.parent_dispatch===null);
  if(!roots.length)return {issues};
  need(roots.length===1 && sameProof(roots[0].receipt.intent,intent) && sameProof(roots[0].receipt.collector,contexts[0].proof)
   && same(roots[0].receipt.issue,known) && roots[0].receipt.selected_step==='optimize','Ambiguous/substituted original auto-pilot admission');
  const root=roots[0].receipt;
  return {issues,request,issue:known,continuation:{workflow:'agents-auto-pilot.yml',run_id:String(root.run_id),run_attempt:String(root.run_attempt),
   request_sha256:request.request_sha256,issue_node_id:known.node_id}};
 };
}
module.exports.createEffectReconciler=createEffectReconciler;
