'use strict';

const fs = require('fs');
const path = require('path');

const { parseScopeTasksAcceptanceSections } = require('./issue_scope_parser');
const { createGithubApiCache } = require('./github-api-cache-client');
const { loadKeepaliveState, formatStateComment } = require('./keepalive_state');
const { resolvePromptMode } = require('./keepalive_prompt_routing');
const { classifyError, ERROR_CATEGORIES } = require('./error_classifier');
const { formatFailureComment } = require('./failure_comment_formatter');
const { detectConflicts } = require('./conflict_detector');
const { parseTimeoutConfig } = require('./timeout_config');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper');

// Token load balancer for rate limit management
let tokenLoadBalancer = null;
try {
  tokenLoadBalancer = require('./token_load_balancer');
} catch (error) {
  // Load balancer not available - will use fallback
}

const ATTEMPT_HISTORY_LIMIT = 5;
const ATTEMPTED_TASK_LIMIT = 6;

const TIMEOUT_VARIABLE_NAMES = [
  'WORKFLOW_TIMEOUT_DEFAULT',
  'WORKFLOW_TIMEOUT_EXTENDED',
  'WORKFLOW_TIMEOUT_WARNING_RATIO',
  'WORKFLOW_TIMEOUT_WARNING_MINUTES',
];

// NOTE: Prompt files live under .github/codex/prompts/ — this directory name is
// an API contract (baked into consumer repos). The prompts are agent-agnostic.
const PROMPT_ROUTES = {
  fix_ci: {
    mode: 'fix_ci',
    file: '.github/codex/prompts/fix_ci_failures.md',
  },
  conflict: {
    mode: 'conflict',
    file: '.github/codex/prompts/fix_merge_conflicts.md',
  },
  verify: {
    mode: 'verify',
    file: '.github/codex/prompts/verifier_acceptance_check.md',
  },
  normal: {
    mode: 'normal',
    file: '.github/codex/prompts/keepalive_next_task.md',
  },
};

// Resolve default agent from registry
let _defaultAgent = 'codex';
try {
  const { loadAgentRegistry } = require('./agent_registry.js');
  _defaultAgent = loadAgentRegistry().default_agent || 'codex';
} catch (_) { /* registry not available */ }

function normalise(value) {
  return String(value ?? '').trim();
}

function resolvePromptRouting({ scenario, mode, action, reason } = {}) {
  const resolvedMode = resolvePromptMode({ scenario, mode, action, reason });
  return PROMPT_ROUTES[resolvedMode] || PROMPT_ROUTES.normal;
}

function toBool(value, defaultValue = false) {
  const raw = normalise(value);
  if (!raw) return Boolean(defaultValue);
  if (['true', 'yes', '1', 'on', 'enabled'].includes(raw.toLowerCase())) {
    return true;
  }
  if (['false', 'no', '0', 'off', 'disabled'].includes(raw.toLowerCase())) {
    return false;
  }
  return Boolean(defaultValue);
}

function toNumber(value, fallback = 0) {
  if (value === null || value === undefined || value === '') {
    return Number.isFinite(fallback) ? Number(fallback) : 0;
  }
  const parsed = Number(value);
  if (Number.isFinite(parsed)) {
    return parsed;
  }
  const int = parseInt(String(value), 10);
  if (Number.isFinite(int)) {
    return int;
  }
  return Number.isFinite(fallback) ? Number(fallback) : 0;
}

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const parsed = Number(value);
  if (Number.isFinite(parsed)) {
    return parsed;
  }
  const int = parseInt(String(value), 10);
  if (Number.isFinite(int)) {
    return int;
  }
  return null;
}

function normaliseWarningRatio(value) {
  if (!Number.isFinite(value)) {
    return null;
  }
  if (value > 1 && value <= 100) {
    return value / 100;
  }
  return value;
}

function buildAttemptEntry({
  iteration,
  action,
  reason,
  runResult,
  promptMode,
  promptFile,
  gateConclusion,
  errorCategory,
  errorType,
  tasksTotal,
  tasksUnchecked,
  tasksCompletedDelta,
  allComplete,
}) {
  const actionValue = normalise(action) || 'unknown';
  const reasonValue = normalise(reason) || actionValue;
  const entry = {
    iteration: Math.max(0, toNumber(iteration, 0)),
    action: actionValue,
    reason: reasonValue,
  };

  if (runResult) {
    entry.run_result = normalise(runResult);
  }
  if (promptMode) {
    entry.prompt_mode = normalise(promptMode);
  }
  if (promptFile) {
    entry.prompt_file = normalise(promptFile);
  }
  if (gateConclusion) {
    entry.gate = normalise(gateConclusion);
  }
  if (errorCategory) {
    entry.error_category = normalise(errorCategory);
  }
  if (errorType) {
    entry.error_type = normalise(errorType);
  }
  if (Number.isFinite(tasksTotal)) {
    entry.tasks_total = Math.max(0, Math.floor(tasksTotal));
  }
  if (Number.isFinite(tasksUnchecked)) {
    entry.tasks_unchecked = Math.max(0, Math.floor(tasksUnchecked));
  }
  if (Number.isFinite(tasksCompletedDelta)) {
    entry.tasks_completed_delta = Math.max(0, Math.floor(tasksCompletedDelta));
  }
  if (typeof allComplete === 'boolean') {
    entry.all_complete = allComplete;
  }

  return entry;
}

function updateAttemptHistory(existing, nextEntry, limit = ATTEMPT_HISTORY_LIMIT) {
  const history = Array.isArray(existing)
    ? existing.filter((item) => item && typeof item === 'object')
    : [];
  if (!nextEntry || typeof nextEntry !== 'object') {
    return history.slice(-limit);
  }
  const trimmed = history.slice(-limit);
  const last = trimmed[trimmed.length - 1];
  if (
    last &&
    last.iteration === nextEntry.iteration &&
    last.action === nextEntry.action &&
    last.reason === nextEntry.reason
  ) {
    return [...trimmed.slice(0, -1), { ...last, ...nextEntry }];
  }
  return [...trimmed, nextEntry].slice(-limit);
}

function normaliseTaskText(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function normaliseTaskKey(value) {
  return normaliseTaskText(value).toLowerCase();
}

function normaliseAttemptedTasks(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  const entries = [];
  value.forEach((entry) => {
    if (typeof entry === 'string') {
      const task = normaliseTaskText(entry);
      if (task) {
        entries.push({ task, key: normaliseTaskKey(task) });
      }
      return;
    }
    if (entry && typeof entry === 'object') {
      const task = normaliseTaskText(entry.task || entry.text || '');
      if (!task) {
        return;
      }
      entries.push({
        ...entry,
        task,
        key: normaliseTaskKey(entry.key || task),
      });
    }
  });
  return entries;
}

function updateAttemptedTasks(existing, nextTask, iteration, limit = ATTEMPTED_TASK_LIMIT) {
  const history = normaliseAttemptedTasks(existing);
  const taskText = normaliseTaskText(nextTask);
  if (!taskText) {
    return history.slice(-limit);
  }
  const key = normaliseTaskKey(taskText);
  const trimmed = history.filter((entry) => entry.key !== key).slice(-limit);
  const entry = {
    task: taskText,
    key,
    iteration: Math.max(0, toNumber(iteration, 0)),
    timestamp: new Date().toISOString(),
  };
  return [...trimmed, entry].slice(-limit);
}

function resolveDurationMs({ durationMs, startTs }) {
  if (Number.isFinite(durationMs)) {
    return Math.max(0, Math.floor(durationMs));
  }
  if (!Number.isFinite(startTs)) {
    return 0;
  }
  const startMs = startTs > 1e12 ? startTs : startTs * 1000;
  const delta = Date.now() - startMs;
  return Math.max(0, Math.floor(delta));
}

function getGithubApiCache({ github, core }) {
  if (github && github.__keepaliveApiCache) {
    return github.__keepaliveApiCache;
  }
  const cache = createGithubApiCache({ core });
  if (github) {
    Object.defineProperty(github, '__keepaliveApiCache', {
      value: cache,
      enumerable: false,
      configurable: false,
      writable: false,
    });
  }
  return cache;
}

async function fetchPullRequestCached({ github, context, prNumber, core }) {
  if (!github?.rest?.pulls?.get || !context?.repo?.owner || !context?.repo?.repo) {
    return null;
  }
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    return null;
  }
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const cache = getGithubApiCache({ github, core });
  const key = cache.buildPrCacheKey({ owner, repo, number: prNumber, resource: 'pulls.get' });
  return cache.getOrSet({
    key,
    fetcher: async () => {
      const { data } = await github.rest.pulls.get({
        owner,
        repo,
        pull_number: prNumber,
      });
      return data;
    },
  });
}

async function fetchPrFilesCached({ github, context, prNumber, core }) {
  if (!github?.rest?.pulls?.listFiles || !context?.repo?.owner || !context?.repo?.repo) {
    return [];
  }
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    return [];
  }
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const cache = getGithubApiCache({ github, core });
  const key = cache.buildPrCacheKey({ owner, repo, number: prNumber, resource: 'pulls.listFiles' });
  return cache.getOrSet({
    key,
    fetcher: async () => {
      const { data } = await github.rest.pulls.listFiles({
        owner,
        repo,
        pull_number: prNumber,
        per_page: 100,
      });
      return Array.isArray(data) ? data : [];
    },
  });
}

async function fetchPrLabels({ github, context, prNumber, core }) {
  if (!github?.rest?.pulls?.get || !context?.repo?.owner || !context?.repo?.repo) {
    return [];
  }
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    return [];
  }
  try {
    const pr = await fetchPullRequestCached({ github, context, prNumber, core });
    const rawLabels = Array.isArray(pr?.labels) ? pr.labels : [];
    return rawLabels.map((label) => normalise(label?.name).toLowerCase()).filter(Boolean);
  } catch (error) {
    if (core) {
      core.info(`Failed to fetch PR labels for timeout config: ${error.message}`);
    }
    return [];
  }
}

async function fetchRepoVariables({ github, context, core, names = [] }) {
  if (!github?.rest?.actions?.listRepoVariables || !context?.repo?.owner || !context?.repo?.repo) {
    return {};
  }

  const wanted = new Set((names || []).map((name) => normalise(name)).filter(Boolean));
  if (!wanted.size) {
    return {};
  }

  const results = {};
  let page = 1;
  const perPage = 100;

  try {
    while (true) {
      const { data } = await github.rest.actions.listRepoVariables({
        owner: context.repo.owner,
        repo: context.repo.repo,
        per_page: perPage,
        page,
      });
      const variables = Array.isArray(data?.variables) ? data.variables : [];
      for (const variable of variables) {
        const name = normalise(variable?.name);
        if (!wanted.has(name)) {
          continue;
        }
        results[name] = normalise(variable?.value);
      }
      if (variables.length < perPage || Object.keys(results).length === wanted.size) {
        break;
      }
      page += 1;
    }
  } catch (error) {
    if (core) {
      core.debug(`Repository variables not accessible for timeout config (using defaults): ${error.message}`);
    }
  }

  return results;
}

async function resolveWorkflowRunStartMs({ github, context, core }) {
  const payloadStartedAt =
    context?.payload?.workflow_run?.run_started_at ??
    context?.payload?.workflow_run?.created_at;
  if (payloadStartedAt) {
    const parsed = Date.parse(payloadStartedAt);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  if (!github?.rest?.actions?.getWorkflowRun) {
    return null;
  }
  const runId = context?.runId || context?.run_id;
  if (!runId || !context?.repo?.owner || !context?.repo?.repo) {
    return null;
  }
  try {
    const { data } = await github.rest.actions.getWorkflowRun({
      owner: context.repo.owner,
      repo: context.repo.repo,
      run_id: runId,
    });
    const startedAt = data?.run_started_at;
    if (!startedAt) {
      return null;
    }
    const parsed = Date.parse(startedAt);
    return Number.isFinite(parsed) ? parsed : null;
  } catch (error) {
    if (core) {
      core.info(`Failed to fetch workflow run start time: ${error.message}`);
    }
    return null;
  }
}

async function resolveElapsedMs({ github, context, inputs, core }) {
  const durationMs = resolveDurationMs({
    durationMs: toOptionalNumber(
      inputs?.elapsed_ms ??
      inputs?.elapsedMs ??
      inputs?.duration_ms ??
      inputs?.durationMs
    ),
    startTs: toOptionalNumber(inputs?.start_ts ?? inputs?.startTs),
  });
  if (durationMs > 0) {
    return durationMs;
  }
  const runStartMs = await resolveWorkflowRunStartMs({ github, context, core });
  if (!Number.isFinite(runStartMs)) {
    return 0;
  }
  return Math.max(0, Date.now() - runStartMs);
}

function buildTimeoutStatus({
  timeoutConfig,
  elapsedMs,
  warningRatio = 0.8,
  warningRemainingMs = 5 * 60 * 1000,
} = {}) {
  const resolvedMinutes = Number.isFinite(timeoutConfig?.resolvedMinutes)
    ? timeoutConfig.resolvedMinutes
    : null;
  const timeoutMs = Number.isFinite(resolvedMinutes) ? resolvedMinutes * 60 * 1000 : null;
  const elapsedSafe = Number.isFinite(elapsedMs) && elapsedMs > 0 ? elapsedMs : null;
  let remainingMs = null;
  let usageRatio = null;
  let warning = null;

  if (timeoutMs && elapsedSafe !== null) {
    remainingMs = Math.max(0, timeoutMs - elapsedSafe);
    usageRatio = Math.min(1, elapsedSafe / timeoutMs);
    const remainingMinutes = Math.ceil(remainingMs / 60000);
    const usagePercent = Math.round(usageRatio * 100);
    const thresholdPercent = Number.isFinite(warningRatio) ? Math.round(warningRatio * 100) : null;
    const thresholdRemainingMinutes = Number.isFinite(warningRemainingMs)
      ? Math.ceil(warningRemainingMs / 60000)
      : null;
    const warnByRatio = usageRatio >= warningRatio;
    const warnByRemaining = remainingMs <= warningRemainingMs;
    if (warnByRatio || warnByRemaining) {
      warning = {
        percent: usagePercent,
        remaining_minutes: remainingMinutes,
        threshold_percent: thresholdPercent,
        threshold_remaining_minutes: thresholdRemainingMinutes,
        reason: warnByRemaining ? 'remaining' : 'usage',
      };
    }
  }

  return {
    defaultMinutes: timeoutConfig?.defaultMinutes ?? null,
    extendedMinutes: timeoutConfig?.extendedMinutes ?? null,
    overrideMinutes: timeoutConfig?.overrideMinutes ?? null,
    resolvedMinutes,
    source: timeoutConfig?.source ?? '',
    label: timeoutConfig?.label ?? null,
    timeoutMs,
    elapsedMs: elapsedSafe,
    remainingMs,
    usageRatio,
    warning,
  };
}

function resolveTimeoutWarningConfig({ inputs = {}, env = process.env, variables = {} } = {}) {
  const warningMinutes = toOptionalNumber(
    inputs.timeout_warning_minutes ??
    inputs.timeoutWarningMinutes ??
    env.WORKFLOW_TIMEOUT_WARNING_MINUTES ??
    variables.WORKFLOW_TIMEOUT_WARNING_MINUTES ??
    env.TIMEOUT_WARNING_MINUTES ??
    variables.TIMEOUT_WARNING_MINUTES
  );
  const warningRatioRaw = toOptionalNumber(
    inputs.timeout_warning_ratio ??
    inputs.timeoutWarningRatio ??
    env.WORKFLOW_TIMEOUT_WARNING_RATIO ??
    variables.WORKFLOW_TIMEOUT_WARNING_RATIO ??
    env.TIMEOUT_WARNING_RATIO ??
    variables.TIMEOUT_WARNING_RATIO
  );
  const warningRatio = normaliseWarningRatio(warningRatioRaw);
  const config = {};
  if (Number.isFinite(warningMinutes) && warningMinutes > 0) {
    config.warningRemainingMs = warningMinutes * 60 * 1000;
  }
  if (Number.isFinite(warningRatio) && warningRatio > 0 && warningRatio <= 1) {
    config.warningRatio = warningRatio;
  }
  return config;
}

function resolveTimeoutInputs({ inputs = {}, context } = {}) {
  const payloadInputs = context?.payload?.inputs;
  if (!payloadInputs || typeof payloadInputs !== 'object') {
    return inputs;
  }
  return { ...payloadInputs, ...inputs };
}

function formatTimeoutMinutes(minutes) {
  if (!Number.isFinite(minutes)) {
    return '0';
  }
  return String(Math.max(0, Math.round(minutes)));
}

function formatTimeoutUsage({ elapsedMs, usageRatio, remainingMs }) {
  if (!Number.isFinite(elapsedMs) || !Number.isFinite(usageRatio)) {
    return '';
  }
  const elapsedMinutes = Math.floor(elapsedMs / 60000);
  const usagePercent = Math.round(usageRatio * 100);
  const remainingMinutes = Number.isFinite(remainingMs)
    ? Math.ceil(Math.max(0, remainingMs) / 60000)
    : null;
  if (remainingMinutes === null) {
    return `${elapsedMinutes}m elapsed (${usagePercent}%)`;
  }
  return `${elapsedMinutes}m elapsed (${usagePercent}%, ${remainingMinutes}m remaining)`;
}

function formatTimeoutWarning(warning) {
  if (!warning || typeof warning !== 'object') {
    return '';
  }
  const percent = Number.isFinite(warning.percent) ? warning.percent : null;
  const remaining = Number.isFinite(warning.remaining_minutes) ? warning.remaining_minutes : null;
  const reason = warning.reason === 'remaining' ? 'remaining threshold' : 'usage threshold';
  const parts = [];
  if (percent !== null) {
    parts.push(`${percent}% consumed`);
  }
  if (remaining !== null) {
    parts.push(`${remaining}m remaining`);
  }
  if (!parts.length) {
    return '';
  }
  return `${parts.join(', ')} (${reason})`;
}

function buildMetricsRecord({
  prNumber,
  iteration,
  action,
  errorCategory,
  durationMs,
  tasksTotal,
  tasksComplete,
}) {
  return {
    pr_number: toNumber(prNumber, 0),
    iteration: Math.max(1, toNumber(iteration, 0)),
    timestamp: new Date().toISOString(),
    action: normalise(action) || 'unknown',
    error_category: normalise(errorCategory) || 'none',
    duration_ms: Math.max(0, toNumber(durationMs, 0)),
    tasks_total: Math.max(0, toNumber(tasksTotal, 0)),
    tasks_complete: Math.max(0, toNumber(tasksComplete, 0)),
  };
}

function emitMetricsRecord({ core, record }) {
  if (core && typeof core.setOutput === 'function') {
    core.setOutput('metrics_record_json', JSON.stringify(record));
  }
}

function resolveMetricsPath(inputs) {
  const explicitPath = normalise(
    inputs.metrics_path ??
    inputs.metricsPath ??
    process.env.KEEPALIVE_METRICS_PATH ??
    process.env.keepalive_metrics_path
  );
  if (explicitPath) {
    return explicitPath;
  }
  const githubActions = normalise(process.env.GITHUB_ACTIONS).toLowerCase();
  const workspace = normalise(process.env.GITHUB_WORKSPACE);
  if (githubActions === 'true' && workspace) {
    return path.join(workspace, 'keepalive-metrics.ndjson');
  }
  return '';
}

async function appendMetricsRecord({ core, record, metricsPath }) {
  const targetPath = normalise(metricsPath);
  if (!targetPath) {
    return;
  }
  try {
    const absolutePath = path.resolve(targetPath);
    await fs.promises.mkdir(path.dirname(absolutePath), { recursive: true });
    await fs.promises.appendFile(absolutePath, `${JSON.stringify(record)}\n`, 'utf8');
  } catch (error) {
    if (core && typeof core.warning === 'function') {
      core.warning(`keepalive metrics write failed: ${error.message}`);
    }
  }
}

async function writeStepSummary({
  core,
  iteration,
  maxIterations,
  tasksTotal,
  tasksUnchecked,
  tasksCompletedDelta,
  agentFilesChanged,
  outcome,
}) {
  if (!core?.summary || typeof core.summary.addRaw !== 'function') {
    return;
  }
  const total = Number.isFinite(tasksTotal) ? tasksTotal : 0;
  const unchecked = Number.isFinite(tasksUnchecked) ? tasksUnchecked : 0;
  const completed = Math.max(0, total - unchecked);
  const iterationLabel = maxIterations > 0 ? `${iteration}/${maxIterations}` : `${iteration}/∞`;
  const filesChanged = Number.isFinite(agentFilesChanged) ? agentFilesChanged : 0;
  const delta = Number.isFinite(tasksCompletedDelta) ? tasksCompletedDelta : null;
  const rows = [
    `| Iteration | ${iterationLabel} |`,
    `| Tasks completed | ${completed}/${total} |`,
  ];
  if (delta !== null) {
    rows.push(`| Tasks completed this run | ${delta} |`);
  }
  rows.push(`| Files changed | ${filesChanged} |`);
  rows.push(`| Outcome | ${outcome || 'unknown'} |`);
  const summaryLines = [
    '### Keepalive iteration summary',
    '',
    '| Field | Value |',
    '| --- | --- |',
    ...rows,
  ];
  await core.summary.addRaw(summaryLines.join('\n')).addEOL().write();
}

function countCheckboxes(markdown) {
  // Apply parent-child cascade before counting so that checked parents
  // automatically cascade to their indented children.
  const cascaded = cascadeParentCheckboxes(String(markdown || ''));
  const result = { total: 0, checked: 0, unchecked: 0 };
  const regex = /(?:^|\n)\s*(?:[-*+]|\d+[.)])\s*\[( |x|X)\]/g;
  let match;
  while ((match = regex.exec(cascaded)) !== null) {
    result.total += 1;
    if ((match[1] || '').toLowerCase() === 'x') {
      result.checked += 1;
    } else {
      result.unchecked += 1;
    }
  }
  return result;
}

