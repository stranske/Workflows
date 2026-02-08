'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const {
  buildVerifierContext,
  formatDiffForContext,
  fetchLocalGitDiff,
  isValidSha,
} = require('../agents_verifier_context.js');

const fixturesDir = path.join(__dirname, 'fixtures');
const prBodyFixture = fs.readFileSync(path.join(fixturesDir, 'pr-body.md'), 'utf8');
const issueBodyOpen = fs.readFileSync(path.join(fixturesDir, 'issue-body-open.md'), 'utf8');
const issueBodyClosed = fs.readFileSync(path.join(fixturesDir, 'issue-body-closed.md'), 'utf8');

const withEnv = async (key, value, callback) => {
  const hadKey = Object.prototype.hasOwnProperty.call(process.env, key);
  const previous = process.env[key];
  if (value === undefined) {
    delete process.env[key];
  } else {
    process.env[key] = value;
  }
  try {
    return await callback();
  } finally {
    if (hadKey) {
      process.env[key] = previous;
    } else {
      delete process.env[key];
    }
  }
};

const buildCore = () => {
  const outputs = {};
  const notices = [];
  const warnings = [];
  return {
    outputs,
    notices,
    warnings,
    setOutput(key, value) {
      outputs[key] = value;
    },
    notice(message) {
      notices.push(message);
    },
    warning(message) {
      warnings.push(message);
    },
  };
};

const buildGithubStub = ({
  prDetails,
  prsForSha = [],
  closingIssues = [],
  listError = null,
  graphqlError = null,
  runsByWorkflow = {},
  listWorkflowRunsHook = null,
  diffText = '',
} = {}) => ({
  rest: {
    actions: {
      async listWorkflowRuns({ workflow_id: workflowId, head_sha: headSha }) {
        if (listWorkflowRunsHook) {
          const hooked = await listWorkflowRunsHook({ workflow_id: workflowId, head_sha: headSha });
          if (hooked !== undefined) {
            return hooked;
          }
        }
        return { data: { workflow_runs: runsByWorkflow[workflowId] || [] } };
      },
    },
    pulls: {
      async get(params = {}) {
        if (params?.mediaType?.format === 'diff') {
          return { data: diffText };
        }
        return { data: prDetails };
      },
    },
    repos: {
      async listPullRequestsAssociatedWithCommit() {
        if (listError) {
          throw listError;
        }
        return { data: prsForSha };
      },
    },
  },
  async graphql() {
    if (graphqlError) {
      throw graphqlError;
    }
    return {
      repository: {
        pullRequest: {
          closingIssuesReferences: {
            nodes: closingIssues,
          },
        },
      },
    };
  },
});

const withEmptyJobs = (result) => ({
  ...result,
  jobs_summary: { total: 0, conclusions: {}, samples: [], truncated: false },
  jobs_error_category: '',
  jobs_error_message: '',
});

test('buildVerifierContext skips when pull request is not merged', async () => {
  const core = buildCore();
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: { pull_request: { merged: false } },
    sha: 'sha-1',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub(),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.deepEqual(result.ciResults, []);
  assert.equal(core.outputs.should_run, 'false');
  assert.ok(core.outputs.skip_reason.includes('not merged'));
});

test('buildVerifierContext resolves PR from VERIFIER_PR_NUMBER', async () => {
  await withEnv('VERIFIER_PR_NUMBER', '101', async () => {
    const core = buildCore();
    const prDetails = {
      merged: true,
      number: 101,
      title: 'Verifier PR resolution',
      body: prBodyFixture,
      html_url: 'https://example.com/pr/101',
      merge_commit_sha: 'merge-sha-101',
      base: {
        ref: 'main',
        repo: { full_name: 'octo/workflows', owner: { login: 'octo' } },
      },
      head: {
        sha: 'head-sha-101',
        repo: { full_name: 'octo/workflows', owner: { login: 'octo' }, fork: false },
      },
    };
    const context = {
      eventName: 'workflow_call',
      repo: { owner: 'octo', repo: 'workflows' },
      payload: {
        repository: { default_branch: 'main' },
      },
      sha: 'sha-101',
    };
    const result = await buildVerifierContext({
      github: buildGithubStub({ prDetails }),
      context,
      core,
    });
    assert.equal(result.shouldRun, true);
    assert.equal(core.outputs.pr_number, '101');
  });
});

