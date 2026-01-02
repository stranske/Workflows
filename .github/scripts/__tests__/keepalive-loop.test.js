'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  countCheckboxes,
  parseConfig,
  evaluateKeepaliveLoop,
  updateKeepaliveLoopSummary,
  markAgentRunning,
  analyzeTaskCompletion,
  autoReconcileTasks,
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
        async listJobsForWorkflowRun() {
          // Return empty jobs by default - tests can override if needed
          return { data: { jobs: [] } };
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
  setOutput() {},
});

test.after(() => {
  const metricsPath = path.join(process.cwd(), 'keepalive-metrics.ndjson');
  try {
    fs.unlinkSync(metricsPath);
  } catch (error) {
    if (error?.code !== 'ENOENT') {
      throw error;
    }
  }
});

test('countCheckboxes tallies checked and unchecked tasks', () => {
  const counts = countCheckboxes('- [ ] one\n- [x] two\n- [X] three\n- [ ] four');
  assert.deepEqual(counts, { total: 4, checked: 2, unchecked: 2 });
});

test('countCheckboxes handles alternate list markers', () => {
  const markdown = '* [ ] alpha\n+ [x] beta\n1. [ ] gamma\n2. [X] delta';
  const counts = countCheckboxes(markdown);
  assert.deepEqual(counts, { total: 4, checked: 2, unchecked: 2 });
});

