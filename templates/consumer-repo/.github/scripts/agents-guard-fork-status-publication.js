'use strict';

const crypto = require('crypto');

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
function routingLabelsFromRegistry(text) {
  // Parse only the canonical agents mapping, never execute registry contents.
  const labels = new Set(['agent:auto', 'agent:copilot', 'agents:auto-pilot', 'agents:keepalive']);
  const agents = new Map();
  let inAgents = false;
  let sections = 0;
  let key = null;
  let enabledSeen = false;
  for (const raw of String(text).split(/\r?\n/)) {
    const line = raw.replace(/\s+#.*$/, '').replace(/\s+$/, '');
    if (!line.trim() || line.trimStart().startsWith('#')) continue;
    if (line.includes('\t')) throw new Error('Agent registry tabs are unsupported');
    if (/^agents:\s*$/.test(line)) { inAgents = true; sections++; key = null; continue; }
    if (/^\S/.test(line)) { inAgents = false; key = null; continue; }
    if (!inAgents) continue;
    const entry = line.match(/^  ([a-z][a-z0-9_-]*):\s*$/);
    if (entry) {
      key = entry[1];
      if (agents.has(key)) throw new Error('Duplicate agent registry entry');
      agents.set(key, true);
      enabledSeen = false;
      continue;
    }
    if (/^  \S/.test(line) || !key) throw new Error('Malformed agent registry entry');
    if (/^    enabled:/.test(line)) {
      const value = line.match(/^    enabled:\s*(true|false)$/);
      if (!value || enabledSeen) throw new Error('Malformed agent enabled flag');
      enabledSeen = true;
      agents.set(key, value[1] === 'true');
    }
  }
  if (sections !== 1 || agents.size === 0) throw new Error('Agent registry mapping is incomplete');
  for (const [agent, enabled] of agents) if (enabled) labels.add(`agent:${agent}`);
  return labels;
}
const PERMISSION_LABEL = 'agents:allow-change';

function policyLabelNames(labels, routingLabels) {
  if (!Array.isArray(labels)) throw new Error('PR label evidence is incomplete');
  const names = labels.map(label => {
    if (typeof label?.name !== 'string') throw new Error('PR label evidence is malformed');
    const raw = label.name;
    const routing = raw.trim().toLowerCase();
    if (routingLabels.has(routing)) return routing;
    return raw.toLowerCase() === PERMISSION_LABEL ? PERMISSION_LABEL : '';
  }).filter(Boolean);
  return [...new Set(names)].sort();
}

function policyFingerprint(labels) {
  return crypto.createHash('sha256').update(labels.join('\n')).digest('hex');
}

function policyReceipt(labels, routingLabels) {
  return ` [guard-policy-sha256:${policyFingerprint(policyLabelNames(labels, routingLabels))}]`;
}

const POLICY_STEP_PREFIX = 'Evaluated policy labels sha256:';

function evaluatedPolicyFingerprint(jobs) {
  const guards = jobs.filter(job => GUARD_JOB_NAMES.has(job?.name));
  const receipts = guards.length === 1 && Array.isArray(guards[0].steps)
    ? guards[0].steps.filter(step => typeof step?.name === 'string' && step.name.startsWith(POLICY_STEP_PREFIX))
    : [];
  const receipt = receipts[0];
  const digest = receipt?.name.match(/^Evaluated policy labels sha256:([0-9a-f]{64})$/)?.[1];
  if (receipts.length !== 1 || !digest || receipt.status !== 'completed' || receipt.conclusion !== 'success') {
    throw new Error('Evaluated policy label receipt is missing or ambiguous');
  }
  return digest;
}

function prReceipt(prNumber) {
  if (!Number.isSafeInteger(Number(prNumber)) || Number(prNumber) <= 0) {
    throw new Error('Pull request number is missing or invalid');
  }
  return `[guard-pr:${Number(prNumber)}] `;
}

function hasCurrentReceipt(description, labels, prNumber, routingLabels) {
  return typeof description === 'string' &&
    description.startsWith(prReceipt(prNumber)) &&
    description.endsWith(policyReceipt(labels, routingLabels));
}

function withPolicyReceipt(description, labels, prNumber, routingLabels) {
  const prefix = prReceipt(prNumber);
  const receipt = policyReceipt(labels, routingLabels);
  const maximum = 140 - prefix.length - receipt.length;
  const summary = description.length > maximum
    ? `${description.slice(0, maximum - 3)}...`
    : description;
  return `${prefix}${summary}${receipt}`;
}

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
  if (!pr.head?.repo?.id) throw new Error('PR head repository is missing');
  if (Number(run.head_repository?.id) !== Number(pr.head.repo.id)) {
    throw new Error('Agents Guard head repository does not match pull request head repository');
  }
}

