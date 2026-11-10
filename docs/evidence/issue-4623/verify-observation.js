'use strict';

// Replay the bounded live observation; this does not dispatch, merge or modify GitHub.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const WORKFLOW = '.github/workflows/maint-71-merge-sync-prs.yml';
const REPOSITORY = 'stranske/Portable-Alpha-Extension-Model';

function timestamp(value) {
  assert.equal(typeof value, 'string', 'missing observation timestamp');
  assert.match(value, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/, 'invalid UTC timestamp');
  const time = Date.parse(value);
  assert.ok(Number.isFinite(time), 'invalid observation timestamp');
  assert.equal(new Date(time).toISOString(), value.replace('Z', '.000Z'));
  return time;
}

function verify(evidence) {
  assert.equal(evidence.schema, 'workflows.issue-4623-observation/v1');
  const observed = timestamp(evidence.observed_at);
  const source = evidence.source_pr;
  const consumer = evidence.consumer;
  assert.equal(source.number, 4463);
  assert.equal(source.merged, true, 'source repair has not merged');
  assert.equal(consumer.repository, REPOSITORY);
  assert.equal(consumer.number, 2454);
  assert.match(consumer.head_sha, /^[a-f0-9]{40}$/);
  assert.match(consumer.source_commit, /^[a-f0-9]{40}$/);
  assert.ok(timestamp(source.merged_at) < timestamp(consumer.regenerated_at));
  assert.ok(timestamp(consumer.regenerated_at) < timestamp(consumer.merged_at));
  assert.ok(timestamp(consumer.merged_at) <= observed);
  assert.ok(consumer.commit_message.includes(`Source commit: ${consumer.source_commit}`));
  assert.equal(evidence.ancestry.behind_by, 0, 'delivery does not contain source repair');
  assert.equal(evidence.ancestry.merge_base_sha, source.merge_commit_sha);

  const first = evidence.first_run;
  assert.equal(first.path, WORKFLOW);
  assert.equal(first.status, 'completed');
  assert.equal(first.conclusion, 'success');
  const delivered = timestamp(consumer.regenerated_at);
  const started = timestamp(first.run_started_at);
  assert.ok(delivered < started && timestamp(first.updated_at) <= observed);
  // The retained first window is a complete, single repository page, without an
  // event filter. A workflow_dispatch-only page would miss other event types.
  const inventory = evidence.first_inventory;
  const inventoryUrl = new URL(evidence.collection.first_inventory_url);
  assert.equal(inventoryUrl.origin, 'https://api.github.com');
  assert.equal(inventoryUrl.pathname, '/repos/stranske/Workflows/actions/runs');
  assert.deepEqual([...inventoryUrl.searchParams.keys()].sort(), ['created', 'per_page']);
  assert.equal(inventoryUrl.searchParams.get('created'), `${consumer.regenerated_at}..${first.run_started_at}`);
  assert.equal(inventoryUrl.searchParams.get('per_page'), '100');
  assert.ok(inventory.total_count > 0 && inventory.total_count < 100);
  assert.equal(inventory.workflow_runs.length, inventory.total_count, 'truncated first-run inventory');
  assert.equal(new Set(inventory.workflow_runs.map(row => row.id)).size, inventory.total_count);
  const mergers = inventory.workflow_runs.filter(row => row.path === WORKFLOW);
  assert.ok(mergers.some(row => row.id === first.id), 'observed run is missing from inventory');
  for (const row of inventory.workflow_runs) {
    assert.ok(timestamp(row.created_at) >= delivered && timestamp(row.created_at) <= started);
    if (row.path === WORKFLOW) assert.ok(timestamp(row.run_started_at) >= started);
  }

  const report = evidence.delivery_report;
  assert.equal(`${report.owner}/${report.repo}`, REPOSITORY);
  assert.equal(report.pr, consumer.number);
  assert.equal(report.head_sha, consumer.head_sha, 'report is for a different consumer head');
  assert.equal(report.source_commit, consumer.source_commit, 'report is for a different source');
  assert.equal(report.review_state, 'clear');
  const findings = report.review_finding_disposition;
  assert.equal(findings.binding.repository, REPOSITORY);
  assert.equal(findings.binding.pr, consumer.number);
  assert.equal(findings.binding.head_sha, consumer.head_sha);
  assert.equal(findings.binding.source_commit, consumer.source_commit);
  assert.equal(findings.raw_active_count, 0);
  assert.equal(findings.blocked, false);
  assert.deepEqual(findings.findings, []);
  assert.deepEqual(findings.errors, []);

  assert.ok(evidence.latest_runs.length >= 3, 'missing latest three runs');
  for (const row of evidence.latest_runs) {
    assert.equal(row.path, WORKFLOW);
    assert.ok(timestamp(row.run_started_at) >= started && timestamp(row.run_started_at) <= observed);
  }
  assert.ok(Array.isArray(evidence.consumer_comments) && evidence.consumer_comments.length > 0);
  const counts = Object.values(consumer.comment_counts);
  assert.equal(counts.length, 3);
  assert.ok(counts.every(count => Number.isSafeInteger(count) && count >= 0));
  assert.equal(evidence.consumer_comments.length, counts.reduce((sum, count) => sum + count, 0),
    'incomplete consumer discussion');
  assert.equal(new Set(evidence.consumer_comments.map(row => row.id)).size, evidence.consumer_comments.length);
  for (const comment of evidence.consumer_comments) {
    const changed = timestamp(comment.updated_at || comment.created_at);
    assert.ok(changed <= observed);
    if (changed < started) continue;
    // Recognize the two original findings and Maint71's reassessment request.
    // Source-fix dispositions remain evidence, not new findings or reviewer acceptance.
    const related = comment.path === '.github/workflows/agents-auto-pilot.yml' || !comment.path;
    if (related) assert.doesNotMatch(comment.body,
      /Adding the PR label does not guarantee|The search does not test for a match|please reassess this specific finding/i,
      `known handoff finding reposted after delivery: ${comment.id}`);
  }
  const issue = evidence.source_issue;
  assert.equal(issue.number, 4366);
  assert.ok(timestamp(issue.updated_at) <= observed);
  assert.equal(issue.comment_rows.length, issue.comments, 'incomplete source-issue comments');
  assert.equal(new Set(issue.comment_rows.map(row => row.id)).size, issue.comments);
  for (const comment of issue.comment_rows) {
    const created = timestamp(comment.created_at), updated = timestamp(comment.updated_at);
    assert.ok(created <= updated && updated <= observed);
    if (comment.body.includes('<!-- sync-core/v1')) {
      assert.ok(updated < started, `sync-core bumped source issue after delivery: ${comment.id}`);
    }
  }
  return { status: 'VERIFIED', observed_at: evidence.observed_at, first_run: first.id,
    latest_run: evidence.latest_runs[0].id, consumer_head: consumer.head_sha };
}

if (require.main === module) {
  try {
    assert.equal(process.argv.length, 3, 'usage: node verify-observation.js observation.json');
    process.stdout.write(`${JSON.stringify(verify(JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))), null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`Observation unverified: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { verify };
