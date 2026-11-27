'use strict';
// Maint 90 replays: the Trend_Model_Project#6250 thread that held the fleet for
// 15 hours on 2026-11-26 must now reach a verdict without a person.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const A = require('../maint71_finding_assessment');
const { discover, publish } = require('../maint90_finding_assessment_run');
const { validateReviewResolutionProof } = require('../maint71_merge_sync_prs');
const { isStockFindingReceipt } = require('../maint71_finding_verification');

const policy = require('../../../config/consumer_sync_review_policy.json');
const timeline = require('./fixtures/maint71-trend-6250-review-timeline.json');

const HEAD = '67492a53b310a27e3436d004c46b80333096343e';
const SOURCE = '1f7b9f46cc2db0865c9addd5601c63e10d9b1d99';
const SOURCE_FIX = '0a1b2c3d4e5f60718293a4b5c6d7e8f901234567';
const RECEIVER_FIX_MERGE = '5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f7081';
const THREAD = 'PRRT_kwDOO0LrSc68P4-l';
const REPO = 'stranske/Trend_Model_Project';
const AFTER_WINDOW = Date.parse('2026-11-26T17:40:00Z');

const deliveryRecord = {
  schema: 'sync-pr-delivery-record/v1', durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
  plan_id: 'sha256:6b72242c32d8cbf728bcdb29b2b4f2f17bf1964b3aaad64f0ccfe6b5c9ea0e70', generation: '6b72242c32d8',
  repository: REPO, desired_tree_hash: '371bc72ee1e669ad29011ce38d168c5fea7863ee', source_commit: SOURCE,
  head_observed_sha: HEAD, head_observed_at: '2026-11-26T06:42:10Z', lease_expires_at: '2026-11-29T21:36:11Z',
  predecessor_prs: [], successor_prs: [], delivery_state: 'sealed', review_started_at: '2026-11-26T06:43:57.789Z',
  sealed_at: '2026-11-26T06:43:57.789Z', sealed_head_sha: HEAD,
  review_evidence: { delivery_digest: 'sha256:44cabb775b30b3f0fc1cb9f5d939793689e01607fecb1e58216cf47781f374e2',
    policy_schema: 'workflows.consumer-sync-review-policy/v1', request_comment_id: null,
    reason: 'integration_checks_required', degraded: false, responded_reviewers: [], unavailable_reviewers: [] },
  terminal_disposition: '',
};
const consumerSync = { plan_id: deliveryRecord.plan_id, plan_scope: 'full', scope_base_sha: '',
  source_commit: SOURCE, sync_phase: 'promote' };
const PR_BODY = [
  'Generated sync.',
  `<!-- workflows-consumer-sync:v1 ${JSON.stringify(consumerSync)} -->`,
  `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(deliveryRecord)} -->`,
].join('\n');

function reviewState(nodes = timeline) {
  return {
    headRefOid: HEAD, headRefName: 'sync/workflows-delivery', body: PR_BODY,
    reviewThreads: { pageInfo: { hasNextPage: false, endCursor: null }, nodes: [{
      id: THREAD, isResolved: false, isOutdated: false,
      comments: { pageInfo: { hasNextPage: false, endCursor: null }, nodes: structuredClone(nodes) },
    }] },
  };
}

function select(now = AFTER_WINDOW, nodes = timeline) {
  const state = reviewState(nodes);
  return A.selectAssessableFindings({ repository: REPO, pr: 6250, state, record: deliveryRecord,
    policy, profiles: policy.reviewers, now });
}

test('the #6250 thread becomes assessable once the window has passed since the first request', () => {
  const early = select(Date.parse('2026-11-26T17:30:00Z'));
  assert.equal(early.selected.length, 0);
  assert.equal(early.skipped[0].reason, 'reassessment_window_open');
  const { selected } = select();
  assert.equal(selected.length, 1);
  assert.equal(selected[0].thread_id, THREAD);
  assert.equal(selected[0].head_sha, HEAD);
  assert.equal(selected[0].first_requested_at, '2026-11-26T15:32:36.000Z');
  // The latest current-head request is the 16:23 disposition request.
  assert.equal(selected[0].reassessment_request_url, timeline[3].url);
});

