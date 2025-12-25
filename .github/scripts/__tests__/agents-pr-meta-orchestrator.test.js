'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  acquireActivationLock,
  dispatchOrchestrator,
  confirmDispatch,
  dispatchKeepaliveCommand,
} = require('../agents_pr_meta_orchestrator');

function makeCore() {
  return {
    info: () => {},
    warning: () => {},
    error: () => {},
  };
}

const baseContext = {
  repo: { owner: 'octo', repo: 'repo' },
  payload: { repository: { default_branch: 'main' } },
};

test('acquireActivationLock returns missing when comment id is invalid', async () => {
  const result = await acquireActivationLock({
    github: {},
    context: baseContext,
    core: makeCore(),
    commentId: null,
  });

  assert.equal(result.status, 'missing');
  assert.equal(result.reason, 'no-activation-found');
});

test('acquireActivationLock reports ok when reaction is created', async () => {
  let called = false;
  const github = {
    rest: {
      reactions: {
        async createForIssueComment(payload) {
          called = true;
          assert.equal(payload.owner, 'octo');
          assert.equal(payload.repo, 'repo');
          assert.equal(payload.comment_id, 123);
          assert.equal(payload.content, 'rocket');
        },
      },
    },
  };

  const result = await acquireActivationLock({
    github,
    context: baseContext,
    core: makeCore(),
    commentId: 123,
  });

  assert.equal(called, true);
  assert.equal(result.status, 'ok');
});

test('acquireActivationLock reports lock-held when reaction already exists', async () => {
  const github = {
    rest: {
      reactions: {
        async createForIssueComment() {
          const error = new Error('conflict');
          error.status = 409;
          throw error;
        },
      },
    },
  };

  const result = await acquireActivationLock({
    github,
    context: baseContext,
    core: makeCore(),
    commentId: 321,
  });

  assert.equal(result.status, 'lock-held');
  assert.equal(result.reason, 'lock-held');
});

test('dispatchOrchestrator posts workflow dispatch with keepalive inputs', async () => {
  let received = null;
  const github = {
    rest: {
      actions: {
        async createWorkflowDispatch(payload) {
          received = payload;
        },
      },
    },
  };

  const result = await dispatchOrchestrator({
    github,
    context: baseContext,
    core: makeCore(),
    inputs: {
      issue: 12,
      prNumber: 34,
      branch: 'feature',
      base: 'main',
      round: 2,
      trace: 'trace-123',
      instructionBody: 'Instruction text',
    },
  });

  assert.equal(result.ok, true);
  assert.equal(received.workflow_id, 'agents-70-orchestrator.yml');
  assert.equal(received.ref, 'main');
  assert.equal(received.inputs.keepalive_enabled, 'true');
  assert.equal(received.inputs.pr_number, '34');
  const params = JSON.parse(received.inputs.params_json);
  assert.equal(params.dispatcher_force_issue, '12');
  assert.equal(params.keepalive_branch, 'feature');
  assert.equal(params.keepalive_base, 'main');
  const options = JSON.parse(received.inputs.options_json);
  assert.equal(options.round, '2');
  assert.equal(options.pr, '34');
  assert.equal(options.keepalive_trace, 'trace-123');
  assert.equal(options.keepalive_instruction, 'Instruction text');
});

test('dispatchOrchestrator falls back to GITHUB_TOKEN when scope error occurs', async () => {
  const previousToken = process.env.GITHUB_TOKEN;
  process.env.GITHUB_TOKEN = 'fallback-token';
  const fallbackCalls = [];

  function FakeOctokit({ auth }) {
    this.auth = auth;
    this.rest = {
      actions: {
        async createWorkflowDispatch(payload) {
          fallbackCalls.push({ auth, payload });
        },
      },
    };
  }

  const github = {
    constructor: FakeOctokit,
    rest: {
      actions: {
        async createWorkflowDispatch() {
          const error = new Error('Resource not accessible by integration');
          throw error;
        },
      },
    },
  };

  try {
    const result = await dispatchOrchestrator({
      github,
      context: baseContext,
      core: makeCore(),
      inputs: { issue: 1, prNumber: 2, trace: 'trace', round: 1 },
    });

    assert.equal(result.ok, true);
    assert.equal(fallbackCalls.length, 1);
    assert.equal(fallbackCalls[0].auth, 'fallback-token');
  } finally {
    process.env.GITHUB_TOKEN = previousToken;
  }
});

test('confirmDispatch confirms when a new run matches the PR number', async () => {
  const github = {
    rest: {
      actions: {
        async listWorkflowRuns() {
          return {
            data: {
              workflow_runs: [{
                id: 550,
                concurrency: 'pr-77-keepalive',
                created_at: '2024-01-01T00:00:00Z',
                html_url: 'https://example.test/runs/550',
              }],
            },
          };
        },
      },
    },
  };

  const result = await confirmDispatch({
    github,
    context: baseContext,
    core: makeCore(),
    baselineIds: '[]',
    baselineTimestamp: '2023-12-31T00:00:00Z',
    prNumber: 77,
    trace: 'trace',
  });

  assert.equal(result.confirmed, true);
  assert.equal(result.runId, '550');
  assert.equal(result.runUrl, 'https://example.test/runs/550');
});

test('confirmDispatch returns unconfirmed when no new runs appear', async () => {
  const originalSetTimeout = global.setTimeout;
  global.setTimeout = (fn, _delay, ...args) => originalSetTimeout(fn, 0, ...args);

  const github = {
    rest: {
      actions: {
        async listWorkflowRuns() {
          return { data: { workflow_runs: [] } };
        },
      },
    },
  };

  try {
    const result = await confirmDispatch({
      github,
      context: baseContext,
      core: makeCore(),
      baselineIds: '[]',
      baselineTimestamp: null,
      prNumber: 77,
      trace: 'trace',
    });

    assert.equal(result.confirmed, false);
    assert.equal(result.reason, 'dispatch-unconfirmed');
  } finally {
    global.setTimeout = originalSetTimeout;
  }
});

test('dispatchKeepaliveCommand requires instruction body', async () => {
  const github = {
    rest: {
      pulls: {
        async get() {
          return { data: { base: { ref: 'main' }, head: { ref: 'feature' } } };
        },
      },
      repos: {
        async createDispatchEvent() {},
      },
    },
  };

  await assert.rejects(
    () => dispatchKeepaliveCommand({
      github,
      context: baseContext,
      core: makeCore(),
      inputs: {
        prNumber: 10,
        base: 'main',
        head: 'feature',
        round: 1,
        trace: 'trace',
        commentId: 99,
        commentUrl: 'https://example.test/comment/99',
        instructionBody: '',
      },
    }),
    /Instruction body unavailable/,
  );
});
