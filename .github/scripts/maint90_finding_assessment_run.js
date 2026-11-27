'use strict';

// Runtime for Maint 90 (see maint71_finding_assessment.js for the contract).
// discover: select held findings and plan assessments.
// publish:  turn assessment + regression artifacts into a verification record on
//           the durable issue and dispatch Maint 71 with the resolution proof.

const fs = require('node:fs');
const path = require('node:path');
const {
  collectFindingReviewState, validateIndependentFindingVerification,
} = require('./maint71_finding_verification');
const { validateReviewResolutionProof } = require('./maint71_merge_sync_prs');
const { parseDeliveryRecord } = require('./sync_pr_lease_contract');
const A = require('./maint71_finding_assessment');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

const ROOT = path.join(__dirname, '..', '..');
const ACTIVE = ['queued', 'in_progress', 'waiting', 'pending', 'requested'];
const MAX_ASSESSMENTS_PER_RUN = 3;
// After this many completed Maint 71 runs since the verification without the
// thread resolving, stop redispatching and hand the finding to its owner.
const MAX_REDISPATCH_RUNS = 2;

function loadPolicy() {
  const policy = JSON.parse(fs.readFileSync(path.join(ROOT, 'config/consumer_sync_review_policy.json'), 'utf8'));
  return { policy, profiles: policy.reviewers || [] };
}

function trustedPublishers(policy) {
  return policy.finding_verification_fallback?.trusted_publishers || [];
}

function durableIssueNumber(url) {
  const match = /^https:\/\/github\.com\/stranske\/Workflows\/issues\/([1-9]\d*)$/.exec(String(url || ''));
  return match ? Number(match[1]) : null;
}

async function listDurableComments(github, owner, repo, issueUrl, since) {
  const number = durableIssueNumber(issueUrl);
  if (!number) return [];
  return github.paginate(github.rest.issues.listComments, {
    owner, repo, issue_number: number, since, per_page: 100,
  });
}

async function maint71Runs(github, context) {
  const { data } = await github.rest.actions.listWorkflowRuns({
    ...context.repo, workflow_id: 'maint-71-merge-sync-prs.yml', per_page: 30,
  });
  return data.workflow_runs || [];
}

async function readSyncPr(github, owner, repo, number) {
  const { data } = await github.rest.pulls.get({ owner, repo, pull_number: number });
  return data;
}

async function liveCandidateState({ github, candidate, policy, profiles, now }) {
  const [owner, repo] = candidate.repository.split('/');
  const read = (fn) => fn(github);
  const state = await collectFindingReviewState({ owner, repo, number: candidate.pr, read });
  const record = parseDeliveryRecord(state.body || '');
  const { selected } = A.selectAssessableFindings({
    repository: candidate.repository, pr: candidate.pr, state, record, policy, profiles, now,
  });
  const live = selected.find((item) => A.findingKey(item) === A.findingKey(candidate));
  return { state, record, live, consumerSync: A.consumerSyncMarker(state.body || '') };
}