test('buildVerifierContext skips when VERIFIER_PR_NUMBER PR is not merged', async () => {
  await withEnv('VERIFIER_PR_NUMBER', '202', async () => {
    const core = buildCore();
    const prDetails = {
      merged: false,
      number: 202,
      title: 'Unmerged PR',
      body: prBodyFixture,
      html_url: 'https://example.com/pr/202',
      merge_commit_sha: 'merge-sha-202',
      base: { ref: 'main' },
      head: { sha: 'head-sha-202' },
    };
    const context = {
      eventName: 'workflow_call',
      repo: { owner: 'octo', repo: 'workflows' },
      payload: {
        repository: { default_branch: 'main' },
      },
      sha: 'sha-202',
    };
    const result = await buildVerifierContext({
      github: buildGithubStub({ prDetails }),
      context,
      core,
    });
    assert.equal(result.shouldRun, false);
    assert.equal(core.outputs.should_run, 'false');
    assert.ok(core.outputs.skip_reason.includes('not merged'));
  });
});

test('buildVerifierContext warns on invalid VERIFIER_PR_NUMBER and falls back', async () => {
  await withEnv('VERIFIER_PR_NUMBER', 'not-a-number', async () => {
    const core = buildCore();
    const prDetails = {
      merged: true,
      number: 303,
      title: 'Fallback PR',
      body: prBodyFixture,
      html_url: 'https://example.com/pr/303',
      merge_commit_sha: 'merge-sha-303',
      base: { ref: 'main' },
      head: { sha: 'head-sha-303' },
    };
    const context = {
      eventName: 'pull_request',
      repo: { owner: 'octo', repo: 'workflows' },
      payload: {
        repository: { default_branch: 'main' },
        pull_request: {
          merged: true,
          number: 303,
          base: { ref: 'main' },
          html_url: 'https://example.com/pr/303',
        },
      },
      sha: 'sha-303',
    };
    const result = await buildVerifierContext({
      github: buildGithubStub({ prDetails }),
      context,
      core,
    });
    assert.equal(result.shouldRun, true);
    assert.equal(core.outputs.pr_number, '303');
    assert.ok(core.warnings.some((message) => message.includes('Invalid VERIFIER_PR_NUMBER')));
  });
});

test('buildVerifierContext skips when base branch mismatches default', async () => {
  const core = buildCore();
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 99,
        base: { ref: 'dev' },
        html_url: 'https://example.com/pr/99',
      },
    },
    sha: 'sha-2',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub(),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.pr_number, '99');
  assert.ok(core.outputs.skip_reason.includes('base ref'));
});

test('buildVerifierContext skips forked pull requests', async () => {
  const core = buildCore();
  const prDetails = {
    number: 77,
    title: 'Forked change',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/77',
    merge_commit_sha: 'merge-sha-77',
    base: {
      ref: 'main',
      repo: { full_name: 'octo/workflows', owner: { login: 'octo' } },
    },
    head: {
      sha: 'head-sha-77',
      repo: { full_name: 'forker/workflows', owner: { login: 'forker' }, fork: true },
    },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 77,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/77',
      },
    },
    sha: 'sha-77',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub({ prDetails }),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.should_run, 'false');
  assert.equal(core.outputs.pr_number, '77');
  assert.ok(core.outputs.skip_reason.includes('fork'));
});

test('buildVerifierContext skips when no acceptance criteria found', async () => {
  const core = buildCore();
  // PR body with no acceptance criteria section
  const prBodyNoAcceptance = `## Summary
This PR adds a new feature.

## Tasks
- [x] Implement the feature
- [x] Add documentation
`;
  const prDetails = {
    number: 88,
    title: 'Feature without acceptance',
    body: prBodyNoAcceptance,
    html_url: 'https://example.com/pr/88',
    merge_commit_sha: 'merge-sha-88',
    base: { ref: 'main' },
    head: { sha: 'head-sha-88' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 88,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/88',
      },
    },
    sha: 'sha-88',
  };
  // No linked issues, no acceptance criteria in PR
  const result = await buildVerifierContext({
    github: buildGithubStub({ prDetails, closingIssues: [] }),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.should_run, 'false');
  assert.equal(core.outputs.pr_number, '88');
  assert.ok(core.outputs.skip_reason.includes('No acceptance criteria'));
  assert.equal(core.outputs.acceptance_count, '0');
});

