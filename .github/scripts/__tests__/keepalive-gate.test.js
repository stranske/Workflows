'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { countActive, evaluateRunCapForPr } = require('../keepalive_gate.js');

// The `details` parameter provides mock run details for getWorkflowRun.
// By default, it is an empty object, so getWorkflowRun will throw a 404 error
// for any runId not explicitly provided in `details`. This is intentional and
// expected behavior for test isolation, simulating the real GitHub API's response.
function makeGithubStub(registry, details = {}, pulls = {}) {
  return {
    rest: {
      actions: {
        listWorkflowRuns: Symbol('listWorkflowRuns'),
        async getWorkflowRun({ run_id: runId }) {
          if (Object.prototype.hasOwnProperty.call(details, runId)) {
            return { data: details[runId] };
          }
          const error = new Error('not found');
          error.status = 404;
          throw error;
        },
      },
      pulls: {
        async get({ pull_number: pullNumber }) {
          if (Object.prototype.hasOwnProperty.call(pulls, pullNumber)) {
            return { data: pulls[pullNumber] };
          }
          const error = new Error('pull not found');
          error.status = 404;
          throw error;
        },
      },
    },
    async paginate(_fn, params) {
      const key = `${params.workflow_id}|${params.status}`;
      const payload = registry[key] || [];
      return payload;
    },
  };
}

test('countActive counts queued and in-progress orchestrator runs without duplication', async () => {
  const registry = {
    'agents-keepalive-loop.yml|queued': [
      { id: 101, pull_requests: [{ number: 42 }] },
      { id: 102, pull_requests: [{ number: 999 }] }, // mismatched PR should be ignored
    ],
    'agents-keepalive-loop.yml|in_progress': [
      { id: 103, pull_requests: [{ number: 42 }] },
      { id: 101, pull_requests: [{ number: 42 }] }, // duplicate id should not double count
    ],
  };
  const github = makeGithubStub(registry);
  const result = await countActive({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 42,
    headSha: 'abc',
    headRef: 'feature/run-cap',
    currentRunId: 9999,
  });

  assert.equal(result.active, 2); // ids 101 and 103
  assert.equal(result.breakdown.get('orchestrator'), 2);
  assert.equal(result.breakdown.get('worker'), undefined);
});

test('countActive optionally includes worker runs when requested', async () => {
  const registry = {
    'agents-keepalive-loop.yml|queued': [
      { id: 201, pull_requests: [{ number: 7 }] },
    ],
    'agents-72-codex-belt-worker.yml|in_progress': [
      { id: 301, pull_requests: [{ number: 7 }] },
    ],
  };
  const github = makeGithubStub(registry);
  const defaultOrchestratorOnly = await countActive({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 7,
  });

  assert.equal(defaultOrchestratorOnly.active, 1);
  assert.equal(defaultOrchestratorOnly.breakdown.get('orchestrator'), 1);
  assert.equal(defaultOrchestratorOnly.breakdown.get('worker'), undefined);

  const withWorker = await countActive({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 7,
    includeWorker: true,
  });

  assert.equal(withWorker.active, 2);
  assert.equal(withWorker.breakdown.get('orchestrator'), 1);
  assert.equal(withWorker.breakdown.get('worker'), 1);
});

test('countActive ignores the current run id to avoid self-counting', async () => {
  const registry = {
    'agents-keepalive-loop.yml|queued': [
      { id: 555, pull_requests: [{ number: 5 }] },
    ],
  };
  const github = makeGithubStub(registry);
  const result = await countActive({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 5,
    headSha: 'sha',
    headRef: 'refs/heads/branch',
    currentRunId: 555,
  });

  assert.equal(result.active, 0);
  assert.equal(result.breakdown.size, 0);
});

test('countActive matches by branch metadata when pull requests array is empty', async () => {
  const registry = {
    'agents-keepalive-loop.yml|queued': [
      { id: 610, head_branch: 'refs/heads/feature/match-me' },
    ],
  };
  const details = {
    610: {
      id: 610,
      head_branch: 'feature/match-me',
      head_sha: 'abc123',
    },
  };
  const github = makeGithubStub(registry, details);
  const result = await countActive({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 8,
    headRef: 'feature/match-me',
    headSha: 'abc123',
  });

  assert.equal(result.active, 1);
  assert.equal(result.breakdown.get('orchestrator'), 1);
});

test('countActive matches runs tagged via concurrency group', async () => {
  const registry = {
    'agents-keepalive-loop.yml|queued': [
      {
        id: 615,
        head_branch: 'main',
        concurrency: 'keepalive-pr-42-trace1234',
        pull_requests: [],
      },
    ],
  };
  const github = makeGithubStub(registry);
  const result = await countActive({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 42,
    headRef: 'codex/issue-42',
    headSha: 'non-matching-sha',
  });

  assert.equal(result.active, 1);
  assert.equal(result.breakdown.get('orchestrator'), 1);
});

