'use strict';

const fs = require('fs');

function trim(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function isRateLimitError(error) {
  if (!error) {
    return false;
  }
  const status = error.status || error?.response?.status;
  if (status !== 403) {
    return false;
  }
  const message = String(error.message || error?.response?.data?.message || '').toLowerCase();
  return message.includes('rate limit') || message.includes('ratelimit');
}

function isPullRequestEvent(context) {
  return context?.eventName === 'pull_request';
}

async function listIssueLabels({ github, owner, repo, issue_number, core }) {
  if (!github?.rest?.issues?.listLabelsOnIssue) {
    return [];
  }
  try {
    if (typeof github.paginate === 'function') {
      return await github.paginate(github.rest.issues.listLabelsOnIssue, {
        owner,
        repo,
        issue_number,
        per_page: 100,
      });
    }
    const response = await github.rest.issues.listLabelsOnIssue({
      owner,
      repo,
      issue_number,
      per_page: 100,
    });
    return Array.isArray(response?.data) ? response.data : [];
  } catch (error) {
    if (isRateLimitError(error)) {
      warn(core, 'Rate limit while fetching labels; skipping agent label check.');
      return [];
    }
    throw error;
  }
}

async function hasAgentLabel({ github, owner, repo, issue_number, core }) {
  const labels = await listIssueLabels({ github, owner, repo, issue_number, core });
  return labels.some((label) => {
    const name = typeof label === 'string' ? label : label?.name;
    return String(name || '').trim().toLowerCase().startsWith('agent:');
  });
}

function selectMarkerComment(comments, { marker, baseMessage }) {
  const normalizedMarker = marker || '';
  const normalizedBase = trim(baseMessage || '');
  let target = null;
  const duplicates = [];

  for (const comment of comments || []) {
    if (!comment || typeof comment.body !== 'string') {
      continue;
    }
    const body = comment.body;
    const trimmed = trim(body);
    const hasMarker = normalizedMarker && body.includes(normalizedMarker);
    const isLegacy = normalizedBase && (trimmed === normalizedBase || trimmed.startsWith(normalizedBase));
    if (!hasMarker && !isLegacy) {
      continue;
    }
    if (!target) {
      target = { comment, hasMarker };
      continue;
    }
    if (!target.hasMarker && hasMarker) {
      duplicates.push(target.comment);
      target = { comment, hasMarker };
    } else {
      duplicates.push(comment);
    }
  }

  return {
    target: target ? target.comment : null,
    targetHasMarker: Boolean(target?.hasMarker),
    duplicates,
  };
}

function info(core, message) {
  if (core && typeof core.info === 'function') {
    core.info(message);
  } else {
    console.log(message);
  }
}

function warn(core, message) {
  if (core && typeof core.warning === 'function') {
    core.warning(message);
  } else {
    console.warn(message);
  }
}

async function ensureMarkerComment({ github, context, core, commentBody, marker, baseMessage }) {
  if (!isPullRequestEvent(context)) {
    info(core, 'Not a pull_request event; skipping comment management.');
    return;
  }

  const body = trim(commentBody);
  if (!body) {
    const message = 'Docs-only comment body is missing.';
    if (core) {
      core.setFailed(message);
    }
    throw new Error(message);
  }

  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const issue_number = context.payload.pull_request.number;

  let comments;
  try {
    comments = await github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number,
      per_page: 100,
    });
  } catch (error) {
    if (isRateLimitError(error)) {
      warn(core, 'Rate limit while fetching existing comments; skipping docs-only comment management.');
      return;
    }
    throw error;
  }

  const { target, duplicates } = selectMarkerComment(comments, { marker, baseMessage });
  const desired = body;
  let targetId = target?.id;

  if (targetId) {
    const current = trim(target.body);
    if (current === desired) {
      info(core, `Existing docs-only comment ${targetId} is up to date.`);
    } else {
      try {
        await github.rest.issues.updateComment({ owner, repo, comment_id: targetId, body: desired });
        info(core, `Updated docs-only comment ${targetId}.`);
      } catch (error) {
        if (isRateLimitError(error)) {
          warn(core, `Rate limit while updating docs-only comment ${targetId}; leaving existing content.`);
          return;
        }
        throw error;
      }
    }
  } else {
    try {
      const created = await github.rest.issues.createComment({ owner, repo, issue_number, body: desired });
      targetId = created?.data?.id;
      info(core, `Created docs-only comment ${targetId}.`);
    } catch (error) {
      if (isRateLimitError(error)) {
        warn(core, 'Rate limit while creating docs-only comment; skipping.');
        return;
      }
      throw error;
    }
  }

  for (const duplicate of duplicates) {
    if (!duplicate || duplicate.id === targetId) {
      continue;
    }
    try {
      await github.rest.issues.deleteComment({ owner, repo, comment_id: duplicate.id });
      info(core, `Removed duplicate docs-only comment ${duplicate.id}.`);
    } catch (error) {
      if (isRateLimitError(error)) {
        warn(core, `Rate limit while deleting duplicate comment ${duplicate.id}; leaving remaining duplicates.`);
        break;
      }
      throw error;
    }
  }
}

