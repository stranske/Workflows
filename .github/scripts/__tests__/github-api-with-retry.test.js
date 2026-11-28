'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  isRateLimitError,
  isSecondaryRateLimitError,
  withRetry,
  paginateWithRetry,
  collectTokenSecrets,
  createTokenAwareRetry,
  checkRateLimitStatus,
  createGithubFetchRequester,
  computeRetryDelayMs,
  resolveMaxRetries,
  withGithubApiRetry,
} = require(path.join(__dirname, '../github-api-with-retry'));
const { classifyError, ERROR_CATEGORIES } = require(path.join(__dirname, '../error_classifier'));

test('exports rate limit classifiers for workflow fail-open guards', () => {
  const primary = new Error('API rate limit exceeded');
  primary.status = 403;
  primary.response = { headers: { 'x-ratelimit-remaining': '0' } };

  const secondary = new Error('You have exceeded a secondary rate limit');
  secondary.status = 403;

  assert.equal(isRateLimitError(primary), true);
  assert.equal(isSecondaryRateLimitError(secondary), true);
});

test('GraphQL quota errors rotate but permission errors do not', () => {
  const graphqlLimit = new Error('Request failed due to following response errors');
  graphqlLimit.errors = [{ type: 'RATE_LIMITED' }];
  const permission = new Error('Resource not accessible by integration');
  permission.errors = [{ type: 'FORBIDDEN', code: 'FORBIDDEN' }];

  assert.equal(isRateLimitError(graphqlLimit), true);
  assert.equal(isRateLimitError(permission), false);
});

