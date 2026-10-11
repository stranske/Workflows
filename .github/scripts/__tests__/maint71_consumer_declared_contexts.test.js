'use strict';

// A generated delivery merged into stranske/Orchestrator (#530) while that
// repository's own verify.py had failed on the exact head, because Maint 71
// gated only on 'Gate / gate' and Orchestrator has no branch protection. These
// tests pin the consumer-declared contexts that close that hole, using the
// check runs #530 actually had, and the absence rule that keeps a declared
// check which never started from holding a delivery forever.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const {
  CONSUMER_REQUIRED_CONTEXTS_PATH,
  classifySyncPrChecks,
  describeConsumerDeclaredContexts,
  parseConsumerRequiredContexts,
} = require('../sync_pr_merge_contract.js');
const {
  enforceGeneratedDeliveryRequiredContexts,
  legacyStatusAsCheck,
  readConsumerDeclaredContexts,
} = require('../maint71_merge_sync_prs.js');

const fixture = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'fixtures', 'maint71-orchestrator-530-checks.json'),
  'utf8',
));

// Maint 71 merges check runs with legacy statuses the same way:
// a status named like an existing check run is dropped.
function checksAsMaint71ReadsThem({ checkRuns, statuses }) {
  const names = new Set(checkRuns.map((check) => check.name));
  return [
    ...checkRuns,
    ...statuses.map(legacyStatusAsCheck).filter((status) => !names.has(status.name)),
  ];
}

const VERIFY = 'verify.py (real pytest counts + selftests + capability gates)';
const EXEC_MIRROR = 'verify.py in the flat exec-mirror shape (the tree a sync ships)';
const COVERAGE = 'combined coverage (pytest + selftests, the honest number)';
const ORCHESTRATOR_DECLARED = [VERIFY, EXEC_MIRROR, COVERAGE];

const actionsRun = ({ name, status = 'completed', conclusion = 'success', started_at }) => ({
  name,
  status,
  conclusion: status === 'completed' ? conclusion : null,
  started_at: started_at || '2026-10-11T21:36:19Z',
  app: { slug: 'github-actions' },
});

test('#530 as Maint 71 read it: Gate alone is ready, which is how the red merge happened', () => {
  const result = classifySyncPrChecks({
    checkRuns: checksAsMaint71ReadsThem({
      checkRuns: fixture.check_runs,
      statuses: fixture.statuses,
    }),
    requiredContexts: enforceGeneratedDeliveryRequiredContexts([]),
  });
  assert.equal(result.status, 'ready');
  assert.deepEqual(result.declared_contexts.failed, []);
});

test('#530 with Orchestrator declaring its CI: the failed verify.py blocks the delivery', () => {
  const result = classifySyncPrChecks({
    checkRuns: checksAsMaint71ReadsThem({
      checkRuns: fixture.check_runs,
      statuses: fixture.statuses,
    }),
    requiredContexts: enforceGeneratedDeliveryRequiredContexts([]),
    declaredContexts: new Set(ORCHESTRATOR_DECLARED),
  });
  assert.equal(result.status, 'checks_failed');
  assert.equal(result.failure_scope, 'repo-local');
  assert.deepEqual(
    result.failed.map((check) => check.name).sort(),
    [...ORCHESTRATOR_DECLARED].sort(),
  );
  assert.deepEqual(result.declared_contexts.failed.sort(), [...ORCHESTRATOR_DECLARED].sort());
  assert.equal(result.declared_contexts.never_started.length, 0);
  assert.match(
    describeConsumerDeclaredContexts({
      declared: { state: 'declared', contexts: new Set(ORCHESTRATOR_DECLARED) },
      classification: result,
    }),
    /^Consumer-declared delivery checks: 0 of 3 passed; 3 failed: /,
  );
});

test('an undeclared failing check still never blocks (the #2486 contract)', () => {
  const result = classifySyncPrChecks({
    checkRuns: [
      actionsRun({ name: 'Gate / gate' }),
      actionsRun({ name: VERIFY }),
      actionsRun({ name: 'Resolve Context', conclusion: 'failure' }),
    ],
    requiredContexts: ['Gate / gate'],
    declaredContexts: [VERIFY],
  });
  assert.equal(result.status, 'ready');
  assert.deepEqual(result.declared_contexts.passed, [VERIFY]);
});

