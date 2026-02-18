'use strict';

const { paginateWithBackoff, withBackoff } = require('./api-helpers.js');
const { createGithubApiCache } = require('./github-api-cache-client');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

const KEEPALIVE_LABEL = 'agents:keepalive';
const AGENT_LABEL_PREFIX = 'agent:';
const MAX_RUNS_PREFIX = 'agents:max-runs:';
const SYNC_REQUIRED_LABEL = 'agents:sync-required';
const ACTIVATED_LABEL = 'agents:activated';
const PAUSE_LABEL = 'agents:paused';
const DEFAULT_RUN_CAP = 1;
const MIN_RUN_CAP = 1;
const MAX_RUN_CAP = 5;
const AUTOMATION_LOGINS = new Set(['chatgpt-codex-connector', 'stranske-automation-bot']);
const ORCHESTRATOR_WORKFLOW_FILE = 'agents-70-orchestrator.yml';
const WORKER_WORKFLOW_FILE = 'agents-72-codex-belt-worker.yml';
const RECENT_COMPLETED_LOOKBACK_SECONDS = 300; // 5 minutes

// Rate limit retry configuration - now handled by api-helpers
const RATE_LIMIT_MAX_RETRIES = 3;
const RATE_LIMIT_BASE_DELAY_MS = 2000;

function getGithubApiCache({ github, core }) {
  if (!github) {
    return createGithubApiCache({ core });
  }
  if (github.__keepaliveGateApiCache) {
    return github.__keepaliveGateApiCache;
  }
  const cache = createGithubApiCache({ core });
  Object.defineProperty(github, '__keepaliveGateApiCache', {
    value: cache,
    enumerable: false,
    configurable: false,
    writable: false,
  });
  return cache;
}

async function fetchPullRequestCached({ github, owner, repo, prNumber, core }) {
  if (!github?.rest?.pulls?.get || !owner || !repo) {
    return null;
  }
  const number = Number(prNumber);
  if (!Number.isFinite(number) || number <= 0) {
    return null;
  }
  const cache = getGithubApiCache({ github, core });
  const key = cache.buildPrCacheKey({ owner, repo, number, resource: 'pulls.get' });
  return cache.getOrSet({
    key,
    fetcher: async () => {
      const response = await withBackoff(
        () => github.rest.pulls.get({ owner, repo, pull_number: number }),
        { core, maxRetries: RATE_LIMIT_MAX_RETRIES, baseDelay: RATE_LIMIT_BASE_DELAY_MS }
      );
      const data = response?.data;
      if (!data) {
        const error = new Error('pull request data unavailable');
        if (response && typeof response === 'object') {
          error.status = response.status;
        }
        throw error;
      }
      return data;
    },
  });
}

/**
 * Sleep for a given number of milliseconds.
 * @param {number} ms - Milliseconds to sleep
 * @returns {Promise<void>}
 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Check if an error is a GitHub rate limit error.
 * @param {Error|unknown} error
 * @returns {boolean}
 */
function isRateLimitError(error) {
  if (!error) return false;
  const message = error instanceof Error ? error.message : String(error);
  const status = error?.status || error?.response?.status;
  return (
    status === 403 ||
    status === 429 ||
    /rate\s*limit/i.test(message) ||
    /secondary\s*rate\s*limit/i.test(message)
  );
}

function toInteger(value) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

