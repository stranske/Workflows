'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { countCheckboxes, parseConfig, evaluateKeepaliveLoop } = require('../keepalive_loop.js');
const { formatStateComment } = require('../keepalive_state.js');

const buildGithubStub = ({ pr, comments = [], workflowRuns = [] } = {}) => ({
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
    },
  },
  async paginate(fn, params) {
    const response = await fn(params);
    return Array.isArray(response?.data) ? response.data : [];
  },
});

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
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
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
    body: '## Tasks\n- [x] one\n## Acceptance Criteria\n- [X] a',
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
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
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
