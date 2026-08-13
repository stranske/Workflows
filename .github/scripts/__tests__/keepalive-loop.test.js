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
  buildAuthorityChallengeEvidence,
  selectEscalationDisposition,
} = require('../keepalive_loop.js');
const { formatStateComment, parseStateComment } = require('../keepalive_state.js');
const { signAuthorityChallengeClaim } = require('../keepalive_challenge_due.js');

const authorityClaimInputs = (prNumber, boundaryFingerprint, overrides = {}) => {
  const claim = {
    signingKey: 'test-only-authority-signing-key',
    repository: 'octo/workflows',
    prNumber,
    boundaryFingerprint,
    nonce: overrides.nonce || 'a'.repeat(64),
    sweepRunId: overrides.sweepRunId || '987654321',
    sweepRunAttempt: overrides.sweepRunAttempt || '1',
  };
  return {
    authority_challenge_fingerprint: boundaryFingerprint,
    authority_challenge_claim: JSON.stringify({
      signature: signAuthorityChallengeClaim(claim),
      nonce: claim.nonce,
      sweep_run_id: claim.sweepRunId,
      sweep_run_attempt: claim.sweepRunAttempt,
    }),
    authority_challenge_signing_key: claim.signingKey,
  };
};

const fixturesDir = path.join(__dirname, 'fixtures');
const prBodyFixture = fs.readFileSync(path.join(fixturesDir, 'pr-body.md'), 'utf8');

const buildGithubStub = ({
  pr,
  comments = [],
  labels = [],
  workflowRuns = [],
  workflowJobs = [],
  workflowRun = null,
  annotationsByCheckRunId = {},
  jobLogsByJobId = {},
  failNeedsHumanLabel = false,
  failNeedsAttentionLabel = false,
  failNeedsAttentionRemoval = false,
  failStateCommentWriteAt = 0,
  failWorkflowDispatch = false,
} = {}) => {
  const actions = [];
  let stateCommentWriteCount = 0;
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
        async getWorkflowRun() {
          return { data: workflowRun || {} };
        },
        async listJobsForWorkflowRun() {
          return { data: { jobs: workflowJobs } };
        },
        async downloadJobLogsForWorkflowRun({ job_id: jobId }) {
          const data = jobLogsByJobId[jobId] ?? '';
          const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data);
          return { data: buffer };
        },
        async createWorkflowDispatch(payload) {
          if (failWorkflowDispatch) {
            actions.push({ type: 'workflow-dispatch-failed', ...payload });
            throw new Error('simulated workflow dispatch failure');
          }
          actions.push({ type: 'workflow-dispatch', ...payload });
          return { data: {} };
        },
      },
      checks: {
        async listAnnotations({ check_run_id: checkRunId }) {
          return { data: annotationsByCheckRunId[checkRunId] || [] };
        },
      },
      issues: {
        async listComments() {
          return {
            data: comments.map((comment) => ({
              user: { login: 'agents-workflows-bot[bot]', type: 'Bot' },
              ...comment,
            })),
          };
        },
        async listLabelsOnIssue() {
          return { data: labels.map((name) => ({ name })) };
        },
        async updateComment({ body, comment_id: commentId }) {
          stateCommentWriteCount += 1;
          if (failStateCommentWriteAt === stateCommentWriteCount) {
            actions.push({ type: 'update-failed', body, commentId });
            throw new Error('simulated state comment failure');
          }
          actions.push({ type: 'update', body, commentId });
          return { data: { id: commentId } };
        },
        async createComment({ body }) {
          stateCommentWriteCount += 1;
          if (failStateCommentWriteAt === stateCommentWriteCount) {
            actions.push({ type: 'create-failed', body });
            throw new Error('simulated state comment failure');
          }
          actions.push({ type: 'create', body });
          return { data: { id: 101, html_url: 'https://example.com/101' } };
        },
        async addLabels({ labels }) {
          if (failNeedsHumanLabel && labels.includes('needs-human')) {
            actions.push({ type: 'label-failed', labels });
            throw new Error('simulated needs-human label failure');
          }
          if (failNeedsAttentionLabel && labels.includes('agent:needs-attention')) {
            actions.push({ type: 'label-failed', labels });
            throw new Error('simulated attention label failure');
          }
          actions.push({ type: 'label', labels });
          return { data: {} };
        },
        async removeLabel({ name }) {
          if (failNeedsAttentionRemoval && name === 'agent:needs-attention') {
            actions.push({ type: 'remove-label-failed', name });
            throw new Error('simulated attention label removal failure');
          }
          actions.push({ type: 'remove-label', name });
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

const buildContext = (prNumber = 101, runId = 9001, overrides = {}) => ({
  eventName: overrides.eventName ?? 'pull_request',
  repo: { owner: 'octo', repo: 'workflows' },
  payload: overrides.payload ?? { pull_request: { number: prNumber } },
  runId,
});

const buildCore = () => ({
  info() {},
  warning() {},
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
{"keepalive_enabled": false, "iteration": "2", "max_iterations": 4, "failure_threshold": "7", "trace": "abc", "prompt_scenario": "verification"}
<!-- keepalive-config:end -->
`;
  const config = parseConfig(body);
  assert.equal(config.keepalive_enabled, false);
  assert.equal(config.iteration, 2);
  assert.equal(config.max_iterations, 4);
  assert.equal(config.failure_threshold, 7);
  assert.equal(config.trace, 'abc');
  assert.equal(config.prompt_scenario, 'verification');
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

test('normaliseConfig preserves verifier_agent / progress_review_threshold / complete_gate_failure_rounds', () => {
  const body = `
<!-- keepalive-config:start -->
{"keepalive_enabled": true, "verifier_agent": "claude", "progress_review_threshold": 6, "complete_gate_failure_rounds": 5}
<!-- keepalive-config:end -->
`;
  const config = parseConfig(body);
  assert.equal(config.verifier_agent, 'claude');
  assert.equal(config.progress_review_threshold, 6);
  assert.equal(config.complete_gate_failure_rounds, 5);
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

test('evaluateKeepaliveLoop skips a paused PR even on a green Gate with work remaining (#2267)', async () => {
  const pr = {
    number: 267,
    head: { ref: 'codex/issue-1', sha: 'sha-267' },
    labels: [{ name: 'agent:codex' }, { name: 'agents:paused' }],
    body: '## Tasks\n- [ ] one\n- [ ] two\n## Acceptance Criteria\n- [ ] a\n- [ ] b\n',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-267', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  // Deliberate-break gate (#2267): removing the `pausedByLabel` branch in
  // evaluateKeepaliveLoop makes this same PR dispatch (action 'run') instead of skipping,
  // so this assertion is what catches a regression of the operator pause control.
  assert.equal(result.action, 'skip');
  assert.equal(result.reason, 'paused');
});

test('evaluateKeepaliveLoop skips a needs-human PR until the label is cleared (#2267)', async () => {
  const pr = {
    number: 268,
    head: { ref: 'codex/issue-2', sha: 'sha-268' },
    labels: [{ name: 'agent:codex' }, { name: 'needs-human' }],
    body: '## Tasks\n- [ ] one\n- [ ] two\n## Acceptance Criteria\n- [ ] a\n- [ ] b\n',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-268', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'skip');
  assert.equal(result.reason, 'needs-human');
});

test('evaluateKeepaliveLoop stops when tasks are complete and verification is done', async () => {
  const pr = {
    number: 303,
    head: { ref: 'feature/three', sha: 'sha-3' },
    labels: [{ name: 'agent:codex' }],
    body: prBodyFixture.replace(/- \[ \]/g, '- [x]'),
  };
  const existingState = formatStateComment({
    trace: 'fixture-trace',
    verification: { status: 'done' },
  });
  const github = buildGithubStub({
    pr,
    comments: [{ id: 23, body: existingState, html_url: 'https://example.com/23' }],
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

test('evaluateKeepaliveLoop stops when round budget is exhausted', async () => {
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
  assert.equal(result.reason, 'round-budget-exhausted');
});

test('evaluateKeepaliveLoop grants a forced recovery lease across the round budget', async () => {
  const pr = {
    number: 406,
    head: { ref: 'feature/forced-budget-recovery', sha: 'sha-forced-budget' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a\n<!-- keepalive-config: {"iteration": 5, "max_iterations": 5} -->',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-forced-budget', conclusion: 'success' }],
  });

  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    forceRetry: true,
  });

  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'ready');
  assert.equal(result.forceRetry, true);
});

test('evaluateKeepaliveLoop grants a forced recovery lease after verification exhaustion', async () => {
  const pr = {
    number: 408,
    head: { ref: 'feature/forced-verification-recovery', sha: 'sha-forced-verification' },
    labels: [{ name: 'agent:codex' }],
    body: prBodyFixture.replace(/- \[ \]/g, '- [x]'),
  };
  const existingState = formatStateComment({
    trace: 'fixture-trace',
    verification: { status: 'failed', iteration: 2, attempt_count: 2 },
  });
  const github = buildGithubStub({
    pr,
    comments: [{ id: 24, body: existingState, html_url: 'https://example.com/24' }],
    workflowRuns: [{ head_sha: 'sha-forced-verification', conclusion: 'success' }],
  });

  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    forceRetry: true,
  });

  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'fix-verification-gaps');
});

test('evaluateKeepaliveLoop uses a forced lease to repair an exhausted complete Gate', async () => {
  const pr = {
    number: 409,
    head: { ref: 'feature/forced-complete-gate-recovery', sha: 'sha-forced-complete-gate' },
    labels: [{ name: 'agent:codex' }],
    body: prBodyFixture.replace(/- \[ \]/g, '- [x]'),
  };
  const existingState = formatStateComment({
    trace: 'fixture-trace',
    iteration: 4,
    max_iterations: 12,
    consecutive_fix_rounds: 2,
    complete_gate_failure_rounds: 3,
    complete_gate_failure_rounds_max: 3,
  });
  const github = buildGithubStub({
    pr,
    comments: [{ id: 25, body: existingState, html_url: 'https://example.com/25' }],
    workflowRuns: [{ id: 1004, head_sha: 'sha-forced-complete-gate', conclusion: 'failure' }],
  });
  github.rest.actions.listJobsForWorkflowRun = async () => ({
    data: { jobs: [{ name: 'lint (ruff)', status: 'completed', conclusion: 'failure' }] },
  });

  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    forceRetry: true,
  });

  assert.equal(result.action, 'fix');
  assert.equal(result.reason, 'force-retry-fix-lint');
});

test('evaluateKeepaliveLoop stops at max iterations even when productive with tasks remaining', async () => {
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
  assert.equal(result.action, 'stop', 'Should stop once the per-PR round budget is exhausted');
  assert.equal(result.reason, 'round-budget-exhausted');
});

test('evaluateKeepaliveLoop stops at max iterations before fixable gate failures', async () => {
  const pr = {
    number: 407,
    head: { ref: 'feature/budget-gate-fail', sha: 'sha-budget-fail' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const stateComment = formatStateComment({
    trace: '',
    iteration: 5,
    max_iterations: 5,
    last_files_changed: 2,
    failure: {},
  });
  const github = buildGithubStub({
    pr,
    comments: [{ id: 25, body: stateComment, html_url: 'https://example.com/25' }],
    workflowRuns: [{ id: 1007, head_sha: 'sha-budget-fail', conclusion: 'failure' }],
  });
  github.rest.actions.listJobsForWorkflowRun = async () => ({
    data: { jobs: [{ name: 'test (3.12)', status: 'completed', conclusion: 'failure' }] },
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'stop');
  assert.equal(result.reason, 'round-budget-exhausted');
  assert.notEqual(result.reason, 'fix-test');
});

test('evaluateKeepaliveLoop falls back to default budget for invalid max iterations', async () => {
  const cases = [
    { name: 'negative config', configValue: -3, stateValue: 0 },
    { name: 'partial numeric string config', configValue: '3 rounds', stateValue: 0 },
    { name: 'decimal config', configValue: 3.9, stateValue: 0 },
    { name: 'partial numeric string state', configValue: 0, stateValue: '3 rounds' },
    { name: 'decimal state', configValue: 0, stateValue: 3.9 },
  ];

  for (const testCase of cases) {
    const pr = {
      number: 408,
      head: {
        ref: `feature/invalid-budget-${testCase.name.replaceAll(' ', '-')}`,
        sha: `sha-invalid-budget-${testCase.name}`,
      },
      labels: [{ name: 'agent:codex' }],
      body: `<!-- keepalive-config: ${JSON.stringify({ keepalive_enabled: true, max_iterations: testCase.configValue })} -->\n## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a`,
    };
    const stateComment = formatStateComment({
      trace: '',
      iteration: 12,
      max_iterations: testCase.stateValue,
      last_files_changed: 1,
      failure: {},
    });
    const github = buildGithubStub({
      pr,
      comments: [{ id: 26, body: stateComment, html_url: 'https://example.com/26' }],
      workflowRuns: [{ id: 1008, head_sha: pr.head.sha, conclusion: 'success' }],
    });

    const result = await evaluateKeepaliveLoop({
      github,
      context: buildContext(pr.number),
      core: buildCore(),
    });

    assert.equal(result.action, 'stop', testCase.name);
    assert.equal(result.reason, 'round-budget-exhausted', testCase.name);
    assert.equal(result.maxIterations, 12, testCase.name);
  }
});

