'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { SKIP_MARKER } = require('../keepalive_guard_utils');

function createSummary() {
  return {
    entries: [],
    written: false,
    addHeading(text) {
      this.entries.push({ type: 'heading', text });
      return this;
    },
    addRaw(text) {
      this.entries.push({ type: 'raw', text });
      return this;
    },
    addEOL() {
      this.entries.push({ type: 'eol' });
      return this;
    },
    async write() {
      this.written = true;
    },
  };
}

function createCore() {
  const outputs = {};
  const warnings = [];
  const summary = createSummary();
  const core = {
    summary,
    setOutput(key, value) {
      outputs[key] = value;
    },
    warning(message) {
      warnings.push(message);
    },
  };
  return { core, outputs, warnings, summary };
}

function loadRunnerWithGate(stub) {
  const gatePath = require.resolve('../keepalive_gate.js');
  const runnerPath = require.resolve('../keepalive_orchestrator_gate_runner.js');
  const gateModule = require(gatePath);
  const original = gateModule.evaluateKeepaliveGate;
  gateModule.evaluateKeepaliveGate = stub;
  delete require.cache[runnerPath];
  const { runKeepaliveGate } = require(runnerPath);
  return {
    runKeepaliveGate,
    restore() {
      gateModule.evaluateKeepaliveGate = original;
      delete require.cache[runnerPath];
    },
  };
}

function createGithub(options = {}) {
  const {
    pull,
    pullError,
    runsByWorkflow = {},
    combinedStatus = { state: 'success', statuses: [] },
    comments = [],
    commentPages = null,
    commentScanError = null,
    graphqlError,
    graphqlUnavailable = false,
  } = options;
  const calls = {
    labelAdds: [],
    labelRemoves: [],
    commentsCreated: [],
    commentPaginateCalls: 0,
    commentIteratorCalls: 0,
    commentPagesFetched: 0,
    graphql: [],
  };

  const github = {
    rest: {
      pulls: {
        async get() {
          if (pullError) {
            throw pullError;
          }
          return { data: pull };
        },
      },
      repos: {
        async getCombinedStatusForRef() {
          return { data: combinedStatus };
        },
      },
      actions: {
        async listWorkflowRuns({ workflow_id: workflowId }) {
          return { data: { workflow_runs: runsByWorkflow[workflowId] || [] } };
        },
      },
      issues: {
        async listComments() {
          return { data: comments };
        },
        async addLabels(params) {
          calls.labelAdds.push(params);
          return { data: params.labels || [] };
        },
        async removeLabel(params) {
          calls.labelRemoves.push(params);
          return { data: { name: params.name } };
        },
        async createComment(params) {
          calls.commentsCreated.push(params);
          return { data: { id: 123, body: params.body } };
        },
      },
    },
    paginate: async function paginate() {
      calls.commentPaginateCalls += 1;
      if (commentScanError) {
        throw commentScanError;
      }
      if (commentPages) {
        calls.commentPagesFetched += commentPages.length;
        return commentPages.flat();
      }
      calls.commentPagesFetched += 1;
      return comments;
    },
    __calls: calls,
  };
  if (!graphqlUnavailable) {
    github.graphql = async function graphql(query, variables) {
      calls.graphql.push({ query, variables });
      if (graphqlError) {
        throw graphqlError;
      }
      return { markPullRequestReadyForReview: { pullRequest: { number: pull?.number || 17, isDraft: false } } };
    };
  }
  github.paginate.iterator = async function* paginateIterator() {
    calls.commentIteratorCalls += 1;
    if (commentScanError) {
      throw commentScanError;
    }
    const pages = commentPages || [comments];
    for (const page of pages) {
      calls.commentPagesFetched += 1;
      yield { data: page };
    }
  };
  return github;
}

function makeEnv(overrides = {}) {
  return {
    KEEPALIVE_ENABLED: 'true',
    KEEPALIVE_TRACE: 'trace-1',
    KEEPALIVE_ROUND: '2',
    KEEPALIVE_PR: '17',
    KEEPALIVE_MAX_RETRIES: '2',
    ...overrides,
  };
}

