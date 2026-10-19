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
        listForRepo: async () => ({ data: [] }),
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
        get: async () => ({ data: { state: 'open', body: `Occurrences: 1\nLast seen: ${staleTime}` } }),
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
          listForRepo: async () => ({ data: [{ number: 21 }] }),
          get: async () => ({
            data: {
              number: 21,
              state: 'open',
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


// Execute the authored workflow script, not a parallel test-only coordinator.
function trackerWorkflowScript() {
  const workflow = fs.readFileSync(path.join(__dirname, '../../workflows/maint-46-post-ci.yml'), 'utf8');
  const step = workflow.split('      - name: Track completed Gate and snapshot\n')[1];
  assert.ok(step, 'tracker step must remain wired');
  const block = step.split('          script: |\n')[1].split('      - name:')[0];
  assert.match(workflow, /path: artifacts\/ci_failures_snapshot.json/);
  assert.match(workflow, /failure-tracker:[\s\S]*issues: write/);
  return block.split('\n').filter(line => line.trim()).map(line => {
    assert.ok(line.startsWith('            '));
    return line.slice(12);
  }).join('\n');
}

function trackerReplayHarness() {
  const issues = [];
  const comments = [];
  const writes = [];
  const calls = [];
  const run = {
    id: 100, run_attempt: 1, workflow_id: 44, name: 'Gate', event: 'pull_request',
    status: 'completed', conclusion: 'failure', head_sha: 'a'.repeat(40),
    path: '.github/workflows/pr-00-gate.yml', html_url: 'https://example.test/runs/100',
    repository: { id: 10 }, head_repository: { id: 10 },
    pull_requests: [{ number: 5, head: { sha: 'b'.repeat(40) } }],
  };
  const pr = { number: 5, state: 'open', head: { sha: 'b'.repeat(40), repo: { id: 10 } } };
  const state = {
    jobs: [{ id: 1, name: 'summary', status: 'completed', conclusion: 'success' },
      { id: 2, name: 'Python CI', status: 'completed', conclusion: 'failure' },
      { id: 3, name: 'optional', status: 'completed', conclusion: 'skipped' }],
    newerRuns: [],
  };
  const github = { rest: {
    actions: {
      getWorkflowRun: async () => ({ data: structuredClone(state.latestRun || run) }),
      listWorkflowRuns: async () => ({ data: { workflow_runs: [run, ...state.newerRuns] } }),
      listJobsForWorkflowRunAttempt: async params => {
        calls.push(params);
        assert.equal(params.run_id, run.id);
        assert.equal(params.attempt_number, run.run_attempt);
        return { data: { jobs: state.jobs } };
      },
    },
    pulls: { get: async () => ({ data: pr }) },
    search: { issuesAndPullRequests: async ({ q }) => {
      const tag = q.match(/tracked-pr: (\d+)/);
      return { data: { items: state.searchItems || issues.filter(item => item.state === 'open'
        && (!tag || item.body.includes(`<!-- tracked-pr: ${tag[1]} -->`))) } };
    } },
    issues: {
      listForRepo: async () => ({ data: issues.filter(item => item.state === 'open') }),
      get: async ({ issue_number }) => ({ data: issues.find(item => item.number === issue_number) }),
      create: async input => {
        writes.push(['create', input]);
        const issue = { ...input, number: 200 + issues.length, state: 'open',
          created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
          html_url: `https://example.test/issues/${200 + issues.length}` };
        issues.push(issue);
        return { data: issue };
      },
      update: async input => {
        writes.push(['update', input]);
        Object.assign(issues.find(item => item.number === input.issue_number), input);
      },
      createComment: async input => { comments.push(input); writes.push(['comment', input]); },
    },
  } };
  github.paginate = async (method, params) => {
    const result = await method(params);
    return result.data.workflow_runs || result.data.jobs || result.data.items || result.data;
  };
  const context = { repo: { owner: 'octo', repo: 'demo' },
    payload: { repository: { id: 10 }, workflow_run: structuredClone(run) } };
  const core = createCore();
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const execute = new AsyncFunction('require', 'github', 'context', 'core', 'process', trackerWorkflowScript());
  return { run, pr, state, issues, comments, writes, calls, context, core,
    async replay() {
      context.payload.workflow_run = structuredClone(run);
      await execute(modulePath => {
        assert.equal(modulePath, './.github/scripts/maint-post-ci.js');
        return require('../maint-post-ci');
      }, github, context, core, process);
    },
  };
}

async function inTrackerReplay(fn) {
  const originalCwd = process.cwd();
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'gate-tracker-replay-'));
  const names = ['PR_NUMBER', 'RUN_URL', 'STACK_TOKENS_ENABLED', 'NEW_ISSUE_COOLDOWN_HOURS',
    'COOLDOWN_SCOPE', 'DISABLE_FAILURE_ISSUES', 'AUTO_HEAL_INACTIVITY_HOURS', 'RATE_LIMIT_MINUTES'];
  const previous = Object.fromEntries(names.map(name => [name, process.env[name]]));
  process.chdir(temp);
  Object.assign(process.env, { STACK_TOKENS_ENABLED: 'false', NEW_ISSUE_COOLDOWN_HOURS: '12',
    COOLDOWN_SCOPE: 'global', DISABLE_FAILURE_ISSUES: 'false', AUTO_HEAL_INACTIVITY_HOURS: '24', RATE_LIMIT_MINUTES: '15' });
  try { await fn(trackerReplayHarness()); }
  finally {
    process.chdir(originalCwd);
    for (const name of names) {
      if (previous[name] === undefined) delete process.env[name];
      else process.env[name] = previous[name];
    }
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

function readTrackerSnapshot() {
  return JSON.parse(fs.readFileSync('artifacts/ci_failures_snapshot.json', 'utf8'));
}

test('authored Gate tracker replays upstream failure, recurrence, duplicate and recovery snapshots', async () => {
  await inTrackerReplay(async h => {
    await h.replay(); // Successful summary must not suppress the failed Python leg.
    assert.equal(h.issues.length, 1);
    assert.match(h.issues[0].body, /Python CI \(failure\)/);
    assert.doesNotMatch(h.issues[0].body, /optional \(skipped\)/);
    const failed = readTrackerSnapshot();
    assert.deepEqual(failed.monitored_run, { id: 100, attempt: 1, head_sha: h.run.head_sha });
    assert.equal(failed.issues[0].occurrences, 1);
    h.issues[0].body += '\nOwner investigation notes must survive recurrence.';
    h.run.id = 101;
    h.run.html_url = 'https://example.test/runs/101';
    await h.replay();
    assert.equal(h.issues.length, 1);
    assert.equal(readTrackerSnapshot().issues[0].occurrences, 2);
    assert.match(h.issues[0].body, /Owner investigation notes must survive/);
    assert.equal(h.comments.length, 1);
    await h.replay();
    assert.equal(readTrackerSnapshot().issues[0].occurrences, 2);
    h.run.id = 102;
    h.state.jobs[1].name = 'different failure'; // cooldown appends, does not create a duplicate
    await h.replay();
    assert.equal(h.issues.length, 1);
    assert.equal(readTrackerSnapshot().issues[0].occurrences, 3);
    assert.equal(h.comments.length, 1); // rate-limited without losing occurrence metadata
    h.run.id = 103;
    h.run.conclusion = 'success';
    h.state.jobs[1].conclusion = 'success';
    await h.replay();
    assert.equal(h.issues[0].state, 'closed');
    const recovered = readTrackerSnapshot();
    assert.equal(recovered.monitored_run.id, 103);
    assert.deepEqual(recovered.issues, []);
    assert.ok(h.comments.some(item => item.body.includes('Resolution:')));
    if (process.env.TRACKER_REPLAY_OUTPUT) {
      fs.mkdirSync(process.env.TRACKER_REPLAY_OUTPUT, { recursive: true });
      fs.writeFileSync(path.join(process.env.TRACKER_REPLAY_OUTPUT, 'failure.json'), JSON.stringify(failed, null, 2));
      fs.writeFileSync(path.join(process.env.TRACKER_REPLAY_OUTPUT, 'recovery.json'), JSON.stringify(recovered, null, 2));
      fs.writeFileSync(path.join(process.env.TRACKER_REPLAY_OUTPUT, 'receipt.json'), JSON.stringify({
        synthetic: true, workflow_head: process.env.GITHUB_SHA || null,
        hosted_run_url: process.env.GITHUB_RUN_ID ? `https://github.com/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}` : null,
        writes: h.writes, job_attempt_reads: h.calls,
      }, null, 2));
    }
  });
});

for (const [name, mutate] of [
  ['fork identity', h => { h.run.head_repository.id = 11; }],
  ['missing identity', h => { delete h.context.payload.repository; }],
  ['superseded attempt', h => { h.state.latestRun = { ...h.run, run_attempt: 2 }; }],
  ['current head drift', h => { h.pr.head.sha = 'c'.repeat(40); }],
  ['newer Gate run', h => { h.state.newerRuns.push({ ...h.run, id: 999 }); }],
  ['new merge SHA on the same PR head', h => { h.state.newerRuns.push({ ...h.run, id: 999, head_sha: 'd'.repeat(40) }); }],
  ['non-Gate workflow', h => { h.run.path = '.github/workflows/other.yml'; }],
  ['incomplete implementation job', h => { h.state.jobs[1].status = 'in_progress'; }],
]) {
  test(`authored Gate tracker refuses ${name} before writing`, async () => {
    await inTrackerReplay(async h => {
      mutate(h);
      await h.replay();
      assert.deepEqual(h.writes, []);
      assert.equal(fs.existsSync('artifacts/ci_failures_snapshot.json'), false);
    });
  });
}

test('authored Gate tracker retains other PRs in a cooldown aggregate on recovery', async () => {
  await inTrackerReplay(async h => {
    await h.replay();
    h.issues[0].body += '\n<!-- tracked-pr: 6 -->';
    const stale = new Date(Date.now() - 48 * 3_600_000).toISOString();
    h.issues[0].body = h.issues[0].body.replace(/^Last seen: .+$/m, `Last seen: ${stale}`);
    h.run.id = 101;
    h.run.conclusion = 'success';
    h.state.jobs[1].conclusion = 'success';
    await h.replay();
    assert.equal(h.issues[0].state, 'open');
    assert.doesNotMatch(h.issues[0].body, /<!-- tracked-pr: 5 -->/);
    assert.match(h.issues[0].body, /<!-- tracked-pr: 6 -->/);
  });
});


test('authored Gate tracker scans failed jobs beyond the first page', async () => {
  await inTrackerReplay(async h => {
    h.state.jobs = Array.from({ length: 100 }, (_, index) => ({
      id: index + 1, name: `passing-${index}`, status: 'completed', conclusion: 'success',
    }));
    h.state.jobs.push({ id: 101, name: 'page-two-failure', status: 'completed', conclusion: 'failure' });
    await h.replay();
    assert.match(h.issues[0].body, /page-two-failure/);
    assert.equal(h.calls[0].per_page, 100);
  });
});

test('authored Gate tracker snapshots an issue-write failure without claiming recovery', async () => {
  await inTrackerReplay(async h => {
    await h.replay();
    h.run.id = 101;
    // A failed update must not skip the same run-bound snapshot.
    const original = h.issues[0];
    Object.defineProperty(original, 'body', { get() { return 'Occurrences: 1'; }, set() { throw new Error('write denied'); } });
    await assert.rejects(h.replay(), /write denied/);
    const snapshot = readTrackerSnapshot();
    assert.equal(snapshot.monitored_run.id, 101);
    assert.equal(snapshot.issues.length, 1);
    assert.equal(snapshot.issues[0].occurrences, 1);
  });
});

test('authored Gate tracker does not heal cancelled outcomes', async () => {
  await inTrackerReplay(async h => {
    await h.replay();
    h.run.id = 101;
    h.run.conclusion = 'cancelled';
    h.state.jobs[1].conclusion = 'cancelled';
    const before = h.writes.length;
    await h.replay();
    assert.equal(h.writes.length, before);
    assert.equal(readTrackerSnapshot().issues.length, 1);
  });
});


test('snapshot uses consistent issue list despite delayed search writes', async () => {
  await inTrackerReplay(async h => {
    h.state.searchItems = [];
    await h.replay();
    assert.equal(readTrackerSnapshot().issues.length, 1);
    const closed = h.issues[0];
    closed.state = 'closed';
    // Even an older list page cannot turn a closed issue into an open failure.
    h.state.searchItems = [closed];
    const github = { rest: { issues: {
      listForRepo: async () => ({ data: [closed, { number: 999, pull_request: {} }] }),
      get: async () => ({ data: closed }),
    } } };
    await snapshotFailureIssues({ github, context: h.context, core: h.core });
    assert.deepEqual(readTrackerSnapshot().issues, []);
  });
});

for (const state of ['closed', 'open', 'unavailable']) {
  test(`inactivity retires only confirmed closed PR tags: ${state}`, async () => {
    await inTrackerReplay(async h => {
      await h.replay();
      const issue = h.issues[0];
      const stale = new Date(Date.now() - 48 * 3600_000).toISOString();
      issue.body = issue.body.replace(/^Last seen: .+$/m, `Last seen: ${stale}`);
      const github = { rest: {
        search: { issuesAndPullRequests: async () => ({ data: { items: [issue] } }) },
        pulls: { get: async () => {
          if (state === 'unavailable') throw new Error('unavailable');
          return { data: { state } };
        } },
        issues: {
          get: async () => ({ data: issue }),
          update: async payload => Object.assign(issue, payload),
          createComment: async () => {},
        },
      } };
      await autoHealFailureIssues({ github, context: h.context, core: h.core });
      assert.equal(issue.state, state === 'closed' ? 'closed' : 'open');
      assert.equal(/<!-- tracked-pr: 5 -->/.test(issue.body), state !== 'closed');
    });
  });
}
