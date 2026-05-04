// Keepalive orchestrator gate runner extracted from the reusable workflow to
// reduce workflow YAML size and avoid GitHub parsing limits. This mirrors the
// previous inline github-script logic.

const {
  analyseSkipComments,
  isGateReason,
} = require('./keepalive_guard_utils.js');
const { evaluateKeepaliveGate } = require('./keepalive_gate.js');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');
const { parseScopeTasksAcceptanceSections } = require('./issue_scope_parser.js');

const KEEPALIVE_LABEL = 'agents:keepalive';
const PAUSE_LABEL = 'agents:paused';
const NEEDS_HUMAN_LABEL = 'needs-human';
const NEEDS_ATTENTION_LABEL = 'agent:needs-attention';
const NON_ROUTING_AGENT_LABELS = new Set([
  NEEDS_ATTENTION_LABEL,
  'agent:rate-limited',
  'agent:retry',
  'agent:auto',
]);
const DRAFT_DISPOSITION_MARKER = '<!-- keepalive-draft-disposition -->';
const MARK_PULL_REQUEST_READY_FOR_REVIEW_MUTATION = `mutation MarkPullRequestReadyForReview($pullRequestId: ID!) {
  markPullRequestReadyForReview(input: {pullRequestId: $pullRequestId}) {
    pullRequest {
      number
      isDraft
    }
  }
}`;

function normaliseLabelName(label) {
  if (!label) {
    return '';
  }
  if (typeof label === 'string') {
    return label.trim().toLowerCase();
  }
  return String(label.name || '').trim().toLowerCase();
}

function isConcreteAgentLabel(label) {
  const value = String(label || '').trim().toLowerCase();
  return /^agent:[a-z0-9_-]+$/.test(value) && !NON_ROUTING_AGENT_LABELS.has(value);
}

function inferAgentFromBranch(headRef, registry) {
  const ref = String(headRef || '').trim().toLowerCase();
  if (!ref || !registry || !registry.agents) {
    return '';
  }
  const firstSegment = ref.split('/')[0];
  if (!firstSegment) {
    return '';
  }
  for (const [key, config] of Object.entries(registry.agents)) {
    const branchPrefix = String(config?.branch_prefix || '').trim().toLowerCase();
    const prefixSegment = branchPrefix ? branchPrefix.split('/')[0] : '';
    if (prefixSegment && prefixSegment === firstSegment) {
      return String(key).trim().toLowerCase();
    }
    if (String(key).trim().toLowerCase() === firstSegment) {
      return String(key).trim().toLowerCase();
    }
  }
  return '';
}

function hasAutomationSignal(pr, labels) {
  const headRef = String(pr?.head?.ref || '').trim().toLowerCase();
  return (
    labels.has('codex-automation') ||
    labels.has('codex') ||
    labels.has('autofix') ||
    Array.from(labels).some((label) => isConcreteAgentLabel(label)) ||
    headRef.startsWith('codex/') ||
    headRef.startsWith('claude/') ||
    /^feat\/\d+/.test(headRef)
  );
}

function countMarkdownCheckboxes(body) {
  const counts = { checked: 0, unchecked: 0 };
  const text = String(body || '');
  const checkboxPattern = /^\s*[-*]\s+\[([ xX])\]/gm;
  for (const match of text.matchAll(checkboxPattern)) {
    if (String(match[1] || '').trim().toLowerCase() === 'x') {
      counts.checked += 1;
    } else {
      counts.unchecked += 1;
    }
  }
  return counts;
}

function countDraftDispositionCheckboxes(body) {
  const sections = parseScopeTasksAcceptanceSections(body || '');
  const scopedChecklist = [sections?.tasks, sections?.acceptance]
    .filter(Boolean)
    .join('\n');
  return countMarkdownCheckboxes(scopedChecklist);
}

async function addLabelsIfMissing({ github, owner, repo, prNumber, labels, currentLabels, core, summary }) {
  const toAdd = labels.filter((label) => label && !currentLabels.has(label.toLowerCase()));
  if (!toAdd.length) {
    return true;
  }

  try {
    await github.rest.issues.addLabels({
      owner,
      repo,
      issue_number: prNumber,
      labels: toAdd,
    });
    toAdd.forEach((label) => currentLabels.add(label.toLowerCase()));
    summary.addRaw(`Self-healed missing PR label(s): ${toAdd.join(', ')}`).addEOL();
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    core.warning(`Unable to add label(s) to PR #${prNumber}: ${message}`);
    summary.addRaw(`Failed to self-heal missing PR label(s): ${toAdd.join(', ')} (${message})`).addEOL();
    return false;
  }
}

