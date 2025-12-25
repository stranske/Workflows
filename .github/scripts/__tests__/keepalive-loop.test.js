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

test('evaluateKeepaliveLoop normalizes numbered lists with parentheses', async () => {
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