test('a substantive reply from the originating reviewer keeps the thread with the reviewer', () => {
  const nodes = structuredClone(timeline);
  nodes[2].body = 'REJECT\nThe stale footer assertion still fails.';
  const { selected, skipped } = select(AFTER_WINDOW, nodes);
  assert.equal(selected.length, 0);
  assert.equal(skipped[0].reason, 'originating_reviewer_answered');
});

test('an unlisted cheer in a receipt-shaped reply holds the thread and is named, not silent', () => {
  const nodes = structuredClone(timeline);
  nodes[2].body = nodes[2].body.replace('Hooray!', 'Still broken.');
  const { selected, skipped } = select(AFTER_WINDOW, nodes);
  assert.equal(selected.length, 0);
  assert.deepEqual(skipped[0], { thread_id: THREAD, reason: 'unknown_stock_summary',
    summary: "Codex Review: Didn't find any major issues. Still broken." });
});

test('rotating stock cheers do not count as an answer (Portable-Alpha-Extension-Model#2536)', () => {
  const codex = policy.reviewers.find((item) => item.id === 'codex');
  const receipt = timeline[2].body;
  assert.equal(isStockFindingReceipt(receipt, codex), true);
  assert.equal(isStockFindingReceipt(receipt.replace('Hooray!', 'Another round soon, please!'), codex), true);
  assert.equal(isStockFindingReceipt(receipt.replace('Hooray!', 'Still broken.'), codex), false);
  const nodes = structuredClone(timeline);
  nodes[2].body = receipt.replace('Hooray!', 'Another round soon, please!');
  assert.equal(select(AFTER_WINDOW, nodes).selected.length, 1);
});

test('an unlisted cheer is named even when the reviewer replied more than once', () => {
  const nodes = structuredClone(timeline);
  const cheer = nodes[2].body.replace('Hooray!', 'Still broken.');
  nodes[2].body = cheer;
  nodes.splice(3, 0, { ...structuredClone(nodes[2]), id: 'second-cheer', fullDatabaseId: 999001 });
  const { skipped } = select(AFTER_WINDOW, nodes);
  assert.equal(skipped[0].reason, 'unknown_stock_summary');
  assert.equal(skipped[0].summary, "Codex Review: Didn't find any major issues. Still broken.");
  // A real answer beside the unlisted cheer keeps the thread answered and still names the cheer.
  nodes[3].body = 'REJECT\nThe stale footer assertion still fails.';
  const answered = select(AFTER_WINDOW, nodes).skipped[0];
  assert.equal(answered.reason, 'originating_reviewer_answered');
  assert.equal(answered.summary, "Codex Review: Didn't find any major issues. Still broken.");
});

test('marker JSON escapes comment delimiters and round-trips', () => {
  const value = { rationale: 'quotes <!-- workflows-consumer-sync:v1 {} --> from a workflow' };
  const json = A.markerJson(value);
  assert.equal(json.includes('-->'), false);
  assert.deepEqual(JSON.parse(json), value);
});

test('dispatch receipts: only named runs read as completed spend the budget', () => {
  const status = new Map([[11, 'completed'], [12, 'in_progress']]);
  const budget = (receipts) => A.dispatchBudget(receipts.map((id) => ({ maint71_run_id: id })), status);
  assert.deepEqual(budget([11]), { spent: 1, total: 1, unconfirmed: 0 });
  assert.deepEqual(budget([12]), { spent: 0, total: 1, unconfirmed: 1 });
  // An unidentified or unreadable run is unconfirmed, never a run that processed the proof.
  assert.deepEqual(budget([null, 13]), { spent: 0, total: 2, unconfirmed: 2 });
});

