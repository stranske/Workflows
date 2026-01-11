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

test('calculateElapsedTime returns 0s for invalid date strings with a valid now', () => {
  const now = 1700000000000;
  assert.equal(calculateElapsedTime('invalid', now), '0s');
});

test('calculateElapsedTime returns 0s for empty strings', () => {
  assert.equal(calculateElapsedTime('  '), '0s');
});

test('calculateElapsedTime returns 0s for invalid Date objects', () => {
  const invalidDate = new Date('invalid');
  assert.equal(calculateElapsedTime(invalidDate), '0s');
});

test('calculateElapsedTime returns 0s for NaN inputs', () => {
  assert.equal(calculateElapsedTime(Number.NaN), '0s');
});

test('calculateElapsedTime trims date string inputs', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = `  ${new Date(now - 4000).toISOString()}  `;
    assert.equal(calculateElapsedTime(start), '4s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime formats minutes and seconds', () => {
  const now = 1700000000000;
  const start = new Date(now - (5 * 60 * 1000 + 23 * 1000)).toISOString();
  assert.equal(calculateElapsedTime(start, now), '5m 23s');
});

test('calculateElapsedTime accepts now as a numeric string', () => {
  const now = 1700000000000;
  const start = new Date(now - 12 * 1000).toISOString();
  assert.equal(calculateElapsedTime(start, String(now)), '12s');
});

test('calculateElapsedTime accepts now as a Date object', () => {
  const now = 1700000000000;
  const start = new Date(now - 18 * 1000).toISOString();
  assert.equal(calculateElapsedTime(start, new Date(now)), '18s');
});

test('calculateElapsedTime trims ISO string now input', () => {
  const start = '2026-01-10T20:00:00Z';
  const nowIso = '2026-01-10T20:05:23Z';
  assert.equal(calculateElapsedTime(start, `  ${nowIso}  `), '5m 23s');
});

test('calculateElapsedTime falls back to Date.now when now is invalid', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = new Date(now - 7 * 1000).toISOString();
    assert.equal(calculateElapsedTime(start, 'invalid'), '7s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime formats whole minutes', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = new Date(now - 60 * 1000).toISOString();
    assert.equal(calculateElapsedTime(start), '1m 0s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime returns 0s for zero duration', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = new Date(now).toISOString();
    assert.equal(calculateElapsedTime(start), '0s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime matches the documented example', () => {
  const start = '2026-01-10T20:00:00Z';
  const now = Date.parse('2026-01-10T20:05:23Z');
  assert.equal(calculateElapsedTime(start, now), '5m 23s');
});

test('calculateElapsedTime matches documented example with Date.now', () => {
  const realNow = Date.now;
  const now = Date.parse('2026-01-10T20:05:23Z');
  Date.now = () => now;
  try {
    const start = '2026-01-10T20:00:00Z';
    assert.equal(calculateElapsedTime(start), '5m 23s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime truncates fractional seconds', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = new Date(now - 1999).toISOString();
    assert.equal(calculateElapsedTime(start), '1s');
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

test('calculateElapsedTime supports numeric timestamp strings', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = String(now - 15 * 1000);
    assert.equal(calculateElapsedTime(start), '15s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime trims numeric timestamp strings', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = `  ${now - 8 * 1000}  `;
    assert.equal(calculateElapsedTime(start), '8s');
  } finally {
    Date.now = realNow;
  }
});

test('calculateElapsedTime supports decimal numeric timestamp strings', () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const start = String(now - 1500.5);
    assert.equal(calculateElapsedTime(start), '1s');
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

test('loadKeepaliveState sets first_iteration_at for the first iteration', async () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const commentBody = '<!-- keepalive-state:v1 {"iteration":1} -->';
    const github = {
      paginate: async () => [
        {
          body: commentBody,
          id: 124,
          html_url: 'https://example.com/comment/124',
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
      prNumber: 102,
      trace: '',
    });
    const expectedTimestamp = new Date(now).toISOString();
    assert.equal(result.state.first_iteration_at, expectedTimestamp);
    assert.equal(result.state.current_iteration_at, expectedTimestamp);
  } finally {
    Date.now = realNow;
  }
});

test('loadKeepaliveState preserves first_iteration_at for later iterations', async () => {
  const realNow = Date.now;
  const now = 1700000000000;
  Date.now = () => now;
  try {
    const firstIterationAt = '2025-01-01T00:00:00.000Z';
    const commentBody = `<!-- keepalive-state:v1 {"iteration":2,"first_iteration_at":"${firstIterationAt}"} -->`;
    const github = {
      paginate: async () => [
        {
          body: commentBody,
          id: 125,
          html_url: 'https://example.com/comment/125',
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
      prNumber: 103,
      trace: '',
    });
    assert.equal(result.state.first_iteration_at, firstIterationAt);
    assert.equal(result.state.current_iteration_at, new Date(now).toISOString());
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