test('evaluateKeepaliveLoop triggers progress review without file changes', async () => {
  const pr = {
    number: 406,
    head: { ref: 'feature/progress-review', sha: 'sha-progress' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const stateComment = formatStateComment({
    trace: '',
    iteration: 2,
    max_iterations: 6,
    progress_review_threshold: 2,
    rounds_without_task_completion: 1,
    last_files_changed: 0,
    prev_files_changed: 0,
    tasks: { unchecked: 2 },
  });
  const comments = [
    { id: 24, body: stateComment, html_url: 'https://example.com/24' },
  ];
  const github = buildGithubStub({
    pr,
    comments,
    workflowRuns: [{ head_sha: 'sha-progress', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'review');
  assert.equal(result.reason, 'progress-review-2');
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
    data: { jobs: [{ name: 'test (3.11)', status: 'completed', conclusion: 'failure' }] },
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'fix');
  assert.equal(result.reason, 'fix-test');
  assert.equal(result.promptMode, 'fix_ci');
  assert.equal(result.promptFile, '.github/codex/prompts/fix_ci_failures.md');
});

test('evaluateKeepaliveLoop uses normal prompt when tasks remain', async () => {
  const pr = {
    number: 5051,
    head: { ref: 'feature/next-task', sha: 'sha-next' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-next', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'ready');
  assert.equal(result.promptMode, 'normal');
  assert.equal(result.promptFile, '.github/codex/prompts/keepalive_next_task.md');
});

test('evaluateKeepaliveLoop honors prompt scenario overrides from config', async () => {
  const pr = {
    number: 5050,
    head: { ref: 'feature/override', sha: 'sha-override' },
    labels: [{ name: 'agent:codex' }],
    body: [
      '## Tasks',
      '- [ ] one',
      '## Acceptance Criteria',
      '- [ ] a',
      '<!-- keepalive-config: {"prompt_scenario": "verification"} -->',
    ].join('\n'),
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 2001, head_sha: 'sha-override', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'run');
  assert.equal(result.promptMode, 'verify');
});

test('evaluateKeepaliveLoop dispatches fix when gate fails with lint failures', async () => {
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
    data: { jobs: [{ name: 'lint (ruff)', status: 'completed', conclusion: 'failure' }] },
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'fix');
  assert.equal(result.reason, 'fix-lint');
});

test('evaluateKeepaliveLoop bypasses gate fix after consecutive fix rounds exhausted', async () => {
  const pr = {
    number: 508,
    head: { ref: 'feature/lint-bypass', sha: 'sha-lb' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  // State shows 2 consecutive fix rounds already attempted
  const stateComment = formatStateComment({
    trace: '',
    iteration: 3,
    consecutive_fix_rounds: 2,
  });
  const comments = [
    { id: 33, body: stateComment, html_url: 'https://example.com/33' },
  ];
  const github = buildGithubStub({
    pr,
    comments,
    workflowRuns: [{ id: 2001, head_sha: 'sha-lb', conclusion: 'failure' }],
  });
  // Override to return lint failures
  github.rest.actions.listJobsForWorkflowRun = async () => ({
    data: { jobs: [{ name: 'lint (ruff)', status: 'completed', conclusion: 'failure' }] },
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'run', 'Should bypass gate fix and continue with tasks');
  assert.equal(result.reason, 'bypass-fix-lint', 'Should report bypass reason');
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
  assert.equal(result.reason, 'gate-cancelled-transient');
});

test('evaluateKeepaliveLoop bypasses rate limit cancelled gate', async () => {
  const pr = {
    number: 509,
    head: { ref: 'feature/cancelled-rate', sha: 'sha-cancelled-rate' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 2001, head_sha: 'sha-cancelled-rate', conclusion: 'cancelled' }],
    workflowJobs: [{ id: 3001, check_run_id: 9001, name: 'gate', status: 'completed', conclusion: 'cancelled' }],
    annotationsByCheckRunId: {
      9001: [{ message: 'Secondary rate limit exceeded for GitHub API.' }],
    },
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  // Rate limits are infrastructure noise - work should proceed
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'bypass-rate-limit-gate');
});

test('evaluateKeepaliveLoop bypasses rate limit cancelled gate from logs', async () => {
  const pr = {
    number: 510,
    head: { ref: 'feature/cancelled-rate-logs', sha: 'sha-cancelled-rate-logs' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 2002, head_sha: 'sha-cancelled-rate-logs', conclusion: 'cancelled' }],
    workflowJobs: [{ id: 3002, name: 'gate', status: 'completed', conclusion: 'cancelled' }],
    jobLogsByJobId: {
      3002: 'Error: API rate limit exceeded, please retry later.',
    },
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  // Rate limits are infrastructure noise - work should proceed
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'bypass-rate-limit-gate');
});

test('evaluateKeepaliveLoop force_retry bypasses cancelled gate', async () => {
  const pr = {
    number: 511,
    head: { ref: 'feature/force-retry', sha: 'sha-force-retry' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 2003, head_sha: 'sha-force-retry', conclusion: 'cancelled' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    forceRetry: true,
  });
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'force-retry-cancelled');
  assert.equal(result.forceRetry, true);
});

test('evaluateKeepaliveLoop rate limit bypass takes precedence over force_retry', async () => {
  const pr = {
    number: 512,
    head: { ref: 'feature/force-retry-rate', sha: 'sha-force-retry-rate' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 2004, head_sha: 'sha-force-retry-rate', conclusion: 'cancelled' }],
    workflowJobs: [{ id: 3004, check_run_id: 9004, name: 'gate', status: 'completed', conclusion: 'cancelled' }],
    annotationsByCheckRunId: {
      9004: [{ message: 'Secondary rate limit exceeded for GitHub API.' }],
    },
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    forceRetry: true,
  });
  // Rate limit bypass is automatic infrastructure handling - takes precedence
  // forceRetry is still honored for non-rate-limit cases
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'bypass-rate-limit-gate');
});

test('evaluateKeepaliveLoop force_retry bypasses failed gate', async () => {
  const pr = {
    number: 513,
    head: { ref: 'feature/force-retry-failed', sha: 'sha-force-retry-failed' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 2005, head_sha: 'sha-force-retry-failed', conclusion: 'failure' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    forceRetry: true,
  });
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'force-retry-gate');
});

test('evaluateKeepaliveLoop overridePrNumber takes precedence', async () => {
  const pr = {
    number: 514,
    head: { ref: 'feature/override-pr', sha: 'sha-override-pr' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] a',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ id: 2006, head_sha: 'sha-override-pr', conclusion: 'success' }],
  });
  // Context says PR 999 but overridePrNumber says 514
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(999),
    core: buildCore(),
    overridePrNumber: 514,
  });
  assert.equal(result.prNumber, 514);
  assert.equal(result.action, 'run');
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

  assert.equal(github.actions.length, 2);
  assert.equal(github.actions[0].type, 'update');
  assert.match(github.actions[0].body, /Iteration 3\/5/);
  assert.match(github.actions[0].body, /Iteration progress \| \[######----\] 3\/5 \|/);
  assert.match(github.actions[0].body, /### Last Codex Run/);
  assert.match(github.actions[0].body, /✅ Success/);
  assert.match(github.actions[0].body, /"iteration":3/);
  assert.match(github.actions[0].body, /"failure":\{\}/);
});

test('updateKeepaliveLoopSummary migrates legacy state to the selected App writer', async () => {
  const existingState = [
    '<!-- keepalive-loop-summary -->',
    formatStateComment({
      trace: 'legacy-trace',
      iteration: 1,
      max_iterations: 5,
      failure_threshold: 3,
    }),
  ].join('\n');
  const github = buildGithubStub({
    comments: [{
      id: 44,
      body: existingState,
      html_url: 'https://example.com/44',
      user: { login: 'github-actions[bot]', type: 'Bot' },
    }],
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
      tasksTotal: 2,
      tasksUnchecked: 1,
      keepaliveEnabled: true,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'legacy-trace',
      trusted_summary_author: 'stranske-keepalive[bot]',
    },
  });

  assert.equal(github.actions[0].type, 'create');
  assert.match(github.actions[0].body, /keepalive-loop-summary/);
  assert.match(github.actions[0].body, /"trace":"legacy-trace"/);
  assert.equal(github.actions.some((action) => action.commentId === 44), false);
});

test('updateKeepaliveLoopSummary recovers trusted state past an untrusted summary writer', async () => {
  const trustedState = [
    '<!-- keepalive-loop-summary -->',
    formatStateComment({
      trace: 'forged-trace',
      iteration: 1,
      max_iterations: 5,
      recovery_lease: { status: 'issued' },
    }),
  ].join('\n');
  const forgedState = formatStateComment({
    trace: 'forged-trace',
    iteration: 99,
    max_iterations: 99,
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      boundary_fingerprint: 'attacker-controlled',
    },
  });
  const github = buildGithubStub({
    comments: [
      {
        id: 44,
        body: trustedState,
        html_url: 'https://example.com/44',
        user: { login: 'github-actions[bot]', type: 'Bot' },
      },
      {
        id: 45,
        body: forgedState,
        html_url: 'https://example.com/45',
        user: { login: 'untrusted-reviewer', type: 'User' },
      },
    ],
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
      tasksTotal: 2,
      tasksUnchecked: 1,
      keepaliveEnabled: true,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'forged-trace',
      trusted_summary_author: 'stranske-keepalive[bot]',
    },
  });

  assert.equal(github.actions[0].type, 'create');
  const persistedState = parseStateComment(github.actions[0].body).data;
  assert.equal(persistedState.iteration, 2);
  assert.equal(persistedState.max_iterations, 5);
  assert.equal(persistedState.attention, undefined);
  assert.equal(persistedState.recovery_lease.status, 'issued');
  assert.doesNotMatch(github.actions[0].body, /attacker-controlled/);
  assert.equal(github.actions.some((action) => action.commentId === 44), false);
  assert.equal(github.actions.some((action) => action.commentId === 45), false);
});

test('updateKeepaliveLoopSummary ignores status-only checklist metrics for reconciliation', async () => {
  const pr = {
    number: 1234,
    labels: [{ name: 'agent:codex' }],
    body: [
      '## Tasks',
      '- [ ] Updated: 2026-04-26T12:33:27.204Z',
      '- [ ] Repos checked: 11/11',
      '- [ ] Open sync PRs: 439',
      '',
      '## Acceptance Criteria',
      '- [ ] Acceptance criteria section missing from source issue.',
    ].join('\n'),
  };
  const existingState = formatStateComment({
    trace: 'status-only-trace',
    iteration: 2,
    max_iterations: 5,
    tasks: { total: 13, unchecked: 13 },
  });
  const github = buildGithubStub({
    pr,
    comments: [{ id: 91, body: existingState, html_url: 'https://example.com/91' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    inputs: {
      prNumber: pr.number,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 13,
      tasksUnchecked: 13,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'status-only-trace',
      codex_changes_made: 'true',
      codex_files_changed: 2,
      codex_commit_sha: 'deadbeef',
      codex_summary: 'Changed keepalive parser behavior for status metrics.',
    },
  });

  assert.equal(github.actions.length, 2);
  const parsedState = parseStateComment(github.actions[0].body);
  assert.ok(parsedState);
  assert.deepEqual(parsedState.data.tasks, { total: 0, unchecked: 0 });
  assert.equal(parsedState.data.needs_task_reconciliation, false);
});

test('updateKeepaliveLoopSummary reuses cached PR data for labels and body', async () => {
  const pr = {
    number: 321,
    labels: [{ name: 'agent:codex' }],
    body: prBodyFixture,
  };
  const github = buildGithubStub({ pr });
  let prCalls = 0;
  const originalGet = github.rest.pulls.get;
  github.rest.pulls.get = async (...args) => {
    prCalls += 1;
    return originalGet(...args);
  };

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    inputs: {
      prNumber: pr.number,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 2,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
    },
  });

  assert.equal(prCalls, 1);
});

test('evaluateKeepaliveLoop invalidates cache and emits cache metrics', async () => {
  const pr = {
    number: 808,
    head: { ref: 'feature/cache', sha: 'sha-808' },
    labels: [],
    body: prBodyFixture,
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: pr.head.sha, conclusion: 'success' }],
  });
  const cacheCalls = { invalidations: [], metrics: 0 };
  // Single shared cache sentinel after issue #2278 consolidation.
  github.__githubApiCache = {
    buildPrCacheKey() {
      return 'pr-key';
    },
    async getOrSet({ fetcher }) {
      return fetcher();
    },
    invalidateForWebhook(args) {
      cacheCalls.invalidations.push(args);
      return { invalidated: 1, prNumbers: [pr.number] };
    },
    emitMetrics() {
      cacheCalls.metrics += 1;
    },
  };

  await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });

  assert.equal(cacheCalls.invalidations.length, 1);
  assert.equal(cacheCalls.invalidations[0].eventName, 'pull_request');
  assert.equal(cacheCalls.invalidations[0].owner, 'octo');
  assert.equal(cacheCalls.invalidations[0].repo, 'workflows');
  assert.equal(cacheCalls.metrics, 1);
});

test('updateKeepaliveLoopSummary logs timeout warning near expiration', async () => {
  const nowMs = Date.parse('2026-01-01T00:00:00Z');
  const realNow = Date.now;
  Date.now = () => nowMs;
  try {
    const existingState = formatStateComment({
      trace: 'trace-timeout',
      iteration: 1,
      max_iterations: 5,
    });
    const pr = {
      number: 555,
      head: { ref: 'feature/timeout', sha: 'sha-55' },
      labels: [{ name: 'agent:codex' }],
      body: prBodyFixture,
    };
    const github = buildGithubStub({
      pr,
      comments: [{ id: 77, body: existingState, html_url: 'https://example.com/77' }],
      workflowRun: { run_started_at: new Date(nowMs - 41 * 60 * 1000).toISOString() },
    });
    await updateKeepaliveLoopSummary({
      github,
      context: buildContext(555),
      core: buildCore(),
      inputs: {
        prNumber: 555,
        action: 'run',
        runResult: 'success',
        gateConclusion: 'success',
        tasksTotal: 3,
        tasksUnchecked: 1,
        keepaliveEnabled: true,
        autofixEnabled: false,
        iteration: 1,
        maxIterations: 5,
        failureThreshold: 3,
        trace: 'trace-timeout',
        codex_changes_made: 'true',
        codex_files_changed: 2,
        codex_commit_sha: 'abcd9999',
        codex_summary: 'Near timeout check.',
      },
    });

    const body = github.actions[0].body;
    assert.match(body, /Timeout \| 45 min \(default\)/);
    assert.match(body, /Timeout warning/);

    const parsed = parseStateComment(body);
    assert.equal(parsed.data.timeout.resolved_minutes, 45);
    assert.equal(parsed.data.timeout.source, 'default');
    assert.ok(parsed.data.timeout.warning);
  } finally {
    Date.now = realNow;
  }
});

test('updateKeepaliveLoopSummary logs timeout warning at 80 percent usage', async () => {
  const nowMs = Date.parse('2026-03-01T00:00:00Z');
  const realNow = Date.now;
  const warnings = [];
  Date.now = () => nowMs;
  try {
    const existingState = formatStateComment({
      trace: 'trace-timeout-usage',
      iteration: 1,
      max_iterations: 5,
    });
    const pr = {
      number: 557,
      head: { ref: 'feature/timeout-usage', sha: 'sha-57' },
      labels: [{ name: 'agent:codex' }],
      body: prBodyFixture,
    };
    const github = buildGithubStub({
      pr,
      comments: [{ id: 79, body: existingState, html_url: 'https://example.com/79' }],
      workflowRun: { run_started_at: new Date(nowMs - 36 * 60 * 1000).toISOString() },
    });
    const core = {
      info() {},
      setOutput() {},
      warning(message) {
        warnings.push(message);
      },
    };
    await updateKeepaliveLoopSummary({
      github,
      context: buildContext(557),
      core,
      inputs: {
        prNumber: 557,
        action: 'run',
        runResult: 'success',
        gateConclusion: 'success',
        tasksTotal: 3,
        tasksUnchecked: 1,
        keepaliveEnabled: true,
        autofixEnabled: false,
        iteration: 1,
        maxIterations: 5,
        failureThreshold: 3,
        trace: 'trace-timeout-usage',
        codex_changes_made: 'true',
        codex_files_changed: 2,
        codex_commit_sha: 'abcd2000',
        codex_summary: 'Usage ratio timeout check.',
      },
    });

    const body = github.actions[0].body;
    assert.match(body, /Timeout warning/);
    assert.match(body, /80% consumed/);
    assert.match(body, /usage threshold/);

    const parsed = parseStateComment(body);
    assert.equal(parsed.data.timeout.warning.reason, 'usage');
    assert.equal(parsed.data.timeout.warning.percent, 80);
    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /80% consumed, 9m remaining/);
  } finally {
    Date.now = realNow;
  }
});

test('updateKeepaliveLoopSummary uses workflow_run payload start time for warnings', async () => {
  const nowMs = Date.parse('2026-04-01T00:00:00Z');
  const realNow = Date.now;
  const warnings = [];
  Date.now = () => nowMs;
  try {
    const existingState = formatStateComment({
      trace: 'trace-timeout-payload',
      iteration: 1,
      max_iterations: 5,
    });
    const pr = {
      number: 562,
      head: { ref: 'feature/timeout-payload', sha: 'sha-62' },
      labels: [{ name: 'agent:codex' }],
      body: prBodyFixture,
    };
    const github = buildGithubStub({
      pr,
      comments: [{ id: 84, body: existingState, html_url: 'https://example.com/84' }],
      workflowRun: {},
    });
    const core = {
      info() {},
      setOutput() {},
      warning(message) {
        warnings.push(message);
      },
    };
    await updateKeepaliveLoopSummary({
      github,
      context: buildContext(562, 9001, {
        eventName: 'workflow_run',
        payload: {
          workflow_run: {
            run_started_at: new Date(nowMs - 36 * 60 * 1000).toISOString(),
          },
        },
      }),
      core,
      inputs: {
        prNumber: 562,
        action: 'run',
        runResult: 'success',
        gateConclusion: 'success',
        tasksTotal: 3,
        tasksUnchecked: 1,
        keepaliveEnabled: true,
        autofixEnabled: false,
        iteration: 1,
        maxIterations: 5,
        failureThreshold: 3,
        trace: 'trace-timeout-payload',
        codex_changes_made: 'true',
        codex_files_changed: 2,
        codex_commit_sha: 'abcd2200',
        codex_summary: 'Payload timeout warning check.',
      },
    });

    const body = github.actions[0].body;
    assert.match(body, /Timeout warning/);
    assert.equal(warnings.length, 1);
  } finally {
    Date.now = realNow;
  }
});

