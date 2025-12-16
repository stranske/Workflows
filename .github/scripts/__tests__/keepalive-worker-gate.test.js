'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { evaluateKeepaliveWorkerGate } = require('../keepalive_worker_gate.js');

function buildInstructionComment({ id, trace, createdAt }) {
  const bodyLines = [
    '@codex use the scope, acceptance criteria, and task list so the keepalive workflow continues nudging until everything is complete.',
    '',
    '<!-- codex-keepalive-marker -->',
    '<!-- codex-keepalive-round: 5 -->',
    `<!-- codex-keepalive-trace: ${trace} -->`,
  ];
  return {
    id,
    body: bodyLines.join('\n'),
    created_at: createdAt,
    html_url: `https://example.test/comment/${id}`,
    user: { login: 'stranske', type: 'User' },
  };
}

function buildStateComment({ commentId, headSha, trace }) {
  const payload = {
    trace,
    head_sha: headSha,
    last_instruction: {
      comment_id: String(commentId),
      head_sha: headSha,
    },
    version: 'v1',
  };
  const body = `<!-- keepalive-state:v1 ${JSON.stringify(payload)} -->`;
  return {
    id: commentId - 1,
    body,
    created_at: '2024-01-01T00:00:00Z',
    html_url: `https://example.test/state/${commentId - 1}`,
    user: { login: 'stranske-automation-bot', type: 'Bot' },
  };
}

function makeGithubStub({ prNumber, headSha, comments }) {
  const commentsByIssue = new Map([[prNumber, comments]]);
  return {
    rest: {
      pulls: {
        async get({ pull_number: pullNumber }) {
          if (pullNumber !== prNumber) {
            throw new Error(`unexpected pull number ${pullNumber}`);
          }
          return {
            data: {
              head: { sha: headSha, ref: 'codex/issue-1' },
              base: { ref: 'main' },
            },
          };
        },
        async list() {
          return { data: [] };
        },
      },
      issues: {
        async listComments({ issue_number: issueNumber }) {
          return { data: commentsByIssue.get(issueNumber) || [] };
        },
      },
      reactions: {
        async listForIssueComment() {
          return { data: [] };
        },
        async createForIssueComment() {
          return { status: 201, data: { content: 'hooray' } };
        },
      },
    },
    async paginate(method, params) {
      if (method === this.rest.issues.listComments) {
        return commentsByIssue.get(params.issue_number) || [];
      }
      if (method === this.rest.reactions.listForIssueComment) {
        return [];
      }
      return [];
    },
  };
}

const baseContext = {
  repo: { owner: 'stranske', repo: 'Trend_Model_Project' },
};

const baseEnv = {
  KEEPALIVE: 'true',
  PR_NUMBER: '123',
};

function makeCore() {
  return {
    info: () => {},
    warning: () => {},
    error: () => {},
    setOutput: () => {},
  };
}

test('keepalive worker gate skips when no new instruction and head unchanged', async () => {
  const instructionId = 200;
  const headSha = 'abc123';
  const comments = [
    buildStateComment({ commentId: instructionId, headSha, trace: 'trace-upcoming' }),
    buildInstructionComment({ id: instructionId, trace: 'trace-current', createdAt: '2024-01-01T01:00:00Z' }),
  ];
  const github = makeGithubStub({ prNumber: 123, headSha, comments });
  const result = await evaluateKeepaliveWorkerGate({ core: makeCore(), github, context: baseContext, env: baseEnv });
  assert.equal(result.action, 'skip');
  assert.equal(result.reason, 'no-new-instruction-and-head-unchanged');
  assert.equal(result.prNumber, '123');
  assert.equal(result.headSha, headSha);
  assert.equal(result.instructionId, String(instructionId));
  assert.equal(result.lastProcessedCommentId, String(instructionId));
  assert.equal(result.lastProcessedHeadSha, headSha);
});

test('keepalive worker gate executes when a newer instruction exists', async () => {
  const storedCommentId = 199;
  const instructionId = 200;
  const headSha = 'abc123';
  const stateComment = buildStateComment({ commentId: storedCommentId, headSha, trace: 'trace-prev' });
  const instructionComment = buildInstructionComment({ id: instructionId, trace: 'trace-current', createdAt: '2024-01-01T01:00:00Z' });
  const github = makeGithubStub({ prNumber: 123, headSha, comments: [stateComment, instructionComment] });
  const env = { ...baseEnv };
  const result = await evaluateKeepaliveWorkerGate({ core: makeCore(), github, context: baseContext, env });
  assert.equal(result.action, 'execute');
  assert.equal(result.reason, 'new-instruction');
  assert.equal(result.instructionId, String(instructionId));
});

test('keepalive worker gate executes when head changed despite matching instruction', async () => {
  const instructionId = 200;
  const previousHead = 'abc123';
  const currentHead = 'def456';
  const stateComment = buildStateComment({ commentId: instructionId, headSha: previousHead, trace: 'trace-prev' });
  const instructionComment = buildInstructionComment({ id: instructionId, trace: 'trace-prev', createdAt: '2024-01-01T01:00:00Z' });
  const github = makeGithubStub({ prNumber: 123, headSha: currentHead, comments: [stateComment, instructionComment] });
  const env = { ...baseEnv };
  const result = await evaluateKeepaliveWorkerGate({ core: makeCore(), github, context: baseContext, env });
  assert.equal(result.action, 'execute');
  assert.equal(result.reason, 'head-changed');
  assert.equal(result.headSha, currentHead);
});

test('keepalive worker gate executes when keepalive disabled', async () => {
  const headSha = 'abc123';
  const github = makeGithubStub({ prNumber: 123, headSha, comments: [] });
  const env = { ...baseEnv, KEEPALIVE: 'false' };
  const result = await evaluateKeepaliveWorkerGate({ core: makeCore(), github, context: baseContext, env });
  assert.equal(result.action, 'execute');
  assert.equal(result.reason, 'keepalive-disabled');
  assert.equal(result.prNumber, '');
  assert.equal(result.headSha, '');
});
