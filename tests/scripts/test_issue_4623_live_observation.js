'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { verify } = require('../../docs/evidence/issue-4623/verify-observation');
const retained = require('../../docs/evidence/issue-4623/observation.json');

test('retained live observation binds the first merger report to delivered PR #2454', () => {
  assert.deepEqual(verify(retained), {
    status: 'VERIFIED', observed_at: '2026-11-10T14:34:09Z',
    first_run: 42445636759, latest_run: 42789507724,
    consumer_head: '9c85282d05359ddc468d0881ec6b09269ac592a2',
  });
});

for (const [name, mutate] of [
  ['unmerged repair', e => { e.source_pr.merged = false; }],
  ['delivery missing the repair', e => { e.ancestry.behind_by = 1; }],
  ['wrong repair ancestry', e => { e.ancestry.merge_base_sha = '0'.repeat(40); }],
  ['pre-delivery run', e => { e.first_run.run_started_at = e.source_pr.merged_at; }],
  ['failed first run', e => { e.first_run.conclusion = 'failure'; }],
  ['truncated inventory', e => { e.first_inventory.workflow_runs.pop(); }],
  ['event-filtered inventory', e => { e.collection.first_inventory_url += '&event=workflow_dispatch'; }],
  ['different consumer head', e => { e.delivery_report.head_sha = '0'.repeat(40); }],
  ['different bound source', e => { e.delivery_report.review_finding_disposition.binding.source_commit = '0'.repeat(40); }],
  ['active findings', e => { e.delivery_report.review_finding_disposition.raw_active_count = 1; }],
  ['finding lookup error', e => { e.delivery_report.review_finding_disposition.errors.push('API unavailable'); }],
  ['missing latest runs', e => { e.latest_runs = []; }],
  ['missing consumer comments', e => { e.consumer_comments.pop(); }],
  ['missing issue comments', e => { e.source_issue.comment_rows.pop(); }],
  ['invalid comment timestamp', e => { e.source_issue.comment_rows[0].updated_at = null; }],
  ['post-delivery sync-core bump', e => {
    const row = e.source_issue.comment_rows.find(c => c.body.includes('<!-- sync-core/v1'));
    row.updated_at = e.first_run.updated_at;
  }],
  ['reposted original finding', e => {
    const row = e.consumer_comments.find(c => c.id === 4434491646);
    row.created_at = row.updated_at = e.first_run.updated_at;
  }],
  ['reposted reassessment', e => {
    const row = e.consumer_comments.find(c => c.id === 4496394007);
    row.created_at = row.updated_at = e.first_run.updated_at;
  }],
]) {
  test(`live observation refuses ${name}`, () => {
    const evidence = structuredClone(retained);
    mutate(evidence);
    assert.throws(() => verify(evidence));
  });
}

test('later non-sync issue activity does not imply sync-core is still bumping it', () => {
  assert.ok(retained.source_issue.updated_at > retained.first_run.updated_at);
  assert.equal(verify(retained).status, 'VERIFIED');
});
