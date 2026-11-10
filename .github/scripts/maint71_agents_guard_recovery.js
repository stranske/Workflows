'use strict';

const { createHash } = require('node:crypto');
const { parseDeliveryRecord } = require('./sync_pr_lease_contract');
const { isTrustedGeneratedDeliveryPr } = require('./sync_pr_merge_contract');
const WORKFLOW = 'agents-guard.yml';
const CONTEXT = 'Health 45 Agents Guard / guard';
const ACTORS = ['stranske', 'stranske-automation-bot', 'github-actions[bot]'];
const MAX_ATTEMPT = 3;
// Both native callers inject withRetry from createTokenAwareRetry; this helper
// uses that transport for every read and disables retries on non-idempotent writes.
const sha = value => /^[a-f0-9]{40}$/.test(value || '');
const need = (condition, reason) => { if (!condition) throw new Error(reason); };
const version = run => JSON.stringify([run.id, run.run_attempt, run.head_sha, run.status, run.conclusion, run.updated_at]);

function agentsGuardNeedsRecovery(classification) {
  return [...(classification?.failed || []), ...(classification?.pending || [])]
    .some(check => check.name === CONTEXT)
    || (classification?.declared_contexts?.never_started || []).includes(CONTEXT);
}

function agentsGuardNeedsInspection(classification, checks = []) {
  return agentsGuardNeedsRecovery(classification)
    || (!checks.some(check => check.name === CONTEXT) && checks.some(check => check.name === 'guard'
      && check.app?.slug === 'github-actions' && /\/actions\/runs\/\d+\/job\/\d+/.test(check.details_url || '')));
}

function agentsGuardRefusalHandoff(classification, recovery, reviewBlocked = false) {
  if (reviewBlocked || recovery?.mode !== 'refused' || !agentsGuardNeedsRecovery(classification)) return null;
  const other = [...(classification.failed || []), ...(classification.pending || [])]
    .some(check => check.name !== CONTEXT)
    || (classification.declared_contexts?.never_started || []).some(name => name !== CONTEXT);
  return other ? null : recovery.next_command;
}

