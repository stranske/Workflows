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

async function writeStepSummary({
  core,
  iteration,
  maxIterations,
  tasksTotal,
  tasksUnchecked,
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
  const summaryLines = [
    '### Keepalive iteration summary',
    '',
    '| Field | Value |',
    '| --- | --- |',
    `| Iteration | ${iterationLabel} |`,
    `| Tasks completed | ${completed}/${total} |`,
    `| Files changed | ${filesChanged} |`,
    `| Outcome | ${outcome || 'unknown'} |`,
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
    const match = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (!match) {
      return line;
    }
    const [, indent, bullet, remainderRaw] = match;
    const remainder = remainderRaw.trim();
    if (!remainder) {
      return line;
    }
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

/**
 * Build the task appendix that gets passed to the agent prompt.
 * This provides explicit, structured tasks and acceptance criteria.
 * @param {object} sections - Parsed scope/tasks/acceptance sections
 * @param {object} checkboxCounts - { total, checked, unchecked }
 * @param {object} [state] - Optional keepalive state for reconciliation info
 */
function buildTaskAppendix(sections, checkboxCounts, state = {}) {
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
  const iteration = toNumber(config.iteration ?? state.iteration, 0);
  const maxIterations = toNumber(config.max_iterations ?? state.max_iterations, 5);
  const failureThreshold = toNumber(config.failure_threshold ?? state.failure_threshold, 3);

  // Build task appendix for the agent prompt (after state load for reconciliation info)
  const taskAppendix = buildTaskAppendix(normalisedSections, checkboxCounts, state);

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
    prRef: pr.head.ref || '',
    action,
    reason,
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
  let stop = action === 'stop';
  let summaryReason = reason || action || 'unknown';

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
  } else {
    const sameReason = failure.reason && failure.reason === summaryReason;
    const count = sameReason ? toNumber(failure.count, 0) + 1 : 1;
    failure = { reason: summaryReason, count };
    if (!stop && count >= failureThreshold) {
      stop = true;
      summaryReason = `${summaryReason}-repeat`;
    }
  }

  // Capitalize agent name for display
  const agentDisplayName = agentType.charAt(0).toUpperCase() + agentType.slice(1);

  const summaryLines = [
    '<!-- keepalive-loop-summary -->',
    `## 🤖 Keepalive Loop Status`,
    '',
    `**PR #${prNumber}** | Agent: **${agentDisplayName}** | Iteration **${nextIteration}/${maxIterations || '∞'}**`,
    '',
    '### Current State',
    `| Metric | Value |`,
    `|--------|-------|`,
    `| Iteration progress | ${
      maxIterations > 0
        ? formatProgressBar(nextIteration, maxIterations)
        : 'n/a (unbounded)'
    } |`,
    `| Action | ${action || 'unknown'} (${summaryReason || 'n/a'}) |`,
    `| Gate | ${gateConclusion || 'unknown'} |`,
    `| Tasks | ${Math.max(0, tasksTotal - tasksUnchecked)}/${tasksTotal} complete |`,
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
        `| Status | ❌ Failed (exit code: ${agentExitCode || 'unknown'}) |`,
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
    tasks: { total: tasksTotal, unchecked: tasksUnchecked },
    gate_conclusion: gateConclusion,
    failure_threshold: failureThreshold,
    // Track task reconciliation for next iteration
    needs_task_reconciliation: madeChangesButNoTasksChecked,
    last_files_changed: agentFilesChanged,
  };

  const summaryOutcome = runResult || summaryReason || action || 'unknown';
  if (action === 'run' || runResult) {
    await writeStepSummary({
      core,
      iteration: nextIteration,
      maxIterations,
      tasksTotal,
      tasksUnchecked,
      agentFilesChanged,
      outcome: summaryOutcome,
    });
  }

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
  
  const summaryLines = [
    '<!-- keepalive-loop-summary -->',
    `## 🤖 Keepalive Loop Status`,
    '',
    `**PR #${prNumber}** | Agent: **${agentDisplayName}** | Iteration **${displayIteration}/${maxIterations || '∞'}**`,
    '',
    '### 🔄 Agent Running',
    '',
    `**${agentDisplayName} is actively working on this PR**${runLinkText}`,
    '',
    `| Status | Value |`,
    `|--------|-------|`,
    `| Agent | ${agentDisplayName} |`,
    `| Iteration | ${displayIteration} of ${maxIterations || '∞'} |`,
    `| Tasks remaining | ${tasksUnchecked}/${tasksTotal} |`,
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

module.exports = {
  countCheckboxes,
  parseConfig,
  buildTaskAppendix,
  evaluateKeepaliveLoop,
  markAgentRunning,
  updateKeepaliveLoopSummary,
};
