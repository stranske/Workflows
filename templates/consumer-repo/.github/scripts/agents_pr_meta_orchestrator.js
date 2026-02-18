'use strict';

const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

// Resolve default agent from registry
let _defaultAgent = 'codex';
try {
  const { loadAgentRegistry } = require('./agent_registry.js');
  _defaultAgent = loadAgentRegistry().default_agent || 'codex';
} catch (_) { /* registry not available */ }

/**
 * agents_pr_meta_orchestrator.js
 *
 * External script for keepalive orchestrator functionality in agents-pr-meta workflow.
 * Handles token selection, activation locks, snapshot runs, dispatch, and confirmation.
 */

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Check if an error is transient and retryable
 * @param {Error} error - The error to check
 * @returns {boolean}
 */
function isTransientError(error) {
  if (!error) return false;
  const status = Number(error?.status || 0);
  const message = String(error?.message || '').toLowerCase();
  // Secondary rate limit (429), server errors (5xx) are always retryable
  if (status === 429 || status >= 500) return true;
  // 403 is only retryable if message indicates rate limit or abuse detection
  if (status === 403 && (message.includes('rate limit') || message.includes('abuse detection'))) return true;
  // Check for rate limit keywords in any error message
  if (message.includes('rate limit') || message.includes('abuse detection') || message.includes('timeout')) return true;
  return false;
}

/**
 * Acquire activation lock by adding rocket reaction
 */
async function acquireActivationLock({github, context, core, commentId}) {
  if (!Number.isFinite(commentId) || commentId <= 0) {
    return { status: 'missing', reason: 'no-activation-found' };
  }

  const { owner, repo } = context.repo;
  try {
    await github.rest.reactions.createForIssueComment({
      owner,
      repo,
      comment_id: commentId,
      content: 'rocket',
    });
    core.info(`Activation lock applied to comment ${commentId}.`);
    return { status: 'ok', reason: 'ok' };
  } catch (error) {
    const status = Number(error?.status || 0);
    const message = error instanceof Error ? error.message : String(error);
    if (status === 409) {
      core.info(`Activation lock already present on comment ${commentId}.`);
    } else {
      core.warning(`Failed to add activation lock to comment ${commentId}: ${message}`);
    }
    return { status: 'lock-held', reason: 'lock-held' };
  }
}

/**
 * Snapshot current orchestrator runs for deduplication
 */
async function snapshotOrchestratorRuns({github, context, core, prNumber, trace}) {
  const { owner, repo } = context.repo;
  const response = await github.rest.actions.listWorkflowRuns({
    owner,
    repo,
    workflow_id: 'agents-70-orchestrator.yml',
    event: 'workflow_dispatch',
    per_page: 50,
  });
  const runs = Array.isArray(response.data?.workflow_runs) ? response.data.workflow_runs : [];
  const ids = runs.map((run) => Number(run?.id)).filter((value) => Number.isFinite(value));
  core.info(`Snapshot captured ${ids.length} workflow_dispatch runs for agents-70-orchestrator.yml.`);
  return {
    ids: JSON.stringify(ids),
    timestamp: new Date().toISOString(),
    pr: prNumber > 0 ? String(prNumber) : '',
    trace: trace || '',
  };
}

/**
 * Dispatch Agents 70 orchestrator for keepalive with retry for transient errors
 */