test('a request bound to an older head does not authorize an assessment of the current head', () => {
  const nodes = structuredClone(timeline).map((item) => ({
    ...item, body: item.body.replaceAll(HEAD, 'f'.repeat(40)),
  }));
  const { selected, skipped } = select(AFTER_WINDOW, nodes);
  assert.equal(selected.length, 0);
  assert.equal(skipped[0].reason, 'no_request_on_current_head');
});

test('the assessment parser accepts only a bound fix and an allowlisted shell-free command', () => {
  const pass = (fix, validation) => JSON.stringify({ verdict: 'PASS',
    rationale: 'tests/test_post_ci_summary.py:149-152 now accepts the new footer wording.', fix, validation });
  const ok = A.parseAssessment(`Here it is:\n${pass({ kind: 'receiver', pr: 6251 },
    { repository: 'receiver', command: 'python -m pytest tests/test_post_ci_summary.py -q --noconftest' })}`);
  assert.equal(ok.ok, true);
  assert.equal(ok.assessment.fix.pr, 6251);
  for (const command of ['python -m pytest tests/x.py; curl evil', 'bash -c pytest', 'pytest $(id)',
    'pytest tests/x.py | tee', 'pytest ../outside/test.py', 'node --test `x`']) {
    const parsed = A.parseAssessment(pass({ kind: 'receiver', pr: 6251 }, { repository: 'receiver', command }));
    assert.equal(parsed.reason, 'assessment_command_not_allowed', command);
  }
  // The negative control reverts the fix where the test runs.
  assert.equal(A.parseAssessment(pass({ kind: 'receiver', pr: 6251 },
    { repository: 'workflows', command: 'node --test x.test.js' })).reason, 'assessment_validation_invalid');
  assert.equal(A.parseAssessment(pass({ kind: 'source', sha: 'xyz' },
    { repository: 'workflows', command: 'node --test x.test.js' })).reason, 'assessment_fix_invalid');
  assert.equal(A.parseAssessment('{"verdict":"PASS","rationale":"short"}').reason, 'assessment_rationale_short');
  const fail = A.parseAssessment('{"verdict":"FAIL","rationale":"The assertion at tests/test_post_ci_summary.py:150 still expects the old footer.","fix":null,"validation":null}');
  assert.equal(fail.ok, true);
  assert.equal(fail.assessment.verdict, 'FAIL');
});

