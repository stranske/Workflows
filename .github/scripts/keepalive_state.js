'use strict';

const STATE_MARKER = 'keepalive-state';
const STATE_VERSION = 'v1';
const STATE_REGEX = /<!--\s*keepalive-state(?::([\w.-]+))?\s+(.*?)\s*-->/s;

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
    }
    return {
      comment,
      state: candidate,
      version: parsed.version,
    };
  }
  return null;
}

async function createKeepaliveStateManager({ github, context, prNumber, trace, round }) {
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

  const save = async (updates = {}) => {
    state = deepMerge(state, updates);
    ensureDefaults();
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

async function saveKeepaliveState({ github, context, prNumber, trace, round, updates }) {
  const manager = await createKeepaliveStateManager({ github, context, prNumber, trace, round });
  return manager.save(updates);
}

async function loadKeepaliveState({ github, context, prNumber, trace }) {
  const owner = context?.repo?.owner;
  const repo = context?.repo?.repo;
  if (!owner || !repo || !Number.isFinite(prNumber) || prNumber <= 0) {
    return { state: {}, commentId: 0, commentUrl: '' };
  }
  const existing = await findStateComment({ github, owner, repo, prNumber, trace });
  if (!existing) {
    return { state: {}, commentId: 0, commentUrl: '' };
  }
  return {
    state: existing.state && typeof existing.state === 'object' ? { ...existing.state } : {},
    commentId: existing.comment?.id ? Number(existing.comment.id) : 0,
    commentUrl: existing.comment?.html_url || '',
  };
}

module.exports = {
  createKeepaliveStateManager,
  saveKeepaliveState,
  loadKeepaliveState,
  parseStateComment,
  formatStateComment,
  upsertStateCommentBody,
  deepMerge,
};