test('updateKeepaliveLoopSummary does not warn before 80 percent usage', async () => {
  const warnings = [];
  const existingState = formatStateComment({
    trace: 'trace-timeout-prewarn',
    iteration: 1,
    max_iterations: 5,
  });
  const pr = {
    number: 561,
    head: { ref: 'feature/timeout-prewarn', sha: 'sha-61' },
    labels: [{ name: 'agent:codex' }],
    body: prBodyFixture,
  };
  const github = buildGithubStub({
    pr,
    comments: [{ id: 83, body: existingState, html_url: 'https://example.com/83' }],
  });
  const core = {
    info() {},
    setOutput() {},
    warning(message) {
      warnings.push(message);
    },
  };
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(561),
    core,
    inputs: {
      prNumber: 561,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 1,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-timeout-prewarn',
      elapsed_ms: 35 * 60 * 1000,
      codex_changes_made: 'true',
      codex_files_changed: 1,
      codex_commit_sha: 'abcd2100',
      codex_summary: 'Pre-warning timeout check.',
    },
  });

  const body = github.actions[0].body;
  assert.doesNotMatch(body, /Timeout warning/);

  const parsed = parseStateComment(body);
  assert.equal(parsed.data.timeout.warning, null);
  assert.equal(warnings.length, 0);
});

test('updateKeepaliveLoopSummary treats percent warning ratio inputs as percentages', async () => {
  const warnings = [];
  const existingState = formatStateComment({
    trace: 'trace-timeout-percent',
    iteration: 1,
    max_iterations: 5,
  });
  const pr = {
    number: 560,
    head: { ref: 'feature/timeout-percent', sha: 'sha-60' },
    labels: [{ name: 'agent:codex' }],
    body: prBodyFixture,
  };
  const github = buildGithubStub({
    pr,
    comments: [{ id: 82, body: existingState, html_url: 'https://example.com/82' }],
  });
  const core = {
    info() {},
    setOutput() {},
    warning(message) {
      warnings.push(message);
    },
  };

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(560),
    core,
    inputs: {
      prNumber: 560,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 1,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-timeout-percent',
      elapsed_ms: 39 * 60 * 1000,
      timeout_warning_ratio: 90,
      timeout_warning_minutes: 1,
      codex_changes_made: 'true',
      codex_files_changed: 1,
      codex_commit_sha: 'abcd4000',
      codex_summary: 'Percent warning ratio check.',
    },
  });

  const body = github.actions[0].body;
  assert.doesNotMatch(body, /Timeout warning/);

  const parsed = parseStateComment(body);
  assert.equal(parsed.data.timeout.warning, null);
  assert.equal(warnings.length, 0);
});

test('updateKeepaliveLoopSummary logs timeout warning when elapsed_ms crosses 80 percent', async () => {
  const warnings = [];
  const existingState = formatStateComment({
    trace: 'trace-timeout-elapsed',
    iteration: 1,
    max_iterations: 5,
  });
  const pr = {
    number: 559,
    head: { ref: 'feature/timeout-elapsed', sha: 'sha-59' },
    labels: [{ name: 'agent:codex' }],
    body: prBodyFixture,
  };
  const github = buildGithubStub({
    pr,
    comments: [{ id: 81, body: existingState, html_url: 'https://example.com/81' }],
  });
  const core = {
    info() {},
    setOutput() {},
    warning(message) {
      warnings.push(message);
    },
  };
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(559),
    core,
    inputs: {
      prNumber: 559,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 1,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-timeout-elapsed',
      elapsed_ms: 36 * 60 * 1000,
      codex_changes_made: 'true',
      codex_files_changed: 2,
      codex_commit_sha: 'abcd2222',
      codex_summary: 'Elapsed override timeout check.',
    },
  });

  const body = github.actions[0].body;
  assert.match(body, /Timeout warning/);

  const parsed = parseStateComment(body);
  assert.equal(parsed.data.timeout.warning.reason, 'usage');
  assert.equal(parsed.data.timeout.warning.percent, 80);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /80% consumed/);
});

test('updateKeepaliveLoopSummary reads timeout override from workflow inputs payload', async () => {
  const nowMs = Date.parse('2026-04-01T00:00:00Z');
  const realNow = Date.now;
  Date.now = () => nowMs;
  try {
    const existingState = formatStateComment({
      trace: 'trace-timeout-input',
      iteration: 1,
      max_iterations: 5,
    });
    const pr = {
      number: 558,
      head: { ref: 'feature/timeout-input', sha: 'sha-58' },
      labels: [{ name: 'agent:codex' }],
      body: prBodyFixture,
    };
    const github = buildGithubStub({
      pr,
      comments: [{ id: 80, body: existingState, html_url: 'https://example.com/80' }],
      workflowRun: { run_started_at: new Date(nowMs - 10 * 60 * 1000).toISOString() },
    });
    await updateKeepaliveLoopSummary({
      github,
      context: buildContext(558, 9001, {
        eventName: 'workflow_dispatch',
        payload: { inputs: { timeout_minutes: '75' } },
      }),
      core: buildCore(),
      inputs: {
        prNumber: 558,
        action: 'run',
        runResult: 'success',
        gateConclusion: 'success',
        tasksTotal: 3,
        tasksUnchecked: 1,
        keepaliveEnabled: true,
        autofixEnabled: false,
        iteration: 1,
        maxIterations: 5,
        failureThreshold: 3,
        trace: 'trace-timeout-input',
        codex_changes_made: 'true',
        codex_files_changed: 1,
        codex_commit_sha: 'abcd3000',
        codex_summary: 'Workflow input override.',
      },
    });

    const body = github.actions[0].body;
    assert.match(body, /Timeout \| 75 min \(override\)/);

    const parsed = parseStateComment(body);
    assert.equal(parsed.data.timeout.resolved_minutes, 75);
    assert.equal(parsed.data.timeout.source, 'override');
  } finally {
    Date.now = realNow;
  }
});

test('updateKeepaliveLoopSummary honors timeout warning overrides', async () => {
  const nowMs = Date.parse('2026-02-01T00:00:00Z');
  const realNow = Date.now;
  Date.now = () => nowMs;
  try {
    const existingState = formatStateComment({
      trace: 'trace-warning-hint',
      iteration: 1,
      max_iterations: 5,
    });
    const pr = {
      number: 556,
      head: { ref: 'feature/timeout-warning', sha: 'sha-56' },
      labels: [{ name: 'agent:codex' }],
      body: prBodyFixture,
    };
    const github = buildGithubStub({
      pr,
      comments: [{ id: 78, body: existingState, html_url: 'https://example.com/78' }],
      workflowRun: { run_started_at: new Date(nowMs - 12 * 60 * 1000).toISOString() },
    });
    await updateKeepaliveLoopSummary({
      github,
      context: buildContext(556),
      core: buildCore(),
      inputs: {
        prNumber: 556,
        action: 'run',
        runResult: 'success',
        gateConclusion: 'success',
        tasksTotal: 3,
        tasksUnchecked: 1,
        keepaliveEnabled: true,
        autofixEnabled: false,
        iteration: 1,
        maxIterations: 5,
        failureThreshold: 3,
        trace: 'trace-warning-hint',
        codex_changes_made: 'true',
        codex_files_changed: 1,
        codex_commit_sha: 'abcd1000',
        codex_summary: 'Override timeout warning threshold.',
        timeout_minutes: 20,
        timeout_warning_minutes: 10,
        timeout_warning_ratio: 0.9,
      },
    });

    const body = github.actions[0].body;
    assert.match(body, /Timeout \| 20 min \(override\)/);
    assert.match(body, /Timeout warning/);

    const parsed = parseStateComment(body);
    assert.equal(parsed.data.timeout.resolved_minutes, 20);
    assert.equal(parsed.data.timeout.source, 'override');
    assert.equal(parsed.data.timeout.warning.reason, 'remaining');
  } finally {
    Date.now = realNow;
  }
});

test('updateKeepaliveLoopSummary tracks attempt history across rounds', async () => {
  const existingState = formatStateComment({
    trace: 'trace-history',
    iteration: 1,
    attempts: [{ iteration: 1, action: 'run', reason: 'ready', run_result: 'success' }],
  });
  const github = buildGithubStub({
    comments: [{ id: 40, body: existingState, html_url: 'https://example.com/40' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(321),
    core: buildCore(),
    inputs: {
      prNumber: 321,
      action: 'run',
      reason: 'ready',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 1,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-history',
      prompt_mode: 'normal',
      prompt_file: '.github/codex/prompts/keepalive_next_task.md',
    },
  });

  const parsed = parseStateComment(github.actions[0].body);
  assert.ok(parsed);
  assert.equal(parsed.version, 'v1');
  const attempts = parsed.data.attempts;
  assert.equal(attempts.length, 2);
  assert.equal(attempts[1].iteration, 2);
  assert.equal(attempts[1].action, 'run');
  assert.equal(attempts[1].reason, 'ready');
  assert.equal(attempts[1].run_result, 'success');
  assert.equal(attempts[1].prompt_mode, 'normal');
});

test('updateKeepaliveLoopSummary stores attempted task focus', async () => {
  const existingState = formatStateComment({
    trace: 'trace-focus',
    iteration: 0,
    current_focus: 'Task B',
  });
  const pr = {
    number: 654,
    head: { ref: 'feature/attempted', sha: 'sha-attempt' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] Task A\n- [ ] Task B\n## Acceptance Criteria\n- [ ] pass',
  };
  const github = buildGithubStub({
    pr,
    comments: [{ id: 41, body: existingState, html_url: 'https://example.com/41' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    inputs: {
      prNumber: pr.number,
      action: 'run',
      reason: 'ready',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 3,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 0,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-focus',
    },
  });

  const parsed = parseStateComment(github.actions[0].body);
  assert.ok(parsed);
  assert.equal(parsed.data.last_focus, 'Task B');
  assert.ok(Array.isArray(parsed.data.attempted_tasks));
  assert.equal(parsed.data.attempted_tasks[0].task, 'Task B');
});

test('updateKeepaliveLoopSummary marks verification when verifier succeeds', async () => {
  const existingState = formatStateComment({
    trace: 'trace-verify',
    iteration: 1,
  });
  const pr = {
    number: 777,
    head: { ref: 'feature/verify-summary', sha: 'sha-ver' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [x] done\n## Acceptance Criteria\n- [x] pass',
  };
  const github = buildGithubStub({
    pr,
    comments: [{ id: 52, body: existingState, html_url: 'https://example.com/52' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
    inputs: {
      prNumber: pr.number,
      action: 'run',
      reason: 'verify-acceptance',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 2,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-verify',
    },
  });

  const parsed = parseStateComment(github.actions[0].body);
  assert.ok(parsed);
  assert.equal(parsed.data.verification.status, 'done');
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

  assert.equal(github.actions.length, 2);
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

  assert.equal(github.actions.length, 2);
  assert.equal(github.actions[0].type, 'update');
  // Should preserve iteration=2 from state, NOT use stale iteration=0 from inputs
  assert.match(github.actions[0].body, /"iteration":2/);
  assert.match(github.actions[0].body, /Iteration 2\/5/);
});

test('updateKeepaliveLoopSummary suppresses first missing-agent-label PR comment', async () => {
  const outputs = {};
  const github = buildGithubStub({
    pr: {
      number: 125,
      labels: [{ name: 'codex' }, { name: 'codex-automation' }],
      body: '## Tasks\n- [ ] one\n## Acceptance Criteria\n- [ ] done',
    },
    comments: [],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(125),
    core: {
      info() {},
      setOutput(name, value) {
        outputs[name] = value;
      },
    },
    inputs: {
      prNumber: 125,
      action: 'wait',
      reason: 'missing-agent-label',
      gateConclusion: 'success',
      tasksTotal: 2,
      tasksUnchecked: 2,
      keepaliveEnabled: false,
      autofixEnabled: false,
      iteration: 0,
      maxIterations: 5,
    },
  });

  assert.deepEqual(github.actions, []);
  assert.equal(outputs.comment_suppressed, 'true');
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
  assert.equal(github.actions.length, 2);
  assert.equal(github.actions[0].type, 'update');
  // Failure state should be cleared for transient wait conditions
  assert.match(github.actions[0].body, /"failure":\{\}/);
  // Should NOT have -repeat suffix since we're not counting wait states
  assert.doesNotMatch(github.actions[0].body, /gate-not-success-repeat/);
});

test('updateKeepaliveLoopSummary marks deferred rate limit cancellations as transient', async () => {
  const existingState = formatStateComment({
    trace: 'trace-defer',
    iteration: 1,
    failure_threshold: 3,
    failure: { reason: 'gate-not-success', count: 1 },
  });
  const github = buildGithubStub({
    comments: [{ id: 50, body: existingState, html_url: 'https://example.com/50' }],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(500),
    core: buildCore(),
    inputs: {
      prNumber: 500,
      action: 'defer',
      reason: 'gate-cancelled-rate-limit',
      gateConclusion: 'cancelled',
      tasksTotal: 2,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-defer',
    },
  });

  assert.equal(github.actions.length, 2);
  const updateAction = github.actions[0];
  assert.equal(updateAction.type, 'update');
  assert.match(updateAction.body, /Disposition \| deferred \(transient\)/);
  assert.match(updateAction.body, /Deferred/);
  assert.match(updateAction.body, /"failure":\{\}/);
});

test('updateKeepaliveLoopSummary routes repeated actual failures to automation retry', async () => {
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

  const updateAction = github.actions.find((action) => action.type === 'update');
  assert.ok(updateAction);
  assert.match(updateAction.body, /agent-run-failed-repeat/);
  assert.match(updateAction.body, /AGENT FAILED/);
  assert.match(updateAction.body, /Automation Recovery Required/);

  const retryLabel = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('agent:retry')
  );
  assert.equal(retryLabel, undefined);
  const retryDispatch = github.actions.find((action) => action.type === 'workflow-dispatch');
  assert.ok(retryDispatch, 'a newly stopped strategy must receive one immediate recovery lease');
  assert.deepEqual(retryDispatch.inputs, { pr_number: '457', force_retry: 'true' });

  const humanLabel = github.actions.find((action) =>
    action.type === 'label' && (
      action.labels.includes('agent:needs-attention') || action.labels.includes('needs-human')
    )
  );
  assert.equal(humanLabel, undefined);
});

test('updateKeepaliveLoopSummary applies automerge label on tasks-complete (#2270)', async () => {
  // After native auto-merge was removed from the belt worker, the loop's
  // tasks-complete terminal is the reliable producer of the `automerge` label
  // that routes a completed PR to the guarded merger.
  const existingState = formatStateComment({
    trace: 'trace-automerge',
    iteration: 3,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 47, body: existingState, html_url: 'https://example.com/47' }],
    labels: ['agent:codex', 'agents:keepalive'],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(459),
    core: buildCore(),
    inputs: {
      prNumber: 459,
      action: 'stop',
      reason: 'tasks-complete',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 3,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-automerge',
    },
  });

  const automergeLabel = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('automerge')
  );
  assert.ok(automergeLabel, 'expected automerge label to be applied on tasks-complete');
});

test('updateKeepaliveLoopSummary does not re-add automerge when already present (#2270 idempotent)', async () => {
  const existingState = formatStateComment({
    trace: 'trace-automerge-idem',
    iteration: 3,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 48, body: existingState, html_url: 'https://example.com/48' }],
    // automerge already present (any case) — must be treated as idempotent.
    labels: ['agent:codex', 'AutoMerge', 'agents:keepalive'],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(460),
    core: buildCore(),
    inputs: {
      prNumber: 460,
      action: 'stop',
      reason: 'tasks-complete',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 3,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-automerge-idem',
    },
  });

  const automergeAdds = github.actions.filter((action) =>
    action.type === 'label' && action.labels.includes('automerge')
  );
  assert.equal(automergeAdds.length, 0, 'automerge label must not be re-added when already present');
});

test('updateKeepaliveLoopSummary does not apply automerge on a non-success stop (#2270)', async () => {
  // Only the tasks-complete terminal should route to the guarded merger.
  const existingState = formatStateComment({
    trace: 'trace-no-automerge',
    iteration: 5,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 49, body: existingState, html_url: 'https://example.com/49' }],
    labels: ['agent:codex', 'agents:keepalive'],
  });
  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(461),
    core: buildCore(),
    inputs: {
      prNumber: 461,
      action: 'stop',
      reason: 'max-iterations-unproductive',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 1,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 5,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-no-automerge',
    },
  });

  const automergeAdds = github.actions.filter((action) =>
    action.type === 'label' && action.labels.includes('automerge')
  );
  assert.equal(automergeAdds.length, 0, 'automerge must only be applied on tasks-complete');
});