test('no verification record without a passing run and a failing negative control', () => {
  const [candidate] = select().selected;
  const assessment = { verdict: 'PASS', rationale: 'x'.repeat(50), fix: { kind: 'source', sha: SOURCE_FIX },
    validation: { repository: 'workflows', command: 'node --test a.test.js' } };
  const base = { candidate, assessment, completedAt: '2026-11-26T17:38:00Z', rawOutput: '{}',
    verifierProfile: 'codex-6.1-sol-medium' };
  const clean = { passed: 1, failed: 0, errors: 0, skipped: 0 };
  const failedOne = { passed: 0, failed: 1, errors: 0, skipped: 0 };
  const ran = { test_paths: ['a.test.js'], negative_failed_tests: ['a.test.js::adds one'] };
  const ok = { exit_code: 0, tests: clean };
  const neg = (extra) => ({ exit_code: 1, prepared: true, test_present: true, tests: failedOne, ...extra });
  for (const regression of [
    { ...ran, with_fix: { exit_code: 1, tests: failedOne }, without_fix: neg() },
    { ...ran, with_fix: ok, without_fix: neg({ exit_code: 0, tests: clean }) },
    { ...ran, with_fix: ok, without_fix: { exit_code: null, prepared: false } },
    // The fix added its own test and the revert removed it: not evidence.
    { ...ran, with_fix: ok, without_fix: neg({ test_present: false }) },
    // Timeout, start failure, pytest usage error / no tests collected: not evidence.
    { ...ran, with_fix: ok, without_fix: neg({ exit_code: 124 }) },
    { ...ran, with_fix: ok, without_fix: neg({ exit_code: 127 }) },
    { ...ran, with_fix: ok, without_fix: neg({ exit_code: 4 }) },
    { ...ran, with_fix: ok, without_fix: neg({ exit_code: 5 }) },
    // pytest --continue-on-collection-errors: exit 1, but the test never ran.
    { ...ran, negative_failed_tests: [], with_fix: ok,
      without_fix: neg({ tests: { passed: 0, failed: 0, errors: 1, skipped: 0 } }) },
    // The target test failed, but a collection or setup error also occurred.
    { ...ran, with_fix: ok, without_fix: neg({ tests: { passed: 0, failed: 1, errors: 1, skipped: 0 } }) },
    // Exit 1 from a different test than the one that passed with the fix.
    { ...ran, negative_failed_tests: [], with_fix: ok, without_fix: neg() },
    // No per-test results, or a with-fix run that executed nothing.
    { ...ran, with_fix: { exit_code: 0 }, without_fix: neg() },
    { ...ran, with_fix: { exit_code: 0, tests: { passed: 0, failed: 0, errors: 0, skipped: 1 } }, without_fix: neg() },
    { ...ran, with_fix: ok, without_fix: neg({ tests: null }) },
    // No named test file.
    { ...ran, test_paths: [], with_fix: ok, without_fix: neg() },
  ]) {
    assert.throws(() => A.buildVerificationRecord({ ...base, regression }), /verification_requires_pass_and_regression/);
  }
  assert.equal(A.regressionEstablished({ ...ran, with_fix: ok, without_fix: neg() }), true);
});

// ---- end-to-end replay through discover -> artifacts -> publish ----

const THREAD2 = 'PRRT_kwDOO0LrSc68P4-second';
function secondThread() {
  const nodes = JSON.parse(JSON.stringify(timeline).split(THREAD).join(THREAD2));
  return nodes.map((node, index) => ({ ...node, id: `${node.id}-2`, fullDatabaseId: 880000 + index }));
}

function mockGithub({ comments = [], runs = [], runIdBase = 9000, answerFromGraphqlCall = Infinity,
  twoThreads = false, failDurableReadOn = Infinity } = {}) {
  const calls = { comments: [], dispatches: [], graphql: 0, durableReads: 0 };
  const pull = { number: 6250, state: 'open', head: { ref: 'sync/workflows-delivery', sha: HEAD,
    repo: { full_name: REPO } }, base: { ref: 'main', repo: { full_name: REPO } },
    user: { login: 'stranske' }, body: PR_BODY };
  const fixPull = { number: 6251, title: 'Accept the new footer', state: 'closed', merged: true,
    merged_at: '2026-11-26T15:29:00Z', merge_commit_sha: RECEIVER_FIX_MERGE,
    base: { ref: 'main', repo: { full_name: REPO } }, head: { repo: { full_name: REPO } } };
  const rest = {
    pulls: {
      list: async (params) => ({ data: params.state === 'closed' ? [fixPull] : [pull] }),
      get: async ({ pull_number: number }) => ({ data: number === 6251 ? fixPull : pull }),
    },
    issues: {
      listComments: async () => ({ data: comments }),
      createComment: async ({ issue_number: issue, body }) => {
        const id = 7000 + calls.comments.length;
        const comment = { id, body, created_at: '2026-11-26T17:39:00Z', user: { login: 'stranske' },
          html_url: `https://github.com/stranske/Workflows/issues/${issue}#issuecomment-${id}` };
        calls.comments.push(comment);
        return { data: comment };
      },
    },
    repos: { compareCommitsWithBasehead: async () => ({ data: { status: 'ahead', behind_by: 0, ahead_by: 3 } }) },
    actions: {
      listWorkflowRuns: async () => ({ data: { workflow_runs: runs } }),
      getWorkflowRun: async ({ run_id: id }) => {
        const run = runs.find((item) => item.id === id);
        if (!run) throw Object.assign(new Error('Not Found'), { status: 404 });
        return { data: run };
      },
      createWorkflowDispatch: async (params) => {
        calls.dispatches.push(params);
        return { data: { workflow_run_id: runIdBase + calls.dispatches.length - 1 } };
      },
    },
  };
  const github = {
    rest,
    paginate: async (method, params) => {
      if (method === rest.pulls.list) return [pull];
      if (method === rest.issues.listComments) {
        if (params?.issue_number === 1836) {
          calls.durableReads += 1;
          if (calls.durableReads >= failDurableReadOn) throw Object.assign(new Error('Server Error'), { status: 502 });
        }
        return comments;
      }
      return [];
    },
    graphql: async () => {
      calls.graphql += 1;
      if (calls.graphql < answerFromGraphqlCall) {
        const state = reviewState();
        if (twoThreads) state.reviewThreads.nodes.push({ id: THREAD2, isResolved: false, isOutdated: false,
          comments: { pageInfo: { hasNextPage: false, endCursor: null }, nodes: secondThread() } });
        return { repository: { pullRequest: state } };
      }
      const nodes = structuredClone(timeline);
      nodes[2].body = 'REJECT\nThe stale footer assertion still fails.';
      return { repository: { pullRequest: reviewState(nodes) } };
    },
  };
  return { github, calls };
}

