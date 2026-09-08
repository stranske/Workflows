'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { run } = require('../maint71_merge_sync_prs');

async function reportSelection(t, { syncHash, withRecord }) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-selection-'));
  t.after(() => fs.rmSync(tempDir, { recursive: true, force: true }));
  const reportPath = path.join(tempDir, 'report.json');
  const repository = 'stranske/Travel-Plan-Permission';
  const headSha = 'd'.repeat(40);
  const sourceCommit = 'c'.repeat(40);
  const observedAt = new Date().toISOString();
  const metadata = {
    schema: 'workflows-consumer-sync-pr/v1', consumer_repo: repository,
    plan_id: `sha256:${'a'.repeat(64)}`, plan_scope: 'full',
    source_commit: sourceCommit, source_sha: sourceCommit,
    template_hash: 'candidate-generation', sync_phase: 'canary',
  };
  const record = {
    schema: 'sync-pr-delivery-record/v1',
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: metadata.plan_id, generation: 'record-generation', repository,
    desired_tree_hash: 'tree-abc', source_commit: sourceCommit,
    head_observed_sha: headSha, head_observed_at: observedAt,
    lease_expires_at: '2099-08-14T00:00:00Z', predecessor_prs: [], successor_prs: [],
  };
  const candidate = {
    number: 1480, title: 'chore: sync workflow templates',
    body: `<!-- workflows-consumer-sync:v1 ${JSON.stringify(metadata)} -->` +
      (withRecord ? `\n<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->` : ''),
    created_at: observedAt, updated_at: observedAt, state: 'open',
    base: { ref: 'main' }, head: { ref: 'sync/workflows-candidate', sha: headSha },
    user: { login: 'stranske' },
  };
  // Expose read methods only: an unexpected mutation fails the test.
  const github = {
    paginate: async (_method, params) => params.state === 'open' ? [candidate] : [],
    rest: {
      pulls: { list: async () => ({ data: [candidate] }), get: async () => ({ data: candidate }) },
      git: { getCommit: async () => ({ data: { tree: { sha: 'tree-abc' } } }) },
    },
  };
  const logs = [];
  const failures = [];
  const warnings = [];
  t.mock.method(console, 'log', (...args) => logs.push(args.join(' ')));
  const core = {
    notice: () => {}, warning: (message) => warnings.push(message),
    setFailed: (message) => failures.push(message),
    summary: { addRaw: () => ({ write: async () => {} }) },
  };
  const env = {
    REGISTERED_REPOS_INPUT: repository, REPOS_INPUT: repository,
    CLEANUP_BRANCHES_INPUT: 'false', DRY_RUN_INPUT: 'true', AUTO_MERGE_INPUT: 'false',
    ACTIVE_SYNC_HASH_INPUT: syncHash, SYNC_HASH_INPUT: '',
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
        runId: 71, runNumber: 71, workflow: 'Maint 71',
        ref: 'refs/heads/main', sha: sourceCommit },
    });
    assert.deepEqual(failures, []);
    assert.deepEqual(warnings, []);
    return { report: JSON.parse(fs.readFileSync(reportPath, 'utf8')), logs: logs.join('\n') };
  } finally {
    process.chdir(originalCwd);
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test('Maint 71 reports no_active_sync_pr when a valid candidate does not match the active hash', async (t) => {
  const { report, logs } = await reportSelection(t, { syncHash: 'expected-hash', withRecord: true });
  assert.equal(report.results.length, 1);
  const row = report.results[0];
  assert.equal(row.status, 'target_missing');
  assert.equal(row.delivery_reason, 'no_active_sync_pr');
  assert.equal(row.expected_branch, 'sync/workflows-expected-hash');
  assert.equal(row.active_sync_hash, 'expected-hash');
  assert.equal(row.open_sync_prs[0].number, 1480);
  assert.match(logs, /no_active_sync_pr \(expected sync\/workflows-expected-hash, active hash 'expected-hash'\)/);
  assert.doesNotMatch(logs, /missing_delivery_record/);
  assert.deepEqual(report.handoff_records, []);
});

test('Maint 71 reports missing_delivery_record for a selected candidate with no record', async (t) => {
  const { report, logs } = await reportSelection(t, { syncHash: '', withRecord: false });
  assert.equal(report.results.length, 1);
  assert.equal(report.results[0].status, 'delivery_contract_blocked');
  assert.equal(report.results[0].pr, 1480);
  assert.equal(report.results[0].delivery_reason, 'missing_delivery_record');
  assert.match(logs, /Delivery contract blocks merge: missing_delivery_record/);
  assert.doesNotMatch(logs, /no_active_sync_pr/);
  assert.deepEqual(report.handoff_records, []);
});

test('Maint 71 empty-hash dispatch still selects a candidate with a valid delivery record', async (t) => {
  const { report, logs } = await reportSelection(t, { syncHash: '', withRecord: true });
  assert.equal(report.results.length, 1);
  assert.equal(report.results[0].status, 'review_window_pending');
  assert.equal(report.results[0].pr, 1480);
  assert.doesNotMatch(JSON.stringify(report), /no_active_sync_pr|missing_delivery_record/);
  assert.doesNotMatch(logs, /no_active_sync_pr|missing_delivery_record/);
});