/**
 * Cascade checked parent checkboxes to their indented children.
 *
 * When a parent checkbox line is checked (`[x]`), all immediately following
 * lines that are indented deeper and contain unchecked checkboxes (`[ ]`) are
 * also checked.  The cascade stops when a line at the same or lesser
 * indentation as the parent is encountered.
 *
 * This solves the bookkeeping problem where top-level tasks get checked off
 * (because Codex completes the work and the reconciler matches the parent),
 * but the automatically-generated sub-tasks ("Define scope for: …",
 * "Implement focused slice for: …", "Validate focused slice for: …") remain
 * unchecked — causing the keepalive loop to believe work remains.
 *
 * @param {string} body - Markdown text (typically the PR body or task section).
 * @returns {string} The body with sub-task checkboxes cascaded from checked parents.
 */
function cascadeParentCheckboxes(body) {
  if (!body) return body;
  const lines = body.split('\n');
  const result = [];
  // Track the indentation level of the most recent checked parent (if any).
  // null means we are not inside a cascading region.
  let parentIndent = null;
  // Track whether we are inside a fenced code block (``` or ~~~).
  let inCodeBlock = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Detect code fence boundaries — reset cascade and skip contents.
    if (/^\s*(`{3,}|~{3,})/.test(line)) {
      inCodeBlock = !inCodeBlock;
      parentIndent = null;
      result.push(line);
      continue;
    }
    if (inCodeBlock) {
      result.push(line);
      continue;
    }

    // Match checkbox lines: optional indent, bullet, [x] or [ ]
    const cbMatch = line.match(/^(\s*)([-*+]|\d+[.)])\s*\[([ xX])\]\s*/);
    if (!cbMatch) {
      // Non-checkbox line — reset cascade if it's a heading or blank section break
      if (/^\s*$/.test(line) || /^#{1,6}\s/.test(line)) {
        parentIndent = null;
      }
      result.push(line);
      continue;
    }

    const indent = cbMatch[1].length;
    const checked = cbMatch[3].toLowerCase() === 'x';

    if (parentIndent !== null && indent > parentIndent) {
      // This is a child of the current checked parent — cascade the check
      if (!checked) {
        result.push(line.replace(/\[\s+\]/, '[x]'));
      } else {
        result.push(line);
      }
      continue;
    }

    // This line is at the same or lesser indentation — it may be a new parent
    parentIndent = null;
    if (checked) {
      parentIndent = indent;
    }
    result.push(line);
  }

  return result.join('\n');
}

function normaliseChecklistSection(content) {
  const raw = String(content || '');
  if (!raw.trim()) {
    return raw;
  }
  const lines = raw.split('\n');
  let mutated = false;

  const updated = lines.map((line) => {
    // Match bullet points (-, *, +) or numbered lists, for example: 1., 2., 3. or 1), 2), 3).
    const match = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (!match) {
      return line;
    }
    const [, indent, bullet, remainderRaw] = match;
    const remainder = remainderRaw.trim();
    if (!remainder) {
      return line;
    }
    // If already a checkbox, preserve it
    if (/^\[[ xX]\]/.test(remainder)) {
      return `${indent}${bullet} ${remainder}`;
    }

    mutated = true;
    return `${indent}${bullet} [ ] ${remainder}`;
  });
  return mutated ? updated.join('\n') : raw;
}

function normaliseChecklistSections(sections = {}) {
  return {
    ...sections,
    tasks: normaliseChecklistSection(sections.tasks),
    acceptance: normaliseChecklistSection(sections.acceptance),
  };
}

function classifyFailureDetails({ action, runResult, summaryReason, agentExitCode, agentSummary }) {
  const runFailed = action === 'run' && runResult && runResult !== 'success';
  const shouldClassify = runFailed || (action && action !== 'run' && summaryReason);
  if (!shouldClassify) {
    return { category: '', type: '', recovery: '', message: '' };
  }

  const message = [agentSummary, summaryReason, runResult].filter(Boolean).join(' ');
  const errorInfo = classifyError({ message, code: agentExitCode });
  let category = errorInfo.category;
  const isGateCancelled = summaryReason.startsWith('gate-cancelled');

  // If the agent runner reports failure with exit code 0, that strongly suggests
  // an infrastructure/control-plane hiccup rather than a code/tool failure.
  if (runFailed && summaryReason === 'agent-run-failed' && (!agentExitCode || agentExitCode === '0')) {
    category = ERROR_CATEGORIES.transient;
  }

  // Detect dirty git state issues - agent saw unexpected changes before starting.
  // These are typically workflow artifacts (.workflows-lib, agent session *.jsonl)
  // that should have been cleaned up but weren't. Classify as transient.
  const dirtyGitPatterns = [
    /unexpected\s*changes/i,
    /\.workflows-lib.*modified/i,
    /codex-session.*untracked/i, // Codex-specific session artifact pattern
    /agent-session.*untracked/i,
    /existing\s*changes/i,
    /how\s*would\s*you\s*like\s*me\s*to\s*proceed/i,
    /before\s*making\s*edits/i,
  ];
  if (dirtyGitPatterns.some(pattern => pattern.test(message))) {
    category = ERROR_CATEGORIES.transient;
  }

  if (runFailed && (runResult === 'cancelled' || runResult === 'skipped')) {
    category = ERROR_CATEGORIES.transient;
  }
  if (!runFailed && isGateCancelled) {
    category = ERROR_CATEGORIES.transient;
  }

  let type = '';
  if (runFailed) {
    if (category === ERROR_CATEGORIES.transient) {
      type = 'infrastructure';
    } else if (agentExitCode && agentExitCode !== '0') {
      type = 'agent';
    } else {
      type = 'infrastructure';
    }
  } else {
    type = 'infrastructure';
  }


  return {
    category,
    type,
    recovery: errorInfo.recovery,
    message: errorInfo.message,
  };
}

const SOURCE_CONTEXT_HEADINGS = new Set(['context for agent']);

function isCodeFenceLine(line) {
  return /^(`{3,}|~{3,})/.test(String(line || '').trim());
}

function parseHeading(line) {
  const match = String(line || '').match(/^\s*(#{1,6})\s+(.*)$/);
  if (!match) {
    return null;
  }
  const level = match[1].length;
  const title = match[2].replace(/\s*:\s*$/, '').trim();
  if (!title) {
    return null;
  }
  return { level, title };
}

function isSourceHeading(title) {
  return /^source\b/i.test(title);
}

function isSourceContinuationHeading(title) {
  return SOURCE_CONTEXT_HEADINGS.has(String(title || '').toLowerCase());
}

/**
 * Extract Source section from PR/issue body that contains links to parent issues/PRs.
 * @param {string} body - PR or issue body text
 * @returns {string|null} Source section content or null if not found
 */
function extractSourceSection(body) {
  const text = String(body || '');
  if (!text.trim()) {
    return null;
  }

  const lines = text.split('\n');
  let insideCodeBlock = false;
  let startIndex = -1;
  let sourceLevel = null;

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (isCodeFenceLine(line)) {
      insideCodeBlock = !insideCodeBlock;
      continue;
    }
    if (insideCodeBlock) {
      continue;
    }
    const heading = parseHeading(line);
    if (heading && isSourceHeading(heading.title)) {
      startIndex = i + 1;
      sourceLevel = heading.level;
      break;
    }
  }

  if (startIndex < 0 || sourceLevel === null) {
    return null;
  }

  const captured = [];
  insideCodeBlock = false;

  for (let i = startIndex; i < lines.length; i += 1) {
    const line = lines[i];
    if (isCodeFenceLine(line)) {
      insideCodeBlock = !insideCodeBlock;
      captured.push(line);
      continue;
    }
    if (!insideCodeBlock) {
      const heading = parseHeading(line);
      if (heading && heading.level <= sourceLevel && !isSourceContinuationHeading(heading.title)) {
        break;
      }
    }
    captured.push(line);
  }

  const content = captured.join('\n').trim();
  if (content && /#\d+|github\.com/i.test(content)) {
    return content;
  }
  return null;
}

function extractChecklistItems(markdown) {
  const items = [];
  const content = String(markdown || '');
  const regex = /(?:^|\n)\s*(?:[-*+]|\d+[.)])\s*\[( |x|X)\]\s*(.+)/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    const checked = (match[1] || '').toLowerCase() === 'x';
    const text = normaliseTaskText(match[2] || '');
    if (text) {
      items.push({ text, checked });
    }
  }
  return items;
}

/**
 * Build the task appendix that gets passed to the agent prompt.
 * This provides explicit, structured tasks and acceptance criteria.
 * @param {object} sections - Parsed scope/tasks/acceptance sections
 * @param {object} checkboxCounts - { total, checked, unchecked }
 * @param {object} [state] - Optional keepalive state for reconciliation info
 * @param {object} [options] - Additional options
 * @param {string} [options.prBody] - Full PR body to extract Source section from
 */
function buildTaskAppendix(sections, checkboxCounts, state = {}, options = {}) {
  const lines = [];

  lines.push('---');
  lines.push('## PR Tasks and Acceptance Criteria');
  lines.push('');
  lines.push(`**Progress:** ${checkboxCounts.checked}/${checkboxCounts.total} tasks complete, ${checkboxCounts.unchecked} remaining`);
  lines.push('');

  // Add reconciliation reminder if the previous iteration made changes but didn't check off tasks
  if (state.needs_task_reconciliation) {
    lines.push('### ⚠️ IMPORTANT: Task Reconciliation Required');
    lines.push('');
    lines.push(`The previous iteration changed **${state.last_files_changed || 'some'} file(s)** but did not update task checkboxes.`);
    lines.push('');
    lines.push('**Before continuing, you MUST:**');
    lines.push('1. Review the recent commits to understand what was changed');
    lines.push('2. Determine which task checkboxes should be marked complete');
    lines.push('3. Update the PR body to check off completed tasks');
    lines.push('4. Then continue with remaining tasks');
    lines.push('');
    lines.push('_Failure to update checkboxes means progress is not being tracked properly._');
    lines.push('');
  }

  if (sections?.scope) {
    lines.push('### Scope');
    lines.push(sections.scope);
    lines.push('');
  }

  if (sections?.tasks) {
    lines.push('### Tasks');
    lines.push('Complete these in order. Mark checkbox done ONLY after implementation is verified:');
    lines.push('');
    lines.push(sections.tasks);
    lines.push('');
  }

  if (sections?.acceptance) {
    lines.push('### Acceptance Criteria');
    lines.push('The PR is complete when ALL of these are satisfied:');
    lines.push('');
    lines.push(sections.acceptance);
    lines.push('');
  }

  const attemptedTasks = normaliseAttemptedTasks(state?.attempted_tasks);
  const candidateSource = sections?.tasks || sections?.acceptance || '';
  const taskItems = extractChecklistItems(candidateSource);
  const unchecked = taskItems.filter((item) => !item.checked);
  const attemptedKeys = new Set(attemptedTasks.map((entry) => entry.key));
  const suggested = unchecked.find((item) => !attemptedKeys.has(normaliseTaskKey(item.text))) || unchecked[0];

  if (attemptedTasks.length > 0) {
    lines.push('### Recently Attempted Tasks');
    lines.push('Avoid repeating these unless a task needs explicit follow-up:');
    lines.push('');
    attemptedTasks.slice(-3).forEach((entry) => {
      lines.push(`- ${entry.task}`);
    });
    lines.push('');
  }

  if (suggested?.text) {
    lines.push('### Suggested Next Task');
    lines.push(`- ${suggested.text}`);
    lines.push('');
  }

  // Add Source section if PR body contains links to parent issues/PRs
  if (options.prBody) {
    const sourceSection = extractSourceSection(options.prBody);
    if (sourceSection) {
      lines.push('### Source Context');
      lines.push('_For additional background, check these linked issues/PRs:_');
      lines.push('');
      lines.push(sourceSection);
      lines.push('');
    }
  }

  lines.push('---');

  return lines.join('\n');
}

async function fetchPrBody({ github, context, prNumber, core }) {
  if (!github?.rest?.pulls?.get || !context?.repo?.owner || !context?.repo?.repo) {
    return '';
  }
  try {
    const pr = await fetchPullRequestCached({ github, context, prNumber, core });
    return String(pr?.body || '');
  } catch (error) {
    if (core) {
      core.info(`Failed to fetch PR body for task focus: ${error.message}`);
    }
    return '';
  }
}

