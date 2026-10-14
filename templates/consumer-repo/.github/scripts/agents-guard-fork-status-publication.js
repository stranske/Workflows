'use strict';

const GUARD_CONTEXT = 'Health 45 Agents Guard / guard';
const GUARD_PATH = '.github/workflows/agents-guard.yml';
const GUARD_JOB_NAMES = new Set(['guard']);
const ELIGIBILITY_STEP = 'Check event eligibility';
const EVALUATE_STEP = 'Evaluate protected file changes';
const BLOCKED_PREFIXES = [
  '.github/actions/',
  '.github/scripts/',
  '.github/workflows/',
];
const BLOCKED_FILES = new Set([
  '.github/path-classification.yml',
  'tools/post_ci_summary.py',
]);

function runSnapshot(run) {
  const attempt = Number(run?.run_attempt);
  if (!Number.isInteger(attempt) || attempt < 1) {
    throw new Error('Agents Guard run attempt is missing or invalid');
  }
  return {
    id: Number(run.id),
    workflowId: Number(run.workflow_id),
    headSha: run.head_sha,
    attempt,
    status: run.status,
    conclusion: run.conclusion ?? null,
  };
}

function assertRunUnchanged(snapshot, run) {
  const current = runSnapshot(run);
  for (const key of Object.keys(snapshot)) {
    if (current[key] !== snapshot[key]) {
      throw new Error(`Agents Guard run ${key} changed before publication`);
    }
  }
}

function collectChangedPaths(pr, files) {
  const expected = Number(pr?.changed_files);
  if (!Number.isInteger(expected) || expected < 0) {
    throw new Error('Pull request changed-file count is missing or invalid');
  }
  if (!Array.isArray(files) || files.length !== expected) {
    throw new Error(`Pull request changed-file evidence is incomplete (${files?.length ?? 'missing'}/${expected})`);
  }

  const filenames = new Set();
  const paths = [];
  for (const file of files) {
    const filename = typeof file?.filename === 'string' ? file.filename.trim() : '';
    if (!filename || filenames.has(filename)) {
      throw new Error('Pull request changed-file evidence is malformed or duplicated');
    }
    filenames.add(filename);
    paths.push(filename);
    if (file.status === 'renamed') {
      const previous = typeof file.previous_filename === 'string'
        ? file.previous_filename.trim()
        : '';
      if (!previous) throw new Error('Renamed file is missing previous_filename');
      paths.push(previous);
    } else if (typeof file.previous_filename === 'string' && file.previous_filename.trim()) {
      paths.push(file.previous_filename.trim());
    }
  }
  return paths;
}

function publicationState({ run, jobs, changedFiles }) {
  if (changedFiles.some(path => BLOCKED_FILES.has(path) || BLOCKED_PREFIXES.some(prefix => path.startsWith(prefix)))) {
    return { state: 'error', description: 'Agents Guard controls changed; trusted review required', evaluated: false };
  }
  if (run.status !== 'completed') {
    return { state: 'error', description: 'Agents Guard run is not completed', evaluated: false };
  }
  const guards = jobs.filter(job => GUARD_JOB_NAMES.has(job.name));
  if (jobs.length !== 1 || guards.length !== 1 || jobs.some(job => job.status !== 'completed')) {
    return { state: 'error', description: 'Agents Guard job set is missing or incomplete', evaluated: false };
  }
  const failed = new Set(['failure', 'cancelled', 'timed_out', 'action_required', 'startup_failure']);
  if (failed.has(run.conclusion) || jobs.some(job => failed.has(job.conclusion))) {
    return { state: 'failure', description: 'Trusted Agents Guard reported a failing job', evaluated: false };
  }
  const steps = Array.isArray(guards[0].steps) ? guards[0].steps : [];
  const eligibilitySteps = steps.filter(step => step?.name === ELIGIBILITY_STEP);
  const evaluateSteps = steps.filter(step => step?.name === EVALUATE_STEP);
  if (
    eligibilitySteps.length !== 1 ||
    eligibilitySteps[0].status !== 'completed' ||
    eligibilitySteps[0].conclusion !== 'success' ||
    evaluateSteps.length !== 1 ||
    evaluateSteps[0].status !== 'completed' ||
    !['success', 'skipped'].includes(evaluateSteps[0].conclusion)
  ) {
    return { state: 'error', description: 'Agents Guard evaluation evidence is missing or ambiguous', evaluated: false };
  }
  const evaluated = evaluateSteps[0].status === 'completed' && evaluateSteps[0].conclusion === 'success';
  const noOp = evaluateSteps[0].status === 'completed' && evaluateSteps[0].conclusion === 'skipped';
  if (run.conclusion === 'success' && guards[0].conclusion === 'success' && (evaluated || noOp)) {
    return { state: 'success', description: evaluated ? 'Trusted Agents Guard completed successfully' : 'Trusted Agents Guard was ineligible; preserving any existing verdict', evaluated };
  }
  return { state: 'error', description: 'Agents Guard conclusion is not an explicit success', evaluated: false };
}