test('countActive treats recently completed runs as active within lookback window', async () => {
  const registry = {
    'agents-keepalive-loop.yml|completed': [
      {
        id: 9100,
        pull_requests: [{ number: 77 }],
        updated_at: '2025-11-16T20:59:30Z',
      },
    ],
  };
  const github = makeGithubStub(registry);
  const originalNow = Date.now;
  Date.now = () => Date.parse('2025-11-16T21:00:00Z');
  try {
    const result = await countActive({
      github,
      owner: 'stranske',
      repo: 'Workflows',
      prNumber: 77,
      completedLookbackSeconds: 300,
    });

    assert.equal(result.active, 1);
    assert.equal(result.breakdown.get('orchestrator_recent'), 1);
  } finally {
    Date.now = originalNow;
  }
});

test('countActive counts long-running dispatches that complete inside the lookback', async () => {
  let detailCalls = 0;
  const github = {
    rest: {
      actions: {
        listWorkflowRuns: Symbol('listWorkflowRuns'),
        async getWorkflowRun() {
          detailCalls += 1;
          return {
            data: {
              inputs: {
                pr_number: '77',
              },
            },
          };
        },
      },
    },
    async paginate(_fn, params) {
      if (params.workflow_id === 'agents-keepalive-loop.yml' && params.status === 'completed') {
        assert.equal(params.created, undefined);
        return [
          {
            id: 9150,
            event: 'workflow_dispatch',
            pull_requests: [],
            created_at: '2025-11-16T20:00:00Z',
            updated_at: '2025-11-16T20:59:30Z',
          },
        ];
      }
      return [];
    },
  };
  const originalNow = Date.now;
  Date.now = () => Date.parse('2025-11-16T21:00:00Z');
  try {
    const result = await countActive({
      github,
      owner: 'stranske',
      repo: 'Workflows',
      prNumber: 77,
      completedLookbackSeconds: 300,
    });

    assert.equal(result.active, 1);
    assert.equal(result.breakdown.get('orchestrator_recent'), 1);
    assert.equal(detailCalls, 1);
  } finally {
    Date.now = originalNow;
  }
});

test('countActive ignores completed runs outside the lookback window', async () => {
  const registry = {
    'agents-keepalive-loop.yml|completed': [
      {
        id: 9200,
        pull_requests: [{ number: 78 }],
        updated_at: '2025-11-16T20:40:00Z',
      },
    ],
  };
  const github = makeGithubStub(registry);
  const originalNow = Date.now;
  Date.now = () => Date.parse('2025-11-16T21:00:00Z');
  try {
    const result = await countActive({
      github,
      owner: 'stranske',
      repo: 'Workflows',
      prNumber: 78,
      completedLookbackSeconds: 300,
    });

    assert.equal(result.active, 0);
    assert.equal(result.breakdown.size, 0);
  } finally {
    Date.now = originalNow;
  }
});

test('countActive does not fetch run details for completed runs older than the lookback', async () => {
  let detailCalls = 0;
  const capturedParams = [];
  const github = {
    rest: {
      actions: {
        listWorkflowRuns: Symbol('listWorkflowRuns'),
        async getWorkflowRun() {
          detailCalls += 1;
          return {
            data: {
              inputs: {
                pr_number: '79',
              },
            },
          };
        },
      },
    },
    async paginate(_fn, params) {
      capturedParams.push(params);
      if (params.workflow_id === 'agents-keepalive-loop.yml' && params.status === 'completed') {
        return [
          {
            id: 9300,
            event: 'workflow_dispatch',
            pull_requests: [],
            updated_at: '2025-11-16T20:40:00Z',
          },
        ];
      }
      return [];
    },
  };
  const originalNow = Date.now;
  Date.now = () => Date.parse('2025-11-16T21:00:00Z');
  try {
    const result = await countActive({
      github,
      owner: 'stranske',
      repo: 'Workflows',
      prNumber: 79,
      completedLookbackSeconds: 300,
    });

    assert.equal(result.active, 0);
    assert.equal(detailCalls, 0);
    const completedParams = capturedParams.find((params) => params.status === 'completed');
    assert.equal(completedParams.created, undefined);
  } finally {
    Date.now = originalNow;
  }
});

test('evaluateRunCapForPr caches pull request fetches', async () => {
  let pullCalls = 0;
  const github = {
    rest: {
      actions: {
        listWorkflowRuns: Symbol('listWorkflowRuns'),
        async getWorkflowRun() {
          const error = new Error('not found');
          error.status = 404;
          throw error;
        },
      },
      pulls: {
        async get() {
          pullCalls += 1;
          return {
            data: {
              labels: [],
              head: { sha: 'abc123', ref: 'feature/cache-test' },
            },
          };
        },
      },
    },
    async paginate() {
      return [];
    },
  };

  const args = {
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 12,
    headSha: 'abc123',
    headRef: 'feature/cache-test',
  };

  await evaluateRunCapForPr(args);
  await evaluateRunCapForPr(args);

  assert.equal(pullCalls, 1);
});

