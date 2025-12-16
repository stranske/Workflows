'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { detectKeepalive } = require('../agents_pr_meta_keepalive.js');

function createCore(outputs) {
  return {
    setOutput(key, value) {
      outputs[key] = value;
    },
    info() {},
    warning() {},
  };
}

test('automation summary comment is upgraded to next keepalive round', async () => {
  const outputs = {};
  const updatedBodies = [];
  const reactionCalls = [];
  const existingComments = [
    {
      body: '<!-- codex-keepalive-round: 1 -->\n<!-- codex-keepalive-marker -->',
      id: 123,
    },
  ];

  const github = {
    rest: {
      issues: {
        async listComments() {
          return { data: existingComments };
        },
        async updateComment({ body }) {
          updatedBodies.push(body);
          return {};
        },
      },
      pulls: {
        async get() {
          return {
            data: {
              head: {
                ref: 'codex/issue-3419',
                sha: 'abc123',
                repo: { fork: false, owner: { login: 'stranske' } },
              },
              base: {
                ref: 'phase-2-dev',
                repo: { owner: { login: 'stranske' } },
              },
            },
          };
        },
      },
      reactions: {
        async listForIssueComment() {
          return { data: [] };
        },
        async createForIssueComment({ content }) {
          reactionCalls.push(content);
          if (content === 'eyes') {
            return { status: 201, data: { content: 'eyes' } };
          }
          if (content === 'rocket') {
            return { status: 201, data: { content: 'rocket' } };
          }
          throw new Error(`Unexpected reaction ${content}`);
        },
      },
    },
    async paginate(method) {
      if (method === this.rest.issues.listComments) {
        return existingComments;
      }
      if (method === this.rest.reactions.listForIssueComment) {
        return [];
      }
      return [];
    },
  };

  const env = {
    ALLOWED_LOGINS: 'stranske',
    KEEPALIVE_MARKER: '<!-- codex-keepalive-marker -->',
    KEEPALIVE_AGENT_ALIAS: 'codex',
    GATE_OK: 'true',
    GATE_REASON: 'ok',
    GATE_PENDING: 'false',
  };

  const context = {
    repo: { owner: 'stranske', repo: 'Trend_Model_Project' },
    payload: {
      comment: {
        id: 3508466875,
        html_url: 'https://github.com/stranske/Trend_Model_Project/pull/3419#issuecomment-3508466875',
        body: '**Scope**\n- [ ] alpha\n\n**Acceptance criteria**\n- [ ] beta',
        user: { login: 'chatgpt-codex-connector[bot]' },
      },
      issue: { number: 3419 },
    },
  };

  await detectKeepalive({
    core: createCore(outputs),
    github,
    context,
    env,
  });

  assert.equal(outputs.dispatch, 'false');
  assert.equal(outputs.reason, 'automation-comment');
  assert.equal(updatedBodies.length, 0);
  assert.deepEqual(reactionCalls, []);
});

test('automation summary with round but no marker is ignored', async () => {
  const outputs = {};
  const reactionCalls = [];

  const github = {
    rest: {
      pulls: {
        async get() {
          return {
            data: {
              head: { ref: 'codex/issue-3419', repo: { fork: false, owner: { login: 'stranske' } } },
              base: { ref: 'phase-2-dev', repo: { owner: { login: 'stranske' } } },
            },
          };
        },
      },
      issues: {
        async listComments() {
          return { data: [] };
        },
      },
      reactions: {
        async listForIssueComment() {
          return { data: [] };
        },
        async createForIssueComment({ content }) {
          reactionCalls.push(content);
          return { status: 201, data: { content } };
        },
      },
    },
    async paginate(method) {
      if (method === this.rest.issues.listComments) {
        return [];
      }
      if (method === this.rest.reactions.listForIssueComment) {
        return [];
      }
      return [];
    },
  };

  const env = {
    ALLOWED_LOGINS: 'stranske',
    KEEPALIVE_MARKER: '<!-- codex-keepalive-marker -->',
    KEEPALIVE_AGENT_ALIAS: 'codex',
    GATE_OK: 'true',
  };

  const context = {
    repo: { owner: 'stranske', repo: 'Trend_Model_Project' },
    payload: {
      comment: {
        id: 789,
        html_url: 'https://github.com/stranske/Trend_Model_Project/pull/3419#issuecomment-789',
        body: '<!-- codex-keepalive-round: 4 -->\nAutofix attempt 1/1 complete.',
        user: { login: 'chatgpt-codex-connector[bot]' },
      },
      issue: { number: 3419 },
    },
  };

  await detectKeepalive({
    core: createCore(outputs),
    github,
    context,
    env,
  });

  assert.equal(outputs.dispatch, 'false');
  assert.equal(outputs.reason, 'automation-comment');
  assert.deepEqual(reactionCalls, []);
});