test('updateKeepaliveLoopSummary does not treat skipped runs as agent failures', async () => {
  const existingState = formatStateComment({
    trace: 'trace-run-skipped',
    iteration: 1,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 77, body: existingState, html_url: 'https://example.com/77' }],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(777),
    core: buildCore(),
    inputs: {
      prNumber: 777,
      action: 'run',
      reason: 'ready',
      runResult: 'skipped',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 3,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-run-skipped',
    },
  });

  assert.equal(github.actions.length, 2);
  const updateAction = github.actions[0];
  assert.equal(updateAction.type, 'update');
  assert.match(updateAction.body, /agent-run-skipped/);
  assert.doesNotMatch(updateAction.body, /AGENT FAILED/);
  assert.match(updateAction.body, /"failure":\{\}/);
});

test('updateKeepaliveLoopSummary sends preflight auth failures without a runner exit to independent challenge', async () => {
  const authSummary = 'Missing token ACTIONS_BOT_PAT for GitHub API repository dispatch.';
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
      agent_summary: authSummary,
    },
  });

  const labelAction = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('agent:needs-attention')
  );
  assert.ok(labelAction);
  assert.equal(
    github.actions.some((action) => action.type === 'label' && action.labels.includes('needs-human')),
    false
  );
  const updateAction = github.actions.find((action) => action.type === 'update');
  assert.match(updateAction.body, /"disposition":"challenge-due"/);
  assert.match(updateAction.body, /"owner":"automation"/);
  assert.match(updateAction.body, /"boundary_fingerprint":"[0-9a-f]{64}"/);
  assert.match(updateAction.body, /"boundary_detail":"Required credential: ACTIONS_BOT_PAT/);
  assert.match(updateAction.body, /"next_action":"Independently rerun the current operation/);
});

test('a scheduled recheck that reproduces auth failure records a terminal human action', async () => {
  const authSummary = 'Missing token ACTIONS_BOT_PAT for GitHub API repository dispatch.';
  const boundary = buildAuthorityChallengeEvidence({ agentSummary: authSummary });
  const existingState = formatStateComment({
    trace: 'trace-attention-auth-confirmed',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 1 },
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      first_seen_at: '2026-08-12T12:00:00Z',
      challenge_due_at: '2026-08-12T12:05:00Z',
      key: 'agent-run-failed|failure|auth|agent|1',
      boundary_fingerprint: boundary.fingerprint,
      boundary_detail: boundary.detail,
    },
  });
  const github = buildGithubStub({
    comments: [{ id: 89, body: existingState, html_url: 'https://example.com/89' }],
    labels: ['agent:codex', 'agent:needs-attention'],
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
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-auth-confirmed',
      forceRetry: true,
      ...authorityClaimInputs(654, boundary.fingerprint),
      agent_exit_code: '1',
      agent_summary: authSummary,
    },
  });

  assert.ok(github.actions.some((action) =>
    action.type === 'remove-label' && action.name === 'agent:needs-attention'
  ));
  assert.ok(github.actions.some((action) =>
    action.type === 'label' && action.labels.includes('needs-human')
  ));
  const hardLabelIndex = github.actions.findIndex((action) =>
    action.type === 'label' && action.labels.includes('needs-human')
  );
  const softLabelRemovalIndex = github.actions.findIndex((action) =>
    action.type === 'remove-label' && action.name === 'agent:needs-attention'
  );
  const pendingStateIndex = github.actions.findIndex((action) =>
    action.type === 'update' && action.body.includes('Applying Blocker')
  );
  const finalStateIndex = github.actions.findIndex((action) =>
    action.type === 'update' && action.body.includes('Independent Authority Challenge Confirmed')
  );
  assert.ok(pendingStateIndex >= 0 && pendingStateIndex < hardLabelIndex);
  assert.ok(hardLabelIndex >= 0 && hardLabelIndex < finalStateIndex);
  assert.ok(finalStateIndex >= 0 && finalStateIndex < softLabelRemovalIndex);
  assert.equal(
    github.actions.some((action) => action.type === 'workflow-dispatch'),
    false,
  );
  const updateAction = github.actions.find((action) =>
    action.type === 'update' && action.body.includes('Independent Authority Challenge Confirmed')
  );
  assert.match(updateAction.body, /Independent Authority Challenge Confirmed/);
  assert.match(updateAction.body, /"disposition":"needs-human"/);
  assert.match(updateAction.body, /"owner":"human"/);
  assert.match(updateAction.body, /"confirmation":"scheduled-current-state-recheck-reproduced-auth-boundary"/);
  assert.match(
    updateAction.body,
    /"human_action":"Resolve the reproduced runner authority failure: Required credential: ACTIONS_BOT_PAT"/,
  );
});

test('a two-phase terminal transition reuses a newly created summary comment', async () => {
  const authSummary = 'Missing token ACTIONS_BOT_PAT for GitHub API repository dispatch.';
  const boundary = buildAuthorityChallengeEvidence({ agentSummary: authSummary });
  const existingState = formatStateComment({
    trace: 'trace-attention-auth-create',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 1 },
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      first_seen_at: '2026-08-12T12:00:00Z',
      challenge_due_at: '2026-08-12T12:05:00Z',
      key: 'agent-run-failed|failure|auth|agent|1',
      boundary_fingerprint: boundary.fingerprint,
      boundary_detail: boundary.detail,
    },
  });
  const github = buildGithubStub({
    // GitHub comments always have ids; omitting it exercises the defensive
    // create path while retaining the prior challenge state needed to confirm.
    comments: [{ body: existingState }],
    labels: ['agent:codex', 'agent:needs-attention'],
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
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-auth-create',
      forceRetry: true,
      ...authorityClaimInputs(654, boundary.fingerprint),
      agent_exit_code: '1',
      agent_summary: authSummary,
    },
  });

  const stateCreates = github.actions.filter(
    (action) => action.type === 'create' && action.body.includes('keepalive-state:v1'),
  );
  const stateUpdates = github.actions.filter(
    (action) => action.type === 'update' && action.body.includes('keepalive-state:v1'),
  );
  assert.equal(stateCreates.length, 1);
  assert.match(stateCreates[0].body, /Applying Blocker/);
  assert.equal(stateUpdates.length, 1);
  assert.equal(stateUpdates[0].commentId, 101);
  assert.match(stateUpdates[0].body, /Independent Authority Challenge Confirmed/);
});

test('a failed hard label write keeps the authority challenge automation-owned', async () => {
  const authSummary = 'Missing token ACTIONS_BOT_PAT for GitHub API repository dispatch.';
  const boundary = buildAuthorityChallengeEvidence({ agentSummary: authSummary });
  const existingState = formatStateComment({
    trace: 'trace-attention-auth-label-failed',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 1 },
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      first_seen_at: '2026-08-12T12:00:00Z',
      challenge_due_at: '2026-08-12T12:05:00Z',
      key: 'agent-run-failed|failure|auth|agent|1',
      boundary_fingerprint: boundary.fingerprint,
      boundary_detail: boundary.detail,
    },
  });
  const github = buildGithubStub({
    comments: [{ id: 93, body: existingState, html_url: 'https://example.com/93' }],
    labels: ['agent:codex', 'agent:needs-attention'],
    failNeedsHumanLabel: true,
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
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-auth-label-failed',
      forceRetry: true,
      ...authorityClaimInputs(654, boundary.fingerprint),
      agent_exit_code: '1',
      agent_summary: authSummary,
    },
  });

  assert.ok(github.actions.some((action) => action.type === 'label-failed'));
  assert.equal(
    github.actions.some((action) =>
      action.type === 'label' && action.labels.includes('needs-human')
    ),
    false,
  );
  assert.ok(github.actions.some((action) =>
    action.type === 'label' && action.labels.includes('agent:needs-attention')
  ));
  const updateAction = github.actions.find((action) => action.type === 'update');
  const state = parseStateComment(updateAction.body).data;
  assert.equal(state.attention.owner, 'automation');
  assert.equal(state.attention.disposition, 'challenge-due');
  assert.equal(state.attention.boundary_fingerprint, boundary.fingerprint);
  assert.doesNotMatch(updateAction.body, /Independent Authority Challenge Confirmed/);
});

test('a failed terminal state write leaves a durable actionable pending transition', async () => {
  const authSummary = 'Missing token ACTIONS_BOT_PAT for GitHub API repository dispatch.';
  const boundary = buildAuthorityChallengeEvidence({ agentSummary: authSummary });
  const existingState = formatStateComment({
    trace: 'trace-attention-auth-state-failed',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 1 },
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      first_seen_at: '2026-08-12T12:00:00Z',
      challenge_due_at: '2026-08-12T12:05:00Z',
      key: 'agent-run-failed|failure|auth|agent|1',
      boundary_fingerprint: boundary.fingerprint,
      boundary_detail: boundary.detail,
    },
  });
  const github = buildGithubStub({
    comments: [{ id: 95, body: existingState, html_url: 'https://example.com/95' }],
    labels: ['agent:codex', 'agent:needs-attention'],
    failStateCommentWriteAt: 2,
  });

  await assert.rejects(
    updateKeepaliveLoopSummary({
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
        iteration: 2,
        maxIterations: 5,
        failureThreshold: 3,
        trace: 'trace-attention-auth-state-failed',
        forceRetry: true,
        ...authorityClaimInputs(654, boundary.fingerprint),
        agent_exit_code: '1',
        agent_summary: authSummary,
      },
    }),
    /simulated state comment failure/,
  );

  const hardLabelIndex = github.actions.findIndex((action) =>
    action.type === 'label' && action.labels.includes('needs-human')
  );
  const failedWriteIndex = github.actions.findIndex((action) => action.type === 'update-failed');
  assert.ok(hardLabelIndex >= 0 && hardLabelIndex < failedWriteIndex);
  assert.equal(
    github.actions.some((action) =>
      action.type === 'remove-label' && action.name === 'needs-human'
    ),
    false,
  );
  assert.equal(
    github.actions.some((action) =>
      action.type === 'remove-label' && action.name === 'agent:needs-attention'
    ),
    false,
  );
  const pendingUpdate = github.actions.find((action) =>
    action.type === 'update' && action.body.includes('Applying Blocker')
  );
  const pendingState = parseStateComment(pendingUpdate.body).data;
  assert.equal(pendingState.attention.owner, 'automation');
  assert.equal(pendingState.attention.disposition, 'challenge-due');
  assert.equal(pendingState.attention.confirmation_pending_label, true);
  assert.match(pendingState.attention.next_action, /ACTIONS_BOT_PAT/);
});

test('a forged sweep claim cannot confirm an authority challenge', async () => {
  const authSummary = 'Missing token ACTIONS_BOT_PAT for GitHub API repository dispatch.';
  const boundary = buildAuthorityChallengeEvidence({ agentSummary: authSummary });
  const existingState = formatStateComment({
    trace: 'trace-attention-auth-unproven',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 1 },
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      first_seen_at: '2026-08-12T12:00:00Z',
      challenge_due_at: '2026-08-12T12:05:00Z',
      key: 'original-auth-boundary',
      boundary_fingerprint: boundary.fingerprint,
      boundary_detail: boundary.detail,
    },
  });
  const github = buildGithubStub({
    comments: [{ id: 92, body: existingState, html_url: 'https://example.com/92' }],
    labels: ['agent:codex', 'agent:needs-attention'],
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
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-auth-unproven',
      forceRetry: true,
      authority_challenge_fingerprint: boundary.fingerprint,
      authority_challenge_claim: JSON.stringify({
        signature: '0'.repeat(64),
        nonce: 'a'.repeat(64),
        sweep_run_id: '987654321',
        sweep_run_attempt: '1',
      }),
      authority_challenge_signing_key: 'test-only-authority-signing-key',
      agent_exit_code: '1',
      agent_summary: authSummary,
    },
  });

  assert.equal(
    github.actions.some((action) =>
      action.type === 'label' && action.labels.includes('needs-human')
    ),
    false,
  );
  const updateAction = github.actions.find((action) =>
    action.type === 'update' && parseStateComment(action.body)?.data?.attention
  );
  const state = parseStateComment(updateAction.body).data;
  assert.equal(state.attention.owner, 'automation');
  assert.equal(state.attention.disposition, 'challenge-due');
  assert.equal(state.attention.boundary_fingerprint, boundary.fingerprint);
});

test('a reproduced generic auth failure remains automation-owned', async () => {
  const authSummary = 'Authentication failed';
  const boundary = buildAuthorityChallengeEvidence({
    agentSummary: authSummary,
    agentType: 'codex',
    operation: 'run',
  });
  const existingState = formatStateComment({
    trace: 'trace-attention-auth-generic',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 1 },
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      first_seen_at: '2026-08-12T12:00:00Z',
      challenge_due_at: '2026-08-12T12:05:00Z',
      key: 'generic-auth-boundary',
      boundary_fingerprint: boundary.fingerprint,
      boundary_detail: boundary.detail,
    },
  });
  const github = buildGithubStub({
    comments: [{ id: 96, body: existingState, html_url: 'https://example.com/96' }],
    labels: ['agent:codex', 'agent:needs-attention'],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(654),
    core: buildCore(),
    inputs: {
      prNumber: 654,
      action: 'run',
      agent_type: 'codex',
      runResult: 'failure',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 3,
      keepaliveEnabled: true,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-auth-generic',
      forceRetry: true,
      authority_challenge_fingerprint: boundary.fingerprint,
      agent_exit_code: '1',
      agent_summary: authSummary,
    },
  });

  assert.equal(boundary.actionable, false);
  assert.equal(boundary.humanAction, '');
  assert.equal(
    github.actions.some((candidate) =>
      candidate.type === 'label' && candidate.labels.includes('needs-human')
    ),
    false,
  );
  const updateAction = github.actions.find((candidate) =>
    candidate.type === 'update' && parseStateComment(candidate.body)?.data?.attention
  );
  const state = parseStateComment(updateAction.body).data;
  assert.equal(state.attention.owner, 'automation');
  assert.equal(state.attention.disposition, 'challenge-due');
});