function makePullRequest(overrides = {}) {
  return {
    number: 17,
    node_id: 'PR_node_17',
    state: 'open',
    draft: false,
    labels: [],
    body: '',
    head: { sha: 'abc123', ref: 'feature/keepalive' },
    ...overrides,
  };
}

function createGateResult(overrides = {}) {
  return {
    ok: true,
    pendingGate: false,
    primaryAgent: 'codex',
    runCap: 2,
    activeRuns: 1,
    activeBreakdown: { orchestrator: 1, worker: 0 },
    hasSyncRequiredLabel: false,
    headSha: 'abc123',
    lastGreenSha: 'abc123',
    ...overrides,
  };
}

test('runKeepaliveGate proceeds when keepalive gating is not required', async () => {
  const { core, outputs, summary } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  await runKeepaliveGate({
    core,
    github: createGithub(),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 99 },
    env: makeEnv({ KEEPALIVE_ENABLED: 'false' }),
  });

  assert.equal(outputs.proceed, 'true');
  assert.equal(outputs.reason, '');
  assert.ok(summary.entries.some((entry) => entry.type === 'raw'));
  restore();
});

test('runKeepaliveGate skips when PR number is missing', async () => {
  const { core, outputs, summary } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  await runKeepaliveGate({
    core,
    github: createGithub(),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 88 },
    env: makeEnv({ KEEPALIVE_PR: 'not-a-number' }),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'missing-pr-number');
  assert.equal(summary.written, true);
  restore();
});

test('runKeepaliveGate reports failure when PR fetch fails', async () => {
  const { core, outputs, warnings } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const error = new Error('no access');
  await runKeepaliveGate({
    core,
    github: createGithub({ pullError: error }),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 77 },
    env: makeEnv(),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'pr-fetch-failed');
  assert.ok(warnings.some((message) => message.includes('Unable to load PR')));
  restore();
});

test('runKeepaliveGate records gate status when workflow run is queued', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult({ runCap: 3, activeRuns: 2 });
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: ['agents:keepalive', 'agent:codex'],
  });

  await runKeepaliveGate({
    core,
    github: createGithub({
      pull: pr,
      runsByWorkflow: {
        'pr-00-gate.yml': [
          { head_sha: 'abc123', status: 'queued', conclusion: null },
        ],
      },
    }),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 66 },
    env: makeEnv(),
  });

  assert.equal(outputs.agent_alias, 'codex');
  assert.equal(outputs.run_cap, '3');
  assert.equal(outputs.active_runs, '2');
  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'gate-run-status:queued');
  restore();
});

test('runKeepaliveGate skips when keepalive is paused by label', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: ['agents:paused', 'agents:keepalive', 'agent:codex'],
  });

  await runKeepaliveGate({
    core,
    github: createGithub({
      pull: pr,
      runsByWorkflow: {
        'pr-00-gate.yml': [
          { head_sha: 'abc123', status: 'completed', conclusion: 'success' },
        ],
      },
    }),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 55 },
    env: makeEnv(),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'keepalive-paused');
  restore();
});

test('runKeepaliveGate reports missing keepalive labels', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: [],
  });

  await runKeepaliveGate({
    core,
    github: createGithub({
      pull: pr,
      runsByWorkflow: {
        'pr-00-gate.yml': [
          { head_sha: 'abc123', status: 'completed', conclusion: 'success' },
        ],
      },
    }),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 50 },
    env: makeEnv(),
  });

  assert.equal(outputs.proceed, 'false');
  assert.ok(outputs.reason.includes('missing-label:agents:keepalive'));
  assert.ok(outputs.reason.includes('missing-label:agent:codex'));
  restore();
});

test('runKeepaliveGate does not report gate-run-missing when head SHA is unavailable', async () => {
  const { core, outputs, warnings } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: ['agents:keepalive', 'agent:codex'],
    head: { sha: '', ref: 'feature/keepalive' },
  });

  await runKeepaliveGate({
    core,
    github: createGithub({ pull: pr }),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 51 },
    env: makeEnv(),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'missing-head-sha');
  assert.ok(warnings.some((message) => message.includes('head SHA is unavailable')));
  assert.ok(!outputs.reason.includes('gate-run-missing'));
  restore();
});

