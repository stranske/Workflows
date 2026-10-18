'use strict';

const { validateIndependentFindingVerification, collectFindingReviewState,
  validateNativeConversationDisposition, collectOriginatingCompletions } = require('./maint71_finding_verification');

const DEFAULT_REVIEW_POLICY = Object.freeze({
  minimum_responses: 1,
  quiet_period_minutes: 7,
  maximum_wait_minutes: 15,
  non_response_patterns: [],
});

const GENERATED_DELIVERY_REQUIRED_CONTEXTS = Object.freeze(['Gate / gate']);
const STALE_CANARY_HOURS = 6;

// Age is a recovery trigger for blocked canaries, never a hold on green ones.
// Only a successful producer observation resets the clock; comments do not.
function canaryNeedsRefresh(canary, now = Date.now()) {
  if (canary.mergeable_state === 'behind') return 'behind';
  if (canary.check_status === 'checks_failed' && !canary.expected_preseal_gate_hold) {
    return 'checks_failed';
  }
  if (canary.active_review_thread_count > 0) return 'review_blocked';
  // Leave healthy heads on the normal exact-head merge/evidence path. Unknown
  // mergeability still goes through that path's existing fail-closed gates.
  if (['ready', 'success'].includes(canary.check_status) && canary.mergeable !== false
    && !['dirty', 'blocked', 'unknown', 'draft'].includes(canary.mergeable_state)) return null;
  const observed = Date.parse(canary.head_observed_at || canary.updated_at || canary.created_at || '');
  if (Number(now) - observed > STALE_CANARY_HOURS * 60 * 60 * 1000) return 'stale';
  return null;
}

const EXPECTED_PRESEAL_GATE_JOB_SETS = Object.freeze([
  // Current consumer template.
  Object.freeze(['detect changed files', 'generated delivery seal', 'summary']),
  // Legacy checks still present on already-open stable canaries.
  Object.freeze(['classify changed paths', 'gate-summary', 'generated delivery seal']),
]);
const EXPECTED_PRESEAL_ANNOTATION = 'Process completed with exit code 1.';

function workflowRunIdFromUrl(value, owner, repo) {
  try {
    const url = new URL(String(value || ''));
    if (url.hostname !== 'github.com'
      || url.pathname.split('/').slice(1, 3).join('/') !== `${owner}/${repo}`) return 0;
    const match = url.pathname.match(/\/actions\/runs\/(\d+)(?:\/|$)/);
    return match ? Number(match[1]) : 0;
  } catch {
    return 0;
  }
}

// This recognizes only the exact-head staging/reviewing seal hold so the
// existing lifecycle can run. The classifier check exposes only a generic
// process-exit annotation, so a concurrent classifier error may also advance
// to sealing; the raw checks remain failed and only a fresh post-seal Gate can
// authorize the existing merge path.
async function isExpectedPresealGateFailure({
  owner, repo, headSha, deliveryRecord, deliveryState, classification, allChecks, withRetry,
}) {
  if (!['staging', 'reviewing'].includes(deliveryState)
    || !/^[a-f0-9]{40}$/i.test(String(headSha || ''))
    || deliveryRecord?.delivery_state !== deliveryState
    || String(deliveryRecord?.head_observed_sha || '').toLowerCase() !== headSha.toLowerCase()
    || classification?.status !== 'checks_failed'
    || !Array.isArray(classification.failed) || classification.failed.length !== 1
    || String(classification.failed[0]?.name || '').trim() !== 'Gate / gate'
    || String(classification.failed[0]?.conclusion || '').toLowerCase() !== 'failure') {
    return false;
  }
  const gateCheck = (allChecks || []).find((check) => check === classification.failed[0]
    || (String(check?.name || '').trim() === 'Gate / gate'
      && String(check?.head_sha || '').toLowerCase() === headSha.toLowerCase()
      && String(check?.conclusion || '').toLowerCase() === 'failure'));
  const runId = workflowRunIdFromUrl(
    gateCheck?.details_url || gateCheck?.html_url, owner, repo,
  );
  if (!runId) return false;
  try {
    const { data: run } = await withRetry((client) => client.rest.actions.getWorkflowRun({
      owner, repo, run_id: runId,
    }));
    if (Number(run?.id) !== runId
      || String(run?.head_sha || '').toLowerCase() !== headSha.toLowerCase()
      || String(run?.name || '').trim() !== 'Gate'
      || String(run?.path || '') !== '.github/workflows/pr-00-gate.yml'
      || run?.status !== 'completed' || run?.conclusion !== 'failure') return false;

    const jobs = await withRetry((client) => client.paginate(
      client.rest.actions.listJobsForWorkflowRun,
      { owner, repo, run_id: runId, per_page: 100 },
    ));
    if (!Array.isArray(jobs) || jobs.length === 0) return false;
    const failed = jobs.filter((job) => job?.status === 'completed'
      && job?.conclusion === 'failure').map((job) => String(job?.name || '').trim()).sort();
    const expectedJobs = EXPECTED_PRESEAL_GATE_JOB_SETS.find((names) =>
      names.length === failed.length && names.every((name, index) => name === failed[index]));
    if (!expectedJobs) return false;
    if (jobs.some((job) => job?.status !== 'completed'
      || !['success', 'skipped', 'neutral', 'failure'].includes(job?.conclusion)
      || (job.conclusion === 'failure'
        && !expectedJobs.includes(String(job?.name || '').trim())))) return false;
    const sealJob = jobs.find((job) => job?.name === 'generated delivery seal'
      && job?.status === 'completed' && job?.conclusion === 'failure');
    if (!Number.isSafeInteger(Number(sealJob?.id)) || Number(sealJob.id) <= 0) return false;

    const { data: sealCheck } = await withRetry((client) => client.rest.checks.get({
      owner, repo, check_run_id: Number(sealJob.id),
    }));
    if (String(sealCheck?.name || '').trim() !== 'generated delivery seal'
      || String(sealCheck?.head_sha || '').toLowerCase() !== headSha.toLowerCase()
      || sealCheck?.status !== 'completed' || sealCheck?.conclusion !== 'failure'
      || String(sealCheck?.app?.slug || '').toLowerCase() !== 'github-actions'
      || !Number.isSafeInteger(sealCheck?.output?.annotations_count)) return false;
    const annotations = await withRetry((client) => client.paginate(
      client.rest.checks.listAnnotations,
      { owner, repo, check_run_id: Number(sealJob.id), per_page: 100 },
    ));
    if (!Array.isArray(annotations)
      || annotations.length !== sealCheck.output.annotations_count) return false;
    const failures = annotations.filter((row) => row?.annotation_level === 'failure');
    const exactReason = `Mutable generated delivery is not mergeable: delivery_not_sealed:${deliveryState}. Maint 71 must seal this exact head after bounded reviewer settlement.`;
    if (failures.filter((row) => String(row?.message || '').trim() === exactReason).length !== 1
      || failures.some((row) => ![exactReason, EXPECTED_PRESEAL_ANNOTATION]
        .includes(String(row?.message || '').trim()))) return false;
    return true;
  } catch {
    return false;
  }
}

async function routeCanaryReviewUpstream({ canary, manifestEntries, withRetry, context }) {
  const { resolveManifestSyncedSource } = require('./sync_pr_merge_contract');
  const { data: writer } = await withRetry((client) => client.rest.users.getAuthenticated());
  const writerLogin = String(writer?.login || '').trim();
  if (!writerLogin) throw new Error('canary_upstream_writer_unknown');
  const routed = [];
  for (const thread of canary.threads || []) {
    if (thread.isResolved || thread.isOutdated) continue;
    const source = resolveManifestSyncedSource(thread.path, manifestEntries);
    if (!source) continue;
    const origin = thread.comments?.nodes?.[0]?.url;
    if (!origin || !thread.id) throw new Error('canary_review_thread_link_missing');
    const location = { owner: context.repo.owner, repo: context.repo.repo };
    const { data: commits } = await withRetry((client) => client.rest.repos.listCommits({
      ...location, sha: context.payload.repository?.default_branch || 'main',
      path: source.sourcePath, per_page: 1,
    }));
    if (!commits[0]?.sha) throw new Error(`canary_upstream_source_missing:${source.sourcePath}`);
    const commit = commits[0].sha;
    const prs = await withRetry((client) => client.paginate(
      client.rest.repos.listPullRequestsAssociatedWithCommit,
      { ...location, commit_sha: commit, per_page: 100 },
    ));
    const latest = prs.filter((pr) => pr.merged_at && pr.base?.repo?.full_name ===
      `${location.owner}/${location.repo}`)
      .sort((a, b) => Date.parse(b.merged_at) - Date.parse(a.merged_at))[0];
    const marker = `<!-- maint71-canary-upstream:${canary.owner}/${canary.repo}:${thread.id} -->`;
    const comments = await withRetry((client) => client.paginate(
      latest ? client.rest.issues.listComments : client.rest.repos.listCommentsForCommit,
      { ...location, ...(latest ? { issue_number: latest.number } : { commit_sha: commit }),
        per_page: 100 },
    ));
    if (comments.some((comment) => comment?.user?.login === writerLogin
      && String(comment.body || '').includes(marker))) continue;
    const body = [marker,
      `Maint 71: stable canary ${canary.owner}/${canary.repo}#${canary.pr} is review_blocked.`,
      `Upstream source: \`${source.sourcePath}\` (consumer path \`${thread.path}\`).`,
      `Consumer finding: [${thread.id}](${origin}).`,
      'Repair the shared source and redeliver through Maint 68; consumer review remains blocking.',
    ].join('\n');
    await withRetry((client) => latest
      ? client.rest.issues.createComment({ ...location, issue_number: latest.number, body })
      : client.rest.repos.createCommitComment({ ...location, commit_sha: commit, body }));
    routed.push({ source_path: source.sourcePath, thread_id: thread.id, pr: latest?.number || null });
  }
  return routed;
}

async function refreshStableCanaries({
  canaries, withRetry, context, core, manifestEntries, enabled, now = Date.now(),
}) {
  const counts = { red: 0, review_blocked: 0, stale: 0, refresh_dispatched: 0 };
  // Run-local plan-id deduplication: each distinct held plan gets one request.
  const plans = new Map();
  const errors = [];
  for (const canary of canaries) {
    if (canary.check_status === 'checks_failed') counts.red++;
    if (canary.active_review_thread_count > 0) counts.review_blocked++;
    const reason = canaryNeedsRefresh(canary, now);
    if (reason && canaryNeedsRefresh({ ...canary, mergeable_state: '', mergeable: false,
      check_status: '', active_review_thread_count: 0 }, now) === 'stale') counts.stale++;
    canary.refresh_reason = reason;
    if (!reason) continue;
    if (!canary.plan_id) {
      errors.push(`canary_refresh_plan_missing:${canary.owner}/${canary.repo}`);
      continue;
    }
    if (!plans.has(canary.plan_id)) plans.set(canary.plan_id, []);
    plans.get(canary.plan_id).push(canary);
  }
  try {
    if (enabled && plans.size) {
      // Keep the existing producer-writer guard. A running promotion or
      // refresh owns these stable heads; leave the request visible for retry.
      const { data } = await withRetry((client) => client.rest.actions.listWorkflowRuns({
        owner: context.repo.owner, repo: context.repo.repo,
        workflow_id: 'maint-68-sync-consumer-repos.yml', per_page: 100,
      }));
      if (!Array.isArray(data.workflow_runs)) throw new Error('canary_refresh_history_unreadable');
      const active = data.workflow_runs.some((run) =>
        ['queued', 'in_progress', 'waiting', 'pending', 'requested'].includes(run.status)
        && /^Maint 68 (canary|promote) /.test(run.display_title || ''));
      for (const [plan, rows] of plans) {
        for (const canary of rows.filter((row) => row.active_review_thread_count > 0)) {
          try {
            canary.upstream_comments = await routeCanaryReviewUpstream({
              canary, manifestEntries, withRetry, context,
            });
          } catch (error) {
            errors.push(`canary_upstream_routing_failed:${error.message}`);
          }
        }
        if (active) {
          core.notice(`Canary refresh ${plan} queued: Maint 68 writer already active`);
          continue;
        }
        await withRetry((client) => client.rest.actions.createWorkflowDispatch({
          owner: context.repo.owner, repo: context.repo.repo,
          workflow_id: 'maint-68-sync-consumer-repos.yml',
          ref: context.payload.repository?.default_branch || 'main',
          inputs: { phase: 'canary', delivery_scope: 'full', dry_run: 'false', force: 'false' },
        }));
        counts.refresh_dispatched++;
        core.notice(`dispatch-maint-68-phase-canary-no-filter: ${plan}; reasons=` +
          rows.map((row) => `${row.owner}/${row.repo}:${row.refresh_reason}`).join(', ') +
          '; completion awaits a successful Maint 68 run');
      }
    }
  } catch (error) {
    errors.push(`canary_refresh_failed:${error.message}`);
  }
  const line = `canaries: red=${counts.red} review_blocked=${counts.review_blocked} ` +
    `stale=${counts.stale} refresh_dispatched=${counts.refresh_dispatched} ` +
    `held_plan=${[...plans.keys()].join(',') || 'none'}`;
  console.log(line);
  await core.summary.addRaw(`${line}\n`).write();
  for (const error of errors) core.setFailed(error);
  return { ...counts, held_plans: [...plans.keys()], errors, canaries };
}

function enforceGeneratedDeliveryRequiredContexts(contexts = []) {
  const enforced = new Set(
    [...(contexts || [])].map((context) => String(context || '').trim()).filter(Boolean),
  );
  for (const context of GENERATED_DELIVERY_REQUIRED_CONTEXTS) {
    enforced.add(context);
  }
  return enforced;
}

// Read from the BASE branch: the consumer's merged declaration binds its
// deliveries, and a delivery's own head can never loosen it.
async function readConsumerDeclaredContexts({ withRetry, owner, repo, branch }) {
  const {
    CONSUMER_REQUIRED_CONTEXTS_PATH,
    parseConsumerRequiredContexts,
  } = require('./sync_pr_merge_contract.js');
  let file;
  try {
    ({ data: file } = await withRetry((client) => client.rest.repos.getContent({
      owner,
      repo,
      path: CONSUMER_REQUIRED_CONTEXTS_PATH,
      ref: branch,
    })));
  } catch (error) {
    const status = error?.status || error?.response?.status;
    if (status === 404) return { state: 'none', contexts: new Set(), error: '' };
    throw error;
  }
  if (Array.isArray(file) || file?.type !== 'file' || typeof file?.content !== 'string') {
    return { state: 'unparseable', contexts: new Set(), error: 'not a readable file' };
  }
  const encoding = String(file.encoding || 'base64');
  const text = encoding === 'base64'
    ? Buffer.from(file.content, 'base64').toString('utf8')
    : file.content;
  return parseConsumerRequiredContexts(text);
}

// Every exact-head gate reads the checks afresh. The row adopts the latest
// reading, so a declared check that changed between gates is reported as the
// gate that decided saw it, never as an earlier snapshot.
function adoptFinalCheckEvidence(deliveryContext, gate) {
  const evidence = gate?.finalCheckEvidence;
  if (!evidence) return;
  deliveryContext.consumer_declared_contexts = {
    state: evidence.declaredContexts?.state || 'none',
    ...(evidence.classification?.declared_contexts || {}),
  };
}

function hasCompleteReviewThreadEvidence(connection) {
  return Boolean(
    connection
    && Array.isArray(connection.nodes)
    && connection.pageInfo?.hasNextPage === false
    && connection.nodes.every((thread) =>
      typeof thread?.isResolved === 'boolean' && typeof thread?.isOutdated === 'boolean'
    )
  );
}

// Keep the last delivery read bound to the selected record and exact PR head.
function independentVerificationDeliveryUnchanged({ previous, current, head, branch, now = Date.now() }) {
  const { generatedDeliveryLane } = require('./sync_pr_merge_contract');
  const { isDeepStrictEqual } = require('node:util');
  const lane = generatedDeliveryLane(branch);
  const devTool = lane === 'dev-tool-sync';
  return Boolean(previous && current
    && /^[a-f0-9]{40}$/.test(head || '')
    && (devTool || lane === 'sync')
    && isDeepStrictEqual(previous, current)
    && Date.parse(current.lease_expires_at) > now
    // Maint52 does not emit an observation pair; its fresh REST/GraphQL PR
    // heads are checked by the caller. Never accept a conflicting observation.
    && (current.head_observed_sha
      ? current.head_observed_sha === head
      : devTool));
}

function confirmedClosedPrIdentity(closedResponse, selectedPr) {
  const closed = closedResponse?.data;
  return closed?.state === 'closed'
    && closed.head?.sha === selectedPr?.head?.sha
    && closed.head?.ref === selectedPr?.head?.ref;
}

function legacyStatusAsCheck(status = {}) {
  const state = String(status.state || '').toLowerCase();
  return {
    name: status.context,
    ...(typeof status.target_url === 'string' && status.target_url.trim()
      ? { details_url: status.target_url.trim() } : {}),
    status: state === 'pending' ? 'in_progress' : 'completed',
    conclusion:
      state === 'success'
        ? 'success'
        : state === 'pending'
          ? null
          : 'failure',
    // Reviewer settlement is anchored to review_started_at. Preserve the
    // legacy status timestamp so a reviewer status posted after that boundary
    // can satisfy the configured one-reviewer quorum.
    completed_at: status.updated_at || status.created_at || '',
    summary: status.description || '',
  };
}

