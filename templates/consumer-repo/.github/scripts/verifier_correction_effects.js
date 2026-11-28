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

module.exports={validateIssueResponse,seedForRequest,sourceScopeDigest,effectKey,issueIdentity,validateLedger};