test('runKeepaliveGate does not self-heal from non-routing agent metadata labels', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: ['agent:rate-limited', 'agent:retry'],
  });
  const github = createGithub({
    pull: pr,
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'abc123', status: 'completed', conclusion: 'success' },
      ],
    },
  });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 49 },
    env: makeEnv(),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(github.__calls.labelAdds.length, 0);
  assert.ok(outputs.reason.includes('missing-label:agents:keepalive'));
  assert.ok(outputs.reason.includes('missing-label:agent:codex'));
  restore();
});

test('runKeepaliveGate self-heals missing keepalive labels for automation PRs', async () => {
  const { core, outputs, summary } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: ['codex-automation'],
    head: { sha: 'abc123', ref: 'codex/issue-17' },
  });
  const github = createGithub({
    pull: pr,
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'abc123', status: 'completed', conclusion: 'success' },
      ],
    },
  });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 47 },
    env: makeEnv(),
  });

  assert.equal(outputs.proceed, 'true');
  assert.deepEqual(github.__calls.labelAdds.map((call) => call.labels), [
    ['agents:keepalive', 'agent:codex'],
  ]);
  assert.ok(summary.entries.some((entry) => entry.text?.includes('Self-healed missing PR label')));
  restore();
});

test('runKeepaliveGate infers agent from claude/* branch when no agent label is present', async () => {
  const { core, outputs } = createCore();
  // Simulate evaluateKeepaliveGate returning no primaryAgent (no existing agent:* label).
  const gateStub = async () => createGateResult({ primaryAgent: '' });
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: [],
    head: { sha: 'abc123', ref: 'claude/issue-17-portal-state' },
  });
  const github = createGithub({
    pull: pr,
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'abc123', status: 'completed', conclusion: 'success' },
      ],
    },
  });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 46 },
    env: makeEnv(),
  });

  assert.equal(outputs.agent_alias, 'claude');
  assert.deepEqual(github.__calls.labelAdds.map((call) => call.labels), [
    ['agents:keepalive', 'agent:claude'],
  ]);
  restore();
});

test('runKeepaliveGate stops after too many prior failures', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    labels: [],
  });

  await runKeepaliveGate({
    core,
    github: createGithub({
      pull: pr,
      runsByWorkflow: {
        'pr-00-gate.yml': [
          { head_sha: 'abc123', status: 'completed', conclusion: 'success' },
        ],
      },
      comments: [
        { body: `${SKIP_MARKER}\nKeepalive 1 trace skipped: missing-label:agents:keepalive` },
        { body: `${SKIP_MARKER}\nKeepalive 2 trace skipped: missing-label:agent:codex` },
      ],
    }),
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 49 },
    env: makeEnv({ KEEPALIVE_MAX_RETRIES: '1' }),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'too-many-failures');
  restore();
});

test('runKeepaliveGate converts checklist-complete draft PRs to ready for review', async () => {
  const { core, outputs, summary } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    draft: true,
    labels: ['agents:keepalive', 'agent:codex', 'agents:paused', 'needs-human', 'agent:needs-attention'],
    body: [
      '## Review Checklist',
      '- [ ] CI passes with updated workflows',
      '- [x] No repo-specific customizations were overwritten',
      '',
      '<!-- auto-status-summary:start -->',
      '## Automated Status Summary',
      '',
      '#### Tasks',
      '- [x] Acceptance covered',
      '',
      '#### Acceptance Criteria',
      '- [x] Tests pass',
      '<!-- auto-status-summary:end -->',
    ].join('\n'),
  });
  const github = createGithub({
    pull: pr,
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'abc123', status: 'completed', conclusion: 'success' },
      ],
    },
  });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 44 },
    env: makeEnv({ KEEPALIVE_MAX_RETRIES: '5' }),
  });

  assert.equal(outputs.proceed, 'true');
  assert.equal(outputs.reason, '');
  assert.equal(github.__calls.graphql.length, 1);
  assert.equal(github.__calls.graphql[0].variables.pullRequestId, 'PR_node_17');
  const readyMutation = github.__calls.graphql[0].query;
  assert.match(readyMutation, /mutation MarkPullRequestReadyForReview\(\$pullRequestId: ID!\) \{/);
  assert.equal(
    (readyMutation.match(/\{/g) || []).length,
    (readyMutation.match(/\}/g) || []).length
  );
  assert.match(readyMutation, /\n\}$/);
  assert.deepEqual(github.__calls.labelRemoves.map((call) => call.name), [
    'agent:needs-attention',
    'needs-human',
    'agents:paused',
  ]);
  assert.ok(summary.entries.some((entry) => entry.text?.includes('marked ready for review')));
  restore();
});