async function recoverCancelledAgentsGuard({ owner, repo, pr: selected, withRetry,
  verifyPlan, dryRunMode = false, context }) {
  const target = { owner, repo }, repository = `${owner}/${repo}`;
  const result = { workflow: WORKFLOW, required_context: CONTEXT, head_sha: selected?.head?.sha,
    blocking: 1, drainable: 1, next_command: 'reread-original-agents-guard-run-and-qualified-status' };
  const done = (mode, reason, extra = {}) => ({ ...result, mode, reason, ...extra });
  const read = async (group, method, args) => (await withRetry(client => client.rest[group][method](args))).data;
  async function pages(group, method, args, field) {
    const rows = [];
    for (let page = 1; page <= 10; page++) {
      const data = await read(group, method, { ...args, per_page: 100, page });
      const chunk = field ? data?.[field] : data;
      need(Array.isArray(chunk), 'guard_inventory_unreadable'); rows.push(...chunk);
      if (chunk.length < 100) {
        if (field) need(Number.isSafeInteger(data.total_count) && data.total_count === rows.length,
          'guard_inventory_incomplete');
        return rows;
      }
    }
    throw new Error('guard_inventory_bound');
  }
  function validatePr(pr) {
    need(pr?.state === 'open' && !pr.merged && pr.draft === false
      && pr.number === selected.number && pr.head?.sha === selected.head?.sha
      && pr.head?.ref === selected.head?.ref && sha(pr.head.sha)
      && pr.head.repo?.full_name === repository && pr.base?.repo?.full_name === repository
      && isTrustedGeneratedDeliveryPr(pr, ACTORS), 'guard_target_changed_or_untrusted');
    const record = parseDeliveryRecord(pr.body || '');
    need(record?.repository === repository && record.delivery_state === 'sealed'
      && record.head_observed_sha === pr.head.sha && record.sealed_head_sha === pr.head.sha,
    'guard_target_not_exactly_sealed');
    return record;
  }
  function ordinary(rows, pr) {
    need(new Set(rows.map(run => run.id)).size === rows.length, 'guard_inventory_changed');
    const original = rows.filter(run => run.event === 'pull_request');
    need(original.length, 'guard_original_pr_event_missing');
    need(original.every(run => run.path === `.github/workflows/${WORKFLOW}`
      && run.name === 'Health 45 Agents Guard' && run.head_sha === pr.head.sha
      && run.repository?.full_name === repository && Number.isSafeInteger(run.repository.id)
      && run.repository.id > 0 && run.head_repository?.id === run.repository.id
      && run.head_repository?.full_name === repository && run.head_branch === pr.head.ref
      && Array.isArray(run.pull_requests)
      && (run.pull_requests.some(row => row.number === pr.number) || run.pull_requests.length === 0)
      && Number.isSafeInteger(run.run_number) && Number.isSafeInteger(run.run_attempt)
      && run.run_attempt > 0 && Number.isSafeInteger(run.id) && run.id > 0), 'guard_original_identity_ambiguous');
    return original.sort((a, b) => b.run_number - a.run_number || b.run_attempt - a.run_attempt)[0];
  }
  try {
    need(repository.toLowerCase() !== 'stranske/collab-admin' && owner === 'stranske'
      && selected?.number && sha(selected.head?.sha), 'guard_target_invalid');
    const pr = await read('pulls', 'get', { ...target, pull_number: selected.number });
    if (pr?.merged || pr?.state === 'closed') return done('not-needed', 'guard_pr_already_closed', { blocking: 0, drainable: 0 });
    const record = validatePr(pr);
    const query = { ...target, workflow_id: WORKFLOW, head_sha: pr.head.sha };
    let runs = await pages('actions', 'listWorkflowRuns', query, 'workflow_runs');
    if (runs.some(run => run.status !== 'completed')) return done('wait', 'guard_writer_active');
    const run = ordinary(runs, pr);
    Object.assign(result, { run_id: run.id, run_attempt: run.run_attempt, event: run.event });
    if (run.conclusion === 'success') {
      const statuses = await pages('repos', 'listCommitStatusesForRef', { ...target, ref: pr.head.sha });
      const status = statuses.filter(row => row.context === CONTEXT
        && String(row.description || '').startsWith(`[guard-pr:${pr.number}] `))
        .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0];
      const qualified = status?.state === 'success'
        && status.target_url === run.html_url
        && Number.isFinite(Date.parse(run.run_started_at))
        && Date.parse(status.updated_at) >= Date.parse(run.run_started_at);
      return qualified ? done('existing', 'guard_qualified_pass', { blocking: 0, drainable: 0, qualified_pass: true })
        : done('refused', 'guard_success_without_current_qualified_pass', { next_command: 'repair-original-guard-status-publication' });
    }
    if (run.conclusion !== 'cancelled') return done('refused', 'guard_not_jobless_cancellation');
    if (run.run_attempt >= MAX_ATTEMPT) return done('refused', 'guard_repeated_cancellation', {
      next_command: 'repair-workflow-admission-then-trigger-a-new-original-pr-event' });
    const jobs = await read('actions', 'listJobsForWorkflowRunAttempt', {
      ...target, run_id: run.id, attempt_number: run.run_attempt, per_page: 100, page: 1 });
    if (jobs?.total_count !== 0 || !Array.isArray(jobs.jobs) || jobs.jobs.length !== 0) {
      return done('refused', 'guard_cancellation_had_jobs_or_incomplete_evidence', {
        next_command: 'inspect-original-attempt-jobs-before-any-retry' });
    }
    const markers = [...String(pr.body || '').matchAll(/<!-- workflows-consumer-sync:v1 ([\s\S]*?) -->/g)];
    need(markers.length === 1, 'guard_native_metadata_ambiguous');
    const metadata = JSON.parse(markers[0][1]);
    need(metadata.consumer_repo === repository && typeof verifyPlan === 'function', 'guard_native_binding_missing');
    const binding = await verifyPlan({ ...target, pr, record, metadata, withRetry });
    const identity = { repository, pr: pr.number, head_sha: pr.head.sha, run_id: run.id,
      run_attempt: run.run_attempt, plan_id: binding.plan_id, source_commit: binding.source_commit };
    const id = createHash('sha256').update(JSON.stringify(identity)).digest('hex');
    const marker = `<!-- maint71-guard-rerun:v1 ${id} -->`;
    result.claim_id = id;
    const comments = await pages('issues', 'listComments', { ...target, issue_number: pr.number });
    if (comments.some(comment => ACTORS.includes(comment.user?.login) && String(comment.body || '').includes(marker))) {
      return done('wait', 'guard_rerun_claim_retained');
    }
    if (dryRunMode) return done('would-rerun', 'guard_original_jobless_cancellation_verified');
    need(context?.repo?.owner === 'stranske' && context.repo.repo === 'Workflows'
      && Number.isSafeInteger(context.runId) && context.runId > 0, 'guard_native_writer_context_required');
    const body = `${marker}\n${JSON.stringify({ ...identity, requested_by: {
      repository: 'stranske/Workflows', run_id: context.runId } })}`;
    const claim = await withRetry(client => client.rest.issues.createComment({ ...target,
      issue_number: pr.number, body }), { maxRetries: 0 });
    need(Number.isSafeInteger(claim.data?.id) && ACTORS.includes(claim.data?.user?.login)
      && claim.data?.body === body, 'guard_claim_write_unconfirmed');
    result.claim_comment_id = claim.data.id;
    const currentPr = await read('pulls', 'get', { ...target, pull_number: pr.number });
    const currentRecord = validatePr(currentPr);
    need(currentRecord.plan_id === record.plan_id && currentRecord.source_commit === record.source_commit,
      'guard_target_binding_changed');
    const current = await read('actions', 'getWorkflowRun', { ...target, run_id: run.id });
    need(version(current) === version(run), 'guard_original_attempt_changed');
    runs = await pages('actions', 'listWorkflowRuns', query, 'workflow_runs');
    if (runs.some(row => row.status !== 'completed') || version(ordinary(runs, currentPr)) !== version(run)) {
      return done('wait', 'guard_writer_or_attempt_changed_after_claim');
    }
    try {
      const response = await withRetry(client => client.rest.actions.reRunWorkflow({ ...target, run_id: run.id }), { maxRetries: 0 });
      need(response.status >= 200 && response.status < 300, 'guard_rerun_response_unconfirmed');
      return done('requested', 'guard_original_event_rerun_accepted', { rerun_status: response.status });
    } catch (error) {
      const status = Number(error?.status || error?.response?.status);
      return done('wait', 'guard_rerun_outcome_requires_original_attempt_readback', {
        ...(status >= 100 && status <= 599 ? { http_status: status } : {}) });
    }
  } catch (error) {
    return done('unknown', /^[a-z][a-z0-9_]+$/.test(error?.message || '') ? error.message : 'guard_evidence_or_operation_unavailable');
  }
}

module.exports = { CONTEXT, MAX_ATTEMPT, agentsGuardNeedsRecovery, agentsGuardNeedsInspection,
  agentsGuardRefusalHandoff, recoverCancelledAgentsGuard };