test('buildVerifierContext runs when acceptance criteria exists in linked issue', async () => {
  const core = buildCore();
  // PR body with no acceptance criteria
  const prBodyNoAcceptance = `## Summary
Simple change.
`;
  const prDetails = {
    number: 89,
    title: 'PR with issue acceptance',
    body: prBodyNoAcceptance,
    html_url: 'https://example.com/pr/89',
    merge_commit_sha: 'merge-sha-89',
    base: { ref: 'main' },
    head: { sha: 'head-sha-89' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 89,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/89',
      },
    },
    sha: 'sha-89',
  };
  // Linked issue HAS acceptance criteria AND tasks
  const issueWithAcceptance = {
    number: 100,
    title: 'Issue with acceptance',
    body: `## Tasks
- [ ] Implement feature

## Acceptance Criteria
- [ ] Feature works correctly
- [ ] Tests pass
`,
    state: 'OPEN',
    url: 'https://example.com/issues/100',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub({ prDetails, closingIssues: [issueWithAcceptance] }),
    context,
    core,
  });
  assert.equal(result.shouldRun, true);
  assert.equal(core.outputs.should_run, 'true');
  assert.equal(core.outputs.pr_number, '89');
});

test('buildVerifierContext uses custom ciWorkflows when provided', async () => {
  const core = buildCore();
  const prDetails = {
    number: 90,
    title: 'Custom CI test',
    body: `## Tasks\n- [ ] Setup CI\n\n## Acceptance Criteria\n- [ ] CI passes`,
    html_url: 'https://example.com/pr/90',
    merge_commit_sha: 'merge-sha-90',
    base: { ref: 'main' },
    head: { sha: 'head-sha-90' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 90,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/90',
      },
    },
    sha: 'sha-90',
  };
  // Custom CI workflow
  const customCiWorkflows = '["custom-ci.yml", "another-ci.yml"]';
  const github = buildGithubStub({
    prDetails,
    closingIssues: [],
    runsByWorkflow: {
      'custom-ci.yml': [
        { head_sha: 'merge-sha-90', conclusion: 'success', html_url: 'https://ci/custom' },
      ],
      'another-ci.yml': [
        { head_sha: 'merge-sha-90', conclusion: 'success', html_url: 'https://ci/another' },
      ],
    },
  });
  const result = await buildVerifierContext({
    github,
    context,
    core,
    ciWorkflows: customCiWorkflows,
  });
  const ciResults = JSON.parse(core.outputs.ci_results);
  assert.equal(result.shouldRun, true);
  // Should query custom workflows, not defaults
  assert.equal(ciResults.length, 2);
  assert.equal(ciResults[0].workflow_name, 'custom-ci.yml');
  assert.equal(ciResults[1].workflow_name, 'another-ci.yml');
});