test('a forced recheck with a different auth boundary stays automation-owned', async () => {
  const original = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing token ACTIONS_BOT_PAT for GitHub API repository dispatch.',
  });
  const existingState = formatStateComment({
    trace: 'trace-attention-auth-different',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 1 },
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      first_seen_at: '2026-08-12T12:00:00Z',
      challenge_due_at: '2026-08-12T12:05:00Z',
      key: 'original-auth-boundary',
      boundary_fingerprint: original.fingerprint,
      boundary_detail: original.detail,
    },
  });
  const github = buildGithubStub({
    comments: [{ id: 91, body: existingState, html_url: 'https://example.com/91' }],
    labels: ['agent:codex', 'agent:needs-attention'],
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
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-auth-different',
      forceRetry: true,
      authority_challenge_fingerprint: original.fingerprint,
      agent_exit_code: '1',
      agent_summary: 'Insufficient permission pull-requests:write for repository update.',
    },
  });

  assert.equal(
    github.actions.some((action) =>
      action.type === 'label' && action.labels.includes('needs-human')
    ),
    false,
  );
  assert.ok(github.actions.some((action) =>
    action.type === 'label' && action.labels.includes('agent:needs-attention')
  ));
  const updateAction = github.actions.find((action) =>
    action.type === 'update' && parseStateComment(action.body)?.data?.attention
  );
  const state = parseStateComment(updateAction.body).data;
  assert.equal(state.attention.owner, 'automation');
  assert.equal(state.attention.disposition, 'challenge-due');
  assert.notEqual(state.attention.boundary_fingerprint, original.fingerprint);
  assert.match(state.attention.boundary_detail, /pull-requests:write/);
});

test('renewing an authority challenge never removes its existing soft label', async () => {
  const original = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing token ACTIONS_BOT_PAT for GitHub API repository dispatch.',
  });
  const existingState = formatStateComment({
    trace: 'trace-attention-auth-renewal-label-failed',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 1 },
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      first_seen_at: '2026-08-12T12:00:00Z',
      challenge_due_at: '2026-08-12T12:05:00Z',
      key: 'original-auth-boundary',
      boundary_fingerprint: original.fingerprint,
      boundary_detail: original.detail,
    },
  });
  const github = buildGithubStub({
    comments: [{ id: 94, body: existingState, html_url: 'https://example.com/94' }],
    labels: ['agent:codex', 'agent:needs-attention'],
    failNeedsAttentionLabel: true,
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
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-auth-renewal-label-failed',
      forceRetry: true,
      authority_challenge_fingerprint: original.fingerprint,
      agent_exit_code: '1',
      agent_summary: 'Insufficient permission pull-requests:write for repository update.',
    },
  });

  assert.ok(github.actions.some((action) =>
    action.type === 'label-failed' && action.labels.includes('agent:needs-attention')
  ));
  assert.equal(
    github.actions.some((action) =>
      action.type === 'remove-label' && action.name === 'agent:needs-attention'
    ),
    false,
  );
  const updateAction = github.actions.find((action) => action.type === 'update');
  const state = parseStateComment(updateAction.body).data;
  assert.equal(state.attention.owner, 'automation');
  assert.equal(state.attention.disposition, 'challenge-due');
  assert.notEqual(state.attention.boundary_fingerprint, original.fingerprint);
});

