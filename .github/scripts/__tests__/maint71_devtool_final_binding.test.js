'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { independentVerificationDeliveryUnchanged: unchanged } = require('../maint71_merge_sync_prs');
const { parseDeliveryRecord } = require('../sync_pr_lease_contract');
const { buildMarkdownSummary } = require('../sync_pr_merge_contract');

const head = '39ab28414db3944adcb74f73daee66806921edfc';
const record = {
  schema: 'sync-pr-delivery-record/v1',
  durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
  plan_id: 'dev-tool-ab725abacde7', generation: 'ab725abacde7',
  repository: 'stranske/Trend_Model_Project',
  desired_tree_hash: '79080970d514c98122ec25fae6fd41933c587b5f',
  source_commit: '19ab61a1e281791e915e512407fffa20515600bb',
  lease_expires_at: '2026-10-14T23:53:24Z', predecessor_prs: [], successor_prs: [],
};
const parsed = (value) => parseDeliveryRecord(
  '<!-- sync-pr-delivery-record:v1 ' + JSON.stringify(value) + ' -->',
);
const now = Date.parse('2026-10-12T00:04:17Z');
const branch = 'deps/sync-dev-versions-ab725abacde7';
const verify = (previous, current, options = {}) =>
  unchanged({ previous: parsed(previous), current: parsed(current), head, branch, now, ...options });

test('actual Maint52 dev-tool record survives both final reads without invented observed-head fields', () => {
  assert.equal(verify(record, record), true);
  assert.equal(verify(record, structuredClone(record)), true);
});

test('dev-tool optional observation must agree; workflow deliveries require an observation', () => {
  const observed = { ...record, head_observed_sha: head, head_observed_at: '2026-10-11T23:53:24Z' };
  assert.equal(verify(observed, observed), true);
  const conflict = { ...observed, head_observed_sha: 'b'.repeat(40) };
  assert.equal(verify(conflict, conflict), false);
  assert.equal(verify(record, record, { branch: 'sync/workflows-candidate' }), false);
  assert.equal(verify(observed, observed, { branch: 'sync/workflows-candidate' }), true);
  assert.equal(verify(observed, observed, { branch: 'sync/workflows-legacy-generation' }), true);
  assert.equal(verify(record, record, { branch: 'sync/workflows-legacy-generation' }), false);
  assert.equal(verify(record, record, { branch: 'ordinary-feature' }), false);
  assert.equal(verify(record, record, { head: '' }), false);
});

test('each record binding change and expired/invalid lease fails closed at either final read', () => {
  for (const field of ['plan_id', 'generation', 'source_commit', 'desired_tree_hash',
    'repository', 'durable_issue_url', 'lease_expires_at', 'predecessor_prs', 'successor_prs']) {
    const changed = { ...record, [field]: Array.isArray(record[field]) ? ['42'] : record[field] + '-changed' };
    assert.equal(verify(record, changed), false, field);
    assert.equal(verify(changed, record), false, 'reverse:' + field);
  }
  const expired = { ...record, lease_expires_at: '2026-10-11T23:00:00Z' };
  assert.equal(verify(expired, expired), false);
  const invalid = { ...record, lease_expires_at: 'invalid' };
  assert.equal(verify(invalid, invalid), false);
});

test('controller uses the same binding guard on REST and immediately-pre-resolution GraphQL records', () => {
  const source = fs.readFileSync(path.join(__dirname, '../maint71_merge_sync_prs.js'), 'utf8');
  assert.match(source, /previous: deliveryRecord, current: currentRecord/);
  assert.match(source, /previous: currentRecord, current: latestRecord/);
  assert.match(source, /currentPr\.head\?\.sha !== pr\.head\.sha/);
  assert.match(source, /latest\?\.headRefOid !== pr\.head\.sha \|\| !finalVerification\.ok/);
});