function harness() {
  const notices = [];
  const outputs = {};
  const core = { notice: (message) => notices.push(message), warning: (message) => notices.push(message),
    setOutput: (key, value) => { outputs[key] = value; } };
  const context = { repo: { owner: 'stranske', repo: 'Workflows' }, serverUrl: 'https://github.com', runId: 1,
    payload: { repository: { default_branch: 'main' } } };
  return { core, context, notices, outputs };
}

function writeArtifacts(item, { assessment, regression, raw = '{"verdict":"PASS"}' }) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'maint90-'));
  const a = path.join(root, `assessment-${item.slug}`);
  const r = path.join(root, `regression-${item.slug}`);
  fs.mkdirSync(a); fs.mkdirSync(r);
  fs.writeFileSync(path.join(a, 'assessment.json'), JSON.stringify(assessment));
  fs.writeFileSync(path.join(a, 'codex-output.md'), raw);
  if (regression) fs.writeFileSync(path.join(r, 'regression.json'), JSON.stringify(regression));
  return root;
}

async function replay({ fix, validation, regression, verdict = 'PASS', rationale, mock = {} }) {
  const { github, calls } = mockGithub(mock);
  const h = harness();
  const env = { REGISTERED_REPOS: REPO, TRUSTED_SYNC_ACTORS: 'stranske,stranske-automation-bot' };
  const found = await discover({ github, context: h.context, core: h.core, env, now: AFTER_WINDOW });
  assert.equal(found.matrix.length, 1, 'the held finding must be selected for assessment');
  assert.match(h.notices[0], /findings held 1, drainable now 1/);
  const [item] = found.matrix;
  assert.equal(item.receiver_pulls[0].number, 6251);
  const assessment = verdict === 'PASS'
    ? { ok: true, assessment: { verdict, rationale: rationale || 'tests/test_post_ci_summary.py:149-152 accepts the new footer; the stale assertion is gone.', fix, validation } }
    : { ok: true, assessment: { verdict, rationale: 'The stale assertion at tests/test_post_ci_summary.py:150 still fails.', fix: null, validation: null } };
  const root = writeArtifacts(item, { assessment, regression });
  const outcomes = await publish({ github, context: h.context, core: h.core, now: AFTER_WINDOW,
    env: { MATRIX_JSON: h.outputs.matrix, REDISPATCH_JSON: h.outputs.redispatch, ARTIFACT_ROOT: root,
      DRY_RUN: 'false', PUBLISHER_LOGIN: 'stranske' } });
  return { outcomes, calls, item };
}

