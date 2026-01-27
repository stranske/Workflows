'use strict';

const { setTimeout: sleep } = require('timers/promises');
const { createKeepaliveStateManager } = require('./keepalive_state.js');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

const AGENT_LABEL_PREFIX = 'agent:';
const MERGE_METHODS = new Set(['merge', 'squash', 'rebase']);


function normalise(value) {
  return String(value ?? '').trim();
}

function normaliseLower(value) {
  return normalise(value).toLowerCase();
}

function parseBoolean(value, fallback = false) {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  const lowered = normaliseLower(value);
  if (!lowered) {
    return fallback;
  }
  if (['true', '1', 'yes', 'on'].includes(lowered)) {
    return true;
  }
  if (['false', '0', 'no', 'off'].includes(lowered)) {
    return false;
  }
  return fallback;
}

function parseCommaList(value) {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value
      .map((entry) => normaliseLower(typeof entry === 'string' ? entry : entry?.login || entry?.name))
      .filter(Boolean);
  }
  if (typeof value !== 'string') {
    return [];
  }
  return value
    .split(/[\s,]+/)
    .map((entry) => normaliseLower(entry))
    .filter(Boolean);
}

function clampMergeMethod(method, fallback = 'squash') {
  const candidate = normaliseLower(method);
  if (MERGE_METHODS.has(candidate)) {
    return candidate;
  }
  if (candidate === 'ff' || candidate === 'fast-forward' || candidate === 'fastforward') {
    return 'merge';
  }
  return fallback;
}

function toTimestamp(value) {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return parsed;
}

async function delay(ms) {
  const value = Number(ms);
  const timeout = Number.isFinite(value) && value > 0 ? value : 0;
  await sleep(timeout);
}

function parseNumber(value, fallback, { min = Number.NEGATIVE_INFINITY } = {}) {
  if (value === null || value === undefined) {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < min) {
    return fallback;
  }
  return parsed;
}

function computeIdempotencyKey(prNumber, round, trace) {
  const safeTrace = normalise(trace) || 'trace-missing';
  const safeRound = normalise(round) || '?';
  const safePr = Number.isFinite(prNumber) ? String(prNumber) : normalise(prNumber) || '?';
  return `${safePr}/${safeRound}#${safeTrace}`;
}

async function loadPull({ github, owner, repo, prNumber }) {
  const { data } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
  return {
    headSha: data?.head?.sha || '',
    headRef: data?.head?.ref || '',
    headRepo: data?.head?.repo?.full_name || '',
    baseRepo: data?.base?.repo?.full_name || `${owner}/${repo}`,
    baseRef: data?.base?.ref || '',
    userLogin: data?.user?.login || '',
    raw: data,
  };
}

async function listLabels({ github, owner, repo, prNumber }) {
  const response = await github.rest.issues.listLabelsOnIssue({
    owner,
    repo,
    issue_number: prNumber,
    per_page: 100,
  });
  return Array.isArray(response?.data) ? response.data : [];
}

function extractLabelNames(labels) {
  if (!Array.isArray(labels)) {
    return [];
  }
  return labels
    .map((entry) => {
      if (!entry) {
        return '';
      }
      if (typeof entry === 'string') {
        return normaliseLower(entry);
      }
      if (typeof entry.name === 'string') {
        return normaliseLower(entry.name);
      }
      return '';
    })
    .filter(Boolean);
}

function extractAgentAliasFromLabels(labels, fallback) {
  const names = extractLabelNames(labels);
  for (const name of names) {
    if (name.startsWith(AGENT_LABEL_PREFIX)) {
      const alias = normalise(name.slice(AGENT_LABEL_PREFIX.length));
      if (alias) {
        return alias;
      }
    }
  }
  return normalise(fallback) || 'codex';
}

