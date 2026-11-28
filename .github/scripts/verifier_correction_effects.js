'use strict';

// Effect identity for correction requests: seed, scope digest, effect key, issue
// identity and ledger validation. The Auto-Pilot dispatch consumer that used to live
// here was removed with Auto-Pilot (#5379); no effect producer is wired.
const {createHash} = require('crypto');
const {canonical,digest} = require('./verification_event');
const {validateRequest,nativeBody} = require('./verifier_correction_consumer');
const SHA = /^[a-f0-9]{64}$/;
const isSha = value => typeof value === 'string' && SHA.test(value);
const sha = value => createHash('sha256').update(value).digest('hex');
const requireInventory = (value,message) => {if (!value) {const error=new Error(message);error.code='CORRECTION_INVENTORY_UNKNOWN';throw error;}};
const requireThat = (value,message) => {if (!value) throw new Error(message);};
const same = (left,right) => canonical(left) === canonical(right);

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
    && typeof issue.node_id === 'string' && issue.node_id.length > 0
    && !issue.pull_request, 'Exact issue identity unavailable');
  return {number:String(issue.number),node_id:issue.node_id,body_sha256:sha(nativeBody(issue.body))};
}
function validateIssueResponse(proof,request,key,consumer) {
  requireThat(proof?.schema==='closer-correction-issue-response/v1' && proof.http_status===201
    && proof.request_sha256===request.request_sha256 && proof.effect_key===key && same(proof.consumer,consumer)
    && typeof proof.github_request_id==='string' && proof.github_request_id.length>0 && proof.github_request_id.length<=4096
    && proof.creator?.id===41898282 && proof.creator.login==='github-actions[bot]' && proof.creator.type==='Bot'
    && typeof proof.created_at==='string' && Number.isFinite(Date.parse(proof.created_at))
    && proof.issue && typeof proof.issue.number==='string' && /^[1-9]\d{0,15}$/.test(proof.issue.number)
    && typeof proof.issue.node_id==='string' && isSha(proof.issue.body_sha256), 'Original native issue-creation response proof unavailable');
  return proof;
}
function validateOwnership(value,seed) {
  const fields=['schema','kind','seed_effect_key','source_scope_digest','observed_at','evidence_refs',...(value?.kind==='existing'?['incumbent']:[])].sort();
  requireThat(value && same(Object.keys(value).sort(),fields), 'Unexpected trusted ownership fields');
  requireThat(value?.schema === 'closer-correction-ownership/v1'
    && ['existing','no_incumbent','unknown'].includes(value.kind)
    && value.seed_effect_key === effectKey(seed) && value.source_scope_digest === sourceScopeDigest(seed)
    && typeof value.observed_at === 'string' && Number.isFinite(Date.parse(value.observed_at))
    && Array.isArray(value.evidence_refs) && value.evidence_refs.length > 0
    && value.evidence_refs.every(ref => typeof ref === 'string' && ref.length > 0 && ref.length <= 4096), 'Trusted fresh ownership binding unavailable');
  if (value.kind === 'existing') requireThat(value.incumbent && typeof value.incumbent === 'object', 'Existing incumbent evidence unavailable');
  else requireThat(!Object.hasOwn(value,'incumbent'), 'No-incumbent/unknown evidence cannot assert an incumbent');
  return value;
}
function checkFreshFacts(request,facts,{ownership = null,createdIssue = null,incumbentIssue = null,ownedFormatPauseIssue = null} = {}) {
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
    const expected=incumbentIssue || request.incumbent.issue;
    requireThat(expected.number===request.incumbent.issue.number && expected.node_id===request.incumbent.issue.node_id,
      'Current incumbent cannot replace original issue/node');
    requireThat(same(issueIdentity(facts.incumbentIssue),expected)
      && facts.incumbentIssue.state === 'open'
      && facts.incumbentIssue.assignees?.some(person => person.login === request.incumbent.owner), 'Current incumbent assignment changed');
    if (ownership) requireThat(same(ownership.incumbent,{...request.incumbent,issue:expected}), 'Declared incumbent differs from trusted current owner');
    requireThat(facts.assignmentRef === request.incumbent.assignment_ref
      && facts.lineageRef === request.incumbent.lineage_ref, 'Fresh corrective-owner evidence unavailable');
    issues.push(facts.incumbentIssue);
  }
  if(ownedFormatPauseIssue)requireThat(facts.incumbentIssue && same(issueIdentity(facts.incumbentIssue),ownedFormatPauseIssue),
    'Owned formatter pause proof cannot refer to another issue');
  requireThat(!issues.some(issue => labels(issue).some(label =>
    ['needs-human','agents:auto-pilot-failed','agents:paused'].includes(label)
    || (label==='agents:auto-pilot-pause' && (!ownedFormatPauseIssue || issue.node_id!==ownedFormatPauseIssue.node_id)))),
  'Current corrective lane is held');
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
      && isSha(agent.registry_sha256), 'Enabled registry-derived correction agent unavailable');
  }
}
function confirmedIssue(snapshot) {
  const confirmed=snapshot.records.filter(row=>row.kind==='issue_confirmed');
  if (!confirmed.length) return null;
  requireThat(new Set(confirmed.map(row=>canonical(row.issue))).size===1, 'Conflicting durable created-issue identities');
  return confirmed[0].issue;
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
      && isSha(record.request_sha256), 'Existing follow-up ledger binding corrupt');
    if (record.kind==='issue_confirmed') {
      const issue=record.issue;
      requireThat(record.phase==='issue_creation' && issue && same(Object.keys(issue).sort(),['body_sha256','node_id','number'])
        && typeof issue.number==='string' && /^[1-9]\d{0,15}$/.test(issue.number)
        && typeof issue.node_id==='string' && issue.node_id.length>0 && isSha(issue.body_sha256)
        && record.creation_response?.schema==='closer-correction-issue-response/v1'
        && record.creation_response.http_status===201 && same(record.creation_response.issue,issue)
        && record.creation_response.request_sha256===record.request_sha256 && record.creation_response.effect_key===key
        && same(record.creation_response.consumer,record.consumer)
        && snapshot.records.slice(0,index).some(row=>row.kind==='intent' && row.phase==='issue_creation'
          && row.request_sha256===record.request_sha256), 'Durable created issue lacks exact original intent');
      validateIssueResponse(record.creation_response,{request_sha256:record.request_sha256},key,record.consumer);
    }
  }
  confirmedIssue(snapshot);
  return snapshot;
}

module.exports={validateIssueResponse,seedForRequest,sourceScopeDigest,effectKey,issueIdentity,validateOwnership,checkFreshFacts,validateLedger};
