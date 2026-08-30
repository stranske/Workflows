'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  isRateLimitError,
  isSecondaryRateLimitError,
  withRetry,
  paginateWithRetry,
  createTokenAwareRetry,
  checkRateLimitStatus,
} = require(path.join(__dirname, '../github-api-with-retry'));

test('exports rate limit classifiers for workflow fail-open guards', () => {
  const primary = new Error('API rate limit exceeded');
  primary.status = 403;
  primary.response = { headers: { 'x-ratelimit-remaining': '0' } };

  const secondary = new Error('You have exceeded a secondary rate limit');
  secondary.status = 403;

  assert.equal(isRateLimitError(primary), true);
  assert.equal(isSecondaryRateLimitError(secondary), true);
});

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

test('paginateWithRetry switches tokens on primary rate limit errors', async () => {
  const calls = [];
  const tokenRegistry = {
    async getOptimalToken() {
      return {
        token: 'token-b',
        source: 'TOKEN_B',
        remaining: 4000,
        percentRemaining: 80,
      };
    },
  };

  const github = {
    token: 'token-a',
    async paginate() {
      calls.push('token-a');
      const error = new Error('API rate limit exceeded');
      error.status = 403;
      error.response = { headers: { 'x-ratelimit-remaining': '0' } };
      throw error;
    },
  };

  const getOctokit = (token) => ({
    token,
    async paginate() {
      calls.push(token);
      return [{ id: 1 }];
    },
  });

  const result = await paginateWithRetry(
    github,
    github.paginate,
    { page: 1 },
    {
      tokenRegistry,
      getOctokit,
      tokenSource: 'TOKEN_A',
      maxRetries: 1,
    }
  );

  assert.deepEqual(result, [{ id: 1 }]);
  assert.deepEqual(calls, ['token-a', 'token-b']);
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
    env: { GITHUB_TOKEN: 'github-token' },
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

test('createTokenAwareRetry skips registry initialization when no token inputs exist', async () => {
  const calls = [];
  const tokenRegistry = {
    async initializeTokenRegistry() {
      calls.push('initialize');
      throw new Error('should not initialize without tokens');
    },
    async getOptimalToken() {
      calls.push('select');
      throw new Error('should not select without tokens');
    },
    isInitialized() {
      return false;
    },
  };

  const github = { token: 'github-script-client' };
  const warnings = [];
  const client = await createTokenAwareRetry({
    github,
    core: { warning: (message) => warnings.push(String(message)) },
    env: {},
    tokenRegistry,
  });

  assert.equal(client.github, github);
  assert.equal(client.tokenRegistry, null);
  assert.equal(client.getTokenSource(), null);
  assert.deepEqual(calls, []);
  assert.deepEqual(warnings, []);
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
  // Provide getOctokit factory so the token selection code path is exercised
  const getOctokit = (token) => ({ token });

  const client = await createTokenAwareRetry({
    github,
    core,
    env: {},
    tokenRegistry,
    getOctokit,
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

test('withRetry fails fast on primary rate limit exhaustion and logs incident', async () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rate-limit-test-'));
  const incidentLogPath = path.join(tmpDir, 'incidents.ndjson');

  let callCount = 0;
  const github = { token: 'token-a' };
  const startedAt = process.hrtime.bigint();

  await assert.rejects(
    async () => withRetry(
      async () => {
        callCount += 1;
        const error = new Error('API rate limit exceeded for token secret_token_xyz');
        error.status = 403;
        error.response = { headers: { 'x-ratelimit-remaining': '0', 'x-ratelimit-limit': '5000' } };
        throw error;
      },
      {
        github,
        tokenSource: 'TOKEN_A',
        task: 'test-fail-fast',
        maxRetries: 5,
        initialDelay: 5000,
        incidentLogPath,
      }
    ),
    /API rate limit exceeded/
  );
  const elapsedMs = Number(process.hrtime.bigint() - startedAt) / 1e6;

  // Must fail fast on first attempt without retrying 5 times or sleeping
  // through any backoff delay (initialDelay above is deliberately large so a
  // stray sleep would make this test slow and flaky, not just wrong).
  assert.equal(callCount, 1);
  assert.ok(elapsedMs < 500, `expected no sleep, took ${elapsedMs}ms`);

  // Verify NDJSON incident record
  assert.ok(fs.existsSync(incidentLogPath));
  const content = fs.readFileSync(incidentLogPath, 'utf8').trim();
  const incident = JSON.parse(content.split('\n')[0]);

  assert.equal(incident.schema, 'rate-limit-incident/v1');
  assert.equal(incident.provider, 'github');
  assert.match(incident.incident_id, /^[0-9a-f]{16}$/);
  assert.equal(incident.surface, 'test-fail-fast');
  assert.equal(incident.credential_pool, 'TOKEN_A');
  assert.equal(incident.resource, 'core');
  assert.equal(incident.reroute, 'caller_circuit_break');
  assert.equal(incident.extra.token_source, 'TOKEN_A');
  assert.equal(incident.subcategory, 'primary_rate_limit_exhausted');
  assert.equal(incident.status, 'exhausted');
  assert.equal(incident.remaining, 0);
  assert.equal(incident.limit, 5000);
  assert.equal(incident.evidence_excerpt.includes('secret_token_xyz'), false);
  assert.match(incident.evidence_hash, /^[0-9a-f]{16}$/);

  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test('withRetry preserves retries for secondary rate limit errors', async () => {
  let callCount = 0;
  const retryDelays = [];
  const github = { token: 'token-a' };

  await assert.rejects(
    async () => withRetry(
      async () => {
        callCount += 1;
        const error = new Error('You have exceeded a secondary rate limit');
        error.status = 403;
        throw error;
      },
      {
        github,
        maxRetries: 2,
        initialDelay: 10,
        onRetry: (attempt, err, delay) => retryDelays.push({ attempt, delay }),
      }
    ),
    /secondary rate limit/
  );

  assert.equal(callCount, 3); // initial attempt + 2 retries
  assert.equal(retryDelays.length, 2);
});

test('withRetry does not record ordinary transient failures as rate-limit incidents', async () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rate-limit-test-'));
  const incidentLogPath = path.join(tmpDir, 'incidents.ndjson');
  const error = new Error('upstream service unavailable');
  error.status = 503;
  error.request = { method: 'GET' };

  await assert.rejects(
    withRetry(async () => { throw error; }, { maxRetries: 0, incidentLogPath }),
    /unavailable/
  );
  assert.equal(fs.existsSync(incidentLogPath), false);
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test('withRetry incident logging appends to and preserves existing NDJSON rows', async () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rate-limit-test-'));
  const incidentLogPath = path.join(tmpDir, 'incidents.ndjson');
  const priorRow = JSON.stringify({ schema: 'rate-limit-incident/v1', surface: 'prior-run' });
  fs.writeFileSync(incidentLogPath, priorRow + '\n', 'utf8');

  const github = { token: 'token-a' };
  await assert.rejects(
    async () => withRetry(
      async () => {
        const error = new Error('API rate limit exceeded');
        error.status = 403;
        error.response = { headers: { 'x-ratelimit-remaining': '0' } };
        throw error;
      },
      { github, tokenSource: 'TOKEN_A', task: 'test-preserve-rows', incidentLogPath }
    ),
    /API rate limit exceeded/
  );

  const rows = fs.readFileSync(incidentLogPath, 'utf8').trim().split('\n');
  assert.equal(rows.length, 2);
  assert.equal(rows[0], priorRow);
  assert.equal(JSON.parse(rows[1]).surface, 'test-preserve-rows');

  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test('withRetry only defaults the incident log path under artifacts/ when GITHUB_ACTIONS=true', async () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const originalCwd = process.cwd();
  const originalGithubActions = process.env.GITHUB_ACTIONS;
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rate-limit-test-'));
  const defaultRelativePath = path.join('artifacts', 'rate-limit-incidents.ndjson');

  const throwRateLimit = async () => {
    const github = { token: 'token-a' };
    await assert.rejects(
      withRetry(
        async () => {
          const error = new Error('API rate limit exceeded');
          error.status = 403;
          error.response = { headers: { 'x-ratelimit-remaining': '0' } };
          throw error;
        },
        { github, tokenSource: 'TOKEN_A', task: 'test-default-path' }
      ),
      /API rate limit exceeded/
    );
  };

  try {
    process.chdir(tmpDir);

    delete process.env.GITHUB_ACTIONS;
    await throwRateLimit();
    assert.equal(
      fs.existsSync(defaultRelativePath),
      false,
      'no incident log should be written outside GitHub Actions without an explicit path'
    );

    process.env.GITHUB_ACTIONS = 'true';
    await throwRateLimit();
    assert.equal(fs.existsSync(defaultRelativePath), true);
  } finally {
    process.chdir(originalCwd);
    if (originalGithubActions === undefined) delete process.env.GITHUB_ACTIONS;
    else process.env.GITHUB_ACTIONS = originalGithubActions;
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('checkRateLimitStatus fails closed on probe errors by default', async () => {
  const github = {
    rest: {
      rateLimit: {
        get: async () => {
          throw new Error('probe failed');
        },
      },
    },
  };

  const status = await checkRateLimitStatus(github, { threshold: 1000, failOpen: false });
  assert.equal(status.safe, false);
  assert.equal(status.state, 'unknown');
  assert.equal(status.error, 'probe failed');
});

test('checkRateLimitStatus can fail open for ancillary probes', async () => {
  const github = {
    rest: {
      rateLimit: {
        get: async () => {
          throw new Error('probe failed');
        },
      },
    },
  };

  const status = await checkRateLimitStatus(github, { threshold: 1000, failOpen: true });
  assert.equal(status.safe, true);
  assert.equal(status.state, 'safe');
  assert.equal(status.error, 'probe failed');
});

test('checkRateLimitStatus blocks API-heavy work below threshold', async () => {
  const github = {
    rest: {
      rateLimit: {
        get: async () => ({
          data: {
            resources: {
              core: { remaining: 50, limit: 5000, reset: 1_700_000_000 },
            },
          },
        }),
      },
    },
  };

  const status = await checkRateLimitStatus(github, { threshold: 1000, failOpen: false });
  assert.equal(status.safe, false);
  assert.equal(status.state, 'low');
  assert.equal(status.remaining, 50);
});

test('checkRateLimitStatus protects a percentage reserve plus forecast cost', async () => {
  const github = {
    rest: {
      rateLimit: {
        get: async () => ({
          data: {
            resources: {
              core: { remaining: 249, limit: 1000, reset: 1_700_000_000 },
            },
          },
        }),
      },
    },
  };

  const status = await checkRateLimitStatus(github, {
    threshold: 0,
    reserveFraction: 0.15,
    estimatedCost: 100,
    failOpen: false,
  });
  assert.equal(status.requiredRemaining, 250);
  assert.equal(status.safe, false);
});

test('checkRateLimitStatus probes an already wrapped consuming pool without reselection', async () => {
  const github = {
    rest: {
      rateLimit: {
        get: async () => ({
          data: {
            resources: {
              core: { remaining: 4000, limit: 5000, reset: 1_700_000_000 },
            },
          },
        }),
      },
    },
  };
  Object.defineProperty(github, '__rateLimitWrapped', { value: true });
  Object.defineProperty(github, '__getTokenSource', { value: () => 'WORKFLOWS_APP' });

  const status = await checkRateLimitStatus(github, {
    threshold: 0,
    reserveFraction: 0.15,
    estimatedCost: 100,
    failOpen: false,
  });
  assert.equal(status.safe, true);
  assert.equal(status.credentialPoolId, 'WORKFLOWS_APP');
});
