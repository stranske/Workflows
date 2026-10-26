'use strict';

// Admission beside verify:create-new-pr. No issue/dispatch mutation lives here.
const fs = require('fs');
const path = require('path');
const {createHash} = require('crypto');
const {canonical, digest, validateEvent, completedEvent} = require('./verification_event');
const {acquireRetainedExecution, readRetainedArchive} = require('./verifier_pending_execution');
const SHA = /^[a-f0-9]{64}$/;
const COMMIT = /^[a-f0-9]{40}$/;
const ID = /^[1-9]\d{0,15}$/;
const MEMBER = 'closer-correction-request.json';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const requireThat = (ok, reason) => { if (!ok) throw new Error(reason); };
const exact = (row, keys) => row && typeof row === 'object' && !Array.isArray(row)
  && Object.keys(row).sort().join(',') === keys.split(' ').sort().join(',');
const text = value => typeof value === 'string' && value.length > 0 && value.length <= 4096;
const identity = row => exact(row, 'number node_id body_sha256') && ID.test(row.number)
  && typeof row.number === 'string' && text(row.node_id) && SHA.test(row.body_sha256);
const evidence = row => exact(row, 'ref sha256') && text(row.ref) && SHA.test(row.sha256);

function validateRequest(request) {
  requireThat(exact(request, 'schema request_sha256 target source_issue original_verifier finding required_tests incumbent original_operation scope'), 'Invalid correction request fields');
  requireThat(request.schema === 'closer-correction-request/v1', 'Unsupported correction request');
  const {request_sha256, ...payload} = request;
  requireThat(SHA.test(request_sha256) && digest(payload) === request_sha256, 'Correction request digest mismatch');
  const t = request.target;
  requireThat(exact(t, 'repository pr head_sha base_sha merge_sha') && /^[^/\s]+\/[^/\s]+$/.test(t.repository)
    && t.repository === t.repository.toLowerCase() && typeof t.pr === 'string' && ID.test(t.pr)
    && [t.head_sha,t.base_sha,t.merge_sha].every(value => COMMIT.test(value)), 'Invalid correction target');
  requireThat(identity(request.source_issue), 'Invalid source issue binding');
  const v = request.original_verifier;
  requireThat(exact(v, 'verification_event run_id run_attempt comment_id comment_sha256 decision_sha256')
    && [v.run_id,v.run_attempt,v.comment_id].every(value => typeof value === 'string' && ID.test(value))
    && SHA.test(v.comment_sha256) && SHA.test(v.decision_sha256), 'Invalid original verifier binding');
  const event = validateEvent(v.verification_event);
  requireThat(event.repo === t.repository && event.pr === t.pr && event.head_sha === t.head_sha
    && event.evaluated_sha === t.merge_sha, 'Original verifier target mismatch');
  requireThat(exact(request.finding, 'id evidence') && text(request.finding.id)
    && evidence(request.finding.evidence), 'Invalid exact finding');
  requireThat(Array.isArray(request.required_tests) && request.required_tests.length > 0
    && request.required_tests.length <= 20, 'Explicit required tests missing');
  for (const test of request.required_tests) {
    const common = typeof test?.id === 'string' && text(test.id) && test.finding_id === request.finding.id;
    if (test.kind === 'existing_selector') {
      requireThat(common && exact(test, 'kind id finding_id source_ref path selector file_sha256')
        && text(test.source_ref) && text(test.path) && !test.path.startsWith('/')
        && !test.path.split('/').includes('..') && text(test.selector) && SHA.test(test.file_sha256), 'Invalid existing required-test selector');
    } else {
      requireThat(common && test?.kind === 'required_test_spec'
        && exact(test, 'kind id finding_id specification source_evidence')
        && text(test.specification) && evidence(test.source_evidence)
        && test.source_evidence.ref === request.finding.evidence.ref
        && test.source_evidence.sha256 === request.finding.evidence.sha256, 'Invalid required-test specification');
    }
  }
  requireThat(new Set(request.required_tests.map(test => test.id)).size === request.required_tests.length, 'Duplicate required-test identity');
  const i = request.incumbent;
  requireThat(exact(i, 'issue owner assignment_ref lineage_ref') && identity(i.issue)
    && text(i.owner) && text(i.assignment_ref) && text(i.lineage_ref), 'Invalid incumbent binding');
  const op = request.original_operation;
  requireThat(exact(op, 'hold_id run_id operation_id idempotency_key deadline attempt_budget escalation_owner')
    && [op.hold_id,op.run_id,op.operation_id,op.idempotency_key,op.escalation_owner].every(text)
    && typeof op.deadline === 'string' && Number.isFinite(Date.parse(op.deadline))
    && Number.isSafeInteger(op.attempt_budget) && op.attempt_budget > 0 && op.attempt_budget <= 10, 'Invalid original operation');
  requireThat(request.scope === 'substantive_implementation', 'Correction scope requires qualified owner');
  return request;
}