function normaliseBranch(value) {
  const branch = String(value || '').trim();
  if (!branch) {
    return '';
  }
  return branch.replace(/^refs\/(heads|remotes)\//i, '');
}

function extractPrNumbersFromText(text) {
  if (!text || typeof text !== 'string') {
    return [];
  }
  const result = new Set();
  const candidates = [
    /#(\d{1,6})/g,
    /(?:^|[^A-Za-z0-9])pr[-_/\s]*(\d{1,6})(?=[^A-Za-z0-9]|$)/gi,
    /(?:^|[^A-Za-z0-9])pull[-_/\s]*(\d{1,6})(?=[^A-Za-z0-9]|$)/gi,
    /(?:^|[^A-Za-z0-9])issue[-_/\s]*(\d{1,6})(?=[^A-Za-z0-9]|$)/gi,
  ];
  for (const pattern of candidates) {
    for (const match of text.matchAll(pattern)) {
      const parsed = toInteger(match[1]);
      if (Number.isFinite(parsed)) {
        result.add(parsed);
      }
    }
  }
  return Array.from(result);
}

function extractPrNumbersFromConcurrency(value) {
  const text = String(value || '').trim();
  if (!text) {
    return [];
  }

  const numbers = new Set();
  const tokens = text.split('-').map((token) => token.trim()).filter(Boolean);
  for (let index = 0; index < tokens.length - 1; index += 1) {
    const marker = tokens[index].toLowerCase();
    if (!['orchestrator', 'worker', 'pr', 'issue'].includes(marker)) {
      continue;
    }
    const candidate = toInteger(tokens[index + 1]);
    if (Number.isFinite(candidate)) {
      numbers.add(candidate);
    }
  }
  return Array.from(numbers);
}

function parseMaybeJson(value) {
  if (!value) {
    return null;
  }
  if (typeof value === 'object') {
    return value;
  }
  if (typeof value !== 'string') {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  try {
    return JSON.parse(trimmed);
  } catch (error) {
    return null;
  }
}
// Support both canonical and common consumer gate workflow filenames
const GATE_WORKFLOW_FILES = ['pr-00-gate.yml', 'gate.yml'];

function normaliseLabelName(name) {
  return String(name || '')
    .trim()
    .toLowerCase();
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
        return normaliseLabelName(entry);
      }
      if (typeof entry.name === 'string') {
        return normaliseLabelName(entry.name);
      }
      return '';
    })
    .filter(Boolean);
}

function normaliseLogin(login) {
  return String(login || '')
    .trim()
    .toLowerCase()
    .replace(/\[bot\]$/i, '');
}

function isAutomationStatusComment(comment) {
  if (!comment) {
    return false;
  }
  const body = String(comment.body || '').replace(/\r\n/g, '\n').trim();
  if (!body) {
    return false;
  }
  const login = normaliseLogin(comment?.user?.login);
  const lower = body.toLowerCase();
  if (lower.includes('<!-- autofix-loop:')) {
    return true;
  }
  if (lower.startsWith('autofix attempt')) {
    return true;
  }
  if (AUTOMATION_LOGINS.has(login)) {
    const looksLikeInstruction = lower.startsWith('@codex') || lower.includes('<!-- codex-keepalive-marker') || lower.includes('<!-- agent-activation-marker');
    if (!looksLikeInstruction) {
      return true;
    }
  }
  return false;
}

function extractAgentAliases(labels) {
  const names = extractLabelNames(labels);
  const aliases = new Set();
  for (const name of names) {
    if (!name.startsWith(AGENT_LABEL_PREFIX)) {
      continue;
    }
    const alias = name.slice(AGENT_LABEL_PREFIX.length).trim();
    if (alias) {
      aliases.add(alias);
    }
  }
  return Array.from(aliases);
}

function parseRunCap(labels) {
  const names = extractLabelNames(labels);
  for (const name of names) {
    if (!name.startsWith(MAX_RUNS_PREFIX)) {
      continue;
    }
    const value = name.slice(MAX_RUNS_PREFIX.length).trim();
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed)) {
      const clamped = Math.min(MAX_RUN_CAP, Math.max(MIN_RUN_CAP, parsed));
      return clamped;
    }
  }
  return DEFAULT_RUN_CAP;
}

function escapeForRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function buildMentionPatterns(aliases) {
  return aliases.map((alias) => {
    const escaped = escapeForRegex(alias);
    return new RegExp(`(^|[^A-Za-z0-9_-])@${escaped}(?![A-Za-z0-9_-])`, 'i');
  });
}

function isHumanUser(user) {
  if (!user) {
    return false;
  }
  const type = String(user.type || '').toLowerCase();
  if (type === 'bot' || type === 'app') {
    return false;
  }
  const login = String(user.login || '').toLowerCase();
  if (!login) {
    return false;
  }
  if (login.endsWith('[bot]')) {
    return false;
  }
  return true;
}