test('authority evidence persists only an allowlisted safe projection', () => {
  const commonPrefix = `Permission failure ${'x'.repeat(320)}`;
  const first = buildAuthorityChallengeEvidence({
    agentSummary: `${commonPrefix} missing scope contents:write Bearer secret-one`,
  });
  const second = buildAuthorityChallengeEvidence({
    agentSummary: `${commonPrefix} missing scope pull-requests:write Bearer secret-two`,
  });
  const sensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Forbidden request with Bearer secret-three and token=secret-four',
  });
  const uppercaseSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Forbidden request with password=CORRECT_HORSE.',
  });
  const undelimitedSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Forbidden request returned token CORRECT_HORSE.',
  });
  const genericCredentialSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Forbidden credential=correct-horse-battery-staple credentials another-secret-value.',
  });
  const oauthSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing OPENAI_API_KEY=sk-proj-value client_secret=oauth-value access_token=access-value.',
  });
  const jsonSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Forbidden response {"access_token":"json-access", "password": "json-password"}.',
  });
  const prefixedSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Unauthorized: OPENAI_API_KEY=sk-prefixed-secret',
  });
  const headerSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied Authorization: Basic dXNlcjpzdXBlcnNlY3JldA== Proxy-Authorization=Bearer proxy-secret Cookie: session=secret-cookie',
  });
  const digestHeaderSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied Authorization: Digest username="Mufasa", realm="example", nonce="abc", response="deadbeef" after retry',
  });
  const arbitraryHeaderSensitive = buildAuthorityChallengeEvidence({
    agentSummary: `Denied Authorization: ApiKey ${'super-' + 'secret-value'} after retry`,
  });
  const standaloneHttpAuthSensitive = [
    'Basic dXNlcjpwYXNz',
    'Digest username="Mufasa", response="deadbeef"',
    'Negotiate runtime-ticket',
    'NTLM runtime-token',
    'ApiKey runtime-secret',
  ].map(value => buildAuthorityChallengeEvidence({
    agentSummary: `HTTP 401 using ${value}; required permission contents:write`,
  }));
  const sigV4HeaderSensitive = buildAuthorityChallengeEvidence({
    agentSummary:
      `Denied Authorization: AWS4-HMAC-SHA256 Credential=${'access-key'}/scope, ` +
      `SignedHeaders=host, Signature=${'dead' + 'beef'} after retry`,
  });
  const headerWithPermissionRemedy = buildAuthorityChallengeEvidence({
    agentSummary:
      `Denied Authorization: Bearer ${'runtime-' + 'secret'}; ` +
      'requires contents:write permission',
  });
  const headerWithEarlierPermissionValue = buildAuthorityChallengeEvidence({
    agentSummary:
      `Attempted contents:read request. Authorization: Bearer ${'runtime-' + 'secret'}; ` +
      'requires pull-requests:write permission',
  });
  const headerWithCredentialRemedy = buildAuthorityChallengeEvidence({
    agentSummary:
      `Denied Authorization: ApiKey ${'runtime-' + 'secret'}; ` +
      'Missing token: CODEX_AUTH_JSON',
  });
  const headerWithCredentialShapedSecret = buildAuthorityChallengeEvidence({
    agentSummary:
      'Denied Authorization: Custom Missing token: CORRECT_HORSE; ' +
      'requires contents:write permission',
  });
  const pemBegin = ['-----BEGIN', 'PRIVATE KEY-----'].join(' ');
  const pemEnd = ['-----END', 'PRIVATE KEY-----'].join(' ');
  const openSshPemBegin = ['-----BEGIN', 'OPENSSH PRIVATE KEY-----'].join(' ');
  const pemPrivateKeySensitive = buildAuthorityChallengeEvidence({
    // Assemble key-shaped material at runtime so the repository secret scanner
    // does not mistake the redaction fixture for a live private key.
    agentSummary:
      `Authentication failed ${pemBegin} ${'private-' + 'key-material'} ${pemEnd} ` +
      'requires contents:write permission',
  });
  const truncatedPrivateKeySensitive = buildAuthorityChallengeEvidence({
    agentSummary:
      `Authentication failed ${openSshPemBegin} ${'truncated-' + 'key-material'} ` +
      'Missing token: CORRECT_HORSE; requires contents:write permission',
  });
  const multiCookieSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied Cookie: session=alpha; csrf=beta after retry',
  });
  const commaCookieSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied Set-Cookie: session=alpha, csrf=beta; requires contents:write permission',
  });
  const attributedCookieSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied Set-Cookie: session=alpha; Path=/; HttpOnly, csrf=beta; Secure; requires contents:write permission',
  });
  const compactJwtSensitive = buildAuthorityChallengeEvidence({
    agentSummary:
      `Denied JWT ${'eyJhbGciOiJIUzI1NiJ9'}.${'eyJzdWIiOiJ1c2VyIn0'}.${'runtime-signature-value'}; ` +
      'requires contents:write permission',
  });
  const githubAppSensitive = buildAuthorityChallengeEvidence({
    // Build the scanner-shaped fixture at runtime so the repository's own
    // complete-diff secret scanner does not mistake test data for a live token.
    agentSummary: `Authentication failed for ${'ghs_'}abcdefghijklmnopqrstuvwxyz123456`,
  });
  const quotedSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Forbidden password="correct horse battery staple" token=\'another secret phrase\'.',
  });
  const quotedUppercasePassword = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing password: "HUNTERTWO"; requires contents:write permission',
  });
  const unquotedUppercasePassword = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing password: HUNTERTWO; requires contents:write permission',
  });
  const passwordAliasSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied passwd=correct-horse-battery-staple pwd another-secret; requires contents:write permission',
  });
  const extendedAliasSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied pass=alpha pin beta otp=gamma mfa_code delta session_token=epsilon signature zeta; requires contents:write permission',
  });
  const credentialFieldShapes = [
    'secretAccessKey', 'secretAccessKeyId', 'privateKeyData', 'privateKeyPEM',
    'clientSecretValue', 'apiKeys', 'accessTokens', 'passwordHashes',
    'credentialBlob', 'sessionTokenString', 'private_key_material',
    'api_keys', 'client_secret_value', 'access_tokens', 'password_hashes',
    'serviceAuthMaterial', 'oauthCredentialsBundle', 'signingKeyBytes',
    'pfxData', 'pkcs12Bytes', 'p12Blob', 'releaseKeystore', 'buildTruststore',
  ];
  const credentialFieldEvidence = credentialFieldShapes.map((field, index) => ({
    field,
    sentinel: `sensitive-value-${index}`,
    evidence: buildAuthorityChallengeEvidence({
      agentSummary: `Denied ${field}=sensitive-value-${index}; requires contents:write permission`,
    }),
  }));
  const jsonCamelCaseSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied "clientSecretValue": "json-secret"; requires contents:write permission',
  });
  const structuredCredentialSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied apiKeys=["array-secret-one","array-secret-two"]; requires contents:write permission',
  });
  const structuredCredentialObjectSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied credentials={"clientSecret":"object-secret"}; requires contents:write permission',
  });
  const ordinaryLowercaseControl = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied monkey=banana while reading metadata',
  });
  const novelUnrecognizedSecret = buildAuthorityChallengeEvidence({
    agentSummary:
      'Denied futuristicEnvelope=NEVER_PERSIST_THIS_FORMAT; ' +
      'required permission contents:write',
  });
  const unrecognizedEnvShapedValue = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing token: NEVER_PERSIST_THIS_FORMAT for runner launch.',
  });
  const aiderRegistryCredential = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing Aider auth: set AIDER_API_KEY',
    agentType: 'aider',
  });
  const wrongRoutedAgentCredential = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing Aider auth: set AIDER_API_KEY',
    agentType: 'codex',
  });
  const pluralNamedCredentials = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing credentials: OPENAI_API_KEY',
  });
  const qualifiedNamedCredentials = [
    { agentSummary: 'Missing API key: OPENAI_API_KEY', agentType: 'codex' },
    { agentSummary: 'Required API token: OPENAI_API_KEY', agentType: 'codex' },
    { agentSummary: 'Unset OAuth token: CLAUDE_CODE_OAUTH_TOKEN', agentType: 'claude' },
  ].map(input => buildAuthorityChallengeEvidence(input));
  const unrecognizedNamespacedPermission = buildAuthorityChallengeEvidence({
    agentSummary: 'Required permission read:CORRECT_HORSE_BATTERY_STAPLE',
  });
  const passphraseSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Key authentication failed passphrase="correct horse battery staple".',
  });
  const longPermissionRemediation = buildAuthorityChallengeEvidence({
    agentSummary:
      `Access denied: requires contents:write permission ` +
      'while processing extended runner diagnostics '.repeat(20),
  });
  const urlSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Permission denied for https://alice:correct-horse@example.com/private',
  });
  const sshUrlSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Permission denied for ssh://alice:correct-horse@example.com/private',
  });
  const databaseUrlSensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Permission denied for postgres://alice:correct-horse@example.com/private',
  });
  const undelimitedApiKeySensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied X-API-Key correct-horse-battery-staple; requires contents:write permission',
  });
  const undelimitedAwsKeySensitive = buildAuthorityChallengeEvidence({
    agentSummary: 'Denied AWS_SECRET_ACCESS_KEY correct-horse-battery-staple; requires contents:write permission',
  });
  const bareProviderSensitive = buildAuthorityChallengeEvidence({
    agentSummary:
      `Unauthorized provider key ${'sk-'}abcdefghijklmnopqrstuvwxyz123456 ` +
      `and access key ${'AKIA'}ABCDEFGHIJKLMNOP`,
  });

  assert.ok(first.detail.length <= 300);
  assert.match(first.detail, /contents:write/);
  assert.match(first.humanAction, /contents:write/);
  assert.match(second.detail, /pull-requests:write/);
  assert.notEqual(first.fingerprint, second.fingerprint);
  const sameFailureCodex = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing token ACTIONS_BOT_PAT for repository dispatch.',
    agentType: 'codex',
    operation: 'run',
  });
  const sameFailureClaude = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing token ACTIONS_BOT_PAT for repository dispatch.',
    agentType: 'claude',
    operation: 'run',
  });
  const sameFailureFix = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing token ACTIONS_BOT_PAT for repository dispatch.',
    agentType: 'codex',
    operation: 'fix',
  });
  assert.notEqual(sameFailureCodex.fingerprint, sameFailureClaude.fingerprint);
  assert.notEqual(sameFailureCodex.fingerprint, sameFailureFix.fingerprint);
  const githubPermissionBefore = buildAuthorityChallengeEvidence({
    agentSummary: 'missing contents: write permission',
  });
  const githubScopeBefore = buildAuthorityChallengeEvidence({
    agentSummary: 'requires contents:write scope',
  });
  const githubScopeAfter = buildAuthorityChallengeEvidence({
    agentSummary: 'missing scope contents: write',
  });
  const githubScopeAfterCompact = buildAuthorityChallengeEvidence({
    agentSummary: 'missing scope contents:write',
  });
  const githubOauthScope = buildAuthorityChallengeEvidence({
    agentSummary: 'requires read:org scope',
  });
  const githubRepoScope = buildAuthorityChallengeEvidence({
    agentSummary: 'requires repo scope',
  });
  const githubWorkflowScope = buildAuthorityChallengeEvidence({
    agentSummary: 'missing workflow scope',
  });
  const pluralPermissionRemedies = [
    'missing permissions: contents:write',
    'permissions required: contents:write',
    'permissions: contents:write are required',
    'contents:write permissions are required',
    'scopes required: repo',
    'required permission `contents:write`',
    'required permission "pull-requests:write"',
    "required scope 'repo'",
    'required permission **issues:write**',
    'required permission [statuses:write]',
    'required scope <workflow>',
  ].map(agentSummary => buildAuthorityChallengeEvidence({ agentSummary }));
  const metadataOnly = buildAuthorityChallengeEvidence({
    agentSummary: 'Permission denied; error:403 from repository API',
  });
  const ordinaryRepoWord = buildAuthorityChallengeEvidence({
    agentSummary: 'Permission denied while updating repo metadata.',
  });
  const ordinaryUserWord = buildAuthorityChallengeEvidence({
    agentSummary: 'Insufficient permission to access user profile.',
  });
  const attemptedPermissionOnly = buildAuthorityChallengeEvidence({
    agentSummary: 'Attempted contents:read request. Permission denied by repository policy.',
  });
  const unrelatedUppercaseRemedy = buildAuthorityChallengeEvidence({
    agentSummary: 'Authentication failed while reading repository metadata. Missing README',
  });
  const unnamedEnvironmentRemedy = buildAuthorityChallengeEvidence({
    agentSummary: 'Authentication failed while launching runner. Missing OPENAI_API_KEY',
  });
  const separatePermissionRemedies = buildAuthorityChallengeEvidence({
    agentSummary:
      'contents:read permission granted. Authorization: opaque; Required permission: issues:write',
  });
  assert.equal(githubPermissionBefore.actionable, true);
  assert.equal(githubScopeBefore.actionable, true);
  assert.equal(githubScopeAfter.actionable, true);
  assert.equal(githubOauthScope.actionable, true);
  assert.equal(githubRepoScope.actionable, true);
  assert.equal(githubWorkflowScope.actionable, true);
  for (const evidence of pluralPermissionRemedies) assert.equal(evidence.actionable, true);
  assert.equal(metadataOnly.actionable, false);
  assert.equal(metadataOnly.humanAction, '');
  assert.equal(ordinaryRepoWord.actionable, false);
  assert.equal(ordinaryRepoWord.humanAction, '');
  assert.equal(ordinaryUserWord.actionable, false);
  assert.equal(ordinaryUserWord.humanAction, '');
  assert.equal(attemptedPermissionOnly.actionable, false);
  assert.equal(attemptedPermissionOnly.humanAction, '');
  assert.equal(unrelatedUppercaseRemedy.actionable, false);
  assert.equal(unrelatedUppercaseRemedy.humanAction, '');
  assert.equal(unnamedEnvironmentRemedy.actionable, true);
  assert.match(unnamedEnvironmentRemedy.humanAction, /OPENAI_API_KEY/);
  assert.equal(separatePermissionRemedies.actionable, true);
  assert.match(separatePermissionRemedies.humanAction, /issues:write/);
  assert.doesNotMatch(separatePermissionRemedies.humanAction, /Required permission: contents:read/);
  assert.equal(githubScopeAfter.fingerprint, githubScopeAfterCompact.fingerprint);
  assert.equal(githubPermissionBefore.fingerprint, githubScopeAfter.fingerprint);
  const safeProjection = /^(?:Required credential: [A-Z][A-Z0-9_]+|Required permission: [A-Za-z0-9_.:-]+|HTTP (?:401|403)(?:\/(?:401|403))*|Authority failure(?: \([a-z, ]+\))?)(?:; (?:Required credential: [A-Z][A-Z0-9_]+|Required permission: [A-Za-z0-9_.:-]+|HTTP (?:401|403)(?:\/(?:401|403))*))*$/;
  const projectedEvidence = [
    sensitive, uppercaseSensitive, undelimitedSensitive, genericCredentialSensitive,
    oauthSensitive, jsonSensitive, prefixedSensitive, headerSensitive,
    digestHeaderSensitive, arbitraryHeaderSensitive, sigV4HeaderSensitive,
    headerWithPermissionRemedy, headerWithEarlierPermissionValue,
    headerWithCredentialRemedy, headerWithCredentialShapedSecret,
    pemPrivateKeySensitive, truncatedPrivateKeySensitive, multiCookieSensitive,
    commaCookieSensitive, attributedCookieSensitive, compactJwtSensitive,
    githubAppSensitive, quotedSensitive, quotedUppercasePassword,
    unquotedUppercasePassword, passwordAliasSensitive, extendedAliasSensitive,
    jsonCamelCaseSensitive, structuredCredentialSensitive,
    structuredCredentialObjectSensitive, passphraseSensitive, urlSensitive,
    sshUrlSensitive, databaseUrlSensitive, undelimitedApiKeySensitive,
    undelimitedAwsKeySensitive, bareProviderSensitive, novelUnrecognizedSecret,
    unrecognizedEnvShapedValue,
    unrecognizedNamespacedPermission,
    ...standaloneHttpAuthSensitive,
    ...credentialFieldEvidence.map(item => item.evidence),
  ];
  for (const evidence of projectedEvidence) assert.match(evidence.detail, safeProjection);
  const forbiddenSecretFragments = /dXNlc|proxy-secret|secret-cookie|Mufasa|example|nonce|deadbeef|ApiKey|secret-value|runtime-secret|CORRECT_HORSE|private-key-material|truncated-key-material|alpha|beta|HttpOnly|Secure|eyJhbGci|eyJzdWI|runtime-signature|ghs_|HUNTERTWO|correct-horse|another-secret|json-secret|array-secret|object-secret|alice|abcdefghijklmnopqrstuvwxyz|ABCDEFGHIJKLMNOP/;
  for (const evidence of projectedEvidence) {
    assert.doesNotMatch(evidence.detail, forbiddenSecretFragments);
    assert.doesNotMatch(evidence.humanAction, forbiddenSecretFragments);
  }
  assert.equal(sensitive.actionable, false);
  assert.equal(genericCredentialSensitive.actionable, false);
  assert.equal(headerSensitive.actionable, false);
  assert.equal(digestHeaderSensitive.actionable, false);
  assert.equal(arbitraryHeaderSensitive.actionable, false);
  for (const evidence of standaloneHttpAuthSensitive) {
    assert.match(evidence.humanAction, /contents:write/);
  }
  assert.equal(headerWithPermissionRemedy.actionable, true);
  assert.match(headerWithPermissionRemedy.humanAction, /contents:write/);
  assert.match(headerWithEarlierPermissionValue.humanAction, /pull-requests:write/);
  assert.doesNotMatch(headerWithEarlierPermissionValue.humanAction, /Required permission: contents:read/);
  assert.equal(headerWithCredentialRemedy.actionable, true);
  assert.match(headerWithCredentialRemedy.humanAction, /CODEX_AUTH_JSON/);
  assert.equal(headerWithCredentialShapedSecret.actionable, true);
  assert.equal(pemPrivateKeySensitive.actionable, true);
  assert.equal(truncatedPrivateKeySensitive.actionable, true);
  for (const { evidence, field, sentinel } of credentialFieldEvidence) {
    assert.match(evidence.detail, safeProjection, field);
    assert.doesNotMatch(evidence.detail, new RegExp(sentinel), field);
    assert.doesNotMatch(evidence.humanAction, new RegExp(sentinel), field);
  }
  assert.match(structuredCredentialSensitive.humanAction, /contents:write/);
  assert.match(structuredCredentialObjectSensitive.humanAction, /contents:write/);
  assert.match(ordinaryLowercaseControl.detail, safeProjection);
  assert.doesNotMatch(ordinaryLowercaseControl.detail, /monkey|banana/);
  assert.equal(novelUnrecognizedSecret.detail, 'Required permission: contents:write');
  assert.doesNotMatch(
    `${novelUnrecognizedSecret.detail} ${novelUnrecognizedSecret.humanAction}`,
    /NEVER_PERSIST_THIS_FORMAT|futuristicEnvelope/,
  );
  assert.equal(unrecognizedEnvShapedValue.actionable, false);
  assert.doesNotMatch(
    `${unrecognizedEnvShapedValue.detail} ${unrecognizedEnvShapedValue.humanAction}`,
    /NEVER_PERSIST_THIS_FORMAT/,
  );
  assert.equal(aiderRegistryCredential.actionable, true);
  assert.match(aiderRegistryCredential.humanAction, /AIDER_API_KEY/);
  assert.equal(wrongRoutedAgentCredential.actionable, false);
  assert.doesNotMatch(wrongRoutedAgentCredential.detail, /AIDER_API_KEY/);
  assert.equal(pluralNamedCredentials.actionable, true);
  assert.match(pluralNamedCredentials.detail, /OPENAI_API_KEY/);
  assert.match(pluralNamedCredentials.humanAction, /OPENAI_API_KEY/);
  for (const evidence of qualifiedNamedCredentials) {
    assert.equal(evidence.actionable, true);
    assert.match(evidence.humanAction, /OPENAI_API_KEY|CLAUDE_CODE_OAUTH_TOKEN/);
  }
  assert.equal(unrecognizedNamespacedPermission.actionable, false);
  assert.doesNotMatch(
    `${unrecognizedNamespacedPermission.detail} ${unrecognizedNamespacedPermission.humanAction}`,
    /CORRECT_HORSE_BATTERY_STAPLE/,
  );
  assert.match(longPermissionRemediation.detail, /contents:write/);
  assert.match(longPermissionRemediation.humanAction, /contents:write/);
  assert.ok(longPermissionRemediation.detail.length <= 300);
  const missingCodexCredential = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing token: CODEX_AUTH_JSON for runner launch.',
  });
  const missingClaudeCredential = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing token: CLAUDE_CODE_OAUTH_TOKEN for runner launch.',
    agentType: 'claude',
  });
  const missingNamedCredential = buildAuthorityChallengeEvidence({
    agentSummary: 'Missing credential ACTIONS_BOT_PAT for runner launch.',
  });
  const requiredNamedCredential = buildAuthorityChallengeEvidence({
    agentSummary: 'Required credential: OPENAI_API_KEY for runner launch.',
  });
  const routedMissingAuth = [
    buildAuthorityChallengeEvidence({
      agentSummary: 'Missing Claude auth: set CLAUDE_CODE_OAUTH_TOKEN',
      agentType: 'claude',
    }),
    buildAuthorityChallengeEvidence({
      agentSummary: 'Missing Cursor auth: set the CURSOR_API_KEY secret',
      agentType: 'cursor',
    }),
    buildAuthorityChallengeEvidence({
      agentSummary: 'Missing Gemini auth: set the GEMINI_API_KEY secret',
      agentType: 'gemini',
    }),
  ];
  assert.match(missingCodexCredential.detail, /CODEX_AUTH_JSON/);
  assert.match(missingClaudeCredential.detail, /CLAUDE_CODE_OAUTH_TOKEN/);
  assert.match(missingNamedCredential.detail, /ACTIONS_BOT_PAT/);
  assert.equal(missingNamedCredential.actionable, true);
  assert.match(requiredNamedCredential.detail, /OPENAI_API_KEY/);
  assert.equal(requiredNamedCredential.actionable, true);
  for (const evidence of routedMissingAuth) {
    assert.equal(evidence.actionable, true);
    assert.match(evidence.humanAction, /_OAUTH_|_API_KEY/);
  }
  assert.notEqual(missingCodexCredential.fingerprint, missingClaudeCredential.fingerprint);
  const unauthorized = buildAuthorityChallengeEvidence({
    agentSummary: 'GitHub API returned HTTP 401 for repository dispatch run 123456789.',
  });
  const forbidden = buildAuthorityChallengeEvidence({
    agentSummary: 'GitHub API returned HTTP 403 for repository dispatch run 987654321.',
  });
  const unauthorizedAgain = buildAuthorityChallengeEvidence({
    agentSummary: 'GitHub API returned HTTP 401 for repository dispatch run 987654321.',
  });
  assert.notEqual(unauthorized.fingerprint, forbidden.fingerprint);
  assert.equal(unauthorized.fingerprint, unauthorizedAgain.fingerprint);
  const timestampedOne = buildAuthorityChallengeEvidence({
    agentSummary: '2026-08-13T01:00:00Z missing credential at timestamp=1786410000',
  });
  const timestampedTwo = buildAuthorityChallengeEvidence({
    agentSummary: '2026-08-13T02:00:00Z missing credential at timestamp=1786413600',
  });
  const commaTimestampedOne = buildAuthorityChallengeEvidence({
    agentSummary: '2026-08-13 01:00:00,123 missing credential',
  });
  const commaTimestampedTwo = buildAuthorityChallengeEvidence({
    agentSummary: '2026-08-13 01:00:00,987 missing credential',
  });
  assert.equal(timestampedOne.fingerprint, timestampedTwo.fingerprint);
  assert.equal(commaTimestampedOne.fingerprint, commaTimestampedTwo.fingerprint);
  const requestIdOne = buildAuthorityChallengeEvidence({
    agentSummary: 'Authentication failed. Request ID: req_Qwerty123456',
  });
  const requestIdTwo = buildAuthorityChallengeEvidence({
    agentSummary: 'Authentication failed. Request ID: req_Asdfgh987654',
  });
  const traceIdOne = buildAuthorityChallengeEvidence({
    agentSummary: 'Authentication failed. correlation_id=traceAlpha123',
  });
  const traceIdTwo = buildAuthorityChallengeEvidence({
    agentSummary: 'Authentication failed. correlation_id=traceBeta987',
  });
  assert.equal(requestIdOne.fingerprint, requestIdTwo.fingerprint);
  assert.equal(traceIdOne.fingerprint, traceIdTwo.fingerprint);
  const permissionCodeOne = buildAuthorityChallengeEvidence({
    agentSummary: 'Repository permission policy code 123456 denied dispatch.',
  });
  const permissionCodeTwo = buildAuthorityChallengeEvidence({
    agentSummary: 'Repository permission policy code 654321 denied dispatch.',
  });
  // Arbitrary numeric policy codes are not durable authority facts. Generic,
  // non-actionable failures intentionally collapse to the same safe projection.
  assert.equal(permissionCodeOne.fingerprint, permissionCodeTwo.fingerprint);
});

test('a successful authority recheck clears the automation challenge with or without a signed force claim', async () => {
  for (const forceRetry of [true, false]) {
    const existingState = formatStateComment({
      trace: `trace-attention-auth-cleared-${forceRetry}`,
      iteration: 2,
      failure_threshold: 3,
      failure: { reason: 'agent-run-failed', count: 1 },
      attention: {
        owner: 'automation',
        disposition: 'challenge-due',
        first_seen_at: '2026-08-12T12:00:00Z',
        challenge_due_at: '2026-08-12T12:05:00Z',
        key: 'agent-run-failed|failure|auth|agent|1',
      },
    });
    const github = buildGithubStub({
      comments: [{ id: 90, body: existingState, html_url: 'https://example.com/90' }],
      labels: ['agent:codex', 'agent:needs-attention'],
    });

    await updateKeepaliveLoopSummary({
      github,
      context: buildContext(654),
      core: buildCore(),
      inputs: {
        prNumber: 654,
        action: 'run',
        runResult: 'success',
        gateConclusion: 'success',
        tasksTotal: 3,
        tasksUnchecked: 2,
        keepaliveEnabled: true,
        autofixEnabled: false,
        iteration: 2,
        maxIterations: 5,
        failureThreshold: 3,
        trace: `trace-attention-auth-cleared-${forceRetry}`,
        forceRetry,
      },
    });

    assert.ok(github.actions.some((action) =>
      action.type === 'remove-label' && action.name === 'agent:needs-attention'
    ));
    assert.equal(
      github.actions.some((action) =>
        action.type === 'label' && action.labels.includes('needs-human')
      ),
      false,
    );
    const updateAction = github.actions.find((action) => action.type === 'update');
    const state = parseStateComment(updateAction.body).data;
    assert.equal(state.attention, undefined);
  }
});

test('a recovered authority challenge retains automation ownership until its soft label is removed', async () => {
  const existingState = formatStateComment({
    trace: 'trace-attention-cleanup-pending',
    iteration: 2,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 1 },
    attention: {
      owner: 'automation',
      disposition: 'challenge-due',
      first_seen_at: '2026-08-12T12:00:00Z',
      challenge_due_at: '2026-08-12T12:05:00Z',
      key: 'agent-run-failed|failure|auth|agent|1',
    },
  });
  const github = buildGithubStub({
    comments: [{ id: 90, body: existingState, html_url: 'https://example.com/90' }],
    labels: ['agent:codex', 'agent:needs-attention'],
    failNeedsAttentionRemoval: true,
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(654),
    core: buildCore(),
    inputs: {
      prNumber: 654,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 2,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-attention-cleanup-pending',
      forceRetry: false,
    },
  });

  assert.ok(github.actions.some((action) => action.type === 'remove-label-failed'));
  const updateAction = github.actions.find((action) => action.type === 'update');
  const state = parseStateComment(updateAction.body).data;
  assert.equal(state.attention.owner, 'automation');
  assert.equal(state.attention.disposition, 'challenge-due');
  assert.equal(state.attention.cleanup_pending_label, true);
  assert.match(state.attention.next_action, /Retry removal/);
});

