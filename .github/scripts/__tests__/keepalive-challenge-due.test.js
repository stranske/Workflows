'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  authorityClaimPayload,
  parseLatestKeepaliveState,
  selectDueAuthorityChallenge,
  signAuthorityChallengeClaim,
  verifyAuthorityChallengeClaim,
} = require('../keepalive_challenge_due.js');

const marker = (attention) => ({
  body: `status\n<!-- keepalive-state:v1 ${JSON.stringify({ attention })} -->`,
});

test('parseLatestKeepaliveState uses the newest valid state marker', () => {
  const state = parseLatestKeepaliveState([
    marker({ owner: 'automation', disposition: 'automation-retry' }),
    { body: '<!-- keepalive-state:v1 not-json -->' },
    marker({ owner: 'automation', disposition: 'challenge-due' }),
  ]);
  assert.equal(state.attention.disposition, 'challenge-due');
});

test('authority challenge claims bind the exact sweep selection', () => {
  const claim = {
    signingKey: 'test-only-signing-key',
    repository: 'stranske/Workflows',
    prNumber: 3066,
    boundaryFingerprint: 'a'.repeat(64),
    nonce: 'b'.repeat(64),
    sweepRunId: '31683971486',
    sweepRunAttempt: '1',
  };
  const signature = signAuthorityChallengeClaim(claim);
  assert.match(signature, /^[0-9a-f]{64}$/);
  assert.equal(verifyAuthorityChallengeClaim({ ...claim, signature }), true);
  assert.equal(
    verifyAuthorityChallengeClaim({ ...claim, signature, prNumber: 3067 }),
    false,
  );
  assert.equal(
    verifyAuthorityChallengeClaim({ ...claim, signature, signingKey: 'forged-key' }),
    false,
  );
});

test('authority challenge claims fail closed on incomplete or malformed fields', () => {
  assert.equal(authorityClaimPayload({}), '');
  assert.equal(signAuthorityChallengeClaim({ signingKey: 'key' }), '');
  assert.equal(
    verifyAuthorityChallengeClaim({
      signingKey: 'key',
      signature: 'not-a-signature',
      repository: 'stranske/Workflows',
      prNumber: 3066,
      boundaryFingerprint: 'a'.repeat(64),
      nonce: 'b'.repeat(64),
      sweepRunId: '31683971486',
      sweepRunAttempt: '1',
    }),
    false,
  );
});

test('selectDueAuthorityChallenge schedules an automation-owned due challenge', () => {
  const result = selectDueAuthorityChallenge({
    labels: ['agent:codex', 'agent:needs-attention'],
    comments: [marker({
      owner: 'automation',
      disposition: 'challenge-due',
      challenge_due_at: '2026-08-12T12:00:00Z',
      key: 'auth',
      boundary_fingerprint: 'fingerprint-auth',
      next_action: 'reproduce access failure',
    })],
    now: new Date('2026-08-12T13:00:00Z'),
  });
  assert.deepEqual(result, {
    dueAt: '2026-08-12T12:00:00.000Z',
    key: 'auth',
    boundaryFingerprint: 'fingerprint-auth',
    nextAction: 'reproduce access failure',
  });
});

test('scheduled sweep forces only an explicitly due authority challenge', () => {
  const due = selectDueAuthorityChallenge({
    labels: ['agent:codex', 'agent:needs-attention'],
    comments: [marker({
      owner: 'automation',
      disposition: 'challenge-due',
      challenge_due_at: '2026-08-12T12:00:00Z',
    })],
    now: new Date('2026-08-12T13:00:00Z'),
  });
  const ordinary = selectDueAuthorityChallenge({
    labels: ['agent:codex'],
    comments: [],
    now: new Date('2026-08-12T13:00:00Z'),
  });
  assert.equal(String(Boolean(due)), 'true');
  assert.equal(String(Boolean(ordinary)), 'false');
});

test('selectDueAuthorityChallenge preserves confirmed human blockers', () => {
  const result = selectDueAuthorityChallenge({
    labels: ['agent:needs-attention', 'needs-human'],
    comments: [marker({
      owner: 'automation',
      disposition: 'challenge-due',
      challenge_due_at: '2026-08-12T12:00:00Z',
    })],
    now: new Date('2026-08-12T13:00:00Z'),
  });
  assert.equal(result, null);
});

test('selectDueAuthorityChallenge rejects future and unowned claims', () => {
  const future = selectDueAuthorityChallenge({
    labels: ['agent:needs-attention'],
    comments: [marker({
      owner: 'automation',
      disposition: 'challenge-due',
      challenge_due_at: '2026-08-12T14:00:00Z',
    })],
    now: new Date('2026-08-12T13:00:00Z'),
  });
  const human = selectDueAuthorityChallenge({
    labels: ['agent:needs-attention'],
    comments: [marker({
      owner: 'human',
      disposition: 'challenge-due',
      challenge_due_at: '2026-08-12T12:00:00Z',
    })],
    now: new Date('2026-08-12T13:00:00Z'),
  });
  assert.equal(future, null);
  assert.equal(human, null);
});