test('buildVerifierContext writes verifier context with linked issues', async () => {
  const core = buildCore();
  const prDetails = {
    number: 321,
    title: 'Add tests',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/321',
    merge_commit_sha: 'merge-sha',
    base: { ref: 'main' },
    head: { sha: 'head-sha' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 321,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/321',
      },
    },
    sha: 'sha-3',
  };
  const github = buildGithubStub({
    prDetails,
    closingIssues: [
      {
        number: 456,
        title: 'Issue 456',
        body: issueBodyOpen,
        state: 'OPEN',
        url: 'https://example.com/issues/456',
      },
      {
        number: 456,
        title: 'Duplicate',
        body: '',
        state: 'OPEN',
        url: 'https://example.com/issues/456',
      },
      {
        number: 789,
        title: 'Issue 789',
        body: issueBodyClosed,
        state: 'CLOSED',
        url: 'https://example.com/issues/789',
      },
    ],
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'merge-sha', conclusion: 'success', html_url: 'https://ci/gate' },
      ],
      'selftest-ci.yml': [
        { head_sha: 'merge-sha', conclusion: 'success', html_url: 'https://ci/selftest' },
      ],
      'pr-11-ci-smoke.yml': [
        { head_sha: 'merge-sha', conclusion: 'success', html_url: 'https://ci/pr11' },
      ],
    },
  });

  const result = await buildVerifierContext({ github, context, core });
  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  const markdown = fs.readFileSync(contextPath, 'utf8');
  const ciResults = JSON.parse(core.outputs.ci_results);

  assert.equal(result.shouldRun, true);
  assert.equal(result.ciResults.length, 3);
  assert.equal(core.outputs.should_run, 'true');
  assert.equal(core.outputs.issue_numbers, JSON.stringify([456, 789]));
  assert.equal(ciResults.length, 3);
  assert.equal(ciResults[0].workflow_name, 'Gate');
  assert.equal(ciResults[0].conclusion, 'success');
  assert.ok(markdown.includes('Pull request #321'));
  assert.ok(markdown.includes('Issue #456'));
  assert.ok(markdown.includes('Issue #789'));
  assert.ok(markdown.includes('## CI Information (Reference Only)'));
  assert.ok(markdown.includes('CI status is irrelevant - focus on evaluating the code changes'));
  assert.ok(markdown.includes('| Workflow | Conclusion | Run |'));
  assert.ok(markdown.includes('| Gate | success | [run](https://ci/gate) |'));
  assert.ok(markdown.includes('| Selftest CI | success | [run](https://ci/selftest) |'));
  assert.ok(markdown.includes('| PR 11 - Minimal invariant CI | success | [run](https://ci/pr11) |'));

  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext writes diff summary for LLM context', async () => {
  const core = buildCore();
  const prDetails = {
    number: 555,
    title: 'Summarize diff',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/555',
    merge_commit_sha: 'merge-sha-555',
    base: { ref: 'main' },
    head: { sha: 'head-sha-555' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 555,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/555',
      },
    },
    sha: 'sha-555',
  };
  const diffText = [
    'diff --git a/src/app.py b/src/app.py',
    'index 111..222 100644',
    '--- a/src/app.py',
    '+++ b/src/app.py',
    '+print("hello")',
    '-print("bye")',
    'diff --git a/docs/readme.md b/docs/readme.md',
    'deleted file mode 100644',
    '--- a/docs/readme.md',
    '+++ /dev/null',
    '-Old content',
  ].join('\n');
  const github = buildGithubStub({
    prDetails,
    closingIssues: [],
    diffText,
  });

  const result = await buildVerifierContext({ github, context, core });
  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  const diffSummaryPath = core.outputs.diff_summary_path;
  const markdown = fs.readFileSync(contextPath, 'utf8');
  const diffSummary = fs.readFileSync(diffSummaryPath, 'utf8');

  assert.equal(result.shouldRun, true);
  assert.ok(diffSummaryPath.endsWith('verifier-diff-summary.md'));
  assert.ok(markdown.includes('## PR Diff Summary'));
  assert.ok(markdown.includes('src/app.py'));
  assert.ok(diffSummary.includes('Files changed: 2'));
  assert.ok(diffSummary.includes('docs/readme.md (deleted)'));

  fs.rmSync(contextPath, { force: true });
  fs.rmSync(diffSummaryPath, { force: true });
});

test('buildVerifierContext queries CI runs for merge and head SHAs', async () => {
  const core = buildCore();
  const prDetails = {
    number: 404,
    title: 'Verify CI results',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/404',
    merge_commit_sha: 'merge-sha-404',
    base: { ref: 'main' },
    head: { sha: 'head-sha-404' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 404,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/404',
      },
    },
    sha: 'context-sha-404',
  };
  const calls = [];
  const github = buildGithubStub({
    prDetails,
    listWorkflowRunsHook: ({ workflow_id: workflowId, head_sha: headSha }) => {
      calls.push({ workflowId, headSha });
      if (headSha === 'merge-sha-404') {
        return { data: { workflow_runs: [] } };
      }
      if (headSha === 'head-sha-404') {
        return {
          data: {
            workflow_runs: [
              {
                head_sha: headSha,
                conclusion: 'success',
                html_url: `https://ci/${workflowId}`,
              },
            ],
          },
        };
      }
      return { data: { workflow_runs: [] } };
    },
  });

  const result = await buildVerifierContext({ github, context, core });
  assert.equal(result.ciResults.length, 3);
  const callMap = new Map();
  for (const call of calls) {
    if (!callMap.has(call.workflowId)) {
      callMap.set(call.workflowId, new Set());
    }
    callMap.get(call.workflowId).add(call.headSha);
  }
  for (const workflowId of ['pr-00-gate.yml', 'selftest-ci.yml', 'pr-11-ci-smoke.yml']) {
    const shas = callMap.get(workflowId);
    assert.ok(shas, `missing calls for ${workflowId}`);
    assert.ok(shas.has('merge-sha-404'));
    assert.ok(shas.has('head-sha-404'));
  }
});

