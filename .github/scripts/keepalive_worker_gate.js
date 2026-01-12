'use strict';

const { detectKeepalive } = require('./agents_pr_meta_keepalive.js');
const { loadKeepaliveState } = require('./keepalive_state.js');

function normalise(value) {
  return String(value ?? '').trim();
}

function normaliseLower(value) {
  return normalise(value).toLowerCase();
}

function toBool(value) {
  const lowered = normaliseLower(value);
  if (!lowered) {
    return false;
  }
  return ['true', '1', 'yes', 'y', 'on'].includes(lowered);
}

function parsePositiveInteger(value) {
  const text = normalise(value);
  if (!text) {
    return NaN;
  }
  const parsed = Number.parseInt(text, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return NaN;
  }
  return parsed;
}

function toBigInt(value) {
  if (typeof value === 'bigint') {
    return value;
  }
  const text = normalise(value);
  if (!text) {
    return 0n;
  }
  try {
    return BigInt(text);
  } catch (error) {
    const parsed = Number.parseInt(text, 10);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return 0n;
    }
    return BigInt(parsed);
  }
}

function createStubSummary() {
  const summary = {
    addHeading() {
      return summary;
    },
    addRaw() {
      return summary;
    },
    addTable() {
      return summary;
    },
    addList() {
      return summary;
    },
    addEOL() {
      return summary;
    },
    async write() {
      return undefined;
    },
  };
  return summary;
}

function createStubCore() {
  const noop = () => {};
  return {
    info: noop,
    warning: noop,
    error: noop,
    setOutput: noop,
    summary: createStubSummary(),
  };
}

function buildSafeGithub(github) {
  if (!github || typeof github !== 'object') {
    return github;
  }
  const safe = {
    ...github,
    paginate: github.paginate ? (...args) => github.paginate(...args) : async () => [],
    rest: { ...(github.rest || {}) },
  };
  const reactions = { ...(github.rest?.reactions || {}) };
  reactions.createForIssueComment = async () => ({ status: 200, data: { content: 'hooray' } });
  safe.rest.reactions = reactions;
  return safe;
}

async function detectInstructionComment({ github, context, comment, prNumber, env }) {
  if (!comment) {
    return null;
  }

  const detectionEnv = {
    ALLOWED_LOGINS: normalise(env.ALLOWED_LOGINS) || 'stranske',
    KEEPALIVE_MARKER: normalise(env.KEEPALIVE_MARKER) || '<!-- codex-keepalive-marker -->',
    GATE_OK: 'true',
    GATE_REASON: '',
    GATE_PENDING: 'false',
    ALLOW_REPLAY: 'true',
  };

  const stubCore = createStubCore();
  const safeGithub = buildSafeGithub(github);
  const detectionContext = {
    ...context,
    eventName: 'issue_comment',
    payload: {
      action: 'created',
      issue: { number: prNumber },
      comment,
    },
  };

  const result = await detectKeepalive({ core: stubCore, github: safeGithub, context: detectionContext, env: detectionEnv });
  if (!result) {
    return null;
  }

  const dispatch = normaliseLower(result.dispatch);
  const reason = normaliseLower(result.reason);
  const isValid = dispatch === 'true' || reason === 'duplicate-keepalive' || reason === 'keepalive-detected';
  if (!isValid) {
    return null;
  }

  const commentId = result.comment_id ? toBigInt(result.comment_id) : toBigInt(comment.id);
  const createdAt = comment.created_at ? Date.parse(comment.created_at) : 0;

  return {
    commentId,
    commentIdRaw: result.comment_id || String(comment.id || ''),
    trace: normalise(result.trace || comment.trace || ''),
    round: normalise(result.round || ''),
    url: comment.html_url || '',
    createdAt: Number.isFinite(createdAt) ? createdAt : 0,
  };
}

async function findLatestInstruction({ github, context, owner, repo, prNumber, env }) {
  if (!github?.paginate || !github?.rest?.issues?.listComments) {
    return null;
  }

  let comments = [];
  try {
    comments = await github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: prNumber,
      per_page: 100,
    });
  } catch (error) {
    return null;
  }

  if (!Array.isArray(comments) || comments.length === 0) {
    return null;
  }

  let latest = null;
  for (const comment of comments) {
    const info = await detectInstructionComment({
      github,
      context,
      comment,
      prNumber,
      env,
    });
    if (!info) {
      continue;
    }
    if (!latest) {
      latest = info;
      continue;
    }
    if (info.commentId > latest.commentId) {
      latest = info;
      continue;
    }
    if (info.commentId === latest.commentId && info.createdAt > latest.createdAt) {
      latest = info;
    }
  }

  return latest;
}

