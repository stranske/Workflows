'use strict';

const crypto = require('node:crypto');

const STATE_RE = /<!-- keepalive-state:v1 (\{.*?\}) -->/gs;
const KEEPALIVE_SUMMARY_MARKER = '<!-- keepalive-loop-summary -->';
const TRUSTED_KEEPALIVE_STATE_AUTHORS = new Set([
  'agents-workflows-bot[bot]',
  'stranske-keepalive[bot]',
]);

function isTrustedKeepaliveStateComment(comment = {}) {
  const body = String(comment?.body || '');
  const login = String(comment?.user?.login || '').trim().toLowerCase();
  const type = String(comment?.user?.type || '').trim().toLowerCase();
  return (
    body.includes(KEEPALIVE_SUMMARY_MARKER) &&
    TRUSTED_KEEPALIVE_STATE_AUTHORS.has(login) &&
    type === 'bot'
  );
}

function authorityClaimPayload({
  repository,
  prNumber,
  boundaryFingerprint,
  nonce,
  sweepRunId,
  sweepRunAttempt,
} = {}) {
  const fields = {
    repository: String(repository || '').toLowerCase(),
    prNumber: String(prNumber || ''),
    boundaryFingerprint: String(boundaryFingerprint || '').toLowerCase(),
    nonce: String(nonce || '').toLowerCase(),
    sweepRunId: String(sweepRunId || ''),
    sweepRunAttempt: String(sweepRunAttempt || ''),
  };
  if (
    !/^[a-z0-9_.-]+\/[a-z0-9_.-]+$/.test(fields.repository) ||
    !/^\d+$/.test(fields.prNumber) ||
    !/^[0-9a-f]{64}$/.test(fields.boundaryFingerprint) ||
    !/^[0-9a-f]{64}$/.test(fields.nonce) ||
    !/^\d+$/.test(fields.sweepRunId) ||
    !/^\d+$/.test(fields.sweepRunAttempt)
  ) {
    return '';
  }
  return [
    'keepalive-authority-claim:v1',
    `repository=${fields.repository}`,
    `pr=${fields.prNumber}`,
    `fingerprint=${fields.boundaryFingerprint}`,
    `nonce=${fields.nonce}`,
    `sweep_run_id=${fields.sweepRunId}`,
    `sweep_run_attempt=${fields.sweepRunAttempt}`,
  ].join('\n');
}

function signAuthorityChallengeClaim({ signingKey, ...claim } = {}) {
  const key = String(signingKey || '');
  const payload = authorityClaimPayload(claim);
  if (!key || !payload) return '';
  return crypto.createHmac('sha256', key).update(payload).digest('hex');
}

function verifyAuthorityChallengeClaim({ signature, ...options } = {}) {
  const supplied = String(signature || '').toLowerCase();
  const expected = signAuthorityChallengeClaim(options);
  if (!/^[0-9a-f]{64}$/.test(supplied) || !expected) return false;
  return crypto.timingSafeEqual(Buffer.from(supplied, 'hex'), Buffer.from(expected, 'hex'));
}

function verifyAuthorityChallengeEnvelope({
  claimJson,
  signingKey,
  repository,
  prNumber,
  boundaryFingerprint,
} = {}) {
  let claim;
  try {
    claim = JSON.parse(String(claimJson || ''));
  } catch (_) {
    return false;
  }
  if (!claim || typeof claim !== 'object' || Array.isArray(claim)) return false;
  return verifyAuthorityChallengeClaim({
    signingKey,
    signature: claim.signature,
    repository,
    prNumber,
    boundaryFingerprint,
    nonce: claim.nonce,
    sweepRunId: claim.sweep_run_id,
    sweepRunAttempt: claim.sweep_run_attempt,
  });
}

function parseLatestKeepaliveState(comments = []) {
  let latest = null;
  for (const comment of comments) {
    if (!isTrustedKeepaliveStateComment(comment)) continue;
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
    boundaryFingerprint: String(attention.boundary_fingerprint || ''),
    nextAction: String(attention.next_action || ''),
  };
}

module.exports = {
  authorityClaimPayload,
  isTrustedKeepaliveStateComment,
  parseLatestKeepaliveState,
  selectDueAuthorityChallenge,
  signAuthorityChallengeClaim,
  verifyAuthorityChallengeClaim,
  verifyAuthorityChallengeEnvelope,
};
