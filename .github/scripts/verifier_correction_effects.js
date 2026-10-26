'use strict';

// Local effect-side adapter for the EXISTING follow-up issue / auto-pilot lane.
// No live defaults or Actions wiring: trusted authentication, durable existing-
// ledger transport and actual started-receipt transport are integration gaps.
const {createHash} = require('crypto');
const {canonical,digest} = require('./verification_event');
const {validateRequest,receipt} = require('./verifier_correction_consumer');
const SHA = /^[a-f0-9]{64}$/;
const sha = value => createHash('sha256').update(value).digest('hex');
const requireThat = (value,message) => {if (!value) throw new Error(message);};
const requireInventory = (value,message) => {if (!value) {const error=new Error(message);error.code='CORRECTION_INVENTORY_UNKNOWN';throw error;}};
const same = (left,right) => canonical(left) === canonical(right);
const ACCEPTED = 'accepted_with_exact_issue_and_actual_autopilot_run_attempt';

function seedForRequest(request) {
  validateRequest(request);
  return {schema:'closer-correction-seed/v1',target:request.target,source_issue:request.source_issue,
    original_verifier:request.original_verifier,finding:request.finding,scope:request.scope};
}
function sourceScopeDigest(seed) {
  return digest({target:seed.target,source_issue:seed.source_issue,
    finding_evidence:seed.finding.evidence,scope:seed.scope});
}
function effectKey(seed) {
  // Caller request/hold/idempotency, display finding IDs and mutable incumbent
  // assignments cannot create another writer for the same original raw finding.
  return digest({schema:'closer-correction-effect/v1',repository:seed.target.repository,
    event_id:seed.original_verifier.verification_event.event_id,
    finding_evidence:seed.finding.evidence,source_issue:seed.source_issue,scope:seed.scope});
}
function issueIdentity(issue) {
  requireThat(issue && Number.isSafeInteger(issue.number) && issue.number > 0
    && typeof issue.node_id === 'string' && issue.node_id.length > 0 && typeof issue.body === 'string'
    && !issue.pull_request, 'Exact issue identity unavailable');
  return {number:String(issue.number),node_id:issue.node_id,body_sha256:sha(issue.body)};
}
function validateOwnership(value,seed) {
  const fields=['schema','kind','seed_effect_key','source_scope_digest','observed_at','evidence_refs',...(value?.kind==='existing'?['incumbent']:[])].sort();
  requireThat(value && same(Object.keys(value).sort(),fields), 'Unexpected trusted ownership fields');
  requireThat(value?.schema === 'closer-correction-ownership/v1'
    && ['existing','no_incumbent','unknown'].includes(value.kind)
    && value.seed_effect_key === effectKey(seed) && value.source_scope_digest === sourceScopeDigest(seed)
    && Number.isFinite(Date.parse(value.observed_at))
    && Array.isArray(value.evidence_refs) && value.evidence_refs.length > 0
    && value.evidence_refs.every(ref => typeof ref === 'string' && ref.length > 0), 'Trusted fresh ownership binding unavailable');
  if (value.kind === 'existing') requireThat(value.incumbent && typeof value.incumbent === 'object', 'Existing incumbent evidence unavailable');
  else requireThat(!Object.hasOwn(value,'incumbent'), 'No-incumbent/unknown evidence cannot assert an incumbent');
  return value;
}
function checkFreshFacts(request,facts,{ownership = null,createdIssue = null} = {}) {
  const labels = issue => {
    requireInventory(Array.isArray(issue?.labels), 'Fresh label inventory unavailable');
    return issue.labels.map(label => typeof label === 'string' ? label : label.name);
  };
  const target=request.target;
  requireThat(facts?.pull?.merged === true && facts.pull.head?.sha === target.head_sha
    && facts.pull.base?.sha === target.base_sha && facts.pull.merge_commit_sha === target.merge_sha
    && facts.pull.base?.repo?.full_name?.toLowerCase() === target.repository, 'Current merged PR binding changed');
  requireThat(same(issueIdentity(facts.sourceIssue),request.source_issue), 'Current source issue binding changed');
  const issues=[facts.pull,facts.sourceIssue];
  if (ownership?.kind === 'no_incumbent') {
    if (createdIssue) {
      requireThat(same(issueIdentity(facts.incumbentIssue),createdIssue)
        && facts.incumbentIssue.state === 'open' && Array.isArray(facts.incumbentIssue.assignees)
        && facts.incumbentIssue.assignees.length === 0, 'Created issue acquired another owner or changed binding');
      issues.push(facts.incumbentIssue);
    } else requireThat(facts.incumbentIssue === null, 'No-incumbent collector conflicts with existing issue');
  } else {
    requireThat(same(issueIdentity(facts.incumbentIssue),request.incumbent.issue)
      && facts.incumbentIssue.state === 'open'
      && facts.incumbentIssue.assignees?.some(person => person.login === request.incumbent.owner), 'Current incumbent assignment changed');
    if (ownership) requireThat(same(ownership.incumbent,request.incumbent), 'Declared incumbent differs from trusted current owner');
    requireThat(facts.assignmentRef === request.incumbent.assignment_ref
      && facts.lineageRef === request.incumbent.lineage_ref, 'Fresh corrective-owner evidence unavailable');
    issues.push(facts.incumbentIssue);
  }
  requireThat(!issues.some(issue => labels(issue).some(label =>
    ['needs-human','agents:auto-pilot-pause','agents:auto-pilot-failed','agents:paused'].includes(label))), 'Current corrective lane is held');
  requireInventory(Number.isSafeInteger(facts.chainDepth) && facts.chainDepth >= 0, 'Follow-up chain inventory unavailable');
  requireThat(facts.chainDepth < 2, 'Follow-up chain limit reached');
  requireThat(facts.verdictPolicy === 'follow-up' && ['admin','maintain','write'].includes(facts.dispatchActorPermission), 'Existing dispatch/policy authority unavailable');
  const inventory=facts.workInventory;
  requireInventory(inventory?.complete === true && ['continuations','openPullRequests','assignments','retainedEffects'].every(key => Array.isArray(inventory[key])), 'Complete existing corrective-work inventory unavailable');
  if (ownership?.kind === 'no_incumbent') {
    requireInventory(inventory.assignments.length === 0 && (inventory.retainedEffects.length === 0
      || (createdIssue && inventory.retainedEffects.every(row => row.effect_key === effectKey(seedForRequest(request))
        && row.state === 'issue_confirmed' && same(row.issue,createdIssue)))),
      'No-incumbent evidence includes unknown/starting/denied or assigned work');
    const agent=facts.agent;
    requireThat(agent?.enabled === true && /^[a-z0-9][a-z0-9-]*$/.test(agent.key || '')
      && SHA.test(agent.registry_sha256), 'Enabled registry-derived correction agent unavailable');
  }
}
function validateLedger(snapshot,key) {
  requireThat(snapshot && Number.isSafeInteger(snapshot.revision) && snapshot.revision >= 0
    && Array.isArray(snapshot.records) && snapshot.revision === snapshot.records.length, 'Complete existing follow-up ledger unavailable');
  for (let index=0;index<snapshot.records.length;index++) {
    const record=snapshot.records[index],{record_sha256,...payload}=record;
    requireThat(record.schema === 'closer-correction-effect-ledger/v1' && record.effect_key === key
      && record.revision === index+1 && digest(payload) === record_sha256
      && ['intent','issue_confirmed'].includes(record.kind)
      && ['issue_creation','autopilot_dispatch'].includes(record.phase)
      && SHA.test(record.request_sha256), 'Existing follow-up ledger binding corrupt');
  }
  return snapshot;
}
async function appendRecord({ledger,snapshot,key,request,consumer,kind,phase,ownership=null,issue=null}) {
  const payload={schema:'closer-correction-effect-ledger/v1',effect_key:key,revision:snapshot.revision+1,
    kind,phase,request_sha256:request.request_sha256,consumer,...(ownership?{ownership}:{}),...(issue?{issue}:{})};
  const record={...payload,record_sha256:digest(payload)};
  const stored=await ledger.append({effect_key:key,expected_revision:snapshot.revision,record});
  requireThat(same(stored,record),'Durable intent acknowledgment mismatch');
  return record;
}
async function attemptEffect({ledger,snapshot,key,request,consumer,phase,invoke,ownership=null}) {
  validateRequest(request);receipt(request,{reason:'validate_consumer_before_effect',consumer});validateLedger(snapshot,key);
  requireThat(['issue_creation','autopilot_dispatch'].includes(phase) && typeof invoke === 'function', 'Unsupported correction effect');
  if (snapshot.records.some(row=>row.kind==='intent' && row.phase===phase)) {
    return {state:'outcome_unknown',reason:'original_stage_intent_already_exists_no_repeat'};
  }
  try {await appendRecord({ledger,snapshot,key,request,consumer,kind:'intent',phase,ownership});}
  catch {return {state:'outcome_unknown',reason:'durable_intent_not_confirmed_no_effect_invoked'};}
  try {await invoke();return {state:'outcome_unknown',reason:`${phase}_invoked_requires_authenticated_reconciliation`};}
  catch {return {state:'outcome_unknown',reason:`${phase}_response_uncertain_reconcile_original_intent`};}
}
function issueMarker(request,intent) {
  return `<!-- closer-correction-effect/v1 ${canonical({effect_key:intent.effect_key,request_sha256:request.request_sha256,consumer:intent.consumer})} -->`;
}
async function reconcileIssueCreation({request,intent,observe}) {
  validateRequest(request);
  const key=effectKey(seedForRequest(request)),{record_sha256,...payload}=intent;
  requireThat(digest(payload) === record_sha256 && intent.kind === 'intent' && intent.phase === 'issue_creation'
    && intent.effect_key === key && intent.request_sha256 === request.request_sha256, 'Original create intent binding unavailable');
  const unknown=reason=>({effect_state:'outcome_unknown',reason,issue:null,retry_authorized:false});
  let issues;try {issues=await observe({effect_key:key,original_intent:intent});}
  catch {return unknown('original_issue_creation_observation_unavailable');}
  if (!Array.isArray(issues) || issues.length !== 1) return unknown('original_issue_creation_absent_or_ambiguous_no_repeat');
  try {
    requireThat(issues[0].body?.split(issueMarker(request,intent)).length === 2, 'Exact original issue marker unavailable');
    return {effect_state:'outcome_unknown',reason:'exact_issue_known_actual_autopilot_continuation_not_established',
      issue:issueIdentity(issues[0]),retry_authorized:false};
  } catch {return unknown('original_issue_creation_binding_mismatch');}
}
function createPayload(request,facts,intent) {
  const tasks=request.required_tests.map(row => row.kind === 'required_test_spec'
    ? `- [ ] ${row.specification}` : `- [ ] Verify existing test ${row.source_ref}:${row.path} / ${row.selector} (${row.file_sha256})`);
  return {title:`[Follow-up] PR #${request.target.pr}: ${request.finding.id}`,
    body:[`<!-- follow-up-depth: ${facts.chainDepth+1} -->`,issueMarker(request,intent),'## Why','',
      `Exact verification finding ${request.finding.id} from PR #${request.target.pr}.`,'','## Scope','',
      `${request.finding.evidence.ref} (${request.finding.evidence.sha256})`,'','## Tasks','',...tasks,'',
      '## Acceptance Criteria','','- [ ] Address the exact source-bound finding and required tests.'].join('\n'),
    // Single activation via explicit dispatch. Adding agents:auto-pilot here
    // would also trigger a label-event run and could create a parallel writer.
    labels:['follow-up',`agent:${facts.agent.key}`,`from:${facts.agent.key}`,`runner:${facts.agent.key}`]};
}

