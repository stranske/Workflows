'use strict';

const fs = require('fs');
const path = require('path');

const { parseScopeTasksAcceptanceSections } = require('./issue_scope_parser');
const { loadKeepaliveState, formatStateComment } = require('./keepalive_state');
const { classifyError, ERROR_CATEGORIES } = require('./error_classifier');
const { formatFailureComment } = require('./failure_comment_formatter');

function normalise(value) {
  return String(value ?? '').trim();
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
  const result = { total: 0, checked: 0, unchecked: 0 };
  const regex = /(?:^|\n)\s*(?:[-*+]|\d+[.)])\s*\[( |x|X)\]/g;
  const content = String(markdown || '');
  let match;
  while ((match = regex.exec(content)) !== null) {
    result.total += 1;
    if ((match[1] || '').toLowerCase() === 'x') {
      result.checked += 1;
    } else {
      result.unchecked += 1;
    }
  }
  return result;
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
      type = 'codex';
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

/**
 * Extract Source section from PR/issue body that contains links to parent issues/PRs.
 * @param {string} body - PR or issue body text
 * @returns {string|null} Source section content or null if not found
 */
function extractSourceSection(body) {
  const text = String(body || '');
  // Match "## Source" or "### Source" section
  const match = text.match(/##?\s*Source\s*\n([\s\S]*?)(?=\n##|\n---|\n\n\n|$)/i);
  if (match && match[1]) {
    const content = match[1].trim();
    // Only return if it has meaningful content (links to issues/PRs)
    if (/#\d+|github\.com/.test(content)) {
      return content;
    }
  }
  return null;
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

function extractConfigSnippet(body) {
  const source = String(body || '');
  if (!source.trim()) {
    return '';
  }

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
        if (jobId) {
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

async function evaluateKeepaliveLoop({ github, context, core, payload: overridePayload, overridePrNumber, forceRetry }) {
  const payload = overridePayload || context.payload || {};
  let prNumber = overridePrNumber || await resolvePrNumber({ github, context, core, payload });
  if (!prNumber) {
    return {
      prNumber: 0,
      action: 'skip',
      reason: 'pr-not-found',
    };
  }

  const { data: pr } = await github.rest.pulls.get({
    owner: context.repo.owner,
    repo: context.repo.repo,
    pull_number: prNumber,
  });

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
  const labels = Array.isArray(pr.labels) ? pr.labels.map((label) => normalise(label.name).toLowerCase()) : [];
  
  // Extract agent type from agent:* labels (supports agent:codex, agent:claude, etc.)
  const agentLabel = labels.find((label) => label.startsWith('agent:'));
  const agentType = agentLabel ? agentLabel.replace('agent:', '') : '';
  const hasAgentLabel = Boolean(agentType);
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
  // Prefer state iteration unless config explicitly sets it (0 from config is default, not explicit)
  const configHasExplicitIteration = config.iteration > 0;
  const iteration = configHasExplicitIteration ? config.iteration : toNumber(state.iteration, 0);
  const maxIterations = toNumber(config.max_iterations ?? state.max_iterations, 5);
  const failureThreshold = toNumber(config.failure_threshold ?? state.failure_threshold, 3);

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
  const tasksCompletedSinceLastRound = prevUnchecked - checkboxCounts.unchecked;
  
  // Calculate productivity score (0-100)
  // This is evidence-based: higher score = more confidence work is happening
  let productivityScore = 0;
  if (lastFilesChanged > 0) productivityScore += Math.min(40, lastFilesChanged * 10);
  if (tasksCompletedSinceLastRound > 0) productivityScore += Math.min(40, tasksCompletedSinceLastRound * 20);
  if (prevFilesChanged > 0 && iteration > 1) productivityScore += 10; // Recent historical activity
  if (!hasRecentFailures) productivityScore += 10; // No failures is a positive signal
  
  // An iteration is productive if it has a reasonable productivity score
  const isProductive = productivityScore >= 20 && !hasRecentFailures;
  
  // Early detection: Check for diminishing returns pattern
  // If we had activity before but now have none, might be naturally completing
  const diminishingReturns = 
    iteration >= 2 && 
    prevFilesChanged > 0 && 
    lastFilesChanged === 0 && 
    tasksCompletedSinceLastRound === 0;
  
  // max_iterations is a "stuck detection" threshold, not a hard cap
  // Continue past max if productive work is happening
  // But stop earlier if we detect diminishing returns pattern
  const shouldStopForMaxIterations = iteration >= maxIterations && !isProductive;
  const shouldStopEarly = diminishingReturns && iteration >= Math.ceil(maxIterations * 0.6);

  // Build task appendix for the agent prompt (after state load for reconciliation info)
  const taskAppendix = buildTaskAppendix(normalisedSections, checkboxCounts, state, { prBody: pr.body });

  let action = 'wait';
  let reason = 'pending';

  if (!hasAgentLabel) {
    action = 'wait';
    reason = 'missing-agent-label';
  } else if (!keepaliveEnabled) {
    action = 'skip';
    reason = 'keepalive-disabled';
  } else if (!tasksPresent) {
    action = 'stop';
    reason = 'no-checklists';
  } else if (allComplete) {
    action = 'stop';
    reason = 'tasks-complete';
  } else if (shouldStopEarly) {
    // Evidence-based early stopping: diminishing returns detected
    action = 'stop';
    reason = 'diminishing-returns';
  } else if (shouldStopForMaxIterations) {
    action = 'stop';
    reason = isProductive ? 'max-iterations' : 'max-iterations-unproductive';
  } else if (gateNormalized !== 'success') {
    if (gateNormalized === 'cancelled') {
      gateRateLimit = await detectRateLimitCancellation({
        github,
        context,
        runId: gateRun.runId,
        core,
      });
      // forceRetry bypasses defer/wait for cancelled gates
      if (forceRetry && tasksRemaining) {
        action = 'run';
        reason = 'force-retry-cancelled';
        if (core) core.info(`Force retry enabled: bypassing cancelled gate (rate_limit=${gateRateLimit})`);
      } else {
        action = gateRateLimit ? 'defer' : 'wait';
        reason = gateRateLimit ? 'gate-cancelled-rate-limit' : 'gate-cancelled';
      }
    } else {
      // Gate failed - check if we should route to fix mode or wait
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
  } else if (tasksRemaining) {
    action = 'run';
    reason = iteration >= maxIterations ? 'ready-extended' : 'ready';
  }

  // Determine prompt mode based on action
  const promptMode = action === 'fix' ? 'fix_ci' : 'normal';
  const promptFile = action === 'fix'
    ? '.github/codex/prompts/fix_ci_failures.md'
    : '.github/codex/prompts/keepalive_next_task.md';

  return {
    prNumber,
    prRef: pr.head.ref || '',
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
    agentType,
    taskAppendix,
    keepaliveEnabled,
    stateCommentId: stateResult.commentId || 0,
    state,
    forceRetry: Boolean(forceRetry),
  };
}

async function updateKeepaliveLoopSummary({ github, context, core, inputs }) {
  const prNumber = Number(inputs.prNumber || inputs.pr_number || 0);
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    if (core) core.info('No PR number available for summary update.');
    return;
  }

  const gateConclusion = normalise(inputs.gateConclusion || inputs.gate_conclusion);
  const action = normalise(inputs.action);
  const reason = normalise(inputs.reason);
  const tasksTotal = toNumber(inputs.tasksTotal ?? inputs.tasks_total, 0);
  const tasksUnchecked = toNumber(inputs.tasksUnchecked ?? inputs.tasks_unchecked, 0);
  const keepaliveEnabled = toBool(inputs.keepaliveEnabled ?? inputs.keepalive_enabled, false);
  const autofixEnabled = toBool(inputs.autofixEnabled ?? inputs.autofix_enabled, false);
  const agentType = normalise(inputs.agent_type ?? inputs.agentType) || 'codex';
  const iteration = toNumber(inputs.iteration, 0);
  const maxIterations = toNumber(inputs.maxIterations ?? inputs.max_iterations, 0);
  const failureThreshold = Math.max(1, toNumber(inputs.failureThreshold ?? inputs.failure_threshold, 3));
  const runResult = normalise(inputs.runResult || inputs.run_result);
  const stateTrace = normalise(inputs.trace || inputs.keepalive_trace || '');

  // Agent output details (agent-agnostic, with fallback to old codex_ names)
  const agentExitCode = normalise(inputs.agent_exit_code ?? inputs.agentExitCode ?? inputs.codex_exit_code ?? inputs.codexExitCode);
  const agentChangesMade = normalise(inputs.agent_changes_made ?? inputs.agentChangesMade ?? inputs.codex_changes_made ?? inputs.codexChangesMade);
  const agentCommitSha = normalise(inputs.agent_commit_sha ?? inputs.agentCommitSha ?? inputs.codex_commit_sha ?? inputs.codexCommitSha);
  const agentFilesChanged = toNumber(inputs.agent_files_changed ?? inputs.agentFilesChanged ?? inputs.codex_files_changed ?? inputs.codexFilesChanged, 0);
  const agentSummary = normalise(inputs.agent_summary ?? inputs.agentSummary ?? inputs.codex_summary ?? inputs.codexSummary);
  const runUrl = normalise(inputs.run_url ?? inputs.runUrl);

  // LLM task analysis details
  const llmProvider = normalise(inputs.llm_provider ?? inputs.llmProvider);
  const llmConfidence = toNumber(inputs.llm_confidence ?? inputs.llmConfidence, 0);
  const llmAnalysisRun = toBool(inputs.llm_analysis_run ?? inputs.llmAnalysisRun, false);
  
  // Quality metrics for BS detection and evidence-based decisions
  const llmRawConfidence = toNumber(inputs.llm_raw_confidence ?? inputs.llmRawConfidence, llmConfidence);
  const llmConfidenceAdjusted = toBool(inputs.llm_confidence_adjusted ?? inputs.llmConfidenceAdjusted, false);
  const llmQualityWarnings = normalise(inputs.llm_quality_warnings ?? inputs.llmQualityWarnings);
  const sessionDataQuality = normalise(inputs.session_data_quality ?? inputs.sessionDataQuality);
  const sessionEffortScore = toNumber(inputs.session_effort_score ?? inputs.sessionEffortScore, 0);
  const analysisTextLength = toNumber(inputs.analysis_text_length ?? inputs.analysisTextLength, 0);

  const { state: previousState, commentId } = await loadKeepaliveState({
    github,
    context,
    prNumber,
    trace: stateTrace,
  });
  const previousFailure = previousState?.failure || {};

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
  const runFailed = action === 'run' && runResult && runResult !== 'success';
  const isTransientFailure =
    action === 'run' &&
    runResult &&
    runResult !== 'success' &&
    transientDetails.category === ERROR_CATEGORIES.transient;
  const waitLikeAction = action === 'wait' || action === 'defer';
  const waitIsTransientReason = [
    'gate-pending',
    'missing-agent-label',
    'gate-cancelled',
    'gate-cancelled-rate-limit',
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
      if (isTransientFailure) {
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
    `| Iteration progress | ${
      maxIterations > 0
        ? inExtendedMode 
          ? `${formatProgressBar(maxIterations, maxIterations)} ${maxIterations} base + ${extendedCount} extended = **${nextIteration}** total`
          : formatProgressBar(nextIteration, maxIterations)
        : 'n/a (unbounded)'
    } |`,
    `| Action | ${action || 'unknown'} (${actionReason || 'n/a'}) |`,
    ...(dispositionLabel ? [`| Disposition | ${dispositionLabel} |`] : []),
    ...(runFailed ? [`| Agent status | ❌ AGENT FAILED |`] : []),
    `| Gate | ${gateConclusion || 'unknown'} |`,
    `| Tasks | ${tasksComplete}/${tasksTotal} complete |`,
    `| Keepalive | ${keepaliveEnabled ? '✅ enabled' : '❌ disabled'} |`,
    `| Autofix | ${autofixEnabled ? '✅ enabled' : '❌ disabled'} |`,
  ];

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
    } else {
      summaryLines.push(
        `| Result | Value |`,
        `|--------|-------|`,
        `| Status | ❌ AGENT FAILED |`,
        `| Reason | ${summaryReason || runResult || 'unknown'} |`,
        `| Exit code | ${agentExitCode || 'unknown'} |`,
        `| Failures | ${failure.count || 1}/${failureThreshold} before pause |`,
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
      `| Confidence | ${confidencePercent}% |`,
    );
    
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

  if (stop) {
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
    // Track task reconciliation for next iteration
    needs_task_reconciliation: madeChangesButNoTasksChecked,
    // Productivity tracking for evidence-based decisions
    last_files_changed: agentFilesChanged,
    prev_files_changed: toNumber(previousState?.last_files_changed, 0),
    // Quality metrics for analysis validation
    last_effort_score: sessionEffortScore,
    last_data_quality: sessionDataQuality,
  };

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

  // NOTE: Failure comment posting removed - handled by reusable-codex-run.yml with proper deduplication
  // This prevents duplicate failure notifications on PRs

  summaryLines.push('', formatStateComment(newState));
  const body = summaryLines.join('\n');

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
}

/**
 * Mark that an agent is currently running by updating the summary comment.
 * This provides real-time visibility into the keepalive loop's activity.
 */
async function markAgentRunning({ github, context, core, inputs }) {
  const prNumber = Number(inputs.prNumber || inputs.pr_number || 0);
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    if (core) core.info('No PR number available for running status update.');
    return;
  }

  const agentType = normalise(inputs.agent_type ?? inputs.agentType) || 'codex';
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
async function analyzeTaskCompletion({ github, context, prNumber, baseSha, headSha, taskText, core }) {
  const matches = [];
  const log = (msg) => core?.info?.(msg) || console.log(msg);

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
    const { data } = await github.rest.pulls.listFiles({
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: prNumber,
      per_page: 100,
    });
    filesChanged = data.map(f => f.filename);
  } catch (error) {
    log(`Failed to get files: ${error.message}`);
  }

  // Parse tasks into individual items
  const taskLines = taskText.split('\n')
    .filter(line => /^\s*[-*+]\s*\[\s*\]/.test(line))
    .map(line => {
      const match = line.match(/^\s*[-*+]\s*\[\s*\]\s*(.+)$/);
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

  // Match tasks to commits/files
  for (const task of taskLines) {
    const taskLower = task.toLowerCase();
    const taskWords = taskLower.match(/\b[a-z_-]{3,}\b/g) || [];
    const isTestTask = /\b(test|tests|unit\s*test|coverage)\b/i.test(task);
    
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
async function autoReconcileTasks({ github, context, prNumber, baseSha, headSha, llmCompletedTasks, core }) {
  const log = (msg) => core?.info?.(msg) || console.log(msg);

  // Get current PR body
  let pr;
  try {
    const { data } = await github.rest.pulls.get({
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: prNumber,
    });
    pr = data;
  } catch (error) {
    log(`Failed to get PR: ${error.message}`);
    return { updated: false, tasksChecked: 0, details: `Failed to get PR: ${error.message}` };
  }

  const sections = parseScopeTasksAcceptanceSections(pr.body || '');
  const taskText = [sections.tasks, sections.acceptance].filter(Boolean).join('\n');

  if (!taskText) {
    log('Skipping reconciliation: no tasks found in PR body.');
    return { updated: false, tasksChecked: 0, details: 'No tasks found in PR body' };
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
    }
  }

  // Source 2: Commit/file analysis (fallback or supplementary)
  const analysis = await analyzeTaskCompletion({
    github, context, prNumber, baseSha, headSha, taskText, core
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
    }
  }
  
  if (highConfidence.length === 0) {
    log('No high-confidence task matches to auto-check');
    return { 
      updated: false, 
      tasksChecked: 0, 
      details: analysis.summary + ' (no high-confidence matches for auto-check)'
    };
  }

  // Update PR body to check off matched tasks
  let updatedBody = pr.body;
  let checkedCount = 0;

  for (const match of highConfidence) {
    // Escape special regex characters in task text
    const escaped = match.task.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`([-*+]\\s*)\\[\\s*\\](\\s*${escaped})`, 'i');
    
    if (pattern.test(updatedBody)) {
      updatedBody = updatedBody.replace(pattern, '$1[x]$2');
      checkedCount++;
      log(`Auto-checked task: ${match.task.slice(0, 50)}... (${match.reason})`);
    }
  }

  if (checkedCount === 0) {
    log('Matched tasks but no checkbox patterns found to update.');
    return { 
      updated: false, 
      tasksChecked: 0, 
      details: 'Tasks matched but patterns not found in body' 
    };
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
      sources: { llm: 0, commit: 0 },
    };
  }

  // Count matches by source for reporting
  const llmCount = highConfidence.filter(m => m.source === 'llm').length;
  const commitCount = highConfidence.filter(m => m.source === 'commit').length;
  
  // Build detailed description
  const sourceDesc = [];
  if (llmCount > 0) sourceDesc.push(`${llmCount} from LLM analysis`);
  if (commitCount > 0) sourceDesc.push(`${commitCount} from commit analysis`);
  const sourceInfo = sourceDesc.length > 0 ? ` (${sourceDesc.join(', ')})` : '';

  return {
    updated: true,
    tasksChecked: checkedCount,
    details: `Auto-checked ${checkedCount} task(s)${sourceInfo}: ${highConfidence.map(m => m.task.slice(0, 30) + '...').join(', ')}`,
    sources: { llm: llmCount, commit: commitCount },
  };
}

module.exports = {
  countCheckboxes,
  parseConfig,
  buildTaskAppendix,
  extractSourceSection,
  evaluateKeepaliveLoop,
  markAgentRunning,
  updateKeepaliveLoopSummary,
  analyzeTaskCompletion,
  autoReconcileTasks,
  normaliseChecklistSection,
};