async function removeLabelsIfPresent({ github, owner, repo, prNumber, labels, currentLabels, core, summary }) {
  const toRemove = labels.filter((label) => label && currentLabels.has(label.toLowerCase()));
  if (!toRemove.length) {
    return true;
  }

  let ok = true;
  for (const label of toRemove) {
    try {
      await github.rest.issues.removeLabel({
        owner,
        repo,
        issue_number: prNumber,
        name: label,
      });
      currentLabels.delete(label.toLowerCase());
    } catch (error) {
      const status = Number(error?.status || 0);
      if (status === 404) {
        currentLabels.delete(label.toLowerCase());
        continue;
      }
      ok = false;
      const message = error instanceof Error ? error.message : String(error);
      core.warning(`Unable to remove label ${label} from PR #${prNumber}: ${message}`);
      summary.addRaw(`Failed to clear draft routing label ${label}: ${message}`).addEOL();
    }
  }

  const removed = toRemove.filter((label) => !currentLabels.has(label.toLowerCase()));
  if (removed.length) {
    summary.addRaw(`Cleared draft routing label(s): ${removed.join(', ')}`).addEOL();
  }
  return ok;
}

async function markDraftReadyForReview({ github, pr, core, summary }) {
  const nodeId = String(pr?.node_id || '').trim();
  if (!nodeId) {
    summary.addRaw('Draft PR could not be converted automatically: missing GraphQL PR node id.').addEOL();
    return false;
  }
  if (typeof github.graphql !== 'function') {
    summary.addRaw('Draft PR could not be converted automatically: GitHub GraphQL client is unavailable.').addEOL();
    return false;
  }

  try {
    await github.graphql(MARK_PULL_REQUEST_READY_FOR_REVIEW_MUTATION, { pullRequestId: nodeId });
    summary.addRaw('Draft PR had no unchecked checklist items; marked ready for review.').addEOL();
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    core.warning(`Unable to mark draft PR ready for review: ${message}`);
    summary.addRaw(`Draft PR could not be converted automatically: ${message}`).addEOL();
    return false;
  }
}

function createIssueCommentAccess({ github, owner, repo, prNumber }) {
  const params = {
    owner,
    repo,
    issue_number: prNumber,
    per_page: 100,
  };
  let loaded = false;
  let cachedComments = [];
  let cachedError = null;

  const commentHasMarker = (comment, marker) =>
    String(comment?.body || '').includes(marker);

  async function loadIssueComments() {
    if (loaded) {
      if (cachedError) {
        throw cachedError;
      }
      return cachedComments;
    }

    try {
      cachedComments = (await github.paginate(github.rest.issues.listComments, params)) || [];
      loaded = true;
      return cachedComments;
    } catch (error) {
      cachedError = error;
      loaded = true;
      throw error;
    }
  }

  async function hasIssueCommentMarker(marker) {
    if (loaded) {
      if (cachedError) {
        throw cachedError;
      }
      return cachedComments.some((comment) => commentHasMarker(comment, marker));
    }

    if (typeof github.paginate?.iterator !== 'function') {
      return hasExistingDraftDispositionComment(await loadIssueComments());
    }

    const scannedComments = [];
    try {
      for await (const response of github.paginate.iterator(github.rest.issues.listComments, params)) {
        const pageComments = Array.isArray(response?.data) ? response.data : [];
        scannedComments.push(...pageComments);
        if (pageComments.some((comment) => commentHasMarker(comment, marker))) {
          return true;
        }
      }
      cachedComments = scannedComments;
      loaded = true;
      return false;
    } catch (error) {
      cachedError = error;
      loaded = true;
      throw error;
    }
  }

  return {
    hasIssueCommentMarker,
    loadIssueComments,
  };
}

function hasExistingDraftDispositionComment(comments) {
  return (comments || []).some((comment) =>
    String(comment?.body || '').includes(DRAFT_DISPOSITION_MARKER)
  );
}

