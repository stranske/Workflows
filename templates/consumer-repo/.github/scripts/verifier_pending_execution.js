'use strict';

const { digest, validateEvent, sameAssessment, parseRecoverySelector, completedEvent } = require('./verification_event.js');
const { createTokenAwareRetry } = require('./github-api-with-retry.js');

function executionBinding(mode) {
  if (!['evaluate','compare'].includes(mode)) throw new Error('Unsupported verifier execution mode');
  return {schema:'verifier-execution-binding/v1',workflow_path:'.github/workflows/agents-verifier.yml',
    job_name:'Run post-merge verifier',pending_step:'Record verification event pending',
    evaluator_step:mode === 'evaluate' ? 'Run LLM evaluation' : 'Run multi-provider comparison'};
}

async function reconcilePendingExecution({github,event,assessment,state,maxPages = 10,currentExecution = null}) {
  const unknown = reason => ({retry_kind:'uncertain_execution',retryable:false,failure_cause:reason,
    existing_execution:{repo:event.repo,run_id:String(state?.run_id || ''),run_attempt:String(state?.run_attempt || '')}});
  try {
    const actual = validateEvent(state.verification_event);
    const retained = state.execution_binding?.retained_revalidation === true;
    const binding = {...executionBinding(assessment.mode), ...(retained ? {retained_revalidation:true} : {})};
    if(retained && (!state.retained_revalidation?.recovery_key || state.retained_revalidation.schema!=='retained-revalidation/v1')) return unknown('recovery_identity_unavailable');
    if (state.schema !== 'verifier-event-state/v1' || state.status !== 'pending'
        || actual.event_id !== event.event_id || !sameAssessment(state.assessment_identity,assessment)
        || ['repo','pr','head_sha','evaluated_sha'].some(key => state[key] !== event[key])
        || !state.execution_binding || digest(state.execution_binding) !== digest(binding)) return unknown('pending_execution_binding_unavailable');
    const runId = Number(state.run_id), attempt = Number(state.run_attempt);
    if (![runId,attempt].every(value => Number.isSafeInteger(value) && value > 0)
        || String(runId) !== String(state.run_id) || String(attempt) !== String(state.run_attempt)) return unknown('pending_run_identity_invalid');
    const [owner,repo] = event.repo.split('/');
    const { withRetry } = await createTokenAwareRetry({github,
      task:'verifier',capabilities:['read-repo'],minRemaining:50});
    const retryOptions = {maxRetries:2,initialDelay:250,maxDelay:1000};
    const readLatest = async () => (await withRetry(client => client.rest.actions.getWorkflowRun({
      owner,repo,run_id:runId,request:{timeout:15000}}),retryOptions)).data;
    const readAttempt = async number => (await withRetry(client => client.rest.actions.getWorkflowRunAttempt({
      owner,repo,run_id:runId,attempt_number:number,request:{timeout:15000}}),retryOptions)).data;
    const boundRun = run => run?.id === runId && Number.isSafeInteger(run.run_attempt)
      && run.run_attempt > 0 && run.path === binding.workflow_path && /^[0-9a-f]{40}$/.test(run.head_sha || '')
      && ['workflow_dispatch','pull_request_target'].includes(run.event)
      && String(run.repository?.full_name || '').toLowerCase() === event.repo
      && String(run.head_repository?.full_name || '').toLowerCase() === event.repo;
    const runIdentity = run => digest({id:run.id,run_attempt:run.run_attempt,status:run.status,
      conclusion:run.conclusion,head_sha:run.head_sha,path:run.path,event:run.event,
      repository:String(run.repository?.full_name || '').toLowerCase(),
      head_repository:String(run.head_repository?.full_name || '').toLowerCase()});
    const isCurrentCollection = number => String(currentExecution?.run_id || '') === String(runId)
      && String(currentExecution?.run_attempt || '') === String(number)
      && String(currentExecution?.repo || '').toLowerCase() === event.repo
      && typeof currentExecution?.workflow_ref === 'string'
      && currentExecution.workflow_ref.toLowerCase().startsWith(`${event.repo}/${binding.workflow_path}@`)
      && currentExecution.workflow_ref.split('@')[1]?.length > 0;
    const latest = await readLatest();
    if (!boundRun(latest) || latest.run_attempt < attempt || latest.run_attempt - attempt >= 10
        || (latest.status !== 'completed' && !(latest.status === 'in_progress' && isCurrentCollection(latest.run_attempt)))) {
      return unknown('prior_run_active_changed_or_unbound');
    }
    let remainingPages = Math.min(maxPages,10);
    const observations = [];
    for (let number=attempt;number<=latest.run_attempt;number+=1) {
      const current = latest.status === 'in_progress' && number > attempt
        && number === latest.run_attempt && isCurrentCollection(number);
      const run = await readAttempt(number);
      if (!boundRun(run) || run.run_attempt !== number || run.head_sha !== latest.head_sha
          || (run.status !== 'completed' && !(current && run.status === 'in_progress'))) {
        return unknown('prior_attempt_active_changed_or_unbound');
      }
      const jobs = [], ids = new Set();
      let total, complete = false;
      for (let page=1;remainingPages>0;page+=1) {
        remainingPages-=1;
        const response = await withRetry(client => client.rest.actions.listJobsForWorkflowRunAttempt({owner,repo,
          run_id:runId,attempt_number:number,per_page:100,page,request:{timeout:15000}}),retryOptions);
        if (!Array.isArray(response?.data?.jobs) || !Number.isSafeInteger(response.data.total_count)
            || response.data.total_count < 0 || (total !== undefined && total !== response.data.total_count)) return unknown('prior_attempt_jobs_incomplete');
        total = response.data.total_count;
        for (const job of response.data.jobs) {
          if (!Number.isSafeInteger(job?.id) || job.id < 1 || ids.has(job.id)
              || job.run_id !== runId || job.run_attempt !== number || job.head_sha !== run.head_sha) return unknown('prior_attempt_job_identity_mismatch');
          ids.add(job.id);jobs.push(job);
        }
        const hasNext = Boolean(response.headers?.link?.includes('rel="next"'));
        if (jobs.length === total && !hasNext) {complete=true;break;}
        if (!response.data.jobs.length || jobs.length >= total) return unknown('prior_attempt_jobs_incomplete');
      }
      if (!complete) return unknown('prior_attempt_jobs_incomplete');
      const candidates = jobs.filter(job => job.name === binding.job_name || job.name.endsWith(` / ${binding.job_name}`));
      if (candidates.length !== 1) return unknown('prior_verifier_job_ambiguous');
      const job = candidates[0];
      if (!Array.isArray(job.steps) || (!current && job.status !== 'completed')) return unknown('prior_verifier_job_incomplete');
      const pending = job.steps.filter(step => step.name === binding.pending_step);
      const evaluator = job.steps.filter(step => step.name === binding.evaluator_step);
      if (number === attempt && (pending.length !== 1 || pending[0].status !== 'completed'
          || pending[0].conclusion !== 'success' || !Number.isSafeInteger(pending[0].number)
          || pending[0].number < 1)) return unknown('prior_evaluator_step_evidence_unavailable');
      if (!current && (evaluator.length !== 1 || !Number.isSafeInteger(evaluator[0].number)
          || evaluator[0].number < 1 || (number === attempt && evaluator[0].number <= pending[0].number))) {
        return unknown('prior_evaluator_step_evidence_unavailable');
      }
      const allEvaluatorSteps = jobs.flatMap(item => Array.isArray(item.steps) ? item.steps : [])
        .filter(step => (retained ? ['Run LLM evaluation','Run multi-provider comparison','Run verifier (checkbox mode)','Shadow candidate verifier judges (recorded only; never posted, never counted)'] : ['Run LLM evaluation','Run multi-provider comparison']).includes(step.name));
      const notStarted = step => step.status === 'completed' && step.conclusion === 'skipped'
        || current && ['queued','pending'].includes(step.status) && step.conclusion == null
          && step.started_at == null && step.completed_at == null;
      if (allEvaluatorSteps.some(step => !notStarted(step))) {
        const result = unknown('prior_evaluator_started_collect_existing_outputs');
        result.existing_execution.run_attempt = String(number);
        result.existing_execution.run_url = `https://github.com/${event.repo}/actions/runs/${runId}/attempts/${number}`;
        result.existing_execution.output_names = assessment.mode === 'evaluate'
          ? ['evaluation.json','evaluation-execution.json'] : ['comparison.json'];
        return result;
      }
      let publication;
      if(retained) {
        const publishers=job.steps.filter(step=>step.name==='Publish retained revalidation through verifier lifecycle');
        const ownPrePost=current && currentExecution?.phase==='pre_publication'
          && publishers[0]?.status==='in_progress' && publishers[0].conclusion==null;
        if(publishers.length!==1 || !Number.isSafeInteger(publishers[0].number)
            || !evaluator[0] || publishers[0].number<=evaluator[0].number
            || !(notStarted(publishers[0]) || ownPrePost)) return unknown('prior_recovery_publication_may_have_started');
        publication=publishers[0];
      }
      observations.push({run,jobs,job,pending,evaluator,current,publication});
    }
    for (const item of observations) {
      const refreshed = await readAttempt(item.run.run_attempt);
      if (!boundRun(refreshed) || runIdentity(refreshed) !== runIdentity(item.run)) {
        return unknown('prior_run_changed_during_reconciliation');
      }
    }
    const refreshedLatest = await readLatest();
    if (!boundRun(refreshedLatest) || runIdentity(refreshedLatest) !== runIdentity(latest)) {
      return unknown('prior_run_changed_during_reconciliation');
    }
    const {run,jobs,job,pending,evaluator} = observations[0];
    const proof = {schema:'verifier-no-evaluation-proof/v1',repo:event.repo,event_id:event.event_id,
      assessment_identity:assessment,run_id:String(runId),run_attempt:String(attempt),run_head_sha:run.head_sha,
      workflow_path:binding.workflow_path,job_id:job.id,pending_step_number:pending[0].number,
      evaluator_step_number:evaluator[0].number,evaluator_step:binding.evaluator_step,conclusion:'skipped',
      source:'actions.listJobsForWorkflowRunAttempt',jobs_sha256:digest(jobs),
      latest_run_attempt:String(latest.run_attempt),
      subsequent_attempts:observations.slice(1).map(item => ({run_attempt:String(item.run.run_attempt),
        run_head_sha:item.run.head_sha,workflow_path:binding.workflow_path,job_id:item.job.id,
        ...(item.current ? {current_execution:true} : {evaluator_step_number:item.evaluator[0].number,
          evaluator_step:binding.evaluator_step,conclusion:'skipped'}),jobs_sha256:digest(item.jobs)}))};
    if(retained) Object.assign(proof,{recovery_key:state.retained_revalidation.recovery_key,publication_step:'Publish retained revalidation through verifier lifecycle',publication_conclusion:'skipped',publication_step_number:observations[0].publication.number});
    return {retry_kind:'known_no_evaluation',retryable:true,failure_cause:'authoritative_evaluator_step_skipped',proof};
  } catch { return unknown('prior_execution_reconciliation_unavailable'); }
}