async function paginate(retry, method, params) {
  return retry.paginateWithRetry(method, { ...params, per_page: 100 });
}

async function getFreshRun({ retry, owner, repo, runId }) {
  return (await retry.withRetry(client =>
    client.rest.actions.getWorkflowRun({ owner, repo, run_id: runId })
  )).data;
}

async function resolvePullRequest({ github, retry, owner, repo, run }) {
  const associated = Array.isArray(run.pull_requests) ? run.pull_requests : [];
  const associatedMatches = [];
  for (const item of associated) {
    if (!item || !Number(item.number)) continue;
    const pr = (await retry.withRetry(client =>
      client.rest.pulls.get({ owner, repo, pull_number: Number(item.number) })
    )).data;
    if (pr.state === 'open' && pr.head?.sha === run.head_sha) associatedMatches.push(pr);
  }
  if (associatedMatches.length === 1) return associatedMatches[0];
  if (associatedMatches.length > 1) {
    throw new Error(`Expected one associated open PR at Agents Guard head ${run.head_sha}; found ${associatedMatches.length}`);
  }

  const candidates = await paginate(retry, github.rest.pulls.list, { owner, repo, state: 'open' });
  const matches = candidates.filter(pr => pr.head?.sha === run.head_sha);
  if (matches.length !== 1) {
    throw new Error(`Expected one open PR at Agents Guard head ${run.head_sha}; found ${matches.length}`);
  }
  return (await retry.withRetry(client =>
    client.rest.pulls.get({ owner, repo, pull_number: matches[0].number })
  )).data;
}

function validateBinding({ run, workflow, pr, repository }) {
  if (run.event !== 'pull_request') throw new Error(`Unexpected Agents Guard event ${run.event}`);
  if (run.repository?.id !== repository.id) throw new Error('Agents Guard run repository does not match publisher repository');
  if (workflow.path !== GUARD_PATH || Number(workflow.id) !== Number(run.workflow_id) || run.name !== 'Health 45 Agents Guard') {
    throw new Error('Run is not the canonical Agents Guard workflow');
  }
  if (pr.state !== 'open') throw new Error('Pull request is no longer open');
  if (pr.base?.repo?.id !== repository.id) throw new Error('PR base repository does not match publisher repository');
  if (!repository.default_branch || pr.base?.ref !== repository.default_branch) {
    throw new Error('PR base is not the trusted default branch');
  }
  if (pr.head?.sha !== run.head_sha) throw new Error('PR head no longer matches Agents Guard head');
  if (!pr.head?.repo?.id || pr.head.repo.id === repository.id) throw new Error('Publisher only handles fork pull requests');
  if (Number(run.head_repository?.id) !== Number(pr.head.repo.id)) {
    throw new Error('Agents Guard head repository does not match pull request head repository');
  }
}

async function jobsForAttempt({ github, retry, owner, repo, run }) {
  const attempt = runSnapshot(run).attempt;
  if (!github.rest.actions.listJobsForWorkflowRunAttempt) {
    throw new Error('Attempt-bound Agents Guard jobs API is unavailable');
  }
  return paginate(retry, github.rest.actions.listJobsForWorkflowRunAttempt, {
    owner, repo, run_id: run.id, attempt_number: attempt,
  });
}

async function assertLatestAttempt({ github, retry, owner, repo, run }) {
  const runs = await paginate(retry, github.rest.actions.listWorkflowRuns, {
    owner, repo, workflow_id: run.workflow_id, event: 'pull_request', head_sha: run.head_sha,
  });
  const newer = runs.find(candidate =>
    candidate.id !== run.id &&
    (Number(candidate.run_number) > Number(run.run_number) ||
      (Number(candidate.run_number) === Number(run.run_number) && Number(candidate.run_attempt) > Number(run.run_attempt)))
  );
  if (newer) throw new Error(`Agents Guard run ${run.id} was superseded by ${newer.id}`);
}

