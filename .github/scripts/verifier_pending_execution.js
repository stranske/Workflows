'use strict';

const { digest, validateEvent, sameAssessment } = require('./verification_event.js');
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
    const binding = executionBinding(assessment.mode);
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
        .filter(step => ['Run LLM evaluation','Run multi-provider comparison'].includes(step.name));
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
      observations.push({run,jobs,job,pending,evaluator,current});
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
    return {retry_kind:'known_no_evaluation',retryable:true,failure_cause:'authoritative_evaluator_step_skipped',proof};
  } catch { return unknown('prior_execution_reconciliation_unavailable'); }
}

module.exports = {executionBinding,reconcilePendingExecution};
