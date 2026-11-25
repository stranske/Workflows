'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  acquireActivationLock,
  runKeepaliveOrchestrator,
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

test('admitted comments emit the keepalive command directly after taking the activation lock', async () => {
  const calls = [];
  const github = { rest: {
    reactions: { createForIssueComment: async ({ comment_id }) => calls.push(comment_id) },
    repos: { createDispatchEvent: async (event) => calls.push(event) },
  } };
  const inputs = {
    commentId: 42, commentUrl: 'https://github.com/octo/repo/pull/34#issuecomment-42',
    prNumber: 34, branch: 'agent/repair', base: 'main', round: 2,
    trace: 'trace-123', agentAlias: 'codex', instructionBody: '@codex continue',
  };
  const result = await runKeepaliveOrchestrator({
    github, context: baseContext, core: makeCore(), inputs, secrets: { SERVICE_BOT_PAT: true },
  });
  assert.deepEqual(result, { ok: true, reason: 'ok' });
  assert.deepEqual(calls, [42, {
    owner: 'octo', repo: 'repo', event_type: 'codex-pr-comment-command',
    client_payload: {
      issue: 34, base: 'main', head: 'agent/repair', agent: 'codex', instruction_body: '@codex continue',
      meta: { comment_id: 42, comment_url: inputs.commentUrl, round: 2, trace: 'trace-123' },
      quiet: true, reply: 'none',
    },
  }]);
});

test('missing credentials and a held activation lock stop the command', async () => {
  const github = { rest: { reactions: {
    async createForIssueComment() { throw Object.assign(new Error('conflict'), { status: 409 }); },
  } } };
  const args = { github, context: baseContext, core: makeCore(), inputs: { commentId: 42 } };
  assert.equal((await runKeepaliveOrchestrator({ ...args, secrets: {} })).reason, 'forbidden-token');
  assert.deepEqual(await runKeepaliveOrchestrator({ ...args, secrets: { SERVICE_BOT_PAT: true } }),
    { ok: false, reason: 'lock-held' });
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
