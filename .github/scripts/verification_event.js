'use strict';

// Shared with Orchestrator's verification_event.py. Hash semantic, retained
// inputs, never transport archives, clocks, model output, or optional logs.
const { createHash } = require('crypto');
const SHA = /^[0-9a-f]{64}$/;
const COMMIT = /^[0-9a-f]{40}$/;
const CORE = ['schema', 'repo', 'pr', 'head_sha', 'evaluated_sha', 'request_sha256', 'material_sha256'];

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}
function digest(value) { return createHash('sha256').update(canonical(value), 'utf8').digest('hex'); }
function sorted(rows) { return rows.sort((a, b) => canonical(a) < canonical(b) ? -1 : canonical(a) > canonical(b) ? 1 : 0); }
function parse(value, fallback) {
  if (typeof value === 'string') return value.trim() ? JSON.parse(value) : fallback;
  return value ?? fallback;
}
function parseRecoverySelector(value) {
  if (value == null || value === '') return null;
  if (typeof value !== 'string' || Buffer.byteLength(value, 'utf8') > 512) {
    throw new Error('Invalid retained verification recovery selector');
  }
  const selected = JSON.parse(value);
  if (!selected || typeof selected !== 'object' || Array.isArray(selected)
      || Object.keys(selected).sort().join(',') !== 'artifact_id,run_attempt,run_id'
      || !Object.values(selected).every(id => Number.isSafeInteger(id) && id > 0)) {
    throw new Error('Recovery accepts exact run_id/run_attempt/artifact_id selectors only');
  }
  return Object.freeze({...selected});
}

function assessmentIdentity({mode,provider = '',model = '',model2 = '',canonical: production = true}) {
  if (!['evaluate','compare'].includes(mode) || production !== true
      || [provider,model,model2].some(value => typeof value !== 'string')) throw new Error('Invalid production assessment identity');
  // Mirror the authored CLI, not ignored workflow inputs. No provider routing
  // decision is made here; equivalent consumed arguments share dedup identity.
  return {mode,provider:mode === 'compare' || ['', 'auto','github-models'].includes(provider) ? '' : provider,
    model,model2:mode === 'evaluate' ? '' : model2 || model,canonical:true};
}
function sameAssessment(left, right) {
  if (left?.canonical !== true || right?.canonical !== true) return false;
  try { return canonical(assessmentIdentity(left)) === canonical(assessmentIdentity(right)); }
  catch { return false; }
}
function validateEvent(value) {
  const event = parse(value, null);
  if (!event || event.schema !== 'verification-event/v1'
      || !/^[^/\s]+\/[^/\s]+$/.test(event.repo) || event.repo !== event.repo.toLowerCase()
      || !/^[1-9]\d*$/.test(event.pr) || typeof event.pr !== 'string'
      || !COMMIT.test(event.head_sha) || !COMMIT.test(event.evaluated_sha)
      || !SHA.test(event.request_sha256) || !SHA.test(event.material_sha256)
      || !SHA.test(event.event_id)
      || digest(Object.fromEntries(CORE.map(key => [key, event[key]]))) !== event.event_id) {
    throw new Error('Invalid verification event identity or content digest');
  }
  return event;
}