test('a declared check that was skipped or neutral passes; cancelled and timed out block', () => {
  for (const conclusion of ['skipped', 'neutral']) {
    const result = classifySyncPrChecks({
      checkRuns: [actionsRun({ name: 'Gate / gate' }), actionsRun({ name: VERIFY, conclusion })],
      requiredContexts: ['Gate / gate'],
      declaredContexts: [VERIFY],
    });
    assert.equal(result.status, 'ready', conclusion);
  }
  for (const conclusion of ['cancelled', 'timed_out', 'action_required', 'failure']) {
    const result = classifySyncPrChecks({
      checkRuns: [actionsRun({ name: 'Gate / gate' }), actionsRun({ name: VERIFY, conclusion })],
      requiredContexts: ['Gate / gate'],
      declaredContexts: [VERIFY],
    });
    assert.equal(result.status, 'checks_failed', conclusion);
  }
});

test('a declared check still running is awaited, and a re-run that passes clears it', () => {
  const running = classifySyncPrChecks({
    checkRuns: [
      actionsRun({ name: 'Gate / gate' }),
      actionsRun({ name: VERIFY, status: 'in_progress' }),
    ],
    requiredContexts: ['Gate / gate'],
    declaredContexts: [VERIFY],
  });
  assert.equal(running.status, 'checks_pending');
  assert.deepEqual(running.declared_contexts.pending, [VERIFY]);

  const rerun = classifySyncPrChecks({
    checkRuns: [
      actionsRun({ name: 'Gate / gate' }),
      actionsRun({ name: VERIFY, conclusion: 'failure', started_at: '2026-10-11T21:36:19Z' }),
      actionsRun({ name: VERIFY, conclusion: 'success', started_at: '2026-10-11T22:30:00Z' }),
    ],
    requiredContexts: ['Gate / gate'],
    declaredContexts: [VERIFY],
  });
  assert.equal(rerun.status, 'ready');
});

test('a declared check with no run waits only while an Actions run on the head is unfinished', () => {
  const starting = classifySyncPrChecks({
    checkRuns: [
      actionsRun({ name: 'Gate / gate' }),
      actionsRun({ name: 'detect changed files', status: 'queued' }),
    ],
    requiredContexts: ['Gate / gate'],
    declaredContexts: [VERIFY],
  });
  assert.equal(starting.status, 'checks_pending');
  assert.deepEqual(
    starting.pending.map((check) => [check.name, check.status]),
    [[VERIFY, 'not_started']],
  );
  assert.deepEqual(starting.declared_contexts.pending, [VERIFY]);

  // Every Actions run finished and the declared job never ran (path filter,
  // renamed job, held workflow). A pending legacy status from another app,
  // which nothing times out, must not keep the delivery waiting.
  const settled = classifySyncPrChecks({
    checkRuns: [
      actionsRun({ name: 'Gate / gate' }),
      legacyStatusAsCheck({ context: 'CodeRabbit', state: 'pending' }),
    ],
    requiredContexts: ['Gate / gate'],
    declaredContexts: [VERIFY],
  });
  assert.equal(settled.status, 'ready');
  assert.deepEqual(settled.declared_contexts.never_started, [VERIFY]);
  assert.match(
    describeConsumerDeclaredContexts({
      declared: { state: 'declared', contexts: new Set([VERIFY]) },
      classification: settled,
    }),
    /0 of 1 passed; 1 never started, not enforced: verify\.py/,
  );
});

test('a declared name the required set already gates keeps the required rule', () => {
  const result = classifySyncPrChecks({
    checkRuns: [actionsRun({ name: 'Gate / gate' }), actionsRun({ name: VERIFY })],
    requiredContexts: ['Gate / gate'],
    declaredContexts: ['Gate / gate', VERIFY],
  });
  assert.equal(result.status, 'ready');
  assert.deepEqual(result.declared_contexts.also_required, ['Gate / gate']);
  assert.deepEqual(result.declared_contexts.passed, [VERIFY]);
});

test('the consumer file parses in every shape the Gate summary accepts, with three states', () => {
  assert.deepEqual(
    [...parseConsumerRequiredContexts(JSON.stringify({ required_contexts: [VERIFY, ' '] })).contexts],
    [VERIFY],
  );
  assert.deepEqual(
    [...parseConsumerRequiredContexts(JSON.stringify({ contexts: [VERIFY] })).contexts],
    [VERIFY],
  );
  assert.deepEqual([...parseConsumerRequiredContexts(JSON.stringify([VERIFY])).contexts], [VERIFY]);
  const empty = parseConsumerRequiredContexts(JSON.stringify({ required_contexts: [] }));
  assert.equal(empty.state, 'declared');
  assert.equal(empty.contexts.size, 0);
  // Workflows' own file, which the Gate summary and Health 44 already read.
  const workflowsOwn = fs.readFileSync(
    path.join(__dirname, '..', '..', 'config', 'required-contexts.json'),
    'utf8',
  );
  assert.deepEqual([...parseConsumerRequiredContexts(workflowsOwn).contexts], ['summary']);
  for (const text of ['{not json', '"verify"', '{"required_contexts": "verify"}', '[1]', '{}']) {
    const parsed = parseConsumerRequiredContexts(text);
    assert.equal(parsed.state, 'unparseable', text);
    assert.equal(parsed.contexts.size, 0, text);
    assert.ok(parsed.error, text);
  }
});