// Recovery accepts selectors only. Every authority-bearing field below comes
// from authenticated Actions APIs, not the caller or the retained JSON itself.
async function acquireRetainedExecution({github,event,assessment,selector,currentRun,maxBytes=8388608}) {
  const {createHash} = require('crypto');
  const fs = require('fs');
  const selected = parseRecoverySelector(typeof selector === 'string' ? selector : JSON.stringify(selector));
  if (!selected || !Number.isSafeInteger(currentRun) || currentRun <= selected.run_id) throw new Error('Recovery source must precede current execution');
  validateEvent(event);
  const binding = executionBinding(assessment.mode);
  const [owner,repo] = event.repo.split('/');
  const {withRetry} = await createTokenAwareRetry({github,task:'verifier',capabilities:['read-repo'],minRemaining:50});
  const opts = {maxRetries:2,initialDelay:250,maxDelay:1000};
  const read = async fn => (await withRetry(fn,opts)).data;
  const latest = await read(client=>client.rest.actions.getWorkflowRun({owner,repo,run_id:selected.run_id,request:{timeout:15000}}));
  if(latest.run_attempt!==selected.run_attempt || latest.status!=='completed') throw new Error('Retained source has a newer or active attempt');
  const run = await read(client => client.rest.actions.getWorkflowRunAttempt({owner,repo,run_id:selected.run_id,attempt_number:selected.run_attempt,request:{timeout:15000}}));
  const canonicalOrigins = new Map();
  const canonicalCommit = async (repository, commit) => {
    const [sourceOwner,sourceRepo]=repository.split('/');
    let canonical=canonicalOrigins.get(repository);
    if(!canonical) {
      const metadata=await read(client=>client.rest.repos.get({owner:sourceOwner,repo:sourceRepo,request:{timeout:15000}}));
      if(String(metadata.full_name).toLowerCase()!==repository.toLowerCase() || typeof metadata.default_branch!=='string' || !metadata.default_branch) throw new Error('Canonical source repository origin unavailable');
      const head=await read(client=>client.rest.repos.getCommit({owner:sourceOwner,repo:sourceRepo,ref:metadata.default_branch,request:{timeout:15000}}));
      if(!/^[0-9a-f]{40}$/.test(head.sha || '')) throw new Error('Canonical source revision unavailable');
      canonical={branch:metadata.default_branch,sha:head.sha};canonicalOrigins.set(repository,canonical);
    }
    const comparison=await read(client=>client.rest.repos.compareCommitsWithBasehead({owner:sourceOwner,repo:sourceRepo,basehead:`${commit}...${canonical.sha}`,request:{timeout:15000}}));
    if(!['ahead','identical'].includes(comparison.status) || comparison.base_commit?.sha!==commit || comparison.merge_base_commit?.sha!==commit) throw new Error('Retained helper/workflow revision is not canonical merged source');
    return canonical;
  };
  const boundRepo = value => String(value?.full_name || '').toLowerCase() === event.repo;
  if (run.id !== selected.run_id || run.run_attempt !== selected.run_attempt || run.status !== 'completed'
      || run.path !== binding.workflow_path
      || !['workflow_dispatch','pull_request_target'].includes(run.event)
      || !boundRepo(run.repository) || !boundRepo(run.head_repository)
      || run.repository.id !== run.head_repository.id || !/^[0-9a-f]{40}$/.test(run.head_sha || '')) throw new Error('Retained source run is not an exact trusted completed attempt');
  const callerOrigin=await canonicalCommit(event.repo,run.head_sha);
  const references = (run.referenced_workflows || []).filter(row => row.path?.startsWith('stranske/Workflows/.github/workflows/reusable-agents-verifier.yml@'));
  if (references.length !== 1 || !/^[0-9a-f]{40}$/.test(references[0].sha || '')) throw new Error('Retained reusable workflow origin unavailable');
  const jobs = [], ids = new Set();
  let total, complete=false;
  for(let page=1;page<=10;page++) {
    const response = await withRetry(client => client.rest.actions.listJobsForWorkflowRunAttempt({owner,repo,run_id:selected.run_id,attempt_number:selected.run_attempt,per_page:100,page,request:{timeout:15000}}),opts);
    if (!Array.isArray(response.data?.jobs) || !Number.isSafeInteger(response.data.total_count)
        || (total !== undefined && total !== response.data.total_count)) throw new Error('Retained job inventory incomplete');
    total=response.data.total_count;
    for(const job of response.data.jobs) {
      if(ids.has(job.id) || job.run_id !== run.id || job.run_attempt !== selected.run_attempt || job.head_sha !== run.head_sha) throw new Error('Retained job identity mismatch');
      ids.add(job.id); jobs.push(job);
    }
    if(jobs.length===total && !response.headers?.link?.includes('rel="next"')) {complete=true;break;}
    if(!response.data.jobs.length || jobs.length>=total) throw new Error('Retained job inventory incomplete');
  }
  const candidates=jobs.filter(job=>job.name===binding.job_name || job.name.endsWith(` / ${binding.job_name}`));
  if(!complete || candidates.length!==1 || candidates[0].status!=='completed') throw new Error('Retained verifier job ambiguous');
  const job=candidates[0];
  const one = name => {const rows=(job.steps || []).filter(step=>step.name===name);if(rows.length!==1 || rows[0].status!=='completed' || rows[0].conclusion!=='success') throw new Error(`Retained step unproven: ${name}`);return rows[0];};
  const checkout=one('Checkout Workflows scripts'), pending=one(binding.pending_step), evaluator=one(binding.evaluator_step);
  const upload=one(assessment.mode==='evaluate'?'Retain evaluation execution evidence':'Upload comparison artifacts');
  if(![checkout,pending,evaluator,upload].every(step=>Number.isSafeInteger(step.number) && step.number>0 && Number.isFinite(Date.parse(step.started_at)) && Number.isFinite(Date.parse(step.completed_at)))) throw new Error('Retained step identity/timestamps unavailable');
  if(!(checkout.number<pending.number && pending.number<evaluator.number && evaluator.number<upload.number)) throw new Error('Retained execution ordering mismatch');
  const artifact=await read(client=>client.rest.actions.getArtifact({owner,repo,artifact_id:selected.artifact_id,request:{timeout:15000}}));
  const stem=assessment.mode==='evaluate'?'evaluation':'comparison';
  const created=Date.parse(artifact.created_at);
  if(artifact.id!==selected.artifact_id || artifact.name!==`${stem}-results-${run.id}` || artifact.expired!==false
      || !Number.isSafeInteger(artifact.size_in_bytes) || artifact.size_in_bytes<1 || artifact.size_in_bytes>maxBytes
      || !/^sha256:[0-9a-f]{64}$/.test(artifact.digest || '')
      || artifact.workflow_run?.id!==run.id || artifact.workflow_run.head_sha!==run.head_sha
      || artifact.workflow_run.repository_id!==run.repository.id || artifact.workflow_run.head_repository_id!==run.repository.id
      || !Number.isFinite(created) || created<Date.parse(upload.started_at) || created>Date.parse(upload.completed_at)) throw new Error('Retained artifact attempt/origin/size unproven');
  // Legacy receipts did not record the helper checkout SHA. Recover only the
  // exact checkout step's authenticated log window; never infer it from main.
  const logResponse=await read(client=>client.rest.actions.downloadJobLogsForWorkflowRun({owner,repo,job_id:job.id,request:{timeout:15000}}));
  const log=Buffer.isBuffer(logResponse)?logResponse.toString('utf8'):typeof logResponse==='string'?logResponse:Buffer.from(logResponse).toString('utf8');
  if(Buffer.byteLength(log)>16777216) throw new Error('Retained checkout log exceeds transport bound');
  const lines=log.split(/\r?\n/).filter(line=>{const stamp=Date.parse(line.slice(0,line.indexOf(' ')));return stamp>=Date.parse(checkout.started_at) && stamp<Date.parse(checkout.completed_at)+1000;}).join('\n');
  if(!lines.includes('repository: stranske/Workflows') || !lines.includes('path: .workflows-lib')) throw new Error('Retained helper checkout origin unproven');
  const hashes=[...lines.matchAll(/git log -1 --format=%H\r?\n[^\n]*?\s([0-9a-f]{40})\s*(?:\n|$)/g)].map(match=>match[1]);
  if(hashes.length!==1) throw new Error('Retained helper revision ambiguous');
  const helperSha=hashes[0];
  const helperOrigin=await canonicalCommit('stranske/Workflows',helperSha);
  if(helperSha!==references[0].sha) await canonicalCommit('stranske/Workflows',references[0].sha);
  const source=await read(client=>client.rest.repos.getContent({owner:'stranske',repo:'Workflows',path:'scripts/langchain/pr_verifier.py',ref:helperSha,request:{timeout:15000}}));
  if(source.encoding!=='base64' || typeof source.content!=='string' || Buffer.byteLength(source.content)>2796204) throw new Error('Retained helper validator source unavailable');
  const sourceHash=createHash('sha256').update(Buffer.from(source.content,'base64')).digest('hex');
  const archiveResponse=await read(client=>client.rest.actions.downloadArtifact({owner,repo,artifact_id:artifact.id,archive_format:'zip',request:{timeout:15000}}));
  const archive=Buffer.from(archiveResponse);
  const archiveHash=createHash('sha256').update(archive).digest('hex');
  if(archive.length>maxBytes || archiveHash!==artifact.digest.slice(7)) throw new Error('Retained artifact archive digest mismatch');
  const refreshed=await read(client=>client.rest.actions.getWorkflowRun({owner,repo,run_id:selected.run_id,request:{timeout:15000}}));
  if(refreshed.run_attempt!==latest.run_attempt || refreshed.status!=='completed' || refreshed.head_sha!==run.head_sha) throw new Error('Retained source changed during authentication');
  const proof={schema:'workflows-retained-origin/v1',repository:event.repo,current_run_id:String(currentRun),
    source_run_id:String(run.id),source_run_attempt:String(selected.run_attempt),source_run_head_sha:run.head_sha,
    workflow_path:binding.workflow_path,reusable_sha:references[0].sha,helper_sha:helperSha,validator_sha256:sourceHash,
    canonical_caller:callerOrigin,canonical_helpers:helperOrigin,
    job_id:job.id,job_inventory_sha256:digest(jobs),checkout_log_sha256:createHash('sha256').update(lines).digest('hex'),
    artifact_id:artifact.id,artifact_name:artifact.name,archive_sha256:archiveHash,archive_bytes:archive.length,
    verification_event:event,assessment_identity:assessment};
  fs.writeFileSync('verification-recovery-source.zip',archive,{flag:'wx'});
  fs.writeFileSync('verification-recovery-origin.json',JSON.stringify(proof,null,2)+'\n',{flag:'wx'});
  return proof;
}