test('buildVerifierContext queries CI runs with merge commit SHA', async () => {
  const core = buildCore();
  const prDetails = {
    number: 222,
    title: 'Merge commit',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/222',
    merge_commit_sha: 'merge-sha-222',
    base: { ref: 'main' },
    head: { sha: 'head-sha-222' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 222,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/222',
      },
    },
    sha: 'sha-222',
  };
  const headShas = [];
  const github = buildGithubStub({
    prDetails,
    listWorkflowRunsHook: ({ head_sha: headSha }) => {
      headShas.push(headSha);
    },
  });

  const result = await buildVerifierContext({ github, context, core });

  assert.equal(result.shouldRun, true);
  assert.ok(headShas.length > 0);
  assert.equal(headShas[0], 'merge-sha-222');
  assert.ok(headShas.includes('merge-sha-222'));

  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext selects CI results for the merge commit SHA', async () => {
  const core = buildCore();
  const prDetails = {
    number: 333,
    title: 'Merge commit selection',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/333',
    merge_commit_sha: 'merge-sha-333',
    base: { ref: 'main' },
    head: { sha: 'head-sha-333' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 333,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/333',
      },
    },
    sha: 'sha-333',
  };
  const headShas = [];
  const github = buildGithubStub({
    prDetails,
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'other-sha', conclusion: 'failure', html_url: 'https://ci/gate-old' },
        { head_sha: 'merge-sha-333', conclusion: 'success', html_url: 'https://ci/gate-merge' },
      ],
      'selftest-ci.yml': [
        { head_sha: 'merge-sha-333', conclusion: 'success', html_url: 'https://ci/selftest-merge' },
      ],
      'pr-11-ci-smoke.yml': [
        { head_sha: 'merge-sha-333', conclusion: 'success', html_url: 'https://ci/pr11-merge' },
      ],
    },
    listWorkflowRunsHook: ({ head_sha: headSha }) => {
      headShas.push(headSha);
    },
  });

  const result = await buildVerifierContext({ github, context, core });

  assert.equal(result.shouldRun, true);
  assert.ok(headShas.length > 0);
  assert.ok(headShas.every((sha) => sha === 'merge-sha-333'));
  assert.deepEqual(result.ciResults, [
    withEmptyJobs({
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'https://ci/gate-merge',
      error_category: '',
      error_message: '',
    }),
    withEmptyJobs({
      workflow_name: 'Selftest CI',
      conclusion: 'success',
      run_url: 'https://ci/selftest-merge',
      error_category: '',
      error_message: '',
    }),
    withEmptyJobs({
      workflow_name: 'PR 11 - Minimal invariant CI',
      conclusion: 'success',
      run_url: 'https://ci/pr11-merge',
      error_category: '',
      error_message: '',
    }),
  ]);

  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext uses API url when html_url is missing', async () => {
  const core = buildCore();
  const prDetails = {
    number: 444,
    title: 'Run URL fallback',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/444',
    merge_commit_sha: 'merge-sha-444',
    base: { ref: 'main' },
    head: { sha: 'head-sha-444' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 444,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/444',
      },
    },
    sha: 'sha-444',
  };
  const github = buildGithubStub({
    prDetails,
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'merge-sha-444', conclusion: 'success', url: 'https://ci/gate-api' },
      ],
    },
  });

  const result = await buildVerifierContext({ github, context, core });
  const ciResults = JSON.parse(core.outputs.ci_results);
  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  const markdown = fs.readFileSync(contextPath, 'utf8');

  assert.equal(result.shouldRun, true);
  assert.equal(ciResults[0].run_url, 'https://ci/gate-api');
  assert.ok(markdown.includes('| Gate | success | [run](https://ci/gate-api) |'));

  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext falls back to head SHA when merge runs are missing', async () => {
  const core = buildCore();
  const prDetails = {
    number: 555,
    title: 'Merge commit fallback',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/555',
    merge_commit_sha: 'merge-sha-555',
    base: { ref: 'main' },
    head: { sha: 'head-sha-555' },
  };
  const context = {
    eventName: 'pull_request',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: {
        merged: true,
        number: 555,
        base: { ref: 'main' },
        html_url: 'https://example.com/pr/555',
      },
    },
    sha: 'sha-555',
  };
  const calls = [];
  const workflowIds = ['pr-00-gate.yml', 'selftest-ci.yml', 'pr-11-ci-smoke.yml'];
  const github = buildGithubStub({
    prDetails,
    listWorkflowRunsHook: ({ workflow_id: workflowId, head_sha: headSha }) => {
      calls.push(`${workflowId}:${headSha}`);
      if (headSha === 'merge-sha-555') {
        return { data: { workflow_runs: [] } };
      }
      if (headSha === 'head-sha-555') {
        return {
          data: {
            workflow_runs: [
              {
                head_sha: 'head-sha-555',
                conclusion: 'success',
                html_url: `https://ci/${workflowId}`,
              },
            ],
          },
        };
      }
      return { data: { workflow_runs: [] } };
    },
  });

  const result = await buildVerifierContext({ github, context, core });

  assert.equal(result.shouldRun, true);
  assert.deepEqual(result.ciResults, [
    withEmptyJobs({
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'https://ci/pr-00-gate.yml',
      error_category: '',
      error_message: '',
    }),
    withEmptyJobs({
      workflow_name: 'Selftest CI',
      conclusion: 'success',
      run_url: 'https://ci/selftest-ci.yml',
      error_category: '',
      error_message: '',
    }),
    withEmptyJobs({
      workflow_name: 'PR 11 - Minimal invariant CI',
      conclusion: 'success',
      run_url: 'https://ci/pr-11-ci-smoke.yml',
      error_category: '',
      error_message: '',
    }),
  ]);
  for (const workflowId of workflowIds) {
    assert.ok(calls.includes(`${workflowId}:merge-sha-555`));
    assert.ok(calls.includes(`${workflowId}:head-sha-555`));
  }

  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext uses merge commit SHA for push events', async () => {
  const core = buildCore();
  const prDetails = {
    number: 444,
    title: 'Push merge commit',
    body: prBodyFixture,
    html_url: 'https://example.com/pr/444',
    merge_commit_sha: 'merge-sha-444',
    base: { ref: 'main' },
    head: { sha: 'head-sha-444' },
  };
  const context = {
    eventName: 'push',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {
      after: 'merge-sha-444',
      repository: { default_branch: 'main' },
    },
    sha: 'merge-sha-444',
  };
  const headShas = [];
  const github = buildGithubStub({
    prDetails,
    prsForSha: [
      {
        number: 444,
        merged_at: '2024-01-01T00:00:00Z',
        merge_commit_sha: 'merge-sha-444',
      },
    ],
    runsByWorkflow: {
      'pr-00-gate.yml': [
        { head_sha: 'merge-sha-444', conclusion: 'success', html_url: 'https://ci/gate-push' },
      ],
      'selftest-ci.yml': [
        {
          head_sha: 'merge-sha-444',
          conclusion: 'success',
          html_url: 'https://ci/selftest-push',
        },
      ],
      'pr-11-ci-smoke.yml': [
        { head_sha: 'merge-sha-444', conclusion: 'success', html_url: 'https://ci/pr11-push' },
      ],
    },
    listWorkflowRunsHook: ({ head_sha: headSha }) => {
      headShas.push(headSha);
    },
  });

  const result = await buildVerifierContext({ github, context, core });

  assert.equal(result.shouldRun, true);
  assert.ok(headShas.length > 0);
  assert.ok(headShas.every((sha) => sha === 'merge-sha-444'));
  assert.deepEqual(result.ciResults, [
    withEmptyJobs({
      workflow_name: 'Gate',
      conclusion: 'success',
      run_url: 'https://ci/gate-push',
      error_category: '',
      error_message: '',
    }),
    withEmptyJobs({
      workflow_name: 'Selftest CI',
      conclusion: 'success',
      run_url: 'https://ci/selftest-push',
      error_category: '',
      error_message: '',
    }),
    withEmptyJobs({
      workflow_name: 'PR 11 - Minimal invariant CI',
      conclusion: 'success',
      run_url: 'https://ci/pr11-push',
      error_category: '',
      error_message: '',
    }),
  ]);

  const contextPath = result.contextPath || path.join(process.cwd(), 'verifier-context.md');
  fs.rmSync(contextPath, { force: true });
});