function createCorrectionEffectConsumer({authenticate,collectFreshFacts,ledger,reconcile,github,defaultBranch,clock}) {
  requireThat([authenticate,collectFreshFacts,reconcile,clock].every(value => typeof value === 'function')
    && typeof ledger?.read === 'function' && typeof ledger?.append === 'function'
    && typeof github?.rest?.actions?.createWorkflowDispatch === 'function'
    && typeof defaultBranch === 'string' && defaultBranch.length > 0, 'Trusted effect dependencies unavailable');
  return async function consume(selector,consumer) {
    const admission=await authenticate(selector),request=validateRequest(admission.request),seed=seedForRequest(request);
    receipt(request,{reason:'validate_consumer_before_effect',consumer});
    requireThat(same(admission.seed,seed),'Request differs from authenticated original finding seed');
    requireThat(same(admission.required_tests,request.required_tests), 'Request differs from authenticated source-bound required-test decision');
    const key=effectKey(seed),[owner,repo]=request.target.repository.split('/');
    let ownership=null;
    const finish=(state,reason,issue=null,continuation=null)=>receipt(request,{state,reason,issue,continuation,consumer,ownership});
    const read=async()=>validateLedger(await ledger.read(key),key);
    let snapshot;try {snapshot=await read();}catch {return finish('outcome_unknown','existing_followup_ledger_unavailable_no_effect_invoked');}
    const observe=async()=>reconcile({effect_key:key,seed,records:snapshot.records});
    let issue=null,observed=null;
    if (snapshot.records.length) {
      // Always reconcile old effects before later expiry or policy changes.
      try {observed=await observe();}catch {return finish('outcome_unknown','prior_effect_reconciliation_unavailable');}
      const origin=snapshot.records.find(row=>row.kind==='intent');
      if (origin?.ownership) {
        try {ownership=validateOwnership(origin.ownership,seed);}catch {return finish('outcome_unknown','prior_ownership_binding_unavailable');}
      }
      if (observed?.continuation) {
        try {requireThat(same(observed.request,request),'Reconciled request differs');return finish(ACCEPTED,'authenticated_actual_autopilot_continuation',observed.issue,observed.continuation);}
        catch {return finish('outcome_unknown','prior_continuation_binding_unproven_no_repeat');}
      }
      if (snapshot.records.some(row=>row.phase==='autopilot_dispatch')) return finish('outcome_unknown','prior_effect_requires_exact_reconciliation_no_repeat');
      const creation=snapshot.records.find(row=>row.phase==='issue_creation' && row.kind==='intent');
      if (!creation || creation.request_sha256 !== request.request_sha256 || ownership?.kind !== 'no_incumbent') {
        return finish('outcome_unknown','prior_effect_requires_exact_reconciliation_no_repeat');
      }
      const resolved=await reconcileIssueCreation({request,intent:creation,observe:async()=>observed?.issues});
      if (!resolved.issue) return finish('outcome_unknown',resolved.reason);
      issue=resolved.issue;
    }
    if (clock().getTime() >= Date.parse(request.original_operation.deadline)) {
      return finish(snapshot.records.length?'outcome_unknown':'confirmed_not_started','requester_deadline_expired_before_remaining_stage',issue);
    }
    let facts;
    try {facts=await collectFreshFacts(request,{createdIssue:issue});}
    catch {return finish('outcome_unknown','fresh_github_ownership_inventory_unread',issue);}
    try {if (!ownership) ownership=validateOwnership(facts.ownership,seed);}
    catch {return finish('outcome_unknown','trusted_ownership_provenance_unavailable',issue);}
    if (ownership.kind==='unknown') return finish('outcome_unknown','trusted_ownership_inventory_unknown');
    try {
      requireThat((ownership.kind==='no_incumbent') === (request.incumbent.kind==='no_incumbent'), 'Declared incumbent conflicts with fresh trusted ownership');
      checkFreshFacts(request,facts,{ownership,createdIssue:issue});
    } catch (error) {return finish(snapshot.records.length || error.code==='CORRECTION_INVENTORY_UNKNOWN'?'outcome_unknown':'confirmed_not_started','fresh_source_incumbent_or_policy_gate_refused_before_effect',issue);}
    if (facts.workInventory.continuations.length || facts.workInventory.openPullRequests.length) return finish('outcome_unknown','incumbent_continuation_exists_reconcile_without_dispatch',issue);
    if (clock().getTime() >= Date.parse(request.original_operation.deadline)) return finish(snapshot.records.length?'outcome_unknown':'confirmed_not_started','requester_deadline_expired_during_fresh_collection',issue);
    if (ownership.kind==='no_incumbent' && !issue) {
      requireThat(typeof github.rest.issues?.create==='function','Existing issue creation endpoint unavailable');
      await attemptEffect({ledger,snapshot,key,request,consumer,phase:'issue_creation',ownership,invoke:async()=>{
        requireThat(clock().getTime()<Date.parse(request.original_operation.deadline),'Requester deadline expired after durable intent');
        const intent={effect_key:key,consumer};
        return github.rest.issues.create({owner,repo,...createPayload(request,facts,intent)});
      }});
      try {snapshot=await read();observed=await observe();}catch {return finish('outcome_unknown','issue_creation_requires_exact_reconciliation');}
      const intent=snapshot.records.find(row=>row.kind==='intent' && row.phase==='issue_creation');
      if (!intent || intent.request_sha256 !== request.request_sha256) return finish('outcome_unknown','issue_creation_intent_unavailable_or_different_request_no_repeat');
      const resolved=await reconcileIssueCreation({request,intent,observe:async()=>observed?.issues});
      if (!resolved.issue) return finish('outcome_unknown',resolved.reason);
      issue=resolved.issue;
      // Freshly read the created issue and competing-work inventory before the
      // next stage. An issue acknowledgment alone is never ownership acceptance.
      try {facts=await collectFreshFacts(request,{createdIssue:issue});checkFreshFacts(request,facts,{ownership,createdIssue:issue});}
      catch {return finish('outcome_unknown','created_issue_fresh_gate_unavailable',issue);}
      if (facts.workInventory.continuations.length || facts.workInventory.openPullRequests.length) return finish('outcome_unknown','created_issue_has_existing_work_no_dispatch',issue);
    }
    issue=issue || request.incumbent.issue;
    if (ownership.kind==='no_incumbent' && !snapshot.records.some(row=>row.kind==='issue_confirmed')) {
      try {await appendRecord({ledger,snapshot,key,request,consumer,kind:'issue_confirmed',phase:'issue_creation',ownership,issue});snapshot=await read();}
      catch {return finish('outcome_unknown','created_issue_retention_uncertain_no_dispatch',issue);}
    }
    const outcome=await attemptEffect({ledger,snapshot,key,request,consumer,phase:'autopilot_dispatch',ownership,invoke:()=>{
      requireThat(clock().getTime()<Date.parse(request.original_operation.deadline),'Requester deadline expired after durable intent');
      return github.rest.actions.createWorkflowDispatch({owner,repo,workflow_id:'agents-auto-pilot.yml',ref:defaultBranch,
        inputs:{issue_number:issue.number,force_step:'optimize',correction_request_sha256:request.request_sha256,correction_effect_key:key}});
    }});
    try {
      snapshot=await read();observed=await observe();
      if (observed?.continuation && same(observed.request,request)) return finish(ACCEPTED,'authenticated_actual_autopilot_continuation',observed.issue,observed.continuation);
    } catch { /* Retain original uncertain effect, never repeat. */ }
    return finish(outcome.state,outcome.reason,issue);
  };
}
module.exports={seedForRequest,sourceScopeDigest,effectKey,issueIdentity,validateOwnership,checkFreshFacts,validateLedger,attemptEffect,reconcileIssueCreation,createCorrectionEffectConsumer};