async function removeMarkerComments({ github, context, core, marker, baseMessages = [] }) {
  if (!isPullRequestEvent(context)) {
    info(core, 'Not a pull_request event; nothing to clean up.');
    return;
  }

  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const issue_number = context.payload.pull_request.number;
  const legacyBodies = new Set(baseMessages.map(value => trim(value)).filter(Boolean));

  let comments;
  try {
    comments = await github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number,
      per_page: 100,
    });
  } catch (error) {
    if (isRateLimitError(error)) {
      warn(core, 'Rate limit while fetching comments for cleanup; skipping.');
      return;
    }
    throw error;
  }

  const targets = comments.filter(comment => {
    if (!comment || typeof comment.body !== 'string') {
      return false;
    }
    if (marker && comment.body.includes(marker)) {
      return true;
    }
    const trimmed = trim(comment.body);
    if (legacyBodies.has(trimmed)) {
      return true;
    }
    if (legacyBodies.size > 0) {
      for (const legacy of legacyBodies) {
        if (trimmed.startsWith(legacy)) {
          return true;
        }
      }
    }
    return false;
  });

  if (!targets.length) {
    info(core, 'No docs-only fast-pass comment found to remove.');
    return;
  }

  for (const comment of targets) {
    try {
      await github.rest.issues.deleteComment({ owner, repo, comment_id: comment.id });
      info(core, `Removed docs-only fast-pass comment ${comment.id}.`);
    } catch (error) {
      if (isRateLimitError(error)) {
        warn(core, `Rate limit while removing docs-only comment ${comment.id}; aborting further removals.`);
        break;
      }
      throw error;
    }
  }
}

function extractAnchoredMetadata(body, anchorPattern) {
  const pattern = anchorPattern instanceof RegExp
    ? anchorPattern
    : new RegExp(anchorPattern || '', 'i');
  const match = typeof body === 'string' ? body.match(pattern) : null;
  if (!match) {
    return null;
  }
  const content = match[1] || '';
  const prMatch = content.match(/pr=([0-9]+)/i);
  const headMatch = content.match(/head=([0-9a-f]+)/i);
  return {
    raw: match[0],
    pr: prMatch ? prMatch[1] : null,
    head: headMatch ? headMatch[1] : null,
  };
}

function findAnchoredComment(comments, { anchorPattern, fallbackMarker, targetAnchor }) {
  const marker = fallbackMarker || '';
  if (targetAnchor) {
    const anchored = comments.find(comment => {
      const info = extractAnchoredMetadata(comment?.body, anchorPattern);
      if (!info) {
        return false;
      }
      if (targetAnchor.pr && info.pr && info.pr !== targetAnchor.pr) {
        return false;
      }
      if (targetAnchor.head && info.head && info.head !== targetAnchor.head) {
        return false;
      }
      return true;
    });
    if (anchored) {
      return anchored;
    }
  }

  if (marker) {
    return comments.find(comment => typeof comment?.body === 'string' && comment.body.includes(marker)) || null;
  }

  return null;
}

async function upsertAnchoredComment({
  github,
  context,
  core,
  prNumber,
  commentPath,
  body,
  anchorPattern = /<!--\s*maint-46-post-ci:([^>]*)-->/i,
  fallbackMarker = '<!-- maint-46-post-ci:',
}) {
  let commentBody = body;
  if (!commentBody && commentPath) {
    try {
      commentBody = fs.readFileSync(commentPath, 'utf8');
    } catch (error) {
      warn(core, `Failed to read comment body from ${commentPath}: ${error?.message || error}`);
    }
  }
  commentBody = trim(commentBody);
  if (!commentBody) {
    warn(core, 'Comment body empty; skipping update.');
    return;
  }

  let pr = Number(prNumber || 0);
  if (!Number.isFinite(pr) || pr <= 0) {
    const anchorMeta = extractAnchoredMetadata(commentBody, anchorPattern);
    if (anchorMeta?.pr) {
      const parsed = Number(anchorMeta.pr);
      if (Number.isFinite(parsed) && parsed > 0) {
        pr = parsed;
      }
    }
  }

  if (!Number.isFinite(pr) || pr <= 0) {
    warn(core, 'PR number missing; skipping comment update.');
    return;
  }

  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const anchorSource = anchorPattern instanceof RegExp ? anchorPattern.source : String(anchorPattern || '');
  const gateProbe = `${anchorSource} ${fallbackMarker || ''} ${commentBody}`.toLowerCase();
  const isGateSummary = gateProbe.includes('gate-summary');

  if (isGateSummary) {
    const agentLabel = await hasAgentLabel({ github, owner, repo, issue_number: pr, core });
    if (agentLabel) {
      info(core, 'Skipping gate summary comment for agent-labeled PR.');
      return;
    }
  }

  let comments;
  try {
    comments = await github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: pr,
      per_page: 100,
    });
  } catch (error) {
    if (isRateLimitError(error)) {
      warn(core, 'Rate limit while fetching comments for consolidated status; skipping update.');
      return;
    }
    throw error;
  }

  const targetAnchor = extractAnchoredMetadata(commentBody, anchorPattern);
  const existing = findAnchoredComment(comments, { anchorPattern, fallbackMarker, targetAnchor });

  if (existing) {
    try {
      await github.rest.issues.updateComment({ owner, repo, comment_id: existing.id, body: commentBody });
      info(core, 'Updated existing consolidated status comment.');
    } catch (error) {
      if (isRateLimitError(error)) {
        warn(core, 'Rate limit while updating consolidated status comment; leaving existing content.');
        return;
      }
      throw error;
    }
  } else {
    try {
      await github.rest.issues.createComment({ owner, repo, issue_number: pr, body: commentBody });
      info(core, 'Created consolidated status comment.');
    } catch (error) {
      if (isRateLimitError(error)) {
        warn(core, 'Rate limit while creating consolidated status comment; skipping.');
        return;
      }
      throw error;
    }
  }
}

module.exports = {
  selectMarkerComment,
  ensureMarkerComment,
  removeMarkerComments,
  extractAnchoredMetadata,
  findAnchoredComment,
  upsertAnchoredComment,
};