function hasHumanMention(comment, patterns) {
  if (!comment || patterns.length === 0) {
    return false;
  }
  if (!isHumanUser(comment.user)) {
    return false;
  }
  const body = String(comment.body || '');
  if (!body) {
    return false;
  }
  return patterns.some((pattern) => pattern.test(body));
}

function normaliseTimestamp(value) {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return parsed;
}

function selectLatestComment(current, candidate) {
  if (!candidate || !candidate.id) {
    return current;
  }
  if (!current) {
    return candidate;
  }
  const currentTime = normaliseTimestamp(current.updated_at || current.created_at);
  const candidateTime = normaliseTimestamp(candidate.updated_at || candidate.created_at);
  if (candidateTime > currentTime) {
    return candidate;
  }
  return current;
}

function sanitiseComment(comment) {
  if (!comment || typeof comment !== 'object') {
    return null;
  }
  const idRaw = comment.id;
  const id = idRaw === undefined || idRaw === null ? '' : String(idRaw);
  const htmlUrl = typeof comment.html_url === 'string' ? comment.html_url : '';
  const userLogin = comment?.user?.login ?? '';
  const userType = comment?.user?.type ?? '';
  return {
    id,
    body: typeof comment.body === 'string' ? comment.body : '',
    html_url: htmlUrl,
    user: userLogin
      ? {
          login: userLogin,
          type: userType,
        }
      : null,
    created_at: comment.created_at || '',
    updated_at: comment.updated_at || '',
  };
}

async function detectHumanActivation({ core, github, owner, repo, prNumber, aliases, comments }) {
  const logPrefix = '[human-activation]';
  const logInfo = (message) => {
    if (core && typeof core.info === 'function') {
      core.info(`${logPrefix} ${message}`);
    }
  };

  if (!Array.isArray(aliases) || aliases.length === 0) {
    logInfo('Skipped scan: no agent aliases provided.');
    return null;
  }
  const patterns = buildMentionPatterns(aliases);
  let latest = null;

  logInfo(
    `Scanning PR #${prNumber ?? 'unknown'} for human activation via aliases [${aliases.join(', ')}] (prefetched comments=${
      Array.isArray(comments) ? comments.length : 0
    }).`
  );

  const considerComment = (comment) => {
    if (!comment) {
      return;
    }
    if (hasHumanMention(comment, patterns)) {
      const updated = selectLatestComment(latest, comment);
      if (updated !== latest) {
        const author = comment?.user?.login || '(unknown)';
        const created = comment?.created_at || comment?.updated_at || '(no timestamp)';
        logInfo(
          `Found activation candidate comment ${comment.id || '(no id)'} by ${author} at ${created}; replacing previous candidate ${
            latest?.id || 'none'
          }.`
        );
        latest = updated;
      }
    }
  };

  if (Array.isArray(comments) && comments.length > 0) {
    for (const comment of comments) {
      considerComment(comment);
    }
  }

  const iterator = github.paginate.iterator(github.rest.issues.listComments, {
    owner,
    repo,
    issue_number: prNumber,
    per_page: 100,
  });

  for await (const page of iterator) {
    const entries = Array.isArray(page?.data) ? page.data : page;
    if (!Array.isArray(entries)) {
      continue;
    }
    for (const comment of entries) {
      considerComment(comment);
    }
  }

  if (latest) {
    const author = latest?.user?.login || '(unknown)';
    const created = latest?.created_at || latest?.updated_at || '(no timestamp)';
    logInfo(`Selected activation comment ${latest.id || '(no id)'} by ${author} at ${created}.`);
  } else {
    logInfo('No qualifying human activation comment found.');
  }

  return latest;
}

const STATUS_RANK = {
  completed: 3,
  in_progress: 2,
  queued: 1,
};

const CONCLUSION_RANK = {
  success: 6,
  neutral: 5,
  failure: 4,
  skipped: 3,
  cancelled: 2,
  timed_out: 1,
  action_required: 0,
  stale: 0,
};