function draftDispositionText(checkboxCounts, dispositionReason) {
  const checked = Number(checkboxCounts?.checked || 0);
  const unchecked = Number(checkboxCounts?.unchecked || 0);
  const total = checked + unchecked;

  if (total === 0 || dispositionReason === 'no-checklist') {
    return {
      summary: 'no keepalive checklist items were found',
      detail:
        'Keepalive found this PR still in draft, but no keepalive checklist items were found in the Tasks or Acceptance Criteria sections. Draft PRs must not occupy automation capacity silently.',
      nextAction:
        'Next human action: add or restore the keepalive checklist, disposition the draft, and rerun Gate when the PR is ready; or close/supersede the PR.',
    };
  }

  if (unchecked === 0) {
    return {
      summary: 'the keepalive checklist is complete, but automatic draft conversion failed',
      detail:
        'Keepalive found this PR still in draft and the keepalive checklist has no unchecked items, but automatic ready-for-review conversion failed. Draft PRs must not occupy automation capacity silently.',
      nextAction:
        'Next human action: mark the PR ready for review manually and rerun Gate; or close/supersede the PR.',
    };
  }

  return {
    summary: `${unchecked} unchecked keepalive checklist item(s) remain`,
    detail:
      `Keepalive found this PR still in draft with ${unchecked} unchecked keepalive checklist item(s). Draft PRs must not occupy automation capacity silently.`,
    nextAction:
      'Next human action: finish the unchecked acceptance items, mark the PR ready for review, and rerun Gate; or close/supersede the PR.',
  };
}

async function routeDraftToHuman({ github, owner, repo, prNumber, currentLabels, checkboxCounts, dispositionReason = '', hasDraftDispositionComment, core, summary }) {
  await addLabelsIfMissing({
    github,
    owner,
    repo,
    prNumber,
    labels: [NEEDS_ATTENTION_LABEL, NEEDS_HUMAN_LABEL],
    currentLabels,
    core,
    summary,
  });

  const disposition = draftDispositionText(checkboxCounts, dispositionReason);
  summary
    .addRaw(
      `Draft PR requires human disposition: ${disposition.summary} (checked=${checkboxCounts.checked}, unchecked=${checkboxCounts.unchecked}).`
    )
    .addEOL();

  let alreadyCommented = false;
  try {
    alreadyCommented = await hasDraftDispositionComment();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    core.warning(`Unable to scan draft disposition comments for PR #${prNumber}: ${message}`);
    summary
      .addRaw(`Skipped posting draft disposition comment because existing comments could not be scanned: ${message}`)
      .addEOL();
    return;
  }

  if (alreadyCommented) {
    summary.addRaw('Draft disposition comment already exists; not posting a duplicate.').addEOL();
    return;
  }

  const body = [
    DRAFT_DISPOSITION_MARKER,
    '### Draft PR requires human disposition',
    '',
    disposition.detail,
    '',
    `Applied \`${NEEDS_ATTENTION_LABEL}\` and \`${NEEDS_HUMAN_LABEL}\` so this is visible in automation summaries and human queues without permanently pausing keepalive.`,
    '',
    disposition.nextAction,
  ].join('\n');

  try {
    await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: prNumber,
      body,
    });
    summary.addRaw('Posted durable draft disposition comment for human routing.').addEOL();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    core.warning(`Unable to post draft disposition comment for PR #${prNumber}: ${message}`);
    summary.addRaw(`Failed to post draft disposition comment: ${message}`).addEOL();
  }
}

/**
 * Execute keepalive gate evaluation and emit outputs.
 * @param {{ core: any, github: any, context: any, env: NodeJS.ProcessEnv }} args
 */
