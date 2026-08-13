'use strict';

const STATE_RE = /<!-- keepalive-state:v1 (\{.*?\}) -->/gs;

function parseLatestKeepaliveState(comments = []) {
  let latest = null;
  for (const comment of comments) {
    const body = String(comment?.body || '');
    for (const match of body.matchAll(STATE_RE)) {
      try {
        latest = JSON.parse(match[1]);
      } catch (_) {
        // Ignore malformed or manually edited state markers and keep looking.
      }
    }
  }
  return latest;
}

function selectDueAuthorityChallenge({ labels = [], comments = [], now = new Date() } = {}) {
  const labelNames = new Set(labels.map((label) => String(label?.name || label).toLowerCase()));
  if (!labelNames.has('agent:needs-attention') || labelNames.has('needs-human')) return null;

  const state = parseLatestKeepaliveState(comments);
  const attention = state?.attention;
  if (
    attention?.owner !== 'automation' ||
    attention?.disposition !== 'challenge-due' ||
    !attention?.challenge_due_at
  ) {
    return null;
  }

  const dueAt = Date.parse(attention.challenge_due_at);
  const nowMs = now instanceof Date ? now.getTime() : Date.parse(String(now));
  if (!Number.isFinite(dueAt) || !Number.isFinite(nowMs) || dueAt > nowMs) return null;

  return {
    dueAt: new Date(dueAt).toISOString(),
    key: String(attention.key || ''),
    nextAction: String(attention.next_action || ''),
  };
}

module.exports = {
  parseLatestKeepaliveState,
  selectDueAuthorityChallenge,
};