test('updateKeepaliveLoopSummary routes resource failures to automation retry', async () => {
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
      retry_workflow_id: 'agents-81-gate-followups.yml',
      agent_exit_code: '1',
      agent_summary: 'Repository not found for this request.',
    },
  });

  const retryLabel = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('agent:retry')
  );
  assert.equal(retryLabel, undefined);
  const retryDispatch = github.actions.find((action) => action.type === 'workflow-dispatch');
  assert.equal(retryDispatch.workflow_id, 'agents-81-gate-followups.yml');
  assert.deepEqual(retryDispatch.inputs, { pr_number: '655', force_retry: 'true' });
  assert.equal(
    github.actions.some((action) => action.type === 'label' && action.labels.includes('needs-human')),
    false
  );
});

test('automation-owned terminal stops dispatch exactly one forced recovery lease', async () => {
  for (const reason of [
    'round-budget-exhausted',
    'verification-exhausted',
    'zero-activity-infrastructure',
  ]) {
    for (const forceRetry of [false, true]) {
      const existingState = formatStateComment({
        trace: `trace-terminal-${reason}-${forceRetry}`,
        iteration: 5,
        max_iterations: 5,
        failure_threshold: 3,
        failure: {},
      });
      const github = buildGithubStub({
        comments: [{ id: 104, body: existingState, html_url: 'https://example.com/104' }],
      });

      await updateKeepaliveLoopSummary({
        github,
        context: buildContext(659),
        core: buildCore(),
        inputs: {
          prNumber: 659,
          action: 'stop',
          reason,
          gateConclusion: 'success',
          tasksTotal: 3,
          tasksUnchecked: reason === 'verification-exhausted' ? 0 : 2,
          keepaliveEnabled: true,
          autofixEnabled: false,
          iteration: 5,
          maxIterations: 5,
          failureThreshold: 3,
          trace: `trace-terminal-${reason}-${forceRetry}`,
          forceRetry,
          retry_workflow_id: 'agents-81-gate-followups.yml',
        },
      });

      const dispatches = github.actions.filter((action) => action.type === 'workflow-dispatch');
      assert.equal(dispatches.length, forceRetry ? 0 : 1, `${reason} forceRetry=${forceRetry}`);
      if (!forceRetry) {
        assert.deepEqual(dispatches[0].inputs, { pr_number: '659', force_retry: 'true' });
      }
    }
  }
});

