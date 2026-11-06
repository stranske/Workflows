'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { independentVerificationDeliveryUnchanged: unchanged } = require('../maint71_merge_sync_prs');
const { parseDeliveryRecord } = require('../sync_pr_lease_contract');

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
