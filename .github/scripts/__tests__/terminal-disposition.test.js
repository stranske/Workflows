const test = require('node:test');
const assert = require('node:assert/strict');

const {
  normalizeTerminalDisposition,
  summarizeTerminalDispositionSources,
  formatTerminalDispositionMarkdown,
  sourceKey,
} = require('../terminal_disposition.js');

test('normalizes terminal disposition records with stable source keys', () => {
  const record = normalizeTerminalDisposition({
    sourceType: 'Source Issue',
    sourceId: 42,
    prNumber: '101',
    issueNumber: '42',
    disposition: 'follow-up-created',
    followupIssueNumber: 105,
    reason: '  Dispatch completed  ',
    dispatchOutcome: ' success ',
    artifactName: 'verifier-terminal-disposition-123',
    artifactFamily: 'verifier-terminal-disposition',
    needsHuman: false,
    timestamp: '2026-04-25T00:00:00Z',
  });

  assert.equal(record.schema, 'workflows-terminal-disposition/v1');
  assert.equal(record.metric_type, 'verifier_terminal_disposition');
  assert.equal(record.source_type, 'source-issue');
  assert.equal(record.source_id, '42');
  assert.equal(record.source_key, 'source-issue:42');
  assert.equal(record.pr_number, 101);
  assert.equal(record.issue_number, 42);
  assert.equal(record.followup_issue_number, 105);
  assert.equal(record.reason, 'Dispatch completed');
  assert.equal(record.dispatch_outcome, 'success');
  assert.equal(record.artifact_name, 'verifier-terminal-disposition-123');
  assert.equal(record.artifact_family, 'verifier-terminal-disposition');
  assert.equal(record.needs_human, false);
});

test('sourceKey falls back to unknown for blank values', () => {
  assert.equal(sourceKey('', ''), 'unknown:unknown');
});

test('summarizes terminal dispositions by source', () => {
  const summary = summarizeTerminalDispositionSources([
    { source_type: 'source-issue', source_id: 7, disposition: 'follow-up-created', pr_number: 11 },
    { source_type: 'source-issue', source_id: 7, disposition: 'needs-human', pr_number: 12 },
    { source_type: 'review-thread', source_id: 12, disposition: 'unresolved-bot-comments', pr_number: 12 },
  ]);

  assert.deepEqual(summary, [
    {
      source_type: 'review-thread',
      source_id: '12',
      total: 1,
      dispositions: { 'unresolved-bot-comments': 1 },
      pr_numbers: [12],
      issue_numbers: [],
    },
    {
      source_type: 'source-issue',
      source_id: '7',
      total: 2,
      dispositions: { 'follow-up-created': 1, 'needs-human': 1 },
      pr_numbers: [11, 12],
      issue_numbers: [],
    },
  ]);
});

test('formats terminal disposition summary as markdown', () => {
  const markdown = formatTerminalDispositionMarkdown([
    { source_type: 'source-issue', source_id: 7, disposition: 'follow-up-created', pr_number: 11 },
  ]);

  assert.match(markdown, /Source/);
  assert.match(markdown, /source-issue:7/);
  assert.match(markdown, /follow-up-created \(1\)/);
  assert.match(markdown, /#11/);
});