const PASSING_REGRESSION = { test_paths: ['tests/test_post_ci_summary.py'],
  with_fix: { exit_code: 0, tail: '1 passed', tests: { passed: 1, failed: 0, errors: 0, skipped: 0 } },
  without_fix: { exit_code: 1, prepared: true, test_present: true, tail: '1 failed',
    tests: { passed: 0, failed: 1, errors: 0, skipped: 0 } },
  negative_failed_tests: ['tests/test_post_ci_summary.py::test_footer'], finished_at: '2026-11-26T17:38:00Z' };

test('replay: #6250 with a verified Workflows source fix publishes the verification and dispatches Maint 71', async () => {
  const { outcomes, calls } = await replay({
    fix: { kind: 'source', sha: SOURCE_FIX },
    validation: { repository: 'workflows', command: 'node --test .github/scripts/__tests__/post-ci.test.js' },
    regression: PASSING_REGRESSION,
    rationale: 'post-ci.test.js:40 now expects the footer <!-- post-ci --> marker; the stale assertion is gone.',
  });
  assert.deepEqual(outcomes.map((item) => item.outcome), ['verified_and_dispatched']);
  assert.equal(calls.comments.length, 2, 'verification plus one dispatch receipt');
  const record = JSON.parse(calls.comments[0].body.match(/<!-- maint71-finding-verification:v1 (.*?) -->/)[1]);
  assert.match(record.rationale, /<!-- post-ci -->/);
  const receipt = JSON.parse(calls.comments[1].body.match(/<!-- maint90-maint71-dispatch:v1 (.*?) -->/)[1]);
  assert.equal(receipt.maint71_run_id, 9000);
  assert.equal(receipt.verification_url, calls.comments[0].html_url);
  assert.equal(record.thread_id, THREAD);
  assert.equal(record.reviewer_unanswered, true);
  assert.equal(record.validation[0].negative_control, 'failed-before-fix');
  assert.equal(calls.dispatches.length, 1);
  const inputs = calls.dispatches[0].inputs;
  assert.equal(calls.dispatches[0].workflow_id, 'maint-71-merge-sync-prs.yml');
  assert.equal(inputs.active_sync_hash, 'campaign');
  assert.deepEqual(JSON.parse(inputs.immutable_handoff_json), { plan_id: consumerSync.plan_id,
    plan_scope: 'full', scope_base_sha: '', source_commit: SOURCE });
  const [proof] = JSON.parse(inputs.review_resolution_json);
  assert.equal(proof.reviewer_acceptance_url, calls.comments[0].html_url);
  assert.equal(proof.acceptance_mode, 'independent-verification');
  assert.equal(validateReviewResolutionProof(proof, { owner: 'stranske', repo: 'Trend_Model_Project',
    prNumber: 6250, headSha: HEAD, actor: 'stranske', trustedActors: ['stranske'] }).ok, true);
});

test('replay: the real #6251 receiver fix is verified and dispatched (#5290 receiver_fix proof)', async () => {
  const { outcomes, calls } = await replay({
    fix: { kind: 'receiver', pr: 6251 },
    validation: { repository: 'receiver', command: 'python -m pytest tests/test_post_ci_summary.py -q --noconftest' },
    regression: PASSING_REGRESSION,
  });
  assert.deepEqual(outcomes.map((item) => item.outcome), ['verified_and_dispatched']);
  assert.equal(calls.comments.length, 2);
  assert.equal(calls.dispatches.length, 1);
});