async function publishGuardForkStatus({ github, context, core }) {
  const publisherAttempt = Number(process.env.GITHUB_RUN_ATTEMPT);
  if (!Number.isInteger(publisherAttempt) || publisherAttempt < 1) {
    throw new Error('Publisher run attempt is missing or invalid');
  }
  const payloadRun = context.payload.workflow_run;
  if (!payloadRun?.id) throw new Error('workflow_run id is required');
  const { owner, repo } = context.repo;
  const repository = context.payload.repository;

  // This privileged publisher deliberately uses only the workflow token. The
  // shared wrapper supplies bounded retry/backoff, while env:{} prevents PAT or
  // App credential rotation from widening this job's authority.
  const { createTokenAwareRetry } = require('./github-api-with-retry.js');
  const retry = await createTokenAwareRetry({
    github,
    core,
    env: {},
    task: 'agents-guard-fork-status-publication',
  });

  let run = await getFreshRun({ retry, owner, repo, runId: payloadRun.id });
  if (run.status !== 'completed') throw new Error('Agents Guard run is not completed');
  const workflow = (await retry.withRetry(client =>
    client.rest.actions.getWorkflow({ owner, repo, workflow_id: run.workflow_id })
  )).data;
  let pr = await resolvePullRequest({ github, retry, owner, repo, run });
  if (pr.head?.repo?.id === repository.id) {
    core.info(`PR #${pr.number} is not from a fork; the Agents Guard remains its status writer.`);
    return { state: 'skipped', description: 'Same-repository PR' };
  }
  validateBinding({ run, workflow, pr, repository });
  const evaluatedRun = runSnapshot(run);
  const evaluatedPr = {
    headSha: pr.head.sha,
    baseRepoId: pr.base.repo.id,
    baseRef: pr.base.ref,
    changedFiles: Number(pr.changed_files),
  };
  await assertLatestAttempt({ github, retry, owner, repo, run });

  const files = await paginate(retry, github.rest.pulls.listFiles, {
    owner, repo, pull_number: pr.number,
  });
  const changedPaths = collectChangedPaths(pr, files);
  const jobs = run.status === 'completed'
    ? await jobsForAttempt({ github, retry, owner, repo, run })
    : [];
  const result = publicationState({ run, jobs, changedFiles: changedPaths });

  // Pagination can outlive a rerun, so read statuses before the final binding
  // checks for both replay suppression and a new write.
  const statuses = await paginate(retry, github.rest.repos.listCommitStatusesForRef, {
    owner, repo, ref: pr.head.sha,
  });

  // Re-read both resources after pagination. A force-push or rerun between the
  // earlier inspection and this point must never bless a stale SHA.
  run = await getFreshRun({ retry, owner, repo, runId: payloadRun.id });
  pr = (await retry.withRetry(client =>
    client.rest.pulls.get({ owner, repo, pull_number: pr.number })
  )).data;
  validateBinding({ run, workflow, pr, repository });
  assertRunUnchanged(evaluatedRun, run);
  if (
    pr.head.sha !== evaluatedPr.headSha ||
    Number(pr.base?.repo?.id) !== Number(evaluatedPr.baseRepoId) ||
    pr.base?.ref !== evaluatedPr.baseRef ||
    Number(pr.changed_files) !== evaluatedPr.changedFiles
  ) {
    throw new Error('Pull request binding changed before publication');
  }
  await assertLatestAttempt({ github, retry, owner, repo, run });

  if (!Array.isArray(statuses)) throw new Error('Exact-head status inventory is incomplete');
  const existing = statuses.filter(status => status?.context === GUARD_CONTEXT);
  if (existing.some(status => !['success', 'failure', 'error', 'pending'].includes(status.state) || typeof status.target_url !== 'string')) {
    throw new Error('Exact-head guard status evidence is malformed');
  }
  const terminal = existing.filter(status => ['success', 'failure', 'error'].includes(status.state));
  // An ineligible completed pull_request run may establish a missing required
  // check, but must never replace a terminal verdict already recorded for this
  // head. A completed, step-proven evaluation is the only success allowed to do so.
  if (result.state === 'success' && result.evaluated === false && terminal.length > 0) {
    core.info(`Agents Guard preserves ${terminal.length} terminal exact-head verdict(s); no write needed.`);
    return result;
  }
  // listCommitStatusesForRef is newest-first. Only the latest status for this
  // context can suppress a replay: older attempts may share the same run URL.
  const current = existing[0];
  if (current?.state === result.state && current.target_url === run.html_url) {
    core.info(`Agents Guard status already ${result.state} for ${pr.head.sha}; no write needed.`);
    return result;
  }

  const published = await retry.withRetry(client => client.rest.repos.createCommitStatus({
      owner,
      repo,
      sha: pr.head.sha,
      state: result.state,
      context: GUARD_CONTEXT,
      description: result.description,
      target_url: run.html_url,
    }), { maxRetries: 0 });
  core.info('AGENTS_GUARD_FORK_STATUS_RECEIPT=' + JSON.stringify({
    schema: 'agents-guard-fork-status/v1',
    repository: `${owner}/${repo}`,
    head: pr.head.sha,
    pr: pr.number,
    guard_run_id: run.id,
    guard_run_attempt: run.run_attempt,
    publisher_run_id: context.runId,
    publisher_run_attempt: publisherAttempt,
    status_id: published.data.id,
  }));
  core.notice(`Published ${GUARD_CONTEXT}=${result.state} for fork PR #${pr.number} at ${pr.head.sha}.`);
  return result;
}

module.exports = {
  ELIGIBILITY_STEP,
  EVALUATE_STEP,
  GUARD_CONTEXT,
  GUARD_PATH,
  assertRunUnchanged,
  collectChangedPaths,
  publicationState,
  publishGuardForkStatus,
  runSnapshot,
  validateBinding,
};