function requiredEvidence(selectors, evidence, target = {}) {
  const {validatedSelectors} = require('./verifier_gzip_assets');
  const selected = validatedSelectors(selectors);
  const rows = selected.map(selector => {
    if (!selector || typeof selector !== 'object') throw new Error('Invalid required evidence selector');
    if (selector.kind === 'comment') {
      if (typeof selector.url !== 'string'
          || !/^https:\/\/github\.com\/[^\s]+#(?:issuecomment-|discussion_r|pullrequestreview-)[1-9]\d*$/.test(selector.url)) {
        throw new Error('Invalid required verification comment selector');
      }
      const matches = (evidence.comments?.records || []).filter(record => record.url === selector.url);
      if (matches.length !== 1 || matches[0].truncated || typeof matches[0].body !== 'string') {
        throw new Error('Required verification comment is absent, ambiguous or incomplete');
      }
      // The existing collector supplies authenticated API records. URLs are
      // exact selectors, not instructions to fetch an arbitrary destination.
      return { kind: 'comment', url: selector.url,
        body_sha256: createHash('sha256').update(matches[0].body, 'utf8').digest('hex') };
    }
    if (selector.kind === 'git_blob') {
      const {evidencePath} = require('./verifier_gzip_assets');
      if (Object.keys(selector).sort().join(',') !== 'kind,path' || !evidencePath(selector.path)) throw new Error('Invalid git_blob selector');
      const matches = (evidence.gzip_assets || []).filter(row => row.source === selector.path);
      if (matches.length !== 1 || matches[0].status !== 'captured') throw new Error('Required git_blob evidence unavailable');
      const row=matches[0];
      return {kind:'git_blob',path:row.source,git_blob_sha:row.git_blob_sha,raw_sha256:row.raw_sha256,
        text_sha256:row.text_sha256,codec:row.codec};
    }
    if (selector.kind === 'artifact_member') {
      if (![selector.run_id, selector.artifact_id].every(id => Number.isSafeInteger(id) && id > 0)
          || typeof selector.path !== 'string' || !selector.path) throw new Error('Invalid artifact member selector');
      const archives = (evidence.diagnostics?.archive_inventory || []).filter(record =>
        record.run_id === selector.run_id && record.artifact_id === selector.artifact_id);
      const members = archives.length === 1 ? (archives[0].members || []).filter(member =>
        member.path === selector.path || member.name === selector.path) : [];
      if (archives.length !== 1 || !archives[0].member_inventory_complete || members.length !== 1
          || !['included', 'captured'].includes(members[0].status) || !SHA.test(members[0].raw_sha256)) {
        throw new Error('Required verification artifact member is absent, ambiguous or incomplete');
      }
      const binding = archives[0].historical_binding;
      if (selector.evidence_role === 'comparison-baseline'
          && (binding?.schema !== 'verifier-comparison-baseline/v1'
            || binding.run_id !== selector.run_id || archives[0].head_sha !== binding.run_head_sha
            || binding.repository !== String(target.repository || '').toLowerCase()
            || String(archives[0].repository || '').toLowerCase() !== binding.repository
            || binding.evaluated_sha !== target.evaluatedSha
            || !selector.compared_paths.every(source => binding.compared_sources?.some(row => row.path === source && SHA.test(row.sha256))))) {
        throw new Error('Required comparison baseline binding unavailable');
      }
      return { kind: 'artifact_member', run_id: selector.run_id, artifact_id: selector.artifact_id,
        path: selector.path, raw_sha256: members[0].raw_sha256,
        ...(selector.evidence_role ? {evidence_role:selector.evidence_role,comparison_binding:binding} : {}) };
    }
    throw new Error('Unsupported required verification evidence selector');
  });
  if (new Set(rows.map(canonical)).size !== rows.length) throw new Error('Duplicate required evidence selector');
  return sorted(rows);
}

function completedEvent(event, comments, assessmentIdentity) {
  const prefix = `https://github.com/${event.repo}/pull/${event.pr}#issuecomment-`;
  return comments.some(comment => {
    if (!['github-actions', 'github-actions[bot]'].includes(comment.author)
        || !String(comment.url).toLowerCase().startsWith(prefix) || comment.truncated) return false;
    for (const match of String(comment.body).matchAll(/<!-- verifier-corpus-decision\/v1 (\{[^\n]+\}) -->/g)) {
      try {
        const decision = JSON.parse(match[1]);
        const actual = validateEvent(decision.verification_event);
        const providers = decision.provider_verdicts;
        if (actual.event_id === event.event_id && sameAssessment(decision.assessment_identity, assessmentIdentity)
            && decision.schema === 'verifier-corpus-decision/v1'
            && String(decision.repo).toLowerCase() === event.repo && String(decision.pr) === event.pr
            && decision.head_sha === event.head_sha && decision.evaluated_sha === event.evaluated_sha
            && /^[1-9]\d*$/.test(String(decision.run_id)) && /^[1-9]\d*$/.test(String(decision.run_attempt))
            && typeof decision.ci_failed === 'boolean' && Array.isArray(providers) && providers.length
            && providers.every(value => ['PASS', 'CONCERNS', 'FAIL', 'NON_PASS'].includes(value))
            && decision.verdict === (!decision.ci_failed && providers.every(value => value === 'PASS') ? 'PASS' : 'NON_PASS')) return true;
      } catch { /* Unauthenticated/malformed history is never completion. */ }
    }
    return false;
  });
}