test('runKeepaliveGate routes incomplete draft PRs to human', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    draft: true,
    labels: ['agents:keepalive', 'agent:codex'],
    body: [
      '<!-- auto-status-summary:start -->',
      '## Automated Status Summary',
      '',
      '#### Tasks',
      '- [x] Implementation started',
      '',
      '#### Acceptance Criteria',
      '- [ ] Acceptance complete',
      '<!-- auto-status-summary:end -->',
    ].join('\n'),
  });
  const github = createGithub({ pull: pr });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 44 },
    env: makeEnv({ KEEPALIVE_MAX_RETRIES: '5' }),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'pr-draft-needs-human');
  assert.deepEqual(github.__calls.labelAdds.map((call) => call.labels), [
    ['agent:needs-attention', 'needs-human'],
  ]);
  assert.equal(github.__calls.commentsCreated.length, 1);
  assert.match(github.__calls.commentsCreated[0].body, /Draft PR requires human disposition/);
  assert.doesNotMatch(github.__calls.commentsCreated[0].body, /agents:paused/);
  restore();
});

test('runKeepaliveGate routes draft PRs with no keepalive checklist to human with explicit reason', async () => {
  const { core, outputs, summary } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    draft: true,
    labels: ['agents:keepalive', 'agent:codex'],
    body: [
      '<!-- auto-status-summary:start -->',
      '## Automated Status Summary',
      '',
      '#### Scope',
      'Draft was opened before tasks were written.',
      '<!-- auto-status-summary:end -->',
    ].join('\n'),
  });
  const github = createGithub({ pull: pr });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 44 },
    env: makeEnv({ KEEPALIVE_MAX_RETRIES: '5' }),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'pr-draft-no-checklist');
  assert.equal(github.__calls.graphql.length, 0);
  assert.equal(github.__calls.commentsCreated.length, 1);
  assert.match(github.__calls.commentsCreated[0].body, /no keepalive checklist items were found/);
  assert.doesNotMatch(github.__calls.commentsCreated[0].body, /with 0 unchecked checklist item/);
  assert.ok(
    summary.entries.some((entry) =>
      entry.text?.includes('no keepalive checklist items were found')
    )
  );
  restore();
});

test('runKeepaliveGate explains draft ready conversion failures without claiming unchecked items remain', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    draft: true,
    labels: ['agents:keepalive', 'agent:codex'],
    body: [
      '<!-- auto-status-summary:start -->',
      '## Automated Status Summary',
      '',
      '#### Tasks',
      '- [x] Implementation complete',
      '',
      '#### Acceptance Criteria',
      '- [x] Verified behavior',
      '<!-- auto-status-summary:end -->',
    ].join('\n'),
  });
  const github = createGithub({
    pull: pr,
    graphqlError: new Error('mutation blocked'),
  });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 44 },
    env: makeEnv({ KEEPALIVE_MAX_RETRIES: '5' }),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'pr-draft-ready-failed');
  assert.equal(github.__calls.graphql.length, 1);
  assert.equal(github.__calls.commentsCreated.length, 1);
  assert.match(github.__calls.commentsCreated[0].body, /automatic ready-for-review conversion failed/);
  assert.doesNotMatch(github.__calls.commentsCreated[0].body, /with 0 unchecked checklist item/);
  restore();
});

test('runKeepaliveGate distinguishes unavailable GraphQL client from missing PR node id', async () => {
  const { core, outputs, summary } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    draft: true,
    labels: ['agents:keepalive', 'agent:codex'],
    body: [
      '<!-- auto-status-summary:start -->',
      '## Automated Status Summary',
      '',
      '#### Tasks',
      '- [x] Implementation complete',
      '',
      '#### Acceptance Criteria',
      '- [x] Verified behavior',
      '<!-- auto-status-summary:end -->',
    ].join('\n'),
  });
  const github = createGithub({
    pull: pr,
    graphqlUnavailable: true,
  });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 44 },
    env: makeEnv({ KEEPALIVE_MAX_RETRIES: '5' }),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'pr-draft-ready-failed');
  assert.equal(github.__calls.graphql.length, 0);
  assert.ok(
    summary.entries.some((entry) =>
      entry.text?.includes('GitHub GraphQL client is unavailable')
    )
  );
  assert.ok(
    !summary.entries.some((entry) =>
      entry.text?.includes('missing GraphQL PR node id')
    )
  );
  restore();
});