function extractConfigSnippet(body) {
  const source = String(body || '');
  if (!source.trim()) {
    return '';
  }

  // API contract: both naming variants exist in production PR bodies
  const commentBlockPatterns = [
    /<!--\s*keepalive-config:start\s*-->([\s\S]*?)<!--\s*keepalive-config:end\s*-->/i,
    /<!--\s*codex-config:start\s*-->([\s\S]*?)<!--\s*codex-config:end\s*-->/i,
    /<!--\s*keepalive-config:\s*({[\s\S]*?})\s*-->/i,
  ];
  for (const pattern of commentBlockPatterns) {
    const match = source.match(pattern);
    if (match && match[1]) {
      return match[1].trim();
    }
  }

  const headingBlock = source.match(
    /(#+\s*(?:Keepalive|Codex)\s+config[^\n]*?)\n+```[a-zA-Z0-9_-]*\n([\s\S]*?)```/i
  );
  if (headingBlock && headingBlock[2]) {
    return headingBlock[2].trim();
  }

  return '';
}

function parseConfigFromSnippet(snippet) {
  const trimmed = normalise(snippet);
  if (!trimmed) {
    return {};
  }

  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed === 'object') {
      return parsed;
    }
  } catch (error) {
    // fall back to key/value parsing
  }

  const result = {};
  const lines = trimmed.split(/\r?\n/);
  for (const line of lines) {
    const candidate = line.trim();
    if (!candidate || candidate.startsWith('#')) {
      continue;
    }
    const match = candidate.match(/^([^:=\s]+)\s*[:=]\s*(.+)$/);
    if (!match) {
      continue;
    }
    const key = match[1].trim();
    const rawValue = match[2].trim();
    const cleanedValue = rawValue.replace(/\s+#.*$/, '').replace(/\s+\/\/.*$/, '').trim();
    if (!key) {
      continue;
    }
    const lowered = cleanedValue.toLowerCase();
    if (['true', 'false', 'yes', 'no', 'on', 'off'].includes(lowered)) {
      result[key] = ['true', 'yes', 'on'].includes(lowered);
    } else if (!Number.isNaN(Number(cleanedValue))) {
      result[key] = Number(cleanedValue);
    } else {
      result[key] = cleanedValue;
    }
  }

  return result;
}

function normaliseConfig(config = {}) {
  const cfg = config && typeof config === 'object' ? config : {};
  const trace = normalise(cfg.trace || cfg.keepalive_trace);
  const promptMode = normalise(cfg.prompt_mode ?? cfg.promptMode);
  const promptFile = normalise(cfg.prompt_file ?? cfg.promptFile);
  const promptScenario = normalise(cfg.prompt_scenario ?? cfg.promptScenario);
  return {
    keepalive_enabled: toBool(
      cfg.keepalive_enabled ?? cfg.enable_keepalive ?? cfg.keepalive,
      true
    ),
    autofix_enabled: toBool(cfg.autofix_enabled ?? cfg.autofix, false),
    iteration: toNumber(cfg.iteration ?? cfg.keepalive_iteration, 0),
    max_iterations: toNumber(cfg.max_iterations ?? cfg.keepalive_max_iterations, 5),
    failure_threshold: toNumber(cfg.failure_threshold ?? cfg.keepalive_failure_threshold, 3),
    trace,
    prompt_mode: promptMode,
    prompt_file: promptFile,
    prompt_scenario: promptScenario,
  };
}

function parseConfig(body) {
  const snippet = extractConfigSnippet(body);
  const parsed = parseConfigFromSnippet(snippet);
  return normaliseConfig(parsed);
}

function formatProgressBar(current, total, width = 10) {
  if (!Number.isFinite(total) || total <= 0) {
    return 'n/a';
  }
  const safeWidth = Number.isFinite(width) && width > 0 ? Math.floor(width) : 10;
  const bounded = Math.max(0, Math.min(current, total));
  const filled = Math.round((bounded / total) * safeWidth);
  const empty = Math.max(0, safeWidth - filled);
  return `[${'#'.repeat(filled)}${'-'.repeat(empty)}] ${bounded}/${total}`;
}

async function resolvePrNumber({ github, context, core, payload: overridePayload }) {
  const payload = overridePayload || context.payload || {};
  const eventName = context.eventName;

  // Support explicit PR number from override payload (for workflow_dispatch)
  if (overridePayload?.workflow_run?.pull_requests?.[0]?.number) {
    return overridePayload.workflow_run.pull_requests[0].number;
  }

  if (eventName === 'pull_request' && payload.pull_request) {
    return payload.pull_request.number;
  }

  if (eventName === 'workflow_run' && payload.workflow_run) {
    const pr = Array.isArray(payload.workflow_run.pull_requests)
      ? payload.workflow_run.pull_requests[0]
      : null;
    if (pr && pr.number) {
      return pr.number;
    }
    const headSha = payload.workflow_run.head_sha;
    if (headSha && github?.rest?.repos?.listPullRequestsAssociatedWithCommit) {
      try {
        const { data } = await github.rest.repos.listPullRequestsAssociatedWithCommit({
          owner: context.repo.owner,
          repo: context.repo.repo,
          commit_sha: headSha,
        });
        if (Array.isArray(data) && data[0]?.number) {
          return data[0].number;
        }
      } catch (error) {
        if (core) core.info(`Unable to resolve PR from head sha: ${error.message}`);
      }
    }
  }

  return 0;
}

/**
 * Classify gate failure type to determine appropriate fix mode
 * @returns {Object} { failureType: 'test'|'mypy'|'lint'|'none'|'unknown', shouldFixMode: boolean, failedJobs: string[] }
 */
async function classifyGateFailure({ github, context, pr, core }) {
  if (!pr) {
    return { failureType: 'unknown', shouldFixMode: false, failedJobs: [] };
  }

  try {
    // Get the latest Gate workflow run
    const { data } = await github.rest.actions.listWorkflowRuns({
      owner: context.repo.owner,
      repo: context.repo.repo,
      workflow_id: 'pr-00-gate.yml',
      branch: pr.head.ref,
      event: 'pull_request',
      per_page: 5,
    });

    const run = data?.workflow_runs?.find((r) => r.head_sha === pr.head.sha);
    if (!run || run.conclusion === 'success') {
      return { failureType: 'none', shouldFixMode: false, failedJobs: [] };
    }

    // Get jobs for this run to identify what failed
    const { data: jobsData } = await github.rest.actions.listJobsForWorkflowRun({
      owner: context.repo.owner,
      repo: context.repo.repo,
      run_id: run.id,
    });

    const failedJobs = (jobsData?.jobs || [])
      .filter((job) => job.conclusion === 'failure')
      .map((job) => job.name.toLowerCase());

    if (failedJobs.length === 0) {
      return { failureType: 'unknown', shouldFixMode: false, failedJobs: [] };
    }

    // Classify failure type based on job names
    const hasTestFailure = failedJobs.some((name) =>
      name.includes('test') || name.includes('pytest') || name.includes('unittest')
    );
    const hasMypyFailure = failedJobs.some((name) =>
      name.includes('mypy') || name.includes('type') || name.includes('typecheck')
    );
    const hasLintFailure = failedJobs.some((name) =>
      name.includes('lint') || name.includes('ruff') || name.includes('black') || name.includes('format')
    );

    // Determine primary failure type (prioritize test > mypy > lint)
    let failureType = 'unknown';
    if (hasTestFailure) {
      failureType = 'test';
    } else if (hasMypyFailure) {
      failureType = 'mypy';
    } else if (hasLintFailure) {
      failureType = 'lint';
    }

    // Only route to fix mode for test/mypy failures
    // Lint failures should go to autofix
    const shouldFixMode = failureType === 'test' || failureType === 'mypy' || failureType === 'unknown';

    if (core) {
      core.info(`[keepalive] Gate failure classification: type=${failureType}, shouldFixMode=${shouldFixMode}, failedJobs=[${failedJobs.join(', ')}]`);
    }

    return { failureType, shouldFixMode, failedJobs };
  } catch (error) {
    if (core) core.info(`Failed to classify gate failure: ${error.message}`);
    return { failureType: 'unknown', shouldFixMode: true, failedJobs: [] };
  }
}


async function resolveGateConclusion({ github, context, pr, eventName, payload, core }) {
  const run = await resolveGateRun({ github, context, pr, eventName, payload, core });
  return run.conclusion;
}

async function resolveGateRun({ github, context, pr, eventName, payload, core }) {
  if (eventName === 'workflow_run') {
    return {
      conclusion: normalise(payload?.workflow_run?.conclusion),
      runId: payload?.workflow_run?.id ? Number(payload.workflow_run.id) : 0,
    };
  }

  if (!pr) {
    return { conclusion: '', runId: 0 };
  }

  try {
    const { data } = await github.rest.actions.listWorkflowRuns({
      owner: context.repo.owner,
      repo: context.repo.repo,
      workflow_id: 'pr-00-gate.yml',
      branch: pr.head.ref,
      event: 'pull_request',
      per_page: 20,
    });
    if (Array.isArray(data?.workflow_runs)) {
      const match = data.workflow_runs.find((run) => run.head_sha === pr.head.sha);
      if (match) {
        return {
          conclusion: normalise(match.conclusion),
          runId: Number(match.id) || 0,
        };
      }
      const latest = data.workflow_runs[0];
      if (latest) {
        return {
          conclusion: normalise(latest.conclusion),
          runId: Number(latest.id) || 0,
        };
      }
    }
  } catch (error) {
    if (core) core.info(`Failed to resolve Gate conclusion: ${error.message}`);
  }

  return { conclusion: '', runId: 0 };
}

function extractCheckRunId(job) {
  const directId = Number(job?.check_run_id);
  if (Number.isFinite(directId) && directId > 0) {
    return directId;
  }
  const url = normalise(job?.check_run_url ?? job?.check_run?.url);
  const match = url.match(/\/check-runs\/(\d+)/i);
  if (match) {
    return Number(match[1]) || 0;
  }
  return 0;
}

const RATE_LIMIT_PATTERNS = [
  /rate limit/i,
  /rate[-\s]limit/i,
  /rate[-\s]limited/i,
  /secondary rate limit/i,
  /abuse detection/i,
  /too many requests/i,
  /api rate/i,
  /exceeded.*rate limit/i,
];

function hasRateLimitSignal(text) {
  const candidate = normalise(text);
  if (!candidate) {
    return false;
  }
  return RATE_LIMIT_PATTERNS.some((pattern) => pattern.test(candidate));
}

// Comment marker for rate limit notifications to prevent spam
const RATE_LIMIT_COMMENT_MARKER = '<!-- rate-limit-notification -->';
// Minimum time between rate limit notifications (1 hour in ms)
const RATE_LIMIT_NOTIFICATION_COOLDOWN_MS = 60 * 60 * 1000;

/**
 * Check if a rate limit notification was recently posted to avoid spam.
 * Looks for comments with the rate limit marker within the cooldown period.
 */
async function hasRecentRateLimitNotification({ github: rawGithub, context, prNumber, core }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  try {
    const { data: comments } = await github.rest.issues.listComments({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: prNumber,
      per_page: 20,
      sort: 'created',
      direction: 'desc',
    });

    const now = Date.now();
    for (const comment of comments) {
      if (comment.body && comment.body.includes(RATE_LIMIT_COMMENT_MARKER)) {
        const commentTime = new Date(comment.created_at).getTime();
        if (now - commentTime < RATE_LIMIT_NOTIFICATION_COOLDOWN_MS) {
          if (core) core.info(`Recent rate limit notification found (${Math.round((now - commentTime) / 60000)}m ago), skipping duplicate`);
          return true;
        }
      }
    }
    return false;
  } catch (error) {
    // If we can't check comments, assume no recent notification to be safe
    if (core) core.debug(`Failed to check for recent rate limit notifications: ${error.message}`);
    return false;
  }
}

/**
 * Post a rate limit notification to a PR and add the agent:rate-limited label.
 * This is called when rate limits prevent the agent from working.
 *
 * @param {Object} options
 * @param {Object} options.github - GitHub API client (should use a different token pool if possible)
 * @param {Object} options.context - GitHub Actions context
 * @param {Object} options.core - GitHub Actions core
 * @param {number} options.prNumber - PR number
 * @param {string} options.errorMessage - The rate limit error message
 * @param {string} options.resetTime - When the rate limit resets (ISO string)
 * @param {number} options.remaining - Remaining API calls
 * @param {string} options.action - The action that was being performed
 * @param {string} options.reason - The reason for the action
 * @returns {Object} { posted: boolean, labeled: boolean, skipped: boolean, error: string|null }
 */
async function postRateLimitNotification({
  github: rawGithub,
  context,
  core,
  prNumber,
  errorMessage,
  resetTime,
  remaining,
  action,
  reason,
}) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const result = { posted: false, labeled: false, skipped: false, error: null };

  if (!prNumber || !github?.rest?.issues) {
    result.error = 'Missing required parameters';
    return result;
  }

  try {
    // Check for recent notification to avoid spam
    const hasRecent = await hasRecentRateLimitNotification({ github, context, prNumber, core });
    if (hasRecent) {
      result.skipped = true;
      if (core) core.info('Skipping rate limit notification - recent notification exists');
      return result;
    }
  } catch (error) {
    // Continue even if check fails - better to potentially duplicate than to miss notification
    if (core) core.debug(`Rate limit notification check failed: ${error.message}`);
  }

  // Build the notification comment
  const resetTimeFormatted = resetTime || 'unknown';
  const commentBody = `${RATE_LIMIT_COMMENT_MARKER}
## ⚠️ Agent Paused - Rate Limit Reached

The keepalive loop has been **paused** because GitHub API rate limits have been exceeded.

| Field | Value |
|-------|-------|
| PR | #${prNumber} |
| Action | ${action || 'unknown'} |
| Reason | ${reason || 'rate-limit'} |
| Rate Limit Remaining | ${remaining ?? 'unknown'} |
| Rate Limit Reset | ${resetTimeFormatted} |
| Error | ${errorMessage || 'API rate limit exceeded'} |

### What this means
- The agent cannot make progress until rate limits reset
- The PR status comment may show as "running" but no work is being done
- This notification will not repeat for at least 1 hour

### To restart the agent
1. **Wait** for the rate limit to reset (see time above)
2. **Add** the \`agent:retry\` label to this PR
   - This will trigger the keepalive loop to retry
   - The \`agent:rate-limited\` label will be automatically removed

_If this happens frequently, consider adjusting workflow concurrency or rate limit capacity._
`;

  // Try to post the comment
  try {
    await github.rest.issues.createComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: prNumber,
      body: commentBody,
    });
    result.posted = true;
    if (core) core.info(`Posted rate limit notification to PR #${prNumber}`);
  } catch (error) {
    result.error = `Failed to post comment: ${error.message}`;
    if (core) core.warning(result.error);
  }

  // Try to add the label
  try {
    await github.rest.issues.addLabels({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: prNumber,
      labels: ['agent:rate-limited'],
    });
    result.labeled = true;
    if (core) core.info(`Added agent:rate-limited label to PR #${prNumber}`);
  } catch (error) {
    // Don't overwrite previous error
    const labelError = `Failed to add label: ${error.message}`;
    if (core) core.warning(labelError);
    if (!result.error) {
      result.error = labelError;
    }
  }

  return result;
}

function annotationsContainRateLimit(annotations = []) {
  for (const annotation of annotations) {
    const combined = [
      annotation?.message,
      annotation?.title,
      annotation?.raw_details,
    ]
      .filter(Boolean)
      .join(' ');
    if (hasRateLimitSignal(combined)) {
      return true;
    }
  }
  return false;
}

function extractRateLimitLogText(data) {
  if (!data) {
    return '';
  }
  const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data);
  if (buffer.length >= 2 && buffer[0] === 0x1f && buffer[1] === 0x8b) {
    try {
      const zlib = require('zlib');
      return zlib.gunzipSync(buffer).toString('utf8');
    } catch (error) {
      return buffer.toString('utf8');
    }
  }
  return buffer.toString('utf8');
}

function logContainsRateLimit(data) {
  const text = extractRateLimitLogText(data);
  if (!text) {
    return false;
  }
  const sample = text.length > 500000 ? `${text.slice(0, 250000)}\n${text.slice(-250000)}` : text;
  return hasRateLimitSignal(sample);
}

async function detectRateLimitCancellation({ github, context, runId, core }) {
  const targetRunId = Number(runId) || 0;
  if (!targetRunId || !github?.rest?.actions?.listJobsForWorkflowRun) {
    return false;
  }
  const canCheckAnnotations = Boolean(github?.rest?.checks?.listAnnotations);
  const canCheckLogs = Boolean(github?.rest?.actions?.downloadJobLogsForWorkflowRun);
  if (!canCheckAnnotations && !canCheckLogs) {
    if (core) core.info('Rate limit detection skipped; no annotations or logs API available.');
    return false;
  }

  try {
    const { data } = await github.rest.actions.listJobsForWorkflowRun({
      owner: context.repo.owner,
      repo: context.repo.repo,
      run_id: targetRunId,
      per_page: 100,
    });
    const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
    for (const job of jobs) {
      // Skip jobs that never ran — they have no logs to download and
      // querying them returns 404 ("Not Found"), producing noisy warnings.
      const jobStatusRaw = job?.status;
      const jobConclusionRaw = job?.conclusion;
      const jobStatus = String(jobStatusRaw || '').toLowerCase();
      const jobConclusion = String(jobConclusionRaw || '').toLowerCase();
      const hasStatus = typeof jobStatusRaw === 'string' && jobStatusRaw.trim() !== '';
      const hasConclusion = typeof jobConclusionRaw === 'string' && jobConclusionRaw.trim() !== '';
      const jobRan = (!hasStatus && !hasConclusion) ||
        (jobStatus === 'completed' && jobConclusion !== 'skipped');

      if (canCheckAnnotations) {
        const checkRunId = extractCheckRunId(job);
        if (checkRunId) {
          const params = {
            owner: context.repo.owner,
            repo: context.repo.repo,
            check_run_id: checkRunId,
            per_page: 100,
          };
          const annotations = github.paginate
            ? await github.paginate(github.rest.checks.listAnnotations, params)
            : (await github.rest.checks.listAnnotations(params))?.data;
          if (annotationsContainRateLimit(annotations)) {
            return true;
          }
        }
      }

      if (canCheckLogs) {
        const jobId = Number(job?.id) || 0;
        if (jobId && jobRan) {
          try {
            const logs = await github.rest.actions.downloadJobLogsForWorkflowRun({
              owner: context.repo.owner,
              repo: context.repo.repo,
              job_id: jobId,
            });
            if (logContainsRateLimit(logs?.data)) {
              return true;
            }
          } catch (error) {
            if (core) core.info(`Failed to inspect Gate job logs for rate limits: ${error.message}`);
          }
        }
      }
    }
  } catch (error) {
    if (core) core.info(`Failed to inspect Gate cancellation signals for rate limits: ${error.message}`);
  }

  return false;
}