function authenticatePredecessor(event, predecessor, evidence, reconciledPending = new Set(), repairContext = null) {
  const history = evidence.event_history;
  if (!SHA.test(predecessor) || !history?.complete) {
    throw new Error('Verification predecessor requires complete authenticated comment evidence');
  }
  const prefix = `https://github.com/${event.repo}/pull/${event.pr}#issuecomment-`;
  for (const comment of history.records || []) {
    if (!['github-actions', 'github-actions[bot]'].includes(comment.author)
        || !String(comment.url).toLowerCase().startsWith(prefix) || comment.truncated) continue;
    for (const match of String(comment.body).matchAll(/<!-- verifier-corpus-decision\/v1 (\{[^\n]+\}) -->/g)) {
      try {
        const d = JSON.parse(match[1]);
        if (d.assessment_identity?.canonical === false) continue;
        if (d.schema !== 'verifier-corpus-decision/v1' || String(d.repo).toLowerCase() !== event.repo
            || String(d.pr) !== event.pr || d.head_sha !== event.head_sha || d.evaluated_sha !== event.evaluated_sha
            || !/^[1-9]\d*$/.test(String(d.run_id)) || !/^[1-9]\d*$/.test(String(d.run_attempt))
            || typeof d.ci_failed !== 'boolean' || !Array.isArray(d.provider_verdicts) || !d.provider_verdicts.length
            || d.provider_verdicts.some(value => !['PASS','CONCERNS','FAIL','NON_PASS'].includes(value))
            || d.verdict !== (!d.ci_failed && d.provider_verdicts.every(value => value === 'PASS') ? 'PASS' : 'NON_PASS')) continue;
        let identity;
        if (d.verification_event) {
          const previous = validateEvent(d.verification_event);
          if (['repo','pr','head_sha','evaluated_sha'].some(key => previous[key] !== event[key])) continue;
          identity = previous.event_id;
        } else {
          identity = digest({ schema:'verification-legacy-event/v1',repo:event.repo,pr:event.pr,
            head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,
            run_id:String(d.run_id),run_attempt:String(d.run_attempt) });
        }
        if (identity === predecessor) {
          const contested=(history.records || []).some(other => {
            if (!['github-actions','github-actions[bot]'].includes(other.author)
                || !String(other.url).toLowerCase().startsWith(prefix)) return false;
            return [...String(other.body).matchAll(/<!-- verifier-event-state\/v1 (\{[^\n]+\}) -->/g)].some(match => {
              try {
                const state=JSON.parse(match[1]);
                return state.assessment_identity?.canonical !== false
                  && state.status==='incomplete' && state.verification_event?.event_id===identity
                  && String(state.run_id)===String(d.run_id) && String(state.run_attempt)===String(d.run_attempt)
                  && ['repo','pr','head_sha','evaluated_sha'].every(key=>String(state[key]).toLowerCase()===String(event[key]).toLowerCase());
              } catch {return false;}
            });
          });
          if (contested) continue;
          return;
        }
      } catch { /* Malformed history cannot supply causal authority. */ }
    }
  }
  if (predecessor !== event.event_id && authenticateIncompletePredecessor(event,predecessor,history.records || [],reconciledPending,evidence,repairContext)) return;
  throw new Error('Verification predecessor is not an authenticated exact-subject terminal event');
}

