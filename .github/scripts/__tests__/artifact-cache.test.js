'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  deriveCachePlan,
  deriveWindow,
  discoverCommand,
  parseBoolean,
  selectArtifact,
} = require('../../actions/artifact-cache/artifact_cache');

test('derives weekly cache key using ISO run window', () => {
  const plan = deriveCachePlan({
    cacheKeyBase: 'weekly-metrics',
    artifactName: 'agent-weekly-metrics',
    now: '2026-05-06T12:00:00Z',
    windowResolution: 'weekly',
  });

  assert.equal(plan.cacheKey, 'weekly-metrics-2026-W19');
  assert.equal(plan.window.start.toISOString(), '2026-05-04T00:00:00.000Z');
  assert.equal(plan.window.end.toISOString(), '2026-05-11T00:00:00.000Z');
  assert.equal(
    plan.artifactPath,
    path.join('.artifact-cache', 'weekly-metrics', '2026-W19', 'agent-weekly-metrics'),
  );
});

test('derives daily and run cache keys', () => {
  assert.equal(
    deriveCachePlan({
      cacheKeyBase: 'ci-artifacts',
      artifactName: 'coverage',
      now: '2026-05-06T23:30:00Z',
      windowResolution: 'daily',
    }).cacheKey,
    'ci-artifacts-2026-05-06',
  );

  const runPlan = deriveCachePlan({
    cacheKeyBase: 'ci-artifacts',
    artifactName: 'coverage',
    windowResolution: 'run',
    runId: '12345',
  });
  assert.equal(runPlan.cacheKey, 'ci-artifacts-run-12345');
  assert.equal(runPlan.window.label, 'run-12345');
});

test('supports explicit artifact path for workflow compatibility', () => {
  const plan = deriveCachePlan({
    cacheKeyBase: 'coverage',
    artifactName: 'gate-coverage',
    artifactPath: 'coverage_artifacts/payload',
    now: '2026-05-06T12:00:00Z',
  });

  assert.equal(plan.artifactPath, 'coverage_artifacts/payload');
});

test('selects newest matching artifact in the active window', () => {
  const window = deriveWindow({
    resolution: 'weekly',
    now: '2026-05-06T12:00:00Z',
  });
  const artifact = selectArtifact([
    {
      id: 1,
      name: 'gate-coverage',
      created_at: '2026-04-30T00:00:00Z',
      workflow_run: { id: 100, head_branch: 'main' },
    },
    {
      id: 2,
      name: 'gate-coverage',
      created_at: '2026-05-05T00:00:00Z',
      workflow_run: { id: 101, head_branch: 'feature' },
    },
    {
      id: 3,
      name: 'gate-coverage',
      created_at: '2026-05-06T00:00:00Z',
      workflow_run: { id: 102, head_branch: 'main' },
    },
    {
      id: 4,
      name: 'other',
      created_at: '2026-05-07T00:00:00Z',
      workflow_run: { id: 103, head_branch: 'main' },
    },
  ], {
    artifactName: 'gate-coverage',
    window,
    producerBranch: 'main',
  });

  assert.equal(artifact.id, 3);
});

test('can scope artifact discovery to an exact producer run', () => {
  const window = deriveWindow({
    resolution: 'weekly',
    now: '2026-05-06T12:00:00Z',
  });
  const artifact = selectArtifact([
    {
      id: 1,
      name: 'gate-coverage',
      created_at: '2026-05-06T02:00:00Z',
      workflow_run: { id: 100, head_branch: 'main' },
    },
    {
      id: 2,
      name: 'gate-coverage',
      created_at: '2026-05-06T03:00:00Z',
      workflow_run: { id: 101, head_branch: 'main' },
    },
  ], {
    artifactName: 'gate-coverage',
    window,
    producerRunId: '100',
    producerBranch: 'main',
  });

  assert.equal(artifact.id, 1);
});

test('ignores expired artifacts and run-window mismatches', () => {
  const runWindow = deriveWindow({
    resolution: 'run',
    runId: '555',
  });
  const artifact = selectArtifact([
    {
      id: 1,
      name: 'selftest-report',
      created_at: '2026-05-06T00:00:00Z',
      workflow_run: { id: 444 },
    },
    {
      id: 2,
      name: 'selftest-report',
      created_at: '2026-05-06T00:00:00Z',
      expired: true,
      workflow_run: { id: 555 },
    },
    {
      id: 3,
      name: 'selftest-report',
      created_at: '2026-05-06T00:00:00Z',
      workflow_run: { id: 555 },
    },
  ], {
    artifactName: 'selftest-report',
    window: runWindow,
    runId: '555',
  });

  assert.equal(artifact.id, 3);
});