test('countCheckboxes handles numbered lists with parentheses', () => {
  const markdown = '1) [ ] alpha\n2) [x] beta\n3) [ ] gamma';
  const counts = countCheckboxes(markdown);
  assert.deepEqual(counts, { total: 3, checked: 1, unchecked: 2 });
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

test('parseConfig ignores inline comments in key/value config blocks', () => {
  const body = `
## Keepalive config
\`\`\`
keepalive_enabled = true # enable keepalive
autofix_enabled: true // enable autofix
failure_threshold: 4 # stop after 4
\`\`\`
`;
  const config = parseConfig(body);
  assert.equal(config.keepalive_enabled, true);
  assert.equal(config.autofix_enabled, true);
  assert.equal(config.failure_threshold, 4);
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

test('evaluateKeepaliveLoop stops when max iterations reached AND unproductive', async () => {
  const pr = {
    number: 404,
    head: { ref: 'feature/four', sha: 'sha-4' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a\n<!-- keepalive-config: {"iteration": 5, "max_iterations": 5} -->',
  };
  // No previous state with file changes = unproductive
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
  assert.equal(result.reason, 'max-iterations-unproductive');
});

test('evaluateKeepaliveLoop continues past max iterations when productive', async () => {
  const pr = {
    number: 405,
    head: { ref: 'feature/extended', sha: 'sha-ext' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  // State shows productive work (files changed, no failures)
  const stateComment = formatStateComment({
    trace: '',
    iteration: 6,
    max_iterations: 5,
    last_files_changed: 3,
    failure: {},
  });
  const comments = [
    { id: 22, body: stateComment, html_url: 'https://example.com/22' },
  ];
  const github = buildGithubStub({
    pr,
    comments,
    workflowRuns: [{ head_sha: 'sha-ext', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'run', 'Should continue running when productive');
  assert.equal(result.reason, 'ready-extended', 'Should show extended mode');
});

test('evaluateKeepaliveLoop triggers fix mode when gate fails with test failures', async () => {
  const pr = {
    number: 505,
    head: { ref: 'feature/five', sha: 'sha-5' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 1001, head_sha: 'sha-5', conclusion: 'failure' }],
  });
  // Override listJobsForWorkflowRun to return test failures
  github.rest.actions.listJobsForWorkflowRun = async () => ({
    data: { jobs: [{ name: 'test (3.11)', conclusion: 'failure' }] },
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'fix');
  assert.equal(result.reason, 'fix-test');
  assert.equal(result.promptMode, 'fix_ci');
});

test('evaluateKeepaliveLoop waits when gate fails with lint failures', async () => {
  const pr = {
    number: 506,
    head: { ref: 'feature/lint', sha: 'sha-lint' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 1002, head_sha: 'sha-lint', conclusion: 'failure' }],
  });
  // Override listJobsForWorkflowRun to return lint failures
  github.rest.actions.listJobsForWorkflowRun = async () => ({
    data: { jobs: [{ name: 'lint (ruff)', conclusion: 'failure' }] },
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'wait');
  assert.equal(result.reason, 'gate-not-success');
});

test('evaluateKeepaliveLoop waits when gate is pending', async () => {
  const pr = {
    number: 507,
    head: { ref: 'feature/pending', sha: 'sha-pending' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 1003, head_sha: 'sha-pending', conclusion: null }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'wait');
  assert.equal(result.reason, 'gate-pending');
});

test('evaluateKeepaliveLoop treats cancelled gate as transient wait', async () => {
  const pr = {
    number: 508,
    head: { ref: 'feature/cancelled', sha: 'sha-cancelled' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 1004, head_sha: 'sha-cancelled', conclusion: 'cancelled' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'wait');
  assert.equal(result.reason, 'gate-cancelled');
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
  assert.match(github.actions[0].body, /Iteration 3\/5/);
  assert.match(github.actions[0].body, /Iteration progress \| \[######----\] 3\/5 \|/);
  assert.match(github.actions[0].body, /### Last Codex Run/);
  assert.match(github.actions[0].body, /✅ Success/);
  assert.match(github.actions[0].body, /"iteration":3/);
  assert.match(github.actions[0].body, /"failure":\{\}/);
});

test('updateKeepaliveLoopSummary writes step summary for agent runs', async () => {
  const summary = {
    buffer: '',
    written: false,
    addRaw(text) {
      this.buffer += text;
      return this;
    },
    addEOL() {
      this.buffer += '\n';
      return this;
    },
    async write() {
      this.written = true;
    },
  };
  const core = { info() {}, summary };
  const existingState = formatStateComment({
    trace: 'trace-summary',
    iteration: 0,
    max_iterations: 5,
  });
  const github = buildGithubStub({
    comments: [{ id: 55, body: existingState, html_url: 'https://example.com/55' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(789),
    core,
    inputs: {
      prNumber: 789,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 5,
      tasksUnchecked: 3,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 0,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-summary',
      agent_files_changed: 2,
    },
  });

  assert.equal(summary.written, true);
  assert.match(summary.buffer, /Keepalive iteration summary/);
  assert.match(summary.buffer, /Iteration \| 1\/5/);
  assert.match(summary.buffer, /Tasks completed \| 2\/5/);
  assert.match(summary.buffer, /Tasks completed this run \| 0/);
  assert.match(summary.buffer, /Files changed \| 2/);
  assert.match(summary.buffer, /Outcome \| success/);
});

test('updateKeepaliveLoopSummary emits metrics output for keepalive runs', async () => {
  const outputs = {};
  const core = {
    info() {},
    setOutput(key, value) {
      outputs[key] = value;
    },
  };
  const existingState = formatStateComment({
    trace: 'trace-metrics',
    iteration: 3,
    max_iterations: 5,
  });
  const github = buildGithubStub({
    comments: [{ id: 77, body: existingState, html_url: 'https://example.com/77' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(2468),
    core,
    inputs: {
      prNumber: 2468,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 10,
      tasksUnchecked: 6,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 3,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-metrics',
      duration_ms: 1234,
    },
  });

  assert.ok(outputs.metrics_record_json);
  const record = JSON.parse(outputs.metrics_record_json);
  assert.equal(record.pr_number, 2468);
  assert.equal(record.iteration, 4);
  assert.equal(record.action, 'run');
  assert.equal(record.error_category, 'none');
  assert.equal(record.duration_ms, 1234);
  assert.equal(record.tasks_total, 10);
  assert.equal(record.tasks_complete, 4);
  assert.ok(typeof record.timestamp === 'string' && record.timestamp.includes('T'));
});

test('updateKeepaliveLoopSummary appends metrics record when path provided', async () => {
  const core = {
    info() {},
    warning() {},
    setOutput() {},
  };
  const existingState = formatStateComment({
    trace: 'trace-metrics-file',
    iteration: 1,
    max_iterations: 5,
  });
  const github = buildGithubStub({
    comments: [{ id: 77, body: existingState, html_url: 'https://example.com/77' }],
  });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'keepalive-metrics-'));
  const metricsPath = path.join(tmpDir, 'metrics.ndjson');
  const original = process.env.KEEPALIVE_METRICS_PATH;
  process.env.KEEPALIVE_METRICS_PATH = metricsPath;
  try {
    await updateKeepaliveLoopSummary({
      github,
      context: buildContext(1357),
      core,
      inputs: {
        prNumber: 1357,
        action: 'run',
        runResult: 'success',
        gateConclusion: 'success',
        tasksTotal: 2,
        tasksUnchecked: 1,
        keepaliveEnabled: true,
        autofixEnabled: false,
        iteration: 1,
        maxIterations: 5,
        failureThreshold: 3,
        trace: 'trace-metrics-file',
      },
    });
  } finally {
    if (original === undefined) {
      delete process.env.KEEPALIVE_METRICS_PATH;
    } else {
      process.env.KEEPALIVE_METRICS_PATH = original;
    }
  }

  const lines = fs.readFileSync(metricsPath, 'utf8').trim().split('\n');
  assert.equal(lines.length, 1);
  const record = JSON.parse(lines[0]);
  assert.equal(record.pr_number, 1357);
  assert.equal(record.iteration, 2);
  assert.equal(record.tasks_total, 2);
  assert.equal(record.tasks_complete, 1);
});

test('updateKeepaliveLoopSummary appends metrics record in GitHub Actions workspace by default', async () => {
  const core = {
    info() {},
    warning() {},
    setOutput() {},
  };
  const existingState = formatStateComment({
    trace: 'trace-metrics-default',
    iteration: 2,
    max_iterations: 5,
  });
  const github = buildGithubStub({
    comments: [{ id: 77, body: existingState, html_url: 'https://example.com/77' }],
  });
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'keepalive-metrics-actions-'));
  const originalActions = process.env.GITHUB_ACTIONS;
  const originalWorkspace = process.env.GITHUB_WORKSPACE;
  process.env.GITHUB_ACTIONS = 'true';
  process.env.GITHUB_WORKSPACE = tmpDir;
  try {
    await updateKeepaliveLoopSummary({
      github,
      context: buildContext(2469),
      core,
      inputs: {
        prNumber: 2469,
        action: 'run',
        runResult: 'success',
        gateConclusion: 'success',
        tasksTotal: 3,
        tasksUnchecked: 1,
        keepaliveEnabled: true,
        autofixEnabled: false,
        iteration: 2,
        maxIterations: 5,
        failureThreshold: 3,
        trace: 'trace-metrics-default',
      },
    });
  } finally {
    if (originalActions === undefined) {
      delete process.env.GITHUB_ACTIONS;
    } else {
      process.env.GITHUB_ACTIONS = originalActions;
    }
    if (originalWorkspace === undefined) {
      delete process.env.GITHUB_WORKSPACE;
    } else {
      process.env.GITHUB_WORKSPACE = originalWorkspace;
    }
  }

  const metricsPath = path.join(tmpDir, 'keepalive-metrics.ndjson');
  const lines = fs.readFileSync(metricsPath, 'utf8').trim().split('\n');
  assert.equal(lines.length, 1);
  const record = JSON.parse(lines[0]);
  assert.equal(record.pr_number, 2469);
  assert.equal(record.iteration, 3);
  assert.equal(record.tasks_total, 3);
  assert.equal(record.tasks_complete, 2);
});

test('updateKeepaliveLoopSummary resets failure count on transient errors', async () => {
  const existingState = formatStateComment({
    trace: 'trace-transient',
    iteration: 1,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 2 },
  });
  const github = buildGithubStub({
    comments: [{ id: 77, body: existingState, html_url: 'https://example.com/77' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(321),
    core: buildCore(),
    inputs: {
      prNumber: 321,
      action: 'run',
      runResult: 'failure',
      gateConclusion: 'success',
      tasksTotal: 4,
      tasksUnchecked: 4,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-transient',
      agent_exit_code: '1',
      agent_summary: 'Request timed out after 30s while running Codex.',
    },
  });

  assert.equal(github.actions.length, 1);
  const updateAction = github.actions.find((action) => action.type === 'update');
  assert.ok(updateAction);
  const body = updateAction.body;
  assert.match(body, /agent-run-transient/);
  assert.match(body, /Transient Issue Detected/);
  assert.match(body, /"failure":\{\}/);
  assert.match(body, /"error_type":"infrastructure"/);
  assert.match(body, /"error_category":"transient"/);
});

test('updateKeepaliveLoopSummary uses state iteration when inputs have stale value', async () => {
  // Simulates race condition: evaluate ran with stale iteration=0, but state was updated to iteration=2
  const existingState = formatStateComment({
    trace: 'trace-race',
    iteration: 2,  // Current state has iteration=2
    max_iterations: 5,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 44, body: existingState, html_url: 'https://example.com/44' }],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(124),
    core: buildCore(),
    inputs: {
      prNumber: 124,
      action: 'wait',  // Gate failed, agent didn't run
      reason: 'gate-not-success',
      gateConclusion: 'failure',
      tasksTotal: 10,
      tasksUnchecked: 8,
      keepaliveEnabled: true,
      iteration: 0,  // STALE value from evaluate (ran before state was updated)
      maxIterations: 5,
      trace: 'trace-race',
    },
  });

  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'update');
  // Should preserve iteration=2 from state, NOT use stale iteration=0 from inputs
  assert.match(github.actions[0].body, /"iteration":2/);
  assert.match(github.actions[0].body, /Iteration 2\/5/);
});

test('updateKeepaliveLoopSummary does NOT count wait states as failures', async () => {
  // Wait states (gate-not-success, gate-pending, missing-agent-label) are transient
  // and should NOT increment the failure counter or trigger needs-human
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

  // Should only update comment, NOT add needs-human label
  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'update');
  // Failure state should be cleared for transient wait conditions
  assert.match(github.actions[0].body, /"failure":\{\}/);
  // Should NOT have -repeat suffix since we're not counting wait states
  assert.doesNotMatch(github.actions[0].body, /gate-not-success-repeat/);
});

test('updateKeepaliveLoopSummary adds needs-human after repeated actual failures', async () => {
  // Only actual failures (agent-run-failed) should count toward threshold
  const existingState = formatStateComment({
    trace: 'trace-fail',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 2 },
  });
  const github = buildGithubStub({
    comments: [{ id: 45, body: existingState, html_url: 'https://example.com/45' }],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(457),
    core: buildCore(),
    inputs: {
      prNumber: 457,
      action: 'run',
      reason: 'ready',
      runResult: 'failure',  // Agent run failed
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-fail',
    },
  });

  assert.equal(github.actions.length, 3);
  const updateAction = github.actions.find((action) => action.type === 'update');
  assert.ok(updateAction);
  assert.match(updateAction.body, /agent-run-failed-repeat/);
  assert.match(updateAction.body, /AGENT FAILED/);

  const needsAttentionLabel = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('agent:needs-attention')
  );
  assert.ok(needsAttentionLabel);

  const needsHumanLabel = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('needs-human')
  );
  assert.ok(needsHumanLabel);
});

test('updateKeepaliveLoopSummary adds attention label for auth failures', async () => {
  const existingState = formatStateComment({
    trace: 'trace-attention-auth',
    iteration: 1,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 88, body: existingState, html_url: 'https://example.com/88' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(654),
    core: buildCore(),
    inputs: {
      prNumber: 654,
      action: 'run',
      runResult: 'failure',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 3,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-auth',
      agent_exit_code: '1',
      agent_summary: 'Bad credentials while calling GitHub API.',
    },
  });

  const labelAction = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('agent:needs-attention')
  );
  assert.ok(labelAction);
});

test('updateKeepaliveLoopSummary adds attention label for resource failures', async () => {
  const existingState = formatStateComment({
    trace: 'trace-attention-resource',
    iteration: 1,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 99, body: existingState, html_url: 'https://example.com/99' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(655),
    core: buildCore(),
    inputs: {
      prNumber: 655,
      action: 'run',
      runResult: 'failure',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 3,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-resource',
      agent_exit_code: '1',
      agent_summary: 'Repository not found for this request.',
    },
  });

  const attentionLabel = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('agent:needs-attention')
  );
  assert.ok(attentionLabel);
});

test('updateKeepaliveLoopSummary adds attention label for logic failures', async () => {
  const existingState = formatStateComment({
    trace: 'trace-attention-logic',
    iteration: 1,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 102, body: existingState, html_url: 'https://example.com/102' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(656),
    core: buildCore(),
    inputs: {
      prNumber: 656,
      action: 'run',
      runResult: 'failure',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 3,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-logic',
      agent_exit_code: '1',
      agent_summary: 'Validation failed: invalid request payload.',
    },
  });

  const attentionLabel = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('agent:needs-attention')
  );
  assert.ok(attentionLabel);
});

test('updateKeepaliveLoopSummary formats codex failure details in summary', async () => {
  const existingState = formatStateComment({
    trace: 'trace-attention-codex',
    iteration: 1,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 111, body: existingState, html_url: 'https://example.com/111' }],
  });
  const longSummary = `Validation failed: ${'x'.repeat(400)}`;

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(657),
    core: buildCore(),
    inputs: {
      prNumber: 657,
      action: 'run',
      runResult: 'failure',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 3,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-codex',
      agent_exit_code: '2',
      agent_summary: longSummary,
      run_url: 'https://example.com/run/657',
    },
  });

  const updateAction = github.actions.find((action) => action.type === 'update');
  assert.ok(updateAction);
  assert.match(updateAction.body, /Error category \| logic/);
  assert.match(updateAction.body, /Error type \| codex/);
  assert.match(updateAction.body, /https:\/\/example.com\/run\/657/);
  assert.match(updateAction.body, /Codex output/);
});