function extractLastProcessedState(state) {
  if (!state || typeof state !== 'object') {
    return { commentId: 0n, headSha: '' };
  }
  const source = state.last_instruction && typeof state.last_instruction === 'object' ? state.last_instruction : {};
  return {
    commentId: toBigInt(source.comment_id),
    headSha: normalise(source.head_sha),
  };
}

async function evaluateKeepaliveWorkerGate({ core, github, context, env = process.env }) {
  const keepaliveEnabled = toBool(env.KEEPALIVE || env.KEEPALIVE_ENABLED || env.KEEPALIVE_REQUESTED);
  if (!keepaliveEnabled) {
    return {
      action: 'execute',
      reason: 'keepalive-disabled',
      prNumber: '',
      headSha: '',
      instructionId: '',
      trace: '',
      lastProcessedCommentId: '',
      lastProcessedHeadSha: '',
    };
  }

  const owner = context?.repo?.owner;
  const repo = context?.repo?.repo;
  if (!owner || !repo) {
    throw new Error('Repository context missing owner or repo.');
  }

  const branch = normalise(env.BRANCH || env.WORKER_BRANCH || env.HEAD_BRANCH);
  let prNumber = parsePositiveInteger(env.PR_NUMBER || env.PR || env.PR_NUMBER_HINT);

  if (!Number.isFinite(prNumber) && branch && github?.rest?.pulls?.list) {
    try {
      const { data } = await github.rest.pulls.list({
        owner,
        repo,
        head: `${owner}:${branch}`,
        state: 'open',
        per_page: 1,
      });
      if (Array.isArray(data) && data.length > 0) {
        const candidate = parsePositiveInteger(data[0]?.number);
        if (Number.isFinite(candidate)) {
          prNumber = candidate;
        }
      }
    } catch (error) {
      core?.warning?.(`keepalive worker gate: failed to locate PR for branch ${branch}: ${error.message || error}`);
    }
  }

  if (!Number.isFinite(prNumber)) {
    return {
      action: 'execute',
      reason: 'missing-pr',
      prNumber: '',
      headSha: '',
      instructionId: '',
      trace: '',
      lastProcessedCommentId: '',
      lastProcessedHeadSha: '',
    };
  }

  let headSha = '';
  try {
    const { data } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
    headSha = normalise(data?.head?.sha);
  } catch (error) {
    core?.warning?.(
      `keepalive worker gate: unable to load PR #${prNumber}: ${error instanceof Error ? error.message : String(error)}`,
    );
    return {
      action: 'execute',
      reason: 'pr-fetch-failed',
      prNumber: String(prNumber),
      headSha: '',
      instructionId: '',
      trace: '',
      lastProcessedCommentId: '',
      lastProcessedHeadSha: '',
    };
  }

  const latestInstruction = await findLatestInstruction({ github, context, owner, repo, prNumber, env });
  const stateInfo = await loadKeepaliveState({ github, context, prNumber });
  const lastProcessed = extractLastProcessedState(stateInfo?.state);

  let action = 'execute';
  let reason;

  if (!latestInstruction) {
    reason = 'missing-instruction';
  } else if (lastProcessed.commentId === 0n || !lastProcessed.headSha || !headSha) {
    reason = 'missing-history';
  } else if (latestInstruction.commentId > lastProcessed.commentId) {
    reason = 'new-instruction';
  } else if (headSha !== lastProcessed.headSha) {
    reason = 'head-changed';
  } else {
    action = 'skip';
    reason = 'no-new-instruction-and-head-unchanged';
  }

  if (action === 'skip') {
    core?.info?.(
      `keepalive worker gate: skip (comment_id=${latestInstruction?.commentIdRaw || 'n/a'} head=${headSha || 'unknown'})`,
    );
  } else {
    core?.info?.(
      `keepalive worker gate: execute (reason=${reason} comment_id=${latestInstruction?.commentIdRaw || 'n/a'} head=${
        headSha || 'unknown'
      })`,
    );
  }

  return {
    action,
    reason,
    prNumber: String(prNumber),
    headSha,
    instructionId: latestInstruction?.commentIdRaw || '',
    trace: latestInstruction?.trace || '',
    lastProcessedCommentId: lastProcessed.commentId > 0n ? lastProcessed.commentId.toString() : '',
    lastProcessedHeadSha: lastProcessed.headSha || '',
  };
}

module.exports = {
  evaluateKeepaliveWorkerGate,
};
