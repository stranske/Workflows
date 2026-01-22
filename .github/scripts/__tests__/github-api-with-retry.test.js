'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  withRetry,
  createTokenAwareRetry,
} = require(path.join(__dirname, '../github-api-with-retry'));

test('withRetry switches tokens on primary rate limit errors', async () => {
  const calls = [];
  const debugMessages = [];
  const tokenRegistry = {
    async getOptimalToken() {
      return {
        token: 'token-b',
        source: 'TOKEN_B',
        remaining: 4000,
        percentRemaining: 80,
      };
    },
    updateFromHeaders() {},
  };

  const getOctokit = (token) => ({ token });
  const github = { token: 'token-a' };
  const core = { debug: (message) => debugMessages.push(String(message)) };

  let attempt = 0;
  const response = await withRetry(
    async (client) => {
      calls.push(client.token);
      if (attempt === 0) {
        attempt += 1;
        const error = new Error('API rate limit exceeded');
        error.status = 403;
        error.response = { headers: { 'x-ratelimit-remaining': '0' } };
        throw error;
      }
      return {
        headers: {
          'x-ratelimit-remaining': '4999',
          'x-ratelimit-limit': '5000',
        },
        data: { ok: true },
      };
    },
    {
      github,
      tokenRegistry,
      getOctokit,
      tokenSource: 'TOKEN_A',
      core,
    }
  );

  assert.equal(response.data.ok, true);
  assert.deepEqual(calls, ['token-a', 'token-b']);
  assert.ok(
    debugMessages.some((message) => message.includes('Token TOKEN_B response remaining: 4999/5000'))
  );
});

test('createTokenAwareRetry initializes registry from env secrets', async () => {
  const registryCalls = { secrets: null, githubToken: null };
  const tokenRegistry = {
    async initializeTokenRegistry({ secrets, githubToken }) {
      registryCalls.secrets = secrets;
      registryCalls.githubToken = githubToken;
    },
    async getOptimalToken() {
      return { token: 'token-c', source: 'SERVICE_BOT_PAT' };
    },
  };

  const env = {
    SERVICE_BOT_PAT: 'service-token',
    GITHUB_TOKEN: 'github-token',
  };

  const getOctokit = (token) => ({ token });
  const github = { token: 'fallback' };

  const client = await createTokenAwareRetry({
    github,
    env,
    tokenRegistry,
    getOctokit,
  });

  assert.equal(registryCalls.secrets.SERVICE_BOT_PAT, 'service-token');
  assert.equal(registryCalls.githubToken, 'github-token');
  assert.equal(client.github.token, 'token-c');
  assert.equal(client.getTokenSource(), 'SERVICE_BOT_PAT');

  const callTokens = [];
  await client.withRetry(async (clientInstance) => {
    callTokens.push(clientInstance.token);
    return { headers: {} };
  });

  assert.deepEqual(callTokens, ['token-c']);
});

test('createTokenAwareRetry falls back when registry initialization fails', async () => {
  const warnings = [];
  const tokenRegistry = {
    async initializeTokenRegistry() {
      throw new Error('boom');
    },
    async getOptimalToken() {
      throw new Error('should not be called');
    },
    isInitialized() {
      return false;
    },
  };

  const github = { token: 'fallback' };
  const core = { warning: (message) => warnings.push(String(message)) };

  const client = await createTokenAwareRetry({
    github,
    core,
    env: {},
    tokenRegistry,
  });

  assert.equal(client.github, github);
  assert.equal(client.getTokenSource(), null);
  assert.ok(
    warnings.some((message) => message.includes('Token registry initialization failed: boom'))
  );

  const result = await client.withRetry(async () => ({ headers: {}, data: { ok: true } }));
  assert.equal(result.data.ok, true);
});

test('createTokenAwareRetry falls back when token selection fails', async () => {
  const warnings = [];
  const tokenRegistry = {
    isInitialized() {
      return true;
    },
    async getOptimalToken() {
      throw new Error('select-fail');
    },
  };

  const github = { token: 'fallback' };
  const core = { warning: (message) => warnings.push(String(message)) };

  const client = await createTokenAwareRetry({
    github,
    core,
    env: {},
    tokenRegistry,
  });

  assert.equal(client.github, github);
  assert.equal(client.getTokenSource(), null);
  assert.ok(
    warnings.some((message) => message.includes('Token registry selection failed: select-fail'))
  );
});

test('withRetry ignores token selection errors', async () => {
  const warnings = [];
  const tokenRegistry = {
    async getOptimalToken() {
      throw new Error('select-fail');
    },
    updateFromHeaders() {},
  };

  const github = { token: 'token-a' };
  const getOctokit = (token) => ({ token });
  const core = { warning: (message) => warnings.push(String(message)) };

  await assert.rejects(
    async () => withRetry(
      async () => {
        const error = new Error('API rate limit exceeded');
        error.status = 403;
        error.response = { headers: { 'x-ratelimit-remaining': '0' } };
        throw error;
      },
      {
        github,
        tokenRegistry,
        getOctokit,
        tokenSource: 'TOKEN_A',
        core,
        maxRetries: 0,
      }
    ),
    /API rate limit exceeded/
  );

  assert.ok(
    warnings.some((message) => message.includes('Token registry selection failed: select-fail'))
  );
});

test('withRetry records token usage on rate limit errors without headers', async () => {
  const usageCalls = [];
  const debugMessages = [];
  const tokenRegistry = {
    updateTokenUsage: (tokenSource, calls) => usageCalls.push({ tokenSource, calls }),
  };

  const github = { token: 'token-a' };
  const core = { debug: (message) => debugMessages.push(String(message)) };

  await assert.rejects(
    async () => withRetry(
      async () => {
        const error = new Error('API rate limit exceeded');
        error.status = 403;
        throw error;
      },
      {
        github,
        tokenRegistry,
        tokenSource: 'TOKEN_A',
        core,
        maxRetries: 0,
      }
    ),
    /API rate limit exceeded/
  );

  assert.deepEqual(usageCalls, [{ tokenSource: 'TOKEN_A', calls: 1 }]);
  assert.ok(
    debugMessages.some((message) => message.includes('Token TOKEN_A error usage recorded'))
  );
});

test('withRetry records token usage when headers lack rate limit fields', async () => {
  const usageCalls = [];
  const headerCalls = [];
  const debugMessages = [];
  const tokenRegistry = {
    updateFromHeaders: (...args) => headerCalls.push(args),
    updateTokenUsage: (tokenSource, calls) => usageCalls.push({ tokenSource, calls }),
  };

  const github = { token: 'token-a' };
  const core = { debug: (message) => debugMessages.push(String(message)) };

  const response = await withRetry(
    async () => ({
      headers: { 'content-type': 'application/json' },
      data: { ok: true },
    }),
    {
      github,
      tokenRegistry,
      tokenSource: 'TOKEN_A',
      core,
      maxRetries: 0,
    }
  );

  assert.equal(response.data.ok, true);
  assert.equal(headerCalls.length, 0);
  assert.deepEqual(usageCalls, [{ tokenSource: 'TOKEN_A', calls: 1 }]);
  assert.ok(
    debugMessages.some((message) => message.includes('Token TOKEN_A response usage recorded'))
  );
});
