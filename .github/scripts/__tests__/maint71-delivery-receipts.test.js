'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { dispatchCandidateRefreshFromReport } = require('../maint71_merge_sync_prs');

const evidence = path.join(__dirname, '../../../docs/evidence/issue-4369/runtime-4550');
const read = name => JSON.parse(fs.readFileSync(path.join(evidence, name), 'utf8'));
const selectedRepository = 'stranske/Portable-Alpha-Extension-Model';

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