async function runKeepaliveGate({ core, github, context, env }) {
  const normalise = (value) => String(value || '').trim();
  const toBool = (value) => ['true', '1', 'yes', 'on'].includes(normalise(value).toLowerCase());

  const keepaliveEnabled = toBool(env.KEEPALIVE_ENABLED);
  const trace = normalise(env.KEEPALIVE_TRACE);
  const round = normalise(env.KEEPALIVE_ROUND);
  const prRaw = normalise(env.KEEPALIVE_PR);
  const summary = core.summary;
  summary.addHeading('Keepalive gate evaluation');

  const renderLine = (reason) => {
    const labelRound = round || '?';
    const labelTrace = trace || 'unknown';
    const labelReason = reason || 'unspecified';
    return `Keepalive ${labelRound} ${labelTrace} skipped: ${labelReason}`;
  };

  const setOutputs = (proceed, reason) => {
    core.setOutput('proceed', proceed ? 'true' : 'false');
    core.setOutput('reason', reason || '');
  };

  const { owner, repo } = context.repo;

  const appendDetails = (details) => {
    if (!details) {
      return;
    }
    const entries = Array.isArray(details) ? details : [details];
    for (const entry of entries) {
      if (entry) {
        summary.addRaw(String(entry)).addEOL();
      }
    }
  };

  const finaliseSkip = async (reason, details, options = {}) => {
    const line = renderLine(reason);
    summary.addRaw(line).addEOL();
    appendDetails(details);
    await summary.write();

    setOutputs(false, reason);
  };

  if (!keepaliveEnabled || !trace) {
    setOutputs(true, '');
    summary.addRaw('Keepalive gating not required for this run.').addEOL().write();
    return;
  }

  const prNumber = Number(prRaw);
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    await finaliseSkip('missing-pr-number');
    return;
  }

  let pr;
  try {
    const response = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
    pr = response.data;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    core.warning(`Unable to load PR #${prNumber}: ${message}`);
    await finaliseSkip('pr-fetch-failed', message ? `Details: ${message}` : null);
    return;
  }
  const { hasIssueCommentMarker, loadIssueComments } = createIssueCommentAccess({ github, owner, repo, prNumber });
  const hasDraftDispositionComment = () => hasIssueCommentMarker(DRAFT_DISPOSITION_MARKER);

  const preGate = await evaluateKeepaliveGate({
    core,
    github,
    context,
    options: {
      prNumber,
      pullRequest: pr,
      currentRunId: context.runId,
      requireHumanActivation: true,
      requireGateSuccess: true,
    },
  });

  let _defaultAgent = 'codex';
  let _registry = null;
  try {
    const { loadAgentRegistry } = require('./agent_registry.js');
    _registry = loadAgentRegistry();
    _defaultAgent = _registry.default_agent || 'codex';
  } catch (_) {
    // Registry unavailable — fall back to codex
  }
  const inferredFromBranch = preGate.primaryAgent
    ? ''
    : inferAgentFromBranch(pr?.head?.ref, _registry);
  const agentAlias = String(
    preGate.primaryAgent || inferredFromBranch || _defaultAgent || ''
  )
    .trim()
    .toLowerCase();
  const runCap = Number.isFinite(preGate.runCap) ? preGate.runCap : '';
  const activeRuns = Number.isFinite(preGate.activeRuns) ? preGate.activeRuns : '';
  const inflightRuns = '';
  const recentRuns = '';
  const recentWindow = '';
  const runCapDetail = (() => {
    const breakdown = preGate.activeBreakdown || {};
    const orchestratorCount = Number(breakdown.orchestrator ?? breakdown['agents-70-orchestrator.yml'] ?? 0);
    const workerCount = Number(breakdown.worker ?? breakdown['agents-belt-worker.yml'] ?? breakdown['agents-72-codex-belt-worker.yml'] ?? 0);
    const normaliseCount = (value) => (Number.isFinite(value) ? value : 0);
    return `run cap detail: orchestrator=${normaliseCount(orchestratorCount)}, worker=${normaliseCount(workerCount)}`;
  })();

  core.setOutput('agent_alias', agentAlias);
  core.setOutput('run_cap', runCap !== '' ? String(runCap) : '');
  core.setOutput('active_runs', activeRuns !== '' ? String(activeRuns) : '');
  core.setOutput('active_runs_inflight', inflightRuns !== '' ? String(inflightRuns) : '');
  core.setOutput('active_runs_recent', recentRuns !== '' ? String(recentRuns) : '');
  core.setOutput('active_runs_recent_window', recentWindow !== '' ? String(recentWindow) : '');
  core.setOutput('has_sync_label', preGate.hasSyncRequiredLabel ? 'true' : 'false');
  core.setOutput('cap', runCap !== '' ? String(runCap) : '');
  core.setOutput('active', activeRuns !== '' ? String(activeRuns) : '');
  core.setOutput('head_sha', preGate.headSha || '');
  core.setOutput('last_green_sha', preGate.lastGreenSha || '');

  const reasons = [];
  const addReason = (reason) => {
    const value = typeof reason === 'string' ? reason.trim() : '';
    if (!value) {
      return;
    }
    if (!reasons.includes(value)) {
      reasons.push(value);
    }
  };

  if (!preGate.ok) {
    addReason(preGate.reason || 'pre-gate-failed');
    summary
      .addRaw(
        `Pre-gate check failed: reason=${preGate.reason || 'unknown'} ok=${preGate.ok ? 'true' : 'false'}`
      )
      .addEOL();
  } else if (preGate.pendingGate) {
    summary.addRaw('Gate pending; keepalive will retry once gate concludes.').addEOL();
  }

  let headSha = '';
  if (!pr) {
    addReason('missing-pr');
  } else {
    const labelEntries = Array.isArray(pr.labels) ? pr.labels : [];
    const currentLabels = new Set(
      labelEntries.map(normaliseLabelName).filter(Boolean)
    );

    const requiredLabels = [KEEPALIVE_LABEL];
    if (agentAlias) {
      requiredLabels.push(`agent:${agentAlias}`);
    }
    const unresolvedLabels = requiredLabels.filter((label) => !currentLabels.has(label));
    if (unresolvedLabels.length && hasAutomationSignal(pr, currentLabels)) {
      await addLabelsIfMissing({
        github,
        owner,
        repo,
        prNumber,
        labels: unresolvedLabels,
        currentLabels,
        core,
        summary,
      });
    }

    const remainingMissingLabels = requiredLabels.filter((label) => !currentLabels.has(label));
    if (remainingMissingLabels.length) {
      remainingMissingLabels.forEach((label) => addReason(`missing-label:${label}`));
      summary.addRaw(`Missing required keepalive labels: ${remainingMissingLabels.join(', ')}`).addEOL();
    }

    headSha = String(pr.head?.sha || '').trim();
    if ((pr.state || '').toLowerCase() !== 'open') {
      addReason('pr-not-open');
    }
    if (!headSha) {
      addReason('missing-head-sha');
    }
    let draftRequiresHuman = false;
    if (pr.draft) {
      const checkboxCounts = countDraftDispositionCheckboxes(pr.body || '');
      summary
        .addRaw(
          `Pull request is draft; evaluating keepalive checklist disposition (checked=${checkboxCounts.checked}, unchecked=${checkboxCounts.unchecked}).`
        )
        .addEOL();

      const totalChecklistItems = checkboxCounts.checked + checkboxCounts.unchecked;
      const allChecklistWorkComplete = totalChecklistItems > 0 && checkboxCounts.unchecked === 0;
      if (allChecklistWorkComplete) {
        const ready = await markDraftReadyForReview({ github, pr, core, summary });
        if (ready) {
          pr.draft = false;
          await removeLabelsIfPresent({
            github,
            owner,
            repo,
            prNumber,
            labels: [NEEDS_ATTENTION_LABEL, NEEDS_HUMAN_LABEL, PAUSE_LABEL],
            currentLabels,
            core,
            summary,
          });
        } else {
          draftRequiresHuman = true;
          await routeDraftToHuman({
            github,
            owner,
            repo,
            prNumber,
            currentLabels,
            checkboxCounts,
            dispositionReason: 'ready-failed',
            hasDraftDispositionComment,
            core,
            summary,
          });
          addReason('pr-draft-ready-failed');
        }
      } else if (totalChecklistItems === 0) {
        draftRequiresHuman = true;
        await routeDraftToHuman({
          github,
          owner,
          repo,
          prNumber,
          currentLabels,
          checkboxCounts,
          dispositionReason: 'no-checklist',
          hasDraftDispositionComment,
          core,
          summary,
        });
        addReason('pr-draft-no-checklist');
      } else {
        draftRequiresHuman = true;
        await routeDraftToHuman({
          github,
          owner,
          repo,
          prNumber,
          currentLabels,
          checkboxCounts,
          dispositionReason: 'unchecked-items',
          hasDraftDispositionComment,
          core,
          summary,
        });
        addReason('pr-draft-needs-human');
      }
    }
    if (!draftRequiresHuman && currentLabels.has(PAUSE_LABEL)) {
      addReason('keepalive-paused');
      summary.addRaw(`Keepalive paused by ${PAUSE_LABEL} label.`).addEOL();
    }
    if (!draftRequiresHuman && headSha) {
      try {
        const { data: combined } = await github.rest.repos.getCombinedStatusForRef({
          owner,
          repo,
          ref: headSha,
        });
        const statuses = combined?.statuses || [];
        const gateStatuses = statuses.filter((status) => {
          const ctx = (status.context || '').toLowerCase();
          return ctx === 'gate / gate' || ctx === 'gate' || ctx.endsWith('/ gate');
        });
        if (gateStatuses.length) {
          const statusPreview = gateStatuses
            .map((status) => `${String(status.context || 'gate').trim()}=${(status.state || 'unknown').toLowerCase()}`)
            .join(', ');
          summary.addRaw(`Gate status contexts: ${statusPreview}`).addEOL();
        } else if (combined?.state) {
          summary.addRaw(`Gate combined status: ${(combined.state || 'unknown').toLowerCase()}`).addEOL();
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        core.warning(`Unable to evaluate gate status for ${headSha}: ${message}`);
      }
    } else if (!headSha) {
      core.warning('Unable to evaluate gate status: pull request head SHA is unavailable.');
    }

    const normalisedHead = headSha ? headSha.toLowerCase() : '';
    const gateWorkflowIds = ['pr-00-gate.yml', 'pr-00-gate.yaml'];
    let gateRunEvaluated = false;

    if (!draftRequiresHuman && headSha) {
      for (const workflowId of gateWorkflowIds) {
        try {
          const response = await github.rest.actions.listWorkflowRuns({
            owner,
            repo,
            workflow_id: workflowId,
            branch: pr.head?.ref,
            per_page: 20,
            event: 'pull_request',
          });
          const runs = response.data?.workflow_runs || [];
          if (!runs.length) {
            continue;
          }

          const headRun = runs.find((run) => (run.head_sha || '').toLowerCase() === normalisedHead);
          if (!headRun) {
            summary.addRaw(`Gate workflow ${workflowId} has ${runs.length} run(s) but none for head ${headSha.slice(0, 7)}.`).addEOL();
            continue;
          }

          gateRunEvaluated = true;
          const status = (headRun.status || '').toLowerCase();
          const conclusion = (headRun.conclusion || '').toLowerCase();
          summary
            .addRaw(`Gate workflow ${workflowId} on ${headSha.slice(0, 7)} → status=${status || 'unknown'} conclusion=${conclusion || 'none'}`)
            .addEOL();

          if (status !== 'completed') {
            addReason(`gate-run-status:${status || 'unknown'}`);
          } else if (conclusion && conclusion !== 'success') {
            summary.addRaw(`Gate conclusion ${conclusion} detected; continuing keepalive.`).addEOL();
          }

          break;
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          summary.addRaw(`Failed to inspect gate workflow ${workflowId}: ${message}`).addEOL();
        }
      }
    }

    if (!draftRequiresHuman && headSha && !gateRunEvaluated) {
      addReason('gate-run-missing');
    }
  }

  if (reasons.length) {
    const maxRetries = Math.max(1, Number(env.KEEPALIVE_MAX_RETRIES || '5'));
    let skipHistory = { total: 0, highestCount: 0, nonGateCount: 0 };
    try {
      skipHistory = analyseSkipComments(await loadIssueComments());
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      core.warning(`Failed to scan prior keepalive skip comments: ${message}`);
    }

    const priorSkips = skipHistory.total || 0;
    const priorNonGate = skipHistory.nonGateCount || 0;
    const nextSkipCount = Math.max(1, (skipHistory.highestCount || priorSkips) + 1);
    const nonGateReasons = reasons.filter((reason) => !isGateReason(reason));
    const reasonText = reasons.join(', ');

    if (priorSkips >= maxRetries) {
      await finaliseSkip('too-many-failures', `Previous keepalive attempts: ${priorSkips}`, { skipCount: nextSkipCount });
      return;
    }

    if (nonGateReasons.length === 0) {
      await finaliseSkip(reasonText, undefined, { skipCount: nextSkipCount });
      return;
    }

    if (priorNonGate >= maxRetries) {
      await finaliseSkip('too-many-failures', `Previous non-gate keepalive failures: ${priorNonGate}`, { skipCount: nextSkipCount });
      return;
    }

    if (priorNonGate > 0) {
      await finaliseSkip(`previous-failure:${reasonText}`, `Previous keepalive attempts: ${priorSkips}`, { skipCount: nextSkipCount });
      return;
    }

    await finaliseSkip(reasonText, undefined, { skipCount: nextSkipCount });
    return;
  }

  summary.addRaw(`Keepalive ${round || '?'} trace \`${trace}\`: proceed`).addEOL().write();

  setOutputs(true, '');
}

module.exports = {
  runKeepaliveGate: async function ({ core, github: rawGithub, context, env }) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env });
    return runKeepaliveGate({ core, github, context, env });
  },
};
