'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { dispatchCandidateRefreshFromReport, verifiedCanaryRefreshPlan } = require('../maint71_merge_sync_prs');
const { parseDeliveryRecord } = require('../sync_pr_lease_contract');

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

function replay(report, withRetry) {
  return dispatchCandidateRefreshFromReport({
    report,
    withRetry,
    expectedCanaries: report.inputs.repos,
    trustedActors: ['stranske', 'stranske-automation-bot', 'github-actions[bot]'],
    context: {
      repo: { owner: 'stranske', repo: 'Workflows' },
      payload: { repository: { default_branch: 'main' } },
    },
    core: {
      notice() {},
      summary: { addRaw() { return this; }, async write() {} },
    },
  });
}

for (const run of [42485792262, 42485974523]) {
  test(`Maint 71 ${run}: retained missing-canary reports reproduce the refresh blocker`, async () => {
    const report = read(`maint71-${run}-sync-pr-merge-report.json`);
    const before = structuredClone(report);
    const missing = report.results.filter(row =>
      row.reason === 'candidate_pr_and_no_change_evidence_missing');
    assert.equal(missing.length, 2);
    assert.ok(missing.every(row => row.pr === undefined && row.head_sha === undefined));

    // Exercise the production helper, not a reconstruction of its decision.
    // An absent native subject cannot authorize a read, dispatch or merge.
    await assert.rejects(replay(report, async () => {
      assert.fail('missing canary subjects must be rejected before API execution');
    }), { message: 'canary_refresh_report_subject_unknown' });
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
