'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { calculateElapsedTime, loadKeepaliveState } = require('../.github/scripts/keepalive_state.js');

test('calculateElapsedTime returns 0s for null input', () => {
  assert.equal(calculateElapsedTime(null), '0s');
});

test('calculateElapsedTime returns 0s for invalid date strings', () => {
  assert.equal(calculateElapsedTime('invalid'), '0s');
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
