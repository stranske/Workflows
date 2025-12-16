const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  discoverWorkflowRuns,
  propagateGateCommitStatus,
  resolveAutofixContext,
  inspectFailingJobs,
  evaluateAutofixRerunGuard,
  ensureAutofixComment,
  updateFailureTracker,
  resolveFailureIssuesForRecoveredPR,
  autoHealFailureIssues,
  snapshotFailureIssues,
  applyCiFailureLabel,
  removeCiFailureLabel,
} = require('../maint-post-ci');

function createCore() {
  const outputs = {};
  const summary = {
    items: [],
    addHeading(text) {
      this.items.push(['heading', text]);
      return this;
    },
    addRaw(text) {
      this.items.push(['raw', text]);
      return this;
    },
    async write() {
      return undefined;
    },
  };
  return {
    outputs,
    summary,
    setOutput(key, value) {
      outputs[key] = value;
    },
    notice() {},
    info() {},
    warning() {},
  };
}

test('discoverWorkflowRuns collects gate run metadata', async () => {
  const core = createCore();
  const context = {
    repo: { owner: 'octo', repo: 'demo' },
    payload: {
      workflow_run: {
        head_sha: 'abc123',
        pull_requests: [{ head: { sha: 'abc123' } }],
      },
    },
    sha: 'abc123',
  };
  const jobList = [{ name: 'job', conclusion: 'success', status: 'completed', html_url: 'job-url' }];
  const github = {
    rest: {
      actions: {
        listWorkflowRuns: async () => ({
          data: {
            workflow_runs: [
              { id: 42, head_sha: 'abc123', run_attempt: 1, conclusion: 'success', status: 'completed', html_url: 'run-url' },
            ],
          },
        }),
        listJobsForWorkflowRun: async () => jobList,
      },
    },
    paginate: async (fn, params) => {
      assert.equal(fn, github.rest.actions.listJobsForWorkflowRun);
      assert.equal(params.run_id, 42);
      return jobList;
    },
  };
  delete process.env.WORKFLOW_TARGETS_JSON;
  await discoverWorkflowRuns({ github, context, core });
  assert.equal(core.outputs.head_sha, 'abc123');
  assert.equal(core.outputs.ci_run_id, '42');
  const collected = JSON.parse(core.outputs.runs);
  assert.equal(collected.length, 1);
  assert.equal(collected[0].jobs.length, 1);
});

test('propagateGateCommitStatus posts commit status', async () => {
  const core = createCore();
  const context = { repo: { owner: 'octo', repo: 'demo' }, payload: { workflow_run: { id: 77 } } };
  let called = null;
  const github = {
    rest: {
      repos: {
        createCommitStatus: async payload => {
          called = payload;
        },
      },
    },
  };
  process.env.HEAD_SHA = 'abc123';
  process.env.RUN_CONCLUSION = 'success';
  process.env.RUN_STATUS = 'completed';
  process.env.GATE_RUN_URL = 'https://example/run';
  await propagateGateCommitStatus({ github, context, core });
  assert.deepEqual(called, {
    owner: 'octo',
    repo: 'demo',
    sha: 'abc123',
    state: 'success',
    context: 'Gate / gate',
    description: 'Gate workflow succeeded.',
    target_url: 'https://example/run',
  });
});

test('resolveAutofixContext identifies PR and eligible files', async () => {
  const core = createCore();
  const context = {
    repo: { owner: 'octo', repo: 'demo' },
    payload: {
      workflow_run: {
        pull_requests: [{ number: 15, head: { ref: 'feature', sha: 'abc123' }, draft: false }],
        head_branch: 'feature',
        head_sha: 'abc123',
        id: 55,
        event: 'pull_request',
        head_repository: {},
        conclusion: 'failure',
        actor: { login: 'developer' },
      },
    },
  };
  const files = [
    { filename: 'src/app.py', changes: 10 },
    { filename: 'docs/readme.md', changes: 2 },
  ];
  const github = {
    rest: {
      pulls: {
        get: async () => ({
          data: {
            number: 15,
            head: { ref: 'feature', sha: 'abc123', repo: { full_name: 'octo/demo' } },
            labels: [{ name: 'autofix:clean' }],
            title: 'Update app',
            draft: false,
          },
        }),
        list: async () => ({ data: [] }),
        listFiles: async () => ({ data: files }),
      },
      repos: {
        getCommit: async () => ({ data: { commit: { message: 'Update app' } } }),
      },
      issues: {
        listComments: async () => ({ data: [] }),
      },
    },
    paginate: async (fn, params) => {
      if (fn === github.rest.pulls?.list) {
        return [];
      }
      if (fn === github.rest.pulls?.listFiles) {
        return files;
      }
      return [];
    },
  };
  process.env.AUTOFIX_OPT_IN_LABEL = 'autofix:clean';
  process.env.AUTOFIX_PATCH_LABEL = 'autofix:patch';
  process.env.AUTOFIX_MAX_FILES = '40';
  process.env.AUTOFIX_MAX_CHANGES = '800';
  await resolveAutofixContext({ github, context, core });
  assert.equal(core.outputs.found, 'true');
  assert.equal(core.outputs.pr, '15');
  assert.equal(core.outputs.small_eligible, 'true');
  assert.equal(core.outputs.file_count, '2');
});