function authenticateIncompletePredecessor(event,predecessor,comments,reconciledPending,evidence = {},repairContext = null) {
  const prefix=`https://github.com/${event.repo}/pull/${event.pr}#issuecomment-`;
  const rows=[];
  for (const comment of comments) {
    if (!['github-actions','github-actions[bot]'].includes(comment.author)
        || !String(comment.url).toLowerCase().startsWith(prefix)) continue;
    const matches=[...String(comment.body).matchAll(/<!-- (verifier-event-state\/v1|verifier-corpus-decision\/v1) (\{[^\n]+\}) -->/g)];
    // Input-repair provenance is evaluated by its own artifact-bound check, never as history rows.
    if (!comment.truncated && !matches.length && INPUT_REPAIR.test(String(comment.body))) continue;
    if ((comment.truncated || !matches.length) && String(comment.body).includes(predecessor)) throw new Error('Incomplete predecessor history');
    for (const match of matches) {
      let row;
      try {row=JSON.parse(match[2]);} catch {
        if(match[2].includes(predecessor)) throw new Error('Malformed predecessor history');
        continue;
      }
      const sameSubject=['repo','pr','head_sha','evaluated_sha'].every(key => String(row[key]).toLowerCase()===String(event[key]).toLowerCase());
      if (!sameSubject) continue;
      if (comment.truncated) throw new Error('Truncated predecessor history');
      let actual;
      try {
        if (row.schema==='verifier-corpus-decision/v1' && row.verification_event===undefined) {
          if (!/^[1-9]\d{0,19}$/.test(String(row.run_id)) || !/^[1-9]\d{0,9}$/.test(String(row.run_attempt))
              || typeof row.ci_failed!=='boolean' || !Array.isArray(row.provider_verdicts) || !row.provider_verdicts.length
              || row.provider_verdicts.some(value=>!['PASS','CONCERNS','FAIL','NON_PASS'].includes(value))
              || row.verdict!==(!row.ci_failed && row.provider_verdicts.every(value=>value==='PASS')?'PASS':'NON_PASS')) throw new Error('Invalid legacy history');
          if (row.assessment_identity?.canonical === false) {
            assessmentIdentity({...row.assessment_identity,canonical:true});
            continue;
          }
          rows.push({row,actual:{event_id:digest({schema:'verification-legacy-event/v1',repo:event.repo,pr:event.pr,head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,run_id:String(row.run_id),run_attempt:String(row.run_attempt)})},run:BigInt(row.run_id),attempt:BigInt(row.run_attempt)});
          continue;
        }
        actual=validateEvent(row.verification_event);
        if (['repo','pr','head_sha','evaluated_sha'].some(key=>actual[key]!==event[key])
            || !/^[1-9]\d{0,19}$/.test(String(row.run_id)) || !/^[1-9]\d{0,9}$/.test(String(row.run_attempt))
            || !(row.assessment_identity?.canonical === false
              ? assessmentIdentity({...row.assessment_identity,canonical:true})
              : sameAssessment(row.assessment_identity,row.assessment_identity))
            || row.schema!==match[1]
            || (row.schema==='verifier-event-state/v1' && !['pending','incomplete'].includes(row.status))
            || (row.predecessor_event_id!==undefined && (!SHA.test(row.predecessor_event_id) || row.predecessor_event_id===actual.event_id))) throw new Error('Invalid predecessor row');
      } catch {throw new Error('Malformed authenticated predecessor history');}
      if (row.assessment_identity.canonical === false) {
        if (row.schema==='verifier-corpus-decision/v1'
            && (typeof row.ci_failed!=='boolean' || !Array.isArray(row.provider_verdicts) || !row.provider_verdicts.length
              || row.provider_verdicts.some(value=>!['PASS','CONCERNS','FAIL','NON_PASS'].includes(value))
              || row.verdict!==(!row.ci_failed && row.provider_verdicts.every(value=>value==='PASS')?'PASS':'NON_PASS'))) {
          throw new Error('Malformed advisory predecessor history');
        }
        continue; // Valid advisory reads neither supply nor veto canonical authority.
      }
      rows.push({row,actual,comment,run:BigInt(row.run_id),attempt:BigInt(row.run_attempt)});
    }
  }
  const candidates=rows.filter(entry=>entry.actual.event_id===predecessor);
  if (!candidates.length) return false;
  const newer=(left,right)=>left.run>right.run || (left.run===right.run && left.attempt>right.attempt);
  const latest=candidates.reduce((left,right)=>newer(right,left)?right:left);
  // A changed event cannot fork newer work. Repeating the exact already-created
  // child keeps its original edge; it does not mint a new branch or retry grant.
  const children=rows.filter(entry=>entry.actual.event_id===event.event_id);
  if (rows.some(entry=>newer(entry,latest) && entry.actual.event_id!==event.event_id)) {
    throw new Error('Predecessor has newer authenticated work');
  }
  if (children.some(entry=>!newer(entry,latest) || entry.row.predecessor_event_id!==predecessor)) {
    throw new Error('Repeated verification event has conflicting parent metadata');
  }
  if (children.length) {
    const childLatest=children.reduce((left,right)=>newer(right,left)?right:left);
    const attempts=new Map();
    for (const entry of children) {
      const key=`${entry.run}:${entry.attempt}`;
      attempts.set(key,[...(attempts.get(key) || []),entry]);
    }
    for (const current of attempts.values()) {
      // Scope the existing guard to this authenticated attempt without changing
      // retained records. An older unresolved provider attempt cannot disappear
      // behind a later no-evaluation marker for the same event.
      const attemptComments=current.map(({row,comment})=>({...comment,
        body:`<!-- ${row.schema} ${JSON.stringify(row)} -->`}));
      if (knownNoEvaluationAttempt(current,attemptComments)) continue;
      if (!current.some(({row})=>row.status==='incomplete')
          && completedEvent(event,attemptComments,current[0].row.assessment_identity)) continue;
      if (current.every(({row})=>row.schema==='verifier-event-state/v1' && row.status==='pending')) {
        if (current[0].run===childLatest.run && current[0].attempt===childLatest.attempt) continue;
        const states=[...new Map(current.map(({row})=>[digest(row),row])).values()];
        if (states.length===1) {
          if (reconciledPending.has(digest(states[0]))) continue;
          const error=new Error('Repeated verification event requires older pending execution recovery');
          error.code='VERIFIER_PREDECESSOR_PENDING_EXECUTION';
          error.pendingState=states[0];
          error.verificationEvent=event;
          throw error;
        }
      }
      throw new Error('Repeated verification event requires existing execution recovery');
    }
  }
  const current=candidates.filter(entry=>entry.run===latest.run && entry.attempt===latest.attempt);
  return knownNoEvaluationAttempt(current,comments)
    || authenticateInputRepair(event,predecessor,latest,current,comments,evidence,repairContext);
}