test('evaluateRunCapForPr does not cache empty pull responses', async () => {
  let pullCalls = 0;
  const github = {
    rest: {
      actions: {
        listWorkflowRuns: Symbol('listWorkflowRuns'),
        async getWorkflowRun() {
          const error = new Error('not found');
          error.status = 404;
          throw error;
        },
      },
      pulls: {
        async get() {
          pullCalls += 1;
          return { data: null };
        },
      },
    },
    async paginate() {
      return [];
    },
  };

  const args = {
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 77,
  };

  const first = await evaluateRunCapForPr(args);
  const second = await evaluateRunCapForPr(args);

  assert.equal(pullCalls, 2);
  assert.equal(first.reason, 'pr-fetch-failed');
  assert.equal(second.reason, 'pr-fetch-failed');
});

test('evaluateRunCapForPr returns ok when active runs are below cap', async () => {
  const registry = {
    'agents-keepalive-loop.yml|queued': [
      { id: 701, pull_requests: [{ number: 11 }] },
    ],
  };
  const pulls = {
    11: {
      number: 11,
      head: { ref: 'feature/run-cap', sha: 'abc123' },
      labels: [
        { name: 'agents:max-runs:3' },
      ],
    },
  };
  const github = makeGithubStub(registry, {}, pulls);
  const result = await evaluateRunCapForPr({
    core: { warning: () => {} },
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 11,
  });

  assert.equal(result.ok, true);
  assert.equal(result.runCap, 3);
  assert.equal(result.activeRuns, 1);
  assert.deepEqual(result.breakdown, { orchestrator: 1 });
});

test('evaluateRunCapForPr enforces cap using default when label absent', async () => {
  const registry = {
    'agents-keepalive-loop.yml|queued': [
      { id: 801, pull_requests: [{ number: 12 }] },
    ],
  };
  const pulls = {
    12: {
      number: 12,
      head: { ref: 'feature/default-cap', sha: 'def456' },
      labels: [],
    },
  };
  const github = makeGithubStub(registry, {}, pulls);
  const result = await evaluateRunCapForPr({
    core: { warning: () => {} },
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 12,
  });

  assert.equal(result.ok, false);
  assert.equal(result.reason, 'run-cap-reached');
  assert.equal(result.runCap, 1);
  assert.equal(result.activeRuns, 1);
});

test('evaluateRunCapForPr respects labelled cap across successive attempts', async () => {
  const registry = {};
  const pulls = {
    50: {
      number: 50,
      head: { ref: 'feature/run-cap', sha: 'abc999' },
      labels: [{ name: 'agents:max-runs:2' }],
    },
  };
  const github = makeGithubStub(registry, {}, pulls);
  const baseArgs = {
    core: { warning: () => {} },
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 50,
  };

  // Label sets cap to 2 explicitly, overriding the default of 1
  let result = await evaluateRunCapForPr({ ...baseArgs, currentRunId: 900 });
  assert.equal(result.ok, true);
  assert.equal(result.runCap, 2);
  assert.equal(result.activeRuns, 0);

  registry['agents-keepalive-loop.yml|queued'] = [
    { id: 900, pull_requests: [{ number: 50 }] },
    { id: 901, pull_requests: [{ number: 50 }] },
  ];

  result = await evaluateRunCapForPr({ ...baseArgs, currentRunId: 901 });
  assert.equal(result.ok, true);
  assert.equal(result.activeRuns, 1);

  registry['agents-keepalive-loop.yml|queued'] = [
    { id: 900, pull_requests: [{ number: 50 }] },
    { id: 901, pull_requests: [{ number: 50 }] },
    { id: 902, pull_requests: [{ number: 50 }] },
  ];

  result = await evaluateRunCapForPr({ ...baseArgs, currentRunId: 902 });
  assert.equal(result.ok, false);
  assert.equal(result.reason, 'run-cap-reached');
  assert.equal(result.activeRuns, 2);
});