test('manual restated instructions are autopatched to the next round', async () => {
  const outputs = {};
  const updatedBodies = [];
  const reactionCalls = [];
  const existingComments = [
    {
      body: '<!-- codex-keepalive-round: 1 -->\n<!-- codex-keepalive-marker -->',
      id: 123,
    },
  ];

  const github = {
    rest: {
      issues: {
        async listComments() {
          return { data: existingComments };
        },
        async updateComment({ body }) {
          updatedBodies.push(body);
          return {};
        },
      },
      pulls: {
        async get() {
          return {
            data: {
              head: {
                ref: 'codex/issue-3420',
                repo: { fork: false, owner: { login: 'stranske' } },
              },
              base: {
                ref: 'phase-2-dev',
                repo: { owner: { login: 'stranske' } },
              },
            },
          };
        },
      },
      reactions: {
        async listForIssueComment() {
          return { data: [] };
        },
        async createForIssueComment({ content }) {
          reactionCalls.push(content);
          if (content === 'eyes') {
            return { status: 201, data: { content: 'eyes' } };
          }
          if (content === 'rocket') {
            return { status: 201, data: { content: 'rocket' } };
          }
          throw new Error(`Unexpected reaction ${content}`);
        },
      },
    },
    async paginate(method) {
      if (method === this.rest.issues.listComments) {
        return existingComments;
      }
      if (method === this.rest.reactions.listForIssueComment) {
        return [];
      }
      return [];
    },
  };

  const env = {
    ALLOWED_LOGINS: 'stranske',
    KEEPALIVE_MARKER: '<!-- codex-keepalive-marker -->',
    KEEPALIVE_AGENT_ALIAS: 'codex',
    GATE_OK: 'true',
  };

  const context = {
    repo: { owner: 'stranske', repo: 'Trend_Model_Project' },
    payload: {
      comment: {
        id: 456,
        html_url: 'https://github.com/stranske/Trend_Model_Project/pull/3420#issuecomment-456',
        body: '@codex use the scope, acceptance criteria, and task list so the keepalive workflow continues nudging until everything is complete. Work through the tasks, checking them off only after each acceptance criterion is satisfied, but check during each comment implementation and check off tasks and acceptance criteria that have been satisfied and repost the current version of the initial scope, task list and acceptance criteria each time that any have been newly completed.',
        user: { login: 'stranske' },
      },
      issue: { number: 3420 },
    },
  };

  await detectKeepalive({
    core: createCore(outputs),
    github,
    context,
    env,
  });

  assert.equal(outputs.dispatch, 'false');
  assert.equal(outputs.reason, 'missing-round');
  assert.equal(updatedBodies.length, 0);
  assert.deepEqual(reactionCalls, []);
});

test('keepalive detection captures instruction body without status bundle', async () => {
  const outputs = {};
  const reactionCalls = [];
  const scopeBlock = [
    '<!-- codex-keepalive-round: 3 -->',
    '<!-- codex-keepalive-marker -->',
    '<!-- codex-keepalive-trace: trace-456 -->',
    '@codex Continue working.',
    '',
    '## Automated Status Summary',
    '#### Scope',
    '- [ ] Scope entry',
    '',
    '#### Tasks',
    '- [ ] Task entry',
    '',
    '#### Acceptance criteria',
    '- [ ] Acceptance entry',
    '',
    '**Head SHA:** deadbeef',
    '**Latest Runs:** pending',
    '| Workflow / Job | Result | Logs |',
  ].join('\n');

  const github = {
    rest: {
      pulls: {
        async get() {
          return {
            data: {
              head: { ref: 'codex/issue-1', repo: { fork: false, owner: { login: 'stranske' } } },
              base: { ref: 'phase-2-dev', repo: { owner: { login: 'stranske' } } },
            },
          };
        },
      },
      issues: {
        async listComments() {
          return { data: [] };
        },
      },
      reactions: {
        async listForIssueComment() {
          return { data: [] };
        },
        async createForIssueComment({ content }) {
          reactionCalls.push(content);
          return { status: 201, data: { content } };
        },
      },
    },
    async paginate(method) {
      if (method === this.rest.issues?.listComments) {
        return [];
      }
      if (method === this.rest.reactions.listForIssueComment) {
        return [];
      }
      return [];
    },
  };

  const context = {
    repo: { owner: 'stranske', repo: 'Trend_Model_Project' },
    payload: {
      comment: {
        id: 99,
        html_url: 'https://example.test/comment/99',
        body: scopeBlock,
        user: { login: 'stranske' },
      },
      issue: { number: 4000 },
    },
  };

  const env = {
    ALLOWED_LOGINS: 'stranske',
    KEEPALIVE_MARKER: '<!-- codex-keepalive-marker -->',
    GATE_OK: 'true',
  };

  await detectKeepalive({
    core: createCore(outputs),
    github,
    context,
    env,
  });

  assert.equal(outputs.dispatch, 'true');
  assert.equal(outputs.reason, 'keepalive-detected');
  assert.ok(outputs.instruction_body);
  assert.equal(outputs.instruction_bytes, String(Buffer.byteLength(outputs.instruction_body, 'utf8')));
  assert.ok(!outputs.instruction_body.includes('Head SHA'));
  assert.ok(!outputs.instruction_body.includes('Workflow / Job'));
  assert.ok(reactionCalls.includes('hooray'));
});
