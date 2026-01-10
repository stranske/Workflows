'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  calculateElapsedTime,
  createKeepaliveStateManager,
  loadKeepaliveState,
} = require('../.github/scripts/keepalive_state.js');

test('calculateElapsedTime returns 0s for null input', () => {
  assert.equal(calculateElapsedTime(null), '0s');
});

test('calculateElapsedTime returns 0s for undefined input', () => {
  assert.equal(calculateElapsedTime(undefined), '0s');
});

test('calculateElapsedTime returns 0s for invalid date strings', () => {
  assert.equal(calculateElapsedTime('invalid'), '0s');
});

test('calculateElapsedTime returns 0s for invalid Date objects', () => {
  const invalidDate = new Date('invalid');
  assert.equal(calculateElapsedTime(invalidDate), '0s');
});

test('calculateElapsedTime returns 0s for NaN inputs', () => {
  assert.equal(calculateElapsedTime(Number.NaN), '0s');
});

test('calculateElapsedTime formats minutes and seconds', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = new Date(now - (5 * 60 * 1000 + 23 * 1000)).toISOString();
    assert.equal(calculateElapsedTime(start), '5m 23s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime matches the documented example', () => {
  const realNow = Date.now;
  const start = '2026-01-10T20:00:00Z';
  const now = Date.parse('2026-01-10T20:05:23Z');
  Date.now = () => now;
  try {
    assert.equal(calculateElapsedTime(start), '5m 23s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime handles edge cases', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const futureStart = new Date(now + 60 * 1000).toISOString();
    assert.equal(calculateElapsedTime(futureStart), '0s');
    const start = new Date(now - (2 * 3600 * 1000 + 3 * 60 * 1000 + 4 * 1000)).toISOString();
    assert.equal(calculateElapsedTime(start), '2h 3m 4s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime supports Date and number inputs', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const startDate = new Date(now - 9 * 1000);
    assert.equal(calculateElapsedTime(startDate), '9s');
    assert.equal(calculateElapsedTime(now - 12 * 1000), '12s');
  } finally {
    Date.now = realNow;
  }
});

test('loadKeepaliveState records current iteration timestamp', async () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const commentBody = '<!-- keepalive-state:v1 {"iteration":2} -->';
    const github = {
      paginate: async () => [
        {
          body: commentBody,
          id: 123,
          html_url: 'https://example.com/comment/123',
        },
      ],
      rest: {
        issues: {
          listComments() {},
        },
      },
    };
    const context = { repo: { owner: 'octo', repo: 'keepalive' } };
    const result = await loadKeepaliveState({
      github,
      context,
      prNumber: 101,
      trace: '',
    });
    assert.equal(result.state.current_iteration_at, new Date(now).toISOString());
    assert.equal(result.state.iteration, 2);
    assert.equal(result.commentId, 123);
  } finally {
    Date.now = realNow;
  }
});

test('save computes iteration duration from current_iteration_at', async () => {
  const realNow = Date.now;
  const startNow = 1700000000000;
  const endNow = startNow + 2 * 60 * 1000 + 5 * 1000;
  Date.now = () => startNow;
  try {
    const github = {
      paginate: async () => [],
      rest: {
        issues: {
          listComments() {},
          createComment: async () => ({
            data: { id: 321, html_url: 'https://example.com/comment/321' },
          }),
          updateComment: async () => ({}),
        },
      },
    };
    const context = { repo: { owner: 'octo', repo: 'keepalive' } };
    const manager = await createKeepaliveStateManager({
      github,
      context,
      prNumber: 101,
      trace: 'trace-123',
      round: '1',
    });
    Date.now = () => endNow;
    const result = await manager.save({ iteration: 2 });
    assert.equal(result.state.iteration_duration, '2m 5s');
    assert.equal(result.state.current_iteration_at, new Date(startNow).toISOString());
  } finally {
    Date.now = realNow;
  }
});
