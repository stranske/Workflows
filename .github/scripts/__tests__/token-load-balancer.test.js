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

// ---------------------------------------------------------------------------
// statuses:write capability filtering
//
// Regression guard for the defect these cover: `statuses:write` aliased to the generic
// `write-repo`, which GITHUB_TOKEN, PAT *and* APP all claim, so declaring the capability
// filtered nothing and the balancer could hand out an App installation without the Commit
// statuses scope. Observed in stranske/Orchestrator on 2026-08-23: the Gate's own status post
// selected WORKFLOWS_APP and got a 403, the swallow left the previous status in place, and a
// fully green run kept a red `Gate / gate` that nothing could clear.
// ---------------------------------------------------------------------------

test('TOKEN_CAPABILITIES: statuses is held by GITHUB_TOKEN and PAT but NOT by APP', () => {
  assert.ok(balancer.TOKEN_CAPABILITIES.GITHUB_TOKEN.includes('statuses'));
  assert.ok(balancer.TOKEN_CAPABILITIES.PAT.includes('statuses'));
  assert.equal(
    balancer.TOKEN_CAPABILITIES.APP.includes('statuses'),
    false,
    'APP must not claim `statuses`: an App installation only has Commit statuses if it was '
    + 'granted them, and the installations in use were not. A wrong entry here is silent -- the '
    + 'balancer hands out a token that 403s on POST /statuses/{sha}.'
  );
});

// A multi-token "the App must not win on capacity" test was written and then REMOVED. Selection
// scores `percentRemaining + priority*10 + typeBonus + taskBonus`, so an ineligible App with more
// headroom should out-score a statuses-capable token -- but the test passed even with the alias
// deliberately broken, i.e. for a reason not established (getOptimalToken refreshes rate limits,
// which appears to discard seeded capacities). A test that passes for an unknown reason is a false
// comfort, not coverage, so the guard here is the two assertions below, both of which DO fail when
// the alias is reverted to ['write-repo']: the table itself, and the App-only selection.

/** Register a single token of one type, healthy, so eligibility alone decides the answer. */
function seedOnly(type) {
  balancer.tokenRegistry.tokens.clear();
  balancer.tokenRegistry.lastRefresh = 0;
  balancer.registerToken({
    id: type,
    token: `fake-token-${type}`,
    type,
    source: type,
    capabilities: balancer.TOKEN_CAPABILITIES[type],
    priority: 5,
  });
  const info = balancer.tokenRegistry.tokens.get(type);
  info.rateLimit.remaining = 5000;
  info.rateLimit.limit = 5000;
  info.rateLimit.used = 0;
  info.rateLimit.percentUsed = 0;
  info.rateLimit.percentRemaining = 100;
}

test('a broad write-repo request still accepts APP, so the fix narrowed nothing else', async () => {
  // Asserted on ELIGIBILITY, not on who wins: selection is deterministic given equal capacity,
  // so "APP shows up eventually" would never hold regardless of the capability tables.
  seedOnly('APP');
  const selection = await balancer.getOptimalToken({
    capabilities: ['contents:write'],
    minRemaining: 1,
  });
  assert.equal(
    selection?.source ?? null,
    'APP',
    'APP should still satisfy a generic write-repo request; if it does not, the capability change '
    + 'over-narrowed and every App-backed caller just lost its token'
  );
});

test('statuses:write with only an APP registered returns no token rather than a doomed one', async () => {
  balancer.tokenRegistry.tokens.clear();
  balancer.tokenRegistry.lastRefresh = 0;
  balancer.registerToken({
    id: 'APP',
    token: 'fake-token-APP',
    type: 'APP',
    source: 'APP',
    capabilities: balancer.TOKEN_CAPABILITIES.APP,
    priority: 5,
  });
  const info = balancer.tokenRegistry.tokens.get('APP');
  info.rateLimit.remaining = 5000;
  info.rateLimit.limit = 5000;
  info.rateLimit.percentRemaining = 100;

  const selection = await balancer.getOptimalToken({
    capabilities: ['statuses:write'],
    minRemaining: 1,
  });
  assert.equal(
    selection?.source ?? null,
    null,
    'handing back an APP that cannot write statuses is worse than handing back nothing: the '
    + 'caller falls through to its own github client, which is the token that actually has the scope'
  );
});