function receipt(request, {state = 'confirmed_not_started', reason, issue = null, continuation = null, consumer}) {
  validateRequest(request);
  requireThat(['confirmed_not_started','accepted_with_exact_issue_and_actual_autopilot_run_attempt','outcome_unknown'].includes(state), 'Invalid effect state');
  requireThat(text(reason) && exact(consumer, 'run_id run_attempt')
    && Object.values(consumer).every(value => typeof value === 'string' && ID.test(value)), 'Invalid consumer execution');
  if (issue !== null) requireThat(identity(issue) && canonical(issue) === canonical(request.incumbent.issue), 'Receipt incumbent mismatch');
  if (state === 'accepted_with_exact_issue_and_actual_autopilot_run_attempt') {
    // This constructor validates shape only. The eventual effect producer must
    // authenticate the run's exact issue/request binding before choosing it.
    requireThat(issue && exact(continuation, 'workflow run_id run_attempt request_sha256 issue_node_id')
      && continuation.workflow === 'agents-auto-pilot.yml'
      && [continuation.run_id,continuation.run_attempt].every(value => typeof value === 'string' && ID.test(value))
      && continuation.request_sha256 === request.request_sha256
      && continuation.issue_node_id === issue.node_id, 'Actual exact auto-pilot continuation missing');
  } else requireThat(continuation === null, 'Nonaccepted receipt cannot claim continuation');
  const result = {schema:'closer-correction-receipt/v1', request_sha256:request.request_sha256,
    request, consumer, effect_state:state, reason, issue, continuation,
    retry_authorized:false, act_authorized:false, source_closure_authorized:false};
  return {...result, receipt_sha256:digest(result)};
}