const INPUT_REPAIR = /<!-- verifier-input-repair\/v1 \{[^\n]+\} -->/;
const INPUT_REPAIR_ALL = /<!-- verifier-input-repair\/v1 (\{[^\n]+\}) -->/g;
const REPAIR_VERDICTS = ['PASS','CONCERNS','FAIL','UNVERIFIABLE_INPUT'];

// Appended beside (never over) the original incomplete state. Carries the
// original material so the consumer can prove what changed, plus the retained
// result/receipt digests so the retained artifact can be re-checked by collector.
function inputRepairMarker({state, material, repair}) {
  const marker = {schema:'verifier-input-repair/v1',repo:state.repo,pr:state.pr,head_sha:state.head_sha,
    evaluated_sha:state.evaluated_sha,run_id:String(state.run_id),run_attempt:String(state.run_attempt),
    verification_event:validateEvent(state.verification_event),assessment_identity:state.assessment_identity,
    original_material:material,result:repair.result,receipt:repair.receipt,provider_verdicts:repair.provider_verdicts};
  return {...marker,input_repair_id:digest(marker)};
}

function authenticateInputRepair(event,predecessor,latest,current,comments,evidence,context) {
  const {material,assessmentIdentity:assessment}=context || {};
  if (!material || !assessment || predecessor===event.event_id) return false;
  // Same-attempt state must be exactly the nonretryable, verdict-free retained provider outcome.
  if (current.some(({row})=>row.schema!=='verifier-event-state/v1' || row.verdict!==undefined
      || !['pending','incomplete'].includes(row.status))) return false;
  const incomplete=[...new Map(current.filter(({row})=>row.status==='incomplete').map(({row})=>[digest(row),row])).values()];
  if (incomplete.length!==1) return false;
  const state=incomplete[0];
  if (state.failure_cause!=='retained_provider_evaluation' || state.retry_kind!=='recover_existing_evaluation'
      || state.retryable!==false || state.input_repair!==undefined
      || !sameAssessment(state.assessment_identity,assessment)) return false;
  const prefix=`https://github.com/${event.repo}/pull/${event.pr}#issuecomment-`;
  const markers=new Map();
  for (const comment of comments) {
    if (!['github-actions','github-actions[bot]'].includes(comment.author)
        || !String(comment.url).toLowerCase().startsWith(prefix) || comment.truncated) continue;
    for (const match of String(comment.body).matchAll(INPUT_REPAIR_ALL)) {
      try {
        const row=JSON.parse(match[1]);
        if (row.verification_event?.event_id===predecessor && String(row.run_id)===String(latest.run)
            && String(row.run_attempt)===String(latest.attempt)) markers.set(digest(row),row);
      } catch { /* Unparseable provenance supplies no authority. */ }
    }
  }
  if (markers.size!==1) return false; // absent, or contradictory duplicates
  const marker=[...markers.values()][0];
  try {
    const {input_repair_id,...body}=marker;
    const original=validateEvent(marker.verification_event);
    const stem=assessment.mode==='evaluate' ? 'evaluation' : 'comparison';
    const members=[['result',`${stem}.json`],['receipt',`${stem}-execution.json`]];
    const verdicts=marker.provider_verdicts;
    if (marker.schema!=='verifier-input-repair/v1' || input_repair_id!==digest(body)
        || ['repo','pr','head_sha','evaluated_sha'].some(key=>String(marker[key]).toLowerCase()!==String(event[key]).toLowerCase()
          || original[key]!==event[key])
        || original.request_sha256!==event.request_sha256 || original.material_sha256===event.material_sha256
        || !sameAssessment(marker.assessment_identity,state.assessment_identity)
        || canonical(marker.assessment_identity)!==canonical(state.assessment_identity)
        || !Array.isArray(verdicts) || !verdicts.length
        || verdicts.some(row=>!row || typeof row.provider!=='string' || typeof row.model!=='string' || !REPAIR_VERDICTS.includes(row.verdict))
        || !verdicts.some(row=>row.verdict==='UNVERIFIABLE_INPUT')) return false;
    // The original material is proven by its digest; only necessary material may differ.
    const before=marker.original_material;
    if (before?.schema!=='verification-material/v1' || digest(before)!==original.material_sha256
        || digest(material)!==event.material_sha256
        || canonical(before.code)!==canonical(material.code)
        || !Array.isArray(material.required_evidence) || !material.required_evidence.length
        || canonical(before.required_evidence)===canonical(material.required_evidence)) return false;
    // Artifact binding: the retained result and receipt bytes must be the collector's
    // complete inventory of exactly one archive of the original run.
    const archives=(evidence.diagnostics?.archive_inventory || []).filter(record=>String(record.run_id)===String(marker.run_id)
      && (record.members || []).some(member=>members.some(([,path])=>member.path===path || member.name===path)));
    if (archives.length!==1 || !archives[0].member_inventory_complete) return false;
    for (const [key,path] of members) {
      const claim=marker[key];
      const found=archives[0].members.filter(member=>member.path===path || member.name===path);
      if (claim?.path!==path || !SHA.test(claim.raw_sha256) || found.length!==1
          || !['included','captured'].includes(found[0].status)
          || found[0].raw_sha256!==claim.raw_sha256) return false;
    }
    return true;
  } catch { return false; }
}

