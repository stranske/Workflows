'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { detectKeepalive, extractIssueNumberFromPull } = require('../agents_pr_meta_keepalive.js');

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
    repo: { owner: 'stranske', repo: 'Workflows' },
    payload: {
      comment: {
        id: 3508466875,
        html_url: 'https://github.com/stranske/Workflows/pull/3419#issuecomment-3508466875',
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
    repo: { owner: 'stranske', repo: 'Workflows' },
    payload: {
      comment: {
        id: 789,
        html_url: 'https://github.com/stranske/Workflows/pull/3419#issuecomment-789',
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
    repo: { owner: 'stranske', repo: 'Workflows' },
    payload: {
      comment: {
        id: 456,
        html_url: 'https://github.com/stranske/Workflows/pull/3420#issuecomment-456',
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
    repo: { owner: 'stranske', repo: 'Workflows' },
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

test('keepalive detection accepts valid non-issue source context', async () => {
  const outputs = {};
  const reactionCalls = [];
  const scopeBlock = [
    '<!-- codex-keepalive-round: 3 -->',
    '<!-- codex-keepalive-marker -->',
    '<!-- codex-keepalive-trace: trace-local -->',
    '@codex Continue working on the local request.',
  ].join('\n');

  const github = {
    rest: {
      pulls: {
        async get() {
          return {
            data: {
              body: '<!-- workflow-source:local_request -->\n<!-- workflow-source-ref:codex-thread-2026-04-26 -->',
              head: { ref: 'codex/source-context', repo: { fork: false, owner: { login: 'stranske' } } },
              base: { ref: 'main', repo: { owner: { login: 'stranske' } } },
              title: 'Add source context',
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

  const context = {
    repo: { owner: 'stranske', repo: 'Workflows' },
    payload: {
      comment: {
        id: 199,
        html_url: 'https://example.test/comment/199',
        body: scopeBlock,
        user: { login: 'stranske' },
      },
      issue: { number: 4001 },
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
  assert.equal(outputs.issue, '');
  assert.equal(outputs.source_type, 'local_request');
  assert.equal(outputs.source_ref, 'codex-thread-2026-04-26');
  assert.ok(reactionCalls.includes('hooray'));
  assert.ok(reactionCalls.includes('rocket'));
});

test('detectKeepalive caches pull request lookups across invocations', async () => {
  const outputsFirst = {};
  const outputsSecond = {};
  let getCalls = 0;

  const github = {
    rest: {
      pulls: {
        async get({ pull_number: pullNumber }) {
          getCalls += 1;
          return {
            data: {
              number: pullNumber,
              head: {
                ref: 'codex/issue-42',
                sha: 'abc123',
                repo: { fork: false, owner: { login: 'stranske' } },
              },
              base: {
                ref: 'main',
                repo: { owner: { login: 'stranske' } },
              },
              title: 'Fixes #42',
              labels: [],
            },
          };
        },
      },
      reactions: {
        async listForIssueComment() {
          return { data: [] };
        },
        async createForIssueComment({ content }) {
          return { status: 201, data: { content } };
        },
      },
      issues: {
        async addLabels() {
          return {};
        },
      },
    },
    async paginate(method) {
      if (method === this.rest.reactions.listForIssueComment) {
        return [];
      }
      return [];
    },
  };

  const context = {
    repo: { owner: 'stranske', repo: 'Workflows' },
    payload: {
      comment: {
        id: 101,
        html_url: 'https://example.test/comment/101',
        body: '@codex please proceed',
        user: { login: 'stranske' },
      },
      issue: { number: 42 },
    },
  };

  const env = {
    ALLOWED_LOGINS: 'stranske',
    GATE_OK: 'true',
  };

  await detectKeepalive({
    core: createCore(outputsFirst),
    github,
    context,
    env,
  });

  await detectKeepalive({
    core: createCore(outputsSecond),
    github,
    context,
    env,
  });

  assert.equal(getCalls, 1);
  assert.equal(outputsFirst.dispatch, 'true');
  assert.equal(outputsSecond.dispatch, 'true');
});

test('detectKeepalive does not cache empty pull responses', async () => {
  const outputsFirst = {};
  const outputsSecond = {};
  let getCalls = 0;

  const github = {
    rest: {
      pulls: {
        async get() {
          getCalls += 1;
          return { data: null };
        },
      },
      reactions: {
        async listForIssueComment() {
          return { data: [] };
        },
        async createForIssueComment({ content }) {
          return { status: 201, data: { content } };
        },
      },
      issues: {
        async addLabels() {
          return {};
        },
      },
    },
    async paginate(method) {
      if (method === this.rest.reactions.listForIssueComment) {
        return [];
      }
      return [];
    },
  };

  const context = {
    repo: { owner: 'stranske', repo: 'Workflows' },
    payload: {
      comment: {
        id: 202,
        html_url: 'https://example.test/comment/202',
        body: '@codex please proceed',
        user: { login: 'stranske' },
      },
      issue: { number: 77 },
    },
  };

  const env = {
    ALLOWED_LOGINS: 'stranske',
    GATE_OK: 'true',
  };

  await detectKeepalive({
    core: createCore(outputsFirst),
    github,
    context,
    env,
  });

  await detectKeepalive({
    core: createCore(outputsSecond),
    github,
    context,
    env,
  });

  assert.equal(getCalls, 2);
  assert.equal(outputsFirst.reason, 'pull-fetch-failed');
  assert.equal(outputsSecond.reason, 'pull-fetch-failed');
});

// --- extractIssueNumberFromPull tests ---

test('extractIssueNumberFromPull returns null for null input', () => {
  assert.equal(extractIssueNumberFromPull(null), null);
});

test('extractIssueNumberFromPull extracts from meta comment', () => {
  const pull = { body: 'Some text <!-- meta:issue:42 --> more text', head: { ref: 'feature' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), 42);
});

test('extractIssueNumberFromPull extracts from branch name', () => {
  const pull = { body: '', head: { ref: 'codex/issue-99' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), 99);
});

test('extractIssueNumberFromPull extracts from title', () => {
  const pull = { body: '', head: { ref: 'feature' }, title: 'fix: resolve #55' };
  assert.equal(extractIssueNumberFromPull(pull), 55);
});

test('extractIssueNumberFromPull extracts from body hash ref', () => {
  const pull = { body: 'Fixes #123', head: { ref: 'feature' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), 123);
});

test('extractIssueNumberFromPull skips "Run #NNN" in body', () => {
  const pull = { body: 'Run #2615 timed out after 45 minutes', head: { ref: 'claude/fix-something' }, title: 'fix: pre-timeout watchdog' };
  assert.equal(extractIssueNumberFromPull(pull), null);
});

test('extractIssueNumberFromPull skips "run #NNN" case-insensitive', () => {
  const pull = { body: 'The run #500 failed', head: { ref: 'feature' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), null);
});

test('extractIssueNumberFromPull skips "attempt #N" in body', () => {
  const pull = { body: 'attempt #3 was successful', head: { ref: 'feature' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), null);
});

test('extractIssueNumberFromPull skips "step #N" in body', () => {
  const pull = { body: 'step #2 completed', head: { ref: 'feature' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), null);
});

test('extractIssueNumberFromPull treats "Task #N" as a valid issue ref', () => {
  const pull = { body: 'Task #42 is ready for review', head: { ref: 'feature' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), 42);
});

test('extractIssueNumberFromPull skips "version #N" in body', () => {
  const pull = { body: 'Upgraded to version #4', head: { ref: 'feature' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), null);
});

test('extractIssueNumberFromPull prefers meta comment over "Run #NNN"', () => {
  const pull = { body: '<!-- meta:issue:77 --> Run #2615 timed out', head: { ref: 'feature' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), 77);
});

test('extractIssueNumberFromPull finds real issue after skipping Run ref', () => {
  const pull = { body: 'Run #2615 timed out. Relates to #88', head: { ref: 'feature' }, title: 'stuff' };
  assert.equal(extractIssueNumberFromPull(pull), 88);
});