/**
 * Check API rate limit status before starting operations.
 * Returns summary of available capacity across all tokens.
 *
 * @param {Object} options
 * @param {Object} options.github - GitHub API client
 * @param {Object} options.core - GitHub Actions core
 * @param {number} options.minRequired - Minimum API calls needed (default: 50)
 * @returns {Object} { canProceed, shouldDefer, totalRemaining, totalLimit, tokens, recommendation }
 */
async function checkRateLimitStatus({ github: rawGithub, core, minRequired = 50 }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  // First check the current token's rate limit (always available)
  let primaryRemaining = 5000;
  let primaryLimit = 5000;
  let primaryReset = null;

  try {
    if (github?.rest?.rateLimit?.get) {
      const { data } = await github.rest.rateLimit.get();
      primaryRemaining = data.resources.core.remaining;
      primaryLimit = data.resources.core.limit;
      primaryReset = data.resources.core.reset * 1000;
    }
  } catch (error) {
    core?.warning?.(`Failed to check primary rate limit: ${error.message}`);
  }

  const primaryPercentUsed = primaryLimit > 0
    ? ((primaryLimit - primaryRemaining) / primaryLimit * 100).toFixed(1)
    : 0;

  const result = {
    primary: {
      remaining: primaryRemaining,
      limit: primaryLimit,
      percentUsed: parseFloat(primaryPercentUsed),
      reset: primaryReset ? new Date(primaryReset).toISOString() : null,
    },
    tokens: [],
    totalRemaining: primaryRemaining,
    totalLimit: primaryLimit,
    canProceed: primaryRemaining >= minRequired,
    shouldDefer: false,
    recommendation: 'proceed',
  };

  // If load balancer is available AND initialized, check all tokens
  if (tokenLoadBalancer?.isInitialized?.()) {
    try {
      const summary = tokenLoadBalancer.getRegistrySummary();
      result.tokens = summary;

      // Calculate totals across all token pools
      let totalRemaining = 0;
      let totalLimit = 0;
      let healthyCount = 0;
      let criticalCount = 0;

      for (const token of summary) {
        const remaining = typeof token.rateLimit?.remaining === 'number'
          ? token.rateLimit.remaining
          : 0;
        const limit = typeof token.rateLimit?.limit === 'number'
          ? token.rateLimit.limit
          : 5000;

        totalRemaining += remaining;
        totalLimit += limit;

        if (token.status === 'healthy' || token.status === 'moderate') {
          healthyCount++;
        } else if (token.status === 'critical') {
          criticalCount++;
        }
      }

      result.totalRemaining = totalRemaining || primaryRemaining;
      result.totalLimit = totalLimit || primaryLimit;
      result.healthyTokens = healthyCount;
      result.criticalTokens = criticalCount;

      // Determine if we should defer
      result.shouldDefer = tokenLoadBalancer.shouldDefer(minRequired);
      result.canProceed = !result.shouldDefer && result.totalRemaining >= minRequired;

      // Calculate recommendation
      if (result.shouldDefer) {
        const minutesUntilReset = tokenLoadBalancer.getTimeUntilReset();
        result.recommendation = minutesUntilReset
          ? `defer-${minutesUntilReset}m`
          : 'defer-unknown';
      } else if (result.totalRemaining < minRequired * 3) {
        result.recommendation = 'proceed-with-caution';
      } else {
        result.recommendation = 'proceed';
      }
    } catch (error) {
      core?.debug?.(`Load balancer check failed: ${error.message}`);
    }
  } else {
    // Fallback: just use primary token status
    result.shouldDefer = primaryRemaining < minRequired;
    result.canProceed = primaryRemaining >= minRequired;

    if (result.shouldDefer) {
      const minutesUntilReset = primaryReset
        ? Math.max(0, Math.ceil((primaryReset - Date.now()) / 1000 / 60))
        : null;
      result.recommendation = minutesUntilReset
        ? `defer-${minutesUntilReset}m`
        : 'defer-unknown';
    }
  }

  // Log summary
  core?.info?.(`Rate limit status: ${result.totalRemaining}/${result.totalLimit} remaining, ` +
    `can proceed: ${result.canProceed}, recommendation: ${result.recommendation}`);

  return result;
}

async function evaluateKeepaliveLoop({ github: rawGithub, context, core, payload: overridePayload, overridePrNumber, forceRetry }) {
  // Wrap github client with rate-limit-aware retry for all API calls
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    core?.debug?.('GitHub client wrapped with rate-limit protection');
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const payload = overridePayload || context.payload || {};
  const cache = getGithubApiCache({ github, core });
  let prNumber = overridePrNumber || 0;
  if (cache?.invalidateForWebhook) {
    cache.invalidateForWebhook({
      eventName: context?.eventName,
      payload,
      owner: context?.repo?.owner,
      repo: context?.repo?.repo,
    });
  }

  // Check rate limit status early
  let rateLimitStatus = null;
  let rateLimitDefer = false;
  try {
    rateLimitStatus = await checkRateLimitStatus({ github, core, minRequired: 50 });
    rateLimitDefer = Boolean(rateLimitStatus?.shouldDefer) && !forceRetry;
    if (rateLimitDefer) {
      core?.info?.(`Rate limits exhausted - deferring. Recommendation: ${rateLimitStatus.recommendation}`);
    }
  } catch (error) {
    core?.warning?.(`Rate limit check failed: ${error.message} - continuing anyway`);
  }

  try {
    prNumber = overridePrNumber || await resolvePrNumber({ github, context, core, payload });
    if (!prNumber) {
      return {
        prNumber: 0,
        baseRef: '',
        action: 'skip',
        reason: 'pr-not-found',
      };
    }

    const pr = await fetchPullRequestCached({ github, context, prNumber, core });
    if (!pr) {
      throw new Error(`Failed to fetch PR #${prNumber} for keepalive loop`);
    }

    const gateRun = await resolveGateRun({
      github,
      context,
      pr,
      eventName: context.eventName,
      payload,
      core,
    });
    const gateConclusion = gateRun.conclusion;
    const gateNormalized = normalise(gateConclusion).toLowerCase();
    let gateRateLimit = false;

    const config = parseConfig(pr.body || '');
    const labels = Array.isArray(pr.labels)
      ? pr.labels.map((label) => normalise(label.name).toLowerCase())
      : [];

    // Phase 2: Resolve agent via registry helper when an explicit agent:* label is present.
    // Keepalive stays opt-in: no agent label => keepalive disabled.
    const labelObjects = Array.isArray(pr.labels) ? pr.labels : [];
    const agentPrefix = 'agent:';
    let routingLabelCandidates = labelObjects;
    let requestedAgentKeys = [];
    let hasAgentLabel = false;

    const nonRoutingAgentKeys = new Set(['needs-attention', 'rate-limited', 'retry']);

    try {
      const { loadAgentRegistry } = require('./agent_registry.js');
      const registry = loadAgentRegistry();
      const validAgentKeys = new Set(
        Object.keys(registry.agents || {}).map((key) => normalise(String(key || '')).toLowerCase()),
      );
      validAgentKeys.add('auto');

      const normalizedAgentLabels = labelObjects
        .map((label) => ({
          label,
          normalized: normalise(label.name).toLowerCase(),
        }))
        .filter(({ normalized }) => normalized.startsWith(agentPrefix));

      const routingEntries = normalizedAgentLabels
        .map(({ label, normalized }) => ({
          label,
          key: normalized.slice(agentPrefix.length),
        }))
        .filter(({ key }) => key && !nonRoutingAgentKeys.has(key));

      const registryEntries = routingEntries.filter(({ key }) => validAgentKeys.has(key));
      const entriesForRouting = registryEntries.length > 0 ? registryEntries : routingEntries;

      routingLabelCandidates = entriesForRouting.map(({ label }) => label);
      requestedAgentKeys = Array.from(
        new Set(entriesForRouting.map(({ key }) => key).filter(Boolean)),
      );
    } catch (error) {
      routingLabelCandidates = labelObjects.filter((label) => {
        const normalized = normalise(label.name).toLowerCase();
        if (!normalized.startsWith(agentPrefix)) {
          return false;
        }
        const key = normalized.slice(agentPrefix.length);
        return key && !nonRoutingAgentKeys.has(key);
      });
      requestedAgentKeys = Array.from(
        new Set(
          labels
            .filter((label) => label.startsWith(agentPrefix))
            .map((label) => label.slice(agentPrefix.length))
            .filter((key) => key && !nonRoutingAgentKeys.has(key)),
        ),
      );
    }

    hasAgentLabel = requestedAgentKeys.length > 0;
    let agentType = '';
    let agentRoutingMode = 'default';
    let delegationReason = '';
    let delegationShouldSwitch = false;
    if (hasAgentLabel) {
      try {
        const { resolveAgentRoutingFromLabels } = require('./agent_registry.js');
        const routing = resolveAgentRoutingFromLabels(routingLabelCandidates.length ? routingLabelCandidates : pr.labels);
        agentType = routing.agentKey;
        agentRoutingMode = routing.mode;
      } catch (error) {
        // Treat any routing failure (unknown agent, conflicting labels, missing helper)
        // as invalid to avoid enabling keepalive when no downstream runner is eligible.
        hasAgentLabel = false;
        agentType = '';
      }
    }
    const hasHighPrivilege = labels.includes('agent-high-privilege');
    const keepaliveEnabled = config.keepalive_enabled && hasAgentLabel;

    const sections = parseScopeTasksAcceptanceSections(pr.body || '');
    const normalisedSections = normaliseChecklistSections(sections);
    const combinedChecklist = [normalisedSections?.tasks, normalisedSections?.acceptance]
      .filter(Boolean)
      .join('\n');
    const checkboxCounts = countCheckboxes(combinedChecklist);
    const tasksPresent = checkboxCounts.total > 0;
    const tasksRemaining = checkboxCounts.unchecked > 0;
    const allComplete = tasksPresent && !tasksRemaining;

    const stateResult = await loadKeepaliveState({
      github,
      context,
      prNumber,
      trace: config.trace,
    });
    const state = stateResult.state || {};

    // agent:auto delegation — resolve actual agent via policy after state is available
    if (agentRoutingMode === 'auto') {
      try {
        const { decideNextAgent } = require('./agent_delegation_policy.js');
        const { loadAgentRegistry } = require('./agent_registry.js');
        const registry = loadAgentRegistry();
        // Build secrets availability from env vars set by the workflow
        const secrets = {};
        if (process.env.HAS_CODEX_AUTH === 'true') secrets.CODEX_AUTH_JSON = true;
        if (process.env.HAS_CLAUDE_AUTH === 'true') secrets.CLAUDE_AUTH_JSON = true;
        const decision = decideNextAgent({
          state,
          labels: labels.map(String),
          secrets,
          registry,
          core,
        });
        if (decision.agent) {
          agentType = decision.agent;
          delegationReason = decision.reason;
          delegationShouldSwitch = Boolean(decision.shouldSwitch);
          core?.info?.(`Delegation policy: ${decision.agent} (${decision.reason}, switch=${decision.shouldSwitch})`);
        } else {
          core?.warning?.(`Delegation policy returned no agent: ${decision.reason}`);
        }
      } catch (err) {
        core?.warning?.(`Delegation policy failed, keeping ${agentType}: ${err.message}`);
      }
    }

    // Prefer state iteration unless config explicitly sets it (0 from config is default, not explicit)
    const configHasExplicitIteration = config.iteration > 0;
    const iteration = configHasExplicitIteration ? config.iteration : toNumber(state.iteration, 0);
    const maxIterations = toNumber(config.max_iterations ?? state.max_iterations, 5);
    const failureThreshold = toNumber(config.failure_threshold ?? state.failure_threshold, 3);
    const progressReviewThreshold = toNumber(config.progress_review_threshold ?? state.progress_review_threshold, 4);
    const completeGateFailureMax = Math.max(
      1,
      toNumber(config.complete_gate_failure_rounds ?? state.complete_gate_failure_rounds_max, 2),
    );

    // Evidence-based productivity tracking
    // Uses multiple signals to determine if work is being done:
    // 1. File changes (primary signal)
    // 2. Task completion progress
    // 3. Historical productivity trend
    const lastFilesChanged = toNumber(state.last_files_changed, 0);
    const prevFilesChanged = toNumber(state.prev_files_changed, 0);
    const hasRecentFailures = Boolean(state.failure?.count > 0);

    // Track task completion trend
    const previousTasks = state.tasks || {};
    const prevUnchecked = toNumber(previousTasks.unchecked, checkboxCounts.unchecked);
    const prevTotal = toNumber(previousTasks.total, checkboxCounts.total);
    const totalsStable = prevTotal === checkboxCounts.total;
    const rawCompletionDelta = prevUnchecked - checkboxCounts.unchecked;
    const tasksCompletedSinceLastRound = totalsStable && rawCompletionDelta > 0
      ? rawCompletionDelta
      : 0;

    // Track consecutive rounds without task completion (for progress review trigger)
    const prevRoundsWithoutCompletion = toNumber(state.rounds_without_task_completion, 0);
    const roundsWithoutTaskCompletion = tasksCompletedSinceLastRound > 0
      ? 0
      : prevRoundsWithoutCompletion + (iteration > 0 ? 1 : 0);

    const prevCompleteGateFailureRounds = toNumber(state.complete_gate_failure_rounds, 0);
    const completeGateFailureRounds = allComplete && gateNormalized !== 'success'
      ? prevCompleteGateFailureRounds + 1
      : 0;

    // Progress review threshold: trigger after N rounds of activity without task completion
    // This catches "productive but unfocused" patterns where agent makes changes but doesn't advance criteria
    // Default is 4 rounds - enough leeway for prep work but early enough for course correction
    const needsProgressReview = roundsWithoutTaskCompletion >= progressReviewThreshold
      && (!allComplete || gateNormalized !== 'success');

    // Calculate productivity score (0-100)
    // This is evidence-based: higher score = more confidence work is happening
    let productivityScore = 0;
    if (lastFilesChanged > 0) productivityScore += Math.min(40, lastFilesChanged * 10);
    if (tasksCompletedSinceLastRound > 0) productivityScore += Math.min(40, tasksCompletedSinceLastRound * 20);
    if (prevFilesChanged > 0 && iteration > 1) productivityScore += 10; // Recent historical activity
    if (!hasRecentFailures) productivityScore += 10; // No failures is a positive signal

    // An iteration is productive if it has a reasonable productivity score
    const isProductive = productivityScore >= 20 && !hasRecentFailures;

    // max_iterations is a "stuck detection" threshold, not a hard cap
    // Continue past max if productive work is happening
    const shouldStopForMaxIterations = iteration >= maxIterations && !isProductive;

    // Build task appendix for the agent prompt (after state load for reconciliation info)
    const taskAppendix = buildTaskAppendix(normalisedSections, checkboxCounts, state, { prBody: pr.body });

    // Check for merge conflicts - this takes priority over other work
    let conflictResult = { hasConflict: false };
    try {
      conflictResult = await detectConflicts(github, context, prNumber, pr.head.sha);
      if (conflictResult.hasConflict && core) {
        core.info(`Merge conflict detected via ${conflictResult.primarySource}. Files: ${conflictResult.files?.join(', ') || 'unknown'}`);
      }
    } catch (conflictError) {
      if (core) core.warning(`Conflict detection failed: ${conflictError.message}`);
    }

    let action = 'wait';
    let reason = 'pending';
    const verificationStatus = normalise(state?.verification?.status)?.toLowerCase();
    const verificationDone = ['done', 'verified', 'complete'].includes(verificationStatus);
    const verificationAttempted = Boolean(state?.verification?.iteration);
    // Only try verification once - if it fails, that's OK, tasks are still complete
    const needsVerification = allComplete && !verificationDone && !verificationAttempted;

    // Only treat GitHub API conflicts as definitive (mergeable_state === 'dirty')
    // CI-log based conflict detection has too many false positives from commit messages
    // and should not block fix_ci mode when Gate fails with actual code errors
    const hasDefinitiveConflict = conflictResult.hasConflict &&
      conflictResult.primarySource === 'github-api';

    // Conflict resolution takes highest priority ONLY for definitive conflicts
    if (hasDefinitiveConflict && hasAgentLabel && keepaliveEnabled) {
      action = 'conflict';
      reason = `merge-conflict-${conflictResult.primarySource || 'detected'}`;
    } else if (!hasAgentLabel) {
      action = 'wait';
      reason = 'missing-agent-label';
    } else if (!keepaliveEnabled) {
      action = 'skip';
      reason = 'keepalive-disabled';
    } else if (!tasksPresent) {
      action = 'stop';
      reason = 'no-checklists';
    } else if (gateNormalized !== 'success') {
      if (allComplete && completeGateFailureRounds >= completeGateFailureMax) {
        action = 'stop';
        reason = 'complete-gate-failure-max';
      } else if (gateNormalized === 'cancelled') {
        if (rateLimitDefer) {
          action = 'defer';
          reason = 'rate-limit-exhausted';
        } else {
          gateRateLimit = await detectRateLimitCancellation({
            github,
            context,
            runId: gateRun.runId,
            core,
          });
          if (gateRateLimit) {
            if (tasksRemaining && !rateLimitDefer) {
              // Rate limits are infrastructure noise; proceed with work when tokens remain.
              action = 'run';
              reason = 'bypass-rate-limit-gate';
              if (core) core.info('Gate cancelled due to rate limits - bypassing Gate');
            } else {
              action = 'wait';
              reason = 'gate-cancelled';
            }
          } else if (forceRetry && tasksRemaining) {
            action = 'run';
            reason = 'force-retry-cancelled';
            if (core) core.info(`Force retry enabled: bypassing cancelled gate (rate_limit=${gateRateLimit})`);
          } else {
            action = 'wait';
            reason = 'gate-cancelled';
          }
        }
      } else {
        // Gate failed - check if failure is rate-limit related vs code quality
        const gateFailure = await classifyGateFailure({ github, context, pr, core });
        if (gateFailure.shouldFixMode && gateNormalized === 'failure') {
          action = 'fix';
          reason = `fix-${gateFailure.failureType}`;
        } else if (forceRetry && tasksRemaining) {
          // forceRetry can also bypass non-success gates (user explicitly wants to retry)
          action = 'run';
          reason = 'force-retry-gate';
          if (core) core.info(`Force retry enabled: bypassing gate conclusion '${gateNormalized}'`);
        } else {
          action = 'wait';
          reason = gateNormalized ? 'gate-not-success' : 'gate-pending';
        }
      }
    } else if (allComplete) {
      if (needsVerification) {
        action = 'run';
        reason = 'verify-acceptance';
      } else {
        action = 'stop';
        reason = 'tasks-complete';
      }
    } else if (shouldStopForMaxIterations && forceRetry && tasksRemaining) {
      action = 'run';
      reason = 'force-retry-max-iterations';
      if (core) core.info('Force retry enabled: bypassing max-iterations stop');
    } else if (shouldStopForMaxIterations) {
      action = 'stop';
      reason = isProductive ? 'max-iterations' : 'max-iterations-unproductive';
    } else if (needsProgressReview) {
      // Trigger LLM-based progress review when agent is active but not completing tasks
      // This allows legitimate prep work while catching scope drift early
      // Checked after max-iteration handling to avoid trapping the loop in review-only mode
      action = 'review';
      reason = `progress-review-${roundsWithoutTaskCompletion}`;
    } else if (tasksRemaining) {
      action = 'run';
      reason = iteration >= maxIterations ? 'ready-extended' : 'ready';
    }

    if (
      rateLimitDefer &&
      ['run', 'fix', 'review', 'conflict'].includes(action) &&
      reason !== 'bypass-rate-limit-gate'
    ) {
      action = 'defer';
      reason = 'rate-limit-exhausted';
    }

    const promptScenario = normalise(config.prompt_scenario);
    const promptModeOverride = normalise(config.prompt_mode);
    const promptFileOverride = normalise(config.prompt_file);
    const promptRoute = resolvePromptRouting({
      scenario: promptScenario,
      mode: promptModeOverride,
      action,
      reason,
    });
    const promptMode = promptModeOverride || promptRoute.mode;
    const promptFile = promptFileOverride || promptRoute.file;

    return {
      prNumber,
      prRef: pr.head.ref || '',
      baseRef: pr.base?.ref || '',
      headSha: pr.head.sha || '',
      action,
      reason,
      promptMode,
      promptFile,
      gateConclusion,
      config,
      iteration,
      maxIterations,
      failureThreshold,
      checkboxCounts,
      hasAgentLabel,
      hasHighPrivilege,
      agentType,
      agentRoutingMode,
      delegationReason,
      delegationShouldSwitch,
      taskAppendix,
      keepaliveEnabled,
      stateCommentId: stateResult.commentId || 0,
      state,
      forceRetry: Boolean(forceRetry),
      hasConflict: conflictResult.hasConflict,
      conflictSource: conflictResult.primarySource || null,
      conflictFiles: conflictResult.files || [],
      // Progress review data for LLM-based alignment check
      needsProgressReview,
      roundsWithoutTaskCompletion,
      // Rate limit status for monitoring
      rateLimitStatus,
    };
  } catch (error) {
    const rateLimitMessage = [error?.message, error?.response?.data?.message]
      .filter(Boolean)
      .join(' ');
    const rateLimitRemaining = toNumber(error?.response?.headers?.['x-ratelimit-remaining'], NaN);
    const rateLimitHit = hasRateLimitSignal(rateLimitMessage)
      || (error?.status === 403 && rateLimitRemaining === 0);
    if (rateLimitHit) {
      if (core) core.warning('Keepalive loop hit GitHub API rate limit; deferring.');
      return {
        prNumber,
        prRef: '',
        headSha: '',
        action: 'defer',
        reason: 'api-rate-limit',
        promptMode: 'normal',
        promptFile: PROMPT_ROUTES.normal.file,
        gateConclusion: '',
        config: {},
        iteration: 0,
        maxIterations: 0,
        failureThreshold: 0,
        checkboxCounts: { total: 0, unchecked: 0 },
        hasAgentLabel: false,
        hasHighPrivilege: false,
        agentType: '',
        taskAppendix: '',
        keepaliveEnabled: false,
        stateCommentId: 0,
        state: {},
        forceRetry: Boolean(forceRetry),
        hasConflict: false,
        conflictSource: null,
        conflictFiles: [],
        needsProgressReview: false,
        roundsWithoutTaskCompletion: 0,
      };
    }
    throw error;
  } finally {
    cache?.emitMetrics?.();
  }
}

