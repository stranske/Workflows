'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {
  confirmExactHeadSyncFindingGate, dispatchCandidateRefreshFromReport,
  repositoryConversationGate, verifiedCanaryRefreshPlan,
} = require('../maint71_merge_sync_prs');
const { parseDeliveryRecord, formatDeliveryRecord } = require('../sync_pr_lease_contract');
const { evaluateSyncFindingDispositions } = require('../sync_pr_merge_contract');

const evidence = path.join(__dirname, '../../../docs/evidence/issue-4369/runtime-4550');
const read = name => JSON.parse(fs.readFileSync(path.join(evidence, name), 'utf8'));
const selectedRepository = 'stranske/Portable-Alpha-Extension-Model';

function nativeFixture() {
  const pr = read('supported-live-observation.json').consumer_pr;
  const [marker] = [...pr.body.matchAll(/<!-- workflows-consumer-sync:v1 (.+?) -->/g)];
  return {
    owner: 'stranske', repo: 'Portable-Alpha-Extension-Model', pr,
    metadata: JSON.parse(marker[1]), record: parseDeliveryRecord(pr.body),
    nativeHead: read('native-candidate-commit.json'),
  };
}

async function verifyNative(fixture) {
  const calls = [];
  // Exercise the native commit read as well as production scope verification.
  // No writer/dispatch method is available to this replay.
  const { nativeHead, ...args } = fixture;
  const result = await verifiedCanaryRefreshPlan({ ...args, withRetry: async operation => {
    const value = await operation({ rest: { repos: { getCommit: async request => {
      calls.push(request);
      return { data: nativeHead };
    } } } });
    assert.deepEqual(calls, [{ owner: fixture.owner, repo: fixture.repo,
      ref: fixture.pr.head.sha }]);
    return value;
  } });
  assert.equal(calls.length, 1);
  return result;
}

test('the retained signed consumer head authenticates the frozen source-delta tuple', async () => {
  const fixture = nativeFixture();
  assert.equal(fixture.nativeHead.url,
    `https://api.github.com/repos/${selectedRepository}/commits/${fixture.pr.head.sha}`);
  assert.equal(fixture.nativeHead.sha, fixture.record.sealed_head_sha);
  const result = await verifyNative(fixture);
  assert.deepEqual(result, {
    plan_id: fixture.metadata.plan_id, plan_scope: 'source-delta',
    scope_base_sha: fixture.metadata.scope_base_sha, source_commit: fixture.record.source_commit,
  });
  const producerLog = fs.readFileSync(path.join(evidence, 'maint68-42485644055.log'), 'utf8');
  assert.ok(producerLog.includes(`SOURCE_COMMIT: ${result.source_commit}`));
  assert.notEqual(result.source_commit, read('maint68-42485644055.json').headSha,
    'workflow tooling revision is distinct from the frozen payload source');
});

for (const [field, mutate, errorPrefix] of [
  ['signature', f => { f.nativeHead.commit.verification.verified = false; }, 'canary_refresh_native_head_unverified'],
  ['signature reason', f => { f.nativeHead.commit.verification.reason = 'unsigned'; }, 'canary_refresh_native_head_unverified'],
  ['commit SHA', f => { f.nativeHead.sha = '0'.repeat(40); }, 'canary_refresh_native_head_unverified'],
  ['observed head', f => { f.record.head_observed_sha = '0'.repeat(40); }, 'canary_refresh_native_scope_mismatch'],
  ['source', f => { f.nativeHead.commit.message = f.nativeHead.commit.message.replace(f.record.source_commit, '0'.repeat(40)); }, 'canary_refresh_native_scope_mismatch'],
  ['plan', f => { f.nativeHead.commit.message = f.nativeHead.commit.message.replace(f.record.plan_id, `sha256:${'0'.repeat(64)}`); }, 'canary_refresh_native_scope_mismatch'],
  ['scope', f => { f.metadata.plan_scope = 'full'; }, 'canary_refresh_native_scope_mismatch'],
  ['scope base', f => { f.metadata.scope_base_sha = '0'.repeat(40); }, 'canary_refresh_native_scope_mismatch'],
]) {
  test(`the retained consumer payload refuses substituted ${field} before recovery`, async () => {
    const fixture = nativeFixture();
    mutate(fixture);
    await assert.rejects(verifyNative(fixture), error => error.message.startsWith(errorPrefix));
  });
}