test('every declared-contexts state renders, including the drained one', () => {
  const declared = { state: 'declared', contexts: new Set([VERIFY, EXEC_MIRROR]) };
  const green = classifySyncPrChecks({
    checkRuns: [
      actionsRun({ name: 'Gate / gate' }),
      actionsRun({ name: VERIFY }),
      actionsRun({ name: EXEC_MIRROR, conclusion: 'skipped' }),
    ],
    requiredContexts: ['Gate / gate'],
    declaredContexts: declared.contexts,
  });
  assert.equal(
    describeConsumerDeclaredContexts({ declared, classification: green }),
    'Consumer-declared delivery checks: 2 of 2 passed (all satisfied)',
  );
  assert.equal(
    describeConsumerDeclaredContexts({ declared: { state: 'none' }, classification: green }),
    `Consumer-declared delivery checks: none (${CONSUMER_REQUIRED_CONTEXTS_PATH} absent)`,
  );
  assert.match(
    describeConsumerDeclaredContexts({
      declared: { state: 'unparseable', error: 'invalid JSON: x' },
      classification: green,
    }),
    /NOT ENFORCED, .* is unreadable \(invalid JSON: x\)/,
  );
  assert.equal(
    describeConsumerDeclaredContexts({
      declared: { state: 'declared', contexts: new Set() },
      classification: classifySyncPrChecks({
        checkRuns: [actionsRun({ name: 'Gate / gate' })],
        requiredContexts: ['Gate / gate'],
      }),
    }),
    `Consumer-declared delivery checks: ${CONSUMER_REQUIRED_CONTEXTS_PATH} declares 0 ` +
      'beyond the required checks (all satisfied)',
  );
});

test('the declaration is read from the base branch, and only a 404 means none', async () => {
  const calls = [];
  const client = (respond) => ({
    rest: {
      repos: {
        getContent: async (params) => {
          calls.push(params);
          return respond(params);
        },
      },
    },
  });
  const withRetryFor = (respond) => (fn) => fn(client(respond));
  const body = Buffer.from(JSON.stringify({ required_contexts: ORCHESTRATOR_DECLARED }))
    .toString('base64');

  const declared = await readConsumerDeclaredContexts({
    withRetry: withRetryFor(() => ({ data: { type: 'file', encoding: 'base64', content: body } })),
    owner: 'stranske',
    repo: 'Orchestrator',
    branch: 'main',
  });
  assert.equal(declared.state, 'declared');
  assert.deepEqual([...declared.contexts].sort(), [...ORCHESTRATOR_DECLARED].sort());
  assert.deepEqual(calls[0], {
    owner: 'stranske',
    repo: 'Orchestrator',
    path: CONSUMER_REQUIRED_CONTEXTS_PATH,
    ref: 'main',
  });

  const missing = await readConsumerDeclaredContexts({
    withRetry: withRetryFor(() => {
      throw Object.assign(new Error('Not Found'), { status: 404 });
    }),
    owner: 'stranske',
    repo: 'Orchestrator',
    branch: 'main',
  });
  assert.equal(missing.state, 'none');

  const directory = await readConsumerDeclaredContexts({
    withRetry: withRetryFor(() => ({ data: [] })),
    owner: 'stranske',
    repo: 'Orchestrator',
    branch: 'main',
  });
  assert.equal(directory.state, 'unparseable');

  await assert.rejects(
    readConsumerDeclaredContexts({
      withRetry: withRetryFor(() => {
        throw Object.assign(new Error('Server Error'), { status: 502 });
      }),
      owner: 'stranske',
      repo: 'Orchestrator',
      branch: 'main',
    }),
    /Server Error/,
  );
});

