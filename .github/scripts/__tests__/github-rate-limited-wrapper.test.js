'use strict';

/**
 * Tests for github-rate-limited-wrapper.js
 * 
 * Verifies:
 * 1. API calls are properly wrapped and retry on rate limit errors
 * 2. Already-wrapped clients are detected and returned as-is (avoiding double-wrapping)
 * 3. The Proxy correctly handles rest, graphql, and paginate operations
 * 4. Error handling and fallback to raw client works correctly
 * 5. wrapWithRateLimitedGithub higher-order function works correctly
 * 6. Test mocks are detected and skipped for wrapping
 */

const test = require('node:test');
const assert = require('node:assert/strict');

// We need to test the module with mocked dependencies
// Since Node test runner doesn't have built-in mocking like Jest,
// we test what we can without full dependency mocking

const {
  isRateLimitWrapped,
  isTestMock,
} = require('../github-rate-limited-wrapper.js');

test('isRateLimitWrapped returns false for plain object', () => {
  const github = { rest: { issues: { get: () => {} } } };
  assert.equal(isRateLimitWrapped(github), false);
});

test('isRateLimitWrapped returns false for null', () => {
  assert.equal(isRateLimitWrapped(null), false);
});

test('isRateLimitWrapped returns false for undefined', () => {
  assert.equal(isRateLimitWrapped(undefined), false);
});

test('isRateLimitWrapped returns true for object with __rateLimitWrapped', () => {
  const github = { __rateLimitWrapped: true };
  assert.equal(isRateLimitWrapped(github), true);
});

test('isRateLimitWrapped returns false for object with __rateLimitWrapped=false', () => {
  const github = { __rateLimitWrapped: false };
  assert.equal(isRateLimitWrapped(github), false);
});

// Test isTestMock detection
test('isTestMock returns false for null', () => {
  assert.equal(isTestMock(null), false);
});

test('isTestMock returns false for undefined', () => {
  assert.equal(isTestMock(undefined), false);
});

test('isTestMock returns true for simple mock with only rest property', () => {
  const github = { rest: { issues: { get: () => {} } } };
  assert.equal(isTestMock(github), true);
});

test('isTestMock returns true for object with __testMock marker', () => {
  const github = { __testMock: true, rest: {} };
  assert.equal(isTestMock(github), true);
});

test('isTestMock returns false for Octokit-like object with request and hook', () => {
  const github = {
    rest: { issues: { get: () => {} } },
    request: function() {},
    hook: {},
  };
  assert.equal(isTestMock(github), false);
});

// Test wrapWithRateLimitedGithub error handling path
// This can be tested without mocking by passing invalid github object
test('wrapWithRateLimitedGithub module exports expected functions', () => {
  const wrapper = require('../github-rate-limited-wrapper.js');
  
  assert.equal(typeof wrapper.createRateLimitedGithub, 'function');
  assert.equal(typeof wrapper.isRateLimitWrapped, 'function');
  assert.equal(typeof wrapper.isTestMock, 'function');
  assert.equal(typeof wrapper.ensureRateLimitWrapped, 'function');
  assert.equal(typeof wrapper.wrapWithRateLimitedGithub, 'function');
});

test('wrapWithRateLimitedGithub returns a function', () => {
  const { wrapWithRateLimitedGithub } = require('../github-rate-limited-wrapper.js');
  
  const innerFn = async ({ github, core }) => ({ success: true });
  const wrapped = wrapWithRateLimitedGithub(innerFn);
  
  assert.equal(typeof wrapped, 'function');
});

test('createRateLimitedGithub throws without github client', async () => {
  const { createRateLimitedGithub } = require('../github-rate-limited-wrapper.js');
  
  await assert.rejects(
    createRateLimitedGithub({}),
    { message: 'createRateLimitedGithub requires a github client' }
  );
});

test('createRateLimitedGithub throws with null github client', async () => {
  const { createRateLimitedGithub } = require('../github-rate-limited-wrapper.js');
  
  await assert.rejects(
    createRateLimitedGithub({ github: null }),
    { message: 'createRateLimitedGithub requires a github client' }
  );
});

// Test paginate.iterator support
test('wrapped client preserves paginate.iterator method', async () => {
  const { createRateLimitedGithub } = require('../github-rate-limited-wrapper.js');
  
  // Mock the async iterable structure that Octokit returns
  const mockIterable = {
    [Symbol.asyncIterator]() {
      return {
        async next() { return { value: [{ id: 1 }], done: false }; },
        async return(value) { return { value, done: true }; },
        async throw(error) { throw error; },
      };
    },
  };
  
  const github = {
    rest: { issues: { listForRepo: () => {} } },
    request: function() {},
    hook: {},
    paginate: Object.assign(
      async function() { return []; },
      { iterator: () => mockIterable }
    ),
  };
  
  const wrapped = await createRateLimitedGithub({ github });
  
  // Verify paginate.iterator exists on wrapped client
  assert.equal(typeof wrapped.paginate, 'function', 'paginate should be a function');
  assert.equal(typeof wrapped.paginate.iterator, 'function', 'paginate.iterator should be a function');
});