function replay(report, withRetry, core) {
  return dispatchCandidateRefreshFromReport({
    report,
    withRetry,
    expectedCanaries: report.inputs.repos,
    trustedActors: ['stranske', 'stranske-automation-bot', 'github-actions[bot]'],
    context: {
      repo: { owner: 'stranske', repo: 'Workflows' },
      payload: { repository: { default_branch: 'main' } },
    },
    core: core || {
      notice() {},
      summary: { addRaw() { return this; }, async write() {} },
    },
  });
}

// Counterfactual base-refresh requests for the retained candidate. These are
// offline reads, not evidence that this sealed candidate needs a refresh.
function refreshSubject() {
  const fixture = nativeFixture();
  const report = read('maint71-42485974523-sync-pr-merge-report.json');
  report.results = report.results.filter(row => `${row.owner}/${row.repo}` === selectedRepository);
  Object.assign(report.results[0], {
    status: 'stable_base_refresh_required',
    next_command: 'dispatch-maint-68-phase-canary-no-filter',
  });
  return { ...fixture, report };
}

function nativeReportReader(fixture) {
  const calls = [];
  const client = { rest: {
    pulls: { get: async request => {
      calls.push(['pull', request]);
      return { data: fixture.pr };
    } },
    repos: { getCommit: async request => {
      calls.push(['commit', request]);
      if (request.repo === fixture.repo) return { data: fixture.nativeHead };
      throw new Error('verified-source-history-boundary');
    } },
  } };
  return { calls, withRetry: operation => operation(client) };
}

test('the retained report tuple reaches source history only after native verification', async () => {
  const fixture = refreshSubject();
  const before = structuredClone(fixture.report);
  const reader = nativeReportReader(fixture);
  await assert.rejects(replay(fixture.report, reader.withRetry), {
    message: 'verified-source-history-boundary',
  });
  assert.deepEqual(reader.calls.map(([kind]) => kind), ['pull', 'commit', 'commit']);
  assert.deepEqual(reader.calls[2][1], {
    owner: 'stranske', repo: 'Workflows', ref: fixture.record.source_commit,
  });
  assert.deepEqual(fixture.report, before);
});

for (const [field, substitute] of [
  ['source_commit', '0'.repeat(40)],
  ['plan_id', `sha256:${'0'.repeat(64)}`],
  ['scope_base_sha', '0'.repeat(40)],
  ['plan_scope', 'full'],
]) {
  test(`matching report and PR-body ${field} cannot replace the signed payload identity`, async () => {
    const fixture = refreshSubject();
    const row = fixture.report.results[0];
    row[field] = fixture.metadata[field] = substitute;
    if (field === 'source_commit') fixture.metadata.source_sha = substitute;
    if (field === 'source_commit' || field === 'plan_id') fixture.record[field] = substitute;
    if (field === 'plan_scope') row.scope_base_sha = fixture.metadata.scope_base_sha = '';
    fixture.pr.body = `<!-- workflows-consumer-sync:v1 ${JSON.stringify(fixture.metadata)} -->\n${formatDeliveryRecord(fixture.record)}`;
    // All mutable copies agree; the native signed commit is unchanged. The
    // refusal must occur before reading source history or attempting a write.
    assert.equal(row[field], fixture.metadata[field]);
    const before = structuredClone(fixture.report);
    const reader = nativeReportReader(fixture);
    await assert.rejects(replay(fixture.report, reader.withRetry), error =>
      error.message.startsWith('canary_refresh_native_scope_mismatch'));
    assert.deepEqual(reader.calls, [
      ['pull', { owner: fixture.owner, repo: fixture.repo, pull_number: fixture.pr.number }],
      ['commit', { owner: fixture.owner, repo: fixture.repo, ref: fixture.pr.head.sha }],
    ]);
    assert.deepEqual(fixture.report, before);
  });
}