function scoreWorkflowRun(run) {
  if (!run) {
    return null;
  }
  const status = String(run.status || '').toLowerCase();
  const conclusion = String(run.conclusion || '').toLowerCase();
  const startedAt = normaliseTimestamp(run.run_started_at || run.created_at);
  const runNumber = Number(run.run_number || 0) || 0;
  const runId = Number(run.id || 0) || 0;
  return {
    run,
    status,
    conclusion,
    startedAt,
    runNumber,
    runId,
    statusRank: STATUS_RANK[status] ?? 0,
    conclusionRank: CONCLUSION_RANK[conclusion] ?? 0,
  };
}

function compareWorkflowRunScores(a, b) {
  if (!a && !b) {
    return 0;
  }
  if (!a) {
    return 1;
  }
  if (!b) {
    return -1;
  }
  if (a.startedAt !== b.startedAt) {
    return b.startedAt - a.startedAt;
  }
  if (a.statusRank !== b.statusRank) {
    return b.statusRank - a.statusRank;
  }
  if (a.conclusionRank !== b.conclusionRank) {
    return b.conclusionRank - a.conclusionRank;
  }
  if (a.runNumber !== b.runNumber) {
    return b.runNumber - a.runNumber;
  }
  if (a.runId !== b.runId) {
    return b.runId - a.runId;
  }
  return 0;
}

async function fetchGateStatus({ github, owner, repo, headSha, core }) {
  const normalisedSha = String(headSha || '').trim();
  if (!normalisedSha) {
    return { found: false, success: false, status: '', conclusion: '' };
  }
  
  // Try each gate workflow filename until we find runs
  for (const workflowFile of GATE_WORKFLOW_FILES) {
    try {
      const runs = await paginateWithBackoff(github, github.rest.actions.listWorkflowRuns, {
        owner,
        repo,
        workflow_id: workflowFile,
        head_sha: normalisedSha,
        per_page: 100,
      }, { core });

      const scoredRuns = [];
      for (const run of runs) {
        if (!run) {
          continue;
        }
        const runSha = String(run.head_sha || '').trim();
        if (runSha && runSha !== normalisedSha) {
          continue;
        }
        const scored = scoreWorkflowRun(run);
        if (scored) {
          scoredRuns.push(scored);
        }
      }

      if (scoredRuns.length === 0) {
        // No runs found for this workflow file, try the next one
        continue;
      }

      scoredRuns.sort(compareWorkflowRunScores);
      const latest = scoredRuns[0]?.run;

      if (!latest) {
        continue;
      }

      const status = String(latest.status || '').toLowerCase();
      const conclusion = String(latest.conclusion || '').toLowerCase();
      const success = status === 'completed' && conclusion === 'success';

      return {
        found: true,
        success,
        status,
        conclusion,
        run: latest,
        workflowFile,
      };
    } catch (error) {
      // Log but continue to next workflow file
      const message = error instanceof Error ? error.message : String(error);
      if (core?.warning) {
        core.warning(`Gate status check failed for ${workflowFile}: ${message}`);
      }
      continue;
    }
  }
  
  // No gate workflow runs found in any of the expected files
  return { found: false, success: false, status: '', conclusion: '' };
}

/**
 * Count active workflow runs for a PR.
 * 
 * PERFORMANCE OPTIMIZATIONS (v2):
 * - Skip per-run detail fetches - use data from list results directly
 * - Match PR using multiple signals (pull_requests array, head branch, SHA, concurrency)
 * - Still uses paginate for test compatibility
 */