function knownNoEvaluationAttempt(current,comments) {
  const latest=current[0];
  const incomplete=current.filter(({row})=>row.status==='incomplete');
  if (!incomplete.length || current.some(({row})=>row.verdict!==undefined)
      || incomplete.some(({row})=>row.schema!=='verifier-event-state/v1'
        || !sameAssessment(row.assessment_identity,latest.row.assessment_identity)
        || !['validated_no_evaluation','evaluator_step_not_invoked'].includes(row.failure_cause))) return false;
  if (guardExistingEvent(latest.actual,comments,latest.row.assessment_identity)!=='retry') return false;
  const {executionBinding}=require('./verifier_pending_execution');
  const binding=executionBinding(latest.row.assessment_identity.mode);
  // Identical POST receipts are one authority value, without deleting history.
  const pending=[...new Map(current.filter(({row})=>row.status==='pending')
    .map(entry=>[digest(entry.row),entry])).values()];
  if (pending.length!==1 || !sameAssessment(pending[0].row.assessment_identity,latest.row.assessment_identity)
      || !pending[0].row.execution_binding || digest(pending[0].row.execution_binding)!==digest(binding)
      || current.some(({row})=>row.predecessor_event_id!==latest.row.predecessor_event_id)) return false;
  return true;
}

function completedLegacyEvent(event, evidence) {
  const history = evidence.event_history;
  if (!history?.complete) return false;
  for (const comment of history.records || []) {
    for (const match of String(comment.body).matchAll(/<!-- verifier-corpus-decision\/v1 (\{[^\n]+\}) -->/g)) {
      try {
        const d = JSON.parse(match[1]);
        if (d.verification_event) continue;
        const predecessor = digest({schema:'verification-legacy-event/v1',repo:event.repo,pr:event.pr,
          head_sha:event.head_sha,evaluated_sha:event.evaluated_sha,
          run_id:String(d.run_id),run_attempt:String(d.run_attempt)});
        authenticatePredecessor(event, predecessor, evidence);
        return true;
      } catch { /* Preserve valid legacy completion, not job-success fingerprints. */ }
    }
  }
  return false;
}