async function dispatchOrchestrator({github, context, core, inputs}) {
  const { issue, prNumber, branch, base, round, trace, instructionBody } = inputs;
  const { owner, repo } = context.repo;
  const workflowId = 'agents-70-orchestrator.yml';
  const ref = context.payload?.repository?.default_branch || 'main';

  const isScopeError = (error) => {
    if (!error) return false;
    const message = String(error?.message || error || '').toLowerCase();
    return message.includes('resource not accessible');
  };
  const params = { enable_keepalive: true };
  if (Number.isFinite(issue) && issue > 0) {
    params.dispatcher_force_issue = String(issue);
  }
  if (branch) {
    params.keepalive_branch = branch;
  }
  if (base) {
    params.keepalive_base = base;
  }

  const roundValue = Number.isFinite(round) && round > 0 ? String(round) : '';
  const prValue = Number.isFinite(prNumber) && prNumber > 0 ? String(prNumber) : '';

  const options = {
    keepalive_trace: trace,
    round: roundValue,
    pr: prValue,
  };
  if (instructionBody) {
    options.keepalive_instruction = instructionBody;
  }

  const dispatchPayload = {
    owner,
    repo,
    workflow_id: workflowId,
    ref,
    inputs: {
      keepalive_enabled: 'true',
      params_json: JSON.stringify(params),
      options_json: JSON.stringify(options),
      dry_run: 'false',
      pr_number: prValue,
    },
  };

  const dispatchWithClient = async (client, label) => {
    const maxRetries = 3;
    let lastError;
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        await client.rest.actions.createWorkflowDispatch(dispatchPayload);
        core.info(`Dispatched ${workflowId} (${label}) for keepalive (pr=${prValue || 'n/a'}, trace=${trace || '-'}).`);
        return { ok: true, reason: 'ok' };
      } catch (error) {
        lastError = error;
        const message = error instanceof Error ? error.message : String(error);
        if (isTransientError(error) && attempt < maxRetries) {
          const delayMs = 1000 * Math.pow(2, attempt - 1); // Exponential backoff: 1s, 2s, 4s
          core.warning(`Dispatch attempt ${attempt}/${maxRetries} (${label}) failed (${message}), retrying in ${delayMs}ms...`);
          await sleep(delayMs);
          continue;
        }
        core.error(`Failed to dispatch ${workflowId} after ${attempt} attempts (${label}): ${message}`);
        return { ok: false, reason: 'dispatch-error', error };
      }
    }
    const message = lastError instanceof Error ? lastError.message : String(lastError || 'unknown error');
    core.error(`Failed to dispatch ${workflowId} after ${maxRetries} attempts (${label}): ${message}`);
    return { ok: false, reason: 'dispatch-error', error: lastError || message };
  };

  const primaryResult = await dispatchWithClient(github, 'primary-token');
  if (!primaryResult.ok && isScopeError(primaryResult.error) && process.env.GITHUB_TOKEN) {
    try {
      const FallbackOctokit = github.constructor;
      if (FallbackOctokit) {
        const fallbackClient = new FallbackOctokit({ auth: process.env.GITHUB_TOKEN });
        core.info('Retrying orchestrator dispatch with default GITHUB_TOKEN due to PAT scope limitations.');
        return await dispatchWithClient(fallbackClient, 'github-token-fallback');
      }
    } catch (fallbackError) {
      const message = fallbackError instanceof Error ? fallbackError.message : String(fallbackError);
      core.warning(`Fallback dispatch setup failed: ${message}`);
    }
  }

  return primaryResult;
}

/**
 * Confirm orchestrator dispatch by polling for new run
 */