function historicalConversation() {
  const [thread] = read('scoped-review-thread.json');
  assert.equal(thread.comments[0].database_id, 4434491702);
  assert.equal(thread.comments[1].database_id, 4505043101);
  return {
    id: thread.id, path: thread.path,
    isResolved: thread.is_resolved, isOutdated: thread.is_outdated,
    comments: {
      pageInfo: { hasNextPage: false },
      nodes: thread.comments.map(comment => ({
        id: comment.id, body: comment.body, updatedAt: comment.updated_at,
        author: { login: comment.author.login },
        url: `https://github.com/${selectedRepository}/pull/2454#discussion_r${comment.database_id}`,
      })),
    },
  };
}

// Insert historical evidence into an offline final-gate read. This does not
// claim that the old PR's thread belongs to the new candidate. Reopening it is
// a counterfactual proving that history cannot authorize a current exemption.
async function findingReplay(thread) {
  const { owner, repo, pr, record } = nativeFixture();
  const calls = [];
  const connection = { pageInfo: { hasNextPage: false }, nodes: [thread] };
  const client = {
    rest: { issues: { listComments() {} } },
    paginate: async (method, params) => {
      assert.equal(method, client.rest.issues.listComments);
      assert.deepEqual(params, { owner, repo, issue_number: pr.number, per_page: 100 });
      calls.push('comments');
      return read('scoped-review-thread.json')[0].comments.map(comment => ({
        id: comment.database_id, body: comment.body, updated_at: comment.updated_at,
        user: { login: comment.author.login },
      }));
    },
    graphql: async (_query, params) => {
      assert.deepEqual(params, { owner, repo, number: pr.number });
      calls.push('final-head-and-findings');
      return { repository: { pullRequest: {
        headRefOid: pr.head.sha, body: pr.body, reviewThreads: connection,
      } } };
    },
  };
  const gate = await confirmExactHeadSyncFindingGate({
    owner, repo, pr, record,
    threads: connection.nodes.filter(item => !item.isResolved && !item.isOutdated),
    read: operation => operation(client),
  });
  // Feed the unfiltered native-shaped connection into the production
  // evaluator as well; exclusion must not be implemented only by this fixture.
  assert.deepEqual(evaluateSyncFindingDispositions({
    ...gate.packet, reviewThreads: connection.nodes,
    activeReviewThreadCount: gate.evaluation.raw_active_count,
  }), gate.evaluation);
  return { gate, calls, connection, owner, repo };
}

test('historical discussion is excluded by the final finding gate for both causal reports', async () => {
  const replayed = await findingReplay(historicalConversation());
  assert.deepEqual(replayed.calls, []);
  assert.equal(replayed.gate.ok, true);
  for (const run of [42485792262, 42485974523]) {
    const report = read(`maint71-${run}-sync-pr-merge-report.json`);
    const selected = report.results.find(row => `${row.owner}/${row.repo}` === selectedRepository);
    assert.deepEqual(replayed.gate.evaluation, selected.review_finding_disposition);
  }
  const conversation = await repositoryConversationGate({ ...replayed, branch: 'main',
    read: async () => assert.fail('a resolved historical thread needs no policy exemption'),
  });
  assert.equal(conversation.ok, true);
  assert.equal(conversation.unresolved_count, 0);
});