test('withRetry rotates a statusless GraphQL quota response for a read', async () => {
  const calls = [];
  const tokenRegistry = {
    async getOptimalToken(options) {
      assert.equal(options.preferredSource, 'SERVICE_BOT_PAT');
      assert.deepEqual(options.excludeSources, ['OWNER_PR_PAT']);
      return { token: 'service-token', source: 'SERVICE_BOT_PAT' };
    },
    updateTokenUsage() {},
  };
  const result = await withRetry(
    async (client) => {
      calls.push(client.token);
      if (client.token === 'owner-token') {
        const exhausted = new Error('Request failed due to following response errors');
        exhausted.errors = [{ type: 'RATE_LIMITED' }];
        throw exhausted;
      }
      return { repository: { pullRequest: { headRefOid: 'a'.repeat(40) } } };
    },
    {
      github: { token: 'owner-token' },
      tokenRegistry,
      getOctokit: (token) => ({ token }),
      tokenSource: 'OWNER_PR_PAT',
      preferredSource: 'SERVICE_BOT_PAT',
    },
  );
  assert.equal(result.repository.pullRequest.headRefOid, 'a'.repeat(40));
  assert.deepEqual(calls, ['owner-token', 'service-token']);
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

test('rotation pool excludes the owner PAT', async () => {
  const secrets = collectTokenSecrets({
    OWNER_PR_PAT: 'x',
    SERVICE_BOT_PAT: 'y',
  });
  assert.deepEqual(secrets, { SERVICE_BOT_PAT: 'y' });
  assert.equal('OWNER_PR_PAT' in secrets, false);

  const dynamicSecrets = collectTokenSecrets({
    OWNER_PR_PAT: 'x',
    SERVICE_BOT_PAT: 'y',
    TOKEN_ROTATION_ENV_KEYS: 'OWNER_PR_PAT,PAT_1',
    PAT_1: 'z',
  });
  assert.equal('OWNER_PR_PAT' in dynamicSecrets, false);
  assert.equal(dynamicSecrets.PAT_1, 'z');
  assert.equal(dynamicSecrets.TOKEN_ROTATION_ENV_KEYS, 'PAT_1');

  const ownerOnlyDynamicSecrets = collectTokenSecrets({
    OWNER_PR_PAT: 'x',
    TOKEN_ROTATION_ENV_KEYS: 'OWNER_PR_PAT',
  });
  assert.deepEqual(ownerOnlyDynamicSecrets, {});

  const fallbackDynamicSecrets = collectTokenSecrets({
    OWNER_PR_PAT: 'x',
    TOKEN_ROTATION_ENV_KEYS: 'OWNER_PR_PAT',
    TOKEN_ROTATION_KEYS: 'OWNER_PR_PAT,CUSTOM_POOL_PAT',
    CUSTOM_POOL_PAT: 'custom-token',
  });
  assert.deepEqual(fallbackDynamicSecrets, {
    TOKEN_ROTATION_KEYS: 'CUSTOM_POOL_PAT',
    CUSTOM_POOL_PAT: 'custom-token',
  });

  const jsonSecrets = collectTokenSecrets({
    TOKEN_ROTATION_JSON: JSON.stringify({
      pats: [
        { id: 'OWNER_PR_PAT', token: 'x' },
        { id: 'PAT_1', token: 'z' },
      ],
    }),
  });
  assert.deepEqual(JSON.parse(jsonSecrets.TOKEN_ROTATION_JSON), {
    pats: [{ id: 'PAT_1', token: 'z' }],
  });

  const ownerOnlyJsonSecrets = collectTokenSecrets({
    TOKEN_ROTATION_JSON: JSON.stringify({
      pats: [{ id: 'OWNER_PR_PAT', token: 'x' }],
    }),
  });
  assert.deepEqual(ownerOnlyJsonSecrets, {});

  const ownerWithAppJsonSecrets = collectTokenSecrets({
    TOKEN_ROTATION_JSON: JSON.stringify({
      pats: [{ id: 'OWNER_PR_PAT', token: 'x' }],
      apps: [{ id: 'APP_1', appId: '1', privateKey: 'k' }],
    }),
  });
  assert.deepEqual(JSON.parse(ownerWithAppJsonSecrets.TOKEN_ROTATION_JSON), {
    pats: [],
    apps: [{ id: 'APP_1', appId: '1', privateKey: 'k' }],
  });

  const exclusiveSecrets = collectTokenSecrets(
    {
      OWNER_PR_PAT: 'x',
      SERVICE_BOT_PAT: 'y',
      TOKEN_ROTATION_JSON: JSON.stringify({
        pats: [{ id: 'OWNER_PR_PAT', token: 'x' }],
      }),
    },
    { task: 'pr-creation-as-owner' },
  );
  assert.equal(exclusiveSecrets.OWNER_PR_PAT, 'x');
  assert.deepEqual(JSON.parse(exclusiveSecrets.TOKEN_ROTATION_JSON), {
    pats: [{ id: 'OWNER_PR_PAT', token: 'x' }],
  });

  let initializedSecrets = null;
  await createTokenAwareRetry({
    github: { token: 'fallback' },
    env: {
      OWNER_PR_PAT: 'x',
      SERVICE_BOT_PAT: 'y',
      GITHUB_TOKEN: 'gh-token',
    },
    tokenRegistry: {
      isInitialized: () => false,
      async initializeTokenRegistry({ secrets: passedSecrets }) {
        initializedSecrets = passedSecrets;
      },
      async getOptimalToken() {
        return { token: 'y', source: 'SERVICE_BOT_PAT' };
      },
    },
    getOctokit: (token) => ({ token }),
  });
  assert.deepEqual(initializedSecrets, { SERVICE_BOT_PAT: 'y' });
});

test('createTokenAwareRetry registers OWNER_PR_PAT on demand for exclusive tasks after general init', async () => {
  const balancer = require(path.join(__dirname, '../token_load_balancer'));
  balancer.tokenRegistry.tokens.clear();
  balancer.tokenRegistry.lastRefresh = Date.now();
  try {
    const env = {
      OWNER_PR_PAT: 'owner-token',
      SERVICE_BOT_PAT: 'service-token',
    };
    const getOctokit = (token) => ({ token });

    const generalClient = await createTokenAwareRetry({
      github: { token: 'fallback' },
      env,
      tokenRegistry: balancer,
      getOctokit,
    });
    assert.equal(generalClient.getTokenSource(), 'SERVICE_BOT_PAT');
    assert.equal(balancer.tokenRegistry.tokens.has('OWNER_PR_PAT'), false);

    const ownerClient = await createTokenAwareRetry({
      github: { token: 'fallback' },
      env,
      task: 'pr-creation-as-owner',
      tokenRegistry: balancer,
      getOctokit,
    });
    assert.equal(ownerClient.getTokenSource(), 'OWNER_PR_PAT');
    assert.equal(ownerClient.github.token, 'owner-token');

    // Subsequent general calls must still never select OWNER_PR_PAT even after
    // it has been registered for the exclusive owner task.
    balancer.tokenRegistry.tokens.get('SERVICE_BOT_PAT').rateLimit.remaining = 250;
    balancer.tokenRegistry.tokens.get('SERVICE_BOT_PAT').rateLimit.percentRemaining = 5;
    const generalAfter = await createTokenAwareRetry({
      github: { token: 'fallback' },
      env,
      tokenRegistry: balancer,
      getOctokit,
    });
    assert.equal(generalAfter.getTokenSource(), 'SERVICE_BOT_PAT');

    // When all non-exclusive tokens are exhausted, general retry must NOT fall
    // back to the registered OWNER_PR_PAT even at full capacity.
    balancer.tokenRegistry.tokens.get('SERVICE_BOT_PAT').rateLimit.remaining = 0;
    balancer.tokenRegistry.tokens.get('SERVICE_BOT_PAT').rateLimit.percentRemaining = 0;
    const generalExhausted = await createTokenAwareRetry({
      github: { token: 'fallback' },
      env,
      tokenRegistry: balancer,
      getOctokit,
    });
    assert.equal(generalExhausted.getTokenSource(), null);
    assert.equal(generalExhausted.github.token, 'fallback');

    const attemptedTokens = [];
    await assert.rejects(
      async () => generalExhausted.withRetry(
        async (client) => {
          attemptedTokens.push(client.token);
          const error = new Error('API rate limit exceeded');
          error.status = 403;
          error.response = { headers: { 'x-ratelimit-remaining': '0' } };
          throw error;
        },
        { maxRetries: 1, initialDelay: 1 },
      ),
      /API rate limit exceeded/,
    );
    assert.deepEqual(attemptedTokens, ['fallback']);
  } finally {
    balancer.tokenRegistry.tokens.clear();
    balancer.tokenRegistry.lastRefresh = 0;
  }
});

test('createTokenAwareRetry registers OWNER_PR_PAT from TOKEN_ROTATION_JSON on demand for exclusive tasks', async () => {
  const balancer = require(path.join(__dirname, '../token_load_balancer'));
  balancer.tokenRegistry.tokens.clear();
  balancer.tokenRegistry.lastRefresh = Date.now();
  try {
    const env = {
      SERVICE_BOT_PAT: 'service-token',
      TOKEN_ROTATION_JSON: JSON.stringify({
        pats: [{ id: 'OWNER_PR_PAT', token: 'owner-json-token' }],
      }),
    };
    const getOctokit = (token) => ({ token });

    const generalClient = await createTokenAwareRetry({
      github: { token: 'fallback' },
      env,
      tokenRegistry: balancer,
      getOctokit,
    });
    assert.equal(generalClient.getTokenSource(), 'SERVICE_BOT_PAT');
    assert.equal(balancer.tokenRegistry.tokens.has('OWNER_PR_PAT'), false);

    const ownerClient = await createTokenAwareRetry({
      github: { token: 'fallback' },
      env,
      task: 'pr-creation-as-owner',
      tokenRegistry: balancer,
      getOctokit,
    });
    assert.equal(ownerClient.getTokenSource(), 'OWNER_PR_PAT');
    assert.equal(ownerClient.github.token, 'owner-json-token');
  } finally {
    balancer.tokenRegistry.tokens.clear();
    balancer.tokenRegistry.lastRefresh = 0;
  }
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

test('withRetry attributes headerless GraphQL calls to the GraphQL budget', async () => {
  const usageCalls = [];
  await withRetry(
    async () => ({ data: { ok: true } }),
    {
      github: {},
      tokenRegistry: {
        updateTokenUsage: (...args) => usageCalls.push(args),
      },
      tokenSource: 'SERVICE_BOT_PAT',
      rateResource: 'graphql',
      maxRetries: 0,
    }
  );
  assert.deepEqual(usageCalls, [['SERVICE_BOT_PAT', 1, 'graphql']]);
});

test('withRetry debits unknown partial headers but preserves an authoritative zero', async () => {
  const usageCalls = [];
  const headerCalls = [];
  const tokenRegistry = {
    updateFromHeaders: (...args) => headerCalls.push(args),
    updateTokenUsage: (...args) => usageCalls.push(args),
  };
  await withRetry(async () => ({ headers: { 'x-ratelimit-reset': '123' } }), {
    github: {}, tokenRegistry, tokenSource: 'SERVICE_BOT_PAT', rateResource: 'graphql', maxRetries: 0,
  });
  await assert.rejects(withRetry(async () => {
    const error = new Error('failed');
    error.response = { headers: { 'x-ratelimit-remaining': '0' } };
    throw error;
  }, {
    github: {}, tokenRegistry, tokenSource: 'SERVICE_BOT_PAT', rateResource: 'graphql', maxRetries: 0,
  }), /failed/);
  assert.deepEqual(headerCalls, [[
    'SERVICE_BOT_PAT', { 'x-ratelimit-remaining': '0' }, 'graphql',
  ]]);
  assert.deepEqual(usageCalls, [['SERVICE_BOT_PAT', 1, 'graphql']]);
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

test('computeRetryDelayMs honors Retry-After beyond exponential maxDelay', () => {
  const delayMs = computeRetryDelayMs({
    error: { response: { headers: { 'retry-after': '120' } } },
    attempt: 0,
    baseDelay: 1000,
    maxDelay: 30_000,
    backoffFn: () => 1000,
  });
  assert.equal(delayMs, 120_000);
});

test('createGithubFetchRequester preserves rate-limit headers on HTTP errors', async () => {
  const requester = createGithubFetchRequester({
    token: 'test-token',
    fetchImpl: async () => ({
      ok: false,
      status: 403,
      text: async () => JSON.stringify({ message: 'Resource not accessible by integration' }),
      headers: {
        forEach(callback) {
          callback('90', 'retry-after');
          callback('0', 'x-ratelimit-remaining');
        },
      },
    }),
  });

  await assert.rejects(
    () => requester('GET', '/repos/o/r'),
    (error) => {
      assert.equal(error.response?.headers?.['retry-after'], '90');
      assert.equal(error.response?.headers?.['x-ratelimit-remaining'], '0');
      return true;
    },
  );
});

test('createGithubFetchRequester retries GET network failures', async () => {
  let attempts = 0;
  const requester = createGithubFetchRequester({
    token: 'test-token',
    fetchImpl: async () => {
      attempts += 1;
      if (attempts === 1) {
        const error = new TypeError('fetch failed');
        error.cause = { code: 'ECONNRESET' };
        throw error;
      }
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify({ ok: true }),
        headers: new Map(),
      };
    },
  });

  const data = await requester('GET', '/repos/o/r');
  assert.equal(data.ok, true);
  assert.equal(attempts, 2);
});

test('classifyError treats fetch network failures as transient', () => {
  const error = new TypeError('fetch failed');
  error.cause = { code: 'ECONNRESET' };
  assert.equal(classifyError(error).category, ERROR_CATEGORIES.transient);
});

test('checkRateLimitStatus works on createRateLimitedGithub wrapped client', async () => {
  const { createRateLimitedGithub } = require('../github-rate-limited-wrapper.js');

  const github = {
    rest: {
      rateLimit: {
        get: async () => ({
          data: {
            resources: {
              core: { remaining: 4728, limit: 5000, reset: 1_700_000_000 },
            },
          },
        }),
      },
    },
    request: function request() {},
    hook: {},
  };

  const wrapped = await createRateLimitedGithub({ github, env: {} });
  const tokenSourceDescriptor = Object.getOwnPropertyDescriptor(wrapped, '__getTokenSource');
  assert.ok(tokenSourceDescriptor);
  assert.equal(wrapped.__getTokenSource, tokenSourceDescriptor.value);
  const originalTokenSource = tokenSourceDescriptor.value();

  const status = await checkRateLimitStatus(wrapped, {
    threshold: 0,
    reserveFraction: 0.15,
    estimatedCost: 100,
    failOpen: false,
    env: {},
  });
  assert.equal(status.safe, true);
  assert.equal(status.credentialPoolId, originalTokenSource);
});

function response({ ok, status, body }) {
  return { ok, status, text: async () => body };
}

test('resolveMaxRetries uses operation-specific overrides', () => {
  const limits = { read: 4, unknown: 1 };
  assert.equal(resolveMaxRetries('read', limits), 4);
  assert.equal(resolveMaxRetries('write', limits), 1);
});

test('computeRetryDelayMs respects Retry-After header', () => {
  const delay = computeRetryDelayMs({
    error: { response: { headers: { 'Retry-After': '12' } } },
    attempt: 0,
    baseDelay: 1000,
    maxDelay: 30000,
    backoffFn: () => 5000,
  });
  assert.equal(delay, 12000);
});

test('computeRetryDelayMs uses rate limit reset when remaining is 0', () => {
  const nowMs = 1_700_000_000_000;
  const resetSeconds = Math.floor(nowMs / 1000) + 10;
  const delay = computeRetryDelayMs({
    error: { response: { headers: { 'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': String(resetSeconds) } } },
    attempt: 0,
    baseDelay: 1000,
    maxDelay: 30000,
    backoffFn: () => 5000,
    nowMs,
  });
  assert.equal(delay, 11000);
});

test('withGithubApiRetry retries transient errors then succeeds', async () => {
  let attempts = 0;
  const delays = [];
  const result = await withGithubApiRetry(
    async () => {
      attempts += 1;
      if (attempts < 3) {
        const error = new Error('Service unavailable');
        error.status = 503;
        throw error;
      }
      return 'ok';
    },
    {
      operation: 'read',
      maxRetriesByOperation: { read: 3, unknown: 0 },
      sleep: async (ms) => {
        delays.push(ms);
      },
      backoffFn: () => 1234,
    }
  );

  assert.equal(result, 'ok');
  assert.equal(attempts, 3);
  assert.deepEqual(delays, [1234, 1234]);
});

test('withGithubApiRetry does not retry non-transient errors', async () => {
  let attempts = 0;
  await assert.rejects(
    () =>
      withGithubApiRetry(
        async () => {
          attempts += 1;
          const error = new Error('Bad credentials');
          error.status = 401;
          throw error;
        },
        {
          operation: 'read',
          maxRetriesByOperation: { read: 3, unknown: 0 },
          sleep: async () => {},
          backoffFn: () => 1234,
        }
      ),
    /Bad credentials/
  );
  assert.equal(attempts, 1);
});

test('withGithubApiRetry logs retry context', async () => {
  let attempts = 0;
  const warnings = [];

  const result = await withGithubApiRetry(
    async () => {
      attempts += 1;
      if (attempts === 1) {
        const error = new Error('Service unavailable');
        error.status = 503;
        throw error;
      }
      return 'ok';
    },
    {
      operation: 'read',
      label: 'fetch data',
      maxRetriesByOperation: { read: 1, unknown: 0 },
      sleep: async () => {},
      backoffFn: () => 1234,
      core: {
        warning: (message) => warnings.push(message),
      },
    }
  );

  assert.equal(result, 'ok');
  assert.equal(attempts, 2);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /Retrying fetch data/);
  assert.match(warnings[0], /operation=read/);
  assert.match(warnings[0], /category=transient/);
  assert.match(warnings[0], /attempt=1\/2/);
  assert.match(warnings[0], /delayMs=1234/);
});

test('fetch requester retries reads but never retries uncertain writes', async () => {
  let readAttempts = 0;
  const read = createGithubFetchRequester({
    token: 'test-token',
    apiUrl: 'https://example.invalid',
    fetchImpl: async () => {
      readAttempts += 1;
      return readAttempts === 1
        ? response({ ok: false, status: 503, body: '{"message":"retry"}' })
        : response({ ok: true, status: 200, body: '{"ok":true}' });
    },
  });
  assert.deepEqual(await read('GET', '/resource'), { ok: true });
  assert.equal(readAttempts, 2);

  let writeAttempts = 0;
  const write = createGithubFetchRequester({
    token: 'test-token',
    apiUrl: 'https://example.invalid',
    fetchImpl: async () => {
      writeAttempts += 1;
      return response({ ok: false, status: 503, body: '{"message":"uncertain"}' });
    },
  });
  await assert.rejects(() => write('PUT', '/resource', { value: 1 }), /503/);
  assert.equal(writeAttempts, 1);
});

test('fetch requester preserves status for non-JSON errors', async () => {
  const request = createGithubFetchRequester({
    token: 'test-token',
    apiUrl: 'https://example.invalid',
    fetchImpl: async () => response({ ok: false, status: 502, body: '<html>bad gateway</html>' }),
  });
  await assert.rejects(
    () => request('POST', '/resource'),
    (error) => error.status === 502 && error.response?.status === 502,
  );
});

test('fetch requester deadline remains active through response body reads', async () => {
  const request = createGithubFetchRequester({
    token: 'test-token',
    apiUrl: 'https://example.invalid',
    timeoutMs: 5,
    fetchImpl: async (_url, options) => ({
      ok: true,
      status: 200,
      text: () => new Promise((_resolve, reject) => {
        options.signal.addEventListener('abort', () => {
          const error = new Error('body read aborted');
          error.name = 'AbortError';
          reject(error);
        }, { once: true });
      }),
    }),
  });
  await assert.rejects(() => request('POST', '/resource'), /body read aborted/);
});
