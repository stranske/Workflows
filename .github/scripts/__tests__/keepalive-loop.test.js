'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const {
  countCheckboxes,
  parseConfig,
  evaluateKeepaliveLoop,
  updateKeepaliveLoopSummary,
} = require('../keepalive_loop.js');
const { formatStateComment } = require('../keepalive_state.js');

const fixturesDir = path.join(__dirname, 'fixtures');
const prBodyFixture = fs.readFileSync(path.join(fixturesDir, 'pr-body.md'), 'utf8');

const buildGithubStub = ({ pr, comments = [], workflowRuns = [] } = {}) => {
  const actions = [];
  return {
    actions,
    rest: {
      pulls: {
        async get() {
          return { data: pr };
        },
      },
      actions: {
        async listWorkflowRuns() {
          return { data: { workflow_runs: workflowRuns } };
        },
      },
      issues: {
        async listComments() {
          return { data: comments };
        },
        async updateComment({ body, comment_id: commentId }) {
          actions.push({ type: 'update', body, commentId });
          return { data: { id: commentId } };
        },
        async createComment({ body }) {
          actions.push({ type: 'create', body });
          return { data: { id: 101, html_url: 'https://example.com/101' } };
        },
        async addLabels({ labels }) {
          actions.push({ type: 'label', labels });
          return { data: {} };
        },
      },
    },
    async paginate(fn, params) {
      const response = await fn(params);
      return Array.isArray(response?.data) ? response.data : [];
    },
  };
};

const buildContext = (prNumber = 101) => ({
  eventName: 'pull_request',
  repo: { owner: 'octo', repo: 'workflows' },
  payload: { pull_request: { number: prNumber } },
});

const buildCore = () => ({
  info() {},
});

test('countCheckboxes tallies checked and unchecked tasks', () => {
  const counts = countCheckboxes('- [ ] one\n- [x] two\n- [X] three\n- [ ] four');
  assert.deepEqual(counts, { total: 4, checked: 2, unchecked: 2 });
});

test('parseConfig reads JSON config snippets and normalizes values', () => {
  const body = `
<!-- keepalive-config:start -->
{"keepalive_enabled": false, "iteration": "2", "max_iterations": 4, "failure_threshold": "7", "trace": "abc"}
<!-- keepalive-config:end -->
`;
  const config = parseConfig(body);
  assert.equal(config.keepalive_enabled, false);
  assert.equal(config.iteration, 2);
  assert.equal(config.max_iterations, 4);
  assert.equal(config.failure_threshold, 7);
  assert.equal(config.trace, 'abc');
});

test('parseConfig reads key/value config blocks', () => {
  const body = `
## Keepalive config
\`\`\`
keepalive_enabled = true
autofix_enabled: yes
max_iterations: 9
\`\`\`
`;
  const config = parseConfig(body);
  assert.equal(config.keepalive_enabled, true);
  assert.equal(config.autofix_enabled, true);
  assert.equal(config.max_iterations, 9);
});