function finiteNonNegative(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function normalizeReviewPolicy(policy = {}) {
  if (!policy || typeof policy !== 'object' || Array.isArray(policy)) {
    throw new Error('consumer sync review policy must be a JSON object');
  }
  return {
    ...policy,
    reviewers: Array.isArray(policy.reviewers) ? policy.reviewers : [],
    capacity_patterns: Array.isArray(policy.capacity_patterns) ? policy.capacity_patterns : [],
    non_response_patterns: Array.isArray(policy.non_response_patterns)
      ? policy.non_response_patterns
      : [],
    minimum_responses: finiteNonNegative(
      policy.minimum_responses,
      DEFAULT_REVIEW_POLICY.minimum_responses,
    ),
    quiet_period_minutes: finiteNonNegative(
      policy.quiet_period_minutes,
      DEFAULT_REVIEW_POLICY.quiet_period_minutes,
    ),
    maximum_wait_minutes: finiteNonNegative(
      policy.maximum_wait_minutes,
      DEFAULT_REVIEW_POLICY.maximum_wait_minutes,
    ),
  };
}

// Dispatch on the PR branch so workflow execution and check suites bind to its
// head. Gate resolves pr_number and rejects a head race before running checks.
async function requestSealedGate({ owner, repo, pr, withRetry }) {
  if (!pr.head?.ref) throw new Error('Gate dispatch requires the PR head ref');
  try {
    const response = await withRetry((client) => client.rest.actions.createWorkflowDispatch({
      owner,
      repo,
      workflow_id: 'pr-00-gate.yml',
      ref: pr.head.ref,
      inputs: { pr_number: String(pr.number) },
    }));
    return { mode: 'dispatch', status: response.status };
  } catch (error) {
    const status = error?.status || error?.response?.status;
    if (status !== 422 && status !== 404) throw error;
    console.log('consumer Gate predates pr_number input; falling back to label wakeup');
    await withRetry((client) => client.rest.issues.addLabels({
      owner, repo, issue_number: pr.number, labels: ['sync:delivery-ready'],
    }));
    return { mode: 'label-fallback', status };
  }
}

// This prepares the exact delivery for consumer CI; it is not a PASS or merge.
// Shared source review is not repeated on each generated copy.
async function prepareIntegrationDelivery({ pr, record, hold, seal, dryRun = false }) {
  const { parseDeliveryRecord } = require('./sync_pr_lease_contract.js');
  if (!['staging', 'reviewing'].includes(record?.delivery_state)
      || !/^[0-9a-f]{40}$/i.test(record?.source_commit || '')) {
    throw new Error('Integration delivery requires a bound source and staging record');
  }
  if (dryRun) return { body: pr.body, dryRun: true };
  const current = await hold();
  const fresh = parseDeliveryRecord(current?.body || '');
  if (current?.state !== 'open' || current.draft || current.auto_merge
      || current?.head?.sha !== pr.head.sha
      || fresh?.head_observed_sha !== pr.head.sha
      || fresh?.plan_id !== record.plan_id || fresh?.generation !== record.generation
      || fresh?.source_commit !== record.source_commit
      || fresh?.delivery_state !== record.delivery_state) {
    throw new Error('Delivery changed before integration checks');
  }
  return seal({ pr: current,
    record: { ...fresh, review_started_at: new Date().toISOString() },
    settlement: { ready: true, reason: 'integration_checks_required', responded: [], unavailable: [] } });
}

function reviewRequestMarker({ planId, generation, headSha, reviewerId }) {
  return `<!-- maint71-review-request:v1 ${JSON.stringify({
    plan_id: planId, generation, head_sha: headSha, reviewer: reviewerId,
  })} -->`;
}

// Only Maint 71 may request review on a generated delivery. Reconcile the
// exact-head marker before posting so a successful POST followed by a failed
// body update does not create a second request on the next pass.
async function ensureExactHeadReviewRequest({
  owner, repo, pr, record, reviewerProfiles, withRetry, dryRunMode = false,
  allowUnready = false,
}) {
  const profile = reviewerProfiles.find((item) =>
    String(item?.request_comment || '').trim());
  if (!profile) throw new Error('No configured generated-delivery review request');
  const { parseDeliveryRecord } = require('./sync_pr_lease_contract.js');
  const { data: writer } = await withRetry((client) => client.rest.users.getAuthenticated());
  const writerLogin = String(writer?.login || '').trim();
  if (!writerLogin || writerLogin === 'github-actions[bot]') {
    throw new Error('Review-request writer identity is unavailable or shared');
  }
  async function readRequestState() {
    const { data: fresh } = await withRetry((client) => client.rest.pulls.get({
      owner, repo, pull_number: pr.number,
    }));
    const freshRecord = parseDeliveryRecord(fresh?.body || '');
    if (
      fresh?.state !== 'open' || (!allowUnready && (fresh?.draft || fresh?.auto_merge))
      || fresh?.head?.sha !== pr.head.sha
      || freshRecord?.plan_id !== record.plan_id
      || freshRecord?.generation !== record.generation
      || freshRecord?.delivery_state !== record.delivery_state
      || freshRecord?.head_observed_sha !== pr.head.sha
    ) {
      throw new Error('Generated delivery changed before exact-head review request');
    }
    return fresh;
  }
  await readRequestState();
  const marker = reviewRequestMarker({
    planId: record.plan_id,
    generation: record.generation,
    headSha: pr.head.sha,
    reviewerId: profile.id,
  });
  for (let page = 1; page <= 20; page++) {
    const { data: comments } = await withRetry((client) =>
      client.rest.issues.listComments({
        owner, repo, issue_number: pr.number, per_page: 100, page,
      }));
    if (!Array.isArray(comments)) throw new Error('Incomplete review-request comments');
    const existing = comments.find((comment) =>
      comment?.user?.login === writerLogin
      && String(comment?.body || '').includes(marker)
      && String(comment?.body || '').split('\n')[0].trim() === profile.request_comment.trim());
    if (existing) {
      if (!existing.id || !Number.isFinite(Date.parse(existing.created_at || ''))) {
        throw new Error('Existing review request lacks durable identity or time');
      }
      const current = await readRequestState();
      return { id: existing.id, requestedAt: existing.created_at, reused: true,
        body: current.body, draft: Boolean(current.draft), autoMerge: Boolean(current.auto_merge) };
    }
    if (comments.length < 100) break;
    if (page === 20) throw new Error('Review-request comment inventory truncated');
  }
  if (dryRunMode) return null;
  const body = [
    String(profile.request_comment).trim(),
    `Maint 71 requests review of exact generated head ${pr.head.sha} for plan ${record.plan_id}.`,
    marker,
  ].join('\n\n');
  // Do not blindly retry an ambiguous POST. A later run reconciles its marker.
  const { data: posted } = await withRetry((client) =>
    client.rest.issues.createComment({
      owner, repo, issue_number: pr.number, body,
    }), { maxRetries: 0 });
  if (!posted?.id || !Number.isFinite(Date.parse(posted.created_at || ''))) {
    throw new Error('Review request posted without durable identity or time');
  }
  const current = await readRequestState();
  return { id: posted.id, requestedAt: posted.created_at, reused: false,
    body: current.body, draft: Boolean(current.draft), autoMerge: Boolean(current.auto_merge) };
}

const REASSESSMENT_SCHEMA = 'maint71-review-reassessment/v1';
const REASSESSMENT_FIELDS = [
  'schema', 'repository', 'pr', 'head_sha', 'thread_id', 'plan_id',
  'generation', 'source_commit', 'originating_reviewer',
];

function parseReviewReassessmentRequest(raw = '') {
  if (typeof raw !== 'string' || !raw.trim() || raw.length > 4096) {
    throw new Error('One bounded reviewer reassessment JSON object is required');
  }
  let request;
  try { request = JSON.parse(raw); } catch (_) {
    throw new Error('Reviewer reassessment input is not valid JSON');
  }
  if (!request || typeof request !== 'object' || Array.isArray(request)
    || Object.keys(request).filter((field) => field !== 'request_stage').sort().join(',')
      !== [...REASSESSMENT_FIELDS].sort().join(',')) {
    throw new Error('Reviewer reassessment input has missing or extra fields');
  }
  if (request.schema !== REASSESSMENT_SCHEMA
    || !/^stranske\/[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(request.repository)
    || !Number.isSafeInteger(request.pr) || request.pr <= 0
    || !/^[0-9a-f]{40}$/.test(request.head_sha)
    || !/^PRRT_[A-Za-z0-9_-]+$/.test(request.thread_id)
    || typeof request.plan_id !== 'string' || !request.plan_id.trim()
    || typeof request.generation !== 'string' || !request.generation.trim()
    || !/^[0-9a-f]{40}$/.test(request.source_commit)
    || typeof request.originating_reviewer !== 'string'
    || !/^[a-z][a-z0-9-]*$/.test(request.originating_reviewer)
    || (request.request_stage !== undefined
      && !['disposition', 'retry', 'conversation-disposition'].includes(request.request_stage))) {
    throw new Error('Reviewer reassessment input has invalid identity fields');
  }
  return request;
}

function reviewReassessmentMarker(request) {
  const canonical = Object.fromEntries(
    REASSESSMENT_FIELDS.map((field) => [field, request[field]]),
  );
  const kind = request.request_stage === 'retry' ? 'retry'
    : request.request_stage === 'disposition' ? 'disposition'
      : request.request_stage === 'conversation-disposition' ? 'conversation-disposition'
        : 'reassessment';
  return `<!-- maint71-review-${kind}:v1 ${JSON.stringify(canonical)} -->`;
}

function nativeConversationBinding(request, inlineRequest, origin, protocol = 'maint71-native-conversation-disposition/v1') {
  const requestId = String(inlineRequest?.fullDatabaseId || inlineRequest?.id || '');
  const requestUrl = String(inlineRequest?.html_url || inlineRequest?.url || '');
  const originId = String(origin?.fullDatabaseId || origin?.id || '');
  if (!/^[1-9][0-9]*$/.test(requestId) || !/^https:\/\/github\.com\//.test(requestUrl)
    || !/^[1-9][0-9]*$/.test(originId)) throw new Error('Native conversation disposition requires durable inline request and finding identities');
  if (!['maint71-native-conversation-disposition/v1', 'maint71-native-conversation-disposition/v2'].includes(protocol)) {
    throw new Error('Native conversation disposition has an unsupported protocol');
  }
  return { protocol, repository: request.repository, pr: request.pr,
    head_sha: request.head_sha, thread_id: request.thread_id, plan_id: request.plan_id, generation: request.generation,
    source_commit: request.source_commit, originating_reviewer: request.originating_reviewer, inline_request_id: requestId,
    inline_request_url: requestUrl, finding_id: originId, finding_sha256: require('crypto').createHash('sha256').update(String(origin?.body || '')).digest('hex') };
}
function nativeConversationMarker(binding) {
  const protocol = binding?.protocol === 'maint71-native-conversation-disposition/v2' ? 'v2' : 'v1';
  return `<!-- maint71-native-conversation-disposition:${protocol} ${require('crypto').createHash('sha256').update(JSON.stringify(binding)).digest('hex')} -->`;
}

function hasSubsequentExactHeadReviewerAnswer(thread, request, profiles, requestCreatedAt,
  reviewerProfileForLogin) {
  const requestedAt = Date.parse(requestCreatedAt || '');
  if (!Number.isFinite(requestedAt) || thread?.comments?.pageInfo?.hasNextPage
    || !Array.isArray(thread?.comments?.nodes)) return false;
  return thread.comments.nodes.some((item) =>
    reviewerProfileForLogin(item?.author?.login, profiles) === request.originating_reviewer
    && item?.commit?.oid === request.head_sha
    && Date.parse(item?.createdAt || '') > requestedAt
    && ((/^\s*(?:\*\*)?ACCEPT\b/i.test(String(item?.body || ''))
      && String(item?.body || '').includes(`<!-- sync-review-accepted:${request.head_sha} -->`))
      || /^\s*(?:\*\*)?REJECT\b/i.test(String(item?.body || ''))));
}

// A separate workflow job calls this function only for an explicit trusted
// repository_dispatch. It never enters the ordinary resolution/merge/cleanup run.
async function runReviewReassessment({
  context, withRetry, rawRequest, registeredRepos = [], policyPath,
}) {
  const fs = require('fs');
  const { generatedDeliveryLane, isStableSyncBranchName, isTrustedGeneratedDeliveryPr,
    reviewerProfileForLogin } = require('./sync_pr_merge_contract.js');
  const { parseDeliveryRecord } = require('./sync_pr_lease_contract.js');
  const request = parseReviewReassessmentRequest(rawRequest);
  if (context.eventName !== 'repository_dispatch'
    || context.payload?.action !== 'maint71-review-reassessment'
    || context.ref !== 'refs/heads/main'
    || !['stranske', 'stranske-automation-bot'].includes(context.actor)
    || !registeredRepos.includes(request.repository)
    || ['stranske/Collab-Admin', 'stranske/Collab-Deliverables'].includes(request.repository)) {
    throw new Error('Reviewer reassessment requires a trusted main-branch dispatch and registered repo');
  }
  const policy = JSON.parse(fs.readFileSync(policyPath, 'utf8'));
  const profiles = normalizeReviewPolicy(policy).reviewers;
  const profile = profiles.find((item) => item.id === request.originating_reviewer);
  const dispositionOnly = request.request_stage === 'disposition';
  const retryFailed = request.request_stage === 'retry';
  const nativeConversation = request.request_stage === 'conversation-disposition';
  const nativePolicy = profile?.conversation_disposition;
  const command = String((nativeConversation ? nativePolicy?.inline_comment : dispositionOnly ? profile?.disposition_comment
    : profile?.reassessment_comment) || '').trim();
  if (!profile || !/^@[A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+)*$/.test(command)
    || (nativeConversation && (!nativePolicy || !['maint71-native-conversation-disposition/v1', 'maint71-native-conversation-disposition/v2'].includes(nativePolicy.protocol) || !Array.isArray(nativePolicy.logins) || nativePolicy.logins.some((login) => !profile.logins?.includes(login)) || !/^@[A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+)*$/.test(String(nativePolicy.task_comment || ''))))) {
    throw new Error('Originating reviewer has no configured reassessment command');
  }
  const [owner, repo] = request.repository.split('/');
  const trustedWriters = new Set(['stranske', 'stranske-automation-bot']);
  async function readBoundState() {
    const { data: pr } = await withRetry((client) => client.rest.pulls.get({
      owner, repo, pull_number: request.pr,
    }));
    const record = parseDeliveryRecord(pr?.body || '');
    if (pr?.state !== 'open' || pr?.draft || pr?.auto_merge
      || pr?.head?.sha !== request.head_sha
      || !isTrustedGeneratedDeliveryPr(pr, [...trustedWriters])
      || (generatedDeliveryLane(pr?.head?.ref) !== 'dev-tool-sync'
        && !isStableSyncBranchName(pr?.head?.ref))
      || record?.repository !== request.repository
      || record?.plan_id !== request.plan_id
      || record?.generation !== request.generation
      || record?.source_commit !== request.source_commit
      || (record?.head_observed_sha && record.head_observed_sha !== request.head_sha)
      || !Number.isFinite(Date.parse(record?.lease_expires_at || ''))
      || Date.parse(record.lease_expires_at) <= Date.now()) {
      throw new Error('Generated delivery changed or lease is invalid');
    }
    const data = await withRetry((client) => client.graphql(
      `query($owner: String!, $repo: String!, $number: Int!) {
        repository(owner: $owner, name: $repo) {
          pullRequest(number: $number) {
            reviewThreads(first: 100) {
              pageInfo { hasNextPage }
              nodes {
                id isResolved isOutdated
                comments(first: 100) {
                  pageInfo { hasNextPage }
                  nodes { fullDatabaseId author { login } body createdAt url commit { oid } }
                }
              }
            }
          }
        }
      }`, { owner, repo, number: request.pr },
    ));
    const connection = data?.repository?.pullRequest?.reviewThreads;
    if (!hasCompleteReviewThreadEvidence(connection)) {
      throw new Error('Review-thread inventory is incomplete');
    }
    const thread = connection.nodes.find((item) => item.id === request.thread_id);
    if (!thread || thread.isResolved || thread.isOutdated
      || thread.comments?.pageInfo?.hasNextPage !== false
      || !Array.isArray(thread.comments?.nodes)
      || thread.comments.nodes.length === 0) {
      throw new Error('Requested active review thread is absent or incomplete');
    }
    const origin = thread.comments.nodes[0]?.author?.login;
    if (reviewerProfileForLogin(origin, profiles) !== request.originating_reviewer) {
      throw new Error('Review thread origin does not match requested reviewer');
    }
    return { pr, thread, threads: connection.nodes };
  }
  await readBoundState();
  const { data: writer } = await withRetry((client) => client.rest.users.getAuthenticated());
  if (!trustedWriters.has(String(writer?.login || ''))) {
    throw new Error('Reassessment writer identity is not trusted');
  }
  const marker = reviewReassessmentMarker(request);
  // Revalidate bindings and scan the same fresh snapshot before deciding to
  // POST; a trusted request may have appeared since the initial read.
  // GitHub's APIs are non-transactional, so an ambiguous POST is never retried.
  let current = await readBoundState();
  let found = null;
  for (const comment of current.thread.comments.nodes) {
    if (trustedWriters.has(comment?.author?.login)
      && String(comment?.body || '').includes(marker)) {
      if (found) throw new Error('Duplicate bound reviewer reassessment requests exist');
      found = { id: comment.fullDatabaseId, created_at: comment.createdAt,
        html_url: comment.url, user: comment.author };
    }
  }
  let comment = found;
  if (!comment) {
    if (retryFailed) {
      const priorMarker = reviewReassessmentMarker({ ...request, request_stage: undefined });
      const priors = current.thread.comments.nodes.filter((item) =>
        trustedWriters.has(item?.author?.login)
        && String(item?.body || '').includes(priorMarker));
      const failure = profile.reassessment_failure_summary;
      if (priors.length !== 1 || !Number.isFinite(Date.parse(priors[0]?.createdAt || ''))
        || !failure?.marker || !failure?.row_pattern) {
        throw new Error('Review retry requires one original request and configured terminal-failure proof');
      }
      let comments = await withRetry((client) => client.paginate(client.rest.issues.listComments,
        { owner, repo, issue_number: request.pr, per_page: 100 }));
      if (!Array.isArray(comments)) throw new Error('Review retry comment inventory is incomplete');
      const summaries = comments.filter((item) =>
        reviewerProfileForLogin(item?.user?.login, profiles) === request.originating_reviewer
        && String(item?.body || '').startsWith(failure.marker));
      if (summaries.length !== 1) throw new Error('Review retry requires one trusted terminal-failure summary');
      const rows = String(summaries[0].body).split('\n').map((line) => line.trim()).filter((line) =>
        line.startsWith('|') && !/^\|\s*(?:Review\s*\||---)/.test(line));
      const match = rows.length === 1 ? new RegExp(failure.row_pattern).exec(rows[0]) : null;
      const failedAt = Date.parse(match?.groups?.time || '');
      const ref = match?.groups?.head || '';
      if (!Number.isFinite(failedAt) || failedAt <= Date.parse(priors[0].createdAt)
        || failedAt > Date.now() || !/^[0-9a-f]{7,40}$/.test(ref)
        || !request.head_sha.startsWith(ref)
        || Date.parse(summaries[0].updated_at || '') < failedAt
        || !Number.isFinite(Date.parse(summaries[0].updated_at || ''))) {
        throw new Error('Review retry requires a subsequent exact-head terminal failure, not pending or completed review');
      }
      const { data: commit } = await withRetry((client) => client.rest.repos.getCommit({ owner, repo, ref }));
      if (commit?.sha !== request.head_sha) throw new Error('Review retry failure commit does not resolve to exact head');
      // External summary and commit lookups can outlive the inspected head or
      // a concurrent request. Re-read all bindings before the non-retryable POST.
      current = await readBoundState();
      // A provider can edit its top-level status during the commit lookup.
      // Refresh that evidence too; changed failure proof needs a new inspection.
      comments = await withRetry((client) => client.paginate(client.rest.issues.listComments,
        { owner, repo, issue_number: request.pr, per_page: 100 }));
      if (!Array.isArray(comments)) throw new Error('Review retry comment inventory is incomplete');
      const freshSummaries = comments.filter((item) =>
        reviewerProfileForLogin(item?.user?.login, profiles) === request.originating_reviewer
        && String(item?.body || '').startsWith(failure.marker));
      if (freshSummaries.length !== 1 || freshSummaries[0].body !== summaries[0].body
        || freshSummaries[0].updated_at !== summaries[0].updated_at) {
        throw new Error('Review retry terminal-failure proof changed during discovery');
      }
      current = await readBoundState();
      const freshPriors = current.thread.comments.nodes.filter((item) =>
        trustedWriters.has(item?.author?.login)
        && String(item?.body || '').includes(priorMarker));
      if (freshPriors.length !== 1
        || freshPriors[0].fullDatabaseId !== priors[0].fullDatabaseId
        || freshPriors[0].createdAt !== priors[0].createdAt) {
        throw new Error('Review retry original request changed during discovery');
      }
      if (current.threads.some((item) => item.comments?.pageInfo?.hasNextPage !== false
        || !Array.isArray(item.comments?.nodes))) {
        throw new Error('Review retry thread inventory is incomplete');
      }
      if (current.thread.comments.nodes.some((item) => trustedWriters.has(item?.author?.login)
        && String(item?.body || '').includes(marker))) {
        throw new Error('Review retry request appeared before POST; inspect durable marker and reuse');
      }
      const laterCompletion = (item, author, createdAt) =>
        reviewerProfileForLogin(author, profiles) === request.originating_reviewer
        && Date.parse(createdAt || '') > failedAt
        && ((profile.disposition_completion_prefixes || []).some((prefix) =>
          String(item?.body || '').startsWith(prefix))
          || /^\s*(?:\*\*)?(?:ACCEPT|REJECT)\b/i.test(String(item?.body || ''))
          || String(item?.body || '').trimStart().startsWith(`<!-- sync-review-accepted:${request.head_sha} -->`));
      if (current.threads.flatMap((item) => item.comments.nodes).some((item) =>
        item?.commit?.oid === request.head_sha
        && laterCompletion(item, item?.author?.login, item?.createdAt))
        || comments.some((item) => laterCompletion(item, item?.user?.login, item?.created_at))) {
        throw new Error('Review retry cannot repeat a subsequent completed originating review');
      }
    }
    if (dispositionOnly) {
      const priorMarker = reviewReassessmentMarker({ ...request, request_stage: undefined });
      const prior = current.thread.comments.nodes.find((item) =>
        trustedWriters.has(item?.author?.login)
        && String(item?.body || '').includes(priorMarker));
      if (current.threads.some((item) => item.comments?.pageInfo?.hasNextPage !== false
        || !Array.isArray(item.comments?.nodes))) {
        throw new Error('Review-thread inventory is incomplete');
      }
      const isCompletion = (item) =>
        reviewerProfileForLogin(item?.author?.login, profiles) === request.originating_reviewer
        && Date.parse(item?.createdAt || '') > Date.parse(prior?.createdAt || '')
        && (profile.disposition_completion_prefixes || []).some((prefix) =>
          String(item?.body || '').startsWith(prefix));
      let completed = current.threads.flatMap((item) => item.comments.nodes).some((item) =>
        isCompletion(item) && item?.commit?.oid === request.head_sha);
      if (prior && !completed) {
        const comments = await withRetry((client) => client.paginate(client.rest.issues.listComments,
          { owner, repo, issue_number: request.pr, per_page: 100 }));
        for (const item of comments) {
          if (!isCompletion({ ...item, author: item.user, createdAt: item.created_at })) continue;
          const prefix = String(profile.disposition_reviewed_commit_prefix || '');
          if (!prefix) continue;
          const line = String(item.body || '').split('\n').find((value) => value.startsWith(prefix));
          const ref = line?.slice(prefix.length).match(/`([0-9a-f]{10,40})`/)?.[1];
          if (!ref || !request.head_sha.startsWith(ref)) continue;
          const { data: commit } = await withRetry((client) => client.rest.repos.getCommit({
            owner, repo, ref,
          }));
          if (commit.sha === request.head_sha) { completed = true; break; }
        }
      }
      if (!prior || !completed) {
        throw new Error('Disposition task requires a completed originating review on this binding');
      }
    }
    const body = [`${command} on exact head ${request.head_sha}`,
      ...(retryFailed ? ['One bounded retry after the originating provider reported a verified terminal failure on this exact head. This is not acceptance and grants no resolution or merge authority.'] : []),
      ...(dispositionOnly ? ['This is a disposition-only task, not another general review. Answer the original finding with explicit ACCEPT or REJECT in this existing thread; do not create a separate finding thread.'] : []),
      ...(nativeConversation ? ['This is a native-conversation disposition request. A configured native conversation response may be used only when it supplies the exact protocol marker and exact acceptance token below; it grants no resolution or merge authority.'] : []),
      `Maint 71 requests ${request.originating_reviewer} to reassess active thread ` +
        `${request.thread_id} on exact generated head ${request.head_sha}. ` +
        `The thread remains merge-blocking until reviewer disposition.`,
      `If the finding is satisfied, reply in that active thread on this exact head with ` +
        `<!-- sync-review-accepted:${request.head_sha} -->; otherwise leave actionable feedback.`,
      `Original finding (untrusted review text): ${String(current.thread.comments.nodes[0].body || '').slice(0, 6000)}`,
      `Source validation is bound to Workflows commit ${request.source_commit}; inspect that fix and the exact generated head. Explicitly accept or reject in this thread. No unrelated edits, resolution or merge actions.`,
      marker].join('\n\n');
    const rawOriginId = current.thread.comments.nodes[0].fullDatabaseId;
    const originId = typeof rawOriginId === 'string' ? rawOriginId
      : Number.isSafeInteger(rawOriginId) ? String(rawOriginId) : '';
    if (!/^[1-9][0-9]*$/.test(originId) || BigInt(originId) > 18446744073709551615n) {
      throw new Error('Review thread lacks a verified original comment ID');
    }
    try {
      ({ data: comment } = await withRetry((client) => client.rest.pulls.createReplyForReviewComment({
        owner, repo, pull_number: request.pr, comment_id: originId, body,
      }), { maxRetries: 0 }));
    } catch (error) {
      throw new Error(`Reassessment POST uncertain; inspect exact marker before retry: ${error.message}`);
    }
  }
  if (!comment?.id || !Number.isFinite(Date.parse(comment.created_at || ''))
    || !String(comment.html_url || '').startsWith(
      `https://github.com/${request.repository}/pull/${request.pr}#discussion_r`)) {
    throw new Error('Reassessment request lacks durable URL, ID or timestamp');
  }
  let task = null;
  let taskReused = false;
  let taskSuppressed = false;
  const taskKind = nativeConversation ? 'native-conversation-disposition' : dispositionOnly ? 'disposition' : 'reassessment';
  const taskTransport = nativeConversation ? nativePolicy.task_transport : profile[`${taskKind}_task_transport`];
  const initialTask = !dispositionOnly && !retryFailed && !nativeConversation;
  if ((dispositionOnly || initialTask || nativeConversation) && taskTransport) {
    const taskCommand = String(nativeConversation ? nativePolicy.task_comment : profile[`${taskKind}_task_comment`] || '').trim();
    if (taskTransport !== 'pr-conversation'
      || !/^@[A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+)*$/.test(taskCommand)) {
      throw new Error(`Originating reviewer has no supported ${taskKind} task transport`);
    }
    const taskBinding = nativeConversation ? nativeConversationBinding(
      request, comment, current.thread.comments.nodes[0], nativePolicy.protocol,
    ) : {
      ...Object.fromEntries(REASSESSMENT_FIELDS.map((field) => [field, request[field]])),
      request_id: String(comment.id), request_url: comment.html_url,
    };
    // Keep the bot task command free of review-command text, including schema
    // strings and the inline acceptance token. Hash the complete canonical
    // binding; the existing inline request remains the readable authority.
    const taskDigest = require('crypto').createHash('sha256')
      .update(JSON.stringify(taskBinding)).digest('hex');
    const taskMarker = nativeConversation ? nativeConversationMarker(taskBinding) : `<!-- maint71-${taskKind}-task:v1 ${taskDigest} -->`;
    const findTask = async () => {
      const items = await withRetry((client) => client.paginate(client.rest.issues.listComments,
        { owner, repo, issue_number: request.pr, per_page: 100 }));
      if (!Array.isArray(items)) throw new Error(`${taskKind} task inventory is incomplete`);
      const matches = items.filter((item) => trustedWriters.has(item?.user?.login)
        && String(item?.body || '').includes(taskMarker));
      if (matches.length > 1) throw new Error(`Duplicate bound ${taskKind} task requests exist`);
      return matches[0] || null;
    };
    task = await findTask();
    if (!task) task = await findTask();
    taskReused = Boolean(task);
    const fresh = await readBoundState();
    const originalRequest = fresh.thread.comments.nodes.find((item) =>
      trustedWriters.has(item?.author?.login)
      && String(item?.body || '').includes(marker)
      && String(item.fullDatabaseId) === String(comment.id)
      && item.url === comment.html_url);
    if (!originalRequest) throw new Error(`Bound in-thread ${taskKind} request changed before task`);
    if (initialTask && hasSubsequentExactHeadReviewerAnswer(
      fresh.thread, request, profiles, comment.created_at || comment.createdAt, reviewerProfileForLogin,
    )) taskSuppressed = true;
    if (!task && !taskSuppressed) {
      const body = [`${taskCommand} on exact head ${request.head_sha}`,
        nativeConversation
          ? 'This is a bounded native-conversation disposition task. Do not inspect unrelated changes or start another general pass.'
          : dispositionOnly
          ? 'This is a bounded disposition-only cloud task. Do not inspect unrelated changes or start another general pass.'
          : 'This is a bounded finding-reassessment conversation task. Do not start another general review.',
        `Answer only the original finding in existing thread ${request.thread_id}: ${comment.html_url}`,
        `The authenticated in-thread request above is the authority and contains the exact finding. Inspect its source fix at Workflows commit ${request.source_commit} and generated head ${request.head_sha}.`,
        nativeConversation ? nativePolicy.protocol === 'maint71-native-conversation-disposition/v2'
          ? `An ordinary PR conversation reply is sufficient; an inline reply is not required. If the finding is satisfied, reply with a plain unquoted standalone line exactly equal to @${writer.login} (an exact backtick-wrapped @${writer.login} is also allowed), then ACCEPT, then <!-- sync-review-accepted:${request.head_sha} -->, then ${taskMarker}; these must be the first four visible nonempty answer lines after any automatic hidden/status wrapper, in that order with no intervening content. If the finding is not satisfied, reply with that exact @${writer.login} line followed by standalone REJECT and concrete evidence; do not include an acceptance token or protocol marker. Each required line is outside quoted text, code fences and details blocks; explanations may follow; it is valid only after this task and only under the configured native protocol.`
          : `Reply in this PR conversation with a plain unquoted standalone line exactly equal to ACCEPT or REJECT. For acceptance, after any automatic hidden/status wrapper, the first three visible nonempty answer lines must be exactly ACCEPT, then <!-- sync-review-accepted:${request.head_sha} -->, then ${taskMarker}, in that order with no intervening content. Each is its own plain line outside quoted text, code fences and details blocks; explanations may follow this three-line prefix; it is valid only after this task and only under the configured native protocol.` :
          'Reply in that existing thread with explicit ACCEPT and the exact acceptance token requested there if satisfied, or REJECT with concrete evidence if not. A top-level answer cannot authorize disposition.',
        'No file edits, branch pushes, new finding threads, thread resolution, seal, close or merge actions. If replying there is unsupported, report that limitation explicitly; do not substitute a generic no-issues summary.',
        taskMarker].join('\n\n');
      try {
        ({ data: task } = await withRetry((client) => client.rest.issues.createComment({
          owner, repo, issue_number: request.pr, body,
        }), { maxRetries: 0 }));
      } catch (error) {
        throw new Error(`${taskKind} task POST uncertain; inspect exact task marker before retry: ${error.message}`);
      }
    }
    if (!taskSuppressed && (!task?.id || !trustedWriters.has(task.user?.login)
      || !Number.isFinite(Date.parse(task.created_at || ''))
      || !String(task.html_url || '').startsWith(
        `https://github.com/${request.repository}/pull/${request.pr}#issuecomment-`))) {
      throw new Error(`${taskKind} task lacks durable URL, ID, timestamp or trusted author`);
    }
  }
  await readBoundState();
  return {
    ...request,
    status: found ? 'review_blocked_reassessment_reused' : 'review_blocked_reassessment_requested',
    request_id: comment.id,
    request_url: comment.html_url,
    requested_at: comment.created_at,
    writer: comment.user?.login || '',
    ...(task ? {
      task_status: taskReused ? `${taskKind}_task_reused` : `${taskKind}_task_requested`,
      task_id: task.id, task_url: task.html_url, task_requested_at: task.created_at,
    } : taskSuppressed ? { task_status: `${taskKind}_task_suppressed_reviewer_answered` } : {}),
  };
}

function parseReviewResolutionProofs(raw = '') {
  if (!String(raw || '').trim()) return [];
  let parsed;
  try {
    parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
  } catch (error) {
    throw new Error(`review resolution proof is not valid JSON: ${error.message}`);
  }
  const proofs = Array.isArray(parsed) ? parsed : parsed?.proofs;
  if (!Array.isArray(proofs)) {
    throw new Error('review resolution proof must be an array or contain proofs[]');
  }
  return proofs;
}

// A proof-bound resolution is safe for either a current or outdated thread.
// GitHub rulesets can still require an outdated conversation to be resolved,
// and the proof validation below binds this mutation to the exact PR head and
// a merged Workflows source fix. Ordinary merge eligibility remains stricter:
// it continues to require zero active non-outdated threads.
function isResolvableProofThread(thread) {
  return Boolean(
    thread
    && typeof thread === 'object'
    && thread.isResolved === false,
  );
}

function parseNoChangeEvidenceDocument(raw = '', {
  lane,
  requestedSyncHash,
  documentName,
  rowName,
  schema,
  acceptedEvidenceSources = [],
  expectedRepositories = [],
  expectedPlanId = '',
  expectedPlanScope = 'full',
  expectedScopeBaseSha = '',
  expectedSourceCommit = '',
  requireExactPlan = false,
} = {}) {
  const text = String(raw || '').trim();
  const evidenceByRepo = new Map();
  if (!text) return evidenceByRepo;
  if (requestedSyncHash !== lane) {
    throw new Error(`${documentName} is only valid for the ${lane} lane`);
  }
  if (requireExactPlan && (!expectedPlanId || !expectedSourceCommit)) {
    throw new Error(`${documentName} requires an exact expected plan and source commit`);
  }
  let document;
  try {
    document = JSON.parse(text);
  } catch (error) {
    throw new Error(`${documentName} is not valid JSON: ${error.message}`);
  }
  if (
    document?.schema !== schema
    || document?.version !== 1
    || !Array.isArray(document?.results)
  ) {
    throw new Error(`${documentName} has an unsupported schema`);
  }
  const expected = new Set(expectedRepositories);
  const sources = new Set(acceptedEvidenceSources);
  for (const row of document.results) {
    const repository = String(row?.repo || '').trim();
    const headSha = String(row?.head_sha || '').trim().toLowerCase();
    if (!expected.has(repository)) {
      throw new Error(`Unexpected ${rowName}: ${repository || '<missing-repo>'}`);
    }
    if (evidenceByRepo.has(repository)) {
      throw new Error(`Duplicate ${rowName}: ${repository}`);
    }
    const isNoChangeDelivery = row?.evidence_source === 'no-change-delivery';
    if (
      !sources.has(row?.evidence_source)
      || String(row?.plan_id || '').trim() !== expectedPlanId
      || (String(row?.plan_scope || '').trim() || 'full') !== expectedPlanScope
      || String(row?.scope_base_sha || '').trim().toLowerCase() !== expectedScopeBaseSha
      || String(row?.source_commit || '').trim().toLowerCase() !== expectedSourceCommit
      || !/^[0-9a-f]{40}$/.test(headSha)
      || row?.required_check_state !== (
        isNoChangeDelivery ? 'not-applicable' : 'success'
      )
      || Number(row?.active_review_thread_count) !== 0
      || (
        isNoChangeDelivery
        && row?.delivery_validation_state !== 'exact-tree-no-change'
      )
    ) {
      throw new Error(`Unsafe ${rowName}: ${repository}`);
    }
    evidenceByRepo.set(repository, { ...row, repo: repository, head_sha: headSha });
  }
  return evidenceByRepo;
}

function campaignNoChangeRequiresLiveGate(evidence = {}) {
  return evidence?.evidence_source !== 'no-change-delivery';
}

const MERGE_METHOD_DENIAL_PATTERNS = {
  merge: ['merge commits are not allowed', 'merge commit is not allowed'],
  squash: ['squash merges are not allowed', 'squash merge is not allowed'],
  rebase: ['rebase merges are not allowed', 'rebase merge is not allowed'],
};

function mergeMethodPolicyAllowsFallback(error, mergeMethod) {
  const message = String(error?.message || error || '').toLowerCase();
  const method = String(mergeMethod || '').toLowerCase();
  const patterns = MERGE_METHOD_DENIAL_PATTERNS[method] || [];
  if (patterns.some((pattern) => message.includes(pattern))) {
    return true;
  }
  if (message.includes('merge method is not allowed')) {
    return true;
  }
  return false;
}

function validateReviewResolutionProof(proof = {}, {
  owner,
  repo,
  prNumber,
  headSha,
  actor,
  trustedActors = [],
} = {}) {
  const errors = [];
  if (proof.schema !== 'workflows-sync-review-resolution/v1') errors.push('unsupported_schema');
  if (proof.repository !== `${owner}/${repo}`) errors.push('repository_mismatch');
  if (Number(proof.pr) !== Number(prNumber)) errors.push('pr_mismatch');
  if (String(proof.head_sha || '') !== String(headSha || '')) errors.push('head_mismatch');
  if (!String(proof.thread_id || '').startsWith('PRRT_')) errors.push('invalid_thread_id');
  if (!/^[0-9a-f]{40,64}$/i.test(String(proof.source_fix_sha || ''))) {
    errors.push('invalid_source_fix_sha');
  }
  if (!/^https:\/\/github\.com\/stranske\/Workflows\/(?:pull\/[1-9]\d*|commit\/[0-9a-f]{40,64})$/i.test(
    String(proof.evidence_url || ''),
  )) errors.push('invalid_evidence_url');
  if (!String(proof.originating_reviewer || '').trim()) errors.push('missing_originating_reviewer');
  const independent = proof.acceptance_mode === 'independent-verification';
  const nativeConversation = proof.acceptance_mode === 'native-conversation-disposition';
  if (proof.acceptance_mode && !independent && !nativeConversation) errors.push('unsupported_acceptance_mode');
  if (independent ? !/^https:\/\/github\.com\/stranske\/Workflows\/issues\/[1-9]\d*#issuecomment-[1-9]\d*$/.test(
    String(proof.reviewer_acceptance_url || ''),
  ) : nativeConversation ? !new RegExp(
    `^https://github\\.com/${owner}/${repo}/pull/${prNumber}#issuecomment-[1-9]\\d*$`,
  ).test(String(proof.reviewer_acceptance_url || '')) : !new RegExp(
    `^https://github\\.com/${owner}/${repo}/pull/${prNumber}#discussion_r[1-9]\\d*$`,
  ).test(String(proof.reviewer_acceptance_url || ''))) {
    errors.push('invalid_reviewer_acceptance_url');
  }
  if (!String(proof.reason || '').trim()) errors.push('missing_reason');
  if (!new Set(trustedActors).has(String(actor || ''))) errors.push('untrusted_dispatch_actor');
  return { ok: errors.length === 0, errors };
}

function hasExplicitSameHeadReviewerAcceptance(thread, proof, headSha, reviewerProfiles = []) {
  if (thread?.comments?.pageInfo?.hasNextPage) return false;
  const reviewer = reviewerProfiles.find(
    (profile) => profile.id === proof.originating_reviewer,
  );
  const allowedLogins = new Set(
    (reviewer?.logins || []).map((login) => String(login).toLowerCase()),
  );
  const originatingLogin = String(thread?.comments?.nodes?.[0]?.author?.login || '').toLowerCase();
  if (!allowedLogins.has(originatingLogin)) return false;
  const marker = `<!-- sync-review-accepted:${headSha} -->`;
  return (thread?.comments?.nodes || []).some((comment) =>
    comment.url === proof.reviewer_acceptance_url
    && allowedLogins.has(String(comment.author?.login || '').toLowerCase())
    && comment.commit?.oid === headSha
    && String(comment.body || '').includes(marker)
  );
}

function acceptanceCommentLocation(proof, consumer, source) {
  return proof?.acceptance_mode === 'native-conversation-disposition'
    ? { owner: consumer.owner, repo: consumer.repo }
    : { owner: source.owner, repo: source.repo };
}

function selectReconciliationTargets({
  eventName,
  requestedSyncHash,
  inputRepos,
  registeredRepos,
  expectedCanaryRepos,
  excludedRepos,
  manuallyReconcilableRepos,
}) {
  if (requestedSyncHash === 'candidate') {
    return expectedCanaryRepos;
  }
  if (inputRepos === 'all') {
    return registeredRepos;
  }
  const requestedRepos = inputRepos
    .split(',')
    .map((repo) => repo.trim())
    .filter(Boolean);
  const isExplicitManualDelivery =
    eventName === 'workflow_dispatch'
    && requestedSyncHash === 'delivery'
    && requestedRepos.length === 1
    && manuallyReconcilableRepos.has(requestedRepos[0]);
  return requestedRepos.filter(
    (repo) =>
      !excludedRepos.has(repo)
      || (isExplicitManualDelivery && manuallyReconcilableRepos.has(repo)),
  );
}

async function listMaint71PullRequests({ owner, repo, withRetry, includeClosed = false }) {
  const {
    SYNC_CANDIDATE_BRANCH,
    SYNC_DELIVERY_BRANCH,
  } = require('./sync_pr_merge_contract.js');
  // Open generated deliveries must be complete: omitting an older open stable
  // head can turn target_missing into a false terminal state or expose its live
  // branch to cleanup. Open inventories are normally one page, but correctness
  // cannot depend on that being true.
  const open = await withRetry((client) => client.paginate(
    client.rest.pulls.list,
    { owner, repo, state: 'open', per_page: 100 },
  ));
  if (!includeClosed) return { open, closed: [] };

  // Merged recovery needs only the reusable candidate and delivery heads. Query
  // those heads directly instead of paginating the repository's entire closed
  // PR history; the newest matching row is first and is sufficient.
  const closed = [];
  for (const branch of [SYNC_CANDIDATE_BRANCH, SYNC_DELIVERY_BRANCH]) {
    const response = await withRetry((client) => client.rest.pulls.list({
      owner,
      repo,
      state: 'closed',
      head: `${owner}:${branch}`,
      sort: 'updated',
      direction: 'desc',
      per_page: 1,
    }));
    if (response?.data?.[0]) closed.push(response.data[0]);
  }
  return { open, closed };
}

async function collectReviewerEvidence({
  owner,
  repo,
  number,
  reviewStartedAt,
  headSha = '',
  checkRuns = [],
  reviewerProfiles = [],
  reviewerCapacityPatterns = [],
  reviewerNonResponsePatterns = [],
  withRetry,
  core,
} = {}) {
  const {
    isReviewerCapacitySignal,
    isReviewerNonResponseSignal,
    reviewerProfileForLogin,
  } = require(
    './sync_pr_merge_contract.js'
  );
  const startedAt = new Date(reviewStartedAt || '').getTime();
  if (!Number.isFinite(startedAt)) {
    return { responded: [], unavailable: [], truncated: false };
  }
  let data;
  try {
    data = await withRetry((client) => client.graphql(
      `query($owner: String!, $repo: String!, $number: Int!) {
        repository(owner: $owner, name: $repo) {
          pullRequest(number: $number) {
            comments(first: 100) {
              pageInfo { hasNextPage }
              nodes { body createdAt author { login } }
            }
            reviews(first: 100) {
              pageInfo { hasNextPage }
              nodes { body submittedAt commit { oid } author { login } }
            }
            reviewThreads(first: 100) {
              pageInfo { hasNextPage }
              nodes {
                comments(first: 100) {
                  pageInfo { hasNextPage }
                  nodes { body createdAt commit { oid } author { login } }
                }
              }
            }
          }
        }
      }`,
      { owner, repo, number },
    ));
  } catch (error) {
    core.warning(
      `Unable to read reviewer evidence for ${owner}/${repo}#${number}: ${error}`,
    );
    return { responded: [], unavailable: [], truncated: true };
  }
  const pullRequest = data?.repository?.pullRequest;
  if (!pullRequest) {
    core.warning(`Reviewer evidence was missing for ${owner}/${repo}#${number}`);
    return { responded: [], unavailable: [], truncated: true };
  }
  const activities = [];
  for (const comment of pullRequest.comments?.nodes || []) {
    activities.push({ ...comment, at: comment.createdAt, kind: 'issue-comment' });
  }
  for (const review of pullRequest.reviews?.nodes || []) {
    activities.push({ ...review, at: review.submittedAt, kind: 'review' });
  }
  for (const thread of pullRequest.reviewThreads?.nodes || []) {
    for (const comment of thread.comments?.nodes || []) {
      activities.push({ ...comment, at: comment.createdAt, kind: 'review-comment' });
    }
  }
  const signals = new Map();
  const recordSignal = (reviewer, kind, at) => {
    const timestamp = new Date(at || '').getTime();
    if (!reviewer || !Number.isFinite(timestamp)) return;
    const current = signals.get(reviewer);
    if (
      !current
      || kind === 'responded'
      || (current.kind !== 'responded' && timestamp > current.at)
    ) {
      signals.set(reviewer, { kind, at: timestamp });
    }
  };
  for (const activity of activities) {
    const activityAt = new Date(activity.at || '').getTime();
    if (!Number.isFinite(activityAt) || activityAt < startedAt) continue;
    if (headSha && (
      activity.kind === 'issue-comment'
        ? !String(activity.body || '').includes(headSha)
        : activity.commit?.oid !== headSha
    )) continue;
    const reviewer = reviewerProfileForLogin(activity.author?.login, reviewerProfiles);
    if (!reviewer) continue;
    const unavailable = isReviewerCapacitySignal(activity.body, reviewerCapacityPatterns)
      || isReviewerNonResponseSignal(activity.body, reviewerNonResponsePatterns);
    recordSignal(reviewer, unavailable ? 'unavailable' : 'responded', activity.at);
  }
  for (const check of checkRuns) {
    const completedAt = new Date(
      check.completed_at || check.completedAt || check.started_at || check.startedAt || '',
    ).getTime();
    if (!Number.isFinite(completedAt) || completedAt < startedAt) continue;
    const name = String(check.name || '').trim();
    const profile = reviewerProfiles.find((item) =>
      (item.check_names || []).some((candidate) => candidate === name),
    );
    if (!profile) continue;
    const reviewer = String(profile.id || '').trim();
    const evidenceText = [
      check.summary,
      check.description,
      check.output?.title,
      check.output?.summary,
      check.output?.text,
    ].filter(Boolean).join('\n');
    const signalText = [check.name, evidenceText].filter(Boolean).join('\n');
    const unavailable = isReviewerCapacitySignal(signalText, reviewerCapacityPatterns)
      || isReviewerNonResponseSignal(signalText, reviewerNonResponsePatterns);
    if (unavailable) {
      recordSignal(reviewer, 'unavailable', new Date(completedAt).toISOString());
      continue;
    }
    const conclusion = String(check.conclusion || '').toLowerCase();
    const hasSubstantiveNegativeVerdict = [
      'failure',
      'action_required',
    ].includes(conclusion) && evidenceText.trim().length > 0;
    if (
      String(check.status || '').toLowerCase() === 'completed'
      && (
        ['success', 'neutral'].includes(conclusion)
        || hasSubstantiveNegativeVerdict
      )
    ) {
      recordSignal(reviewer, 'responded', new Date(completedAt).toISOString());
    }
  }
  const responded = [];
  const unavailable = [];
  for (const [reviewer, signal] of signals.entries()) {
    (signal.kind === 'responded' ? responded : unavailable).push(reviewer);
  }
  const completeConnection = (connection) =>
    Array.isArray(connection?.nodes)
    && connection?.pageInfo?.hasNextPage === false;
  const truncated = !(
    completeConnection(pullRequest.comments)
    && completeConnection(pullRequest.reviews)
    && completeConnection(pullRequest.reviewThreads)
    && pullRequest.reviewThreads.nodes.every((thread) =>
      completeConnection(thread?.comments))
  );
  return {
    responded: responded.filter(Boolean).sort(),
    unavailable: unavailable.filter(Boolean).sort(),
    truncated,
  };
}

function devToolBaseRefreshResult(deliveryContext) {
  if (deliveryContext?.delivery_lane !== 'dev-tool-sync') return null;
  return {
    ...deliveryContext,
    delivery_disposition: 'awaiting-base-refresh',
    blocker_owner: 'maint-52',
    next_command: 'dispatch-maint-52-scoped',
    status: 'dev_tool_base_refresh_required',
  };
}

// Promotion consumes only the exact-head evidence collected by run(). Keeping the
// builder and dispatch together makes the workflow's JSON boundary testable.
function buildCanaryPromotionEvidence(rows = [], expectedCanaries = []) {
  const { validateCanaryEvidence } = require('./sync_pr_merge_contract.js');
  const results = rows.map((row) => ({
    repo: row.repo,
    plan_id: row.plan_id,
    plan_scope: row.plan_scope || 'full',
    scope_base_sha: row.scope_base_sha || '',
    source_commit: row.source_commit,
    pr: row.pr,
    head_sha: row.head_sha,
    evidence_source: row.evidence_source,
    required_check_state: row.required_check_state,
    active_review_thread_count: row.active_review_thread_count,
  }));
  const errors = [];
  if (!expectedCanaries.length) errors.push('missing_canary_configuration');
  for (const row of results) {
    for (const key of ['repo', 'plan_id', 'source_commit', 'head_sha', 'evidence_source']) {
      if (!row[key]) errors.push(`missing_key:${key}:${row.repo || '<unknown>'}`);
    }
    // Match Maint 68's jq type check; String() coercion in the shared
    // validator must not authorize evidence that the receiving workflow rejects.
    if (typeof row.plan_id !== 'string') errors.push(`invalid_plan_id:${row.repo}`);
    if (!/^[0-9a-f]{40,64}$/i.test(row.source_commit || '')) {
      errors.push(`invalid_source_commit:${row.repo}`);
    }
    if (row.plan_scope === 'full' && row.scope_base_sha) {
      errors.push(`unexpected_scope_base_sha:${row.repo}`);
    }
  }
  if (new Set(results.map((row) => row.source_commit)).size !== 1) {
    errors.push('missing_or_mixed_source_commit');
  }
  const validation = validateCanaryEvidence(results, expectedCanaries);
  errors.push(...validation.errors);
  return {
    ok: errors.length === 0,
    errors,
    evidence: {
      schema: 'workflows.consumer-sync-canary-evidence/v1',
      version: 1,
      results,
    },
  };
}

async function listPromotionRuns({ withRetry, context, created }) {
  const runs = [];
  for (let page = 1; ; page++) {
    const { data } = await withRetry((client) => client.rest.actions.listWorkflowRuns({
      owner: context.repo.owner,
      repo: context.repo.repo,
      workflow_id: 'maint-68-sync-consumer-repos.yml',
      event: 'workflow_dispatch',
      ...(created ? { created: `>=${created}` } : {}),
      per_page: 100,
      page,
    }));
    if (!Array.isArray(data.workflow_runs)) throw new Error('promotion_history_unreadable');
    const batch = data.workflow_runs;
    runs.push(...batch);
    // GitHub caps filtered workflow-run searches at 1,000. Never silently
    // mistake a truncated history for a measured zero or authorize a replay.
    if (page === 10 && batch.length === 100) throw new Error('promotion_history_truncated');
    if (batch.length < 100) return runs;
  }
}

function promotionRunMatches(run, binding, defaultBranch = 'main') {
  return run.event === 'workflow_dispatch'
    && run.head_branch === defaultBranch
    && String(run.display_title || '').startsWith('Maint 68 promote ')
    && String(run.display_title).endsWith(` ${binding.plan_id} ${binding.source_commit}`);
}

async function dispatchCanaryPromotion({
  report, evidence, expectedCanaries, withRetry, context, core,
}) {
  const { candidatePromotionDecision } = require('./sync_pr_merge_contract.js');
  const built = buildCanaryPromotionEvidence(
    Array.isArray(evidence) ? evidence : evidence?.results || [], expectedCanaries,
  );
  // Current campaigns prepare sealed canaries before fleet commit. Older
  // campaigns may already have merged them; accept those only with the same
  // immutable identity as the freshly revalidated evidence.
  const normalizedReport = { ...report, results: (report.results || []).map((result) => {
    const row = built.evidence.results.find((item) => item.repo === `${result.owner}/${result.repo}`);
    return result.status === 'merged' && row && result.plan_id === row.plan_id
      && result.source_commit === row.source_commit && result.head_sha === row.head_sha
      && result.pr === row.pr
      ? { ...result, status: 'evidence_recovered' } : result;
  }) };
  const decision = candidatePromotionDecision({
    report: normalizedReport, evidence: built.evidence, expectedCanaries,
  });
  const errors = [...built.errors, ...decision.errors];
  if (report.inputs?.dry_run || report.inputs?.auto_merge !== true) errors.push('mutation_disabled');
  const record = async (status, detail) => {
    const message = `Canary promotion ${decision.plan_id || '<unbound>'}: ${status}; ${detail}`;
    core.notice(message);
    await core.summary.addRaw(`${message}\n`).write();
    return { status, plan_id: decision.plan_id, errors };
  };
  if (errors.length) return record('held', errors.join(', '));
  const binding = built.evidence.results[0];
  const branch = context.payload.repository?.default_branch || 'main';
  const { data: source } = await withRetry((client) => client.rest.repos.getCommit({
    owner: context.repo.owner, repo: context.repo.repo, ref: binding.source_commit,
  }));
  const created = source.commit?.committer?.date;
  if (!Number.isFinite(Date.parse(created))) throw new Error('promotion_source_date_unknown');
  const runs = await listPromotionRuns({ withRetry, context, created });
  const successful = runs.find((run) => run.status === 'completed' && run.conclusion === 'success'
    && promotionRunMatches(run, binding, branch));
  if (successful) return record('already-promoted', successful.html_url || `run ${successful.id}`);
  const planRuns = runs.filter((run) => promotionRunMatches(run, binding, branch));
  const active = planRuns.find((run) =>
    ['queued', 'in_progress', 'waiting', 'pending', 'requested'].includes(run.status)
  );
  if (active) return record('waiting', active.html_url || `active run ${active.id}`);
  // One initial dispatch plus at most two redispatches for this immutable plan.
  // Count distinct run IDs, not run_attempt: rerunning a run is not a dispatch.
  const attempts = new Set(planRuns.map((run) => run.id)).size;
  if (attempts >= 3) return record('retry-exhausted',
    `${attempts} dispatches; maximum 2 redispatches; owner repair required`);
  await withRetry((client) => client.rest.actions.createWorkflowDispatch({
    owner: context.repo.owner,
    repo: context.repo.repo,
    workflow_id: 'maint-68-sync-consumer-repos.yml',
    ref: branch,
    inputs: {
      phase: 'promote',
      delivery_scope: 'auto', // Maint 68's evidence-inferred scope value.
      canary_evidence_json: JSON.stringify(built.evidence),
      dry_run: 'false',
      force: 'false',
    },
  }));
  return record('dispatched', `source ${binding.source_commit}; completion awaits a successful Maint 68 run`);
}

function sealedPromotionHealth({ candidates = [], runs = [], now = Date.now(), defaultBranch = 'main' }) {
  const { parseDeliveryRecord } = require('./sync_pr_lease_contract.js');
  const plans = new Map();
  for (const pr of candidates) {
    const record = parseDeliveryRecord(pr.body);
    if (!record || record.delivery_state !== 'sealed') continue;
    const sealedAt = Date.parse(record.sealed_at);
    if (!Number.isFinite(sealedAt) || sealedAt > now) throw new Error('invalid_sealed_at');
    if (runs.some((run) => run.status === 'completed' && run.conclusion === 'success'
      && promotionRunMatches(run, record, defaultBranch))) continue;
    const key = `${record.plan_id}:${record.source_commit}`;
    const prior = plans.get(key);
    if (!prior || sealedAt < prior.sealedAt) plans.set(key, {
      plan_id: record.plan_id, source_commit: record.source_commit, sealedAt,
    });
  }
  const pending = [...plans.values()].sort((a, b) => a.sealedAt - b.sealedAt);
  const oldestHours = pending.length ? (now - pending[0].sealedAt) / 3600000 : 0;
  const exhausted = pending.filter((binding) =>
    new Set(runs.filter((run) => promotionRunMatches(run, binding, defaultBranch))
      .map((run) => run.id)).size >= 3);
  return {
    pending,
    retry_exhausted: exhausted,
    overdue: oldestHours > 48 || exhausted.length > 0,
    line: `plans sealed awaiting promotion: ${pending.length}, oldest: ${pending.length ? `${oldestHours.toFixed(1)} h` : 'n/a'}`
      + (exhausted.length ? `; promotion retry exhausted: ${exhausted.map((row) => row.plan_id).join(', ')} (maximum 2 redispatches)` : ''),
  };
}

// Publish an independent check: an overdue health verdict must not turn the
// recovery promotion itself red, which would prevent a successful receipt.
async function publishPromotionHealthCheck({ github, context, health }) {
  return github.rest.checks.create({
    owner: context.repo.owner,
    repo: context.repo.repo,
    name: 'health-71',
    head_sha: context.sha,
    status: 'completed',
    conclusion: health && !health.overdue && health.state !== 'unknown' ? 'success' : 'failure',
    external_id: `maint68-promotion-health:${context.runId}:${context.runAttempt || 1}`,
    details_url: `${context.serverUrl || 'https://github.com'}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`,
    output: {
      title: health?.line || 'plans sealed awaiting promotion: UNKNOWN',
      summary: health?.line || 'Promotion health could not be measured; inspect the Maint 68 summary.',
    },
  });
}

async function reportSealedPromotionHealth({ withRetry, context, core, expectedCanaries, now = Date.now() }) {
  const { parseDeliveryRecord } = require('./sync_pr_lease_contract.js');
  if (!expectedCanaries.length) throw new Error('missing_canary_configuration');
  const trusted = new Set(['stranske', 'stranske-automation-bot', 'github-actions[bot]']);
  const candidates = [];
  for (const repository of expectedCanaries) {
    // Enforce the owner exclusion before any API call, even if a future config drifts.
    if (repository.toLowerCase() === 'stranske/collab-admin') continue;
    const [owner, repo] = repository.split('/');
    const pulls = [];
    for (let page = 1; ; page++) {
      const { data } = await withRetry((client) => client.rest.pulls.list({
        owner, repo, state: 'all', head: `${owner}:sync/workflows-candidate`,
        sort: 'created', direction: 'desc', per_page: 100, page,
      }));
      if (!Array.isArray(data)) throw new Error('sealed_candidate_history_unreadable');
      pulls.push(...data);
      if (data.length < 100) break;
    }
    const owned = pulls.filter((pr) => trusted.has(pr.user?.login)
      && pr.head?.ref === 'sync/workflows-candidate');
    // Closed unmerged attempts are superseded; old merged generations must not
    // accumulate forever. Recover the latest merged candidate only without an
    // open successor, just as the reconciler does.
    const open = owned.filter((pr) => pr.state === 'open');
    const current = open.length ? open : owned.filter((pr) => pr.merged_at)
      .sort((a, b) => Date.parse(b.merged_at) - Date.parse(a.merged_at)).slice(0, 1);
    for (const pr of current) {
      const record = parseDeliveryRecord(pr.body);
      if (/"delivery_state"\s*:\s*"sealed"/.test(String(pr.body || '')) && !record) {
        throw new Error(`unreadable_sealed_delivery:${repository}#${pr.number}`);
      }
      if (record && record.repository !== repository) throw new Error('sealed_repository_mismatch');
      candidates.push(pr);
    }
  }
  const sources = [...new Set(candidates.map((pr) => parseDeliveryRecord(pr.body))
    .filter((record) => record?.delivery_state === 'sealed')
    .map((record) => record.source_commit))];
  // A reseal must not hide prior dispatches for the same immutable plan.
  const sourceDates = [];
  for (const sourceCommit of sources) {
    const { data } = await withRetry((client) => client.rest.repos.getCommit({
      owner: context.repo.owner, repo: context.repo.repo, ref: sourceCommit,
    }));
    const date = Date.parse(data.commit?.committer?.date);
    if (!Number.isFinite(date)) throw new Error('promotion_source_date_unknown');
    sourceDates.push(date);
  }
  const runs = sourceDates.length ? await listPromotionRuns({
    withRetry, context, created: new Date(Math.min(...sourceDates)).toISOString(),
  }) : [];
  const health = sealedPromotionHealth({
    candidates, runs, now, defaultBranch: context.payload.repository?.default_branch || 'main',
  });
  await core.summary.addRaw(`${health.line}\n${health.pending.map((plan) =>
    `- ${plan.plan_id} @ ${plan.source_commit}; sealed ${new Date(plan.sealedAt).toISOString()}`,
  ).join('\n')}\n`).write();
  core.setOutput('state', health.overdue ? 'overdue' : 'healthy');
  return health;
}

async function run({ github, context, core }) {
  const defaultOwner = context.repo.owner;
  const fs = require('fs');
  const path = require('path');
  // Sibling-relative paths: this module lives under .github/scripts/, so
  // require('./.github/scripts/...') would resolve to a nested non-existent path.
  const retryHelperPath = path.join(__dirname, 'github-api-with-retry.js');
  const {
    buildMarkdownSummary,
    buildMergeReport,
    classifyReviewBlockedDisposition,
    describeConsumerDeclaredContexts,
    hasCampaignCommitAuthorization,
    campaignAuthorizationAllowsMerge,
    campaignAuthorizationRowForRepository,
    candidateEvidenceAllowsMutation,
    classifyGeneratedPr,
    classifySyncPrChecks,
    commitSignatureAllowsMerge,
    collectDeletableSyncBranches,
    evaluatePostPushReviewWindow,
    evaluateReviewerSettlement,
    generatedDeliveryLane,
    generatedDeliveryRequiresVerifiedHead,
    generatedPrsForSyncSelector,
    isBlockingSyncSystemFailure,
    isManifestSyncedPath,
    isStableSyncBranchName,
    normalizeSyncHash,
    parseBooleanInput,
    parseManifestSyncedSources,
    parseManifestSyncedSourceEntries,
    parsePromotionEvidenceFromCommitMessage,
    requiresStrictGateBranchUpdate,
    requiredContextsFromRulesets,
    isTrustedGeneratedDeliveryPr,
    selectLatestMergedCandidatePr,
    selectLatestMergedSyncPr,
    selectMergeEligibleSyncPr,
    selectSyncPrGatingChecks,
    syncBranchForHash,
    syncSelectorForRepository,
    validateCanaryEvidence,
    validateExpectedCandidateIdentity,
    validateSourceDeltaEvidenceBinding,
  } = require('./sync_pr_merge_contract.js');
  let manifestSources = new Set();
  let manifestEntries = new Map();
  try {
    const manifestPath = path.join(__dirname, '..', 'sync-manifest.yml');
    const manifestText = fs.readFileSync(manifestPath, 'utf8');
    manifestSources = parseManifestSyncedSources(manifestText);
    manifestEntries = parseManifestSyncedSourceEntries(manifestText);
  } catch (error) {
    core.warning(`Unable to read sync manifest for review routing: ${error.message || error}`);
  }
  const {
    mergeEligibility,
    parseDeliveryRecord,
    replaceDeliveryRecord,
  } = require('./sync_pr_lease_contract.js');
  const {
    assertRuntimeAcMergeAllowed,
  } = require('./runtime_ac_merge_guard.js');
  // Support repository_dispatch (no inputs) with sensible defaults
  const inputRepos =
    process.env.REPOS_INPUT ||
    (context.payload.client_payload && context.payload.client_payload.repos) ||
    'all';
  const autoMerge = parseBooleanInput(
    process.env.AUTO_MERGE_INPUT ||
      (context.payload.client_payload && context.payload.client_payload.auto_merge),
    true,
  );
  const evidenceOnly = parseBooleanInput(process.env.EVIDENCE_ONLY_INPUT, false);
  const resolutionOnly = parseBooleanInput(process.env.RESOLUTION_ONLY_INPUT, false);
  const prepareOnly = parseBooleanInput(process.env.PREPARE_ONLY_INPUT, false);
  const candidateEvidenceAuthorized = parseBooleanInput(
    process.env.CANDIDATE_EVIDENCE_AUTHORIZED,
    process.env.CANDIDATE_EVIDENCE_RESULT === 'success'
      && process.env.CANDIDATE_ARTIFACT_RESULT === 'success',
  );
  const dryRun = resolutionOnly || evidenceOnly || parseBooleanInput(
    process.env.DRY_RUN_INPUT ||
      (context.payload.client_payload && context.payload.client_payload.dry_run),
    false,
  );
  const cleanupBranches = parseBooleanInput(
    process.env.CLEANUP_BRANCHES_INPUT ||
      (context.payload.client_payload && context.payload.client_payload.cleanup_branches),
    true,
  );
  let campaignCommitAuthorization = null;
  const rawCampaignAuthorization = String(
    process.env.CAMPAIGN_COMMIT_AUTHORIZATION_JSON || '',
  ).trim();
  if (rawCampaignAuthorization) {
    try {
      campaignCommitAuthorization = JSON.parse(rawCampaignAuthorization);
    } catch (error) {
      throw new Error(`Campaign commit authorization is not valid JSON: ${error.message}`);
    }
  }
  let reviewResolutionProofs = [];
  let reviewResolutionProofParseError = '';
  try {
    reviewResolutionProofs = parseReviewResolutionProofs(
      process.env.REVIEW_RESOLUTION_JSON || '',
    );
  } catch (error) {
    reviewResolutionProofParseError = error.message || String(error);
    core.warning(reviewResolutionProofParseError);
  }
  const trustedResolutionActors = String(
    process.env.TRUSTED_REVIEW_RESOLUTION_ACTORS || 'stranske,stranske-automation-bot',
  ).split(',').map((actor) => actor.trim()).filter(Boolean);
  const retryHelpers = fs.existsSync(retryHelperPath)
    ? require(retryHelperPath)
    : {
        // Call sites pass (client) => client.rest...; match that contract.
        withRetry: (fn) => fn(github),
        paginateWithRetry: (githubInstance, method, params) =>
          githubInstance.paginate(method, params),
      };
  if (!String(process.env.OWNER_PR_PAT || '').trim()) {
    throw new Error(
      'Maint 71 requires OWNER_PR_PAT for fail-closed cross-repository PR mutations',
    );
  }
  // The actions/github-script client is authenticated with OWNER_PR_PAT by
  // the workflow. Keep retries on that exact client so credential or quota
  // degradation cannot rotate a cross-repository mutation to a token with a
  // smaller repository installation scope.
  const withRetry = (fn, options = {}) => retryHelpers.withRetry(fn, {
    github,
    core,
    ...options,
  });
  // Review-thread and final exact-head reads can use a separate bot quota.
  // Keep all cross-repository mutations on the owner-pinned withRetry above.
  const reviewReadClient = typeof retryHelpers.createTokenAwareRetry === 'function'
    ? await retryHelpers.createTokenAwareRetry({
        github,
        core,
        env: process.env,
        capabilities: ['cross-repo', 'pulls:read'],
        preferredType: 'PAT',
        preferredSource: 'SERVICE_BOT_PAT',
        task: 'maint71-review-thread-read',
        rateResource: 'graphql',
      })
    : null;
  const withReviewReadRetry = reviewReadClient?.withRetry
    || ((fn) => withRetry(fn));
  const isPrimaryRateLimitExhausted = (error) =>
    typeof retryHelpers.isRateLimitError === 'function'
    && typeof retryHelpers.isSecondaryRateLimitError === 'function'
    && retryHelpers.isRateLimitError(error)
    && !retryHelpers.isSecondaryRateLimitError(error);
  const rethrowPrimaryRateLimit = (error) => {
    if (isPrimaryRateLimitExhausted(error)) throw error;
  };
  async function getRequiredContexts({ owner, repo, branch }) {
    try {
      const { data: protection } = await withRetry((client) =>
        client.rest.repos.getBranchProtection({
          owner,
          repo,
          branch,
        }),
      );
      const requiredStatusChecks = protection?.required_status_checks || {};
      const requiredContexts = new Set();
      for (const contextName of requiredStatusChecks.contexts || []) {
        const normalized = String(contextName || '').trim();
        if (normalized) {
          requiredContexts.add(normalized);
        }
      }
      for (const check of requiredStatusChecks.checks || []) {
        const normalized = String(check?.context || '').trim();
        if (normalized) {
          requiredContexts.add(normalized);
        }
      }
      if (requiredContexts.size > 0) {
        return { contexts: requiredContexts, source: 'branch-protection' };
      }
      console.log(
        `Legacy branch protection for ${owner}/${repo}@${branch} has no ` +
          'required checks; checking active repository and organization rulesets',
      );
    } catch (error) {
      const status = error?.status || error?.response?.status;
      if (status === 403 || status === 404) {
        console.log(
          `Branch protection unavailable for ${owner}/${repo}@${branch} ` +
            `(${status}); checking active repository and organization rulesets`,
        );
      } else {
        throw error;
      }
    }

    const { data: rulesetList } = await withRetry((client) =>
      client.rest.repos.getRepoRulesets({
        owner,
        repo,
        includes_parents: true,
      }),
    );
    const rulesets = [];
    for (const ruleset of rulesetList || []) {
      if (Array.isArray(ruleset?.rules) && ruleset?.conditions) {
        rulesets.push(ruleset);
        continue;
      }
      const { data: rulesetDetail } = await withRetry((client) =>
        client.rest.repos.getRepoRuleset({
          owner,
          repo,
          ruleset_id: ruleset.id,
        }),
      );
      rulesets.push(rulesetDetail);
    }
    const requiredContexts = requiredContextsFromRulesets(rulesets, branch);
    console.log(
      requiredContexts.size > 0
        ? `Ruleset required checks: ${[...requiredContexts].join(', ')}`
        : `No active ruleset requires status checks for ${owner}/${repo}@${branch}`,
    );
    return { contexts: requiredContexts, source: 'rulesets' };
  }

  async function classifyRequiredChecksForRef({
    owner,
    repo,
    branch,
    ref,
    enforceGeneratedDeliveryGate = false,
  }) {
    const { data: combinedStatus } = await withRetry((client) =>
      client.rest.repos.getCombinedStatusForRef({ owner, repo, ref }),
    );
    const paginatedCheckRuns = await withRetry((client) =>
      client.paginate(client.rest.checks.listForRef, {
        owner,
        repo,
        ref,
        per_page: 100,
      }),
    );
    const statusAsChecks = (combinedStatus.statuses || []).map(legacyStatusAsCheck);
    const checkNames = new Set(
      paginatedCheckRuns.map((check) => String(check?.name || '').trim()).filter(Boolean),
    );
    const allChecks = [
      ...paginatedCheckRuns,
      ...statusAsChecks.filter((status) => !checkNames.has(String(status.name || '').trim())),
    ];
    const requiredCheckPolicy = await getRequiredContexts({ owner, repo, branch });
    const requiredContexts = enforceGeneratedDeliveryGate
      ? enforceGeneratedDeliveryRequiredContexts(requiredCheckPolicy.contexts)
      : requiredCheckPolicy.contexts;
    // Only a generated delivery is gated on the consumer's own declaration;
    // no-change canary baselines keep the protection-only contract.
    const declared = enforceGeneratedDeliveryGate
      ? await readConsumerDeclaredContexts({ withRetry, owner, repo, branch })
      : { state: 'none', contexts: new Set(), error: '' };
    let classification = classifySyncPrChecks({
      checkRuns: allChecks,
      requiredContexts,
      declaredContexts: declared.contexts,
    });
    // A malformed declaration cannot establish an empty mandatory set.
    if (declared.state === 'unparseable' && classification.status === 'ready') {
      classification = { ...classification, status: 'checks_pending',
        pending: [{ name: '.github/config/required-contexts.json', status: 'unknown' }] };
    }
    if (classification.status === 'ready') {
      const seenNames = new Set(
        allChecks.map((check) => String(check?.name || '').trim()).filter(Boolean),
      );
      const missingRequired = [...requiredContexts].filter((ctx) => !seenNames.has(ctx));
      if (missingRequired.length > 0) {
        classification = {
          status: 'checks_pending',
          failed: [],
          pending: missingRequired.map((name) => ({ name, status: 'queued' })),
          declared_contexts: classification.declared_contexts,
        };
      }
    }
    if (enforceGeneratedDeliveryGate) {
      const declaredSummary = describeConsumerDeclaredContexts({ declared, classification });
      console.log(`${owner}/${repo}@${String(ref).slice(0, 12)}: ${declaredSummary}`);
      if (
        declared.state === 'unparseable'
        || (classification.declared_contexts?.never_started || []).length > 0
      ) {
        core.warning(`${owner}/${repo}: ${declaredSummary}`);
      }
    }
    return {
      allChecks,
      checkGateMode: requiredCheckPolicy.source,
      classification,
      declaredContexts: declared,
      gatingChecks: requiredContexts.size > 0
        ? selectSyncPrGatingChecks({ checkRuns: allChecks, requiredContexts })
        : [],
      requiredContexts,
    };
  }

  async function resolveProvenReviewDebt({ owner, repo, pr, deliveryRecord }) {
    const matching = reviewResolutionProofs.filter((proof) =>
      proof?.repository === `${owner}/${repo}`
      && Number(proof?.pr) === Number(pr.number),
    );
    const resolved = [];
    const wouldResolve = [];
    const errors = reviewResolutionProofParseError
      ? [`payload:${reviewResolutionProofParseError}`]
      : [];
    for (const proof of matching) {
      const validation = validateReviewResolutionProof(proof, {
        owner,
        repo,
        prNumber: pr.number,
        headSha: pr.head.sha,
        actor: context.actor,
        trustedActors: trustedResolutionActors,
      });
      if (!validation.ok) {
        errors.push(`${proof.thread_id || '<missing-thread>'}:${validation.errors.join(',')}`);
        continue;
      }
      const sourceCommit = String(deliveryRecord?.source_commit || '');
      if (!/^[0-9a-f]{40,64}$/i.test(sourceCommit)) {
        errors.push(`${proof.thread_id}:delivery_source_commit_missing`);
        continue;
      }
      try {
        const evidenceUrl = String(proof.evidence_url || '');
        const commitEvidence = evidenceUrl.match(
          /^https:\/\/github\.com\/stranske\/Workflows\/commit\/([0-9a-f]{40,64})$/i,
        );
        const pullEvidence = evidenceUrl.match(
          /^https:\/\/github\.com\/stranske\/Workflows\/pull\/([1-9]\d*)$/,
        );
        if (commitEvidence) {
          if (commitEvidence[1].toLowerCase() !== String(proof.source_fix_sha).toLowerCase()) {
            errors.push(`${proof.thread_id}:evidence_commit_mismatch`);
            continue;
          }
          await withRetry((client) => client.rest.repos.getCommit({
            owner: context.repo.owner,
            repo: context.repo.repo,
            ref: proof.source_fix_sha,
          }));
        } else if (pullEvidence) {
          const pullNumber = Number(pullEvidence[1]);
          const { data: sourcePull } = await withRetry((client) => client.rest.pulls.get({
            owner: context.repo.owner,
            repo: context.repo.repo,
            pull_number: pullNumber,
          }));
          if (!sourcePull?.merged_at) {
            errors.push(`${proof.thread_id}:evidence_pr_not_merged`);
            continue;
          }
          const sourceCommits = await withRetry((client) => client.paginate(
            client.rest.pulls.listCommits,
            {
              owner: context.repo.owner,
              repo: context.repo.repo,
              pull_number: pullNumber,
              per_page: 100,
            },
          ));
          const evidenceShas = new Set([
            sourcePull.merge_commit_sha,
            ...(sourceCommits || []).map((commit) => commit.sha),
          ].map((sha) => String(sha || '').toLowerCase()).filter(Boolean));
          if (!evidenceShas.has(String(proof.source_fix_sha).toLowerCase())) {
            errors.push(`${proof.thread_id}:source_fix_not_in_evidence_pr`);
            continue;
          }
        } else {
          errors.push(`${proof.thread_id}:invalid_evidence_url`);
          continue;
        }
        const { data: comparison } = await withRetry((client) =>
          client.rest.repos.compareCommitsWithBasehead({
            owner: context.repo.owner,
            repo: context.repo.repo,
            basehead: `${proof.source_fix_sha}...${sourceCommit}`,
          }),
        );
        if (!['ahead', 'identical'].includes(String(comparison?.status || ''))) {
          errors.push(`${proof.thread_id}:source_fix_not_in_delivery_source`);
          continue;
        }
        const fresh = await collectFindingReviewState({
          owner, repo, number: pr.number, read: withReviewReadRetry,
        });
        const threads = fresh?.reviewThreads;
        if (fresh?.headRefOid !== pr.head.sha || fresh?.headRefName !== pr.head.ref) {
          errors.push(`${proof.thread_id}:head_changed`);
          continue;
        }
        if (threads?.pageInfo?.hasNextPage) {
          errors.push(`${proof.thread_id}:review_thread_page_truncated`);
          continue;
        }
        const thread = (threads?.nodes || []).find((item) => item.id === proof.thread_id);
        if (!isResolvableProofThread(thread)) {
          errors.push(`${proof.thread_id}:thread_not_resolvable`);
          continue;
        }
        let accepted = hasExplicitSameHeadReviewerAcceptance(thread, proof, pr.head.sha, reviewerProfiles);
        if (proof.acceptance_mode === 'independent-verification' || proof.acceptance_mode === 'native-conversation-disposition') {
          const commentId = proof.reviewer_acceptance_url.split('#issuecomment-')[1];
          const commentLocation = acceptanceCommentLocation(proof, { owner, repo }, context.repo);
          const { data: comment } = await withRetry((client) => client.rest.issues.getComment({
            ...commentLocation, comment_id: commentId,
          }));
          const topLevelComments = await collectOriginatingCompletions({
            owner, repo, number: pr.number, head: pr.head.sha,
            profiles: reviewerProfiles, read: withRetry,
            includeAuthors: proof.acceptance_mode === 'native-conversation-disposition' ? reviewPolicy.finding_verification_fallback?.trusted_publishers || [] : [],
          });
          const verification = proof.acceptance_mode === 'independent-verification' ? validateIndependentFindingVerification({
            proof, record: deliveryRecord, thread, threads, comment,
            policy: reviewPolicy, reviewerProfiles, topLevelComments,
          }) : validateNativeConversationDisposition({ proof, record: deliveryRecord, thread, threads, comment, policy: reviewPolicy, reviewerProfiles, topLevelComments });
          accepted = verification.ok;
          if (!accepted) {
            errors.push(`${proof.thread_id}:${verification.reason}`);
            continue;
          }
          // Re-read immediately after external evidence; never resolve a changed head.
          const { data: currentPr } = await withRetry((client) => client.rest.pulls.get({
            owner, repo, pull_number: pr.number,
          }));
          const currentRecord = parseDeliveryRecord(currentPr.body || '');
          if (currentPr.state !== 'open' || currentPr.head?.sha !== pr.head.sha
            || currentPr.head?.ref !== pr.head.ref
            || !independentVerificationDeliveryUnchanged({
              previous: deliveryRecord, current: currentRecord,
              head: pr.head.sha, branch: pr.head.ref, now: Date.now(),
            })) {
            errors.push(`${proof.thread_id}:head_changed`);
            continue;
          }
          const latest = await collectFindingReviewState({
            owner, repo, number: pr.number, read: withReviewReadRetry,
          });
          const latestCompletions = await collectOriginatingCompletions({
            owner, repo, number: pr.number, head: pr.head.sha,
            profiles: reviewerProfiles, read: withRetry,
            includeAuthors: proof.acceptance_mode === 'native-conversation-disposition' ? reviewPolicy.finding_verification_fallback?.trusted_publishers || [] : [],
          });
          const { data: latestComment } = await withRetry((client) => client.rest.issues.getComment({
            ...commentLocation, comment_id: commentId,
          }));
          const latestRecord = parseDeliveryRecord(latest?.body || '');
          const latestThread = latest?.reviewThreads?.nodes?.find((item) => item.id === proof.thread_id);
          const finalVerification = proof.acceptance_mode === 'independent-verification' ? validateIndependentFindingVerification({
            proof, record: latestRecord, thread: latestThread, threads: latest?.reviewThreads,
            comment: latestComment, policy: reviewPolicy, reviewerProfiles, topLevelComments: latestCompletions,
          }) : validateNativeConversationDisposition({ proof, record: latestRecord, thread: latestThread, threads: latest?.reviewThreads, comment: latestComment, policy: reviewPolicy, reviewerProfiles, topLevelComments: latestCompletions });
          if (latest?.headRefOid !== pr.head.sha || !finalVerification.ok
            || latest?.headRefName !== pr.head.ref
            || !independentVerificationDeliveryUnchanged({
              previous: currentRecord, current: latestRecord,
              head: pr.head.sha, branch: latest.headRefName, now: Date.now(),
            })) {
            errors.push(`${proof.thread_id}:verification_changed_before_resolution`);
            continue;
          }
        }
        if (!accepted) {
          errors.push(`${proof.thread_id}:same_head_reviewer_acceptance_missing`);
          continue;
        }
        if (dryRun && !resolutionOnly) {
          wouldResolve.push(proof.thread_id);
          console.log(
            `Would resolve proof-bound review thread ${proof.thread_id} using ` +
              `${proof.evidence_url}`,
          );
          continue;
        }
        await withRetry((client) => client.graphql(
          `mutation($threadId: ID!) {
            resolveReviewThread(input: {threadId: $threadId}) {
              thread { id isResolved }
            }
          }`,
          { threadId: proof.thread_id },
        ));
        resolved.push(proof.thread_id);
        console.log(
          `Resolved proof-bound review thread ${proof.thread_id} using ${proof.evidence_url}`,
        );
      } catch (error) {
        errors.push(`${proof.thread_id}:${error.message || error}`);
      }
    }
    return { resolved, wouldResolve, errors };
  }
  
  // Parse repos from previous step
  const excludedRepos = new Set(
    String(process.env.EXCLUDED_REPOS_INPUT || 'stranske/Collab-Admin')
      .split(',')
      .map((repo) => repo.trim())
      .filter(Boolean),
  );
  const manuallyReconcilableRepos = new Set(
    String(process.env.MANUAL_RECONCILIATION_REPOS_INPUT || '')
      .split(',')
      .map((repo) => repo.trim())
      .filter(Boolean),
  );
  const registeredRepos = String(process.env.REGISTERED_REPOS_INPUT || '')
    .split(',')
    .map(r => r.trim())
    .filter((repo) => repo && !excludedRepos.has(repo));
  
  const requestedSyncHash = normalizeSyncHash(
    process.env.ACTIVE_SYNC_HASH_INPUT ||
      process.env.SYNC_HASH_INPUT ||
      (context.payload.client_payload && context.payload.client_payload.active_sync_hash) ||
      (context.payload.client_payload && context.payload.client_payload.sync_hash) ||
    '',
  );
  const expectedPlanId = String(process.env.EXPECTED_PLAN_ID_INPUT || '').trim();
  const expectedPlanScope = String(process.env.EXPECTED_PLAN_SCOPE_INPUT || '').trim() || 'full';
  const expectedScopeBaseSha = String(
    process.env.EXPECTED_SCOPE_BASE_SHA_INPUT || '',
  ).trim().toLowerCase();
  const expectedSourceCommit = String(
    process.env.EXPECTED_SOURCE_COMMIT_INPUT || '',
  ).trim().toLowerCase();
  if (
    ['candidate', 'campaign'].includes(requestedSyncHash)
    && (!expectedPlanId || !expectedSourceCommit)
  ) {
    throw new Error(
      'Candidate/campaign reconciliation requires an exact expected plan and source commit',
    );
  }
  const trustedSyncActors = String(process.env.TRUSTED_SYNC_ACTORS || '')
    .split(',')
    .map((actor) => actor.trim())
    .filter(Boolean);
  const reviewPolicyPath = process.env.CONSUMER_SYNC_REVIEW_POLICY_PATH ||
    path.join(__dirname, '../../config/consumer_sync_review_policy.json');
  let reviewPolicy;
  let reviewPolicyLoaded = true;
  try {
    reviewPolicy = normalizeReviewPolicy(
      JSON.parse(fs.readFileSync(reviewPolicyPath, 'utf8')),
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    core.warning(`Unable to load consumer sync review policy at ${reviewPolicyPath}: ${message}`);
    reviewPolicy = normalizeReviewPolicy({});
    reviewPolicyLoaded = false;
  }
  const integrationOnly = reviewPolicyLoaded && reviewPolicy.generated_delivery_review === 'integration-only';
  const reviewerProfiles = Array.isArray(reviewPolicy.reviewers) ? reviewPolicy.reviewers : [];
  const configuredReviewers = reviewerProfiles
    .map((profile) => String(profile?.id || '').trim())
    .filter(Boolean);
  const minimumReviewerResponses = Number(reviewPolicy.minimum_responses ?? 1);
  const reviewerQuietPeriodMs = Number(reviewPolicy.quiet_period_minutes ?? 7) * 60 * 1000;
  const reviewerMaximumWaitMs = Number(reviewPolicy.maximum_wait_minutes ?? 15) * 60 * 1000;
  const reviewerCapacityPatterns = Array.isArray(reviewPolicy.capacity_patterns)
    ? reviewPolicy.capacity_patterns
    : [];
  const reviewerNonResponsePatterns = Array.isArray(reviewPolicy.non_response_patterns)
    ? reviewPolicy.non_response_patterns
    : [];

  let expectedCanaryRepos = [];
  {
    const canaryConfigPath = process.env.CONSUMER_SYNC_CANARIES_PATH ||
      path.join(__dirname, '../../config/consumer_sync_canaries.json');
    const canaryConfig = JSON.parse(
      fs.readFileSync(canaryConfigPath, 'utf8'),
    );
    expectedCanaryRepos = (canaryConfig.canaries || [])
      .map((entry) => String(entry?.repo || '').trim())
      .filter((repo) => repo && !excludedRepos.has(repo));
  }

  const rawBaselineEvidence = String(
    process.env.CANARY_BASELINE_EVIDENCE_JSON || '',
  ).trim();
  const baselineEvidenceByRepo = parseNoChangeEvidenceDocument(
    requestedSyncHash === 'candidate' ? rawBaselineEvidence : '',
    {
      lane: 'candidate',
      requestedSyncHash,
      documentName: 'No-change canary evidence',
      rowName: 'no-change canary evidence',
      schema: 'workflows.consumer-sync-canary-evidence/v1',
      acceptedEvidenceSources: ['no-change-canary'],
      expectedRepositories: expectedCanaryRepos,
      expectedPlanId,
      expectedPlanScope,
      expectedScopeBaseSha,
      expectedSourceCommit,
      requireExactPlan: true,
    },
  );
  const rawCampaignNoChangeEvidence = String(
    process.env.CAMPAIGN_NO_CHANGE_EVIDENCE_JSON || '',
  ).trim();
  const campaignNoChangeEvidenceByRepo = parseNoChangeEvidenceDocument(
    requestedSyncHash === 'campaign' ? rawCampaignNoChangeEvidence : '',
    {
      lane: 'campaign',
      requestedSyncHash,
      documentName: 'Campaign no-change evidence',
      rowName: 'campaign no-change evidence',
      schema: 'workflows.consumer-sync-no-change-evidence/v1',
      acceptedEvidenceSources: ['no-change-canary', 'no-change-delivery'],
      expectedRepositories: registeredRepos,
      expectedPlanId,
      expectedPlanScope,
      expectedScopeBaseSha,
      expectedSourceCommit,
    },
  );

  // Candidate reconciliation is a registry-owned operation. Processing the
  // complete consumer registry here lets unrelated non-canary delivery PRs
  // create target_missing failures and can make promotion evidence unusable.
  // Always derive this target set from the canonical canary registry.
  const targetRepos = selectReconciliationTargets({
    eventName: context.eventName,
    requestedSyncHash,
    inputRepos,
    registeredRepos,
    expectedCanaryRepos,
    excludedRepos,
    manuallyReconcilableRepos,
  });
  
  console.log(`Registered consumer repos: ${registeredRepos.join(', ')}`);
  console.log(`Processing repos: ${targetRepos.join(', ')}`);
  console.log(`Auto-merge: ${autoMerge}, Dry run: ${dryRun}`);
  console.log(`Evidence only: ${evidenceOnly}`);
  console.log(`Prepare only: ${prepareOnly}`);
  console.log(`Resolution only: ${resolutionOnly}`);
  console.log(`Candidate evidence authorized: ${candidateEvidenceAuthorized}`);
  console.log(
    `Reviewer policy: minimum=${minimumReviewerResponses}, ` +
      `quiet=${reviewerQuietPeriodMs / 60000}m, max=${reviewerMaximumWaitMs / 60000}m`,
  );
  console.log(`Cleanup stale sync branches: ${cleanupBranches}\n`);
  if (requestedSyncHash) {
    console.log(`Target sync hash: ${requestedSyncHash}`);
  }
  if (expectedPlanId) {
    console.log(`Expected plan identity: ${expectedPlanId} @ ${expectedSourceCommit}`);
  }
  
  const results = [];
  const canaryEvidence = [];
  const stableCanaries = [];
  
  function syncMetadata(pr) {
    const match = String(pr.body || '').match(
      /<!-- workflows-consumer-sync:v1 ([\s\S]*?) -->/,
    );
    if (!match) return null;
    try {
      return JSON.parse(match[1]);
    } catch (_) {
      return null;
    }
  }
  
  async function activeReviewThreadCount(owner, repo, number) {
    const details = await fetchActiveReviewThreads(owner, repo, number);
    return details.count;
  }

  async function fetchActiveReviewThreads(owner, repo, number) {
    try {
      const data = await withReviewReadRetry((client) => client.graphql(
        `query($owner: String!, $repo: String!, $number: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $number) {
              reviewThreads(first: 100) {
                pageInfo { hasNextPage }
                nodes {
                  id
                  path
                  isResolved
                  isOutdated
                  comments(first: 10) {
                    nodes {
                      path
                      url
                      author { login }
                    }
                  }
                }
              }
            }
          }
        }`,
        { owner, repo, number },
      ));
      const reviewThreads = data?.repository?.pullRequest?.reviewThreads;
      if (!hasCompleteReviewThreadEvidence(reviewThreads)) {
        core.warning(`Incomplete review-thread evidence for ${owner}/${repo}#${number}`);
        return { count: -1, threads: [] };
      }
      const threads = (reviewThreads.nodes || []).filter(
        (thread) => !thread.isResolved && !thread.isOutdated,
      );
      return { count: threads.length, threads };
    } catch (error) {
      core.warning(`Unable to read active review threads for ${owner}/${repo}#${number}: ${error}`);
      return { count: -1, threads: [] };
    }
  }

  async function holdReadyStableDelivery({ owner, repo, pr, expectedRecord }) {
    const assertObservedDelivery = (current) => {
      if (!expectedRecord) return;
      const observed = parseDeliveryRecord(current?.body || '');
      if (
        current?.state !== 'open' || current?.head?.sha !== pr.head.sha
        || observed?.plan_id !== expectedRecord.plan_id
        || observed?.generation !== expectedRecord.generation
        || observed?.head_observed_sha !== pr.head.sha
        || observed?.delivery_state !== expectedRecord.delivery_state
      ) {
        throw new Error('Generated delivery changed before ready hold');
      }
    };
    let { data: current } = await withRetry((client) => client.rest.pulls.get({
      owner,
      repo,
      pull_number: pr.number,
    }));
    assertObservedDelivery(current);
    if (current.auto_merge) {
      await withRetry((client) => client.graphql(
        `mutation($id: ID!) {
          disablePullRequestAutoMerge(input: {pullRequestId: $id}) {
            pullRequest { id autoMergeRequest { enabledAt } }
          }
        }`,
        { id: current.node_id },
      ));
    }
    if (current.draft) {
      await withRetry((client) => client.graphql(
        `mutation($id: ID!) {
          markPullRequestReadyForReview(input: {pullRequestId: $id}) {
            pullRequest { id isDraft }
          }
        }`,
        { id: current.node_id },
      ));
    }
    ({ data: current } = await withRetry((client) => client.rest.pulls.get({
      owner,
      repo,
      pull_number: pr.number,
    })));
    assertObservedDelivery(current);
    if (current.auto_merge) {
      throw new Error(`Auto-merge remains enabled for staged delivery PR #${pr.number}.`);
    }
    if (current.draft) {
      throw new Error(`Staged delivery PR #${pr.number} remains draft.`);
    }
    return current;
  }

  async function beginStableDeliveryReview({ owner, repo, pr, record, dryRunMode }) {
    if (dryRunMode) {
      return { reviewStartedAt: record.review_started_at || new Date().toISOString(), dryRun: true };
    }
    await holdReadyStableDelivery({ owner, repo, pr, expectedRecord: record });
    const request = await ensureExactHeadReviewRequest({
      owner, repo, pr, record, reviewerProfiles,
      withRetry,
    });
    const reviewStartedAt = request.requestedAt;
    await withRetry((client) => client.rest.issues.addLabels({
      owner,
      repo,
      issue_number: pr.number,
      labels: ['sync:delivery-staging'],
    }));
    // A previous generation can leave this label behind. Clear it while the
    // staging hold is active. This is lifecycle metadata; Gate wakeups use an
    // explicit workflow dispatch after sealing, with a legacy label fallback.
    try {
      await withRetry((client) => client.rest.issues.removeLabel({
        owner,
        repo,
        issue_number: pr.number,
        name: 'sync:delivery-ready',
      }));
    } catch (labelError) {
      if (labelError?.status !== 404) throw labelError;
    }
    const { data: latest } = await withRetry((client) => client.rest.pulls.get({
      owner, repo, pull_number: pr.number,
    }));
    const latestRecord = parseDeliveryRecord(latest?.body || '');
    if (
      latest?.state !== 'open' || latest?.draft || latest?.auto_merge
      || latest?.head?.sha !== pr.head.sha
      || latestRecord?.plan_id !== record.plan_id
      || latestRecord?.generation !== record.generation
      || latestRecord?.head_observed_sha !== pr.head.sha
      || latestRecord?.delivery_state !== 'staging'
    ) {
      throw new Error('Generated delivery changed after exact-head review request');
    }
    const latestBody = replaceDeliveryRecord(latest.body || '', {
      delivery_state: 'reviewing',
      review_started_at: reviewStartedAt,
      sealed_at: '',
      sealed_head_sha: '',
      review_evidence: { request_comment_id: request.id },
    });
    await withRetry((client) => client.rest.pulls.update({
      owner,
      repo,
      pull_number: pr.number,
      body: latestBody,
    }));
    return { reviewStartedAt, body: latestBody, dryRun: false };
  }

  async function restageStableDelivery({ owner, repo, pr, record, dryRunMode }) {
    if (dryRunMode) {
      const body = replaceDeliveryRecord(pr.body || '', {
        delivery_state: 'staging',
        review_started_at: '',
        sealed_at: '',
        sealed_head_sha: '',
        review_evidence: {},
      });
      return { body, dryRun: true };
    }
    const assertRestageIdentity = (current, { requireReady = false } = {}) => {
      const currentRecord = parseDeliveryRecord(current?.body || '');
      if (
        current?.state !== 'open'
        || (requireReady && (current.draft || current.auto_merge))
        || current?.head?.sha !== pr.head.sha
        || currentRecord?.plan_id !== record.plan_id
        || currentRecord?.generation !== record.generation
        || currentRecord?.head_observed_sha !== pr.head.sha
        || currentRecord?.delivery_state !== record.delivery_state
      ) {
        throw new Error('Generated delivery changed before exact-head restage');
      }
    };
    const { data: beforeHold } = await withRetry((client) => client.rest.pulls.get({
      owner, repo, pull_number: pr.number,
    }));
    assertRestageIdentity(beforeHold);
    const current = await holdReadyStableDelivery({ owner, repo, pr, expectedRecord: record });
    assertRestageIdentity(current, { requireReady: true });
    const body = replaceDeliveryRecord(current.body || '', {
      delivery_state: 'staging',
      review_started_at: '',
      sealed_at: '',
      sealed_head_sha: '',
      review_evidence: {},
    });
    await withRetry((client) => client.rest.pulls.update({
      owner,
      repo,
      pull_number: pr.number,
      body,
    }));
    await withRetry((client) => client.rest.issues.addLabels({
      owner,
      repo,
      issue_number: pr.number,
      labels: ['sync:delivery-staging'],
    }));
    try {
      await withRetry((client) => client.rest.issues.removeLabel({
        owner,
        repo,
        issue_number: pr.number,
        name: 'sync:delivery-ready',
      }));
    } catch (labelError) {
      if (labelError?.status !== 404) throw labelError;
    }
    return { body, dryRun: false };
  }

  async function sealStableDelivery({ owner, repo, pr, record, settlement, dryRunMode }) {
    const sealedAt = new Date().toISOString();
    const reviewEvidence = {
      policy_schema: reviewPolicy.schema,
      request_comment_id: record.review_evidence?.request_comment_id || null,
      reason: settlement.reason,
      degraded: Boolean(settlement.degraded),
      responded_reviewers: settlement.responded || [],
      unavailable_reviewers: settlement.unavailable || [],
    };
    if (dryRunMode) return { sealedAt, reviewEvidence, body: pr.body, dryRun: true };
    const body = replaceDeliveryRecord(pr.body || '', {
      delivery_state: 'sealed',
      review_started_at: record.review_started_at,
      sealed_at: sealedAt,
      sealed_head_sha: pr.head.sha,
      review_evidence: reviewEvidence,
    });
    await withRetry((client) => client.rest.pulls.update({
      owner,
      repo,
      pull_number: pr.number,
      body,
    }));
    // Mark the lifecycle state, then explicitly request Gate on this head.
    // Current Gates use dispatch; legacy consumers may use the label wakeup.
    // Keep the staging hold until the Maint 71 exact-head merge completes: generic merge lanes use
    // it as their hard stop, while this workflow's dedicated guard explicitly
    // authorizes the sealed delivery path.
    await withRetry((client) => client.rest.issues.addLabels({
      owner,
      repo,
      issue_number: pr.number,
      labels: ['sync:delivery-ready'],
    }));
    const gateRequest = await requestSealedGate({ owner, repo, pr, withRetry });
    return { sealedAt, reviewEvidence, body, gateRequest, dryRun: false };
  }

  async function confirmExactHeadReviewClear({
    owner,
    repo,
    pr,
    expectMerged,
    requireSealedDelivery = false,
    requireVerifiedHead = false,
    requireGeneratedDeliveryGate = false,
  }) {
    const data = await withReviewReadRetry((client) => client.graphql(
      `query($owner: String!, $repo: String!, $number: Int!, $head: GitObjectID!) {
        repository(owner: $owner, name: $repo) {
          object(oid: $head) {
            ... on Commit {
              signature { isValid state wasSignedByGitHub }
            }
          }
          pullRequest(number: $number) {
            state
            mergedAt
            headRefOid
            body
            createdAt
            updatedAt
            reviewThreads(first: 100) {
              pageInfo { hasNextPage }
              nodes {
                id
                path
                isResolved
                isOutdated
                comments(first: 10) {
                  nodes {
                    path
                    author { login }
                  }
                }
              }
            }
          }
        }
      }`,
      { owner, repo, number: pr.number, head: pr.head.sha },
    ));
    const freshPr = data?.repository?.pullRequest;
    if (freshPr?.headRefOid !== pr.head.sha) {
      return {
        ok: false,
        reason: 'head_changed',
        activeReviewThreads: -1,
        freshHeadSha: freshPr?.headRefOid || '',
      };
    }
    if (expectMerged && !(freshPr?.mergedAt || freshPr?.state === 'MERGED')) {
      return {
        ok: false,
        reason: 'merged_state_changed',
        activeReviewThreads: -1,
        freshHeadSha: freshPr?.headRefOid || '',
      };
    }
    if (!expectMerged && freshPr?.state !== 'OPEN') {
      return {
        ok: false,
        reason: 'pr_state_changed',
        activeReviewThreads: -1,
        freshHeadSha: freshPr?.headRefOid || '',
      };
    }
    const signature = data?.repository?.object?.signature;
    if (requireVerifiedHead && !commitSignatureAllowsMerge(signature)) {
      return {
        ok: false,
        reason: 'head_commit_unverified',
        activeReviewThreads: -1,
        freshHeadSha: freshPr?.headRefOid || '',
        signatureState: signature?.state || 'MISSING',
      };
    }
    if (requireSealedDelivery) {
      const freshRecord = parseDeliveryRecord(freshPr?.body || '');
      const sealEligibility = freshRecord
        ? mergeEligibility(freshRecord, {
            now: new Date().toISOString(),
            repository: `${owner}/${repo}`,
            requireSealed: true,
            headSha: freshPr.headRefOid,
          })
        : { eligible: false, reason: 'missing_delivery_record' };
      if (!sealEligibility.eligible) {
        return {
          ok: false,
          reason: 'delivery_seal_changed',
          deliveryReason: sealEligibility.reason,
          activeReviewThreads: -1,
          freshHeadSha: freshPr.headRefOid,
        };
      }
    }
    const reviewWindow = evaluatePostPushReviewWindow(
      {
        created_at: freshPr?.createdAt || pr.created_at,
        updated_at: freshPr?.updatedAt || pr.updated_at,
        head: {
          sha: pr?.head?.sha,
          observed_sha: pr?.head?.observed_sha,
          observed_at: pr?.head?.observed_at,
        },
      },
      new Date().toISOString(),
      integrationOnly ? 0 : undefined,
    );
    if (!reviewWindow.ready) {
      return {
        ok: false,
        reason: 'review_window_pending',
        activeReviewThreads: -1,
        freshHeadSha: freshPr.headRefOid,
        reviewWindow,
      };
    }
    const reviewThreads = freshPr?.reviewThreads;
    if (!hasCompleteReviewThreadEvidence(reviewThreads)) {
      return {
        ok: false,
        reason: 'review_thread_query_incomplete',
        activeReviewThreads: -1,
        freshHeadSha: freshPr.headRefOid,
      };
    }
    const activeThreadNodes = reviewThreads.nodes.filter(
      (thread) => !thread.isResolved && !thread.isOutdated,
    );
    const activeReviewThreads = activeThreadNodes.length;
    if (activeReviewThreads !== 0) {
      return {
        ok: false,
        reason: 'review_blocked',
        activeReviewThreads,
        reviewThreads: activeThreadNodes,
        freshHeadSha: freshPr.headRefOid,
      };
    }
    // A rerun can turn Gate red without changing the head after the earlier
    // delivery classification. Recheck required contexts at the final merge
    // boundary rather than treating exact-head review evidence as sufficient.
    let finalCheckEvidence = null;
    if (requireGeneratedDeliveryGate) {
      finalCheckEvidence = await classifyRequiredChecksForRef({
        owner,
        repo,
        branch: pr.base.ref,
        ref: pr.head.sha,
        enforceGeneratedDeliveryGate: true,
      });
      if (finalCheckEvidence.classification.status !== 'ready') {
        return {
          ok: false,
          reason: finalCheckEvidence.classification.status,
          activeReviewThreads,
          freshHeadSha: freshPr.headRefOid,
          finalCheckEvidence,
        };
      }
    }
    return {
      ok: true,
      reason: 'exact_head_review_clear',
      activeReviewThreads,
      freshHeadSha: freshPr.headRefOid,
      freshPr,
      finalCheckEvidence,
    };
  }
  
  for (let repoIndex = 0; repoIndex < targetRepos.length; repoIndex += 1) {
    const repoEntry = targetRepos[repoIndex];
    const [entryOwner, entryRepo] = repoEntry.includes('/')
      ? repoEntry.split('/')
      : [defaultOwner, repoEntry];
    const owner = entryOwner || defaultOwner;
    const repo = entryRepo;
    const repository = `${owner}/${repo}`;
    const selectedSyncHash = syncSelectorForRepository({
      syncHash: requestedSyncHash,
      repository,
      canaryRepos: expectedCanaryRepos,
    });
  
    console.log(`\n=== ${owner}/${repo} ===`);
  
    try {
      const pullRequests = await listMaint71PullRequests({
        owner,
        repo,
        withRetry,
        includeClosed:
          cleanupBranches || selectedSyncHash === 'candidate' || requestedSyncHash === 'campaign',
      });
      const prs = pullRequests.open;
      const syncPRs = prs.filter((pr) => isTrustedGeneratedDeliveryPr(pr, trustedSyncActors));
      const closedPRs = pullRequests.closed;
  
      if (cleanupBranches) {
        try {
          const branches = await withRetry((client) => client.paginate(
            client.rest.repos.listBranches,
            { owner, repo, per_page: 100 },
          ));
          const branchesToDelete = collectDeletableSyncBranches({
            branches,
            // Pass every open PR so an open sync head beyond the filtered set is never deleted.
            openPullRequests: prs,
            closedPullRequests: closedPRs,
          });
  
          if (branchesToDelete.length > 0) {
            console.log(
              `Found ${branchesToDelete.length} closed sync PR branch(es) to clean up`,
            );
          }
  
          for (const branch of branchesToDelete) {
            if (dryRun) {
              console.log(`[DRY RUN] Would delete ${branch}`);
              results.push({
                owner,
                repo,
                branch,
                status: 'branch_deleted',
                dry_run: true,
              });
              continue;
            }
  
            try {
              await withRetry((client) => client.rest.git.deleteRef({
                owner,
                repo,
                ref: `heads/${branch}`,
              }));
              console.log(`✓ Deleted leftover branch ${branch}`);
              results.push({ owner, repo, branch, status: 'branch_deleted' });
            } catch (branchErr) {
              rethrowPrimaryRateLimit(branchErr);
              console.log(
                `⚠ Could not delete leftover branch ${branch}: ${branchErr.message}`,
              );
              results.push({
                owner,
                repo,
                branch,
                status: 'branch_delete_failed',
                error: branchErr.message,
              });
            }
          }
        } catch (cleanupErr) {
          rethrowPrimaryRateLimit(cleanupErr);
          console.log(`⚠ Sync branch cleanup failed: ${cleanupErr.message}`);
          results.push({
            owner,
            repo,
            status: 'branch_delete_failed',
            error: cleanupErr.message,
          });
        }
      }

      let candidatePRs = generatedPrsForSyncSelector(syncPRs, selectedSyncHash);
      let recoveredMergedCandidate = false;
      const hasOpenCandidate = syncPRs.some(
        (pr) => pr?.head?.ref === syncBranchForHash('candidate'),
      );
      const baselineEvidence = baselineEvidenceByRepo.get(`${owner}/${repo}`) || null;
      const campaignNoChangeEvidence = campaignNoChangeEvidenceByRepo.get(
        `${owner}/${repo}`,
      ) || null;
      if (candidatePRs.length === 0 && requestedSyncHash === 'campaign' && campaignNoChangeEvidence) {
        const { data: repositoryState } = await withRetry((client) => client.rest.repos.get({
          owner,
          repo,
        }));
        const { data: defaultRef } = await withRetry((client) => client.rest.git.getRef({
          owner,
          repo,
          ref: `heads/${repositoryState.default_branch}`,
        }));
        const liveHeadSha = String(defaultRef?.object?.sha || '').trim().toLowerCase();
        if (liveHeadSha !== campaignNoChangeEvidence.head_sha) {
          results.push({
            owner,
            repo,
            status: 'target_missing',
            expected_head_sha: campaignNoChangeEvidence.head_sha,
            observed_head_sha: liveHeadSha,
            reason: 'campaign_no_change_head_changed',
          });
          continue;
        }
        if (campaignNoChangeRequiresLiveGate(campaignNoChangeEvidence)) {
          const baselineChecks = await classifyRequiredChecksForRef({
            owner,
            repo,
            branch: repositoryState.default_branch,
            ref: liveHeadSha,
          });
          if (
            baselineChecks.requiredContexts.size === 0
            || baselineChecks.classification.status !== 'ready'
          ) {
            results.push({
              owner,
              repo,
              status: baselineChecks.requiredContexts.size === 0
                ? 'checks_failed'
                : baselineChecks.classification.status,
              expected_head_sha: campaignNoChangeEvidence.head_sha,
              observed_head_sha: liveHeadSha,
              reason: 'campaign_no_change_required_checks_not_ready',
            });
            continue;
          }
        }
        results.push({
          owner,
          repo,
          status: 'campaign_no_change_verified',
          observed_head_sha: liveHeadSha,
          plan_id: campaignNoChangeEvidence.plan_id,
          source_commit: campaignNoChangeEvidence.source_commit,
        });
        console.log(`✓ Confirmed campaign no-change evidence at ${liveHeadSha}`);
        continue;
      }
      if (!hasOpenCandidate && selectedSyncHash === 'candidate' && baselineEvidence) {
        const { data: repository } = await withRetry((client) => client.rest.repos.get({
          owner,
          repo,
        }));
        const { data: defaultRef } = await withRetry((client) => client.rest.git.getRef({
          owner,
          repo,
          ref: `heads/${repository.default_branch}`,
        }));
        const liveHeadSha = String(defaultRef?.object?.sha || '').trim().toLowerCase();
        if (liveHeadSha !== baselineEvidence.head_sha) {
          console.log(
            `No-change canary baseline moved: ${baselineEvidence.head_sha} -> ` +
              `${liveHeadSha || '<missing>'}`,
          );
          results.push({
            owner,
            repo,
            status: 'target_missing',
            expected_head_sha: baselineEvidence.head_sha,
            observed_head_sha: liveHeadSha,
            reason: 'no_change_canary_head_changed',
          });
          continue;
        }
        const baselineChecks = await classifyRequiredChecksForRef({
          owner,
          repo,
          branch: repository.default_branch,
          ref: liveHeadSha,
        });
        if (baselineChecks.requiredContexts.size === 0) {
          console.log('No-change canary has no authoritative required check contexts');
          results.push({
            owner,
            repo,
            status: 'checks_failed',
            expected_head_sha: baselineEvidence.head_sha,
            observed_head_sha: liveHeadSha,
            reason: 'no_change_canary_required_checks_unconfigured',
          });
          continue;
        }
        if (baselineChecks.classification.status !== 'ready') {
          console.log(
            `No-change canary required checks are not green: ` +
              baselineChecks.classification.status,
          );
          results.push({
            owner,
            repo,
            status: baselineChecks.classification.status,
            expected_head_sha: baselineEvidence.head_sha,
            observed_head_sha: liveHeadSha,
            reason: 'no_change_canary_required_checks_not_ready',
            failed_checks: baselineChecks.classification.failed.map((check) => check.name),
            pending_checks: baselineChecks.classification.pending.map((check) => check.name),
          });
          continue;
        }
        canaryEvidence.push(baselineEvidence);
        results.push({
          owner,
          repo,
          status: 'evidence_recovered',
          delivery_disposition: 'no-change-canary-confirmed',
          branch: syncBranchForHash('candidate'),
          observed_head_sha: liveHeadSha,
          active_review_thread_count: 0,
        });
        console.log(`✓ Confirmed exact-head no-change evidence at ${liveHeadSha}`);
        continue;
      }
      if (!hasOpenCandidate && requestedSyncHash === 'candidate') {
        const mergedCandidate = selectLatestMergedCandidatePr(closedPRs, trustedSyncActors, {
          planId: expectedPlanId,
          sourceCommit: expectedSourceCommit,
        });
        if (mergedCandidate) {
          candidatePRs = [mergedCandidate];
          recoveredMergedCandidate = true;
          console.log(
            `Recovering canary evidence from merged PR #${mergedCandidate.number} ` +
              `(${mergedCandidate.head.sha})`,
          );
        }
      }

      if (candidatePRs.length === 0 && requestedSyncHash === 'candidate') {
        results.push({
          owner,
          repo,
          branch: syncBranchForHash('candidate'),
          status: 'stable_base_refresh_required',
          next_command: 'dispatch-maint-68-phase-canary-no-filter',
          reason: 'candidate_pr_and_no_change_evidence_missing',
        });
        continue;
      }

      if (candidatePRs.length === 0 && requestedSyncHash === 'campaign') {
        const repoKey = `${owner}/${repo}`;
        const authRow = campaignAuthorizationRowForRepository(
          campaignCommitAuthorization,
          repoKey,
        );
        const recoveryIdentity = authRow && !authRow.no_change
          ? {
            branch: authRow.branch,
            planId: expectedPlanId,
            sourceCommit: expectedSourceCommit,
            prNumber: authRow.pr,
            headSha: authRow.head_sha,
          }
          : prepareOnly
            ? {
              branch: syncBranchForHash(selectedSyncHash),
              planId: expectedPlanId,
              sourceCommit: expectedSourceCommit,
            }
            : null;
        if (recoveryIdentity) {
          const mergedCampaign = selectLatestMergedSyncPr(
            closedPRs,
            trustedSyncActors,
            recoveryIdentity,
          );
          if (mergedCampaign) {
            const mergedDelivery = parseDeliveryRecord(mergedCampaign.body || '');
            const deliveryGeneration = authRow?.delivery_generation
              || mergedDelivery?.generation
              || '';
            if (!deliveryGeneration) {
              console.log(
                `Merged campaign PR #${mergedCampaign.number} lacks delivery generation; ` +
                  'leaving recovery fail-closed',
              );
            } else {
              results.push({
                owner,
                repo,
                pr: mergedCampaign.number,
                branch: mergedCampaign.head.ref,
                head_sha: mergedCampaign.head.sha,
                delivery_generation: deliveryGeneration,
                plan_id: expectedPlanId,
                source_commit: expectedSourceCommit,
                status: 'merged',
                evidence_source: prepareOnly
                  ? 'campaign-prepare-recovery'
                  : 'campaign-commit-recovery',
              });
              console.log(
                `✓ Recovered already-merged campaign row from PR #${mergedCampaign.number} ` +
                  `(${mergedCampaign.head.sha})`,
              );
              continue;
            }
          }
        }
      }

      if (candidatePRs.length === 0 && requestedSyncHash === 'campaign') {
        results.push({
          owner,
          repo,
          branch: syncBranchForHash(selectedSyncHash),
          status: 'target_missing',
          expected_branch: syncBranchForHash(selectedSyncHash),
          reason: 'campaign_pr_and_no_change_evidence_missing',
        });
        continue;
      }

      if (candidatePRs.length === 0) {
        console.log('No sync PRs found');
        results.push({ owner, repo, status: 'no_prs' });
        continue;
      }
  
      let selection = selectMergeEligibleSyncPr(candidatePRs, {
        syncHash: selectedSyncHash,
        now: new Date().toISOString(),
        planId: expectedPlanId,
        repository: `${owner}/${repo}`,
      });
      if (selection.missingExpected) {
        const reason = 'no_active_sync_pr';
        console.log(
          `Delivery contract blocks merge: ${reason} ` +
            `(expected ${selection.expectedBranch}, active hash '${selectedSyncHash}'); leaving ` +
            `${candidatePRs.length} sync PRs untouched`,
        );
        results.push({
          owner,
          repo,
          status: 'target_missing',
          expected_branch: selection.expectedBranch,
          active_sync_hash: selectedSyncHash,
          delivery_reason: reason,
          open_sync_prs: candidatePRs.map((item) => ({
            number: item.number,
            branch: item.head.ref,
            url: item.html_url,
          })),
        });
        continue;
      }
  
      if (selection.foreignPlan) {
        const owningMetadata = syncMetadata(selection.active);
        console.log(`Leaving PR #${selection.active.number} untouched: it belongs to another plan`);
        results.push({
          owner, repo, pr: selection.active.number, branch: selection.active.head.ref,
          head_sha: selection.active.head.sha,
          status: 'delivery_plan_handoff', delivery_reason: 'plan_mismatch',
          delivery_generation: selection.deliveryRecord.generation,
          plan_id: selection.deliveryRecord.plan_id,
          plan_scope: owningMetadata?.plan_scope || 'full',
          scope_base_sha: owningMetadata?.scope_base_sha || '',
          source_commit: selection.deliveryRecord.source_commit,
          continuation_lane: selectedSyncHash === 'candidate' ? 'candidate' : requestedSyncHash,
          check_state: 'checks_pending', review_state: 'not-applicable',
          delivery_disposition: 'other-plan', blocker_owner: 'maint-71',
          expected_plan_id: expectedPlanId, observed_plan_id: selection.deliveryRecord.plan_id,
          next_command: 'resume-owning-plan',
        });
        continue;
      }

      const { data: selectedHeadCommit } = await withRetry((client) =>
        client.rest.git.getCommit({
          owner,
          repo,
          commit_sha: selection.active.head.sha,
        }),
      );
      selection = selectMergeEligibleSyncPr(candidatePRs, {
        syncHash: selectedSyncHash,
        now: new Date().toISOString(),
        planId: expectedPlanId,
        repository: `${owner}/${repo}`,
        desiredTreeHash: selectedHeadCommit?.tree?.sha || '',
      });
  
      // If multiple sync PRs exist, close older ones as stale
      if (selection.stale.length > 0) {
        console.log(
          `Found ${candidatePRs.length} sync PRs - closing ` +
            `${selection.stale.length} stale PRs`,
        );
  
        for (const stalePR of selection.stale) {
          console.log(`\nClosing stale PR #${stalePR.number}: ${stalePR.title}`);
          console.log(`Branch: ${stalePR.head.ref}, Created: ${stalePR.created_at}`);
          const staleRecord = parseDeliveryRecord(stalePR.body || '');
          const staleIdentity = staleRecord?.generation && stalePR.head?.sha
            ? {
              head_sha: stalePR.head.sha,
              delivery_generation: staleRecord.generation,
              plan_id: staleRecord.plan_id || '',
              plan_scope: staleRecord.plan_scope || '',
              scope_base_sha: staleRecord.scope_base_sha || '',
              source_commit: staleRecord.source_commit || '',
            }
            : {};

          if (!dryRun) {
            try {
              // Close PR
              const closedResponse = await withRetry((client) => client.rest.pulls.update({
                owner,
                repo,
                pull_number: stalePR.number,
                state: 'closed'
              }));
              const closureMatches = confirmedClosedPrIdentity(closedResponse, stalePR);
              console.log('✓ Closed');
  
              // Delete branch
              try {
                await withRetry((client) => client.rest.git.deleteRef({
                  owner,
                  repo,
                  ref: `heads/${stalePR.head.ref}`
                }));
                console.log('✓ Branch deleted');
              } catch (delErr) {
                rethrowPrimaryRateLimit(delErr);
                console.log(`⚠ Branch delete failed: ${delErr.message}`);
              }
              results.push({
                owner,
                repo,
                pr: stalePR.number,
                branch: stalePR.head.ref,
                status: 'stale_closed',
                ...(closureMatches ? staleIdentity : {}),
              });
            } catch (staleErr) {
              rethrowPrimaryRateLimit(staleErr);
              console.log(`✗ Stale close failed: ${staleErr.message}`);
              results.push({
                owner,
                repo,
                pr: stalePR.number,
                branch: stalePR.head.ref,
                status: 'stale_close_failed',
                error: staleErr.message,
              });
            }
          } else {
            console.log('[DRY RUN] Would close and delete branch');
            results.push({
              owner,
              repo,
              pr: stalePR.number,
              branch: stalePR.head.ref,
              status: 'stale_closed',
              dry_run: true,
            });
          }
        }
      }
  
      if (!selection.eligibility?.eligible) {
        const reason = selection.eligibility?.reason || 'no_active_sync_pr';
        console.log(`Delivery contract blocks merge: ${reason}`);
        const deliveryDisposition = reason === 'lease_expired'
          ? 'expired'
          : selection.deliveryRecord
            ? 'superseded'
            : 'owner-decision';
        const deliveryContext = {
          owner,
          repo,
          pr: selection.active.number,
          branch: selection.active.head.ref,
          head_sha: selection.active.head.sha,
          delivery_generation: selection.deliveryRecord?.generation || '',
          delivery_lane: generatedDeliveryLane(selection.active.head.ref),
          delivery_disposition: deliveryDisposition,
          delivery_reason: reason,
          blocker_owner: deliveryDisposition === 'owner-decision' ? 'source' : 'maint-71',
          next_command: deliveryDisposition === 'expired'
            ? 'close-expired-delivery'
            : deliveryDisposition === 'superseded'
              ? 'close-or-refresh-delivery'
              : 'attach-or-infer-delivery-record',
        };
        if (deliveryDisposition === 'expired' || deliveryDisposition === 'superseded') {
          if (!dryRun) {
            await withRetry((client) => client.rest.issues.createComment({
              owner,
              repo,
              issue_number: selection.active.number,
              body: [
                'Closing this generated delivery as no longer current.',
                `delivery_reason: ${reason}`,
                `delivery_disposition: ${deliveryDisposition}`,
                `next_command: ${deliveryContext.next_command}`,
              ].join('\n'),
            }));
            const closedResponse = await withRetry((client) => client.rest.pulls.update({
              owner,
              repo,
              pull_number: selection.active.number,
              state: 'closed',
            }));
            // A concurrent push can change the head between selection and close.
            // Never emit a terminal handoff for an identity we did not close.
            if (!confirmedClosedPrIdentity(closedResponse, selection.active)) {
              results.push({
                ...deliveryContext,
                head_sha: '',
                delivery_generation: '',
                status: 'stale_closed',
              });
              continue;
            }
          }
          results.push({ ...deliveryContext, status: 'stale_closed', dry_run: dryRun });
          continue;
        }
        results.push({
          ...deliveryContext,
          status: 'delivery_contract_blocked',
          delivery_reason: reason,
        });
        continue;
      }
  
      // Process the selected active PR from a full, revalidated REST payload.
      // List responses omit mergeable_state and can race an intervening push or
      // body edit, so never authorize lifecycle or merge work from the list row.
      let pr = selection.active;
      try {
        const { data: fullPr } = await withRetry((client) => client.rest.pulls.get({
          owner,
          repo,
          pull_number: pr.number,
        }));
        const changedSinceSelection = !fullPr
          || fullPr.number !== pr.number
          || fullPr.head?.ref !== pr.head?.ref
          || fullPr.head?.sha !== pr.head?.sha
          || fullPr.base?.ref !== pr.base?.ref
          || fullPr.user?.login !== pr.user?.login
          || fullPr.body !== pr.body
          || !isTrustedGeneratedDeliveryPr(fullPr, trustedSyncActors);
        if (changedSinceSelection) {
          throw new Error('refreshed PR no longer matches the trusted delivery selection');
        }
        pr = fullPr;
        const observedHeadMatches = selection.deliveryRecord?.head_observed_sha === pr.head.sha;
        pr.head.observed_sha = observedHeadMatches
          ? selection.deliveryRecord.head_observed_sha
          : '';
        pr.head.observed_at = observedHeadMatches
          ? selection.deliveryRecord.head_observed_at
          : '';
      } catch (error) {
        rethrowPrimaryRateLimit(error);
        const message = String(error?.message || error);
        console.log(`Unable to refresh generated PR #${pr.number}: ${message}`);
        results.push({
          owner,
          repo,
          pr: pr.number,
          branch: pr.head.ref,
          head_sha: pr.head.sha,
          status: 'pr_refresh_failed',
          error: `PR refresh before lifecycle decision: ${message}`,
        });
        continue;
      }
      const metadata = syncMetadata(pr);
      if (
        ['candidate', 'campaign'].includes(requestedSyncHash)
        && !recoveredMergedCandidate
      ) {
        const identity = validateExpectedCandidateIdentity({
          metadata,
          deliveryRecord: selection.deliveryRecord,
          expectedPlanId,
          expectedPlanScope,
          expectedScopeBaseSha,
          expectedSourceCommit,
          repository: `${owner}/${repo}`,
        });
        if (!identity.ok) {
          console.log(`Candidate immutable identity mismatch: ${identity.errors.join(', ')}`);
          results.push({
            owner,
            repo,
            pr: pr.number,
            branch: pr.head.ref,
            head_sha: pr.head.sha,
            status: 'delivery_contract_blocked',
            delivery_disposition: 'source-binding-blocked',
            blocker_owner: 'maint-68',
            next_command: 'refresh-candidate-from-exact-plan',
            delivery_reason: 'candidate_immutable_identity_mismatch',
            identity_errors: identity.errors,
          });
          continue;
        }
      }
      console.log(`\nProcessing active PR #${pr.number}: ${pr.title}`);
      console.log(`Branch: ${pr.head.ref}`);
      console.log(`Created: ${pr.created_at}`);

      // A stable candidate normally receives this from its delivery marker.
      // During the first reconciliation, derive the same immutable generation
      // from the Maint 68 marker; do not emit a handoff the campaign will drop.
      const handoffDeliveryGeneration = selection.deliveryRecord?.generation
        || metadata?.template_hash
        || '';
      if (!handoffDeliveryGeneration) {
        console.log('Delivery contract blocks handoff: missing delivery generation');
        results.push({
          owner,
          repo,
          pr: pr.number,
          branch: pr.head.ref,
          head_sha: pr.head.sha,
          status: 'delivery_contract_blocked',
          delivery_disposition: 'source-binding-blocked',
          blocker_owner: 'maint-68',
          next_command: 'refresh-candidate-from-exact-plan',
          delivery_reason: 'missing_delivery_generation',
        });
        continue;
      }

      const reviewWindow = evaluatePostPushReviewWindow(pr, new Date().toISOString(),
        integrationOnly ? 0 : undefined);
      if (!reviewWindow.ready) {
        console.log(`Post-push review window remains open until ${reviewWindow.eligible_at || 'unknown'}`);
        results.push({
          owner,
          repo,
          pr: pr.number,
          branch: pr.head.ref,
          head_sha: pr.head.sha,
          delivery_generation: handoffDeliveryGeneration,
          // The review-window result is itself a durable Maint 82 handoff.
          // New stable candidates have no delivery marker yet, so bind it to
          // the exact Maint 68 dispatch identity before the early continue.
          plan_id: selection.deliveryRecord?.plan_id || expectedPlanId,
          plan_scope: metadata?.plan_scope || expectedPlanScope,
          scope_base_sha: metadata?.scope_base_sha || expectedScopeBaseSha,
          source_commit: selection.deliveryRecord?.source_commit
            || metadata?.source_commit
            || expectedSourceCommit,
          canary_baseline_evidence_json: selectedSyncHash === 'candidate'
            ? rawBaselineEvidence
            : '',
          campaign_no_change_evidence_json: requestedSyncHash === 'campaign'
            ? rawCampaignNoChangeEvidence
            : '',
          delivery_lane: generatedDeliveryLane(pr.head.ref),
          continuation_lane: requestedSyncHash === 'campaign' ? 'campaign' : '',
          delivery_disposition: 'awaiting-review-window',
          blocker_owner: 'maint-71',
          next_command: reviewWindow.eligible_at
            ? `rerun-after:${reviewWindow.eligible_at}`
            : 'rerun-after-review-window',
          status: 'review_window_pending',
          review_window_eligible_at: reviewWindow.eligible_at || '',
        });
        continue;
      }
  
      // Combined legacy statuses + every check-run page (paginate returns a flat array).
      const checkEvidence = await classifyRequiredChecksForRef({
        owner,
        repo,
        branch: pr.base.ref,
        ref: pr.head.sha,
        enforceGeneratedDeliveryGate: true,
      });
      const {
        allChecks,
        checkGateMode,
        classification,
        gatingChecks,
        requiredContexts,
      } = checkEvidence;
      const failedChecks = classification.failed;
      const pendingChecks = classification.pending;
      let deliveryRecord = parseDeliveryRecord(pr.body || '');
      const reviewResolution = await resolveProvenReviewDebt({
        owner,
        repo,
        pr,
        deliveryRecord,
      });
      const reviewThreadDetails = await fetchActiveReviewThreads(
        owner,
        repo,
        pr.number,
      );
      let activeReviewThreads = reviewThreadDetails.count;
      let deliveryState = classifyGeneratedPr({
        pr,
        checkState: classification,
        activeReviewThreadCount: activeReviewThreads,
        reviewThreads: reviewThreadDetails.threads,
        manifestSources,
        reviewerProfiles,
        reviewPolicyLoaded,
        now: new Date().toISOString(),
      });
      const deliveryContext = {
        owner,
        repo,
        pr: pr.number,
        branch: pr.head.ref,
        head_sha: pr.head.sha,
        delivery_generation: deliveryRecord?.generation || handoffDeliveryGeneration,
        // A freshly created stable candidate has no prior delivery marker yet.
        // Preserve the immutable Maint 68 handoff in the durable Maint 82
        // continuation rather than emitting an unbound retry.
        plan_id: deliveryRecord?.plan_id || expectedPlanId,
        plan_scope: metadata?.plan_scope || expectedPlanScope,
        scope_base_sha: metadata?.scope_base_sha || expectedScopeBaseSha,
        source_commit: deliveryRecord?.source_commit || metadata?.source_commit || expectedSourceCommit,
        canary_baseline_evidence_json: selectedSyncHash === 'candidate'
          ? rawBaselineEvidence
          : '',
        campaign_no_change_evidence_json: requestedSyncHash === 'campaign'
          ? rawCampaignNoChangeEvidence
          : '',
        delivery_lane: generatedDeliveryLane(pr.head.ref),
        continuation_lane: requestedSyncHash === 'campaign' ? 'campaign' : '',
        delivery_disposition: deliveryState.disposition,
        blocker_owner: deliveryState.blocker_owner,
        next_command: deliveryState.next_command,
        review_resolution_thread_ids: reviewResolution.resolved,
        review_resolution_would_resolve_thread_ids: reviewResolution.wouldResolve,
        review_resolution_errors: reviewResolution.errors,
        // The consumer's declared checks, by outcome, on every row this PR
        // produces, so the merge report shows what blocked or went unenforced.
        consumer_declared_contexts: {
          state: checkEvidence.declaredContexts.state,
          ...(classification.declared_contexts || {}),
        },
      };
  
      console.log(
        `Checks (${checkGateMode}): ${gatingChecks.length} gating, ` +
          `${failedChecks.length} failed, ${pendingChecks.length} pending`,
      );
  
      const stableDelivery = isStableSyncBranchName(pr.head.ref);
      if (stableDelivery && !recoveredMergedCandidate
        && expectedCanaryRepos.includes(`${owner}/${repo}`)
        && metadata?.sync_phase === 'canary') {
        // This only lets the existing staging/reviewing lifecycle advance to
        // sealing. The failure stays in `classification`; after sealing, this
        // exact-state predicate no longer matches, so the fresh Gate must pass
        // before any merge path can proceed.
        const expectedPresealGateHold = classification.status === 'checks_failed'
          && await isExpectedPresealGateFailure({ owner, repo, headSha: pr.head.sha,
            deliveryRecord, deliveryState: deliveryRecord?.delivery_state, classification, allChecks,
            withRetry });
        const canary = { owner, repo, pr: pr.number, plan_id: deliveryContext.plan_id,
          mergeable_state: pr.mergeable_state, mergeable: pr.mergeable, check_status: classification.status,
          expected_preseal_gate_hold: expectedPresealGateHold,
          active_review_thread_count: activeReviewThreads,
          head_observed_at: deliveryRecord?.head_observed_at,
          updated_at: pr.updated_at, created_at: pr.created_at,
          threads: reviewThreadDetails.threads };
        stableCanaries.push(canary);
        const reason = canaryNeedsRefresh(canary);
        if (reason) {
          // Refresh belongs to Maint 68. Do not let review/CI early exits hide
          // the request, or update the stable head without reminting its seal.
          if (deliveryRecord?.delivery_state && autoMerge && !dryRun) {
            await restageStableDelivery({ owner, repo, pr, record: deliveryRecord,
              dryRunMode: false });
          }
          results.push({ ...deliveryContext, status: 'stable_base_refresh_required',
            delivery_disposition: 'awaiting-base-refresh', blocker_owner: 'maint-68',
            next_command: 'dispatch-maint-68-phase-canary-no-filter',
            refresh_reason: reason });
          continue;
        }
      }

      if (deliveryState.disposition === 'review-blocked') {
        console.log(`Active review threads block merge: ${activeReviewThreads}`);
        results.push({
          ...deliveryContext,
          status: 'review_blocked',
          active_review_thread_count: activeReviewThreads,
        });
        continue;
      }
  
      // Closed canary PRs may predate the mutable-delivery lifecycle. They are
      // read-only evidence sources, so the staging/sealing contract applies
      // only while a stable delivery PR is still open and mutable.
      if (stableDelivery && !recoveredMergedCandidate) {
        if (!deliveryRecord?.delivery_state) {
          results.push({
            ...deliveryContext,
            delivery_disposition: 'owner-decision',
            blocker_owner: 'source',
            next_command: 'refresh-stable-delivery-record',
            status: 'delivery_contract_blocked',
            delivery_reason: 'stable_delivery_state_missing',
          });
          continue;
        }
        if (integrationOnly && ['staging', 'reviewing'].includes(deliveryRecord.delivery_state)) {
          if (!autoMerge && !dryRun) {
            results.push({ ...deliveryContext, status: 'delivery_review_not_started',
              next_command: 'rerun-with-auto-merge-to-prepare-integration-checks' });
            continue;
          }
          const sealed = await prepareIntegrationDelivery({ pr, record: deliveryRecord, dryRun,
            hold: async () => {
              await holdReadyStableDelivery({ owner, repo, pr, expectedRecord: deliveryRecord });
              await withRetry((client) => client.rest.issues.addLabels({
                owner, repo, issue_number: pr.number, labels: ['sync:delivery-staging'],
              }));
              try {
                await withRetry((client) => client.rest.issues.removeLabel({
                  owner, repo, issue_number: pr.number, name: 'sync:delivery-ready',
                }));
              } catch (error) {
                if (error?.status !== 404) throw error;
              }
              // Clearing a stale ready label lets sealing trigger actual fresh CI.
              return (await withRetry((client) => client.rest.pulls.get({
                owner, repo, pull_number: pr.number,
              }))).data;
            },
            seal: ({ pr: current, record, settlement }) => sealStableDelivery({
              owner, repo, pr: current, record, settlement, dryRunMode: false }),
          });
          results.push({ ...deliveryContext,
            status: dryRun ? 'dry_run_seal' : 'delivery_sealed_checks_pending',
            gate_request: sealed.gateRequest,
            delivery_disposition: 'awaiting-sealed-gate', blocker_owner: 'ci',
            next_command: 'rerun-after-generated-delivery-seal-gate',
            review_mode: 'integration-only',
          });
          continue;
        }
        if (
          deliveryRecord.delivery_state === 'staging'
          || (deliveryRecord.delivery_state === 'reviewing' && pr.draft)
        ) {
          if (!autoMerge && !dryRun) {
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-review-start',
              blocker_owner: 'maint-71',
              next_command: 'rerun-with-auto-merge-to-start-review',
              status: 'delivery_review_not_started',
            });
            continue;
          }
          const started = await beginStableDeliveryReview({
            owner,
            repo,
            pr,
            record: deliveryRecord,
            dryRunMode: dryRun,
          });
          console.log(
            `${dryRun ? '[DRY RUN] Would start' : 'Started'} bounded delivery review ` +
              `for PR #${pr.number} at ${started.reviewStartedAt}`,
          );
          results.push({
            ...deliveryContext,
            delivery_disposition: 'awaiting-review-settlement',
            blocker_owner: 'reviewers',
            next_command: `rerun-after:${new Date(
              new Date(started.reviewStartedAt).getTime() + reviewerQuietPeriodMs,
            ).toISOString()}`,
            status: dryRun ? 'dry_run_review_start' : 'review_window_started',
            review_started_at: started.reviewStartedAt,
          });
          continue;
        }
        if (deliveryRecord.delivery_state === 'reviewing') {
          let request;
          try {
            request = await ensureExactHeadReviewRequest({
              owner, repo, pr, record: deliveryRecord, reviewerProfiles,
              withRetry, dryRunMode: dryRun,
            });
          } catch (error) {
            rethrowPrimaryRateLimit(error);
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-review-settlement',
              blocker_owner: 'maint-71',
              next_command: `rerun-after:${new Date(Date.now() + 10 * 60 * 1000).toISOString()}`,
              status: 'reviewer_settlement_pending',
              reason: 'review_request_unconfirmed',
              error: String(error?.message || error),
            });
            continue;
          }
          if (!request) {
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-review-settlement',
              blocker_owner: 'maint-71',
              next_command: 'rerun-with-auto-merge-to-request-review',
              status: 'reviewer_settlement_pending',
              reason: 'dry_run_review_request_missing',
              dry_run: true,
            });
            continue;
          }
          const freshReviewRecord = parseDeliveryRecord(request.body || '');
          if (freshReviewRecord?.delivery_state !== 'reviewing') {
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-review-settlement',
              blocker_owner: 'maint-71',
              next_command: `rerun-after:${new Date(Date.now() + 10 * 60 * 1000).toISOString()}`,
              status: 'reviewer_settlement_pending',
              reason: 'review_record_changed',
            });
            continue;
          }
          deliveryRecord = freshReviewRecord;
          pr.body = request.body;
          if (deliveryRecord.review_started_at !== request.requestedAt) {
            if (dryRun) {
              results.push({
                ...deliveryContext,
                delivery_disposition: 'awaiting-review-settlement',
                blocker_owner: 'maint-71',
                next_command: 'rerun-with-auto-merge-to-repair-review-clock',
                status: 'reviewer_settlement_pending',
                reason: 'dry_run_review_clock_repair',
                review_started_at: request.requestedAt,
                dry_run: true,
              });
              continue;
            }
            const body = replaceDeliveryRecord(request.body || '', {
              review_started_at: request.requestedAt,
              review_evidence: { request_comment_id: request.id },
            });
            await withRetry((client) => client.rest.pulls.update({
              owner, repo, pull_number: pr.number, body,
            }));
            pr.body = body;
            deliveryRecord = parseDeliveryRecord(body);
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-review-settlement',
              blocker_owner: 'reviewers',
              next_command: `rerun-after:${new Date(
                new Date(request.requestedAt).getTime() + reviewerQuietPeriodMs,
              ).toISOString()}`,
              status: 'reviewer_settlement_pending',
              reason: 'review_request_clock_repaired',
              review_started_at: request.requestedAt,
            });
            continue;
          }
          const reviewerEvidence = await collectReviewerEvidence({
            owner,
            repo,
            number: pr.number,
            reviewStartedAt: deliveryRecord.review_started_at,
            headSha: pr.head.sha,
            checkRuns: allChecks,
            reviewerProfiles,
            reviewerCapacityPatterns,
            reviewerNonResponsePatterns,
            withRetry: withReviewReadRetry,
            core,
          });
          if (reviewerEvidence.truncated) {
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-review-settlement',
              blocker_owner: 'maint-71',
              next_command: `rerun-after:${new Date(Date.now() + 10 * 60 * 1000).toISOString()}`,
              status: 'reviewer_settlement_pending',
              reviewer_evidence_truncated: true,
              reason: 'reviewer_evidence_incomplete',
            });
            continue;
          }
          const settlement = evaluateReviewerSettlement({
            reviewStartedAt: deliveryRecord.review_started_at,
            now: new Date().toISOString(),
            configuredReviewers,
            respondedReviewers: reviewerEvidence.responded,
            unavailableReviewers: reviewerEvidence.unavailable,
            minimumResponses: minimumReviewerResponses,
            quietPeriodMs: reviewerQuietPeriodMs,
            maxWaitMs: reviewerMaximumWaitMs,
          });
          if (!settlement.ready) {
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-review-settlement',
              blocker_owner: 'reviewers',
              next_command: settlement.eligible_at
                ? `rerun-after:${settlement.eligible_at}`
                : 'rerun-review-settlement',
              status: 'reviewer_settlement_pending',
              reviewer_settlement: settlement,
              reviewer_evidence_truncated: reviewerEvidence.truncated,
            });
            continue;
          }
          const sealed = await sealStableDelivery({
            owner,
            repo,
            pr,
            record: deliveryRecord,
            settlement,
            dryRunMode: dryRun,
          });
          if (dryRun) {
            results.push({
              ...deliveryContext,
              delivery_disposition: 'current',
              blocker_owner: 'maint-71',
              next_command: 'rerun-with-auto-merge-to-seal',
              status: 'dry_run_seal',
              reviewer_settlement: settlement,
            });
            continue;
          }
          pr.body = sealed.body;
          deliveryRecord = parseDeliveryRecord(pr.body || '');
          console.log(
            `Sealed exact delivery head ${pr.head.sha} with reviewer result ${settlement.reason}`,
          );
          results.push({
            ...deliveryContext,
            delivery_disposition: 'awaiting-sealed-gate',
            blocker_owner: 'ci',
            next_command: 'rerun-after-generated-delivery-seal-gate',
            status: 'delivery_sealed_checks_pending',
            gate_request: sealed.gateRequest,
            reviewer_settlement: settlement,
          });
          continue;
        }
        if (
          deliveryRecord.delivery_state !== 'sealed'
          || deliveryRecord.sealed_head_sha !== pr.head.sha
        ) {
          await restageStableDelivery({
            owner,
            repo,
            pr,
            record: deliveryRecord,
            dryRunMode: dryRun,
          });
          results.push({
            ...deliveryContext,
            delivery_disposition: dryRun
              ? 'awaiting-review-settlement'
              : 'awaiting-review-start',
            blocker_owner: 'maint-71',
            next_command: dryRun
              ? 'restage-changed-delivery-head'
              : 'rerun-with-auto-merge-to-start-review',
            status: dryRun ? 'sealed_head_mismatch' : 'delivery_review_not_started',
          });
          continue;
        }
        if (!integrationOnly) {
          // A legacy seal can predate the actual reviewer request. A timeout
          // without a request is not reviewer settlement, even on a green head.
          let sealedRequest;
          try {
            sealedRequest = await ensureExactHeadReviewRequest({
              owner, repo, pr, record: deliveryRecord, reviewerProfiles,
              withRetry, dryRunMode: true, allowUnready: true,
            });
          } catch (error) {
            rethrowPrimaryRateLimit(error);
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-review-settlement',
              blocker_owner: 'maint-71',
              next_command: `rerun-after:${new Date(Date.now() + 10 * 60 * 1000).toISOString()}`,
              status: 'reviewer_settlement_pending',
              reason: 'sealed_review_request_unconfirmed',
              error: String(error?.message || error),
            });
            continue;
          }
          // The request lookup reads the PR again; its readiness is newer than
          // the initial inventory snapshot used to enter this branch.
          const needsReadyRecovery = Boolean(sealedRequest?.draft || sealedRequest?.autoMerge);
          if (
            !sealedRequest
            || needsReadyRecovery
            || !Number.isFinite(Date.parse(deliveryRecord.review_started_at || ''))
            || Date.parse(deliveryRecord.review_started_at) < Date.parse(sealedRequest.requestedAt)
            || (deliveryRecord.review_evidence?.request_comment_id
              && deliveryRecord.review_evidence.request_comment_id !== sealedRequest.id)
          ) {
            const previousSeal = {
              sealed_at: deliveryRecord.sealed_at,
              sealed_head_sha: deliveryRecord.sealed_head_sha,
              review_evidence: deliveryRecord.review_evidence,
            };
            await restageStableDelivery({
              owner, repo, pr, record: deliveryRecord, dryRunMode: dryRun,
            });
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-review-start',
              blocker_owner: 'maint-71',
              next_command: dryRun
                ? 'rerun-with-auto-merge-to-restage-unrequested-seal'
                : 'rerun-with-auto-merge-to-start-review',
              status: dryRun ? 'dry_run_unrequested_seal' : 'delivery_review_not_started',
              reason: needsReadyRecovery ? 'sealed_hold_restaged' : 'unrequested_seal_restaged',
              previous_seal: previousSeal,
            });
            continue;
          }
        }
      }

      // A stable PR's own Gate intentionally rejects staging/reviewing
      // delivery records. Advance the bounded review lifecycle first, then
      // enforce the freshly triggered exact-head Gate once the record is
      // sealed. Legacy/hash and dev-tool lanes retain their original ordering.
      if (classification.status === 'checks_failed') {
        console.log('Failed checks:');
        failedChecks.forEach(c => console.log(`  - ${c.name}: ${c.conclusion}`));
        results.push({
          ...deliveryContext,
          status: 'checks_failed',
          failed_checks: failedChecks.map((check) => ({
            name: check.name,
            conclusion: check.conclusion,
            status: check.status,
          })),
        });
        continue;
      }
  
      if (classification.status === 'checks_pending') {
        console.log('Waiting for checks to complete');
        results.push({
          ...deliveryContext,
          status: 'checks_pending',
          pending_checks: pendingChecks.map((check) => ({
            name: check.name,
            conclusion: check.conclusion,
            status: check.status,
          })),
        });
        continue;
      }

      // Stable candidate PRs may advance from staging -> reviewing -> sealed
      // without pre-merge evidence. The evidence artifact authorizes only the
      // irreversible merge, so lifecycle progress cannot deadlock behind the
      // artifact that the sealed state is responsible for producing.
      if (!candidateEvidenceAllowsMutation({
        branch: pr.head.ref,
        evidenceOnly,
        authorized: candidateEvidenceAuthorized
          || prepareOnly
          || hasCampaignCommitAuthorization(campaignCommitAuthorization),
      })) {
        console.log('Candidate merge blocked: pre-merge evidence was not persisted successfully');
        results.push({
          ...deliveryContext,
          delivery_disposition: 'awaiting-canary-evidence',
          blocker_owner: 'maint-71',
          next_command: 'rerun-active-sync-hash-candidate',
          status: 'candidate_evidence_required',
        });
        continue;
      }

      if (
        requestedSyncHash === 'campaign'
        && !prepareOnly
        && !campaignAuthorizationAllowsMerge({
          authorization: campaignCommitAuthorization,
          result: deliveryContext,
        })
      ) {
        console.log('Campaign merge blocked: exact-head fleet authorization is missing or stale');
        results.push({
          ...deliveryContext,
          delivery_disposition: 'awaiting-campaign-authorization',
          blocker_owner: 'maint-71',
          next_command: 'rerun-active-sync-hash-campaign',
          status: 'campaign_authorization_required',
        });
        continue;
      }
  
      // All checks passed. For an actual merge, run the runtime AC guard before
      // the final exact-head/thread query so no intervening network action sits
      // between the hard review gate and the merge call.
      const mergeIntended = autoMerge && !dryRun && !recoveredMergedCandidate;
      const willMerge = mergeIntended && !prepareOnly;
      // Strict required-status-check rules evaluate the merge result. If the
      // head is behind main, every merge strategy creates a new result without
      // the head's Gate context. A leased generated delivery must be refreshed
      // by its producer: updateBranch would change the tree without reminting
      // the immutable desired-tree lease. Ordinary branches may still update.
      if (requiresStrictGateBranchUpdate({
        pr,
        requiredContexts,
        willMerge: mergeIntended,
      })) {
        try {
          if (stableDelivery) {
            await restageStableDelivery({
              owner,
              repo,
              pr,
              record: deliveryRecord,
              dryRunMode: false,
            });
            let promotionEvidence = null;
            if (metadata?.sync_phase === 'promote') {
              const { data: signedHead } = await withRetry((client) =>
                client.rest.repos.getCommit({
                  owner,
                  repo,
                  ref: pr.head.sha,
                }),
              );
              const verification = signedHead?.commit?.verification || {};
              promotionEvidence = parsePromotionEvidenceFromCommitMessage(
                signedHead?.commit?.message || '',
              );
              if (
                verification.verified !== true
                || verification.reason !== 'valid'
                || !promotionEvidence
              ) {
                results.push({
                  ...deliveryContext,
                  delivery_disposition: 'awaiting-promotion-evidence',
                  blocker_owner: 'maint-68',
                  next_command: 'rerun-phase-promote-from-original-evidence-artifact',
                  status: 'delivery_promotion_evidence_missing',
                });
                continue;
              }
            }
            results.push({
              ...deliveryContext,
              delivery_disposition: 'awaiting-base-refresh',
              blocker_owner: 'maint-68',
              next_command: metadata?.sync_phase === 'canary'
                ? 'dispatch-maint-68-phase-canary-no-filter'
                : 'rerun-maint-68-phase-promote-with-same-evidence',
              promotion_evidence: promotionEvidence,
              status: 'stable_base_refresh_required',
            });
            continue;
          }
          const devToolRefresh = devToolBaseRefreshResult(deliveryContext);
          if (devToolRefresh) {
            results.push(devToolRefresh);
            continue;
          }
          await withRetry((client) => client.rest.pulls.updateBranch({
            owner,
            repo,
            pull_number: pr.number,
            expected_head_sha: pr.head.sha,
          }));
          console.log(`Requested branch update for behind PR #${pr.number}; awaiting fresh Gate`);
          results.push({
            ...deliveryContext,
            delivery_disposition: 'awaiting-review-window',
            blocker_owner: 'maint-71',
            next_command: 'rerun-after-updated-branch-gate',
            status: 'review_window_pending',
            branch_update_started: true,
          });
        } catch (error) {
          rethrowPrimaryRateLimit(error);
          const message = String(error?.message || error);
          console.log(`Unable to update behind PR #${pr.number}: ${message}`);
          results.push({ ...deliveryContext, status: 'branch_update_failed', error: message });
        }
        continue;
      }
      if (willMerge) {
        try {
          await assertRuntimeAcMergeAllowed({
            github,
            core,
            owner,
            repo,
            prNumber: pr.number,
            withRetry,
            source: 'maint-71-merge-sync-prs',
            allowSealedSyncDelivery: stableDelivery,
          });
        } catch (guardError) {
          rethrowPrimaryRateLimit(guardError);
          const message = String(guardError?.message || guardError);
          console.log(`Runtime AC merge guard blocked PR #${pr.number}: ${message}`);
          results.push({
            ...deliveryContext,
            status: 'merge_blocked_runtime_ac',
            error: message,
          });
          continue;
        }
      }

      const finalGate = await confirmExactHeadReviewClear({
        owner,
        repo,
        pr,
        expectMerged: recoveredMergedCandidate,
        requireSealedDelivery: stableDelivery && !recoveredMergedCandidate,
        requireVerifiedHead: generatedDeliveryRequiresVerifiedHead(pr.head.ref),
        requireGeneratedDeliveryGate: !recoveredMergedCandidate,
      });
      adoptFinalCheckEvidence(deliveryContext, finalGate);
      if (!finalGate.ok) {
        console.log(`Final exact-head review gate blocked delivery: ${finalGate.reason}`);
        if (finalGate.reason === 'review_window_pending') {
          results.push({
            ...deliveryContext,
            delivery_disposition: 'awaiting-review-window',
            blocker_owner: 'maint-71',
            next_command: finalGate.reviewWindow?.eligible_at
              ? `rerun-after:${finalGate.reviewWindow.eligible_at}`
              : 'rerun-after-review-window',
            status: 'review_window_pending',
            review_window_eligible_at: finalGate.reviewWindow?.eligible_at || '',
          });
        } else if (finalGate.reason === 'review_blocked') {
          const reviewBlock = classifyReviewBlockedDisposition({
            activeReviewThreadCount: finalGate.activeReviewThreads,
            reviewThreads: finalGate.reviewThreads || [],
            manifestSources,
            reviewerProfiles,
            reviewPolicyLoaded,
          });
          results.push({
            ...deliveryContext,
            delivery_disposition: 'review-blocked',
            blocker_owner: reviewBlock?.blocker_owner || 'closer',
            next_command: reviewBlock?.next_command || (
              finalGate.activeReviewThreads < 0
                ? 'retry-review-thread-query'
                : 'resolve-active-review-threads'
            ),
            status: 'review_blocked',
            active_review_thread_count: finalGate.activeReviewThreads,
          });
        } else if (finalGate.reason === 'delivery_seal_changed') {
          results.push({
            ...deliveryContext,
            delivery_disposition: 'awaiting-review-settlement',
            blocker_owner: 'maint-71',
            next_command: 'restage-changed-delivery-record',
            status: 'sealed_head_mismatch',
            delivery_reason: finalGate.deliveryReason || 'delivery_seal_changed',
          });
        } else if (finalGate.reason === 'head_commit_unverified') {
          results.push({
            ...deliveryContext,
            delivery_disposition: 'unsigned-head-blocked',
            blocker_owner: 'maint-68',
            next_command: 'refresh-with-github-signed-sync-commit',
            status: 'head_commit_unverified',
            observed_head_sha: finalGate.freshHeadSha || '',
            signature_state: finalGate.signatureState || 'MISSING',
          });
        } else if (['checks_failed', 'checks_pending'].includes(finalGate.reason)) {
          const finalClassification = finalGate.finalCheckEvidence?.classification || {};
          results.push({
            ...deliveryContext,
            delivery_disposition: finalGate.reason === 'checks_failed'
              ? 'check-failed'
              : 'awaiting-checks',
            blocker_owner: 'consumer',
            next_command: finalGate.reason === 'checks_failed'
              ? 'repair-failing-gate'
              : 'rerun-after-gate-completes',
            status: finalGate.reason,
            failed_checks: (finalClassification.failed || []).map((check) => check.name),
            pending_checks: (finalClassification.pending || []).map((check) => check.name),
          });
        } else {
          results.push({
            ...deliveryContext,
            delivery_disposition: 'awaiting-exact-head',
            blocker_owner: 'maint-71',
            next_command: 'rerun-exact-head-gate',
            status: 'head_changed',
            observed_head_sha: finalGate.freshHeadSha || '',
            gate_reason: finalGate.reason,
          });
        }
        continue;
      }

      if (metadata?.sync_phase === 'canary' && metadata?.plan_id) {
        const sourceBinding = validateSourceDeltaEvidenceBinding({
          metadata,
          deliveryRecord,
          commitMessage: selectedHeadCommit?.message || '',
        });
        if (!sourceBinding.ok) {
          console.log(
            `Immutable source-delta binding failed: ${sourceBinding.errors.join(', ')}`,
          );
          results.push({
            ...deliveryContext,
            status: 'delivery_contract_blocked',
            delivery_disposition: 'source-binding-blocked',
            blocker_owner: 'maint-68',
            next_command: 'refresh-source-delta-delivery',
            source_binding_errors: sourceBinding.errors,
          });
          continue;
        }
        canaryEvidence.push({
          repo: `${owner}/${repo}`,
          plan_id: deliveryRecord.plan_id,
          plan_scope: metadata.plan_scope || 'full',
          scope_base_sha: metadata.scope_base_sha || '',
          source_commit: deliveryRecord.source_commit,
          pr: pr.number,
          head_sha: pr.head.sha,
          evidence_source: recoveredMergedCandidate
            ? 'merged-candidate-recovery'
            : 'open-candidate',
          required_check_state: 'success',
          active_review_thread_count: finalGate.activeReviewThreads,
        });
      }

      if (recoveredMergedCandidate) {
        console.log('✓ Recovered green, review-clear evidence from the merged candidate PR');
        results.push({
          ...deliveryContext,
          status: 'evidence_recovered',
          active_review_thread_count: finalGate.activeReviewThreads,
        });
        continue;
      }


      if (prepareOnly) {
        console.log('✓ Exact head prepared for campaign commit');
        results.push({
          ...deliveryContext,
          status: 'campaign_prepared',
          active_review_thread_count: finalGate.activeReviewThreads,
        });
        continue;
      }

      if (!autoMerge) {
        console.log('✓ Ready to merge (auto-merge disabled)');
        results.push({
          ...deliveryContext,
          status: 'ready',
          active_review_thread_count: finalGate.activeReviewThreads,
        });
        continue;
      }
  
      if (dryRun) {
        console.log('✓ Would merge (dry run)');
        results.push({
          ...deliveryContext,
          status: 'dry_run_merge',
          active_review_thread_count: finalGate.activeReviewThreads,
        });
        continue;
      }
  
      // Merge the PR. The final exact-head and live-thread query above is the
      // immediately preceding network gate for this exact head.
  
      try {
        const mergeMethods = ['merge', 'squash', 'rebase'];
        let merged = false;
        let lastError = null;
  
        for (const [methodIndex, merge_method] of mergeMethods.entries()) {
          try {
            if (methodIndex > 0) {
              const retryGate = await confirmExactHeadReviewClear({
                owner,
                repo,
                pr,
                expectMerged: false,
                requireSealedDelivery: stableDelivery,
                requireVerifiedHead: generatedDeliveryRequiresVerifiedHead(pr.head.ref),
                requireGeneratedDeliveryGate: true,
              });
              adoptFinalCheckEvidence(deliveryContext, retryGate);
              if (!retryGate.ok) {
                throw new Error(`merge retry gate blocked: ${retryGate.reason}`);
              }
            }
            await withRetry(
              (client) => client.rest.pulls.merge({
                owner,
                repo,
                pull_number: pr.number,
                sha: pr.head.sha,
                merge_method,
                commit_title: pr.title,
                commit_message:
                  `Automated merge of sync PR\n\n` +
                  `Sync hash: ${requestedSyncHash || metadata?.sync_hash || 'unknown'}\n` +
                  `Delivery generation: ${selection.deliveryRecord?.generation || 'unknown'}`
              }),
              { maxRetries: 0 },
            );
            console.log(`✓ Merged successfully (method=${merge_method})`);
            merged = true;
            break;
          } catch (e) {
            rethrowPrimaryRateLimit(e);
            lastError = e;
            const message = String(e?.message || 'unknown error');
            console.log(`⚠ Merge attempt failed (method=${merge_method}): ${message}`);
            if (!mergeMethodPolicyAllowsFallback(e, merge_method)) {
              break;
            }
          }
        }
  
        if (!merged) {
          throw lastError || new Error('Merge failed');
        }

        if (stableDelivery) {
          try {
            await withRetry((client) => client.rest.issues.addLabels({
              owner,
              repo,
              issue_number: pr.number,
              labels: ['sync:delivery-ready'],
            }));
            await withRetry((client) => client.rest.issues.removeLabel({
              owner,
              repo,
              issue_number: pr.number,
              name: 'sync:delivery-staging',
            }));
          } catch (labelError) {
            rethrowPrimaryRateLimit(labelError);
            core.notice(
              `Merged PR #${pr.number}, but final delivery-label cleanup failed: ` +
                `${labelError.message || labelError}`,
            );
          }
        }
  
        // Delete the branch
        try {
          await withRetry((client) => client.rest.git.deleteRef({
            owner,
            repo,
            ref: `heads/${pr.head.ref}`
          }));
          console.log('✓ Branch deleted');
          results.push({
            ...deliveryContext,
            status: 'branch_deleted',
          });
        } catch (e) {
          rethrowPrimaryRateLimit(e);
          console.log(`⚠ Could not delete branch: ${e.message}`);
          results.push({
            ...deliveryContext,
            status: 'branch_delete_failed',
            error: e.message,
          });
        }
  
        results.push({
          ...deliveryContext,
          status: 'merged',
        });
      } catch (e) {
        rethrowPrimaryRateLimit(e);
        console.log(`✗ Merge failed: ${e.message}`);
        results.push({
          ...deliveryContext,
          status: 'merge_failed',
          error: e.message,
        });
      }
    } catch (e) {
      console.log(`✗ Error processing ${repo}: ${e.message}`);
      results.push({ owner, repo, status: 'error', error: e.message });

      // A primary rate-limit error that reaches this outer catch is always
      // terminal: withRetry already tried token rotation and found no
      // alternative (see github-api-with-retry.js), so this credential is
      // exhausted for the remainder of the run. Stop instead of calling every
      // remaining repo with a token that is already known to fail.
      if (isPrimaryRateLimitExhausted(e)) {
        const deferredRepos = targetRepos.slice(repoIndex + 1);
        for (const deferredEntry of deferredRepos) {
          const [deferredOwner, deferredRepo] = deferredEntry.includes('/')
            ? deferredEntry.split('/')
            : [defaultOwner, deferredEntry];
          results.push({
            owner: deferredOwner || defaultOwner,
            repo: deferredRepo,
            status: 'deferred_rate_limit',
            error: 'Skipped: primary rate limit exhausted earlier in this run.',
          });
        }
        console.log(
          `✗ Primary rate limit exhausted; deferring ${deferredRepos.length} ` +
            'remaining repo(s) instead of calling them with an exhausted credential.',
        );
        break;
      }
    }
  }

  // Summary
  const canaryRefresh = await refreshStableCanaries({
    canaries: stableCanaries, withRetry, context, core, manifestEntries,
    enabled: autoMerge && !dryRun && !resolutionOnly && !evidenceOnly,
  });
  if (canaryRefresh.refresh_dispatched > 0) {
    // A no-filter refresh also services missing candidates discovered earlier
    // in this scan. Do not ask the workflow's legacy refresh step to dispatch
    // a second copy while the newly queued run becomes visible to the API.
    for (const result of results) {
      if (result.status === 'stable_base_refresh_required'
        && result.next_command === 'dispatch-maint-68-phase-canary-no-filter') {
        result.next_command = 'rerun-after-maint-68-canary-refresh';
      }
    }
  }
  console.log('\n=== Summary ===');
  console.log(JSON.stringify(results, null, 2));
  const report = buildMergeReport({
    results,
    registeredRepos,
    targetRepos,
    autoMerge,
    dryRun,
    syncHash: requestedSyncHash,
    run: {
      repository: `${context.repo.owner}/${context.repo.repo}`,
      run_id: context.runId,
      run_number: context.runNumber,
      workflow: context.workflow,
      ref: context.ref,
      sha: context.sha,
    },
  });
  const reportPath = process.env.SYNC_PR_MERGE_REPORT_JSON || 'artifacts/sync-pr-merge-report.json';
  report.canary_refresh = canaryRefresh;
  const canaryEvidencePath = 'artifacts/sync-canary-evidence.json';
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.mkdirSync(path.dirname(canaryEvidencePath), { recursive: true });
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  fs.writeFileSync(
    canaryEvidencePath,
    `${JSON.stringify({
      schema: 'workflows.consumer-sync-canary-evidence/v1',
      version: 1,
      results: canaryEvidence,
    }, null, 2)}\n`,
    'utf8',
  );
  const evidenceValidation = requestedSyncHash === 'candidate'
    ? validateCanaryEvidence(canaryEvidence, expectedCanaryRepos)
    : { ok: true, errors: [], plan_id: '' };
  if (evidenceOnly && !evidenceValidation.ok) {
    core.notice(
      `Canary evidence is incomplete or unsafe: ${evidenceValidation.errors.join(', ')}`,
    );
  }
  await core.summary.addRaw(buildMarkdownSummary(report)).write();
  if (!dryRun && !evidenceOnly && report.handoff_records.length > 0) {
    // Fleet-wide refresh: a targeted Maint 71 repos filter must not cause
    // Maint 82 to stale unscanned repos. Dispatch is best-effort so a
    // permissions/transient failure does not fail the reconciler run.
    try {
      await withRetry((client) => client.rest.repos.createDispatchEvent({
        owner: context.repo.owner,
        repo: context.repo.repo,
        event_type: 'sync-dependabot-campaign',
        client_payload: {
          repos: registeredRepos.join(','),
          delivery_handoff_records: report.handoff_records,
        },
      }));
    } catch (dispatchError) {
      if (report.results.some((result) =>
        result.status === 'dev_tool_base_refresh_required')) {
        throw new Error(
          `Maint 82 durable dev-tool base-refresh handoff failed: ${dispatchError.message}`,
        );
      }
      core.notice(
        `Maint 71 handoff dispatch failed (non-blocking): ${dispatchError.message}`,
      );
    }
  }
  
  const merged = report.summary.merged;
  const stale = report.summary.stale_closed;
  const branchesDeleted = report.summary.branch_deleted;
  // A consumer's own red CI (checks_failed) is outside this workflow's control,
  // so it must NOT fail the fleet janitor run — otherwise one red consumer turns
  // every scheduled flush red and forces re-runs. Only genuine sync-system action
  // failures (merge/cleanup/missing-target) are blocking; consumer CI health is
  // surfaced via the merge report and Health 68 instead.
  const blockingFailures = results.filter((result) =>
    isBlockingSyncSystemFailure(result.status),
  );
  const branchDeleteFailures = results.filter((r) => r.status === 'branch_delete_failed');
  if (branchDeleteFailures.length > 0) {
    core.notice(
      `${branchDeleteFailures.length} sync branch(es) could not be deleted; ` +
        'the next scheduled run retries the cleanup.',
    );
  }
  const checksFailed = results.filter((r) => r.status === 'checks_failed');
  if (checksFailed.length > 0) {
    core.notice(
      `${checksFailed.length} consumer sync PR(s) have failing checks (consumer CI); ` +
        `left open, not treated as a janitor failure.`,
    );
  }
  const failed = dryRun ? 0 : blockingFailures.length;
  const pending = report.summary.checks_pending;
  const ready = report.summary.ready;
  
  console.log(`\nMerged: ${merged}`);
  console.log(`Stale closed: ${stale}`);
  console.log(`Leftover branches deleted: ${branchesDeleted}`);
  console.log(`Failed: ${failed}`);
  console.log(`Pending: ${pending}`);
  console.log(`Ready (not auto-merged): ${ready}`);
  if (dryRun && blockingFailures.length > 0) {
    core.notice(
      `Dry run observed ${blockingFailures.length} blocking result(s); ` +
        'report-only mode remains successful.',
    );
  }
  
  if (failed > 0) {
    const blockingStatuses = [...new Set(blockingFailures.map((result) => result.status))];
    core.setFailed(
      `${failed} blocking sync-system failure(s): ${blockingStatuses.join(', ')}`,
    );
  }
}