test('replay: a reviewer reply that lands during the provenance reads stops the PASS', async () => {
  // graphql call 1 = discover, 2 = first live read, 3 = re-read after provenance.
  const { outcomes, calls } = await replay({
    fix: { kind: 'source', sha: SOURCE_FIX },
    validation: { repository: 'workflows', command: 'node --test a.test.js' },
    regression: PASSING_REGRESSION, mock: { answerFromGraphqlCall: 3 },
  });
  assert.deepEqual(outcomes.map((item) => item.outcome), ['no_longer_assessable']);
  assert.equal(calls.comments.length, 0);
  assert.equal(calls.dispatches.length, 0);
});

test('replay: a FAIL verdict hands the finding to its owner once and is not re-assessed on that head', async () => {
  const { outcomes, calls, item } = await replay({ verdict: 'FAIL', regression: { reason: 'no_pass_assessment' } });
  assert.deepEqual(outcomes.map((entry) => entry.outcome), ['handed_to_owner:verifier_fail']);
  assert.equal(calls.dispatches.length, 0);
  const attempt = calls.comments[0];
  assert.match(attempt.body, /maint71-finding-assessment-attempt:v1/);
  // The next sweep sees the attempt and does not spend another assessment.
  const { github } = mockGithub({ comments: [attempt] });
  const h = harness();
  const again = await discover({ github, context: h.context, core: h.core, now: AFTER_WINDOW,
    env: { REGISTERED_REPOS: REPO, TRUSTED_SYNC_ACTORS: 'stranske' } });
  assert.equal(again.matrix.length, 0);
  assert.match(h.notices[0], /handed to owner 1/);
  assert.equal(item.candidate.thread_id, THREAD);
});

test('replay: a negative control that passes without the fix is not evidence', async () => {
  const { outcomes, calls } = await replay({
    fix: { kind: 'source', sha: SOURCE_FIX },
    validation: { repository: 'workflows', command: 'node --test a.test.js' },
    regression: { with_fix: { exit_code: 0 }, without_fix: { exit_code: 0, prepared: true },
      reason: 'negative_control_passed_without_fix', finished_at: '2026-11-26T17:38:00Z' },
  });
  assert.deepEqual(outcomes.map((item) => item.outcome), ['handed_to_owner:negative_control_passed_without_fix']);
  assert.equal(calls.dispatches.length, 0);
});

test('redispatch spends its budget only on Maint 71 runs that carried this proof', async () => {
  const first = await replay({ fix: { kind: 'source', sha: SOURCE_FIX },
    validation: { repository: 'workflows', command: 'node --test a.test.js' }, regression: PASSING_REGRESSION });
  const [verification, receipt9000] = first.calls.comments;
  const sweep = async (comments, runs, runIdBase) => {
    const { github, calls } = mockGithub({ comments, runs, runIdBase });
    const h = harness();
    const env = { REGISTERED_REPOS: REPO, TRUSTED_SYNC_ACTORS: 'stranske' };
    const found = await discover({ github, context: h.context, core: h.core, env, now: AFTER_WINDOW });
    assert.equal(found.matrix.length, 0);
    assert.equal(found.redispatch.length, 1);
    const outcomes = await publish({ github, context: h.context, core: h.core, now: AFTER_WINDOW,
      env: { MATRIX_JSON: h.outputs.matrix, REDISPATCH_JSON: h.outputs.redispatch, DRY_RUN: 'false' } });
    return { outcomes, calls };
  };
  const busy = await sweep([verification, receipt9000], [{ id: 9000, status: 'in_progress', created_at: '2026-11-26T17:39:30Z' }], 9100);
  assert.deepEqual(busy.outcomes.map((item) => item.outcome), ['redispatch_held']);
  // Two unrelated Maint 71 runs complete and our run 9000 is unreadable: nothing is spent.
  const unrelated = await sweep([verification, receipt9000], [
    { id: 2, status: 'completed', created_at: '2026-11-26T17:45:00Z' },
    { id: 3, status: 'completed', created_at: '2026-11-26T18:15:00Z' },
  ], 9001);
  assert.deepEqual(unrelated.outcomes.map((item) => item.outcome), ['redispatched']);
  assert.equal(unrelated.calls.dispatches.length, 1);
  const receipt9001 = unrelated.calls.comments[0];
  assert.match(receipt9001.body, /"maint71_run_id":9001/);
  // Both runs that carried the proof completed without resolving: hand off.
  const exhausted = await sweep([verification, receipt9000, receipt9001], [
    { id: 9000, status: 'completed', created_at: '2026-11-26T17:41:00Z' },
    { id: 9001, status: 'completed', created_at: '2026-11-26T18:20:00Z' },
  ], 9200);
  assert.deepEqual(exhausted.outcomes.map((item) => item.outcome), ['handed_to_owner:maint71_did_not_resolve']);
});