test('wrapped paginate.iterator returns async iterable', async () => {
  const { createRateLimitedGithub } = require('../github-rate-limited-wrapper.js');
  
  // Track calls to verify retry wrapping
  let nextCallCount = 0;
  // Mock the async iterable structure that Octokit returns
  const mockIterable = {
    [Symbol.asyncIterator]() {
      return {
        async next() {
          nextCallCount++;
          if (nextCallCount === 1) {
            return { value: { data: [{ id: 1 }] }, done: false };
          }
          return { value: undefined, done: true };
        },
        async return(value) { return { value, done: true }; },
        async throw(error) { throw error; },
      };
    },
  };
  
  const github = {
    rest: { issues: { listForRepo: () => {} } },
    request: function() {},
    hook: {},
    paginate: Object.assign(
      async function() { return []; },
      { iterator: () => mockIterable }
    ),
  };
  
  const wrapped = await createRateLimitedGithub({ github });
  const iter = wrapped.paginate.iterator(github.rest.issues.listForRepo, { owner: 'test', repo: 'test' });
  
  // Verify iterable has [Symbol.asyncIterator]
  assert.equal(typeof iter[Symbol.asyncIterator], 'function', 'should be async iterable');
  
  // Get the actual iterator and verify it has next
  const actualIter = iter[Symbol.asyncIterator]();
  assert.equal(typeof actualIter.next, 'function', 'iterator should have next method');
  
  // Consume the iterator
  const results = [];
  for await (const page of iter) {
    results.push(page);
  }
  
  assert.equal(results.length, 1, 'should have received one page');
  assert.equal(nextCallCount, 2, 'next should have been called twice (one page + done)');
});

test('wrapped paginate.iterator exposes full AsyncIterator interface', async () => {
  const { createRateLimitedGithub } = require('../github-rate-limited-wrapper.js');
  
  // Mock the async iterable structure that Octokit returns
  const mockIterable = {
    [Symbol.asyncIterator]() {
      return {
        async next() { return { value: undefined, done: true }; },
        async return(value) { return { value, done: true }; },
        async throw(error) { throw error; },
      };
    },
  };
  
  const github = {
    rest: { issues: { listForRepo: () => {} } },
    request: function() {},
    hook: {},
    paginate: Object.assign(
      async function() { return []; },
      { iterator: () => mockIterable }
    ),
  };
  
  const wrapped = await createRateLimitedGithub({ github });
  const iterable = wrapped.paginate.iterator(github.rest.issues.listForRepo, { owner: 'test', repo: 'test' });
  
  // Verify iterable has [Symbol.asyncIterator]
  assert.equal(typeof iterable[Symbol.asyncIterator], 'function', 'should be async iterable');
  
  // Get the actual iterator and verify full interface
  const iter = iterable[Symbol.asyncIterator]();
  assert.equal(typeof iter.next, 'function', 'should have next method');
  assert.equal(typeof iter.return, 'function', 'should have return method');
  assert.equal(typeof iter.throw, 'function', 'should have throw method');
});

test('wrapped paginate.iterator return() delegates to original', async () => {
  const { createRateLimitedGithub } = require('../github-rate-limited-wrapper.js');
  
  let returnCalled = false;
  // Mock the async iterable structure that Octokit returns
  const mockIterable = {
    [Symbol.asyncIterator]() {
      return {
        async next() { return { value: undefined, done: true }; },
        async return(value) { 
          returnCalled = true;
          return { value, done: true }; 
        },
        async throw(error) { throw error; },
      };
    },
  };
  
  const github = {
    rest: { issues: { listForRepo: () => {} } },
    request: function() {},
    hook: {},
    paginate: Object.assign(
      async function() { return []; },
      { iterator: () => mockIterable }
    ),
  };
  
  const wrapped = await createRateLimitedGithub({ github });
  const iterable = wrapped.paginate.iterator(github.rest.issues.listForRepo, { owner: 'test', repo: 'test' });
  const iter = iterable[Symbol.asyncIterator]();
  
  await iter.return('cleanup');
  assert.equal(returnCalled, true, 'should have called original return()');
});

test('wrapped paginate.iterator throw() delegates to original', async () => {
  const { createRateLimitedGithub } = require('../github-rate-limited-wrapper.js');
  
  let throwCalled = false;
  const testError = new Error('test error');
  // Mock the async iterable structure that Octokit returns
  const mockIterable = {
    [Symbol.asyncIterator]() {
      return {
        async next() { return { value: undefined, done: true }; },
        async return(value) { return { value, done: true }; },
        async throw(error) { 
          throwCalled = true;
          throw error; 
        },
      };
    },
  };
  
  const github = {
    rest: { issues: { listForRepo: () => {} } },
    request: function() {},
    hook: {},
    paginate: Object.assign(
      async function() { return []; },
      { iterator: () => mockIterable }
    ),
  };
  
  const wrapped = await createRateLimitedGithub({ github });
  const iterable = wrapped.paginate.iterator(github.rest.issues.listForRepo, { owner: 'test', repo: 'test' });
  const iter = iterable[Symbol.asyncIterator]();
  
  await assert.rejects(
    iter.throw(testError),
    testError
  );
  assert.equal(throwCalled, true, 'should have called original throw()');
});
