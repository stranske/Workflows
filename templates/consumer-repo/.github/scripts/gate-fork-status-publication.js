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

async function paginate(github, method, params) {
  return github.paginate(method, { ...params, per_page: 100 });
}

async function getFreshRun({ github, owner, repo, runId }) {
  return (await github.rest.actions.getWorkflowRun({ owner, repo, run_id: runId })).data;
}

async function resolvePullRequest({ github, owner, repo, run }) {
  const associated = Array.isArray(run.pull_requests) ? run.pull_requests : [];
  for (const item of associated) {
    if (!item || !Number(item.number)) continue;
    const pr = (await github.rest.pulls.get({ owner, repo, pull_number: Number(item.number) })).data;
    if (pr.state === 'open' && pr.head?.sha === run.head_sha) return pr;
  }

  const candidates = await paginate(github, github.rest.pulls.list, { owner, repo, state: 'open' });
  const matches = candidates.filter(pr => pr.head?.sha === run.head_sha);
  if (matches.length !== 1) {
    throw new Error(`Expected one open PR at Gate head ${run.head_sha}; found ${matches.length}`);
  }
  return (await github.rest.pulls.get({ owner, repo, pull_number: matches[0].number })).data;
}

function validateBinding({ run, workflow, pr, repository }) {
  if (run.event !== 'pull_request') throw new Error(`Unexpected Gate event ${run.event}`);
  if (run.repository?.id !== repository.id) throw new Error('Gate run repository does not match publisher repository');
  if (workflow.path !== GATE_PATH || run.name !== 'Gate') throw new Error('Run is not the canonical Gate workflow');
  if (pr.base?.repo?.id !== repository.id) throw new Error('PR base repository does not match publisher repository');
  if (pr.head?.sha !== run.head_sha) throw new Error('PR head no longer matches Gate head');
  if (!pr.head?.repo?.id || pr.head.repo.id === repository.id) throw new Error('Publisher only handles fork pull requests');
}

async function jobsForAttempt({ github, owner, repo, run }) {
  if (Number(run.run_attempt) > 0 && github.rest.actions.listJobsForWorkflowRunAttempt) {
    return paginate(github, github.rest.actions.listJobsForWorkflowRunAttempt, {
      owner, repo, run_id: run.id, attempt_number: run.run_attempt,
    });
  }
  return paginate(github, github.rest.actions.listJobsForWorkflowRun, { owner, repo, run_id: run.id });
}

async function assertLatestAttempt({ github, owner, repo, run }) {
  const runs = await paginate(github, github.rest.actions.listWorkflowRuns, {
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

  let run = await getFreshRun({ github, owner, repo, runId: payloadRun.id });
  const workflow = (await github.rest.actions.getWorkflow({ owner, repo, workflow_id: run.workflow_id })).data;
  let pr = await resolvePullRequest({ github, owner, repo, run });
  if (pr.head?.repo?.id === repository.id) {
    core.info(`PR #${pr.number} is not from a fork; the Gate summary remains its status writer.`);
    return { state: 'skipped', description: 'Same-repository PR' };
  }
  validateBinding({ run, workflow, pr, repository });
  await assertLatestAttempt({ github, owner, repo, run });

  const files = await paginate(github, github.rest.pulls.listFiles, {
    owner, repo, pull_number: pr.number,
  });
  const jobs = run.status === 'completed' ? await jobsForAttempt({ github, owner, repo, run }) : [];
  const result = publicationState({ run, jobs, changedFiles: files.map(file => file.filename) });

  // Re-read both resources immediately before the write. A force-push or rerun
  // between the earlier inspection and this point must never bless a stale SHA.
  run = await getFreshRun({ github, owner, repo, runId: payloadRun.id });
  pr = (await github.rest.pulls.get({ owner, repo, pull_number: pr.number })).data;
  validateBinding({ run, workflow, pr, repository });
  await assertLatestAttempt({ github, owner, repo, run });

  const statuses = await paginate(github, github.rest.repos.listCommitStatusesForRef, {
    owner, repo, ref: pr.head.sha,
  });
  const current = statuses.find(status => status.context === GATE_CONTEXT);
  if (current?.state === result.state && current?.target_url === run.html_url) {
    core.info(`Gate status already ${result.state} for ${pr.head.sha}; no write needed.`);
    return result;
  }
  await github.rest.repos.createCommitStatus({
    owner,
    repo,
    sha: pr.head.sha,
    state: result.state,
    context: GATE_CONTEXT,
    description: result.description,
    target_url: run.html_url,
  });
  core.notice(`Published ${GATE_CONTEXT}=${result.state} for fork PR #${pr.number} at ${pr.head.sha}.`);
  return result;
}

module.exports = { GATE_CONTEXT, GATE_PATH, publicationState, publishGateForkStatus, validateBinding };