test('inspectFailingJobs classifies trivial failures', async () => {
  const core = createCore();
  const context = {
    repo: { owner: 'octo', repo: 'demo' },
    payload: { workflow_run: { id: 9, conclusion: 'failure' } },
  };
  const jobs = [
    { name: 'lint check', conclusion: 'failure' },
    { name: 'lint extras', conclusion: 'failure' },
  ];
  const github = {
    rest: {
      actions: {
        listJobsForWorkflowRun: async () => ({ data: { jobs } }),
      },
    },
    paginate: async () => jobs,
  };
  process.env.AUTOFIX_TRIVIAL_KEYWORDS = 'lint';
  await inspectFailingJobs({ github, context, core });
  assert.equal(core.outputs.trivial, 'true');
  assert.equal(core.outputs.count, '2');
});

test('evaluateAutofixRerunGuard detects duplicate patches', async () => {
  const core = createCore();
  const context = { repo: { owner: 'octo', repo: 'demo' } };
  const comments = [
    { body: '<!-- autofix-meta: head=abc123 --> already done' },
  ];
  const github = {
    rest: {
      issues: {
        listComments: async () => ({ data: comments }),
      },
    },
    paginate: async () => comments,
  };
  process.env.PR_NUMBER = '10';
  process.env.HEAD_SHA = 'abc123';
  process.env.SAME_REPO = 'false';
  process.env.HAS_PATCH_LABEL = 'true';
  await evaluateAutofixRerunGuard({ github, context, core });
  assert.equal(core.outputs.skip, 'true');
  assert.equal(core.outputs.reason, 'duplicate-patch');
});

test('ensureAutofixComment posts comment with rerun link', async () => {
  const core = createCore();
  const context = { repo: { owner: 'octo', repo: 'demo' }, payload: { workflow_run: { id: 77 } } };
  let created = null;
  const github = {
    rest: {
      issues: {
        listComments: async () => ({ data: [] }),
        createComment: async payload => {
          created = payload;
        },
      },
    },
    paginate: async (fn, params) => {
      assert.equal(fn, github.rest.issues.listComments);
      assert.equal(params.issue_number, 42);
      return [];
    },
  };

  process.env.PR_NUMBER = '42';
  process.env.HEAD_SHA = 'abc123def4567890';
  process.env.FILE_LIST = 'src/app.py\ntests/test_app.py';
  process.env.GATE_RUN_URL = 'https://example.test/run';
  process.env.GATE_RERUN_TRIGGERED = 'true';

  await ensureAutofixComment({ github, context, core });

  assert.ok(created, 'Expected comment to be created');
  assert.equal(created.owner, 'octo');
  assert.equal(created.repo, 'demo');
  assert.equal(created.issue_number, 42);
  assert.match(created.body, /Autofix applied/);
  assert.match(created.body, /src\/app.py/);
  assert.match(created.body, /Gate rerun: \[View Gate run\]\(https:\/\/example.test\/run\)/);

  delete process.env.PR_NUMBER;
  delete process.env.HEAD_SHA;
  delete process.env.FILE_LIST;
  delete process.env.GATE_RUN_URL;
  delete process.env.GATE_RERUN_TRIGGERED;
});

test('ensureAutofixComment skips when marker present', async () => {
  const core = createCore();
  const context = { repo: { owner: 'octo', repo: 'demo' }, payload: { workflow_run: { id: 88 } } };
  const comments = [
    { body: '<!-- autofix-meta: head=abc123def4567890 --> existing' },
  ];
  const github = {
    rest: {
      issues: {
        listComments: async () => ({ data: comments }),
        createComment: async () => {
          assert.fail('createComment should not be called when marker exists');
        },
      },
    },
    paginate: async () => comments,
  };

  process.env.PR_NUMBER = '99';
  process.env.HEAD_SHA = 'abc123def4567890';

  await ensureAutofixComment({ github, context, core });

  delete process.env.PR_NUMBER;
  delete process.env.HEAD_SHA;
});

