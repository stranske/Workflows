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
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// We need to test the module with mocked dependencies
// Since Node test runner doesn't have built-in mocking like Jest,
// we test what we can without full dependency mocking

const {
  isRateLimitWrapped,
  isTestMock,
} = require('../github-rate-limited-wrapper.js');

// Issue #3606's Gate contract must be exercised by this named Node command.
// Read the actual github-script steps from both create-only workflow copies.
function gateStep(workflowPath, stepName) {
  const lines = fs.readFileSync(workflowPath, 'utf8').split('\n');
  const marker = `- name: ${stepName}`;
  const start = lines.findIndex((line) => line.trim() === marker);
  assert.notEqual(start, -1, `${workflowPath}: missing ${stepName}`);
  const scriptLine = lines.findIndex((line, i) => i > start && line.trim() === 'script: |');
  assert.notEqual(scriptLine, -1, `${workflowPath}: missing script for ${stepName}`);
  const script = [];
  for (const line of lines.slice(scriptLine + 1)) {
    if (line.trim() && !line.startsWith('            ')) break;
    script.push(line.startsWith('            ') ? line.slice(12) : '');
  }
  assert.ok(script.length, `${workflowPath}: empty ${stepName}`);
  return script.join('\n');
}

async function runGateStep(source, stepName, { status, message, response, fork = true }) {
  const warnings = [];
  const summary = [];
  const error = new Error(message);
  error.status = status;
  error.response = response;
  const summaryStub = {
    addHeading() { return this; },
    addRaw(value) { summary.push(String(value)); return this; },
    async write() { summary.push('<written>'); },
  };
  const github = {
    rest: { repos: { async createCommitStatus() { throw error; } } },
  };
  const sandbox = {
    process: { env: { STATE: 'success', DESCRIPTION: 'all checks passed', TARGET_URL: 'https://example.invalid/run' } },
    console: { log() {} },
    github,
    core: { warning(value) { warnings.push(String(value)); }, summary: summaryStub },
    context: {
      repo: { owner: 'stranske', repo: 'Workflows' },
      sha: 'basesha',
      payload: { pull_request: {
        number: 3614,
        head: { sha: 'headsha', repo: { full_name: fork ? 'contributor/Workflows' : 'stranske/Workflows' } },
        base: { repo: { full_name: 'stranske/Workflows' } },
      } },
    },
    require(moduleName) {
      if (moduleName === 'path') return { resolve: () => '/tmp/gate-summary.md' };
      if (moduleName === 'fs') return { existsSync: () => true, readFileSync: () => 'GATE SUMMARY BODY' };
      if (moduleName.includes('comment-dedupe')) return { async upsertAnchoredComment() { throw error; } };
      return { async createTokenAwareRetry() { return { async withRetry(fn) { return fn(github); } }; } };
    },
  };
  let thrown = null;
  try {
    await vm.runInNewContext(`(async () => {\n${source}\n})()`, sandbox);
  } catch (caught) {
    thrown = caught;
  }
  return { warnings, summary, thrown, stepName };
}

for (const workflow of [
  path.resolve(__dirname, '../../workflows/pr-00-gate.yml'),
  path.resolve(__dirname, '../../../templates/consumer-repo/.github/workflows/pr-00-gate.yml'),
]) {
  for (const stepName of ['Ensure consolidated summary comment', 'Report Gate commit status']) {
    const source = gateStep(workflow, stepName);
    const isComment = stepName.startsWith('Ensure');
    test(`${path.relative(process.cwd(), workflow)} ${stepName}: exhausted quota stays out of fork fallback`, async () => {
      const result = await runGateStep(source, stepName, {
        status: 403,
        message: 'Forbidden',
        response: { headers: { 'x-ratelimit-remaining': '0' } },
      });
      if (isComment) {
        assert.equal(result.thrown?.status, 403);
      } else {
        assert.equal(result.thrown, null);
        assert.ok(result.warnings.some((warning) => warning.includes('Rate limit')));
      }
      assert.equal(result.summary.length, 0, 'rate limits must never claim a read-only fork token');
    });
    test(`${path.relative(process.cwd(), workflow)} ${stepName}: positive-quota fork denial and same-repo denial stay distinct`, async () => {
      const options = {
        status: 403,
        message: 'Resource not accessible by integration',
        response: { headers: { 'x-ratelimit-remaining': '42' } },
      };
      const forkResult = await runGateStep(source, stepName, options);
      assert.equal(forkResult.thrown, null);
      assert.ok(forkResult.warnings.some((warning) => warning.includes('read-only')));
      assert.ok(forkResult.summary.includes('<written>'));
      const sameResult = await runGateStep(source, stepName, { ...options, fork: false });
      assert.equal(sameResult.thrown?.status, 403);
      assert.equal(sameResult.summary.length, 0);
    });
  }
}

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

test('wrapped client preserves __getTokenSource function identity', async () => {
  const { createRateLimitedGithub } = require('../github-rate-limited-wrapper.js');

  const github = {
    rest: {
      rateLimit: {
        get: async () => ({
          data: { resources: { core: { remaining: 5000, limit: 5000, reset: 0 } } },
        }),
      },
    },
    request: function request() {},
    hook: {},
  };

  const wrapped = await createRateLimitedGithub({ github });
  const descriptor = Object.getOwnPropertyDescriptor(wrapped, '__getTokenSource');
  assert.ok(descriptor, '__getTokenSource should exist on wrapped client');
  assert.equal(descriptor.configurable, false);
  assert.equal(wrapped.__getTokenSource, descriptor.value);
  assert.equal(typeof wrapped.__getTokenSource, 'function');
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