async function discover({ github: rawGithub, context, core, env = process.env, now = Date.now() }) {
  const github = await ensureRateLimitWrapped({ github: rawGithub, core, env });
  const { policy, profiles } = loadPolicy();
  const trusted = trustedPublishers(policy);
  const syncActors = String(env.TRUSTED_SYNC_ACTORS || '').split(',').map((s) => s.trim()).filter(Boolean);
  const repos = String(env.REGISTERED_REPOS || '').split(',').map((s) => s.trim()).filter(Boolean);
  const assess = [];
  const redispatch = [];
  const counts = { sync_prs: 0, unresolved_findings_with_request: 0, window_open: 0, answered: 0,
    no_current_head_request: 0, unknown_stock_summary: 0, assessable: 0, already_attempted: 0, verified_awaiting_maint71: 0 };
  for (const repository of repos) {
    const [owner, repo] = repository.split('/');
    let pulls;
    try {
      pulls = await github.paginate(github.rest.pulls.list, { owner, repo, state: 'open', per_page: 100 });
    } catch (error) {
      core.warning(`${repository}: cannot list pull requests (${error.status || error.message})`);
      continue;
    }
    for (const pull of pulls) {
      if (!String(pull.head?.ref || '').startsWith('sync/workflows-')
        || !syncActors.includes(pull.user?.login)) continue;
      const record = parseDeliveryRecord(pull.body || '');
      if (!record) continue;
      counts.sync_prs += 1;
      const state = await collectFindingReviewState({ owner, repo, number: pull.number, read: (fn) => fn(github) });
      const { selected, skipped } = A.selectAssessableFindings({
        repository, pr: pull.number, state, record, policy, profiles, now,
      });
      for (const item of skipped) {
        if (item.reason === 'reassessment_window_open') { counts.window_open += 1; counts.unresolved_findings_with_request += 1; }
        if (item.reason === 'originating_reviewer_answered') { counts.answered += 1; counts.unresolved_findings_with_request += 1; }
        if (item.reason === 'no_request_on_current_head') { counts.no_current_head_request += 1; counts.unresolved_findings_with_request += 1; }
        if (item.reason === 'unknown_stock_summary') {
          counts.unknown_stock_summary += 1; counts.unresolved_findings_with_request += 1;
          core.warning(`${repository}#${pull.number} ${item.thread_id}: unlisted stock cheer "${item.summary}"; `
            + 'add it to summary_variants in config/consumer_sync_review_policy.json');
        }
      }
      for (const candidate of selected) {
        counts.unresolved_findings_with_request += 1;
        const comments = await listDurableComments(github, context.repo.owner, context.repo.repo,
          candidate.durable_issue_url, candidate.first_requested_at);
        const prior = A.priorProducerRecords(comments, candidate, trusted);
        if (prior.attempts.length) { counts.already_attempted += 1; continue; }
        const fresh = prior.verifications.filter(({ verification }) =>
          now - Date.parse(verification.completed_at || '') < A.VERIFICATION_TTL_MS);
        if (fresh.length) {
          counts.verified_awaiting_maint71 += 1;
          const latest = fresh[fresh.length - 1];
          redispatch.push({ candidate, comment_url: latest.comment.html_url,
            comment_created_at: latest.comment.created_at, record: latest.verification });
          continue;
        }
        counts.assessable += 1;
        const { data: closed } = await github.rest.pulls.list({
          owner, repo, state: 'closed', base: pull.base.ref, sort: 'updated', direction: 'desc', per_page: 50,
        });
        const receiverPulls = closed.filter((item) => item.merged_at
          && Date.parse(item.merged_at) > Date.parse(candidate.finding_created_at)
          && item.number !== candidate.pr)
          .slice(0, 20)
          .map((item) => ({ number: item.number, title: item.title, merged_at: item.merged_at,
            base: item.base.ref, merge_commit_sha: item.merge_commit_sha }));
        assess.push({
          key: A.findingKey(candidate),
          slug: `${repo}-${candidate.pr}-${candidate.thread_id}`.replace(/[^A-Za-z0-9_-]/g, '-'),
          candidate, base_ref: pull.base.ref, receiver_pulls: receiverPulls,
          prompt: A.buildAssessmentPrompt(candidate, { baseRef: pull.base.ref, receiverPulls }),
        });
      }
    }
  }
  const matrix = assess.slice(0, MAX_ASSESSMENTS_PER_RUN);
  // Blocking and drainable together: held findings vs those this run can drain.
  const held = counts.unresolved_findings_with_request;
  const drainable = matrix.length + redispatch.length;
  core.notice(`Maint 90 findings held ${held}, drainable now ${drainable} `
    + `(assess ${matrix.length}/${counts.assessable}, redispatch ${redispatch.length}; `
    + `window open ${counts.window_open}, answered ${counts.answered}, `
    + `no current-head request ${counts.no_current_head_request}, unlisted stock cheer ${counts.unknown_stock_summary}, `
    + `handed to owner ${counts.already_attempted}; `
    + `sync PRs ${counts.sync_prs})`);
  core.setOutput('matrix', JSON.stringify({ item: matrix }));
  core.setOutput('has_assessments', matrix.length ? 'true' : 'false');
  core.setOutput('redispatch', JSON.stringify(redispatch));
  core.setOutput('has_work', drainable ? 'true' : 'false');
  return { matrix, redispatch, counts };
}