test('evaluateRunCapForPr reuses cached pull request data across calls', async () => {
  const pulls = {
    88: {
      number: 88,
      head: { ref: 'feature/cache', sha: 'abc888' },
      labels: [],
    },
  };
  let getCalls = 0;
  const github = {
    rest: {
      actions: {
        listWorkflowRuns: Symbol('listWorkflowRuns'),
        async getWorkflowRun() {
          const error = new Error('not found');
          error.status = 404;
          throw error;
        },
      },
      pulls: {
        async get({ pull_number: pullNumber }) {
          getCalls += 1;
          if (Object.prototype.hasOwnProperty.call(pulls, pullNumber)) {
            return { data: pulls[pullNumber] };
          }
          const error = new Error('pull not found');
          error.status = 404;
          throw error;
        },
      },
    },
    async paginate() {
      return [];
    },
  };

  const baseArgs = {
    core: { warning: () => {} },
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 88,
  };

  await evaluateRunCapForPr(baseArgs);
  await evaluateRunCapForPr(baseArgs);

  assert.equal(getCalls, 1);
});

test('managed Gate child uses the exact upstream attempt instead of its default-branch SHA', async () => {
  const headSha = 'actual-pr-head';
  const registry = {
    'agents-81-gate-followups.yml|pending': [
      { id: 41, event: 'workflow_run', head_sha: 'default',
        display_title: 'keepalive-gate/v1 run=20 attempt=2 pr=unbound', pull_requests: [] },
    ],
    'agents-81-gate-followups.yml|in_progress': [
      { id: 42, event: 'workflow_run', head_sha: headSha,
        display_title: 'keepalive-gate/v1 run=21 attempt=1 pr=99', pull_requests: [] },
      { id: 43, event: 'workflow_run', head_sha: headSha,
        display_title: 'Agents Gate Followups', pull_requests: [] },
      { id: 44, event: 'workflow_dispatch', head_sha: headSha,
        display_title: 'keepalive-dispatch/v2 ordinary pr=99', pull_requests: [] },
    ],
  };
  const github = makeGithubStub(registry);
  const requested = [];
  github.rest.actions.getWorkflowRunAttempt = async (args) => {
    requested.push([args.run_id, args.attempt_number]);
    return { data: { id: 20, path: '.github/workflows/pr-00-gate.yml', run_attempt: 2, head_sha: headSha, pull_requests: [] } };
  };
  const args = { github, owner: 'stranske', repo: 'Trend_Model_Project', prNumber: 42, headSha };
  assert.deepEqual((await countActive(args)).runIds, new Set([41]));
  assert.deepEqual(requested, [[20, 2]]);
  assert.equal((await countActive({ ...args, currentRunId: 41 })).active, 0);
  github.rest.actions.getWorkflowRunAttempt = async () => ({ data: { id: 20, run_attempt: 3 } });
  assert.match((await countActive(args)).error, /Gate attempt identity/);
});

test('a linked recent managed attempt consumes a slot only when a worker started or is unknown', async () => {
  const workflow = 'agents-81-gate-followups.yml';
  const headSha = 'a'.repeat(40);
  const completed = [51, 52, 53].map((id) => ({
    id, head_sha: headSha, event: 'workflow_dispatch', display_title: 'keepalive-dispatch/v2 ordinary pr=42',
    updated_at: new Date().toISOString(), run_attempt: 2,
  }));
  const github = makeGithubStub({ [`${workflow}|completed`]: completed });
  const originalPaginate = github.paginate;
  const jobs = Symbol('listJobsForWorkflowRunAttempt');
  github.rest.actions.listJobsForWorkflowRunAttempt = jobs;
  github.rest.repos = { async getContent({ ref }) {
    assert.equal(ref, headSha);
    return { data: { type: 'file', encoding: 'base64', content: Buffer.from(
      'agents:\n  codex:\n    capabilities:\n      pr_keepalive: true\n',
    ).toString('base64') } };
  } };
  github.paginate = async (endpoint, params) => {
    if (endpoint !== jobs) return originalPaginate(endpoint, params);
    assert.equal(params.attempt_number, 2);
    if (params.run_id === 53) return [];
    return [{ name: 'Keepalive next task (Codex)', status: 'completed',
      conclusion: params.run_id === 51 ? 'skipped' : 'success',
      steps: [{ name: 'Run Codex', status: 'completed', conclusion: 'success' }] }];
  };
  const result = await countActive({ github, owner: 'stranske', repo: 'Trend_Model_Project',
    prNumber: 42, completedLookbackSeconds: 300 });
  assert.deepEqual(result.runIds, new Set([52, 53]));
});

test('a failed maintained producer lookup does not admit a worker', async () => {
  const pulls = { 42: { number: 42, head: { sha: 'head' }, labels: [] } };
  const github = makeGithubStub({}, {}, pulls);
  github.paginate = async (_endpoint, params) => {
    assert.equal(params.workflow_id, 'agents-81-gate-followups.yml');
    throw Object.assign(new Error('Forbidden'), { status: 403 });
  };
  const result = await evaluateRunCapForPr({ github, owner: 'stranske', repo: 'Trend_Model_Project', prNumber: 42 });
  assert.equal(result.ok, false);
  assert.equal(result.reason, 'run-cap-unavailable');
});