test('buildVerifierContext skips push events without a commit SHA', async () => {
  const core = buildCore();
  const context = {
    eventName: 'push',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: {},
    sha: '',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub(),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.should_run, 'false');
  assert.ok(core.outputs.skip_reason.includes('Missing commit SHA'));
});

test('buildVerifierContext skips push events with no associated PR', async () => {
  const core = buildCore();
  const context = {
    eventName: 'push',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: { after: 'sha-9' },
    sha: 'sha-9',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub({ prsForSha: [] }),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.should_run, 'false');
  assert.ok(core.outputs.skip_reason.includes('No pull request associated'));
});

test('buildVerifierContext skips push events when PR lookup fails', async () => {
  const core = buildCore();
  const context = {
    eventName: 'push',
    repo: { owner: 'octo', repo: 'workflows' },
    payload: { after: 'sha-10' },
    sha: 'sha-10',
  };
  const result = await buildVerifierContext({
    github: buildGithubStub({ listError: new Error('boom') }),
    context,
    core,
  });
  assert.equal(result.shouldRun, false);
  assert.equal(core.outputs.should_run, 'false');
  assert.ok(core.outputs.skip_reason.includes('Unable to resolve pull request'));
  assert.equal(core.warnings.length, 1);
});

test('formatDiffForContext truncates long diffs', () => {
  const diff = 'a'.repeat(50);
  const result = formatDiffForContext(diff, 10);
  assert.ok(result.startsWith('a'.repeat(10)));
  assert.ok(result.includes('diff truncated after 10 characters'));
});