test('a consumed forced recovery lease survives later ordinary wakeups', async () => {
  const initialState = formatStateComment({
    trace: 'trace-durable-recovery-lease',
    iteration: 5,
    max_iterations: 5,
    failure_threshold: 3,
    failure: {},
    tasks: { total: 3, unchecked: 2 },
  });
  const first = buildGithubStub({
    comments: [{ id: 106, body: initialState, html_url: 'https://example.com/106' }],
  });

  await updateKeepaliveLoopSummary({
    github: first,
    context: buildContext(661),
    core: buildCore(),
    inputs: {
      prNumber: 661,
      action: 'stop',
      reason: 'round-budget-exhausted',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 5,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-durable-recovery-lease',
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });

  const issuedUpdate = first.actions.find((action) => action.type === 'update');
  const issuedState = parseStateComment(issuedUpdate.body).data;
  assert.equal(issuedState.recovery_lease.status, 'issued');
  assert.equal(issuedState.recovery_lease.reason, 'round-budget-exhausted');
  assert.equal(
    first.actions.filter((action) => action.type === 'workflow-dispatch').length,
    1,
  );

  const forced = buildGithubStub({
    comments: [{ id: 106, body: issuedUpdate.body, html_url: 'https://example.com/106' }],
  });
  await updateKeepaliveLoopSummary({
    github: forced,
    context: buildContext(661),
    core: buildCore(),
    inputs: {
      prNumber: 661,
      action: 'run',
      reason: 'ready',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 5,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-durable-recovery-lease',
      forceRetry: true,
      agent_files_changed: 1,
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });

  const consumedUpdate = forced.actions.find((action) => action.type === 'update');
  const consumedState = parseStateComment(consumedUpdate.body).data;
  assert.equal(consumedState.recovery_lease.status, 'consumed');
  assert.ok(forced.actions.some((action) =>
    action.type === 'remove-label' && action.name === 'agent:retry'
  ));
  assert.equal(
    forced.actions.filter((action) => action.type === 'workflow-dispatch').length,
    0,
  );

  const laterWakeup = buildGithubStub({
    comments: [{ id: 106, body: consumedUpdate.body, html_url: 'https://example.com/106' }],
  });
  await updateKeepaliveLoopSummary({
    github: laterWakeup,
    context: buildContext(661),
    core: buildCore(),
    inputs: {
      prNumber: 661,
      action: 'stop',
      reason: 'round-budget-exhausted',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 6,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-durable-recovery-lease',
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });

  const laterUpdate = laterWakeup.actions.find((action) => action.type === 'update');
  assert.equal(parseStateComment(laterUpdate.body).data.recovery_lease.status, 'consumed');
  assert.equal(
    laterWakeup.actions.filter((action) => action.type === 'workflow-dispatch').length,
    0,
  );

  const raisedBudget = buildGithubStub({
    comments: [{ id: 106, body: laterUpdate.body, html_url: 'https://example.com/106' }],
  });
  await updateKeepaliveLoopSummary({
    github: raisedBudget,
    context: buildContext(661),
    core: buildCore(),
    inputs: {
      prNumber: 661,
      action: 'stop',
      reason: 'round-budget-exhausted',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 6,
      maxIterations: 6,
      failureThreshold: 3,
      trace: 'trace-durable-recovery-lease',
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });

  const raisedUpdate = raisedBudget.actions.find((action) => action.type === 'update');
  const raisedState = parseStateComment(raisedUpdate.body).data;
  assert.equal(raisedState.recovery_lease.status, 'issued');
  assert.equal(raisedState.recovery_lease.max_iterations, 6);
  assert.equal(
    raisedBudget.actions.filter((action) => action.type === 'workflow-dispatch').length,
    1,
  );
});

test('an operator guard defers rather than consumes a forced recovery lease', async () => {
  const issuedState = formatStateComment({
    trace: 'trace-deferred-recovery-lease',
    iteration: 5,
    max_iterations: 5,
    failure_threshold: 3,
    failure: {},
    tasks: { total: 3, unchecked: 2 },
    recovery_lease: {
      key: 'round-budget-exhausted:max-iterations=5',
      reason: 'round-budget-exhausted',
      status: 'issued',
      issued_at: '2026-08-13T13:00:00Z',
      last_dispatched_at: '2026-08-13T13:00:00Z',
      dispatch_attempt: 1,
      iteration: 5,
      max_iterations: 5,
    },
  });
  const guarded = buildGithubStub({
    comments: [{ id: 107, body: issuedState, html_url: 'https://example.com/107' }],
  });

  await updateKeepaliveLoopSummary({
    github: guarded,
    context: buildContext(662),
    core: buildCore(),
    inputs: {
      prNumber: 662,
      action: 'skip',
      reason: 'paused',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 5,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-deferred-recovery-lease',
      forceRetry: true,
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });

  const deferredUpdate = guarded.actions.find((action) => action.type === 'update');
  const deferredState = parseStateComment(deferredUpdate.body).data;
  assert.equal(deferredState.recovery_lease.status, 'deferred');
  assert.equal(deferredState.recovery_lease.deferred_reason, 'paused');
  assert.equal(
    guarded.actions.filter((action) => action.type === 'workflow-dispatch').length,
    0,
  );

  const resumed = buildGithubStub({
    comments: [{ id: 107, body: deferredUpdate.body, html_url: 'https://example.com/107' }],
  });
  await updateKeepaliveLoopSummary({
    github: resumed,
    context: buildContext(662),
    core: buildCore(),
    inputs: {
      prNumber: 662,
      action: 'stop',
      reason: 'round-budget-exhausted',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 5,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-deferred-recovery-lease',
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });

  const resumedUpdate = resumed.actions.find((action) => action.type === 'update');
  const resumedState = parseStateComment(resumedUpdate.body).data;
  assert.equal(resumedState.recovery_lease.status, 'issued');
  assert.equal(resumedState.recovery_lease.dispatch_attempt, 2);
  assert.equal(
    resumed.actions.filter((action) => action.type === 'workflow-dispatch').length,
    1,
  );

  const skippedRunner = buildGithubStub({
    comments: [{ id: 107, body: resumedUpdate.body, html_url: 'https://example.com/107' }],
  });
  await updateKeepaliveLoopSummary({
    github: skippedRunner,
    context: buildContext(662),
    core: buildCore(),
    inputs: {
      prNumber: 662,
      action: 'run',
      reason: 'ready',
      runResult: 'skipped',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 5,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-deferred-recovery-lease',
      forceRetry: true,
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });

  const skippedUpdate = skippedRunner.actions.find((action) => action.type === 'update');
  const skippedState = parseStateComment(skippedUpdate.body).data;
  assert.equal(skippedState.recovery_lease.status, 'deferred');
  assert.equal(skippedState.recovery_lease.deferred_reason, 'agent-run-skipped');

  const preflightFailure = buildGithubStub({
    comments: [{ id: 107, body: resumedUpdate.body, html_url: 'https://example.com/107' }],
  });
  await updateKeepaliveLoopSummary({
    github: preflightFailure,
    context: buildContext(662),
    core: buildCore(),
    inputs: {
      prNumber: 662,
      action: 'run',
      reason: 'ready',
      runResult: 'failure',
      agent_execution_started: false,
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 5,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-deferred-recovery-lease',
      forceRetry: true,
      agent_summary: 'Missing Codex auth: set CODEX_AUTH_JSON',
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });

  const preflightUpdate = preflightFailure.actions.find(
    (action) => action.type === 'update' && parseStateComment(action.body)?.data?.recovery_lease,
  );
  const preflightState = parseStateComment(preflightUpdate.body).data;
  assert.equal(preflightState.recovery_lease.status, 'deferred');
  assert.equal(preflightState.recovery_lease.deferred_reason, 'agent-run-failed');
});

test('a failed bounded dispatch defers without adding a sticky retry label', async () => {
  const existingState = formatStateComment({
    trace: 'trace-dispatch-fallback',
    iteration: 5,
    max_iterations: 5,
    failure_threshold: 3,
    failure: {},
  });
  const github = buildGithubStub({
    comments: [{ id: 105, body: existingState, html_url: 'https://example.com/105' }],
    failWorkflowDispatch: true,
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(660),
    core: buildCore(),
    inputs: {
      prNumber: 660,
      action: 'stop',
      reason: 'round-budget-exhausted',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 5,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-dispatch-fallback',
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });

  assert.ok(github.actions.some((action) => action.type === 'workflow-dispatch-failed'));
  assert.ok(!github.actions.some((action) =>
    action.type === 'label' && action.labels.includes('agent:retry')
  ));
  const stateUpdates = github.actions.filter((action) => action.type === 'update');
  const deferredState = parseStateComment(stateUpdates.at(-1).body).data;
  assert.equal(deferredState.recovery_lease.status, 'deferred');
  assert.equal(deferredState.recovery_lease.deferred_reason, 'workflow-dispatch-failed');

  const sweepRetry = buildGithubStub({
    comments: [{ id: 105, body: stateUpdates.at(-1).body, html_url: 'https://example.com/105' }],
  });
  await updateKeepaliveLoopSummary({
    github: sweepRetry,
    context: buildContext(660),
    core: buildCore(),
    inputs: {
      prNumber: 660,
      action: 'stop',
      reason: 'round-budget-exhausted',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 2,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 5,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-dispatch-fallback',
      retry_workflow_id: 'agents-81-gate-followups.yml',
    },
  });
  assert.equal(
    sweepRetry.actions.filter((action) => action.type === 'workflow-dispatch').length,
    1,
  );
  assert.ok(!sweepRetry.actions.some((action) =>
    action.type === 'label' && action.labels.includes('agent:retry')
  ));
  const sweepState = parseStateComment(
    sweepRetry.actions.find((action) => action.type === 'update').body,
  ).data;
  assert.equal(sweepState.recovery_lease.status, 'issued');
  assert.equal(sweepState.recovery_lease.dispatch_attempt, 2);
});

test('updateKeepaliveLoopSummary routes logic failures to automation retry', async () => {
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

  const retryLabel = github.actions.find((action) =>
    action.type === 'label' && action.labels.includes('agent:retry')
  );
  assert.equal(retryLabel, undefined);
  assert.ok(github.actions.some((action) => action.type === 'workflow-dispatch'));
  assert.equal(
    github.actions.some((action) => action.type === 'label' && action.labels.includes('needs-human')),
    false
  );
});

test('selectEscalationDisposition never presumes a human authority boundary', () => {
  assert.equal(selectEscalationDisposition({ required: false }), 'none');
  assert.equal(
    selectEscalationDisposition({
      required: true,
      errorCategory: 'auth',
      summaryReason: 'agent-run-failed',
    }),
    'challenge-due'
  );
  for (const errorCategory of ['resource_failure', 'logic_failure', 'unknown_failure']) {
    assert.equal(
      selectEscalationDisposition({
        required: true,
        errorCategory,
        summaryReason: 'agent-run-failed-repeat',
      }),
      'automation-retry'
    );
  }
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
  assert.match(updateAction.body, /Error type \| agent/);
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

  // Should update comment and add the automerge label (tasks-complete), but
  // must NOT add needs-human (tasks-complete is a success terminal, #2270).
  assert.equal(github.actions[0].type, 'update');
  // Should show completed status
  assert.match(github.actions[0].body, /tasks-complete/);
  // Failure state should be clear
  assert.match(github.actions[0].body, /"failure":\{\}/);
  // No needs-human on a success terminal.
  assert.equal(
    github.actions.some((action) => action.type === 'label' && action.labels.includes('needs-human')),
    false,
  );
  // The automerge label IS applied so the completed PR reaches the guarded merger.
  assert.equal(
    github.actions.some((action) => action.type === 'label' && action.labels.includes('automerge')),
    true,
  );
});

test('updateKeepaliveLoopSummary clears stale human-blocker labels on tasks-complete', async () => {
  const existingState = formatStateComment({
    trace: 'trace-stale-human',
    iteration: 3,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 2 },
    attention: { owner: 'automation', disposition: 'challenge-due' },
  });
  const github = buildGithubStub({
    comments: [{ id: 46, body: existingState, html_url: 'https://example.com/46' }],
    labels: ['Agent:Needs-Attention', 'NEEDS-HUMAN', 'agent:claude', 'agents:keepalive'],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(458),
    core: buildCore(),
    inputs: {
      prNumber: 458,
      action: 'stop',
      reason: 'tasks-complete',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 3,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-stale-human',
    },
  });

  const removedLabels = github.actions
    .filter((action) => action.type === 'remove-label')
    .map((action) => action.name)
    .sort();
  assert.deepEqual(removedLabels, ['agent:needs-attention']);
  assert.equal(
    github.actions.some((action) => action.type === 'remove-label' && action.name === 'needs-human'),
    false,
  );
  assert.equal(
    github.actions.some((action) => action.type === 'label' && action.labels.includes('needs-human')),
    false,
  );
});

test('a successful terminal migrates and clears legacy automation attention state', async () => {
  const existingState = formatStateComment({
    trace: 'trace-legacy-attention',
    iteration: 3,
    failure_threshold: 3,
    failure: { reason: 'agent-run-failed', count: 2 },
    attention: {
      key: 'legacy-agent-run-failed',
      first_seen_at: '2026-07-01T12:00:00Z',
    },
  });
  const github = buildGithubStub({
    comments: [{ id: 47, body: existingState, html_url: 'https://example.com/47' }],
    labels: ['agent:needs-attention', 'needs-human'],
  });

  await updateKeepaliveLoopSummary({
    github,
    context: buildContext(459),
    core: buildCore(),
    inputs: {
      prNumber: 459,
      action: 'stop',
      reason: 'tasks-complete',
      gateConclusion: 'success',
      tasksTotal: 3,
      tasksUnchecked: 0,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 3,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-legacy-attention',
    },
  });

  assert.ok(github.actions.some((action) =>
    action.type === 'remove-label' && action.name === 'agent:needs-attention'
  ));
  assert.equal(
    github.actions.some((action) => action.type === 'remove-label' && action.name === 'needs-human'),
    false,
  );
  const updateAction = github.actions.find((action) => action.type === 'update');
  assert.equal(parseStateComment(updateAction.body).data.attention, undefined);
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

test('evaluateKeepaliveLoop routes to verification prompt when tasks complete', async () => {
  const pr = {
    number: 111,
    head: { ref: 'feature/verify', sha: 'sha-11' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [x] done\n## Acceptance Criteria\n- [x] pass',
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-11', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'run');
  assert.equal(result.reason, 'verify-acceptance');
  assert.equal(result.promptMode, 'verify');
  assert.equal(result.promptFile, '.github/codex/prompts/verifier_acceptance_check.md');
});

test('evaluateKeepaliveLoop stops when verification already done', async () => {
  const pr = {
    number: 112,
    head: { ref: 'feature/verified', sha: 'sha-12' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [x] done\n## Acceptance Criteria\n- [x] pass',
  };
  const existingState = formatStateComment({
    verification: { status: 'done' },
  });
  const github = buildGithubStub({
    pr,
    comments: [{ id: 45, body: existingState, html_url: 'https://example.com/45' }],
    workflowRuns: [{ head_sha: 'sha-12', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'stop');
  assert.equal(result.reason, 'tasks-complete');
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

test('extractSourceSection captures source context with agent subsections', () => {
  const { extractSourceSection } = require('../keepalive_loop.js');

  const prBody = `## Source
<!-- Updated WORKFLOW_OUTPUTS.md context:start -->
## Context for Agent

### Related Issues/PRs

### Tasks
- [ ] #1001
`;

  const source = extractSourceSection(prBody);
  assert.ok(source.includes('Context for Agent'));
  assert.ok(source.includes('#1001'));
});

test('extractSourceSection supports nested heading levels', () => {
  const { extractSourceSection } = require('../keepalive_loop.js');

  const prBody = `### Source
- Parent issue: https://github.com/org/repo/issues/123

## Next Section
Unrelated content`;

  const source = extractSourceSection(prBody);
  assert.ok(source.includes('github.com'));
  assert.ok(!source.includes('Unrelated content'));
});

test('extractSourceSection handles indented headings', () => {
  const { extractSourceSection } = require('../keepalive_loop.js');

  const prBody = `  ## Source
  - https://github.com/org/repo/issues/456

  ## Next Section
Unrelated content`;

  const source = extractSourceSection(prBody);
  assert.ok(source.includes('github.com/org/repo/issues/456'));
  assert.ok(!source.includes('Unrelated content'));
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

test('buildTaskAppendix highlights attempted tasks and suggests next task', () => {
  const { buildTaskAppendix } = require('../keepalive_loop.js');
  const sections = {
    tasks: '- [ ] Task A\n- [ ] Task B\n- [ ] Task C',
  };
  const checkboxCounts = { total: 3, checked: 0, unchecked: 3 };
  const state = {
    attempted_tasks: [{ task: 'Task A' }],
  };
  const appendix = buildTaskAppendix(sections, checkboxCounts, state);
  assert.ok(appendix.includes('Recently Attempted Tasks'));
  assert.ok(appendix.includes('Task A'));
  assert.ok(appendix.includes('Suggested Next Task'));
  assert.ok(appendix.includes('- Task B'));
});

test('buildTaskAppendix does not suggest status-metric checklist items as next task', () => {
  const { buildTaskAppendix } = require('../keepalive_loop.js');
  const sections = {
    tasks: [
      '- [ ] Updated: 2026-04-26T12:33:27.204Z',
      '- [ ] Repos checked: 11/11',
      '- [ ] Open sync PRs: 439',
    ].join('\n'),
    acceptance: '- [ ] Acceptance criteria section missing from source issue.',
  };
  const checkboxCounts = { total: 0, checked: 0, unchecked: 0 };

  const appendix = buildTaskAppendix(sections, checkboxCounts, {});
  assert.ok(!appendix.includes('### Suggested Next Task'));
});

test('evaluateKeepaliveLoop stops with no-checklists when only status metrics/placeholders exist', async () => {
  const pr = {
    number: 113,
    head: { ref: 'feature/status-metrics-only', sha: 'sha-13' },
    labels: [{ name: 'agent:codex' }],
    body: [
      '## Tasks',
      '- [ ] Updated: 2026-04-26T12:33:27.204Z',
      '- [ ] Repos checked: 11/11',
      '- [ ] Open sync PRs: 439',
      '',
      '## Acceptance Criteria',
      '- [ ] Acceptance criteria section missing from source issue.',
    ].join('\n'),
  };
  const github = buildGithubStub({
    pr,
    workflowRuns: [{ head_sha: 'sha-13', conclusion: 'success' }],
  });
  const result = await evaluateKeepaliveLoop({
    github,
    context: buildContext(pr.number),
    core: buildCore(),
  });
  assert.equal(result.action, 'stop');
  assert.equal(result.reason, 'no-checklists');
  assert.deepEqual(result.checkboxCounts, { total: 0, checked: 0, unchecked: 0 });
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

test('markAgentRunning records suggested focus task in state', async () => {
  const existingStateBody = formatStateComment({
    trace: 'trace-focus',
    iteration: 1,
    attempted_tasks: [{ task: 'Task A' }],
  });
  const comments = [
    {
      id: 202,
      body: `<!-- keepalive-loop-summary -->\n## Summary\n${existingStateBody}`,
      html_url: 'https://example.com/202',
    },
  ];
  const pr = {
    number: 51,
    head: { ref: 'feature/focus', sha: 'sha-focus' },
    labels: [{ name: 'agent:codex' }],
    body: '## Tasks\n- [ ] Task A\n- [ ] Task B\n## Acceptance Criteria\n- [ ] pass',
  };
  const github = buildGithubStub({ comments, pr });
  const inputs = {
    pr_number: 51,
    agent_type: 'codex',
    iteration: 1,
    max_iterations: 3,
    tasks_total: 3,
    tasks_unchecked: 3,
    trace: 'trace-focus',
  };

  await markAgentRunning({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    core: buildCore(),
    inputs,
  });

  const parsed = parseStateComment(github.actions[0].body);
  assert.ok(parsed);
  assert.equal(parsed.data.current_focus, 'Task B');
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

test('analyzeTaskCompletion parses numbered checklist items', async () => {
  const commits = [
    { sha: 'abc123', commit: { message: 'feat: add step summary output to keepalive loop' } },
  ];
  const files = [
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
1. [ ] Add step summary output to keepalive loop
2) [ ] Add tests for step summary
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

  const numberedMatch = result.matches.find(m =>
    m.task.toLowerCase().includes('step summary output')
  );
  assert.ok(numberedMatch, 'Should match numbered checklist task');
  assert.equal(numberedMatch.confidence, 'high', 'Should be high confidence');
});

test('analyzeTaskCompletion matches issue link tasks using PR metadata', async () => {
  const commits = [
    { sha: 'abc123', commit: { message: 'chore: update keepalive loop' } },
  ];
  const files = [
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
- [ ] [#1001](https://github.com/org/repo/issues/1001)
`;

  const result = await analyzeTaskCompletion({
    github,
    context: { repo: { owner: 'test', repo: 'repo' } },
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    taskText,
    core: buildCore(),
    pr: { title: 'codex/issue-1001', head: { ref: 'codex/issue-1001' } },
  });

  assert.equal(result.matches.length, 1, 'Should match issue link task');
  assert.equal(result.matches[0].confidence, 'high', 'Should be high confidence');
  assert.ok(result.matches[0].reason.includes('Issue 1001'), 'Reason should include issue number');
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

test('analyzeTaskCompletion gives medium confidence for 25% keyword match with file match', async () => {
  // Stricter thresholds: 25% keyword match + file match = medium confidence (was high before tightening)
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
  assert.equal(wizardMatch.confidence, 'medium', 'Should be medium confidence with file match at ~25% keywords (stricter thresholds)');
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
  assert.equal(configMatch.confidence, 'medium', 'Should be medium confidence with synonym matching (stricter thresholds)');
});

test('analyzeTaskCompletion skips when repo context is missing', async () => {
  const github = {
    rest: {
      repos: {
        async compareCommits() {
          throw new Error('compareCommits should not be called');
        },
      },
      pulls: {
        async listFiles() {
          throw new Error('listFiles should not be called');
        },
      },
    },
  };

  const result = await analyzeTaskCompletion({
    github,
    context: {},
    prNumber: 1,
    baseSha: 'base123',
    headSha: 'head456',
    taskText: '- [ ] Example task',
    core: buildCore(),
  });

  assert.deepEqual(result.matches, []);
  assert.equal(result.summary, 'Missing repo context for task analysis');
});

test('autoReconcileTasks handles tasks with backticks and special characters', async () => {
  // This test documents a critical bug: task names with backticks broke the
  // workflow when passed via GitHub Actions expression interpolation.
  // The fix uses environment variables instead of inline string interpolation.
  // See: https://github.com/stranske/Workflows/pull/494
  const prBody = `## Tasks
- [ ] Create \`src/trend_analysis/stages/__init__.py\` package
- [ ] Add "quoted" task name
- [ ] Task with 'single quotes'
- [x] Already completed task
`;

  const llmCompletedTasks = [
    'Create `src/trend_analysis/stages/__init__.py` package',
    'Add "quoted" task name',
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
          return { data: [] };
        },
      },
      repos: {
        async compareCommits() {
          return { data: { commits: [] } };
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
    llmCompletedTasks,
    core: buildCore(),
  });

  assert.ok(result.updated, 'Should update PR body with special character tasks');
  assert.equal(result.tasksChecked, 2, 'Should check off both LLM-detected tasks');
  assert.equal(result.sources.llm, 2, 'Should report LLM sources');
  
  if (updatedBody) {
    assert.ok(updatedBody.includes('[x] Create `src/trend_analysis/stages/__init__.py` package'), 
      'Should check off task with backticks');
    assert.ok(updatedBody.includes('[x] Add "quoted" task name'),
      'Should check off task with double quotes');
    assert.ok(updatedBody.includes('[ ] Task with \'single quotes\''),
      'Should leave uncompleted task with single quotes');
  }
});

test('autoReconcileTasks checks numbered checklist items', async () => {
  const prBody = `## Tasks
1. [ ] Ship first numbered task
2) [ ] Ship second numbered task
`;

  const llmCompletedTasks = [
    'Ship first numbered task',
    'Ship second numbered task',
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
          return { data: [] };
        },
      },
      repos: {
        async compareCommits() {
          return { data: { commits: [] } };
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
    llmCompletedTasks,
    core: buildCore(),
  });

  assert.ok(result.updated, 'Should update PR body for numbered tasks');
  assert.equal(result.tasksChecked, 2, 'Should check off both numbered tasks');
  assert.equal(result.sources.llm, 2, 'Should report LLM sources');

  if (updatedBody) {
    assert.ok(updatedBody.includes('1. [x] Ship first numbered task'),
      'Should check off first numbered task');
    assert.ok(updatedBody.includes('2) [x] Ship second numbered task'),
      'Should check off second numbered task');
  }
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
  assert.equal(result.sources.commit, 1, 'Should report commit-based source count (stricter matching reduces to 1)');
  assert.equal(result.sources.llm, 0, 'Should report no LLM sources');
  
  if (updatedBody) {
    assert.ok(updatedBody.includes('[x] Add step summary'), 'Should check off matched task');
    assert.ok(updatedBody.includes('[x] Already completed'), 'Should preserve already-checked tasks');
  }
});

test('autoReconcileTasks skips when repo context is missing', async () => {
  const github = {
    rest: {
      pulls: {
        async get() {
          throw new Error('get should not be called');
        },
      },
    },
  };

  const result = await autoReconcileTasks({
    github,
    context: {},
    prNumber: 0,
    baseSha: 'base123',
    headSha: 'head456',
    core: buildCore(),
  });

  assert.equal(result.updated, false);
  assert.equal(result.tasksChecked, 0);
  assert.equal(result.details, 'Missing repo context or PR number');
  assert.deepEqual(result.sources, { llm: 0, commit: 0 });
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
  assert.deepEqual(result.sources, { llm: 0, commit: 0 }, 'Should report zero sources');
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

test('updateKeepaliveLoopSummary displays LLM provider analysis details', async () => {
  const existingState = formatStateComment({
    trace: 'trace-llm',
    iteration: 1,
    max_iterations: 5,
    failure_threshold: 3,
  });
  const github = buildGithubStub({
    comments: [{ id: 77, body: existingState, html_url: 'https://example.com/77' }],
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
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-llm',
      llm_provider: 'github-models',
      llm_confidence: 0.95,
      llm_analysis_run: true,
    },
  });

  assert.equal(github.actions.length, 2);
  assert.equal(github.actions[0].type, 'update');
  assert.match(github.actions[0].body, /### 🧠 Task Analysis/);
  assert.match(github.actions[0].body, /GitHub Models \(primary\)/);
  assert.match(github.actions[0].body, /Confidence \| 95%/);
});

test('updateKeepaliveLoopSummary shows fallback warning for OpenAI provider', async () => {
  const existingState = formatStateComment({
    trace: 'trace-openai',
    iteration: 1,
    max_iterations: 5,
    failure_threshold: 3,
  });
  const github = buildGithubStub({
    comments: [{ id: 78, body: existingState, html_url: 'https://example.com/78' }],
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
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-openai',
      llm_provider: 'openai',
      llm_confidence: 0.87,
      llm_analysis_run: true,
    },
  });

  assert.equal(github.actions.length, 2);
  assert.equal(github.actions[0].type, 'update');
  assert.match(github.actions[0].body, /### 🧠 Task Analysis/);
  assert.match(github.actions[0].body, /OpenAI \(fallback\)/);
  assert.match(github.actions[0].body, /Primary provider.*was unavailable/);
});

test('updateKeepaliveLoopSummary shows regex fallback warning', async () => {
  const existingState = formatStateComment({
    trace: 'trace-regex',
    iteration: 1,
    max_iterations: 5,
    failure_threshold: 3,
  });
  const github = buildGithubStub({
    comments: [{ id: 79, body: existingState, html_url: 'https://example.com/79' }],
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
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-regex',
      llm_provider: 'regex-fallback',
      llm_confidence: 0.7,
      llm_analysis_run: true,
    },
  });

  assert.equal(github.actions.length, 2);
  assert.equal(github.actions[0].type, 'update');
  assert.match(github.actions[0].body, /### 🧠 Task Analysis/);
  assert.match(github.actions[0].body, /Regex \(fallback\)/);
  assert.match(github.actions[0].body, /Primary provider.*was unavailable/);
});
