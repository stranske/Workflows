'use strict';

const GATE_CONTEXT = 'Gate / gate';
const GATE_PATH = '.github/workflows/pr-00-gate.yml';
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
    throw new Error('Gate run attempt is missing or invalid');
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
      throw new Error(`Gate run ${key} changed before publication`);
    }
  }
}

function collectChangedPaths(pr, files) {
  const expected = Number(pr?.changed_files);
  if (!Number.isInteger(expected) || expected < 0) {
    throw new Error('Pull request changed-file count is missing or invalid');
  }
  if (!Array.isArray(files) || files.length !== expected || files.length >= 3000) {
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
    return { state: 'error', description: 'Gate controls changed; trusted review required' };
  }
  if (run.status !== 'completed') {
    return { state: 'pending', description: 'Trusted Gate run is in progress' };
  }
  const summaries = jobs.filter(job => String(job.name || '').toLowerCase() === 'summary');
  if (summaries.length !== 1 || jobs.some(job => job.status !== 'completed')) {
    return { state: 'error', description: 'Gate job set is missing or incomplete' };
  }
  const failed = new Set(['failure', 'cancelled', 'timed_out', 'action_required', 'startup_failure']);
  if (run.conclusion === 'success' && summaries[0].conclusion === 'success' && !jobs.some(job => failed.has(job.conclusion))) {
    return { state: 'success', description: 'Trusted Gate completed successfully' };
  }
  if (failed.has(run.conclusion) || jobs.some(job => failed.has(job.conclusion))) {
    return { state: 'failure', description: 'Trusted Gate reported a failing job' };
  }
  return { state: 'error', description: 'Gate conclusion is not an explicit success' };
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
  for (const item of associated) {
    if (!item || !Number(item.number)) continue;
    const pr = (await retry.withRetry(client =>
      client.rest.pulls.get({ owner, repo, pull_number: Number(item.number) })
    )).data;
    if (pr.state === 'open' && pr.head?.sha === run.head_sha) return pr;
  }

  const candidates = await paginate(retry, github.rest.pulls.list, { owner, repo, state: 'open' });
  const matches = candidates.filter(pr => pr.head?.sha === run.head_sha);
  if (matches.length !== 1) {
    throw new Error(`Expected one open PR at Gate head ${run.head_sha}; found ${matches.length}`);
  }
  return (await retry.withRetry(client =>
    client.rest.pulls.get({ owner, repo, pull_number: matches[0].number })
  )).data;
}

function validateBinding({ run, workflow, pr, repository }) {
  if (run.event !== 'pull_request') throw new Error(`Unexpected Gate event ${run.event}`);
  if (run.repository?.id !== repository.id) throw new Error('Gate run repository does not match publisher repository');
  if (workflow.path !== GATE_PATH || Number(workflow.id) !== Number(run.workflow_id) || run.name !== 'Gate') {
    throw new Error('Run is not the canonical Gate workflow');
  }
  if (pr.state !== 'open') throw new Error('Pull request is no longer open');
  if (pr.base?.repo?.id !== repository.id) throw new Error('PR base repository does not match publisher repository');
  if (pr.head?.sha !== run.head_sha) throw new Error('PR head no longer matches Gate head');
  if (!pr.head?.repo?.id || pr.head.repo.id === repository.id) throw new Error('Publisher only handles fork pull requests');
  if (Number(run.head_repository?.id) !== Number(pr.head.repo.id)) {
    throw new Error('Gate head repository does not match pull request head repository');
  }
}

async function jobsForAttempt({ github, retry, owner, repo, run }) {
  const attempt = runSnapshot(run).attempt;
  if (!github.rest.actions.listJobsForWorkflowRunAttempt) {
    throw new Error('Attempt-bound Gate jobs API is unavailable');
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
  if (newer) throw new Error(`Gate run ${run.id} was superseded by ${newer.id}`);
}

async function publishGateForkStatus({ github, context, core }) {
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
    task: 'gate-fork-status-publication',
  });

  let run = await getFreshRun({ retry, owner, repo, runId: payloadRun.id });
  const workflow = (await retry.withRetry(client =>
    client.rest.actions.getWorkflow({ owner, repo, workflow_id: run.workflow_id })
  )).data;
  let pr = await resolvePullRequest({ github, retry, owner, repo, run });
  if (pr.head?.repo?.id === repository.id) {
    core.info(`PR #${pr.number} is not from a fork; the Gate summary remains its status writer.`);
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

  const statuses = await paginate(retry, github.rest.repos.listCommitStatusesForRef, {
    owner, repo, ref: pr.head.sha,
  });
  const current = statuses.find(status => status.context === GATE_CONTEXT);
  if (current?.state === result.state && current?.target_url === run.html_url) {
    core.info(`Gate status already ${result.state} for ${pr.head.sha}; no write needed.`);
    return result;
  }

  // Re-read both resources immediately before the write. A force-push or rerun
  // between the earlier inspection and this point must never bless a stale SHA.
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

  await retry.withRetry(client => client.rest.repos.createCommitStatus({
      owner,
      repo,
      sha: pr.head.sha,
      state: result.state,
      context: GATE_CONTEXT,
      description: result.description,
      target_url: run.html_url,
    }), { maxRetries: 0 });
  core.notice(`Published ${GATE_CONTEXT}=${result.state} for fork PR #${pr.number} at ${pr.head.sha}.`);
  return result;
}

module.exports = {
  GATE_CONTEXT,
  GATE_PATH,
  assertRunUnchanged,
  collectChangedPaths,
  publicationState,
  publishGateForkStatus,
  runSnapshot,
  validateBinding,
};
