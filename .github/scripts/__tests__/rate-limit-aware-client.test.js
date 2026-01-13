'use strict';

const assert = require('node:assert');
const { describe, it, mock } = require('node:test');

const {
  extractRateLimitFromResponse,
  shouldSwitchToken,
  logRateLimitStatus,
  createProactiveRateLimitClient,
  LOW_RATE_LIMIT_THRESHOLD,
  CRITICAL_RATE_LIMIT_THRESHOLD,
} = require('../rate-limit-aware-client');

describe('extractRateLimitFromResponse', () => {
  it('extracts rate limit info from response headers', () => {
    const response = {
      headers: {
        'x-ratelimit-remaining': '4500',
        'x-ratelimit-limit': '5000',
        'x-ratelimit-reset': '1736745600',
      },
    };
    
    const result = extractRateLimitFromResponse(response);
    
    assert.strictEqual(result.remaining, 4500);
    assert.strictEqual(result.limit, 5000);
    assert.strictEqual(result.reset, 1736745600);
    assert.ok(result.resetTime.includes('2025'));
  });
  
  it('returns nulls for missing headers', () => {
    const result = extractRateLimitFromResponse({});
    
    assert.strictEqual(result.remaining, null);
    assert.strictEqual(result.limit, null);
    assert.strictEqual(result.reset, null);
  });
  
  it('handles null response', () => {
    const result = extractRateLimitFromResponse(null);
    
    assert.strictEqual(result.remaining, null);
  });
});

describe('shouldSwitchToken', () => {
  it('returns true when remaining is below threshold', () => {
    assert.strictEqual(shouldSwitchToken(50, 100), true);
    assert.strictEqual(shouldSwitchToken(99, 100), true);
  });
  
  it('returns false when remaining is above threshold', () => {
    assert.strictEqual(shouldSwitchToken(100, 100), false);
    assert.strictEqual(shouldSwitchToken(500, 100), false);
  });
  
  it('returns false for null remaining', () => {
    assert.strictEqual(shouldSwitchToken(null, 100), false);
    assert.strictEqual(shouldSwitchToken(undefined, 100), false);
  });
});

describe('logRateLimitStatus', () => {
  it('logs warning for low remaining', () => {
    const mockCore = {
      warning: mock.fn(),
      info: mock.fn(),
      error: mock.fn(),
    };
    
    logRateLimitStatus(mockCore, {
      remaining: 50,
      limit: 5000,
      resetTime: '2025-01-13T12:00:00Z',
    }, 'test-token');
    
    assert.strictEqual(mockCore.warning.mock.calls.length, 1);
    assert.ok(mockCore.warning.mock.calls[0].arguments[0].includes('50/5000'));
  });
  
  it('logs error for critical remaining', () => {
    const mockCore = {
      warning: mock.fn(),
      info: mock.fn(),
      error: mock.fn(),
    };
    
    logRateLimitStatus(mockCore, {
      remaining: 5,
      limit: 5000,
      resetTime: '2025-01-13T12:00:00Z',
    }, 'test-token');
    
    assert.strictEqual(mockCore.error.mock.calls.length, 1);
    assert.ok(mockCore.error.mock.calls[0].arguments[0].includes('CRITICAL'));
  });
  
  it('logs info for healthy remaining', () => {
    const mockCore = {
      warning: mock.fn(),
      info: mock.fn(),
      error: mock.fn(),
    };
    
    logRateLimitStatus(mockCore, {
      remaining: 4500,
      limit: 5000,
      resetTime: '2025-01-13T12:00:00Z',
    }, 'test-token');
    
    assert.strictEqual(mockCore.info.mock.calls.length, 1);
  });
});

describe('createProactiveRateLimitClient', () => {
  it('creates client with default values', () => {
    const mockOctokit = {};
    const client = createProactiveRateLimitClient(mockOctokit);
    
    assert.strictEqual(client.usingFallback, false);
    assert.strictEqual(client.currentClient, mockOctokit);
  });
  
  it('switches to fallback when available', () => {
    const mockOctokit = { name: 'primary' };
    const mockFallback = { name: 'fallback' };
    
    const client = createProactiveRateLimitClient(mockOctokit, {
      fallbackOctokit: mockFallback,
    });
    
    assert.strictEqual(client.usingFallback, false);
    
    const switched = client.switchToFallback();
    
    assert.strictEqual(switched, true);
    assert.strictEqual(client.usingFallback, true);
    assert.strictEqual(client.currentClient, mockFallback);
  });
  
  it('does not switch when no fallback', () => {
    const mockOctokit = {};
    const client = createProactiveRateLimitClient(mockOctokit);
    
    const switched = client.switchToFallback();
    
    assert.strictEqual(switched, false);
    assert.strictEqual(client.usingFallback, false);
  });
  
  it('does not switch twice', () => {
    const mockOctokit = { name: 'primary' };
    const mockFallback = { name: 'fallback' };
    
    const client = createProactiveRateLimitClient(mockOctokit, {
      fallbackOctokit: mockFallback,
    });
    
    client.switchToFallback();
    const secondSwitch = client.switchToFallback();
    
    assert.strictEqual(secondSwitch, false);
    assert.strictEqual(client.usingFallback, true);
  });
  
  it('tracks rate limit from response', () => {
    const mockOctokit = {};
    const client = createProactiveRateLimitClient(mockOctokit);
    
    const response = {
      headers: {
        'x-ratelimit-remaining': '100',
        'x-ratelimit-limit': '5000',
        'x-ratelimit-reset': '1736745600',
      },
    };
    
    client.trackRateLimit(response, 'test');
    
    assert.strictEqual(client.lastRateLimitInfo.remaining, 100);
    assert.strictEqual(client.lastRateLimitInfo.limit, 5000);
  });
});

describe('constants', () => {
  it('has sensible threshold values', () => {
    assert.ok(LOW_RATE_LIMIT_THRESHOLD > CRITICAL_RATE_LIMIT_THRESHOLD);
    assert.ok(CRITICAL_RATE_LIMIT_THRESHOLD > 0);
    assert.ok(LOW_RATE_LIMIT_THRESHOLD <= 500);
  });
});