test('Maint 71 summary names dev-tool candidate and obsolete PRs explicitly', () => {
  const report = {
    schema: 'sync-pr-merge-report/v1',
    inputs: { repos: ['stranske/Trend_Model_Project'], auto_merge: true, dry_run: false },
    summary: { merged: 1, stale_closed: 1, no_prs: 0 },
    results: [
      {
        owner: 'stranske',
        repo: 'Trend_Model_Project',
        pr: 6189,
        branch: 'deps/sync-dev-versions-91791b44e525',
        delivery_lane: 'dev-tool-sync',
        delivery_disposition: 'merged',
        status: 'merged',
      },
      {
        owner: 'stranske',
        repo: 'Trend_Model_Project',
        pr: 6186,
        branch: 'deps/sync-dev-versions-91791b44e525',
        status: 'stale_closed',
      },
    ],
  };
  const summary = buildMarkdownSummary(report);
  assert.match(summary, /6189/);
  assert.match(summary, /#6186 closed unmerged/);
  report.results[1].dry_run = true;
  assert.match(buildMarkdownSummary(report), /#6186 would close unmerged/);
});

test('Maint 71 accounts for closed dev-tool candidates when no generated PR is open', async (t) => {
  const repository = 'stranske/Trend_Model_Project';
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-devtool-accounting-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const env = {
    REGISTERED_REPOS_INPUT: repository, REPOS_INPUT: repository,
    CLEANUP_BRANCHES_INPUT: 'false', DRY_RUN_INPUT: 'true', AUTO_MERGE_INPUT: 'false',
    ACTIVE_SYNC_HASH_INPUT: '', SYNC_HASH_INPUT: '', EXPECTED_PLAN_ID_INPUT: '',
    EXPECTED_SOURCE_COMMIT_INPUT: '', OWNER_PR_PAT: 'test-owner-token',
    TRUSTED_SYNC_ACTORS: 'stranske', SYNC_PR_MERGE_REPORT_JSON: path.join(dir, 'report.json'),
  };
  const previous = Object.fromEntries(Object.keys(env).map(key => [key, process.env[key]]));
  const cwd = process.cwd();
  t.after(() => {
    process.chdir(cwd);
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  });
  Object.assign(process.env, env);
  process.chdir(dir);
  const rows = [
    { number: 6189, state: 'MERGED', headRefName: 'deps/sync-dev-versions-91791b44e525',
      headRefOid: 'ad09728581df4a27d421f272f9e307efaa581e63' },
    { number: 6186, state: 'CLOSED', headRefName: 'deps/sync-dev-versions-44505f50de37',
      headRefOid: '73120b9a594e0348033bcdc008409bb3e75af67a' },
  ].map(pr => ({ ...pr,
    author: { login: 'stranske' }, repository: { nameWithOwner: repository },
    headRepository: { nameWithOwner: repository } }));
  const github = {
    paginate: async () => [],
    rest: { pulls: { list: async () => ({ data: [] }) } },
    graphql: async (_query, variables) => {
      assert.match(variables.query, /repo:stranske\/Trend_Model_Project/);
      return { search: { nodes: rows, pageInfo: { hasNextPage: false } } };
    },
  };
  t.mock.method(require('../github-api-with-retry'), 'createTokenAwareRetry', async () => null);
  const logs = [];
  t.mock.method(console, 'log', (...args) => logs.push(args.join(' ')));
  let summary = '';
  await require('../maint71_merge_sync_prs').run({ github,
    context: { repo: { owner: 'stranske', repo: 'Workflows' }, payload: {} },
    core: { notice() {}, warning() {}, setFailed(message) { assert.fail(message); },
      summary: { addRaw(text) { summary += text; return this; }, async write() {} } },
  });
  assert.match(summary, /stranske\/Trend_Model_Project.*dev-tool:.*#6189 merged.*#6186 closed unmerged/);
  assert.match(logs.join('\n'), /dev-tool:.*#6189 merged.*#6186 closed unmerged/);
  const report = JSON.parse(fs.readFileSync(env.SYNC_PR_MERGE_REPORT_JSON, 'utf8'));
  assert.deepEqual(report.results, [{ owner: 'stranske', repo: 'Trend_Model_Project', status: 'no_prs' }]);
  assert.equal(report.summary.merged || 0, 0, 'historical merges must not count as this run merging');
});

test('dev-tool accounting bounds history and never presents partial reads as none open', async () => {
  const { readDevToolCandidateAccounting } = require('../maint71_merge_sync_prs');
  const repository = 'stranske/Trend_Model_Project';
  const candidate = { number: 6189, state: 'MERGED', headRefName: branch, headRefOid: head,
    author: { login: 'stranske' }, repository: { nameWithOwner: repository },
    headRepository: { nameWithOwner: repository } };
  for (const defect of ['truncated', 'missing-page', 'missing-identity', 'unavailable', 'open', 'untrusted', 'fork']) {
    let calls = 0;
    const row = await readDevToolCandidateAccounting({ owner: 'stranske', repo: 'Trend_Model_Project',
      trustedActors: ['stranske'], withRetry: async fn => fn({ graphql: async query => {
        calls++;
        assert.match(query, /first:100/);
        if (defect === 'unavailable') throw new Error('API unavailable');
        return { search: { pageInfo: defect === 'missing-page' ? null : { hasNextPage: defect === 'truncated' },
          nodes: [{ ...candidate,
            ...(defect === 'missing-identity' ? { headRefOid: null } : {}),
            ...(defect === 'open' ? { state: 'OPEN' } : {}),
            ...(defect === 'untrusted' ? { author: { login: 'unknown' } } : {}),
            ...(defect === 'fork' ? { headRepository: { nameWithOwner: 'other/Trend_Model_Project' } } : {}),
          }] } };
      } }) });
    const summary = buildMarkdownSummary({ dev_tool_candidates: [row] });
    assert.equal(calls, 1, 'reporting must use one bounded search');
    if (['missing-page', 'missing-identity', 'unavailable'].includes(defect)) {
      assert.equal(row.status, 'unknown');
      assert.match(summary, /accounting unknown/);
      assert.doesNotMatch(summary, /none open/);
    } else if (defect === 'truncated') {
      assert.match(summary, /#6189 merged; accounting truncated/);
      assert.doesNotMatch(summary, /none open/);
    } else if (defect === 'open') {
      assert.match(summary, /#6189 open/);
      assert.doesNotMatch(summary, /none open/);
    } else {
      assert.deepEqual(row.candidates, []);
    }
  }
});

test('dev-tool accounting follows cursors so older candidates beyond page one are still named', async () => {
  const { readDevToolCandidateAccounting } = require('../maint71_merge_sync_prs');
  const repository = 'stranske/Trend_Model_Project';
  const candidate = (number, state) => ({ number, state, headRefName: branch, headRefOid: head,
    author: { login: 'stranske' }, repository: { nameWithOwner: repository },
    headRepository: { nameWithOwner: repository } });
  const pages = [
    { search: { pageInfo: { hasNextPage: true, endCursor: 'cursor-1' },
      nodes: [candidate(6213, 'MERGED'), candidate(6189, 'MERGED')] } },
    { search: { pageInfo: { hasNextPage: false, endCursor: 'cursor-2' },
      nodes: [candidate(6189, 'MERGED'), candidate(6186, 'CLOSED')] } },
  ];
  const afters = [];
  const row = await readDevToolCandidateAccounting({ owner: 'stranske', repo: 'Trend_Model_Project',
    trustedActors: ['stranske'], withRetry: async fn => fn({ graphql: async (query, variables) => {
      assert.match(query, /first:100/);
      afters.push(variables.after);
      return pages[afters.length - 1];
    } }) });
  assert.deepEqual(afters, [null, 'cursor-1']);
  assert.equal(row.status, 'complete');
  assert.deepEqual(row.candidates.map(c => c.pr), [6213, 6189, 6186],
    'page-two candidates are collected and duplicates are not repeated');
  const summary = buildMarkdownSummary({ dev_tool_candidates: [row] });
  assert.match(summary, /stranske\/Trend_Model_Project.*dev-tool:.*#6189 merged.*#6186 closed unmerged/);
});

test('dev-tool accounting stops at its page bound and stays truncated, never none open', async () => {
  const { readDevToolCandidateAccounting } = require('../maint71_merge_sync_prs');
  const repository = 'stranske/Trend_Model_Project';
  let calls = 0;
  const row = await readDevToolCandidateAccounting({ owner: 'stranske', repo: 'Trend_Model_Project',
    trustedActors: ['stranske'], withRetry: async fn => fn({ graphql: async () => {
      calls++;
      return { search: { pageInfo: { hasNextPage: true, endCursor: `cursor-${calls}` },
        nodes: [{ number: 6189, state: 'MERGED', headRefName: branch, headRefOid: head,
          author: { login: 'stranske' }, repository: { nameWithOwner: repository },
          headRepository: { nameWithOwner: repository } }] } };
    } }) });
  assert.equal(calls, 3, 'reporting must keep a bounded page count');
  assert.equal(row.status, 'truncated');
  const summary = buildMarkdownSummary({ dev_tool_candidates: [row] });
  assert.match(summary, /#6189 merged; accounting truncated/);
  assert.doesNotMatch(summary, /none open/);
});