async function confirmDispatch({github, context, core, baselineIds, baselineTimestamp, prNumber, trace}) {
  const parseIds = (value) => {
    if (!value) return new Set();
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) {
        return new Set(parsed.map((entry) => Number(entry)).filter((entry) => Number.isFinite(entry)));
      }
    } catch (error) {
      core.warning(`Unable to parse baseline ids: ${error.message || error}`);
    }
    return new Set();
  };

  const baseline = parseIds(baselineIds);
  const { owner, repo } = context.repo;
  let baselineDate = null;
  if (baselineTimestamp) {
    const tmpDate = new Date(baselineTimestamp);
    if (Number.isNaN(tmpDate.getTime())) {
      core.warning(`Invalid baselineTimestamp "${baselineTimestamp}" provided; ignoring baseline filter.`);
    } else {
      baselineDate = tmpDate;
    }
  }

  const createdAfterBaseline = (run) => {
    if (!baselineDate) return true;
    const createdRaw = run?.created_at || run?.createdAt;
    if (!createdRaw) return true;
    const created = new Date(createdRaw);
    if (Number.isNaN(created.getTime())) {
      core.warning(`Invalid run created_at timestamp "${createdRaw}" for run id ${run?.id ?? 'unknown'}; treating as not after baseline.`);
      return false;
    }
    return created >= baselineDate;
  };

  const matches = (run) => {
    if (!run) return false;
    const runId = Number(run.id);
    if (baseline.has(runId)) return false;
    if (!createdAfterBaseline(run)) return false;
    
    if (prNumber > 0) {
      const concurrency = String(run.concurrency || '');
      if (concurrency.includes(`pr-${prNumber}-`)) return true;
      const pulls = Array.isArray(run.pull_requests) ? run.pull_requests : [];
      if (pulls.some((pull) => Number(pull?.number) === prNumber)) return true;
    }
    if (trace) {
      const candidates = [run.name, run.display_title, run.head_branch, run.head_sha];
      if (candidates.some((value) => typeof value === 'string' && value.includes(trace))) return true;
    }
    // Fallback: accept any new workflow_dispatch run created after the snapshot
    return true;
  };

  const poll = async () => {
    const response = await github.rest.actions.listWorkflowRuns({
      owner,
      repo,
      workflow_id: 'agents-70-orchestrator.yml',
      event: 'workflow_dispatch',
      per_page: 50,
    });
    const runs = Array.isArray(response.data?.workflow_runs) ? response.data.workflow_runs : [];
    return runs.find((run) => matches(run)) || null;
  };

  const attempts = 6;
  const delayMs = 5000;
  let matched = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    matched = await poll();
    if (matched) break;
    await sleep(delayMs);
  }

  if (!matched) {
    return { confirmed: false, reason: 'dispatch-unconfirmed' };
  }

  const runId = String(matched.id);
  const runUrl = matched.html_url || '';
  core.info(`DISPATCH_CONFIRMED: run ${runId}${runUrl ? ` (${runUrl})` : ''}`);
  return { confirmed: true, reason: 'ok', runId, runUrl };
}

/**
 * Dispatch agent keepalive command via repository_dispatch
 */
async function dispatchKeepaliveCommand({github, context, core, inputs}) {
  const { prNumber, base, head, round, trace, commentId, commentUrl, agentAlias, instructionBody } = inputs;
  const { owner, repo } = context.repo;

  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    throw new Error('Unable to determine pull request number for keepalive dispatch.');
  }

  let resolvedBase = base;
  let resolvedHead = head;

  if (!resolvedBase || !resolvedHead) {
    const pull = await github.rest.pulls.get({
      owner,
      repo,
      pull_number: prNumber,
    });
    resolvedBase = resolvedBase || pull.data.base?.ref || '';
    resolvedHead = resolvedHead || pull.data.head?.ref || '';
  }

  if (!resolvedBase || !resolvedHead) {
    throw new Error('Unable to determine pull request base/head branches.');
  }

  if (!commentId || !commentUrl) {
    throw new Error('Comment metadata missing id or url.');
  }

  if (!instructionBody) {
    throw new Error('Instruction body unavailable for keepalive dispatch.');
  }

  const clientPayload = {
    issue: prNumber,
    base: resolvedBase,
    head: resolvedHead,
    agent: agentAlias || _defaultAgent,
    instruction_body: instructionBody,
    meta: {
      comment_id: commentId,
      comment_url: commentUrl,
      round,
      trace,
    },
    quiet: true,
    reply: 'none',
  };

  // Retry dispatch with exponential backoff for transient errors
  const maxRetries = 3;
  let lastError;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      await github.rest.repos.createDispatchEvent({
        owner,
        repo,
        // API contract: event type matched by dispatch handlers in consumers
        event_type: 'codex-pr-comment-command',
        client_payload: clientPayload,
      });
      core.info(`repository_dispatch emitted for PR #${prNumber} (comment ${commentId}).`);
      return; // Success
    } catch (err) {
      lastError = err;
      const message = err instanceof Error ? err.message : String(err);
      if (isTransientError(err) && attempt < maxRetries) {
        const delay = 1000 * Math.pow(2, attempt - 1); // Exponential backoff: 1s, 2s, 4s
        core.warning(`Dispatch attempt ${attempt}/${maxRetries} failed (${message}), retrying in ${delay}ms...`);
        await sleep(delay);
      } else {
        break;
      }
    }
  }
  throw lastError;
}

