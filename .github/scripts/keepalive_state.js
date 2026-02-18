'use strict';

const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

const STATE_MARKER = 'keepalive-state';
const STATE_VERSION = 'v1';
const STATE_REGEX = /<!--\s*keepalive-state(?::([\w.-]+))?\s+(.*?)\s*-->/s;
const LOG_PREFIX = '[keepalive_state]';

function logInfo(message) {
  console.info(`${LOG_PREFIX} ${message}`);
}

function normalise(value) {
  return String(value ?? '').trim();
}

function normaliseLower(value) {
  return normalise(value).toLowerCase();
}

function deepMerge(target, source) {
  const base = target && typeof target === 'object' && !Array.isArray(target) ? { ...target } : {};
  const updates = source && typeof source === 'object' && !Array.isArray(source) ? source : {};
  const result = { ...base };

  for (const [key, value] of Object.entries(updates)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      result[key] = deepMerge(base[key], value);
    } else if (value === undefined) {
      continue;
    } else {
      result[key] = value;
    }
  }

  return result;
}

function toNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function resolveTimestampMs(value) {
  if (value instanceof Date) {
    const parsed = value.getTime();
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  const text = normalise(value);
  if (!text) {
    return null;
  }
  if (/^\d+(\.\d+)?$/.test(text)) {
    const parsedNumber = Number(text);
    return Number.isFinite(parsedNumber) ? parsedNumber : null;
  }
  const parsed = Date.parse(text);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDuration(seconds) {
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;
  const parts = [];
  if (hours > 0) {
    parts.push(`${hours}h`);
  }
  if (hours > 0 || minutes > 0) {
    parts.push(`${minutes}m`);
  }
  parts.push(`${remainingSeconds}s`);
  return parts.join(' ');
}

function calculateElapsedTime(startTime, now) {
  const startMs = resolveTimestampMs(startTime);
  if (!Number.isFinite(startMs)) {
    return '0s';
  }
  const nowMs = resolveTimestampMs(now);
  const resolvedNow = Number.isFinite(nowMs) ? nowMs : Date.now();
  const deltaMs = resolvedNow - startMs;
  if (!Number.isFinite(deltaMs) || deltaMs <= 0) {
    return '0s';
  }
  return formatDuration(deltaMs / 1000);
}

function applyIterationTracking(state) {
  if (!state || typeof state !== 'object') {
    return;
  }
  const nowMs = Date.now();
  const nowIso = new Date(nowMs).toISOString();
  state.current_iteration_at = nowIso;
  const iteration = toNumber(state.iteration, 0);
  if (!state.first_iteration_at && iteration === 1) {
    state.first_iteration_at = nowIso;
  }
}

function formatTimestamp(value = new Date(), { debug = false } = {}) {
  const date = value instanceof Date ? value : new Date(value);
  const iso = date.toISOString();
  if (debug) {
    return iso;
  }
  return iso.replace(/\.\d{3}Z$/, 'Z');
}

function parseStateComment(body) {
  if (typeof body !== 'string' || !body.includes(STATE_MARKER)) {
    return null;
  }
  const match = body.match(STATE_REGEX);
  if (!match) {
    return null;
  }
  const version = normalise(match[1]) || STATE_VERSION;
  const payloadText = normalise(match[2]);
  if (!payloadText) {
    return { version, data: {} };
  }
  try {
    const data = JSON.parse(payloadText);
    if (data && typeof data === 'object') {
      return { version, data };
    }
  } catch (error) {
    // fall through to null
  }
  return { version, data: {} };
}

function hasFiniteNumericValue(value) {
  if (value === null || value === undefined) {
    return false;
  }
  if (typeof value === 'string' && value.trim() === '') {
    return false;
  }
  return Number.isFinite(Number(value));
}

function isLoopState(data) {
  if (!data || typeof data !== 'object') {
    return false;
  }
  if (hasFiniteNumericValue(data.iteration) || hasFiniteNumericValue(data.max_iterations)) {
    return true;
  }
  if (data.tasks && typeof data.tasks === 'object') {
    if (hasFiniteNumericValue(data.tasks.total) || hasFiniteNumericValue(data.tasks.unchecked)) {
      return true;
    }
  }
  if (Object.prototype.hasOwnProperty.call(data, 'keepalive_enabled')) {
    return true;
  }
  if (Object.prototype.hasOwnProperty.call(data, 'autofix_enabled')) {
    return true;
  }
  if (Object.prototype.hasOwnProperty.call(data, 'running')) {
    return true;
  }
  if (data.verification && typeof data.verification === 'object') {
    return true;
  }
  if (data.last_instruction && typeof data.last_instruction === 'object') {
    return true;
  }
  // Delegation state fields (agent:auto mode)
  if (data.current_agent && typeof data.current_agent === 'string') {
    return true;
  }
  if (Array.isArray(data.delegation_log) && data.delegation_log.length > 0) {
    return true;
  }
  if (Array.isArray(data.effectiveness_history) && data.effectiveness_history.length > 0) {
    return true;
  }
  return false;
}

function formatStateComment(data) {
  const payload = data && typeof data === 'object' ? { ...data } : {};
  const version = normalise(payload.version) || STATE_VERSION;
  payload.version = version;
  return `<!-- ${STATE_MARKER}:${version} ${JSON.stringify(payload)} -->`;
}

function upsertStateCommentBody(body, stateComment) {
  const existing = String(body ?? '');
  const marker = String(stateComment ?? '').trim();
  if (!marker) {
    return existing;
  }
  if (!existing.trim()) {
    return marker;
  }
  if (STATE_REGEX.test(existing)) {
    return existing.replace(STATE_REGEX, () => marker);
  }
  const trimmed = existing.trimEnd();
  const separator = trimmed ? '\n\n' : '';
  return `${trimmed}${separator}${marker}`;
}

async function listAllComments({ github, owner, repo, prNumber }) {
  if (!github?.paginate || !github?.rest?.issues?.listComments) {
    return [];
  }
  try {
    const comments = await github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: prNumber,
      per_page: 100,
    });
    return Array.isArray(comments) ? comments : [];
  } catch (error) {
    return [];
  }
}

