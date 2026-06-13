const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

test('refreshAllRateLimits accepts an injected Octokit (simulates NODE_PATH action deps)', async () => {
  // The _Octokit injection escape hatch lets tests supply a mock Octokit
  // without fighting Node.js module resolution order (local node_modules
  // always wins over NODE_PATH, so a NODE_PATH-only mock is unreliable).
  const scriptPath = path.resolve(__dirname, '..', 'token_load_balancer.js');
  // Use a fresh require so we don't pollute the module cache of other tests.
  const balancer = require(scriptPath);

  const mockOctokit = class MockOctokit {
    constructor(options) {
      this.auth = options.auth;
      this.rateLimit = {
        get: async () => ({
          data: {
            resources: {
              core: { limit: 5000, remaining: 4999, used: 1, reset: 2000000000 },
            },
          },
        }),
      };
    }
  };

  const errors = [];
  balancer.tokenRegistry.tokens.clear();
  balancer.tokenRegistry.lastRefresh = 0;
  balancer.registerToken({
    id: 'TEST_TOKEN',
    token: 'token',
    type: 'PAT',
    source: 'TEST_TOKEN',
    capabilities: ['read-repo'],
    priority: 5,
  });
  await balancer.refreshAllRateLimits({
    _Octokit: mockOctokit,
    core: {
      error: (message) => errors.push(message),
      warning: (message) => errors.push(message),
      debug: () => {},
    },
  });

  const rateLimit = balancer.tokenRegistry.tokens.get('TEST_TOKEN').rateLimit;
  assert.deepEqual(errors, []);
  assert.equal(rateLimit.remaining, 4999);
  assert.equal(rateLimit.importFailed, undefined);
});

test('invalid credential warning cache defaults outside the repository workspace', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'token-invalid-auth-runner-temp-'));
  const workspaceDir = fs.mkdtempSync(path.join(os.tmpdir(), 'token-invalid-auth-workspace-'));
  const scriptPath = path.resolve(__dirname, '..', 'token_load_balancer.js');
  const balancer = require(scriptPath);

  const previousRunnerTemp = process.env.RUNNER_TEMP;
  const previousWorkspace = process.env.GITHUB_WORKSPACE;
  process.env.RUNNER_TEMP = tempDir;
  process.env.GITHUB_WORKSPACE = workspaceDir;

  try {
    assert.equal(
      balancer.getInvalidAuthWarningCachePath(),
      path.join(tempDir, 'github-token-invalid-auth-warnings.json')
    );
  } finally {
    if (previousRunnerTemp === undefined) {
      delete process.env.RUNNER_TEMP;
    } else {
      process.env.RUNNER_TEMP = previousRunnerTemp;
    }
    if (previousWorkspace === undefined) {
      delete process.env.GITHUB_WORKSPACE;
    } else {
      process.env.GITHUB_WORKSPACE = previousWorkspace;
    }
  }
});

test('invalid credential warnings are cached across node processes', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'token-invalid-auth-cache-'));
  const cachePath = path.join(tempDir, 'invalid-auth-warnings.json');
  const scriptPath = path.resolve(__dirname, '..', 'token_load_balancer.js');

  const runProbe = () => spawnSync(
    process.execPath,
    [
      '-e',
      `
(async () => {
  const fs = require('node:fs');
  const balancer = require(process.argv[1]);
  const cachePath = process.argv[2];
  const warnings = [];
  const debug = [];
  class Octokit {
    constructor() {
      this.rateLimit = {
        get: async () => {
          const error = new Error('Bad credentials');
          error.status = 401;
          throw error;
        }
      };
    }
  }
  const rateLimit = await balancer.checkTokenRateLimit({
    tokenInfo: {
      id: 'BAD_TOKEN',
      token: 'bad-token',
      type: 'PAT',
    },
    Octokit,
    core: {
      warning: (message) => warnings.push(message),
      debug: (message) => debug.push(message),
    },
  });
  const cache = fs.existsSync(cachePath)
    ? JSON.parse(fs.readFileSync(cachePath, 'utf8'))
    : null;
  process.stdout.write(JSON.stringify({ warnings, debug, cache, rateLimit }) + '\\n');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
`,
      scriptPath,
      cachePath,
    ],
    {
      env: {
        ...process.env,
        TOKEN_INVALID_AUTH_WARNING_CACHE: cachePath,
      },
      encoding: 'utf8',
    }
  );

  const first = runProbe();
  assert.equal(first.status, 0, first.stderr);
  const firstResult = JSON.parse(first.stdout);
  assert.equal(firstResult.warnings.length, 1);
  assert.match(firstResult.warnings[0], /BAD_TOKEN has invalid credentials/);
  assert.deepEqual(firstResult.cache.tokens, ['BAD_TOKEN']);
  assert.equal(firstResult.rateLimit.invalidAuth, true);

  const second = runProbe();
  assert.equal(second.status, 0, second.stderr);
  const secondResult = JSON.parse(second.stdout);
  assert.deepEqual(secondResult.warnings, []);
  assert.ok(
    secondResult.debug.some((message) =>
      message.includes('BAD_TOKEN still has invalid credentials')
    )
  );
  assert.deepEqual(secondResult.cache.tokens, ['BAD_TOKEN']);
  assert.equal(secondResult.rateLimit.invalidAuth, true);
});