async function collectCorrection({github, selector, currentRun, currentAttempt, directory}) {
  requireThat(exact(selector, 'schema run_id run_attempt artifact_id request_sha256 verification_event assessment_identity')
    && selector.schema === 'closer-correction-selector/v1' && SHA.test(selector.request_sha256), 'Invalid correction selector');
  const event = validateEvent(selector.verification_event);
  const proof = await acquireRetainedExecution({github,event,assessment:selector.assessment_identity,
    selector:{run_id:selector.run_id,run_attempt:selector.run_attempt,artifact_id:selector.artifact_id},
    currentRun,directory,pullRequestTargetOrigin:true});
  const archive = fs.readFileSync(path.join(directory,'verification-recovery-source.zip'));
  requireThat(sha(archive) === proof.archive_sha256 && archive.length === proof.archive_bytes, 'Authenticated archive changed');
  const files = readRetainedArchive(archive);
  requireThat(files.has(MEMBER), 'Trusted correction-request producer missing; collection only');
  const request = validateRequest(JSON.parse(files.get(MEMBER).toString('utf8')));
  requireThat(request.request_sha256 === selector.request_sha256
    && canonical(request.original_verifier.verification_event) === canonical(event)
    && request.original_verifier.run_id === String(selector.run_id)
    && request.original_verifier.run_attempt === String(selector.run_attempt), 'Authenticated correction request selector mismatch');
  const manifest = JSON.parse(files.get('verification-event-manifest.json') || 'null');
  requireThat(manifest && canonical(manifest.verification_event) === canonical(event)
    && digest(manifest.request) === event.request_sha256 && digest(manifest.material) === event.material_sha256,
  'Original verifier material mismatch');
  const [owner,repo] = event.repo.split('/');
  const read = async (method, args) => (await method({owner,repo,...args,request:{timeout:15000}})).data;
  const pull = await read(github.rest.pulls.get,{pull_number:Number(event.pr)});
  const target = request.target;
  requireThat(pull.merged === true && pull.head?.sha === target.head_sha && pull.base?.sha === target.base_sha
    && pull.merge_commit_sha === target.merge_sha && String(pull.base?.repo?.full_name).toLowerCase() === target.repository,
  'Current merged PR differs from correction target');
  const source = await read(github.rest.issues.get,{issue_number:Number(request.source_issue.number)});
  const incumbent = await read(github.rest.issues.get,{issue_number:Number(request.incumbent.issue.number)});
  const boundIssue = (actual, expected) => !actual.pull_request && String(actual.number) === expected.number
    && actual.node_id === expected.node_id && sha(actual.body || '') === expected.body_sha256;
  requireThat(boundIssue(source,request.source_issue) && boundIssue(incumbent,request.incumbent.issue)
    && incumbent.state === 'open' && incumbent.assignees?.some(person => person.login === request.incumbent.owner), 'Incumbent/source issue binding mismatch');
  const comment = await read(github.rest.issues.getComment,{comment_id:Number(request.original_verifier.comment_id)});
  requireThat(comment.user?.id === 41898282 && comment.user?.login === 'github-actions[bot]' && comment.user?.type === 'Bot'
    && comment.issue_url === `https://api.github.com/repos/${event.repo}/issues/${event.pr}`
    && sha(comment.body || '') === request.original_verifier.comment_sha256, 'Original verifier comment unauthenticated');
  const decisions = [...comment.body.matchAll(/<!-- verifier-corpus-decision\/v1 (\{[^\n]+\}) -->/g)].map(match => JSON.parse(match[1]));
  requireThat(decisions.length === 1 && decisions[0].verdict === 'NON_PASS'
    && digest(decisions[0]) === request.original_verifier.decision_sha256
    && String(decisions[0].run_id) === request.original_verifier.run_id
    && String(decisions[0].run_attempt) === request.original_verifier.run_attempt
    && completedEvent(event,[{author:comment.user.login,url:comment.html_url,body:comment.body}],selector.assessment_identity), 'Original verifier decision mismatch');
  // Admission does not authenticate a correction producer's authority, owner
  // lineage or test registration. Until those exist, do not invoke legacy effects.
  return receipt(request,{reason:'collection_only_correction_producer_and_continuation_binding_unavailable',
    consumer:{run_id:String(currentRun),run_attempt:String(currentAttempt)}});
}

// Pure reconciliation of already authenticated ledger records. Authentication
// belongs to the artifact/event collector, never a caller-supplied JSON flag.
// This reducer cannot authorize an effect or turn missing history into absence.
function reconcileCorrection(request, authenticatedHistory, consumer) {
  validateRequest(request);
  requireThat(Array.isArray(authenticatedHistory), 'Authenticated receipt history unavailable');
  const matches = [];
  for (const row of authenticatedHistory) {
    const {receipt_sha256, ...payload} = row;
    requireThat(row.schema === 'closer-correction-receipt/v1' && digest(payload) === receipt_sha256,
      'Correction ledger receipt corrupt');
    validateRequest(row.request);
    requireThat(row.request_sha256 === row.request.request_sha256, 'Ledger request digest mismatch');
    if (row.request.original_operation.idempotency_key === request.original_operation.idempotency_key
        && row.request_sha256 !== request.request_sha256) throw new Error('Original idempotency key rebound');
    if (row.request_sha256 === request.request_sha256) matches.push(row);
  }
  const accepted = matches.filter(row => row.effect_state === 'accepted_with_exact_issue_and_actual_autopilot_run_attempt');
  for (const row of accepted) receipt(request,{state:row.effect_state,reason:row.reason,issue:row.issue,
    continuation:row.continuation,consumer:row.consumer});
  if (accepted.length) {
    requireThat(new Set(accepted.map(row => canonical(row.continuation))).size === 1,
      'Conflicting actual auto-pilot continuations');
    return receipt(request,{state:accepted[0].effect_state,reason:'exact_authenticated_request_already_accepted',
      issue:accepted[0].issue,continuation:accepted[0].continuation,consumer});
  }
  // Missing receipts can mean an effect ran before its receipt was retained.
  // Even a prior collection-only refusal cannot reconcile a different effect.
  return receipt(request,{state:'outcome_unknown',reason:matches.some(row => row.effect_state === 'outcome_unknown')
    ? 'prior_uncertain_effect_requires_exact_reconciliation' : 'effect_absence_not_proven_by_ledger',consumer});
}

module.exports = {validateRequest, receipt, collectCorrection, reconcileCorrection};