function guardRecoveryHistory({event,assessment,comments,sourceRun,sourceAttempt=1,currentRun,currentAttempt=1,recoveryKey,reconciled=[]}) {
  validateEvent(event);
  const prefix=`https://github.com/${event.repo}/pull/${event.pr}#issuecomment-`;
  const candidates=[];
  for(const comment of comments) {
    if(!['github-actions','github-actions[bot]'].includes(comment.author)
        || !String(comment.url).toLowerCase().startsWith(prefix)) continue;
    if(comment.truncated && /<!-- (?:verifier-event-state\/v1|verifier-corpus-decision\/v1)/.test(String(comment.body))) {
      throw new Error('Recovery target has truncated authenticated assessment history');
    }
    for(const match of String(comment.body).matchAll(/<!-- (?:verifier-event-state\/v1|verifier-corpus-decision\/v1) (\{[^\n]+\}) -->/g)) {
      let row,actual;
      try {row=JSON.parse(match[1]);} catch {continue;}
      const sameSubject=['repo','pr','head_sha','evaluated_sha'].every(key=>String(row[key]).toLowerCase()===String(event[key]).toLowerCase());
      if(!sameSubject) continue;
      const run=Number(row.run_id), attempt=Number(row.run_attempt);
      const knownOlder=Number.isSafeInteger(run) && Number.isSafeInteger(attempt) && attempt>0
        && (run<sourceRun || (run===sourceRun && attempt<=sourceAttempt));
      if(knownOlder) continue;
      try {
        actual=validateEvent(row.verification_event);
        if(!Number.isSafeInteger(run) || run<1 || !Number.isSafeInteger(attempt) || attempt<1
            || !sameAssessment(row.assessment_identity,row.assessment_identity)
            || ['repo','pr','head_sha','evaluated_sha'].some(key=>actual[key]!==event[key])) throw new Error('Malformed target assessment');
      } catch {throw new Error('Recovery target has malformed authenticated assessment history');}
      if(run===currentRun && attempt===currentAttempt) continue;
      candidates.push({row,actual,comment});
    }
  }
  const identity=row=>`${row.run_id}:${row.run_attempt}`;
  const sameRecovery=row=>row.verification_event.event_id===event.event_id && sameAssessment(row.assessment_identity,assessment)
    && row.retained_revalidation?.recovery_key===recoveryKey;
  const noPost=row=>sameRecovery(row) && row.schema==='verifier-event-state/v1' && row.status==='incomplete'
    && row.retry_kind==='known_no_evaluation' && row.retryable===true
    && row.failure_cause==='retained_revalidation_before_publication'
    && row.retained_revalidation.provider_generation_performed===false
    && row.retained_revalidation.publication_effect==='none';
  const completeRecovery=entry=>sameRecovery(entry.row) && entry.row.schema==='verifier-corpus-decision/v1'
    && completedEvent(event,[entry.comment],assessment);
  const admitted=entry=>entry.row.result_admission?.schema==='verifier-result-admission/v1'
    && entry.row.result_admission.mode===assessment.mode
    && ['payload_sha256','execution_receipt_sha256'].every(key=>/^[0-9a-f]{64}$/.test(entry.row.result_admission[key] || ''))
    && entry.row.retained_revalidation.provider_generation_performed===false;
  // A positively observed admitted report settles a lost publication response.
  // If its lifecycle was left incomplete, a fresh revalidation may complete it;
  // unknown writes without such a report remain fenced below.
  const settled=new Set(candidates.filter(entry=>completeRecovery(entry) && admitted(entry)
    && candidates.some(({row})=>identity(row)===identity(entry.row) && row.status==='incomplete')
    && candidates.filter(({row})=>identity(row)===identity(entry.row) && row.status==='incomplete').every(({row})=>
      sameRecovery(row) && row.retry_kind==='uncertain_execution' && row.retryable===false
      && row.failure_cause==='retained_revalidation_publication_uncertain'
      && row.retained_revalidation.provider_generation_performed===false
      && row.retained_revalidation.publication_effect==='uncertain')).map(({row})=>identity(row)));
  const safe=new Set(candidates.filter(({row})=>noPost(row) && !candidates.some(({row:other})=>identity(other)===identity(row)
    && (other.verdict!==undefined || (other.status==='incomplete' && !noPost(other))))).map(({row})=>identity(row)));
  for(const proof of reconciled) {
    if(proof.schema==='verifier-no-evaluation-proof/v1' && proof.repo===event.repo && proof.event_id===event.event_id
        && sameAssessment(proof.assessment_identity,assessment) && proof.recovery_key===recoveryKey
        && proof.publication_conclusion==='skipped' && Number.isSafeInteger(proof.publication_step_number)
        && proof.publication_step_number>proof.evaluator_step_number) safe.add(identity(proof));
  }
  const newer=[];
  for(const {row,actual,comment} of candidates) {
      if(sameRecovery(row) && settled.has(identity(row))) continue;
      if(completeRecovery({row,actual,comment})
          && !candidates.some(entry=>identity(entry.row)===identity(row) && entry.row.status==='incomplete')) return 'duplicate';
      // A later assessment (including pending/incomplete) can change current
      // applicability. Never use a newer publication run to outvote that work.
      if(sameRecovery(row) && ['pending','incomplete'].includes(row.status) && safe.has(identity(row))) continue;
      newer.push(row);
  }
  if(newer.length) {
    const error=new Error('Retained recovery is superseded by a newer authenticated assessment');
    if(newer.every(row=>sameRecovery(row) && row.status==='pending')) {
      error.code='VERIFIER_RECOVERY_PENDING';
      error.pendingStates=[...new Map(newer.map(row=>[identity(row),row])).values()];
    }
    throw error;
  }
  return 'ready';
}