async function countActive({
  github,
  owner,
  repo,
  prNumber,
  headSha,
  headRef,
  currentRunId,
  includeWorker = false,
  workflows,
  completedLookbackSeconds = 0,
  core = null,
}) {
  const targetPr = Number(prNumber);
  if (!Number.isFinite(targetPr) || targetPr <= 0) {
    return { active: 0, breakdown: new Map(), runIds: new Set(), error: null };
  }

  const includeRecentCompleted = Number.isFinite(completedLookbackSeconds) && completedLookbackSeconds > 0;
  const lookbackMillis = includeRecentCompleted ? Math.max(0, completedLookbackSeconds) * 1000 : 0;
  const statuses = includeRecentCompleted ? ['queued', 'in_progress', 'completed'] : ['queued', 'in_progress'];
  
  let workflowFiles = Array.isArray(workflows)
    ? workflows.filter((entry) => typeof entry === 'string' && entry.trim().length > 0)
    : [];
  if (workflowFiles.length === 0) {
    workflowFiles = [ORCHESTRATOR_WORKFLOW_FILE];
    if (includeWorker) {
      workflowFiles.push(WORKER_WORKFLOW_FILE);
    }
  }

  const runIds = new Set();
  const breakdown = new Map();
  let error = null;

  const normalisedHeadRef = normaliseBranch(headRef);
  const normalisedHeadSha = String(headSha || '').trim();
  const currentRunNumeric = Number(currentRunId);
  const recentCutoff = includeRecentCompleted ? Date.now() - lookbackMillis : 0;

  const resolveCompletionTimestamp = (run) => {
    if (!run) return 0;
    return normaliseTimestamp(run.updated_at || run.run_started_at || run.created_at);
  };

  /**
   * Fetch workflow run details to access inputs (needed for dispatch events).
   * Returns null on error to allow graceful degradation.
   */
  const fetchRunDetails = async (runId) => {
    if (!github?.rest?.actions?.getWorkflowRun) return null;
    try {
      const response = await github.rest.actions.getWorkflowRun({
        owner,
        repo,
        run_id: runId,
      });
      return response?.data || null;
    } catch (err) {
      // Graceful degradation - log but don't fail
      if (core?.info) {
        core.info(`fetchRunDetails(${runId}) failed: ${err instanceof Error ? err.message : String(err)}`);
      }
      return null;
    }
  };

  /**
   * Check if dispatch run inputs contain the target PR number.
   * Orchestrator runs carry PR number in options_json or pr_number inputs.
   */
  const checkDispatchInputsForPr = (inputs) => {
    if (!inputs || typeof inputs !== 'object') return false;

    // Check direct pr_number input
    const directPr = Number(inputs.pr_number ?? inputs.pr);
    if (Number.isFinite(directPr) && directPr === targetPr) {
      return true;
    }

    // Check options_json which may contain { pr: <number> }
    const optionsRaw = inputs.options_json || inputs.options || '';
    const parsedOptions = parseMaybeJson(optionsRaw);
    if (parsedOptions && typeof parsedOptions === 'object') {
      const optionsPr = Number(parsedOptions.pr ?? parsedOptions.keepalive_pr);
      if (Number.isFinite(optionsPr) && optionsPr === targetPr) {
        return true;
      }
    }

    // Check params_json which may also contain PR reference
    const paramsRaw = inputs.params_json || inputs.params || '';
    const parsedParams = parseMaybeJson(paramsRaw);
    if (parsedParams && typeof parsedParams === 'object') {
      const paramsPr = Number(parsedParams.pr ?? parsedParams.pull_request);
      if (Number.isFinite(paramsPr) && paramsPr === targetPr) {
        return true;
      }
    }

    return false;
  };

  /**
   * PR matching with fast path for most runs + fallback for dispatch events.
   * OPTIMIZATION: Only fetches run details for dispatch events where inputs are needed.
   */
  const runMatchesPr = async (run) => {
    if (!run) return false;

    // Skip current run
    if (Number.isFinite(currentRunNumeric) && currentRunNumeric > 0) {
      const runId = Number(run.id || 0);
      if (Number.isFinite(runId) && runId === currentRunNumeric) {
        return false;
      }
    }

    // Check pull_requests array (most reliable)
    if (Array.isArray(run.pull_requests) && run.pull_requests.length > 0) {
      for (const pr of run.pull_requests) {
        const candidate = Number(pr?.number);
        if (Number.isFinite(candidate) && candidate === targetPr) {
          return true;
        }
      }
    }

    // Check head SHA
    const runHeadSha = String(run.head_sha || '').trim();
    if (normalisedHeadSha && runHeadSha && runHeadSha === normalisedHeadSha) {
      return true;
    }

    // Check head branch
    const runHeadBranch = normaliseBranch(run.head_branch);
    if (normalisedHeadRef && runHeadBranch && runHeadBranch === normalisedHeadRef) {
      return true;
    }

    // Check concurrency group for PR number
    const concurrencyNumbers = extractPrNumbersFromConcurrency(run.concurrency);
    if (concurrencyNumbers.includes(targetPr)) {
      return true;
    }

    // Check text fields for PR number mention
    const textCandidates = [run.name, run.display_title, runHeadBranch];
    for (const text of textCandidates) {
      const numbers = extractPrNumbersFromText(text || '');
      if (numbers.includes(targetPr)) {
        return true;
      }
    }

    // For dispatch events, we MUST fetch run details to check inputs.
    // listWorkflowRuns doesn't expose inputs, but getWorkflowRun does.
    // This is the only reliable way to detect orchestrator runs for a specific PR.
    const runEvent = String(run.event || '').toLowerCase();
    if (runEvent === 'workflow_dispatch' || runEvent === 'repository_dispatch') {
      const runId = Number(run.id || 0);
      if (Number.isFinite(runId) && runId > 0) {
        const details = await fetchRunDetails(runId);
        if (details?.inputs && checkDispatchInputsForPr(details.inputs)) {
          return true;
        }
      }
    }

    return false;
  };

  for (const workflowFile of workflowFiles) {
    const label = workflowFile === WORKER_WORKFLOW_FILE ? 'worker' : 'orchestrator';
    for (const status of statuses) {
      try {
        const runs = await paginateWithBackoff(github, github.rest.actions.listWorkflowRuns, {
          owner,
          repo,
          workflow_id: workflowFile,
          status,
          per_page: 100,
        }, { core });
        for (const run of runs) {
          const runId = Number(run?.id || 0);
          if (!Number.isFinite(runId) || runId <= 0) {
            continue;
          }
          if (runIds.has(runId)) {
            continue;
          }
          if (!(await runMatchesPr(run))) {
            continue;
          }

          if (status === 'completed') {
            if (!includeRecentCompleted) {
              continue;
            }
            const completedAt = resolveCompletionTimestamp(run);
            if (completedAt < recentCutoff) {
              continue;
            }
          }

          runIds.add(runId);
          const bucket = status === 'completed' ? `${label}_recent` : label;
          breakdown.set(bucket, (breakdown.get(bucket) || 0) + 1);
        }
      } catch (err) {
        if (!error) {
          error = err instanceof Error ? err.message : String(err);
        }
      }
    }
  }

  return {
    active: runIds.size,
    breakdown,
    runIds,
    error,
  };
}

