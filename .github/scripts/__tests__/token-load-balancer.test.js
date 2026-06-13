'use strict';

/**
 * Tests for token_load_balancer.js key exported functions.
 * Covers shouldDefer, getBestAvailableToken, and hasHealthyTokens
 * using the real implementation against constructed inputs (no mocks of the module).
 *
 * Issue: stranske/Workflows#2335
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const balancer = require(path.resolve(__dirname, '..', 'token_load_balancer.js'));

/**
 * Helper: clear the shared token registry and seed it with a controlled set.
 * Each entry in `tokens` is { id, remaining, limit? }.
 */
function seedRegistry(tokens) {
  balancer.tokenRegistry.tokens.clear();
  balancer.tokenRegistry.lastRefresh = 0;
  for (const { id, remaining, limit = 5000 } of tokens) {
    balancer.registerToken({
      id,
      token: `fake-token-${id}`,
      type: 'PAT',
      source: id,
      capabilities: ['read-repo', 'write-repo'],
      priority: 5,
    });
    // Override the rateLimit that registerToken sets to control remaining.
    const info = balancer.tokenRegistry.tokens.get(id);
    info.rateLimit.remaining = remaining;
    info.rateLimit.limit = limit;
    info.rateLimit.used = limit - remaining;
    info.rateLimit.percentUsed = ((limit - remaining) / limit) * 100;
    info.rateLimit.percentRemaining = (remaining / limit) * 100;
  }
}

// ---------------------------------------------------------------------------
// shouldDefer
// ---------------------------------------------------------------------------

test('shouldDefer: returns false when at least one token exceeds the threshold', () => {
  seedRegistry([
    { id: 'TOKEN_A', remaining: 50 },
    { id: 'TOKEN_B', remaining: 500 },
  ]);
  // Default threshold is 100; TOKEN_B (500) >= 100 → should NOT defer.
  assert.equal(balancer.shouldDefer(), false);
});

test('shouldDefer: returns true when all tokens are below the threshold', () => {
  seedRegistry([
    { id: 'TOKEN_A', remaining: 30 },
    { id: 'TOKEN_B', remaining: 5 },
  ]);
  // Both are below the default threshold of 100 → should defer.
  assert.equal(balancer.shouldDefer(), true);
});

test('shouldDefer: returns true when exactly at threshold (< not <=)', () => {
  // shouldDefer loops for remaining >= minRemaining to return false.
  // So remaining === 100 returns false (not deferred); remaining === 99 defers.
  seedRegistry([{ id: 'TOKEN_A', remaining: 100 }]);
  assert.equal(balancer.shouldDefer(100), false);

  seedRegistry([{ id: 'TOKEN_A', remaining: 99 }]);
  assert.equal(balancer.shouldDefer(100), true);
});

test('shouldDefer: returns true when registry is empty', () => {
  balancer.tokenRegistry.tokens.clear();
  // No tokens → loop never executes → falls through to return true.
  assert.equal(balancer.shouldDefer(), true);
});

test('shouldDefer: respects custom minRemaining argument', () => {
  seedRegistry([{ id: 'TOKEN_A', remaining: 200 }]);
  assert.equal(balancer.shouldDefer(500), true);  // 200 < 500 → defer
  assert.equal(balancer.shouldDefer(200), false); // 200 >= 200 → proceed
  assert.equal(balancer.shouldDefer(50), false);  // 200 >= 50  → proceed
});

// ---------------------------------------------------------------------------
// getBestAvailableToken
// ---------------------------------------------------------------------------

test('getBestAvailableToken: returns the token with highest remaining capacity', () => {
  seedRegistry([
    { id: 'LOW',  remaining: 100 },
    { id: 'HIGH', remaining: 4000 },
    { id: 'MID',  remaining: 1000 },
  ]);
  const best = balancer.getBestAvailableToken();
  assert.ok(best !== null, 'expected a token to be returned');
  assert.equal(best.id, 'HIGH');
});

test('getBestAvailableToken: returns null when registry is empty', () => {
  balancer.tokenRegistry.tokens.clear();
  const best = balancer.getBestAvailableToken();
  // With no tokens, bestRemaining stays -1 and best stays null.
  assert.equal(best, null);
});

test('getBestAvailableToken: returns the only token when registry has one entry', () => {
  seedRegistry([{ id: 'ONLY', remaining: 42 }]);
  const best = balancer.getBestAvailableToken();
  assert.ok(best !== null);
  assert.equal(best.id, 'ONLY');
});

test('getBestAvailableToken: handles tokens with zero remaining', () => {
  seedRegistry([
    { id: 'ZERO_A', remaining: 0 },
    { id: 'ZERO_B', remaining: 0 },
    { id: 'ONE',    remaining: 1 },
  ]);
  const best = balancer.getBestAvailableToken();
  assert.equal(best.id, 'ONE');
});

// ---------------------------------------------------------------------------
// hasHealthyTokens
// ---------------------------------------------------------------------------

test('hasHealthyTokens: returns true when a token has healthy remaining (>50%)', () => {
  seedRegistry([{ id: 'HEALTHY', remaining: 3000, limit: 5000 }]);
  // 3000/5000 = 60% → status = 'healthy' → hasHealthyTokens = true.
  assert.equal(balancer.hasHealthyTokens(), true);
});

test('hasHealthyTokens: returns true when a token is moderate (>20% and <=50%)', () => {
  seedRegistry([{ id: 'MODERATE', remaining: 1500, limit: 5000 }]);
  // 1500/5000 = 30% → status = 'moderate' → hasHealthyTokens = true.
  assert.equal(balancer.hasHealthyTokens(), true);
});

test('hasHealthyTokens: returns false when all tokens are at critical level', () => {
  // criticalThreshold = 5%, so remaining/limit <= 0.05 → 'critical'.
  seedRegistry([
    { id: 'CRITICAL_A', remaining: 50,  limit: 5000 }, // 1%
    { id: 'CRITICAL_B', remaining: 200, limit: 5000 }, // 4%
  ]);
  assert.equal(balancer.hasHealthyTokens(), false);
});

test('hasHealthyTokens: returns false when all tokens are at low level', () => {
  // lowThreshold = 20%, so between 5% and 20% = 'low'.
  seedRegistry([
    { id: 'LOW_A', remaining: 500,  limit: 5000 }, // 10%
    { id: 'LOW_B', remaining: 800,  limit: 5000 }, // 16%
  ]);
  assert.equal(balancer.hasHealthyTokens(), false);
});

test('hasHealthyTokens: returns false when registry is empty', () => {
  balancer.tokenRegistry.tokens.clear();
  assert.equal(balancer.hasHealthyTokens(), false);
});

test('hasHealthyTokens: returns true when mixed critical and healthy tokens exist', () => {
  seedRegistry([
    { id: 'CRITICAL', remaining: 10,   limit: 5000 }, // 0.2% → critical
    { id: 'HEALTHY',  remaining: 3000, limit: 5000 }, // 60%  → healthy
  ]);
  assert.equal(balancer.hasHealthyTokens(), true);
});