function parseAgentState(env = {}) {
  const response = {
    value: '',
    done: false,
  };

  const jsonCandidate = normalise(env.AGENT_STATE_JSON);
  if (jsonCandidate && /^[{[]/.test(jsonCandidate)) {
    try {
      const parsed = JSON.parse(jsonCandidate);
      if (typeof parsed?.value === 'string') {
        response.value = normalise(parsed.value);
      }
      if (typeof parsed?.done === 'boolean') {
        response.done = parsed.done;
      } else if (typeof parsed?.status === 'string') {
        const lower = normaliseLower(parsed.status);
        response.done = lower === 'done' || lower === 'completed' || lower === 'complete';
        if (!response.value) {
          response.value = normalise(parsed.status);
        }
      }
    } catch (error) {
      // fall through to other inputs when JSON parsing fails
    }
  }

  if (!response.value) {
    const valueOrder = [env.AGENT_STATE, env.AGENT_STATUS, env.AGENT_DONE];
    for (const candidate of valueOrder) {
      const normalised = normalise(candidate);
      if (normalised) {
        response.value = normalised;
        break;
      }
    }
  }

  if (!response.done) {
    const lower = normaliseLower(response.value);
    if (lower) {
      response.done = ['done', 'complete', 'completed', 'success', 'true', 'yes'].includes(lower);
    }
  }

  return response;
}

async function pollForHeadChange({ fetchHead, initialSha, timeoutMs, intervalMs, label, core }) {
  const start = Date.now();
  let attempts = 0;
  let lastSha = initialSha;

  while (Date.now() - start <= timeoutMs) {
    attempts += 1;
    try {
      const { headSha } = await fetchHead();
      if (headSha) {
        lastSha = headSha;
      }
      if (headSha && headSha !== initialSha) {
        return { changed: true, headSha, attempts, elapsedMs: Date.now() - start };
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      core?.warning?.(`Failed to poll head during ${label || 'poll'}: ${message}`);
    }

    if (Date.now() - start >= timeoutMs) {
      break;
    }

    await delay(intervalMs);
  }

  return { changed: false, headSha: lastSha, attempts, elapsedMs: Date.now() - start };
}

function buildSummaryRecorder(summary) {
  const rows = [];
  const record = (step, outcome) => {
    rows.push([step, outcome]);
  };

  const flush = async (heading) => {
    if (!summary) {
      return rows;
    }
    summary
      .addHeading(heading)
      .addTable([
        [
          { data: 'Step', header: true },
          { data: 'Outcome', header: true },
        ],
        ...rows.map(([step, outcome]) => [step, outcome]),
      ]);
    await summary.write();
    return rows;
  };

  return { record, flush, rows };
}

function buildSyncSummaryLabel(trace) {
  const safeTrace = normalise(trace) || 'trace-missing';
  return `Keepalive sync (${safeTrace})`;
}

function isForkPull(initialInfo) {
  const forkFlag = initialInfo?.raw?.head?.repo?.fork;
  if (typeof forkFlag === 'boolean') {
    return forkFlag;
  }

  const headRepo = normaliseLower(initialInfo?.headRepo);
  const baseRepo = normaliseLower(initialInfo?.baseRepo);
  if (headRepo && baseRepo && headRepo !== baseRepo) {
    return true;
  }

  return Boolean(forkFlag);
}




function mergeStateShallow(target, updates) {
  if (!updates || typeof updates !== 'object') {
    return target;
  }
  const next = { ...target };
  for (const [key, value] of Object.entries(updates)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      next[key] = mergeStateShallow(target[key] && typeof target[key] === 'object' ? target[key] : {}, value);
    } else {
      next[key] = value;
    }
  }
  return next;
}

function parseRoundNumber(value) {
  const parsed = Number(value);
  if (Number.isFinite(parsed) && parsed > 0) {
    return Math.round(parsed);
  }
  const fallback = Number(String(value || '').trim().replace(/[^0-9]/g, ''));
  if (Number.isFinite(fallback) && fallback > 0) {
    return Math.round(fallback);
  }
  return 0;
}

async function dispatchCommand({
  github,
  owner,
  repo,
  eventType,
  action,
  prNumber,
  agentAlias,
  baseRef,
  headRef,
  headSha,
  trace,
  round,
  commentInfo,
  idempotencyKey,
  roundTag = 'round=?',
  record,
}) {
  const safeEvent = normalise(eventType) || 'codex-pr-comment-command';
  if (!safeEvent) {
    record(`Dispatch ${action}`, `skipped: event type missing ${roundTag}`);
    return false;
  }
  if (!github?.rest?.repos?.createDispatchEvent) {
    record(`Dispatch ${action}`, `skipped: GitHub client missing createDispatchEvent ${roundTag}`);
    return false;
  }

  // GitHub repository_dispatch limits client_payload to 10 top-level properties.
  // Nest auxiliary data under `meta` to stay within the limit while preserving
  // backward compatibility by keeping core routing properties at the top level.
  const meta = {
    trace: trace || '',
    round: parseRoundNumber(round) || 0,
  };
  if (commentInfo?.id) {
    meta.comment_id = Number(commentInfo.id);
  }
  if (commentInfo?.url) {
    meta.comment_url = commentInfo.url;
  }
  if (idempotencyKey) {
    meta.idempotency_key = idempotencyKey;
  }

  const payload = {
    issue: Number.isFinite(prNumber) ? Number(prNumber) : parseNumber(prNumber, 0, { min: 0 }),
    action,
    agent: agentAlias || 'codex',
    base: baseRef || '',
    head: headRef || '',
    head_sha: headSha || '',
    meta,
    quiet: true,
    reply: 'none',
  };

  try {
    await github.rest.repos.createDispatchEvent({
      owner,
      repo,
      event_type: safeEvent,
      client_payload: payload,
    });
    record(`Dispatch ${action}`, `sent action=${action} ${roundTag}`);
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    record(`Dispatch ${action}`, `failed: ${message} ${roundTag}`);
    return false;
  }
}

async function dispatchFallbackWorkflow({
  github,
  owner,
  repo,
  baseRef,
  dispatchRef,
  prNumber,
  headRef,
  headSha,
  headRepo,
  headIsFork,
  trace,
  round,
  agentAlias,
  commentInfo,
  idempotencyKey,
  roundTag = 'round=?',
  record,
}) {
  if (!baseRef || !headRef || !headSha) {
    record('Fallback dispatch', `skipped: base/head/head_sha missing. ${roundTag}`);
    return { dispatched: false };
  }
  try {
    const inputs = {
      pr_number: String(prNumber),
      trace: trace || '',
      base_ref: baseRef,
      head_ref: headRef,
      head_sha: headSha,
    };
    if (headRepo) {
      inputs.head_repository = headRepo;
    }
    if (typeof headIsFork === 'boolean') {
      inputs.head_is_fork = headIsFork ? 'true' : 'false';
    }
    if (agentAlias) {
      inputs.agent = agentAlias;
    }
    if (round) {
      inputs.round = String(round);
    }
    if (idempotencyKey) {
      inputs.idempotency_key = idempotencyKey;
    }

    const response = await github.rest.actions.createWorkflowDispatch({
      owner,
      repo,
      workflow_id: 'agents-keepalive-branch-sync.yml',
      ref: dispatchRef || baseRef,
      inputs,
    });

    record(
      'Fallback dispatch',
      `dispatched=keepalive-branch-sync http=${response?.status ?? 0} trace=${trace || 'missing'} ${roundTag}`,
    );
    return {
      dispatched: true,
      status: response?.status ?? 0,
      dispatchedAt: new Date().toISOString(),
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    record('Fallback dispatch', `failed: ${message} ${roundTag}`);
    return { dispatched: false, error: message };
  }
}

async function findFallbackRun({ github, owner, repo, createdAfter, existingRunId, core }) {
  if (!github?.rest?.actions?.listWorkflowRuns) {
    return null;
  }
  try {
    const response = await github.rest.actions.listWorkflowRuns({
      owner,
      repo,
      workflow_id: 'agents-keepalive-branch-sync.yml',
      event: 'workflow_dispatch',
      per_page: 20,
    });
    const runs = response?.data?.workflow_runs || [];
    const threshold = createdAfter ? new Date(createdAfter).getTime() - 5000 : 0;
    for (const run of runs) {
      if (existingRunId && Number(run?.id) === Number(existingRunId)) {
        return run;
      }
      const created = new Date(run?.created_at || run?.run_started_at || 0).getTime();
      if (!createdAfter || (Number.isFinite(created) && created >= threshold)) {
        return run;
      }
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    core?.warning?.(`Failed to locate keepalive branch-sync run: ${message}`);
  }
  return null;
}

function buildAutomationLoginSet(value, fallback = []) {
  const list = parseCommaList(value);
  if (!list.length && Array.isArray(fallback) && fallback.length) {
    return new Set(parseCommaList(fallback));
  }
  return new Set(list);
}

function containsTrace(text, trace) {
  if (!text || !trace) {
    return false;
  }
  const haystack = normaliseLower(text);
  const needle = normaliseLower(trace);
  if (!haystack || !needle) {
    return false;
  }
  return haystack.includes(needle);
}

function scoreConnectorPr(pr, { trace, baseRef }) {
  let score = 0;
  if (!pr || typeof pr !== 'object') {
    return score;
  }
  if (containsTrace(pr.title, trace)) {
    score += 4;
  }
  if (containsTrace(pr.body, trace)) {
    score += 3;
  }
  const headRef = normaliseLower(pr.head?.ref);
  if (headRef && trace && headRef.includes(normaliseLower(trace))) {
    score += 2;
  }
  if (headRef && baseRef && headRef.includes(normaliseLower(baseRef))) {
    score += 1;
  }
  const createdAt = toTimestamp(pr.created_at || pr.updated_at || pr.closed_at);
  if (Number.isFinite(createdAt) && createdAt > 0) {
    score += 0.000001 * createdAt;
  }
  return score;
}

async function locateConnectorPullRequest({
  github,
  owner,
  repo,
  baseRef,
  trace,
  createdAfter,
  allowedLogins,
}) {
  if (!github?.rest?.pulls?.list) {
    return null;
  }
  try {
    const response = await github.rest.pulls.list({
      owner,
      repo,
      state: 'open',
      base: baseRef,
      sort: 'created',
      direction: 'desc',
      per_page: 50,
    });
    const pulls = Array.isArray(response?.data) ? response.data : [];
    if (!pulls.length) {
      return null;
    }
    const allowed = allowedLogins instanceof Set ? allowedLogins : new Set();
    const threshold = createdAfter ? createdAfter - 30_000 : 0;
    let candidate = null;
    let candidateScore = Number.NEGATIVE_INFINITY;
    for (const pr of pulls) {
      const created = toTimestamp(pr.created_at || pr.updated_at);
      if (threshold && created && created < threshold) {
        break;
      }
      const login = normaliseLower(pr.user?.login);
      if (allowed.size && (!login || !allowed.has(login))) {
        continue;
      }
      const score = scoreConnectorPr(pr, { trace, baseRef });
      if (candidate === null || score > candidateScore) {
        candidate = pr;
        candidateScore = score;
      }
    }
    return candidate;
  } catch (error) {
    return null;
  }
}

async function mergeConnectorPullRequest({
  github,
  owner,
  repo,
  baseRef,
  trace,
  dispatchTimestamp,
  allowedLogins,
  mergeMethod,
  deleteBranch,
  record,
  appendRound,
}) {
  const createdAfter = dispatchTimestamp ? toTimestamp(dispatchTimestamp) : 0;
  const pr = await locateConnectorPullRequest({
    github,
    owner,
    repo,
    baseRef,
    trace,
    createdAfter,
    allowedLogins,
  });
  if (!pr) {
    record('Create-pr auto-merge', appendRound('no connector PR detected.'));
    return { attempted: true, merged: false };
  }

  const prNumber = Number(pr.number);
  const prUrl = normalise(pr?.html_url);
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    record('Create-pr auto-merge', appendRound('skipped: invalid PR identifier.'));
    return { attempted: true, merged: false, prUrl };
  }

  try {
    await github.rest.pulls.merge({
      owner,
      repo,
      pull_number: prNumber,
      merge_method: mergeMethod,
      commit_title: `Keepalive sync ${trace || ''}`.trim(),
    });
    record('Create-pr auto-merge', appendRound(`merged PR #${prNumber} using ${mergeMethod}.`));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    record('Create-pr auto-merge', appendRound(`failed: ${message}`));
    return { attempted: true, merged: false, prNumber, error: message, prUrl };
  }

  let branchDeleted = false;
  if (deleteBranch && pr.head?.ref && !pr.head?.repo?.fork) {
    try {
      await github.rest.git.deleteRef({
        owner,
        repo,
        ref: `heads/${pr.head.ref}`,
      });
      branchDeleted = true;
      record('Create-pr cleanup', appendRound(`deleted branch ${pr.head.ref}.`));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      record('Create-pr cleanup', appendRound(`failed to delete branch ${pr.head.ref}: ${message}`));
    }
  }

  return { attempted: true, merged: true, prNumber, branchDeleted, prUrl };
}

function formatCommandBody(action, trace, round) {
  const parts = [`/${normalise(action)}`.trim()];
  if (trace) {
    parts.push(`trace:${trace}`);
  }
  if (round) {
    parts.push(`round:${round}`);
  }
  return parts.filter(Boolean).join(' ');
}

async function postCommandComment({
  github,
  owner,
  repo,
  prNumber,
  action,
  trace,
  round,
  record,
  appendRound,
}) {
  const body = formatCommandBody(action, trace, round);
  try {
    const { data } = await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: prNumber,
      body,
    });
    const commentId = data?.id ? Number(data.id) : 0;
    record('Comment command', appendRound(`posted ${body}.`));
    if (commentId > 0) {
      try {
        await github.rest.reactions.createForIssueComment({
          owner,
          repo,
          comment_id: commentId,
          content: 'eyes',
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        record('Comment reaction', appendRound(`failed to add 👀: ${message}`));
      }
    }
    return {
      posted: true,
      body,
      commentId,
      commentUrl: data?.html_url || '',
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    record('Comment command', appendRound(`failed to post ${body}: ${message}`));
    return { posted: false, error: message };
  }
}

async function attemptUpdateBranchViaApi({
  github,
  owner,
  repo,
  prNumber,
  baselineHead,
  fetchHead,
  pollTimeoutMs,
  pollIntervalMs,
  core,
  record,
  appendRound,
}) {
  if (!Number.isFinite(prNumber) || prNumber <= 0 || !baselineHead) {
    record('Update-branch API', appendRound('skipped: missing PR context or baseline head.'));
    return { attempted: false };
  }
  if (!github?.rest?.pulls?.updateBranch) {
    record('Update-branch API', appendRound('skipped: Octokit client lacks updateBranch support.'));
    return { attempted: false };
  }

  const requestPayload = {
    owner,
    repo,
    pull_number: prNumber,
    expected_head_sha: baselineHead,
  };

  record('Update-branch API', appendRound('invoking GitHub updateBranch.'));
  try {
    const response = await github.rest.pulls.updateBranch(requestPayload);
    const status = Number(response?.status || 0);
    record('Update-branch API', appendRound(`requested merge (status=${status || 'unknown'}).`));
  } catch (error) {
    const status = Number(error?.status || 0);
    const message = error instanceof Error ? error.message : String(error);
    if (status === 422) {
      record('Update-branch API', appendRound(`blocked: ${message}`));
    } else {
      record('Update-branch API', appendRound(`failed: ${message}`));
    }
    return { attempted: true, changed: false, error: message, blocked: status === 422 };
  }

  let pollResult;
  try {
    pollResult = await pollForHeadChange({
      fetchHead,
      initialSha: baselineHead,
      timeoutMs: pollTimeoutMs,
      intervalMs: pollIntervalMs,
      label: 'update-branch-api',
      core,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    record('Update-branch API', appendRound(`polling failed: ${message}`));
    return { attempted: true, changed: false, error: message };
  }

  if (pollResult?.changed) {
    record('Update-branch API', appendRound(`head advanced to ${pollResult.headSha || '(unknown)'}.`));
  } else {
    record('Update-branch API', appendRound('head unchanged after updateBranch wait.'));
  }

  return {
    attempted: true,
    changed: Boolean(pollResult?.changed),
    headSha: pollResult?.headSha || '',
  };
}

async function runKeepalivePostWork({ core, github: rawGithub, context, env = process.env }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env });
    core?.debug?.('GitHub client wrapped with rate-limit protection');
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const summaryHelper = buildSummaryRecorder(core?.summary);
  const record = summaryHelper.record;
  const remediationNotes = [];

  const noteRemediation = (note) => {
    const value = normalise(note);
    if (!value) {
      return;
    }
    remediationNotes.push(value);
  };

  const trace = normalise(env.TRACE);
  const round = normalise(env.ROUND);
  const prNumber = parseNumber(env.PR_NUMBER, NaN, { min: 1 });
  const issueNumber = parseNumber(env.ISSUE_NUMBER, NaN, { min: 1 });
  const baseBranch = normalise(env.PR_BASE) || normalise(env.BASE_BRANCH) || normalise(env.PR_BASE_BRANCH);
  const headBranchEnv = normalise(env.PR_HEAD) || normalise(env.HEAD_BRANCH) || normalise(env.PR_HEAD_BRANCH);
  const headRepoEnv = normalise(env.HEAD_REPO);
  let baselineHead =
    normalise(env.PR_HEAD_SHA_PREV) ||
    normalise(env.PREVIOUS_HEAD) ||
    normalise(env.HEAD_SHA_PREV) ||
    '';
  const commentIdEnv = parseNumber(env.COMMENT_ID, NaN, { min: 1 });
  const commentUrlEnv = normalise(env.COMMENT_URL);
  const commentTraceEnv = normalise(env.COMMENT_TRACE);
  const commentRoundEnv = normalise(env.COMMENT_ROUND);
  const agentAliasEnv = normalise(env.AGENT_ALIAS) || 'codex';
  const syncLabel = normaliseLower(env.SYNC_LABEL) || 'agents:sync-required';
  const debugLabel = normaliseLower(env.DEBUG_LABEL) || 'agents:debug';
  const dispatchEventType = normalise(env.DISPATCH_EVENT_TYPE) || 'codex-pr-comment-command';
  const ttlShort = parseNumber(env.TTL_SHORT_MS, 90_000, { min: 0 });
  const pollShort = parseNumber(env.POLL_SHORT_MS, 5_000, { min: 0 });
  const ttlLong = parseNumber(env.TTL_LONG_MS, 240_000, { min: 0 });
  const pollLong = parseNumber(env.POLL_LONG_MS, 5_000, { min: 0 });
  const automationLogins = buildAutomationLoginSet(env.AUTOMATION_LOGINS);
  const mergeMethod = clampMergeMethod(env.MERGE_METHOD, 'squash');
  const deleteTempBranch = parseBoolean(env.DELETE_TEMP_BRANCH, true);
  const roundTag = `round=${round || '?'}`;
  const appendRound = (message) => `${message} ${roundTag}`;

  const statusMode = parseBoolean(env.DRY_RUN, false) ? 'dry-run' : 'active';
  let syncStatus = 'needs_update';
  let statusHead = baselineHead || '';
  let statusBase = baseBranch || '';
  let syncLink = normalise(commentUrlEnv) || '-';

  const updateSyncLink = (candidate, { prefer = false } = {}) => {
    const value = normalise(candidate);
    if (!value) {
      return;
    }
    if (syncLink === '-' || prefer) {
      syncLink = value;
    }
  };

  const setStatus = (value) => {
    const allowed = new Set(['in_sync', 'needs_update', 'conflict']);
    const candidate = normaliseLower(value);
    if (allowed.has(candidate)) {
      syncStatus = candidate;
    }
  };

  const setStatusHead = (value) => {
    const candidate = normalise(value);
    if (candidate) {
      statusHead = candidate;
    }
  };

  const setStatusBase = (value) => {
    const candidate = normalise(value);
    if (candidate) {
      statusBase = candidate;
    }
  };

  const finalState = {
    action: 'skip',
    headMoved: false,
    mode: 'none',
    finalHead: '',
    success: false,
    summaryWritten: false,
    status: syncStatus,
    statusHead,
    statusBase,
    statusMode,
    link: syncLink,
  };

  const applyFinalState = (updates = {}) => {
    if (!updates || typeof updates !== 'object') {
      return finalState;
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'action')) {
      const value = normaliseLower(updates.action);
      finalState.action = value || finalState.action;
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'headMoved')) {
      finalState.headMoved = Boolean(updates.headMoved);
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'mode')) {
      const raw = updates.mode;
      finalState.mode = raw ? String(raw) : finalState.mode;
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'finalHead')) {
      const raw = updates.finalHead;
      finalState.finalHead = raw ? String(raw) : '';
      if (finalState.finalHead) {
        setStatusHead(finalState.finalHead);
      }
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'success')) {
      finalState.success = Boolean(updates.success);
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'summaryWritten')) {
      finalState.summaryWritten = Boolean(updates.summaryWritten);
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'status')) {
      setStatus(updates.status);
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'statusHead')) {
      setStatusHead(updates.statusHead);
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'statusBase')) {
      setStatusBase(updates.statusBase);
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'statusMode')) {
      const modeValue = normaliseLower(updates.statusMode);
      finalState.statusMode = modeValue || finalState.statusMode;
    }
    if (Object.prototype.hasOwnProperty.call(updates, 'link')) {
      const linkValue = normalise(updates.link);
      if (linkValue) {
        syncLink = linkValue;
      }
    }
    finalState.status = syncStatus;
    finalState.statusHead = statusHead;
    finalState.statusBase = statusBase;
    finalState.link = syncLink || '-';
    return finalState;
  };

  const setOutputsFromFinalState = () => {
    core?.setOutput?.('action', finalState.action || 'skip');
    core?.setOutput?.('changed', finalState.headMoved ? 'true' : 'false');
    core?.setOutput?.('mode', finalState.mode || '');
    core?.setOutput?.('success', finalState.success ? 'true' : 'false');
    core?.setOutput?.('merged_sha', finalState.finalHead || '');
    core?.setOutput?.('status', finalState.status || syncStatus || 'needs_update');
    core?.setOutput?.('status_head', finalState.statusHead || statusHead || '');
    core?.setOutput?.('status_base', finalState.statusBase || statusBase || '');
    core?.setOutput?.('status_mode', finalState.statusMode || statusMode);
    core?.setOutput?.('link', finalState.link || syncLink || '-');
  };

  const flushSummary = async () => {
    if (!finalState.summaryWritten && core?.summary) {
      const shortHead = (finalState.statusHead || statusHead || '').slice(0, 7) || 'unknown';
      const baseLabel = finalState.statusBase || statusBase || '(unknown)';
      const statusLabel = finalState.status || syncStatus || 'needs_update';
      const modeLabel = finalState.statusMode || statusMode;
      const linkLabel = finalState.link || syncLink || '-';
      if (remediationNotes.length) {
        const uniqueNotes = Array.from(new Set(remediationNotes));
        core.summary.addRaw(`Remediation: ${uniqueNotes.join(' | ')}`).addEOL();
      }
      core.summary
        .addRaw(`SYNC: status=${statusLabel} mode=${modeLabel} head=${shortHead} base=${baseLabel || '(unknown)'}`)
        .addEOL()
        .addRaw(
          `SYNC: action=${finalState.action || 'skip'} head_changed=${
            finalState.headMoved ? 'true' : 'false'
          } link=${linkLabel || '-'} trace=${trace || 'n/a'}`,
        )
        .addEOL();
    }
    await summaryHelper.flush(buildSyncSummaryLabel(trace));
    finalState.summaryWritten = true;
  };

  const complete = async () => {
    setOutputsFromFinalState();
    await flushSummary();
  };

  const { owner, repo } = context.repo || {};
  if (!owner || !repo) {
    record('Initialisation', 'Repository context missing; aborting.');
    setStatus('conflict');
    applyFinalState({
      action: 'skip',
      success: false,
      mode: 'initialisation-missing-repo',
      status: syncStatus,
      statusBase,
      statusHead,
      link: syncLink,
    });
    await complete();
    return;
  }
  if (!Number.isFinite(prNumber)) {
    record('Initialisation', 'PR number missing; aborting.');
    setStatus('conflict');
    applyFinalState({
      action: 'skip',
      success: false,
      mode: 'initialisation-missing-pr',
      status: syncStatus,
      statusBase,
      statusHead,
      link: syncLink,
    });
    await complete();
    return;
  }

  const prConversationUrl = Number.isFinite(prNumber) && prNumber > 0
    ? `https://github.com/${owner}/${repo}/pull/${prNumber}`
    : '';

  const idempotencyKey = computeIdempotencyKey(prNumber, round, trace);
  record('Idempotency', idempotencyKey);
  core?.setOutput?.('idempotency_key', idempotencyKey);
  if (trace) {
    core?.setOutput?.('trace', trace);
  }

  const stateManager = await createKeepaliveStateManager({ github, context, prNumber, trace, round });
  let state = stateManager.state || {};
  let commandState = state.command_dispatch && typeof state.command_dispatch === 'object' ? state.command_dispatch : {};
  let escalationRecord = state.escalation_comment && typeof state.escalation_comment === 'object' ? state.escalation_comment : {};
  let stateCommentId = stateManager.commentId ? Number(stateManager.commentId) : 0;
  let stateCommentUrl = stateManager.commentUrl || '';

  const applyStateUpdate = async (updates, { forcePersist = false } = {}) => {
    if (!forcePersist && !stateCommentId) {
      state = mergeStateShallow(state, updates);
      commandState = state.command_dispatch && typeof state.command_dispatch === 'object' ? state.command_dispatch : {};
      escalationRecord = state.escalation_comment && typeof state.escalation_comment === 'object' ? state.escalation_comment : {};
      return { state: { ...state }, commentId: stateCommentId, commentUrl: stateCommentUrl };
    }

    const saved = await stateManager.save(updates);
    state = saved.state || {};
    commandState = state.command_dispatch && typeof state.command_dispatch === 'object' ? state.command_dispatch : {};
    escalationRecord = state.escalation_comment && typeof state.escalation_comment === 'object' ? state.escalation_comment : {};
    stateCommentId = saved.commentId || stateCommentId;
    stateCommentUrl = saved.commentUrl || stateCommentUrl;
    return saved;
  };

  if (!stateCommentId) {
    const saved = await applyStateUpdate({}, { forcePersist: true });
    stateCommentId = saved.commentId || stateCommentId;
    stateCommentUrl = saved.commentUrl || stateCommentUrl;
    record('State comment', appendRound(`initialised id=${stateCommentId || 0}`));
  } else {
    record('State comment', appendRound(`reused id=${stateCommentId}`));
  }

  const updateCommandState = async (updates) => {
    const merged = mergeStateShallow(commandState, updates);
    await applyStateUpdate({ command_dispatch: merged });
    commandState = state.command_dispatch && typeof state.command_dispatch === 'object' ? state.command_dispatch : {};
    return commandState;
  };

  const updateEscalationRecord = async (updates) => {
    const merged = mergeStateShallow(
      escalationRecord && typeof escalationRecord === 'object' ? escalationRecord : {},
      updates,
    );
    await applyStateUpdate({ escalation_comment: merged });
    escalationRecord = state.escalation_comment && typeof state.escalation_comment === 'object' ? state.escalation_comment : {};
    return escalationRecord;
  };

  const getCommandActionState = (action) => {
    if (!action) {
      return {};
    }
    const entry = commandState && typeof commandState === 'object' ? commandState[action] : undefined;
    return entry && typeof entry === 'object' ? entry : {};
  };

  const buildHistoryWith = (action) => {
    const base = Array.isArray(commandState?.history) ? commandState.history.slice() : [];
    if (action && !base.includes(action)) {
      base.push(action);
    }
    return base;
  };

  const actionsAttempted = [];
  const noteActionAttempt = (action) => {
    const key = normalise(action);
    if (!key) {
      return;
    }
    if (!actionsAttempted.includes(key)) {
      actionsAttempted.push(key);
    }
  };

  if (baselineHead && !normalise(state.head_sha)) {
    await applyStateUpdate({ head_sha: baselineHead, head_recorded_at: new Date().toISOString() });
  }
  if (state.idempotency_key !== idempotencyKey) {
    await applyStateUpdate({ idempotency_key: idempotencyKey });
  }

  const fetchHead = async () => loadPull({ github, owner, repo, prNumber });

  let currentLabels = [];
  try {
    currentLabels = await listLabels({ github, owner, repo, prNumber });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    core?.warning?.(`Unable to list labels on PR #${prNumber}: ${message}`);
  }
  const labelNames = extractLabelNames(currentLabels);
  const hasSyncLabel = labelNames.includes(syncLabel);
  const agentAlias = extractAgentAliasFromLabels(currentLabels, agentAliasEnv);

  record('Labels', hasSyncLabel ? `${syncLabel} present` : `${syncLabel} absent`);
  record('Agent alias', agentAlias);

  const agentState = parseAgentState(env);
  if (!agentState.done) {
    record(
      'Preconditions',
      `Agent state ${agentState.value || '(unknown)'} does not indicate completion; skipping sync gate.`,
    );
    setStatus('needs_update');
    applyFinalState({
      action: 'skip',
      success: false,
      mode: 'skipped-agent-state',
      headMoved: false,
      status: syncStatus,
      statusBase,
      statusHead,
      link: syncLink,
    });
    await complete();
    return;
  }
  record('Preconditions', `Agent reported done (${agentState.value || 'done'}).`);

  let initialHeadInfo;
  try {
    initialHeadInfo = await fetchHead();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    record('Initial head fetch', `Failed: ${message}`);
    setStatus('conflict');
    applyFinalState({
      action: 'skip',
      success: false,
      mode: 'head-fetch-failed',
      headMoved: false,
      status: syncStatus,
      statusBase,
      statusHead,
      link: syncLink,
    });
    await complete();
    return;
  }

  if (isForkPull(initialHeadInfo)) {
    const headRepoName = headRepoEnv || initialHeadInfo.headRepo || '';
    if (!headRepoName) {
      record('Initialisation', 'Forked PR missing head repository; skipping sync operations.');
      setStatus('conflict');
      applyFinalState({
        action: 'skip',
        success: false,
        mode: 'fork-head-repo-missing',
        headMoved: false,
        status: syncStatus,
        statusBase,
        statusHead,
        link: syncLink,
      });
      await complete();
      return;
    }
  }

  const initialHead = initialHeadInfo.headSha || '';
  const headBranch = headBranchEnv || initialHeadInfo.headRef || '';
  const baseRef = baseBranch || initialHeadInfo.baseRef || '';
  const baseRepoFullName = initialHeadInfo.baseRepo || `${owner}/${repo}`;
  const headRepoFullName = headRepoEnv || initialHeadInfo.headRepo || (isForkPull(initialHeadInfo) ? '' : baseRepoFullName);
  const headIsFork = isForkPull(initialHeadInfo);
  setStatusHead(initialHead);
  setStatusBase(baseRef);
  if (!baselineHead) {
    baselineHead = normalise(state.head_sha) || initialHead;
  }
  if (!normalise(state.head_sha) && baselineHead) {
    await applyStateUpdate({ head_sha: baselineHead });
  }
  record('Baseline head', baselineHead || '(unavailable)');

  const instructionComment = Number.isFinite(commentIdEnv)
    ? { id: Number(commentIdEnv), url: commentUrlEnv || '' }
    : null;

  if (instructionComment?.id) {
    record('Instruction comment', appendRound(`id=${instructionComment.id}`));
  } else {
    record('Instruction comment', appendRound('unavailable; proceeding without comment context.'));
  }

  const commentInfo = instructionComment;
  updateSyncLink(commentInfo?.url);

  const persistLastInstruction = async (finalHeadValue) => {
    const payload = {
      comment_id: commentInfo?.id ? String(commentInfo.id) : '',
      comment_url: commentInfo?.url || '',
      trace: commentTraceEnv || '',
      round: commentRoundEnv || '',
      head_sha: normalise(finalHeadValue) || '',
      recorded_at: new Date().toISOString(),
    };

    const filtered = Object.fromEntries(
      Object.entries(payload).filter(([key, value]) => {
        if (key === 'recorded_at') {
          return true;
        }
        return normalise(value) !== '';
      }),
    );

    if (Object.keys(filtered).length === 0) {
      return;
    }

    await applyStateUpdate({ last_instruction: filtered });
  };

  if (baselineHead && initialHead && baselineHead !== initialHead) {
    record('Head check', `Head already advanced to ${initialHead}; skipping sync gate.`);
    if (hasSyncLabel) {
      try {
        await github.rest.issues.removeLabel({ owner, repo, issue_number: prNumber, name: syncLabel });
        record('Sync label', appendRound(`Removed ${syncLabel}.`));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        record('Sync label', appendRound(`Failed to remove ${syncLabel}: ${message}`));
      }
    } else {
      record('Sync label', appendRound(`${syncLabel} not present.`));
    }
    const elapsed = 0;
    const finalHead = initialHead;
    await applyStateUpdate({
      result: {
        status: 'success',
        mode: 'already-synced',
        merged_sha: finalHead,
        recorded_at: new Date().toISOString(),
      },
    });
    await persistLastInstruction(finalHead);
    record('Result', appendRound(`mode=already-synced sha=${finalHead || '(unknown)'} elapsed=${elapsed}ms`));
    setStatus('in_sync');
    setStatusHead(finalHead);
    applyFinalState({
      action: 'skip',
      success: true,
      headMoved: true,
      finalHead,
      mode: 'already-synced',
      status: syncStatus,
      statusBase,
      statusHead,
      link: syncLink,
    });
    await complete();
    return;
  }

  const attemptCommand = async (action, label) => {
    const commandName = normalise(action);
    if (!commandName) {
      record(label || 'Command dispatch', appendRound('skipped: action missing.'));
      return { attempted: false };
    }
    noteActionAttempt(commandName);
    const displayLabel = label || `${commandName} command`;
    const history = buildHistoryWith(commandName);
    const existingEntry = getCommandActionState(commandName);
    const attemptTimestamp = new Date().toISOString();

    const persistEntry = async (updates = {}) => {
      const payload = mergeStateShallow(existingEntry, {
        attempts: Number(existingEntry?.attempts || 0) + 1,
        last_attempt_at: attemptTimestamp,
        last_result: updates.last_result || existingEntry?.last_result || '',
        idempotency_key: idempotencyKey,
        last_round: round || '',
        last_trace: trace || '',
        last_mode: statusMode,
        ...updates,
      });
      await updateCommandState({ history, [commandName]: payload });
      return payload;
    };

    if (statusMode === 'dry-run') {
      record(displayLabel, appendRound('skipped: dry-run mode.'));
      await persistEntry({ last_result: 'dry-run', status: 'skipped' });
      return { attempted: false, dryRun: true };
    }

    const dispatched = await dispatchCommand({
      github,
      owner,
      repo,
      eventType: dispatchEventType,
      action: commandName,
      prNumber,
      agentAlias,
      baseRef,
      headRef: headBranch,
      headSha: baselineHead || initialHead,
      trace,
      round,
      commentInfo,
      idempotencyKey,
      roundTag,
      record,
    });

    if (dispatched) {
      await persistEntry({ last_result: 'dispatched', status: 'pending', dispatched: true, dispatched_at: attemptTimestamp });
      return { attempted: true, dispatched: true };
    }

    const commentResult = await postCommandComment({
      github,
      owner,
      repo,
      prNumber,
      action: commandName,
      trace,
      round,
      record,
      appendRound,
    });

    if (commentResult.posted) {
      await persistEntry({
        last_result: 'comment',
        status: 'pending',
        comment_id: commentResult.commentId || '',
        comment_url: commentResult.commentUrl || '',
        commented_at: attemptTimestamp,
      });
      updateSyncLink(commentResult.commentUrl);
      return { attempted: true, commented: true };
    }

    await persistEntry({ last_result: 'failed', status: 'error' });
    record(displayLabel, appendRound('command attempt failed.'));
    return { attempted: true, failed: true };
  };

  let finalAction = 'skip';

  const attemptUpdateBranchApi = async () => {
    if (!baselineHead) {
      record('Update-branch API', appendRound('skipped: baseline head missing.'));
      return { changed: false };
    }

    try {
      const response = await github.rest.pulls.updateBranch({
        owner,
        repo,
        pull_number: prNumber,
        expected_head_sha: baselineHead,
      });
      record('Update-branch API', appendRound(`requested status=${response?.status ?? 0}`));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      record('Update-branch API', appendRound(`failed: ${message}`));
      return { changed: false, error: message };
    }

    const pollResult = await pollForHeadChange({
      fetchHead,
      initialSha: baselineHead,
      timeoutMs: ttlLong,
      intervalMs: pollLong,
      label: 'api-update-branch',
      core,
    });

    if (pollResult?.changed) {
      const resolvedSha = pollResult.headSha || '';
      success = true;
      finalHead = resolvedSha || finalHead;
      baselineHead = finalHead;
      mode = 'api-update-branch';
      finalAction = 'update-branch';
      setStatus('in_sync');
      setStatusHead(finalHead);
      record('Update-branch API result', appendRound(`Branch advanced to ${resolvedSha || '(unknown)'}.`));
      return { changed: true, headSha: resolvedSha };
    }

    record('Update-branch API result', appendRound('Branch unchanged after API attempt.'));
    return { changed: false };
  };

  const attemptHelperSync = async () => {
    const dispatchInfo = state.fallback_dispatch?.dispatched
      ? { dispatched: true, status: state.fallback_dispatch.status, dispatchedAt: state.fallback_dispatch.dispatched_at }
      : await dispatchFallbackWorkflow({
          github,
          owner,
          repo,
          baseRef,
          dispatchRef: baseRef || context.payload?.repository?.default_branch,
          prNumber,
          headRef: headBranch,
          headSha: baselineHead || initialHead,
          trace,
          round,
          agentAlias,
          commentInfo,
          idempotencyKey,
          headRepo: headRepoFullName,
          headIsFork,
          record,
        });

    if (!dispatchInfo.dispatched) {
      record('Helper sync dispatch', appendRound('skipped: workflow dispatch unavailable.'));
      return { changed: false };
    }

    if (!state.fallback_dispatch?.dispatched) {
      await applyStateUpdate({
        fallback_dispatch: {
          dispatched: true,
          status: dispatchInfo.status ?? 0,
          dispatched_at: dispatchInfo.dispatchedAt,
          workflow: 'agents-keepalive-branch-sync.yml',
        },
      });
      noteRemediation(`branch-sync:dispatched status=${dispatchInfo.status ?? 0}`);
    } else {
      record('Helper sync dispatch', appendRound('reuse previous dispatch record.'));
    }

    const existingRunId = state.fallback_dispatch?.run_id;
    const runInfo = await findFallbackRun({
      github,
      owner,
      repo,
      createdAfter: dispatchInfo.dispatchedAt || state.fallback_dispatch?.dispatched_at,
      existingRunId,
      core,
    });
    if (runInfo) {
      record('Helper sync run', appendRound(runInfo.html_url ? `run=${runInfo.html_url}` : `run_id=${runInfo.id}`));
      updateSyncLink(runInfo.html_url, { prefer: true });
      if (!existingRunId || Number(existingRunId) !== Number(runInfo.id)) {
        await applyStateUpdate({
          fallback_dispatch: {
            ...(state.fallback_dispatch || {}),
            dispatched: true,
            status: state.fallback_dispatch?.status ?? dispatchInfo.status ?? 0,
            dispatched_at: state.fallback_dispatch?.dispatched_at || dispatchInfo.dispatchedAt,
            workflow: 'agents-keepalive-branch-sync.yml',
            run_id: runInfo.id,
            run_url: runInfo.html_url || '',
          },
        });
      }
      noteRemediation(runInfo.html_url ? `branch-sync:run=${runInfo.html_url}` : `branch-sync:run-id=${runInfo.id}`);
    } else {
      record('Helper sync run', appendRound('pending discovery.'));
    }

    const pollResult = await pollForHeadChange({
      fetchHead,
      initialSha: baselineHead || initialHead,
      timeoutMs: ttlLong,
      intervalMs: pollLong,
      label: 'helper-sync',
      core,
    });

    if (pollResult?.changed) {
      const resolvedSha = pollResult.headSha || '';
      success = true;
      finalHead = resolvedSha || finalHead;
      baselineHead = finalHead;
      mode = 'helper-sync';
      finalAction = 'create-pr';
      setStatus('in_sync');
      setStatusHead(finalHead);
      record('Helper sync result', appendRound(`Branch advanced to ${resolvedSha || '(unknown)'}.`));
      return { changed: true, headSha: resolvedSha };
    }

    record('Helper sync result', appendRound('Branch unchanged after helper sync TTL.'));
    return { changed: false };
  };

  const startTime = Date.now();
  let success = false;
  let finalHead = initialHead;
  let mode = 'none';
  let apiResult = null;

  const shortPoll = await pollForHeadChange({
    fetchHead,
    initialSha: baselineHead,
    timeoutMs: ttlShort,
    intervalMs: pollShort,
    label: 'comment-wait',
    core,
  });
  if (shortPoll.changed) {
    success = true;
    finalHead = shortPoll.headSha;
    baselineHead = finalHead;
    mode = 'already-synced';
    setStatus('in_sync');
    setStatusHead(finalHead);
    record('Initial poll', `Branch advanced to ${shortPoll.headSha}`);
  } else {
    record('Comment wait', appendRound('Head unchanged after comment TTL.'));
  }

  if (!success) {
    // As a guard, re-fetch the head once more before dispatching commands. The
    // short-poll window can miss a freshly advanced head on faster runners, so
    // this explicit check lets us bail out without emitting redundant commands.
    try {
      const freshHead = await fetchHead();
      if (baselineHead && freshHead?.headSha && freshHead.headSha !== baselineHead) {
        success = true;
        finalHead = freshHead.headSha;
        baselineHead = finalHead;
        mode = 'already-synced';
        setStatus('in_sync');
        setStatusHead(finalHead);
        record('Pre-dispatch check', appendRound(`Head advanced to ${freshHead.headSha}`));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      core?.warning?.(`Failed to refresh head before dispatch: ${message}`);
    }
  }

  if (!success) {
    apiResult = await attemptUpdateBranchViaApi({
      github,
      owner,
      repo,
      prNumber,
      baselineHead,
      fetchHead,
      pollTimeoutMs: ttlShort,
      pollIntervalMs: pollShort,
      core,
      record,
      appendRound,
    });
    if (apiResult?.attempted) {
      if (apiResult?.changed) {
        noteRemediation(`update-branch:advanced:${apiResult.headSha || '(unknown)'}`);
      } else if (apiResult?.error) {
        noteRemediation(`update-branch:failed:${apiResult.error}`);
      } else if (apiResult?.blocked) {
        noteRemediation('update-branch:blocked');
      } else {
        noteRemediation('update-branch:unchanged');
      }
    }
    if (apiResult?.changed) {
      success = true;
      finalHead = apiResult.headSha || finalHead;
      baselineHead = finalHead;
      mode = 'update-branch-api';
      finalAction = 'update-branch';
      setStatus('in_sync');
      setStatusHead(finalHead);
      if (prConversationUrl) {
        updateSyncLink(prConversationUrl, { prefer: syncLink === '-' });
      }
    } else if (apiResult?.attempted && prConversationUrl) {
      updateSyncLink(prConversationUrl, { prefer: syncLink === '-' });
    }
  }

  if (!success) {
    await attemptCommand('update-branch', 'Update-branch');
  }

  if (!success) {
    await attemptCommand('create-pr', 'Create-pr');
  }

  if (!success) {
    const dispatchInfo = state.fallback_dispatch?.dispatched
      ? { dispatched: true, status: state.fallback_dispatch.status, dispatchedAt: state.fallback_dispatch.dispatched_at }
      : await dispatchFallbackWorkflow({
          github,
          owner,
          repo,
          baseRef,
          dispatchRef: baseRef || context.payload?.repository?.default_branch,
          prNumber,
          headRef: headBranch,
          headSha: baselineHead || initialHead,
          trace,
          round,
          agentAlias,
          commentInfo,
          idempotencyKey,
          headRepo: headRepoFullName,
          headIsFork,
          record,
        });

    if (dispatchInfo.dispatched && !state.fallback_dispatch?.dispatched) {
      await applyStateUpdate({
        fallback_dispatch: {
          dispatched: true,
          status: dispatchInfo.status ?? 0,
          dispatched_at: dispatchInfo.dispatchedAt,
          workflow: 'agents-keepalive-branch-sync.yml',
        },
      });
      noteRemediation(`branch-sync:dispatched status=${dispatchInfo.status ?? 0}`);
    } else if (dispatchInfo.dispatched) {
      record('Fallback dispatch', appendRound('reuse previous dispatch record.'));
    }

    const existingRunId = state.fallback_dispatch?.run_id;
    const runInfo = await findFallbackRun({
      github,
      owner,
      repo,
      prNumber,
      baselineHead,
      fetchHead,
      pollTimeoutMs: ttlShort,
      pollIntervalMs: pollShort,
      core,
      record,
      appendRound,
    });
    if (runInfo?.html_url) {
      noteRemediation(`branch-sync:run=${runInfo.html_url}`);
    } else if (runInfo) {
      noteRemediation(`branch-sync:run-id=${runInfo.id}`);
    }
    if (apiResult?.changed) {
      success = true;
      finalHead = apiResult.headSha || finalHead;
      baselineHead = finalHead;
      mode = 'api-update-branch';
      finalAction = 'update-branch';
      setStatus('in_sync');
      setStatusHead(finalHead);
      if (prConversationUrl) {
        updateSyncLink(prConversationUrl, { prefer: syncLink === '-' });
      }
    } else if (apiResult?.attempted && prConversationUrl) {
      updateSyncLink(prConversationUrl, { prefer: syncLink === '-' });
    }
  }

  if (!success) {
    await attemptCommand('update-branch', 'Update-branch');
  }

  if (!success) {
    noteActionAttempt('helper-sync');
    await attemptHelperSync();
  }

  if (!success && (!mode || mode === 'none')) {
    mode = 'sync-timeout';
  }

  if (success) {
    await applyStateUpdate({
      head_sha: finalHead || '',
      head_recorded_at: new Date().toISOString(),
      result: {
        status: 'success',
        mode,
        merged_sha: finalHead || '',
        recorded_at: new Date().toISOString(),
      },
    });
    await persistLastInstruction(finalHead || baselineHead || initialHead);

    if (hasSyncLabel) {
      try {
        await github.rest.issues.removeLabel({ owner, repo, issue_number: prNumber, name: syncLabel });
        record('Sync label', `Removed ${syncLabel}.`);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        record('Sync label', `Failed to remove ${syncLabel}: ${message}`);
      }
    } else {
      record('Sync label', `${syncLabel} not present.`);
    }
    const elapsed = Date.now() - startTime;
    record('Result', appendRound(`mode=${mode || 'unknown'} sha=${finalHead || '(unknown)'} elapsed=${elapsed}ms`));
    setStatus('in_sync');
    setStatusHead(finalHead);
    applyFinalState({
      action: finalAction || 'skip',
      success: true,
      headMoved: true,
      finalHead,
      mode,
      status: syncStatus,
      statusBase,
      statusHead,
      link: syncLink,
    });
    await complete();
    return;
  }

  await applyStateUpdate({
    result: {
      status: 'timeout',
      mode: mode || 'sync-timeout',
      merged_sha: finalHead || '',
      recorded_at: new Date().toISOString(),
    },
  });

  if (!hasSyncLabel) {
    try {
      await github.rest.issues.addLabels({ owner, repo, issue_number: prNumber, labels: [syncLabel] });
      record('Sync label', appendRound(`Applied ${syncLabel}.`));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      record('Sync label', appendRound(`Failed to apply ${syncLabel}: ${message}`));
    }
  } else {
    record('Sync label', appendRound(`${syncLabel} already present.`));
  }

  const normaliseLink = (value) => {
    const trimmed = normalise(value);
    if (trimmed && /^https?:\/\//i.test(trimmed)) {
      return trimmed;
    }
    return '';
  };

  const manualActionLink = normaliseLink(syncLink) || normaliseLink(prConversationUrl) || '';
  if (manualActionLink && (syncLink === '-' || syncLink === '' || syncLink === manualActionLink)) {
    updateSyncLink(manualActionLink, { prefer: syncLink === '-' });
  }

  const previousEscalationKey = normalise(escalationRecord?.idempotency_key);
  const reusePriorEscalation = previousEscalationKey && previousEscalationKey === normalise(idempotencyKey);
  const havePriorComment = reusePriorEscalation && escalationRecord?.comment_url;
  if (!manualActionLink) {
    record('Escalation comment', appendRound('Skipped: manual action link unavailable.'));
  } else if (havePriorComment) {
    updateSyncLink(escalationRecord.comment_url, { prefer: true });
    record('Escalation comment', appendRound('Reusing previous escalation comment.'));
  } else {
    const escalationMessage = `Keepalive: manual action needed — use update-branch/create-pr controls (click Update Branch or open Create PR) at: ${manualActionLink}`;
    try {
      const { data: escalationComment } = await github.rest.issues.createComment({
        owner,
        repo,
        issue_number: prNumber,
        body: escalationMessage,
      });
      updateSyncLink(escalationComment?.html_url || manualActionLink, { prefer: true });
      await updateEscalationRecord({
        comment_id: escalationComment?.id || '',
        comment_url: escalationComment?.html_url || '',
        idempotency_key: idempotencyKey,
        recorded_at: new Date().toISOString(),
        body: escalationMessage,
      });
      record('Escalation comment', appendRound('Posted escalation notice.'));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      record('Escalation comment', appendRound(`Failed to post escalation comment: ${message}`));
    }
  }

  const timeoutMessage = appendRound(
    `mode=${mode || 'sync-timeout'} trace:${trace || 'missing'} elapsed=${Date.now() - startTime}ms`,
  );
  record('Result', timeoutMessage);
  setStatus('needs_update');
  setStatusHead(baselineHead || finalHead || initialHead || statusHead);
  applyFinalState({
    action: 'escalate',
    success: false,
    headMoved: false,
    mode,
    finalHead,
    status: syncStatus,
    statusBase,
    statusHead,
    link: syncLink,
  });
  await complete();
}

module.exports = {
  runKeepalivePostWork,
};
