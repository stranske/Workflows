'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  REPORT_SCHEMA,
  analyzeTaskList,
  buildPrSourceContextReport,
  renderMarkdown,
  writeReport,
} = require('../pr_source_context_report.js');

test('analyzeTaskList counts checkbox items outside fenced code blocks by section', () => {
  const result = analyzeTaskList(`
# Scope
- [ ] wire source contract
- [x] keep existing issue links

\`\`\`
- [ ] not a task
\`\`\`

## Verification
1. [ ] run node tests
`);

  assert.equal(result.has_task_list, true);
  assert.equal(result.total, 3);
  assert.equal(result.checked, 1);
  assert.equal(result.unchecked, 2);
  assert.deepEqual(result.sections, [
    { heading: 'Scope', total: 2, checked: 1, unchecked: 1 },
    { heading: 'Verification', total: 1, checked: 0, unchecked: 1 },
  ]);
});

test('buildPrSourceContextReport skips non-PR events without failing', () => {
  const report = buildPrSourceContextReport({
    eventName: 'push',
    event: {
      repository: { full_name: 'octo/demo' },
    },
    now: '2026-04-26T22:00:00.000Z',
  });

  assert.equal(report.schema, REPORT_SCHEMA);
  assert.equal(report.status, 'skipped');
  assert.equal(report.reason, 'not-pull-request');
  assert.equal(report.repository, 'octo/demo');
  assert.equal(report.source_context.isValid, false);
});

test('buildPrSourceContextReport passes source-issue PRs', () => {
  const report = buildPrSourceContextReport({
    eventName: 'pull_request',
    event: {
      repository: { full_name: 'octo/demo' },
      pull_request: {
        number: 42,
        title: 'Implement issue work',
        body: '<!-- meta:issue:1836 -->\nRelated to campaign issue #1836',
        head: { ref: 'codex/issue-1836' },
        base: { ref: 'main' },
        user: { login: 'codex' },
        labels: [{ name: 'codex' }],
      },
    },
    now: '2026-04-26T22:00:00.000Z',
  });

  assert.equal(report.status, 'pass');
  assert.equal(report.reason, 'source-context-detected');
  assert.equal(report.source_context.sourceType, 'github_issue');
  assert.equal(report.source_context.issueNumber, 1836);
  assert.equal(report.source_context.isExplicit, true);
  assert.equal(report.task_list.has_task_list, false);
  assert.deepEqual(report.warnings, []);
});

test('buildPrSourceContextReport includes task-list contract for PR bodies', () => {
  const report = buildPrSourceContextReport({
    eventName: 'pull_request',
    event: {
      pull_request: {
        number: 43,
        title: 'Implement issue checklist',
        body: '<!-- meta:issue:1836 -->\n## Tasks\n- [ ] first\n- [x] second',
        head: { ref: 'codex/issue-1836' },
        base: { ref: 'main' },
        user: { login: 'codex' },
        labels: [{ name: 'codex' }],
      },
    },
    now: '2026-04-26T22:00:00.000Z',
  });

  assert.equal(report.task_list.has_task_list, true);
  assert.equal(report.task_list.total, 2);
  assert.equal(report.task_list.open_item_count, 1);
  assert.equal(report.task_list.sections[0].heading, 'Tasks');
});

test('buildPrSourceContextReport accepts explicit local request PRs', () => {
  const report = buildPrSourceContextReport({
    eventName: 'pull_request',
    event: {
      pull_request: {
        number: 7,
        title: 'Manual automation follow-up',
        body: '<!-- workflow-source:local_request -->\n<!-- workflow-source-ref:codex-thread-107 -->',
        head: { ref: 'codex/source-context-contract-107' },
        base: { ref: 'main' },
        user: { login: 'teacher' },
        labels: [{ name: 'codex' }],
      },
    },
    now: '2026-04-26T22:00:00.000Z',
  });

  assert.equal(report.status, 'pass');
  assert.equal(report.source_context.sourceType, 'local_request');
  assert.equal(report.source_context.sourceRef, 'codex-thread-107');
  assert.equal(report.source_context.requiresIssue, false);
});

test('buildPrSourceContextReport warns when PR source is unknown', () => {
  const report = buildPrSourceContextReport({
    eventName: 'pull_request',
    event: {
      pull_request: {
        number: 8,
        title: 'Unlinked change',
        body: 'No source context here.',
        head: { ref: 'feature/no-source' },
        base: { ref: 'main' },
        user: { login: 'teacher' },
        labels: [],
      },
    },
    now: '2026-04-26T22:00:00.000Z',
  });

  assert.equal(report.status, 'warning');
  assert.equal(report.reason, 'source-context-unknown');
  assert.equal(report.source_context.sourceType, 'unknown');
  assert.match(report.warnings[0], /No source issue/);
});

test('buildPrSourceContextReport reports inferred maintenance origins as warnings', () => {
  const report = buildPrSourceContextReport({
    eventName: 'pull_request',
    event: {
      pull_request: {
        number: 9,
        title: 'sync workflow templates',
        body: '',
        head: { ref: 'sync/workflows-abcdef' },
        base: { ref: 'main' },
        user: { login: 'github-actions[bot]' },
        labels: [{ name: 'campaign:sync-dependabot' }],
      },
    },
    now: '2026-04-26T22:00:00.000Z',
  });

  assert.equal(report.status, 'pass');
  assert.equal(report.source_context.sourceType, 'sync_campaign');
  assert.equal(report.source_context.isExplicit, false);
  assert.match(report.warnings[0], /inferred from PR metadata/);
});

test('renderMarkdown and writeReport publish human and machine-readable contracts', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'pr-source-context-'));
  const outputJson = path.join(tmpDir, 'nested', 'report.json');
  const outputMd = path.join(tmpDir, 'nested', 'report.md');
  const report = buildPrSourceContextReport({
    eventName: 'pull_request',
    event: {
      pull_request: {
        number: 10,
        title: 'Local request',
        body: '<!-- workflow-source:local_request -->',
        head: { ref: 'codex/local' },
        base: { ref: 'main' },
        user: { login: 'teacher' },
        labels: [],
      },
    },
    now: '2026-04-26T22:00:00.000Z',
  });

  writeReport(report, { outputJson, outputMd });

  const parsed = JSON.parse(fs.readFileSync(outputJson, 'utf8'));
  const markdown = fs.readFileSync(outputMd, 'utf8');

  assert.equal(parsed.schema, REPORT_SCHEMA);
  assert.match(renderMarkdown(report), /PR Source Context/);
  assert.match(markdown, /Schema: `workflows-pr-source-context\/v1`/);
});