test('formatDiffForContext returns placeholder for empty diff', () => {
  assert.equal(formatDiffForContext('', 100), '_Diff unavailable or empty._');
});

test('isValidSha validates hex shas', () => {
  assert.ok(isValidSha('a1b2c3d'));
  assert.ok(isValidSha('A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6E7F8A9B0'));
  assert.equal(isValidSha('not-a-sha'), false);
});

test('fetchLocalGitDiff skips invalid shas', () => {
  let called = false;
  const execFile = () => {
    called = true;
    return Buffer.from('');
  };
  const result = fetchLocalGitDiff({
    baseSha: 'not-a-sha',
    headSha: 'deadbeef',
    execFile,
  });
  assert.equal(result, '');
  assert.equal(called, false);
});

test('fetchLocalGitDiff returns diff output when exec succeeds', () => {
  const execFile = () => Buffer.from('diff --git a/x b/x\n+hello\n');
  const result = fetchLocalGitDiff({
    baseSha: 'a1b2c3d',
    headSha: 'deadbeef',
    execFile,
  });
  assert.ok(result.includes('diff --git'));
  assert.ok(result.includes('+hello'));
});

// === Chain depth extraction tests ===

test('buildVerifierContext extracts chain_depth from issue body marker', async () => {
  const issueBody = '<!-- follow-up-depth: 2 -->\n## Scope\nFix bugs\n## Tasks\n- [ ] Fix it\n## Acceptance Criteria\n- [ ] It works';
  const prBody = prBodyFixture;
  const github = buildGithubStub({
    prDetails: {
      number: 100,
      html_url: 'https://github.com/example/test/pull/100',
      title: 'follow-up fix',
      body: prBody,
      base: { ref: 'main', sha: 'base123' },
      head: { sha: 'head456' },
      merge_commit_sha: 'merge789',
    },
    closingIssues: [
      {
        number: 50,
        title: 'follow-up issue',
        body: issueBody,
        state: 'OPEN',
        url: 'https://github.com/example/test/issues/50',
        labels: { nodes: [] },
      },
    ],
  });
  const core = buildCore();
  const ctx = {
    eventName: 'pull_request',
    repo: { owner: 'example', repo: 'test' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: { merged: true, number: 100, base: { ref: 'main' }, html_url: 'https://github.com/example/test/pull/100' },
    },
    sha: 'merge789',
  };
  await buildVerifierContext({ github, context: ctx, core });
  assert.equal(core.outputs.chain_depth, '2');
});