test('updateKeepaliveLoopSummary does NOT add needs-human on tasks-complete', async () => {
  // tasks-complete is a SUCCESS state, not an error
  const existingState = formatStateComment({
    trace: 'trace-success',
    iteration: 3,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 46, body: existingState, html_url: 'https://example.com/46' }],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(458),
    core: buildCore(),
    inputs: {
      prNumber: 458,
      action: 'stop',
      reason: 'tasks-complete',  // All tasks done - this is success!
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 0,  // All tasks checked
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 3,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-success',
    },
  });

  // Should only update comment, NOT add needs-human label
  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'update');
  // Should show completed status
  assert.match(github.actions[0].body, /tasks-complete/);
  // Failure state should be clear
  assert.match(github.actions[0].body, /"failure":\{\}/);
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

test('evaluateKeepaliveLoop normalizes bullet tasks into checkboxes', async () => {
  const pr = {
    number: 109,
    head: { ref: 'feature/bullets', sha: 'sha-9' },
    labels: [{ name: 'agent:codex' }],
    body: [
      '## Tasks',
      '- implement parser',
      '- document flow',
      '',
      '## Acceptance Criteria',
      '- tests pass',
    ].join('\n'),
  };
  const github = buildGithubStub({
    pr,
    comments: [],
    workflowRuns: [{ head_sha: 'sha-9', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'ready');
  assert.deepEqual(result.checkboxCounts, { total: 3, checked: 0, unchecked: 3 });
  assert.ok(result.taskAppendix.includes('- [ ] implement parser'));
  assert.ok(result.taskAppendix.includes('- [ ] tests pass'));
});

test('evaluateKeepaliveLoop converts all lists to checkboxes', async () => {
  const pr = {
    number: 110,
    head: { ref: 'feature/numbered', sha: 'sha-10' },
    labels: [{ name: 'agent:codex' }],
    body: [
      '## Tasks',
      '1) add metrics',
      '2) verify outputs',
      '',
      '## Acceptance Criteria',
      '1) reports render',
    ].join('\n'),
  };
  const github = buildGithubStub({
    pr,
    comments: [],
    workflowRuns: [{ head_sha: 'sha-10', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'ready');
  // All lists are converted to checkboxes
  assert.deepEqual(result.checkboxCounts, { total: 3, checked: 0, unchecked: 3 });
  assert.ok(result.taskAppendix.includes('1) [ ] add metrics'));
  assert.ok(result.taskAppendix.includes('1) [ ] reports render'));
});

test('buildTaskAppendix includes reconciliation warning when state.needs_task_reconciliation is true', () => {
  const { buildTaskAppendix } = require('../keepalive_loop.js');
  const sections = {
    scope: 'Fix the bug.',
    tasks: '- [ ] Update code\n- [ ] Add tests',
    acceptance: '- [ ] Tests pass',
  };
  const checkboxCounts = { total: 3, checked: 0, unchecked: 3 };
  const state = { needs_task_reconciliation: true, last_files_changed: 4 };
  
  const appendix = buildTaskAppendix(sections, checkboxCounts, state);
  
  assert.ok(appendix.includes('⚠️ IMPORTANT: Task Reconciliation Required'));
  assert.ok(appendix.includes('changed **4 file(s)**'));
  assert.ok(appendix.includes('Review the recent commits'));
  assert.ok(appendix.includes('Update the PR body to check off'));
});

test('buildTaskAppendix omits reconciliation warning when state.needs_task_reconciliation is false', () => {
  const { buildTaskAppendix } = require('../keepalive_loop.js');
  const sections = {
    tasks: '- [ ] Update code',
    acceptance: '- [ ] Tests pass',
  };
  const checkboxCounts = { total: 2, checked: 0, unchecked: 2 };
  const state = { needs_task_reconciliation: false };
  
  const appendix = buildTaskAppendix(sections, checkboxCounts, state);
  
  assert.ok(!appendix.includes('Task Reconciliation Required'));
});

test('extractSourceSection extracts source links from PR body', () => {
  const { extractSourceSection } = require('../keepalive_loop.js');
  
  const prBody = `## Summary
Some summary text

## Source
- Original PR: #123
- Parent issue: #456

## Tasks
- [ ] Do something`;
  
  const source = extractSourceSection(prBody);
  assert.ok(source.includes('#123'));
  assert.ok(source.includes('#456'));
});

test('extractSourceSection returns null when no source section', () => {
  const { extractSourceSection } = require('../keepalive_loop.js');
  
  const prBody = `## Summary
Some summary text

## Tasks
- [ ] Do something`;
  
  const source = extractSourceSection(prBody);
  assert.equal(source, null);
});

test('extractSourceSection returns null for source section without links', () => {
  const { extractSourceSection } = require('../keepalive_loop.js');
  
  const prBody = `## Source
No actual links here, just text`;
  
  const source = extractSourceSection(prBody);
  assert.equal(source, null);
});

test('buildTaskAppendix includes Source Context when prBody has source links', () => {
  const { buildTaskAppendix } = require('../keepalive_loop.js');
  const sections = {
    scope: 'Fix the bug',
    tasks: '- [ ] Update code',
    acceptance: '- [ ] Tests pass',
  };
  const checkboxCounts = { total: 2, checked: 0, unchecked: 2 };
  const prBody = `## Summary
Fix stuff

## Source
- Original PR: #789
- Parent issue: https://github.com/org/repo/issues/100`;
  
  const appendix = buildTaskAppendix(sections, checkboxCounts, {}, { prBody });
  
  assert.ok(appendix.includes('### Source Context'));
  assert.ok(appendix.includes('#789'));
  assert.ok(appendix.includes('github.com'));
});

test('buildTaskAppendix omits Source Context when prBody has no source section', () => {
  const { buildTaskAppendix } = require('../keepalive_loop.js');
  const sections = {
    tasks: '- [ ] Update code',
  };
  const checkboxCounts = { total: 1, checked: 0, unchecked: 1 };
  const prBody = `## Summary
Just some info`;
  
  const appendix = buildTaskAppendix(sections, checkboxCounts, {}, { prBody });
  
  assert.ok(!appendix.includes('Source Context'));
});

test('markAgentRunning updates summary comment with running status', async () => {
  // Use formatStateComment to create proper state marker
  const existingStateBody = formatStateComment({
    trace: 'test-trace',
    iteration: 2,
    tasks: { total: 10, unchecked: 7 },
  });
  const comments = [
    {
      id: 200,
      body: `<!-- keepalive-loop-summary -->\n## Summary\n${existingStateBody}`,
      html_url: 'https://example.com/200',
    },
  ];
  const github = buildGithubStub({ comments });
  const inputs = {
    pr_number: 42,
    agent_type: 'codex',
    iteration: 2,
    max_iterations: 5,
    tasks_total: 10,
    tasks_unchecked: 7,
    trace: 'test-trace',
    run_url: 'https://github.com/test/repo/actions/runs/12345',
  };

  await markAgentRunning({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    core: buildCore(),
    inputs,
  });

  // Should have updated the comment
  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'update');
  assert.equal(github.actions[0].commentId, 200);
  
  // Check the body content
  const body = github.actions[0].body;
  assert.ok(body.includes('keepalive-loop-summary'), 'Should have summary marker');
  assert.ok(body.includes('🔄 Agent Running'), 'Should show running status');
  assert.ok(body.includes('Codex is actively working'), 'Should show agent name');
  assert.ok(body.includes('Iteration | 3 of 5'), 'Should show next iteration');
  assert.ok(body.includes('Task progress'), 'Should show task progress');
  assert.ok(body.includes('view logs'), 'Should include run URL');
  assert.ok(body.includes('will be updated when the agent completes'), 'Should include completion message');
});

test('markAgentRunning creates comment when none exists', async () => {
  const github = buildGithubStub({ comments: [] });
  const inputs = {
    pr_number: 99,
    agent_type: 'claude',
    iteration: 0,
    max_iterations: 3,
    tasks_total: 5,
    tasks_unchecked: 5,
  };

  await markAgentRunning({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    core: buildCore(),
    inputs,
  });

  // Should have created a new comment
  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'create');
  
  const body = github.actions[0].body;
  assert.ok(body.includes('Claude is actively working'), 'Should capitalize agent name');
  assert.ok(body.includes('Iteration | 1 of 3'), 'Should show iteration 1 (0+1)');
  assert.ok(body.includes('Task progress | 0/5'), 'Should show task progress');
});

// =====================================================
// Task Reconciliation Tests
// =====================================================

test('analyzeTaskCompletion identifies high-confidence matches', async () => {
  const commits = [
    { sha: 'abc123', commit: { message: 'feat: add step summary output to keepalive loop' } },
    { sha: 'def456', commit: { message: 'test: add tests for step summary emission' } },
  ];
  const files = [
    { filename: '.github/workflows/agents-keepalive-loop.yml' },
    { filename: '.github/scripts/keepalive_loop.js' },
  ];
  
  const github = {
    rest: {
      repos: {
        async compareCommits() {
          return { data: { commits } };
        },
      },
      pulls: {
        async listFiles() {
          return { data: files };
        },
      },
    },
  };

  const taskText = `
- [ ] Add step summary output to agents-keepalive-loop.yml after agent run
- [ ] Include: iteration number, tasks completed, files changed, outcome
- [ ] Ensure summary is visible in workflow run UI
- [ ] Unrelated task about something else entirely
`;

  const result = await analyzeTaskCompletion({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    taskText,
    core: buildCore(),
  });

  assert.ok(result.matches.length > 0, 'Should find at least one match');
  
  // Should match the step summary task with high confidence
  const stepSummaryMatch = result.matches.find(m => 
    m.task.toLowerCase().includes('step summary')
  );
  assert.ok(stepSummaryMatch, 'Should match step summary task');
  assert.equal(stepSummaryMatch.confidence, 'high', 'Should be high confidence');
});

test('analyzeTaskCompletion matches explicit file creation tasks', async () => {
  const commits = [
    { sha: 'abc123', commit: { message: 'test: add agents-guard tests' } },
  ];
  const files = [
    { filename: '.github/scripts/__tests__/agents-guard.test.js' },
  ];
  
  const github = {
    rest: {
      repos: {
        async compareCommits() {
          return { data: { commits } };
        },
      },
      pulls: {
        async listFiles() {
          return { data: files };
        },
      },
    },
  };

  const taskText = `
- [ ] Create \`agents-guard.test.js\` with tests for label validation
- [ ] Write poetry about sunsets and rainbows
- [ ] Cook dinner recipes for Italian cuisine
`;

  const result = await analyzeTaskCompletion({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    taskText,
    core: buildCore(),
  });

  assert.ok(result.matches.length > 0, 'Should find at least one match');
  
  // Should match the agents-guard.test.js task with high confidence due to exact file match
  const guardMatch = result.matches.find(m => 
    m.task.toLowerCase().includes('agents-guard.test.js')
  );
  assert.ok(guardMatch, 'Should match agents-guard task');
  assert.equal(guardMatch.confidence, 'high', 'Should be high confidence for exact file');
  assert.ok(guardMatch.reason.includes('Exact file'), 'Reason should mention exact file match');
  
  // Should NOT match poetry task since it's completely unrelated
  const poetryMatch = result.matches.find(m =>
    m.task.toLowerCase().includes('poetry')
  );
  assert.ok(!poetryMatch || poetryMatch.confidence !== 'high', 
    'Should not match unrelated poetry task with high confidence');
});

test('analyzeTaskCompletion returns empty for unrelated commits', async () => {
  const commits = [
    { sha: 'abc123', commit: { message: 'fix: typo in readme' } },
  ];
  const files = [
    { filename: 'README.md' },
  ];
  
  const github = {
    rest: {
      repos: {
        async compareCommits() {
          return { data: { commits } };
        },
      },
      pulls: {
        async listFiles() {
          return { data: files };
        },
      },
    },
  };

  const taskText = `
- [ ] Implement complex feature in keepalive workflow
- [ ] Add database migrations
`;

  const result = await analyzeTaskCompletion({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    taskText,
    core: buildCore(),
  });

  // Should find no high-confidence matches
  const highConfidence = result.matches.filter(m => m.confidence === 'high');
  assert.equal(highConfidence.length, 0, 'Should not find high-confidence matches for unrelated commits');
});

test('analyzeTaskCompletion uses lowered 35% threshold with file match', async () => {
  // Task: "Add config support for financing model"
  // Commit: "Pass schedule inputs into capital validation"
  // Keywords in common: config, schedule, inputs (35%+ overlap with file match)
  const commits = [
    { sha: 'abc123', commit: { message: 'feat: add schedule config inputs to validation' } },
  ];
  const files = [
    { filename: 'src/config/financing_model.py' },
  ];
  
  const github = {
    rest: {
      repos: {
        async compareCommits() {
          return { data: { commits } };
        },
      },
      pulls: {
        async listFiles() {
          return { data: files };
        },
      },
    },
  };

  const taskText = `
- [ ] Add config support for financing model schedule inputs
- [ ] Completely unrelated database task
`;

  const result = await analyzeTaskCompletion({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    taskText,
    core: buildCore(),
  });

  // With lowered threshold (35%) + file match, should be high confidence
  const configMatch = result.matches.find(m => 
    m.task.toLowerCase().includes('config') && m.task.toLowerCase().includes('financing')
  );
  assert.ok(configMatch, 'Should match config/financing task');
  assert.equal(configMatch.confidence, 'high', 'Should be high confidence with 35%+ match and file touch');
});

test('analyzeTaskCompletion gives high confidence for 25% keyword match with file match', async () => {
  // Lower threshold: 25% keyword match + file match = high confidence
  const commits = [
    { sha: 'abc123', commit: { message: 'add wizard step' } },
  ];
  const files = [
    { filename: 'src/ui/wizard_step.py' },
  ];
  
  const github = {
    rest: {
      repos: {
        async compareCommits() {
          return { data: { commits } };
        },
      },
      pulls: {
        async listFiles() {
          return { data: files };
        },
      },
    },
  };

  const taskText = `
- [ ] Add wizard step for sleeve suggestions with tooltips and validation
`;

  const result = await analyzeTaskCompletion({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    taskText,
    core: buildCore(),
  });

  // wizard, step keywords match -> ~25% match, plus file match = high confidence
  const wizardMatch = result.matches.find(m => 
    m.task.toLowerCase().includes('wizard')
  );
  assert.ok(wizardMatch, 'Should match wizard task');
  assert.equal(wizardMatch.confidence, 'high', 'Should be high confidence with file match even at ~25% keywords');
});

test('analyzeTaskCompletion uses synonym expansion for better matching', async () => {
  // Task says "implement", commit says "add" - synonyms should match
  const commits = [
    { sha: 'abc123', commit: { message: 'feat: add config validation logic' } },
  ];
  const files = [
    { filename: 'src/config/validator.py' },
  ];
  
  const github = {
    rest: {
      repos: {
        async compareCommits() {
          return { data: { commits } };
        },
      },
      pulls: {
        async listFiles() {
          return { data: files };
        },
      },
    },
  };

  const taskText = `
- [ ] Implement config validation with proper error handling
`;

  const result = await analyzeTaskCompletion({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    taskText,
    core: buildCore(),
  });

  // "implement" in task should match "add" in commit via synonyms
  // plus "config" and "validation" match directly
  const configMatch = result.matches.find(m => 
    m.task.toLowerCase().includes('config validation')
  );
  assert.ok(configMatch, 'Should match config validation task');
  assert.equal(configMatch.confidence, 'high', 'Should be high confidence with synonym matching');
});

test('autoReconcileTasks updates PR body for high-confidence matches', async () => {
  const prBody = `## Tasks
- [ ] Add step summary output to keepalive loop
- [ ] Add tests for step summary
- [x] Already completed task
`;

  const commits = [
    { sha: 'abc123', commit: { message: 'feat: add step summary output to keepalive loop' } },
  ];
  const files = [
    { filename: '.github/scripts/keepalive_loop.js' },
  ];

  let updatedBody = null;
  const github = {
    rest: {
      pulls: {
        async get() {
          return { data: { body: prBody } };
        },
        async update({ body }) {
          updatedBody = body;
          return { data: {} };
        },
        async listFiles() {
          return { data: files };
        },
      },
      repos: {
        async compareCommits() {
          return { data: { commits } };
        },
      },
    },
  };

  const result = await autoReconcileTasks({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    core: buildCore(),
  });

  assert.ok(result.updated, 'Should update PR body');
  assert.ok(result.tasksChecked > 0, 'Should check at least one task');
  
  if (updatedBody) {
    assert.ok(updatedBody.includes('[x] Add step summary'), 'Should check off matched task');
    assert.ok(updatedBody.includes('[x] Already completed'), 'Should preserve already-checked tasks');
  }
});

test('autoReconcileTasks skips when no high-confidence matches', async () => {
  const prBody = `## Tasks
- [ ] Implement feature X
- [ ] Add tests for feature Y
`;

  const commits = [
    { sha: 'abc123', commit: { message: 'docs: update readme' } },
  ];
  const files = [
    { filename: 'README.md' },
  ];

  let updateCalled = false;
  const github = {
    rest: {
      pulls: {
        async get() {
          return { data: { body: prBody } };
        },
        async update() {
          updateCalled = true;
          return { data: {} };
        },
        async listFiles() {
          return { data: files };
        },
      },
      repos: {
        async compareCommits() {
          return { data: { commits } };
        },
      },
    },
  };

  const result = await autoReconcileTasks({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    core: buildCore(),
  });

  assert.equal(result.updated, false, 'Should not update PR body');
  assert.equal(result.tasksChecked, 0, 'Should not check any tasks');
  assert.equal(updateCalled, false, 'Should not call update API');
});

// ========================================================
// normaliseChecklistSection tests - Simple checkbox conversion
// ========================================================

test('normaliseChecklistSection converts all bullets to checkboxes', () => {
  const { normaliseChecklistSection } = require('../keepalive_loop.js');
  
  const input = `- Deploy application
- Run tests
- Update documentation`;

  const result = normaliseChecklistSection(input);
  const expected = `- [ ] Deploy application
- [ ] Run tests
- [ ] Update documentation`;

  assert.equal(result, expected);
});

test('normaliseChecklistSection preserves existing checkboxes', () => {
  const { normaliseChecklistSection } = require('../keepalive_loop.js');
  
  const input = `- [ ] Deploy application
- [x] Run tests
- [X] Update documentation`;

  const result = normaliseChecklistSection(input);
  
  assert.equal(result, input, 'Should not modify existing checkboxes');
});

test('normaliseChecklistSection handles numbered lists', () => {
  const { normaliseChecklistSection } = require('../keepalive_loop.js');
  
  const input = `- Deploy application
1. Run pytest tests
2. Verify coverage
3. Check CI status
- Update documentation`;

  const result = normaliseChecklistSection(input);
  const expected = `- [ ] Deploy application
1. [ ] Run pytest tests
2. [ ] Verify coverage
3. [ ] Check CI status
- [ ] Update documentation`;

  assert.equal(result, expected);
});

test('normaliseChecklistSection preserves non-list content', () => {
  const { normaliseChecklistSection } = require('../keepalive_loop.js');
  
  const input = `- Deploy application

**Important:** Run all tests

- Update documentation`;

  const result = normaliseChecklistSection(input);
  const expected = `- [ ] Deploy application

**Important:** Run all tests

- [ ] Update documentation`;

  assert.equal(result, expected);
});