function ciHardGate(pull, results = []) {
  if (!Array.isArray(results) || results.length > 100) throw new Error('Invalid configured CI hard-gate inventory');
  const rows = results.map(result => {
    if (!result || typeof result.workflow_id !== 'string' || !result.workflow_id
        || typeof result.conclusion !== 'string' || result.conclusion.length > 80) {
      throw new Error('Missing configured CI hard-gate binding identity');
    }
    const bound = result.binding_status === 'bound'
      && [pull.head?.sha, pull.merge_commit_sha].includes(result.head_sha)
      && Number.isSafeInteger(result.run_id) && result.run_id > 0
      && Number.isSafeInteger(result.run_attempt) && result.run_attempt > 0;
    return { workflow_id: result.workflow_id, binding_status: bound ? 'bound'
      : result.binding_status === 'absent' ? 'absent' : 'unavailable',
    head_sha: bound ? result.head_sha : '', run_id: bound ? result.run_id : null,
    run_attempt: bound ? result.run_attempt : null, conclusion: result.conclusion };
  });
  if (new Set(rows.map(row => row.workflow_id)).size !== rows.length) throw new Error('Duplicate configured CI workflow identity');
  return { schema:'verification-ci-hard-gate/v1',head_sha:pull.head?.sha,
    evaluated_sha:pull.merge_commit_sha,results:sorted(rows) };
}

function guardExistingEvent(event, comments, assessmentIdentity) {
  const prefix = `https://github.com/${event.repo}/pull/${event.pr}#issuecomment-`;
  const records = [];
  for (const comment of comments) {
    if (!['github-actions', 'github-actions[bot]'].includes(comment.author)
        || !String(comment.url).toLowerCase().startsWith(prefix) || comment.truncated) continue;
    for (const match of String(comment.body).matchAll(/<!-- (verifier-event-state\/v1|verifier-corpus-decision\/v1) (\{[^\n]+\}) -->/g)) {
      try {
        const state = JSON.parse(match[2]);
        const actual = validateEvent(state.verification_event);
        if (actual.event_id !== event.event_id
            || ['repo','pr','head_sha','evaluated_sha'].some(key => actual[key] !== event[key])
            || String(state.repo).toLowerCase() !== event.repo || String(state.pr) !== event.pr
            || state.head_sha !== event.head_sha || state.evaluated_sha !== event.evaluated_sha
            || !sameAssessment(state.assessment_identity, assessmentIdentity)
            || !/^[1-9]\d{0,19}$/.test(String(state.run_id)) || !/^[1-9]\d{0,9}$/.test(String(state.run_attempt))) continue;
        if (match[1] === 'verifier-corpus-decision/v1') {
          if (!completedEvent(event, [{...comment,body:`<!-- ${match[1]} ${match[2]} -->`}], assessmentIdentity)) continue;
          records.push({run:BigInt(state.run_id),attempt:BigInt(state.run_attempt),kind:'terminal'});
        } else if (state.schema === 'verifier-event-state/v1' && ['pending','incomplete'].includes(state.status)) {
          records.push({run:BigInt(state.run_id),attempt:BigInt(state.run_attempt),kind:state.status,state});
        }
      } catch { /* A malformed/untrusted state never grants retry authority. */ }
    }
  }
  if (!records.length) return;
  const latest = records.reduce((a,b) => b.run > a.run || (b.run === a.run && b.attempt > a.attempt) ? b : a);
  const current = records.filter(row => row.run === latest.run && row.attempt === latest.attempt);
  const incomplete = current.filter(row => row.kind === 'incomplete');
  const terminal = current.some(row => row.kind === 'terminal');
  if (incomplete.length) {
    // An incomplete marker contradicting a terminal never authorizes another
    // provider call. Preserve the original cause rather than rewriting history.
    if (!terminal && incomplete.every(row => row.state.retry_kind === 'known_no_evaluation'
        && row.state.retryable === true)) return 'retry';
    throw new Error('Current verification event is incomplete; recover retained execution before another evaluation');
  }
  if (!terminal && current.some(row => row.kind === 'pending')) {
    const error = new Error('Current verification event is pending; recover existing execution before another evaluation');
    error.code = 'VERIFIER_PENDING_EXECUTION';
    error.pendingState = current.find(row => row.kind === 'pending').state;
    throw error;
  }
}