test('buildVerifierContext outputs chain_depth 0 when no marker present', async () => {
  const github = buildGithubStub({
    prDetails: {
      number: 101,
      html_url: 'https://github.com/example/test/pull/101',
      title: 'regular PR',
      body: prBodyFixture,
      base: { ref: 'main', sha: 'base123' },
      head: { sha: 'head456' },
      merge_commit_sha: 'merge789',
    },
    closingIssues: [
      {
        number: 51,
        title: 'feature request',
        body: issueBodyOpen,
        state: 'OPEN',
        url: 'https://github.com/example/test/issues/51',
        labels: { nodes: [] },
      },
    ],
  });
  const core = buildCore();
  const ctx = {
    eventName: 'pull_request',
    repo: { owner: 'example', repo: 'test' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: { merged: true, number: 101, base: { ref: 'main' }, html_url: 'https://github.com/example/test/pull/101' },
    },
    sha: 'merge789',
  };
  await buildVerifierContext({ github, context: ctx, core });
  assert.equal(core.outputs.chain_depth, '0');
});

test('buildVerifierContext detects follow-up label as depth 1', async () => {
  const github = buildGithubStub({
    prDetails: {
      number: 102,
      html_url: 'https://github.com/example/test/pull/102',
      title: 'follow-up fix',
      body: prBodyFixture,
      base: { ref: 'main', sha: 'base123' },
      head: { sha: 'head456' },
      merge_commit_sha: 'merge789',
    },
    closingIssues: [
      {
        number: 52,
        title: 'follow-up from verifier',
        body: issueBodyOpen,
        state: 'OPEN',
        url: 'https://github.com/example/test/issues/52',
        labels: { nodes: [{ name: 'follow-up' }] },
      },
    ],
  });
  const core = buildCore();
  const ctx = {
    eventName: 'pull_request',
    repo: { owner: 'example', repo: 'test' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: { merged: true, number: 102, base: { ref: 'main' }, html_url: 'https://github.com/example/test/pull/102' },
    },
    sha: 'merge789',
  };
  await buildVerifierContext({ github, context: ctx, core });
  assert.equal(core.outputs.chain_depth, '1');
});

test('buildVerifierContext includes chain depth in context markdown', async () => {
  const issueBody = '<!-- follow-up-depth: 3 -->\n' + issueBodyOpen;
  const github = buildGithubStub({
    prDetails: {
      number: 103,
      html_url: 'https://github.com/example/test/pull/103',
      title: 'iteration 3',
      body: prBodyFixture,
      base: { ref: 'main', sha: 'base123' },
      head: { sha: 'head456' },
      merge_commit_sha: 'merge789',
    },
    closingIssues: [
      {
        number: 53,
        title: 'iteration issue',
        body: issueBody,
        state: 'OPEN',
        url: 'https://github.com/example/test/issues/53',
        labels: { nodes: [] },
      },
    ],
  });
  const core = buildCore();
  const ctx = {
    eventName: 'pull_request',
    repo: { owner: 'example', repo: 'test' },
    payload: {
      repository: { default_branch: 'main' },
      pull_request: { merged: true, number: 103, base: { ref: 'main' }, html_url: 'https://github.com/example/test/pull/103' },
    },
    sha: 'merge789',
  };
  const result = await buildVerifierContext({ github, context: ctx, core });
  assert.ok(result.markdown.includes('Chain depth: 3'));
  assert.equal(core.outputs.chain_depth, '3');
});