async function updateKeepaliveLoopSummary({ github: rawGithub, context, core, inputs }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const cache = getGithubApiCache({ github, core });
  if (cache?.invalidateForWebhook) {
    cache.invalidateForWebhook({
      eventName: context?.eventName,
      payload: context?.payload,
      owner: context?.repo?.owner,
      repo: context?.repo?.repo,
    });
  }
  try {
    const prNumber = Number(inputs.prNumber || inputs.pr_number || 0);
    if (!Number.isFinite(prNumber) || prNumber <= 0) {
      if (core) core.info('No PR number available for summary update.');
      return;
    }

    const gateConclusion = normalise(inputs.gateConclusion || inputs.gate_conclusion);
    const action = normalise(inputs.action);
    const reason = normalise(inputs.reason);
    const tasksTotalInput = inputs.tasksTotal ?? inputs.tasks_total;
    const tasksUncheckedInput = inputs.tasksUnchecked ?? inputs.tasks_unchecked;
    const keepaliveEnabledInput = inputs.keepaliveEnabled ?? inputs.keepalive_enabled;
    const autofixEnabledInput = inputs.autofixEnabled ?? inputs.autofix_enabled;
    const iterationInput = inputs.iteration;
    const maxIterationsInput = inputs.maxIterations ?? inputs.max_iterations;
    const failureThresholdInput = inputs.failureThreshold ?? inputs.failure_threshold;
    const roundsWithoutTaskCompletionInput =
      inputs.roundsWithoutTaskCompletion ?? inputs.rounds_without_task_completion;
    const agentType = normalise(inputs.agent_type ?? inputs.agentType) || _defaultAgent;
    const runResult = normalise(inputs.runResult || inputs.run_result);
    const stateTrace = normalise(inputs.trace || inputs.keepalive_trace || '');

    // Delegation policy inputs (from evaluate step when agent:auto is active)
    const delegationReason = normalise(inputs.delegation_reason ?? inputs.delegationReason);
    const delegationShouldSwitch = toBool(inputs.delegation_should_switch ?? inputs.delegationShouldSwitch, false);
    const agentRoutingMode = normalise(inputs.agent_routing_mode ?? inputs.agentRoutingMode);

    const { state: previousState, commentId } = await loadKeepaliveState({
      github,
      context,
      prNumber,
      trace: stateTrace,
    });

    const hasTasksTotalInput = tasksTotalInput !== undefined && tasksTotalInput !== '';
    const hasTasksUncheckedInput = tasksUncheckedInput !== undefined && tasksUncheckedInput !== '';
    const hasIterationInput = iterationInput !== undefined && iterationInput !== '';
    const hasMaxIterationsInput = maxIterationsInput !== undefined && maxIterationsInput !== '';
    const hasFailureThresholdInput = failureThresholdInput !== undefined && failureThresholdInput !== '';
    const hasRoundsWithoutTaskCompletionInput =
      roundsWithoutTaskCompletionInput !== undefined && roundsWithoutTaskCompletionInput !== '';
    const hasKeepaliveEnabledInput = keepaliveEnabledInput !== undefined && keepaliveEnabledInput !== '';
    const hasAutofixEnabledInput = autofixEnabledInput !== undefined && autofixEnabledInput !== '';

    const tasksTotal = hasTasksTotalInput
      ? toNumber(tasksTotalInput, 0)
      : toNumber(previousState?.tasks?.total, 0);
    const tasksUnchecked = hasTasksUncheckedInput
      ? toNumber(tasksUncheckedInput, 0)
      : toNumber(previousState?.tasks?.unchecked, 0);
    const keepaliveEnabledFallback = toBool(
      previousState?.keepalive_enabled ??
        previousState?.keepaliveEnabled ??
        previousState?.keepalive,
      Boolean(previousState?.running),
    );
    const keepaliveEnabled = hasKeepaliveEnabledInput
      ? toBool(keepaliveEnabledInput, keepaliveEnabledFallback)
      : keepaliveEnabledFallback;
    const autofixEnabledFallback = toBool(
      previousState?.autofix_enabled ?? previousState?.autofixEnabled ?? previousState?.autofix,
      false,
    );
    const autofixEnabled = hasAutofixEnabledInput
      ? toBool(autofixEnabledInput, autofixEnabledFallback)
      : autofixEnabledFallback;
    const iteration = hasIterationInput
      ? toNumber(iterationInput, 0)
      : toNumber(previousState?.iteration, 0);
    const maxIterations = hasMaxIterationsInput
      ? toNumber(maxIterationsInput, 0)
      : toNumber(previousState?.max_iterations, 0);
    const failureThreshold = Math.max(
      1,
      hasFailureThresholdInput
        ? toNumber(failureThresholdInput, 3)
        : toNumber(previousState?.failure_threshold, 3),
    );
    const roundsWithoutTaskCompletion = hasRoundsWithoutTaskCompletionInput
      ? toNumber(roundsWithoutTaskCompletionInput, 0)
      : toNumber(previousState?.rounds_without_task_completion, 0);

    // Agent output details (agent-agnostic, with backwards-compat fallback to codex_ names)
    const agentExitCode = normalise(inputs.agent_exit_code ?? inputs.agentExitCode ?? inputs.codex_exit_code ?? inputs.codexExitCode);
    const agentChangesMade = normalise(inputs.agent_changes_made ?? inputs.agentChangesMade ?? inputs.codex_changes_made ?? inputs.codexChangesMade);
    const agentCommitSha = normalise(inputs.agent_commit_sha ?? inputs.agentCommitSha ?? inputs.codex_commit_sha ?? inputs.codexCommitSha);
    const agentFilesChanged = toNumber(inputs.agent_files_changed ?? inputs.agentFilesChanged ?? inputs.codex_files_changed ?? inputs.codexFilesChanged, 0);
    const agentSummary = normalise(inputs.agent_summary ?? inputs.agentSummary ?? inputs.codex_summary ?? inputs.codexSummary);
    const runUrl = normalise(inputs.run_url ?? inputs.runUrl);
    const promptModeInput = normalise(inputs.prompt_mode ?? inputs.promptMode);
    const promptFileInput = normalise(inputs.prompt_file ?? inputs.promptFile);
    const promptScenarioInput = normalise(inputs.prompt_scenario ?? inputs.promptScenario);
    const promptRoute = resolvePromptRouting({
      scenario: promptScenarioInput,
      mode: promptModeInput,
      action,
      reason,
    });
    const promptMode = promptModeInput || promptRoute.mode;
    const promptFile = promptFileInput || promptRoute.file;

    // LLM task analysis details
    const llmProvider = normalise(inputs.llm_provider ?? inputs.llmProvider);
    const llmModel = normalise(inputs.llm_model ?? inputs.llmModel);
    const llmConfidence = toNumber(inputs.llm_confidence ?? inputs.llmConfidence, 0);
    const llmAnalysisRun = toBool(inputs.llm_analysis_run ?? inputs.llmAnalysisRun, false);

    // Quality metrics for BS detection and evidence-based decisions
    const llmRawConfidence = toNumber(inputs.llm_raw_confidence ?? inputs.llmRawConfidence, llmConfidence);
    const llmConfidenceAdjusted = toBool(inputs.llm_confidence_adjusted ?? inputs.llmConfidenceAdjusted, false);
    const llmQualityWarnings = normalise(inputs.llm_quality_warnings ?? inputs.llmQualityWarnings);
    const sessionDataQuality = normalise(inputs.session_data_quality ?? inputs.sessionDataQuality);
    const sessionEffortScore = toNumber(inputs.session_effort_score ?? inputs.sessionEffortScore, 0);
    const analysisTextLength = toNumber(inputs.analysis_text_length ?? inputs.analysisTextLength, 0);

    const labels = await fetchPrLabels({ github, context, prNumber, core });
    const timeoutRepoVariables = await fetchRepoVariables({
      github,
      context,
      core,
      names: TIMEOUT_VARIABLE_NAMES,
    });
    const timeoutInputs = resolveTimeoutInputs({ inputs, context });
    const timeoutConfig = parseTimeoutConfig({
      env: process.env,
      inputs: timeoutInputs,
      labels,
      variables: timeoutRepoVariables,
    });
    const elapsedMs = await resolveElapsedMs({ github, context, inputs, core });
    const timeoutWarningConfig = resolveTimeoutWarningConfig({
      inputs: timeoutInputs,
      env: process.env,
      variables: timeoutRepoVariables,
    });
    const timeoutStatus = buildTimeoutStatus({
      timeoutConfig,
      elapsedMs,
      ...timeoutWarningConfig,
    });

    const previousFailure = previousState?.failure || {};
    const prBody = await fetchPrBody({ github, context, prNumber, core });
    const focusSections = prBody ? normaliseChecklistSections(parseScopeTasksAcceptanceSections(prBody)) : {};
    const focusItems = extractChecklistItems(focusSections.tasks || focusSections.acceptance || '');
    const focusUnchecked = focusItems.filter((item) => !item.checked);
    const currentFocus = normaliseTaskText(previousState?.current_focus || '');
    const fallbackFocus = focusUnchecked[0]?.text || '';

    // Use the iteration from the CURRENT persisted state, not the stale value from evaluate.
    // This prevents race conditions where another run updated state between evaluate and summary.
    const currentIteration = toNumber(previousState?.iteration ?? iteration, 0);
    let nextIteration = currentIteration;
    let failure = { ...previousFailure };
    // Stop conditions:
    // - tasks-complete: SUCCESS, don't need needs-human label
    // - no-checklists: neutral, agent has nothing to do
    // - max-iterations: possible issue, MAY need attention
    // - agent-run-failed-repeat: definite issue, needs attention
    const isSuccessStop = reason === 'tasks-complete';
    const isNeutralStop = reason === 'no-checklists' || reason === 'keepalive-disabled';
    let stop = action === 'stop' && !isSuccessStop && !isNeutralStop;
    let summaryReason = reason || action || 'unknown';
    const baseReason = summaryReason;
    const transientDetails = classifyFailureDetails({
      action,
      runResult,
      summaryReason,
      agentExitCode,
      agentSummary,
    });
    const runFailed =
      action === 'run' &&
      runResult &&
      !['success', 'skipped', 'cancelled'].includes(runResult);
    const isTransientFailure =
      runFailed && transientDetails.category === ERROR_CATEGORIES.transient;
    const waitLikeAction = action === 'wait' || action === 'defer';
    const waitIsTransientReason = [
      'gate-pending',
      'missing-agent-label',
      'gate-cancelled',
      'gate-cancelled-rate-limit',
      'rate-limit-exhausted',
    ].includes(baseReason);
    const isTransientWait =
      waitLikeAction &&
      (transientDetails.category === ERROR_CATEGORIES.transient || waitIsTransientReason);

    // Task reconciliation: detect when agent made changes but didn't update checkboxes
    const previousTasks = previousState?.tasks || {};
    const previousUnchecked = toNumber(previousTasks.unchecked, tasksUnchecked);
    const tasksCompletedThisRound = previousUnchecked - tasksUnchecked;
    const madeChangesButNoTasksChecked =
      action === 'run' &&
      runResult === 'success' &&
      agentChangesMade === 'true' &&
      agentFilesChanged > 0 &&
      tasksCompletedThisRound <= 0;

    if (action === 'run') {
      if (runResult === 'success') {
        nextIteration = currentIteration + 1;
        failure = {};
      } else if (runResult) {
        // If the job was skipped/cancelled, it usually means the workflow condition
        // prevented execution (e.g. gate not ready, label missing, concurrency).
        // Don't treat this as an agent failure.
        if (runResult === 'skipped') {
          failure = {};
          summaryReason = 'agent-run-skipped';
        } else if (runResult === 'cancelled') {
          failure = {};
          summaryReason = 'agent-run-cancelled';
        } else if (isTransientFailure) {
          failure = {};
          summaryReason = 'agent-run-transient';
        } else {
          const same = failure.reason === 'agent-run-failed';
          const count = same ? toNumber(failure.count, 0) + 1 : 1;
          failure = { reason: 'agent-run-failed', count };
          if (count >= failureThreshold) {
            stop = true;
            summaryReason = 'agent-run-failed-repeat';
          } else {
            summaryReason = 'agent-run-failed';
          }
        }
      }
    } else if (action === 'stop') {
      // Differentiate between terminal states:
      // - tasks-complete: Success! Clear failure state
      // - no-checklists / keepalive-disabled: Neutral, nothing to do
      // - max-iterations: Could be a problem, count as failure
      if (isSuccessStop) {
        // Tasks complete is success, clear any failure state
        failure = {};
      } else if (isNeutralStop) {
        // Neutral states don't need failure tracking
        failure = {};
      } else {
        // max-iterations type stops should count as potential issues
        const sameReason = failure.reason && failure.reason === summaryReason;
        const count = sameReason ? toNumber(failure.count, 0) + 1 : 1;
        failure = { reason: summaryReason, count };
        if (count >= failureThreshold) {
          summaryReason = `${summaryReason}-repeat`;
        }
      }
    } else if (waitLikeAction) {
      // Wait states are NOT failures - they're transient conditions
      // Don't increment failure counter for: gate-pending, gate-not-success, missing-agent-label
      // These are expected states that will resolve on their own
      // Check if this is a transient error (from error classification)
      if (isTransientWait) {
        failure = {};
        summaryReason = `${summaryReason}-transient`;
      } else if (failure.reason && !failure.reason.startsWith('gate-') && failure.reason !== 'missing-agent-label') {
        // Keep the failure from a previous real failure (like agent-run-failed)
        // but don't increment for wait states
      } else {
        // Clear failure state for transient wait conditions
        failure = {};
      }
    }

    const failureDetails = classifyFailureDetails({
      action,
      runResult,
      summaryReason,
      agentExitCode,
      agentSummary,
    });
    const errorCategory = failureDetails.category;
    const errorType = failureDetails.type;
    const errorRecovery = failureDetails.recovery;
    const tasksComplete = Math.max(0, tasksTotal - tasksUnchecked);
    const allTasksComplete = tasksUnchecked === 0 && tasksTotal > 0;
    const previousCompleteGateFailureRounds = toNumber(previousState?.complete_gate_failure_rounds, 0);
    const completeGateFailureMax = Math.max(
      1,
      toNumber(
        inputs.completeGateFailureRoundsMax ??
          inputs.complete_gate_failure_rounds_max ??
          previousState?.complete_gate_failure_rounds_max,
        2,
      ),
    );
    const completeGateFailureRounds =
      allTasksComplete && gateConclusion && gateConclusion !== 'success'
        ? previousCompleteGateFailureRounds + 1
        : 0;
    const metricsIteration = action === 'run' ? currentIteration + 1 : currentIteration;
    const durationMs = resolveDurationMs({
      durationMs: toOptionalNumber(inputs.duration_ms ?? inputs.durationMs),
      startTs: toOptionalNumber(inputs.start_ts ?? inputs.startTs),
    });
    const metricsRecord = buildMetricsRecord({
      prNumber,
      iteration: metricsIteration,
      action,
      errorCategory,
      durationMs,
      tasksTotal,
      tasksComplete,
    });
    emitMetricsRecord({ core, record: metricsRecord });
    await appendMetricsRecord({
      core,
      record: metricsRecord,
      metricsPath: resolveMetricsPath(inputs),
    });

    // Capitalize agent name for display
    const agentDisplayName = agentType.charAt(0).toUpperCase() + agentType.slice(1);

    // Determine if we're in extended mode (past max_iterations but still productive)
    const inExtendedMode = nextIteration > maxIterations && maxIterations > 0;
    const extendedCount = inExtendedMode ? nextIteration - maxIterations : 0;
    const iterationDisplay = inExtendedMode
      ? `**${maxIterations}+${extendedCount}** 🚀 extended`
      : `${nextIteration}/${maxIterations || '∞'}`;

    const dispositionLabel = (() => {
      if (action === 'defer') {
        return 'deferred (transient)';
      }
      if (action === 'wait') {
        return isTransientWait ? 'skipped (transient)' : 'skipped (failure)';
      }
      if (action === 'skip') {
        return 'skipped';
      }
      return '';
    })();
    const actionReason = waitLikeAction
      ? (baseReason || summaryReason)
      : (summaryReason || baseReason);

    const summaryLines = [
      '<!-- keepalive-loop-summary -->',
      `## 🤖 Keepalive Loop Status`,
      '',
      `**PR #${prNumber}** | Agent: **${agentDisplayName}** | Iteration ${iterationDisplay}`,
      '',
      '### Current State',
      `| Metric | Value |`,
      `|--------|-------|`,
      `| Iteration progress | ${maxIterations > 0
        ? inExtendedMode
          ? `${formatProgressBar(maxIterations, maxIterations)} ${maxIterations} base + ${extendedCount} extended = **${nextIteration}** total`
          : formatProgressBar(nextIteration, maxIterations)
        : 'n/a (unbounded)'
      } |`,
      `| Action | ${action || 'unknown'} (${actionReason || 'n/a'}) |`,
      ...(dispositionLabel ? [`| Disposition | ${dispositionLabel} |`] : []),
      ...(allTasksComplete ? [`| Agent status | ✅ ALL TASKS COMPLETE |`] : runFailed ? [`| Agent status | ❌ AGENT FAILED |`] : []),
      `| Gate | ${gateConclusion || 'unknown'} |`,
      `| Tasks | ${tasksComplete}/${tasksTotal} complete |`,
      `| Timeout | ${formatTimeoutMinutes(timeoutStatus.resolvedMinutes)} min (${timeoutStatus.source || 'default'}) |`,
      `| Keepalive | ${keepaliveEnabled ? '✅ enabled' : '❌ disabled'} |`,
      `| Autofix | ${autofixEnabled ? '✅ enabled' : '❌ disabled'} |`,
    ];

    const timeoutUsage = formatTimeoutUsage({
      elapsedMs: timeoutStatus.elapsedMs,
      usageRatio: timeoutStatus.usageRatio,
      remainingMs: timeoutStatus.remainingMs,
    });
    if (timeoutUsage) {
      summaryLines.splice(summaryLines.length - 2, 0, `| Timeout usage | ${timeoutUsage} |`);
    }
    if (timeoutStatus.warning) {
      const timeoutWarning = formatTimeoutWarning(timeoutStatus.warning);
      const warningValue = timeoutWarning ? `⚠️ ${timeoutWarning}` : `⚠️ ${timeoutStatus.warning.remaining_minutes}m remaining`;
      summaryLines.splice(
        summaryLines.length - 2,
        0,
        `| Timeout warning | ${warningValue} |`,
      );
    }

    if (timeoutStatus.warning && core && typeof core.warning === 'function') {
      const percent = timeoutStatus.warning.percent ?? 0;
      const remaining = timeoutStatus.warning.remaining_minutes ?? 0;
      const reason = timeoutStatus.warning.reason === 'remaining' ? 'remaining threshold' : 'usage threshold';
      const thresholdParts = [];
      const thresholdPercent = timeoutStatus.warning.threshold_percent;
      const thresholdRemaining = timeoutStatus.warning.threshold_remaining_minutes;
      if (Number.isFinite(thresholdPercent)) {
        thresholdParts.push(`${thresholdPercent}% threshold`);
      }
      if (Number.isFinite(thresholdRemaining)) {
        thresholdParts.push(`${thresholdRemaining}m threshold`);
      }
      const thresholdSuffix = thresholdParts.length ? ` (thresholds: ${thresholdParts.join(', ')})` : '';
      core.warning(`Timeout warning (${reason}): ${percent}% consumed, ${remaining}m remaining${thresholdSuffix}.`);
    }

    // Add delegation info when in auto mode
    if (agentRoutingMode === 'auto' && delegationReason) {
      summaryLines.push(
        '',
        '### Agent Delegation (auto mode)',
        `| Field | Value |`,
        `|-------|-------|`,
        `| Selected agent | ${agentDisplayName} |`,
        `| Reason | ${delegationReason} |`,
      );
      if (delegationShouldSwitch) {
        const prevAgent = previousState?.current_agent || 'unknown';
        summaryLines.push(`| Switch | ${prevAgent} → ${agentType} |`);
      }
      const switchCount = toNumber(previousState?.switch_count, 0) + (delegationShouldSwitch ? 1 : 0);
      if (switchCount > 0) {
        summaryLines.push(`| Total switches | ${switchCount} |`);
      }
    }

    // Add agent run details if we ran an agent
    if (action === 'run' && runResult) {
      const runLinkText = runUrl ? ` ([view logs](${runUrl}))` : '';
      summaryLines.push('', `### Last ${agentDisplayName} Run${runLinkText}`);

      if (runResult === 'success') {
        const changesIcon = agentChangesMade === 'true' ? '✅' : '⚪';
        summaryLines.push(
          `| Result | Value |`,
          `|--------|-------|`,
          `| Status | ✅ Success |`,
          `| Changes | ${changesIcon} ${agentChangesMade === 'true' ? `${agentFilesChanged} file(s)` : 'No changes'} |`,
        );
        if (agentCommitSha) {
          summaryLines.push(`| Commit | [\`${agentCommitSha.slice(0, 7)}\`](../commit/${agentCommitSha}) |`);
        }
      } else if (runResult === 'skipped') {
        summaryLines.push(
          `| Result | Value |`,
          `|--------|-------|`,
          `| Status | ⏭️ Skipped |`,
          `| Reason | ${summaryReason || 'agent-run-skipped'} |`,
        );
        
        // Add restart instructions for skipped runs
        summaryLines.push(
          '',
          '**To retry:**',
          '- Add the `agent:retry` label, OR',
          '- Wait for conditions to resolve (e.g., Gate success, labels present)',
        );
      } else if (runResult === 'cancelled') {
        summaryLines.push(
          `| Result | Value |`,
          `|--------|-------|`,
          `| Status | 🚫 Cancelled |`,
          `| Reason | ${summaryReason || 'agent-run-cancelled'} |`,
        );
        
        // Add restart instructions for cancelled runs
        summaryLines.push(
          '',
          '**To retry:**',
          '- Add the `agent:retry` label to this PR',
        );
      } else {
        summaryLines.push(
          `| Result | Value |`,
          `|--------|-------|`,
          `| Status | ❌ AGENT FAILED |`,
          `| Reason | ${summaryReason || runResult || 'unknown'} |`,
          `| Exit code | ${agentExitCode || 'unknown'} |`,
          `| Failures | ${failure.count || 1}/${failureThreshold} before pause |`,
        );
        
        // Add restart instructions for failed runs
        summaryLines.push(
          '',
          '**To retry immediately:**',
          '- Add the `agent:retry` label to this PR',
          '',
          '_Or wait for the next successful Gate run to automatically retry._',
        );
      }

      // Add agent output summary if available
      if (agentSummary && agentSummary.length > 10) {
        const truncatedSummary = agentSummary.length > 300
          ? agentSummary.slice(0, 300) + '...'
          : agentSummary;
        summaryLines.push('', `**${agentDisplayName} output:**`, `> ${truncatedSummary}`);
      }

      // Task reconciliation warning: agent made changes but didn't check off tasks
      if (madeChangesButNoTasksChecked) {
        summaryLines.push(
          '',
          '### 📋 Task Reconciliation Needed',
          '',
          `⚠️ ${agentDisplayName} changed **${agentFilesChanged} file(s)** but didn't check off any tasks.`,
          '',
          '**Next iteration should:**',
          '1. Review the changes made and determine which tasks were addressed',
          '2. Update the PR body to check off completed task checkboxes',
          '3. If work was unrelated to tasks, continue with remaining tasks',
        );
      }
    }

    if (errorType || errorCategory) {
      summaryLines.push(
        '',
        '### 🔍 Failure Classification',
        `| Error type | ${errorType || 'unknown'} |`,
        `| Error category | ${errorCategory || 'unknown'} |`,
      );
      if (errorRecovery) {
        summaryLines.push(`| Suggested recovery | ${errorRecovery} |`);
      }
    }

    // LLM analysis details - show which provider was used for task completion detection
    if (llmAnalysisRun && llmProvider) {
      const providerIcon = llmProvider === 'github-models' ? '✅' :
        llmProvider === 'openai' ? '⚠️' :
          llmProvider === 'regex-fallback' ? '🔶' : 'ℹ️';
      const providerLabel = llmProvider === 'github-models' ? 'GitHub Models (primary)' :
        llmProvider === 'openai' ? 'OpenAI (fallback)' :
          llmProvider === 'regex-fallback' ? 'Regex (fallback)' : llmProvider;
      const confidencePercent = Math.round(llmConfidence * 100);

      summaryLines.push(
        '',
        '### 🧠 Task Analysis',
        `| Provider | ${providerIcon} ${providerLabel} |`,
      );

      // Show model name if available
      if (llmModel && llmModel !== 'unknown') {
        summaryLines.push(`| Model | ${llmModel} |`);
      }

      summaryLines.push(`| Confidence | ${confidencePercent}% |`);

      // Show quality metrics if available
      if (sessionDataQuality) {
        const qualityIcon = sessionDataQuality === 'high' ? '🟢' :
          sessionDataQuality === 'medium' ? '🟡' :
            sessionDataQuality === 'low' ? '🟠' : '🔴';
        summaryLines.push(`| Data Quality | ${qualityIcon} ${sessionDataQuality} |`);
      }
      if (sessionEffortScore > 0) {
        summaryLines.push(`| Effort Score | ${sessionEffortScore}/100 |`);
      }

      // Show BS detection warnings if confidence was adjusted
      if (llmConfidenceAdjusted && llmRawConfidence !== llmConfidence) {
        const rawPercent = Math.round(llmRawConfidence * 100);
        summaryLines.push(
          '',
          `> ⚠️ **Confidence adjusted**: Raw confidence was ${rawPercent}%, adjusted to ${confidencePercent}% based on session quality metrics.`
        );
      }

      // Show specific quality warnings if present
      if (llmQualityWarnings) {
        summaryLines.push(
          '',
          '#### Quality Warnings',
        );
        // Parse warnings (could be JSON array or comma-separated)
        let warnings = [];
        try {
          warnings = JSON.parse(llmQualityWarnings);
        } catch {
          warnings = llmQualityWarnings.split(';').filter(w => w.trim());
        }
        for (const warning of warnings) {
          summaryLines.push(`- ⚠️ ${warning.trim()}`);
        }
      }

      // Analysis data health check
      if (analysisTextLength > 0 && analysisTextLength < 200 && agentFilesChanged > 0) {
        summaryLines.push(
          '',
          `> 🔴 **Data Loss Alert**: Analysis text was only ${analysisTextLength} chars despite ${agentFilesChanged} file changes. Task detection may be inaccurate.`
        );
      }

      if (llmProvider !== 'github-models') {
        summaryLines.push(
          '',
          `> ⚠️ Primary provider (GitHub Models) was unavailable; used ${providerLabel} instead.`,
        );
      }
    } else if (agentChangesMade === 'true' && iteration > 0) {
      // Warn when LLM analysis didn't run but agent made changes
      // This indicates an infrastructure issue that should be investigated
      summaryLines.push(
        '',
        '### ⚠️ Task Analysis Unavailable',
        '> **Warning**: LLM-powered task completion analysis did not run for this iteration.',
        '> This may be due to:',
        '> - Missing analysis dependencies or scripts',
        '> - Failed PR body fetch',
        '> - Session data not captured',
        '>',
        '> Task checkboxes may not be automatically updated. Please review manually.',
      );
    }

    if (isTransientFailure) {
      summaryLines.push(
        '',
        '### ♻️ Transient Issue Detected',
        'This run failed due to a transient issue. The failure counter has been reset to avoid pausing the loop.',
      );
    }

    if (action === 'defer') {
      summaryLines.push(
        '',
        '### ⏳ Deferred',
        'Keepalive deferred due to a transient Gate cancellation (likely rate limits). It will retry later.',
        '',
        '**To retry immediately:** Add the `agent:retry` label to this PR',
      );
    }

    // Show failure tracking prominently if there are failures
    if (failure.count > 0) {
      summaryLines.push(
        '',
        '### ⚠️ Failure Tracking',
        `| Consecutive failures | ${failure.count}/${failureThreshold} |`,
        `| Reason | ${failure.reason || 'unknown'} |`,
      );
    }

    // Rate limit exhaustion - special case with detailed token status
    const isRateLimitExhausted = summaryReason === 'rate-limit-exhausted' || 
      baseReason === 'rate-limit-exhausted' ||
      action === 'defer' && (summaryReason?.includes('rate') || baseReason?.includes('rate'));
    
    if (isRateLimitExhausted) {
      summaryLines.push(
        '',
        '### 🛑 Agent Stopped: API capacity depleted',
        '',
        '**All available API token pools have been exhausted.** The agent cannot make progress until rate limits reset.',
        '',
        '| Status | Details |',
        '|--------|---------|',
        `| Reason | ${summaryReason || baseReason || 'API rate limits exhausted'} |`,
        '| Capacity | All token pools at/near limit |',
        '| Recovery | Automatic when limits reset (usually ~1 hour) |',
        '',
        '**This is NOT a code or prompt problem** - it is a resource limit that will automatically resolve.',
        '',
        '_To resume immediately: Wait for rate limit reset, or add additional API tokens._',
      );
    } else if (stop) {
      summaryLines.push(
        '',
        '### 🛑 Paused – Human Attention Required',
        '',
        'The keepalive loop has paused due to repeated failures.',
        '',
        '**To resume:**',
        '1. Investigate the failure reason above',
        '2. Fix any issues in the code or prompt',
        '3. Remove the `needs-human` label from this PR',
        '4. The next Gate pass will restart the loop',
        '',
        '_Or manually edit this comment to reset `failure: {}` in the state below._',
      );
    }

    const focusTask = currentFocus || fallbackFocus;
    const shouldRecordAttempt = action === 'run' && reason !== 'verify-acceptance';
    let attemptedTasks = normaliseAttemptedTasks(previousState?.attempted_tasks);
    if (shouldRecordAttempt) {
      const attemptLabel = focusTask || (tasksCompletedThisRound > 0 ? 'checkbox-progress' : 'no-focus');
      if (attemptLabel) {
        attemptedTasks = updateAttemptedTasks(attemptedTasks, attemptLabel, metricsIteration);
      }
    }

    let verification = previousState?.verification && typeof previousState.verification === 'object'
      ? { ...previousState.verification }
      : {};
    if (tasksUnchecked > 0) {
      verification = {};
    } else if (reason === 'verify-acceptance') {
      verification = {
        status: runResult === 'success' ? 'done' : 'failed',
        iteration: nextIteration,
        last_result: runResult || '',
        updated_at: new Date().toISOString(),
      };
    }

    const newState = {
      trace: stateTrace || previousState?.trace || '',
      pr_number: prNumber,
      iteration: nextIteration,
      max_iterations: maxIterations,
      last_action: action,
      last_reason: summaryReason,
      failure,
      error_type: errorType,
      error_category: errorCategory,
      tasks: { total: tasksTotal, unchecked: tasksUnchecked },
      gate_conclusion: gateConclusion,
      failure_threshold: failureThreshold,
      // Clear running status when summary is updated (agent completed or failed)
      running: false,
      // Track task reconciliation for next iteration
      needs_task_reconciliation: madeChangesButNoTasksChecked,
      // Productivity tracking for evidence-based decisions
      last_files_changed: agentFilesChanged,
      prev_files_changed: toNumber(previousState?.last_files_changed, 0),
      // Track consecutive rounds without task completion for progress review
      rounds_without_task_completion: roundsWithoutTaskCompletion,
      complete_gate_failure_rounds: completeGateFailureRounds,
      complete_gate_failure_rounds_max: completeGateFailureMax,
      // Quality metrics for analysis validation
      last_effort_score: sessionEffortScore,
      last_data_quality: sessionDataQuality,
      attempted_tasks: attemptedTasks,
      last_focus: focusTask || '',
      verification,
      keepalive_enabled: keepaliveEnabled,
      autofix_enabled: autofixEnabled,
      timeout: {
        resolved_minutes: timeoutStatus.resolvedMinutes,
        default_minutes: timeoutStatus.defaultMinutes,
        extended_minutes: timeoutStatus.extendedMinutes,
        override_minutes: timeoutStatus.overrideMinutes,
        source: timeoutStatus.source,
        label: timeoutStatus.label,
        elapsed_minutes: timeoutStatus.elapsedMs ? Math.floor(timeoutStatus.elapsedMs / 60000) : null,
        remaining_minutes: timeoutStatus.remainingMs ? Math.ceil(timeoutStatus.remainingMs / 60000) : null,
        usage_ratio: timeoutStatus.usageRatio,
        warning: timeoutStatus.warning || null,
      },
    };

    // Persist agent delegation state when in auto mode
    if (agentRoutingMode === 'auto' || previousState?.current_agent) {
      const previousDelegationLog = Array.isArray(previousState?.delegation_log)
        ? previousState.delegation_log
        : [];
      const previousSwitchCount = toNumber(previousState?.switch_count, 0);
      const previousLastSwitchIteration = toNumber(previousState?.last_switch_iteration, 0);
      const previousEffectivenessHistory = Array.isArray(previousState?.effectiveness_history)
        ? previousState.effectiveness_history
        : [];

      // Build effectiveness entry for this round (only when agent ran)
      const effectivenessEntry = action === 'run' ? {
        iteration: nextIteration,
        agent: agentType,
        commits: agentCommitSha ? 1 : 0,
        tasks: Math.max(0, tasksCompletedThisRound),
        gate: gateConclusion === 'success' ? 'pass' : 'fail',
        files_changed: agentFilesChanged,
      } : null;

      const effectivenessHistory = effectivenessEntry
        ? [...previousEffectivenessHistory, effectivenessEntry].slice(-10)
        : previousEffectivenessHistory;

      newState.current_agent = agentType;
      newState.delegation_reason = delegationReason || previousState?.delegation_reason || '';
      newState.effectiveness_history = effectivenessHistory;

      if (delegationShouldSwitch) {
        newState.switch_count = previousSwitchCount + 1;
        newState.last_switch_iteration = nextIteration;
        newState.delegation_log = [
          ...previousDelegationLog,
          {
            iteration: nextIteration,
            previous_agent: previousState?.current_agent || '',
            chosen_agent: agentType,
            reason: delegationReason,
            timestamp: new Date().toISOString(),
          },
        ].slice(-10);
      } else {
        newState.switch_count = previousSwitchCount;
        newState.last_switch_iteration = previousLastSwitchIteration;
        newState.delegation_log = previousDelegationLog;
      }
    }

    const attemptEntry = buildAttemptEntry({
      iteration: metricsIteration,
      action,
      reason: summaryReason,
      runResult,
      promptMode,
      promptFile,
      gateConclusion,
      errorCategory,
      errorType,
      tasksTotal,
      tasksUnchecked,
      tasksCompletedDelta: tasksCompletedThisRound,
      allComplete: allTasksComplete,
    });
    newState.attempts = updateAttemptHistory(previousState?.attempts, attemptEntry);

    const summaryOutcome = runResult || summaryReason || action || 'unknown';
    if (action === 'run' || runResult) {
      await writeStepSummary({
        core,
        iteration: nextIteration,
        maxIterations,
        tasksTotal,
        tasksUnchecked,
        tasksCompletedDelta: tasksCompletedThisRound,
        agentFilesChanged,
        outcome: summaryOutcome,
      });
    }

    const previousAttention = previousState?.attention && typeof previousState.attention === 'object'
      ? previousState.attention
      : {};
    if (Object.keys(previousAttention).length > 0) {
      newState.attention = { ...previousAttention };
    }

    if (core && typeof core.setOutput === 'function') {
      core.setOutput('error_type', errorType || '');
      core.setOutput('error_category', errorCategory || '');
    }

    const shouldEscalate =
      (action === 'run' && runResult && runResult !== 'success' && errorCategory !== ERROR_CATEGORIES.transient) ||
      (action === 'stop' && !isSuccessStop && !isNeutralStop && errorCategory !== ERROR_CATEGORIES.transient);

    const attentionKey = [summaryReason, runResult, errorCategory, errorType, agentExitCode].filter(Boolean).join('|');
    const priorAttentionKey = normalise(previousAttention.key);

    // NOTE: Failure comment posting removed - handled by reusable-*-run.yml with proper deduplication
    // This prevents duplicate failure notifications on PRs

    summaryLines.push('', formatStateComment(newState));
    const body = summaryLines.join('\n');

    try {
      if (commentId) {
        await github.rest.issues.updateComment({
          owner: context.repo.owner,
          repo: context.repo.repo,
          comment_id: commentId,
          body,
        });
      } else {
        await github.rest.issues.createComment({
          owner: context.repo.owner,
          repo: context.repo.repo,
          issue_number: prNumber,
          body,
        });
      }

      if (shouldEscalate) {
        try {
          await github.rest.issues.addLabels({
            owner: context.repo.owner,
            repo: context.repo.repo,
            issue_number: prNumber,
            labels: ['agent:needs-attention'],
          });
        } catch (error) {
          if (core) core.warning(`Failed to add agent:needs-attention label: ${error.message}`);
        }
      }

      if (stop) {
        try {
          await github.rest.issues.addLabels({
            owner: context.repo.owner,
            repo: context.repo.repo,
            issue_number: prNumber,
            labels: ['needs-human'],
          });
        } catch (error) {
          if (core) core.warning(`Failed to add needs-human label: ${error.message}`);
        }
      }
    } catch (error) {
      const rateLimitMessage = [error?.message, error?.response?.data?.message]
        .filter(Boolean)
        .join(' ');
      const rateLimitRemaining = toNumber(error?.response?.headers?.['x-ratelimit-remaining'], NaN);
      const rateLimitReset = error?.response?.headers?.['x-ratelimit-reset'];
      const rateLimitHit = hasRateLimitSignal(rateLimitMessage)
        || (error?.status === 403 && rateLimitRemaining === 0);
      if (rateLimitHit) {
        // Rate limit hit - this is a critical failure that needs human attention
        // We need to:
        // 1. Mark the step as failed so it's visible in the workflow
        // 2. Set outputs so a downstream step can notify the PR (with a different token)
        // 3. Write to step summary (doesn't use API)

        const resetTime = rateLimitReset
          ? new Date(Number(rateLimitReset) * 1000).toISOString()
          : 'unknown';
        const errorSummary = `GitHub API rate limit exceeded. Reset at: ${resetTime}. Remaining: ${rateLimitRemaining}`;

        if (core) {
          // Set outputs so workflow can use a different token pool to notify PR
          core.setOutput('rate_limit_hit', 'true');
          core.setOutput('rate_limit_error', errorSummary);
          core.setOutput('rate_limit_reset', resetTime);
          core.setOutput('rate_limit_remaining', String(rateLimitRemaining));
          core.setOutput('pr_number', String(prNumber));
          core.setOutput('action', action || '');
          core.setOutput('reason', summaryReason || reason || '');

          // Write to step summary (no API call needed)
          core.summary
            .addHeading('⚠️ Rate Limit Failure - Human Attention Required', 2)
            .addRaw(`**PR #${prNumber}** could not be updated due to GitHub API rate limits.\n\n`)
            .addRaw('The keepalive loop status may show as "running" but **no work is being done**.\n\n')
            .addTable([
              [{ data: 'Field', header: true }, { data: 'Value', header: true }],
              ['Error', rateLimitMessage || 'API rate limit exceeded'],
              ['Action', action || 'unknown'],
              ['Reason', summaryReason || reason || 'unknown'],
              ['Rate Limit Remaining', String(rateLimitRemaining)],
              ['Rate Limit Reset', resetTime],
              ['PR Number', String(prNumber)],
            ])
            .addRaw('\n\n**Action Required:**\n')
            .addList([
              'A downstream step will attempt to notify the PR using a different token',
              'If no notification appears, check the PR manually',
              'Wait for rate limit reset before retrying',
            ])
            .write();

          // Mark as failed so it's visible in the workflow UI
          core.setFailed(`Rate limit hit while updating PR #${prNumber}: ${errorSummary}`);
        }
        return;
      }
      throw error;
    }
  } finally {
    cache?.emitMetrics?.();
  }
}