for (const [resolved, outdated] of [[true, false], [false, true]]) {
  test(`historical finding exclusion with resolved=${resolved}, outdated=${outdated} preserves conversation policy`, async () => {
    const thread = historicalConversation();
    thread.isResolved = resolved;
    thread.isOutdated = outdated;
    const replayed = await findingReplay(thread);
    assert.equal(replayed.gate.ok, true);
    assert.equal(replayed.gate.evaluation.raw_active_count, 0);
    assert.deepEqual(replayed.gate.evaluation.findings, []);
    const reads = [];
    const client = { rest: { repos: { getBranchRules() {} } },
      paginate: async (method, params) => {
        assert.equal(method, client.rest.repos.getBranchRules);
        assert.deepEqual(params, { owner: replayed.owner, repo: replayed.repo,
          branch: 'main', per_page: 100 });
        reads.push('applicable-rules');
        return [{ type: 'pull_request', parameters: { required_review_thread_resolution: true } }];
      },
    };
    const conversation = await repositoryConversationGate({ ...replayed, branch: 'main',
      read: operation => operation(client),
    });
    assert.equal(conversation.ok, resolved);
    assert.deepEqual(reads, resolved ? [] : ['applicable-rules']);
    if (!resolved) {
      assert.equal(conversation.reason, 'merge_blocked_repository_policy');
      assert.deepEqual(conversation.unresolved_thread_ids, [thread.id]);
      assert.equal(conversation.unresolved_outdated_count, 1);
    }
  });
}

test('reopening the historical finding cannot reuse its old worker disposition for this head', async () => {
  const thread = historicalConversation();
  thread.isResolved = thread.isOutdated = false;
  const { gate, calls } = await findingReplay(thread);
  assert.deepEqual(calls, ['comments', 'final-head-and-findings']);
  assert.equal(gate.packet.evidenceComplete, true);
  assert.deepEqual(gate.evaluation.errors, []);
  assert.equal(gate.ok, false);
  assert.equal(gate.evaluation.raw_active_count, 1);
  assert.equal(gate.evaluation.aggregates.blocking, 1);
  assert.equal(gate.evaluation.aggregates.unknown, 1);
  assert.deepEqual(gate.evaluation.unknown_thread_ids, [thread.id]);
  const [finding] = gate.evaluation.findings;
  assert.equal(finding.url, thread.comments.nodes[0].url);
  assert.deepEqual(finding.errors, ['classification_missing_or_stale']);
});

