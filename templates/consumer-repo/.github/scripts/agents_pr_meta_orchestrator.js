'use strict';

const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');
const { classifyError, ERROR_CATEGORIES } = require('./error_classifier');

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
 * Handles activation locks and routes admitted comments to the keepalive command handler.
 */

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Check if an error is transient and retryable
 * @param {Error} error - The error to check
 * @returns {boolean}
 */
function isTransientError(error) {
  if (!error) return false;
  return classifyError(error).category === ERROR_CATEGORIES.transient;
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
    branch,
    base,
    round,
    trace,
    agentAlias,
    instructionBody,
    commentUrl,
  } = inputs;

  const token = secrets.AGENTS_AUTOMATION_PAT || secrets.ACTIONS_BOT_PAT || secrets.SERVICE_BOT_PAT;
  if (!token) {
    return { 
      ok: false, 
      reason: 'forbidden-token',
      message: 'Keepalive orchestrator dispatch requires AGENTS_AUTOMATION_PAT, ACTIONS_BOT_PAT, or SERVICE_BOT_PAT.'
    };
  }

  const lockResult = await acquireActivationLock({github, context, core, commentId: Number(commentId)});
  if (lockResult.status === 'lock-held') {
    return { ok: false, reason: 'lock-held' };
  }

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

  return { ok: true, reason: 'ok' };
}

module.exports = {
  acquireActivationLock: async function ({github: rawGithub, context, core, commentId}) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return acquireActivationLock({github, context, core, commentId});
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