/**
 * Mark that an agent is currently running by updating the summary comment.
 * This provides real-time visibility into the keepalive loop's activity.
 */
async function markAgentRunning({ github: rawGithub, context, core, inputs }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const prNumber = Number(inputs.prNumber || inputs.pr_number || 0);
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    if (core) core.info('No PR number available for running status update.');
    return;
  }

  const agentType = normalise(inputs.agent_type ?? inputs.agentType) || _defaultAgent;
  const iteration = toNumber(inputs.iteration, 0);
  const maxIterations = toNumber(inputs.maxIterations ?? inputs.max_iterations, 0);
  const tasksTotal = toNumber(inputs.tasksTotal ?? inputs.tasks_total, 0);
  const tasksUnchecked = toNumber(inputs.tasksUnchecked ?? inputs.tasks_unchecked, 0);
  const stateTrace = normalise(inputs.trace || inputs.keepalive_trace || '');
  const runUrl = normalise(inputs.run_url ?? inputs.runUrl);

  const { state: previousState, commentId } = await loadKeepaliveState({
    github,
    context,
    prNumber,
    trace: stateTrace,
  });
  const prBody = await fetchPrBody({ github, context, prNumber, core });
  const focusSections = prBody ? normaliseChecklistSections(parseScopeTasksAcceptanceSections(prBody)) : {};
  const focusItems = extractChecklistItems(focusSections.tasks || focusSections.acceptance || '');
  const focusUnchecked = focusItems.filter((item) => !item.checked);
  const attemptedTasks = normaliseAttemptedTasks(previousState?.attempted_tasks);
  const attemptedKeys = new Set(attemptedTasks.map((entry) => entry.key));
  const suggestedFocus = focusUnchecked.find((item) => !attemptedKeys.has(normaliseTaskKey(item.text))) || focusUnchecked[0];

  // Capitalize agent name for display
  const agentDisplayName = agentType.charAt(0).toUpperCase() + agentType.slice(1);

  // Show iteration we're starting (current + 1)
  const displayIteration = iteration + 1;

  const runLinkText = runUrl ? ` ([view logs](${runUrl}))` : '';

  // Determine if in extended mode for display
  const inExtendedMode = displayIteration > maxIterations && maxIterations > 0;
  const iterationText = inExtendedMode
    ? `${maxIterations}+${displayIteration - maxIterations} (extended)`
    : `${displayIteration} of ${maxIterations || '∞'}`;

  const tasksCompleted = Math.max(0, tasksTotal - tasksUnchecked);
  const progressPct = tasksTotal > 0 ? Math.round((tasksCompleted / tasksTotal) * 100) : 0;

  const summaryLines = [
    '<!-- keepalive-loop-summary -->',
    `## 🤖 Keepalive Loop Status`,
    '',
    `**PR #${prNumber}** | Agent: **${agentDisplayName}** | Iteration **${iterationText}**`,
    '',
    '### 🔄 Agent Running',
    '',
    `**${agentDisplayName} is actively working on this PR**${runLinkText}`,
    '',
    `| Status | Value |`,
    `|--------|-------|`,
    `| Agent | ${agentDisplayName} |`,
    `| Iteration | ${iterationText} |`,
    `| Task progress | ${tasksCompleted}/${tasksTotal} (${progressPct}%) |`,
    `| Started | ${new Date().toISOString().replace('T', ' ').slice(0, 19)} UTC |`,
    '',
    '_This comment will be updated when the agent completes._',
  ];

  // Preserve state from previous summary (don't modify state while running)
  const preservedState = previousState || {};
  preservedState.running = true;
  preservedState.running_since = new Date().toISOString();
  if (suggestedFocus?.text) {
    preservedState.current_focus = suggestedFocus.text;
    preservedState.current_focus_set_at = new Date().toISOString();
  }

  summaryLines.push('', formatStateComment(preservedState));
  const body = summaryLines.join('\n');

  if (commentId) {
    await github.rest.issues.updateComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      comment_id: commentId,
      body,
    });
    if (core) core.info(`Updated summary comment ${commentId} with running status`);
  } else {
    const { data } = await github.rest.issues.createComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: prNumber,
      body,
    });
    if (core) core.info(`Created summary comment ${data.id} with running status`);
  }
}