test('redispatch hands off after four receipts whose runs cannot be confirmed', async () => {
  const first = await replay({ fix: { kind: 'source', sha: SOURCE_FIX },
    validation: { repository: 'workflows', command: 'node --test a.test.js' }, regression: PASSING_REGRESSION });
  const [verification] = first.calls.comments;
  const receipt = (n) => ({ id: 7100 + n, created_at: '2026-11-26T17:39:00Z', user: { login: 'stranske' },
    html_url: `https://github.com/stranske/Workflows/issues/1836#issuecomment-${7100 + n}`,
    body: A.renderDispatchReceipt({ repository: REPO, pr: 6250, head_sha: HEAD, thread_id: THREAD },
      { runId: null, commentUrl: verification.html_url, dispatchedAt: '2026-11-26T17:39:00Z' }) });
  const sweep = async (comments) => {
    const { github, calls } = mockGithub({ comments });
    const h = harness();
    await discover({ github, context: h.context, core: h.core, now: AFTER_WINDOW,
      env: { REGISTERED_REPOS: REPO, TRUSTED_SYNC_ACTORS: 'stranske' } });
    const outcomes = await publish({ github, context: h.context, core: h.core, now: AFTER_WINDOW,
      env: { MATRIX_JSON: h.outputs.matrix, REDISPATCH_JSON: h.outputs.redispatch, DRY_RUN: 'false' } });
    return { outcomes, calls };
  };
  const three = await sweep([verification, receipt(1), receipt(2), receipt(3)]);
  assert.deepEqual(three.outcomes.map((item) => item.outcome), ['redispatched']);
  const four = await sweep([verification, receipt(1), receipt(2), receipt(3), receipt(4)]);
  assert.deepEqual(four.outcomes.map((item) => item.outcome), ['handed_to_owner:maint71_runs_unconfirmed']);
});

test('a read failure on one finding skips the whole PR and discards its planned work', async () => {
  const both = mockGithub({ twoThreads: true });
  const ok = harness();
  const found = await discover({ github: both.github, context: ok.context, core: ok.core, now: AFTER_WINDOW,
    env: { REGISTERED_REPOS: REPO, TRUSTED_SYNC_ACTORS: 'stranske' } });
  assert.equal(found.matrix.length, 2, 'both findings on the PR are assessable');
  const failing = mockGithub({ twoThreads: true, failDurableReadOn: 2 });
  const h = harness();
  const skipped = await discover({ github: failing.github, context: h.context, core: h.core, now: AFTER_WINDOW,
    env: { REGISTERED_REPOS: REPO, TRUSTED_SYNC_ACTORS: 'stranske' } });
  assert.equal(skipped.matrix.length, 0, 'the first finding queued before the failure is discarded');
  assert.equal(skipped.counts.unreadable_prs, 1);
  assert.match(h.notices.find((line) => line.includes('whole PR skipped')), /6250: durable issue unreadable \(502\)/);
  assert.match(h.notices.find((line) => line.startsWith('Maint 90 findings')), /held 2, drainable now 0.*unreadable this run 1/);
});
