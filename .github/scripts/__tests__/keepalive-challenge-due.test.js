'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  parseLatestKeepaliveState,
  selectDueAuthorityChallenge,
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

test('selectDueAuthorityChallenge schedules an automation-owned due challenge', () => {
  const result = selectDueAuthorityChallenge({
    labels: ['agent:codex', 'agent:needs-attention'],
    comments: [marker({
      owner: 'automation',
      disposition: 'challenge-due',
      challenge_due_at: '2026-08-12T12:00:00Z',
      key: 'auth',
      next_action: 'reproduce access failure',
    })],
    now: new Date('2026-08-12T13:00:00Z'),
  });
  assert.deepEqual(result, {
    dueAt: '2026-08-12T12:00:00.000Z',
    key: 'auth',
    nextAction: 'reproduce access failure',
  });
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