async function fixProvenance({ github, candidate, assessment, receiverPulls, baseRef }) {
  const [owner, repo] = candidate.repository.split('/');
  if (assessment.fix.kind === 'receiver') {
    const listed = (receiverPulls || []).find((item) => item.number === assessment.fix.pr);
    if (!listed) return { ok: false, reason: 'receiver_fix_not_offered' };
    const { data: fixPr } = await github.rest.pulls.get({ owner, repo, pull_number: assessment.fix.pr });
    if (fixPr.merged !== true || fixPr.merge_commit_sha !== listed.merge_commit_sha
      || fixPr.base?.ref !== baseRef || fixPr.base?.repo?.full_name !== candidate.repository
      || fixPr.head?.repo?.full_name !== candidate.repository) return { ok: false, reason: 'receiver_fix_provenance_unverified' };
    const { data: comparison } = await github.rest.repos.compareCommitsWithBasehead({
      owner, repo, basehead: `${fixPr.merge_commit_sha}...${candidate.head_sha}`,
    });
    if (comparison.status !== 'ahead' || comparison.behind_by !== 0) return { ok: false, reason: 'receiver_fix_not_in_head' };
    return { ok: true, receiverFix: { repository: candidate.repository, pr: fixPr.number,
      base_ref: baseRef, merge_sha: fixPr.merge_commit_sha } };
  }
  const { data: comparison } = await github.rest.repos.compareCommitsWithBasehead({
    owner: 'stranske', repo: 'Workflows', basehead: `${assessment.fix.sha}...${candidate.source_commit}`,
  });
  if (!['ahead', 'identical'].includes(comparison.status)) return { ok: false, reason: 'source_fix_not_in_delivery_source' };
  return { ok: true };
}

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; }
}

async function dispatchMaint71({ github, context, core, proof, consumerSync, dryRun }) {
  const runs = await maint71Runs(github, context);
  const active = runs.find((run) => ACTIVE.includes(run.status));
  if (active) {
    core.notice(`Maint 71 writer ${active.id} active; verification kept for the next Maint 90 sweep`);
    return false;
  }
  const inputs = A.buildMaint71Dispatch({ proof, consumerSync });
  if (dryRun) {
    core.notice(`Dry run: would dispatch Maint 71 ${inputs.active_sync_hash} with proof for ${proof.thread_id}`);
    return false;
  }
  await github.rest.actions.createWorkflowDispatch({
    ...context.repo, workflow_id: 'maint-71-merge-sync-prs.yml',
    ref: context.payload.repository?.default_branch || 'main', inputs,
  });
  core.notice(`Dispatched Maint 71 ${inputs.active_sync_hash} to resolve ${proof.repository}#${proof.pr} ${proof.thread_id}`);
  return true;
}

async function postComment({ github, context, issueUrl, body, dryRun, core }) {
  const number = durableIssueNumber(issueUrl);
  if (!number) throw new Error('durable_issue_url_invalid');
  if (dryRun) {
    core.notice(`Dry run: would comment on ${issueUrl}`);
    return { id: 1, html_url: `${issueUrl}#issuecomment-1`, created_at: new Date().toISOString(), body, user: { login: 'dry-run' } };
  }
  const { data } = await github.rest.issues.createComment({ ...context.repo, issue_number: number, body });
  return data;
}