test('updateFailureTracker opens issue when cooldown passes', async () => {
  const core = createCore();
  const context = {
    repo: { owner: 'octo', repo: 'demo' },
    payload: { workflow_run: { id: 30, name: 'Gate', html_url: 'run-url' } },
  };
  let createdIssue = null;
  const github = {
    rest: {
      actions: {
        listJobsForWorkflowRun: async () => ({ data: { jobs: [{ id: 1, name: 'tests', conclusion: 'failure', status: 'completed' }] } }),
        getEnvironmentVariable: async () => { throw new Error('no env'); },
        updateEnvironmentVariable: async () => {},
        downloadJobLogsForWorkflowRun: async () => ({ data: Buffer.from('') }),
      },
      issues: {
        create: async payload => {
          createdIssue = payload;
          return { data: { number: 100 } };
        },
      },
    },
  };
  process.env.PR_NUMBER = '5';
  process.env.NEW_ISSUE_COOLDOWN_HOURS = '0';
  process.env.COOLDOWN_RETRY_MS = '0';
  process.env.STACK_TOKENS_ENABLED = 'false';
  await updateFailureTracker({ github, context, core });
  assert.ok(createdIssue);
  assert.equal(createdIssue.owner, 'octo');
  assert.equal(createdIssue.repo, 'demo');
});

test('resolveFailureIssuesForRecoveredPR closes matching issues', async () => {
  const core = createCore();
  const now = new Date().toISOString();
  const context = { repo: { owner: 'octo', repo: 'demo' }, payload: { workflow_run: { html_url: 'run-url' } } };
  let updated = 0;
  let commented = 0;
  const github = {
    rest: {
      search: {
        issuesAndPullRequests: async () => ({ data: { items: [{ number: 7 }] } }),
      },
      issues: {
        get: async () => ({ data: { body: 'Occurrences: 1\nLast seen: 2024-01-01T00:00:00Z', html_url: 'issue-url', number: 7 } }),
        createComment: async () => { commented += 1; },
        update: async () => { updated += 1; },
      },
    },
  };
  process.env.PR_NUMBER = '5';
  process.env.RUN_URL = 'run-url';
  await resolveFailureIssuesForRecoveredPR({ github, context, core });
  assert.equal(commented, 1);
  assert.equal(updated, 1);
});

test('autoHealFailureIssues closes stale entries and writes summary', async () => {
  const core = createCore();
  const context = { repo: { owner: 'octo', repo: 'demo' } };
  let closed = 0;
  const staleTime = new Date(Date.now() - 48 * 3600_000).toISOString();
  const github = {
    rest: {
      search: {
        issuesAndPullRequests: async () => ({ data: { items: [{ number: 11 }] } }),
      },
      issues: {
        get: async () => ({ data: { body: `Occurrences: 1\nLast seen: ${staleTime}` } }),
        createComment: async () => {},
        update: async () => { closed += 1; },
      },
    },
  };
  process.env.AUTO_HEAL_INACTIVITY_HOURS = '24';
  await autoHealFailureIssues({ github, context, core });
  assert.equal(closed, 1);
  assert.ok(core.summary.items.length > 0);
});

test('snapshotFailureIssues writes artifact snapshot', async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint-post-ci-'));
  const originalCwd = process.cwd();
  process.chdir(tmpDir);
  try {
    const context = { repo: { owner: 'octo', repo: 'demo' } };
    const github = {
      rest: {
        search: {
          issuesAndPullRequests: async () => ({ data: { items: [{ number: 21 }] } }),
        },
        issues: {
          get: async () => ({
            data: {
              number: 21,
              title: 'Failure',
              body: 'Occurrences: 1\nLast seen: 2024-01-01T00:00:00Z',
              html_url: 'issue-url',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-02T00:00:00Z',
            },
          }),
        },
      },
    };
    const core = createCore();
    await snapshotFailureIssues({ github, context, core });
    const snapshotPath = path.join('artifacts', 'ci_failures_snapshot.json');
    assert.ok(fs.existsSync(snapshotPath));
    const data = JSON.parse(fs.readFileSync(snapshotPath, 'utf8'));
    assert.equal(data.issues.length, 1);
  } finally {
    process.chdir(originalCwd);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('applyCiFailureLabel adds label and ignores duplicates', async () => {
  const core = createCore();
  const context = { repo: { owner: 'octo', repo: 'demo' } };
  let callCount = 0;
  const github = {
    rest: {
      issues: {
        addLabels: async payload => {
          callCount += 1;
          if (callCount > 1) {
            const error = new Error('duplicate');
            error.status = 422;
            throw error;
          }
          assert.equal(payload.issue_number, 99);
        },
      },
    },
  };

  await applyCiFailureLabel({ github, context, core, prNumber: '99' });
  await applyCiFailureLabel({ github, context, core, prNumber: '99' });
  assert.equal(callCount, 2);
});

test('removeCiFailureLabel removes label and ignores missing labels', async () => {
  const core = createCore();
  const context = { repo: { owner: 'octo', repo: 'demo' } };
  let callCount = 0;
  const github = {
    rest: {
      issues: {
        removeLabel: async payload => {
          callCount += 1;
          if (callCount > 1) {
            const error = new Error('missing');
            error.status = 404;
            throw error;
          }
          assert.equal(payload.issue_number, 99);
        },
      },
    },
  };

  await removeCiFailureLabel({ github, context, core, prNumber: '99' });
  await removeCiFailureLabel({ github, context, core, prNumber: '99' });
  assert.equal(callCount, 2);
});