test('evaluateKeepaliveLoop waits when agent label is missing', async () => {
  const pr = {
    number: 101,
    head: { ref: 'feature/one', sha: 'sha-1' },
    labels: [],
    body: prBodyFixture,
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-1', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'wait');
  assert.equal(result.reason, 'missing-agent-label');
});

test('evaluateKeepaliveLoop skips when keepalive is disabled', async () => {
  const pr = {
    number: 202,
    head: { ref: 'feature/two', sha: 'sha-2' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a\n<!-- keepalive-config: {"keepalive_enabled": false} -->',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-2', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'skip');
  assert.equal(result.reason, 'keepalive-disabled');
});

test('evaluateKeepaliveLoop stops when tasks are complete', async () => {
  const pr = {
    number: 303,
    head: { ref: 'feature/three', sha: 'sha-3' },
    labels: [{ name: 'agent:codex' }],
    body: prBodyFixture.replace(/- \[ \]/g, '- [x]'),
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-3', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'stop');
  assert.equal(result.reason, 'tasks-complete');
});

test('evaluateKeepaliveLoop stops when max iterations are reached', async () => {
  const pr = {
    number: 404,
    head: { ref: 'feature/four', sha: 'sha-4' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a\n<!-- keepalive-config: {"iteration": 5, "max_iterations": 5} -->',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-4', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'stop');
  assert.equal(result.reason, 'max-iterations');
});

test('evaluateKeepaliveLoop waits when gate has not succeeded', async () => {
  const pr = {
    number: 505,
    head: { ref: 'feature/five', sha: 'sha-5' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-5', conclusion: 'failure' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'wait');
  assert.equal(result.reason, 'gate-not-success');
});

test('evaluateKeepaliveLoop runs when ready', async () => {
  const pr = {
    number: 606,
    head: { ref: 'feature/six', sha: 'sha-6' },
    labels: [{ name: 'agent:codex' }],
    body: prBodyFixture,
  };
  const comments = [
    { id: 11, body: formatStateComment({ trace: '', iteration: 1 }), html_url: 'https://example.com' },
  ];
  const github = buildGithubStub({
    pr,
    comments,
    workflowRuns: [{ head_sha: 'sha-6', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'ready');
});

test('updateKeepaliveLoopSummary increments iteration and clears failures on success', async () => {
  const existingState = formatStateComment({
    trace: 'trace-1',
    iteration: 2,
    max_iterations: 5,
    failure_threshold: 3,
    failure: { reason: 'codex-run-failed', count: 2 },
  });
  const github = buildGithubStub({
    comments: [{ id: 33, body: existingState, html_url: 'https://example.com/33' }],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(123),
    core: buildCore(),
    inputs: {
      prNumber: 123,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 4,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-1',
      codex_changes_made: 'true',
      codex_files_changed: 2,
      codex_commit_sha: 'abcd1234',
      codex_summary: 'Updated tests to cover keepalive loop summary.',
    },
  });

  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'update');
  assert.match(github.actions[0].body, /Iteration \*\*3\/5\*\*/);
  assert.match(github.actions[0].body, /Iteration progress \| \[######----\] 3\/5 \|/);
  assert.match(github.actions[0].body, /### Last Codex Run/);
  assert.match(github.actions[0].body, /✅ Success/);
  assert.match(github.actions[0].body, /"iteration":3/);
  assert.match(github.actions[0].body, /"failure":\{\}/);
});

test('updateKeepaliveLoopSummary pauses after repeated failures and adds label', async () => {
  const existingState = formatStateComment({
    trace: 'trace-2',
    iteration: 1,
    failure_threshold: 3,
    failure: { reason: 'gate-not-success', count: 2 },
  });
  const github = buildGithubStub({
    comments: [{ id: 44, body: existingState, html_url: 'https://example.com/44' }],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(456),
    core: buildCore(),
    inputs: {
      prNumber: 456,
      action: 'wait',
      reason: 'gate-not-success',
      gateConclusion: 'failure',
      tasksTotal: 2,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-2',
    },
  });

  assert.equal(github.actions.length, 2);
  assert.equal(github.actions[0].type, 'update');
  assert.match(github.actions[0].body, /Paused/);
  assert.match(github.actions[0].body, /Iteration progress \| \[##--------\] 1\/5 \|/);
  assert.match(github.actions[0].body, /gate-not-success-repeat/);
  assert.equal(github.actions[1].type, 'label');
  assert.deepEqual(github.actions[1].labels, ['needs-human']);
});

test('evaluateKeepaliveLoop extracts agent type from agent:* labels', async () => {
  const pr = {
    number: 107,
    head: { ref: 'feature/agent-type', sha: 'sha-7' },
    labels: [{ name: 'agent:claude' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const comments = [];
  const github = buildGithubStub({
    pr,
    comments,
    workflowRuns: [{ head_sha: 'sha-7', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.agentType, 'claude');
  assert.equal(result.hasAgentLabel, true);
});

test('buildTaskAppendix formats scope, tasks, and acceptance criteria', () => {
  const { buildTaskAppendix } = require('../keepalive_loop.js');
  const sections = {
    scope: 'Fix the bug in the login flow.',
    tasks: '- [ ] Update validation\n- [x] Add tests',
    acceptance: '- [ ] Users can log in\n- [ ] No errors in console',
  };
  const checkboxCounts = { total: 4, checked: 1, unchecked: 3 };
  
  const appendix = buildTaskAppendix(sections, checkboxCounts);
  
  assert.ok(appendix.includes('## PR Tasks and Acceptance Criteria'));
  assert.ok(appendix.includes('**Progress:** 1/4 tasks complete, 3 remaining'));
  assert.ok(appendix.includes('### Scope'));
  assert.ok(appendix.includes('Fix the bug in the login flow.'));
  assert.ok(appendix.includes('### Tasks'));
  assert.ok(appendix.includes('- [ ] Update validation'));
  assert.ok(appendix.includes('### Acceptance Criteria'));
  assert.ok(appendix.includes('- [ ] Users can log in'));
});

test('evaluateKeepaliveLoop includes taskAppendix in result', async () => {
  const pr = {
    number: 108,
    head: { ref: 'feature/appendix', sha: 'sha-8' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] first task\n## Acceptance Criteria\n- [ ] must pass',
  };
  const github = buildGithubStub({
    pr,
    comments: [],
    workflowRuns: [{ head_sha: 'sha-8', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.ok(result.taskAppendix);
  assert.ok(result.taskAppendix.includes('first task'));
  assert.ok(result.taskAppendix.includes('must pass'));
});