/**
 * Analyze commits and files changed to infer which tasks may have been completed.
 * Uses keyword matching and file path analysis to suggest task completions.
 * @param {object} params - Parameters
 * @param {object} params.github - GitHub API client
 * @param {object} params.context - GitHub Actions context
 * @param {number} params.prNumber - PR number
 * @param {string} params.baseSha - Base SHA to compare from
 * @param {string} params.headSha - Head SHA to compare to
 * @param {string} params.taskText - The raw task/acceptance text from PR body
 * @param {object} [params.core] - Optional core for logging
 * @returns {Promise<{matches: Array<{task: string, reason: string, confidence: string}>, summary: string}>}
 */
async function analyzeTaskCompletion({ github: rawGithub, context, prNumber, baseSha, headSha, taskText, core, pr }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const matches = [];
  const log = (msg) => core?.info?.(msg) || console.log(msg);

  if (!context?.repo?.owner || !context?.repo?.repo) {
    log('Skipping task analysis: missing repo context.');
    return { matches, summary: 'Missing repo context for task analysis' };
  }

  if (!taskText || !baseSha || !headSha) {
    log('Skipping task analysis: missing task text or commit range.');
    return { matches, summary: 'Insufficient data for task analysis' };
  }

  // Get commits between base and head
  let commits = [];
  try {
    const { data } = await github.rest.repos.compareCommits({
      owner: context.repo.owner,
      repo: context.repo.repo,
      base: baseSha,
      head: headSha,
    });
    commits = data.commits || [];
  } catch (error) {
    log(`Failed to get commits: ${error.message}`);
    return { matches, summary: `Failed to analyze: ${error.message}` };
  }

  // Get files changed
  let filesChanged = [];
  try {
    const files = await fetchPrFilesCached({ github, context, prNumber, core });
    filesChanged = files.map(f => f.filename);
  } catch (error) {
    log(`Failed to get files: ${error.message}`);
  }

  // Parse tasks into individual items
  const taskLines = taskText.split('\n')
    .map(line => {
      const match = line.match(/^\s*(?:[-*+]|\d+[.)])\s*\[\s*\]\s*(.+)$/);
      return match ? match[1].trim() : null;
    })
    .filter(Boolean);

  log(`Analyzing ${commits.length} commits against ${taskLines.length} unchecked tasks`);

  // Common action synonyms for better matching
  const SYNONYMS = {
    add: ['create', 'implement', 'introduce', 'build'],
    create: ['add', 'implement', 'introduce', 'build'],
    implement: ['add', 'create', 'build'],
    fix: ['repair', 'resolve', 'correct', 'patch'],
    update: ['modify', 'change', 'revise', 'edit'],
    remove: ['delete', 'drop', 'eliminate'],
    test: ['tests', 'testing', 'spec', 'specs'],
    config: ['configuration', 'settings', 'configure'],
    doc: ['docs', 'documentation', 'document'],
  };

  // Helper to split camelCase/PascalCase into words
  function splitCamelCase(str) {
    return str
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
      .toLowerCase()
      .split(/[\s_-]+/)
      .filter(w => w.length > 2);
  }

  // Build keyword map from commits
  const commitKeywords = new Set();
  const commitMessages = commits
    .map(c => c.commit.message.toLowerCase())
    .join(' ');

  // Extract meaningful words from commit messages
  const words = commitMessages.match(/\b[a-z_-]{3,}\b/g) || [];
  words.forEach(w => commitKeywords.add(w));

  // Also split camelCase words from commit messages
  const camelWords = commits
    .map(c => c.commit.message)
    .join(' ')
    .match(/[a-zA-Z][a-z]+[A-Z][a-zA-Z]*/g) || [];
  camelWords.forEach(w => splitCamelCase(w).forEach(part => commitKeywords.add(part)));

  // Also extract from file paths
  filesChanged.forEach(f => {
    const parts = f.toLowerCase().replace(/[^a-z0-9_/-]/g, ' ').split(/[\s/]+/);
    parts.forEach(p => p.length > 2 && commitKeywords.add(p));
    // Extract camelCase from file names
    const fileName = f.split('/').pop() || '';
    splitCamelCase(fileName.replace(/\.[^.]+$/, '')).forEach(w => commitKeywords.add(w));
  });

  // Add synonyms for all commit keywords
  const expandedKeywords = new Set(commitKeywords);
  for (const keyword of commitKeywords) {
    const synonymList = SYNONYMS[keyword];
    if (synonymList) {
      synonymList.forEach(syn => expandedKeywords.add(syn));
    }
  }

  // Build module-to-test-file map for better test task matching
  // e.g., tests/test_adapter_base.py -> ["adapter", "base", "adapters"]
  const testFileModules = new Map();
  filesChanged.forEach(f => {
    const match = f.match(/tests\/test_([a-z_]+)\.py$/i);
    if (match) {
      const moduleParts = match[1].toLowerCase().split('_');
      // Add both singular and plural forms, plus the full module name
      const modules = [...moduleParts];
      moduleParts.forEach(p => {
        if (!p.endsWith('s')) modules.push(p + 's');
        if (p.endsWith('s')) modules.push(p.slice(0, -1));
      });
      modules.push(match[1]); // full module name like "adapter_base"
      testFileModules.set(f, modules);
    }
  });

  function extractIssueNumber(task) {
    const match = task.match(/#(\d+)|issues\/(\d+)|pull\/(\d+)/i);
    return match ? (match[1] || match[2] || match[3]) : null;
  }

  const issuePatternCache = new Map();
  const buildIssuePattern = (issueNumber) => {
    if (!issueNumber) {
      return null;
    }
    if (!issuePatternCache.has(issueNumber)) {
      issuePatternCache.set(issueNumber, new RegExp(`\\b${issueNumber}\\b`));
    }
    return issuePatternCache.get(issueNumber);
  };

  const issueMatchesText = (pattern, value) => {
    if (!pattern) {
      return false;
    }
    return pattern.test(String(value || ''));
  };

  // Match tasks to commits/files
  for (const task of taskLines) {
    const taskLower = task.toLowerCase();
    const taskWords = taskLower.match(/\b[a-z_-]{3,}\b/g) || [];
    const isTestTask = /\b(test|tests|unit\s*test|coverage)\b/i.test(task);
    const issueNumber = extractIssueNumber(task);
    const issuePattern = buildIssuePattern(issueNumber);
    let strippedIssueTask = task
      .replace(/\[[^\]]*\]\(([^)]+)\)/g, '$1')
      .replace(/https?:\/\/\S+/gi, '');

    // Remove the specific issue reference if pattern exists
    if (issuePattern) {
      strippedIssueTask = strippedIssueTask.replace(issuePattern, '');
    }

    strippedIssueTask = strippedIssueTask
      .replace(/#\d+/g, '') // Remove only #number patterns
      .replace(/[\[\]().]/g, '')
      .trim();
    const isIssueOnlyTask = Boolean(issuePattern) && strippedIssueTask === '';

    // Calculate overlap score using expanded keywords (with synonyms)
    const matchingWords = taskWords.filter(w => expandedKeywords.has(w));
    const score = taskWords.length > 0 ? matchingWords.length / taskWords.length : 0;

    // Extract explicit file references from task (e.g., `filename.js` or filename.test.js)
    const fileRefs = taskLower.match(/`([^`]+\.[a-z]+)`|([a-z0-9_./-]+(?:\.test)?\.(?:js|ts|py|yml|yaml|md))/g) || [];
    const cleanFileRefs = fileRefs.map(f => f.replace(/`/g, '').toLowerCase());

    // Check for explicit file creation (high confidence if exact file was created)
    const exactFileMatch = cleanFileRefs.some(ref => {
      const refBase = ref.split('/').pop(); // Get just filename
      return filesChanged.some(f => {
        const fBase = f.split('/').pop().toLowerCase();
        return fBase === refBase || f.toLowerCase().endsWith(ref);
      });
    });


    // Special check for test tasks: match module references to test files
    // e.g., "Add unit tests for `adapters/` module" should match tests/test_adapter_base.py
    let testModuleMatch = false;
    if (isTestTask) {
      // Extract module references from task (e.g., `adapters/`, `etl/`)
      const moduleRefs = taskLower.match(/`([a-z_\/]+)`|for\s+([a-z_]+)\s+module/gi) || [];
      const cleanModuleRefs = moduleRefs.map(m => m.replace(/[`\/]/g, '').toLowerCase().trim())
        .flatMap(m => [m, m.replace(/s$/, ''), m + 's']); // singular/plural

      for (const [testFile, modules] of testFileModules.entries()) {
        if (cleanModuleRefs.some(ref => modules.some(mod => mod.includes(ref) || ref.includes(mod)))) {
          testModuleMatch = true;
          break;
        }
      }
    }

    // Check for specific file mentions (partial match)
    const fileMatch = filesChanged.some(f => {
      const fLower = f.toLowerCase();
      return taskWords.some(w => fLower.includes(w));
    });

    // Check for specific commit message matches
    const commitMatch = commits.some(c => {
      const msg = c.commit.message.toLowerCase();
      return taskWords.some(w => w.length > 4 && msg.includes(w));
    });

    let confidence = 'low';
    let reason = '';

    // Exact file match is very high confidence
    if (isIssueOnlyTask) {
      if (!pr) {
        core.warning('analyzeTaskCompletion: pr parameter is undefined');
      }
      const prTitle = pr?.title;
      const prRef = pr?.head?.ref;
      const prMatch = issueMatchesText(issuePattern, prTitle) || issueMatchesText(issuePattern, prRef);
      const commitIssueMatch = commits.some(c => issueMatchesText(issuePattern, c.commit?.message));
      const fileIssueMatch = filesChanged.some(f => issueMatchesText(issuePattern, f));
      if (prMatch || commitIssueMatch || fileIssueMatch) {
        const reasonParts = [];
        if (prMatch) {
          reasonParts.push('PR title/branch');
        }
        if (commitIssueMatch) {
          reasonParts.push('commit message');
        }
        if (fileIssueMatch) {
          reasonParts.push('file path');
        }
        reason = `Issue ${issueNumber} matched ${reasonParts.join(', ')}`;
        matches.push({ task, reason, confidence: 'high' });
        continue;
      }
    }

    if (exactFileMatch) {
      confidence = 'high';
      const matchedFile = cleanFileRefs.find(ref => filesChanged.some(f => f.toLowerCase().includes(ref)));
      reason = `Exact file created: ${matchedFile}`;
      matches.push({ task, reason, confidence });
    } else if (isTestTask && testModuleMatch) {
      confidence = 'high';
      reason = 'Test file created matching module reference';
      matches.push({ task, reason, confidence });
    } else if (score >= 0.35 && (fileMatch || commitMatch)) {
      // Lowered threshold from 0.5 to 0.35 to catch more legitimate completions
      confidence = 'high';
      reason = `${Math.round(score * 100)}% keyword match, ${fileMatch ? 'file match' : 'commit match'}`;
      matches.push({ task, reason, confidence });
    } else if (score >= 0.25 && fileMatch) {
      // File match with moderate keyword overlap is high confidence
      confidence = 'high';
      reason = `${Math.round(score * 100)}% keyword match with file match`;
      matches.push({ task, reason, confidence });
    } else if (score >= 0.2 || fileMatch) {
      confidence = 'medium';
      reason = `${Math.round(score * 100)}% keyword match${fileMatch ? ', file touched' : ''}`;
      matches.push({ task, reason, confidence });
    }
  }

  const summary = matches.length > 0
    ? `Found ${matches.length} potential task completion(s): ${matches.filter(m => m.confidence === 'high').length} high, ${matches.filter(m => m.confidence === 'medium').length} medium confidence`
    : 'No clear task matches found in commits';

  log(summary);
  return { matches, summary };
}

/**
 * Auto-reconcile task checkboxes in PR body based on commit analysis.
 * Updates the PR body to check off tasks that appear to be completed.
 * @param {object} params - Parameters
 * @param {object} params.github - GitHub API client
 * @param {object} params.context - GitHub Actions context
 * @param {number} params.prNumber - PR number
 * @param {string} params.baseSha - Base SHA (before agent work)
 * @param {string} params.headSha - Head SHA (after agent work)
 * @param {string[]} [params.llmCompletedTasks] - Tasks marked complete by LLM analysis
 * @param {object} [params.core] - Optional core for logging
 * @returns {Promise<{updated: boolean, tasksChecked: number, details: string}>}
 */
async function autoReconcileTasks({ github: rawGithub, context, prNumber, baseSha, headSha, llmCompletedTasks, core }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const log = (msg) => core?.info?.(msg) || console.log(msg);
  const sources = { llm: 0, commit: 0 };

  if (!context?.repo?.owner || !context?.repo?.repo || !prNumber) {
    log('Skipping reconciliation: missing repo context or PR number.');
    return {
      updated: false,
      tasksChecked: 0,
      details: 'Missing repo context or PR number',
      sources,
    };
  }

  // Get current PR body
  let pr;
  try {
    pr = await fetchPullRequestCached({ github, context, prNumber, core });
    if (!pr) {
      throw new Error('PR data unavailable');
    }
  } catch (error) {
    log(`Failed to get PR: ${error.message}`);
    return { updated: false, tasksChecked: 0, details: `Failed to get PR: ${error.message}` };
  }

  const sections = parseScopeTasksAcceptanceSections(pr.body || '');
  const taskText = [sections.tasks, sections.acceptance].filter(Boolean).join('\n');

  if (!taskText) {
    log('Skipping reconciliation: no tasks found in PR body.');
    return { updated: false, tasksChecked: 0, details: 'No tasks found in PR body', sources };
  }

  // Build high-confidence matches from multiple sources
  let highConfidence = [];

  // Source 1: LLM analysis (highest priority if available)
  if (llmCompletedTasks && Array.isArray(llmCompletedTasks) && llmCompletedTasks.length > 0) {
    log(`LLM analysis found ${llmCompletedTasks.length} completed task(s)`);
    for (const task of llmCompletedTasks) {
      highConfidence.push({
        task,
        reason: 'LLM session analysis',
        confidence: 'high',
        source: 'llm',
      });
      sources.llm += 1;
    }
  }

  // Source 2: Commit/file analysis (fallback or supplementary)
  const analysis = await analyzeTaskCompletion({
    github, context, prNumber, baseSha, headSha, taskText, core, pr,
  });

  // Add commit-based matches that aren't already covered by LLM
  const llmTasksLower = new Set((llmCompletedTasks || []).map(t => t.toLowerCase()));
  const commitMatches = analysis.matches
    .filter(m => m.confidence === 'high')
    .filter(m => !llmTasksLower.has(m.task.toLowerCase()));

  if (commitMatches.length > 0) {
    log(`Commit analysis found ${commitMatches.length} additional task(s)`);
    for (const match of commitMatches) {
      highConfidence.push({ ...match, source: 'commit' });
      sources.commit += 1;
    }
  }

  if (highConfidence.length === 0) {
    log('No high-confidence task matches to auto-check');
    return {
      updated: false,
      tasksChecked: 0,
      details: analysis.summary + ' (no high-confidence matches for auto-check)',
      sources,
    };
  }

  // Update PR body to check off matched tasks
  let updatedBody = pr.body;
  let checkedCount = 0;

  for (const match of highConfidence) {
    // Escape special regex characters in task text
    const escaped = match.task.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`(^|\\n)(\\s*(?:[-*+]|\\d+[.)])\\s*)\\[\\s*\\](\\s*${escaped})`, 'i');

    if (pattern.test(updatedBody)) {
      updatedBody = updatedBody.replace(pattern, '$1$2[x]$3');
      checkedCount++;
      log(`Auto-checked task: ${match.task.slice(0, 50)}... (${match.reason})`);
    }
  }

  if (checkedCount === 0) {
    log('Matched tasks but no checkbox patterns found to update.');
    return {
      updated: false,
      tasksChecked: 0,
      details: 'Tasks matched but patterns not found in body',
      sources,
    };
  }

  // Cascade checked parents to their indented children so that sub-tasks
  // (e.g., "Define scope for: …", "Implement focused slice for: …") are
  // automatically checked when their parent task is marked complete.
  // Count checkboxes *before* cascade using a plain regex so we don't
  // redundantly run cascadeParentCheckboxes inside countCheckboxes.
  const plainCount = (text) => {
    const checked = (text.match(/\[[xX]\]/g) || []).length;
    const total = (text.match(/\[(?:\s|[xX])\]/g) || []).length;
    return { checked, total };
  };
  const beforeCascade = updatedBody;
  updatedBody = cascadeParentCheckboxes(updatedBody);
  const cascadedCounts = countCheckboxes(updatedBody);
  const beforeCounts = plainCount(beforeCascade);
  const cascadedCount = cascadedCounts.checked - beforeCounts.checked;
  if (cascadedCount > 0) {
    log(`Cascaded ${cascadedCount} sub-task checkbox(es) from checked parents`);
    checkedCount += cascadedCount;
  }

  // Update the PR body
  try {
    await github.rest.pulls.update({
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: prNumber,
      body: updatedBody,
    });
    log(`Updated PR body, checked ${checkedCount} task(s)`);
  } catch (error) {
    log(`Failed to update PR body: ${error.message}`);
    return {
      updated: false,
      tasksChecked: 0,
      details: `Failed to update PR: ${error.message}`,
      sources,
    };
  }

  // Build detailed description
  const sourceDesc = [];
  if (sources.llm > 0) sourceDesc.push(`${sources.llm} from LLM analysis`);
  if (sources.commit > 0) sourceDesc.push(`${sources.commit} from commit analysis`);
  const sourceInfo = sourceDesc.length > 0 ? ` (${sourceDesc.join(', ')})` : '';

  return {
    updated: true,
    tasksChecked: checkedCount,
    details: `Auto-checked ${checkedCount} task(s)${sourceInfo}: ${highConfidence.map(m => m.task.slice(0, 30) + '...').join(', ')}`,
    sources,
  };
}

module.exports = {
  countCheckboxes,
  cascadeParentCheckboxes,
  parseConfig,
  buildTaskAppendix,
  extractSourceSection,
  evaluateKeepaliveLoop,
  markAgentRunning,
  updateKeepaliveLoopSummary,
  analyzeTaskCompletion,
  autoReconcileTasks,
  normaliseChecklistSection,
  checkRateLimitStatus,
  postRateLimitNotification,
  hasRecentRateLimitNotification,
  RATE_LIMIT_COMMENT_MARKER,
};