for (const run of [42485792262, 42485974523]) {
  test(`Maint 71 ${run}: retained missing-canary reports reproduce the refresh blocker`, async () => {
    const report = read(`maint71-${run}-sync-pr-merge-report.json`);
    const before = structuredClone(report);
    const missing = report.results.filter(row =>
      row.reason === 'candidate_pr_and_no_change_evidence_missing');
    assert.equal(missing.length, 2);
    assert.ok(missing.every(row => row.pr === undefined && row.head_sha === undefined));
    const notices = [], summaries = [];
    const core = { notice: value => notices.push(value), summary: {
      addRaw(value) { summaries.push(value); return this; }, async write() {},
    } };
    const diagnostic = {
      schema: 'workflows.canary-refresh-subject-refusal/v1',
      code: 'canary_refresh_report_subject_unknown',
      blocking: 2, drainable: 0, next_action: 'owner-recovery-required',
      subjects: missing.map(row => ({ repository: `${row.owner}/${row.repo}`,
        reasons: ['pr_missing_or_invalid', 'head_missing_or_invalid'] })),
      omitted_subjects: 0,
    };

    // Exercise the production helper, not a reconstruction of its decision.
    // An absent native subject cannot authorize a read, dispatch or merge.
    await assert.rejects(replay(report, async () => {
      assert.fail('missing canary subjects must be rejected before API execution');
    }, core), error => {
      assert.equal(error.message, diagnostic.code);
      assert.deepEqual(error.diagnostic, diagnostic);
      return true;
    });
    assert.deepEqual(notices, [`canary-refresh-subject-refusal: ${JSON.stringify(diagnostic)}`]);
    assert.equal(summaries.length, 1);
    assert.ok(summaries[0].includes(JSON.stringify(diagnostic)));
    assert.deepEqual(report, before, 'a rejected refresh must preserve the delivery receipt');
  });

  test(`Maint 71 ${run}: the selected sealed consumer cannot authorize a refresh`, async () => {
    const report = read(`maint71-${run}-sync-pr-merge-report.json`);
    report.results = report.results.filter(row =>
      `${row.owner}/${row.repo}` === selectedRepository);
    assert.equal(report.results.length, 1);
    const result = await replay(report, async () => {
      assert.fail('a selected sealed/prepared candidate has no refresh request');
    });
    assert.deepEqual(result, {
      eligible: false, state: 'no-refresh-request', dispatched: false,
    });
  });

  for (const repository of ['stranske/Travel-Plan-Permission', 'stranske/trip-planner']) {
    test(`Maint 71 ${run}: ${repository} cannot borrow the selected consumer identity`, async () => {
      const report = read(`maint71-${run}-sync-pr-merge-report.json`);
      const candidate = read('supported-live-observation.json').consumer_pr;
      report.results = report.results.filter(row => `${row.owner}/${row.repo}` === repository);
      assert.equal(report.results.length, 1);
      Object.assign(report.results[0], { pr: candidate.number, head_sha: candidate.head.sha });
      const calls = [];
      const client = { rest: { pulls: { get: async request => {
        calls.push(request);
        return { data: candidate };
      } } } };
      // Supplying well-formed IDs is insufficient: the fresh native PR must
      // belong to this repository. No other API method is available to replay.
      await assert.rejects(replay(report, async operation => operation(client)), {
        message: 'canary_refresh_report_native_subject_changed',
      });
      const [owner, repo] = repository.split('/');
      assert.deepEqual(calls, [{ owner, repo, pull_number: candidate.number }]);
      assert.equal(report.canary_refresh.refresh_dispatched, 0);
    });
  }
}

test('report subject refusal bounds diagnostics and excludes unconfigured raw content', async () => {
  const report = read('maint71-42485974523-sync-pr-merge-report.json');
  const row = report.results[0];
  report.results = Array.from({ length: 10 }, () => ({ ...row,
    owner: 'unconfigured', repo: 'arbitrary-report-content',
    reason: 'arbitrary-report-reason', pr: -1, head_sha: 'arbitrary-report-head',
  }));
  const before = structuredClone(report), notices = [];
  await assert.rejects(replay(report, async () => {
    assert.fail('invalid subjects must be refused before any native API reads');
  }, { notice: value => notices.push(value), summary: {
    addRaw() { return this; }, async write() {},
  } }), error => {
    assert.equal(error.message, 'canary_refresh_report_subject_unknown');
    assert.equal(error.diagnostic.blocking, 10);
    assert.equal(error.diagnostic.drainable, 0);
    assert.equal(error.diagnostic.subjects.length, 8);
    assert.equal(error.diagnostic.omitted_subjects, 2);
    assert.ok(error.diagnostic.subjects.every(subject => subject.repository === null
      && JSON.stringify(subject.reasons) === JSON.stringify([
        'repository_not_configured', 'pr_missing_or_invalid', 'head_missing_or_invalid',
      ])));
    return true;
  });
  assert.equal(notices.length, 1);
  assert.ok(!notices[0].includes('arbitrary-report'));
  assert.deepEqual(report, before);
});

test('all report subjects are checked before reading a valid earlier candidate', async () => {
  const fixture = refreshSubject();
  const missing = read('maint71-42485974523-sync-pr-merge-report.json').results[0];
  fixture.report.results.push(missing);
  await assert.rejects(replay(fixture.report, async () => {
    assert.fail('preflight must find the absent subject before reading the first valid PR');
  }), error => {
    assert.equal(error.message, 'canary_refresh_report_subject_unknown');
    assert.equal(error.diagnostic.blocking, 1);
    return true;
  });
});
