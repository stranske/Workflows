'use strict';

const { parseScopeTasksAcceptanceSections } = require('./issue_scope_parser');
const { loadKeepaliveState, formatStateComment } = require('./keepalive_state');

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

function countCheckboxes(markdown) {
  const result = { total: 0, checked: 0, unchecked: 0 };
  const regex = /-\s*\[( |x|X)\]/g;
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
    if (!key) {
      continue;
    }
    const lowered = rawValue.toLowerCase();
    if (['true', 'false', 'yes', 'no', 'on', 'off'].includes(lowered)) {
      result[key] = ['true', 'yes', 'on'].includes(lowered);
    } else if (!Number.isNaN(Number(rawValue))) {
      result[key] = Number(rawValue);
    } else {
      result[key] = rawValue;
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

async function resolvePrNumber({ github, context, core }) {
  const payload = context.payload || {};
  const eventName = context.eventName;

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

async function resolveGateConclusion({ github, context, pr, eventName, payload, core }) {
  if (eventName === 'workflow_run') {
    return normalise(payload?.workflow_run?.conclusion);
  }

  if (!pr) {
    return '';
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
        return normalise(match.conclusion);
      }
      const latest = data.workflow_runs[0];
      if (latest) {
        return normalise(latest.conclusion);
      }
    }
  } catch (error) {
    if (core) core.info(`Failed to resolve Gate conclusion: ${error.message}`);
  }

  return '';
}

async function evaluateKeepaliveLoop({ github, context, core }) {
  const payload = context.payload || {};
  const prNumber = await resolvePrNumber({ github, context, core });
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

  const gateConclusion = await resolveGateConclusion({
    github,
    context,
    pr,
    eventName: context.eventName,
    payload,
    core,
  });
  const gateNormalized = normalise(gateConclusion).toLowerCase();

  const config = parseConfig(pr.body || '');
  const labels = Array.isArray(pr.labels) ? pr.labels.map((label) => normalise(label.name).toLowerCase()) : [];
  const hasAgentLabel = labels.includes('agent:codex');
  const keepaliveEnabled = config.keepalive_enabled && hasAgentLabel;

  const sections = parseScopeTasksAcceptanceSections(pr.body || '');
  const combinedChecklist = [sections?.tasks, sections?.acceptance].filter(Boolean).join('\n');
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
  const iteration = toNumber(config.iteration ?? state.iteration, 0);
  const maxIterations = toNumber(config.max_iterations ?? state.max_iterations, 5);
  const failureThreshold = toNumber(config.failure_threshold ?? state.failure_threshold, 3);

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
  } else if (iteration >= maxIterations) {
    action = 'stop';
    reason = 'max-iterations';
  } else if (gateNormalized !== 'success') {
    action = 'wait';
    reason = gateNormalized ? 'gate-not-success' : 'gate-pending';
  } else if (tasksRemaining) {
    action = 'run';
    reason = 'ready';
  }

  return {
    prNumber,
    action,
    reason,
    gateConclusion,
    config,
    iteration,
    maxIterations,
    failureThreshold,
    checkboxCounts,
    hasAgentLabel,
    keepaliveEnabled,
    stateCommentId: stateResult.commentId || 0,
    state,
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
  const iteration = toNumber(inputs.iteration, 0);
  const maxIterations = toNumber(inputs.maxIterations ?? inputs.max_iterations, 0);
  const failureThreshold = Math.max(1, toNumber(inputs.failureThreshold ?? inputs.failure_threshold, 3));
  const runResult = normalise(inputs.runResult || inputs.run_result);
  const stateTrace = normalise(inputs.trace || inputs.keepalive_trace || '');

  // Codex output details
  const codexExitCode = normalise(inputs.codex_exit_code ?? inputs.codexExitCode);
  const codexChangesMade = normalise(inputs.codex_changes_made ?? inputs.codexChangesMade);
  const codexCommitSha = normalise(inputs.codex_commit_sha ?? inputs.codexCommitSha);
  const codexFilesChanged = toNumber(inputs.codex_files_changed ?? inputs.codexFilesChanged, 0);
  const codexSummary = normalise(inputs.codex_summary ?? inputs.codexSummary);

  const { state: previousState, commentId } = await loadKeepaliveState({
    github,
    context,
    prNumber,
    trace: stateTrace,
  });
  const previousFailure = previousState?.failure || {};

  let nextIteration = iteration;
  let failure = { ...previousFailure };
  let stop = action === 'stop';
  let summaryReason = reason || action || 'unknown';

  if (action === 'run') {
    if (runResult === 'success') {
      nextIteration = iteration + 1;
      failure = {};
    } else if (runResult) {
      const same = failure.reason === 'codex-run-failed';
      const count = same ? toNumber(failure.count, 0) + 1 : 1;
      failure = { reason: 'codex-run-failed', count };
      if (count >= failureThreshold) {
        stop = true;
        summaryReason = 'codex-run-failed-repeat';
      } else {
        summaryReason = 'codex-run-failed';
      }
    }
  } else {
    const sameReason = failure.reason && failure.reason === summaryReason;
    const count = sameReason ? toNumber(failure.count, 0) + 1 : 1;
    failure = { reason: summaryReason, count };
    if (!stop && count >= failureThreshold) {
      stop = true;
      summaryReason = `${summaryReason}-repeat`;
    }
  }

  const summaryLines = [
    '<!-- keepalive-loop-summary -->',
    `## 🤖 Keepalive Loop Status`,
    '',
    `**PR #${prNumber}** | Iteration **${nextIteration}/${maxIterations || '∞'}**`,
    '',
    '### Current State',
    `| Metric | Value |`,
    `|--------|-------|`,
    `| Action | ${action || 'unknown'} (${summaryReason || 'n/a'}) |`,
    `| Gate | ${gateConclusion || 'unknown'} |`,
    `| Tasks | ${Math.max(0, tasksTotal - tasksUnchecked)}/${tasksTotal} complete |`,
    `| Keepalive | ${keepaliveEnabled ? '✅ enabled' : '❌ disabled'} |`,
    `| Autofix | ${autofixEnabled ? '✅ enabled' : '❌ disabled'} |`,
  ];

  // Add Codex run details if we ran Codex
  if (action === 'run' && runResult) {
    summaryLines.push('', '### Last Codex Run');
    
    if (runResult === 'success') {
      const changesIcon = codexChangesMade === 'true' ? '✅' : '⚪';
      summaryLines.push(
        `| Result | Value |`,
        `|--------|-------|`,
        `| Status | ✅ Success |`,
        `| Changes | ${changesIcon} ${codexChangesMade === 'true' ? `${codexFilesChanged} file(s)` : 'No changes'} |`,
      );
      if (codexCommitSha) {
        summaryLines.push(`| Commit | [\`${codexCommitSha.slice(0, 7)}\`](../commit/${codexCommitSha}) |`);
      }
    } else {
      summaryLines.push(
        `| Result | Value |`,
        `|--------|-------|`,
        `| Status | ❌ Failed (exit code: ${codexExitCode || 'unknown'}) |`,
        `| Failures | ${failure.count || 1}/${failureThreshold} before pause |`,
      );
    }
    
    // Add Codex output summary if available
    if (codexSummary && codexSummary.length > 10) {
      const truncatedSummary = codexSummary.length > 300 
        ? codexSummary.slice(0, 300) + '...' 
        : codexSummary;
      summaryLines.push('', '**Codex output:**', `> ${truncatedSummary}`);
    }
  }

  if (stop) {
    summaryLines.push('', '⚠️ **Status: Paused – human attention required**');
  }

  const newState = {
    trace: stateTrace || previousState?.trace || '',
    pr_number: prNumber,
    iteration: nextIteration,
    max_iterations: maxIterations,
    last_action: action,
    last_reason: summaryReason,
    failure,
    tasks: { total: tasksTotal, unchecked: tasksUnchecked },
    gate_conclusion: gateConclusion,
    failure_threshold: failureThreshold,
  };

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

module.exports = {
  countCheckboxes,
  parseConfig,
  evaluateKeepaliveLoop,
  updateKeepaliveLoopSummary,
};
