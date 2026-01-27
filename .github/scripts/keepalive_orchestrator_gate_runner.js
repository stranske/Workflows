// Keepalive orchestrator gate runner extracted from the reusable workflow to
// reduce workflow YAML size and avoid GitHub parsing limits. This mirrors the
// previous inline github-script logic.

const {
  analyseSkipComments,
  isGateReason,
} = require('./keepalive_guard_utils.js');
const { evaluateKeepaliveGate } = require('./keepalive_gate.js');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

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

  const agentAlias = preGate.primaryAgent || 'codex';
  const runCap = Number.isFinite(preGate.runCap) ? preGate.runCap : '';
  const activeRuns = Number.isFinite(preGate.activeRuns) ? preGate.activeRuns : '';
  const inflightRuns = '';
  const recentRuns = '';
  const recentWindow = '';
  const runCapDetail = (() => {
    const breakdown = preGate.activeBreakdown || {};
    const orchestratorCount = Number(breakdown.orchestrator ?? breakdown['agents-70-orchestrator.yml'] ?? 0);
    const workerCount = Number(breakdown.worker ?? breakdown['agents-72-codex-belt-worker.yml'] ?? 0);
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
      labelEntries
        .map((entry) => {
          if (!entry) {
            return '';
          }
          if (typeof entry === 'string') {
            return entry.trim().toLowerCase();
          }
          const name = typeof entry?.name === 'string' ? entry.name : '';
          return name.trim().toLowerCase();
        })
        .filter(Boolean)
    );

    if (currentLabels.has('agents:paused')) {
      addReason('keepalive-paused');
      summary.addRaw('Keepalive paused by agents:paused label.').addEOL();
    }

    const requiredLabels = ['agents:keepalive'];
    if (agentAlias) {
      requiredLabels.push(`agent:${agentAlias}`);
    }
    const missingLabels = requiredLabels.filter((label) => !currentLabels.has(label));

    const unresolvedLabels = requiredLabels.filter((label) => !currentLabels.has(label));
    if (unresolvedLabels.length) {
      unresolvedLabels.forEach((label) => addReason(`missing-label:${label}`));
      summary.addRaw(`Missing required keepalive labels: ${unresolvedLabels.join(', ')}`).addEOL();
    }

    headSha = String(pr.head?.sha || '').trim();
    if ((pr.state || '').toLowerCase() !== 'open') {
      addReason('pr-not-open');
    }
    if (!headSha) {
      addReason('missing-head-sha');
    }
    if (pr.draft) {
      addReason('pr-draft');
    } else {
      if (headSha) {
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
      } else {
        core.warning('Unable to evaluate gate status: pull request head SHA is unavailable.');
      }

      const normalisedHead = headSha ? headSha.toLowerCase() : '';
      const gateWorkflowIds = ['pr-00-gate.yml', 'pr-00-gate.yaml'];
      let gateRunEvaluated = false;

      if (headSha) {
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

      if (!gateRunEvaluated) {
        addReason('gate-run-missing');
      }

    }

  }

  if (reasons.length) {
    const maxRetries = Math.max(1, Number(env.KEEPALIVE_MAX_RETRIES || '5'));
    let skipHistory = { total: 0, highestCount: 0, nonGateCount: 0 };
    try {
      const comments = await github.paginate(github.rest.issues.listComments, {
        owner,
        repo,
        issue_number: prNumber,
        per_page: 100,
      });
      skipHistory = analyseSkipComments(comments || []);
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