/**
 * Run the full keepalive orchestrator flow
 */
async function runKeepaliveOrchestrator({github, context, core, inputs, secrets}) {
  const {
    commentId,
    prNumber,
    issue,
    branch,
    base,
    round,
    trace,
    agentAlias,
    instructionBody,
    commentUrl,
  } = inputs;

  // Step 1: Select token
  const token = secrets.AGENTS_AUTOMATION_PAT || secrets.ACTIONS_BOT_PAT || secrets.SERVICE_BOT_PAT;
  if (!token) {
    return { 
      ok: false, 
      reason: 'forbidden-token',
      message: 'Keepalive orchestrator dispatch requires AGENTS_AUTOMATION_PAT, ACTIONS_BOT_PAT, or SERVICE_BOT_PAT.'
    };
  }

  // Step 2: Acquire activation lock
  const lockResult = await acquireActivationLock({github, context, core, commentId: Number(commentId)});
  if (lockResult.status === 'lock-held') {
    return { ok: false, reason: 'lock-held' };
  }

  // Step 3: Snapshot runs
  const snapshot = await snapshotOrchestratorRuns({
    github, context, core, 
    prNumber: Number(prNumber), 
    trace
  });

  // Step 4: Dispatch orchestrator
  const dispatchResult = await dispatchOrchestrator({
    github, context, core,
    inputs: {
      issue: Number(issue),
      prNumber: Number(prNumber),
      branch,
      base,
      round: Number(round),
      trace,
      instructionBody,
    }
  });
  
  if (!dispatchResult.ok) {
    return { ok: false, reason: dispatchResult.reason };
  }

  // Step 5: Confirm dispatch
  const confirmResult = await confirmDispatch({
    github, context, core,
    baselineIds: snapshot.ids,
    baselineTimestamp: snapshot.timestamp,
    prNumber: Number(prNumber),
    trace,
  });

  if (!confirmResult.confirmed) {
    return { ok: false, reason: confirmResult.reason };
  }

  // Step 6: Dispatch keepalive command
  try {
    await dispatchKeepaliveCommand({
      github, context, core,
      inputs: {
        prNumber: Number(prNumber),
        base,
        head: branch,
        round,
        trace,
        commentId,
        commentUrl,
        agentAlias,
        instructionBody,
      }
    });
  } catch (error) {
    core.error(`Failed to dispatch keepalive command: ${error.message}`);
    return { ok: false, reason: 'dispatch-command-error' };
  }

  return { 
    ok: true, 
    reason: 'ok',
    runId: confirmResult.runId,
    runUrl: confirmResult.runUrl,
  };
}

module.exports = {
  acquireActivationLock: async function ({github: rawGithub, context, core, commentId}) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return acquireActivationLock({github, context, core, commentId});
  },
  snapshotOrchestratorRuns: async function ({github: rawGithub, context, core, prNumber, trace}) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return snapshotOrchestratorRuns({github, context, core, prNumber, trace});
  },
  dispatchOrchestrator: async function ({github: rawGithub, context, core, inputs}) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return dispatchOrchestrator({github, context, core, inputs});
  },
  confirmDispatch: async function ({github: rawGithub, context, core, baselineIds, baselineTimestamp, prNumber, trace}) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return confirmDispatch({github, context, core, baselineIds, baselineTimestamp, prNumber, trace});
  },
  dispatchKeepaliveCommand: async function ({github: rawGithub, context, core, inputs}) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return dispatchKeepaliveCommand({github, context, core, inputs});
  },
  runKeepaliveOrchestrator: async function ({github: rawGithub, context, core, inputs, secrets}) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return runKeepaliveOrchestrator({github, context, core, inputs, secrets});
  },
};
