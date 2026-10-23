'use strict';

const { digest, validateEvent, sameAssessment } = require('./verification_event.js');
const { createTokenAwareRetry } = require('./github-api-with-retry.js');

function executionBinding(mode) {
  if (!['evaluate','compare'].includes(mode)) throw new Error('Unsupported verifier execution mode');
  return {schema:'verifier-execution-binding/v1',workflow_path:'.github/workflows/agents-verifier.yml',
    job_name:'Run post-merge verifier',pending_step:'Record verification event pending',
    evaluator_step:mode === 'evaluate' ? 'Run LLM evaluation' : 'Run multi-provider comparison'};
}

async function reconcilePendingExecution({github,event,assessment,state,maxPages = 10}) {
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
    const readRun = async () => (await withRetry(client => client.rest.actions.getWorkflowRun({
      owner,repo,run_id:runId,request:{timeout:15000}}),retryOptions)).data;
    const matches = run => run?.id === runId && run.run_attempt === attempt && run.status === 'completed'
      && run.path === binding.workflow_path && /^[0-9a-f]{40}$/.test(run.head_sha || '')
      && ['workflow_dispatch','pull_request_target'].includes(run.event)
      && String(run.repository?.full_name || '').toLowerCase() === event.repo
      && String(run.head_repository?.full_name || '').toLowerCase() === event.repo;
    const run = await readRun();
    if (!matches(run)) return unknown('prior_run_active_changed_or_unbound');
    const jobs = [], ids = new Set();
    let total, complete = false;
    for (let page=1;page<=Math.min(maxPages,10);page+=1) {
      const response = await withRetry(client => client.rest.actions.listJobsForWorkflowRunAttempt({owner,repo,
        run_id:runId,attempt_number:attempt,per_page:100,page,request:{timeout:15000}}),retryOptions);
      if (!Array.isArray(response?.data?.jobs) || !Number.isSafeInteger(response.data.total_count)
          || response.data.total_count < 0 || (total !== undefined && total !== response.data.total_count)) return unknown('prior_attempt_jobs_incomplete');
      total = response.data.total_count;
      for (const job of response.data.jobs) {
        if (!Number.isSafeInteger(job?.id) || job.id < 1 || ids.has(job.id)
            || job.run_id !== runId || job.run_attempt !== attempt || job.head_sha !== run.head_sha) return unknown('prior_attempt_job_identity_mismatch');
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
    if (job.status !== 'completed' || !Array.isArray(job.steps)) return unknown('prior_verifier_job_incomplete');
    const pending = job.steps.filter(step => step.name === binding.pending_step);
    const evaluator = job.steps.filter(step => step.name === binding.evaluator_step);
    if (pending.length !== 1 || evaluator.length !== 1 || pending[0].status !== 'completed'
        || pending[0].conclusion !== 'success' || !Number.isSafeInteger(pending[0].number)
        || pending[0].number < 1 || !Number.isSafeInteger(evaluator[0].number)
        || evaluator[0].number <= pending[0].number) return unknown('prior_evaluator_step_evidence_unavailable');
    const allEvaluatorSteps = jobs.flatMap(item => Array.isArray(item.steps) ? item.steps : [])
      .filter(step => ['Run LLM evaluation','Run multi-provider comparison'].includes(step.name));
    if (allEvaluatorSteps.some(step => step.status !== 'completed' || step.conclusion !== 'skipped')) {
      // Started steps are not proof of a usable review. Direct existing
      // collection to retained outputs; never purchase another evaluation here.
      const result = unknown('prior_evaluator_started_collect_existing_outputs');
      result.existing_execution.run_url = `https://github.com/${event.repo}/actions/runs/${runId}/attempts/${attempt}`;
      result.existing_execution.output_names = assessment.mode === 'evaluate'
        ? ['evaluation.json','evaluation-execution.json'] : ['comparison.json'];
      return result;
    }
    const refreshed = await readRun();
    if (!matches(refreshed) || refreshed.head_sha !== run.head_sha) return unknown('prior_run_changed_during_reconciliation');
    const proof = {schema:'verifier-no-evaluation-proof/v1',repo:event.repo,event_id:event.event_id,
      assessment_identity:assessment,run_id:String(runId),run_attempt:String(attempt),run_head_sha:run.head_sha,
      workflow_path:binding.workflow_path,job_id:job.id,pending_step_number:pending[0].number,
      evaluator_step_number:evaluator[0].number,evaluator_step:binding.evaluator_step,conclusion:'skipped',
      source:'actions.listJobsForWorkflowRunAttempt',jobs_sha256:digest(jobs)};
    return {retry_kind:'known_no_evaluation',retryable:true,failure_cause:'authoritative_evaluator_step_skipped',proof};
  } catch { return unknown('prior_execution_reconciliation_unavailable'); }
}

module.exports = {executionBinding,reconcilePendingExecution};
