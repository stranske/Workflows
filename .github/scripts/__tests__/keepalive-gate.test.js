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
    'agents-70-orchestrator.yml|queued': [
      { id: 101, pull_requests: [{ number: 42 }] },
      { id: 102, pull_requests: [{ number: 999 }] }, // mismatched PR should be ignored
    ],
    'agents-70-orchestrator.yml|in_progress': [
      { id: 103, pull_requests: [{ number: 42 }] },
      { id: 101, pull_requests: [{ number: 42 }] }, // duplicate id should not double count
    ],
  };
  const github = makeGithubStub(registry);
  const result = await countActive({
    github,
    owner: 'stranske',
    repo: 'Trend_Model_Project',
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
    'agents-70-orchestrator.yml|queued': [
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
    repo: 'Trend_Model_Project',
    prNumber: 7,
  });

  assert.equal(defaultOrchestratorOnly.active, 1);
  assert.equal(defaultOrchestratorOnly.breakdown.get('orchestrator'), 1);
  assert.equal(defaultOrchestratorOnly.breakdown.get('worker'), undefined);

  const withWorker = await countActive({
    github,
    owner: 'stranske',
    repo: 'Trend_Model_Project',
    prNumber: 7,
    includeWorker: true,
  });

  assert.equal(withWorker.active, 2);
  assert.equal(withWorker.breakdown.get('orchestrator'), 1);
  assert.equal(withWorker.breakdown.get('worker'), 1);
});

test('countActive ignores the current run id to avoid self-counting', async () => {
  const registry = {
    'agents-70-orchestrator.yml|queued': [
      { id: 555, pull_requests: [{ number: 5 }] },
    ],
  };
  const github = makeGithubStub(registry);
  const result = await countActive({
    github,
    owner: 'stranske',
    repo: 'Trend_Model_Project',
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
    'agents-70-orchestrator.yml|queued': [
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
    repo: 'Trend_Model_Project',
    prNumber: 8,
    headRef: 'feature/match-me',
    headSha: 'abc123',
  });

  assert.equal(result.active, 1);
  assert.equal(result.breakdown.get('orchestrator'), 1);
});

test('countActive matches runs tagged via concurrency group', async () => {
  const registry = {
    'agents-70-orchestrator.yml|queued': [
      {
        id: 615,
        head_branch: 'phase-2-dev',
        concurrency: 'agents-70-orchestrator-42-keepalive-trace1234',
        pull_requests: [],
      },
    ],
  };
  const github = makeGithubStub(registry);
  const result = await countActive({
    github,
    owner: 'stranske',
    repo: 'Trend_Model_Project',
    prNumber: 42,
    headRef: 'codex/issue-42',
    headSha: 'non-matching-sha',
  });

  assert.equal(result.active, 1);
  assert.equal(result.breakdown.get('orchestrator'), 1);
});

test('countActive treats recently completed runs as active within lookback window', async () => {
  const registry = {
    'agents-70-orchestrator.yml|completed': [
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
      repo: 'Trend_Model_Project',
      prNumber: 77,
      completedLookbackSeconds: 300,
    });

    assert.equal(result.active, 1);
    assert.equal(result.breakdown.get('orchestrator_recent'), 1);
  } finally {
    Date.now = originalNow;
  }
});

test('countActive ignores completed runs outside the lookback window', async () => {
  const registry = {
    'agents-70-orchestrator.yml|completed': [
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
      repo: 'Trend_Model_Project',
      prNumber: 78,
      completedLookbackSeconds: 300,
    });

    assert.equal(result.active, 0);
    assert.equal(result.breakdown.size, 0);
  } finally {
    Date.now = originalNow;
  }
});

test('evaluateRunCapForPr returns ok when active runs are below cap', async () => {
  const registry = {
    'agents-70-orchestrator.yml|queued': [
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
    repo: 'Trend_Model_Project',
    prNumber: 11,
  });

  assert.equal(result.ok, true);
  assert.equal(result.runCap, 3);
  assert.equal(result.activeRuns, 1);
  assert.deepEqual(result.breakdown, { orchestrator: 1 });
});

test('evaluateRunCapForPr enforces cap using default when label absent', async () => {
  const registry = {
    'agents-70-orchestrator.yml|queued': [
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
    repo: 'Trend_Model_Project',
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
    repo: 'Trend_Model_Project',
    prNumber: 50,
  };

  // Label sets cap to 2 explicitly, overriding the default of 1
  let result = await evaluateRunCapForPr({ ...baseArgs, currentRunId: 900 });
  assert.equal(result.ok, true);
  assert.equal(result.runCap, 2);
  assert.equal(result.activeRuns, 0);

  registry['agents-70-orchestrator.yml|queued'] = [
    { id: 900, pull_requests: [{ number: 50 }] },
    { id: 901, pull_requests: [{ number: 50 }] },
  ];

  result = await evaluateRunCapForPr({ ...baseArgs, currentRunId: 901 });
  assert.equal(result.ok, true);
  assert.equal(result.activeRuns, 1);

  registry['agents-70-orchestrator.yml|queued'] = [
    { id: 900, pull_requests: [{ number: 50 }] },
    { id: 901, pull_requests: [{ number: 50 }] },
    { id: 902, pull_requests: [{ number: 50 }] },
  ];

  result = await evaluateRunCapForPr({ ...baseArgs, currentRunId: 902 });
  assert.equal(result.ok, false);
  assert.equal(result.reason, 'run-cap-reached');
  assert.equal(result.activeRuns, 2);
});
