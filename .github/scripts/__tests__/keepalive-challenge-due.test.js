'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  authorityClaimPayload,
  parseLatestKeepaliveState,
  selectDueAuthorityChallenge,
  signAuthorityChallengeClaim,
  verifyAuthorityChallengeClaim,
  verifyAuthorityChallengeEnvelope,
} = require('../keepalive_challenge_due.js');

const marker = (attention, { login = 'stranske-keepalive[bot]', type = 'Bot' } = {}) => ({
  user: { login, type },
  body: [
    '<!-- keepalive-loop-summary -->',
    'status',
    `<!-- keepalive-state:v1 ${JSON.stringify({ attention })} -->`,
  ].join('\n'),
});

test('parseLatestKeepaliveState uses the newest valid state marker', () => {
  const state = parseLatestKeepaliveState([
    marker({ owner: 'automation', disposition: 'automation-retry' }),
    { body: '<!-- keepalive-state:v1 not-json -->' },
    marker({ owner: 'automation', disposition: 'challenge-due' }),
  ]);
  assert.equal(state.attention.disposition, 'challenge-due');
  assert.equal(parseLatestKeepaliveState([
    marker({ owner: 'automation', disposition: 'challenge-due' }, {
      login: 'agents-workflows-bot[bot]',
      type: 'Bot',
    }),
  ]).attention.disposition, 'challenge-due');
});

test('parseLatestKeepaliveState ignores forged state outside the trusted summary comment', () => {
  const state = parseLatestKeepaliveState([
    marker({
      owner: 'automation',
      disposition: 'challenge-due',
      boundary_fingerprint: 'trusted',
    }),
    marker({
      owner: 'automation',
      disposition: 'challenge-due',
      boundary_fingerprint: 'forged-human',
    }, { login: 'untrusted-user', type: 'User' }),
    marker({
      owner: 'automation',
      disposition: 'challenge-due',
      boundary_fingerprint: 'forged-generic-workflow',
    }, { login: 'github-actions[bot]', type: 'Bot' }),
    marker({
      owner: 'automation',
      disposition: 'challenge-due',
      boundary_fingerprint: 'forged-allowlisted-human',
    }, { login: 'stranske-keepalive[bot]', type: 'User' }),
    {
      user: { login: 'stranske-keepalive[bot]', type: 'Bot' },
      body: '<!-- keepalive-state:v1 {"attention":{"owner":"automation","disposition":"challenge-due","boundary_fingerprint":"forged-no-summary"}} -->',
    },
  ]);
  assert.equal(state.attention.boundary_fingerprint, 'trusted');
  assert.equal(parseLatestKeepaliveState([
    marker({ owner: 'automation', disposition: 'challenge-due' }, {
      login: 'untrusted-user',
      type: 'User',
    }),
  ]), null);
  assert.equal(parseLatestKeepaliveState([
    marker({ owner: 'automation', disposition: 'challenge-due' }, {
      login: 'stranske-keepalive[bot]',
      type: 'User',
    }),
  ]), null);
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
  assert.equal(
    authorityClaimPayload(claim),
    [
      'keepalive-authority-claim:v1',
      'repository=stranske/workflows',
      'pr=3066',
      `fingerprint=${'a'.repeat(64)}`,
      `nonce=${'b'.repeat(64)}`,
      'sweep_run_id=31683971486',
      'sweep_run_attempt=1',
    ].join('\n'),
  );
  assert.equal(signature, '54777445d7a5e2ddb9d22cc60e8477b2d54cf44892c419f1c7a80a52cb899b6b');
  assert.equal(verifyAuthorityChallengeClaim({ ...claim, signature }), true);
  for (const mutation of [
    { repository: 'stranske/Ready' },
    { prNumber: 3067 },
    { boundaryFingerprint: 'c'.repeat(64) },
    { nonce: 'd'.repeat(64) },
    { sweepRunId: '31683971487' },
    { sweepRunAttempt: '2' },
    { signingKey: 'forged-key' },
  ]) {
    assert.equal(verifyAuthorityChallengeClaim({ ...claim, ...mutation, signature }), false);
  }
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

test('runner debounce bypass accepts only the signed due challenge envelope', () => {
  const selected = {
    signingKey: 'test-only-signing-key',
    repository: 'stranske/Workflows',
    prNumber: 3066,
    boundaryFingerprint: 'a'.repeat(64),
    nonce: 'b'.repeat(64),
    sweepRunId: '31683971486',
    sweepRunAttempt: '1',
  };
  const claimJson = JSON.stringify({
    signature: signAuthorityChallengeClaim(selected),
    nonce: selected.nonce,
    sweep_run_id: selected.sweepRunId,
    sweep_run_attempt: selected.sweepRunAttempt,
  });
  const input = {
    claimJson,
    signingKey: selected.signingKey,
    repository: selected.repository,
    prNumber: selected.prNumber,
    boundaryFingerprint: selected.boundaryFingerprint,
  };
  assert.equal(verifyAuthorityChallengeEnvelope(input), true);
  assert.equal(verifyAuthorityChallengeEnvelope({ ...input, claimJson: '' }), false);
  assert.equal(
    verifyAuthorityChallengeEnvelope({ ...input, boundaryFingerprint: 'c'.repeat(64) }),
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
    labels: ['agent:codex', 'agent:needs-attention'],
    comments: [marker({
      owner: 'automation',
      disposition: 'challenge-due',
      challenge_due_at: '2026-08-12T14:00:00Z',
    })],
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