function buildVerificationEvent({ repository, pull, issues, fullDiffBytes, evidence,
  selectors, expected, predecessorEventId, ciResults, reconciledPending, assessmentIdentity: eventAssessment }) {
  const repo = repository.toLowerCase();
  const source = (kind, number, body, repository = repo) => {
    if (!/^[^/\s]+\/[^/\s]+$/.test(repository) || !Number.isSafeInteger(number) || number < 1) {
      throw new Error('Invalid original request source identity');
    }
    return { repository: repository.toLowerCase(), kind, number: String(number),
      body_sha256: createHash('sha256').update(body, 'utf8').digest('hex') };
  };
  if (typeof pull.body !== 'string' || issues.some(issue => typeof issue.body !== 'string')
      || !Buffer.isBuffer(fullDiffBytes) || !fullDiffBytes.length) throw new Error('Verification event requires complete original requests and code');
  const request = { schema: 'verification-request/v1', sources: sorted([
    source('pull_request', pull.number, pull.body),
    ...issues.map(issue => source('issue', issue.number, issue.body, issue.repository || repo)),
  ]) };
  const material = { schema: 'verification-material/v1', code: {
    head_sha: pull.head?.sha, evaluated_sha: pull.merge_commit_sha,
    diff_sha256: createHash('sha256').update(fullDiffBytes).digest('hex'),
  }, ci_hard_gate: ciHardGate(pull, ciResults), required_evidence: requiredEvidence(selectors, evidence, {repository:repo,evaluatedSha:pull.merge_commit_sha}) };
  // Explicit git_blob selectors bind required content above; transport-only
  // views must not mint a new event when optional capture availability changes.
  const event = { schema: 'verification-event/v1', repo, pr: String(pull.number),
    head_sha: pull.head?.sha, evaluated_sha: pull.merge_commit_sha,
    request_sha256: digest(request), material_sha256: digest(material) };
  event.event_id = digest(event);
  validateEvent(event);
  const expectation = parse(expected, null);
  if (expectation && validateEvent(expectation).event_id !== event.event_id) {
    throw new Error('Verification event expectation differs from authoritative collected inputs');
  }
  if (predecessorEventId) authenticatePredecessor(event, predecessorEventId, evidence, reconciledPending, {material, assessmentIdentity: eventAssessment});
  return { verification_event: event, ...(predecessorEventId ? { predecessor_event_id: predecessorEventId } : {}),
    request, material };
}

module.exports = { parseRecoverySelector, canonical, digest, validateEvent, requiredEvidence, buildVerificationEvent, completedEvent, authenticatePredecessor, completedLegacyEvent, ciHardGate, guardExistingEvent, inputRepairMarker, assessmentIdentity, sameAssessment };