async function findStateComment({ github, owner, repo, prNumber, trace }) {
  if (!Number.isFinite(prNumber) || prNumber <= 0) {
    return null;
  }
  const comments = await listAllComments({ github, owner, repo, prNumber });
  if (!comments.length) {
    return null;
  }
  const traceNorm = normaliseLower(trace);
  let fallback = null;
  for (let index = comments.length - 1; index >= 0; index -= 1) {
    const comment = comments[index];
    const parsed = parseStateComment(comment?.body);
    if (!parsed) {
      continue;
    }
    const candidate = parsed.data || {};
    if (traceNorm) {
      const candidateTrace = normaliseLower(candidate.trace);
      if (candidateTrace !== traceNorm) {
        continue;
      }
    } else if (!isLoopState(candidate)) {
      if (!fallback) {
        fallback = {
          comment,
          state: candidate,
          version: parsed.version,
        };
      }
      continue;
    }
    return {
      comment,
      state: candidate,
      version: parsed.version,
    };
  }
  return fallback;
}

async function createKeepaliveStateManager({ github: rawGithub, context, prNumber, trace, round }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, env: process.env });
  } catch (error) {
    console.warn(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const owner = context?.repo?.owner;
  const repo = context?.repo?.repo;
  if (!owner || !repo || !Number.isFinite(prNumber) || prNumber <= 0) {
    return {
      state: {},
      commentId: 0,
      commentUrl: '',
      async save() {
        return { state: {}, commentId: 0, commentUrl: '' };
      },
    };
  }

  const existing = await findStateComment({ github, owner, repo, prNumber, trace });
  let state = existing?.state && typeof existing.state === 'object' ? { ...existing.state } : {};
  let commentId = existing?.comment?.id ? Number(existing.comment.id) : 0;
  let commentUrl = existing?.comment?.html_url || '';
  let commentBody = existing?.comment?.body || '';

  const ensureDefaults = () => {
    if (trace && normalise(state.trace) !== trace) {
      state.trace = trace;
    }
    if (round && normalise(state.round) !== normalise(round)) {
      state.round = normalise(round);
    }
    if (Number.isFinite(prNumber)) {
      state.pr_number = Number(prNumber);
    }
    state.version = STATE_VERSION;
  };

  ensureDefaults();
  applyIterationTracking(state);

  const save = async (updates = {}) => {
    state = deepMerge(state, updates);
    ensureDefaults();
    state.iteration_duration = calculateElapsedTime(state.current_iteration_at);
    const body = formatStateComment(state);

    if (commentId) {
      let latestBody = commentBody;
      if (github?.rest?.issues?.getComment) {
        try {
          const response = await github.rest.issues.getComment({
            owner,
            repo,
            comment_id: commentId,
          });
          if (response?.data?.body) {
            latestBody = response.data.body;
          }
        } catch (error) {
          // fall back to cached body if lookup fails
        }
      }
      const updatedBody = upsertStateCommentBody(latestBody, body);
      await github.rest.issues.updateComment({
        owner,
        repo,
        comment_id: commentId,
        body: updatedBody,
      });
      commentBody = updatedBody;
    } else {
      const { data } = await github.rest.issues.createComment({
        owner,
        repo,
        issue_number: prNumber,
        body,
      });
      commentId = data?.id ? Number(data.id) : 0;
      commentUrl = data?.html_url || '';
      commentBody = body;
    }

    return { state: { ...state }, commentId, commentUrl };
  };

  return {
    state: { ...state },
    commentId,
    commentUrl,
    save,
  };
}

async function saveKeepaliveState({ github: rawGithub, context, prNumber, trace, round, updates }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, env: process.env });
  } catch (error) {
    console.warn(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const manager = await createKeepaliveStateManager({ github, context, prNumber, trace, round });
  return manager.save(updates);
}

async function loadKeepaliveState({ github: rawGithub, context, prNumber, trace }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, env: process.env });
  } catch (error) {
    console.warn(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const owner = context?.repo?.owner;
  const repo = context?.repo?.repo;
  if (!owner || !repo || !Number.isFinite(prNumber) || prNumber <= 0) {
    return { state: {}, commentId: 0, commentUrl: '' };
  }
  const existing = await findStateComment({ github, owner, repo, prNumber, trace });
  if (!existing) {
    return { state: {}, commentId: 0, commentUrl: '' };
  }
  const loadedState = existing.state && typeof existing.state === 'object' ? { ...existing.state } : {};
  applyIterationTracking(loadedState);
  return {
    state: loadedState,
    commentId: existing.comment?.id ? Number(existing.comment.id) : 0,
    commentUrl: existing.comment?.html_url || '',
  };
}

async function resetState({ github: rawGithub, context, prNumber, trace, round }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, env: process.env });
  } catch (error) {
    console.warn(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const startTime = Date.now();
  const timestamp = new Date(startTime).toISOString();
  const issueNumber = Number.isFinite(prNumber) ? String(prNumber) : normalise(prNumber);
  logInfo(`resetState starting: ts=${timestamp} issue=${issueNumber || 'unknown'}`);

  let success = false;
  try {
    const owner = context?.repo?.owner;
    const repo = context?.repo?.repo;
    if (
      !owner ||
      !repo ||
      !Number.isFinite(prNumber) ||
      prNumber <= 0 ||
      !github?.rest?.issues?.createComment ||
      !github?.rest?.issues?.updateComment
    ) {
      return { state: {}, commentId: 0, commentUrl: '' };
    }

    const existing = await findStateComment({ github, owner, repo, prNumber, trace });
    const state = {};
    if (trace) {
      state.trace = trace;
    }
    if (round) {
      state.round = normalise(round);
    }
    state.pr_number = Number(prNumber);
    state.version = STATE_VERSION;
    const body = formatStateComment(state);

    if (existing?.comment?.id) {
      let latestBody = existing.comment.body || '';
      if (github?.rest?.issues?.getComment) {
        try {
          const response = await github.rest.issues.getComment({
            owner,
            repo,
            comment_id: existing.comment.id,
          });
          if (response?.data?.body) {
            latestBody = response.data.body;
          }
        } catch (error) {
          // fall back to cached body if lookup fails
        }
      }
      const updatedBody = upsertStateCommentBody(latestBody, body);
      await github.rest.issues.updateComment({
        owner,
        repo,
        comment_id: existing.comment.id,
        body: updatedBody,
      });
      success = true;
      return {
        state: { ...state },
        commentId: Number(existing.comment.id),
        commentUrl: existing.comment.html_url || '',
      };
    }

    const { data } = await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: prNumber,
      body,
    });
    success = true;
    return {
      state: { ...state },
      commentId: data?.id ? Number(data.id) : 0,
      commentUrl: data?.html_url || '',
    };
  } finally {
    const durationMs = Date.now() - startTime;
    logInfo(`resetState finished: status=${success ? 'success' : 'failure'} duration_ms=${durationMs}`);
  }
}

module.exports = {
  createKeepaliveStateManager,
  saveKeepaliveState,
  loadKeepaliveState,
  calculateElapsedTime,
  resetState,
  parseStateComment,
  formatStateComment,
  upsertStateCommentBody,
  deepMerge,
  formatTimestamp,
};