test('runKeepaliveGate does not let PR-template checkboxes block draft ready conversion', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    draft: true,
    labels: ['agents:keepalive', 'agent:codex'],
    body: [
      '### Review Checklist',
      '- [ ] CI passes with updated workflows',
      '- [ ] No repo-specific customizations were overwritten',
      '',
      '<!-- auto-status-summary:start -->',
      '## Automated Status Summary',
      '',
      '#### Tasks',
      '- [x] Implementation complete',
      '',
      '#### Acceptance Criteria',
      '- [x] Verified behavior',
      '<!-- auto-status-summary:end -->',
    ].join('\n'),
  });
  const github = createGithub({
    pull: pr,
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'abc123', status: 'completed', conclusion: 'success' },
      ],
    },
  });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 43 },
    env: makeEnv({ KEEPALIVE_MAX_RETRIES: '5' }),
  });

  assert.equal(outputs.proceed, 'true');
  assert.equal(outputs.reason, '');
  assert.equal(github.__calls.graphql.length, 1);
  assert.equal(github.__calls.commentsCreated.length, 0);
  restore();
});

test('runKeepaliveGate scans draft disposition marker before loading skip history', async () => {
  const { core, outputs } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    draft: true,
    labels: ['agents:keepalive', 'agent:codex'],
    body: [
      '<!-- auto-status-summary:start -->',
      '## Automated Status Summary',
      '',
      '#### Tasks',
      '- [ ] Implementation complete',
      '<!-- auto-status-summary:end -->',
    ].join('\n'),
  });
  const github = createGithub({
    pull: pr,
    commentPages: [
      [{ body: '<!-- keepalive-draft-disposition -->\nExisting disposition.' }],
      [{ body: `${SKIP_MARKER}\nKeepalive 1 trace skipped: pr-draft-needs-human` }],
    ],
  });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 42 },
    env: makeEnv({ KEEPALIVE_MAX_RETRIES: '5' }),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'previous-failure:pr-draft-needs-human');
  assert.equal(github.__calls.commentIteratorCalls, 1);
  assert.equal(github.__calls.commentPaginateCalls, 1);
  assert.equal(github.__calls.commentPagesFetched, 3);
  assert.equal(github.__calls.commentsCreated.length, 0);
  restore();
});

test('runKeepaliveGate skips draft disposition comment when existing comments cannot be scanned', async () => {
  const { core, outputs, warnings, summary } = createCore();
  const gateStub = async () => createGateResult();
  const { runKeepaliveGate, restore } = loadRunnerWithGate(gateStub);

  const pr = makePullRequest({
    draft: true,
    labels: ['agents:keepalive', 'agent:codex'],
    body: [
      '<!-- auto-status-summary:start -->',
      '## Automated Status Summary',
      '',
      '#### Tasks',
      '- [ ] Implementation complete',
      '<!-- auto-status-summary:end -->',
    ].join('\n'),
  });
  const github = createGithub({
    pull: pr,
    commentScanError: new Error('comments unavailable'),
  });

  await runKeepaliveGate({
    core,
    github,
    context: { repo: { owner: 'octo', repo: 'demo' }, runId: 41 },
    env: makeEnv({ KEEPALIVE_MAX_RETRIES: '5' }),
  });

  assert.equal(outputs.proceed, 'false');
  assert.equal(outputs.reason, 'pr-draft-needs-human');
  assert.equal(github.__calls.commentsCreated.length, 0);
  assert.ok(warnings.some((message) => message.includes('Unable to scan draft disposition comments')));
  assert.ok(
    summary.entries.some((entry) =>
      entry.text?.includes('Skipped posting draft disposition comment because existing comments could not be scanned')
    )
  );
  restore();
});
