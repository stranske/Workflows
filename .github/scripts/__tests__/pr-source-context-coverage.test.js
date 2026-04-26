'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  COVERAGE_SCHEMA,
  buildCoverageReport,
  shouldFail,
} = require('../pr_source_context_coverage.js');

function writeReport(root, artifactName, report) {
  const dir = path.join(root, artifactName, '123');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'pr-source-context.json'), `${JSON.stringify(report)}\n`);
}

test('buildCoverageReport summarizes PR source context and task-list artifacts', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pr-source-context-coverage-'));
  writeReport(root, 'pr-source-context', {
    schema: 'workflows-pr-source-context/v1',
    status: 'pass',
    reason: 'source-context-detected',
    pull_request: { number: 12, title: 'Implement source contract', head_ref: 'codex/source' },
    source_context: { sourceType: 'local_request', isValid: true, isExplicit: true },
    task_list: { has_task_list: true, total: 3, checked: 1, unchecked: 2, open_item_count: 2 },
  });
  writeReport(root, 'pr-source-context-2', {
    schema: 'workflows-pr-source-context/v1',
    status: 'warning',
    reason: 'source-context-unknown',
    pull_request: { number: 13, title: 'Missing context', head_ref: 'feature/no-source' },
    source_context: { sourceType: 'unknown', isValid: false, isExplicit: false },
    task_list: { has_task_list: false, total: 0, checked: 0, unchecked: 0, open_item_count: 0 },
  });

  const report = buildCoverageReport({ root, now: '2026-04-26T23:00:00.000Z' });

  assert.equal(report.schema, COVERAGE_SCHEMA);
  assert.equal(report.status, 'warning');
  assert.equal(report.records, 2);
  assert.equal(report.valid_source_context_count, 1);
  assert.equal(report.unknown_source_context_count, 1);
  assert.equal(report.task_items_total, 3);
  assert.equal(report.task_items_open, 2);
  assert.deepEqual(report.source_type_counts, { local_request: 1, unknown: 1 });
  assert.equal(report.open_task_prs[0].number, 12);
  assert.equal(report.unknown_source_prs[0].number, 13);
});

test('shouldFail only hard-blocks when explicitly approved', () => {
  const report = { status: 'warning' };
  assert.equal(shouldFail(report, {}), false);
  assert.equal(shouldFail(report, { PR_SOURCE_CONTEXT_COVERAGE_MODE: 'hard-block' }), false);
  assert.equal(
    shouldFail(report, {
      PR_SOURCE_CONTEXT_COVERAGE_MODE: 'hard-block',
      PR_SOURCE_CONTEXT_HARD_BLOCK_APPROVED: 'true',
    }),
    true,
  );
});