function targetRunId({ targetUrl, serverUrl, owner, repo }) {
  if (typeof targetUrl !== 'string') return null;
  try {
    const target = new URL(targetUrl);
    const server = new URL(serverUrl || 'https://github.com');
    const prefix = `/${owner}/${repo}/actions/runs/`;
    if (target.origin !== server.origin || !target.pathname.startsWith(prefix)) return null;
    const value = target.pathname.slice(prefix.length);
    return /^\d+$/.test(value) ? Number(value) : null;
  } catch {
    return null;
  }
}

async function canonicalDirectGuardStatus({ current, github, retry, owner, repo, repository, context }) {
  try {
    const runId = targetRunId({
      targetUrl: current.target_url,
      serverUrl: context.serverUrl,
      owner,
      repo,
    });
    if (!runId) return false;
    const directRun = await getFreshRun({ retry, owner, repo, runId });
    if (!directRun ||
      directRun.html_url !== current.target_url ||
      directRun.event !== 'pull_request_target' ||
      directRun.repository?.id !== repository.id ||
      directRun.name !== 'Health 45 Agents Guard'
    ) {
      return false;
    }
    const directWorkflow = (await retry.withRetry(client =>
      client.rest.actions.getWorkflow({ owner, repo, workflow_id: directRun.workflow_id })
    )).data;
    return directWorkflow.path === GUARD_PATH &&
      Number(directWorkflow.id) === Number(directRun.workflow_id);
  } catch {
    return null;
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
    Number(candidate.run_number) > Number(run.run_number) ||
      (Number(candidate.run_number) === Number(run.run_number) && Number(candidate.run_attempt) > Number(run.run_attempt))
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
  const workflow = (await retry.withRetry(client =>
    client.rest.actions.getWorkflow({ owner, repo, workflow_id: run.workflow_id })
  )).data;
  let pr = await resolvePullRequest({ github, retry, owner, repo, run });
  validateBinding({ run, workflow, pr, repository });
  if (!/^[0-9a-f]{40}$/.test(pr.base?.sha || '')) throw new Error('Trusted registry base SHA is missing');
  let routingLabels;
  let registryUnavailable = false;
  try {
    const registry = (await retry.withRetry(client => client.rest.repos.getContent({
      owner, repo, path: '.github/agents/registry.yml', ref: pr.base.sha,
    }))).data;
    if (registry?.type !== 'file' || registry.encoding !== 'base64') throw new Error('Agent registry evidence is incomplete');
    routingLabels = routingLabelsFromRegistry(Buffer.from(registry.content, 'base64').toString('utf8'));
  } catch {
    registryUnavailable = true;
  }
  const registryBaseSha = pr.base.sha;
  const sameRepository = pr.head.repo.id === repository.id;
  const evaluatedRun = runSnapshot(run);
  const evaluatedPr = {
    headSha: pr.head.sha,
    baseRepoId: pr.base.repo.id,
    baseRef: pr.base.ref,
    changedFiles: Number(pr.changed_files),
  };

  // Reconcile policy before reading or trusting the old guard result. This is
  // the only safe action a stale publisher may take.
  const statuses = await paginate(retry, github.rest.repos.listCommitStatusesForRef, {
    owner, repo, ref: pr.head.sha,
  });
  run = await getFreshRun({ retry, owner, repo, runId: payloadRun.id });
  pr = (await retry.withRetry(client =>
    client.rest.pulls.get({ owner, repo, pull_number: pr.number })
  )).data;
  validateBinding({ run, workflow, pr, repository });
  if (
    pr.head.sha !== evaluatedPr.headSha ||
    Number(pr.base?.repo?.id) !== Number(evaluatedPr.baseRepoId) ||
    pr.base?.ref !== evaluatedPr.baseRef || pr.base?.sha !== registryBaseSha
  ) {
    throw new Error('Pull request binding changed before policy reconciliation');
  }
  if (!Array.isArray(statuses)) throw new Error('Exact-head status inventory is incomplete');
  const existing = statuses.filter(status => status?.context === GUARD_CONTEXT);
  if (existing.some(status => !['success', 'failure', 'error', 'pending'].includes(status.state) || typeof status.target_url !== 'string')) {
    throw new Error('Exact-head guard status evidence is malformed');
  }
  const current = existing[0];
  let reconciliationFailure = false;
  let result;
  if (registryUnavailable) {
    // Trusted policy evidence cannot retain a prior green required context.
    // Re-read bindings and the latest producer attempt before this failure,
    // just as for an evaluated success; a stale publisher gets no write.
    assertRunUnchanged(evaluatedRun, run);
    await assertLatestAttempt({ github, retry, owner, repo, run });
    result = {
      state: 'failure',
      description: 'Trusted registry evidence unavailable; fresh evaluation required.',
      evaluated: false,
    };
    reconciliationFailure = true;
  }
  if (!registryUnavailable && current?.state === 'success' && (
    typeof current.description !== 'string' ||
    !hasCurrentReceipt(current.description, pr.labels, pr.number, routingLabels)
  )) {
    result = {
      state: 'failure',
      description: 'Health 45 Agents Guard policy changed; fresh evaluation required.',
      evaluated: false,
    };
    reconciliationFailure = true;
  }
  if (!reconciliationFailure && run.status !== 'completed') {
    throw new Error('Agents Guard run is not completed');
  }
  if (sameRepository && !reconciliationFailure) {
    core.info('Same-repository reconciliation preserves the current exact-head verdict.');
    return { state: 'skipped', description: 'Same-repository PR reconciliation' };
  }

  const directAuthority = !reconciliationFailure &&
    ['success', 'failure', 'error'].includes(current?.state)
    ? await canonicalDirectGuardStatus({ current, github, retry, owner, repo, repository, context })
    : false;
  const directSuccess = directAuthority === true && current.state === 'success' &&
    hasCurrentReceipt(current.description, pr.labels, pr.number, routingLabels);
  const directFailure = ['failure', 'error'].includes(current?.state) &&
    (directAuthority === true || directAuthority === null);
  if (directSuccess || directFailure) {
    core.info('Current direct guard verdict supersedes old fork result.');
    return { state: 'skipped', description: 'Current direct guard verdict preserved' };
  }

  if (!reconciliationFailure) {
    const files = await paginate(retry, github.rest.pulls.listFiles, {
      owner, repo, pull_number: pr.number,
    });
    const changedPaths = collectChangedPaths(pr, files);
    const jobs = run.status === 'completed'
      ? await jobsForAttempt({ github, retry, owner, repo, run })
      : [];
    result = publicationState({ run, jobs, changedFiles: changedPaths });

    // A force-push or rerun after file pagination must never bless a stale
    // success. Reconciliation failure above intentionally remains writable.
    run = await getFreshRun({ retry, owner, repo, runId: payloadRun.id });
    pr = (await retry.withRetry(client =>
      client.rest.pulls.get({ owner, repo, pull_number: pr.number })
    )).data;
    validateBinding({ run, workflow, pr, repository });
    assertRunUnchanged(evaluatedRun, run);
    if (
      pr.head.sha !== evaluatedPr.headSha ||
      Number(pr.base?.repo?.id) !== Number(evaluatedPr.baseRepoId) ||
      pr.base?.ref !== evaluatedPr.baseRef || pr.base?.sha !== registryBaseSha ||
      Number(pr.changed_files) !== evaluatedPr.changedFiles
    ) {
      throw new Error('Pull request binding changed before publication');
    }
    await assertLatestAttempt({ github, retry, owner, repo, run });
    if (result.state === 'success' && result.evaluated === true) {
      // Missing/ambiguous attempt metadata is a failed evaluation, not a
      // transport abort: replace any stale same-head success before returning.
      let evaluatedFingerprint;
      try {
        evaluatedFingerprint = evaluatedPolicyFingerprint(jobs);
      } catch {
        result = {
          state: 'failure',
          description: 'Evaluated policy receipt missing or ambiguous; fresh evaluation required.',
          evaluated: false,
        };
      }
      if (result.state === 'success' &&
          evaluatedFingerprint !== policyFingerprint(policyLabelNames(pr.labels, routingLabels))) {
        result = {
          state: 'failure',
          description: 'Evaluated policy labels differ from current policy; fresh evaluation required.',
          evaluated: false,
        };
      }
    }
    if (result.state === 'success') {
      result = { ...result, description: withPolicyReceipt(result.description, pr.labels, pr.number, routingLabels) };
    }
    if (result.state === 'success' && result.evaluated === false) {
      if (!current && policyLabelNames(pr.labels, routingLabels).some(label => routingLabels.has(label))) {
        result = {
          state: 'failure',
          description: 'Health 45 Agents Guard routing is now eligible; fresh evaluation required.',
          evaluated: false,
        };
      } else if (current) {
        // A fork no-op preserves a current terminal verdict. Current success was
        // already receipt-validated above; non-success remains authoritative.
        core.info('Fork no-op preserves existing exact-head guard verdict.');
        return result;
      }
    }
  }
  // Only the latest status for this context can suppress a replay.
  if (current?.state === result.state && current.target_url === run.html_url
      && current.description === result.description) {
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
  routingLabelsFromRegistry,
  ELIGIBILITY_STEP,
  EVALUATE_STEP,
  GUARD_CONTEXT,
  GUARD_PATH,
  assertRunUnchanged,
  evaluatedPolicyFingerprint,
  collectChangedPaths,
  publicationState,
  publishGuardForkStatus,
  runSnapshot,
  validateBinding,
};