module.exports = {
  STALE_CANARY_HOURS,
  canaryNeedsRefresh,
  isExpectedPresealGateFailure,
  refreshStableCanaries,
  routeCanaryReviewUpstream,
  buildCanaryPromotionEvidence,
  dispatchCanaryPromotion,
  reportSealedPromotionHealth,
  publishPromotionHealthCheck,
  sealedPromotionHealth,
  prepareIntegrationDelivery,
  requestSealedGate,
  independentVerificationDeliveryUnchanged,
  adoptFinalCheckEvidence,
  confirmedClosedPrIdentity,
  devToolBaseRefreshResult,
  campaignNoChangeRequiresLiveGate,
  collectReviewerEvidence,
  enforceGeneratedDeliveryRequiredContexts,
  ensureExactHeadReviewRequest,
  hasCompleteReviewThreadEvidence,
  hasExplicitSameHeadReviewerAcceptance,
  legacyStatusAsCheck,
  listMaint71PullRequests,
  mergeMethodPolicyAllowsFallback,
  normalizeReviewPolicy,
  nativeConversationBinding,
  nativeConversationMarker,
  acceptanceCommentLocation,
  parseReviewReassessmentRequest,
  readConsumerDeclaredContexts,
  reviewReassessmentMarker,
  runReviewReassessment,
  reviewRequestMarker,
  parseNoChangeEvidenceDocument,
  parseReviewResolutionProofs,
  run,
  selectReconciliationTargets,
  isResolvableProofThread,
  validateReviewResolutionProof,
};