// The whole Maint 71 pass over #530 as it stood when it merged: its real
// delivery record and check runs, Orchestrator's empty protection and
// rulesets, and a base branch that does or does not declare its CI.
async function runMaint71Over530(t, { declaration, checkReads = null, merge = null }) {
  const os = require('node:os');
  const { run } = require('../maint71_merge_sync_prs.js');
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-declared-'));
  t.after(() => fs.rmSync(tempDir, { recursive: true, force: true }));
  const reportPath = path.join(tempDir, 'report.json');
  const repository = 'stranske/Orchestrator';
  const headSha = 'e57bc6b6292b4a18cb011e05c396251d034ad33e';
  const record = {
    schema: 'sync-pr-delivery-record/v1',
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: 'dev-tool-ab725abacde7', generation: 'ab725abacde7', repository,
    desired_tree_hash: '0fe8dbcc5a6714de304cc931117668b6737ee398',
    source_commit: 'af65422cdf606647c4d10890d444d00cdde00828',
    lease_expires_at: '2099-10-14T21:36:08Z', predecessor_prs: [], successor_prs: [],
  };
  const pr530 = {
    number: 530, title: 'deps: sync dev tool versions',
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
    created_at: '2026-10-11T21:36:09Z', updated_at: '2026-10-11T21:36:09Z', state: 'open',
    base: { ref: 'main' },
    head: { ref: 'deps/sync-dev-versions-ab725abacde7', sha: headSha },
    user: { login: 'stranske' },
  };
  const contentReads = [];
  // Read methods only: an unexpected mutation fails the run.
  const github = {
    paginate: async (_method, params) => {
      if (params.state === 'open') return [pr530];
      if (params.ref === headSha) {
        // checkReads, when given, is the sequence of check-run lists each read returns.
        if (checkReads) return checkReads.length > 1 ? checkReads.shift() : checkReads[0];
        return fixture.check_runs;
      }
      return [];
    },
    graphql: async () => ({
      repository: { pullRequest: {
        headRefOid: headSha, state: 'OPEN',
        reviewThreads: { pageInfo: { hasNextPage: false }, nodes: [] },
      } },
    }),
    rest: {
      pulls: {
        list: async () => ({ data: [pr530] }),
        get: async () => ({ data: pr530 }),
        // Present only when a test drives a real merge; otherwise a merge call fails the run.
        ...(merge ? { merge } : {}),
      },
      // Read-only: the runtime AC guard reads labels before any real merge.
      issues: { listLabelsOnIssue: async () => ({ data: [] }) },
      checks: { listForRef: () => {} },
      git: { getCommit: async () => ({ data: { tree: { sha: record.desired_tree_hash } } }) },
      repos: {
        getContent: async (params) => {
          contentReads.push(params);
          if (!declaration) throw Object.assign(new Error('Not Found'), { status: 404 });
          return { data: { type: 'file', encoding: 'base64',
            content: Buffer.from(JSON.stringify(declaration)).toString('base64') } };
        },
        getBranchProtection: async () => {
          throw Object.assign(new Error('Branch not protected'), { status: 404 });
        },
        getRepoRulesets: async () => ({ data: [] }),
        getCombinedStatusForRef: async () => ({ data: { statuses: fixture.statuses } }),
      },
    },
  };
  const logs = [];
  const warnings = [];
  const failures = [];
  t.mock.method(console, 'log', (...args) => logs.push(args.join(' ')));
  const retryHelpers = require('../github-api-with-retry.js');
  t.mock.method(retryHelpers, 'createTokenAwareRetry', async () => null);
  const core = {
    notice: () => {}, warning: (message) => warnings.push(message),
    setFailed: (message) => failures.push(message),
    summary: { addRaw: () => ({ write: async () => {} }) },
  };
  const env = {
    REGISTERED_REPOS_INPUT: repository, REPOS_INPUT: repository,
    CLEANUP_BRANCHES_INPUT: 'false',
    DRY_RUN_INPUT: merge ? 'false' : 'true',
    AUTO_MERGE_INPUT: merge ? 'true' : 'false',
    ACTIVE_SYNC_HASH_INPUT: 'dev-tool', SYNC_HASH_INPUT: '',
    EXPECTED_PLAN_ID_INPUT: '', EXPECTED_PLAN_SCOPE_INPUT: '',
    EXPECTED_SCOPE_BASE_SHA_INPUT: '', EXPECTED_SOURCE_COMMIT_INPUT: '',
    OWNER_PR_PAT: 'test-owner-token', TRUSTED_SYNC_ACTORS: 'stranske',
    SYNC_PR_MERGE_REPORT_JSON: reportPath,
  };
  const originalEnv = Object.fromEntries(Object.keys(env).map((key) => [key, process.env[key]]));
  const originalCwd = process.cwd();
  try {
    Object.assign(process.env, env);
    process.chdir(tempDir);
    await run({
      github, core,
      context: { eventName: 'workflow_dispatch',
        repo: { owner: 'stranske', repo: 'Workflows' }, payload: {},
        runId: 530, runNumber: 530, workflow: 'Maint 71',
        ref: 'refs/heads/main', sha: record.source_commit },
    });
    return {
      report: JSON.parse(fs.readFileSync(reportPath, 'utf8')),
      logs: logs.join('\n'), warnings, failures, contentReads,
    };
  } finally {
    process.chdir(originalCwd);
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test('Maint 71 over #530: without a declaration the red head is merge-ready (the incident)', async (t) => {
  const { report, logs, failures } = await runMaint71Over530(t, { declaration: null });
  const row = report.results[0];
  assert.equal(row.pr, 530);
  // Every gate passed: with auto-merge on, this is the row that merged it.
  assert.equal(row.status, 'ready');
  assert.equal(row.delivery_disposition, 'current');
  assert.equal(row.consumer_declared_contexts.state, 'none');
  assert.match(logs, /Consumer-declared delivery checks: none/);
  assert.deepEqual(failures, []);
});

test('Maint 71 over #530: Orchestrator declaring its CI leaves the delivery open', async (t) => {
  const { report, logs, warnings, failures, contentReads } = await runMaint71Over530(t, {
    declaration: { required_contexts: ORCHESTRATOR_DECLARED },
  });
  const row = report.results[0];
  assert.equal(row.pr, 530);
  assert.equal(row.status, 'checks_failed');
  assert.deepEqual(
    row.failed_checks.map((check) => check.name).sort(),
    [...ORCHESTRATOR_DECLARED].sort(),
  );
  assert.equal(row.consumer_declared_contexts.state, 'declared');
  assert.deepEqual(
    row.consumer_declared_contexts.failed.sort(),
    [...ORCHESTRATOR_DECLARED].sort(),
  );
  assert.equal(row.delivery_disposition, 'repo-local-failure');
  assert.equal(report.summary.merged, 0);
  assert.ok(contentReads.length > 0);
  assert.ok(contentReads.every((read) => read.ref === 'main'));
  assert.match(logs, /Consumer-declared delivery checks: 0 of 3 passed; 3 failed/);
  // A consumer's red CI is not a janitor failure (#2186).
  assert.deepEqual(failures, []);
  assert.deepEqual(warnings, []);
});

test('Maint 71 over #530: a declared check that fails before the final recheck is reported as failed', async (t) => {
  const green = fixture.check_runs.map((check) => (ORCHESTRATOR_DECLARED.includes(check.name)
    ? { ...check, conclusion: 'success' }
    : check));
  const { report } = await runMaint71Over530(t, {
    declaration: { required_contexts: ORCHESTRATOR_DECLARED },
    checkReads: [green, fixture.check_runs],
  });
  const row = report.results[0];
  // The first classification passed; the final exact-head recheck read the red runs.
  assert.equal(row.status, 'checks_failed');
  assert.deepEqual(
    row.consumer_declared_contexts.failed.sort(),
    [...ORCHESTRATOR_DECLARED].sort(),
  );
  assert.deepEqual(row.consumer_declared_contexts.passed, []);
});

test('Maint 71 over #530: a merge-method retry gate that reads red reports what it read', async (t) => {
  const green = fixture.check_runs.map((check) => (ORCHESTRATOR_DECLARED.includes(check.name)
    ? { ...check, conclusion: 'success' }
    : check));
  const merges = [];
  const { report } = await runMaint71Over530(t, {
    declaration: { required_contexts: ORCHESTRATOR_DECLARED },
    // classification, final gate: green; the retry gate before the second method: red.
    checkReads: [green, green, fixture.check_runs],
    merge: async (params) => {
      merges.push(params.merge_method);
      throw new Error('Merge method is not allowed on this repository');
    },
  });
  const row = report.results[0];
  assert.deepEqual(merges, ['merge']);
  assert.equal(row.status, 'merge_failed');
  assert.match(row.error, /merge retry gate blocked: checks_failed/);
  assert.deepEqual(
    row.consumer_declared_contexts.failed.sort(),
    [...ORCHESTRATOR_DECLARED].sort(),
  );
  assert.deepEqual(row.consumer_declared_contexts.passed, []);
});