test('returns null on cache miss so producers can fall through', () => {
  const artifact = selectArtifact([], {
    artifactName: 'missing',
    window: deriveWindow({ resolution: 'daily', now: '2026-05-06T00:00:00Z' }),
  });

  assert.equal(artifact, null);
});

test('non-fail-fast discovery falls through when artifact listing is forbidden', async () => {
  const outputPath = path.join(
    fs.mkdtempSync(path.join(os.tmpdir(), 'artifact-cache-test-')),
    'outputs',
  );
  const originalFetch = global.fetch;
  const originalEnv = { ...process.env };
  global.fetch = async () => ({
    ok: false,
    status: 403,
    statusText: 'Forbidden',
    headers: { get: () => '' },
  });
  Object.assign(process.env, {
    ARTIFACT_CACHE_NOW: '2026-05-06T12:00:00Z',
    GITHUB_OUTPUT: outputPath,
    GITHUB_REPOSITORY: 'owner/repo',
    GITHUB_RUN_ID: '123',
    GITHUB_TOKEN: 'token',
    INPUT_ARTIFACT_NAME: 'coverage',
    INPUT_CACHE_KEY_BASE: 'ci-artifacts',
    INPUT_FAIL_FAST: 'false',
    INPUT_WINDOW_RESOLUTION: 'daily',
  });

  try {
    await discoverCommand();
    const outputs = fs.readFileSync(outputPath, 'utf8');
    assert.match(outputs, /artifact-found=false/);
    assert.match(outputs, /artifact-id=/);
    assert.match(outputs, /run-id=/);
  } finally {
    global.fetch = originalFetch;
    for (const key of Object.keys(process.env)) {
      if (!(key in originalEnv)) {
        delete process.env[key];
      }
    }
    Object.assign(process.env, originalEnv);
  }
});

test('fail-fast discovery errors when artifact listing is forbidden', async () => {
  const outputPath = path.join(
    fs.mkdtempSync(path.join(os.tmpdir(), 'artifact-cache-test-')),
    'outputs',
  );
  const originalFetch = global.fetch;
  const originalEnv = { ...process.env };
  global.fetch = async () => ({
    ok: false,
    status: 403,
    statusText: 'Forbidden',
    headers: { get: () => '' },
  });
  Object.assign(process.env, {
    ARTIFACT_CACHE_NOW: '2026-05-06T12:00:00Z',
    GITHUB_OUTPUT: outputPath,
    GITHUB_REPOSITORY: 'owner/repo',
    GITHUB_RUN_ID: '123',
    GITHUB_TOKEN: 'token',
    INPUT_ARTIFACT_NAME: 'coverage',
    INPUT_CACHE_KEY_BASE: 'ci-artifacts',
    INPUT_FAIL_FAST: 'true',
    INPUT_WINDOW_RESOLUTION: 'daily',
  });

  try {
    await assert.rejects(discoverCommand(), /Failed to list artifacts: 403 Forbidden/);
    assert.equal(fs.existsSync(outputPath), false);
  } finally {
    global.fetch = originalFetch;
    for (const key of Object.keys(process.env)) {
      if (!(key in originalEnv)) {
        delete process.env[key];
      }
    }
    Object.assign(process.env, originalEnv);
  }
});

test('parses fail-fast boolean inputs strictly', () => {
  assert.equal(parseBoolean('true'), true);
  assert.equal(parseBoolean('false'), false);
  assert.equal(parseBoolean('', true), true);
  assert.throws(() => parseBoolean('sometimes'), /Invalid boolean value/);
});

test('action metadata exposes required public inputs and outputs', () => {
  const metadata = fs.readFileSync(
    path.join(__dirname, '../../actions/artifact-cache/action.yml'),
    'utf8',
  );

  assert.match(metadata, /cache-key-base:/);
  assert.match(metadata, /window-resolution:/);
  assert.match(metadata, /artifact-name:/);
  assert.match(metadata, /fail-fast:/);
  assert.match(metadata, /producer-run-id:/);
  assert.match(metadata, /producer-branch:/);
  assert.match(metadata, /cache-hit:/);
  assert.match(metadata, /artifact-found:/);
  assert.match(metadata, /artifact-path:/);
  assert.match(metadata, /actions\/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6/);
});
