const test = require('node:test');
const assert = require('node:assert/strict');

const {
  selectBestCandidate,
  issueMentionPatterns,
  candidateScore,
} = require('../issue_pr_locator.js');

function buildCandidate(overrides) {
  return {
    number: overrides.number || 1,
    headRef: overrides.headRef || 'codex/issue-1',
    baseRef: overrides.baseRef || 'phase-2-dev',
    body: overrides.body || '',
    title: overrides.title || '',
    draft: Boolean(overrides.draft),
    state: overrides.state || 'open',
    updatedAt: overrides.updatedAt || new Date().toISOString(),
    branchMatch: Boolean(overrides.branchMatch),
    crossReference: Boolean(overrides.crossReference),
    bodyMentionsIssue: Boolean(overrides.bodyMentionsIssue),
    titleMentionsIssue: Boolean(overrides.titleMentionsIssue),
    labelMatch: Boolean(overrides.labelMatch),
    baseIsDefault: Boolean(overrides.baseIsDefault ?? true),
  };
}

test('selectBestCandidate prefers branch match', () => {
  const branchCandidate = buildCandidate({ number: 1, branchMatch: true, updatedAt: '2025-11-01T00:00:00Z' });
  const mentionCandidate = buildCandidate({ number: 2, bodyMentionsIssue: true, updatedAt: '2025-11-05T00:00:00Z' });
  const best = selectBestCandidate([mentionCandidate, branchCandidate], { issueNumber: 3842 });
  assert.equal(best.number, 1);
});

test('candidateScore rewards cross references and mentions', () => {
  const base = buildCandidate({ number: 1, crossReference: true, bodyMentionsIssue: true, labelMatch: true, updatedAt: '2025-11-03T00:00:00Z' });
  const { score } = candidateScore(base, { issueNumber: 9999 });
  assert(score > 0, 'score should be positive when evidence is present');
});

test('issueMentionPatterns detect references with or without hash', () => {
  const patterns = issueMentionPatterns(1234);
  assert.ok(patterns.length >= 2);
  assert(patterns.some((regex) => regex.test('Fixes #1234')));
  assert(patterns.some((regex) => regex.test('Issue 1234 needs triage')));
});

test('selectBestCandidate falls back to newest when scores tie', () => {
  const older = buildCandidate({ number: 1, bodyMentionsIssue: true, updatedAt: '2025-11-01T00:00:00Z' });
  const newer = buildCandidate({ number: 2, bodyMentionsIssue: true, updatedAt: '2025-11-10T00:00:00Z' });
  const best = selectBestCandidate([older, newer], { issueNumber: 99 });
  assert.equal(best.number, 2);
});