async function publish({ github: rawGithub, context, core, env = process.env, now = Date.now() }) {
  const github = await ensureRateLimitWrapped({ github: rawGithub, core, env });
  const { policy, profiles } = loadPolicy();
  const dryRun = env.DRY_RUN === 'true';
  const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
  const publisher = env.PUBLISHER_LOGIN || 'stranske';
  const matrix = JSON.parse(env.MATRIX_JSON || '{"item":[]}').item || [];
  const redispatch = JSON.parse(env.REDISPATCH_JSON || '[]');
  const artifactRoot = env.ARTIFACT_ROOT || 'assessments';
  const outcomes = [];

  for (const item of matrix) {
    const { candidate } = item;
    const dir = path.join(artifactRoot, `assessment-${item.slug}`);
    const assessmentFile = readJson(path.join(dir, 'assessment.json'));
    const regression = readJson(path.join(artifactRoot, `regression-${item.slug}`, 'regression.json'));
    const rawOutput = fs.existsSync(path.join(dir, 'codex-output.md'))
      ? fs.readFileSync(path.join(dir, 'codex-output.md'), 'utf8') : '';
    const live = await liveCandidateState({ github, candidate, policy, profiles, now });
    if (!live.live) {
      outcomes.push({ key: item.key, outcome: 'no_longer_assessable' });
      continue;
    }
    const handOff = async (reason, rationale) => {
      await postComment({ github, context, core, dryRun, issueUrl: candidate.durable_issue_url,
        body: A.renderAttemptComment(candidate, { verdict: assessmentFile?.assessment?.verdict || 'NONE', reason, rationale, runUrl }) });
      outcomes.push({ key: item.key, outcome: `handed_to_owner:${reason}` });
    };
    if (!assessmentFile?.ok) { await handOff(assessmentFile?.reason || 'assessment_missing'); continue; }
    const { assessment } = assessmentFile;
    if (assessment.verdict !== 'PASS') { await handOff('verifier_fail', assessment.rationale); continue; }
    if (!A.regressionEstablished(regression)) {
      await handOff(regression?.reason || 'regression_not_established', assessment.rationale);
      continue;
    }
    const provenance = await fixProvenance({ github, candidate, assessment,
      receiverPulls: item.receiver_pulls, baseRef: item.base_ref });
    if (!provenance.ok) { await handOff(provenance.reason, assessment.rationale); continue; }
    const completedAt = regression.finished_at;
    const record = A.buildVerificationRecord({ candidate, assessment, regression,
      receiverFix: provenance.receiverFix, completedAt, rawOutput,
      verifierProfile: policy.finding_verification_fallback.verifier_profiles[0] });
    // Check the record with the production validators before publishing.
    const [owner, repo] = candidate.repository.split('/');
    const simulatedId = 1;
    const proof = A.buildResolutionProof({ record, commentUrl: `${candidate.durable_issue_url}#issuecomment-${simulatedId}` });
    const proofCheck = validateReviewResolutionProof(proof, { owner, repo, prNumber: candidate.pr,
      headSha: candidate.head_sha, actor: publisher, trustedActors: trustedPublishers(policy) });
    if (!proofCheck.ok) { await handOff(`proof_rejected:${proofCheck.errors.join(',')}`, assessment.rationale); continue; }
    const simulated = A.simulatedVerificationArgs({ candidate, record, proof, state: live.state,
      recordBinding: live.record, policy, profiles, commentId: simulatedId,
      createdAt: new Date(Math.max(now, Date.parse(completedAt) + 1000)).toISOString(), publisher });
    const check = validateIndependentFindingVerification(simulated);
    if (!check.ok) { await handOff(`verification_rejected:${check.reason}`, assessment.rationale); continue; }
    const comment = await postComment({ github, context, core, dryRun, issueUrl: candidate.durable_issue_url,
      body: A.renderVerificationComment(record, { runUrl }) });
    const realProof = A.buildResolutionProof({ record, commentUrl: comment.html_url });
    const dispatched = await dispatchMaint71({ github, context, core, proof: realProof,
      consumerSync: live.consumerSync, dryRun });
    outcomes.push({ key: item.key, outcome: dispatched ? 'verified_and_dispatched' : 'verified' });
  }

  for (const item of redispatch) {
    const { candidate, record } = item;
    const live = await liveCandidateState({ github, candidate, policy, profiles, now });
    if (!live.live) { outcomes.push({ key: A.findingKey(candidate), outcome: 'no_longer_assessable' }); continue; }
    const runs = await maint71Runs(github, context);
    const since = Date.parse(item.comment_created_at);
    const completedSince = runs.filter((run) => run.status === 'completed' && Date.parse(run.created_at) > since);
    if (completedSince.length >= MAX_REDISPATCH_RUNS) {
      await postComment({ github, context, core, dryRun, issueUrl: candidate.durable_issue_url,
        body: A.renderAttemptComment(candidate, { verdict: 'PASS', reason: 'maint71_did_not_resolve', runUrl }) });
      outcomes.push({ key: A.findingKey(candidate), outcome: 'handed_to_owner:maint71_did_not_resolve' });
      continue;
    }
    const proof = A.buildResolutionProof({ record, commentUrl: item.comment_url });
    const dispatched = await dispatchMaint71({ github, context, core, proof, consumerSync: live.consumerSync, dryRun });
    outcomes.push({ key: A.findingKey(candidate), outcome: dispatched ? 'redispatched' : 'redispatch_held' });
  }
  for (const outcome of outcomes) core.notice(`${outcome.key}: ${outcome.outcome}`);
  return outcomes;
}

module.exports = { discover, publish, fixProvenance, MAX_ASSESSMENTS_PER_RUN, MAX_REDISPATCH_RUNS };