async function guardRetainedRecoveryHistory(options) {
  try {return guardRecoveryHistory(options);} catch(error) {
    if(error.code!=='VERIFIER_RECOVERY_PENDING') throw error;
    const reconciled=[];
    for(const state of error.pendingStates) {
      const result=await reconcilePendingExecution({...options,state});
      if(result.retry_kind!=='known_no_evaluation' || result.proof?.publication_conclusion!=='skipped') throw new Error('Prior recovery publication is active or uncertain; collect its existing result');
      reconciled.push(result.proof);
    }
    if(Array.isArray(options.observations)) options.observations.push(...reconciled);
    return guardRecoveryHistory({...options,reconciled});
  }
}


async function publishRetainedReport({github,manifest,origin,body,currentRun,currentAttempt=1,onPostAttempt=()=>{}}) {
  const {createHash}=require('crypto');
  const event=validateEvent(manifest.verification_event);
  if(origin.verification_event.event_id!==event.event_id || !sameAssessment(origin.assessment_identity,manifest.assessment_identity)) throw new Error('Recovery publication identity changed');
  const {withRetry}=await createTokenAwareRetry({github,task:'verifier',capabilities:['read-repo'],minRemaining:50});
  const opts={maxRetries:2,initialDelay:250,maxDelay:1000};
  const [owner,repo]=event.repo.split('/');
  const read=async fn=>(await withRetry(fn,opts)).data;
  const pull=await read(client=>client.rest.pulls.get({owner,repo,pull_number:Number(event.pr),request:{timeout:15000}}));
  if(pull.merged!==true || pull.head?.sha!==event.head_sha || pull.merge_commit_sha!==event.evaluated_sha) throw new Error('Recovery target revision changed before publication');
  for(const source of manifest.request.sources) {
    if(source.repository!==event.repo) throw new Error('Foreign recovery requirement source');
    const object=source.kind==='pull_request'?pull:source.kind==='issue'?await read(client=>client.rest.issues.get({owner,repo,issue_number:Number(source.number),request:{timeout:15000}})):null;
    if(!object || typeof object.body!=='string' || createHash('sha256').update(object.body).digest('hex')!==source.body_sha256) throw new Error('Recovery requirements changed before publication');
  }
  for(const required of manifest.material?.required_evidence || []) {
    if(required.kind!=='comment') continue; // Artifact IDs are immutable; retained member hashes stay bound to the event.
    const match=String(required.url).match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/(?:pull|issues)\/([1-9]\d*)#(issuecomment-|discussion_r|pullrequestreview-)([1-9]\d*)$/);
    if(!match || `${match[1]}/${match[2]}`.toLowerCase()!==event.repo) throw new Error('Foreign recovery evidence selector');
    const id=Number(match[5]);
    const record=await read(client=>match[4]==='issuecomment-'?client.rest.issues.getComment({owner,repo,comment_id:id,request:{timeout:15000}})
      :match[4]==='discussion_r'?client.rest.pulls.getReviewComment({owner,repo,comment_id:id,request:{timeout:15000}})
      :client.rest.pulls.getReview({owner,repo,pull_number:Number(match[3]),review_id:id,request:{timeout:15000}}));
    if(typeof record.body!=='string' || createHash('sha256').update(record.body).digest('hex')!==required.body_sha256) throw new Error('Required recovery material changed before publication');
  }
  const comments=async()=>{
    const rows=[],ids=new Set();let complete=false;
    for(let page=1;page<=10;page++) {
      const response=await withRetry(client=>client.rest.issues.listComments({owner,repo,issue_number:Number(event.pr),per_page:100,page,request:{timeout:15000}}),opts);
      if(!Array.isArray(response.data)) throw new Error('Recovery publication history incomplete');
      for(const row of response.data) {
        if(ids.has(row.id) || typeof row.body!=='string') throw new Error('Recovery publication history ambiguous');
        ids.add(row.id);rows.push({author:row.user?.login,url:row.html_url,body:row.body,truncated:false});
      }
      if(!response.headers?.link?.includes('rel="next"')) {complete=true;break;}
    }
    if(!complete) throw new Error('Recovery publication history incomplete');
    return rows;
  };
  const check=rows=>guardRetainedRecoveryHistory({github,event,assessment:manifest.assessment_identity,comments:rows,
    sourceRun:Number(origin.source_run_id),sourceAttempt:Number(origin.source_run_attempt),currentRun,currentAttempt,recoveryKey:origin.recovery_key,
    currentExecution:{run_id:String(currentRun),run_attempt:String(currentAttempt),repo:event.repo,workflow_ref:process.env.GITHUB_WORKFLOW_REF || '',phase:'pre_publication'}});
  const alreadyPublished=rows=>rows.some(row=>['github-actions','github-actions[bot]'].includes(row.author) && row.body===body);
  const before=await comments();
  if(alreadyPublished(before) || await check(before)==='duplicate') return {published:true,duplicate:true};
  const markers=[...body.matchAll(/<!-- verifier-corpus-decision\/v1 (\{[^\n]+\}) -->/g)];
  if(markers.length!==1) throw new Error('Recovery report lacks one admitted terminal decision');
  const decision=JSON.parse(markers[0][1]);
  if(decision.retained_revalidation?.recovery_key!==origin.recovery_key || decision.verification_event?.event_id!==event.event_id
      || String(decision.run_id)!==String(currentRun)) throw new Error('Recovery report admission identity mismatch');
  try {
    // Consequential POST is once-only. Retry only reads, never an uncertain write.
    onPostAttempt();
    const response=await github.rest.issues.createComment({owner,repo,issue_number:Number(event.pr),body,request:{timeout:15000}});
    return {published:true,duplicate:false,comment_id:response.data.id};
  } catch(error) {
    const after=await comments();
    if(alreadyPublished(after) || await check(after)==='duplicate') return {published:true,duplicate:true,reconciled_after_uncertain_post:true};
    const uncertain=new Error('Recovery publication outcome uncertain; reconcile authenticated comment identity before retry');
    uncertain.code='VERIFIER_RECOVERY_PUBLICATION_UNCERTAIN';throw uncertain;
  }
}

module.exports = {executionBinding,reconcilePendingExecution,acquireRetainedExecution,guardRecoveryHistory,guardRetainedRecoveryHistory,publishRetainedReport};