async function evaluateRunCapForPr({
  core,
  github,
  owner,
  repo,
  prNumber,
  headSha = '',
  headRef = '',
  includeWorker = false,
  currentRunId,
} = {}) {
  const number = Number(prNumber);
  if (!Number.isFinite(number) || number <= 0) {
    return {
      ok: false,
      reason: 'missing-pr-number',
      runCap: DEFAULT_RUN_CAP,
      activeRuns: 0,
      breakdown: {},
      headSha: '',
      headRef: '',
    };
  }

  let pull;
  try {
    pull = await fetchPullRequestCached({ github, owner, repo, prNumber: number, core });
    if (!pull) {
      throw new Error('pull request data unavailable');
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (core?.warning) {
      core.warning(`Run cap evaluation failed to load PR #${number}: ${message}`);
    }
    return {
      ok: false,
      reason: 'pr-fetch-failed',
      runCap: DEFAULT_RUN_CAP,
      activeRuns: 0,
      breakdown: {},
      error: message,
      headSha: '',
      headRef: '',
    };
  }

  const labels = Array.isArray(pull?.labels) ? pull.labels : [];
  const runCap = parseRunCap(labels);
  const resolvedHeadSha = String(headSha || pull?.head?.sha || '').trim();
  const resolvedHeadRef = String(headRef || pull?.head?.ref || '').trim();

  const { active, breakdown, error } = await countActive({
    github,
    owner,
    repo,
    prNumber: number,
    headSha: resolvedHeadSha,
    headRef: resolvedHeadRef,
    includeWorker,
    currentRunId,
    completedLookbackSeconds: RECENT_COMPLETED_LOOKBACK_SECONDS,
    core,
  });

  if (error && core?.warning) {
    core.warning(`Run cap evaluation encountered an error while counting runs: ${error}`);
  }

  const ok = active < runCap;
  const reason = ok ? 'ok' : 'run-cap-reached';

  return {
    ok,
    reason,
    runCap,
    activeRuns: active,
    breakdown: breakdown ? Object.fromEntries(breakdown) : {},
    error: error || null,
    headSha: resolvedHeadSha,
    headRef: resolvedHeadRef,
  };
}

async function evaluateKeepaliveGate({ core, github, context, options = {} }) {
  const { owner, repo } = context.repo || {};
  if (!owner || !repo) {
    throw new Error('Repository context missing owner or repo.');
  }

  const {
    prNumber: rawPrNumber,
    headSha: inputHeadSha,
    requireHumanActivation = false,
    allowPendingGate = false,
    allowPendingGateForAutomation = true,
    requireGateSuccess = false,
    comments,
    pullRequest,
    currentRunId,
  } = options;

  let prNumber = Number(rawPrNumber);
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    const candidate = Number(pullRequest?.number);
    if (Number.isFinite(candidate) && candidate > 0) {
      prNumber = candidate;
    }
  }

  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    return {
      ok: false,
      reason: 'missing-pr-number',
      hasKeepaliveLabel: false,
      hasHumanActivation: false,
      gateConcluded: false,
      gateSucceeded: false,
      underRunCap: false,
      runCap: DEFAULT_RUN_CAP,
      activeRuns: 0,
      agentAliases: [],
      primaryAgent: '',
      headSha: '',
      headRef: '',
      hasSyncRequiredLabel: false,
      hasActivatedLabel: false,
      hasPauseLabel: false,
      requireHumanActivation: false,
      activationComment: null,
      gateStatus: { found: false, success: false, status: '', conclusion: '' },
      pendingGate: false,
    };
  }

  let pr = pullRequest || null;
  if (!pr) {
    try {
      pr = await fetchPullRequestCached({ github, owner, repo, prNumber, core });
      if (!pr) {
        throw new Error('pull request data unavailable');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        ok: false,
        reason: 'pr-fetch-failed',
        hasKeepaliveLabel: false,
        hasHumanActivation: false,
        gateConcluded: false,
        gateSucceeded: false,
        underRunCap: false,
        runCap: DEFAULT_RUN_CAP,
        activeRuns: 0,
        agentAliases: [],
        primaryAgent: '',
        headSha: '',
        headRef: '',
        hasSyncRequiredLabel: false,
        hasActivatedLabel: false,
        hasPauseLabel: false,
        requireHumanActivation: false,
        activationComment: null,
        gateStatus: { found: false, success: false, status: '', conclusion: '' },
        pendingGate: false,
        error: message,
      };
    }
  }

  const headSha = inputHeadSha || pr?.head?.sha || '';
  const headRef = pr?.head?.ref || '';
  const labels = Array.isArray(pr?.labels) ? pr.labels : [];
  const labelNames = extractLabelNames(labels);
  const hasKeepaliveLabel = labelNames.includes(KEEPALIVE_LABEL);
  const hasPauseLabel = labelNames.includes(PAUSE_LABEL);
  const hasActivatedLabel = labelNames.includes(ACTIVATED_LABEL);
  const hasSyncRequiredLabel = labelNames.includes(SYNC_REQUIRED_LABEL);
  const agentAliases = extractAgentAliases(labels);
  const primaryAgent = agentAliases[0] || '';

  let humanActivation = false;
  let activationComment = null;
  const shouldCheckHumanActivation = hasKeepaliveLabel && agentAliases.length > 0;
  const requireHuman = Boolean(requireHumanActivation) && !hasActivatedLabel;

  if (shouldCheckHumanActivation) {
    try {
      activationComment = await detectHumanActivation({
        core,
        github,
        owner,
        repo,
        prNumber,
        aliases: agentAliases,
        comments,
      });
      humanActivation = Boolean(activationComment);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      core.warning(`Failed to evaluate human activation comments: ${message}`);
      humanActivation = false;
    }
  }

  const gateStatus = await fetchGateStatus({
    github,
    owner,
    repo,
    headSha,
    core,
  });
  if (gateStatus.error) {
    core.warning(`Gate status check failed: ${gateStatus.error}`);
  }

  const gateFound = gateStatus.found === true;
  const gateConcluded = gateStatus.status === 'completed';
  const gateSucceeded = gateConcluded && gateStatus.success === true;

  const runCap = parseRunCap(labels);
  const automationCommentDetected = Array.isArray(comments)
    ? comments.some((comment) => isAutomationStatusComment(comment))
    : false;
  const allowPendingGateResolved = allowPendingGate || (automationCommentDetected && allowPendingGateForAutomation);
  const { active: activeRuns, breakdown: activeBreakdown, error: runError } = await countActive({
    github,
    owner,
    repo,
    prNumber,
    headSha,
    headRef,
    currentRunId,
    workflows: [ORCHESTRATOR_WORKFLOW_FILE],
    completedLookbackSeconds: RECENT_COMPLETED_LOOKBACK_SECONDS,
    core,
  });
  if (runError) {
    core.warning(`Run cap evaluation encountered an error while counting runs: ${runError}`);
  }
  const underRunCap = activeRuns < runCap;

  let ok = true;
  let reason = 'ok';
  let pendingGate = false;

  if (hasPauseLabel) {
    ok = false;
    reason = 'keepalive-paused';
  } else if (hasSyncRequiredLabel) {
    ok = false;
    reason = 'sync-required';
  } else if (!hasKeepaliveLabel) {
    ok = false;
    reason = 'keepalive-label-missing';
  } else if (requireHuman && !humanActivation) {
    ok = false;
    reason = 'no-human-activation';
  }

  if (ok) {
    if (!gateFound) {
      if (allowPendingGateResolved) {
        pendingGate = true;
        if (reason === 'ok') {
          reason = 'gate-pending';
        }
      } else {
        ok = false;
        reason = 'gate-run-missing';
      }
    } else if (!gateConcluded) {
      if (allowPendingGateResolved) {
        pendingGate = true;
        if (reason === 'ok') {
          reason = 'gate-pending';
        }
      } else {
        ok = false;
        reason = 'gate-not-concluded';
      }
    } else if (requireGateSuccess && !gateSucceeded) {
      ok = false;
      reason = 'gate-not-success';
    }
  }

  if (ok && !underRunCap) {
    ok = false;
    reason = 'run-cap-reached';
  }

  if (!ok && core?.info) {
    const gateSummary = `Gate status: found=${gateFound} concluded=${gateConcluded} success=${gateSucceeded}`;
    const capSummary = `Run cap snapshot: active=${activeRuns} cap=${runCap}`;
    core.info(`${gateSummary}; ${capSummary}; reason=${reason}`);
  }

  return {
    ok,
    reason,
    prNumber,
    hasKeepaliveLabel,
    hasHumanActivation: humanActivation,
    gateConcluded,
    gateSucceeded,
    underRunCap,
    runCap,
    cap: runCap,
    activeRuns,
    active: activeRuns,
    activeBreakdown: activeBreakdown ? Object.fromEntries(activeBreakdown) : {},
    agentAliases,
    primaryAgent,
    headSha,
    headRef,
    hasPauseLabel,
    lastGreenSha: gateSucceeded ? headSha : '',
    hasSyncRequiredLabel,
    hasActivatedLabel,
    requireHumanActivation: requireHuman,
    activationComment: sanitiseComment(activationComment),
    gateStatus,
    pendingGate,
  };
}

module.exports = {
  evaluateKeepaliveGate: async function ({ core, github: rawGithub, context, options = {} }) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return evaluateKeepaliveGate({ core, github, context, options });
  },
  countActive: async function ({ github: rawGithub, core, ...rest }) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return countActive({ github, core, ...rest });
  },
  evaluateRunCapForPr: async function ({ github: rawGithub, core, ...rest }) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return evaluateRunCapForPr({ github, core, ...rest });
  },
};
