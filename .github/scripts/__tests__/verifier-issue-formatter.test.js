'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const {
  formatFollowUpIssue,
  formatSimpleFollowUpIssue,
  formatSourceSection,
  parseVerifierFindings,
  extractUncheckedItems,
  extractCheckedItems,
  buildChecklist,
} = require('../verifier_issue_formatter.js');

describe('verifier_issue_formatter', () => {
  describe('formatSourceSection', () => {
    it('includes PR link when provided', () => {
      const result = formatSourceSection({
        prNumber: 123,
        prUrl: 'https://github.com/owner/repo/pull/123',
      });
      assert.ok(result.includes('Original PR:'));
      assert.ok(result.includes('[#123]'));
      assert.ok(result.includes('https://github.com/owner/repo/pull/123'));
    });

    it('uses plain reference when URL not provided', () => {
      const result = formatSourceSection({ prNumber: 123 });
      assert.ok(result.includes('Original PR: #123'));
      assert.ok(!result.includes('[#123]'));
    });

    it('includes parent issues', () => {
      const result = formatSourceSection({
        prNumber: 123,
        issueNumbers: [100, 101],
      });
      assert.ok(result.includes('Parent issues: #100, #101'));
    });

    it('uses singular for single parent issue', () => {
      const result = formatSourceSection({
        prNumber: 123,
        issueNumbers: [100],
      });
      assert.ok(result.includes('Parent issue: #100'));
      assert.ok(!result.includes('Parent issues'));
    });

    it('includes verdict', () => {
      const result = formatSourceSection({
        prNumber: 123,
        verdict: 'fail',
      });
      assert.ok(result.includes('Verifier verdict: FAIL'));
    });

    it('includes workflow run link', () => {
      const result = formatSourceSection({
        prNumber: 123,
        runUrl: 'https://github.com/owner/repo/actions/runs/123',
      });
      assert.ok(result.includes('[workflow run]'));
      assert.ok(result.includes('https://github.com/owner/repo/actions/runs/123'));
    });
  });

  describe('parseVerifierFindings', () => {
    it('extracts pass verdict', () => {
      const output = 'Verdict: PASS\n\nAll criteria met.';
      const findings = parseVerifierFindings(output);
      assert.equal(findings.verdict, 'pass');
    });

    it('extracts fail verdict (case insensitive)', () => {
      const output = 'verdict: Fail\n\nSome issues found.';
      const findings = parseVerifierFindings(output);
      assert.equal(findings.verdict, 'fail');
    });

    it('returns unknown for missing verdict', () => {
      const output = 'Some random text without verdict.';
      const findings = parseVerifierFindings(output);
      assert.equal(findings.verdict, 'unknown');
    });

    it('extracts gaps from blocking section', () => {
      const output = `Verdict: FAIL

Blocking gaps:
- Missing test coverage
- API returns wrong status code`;
      const findings = parseVerifierFindings(output);
      assert.ok(findings.gaps.includes('Missing test coverage'));
      assert.ok(findings.gaps.includes('API returns wrong status code'));
    });

    it('extracts summary after verdict', () => {
      const output = `Verdict: FAIL

The implementation is incomplete.
Several edge cases are not handled.

- Gap 1
- Gap 2`;
      const findings = parseVerifierFindings(output);
      assert.ok(findings.summary.includes('implementation is incomplete'));
    });

    it('parses structured Criteria Status section', () => {
      const output = `Verdict: FAIL

## Criteria Status
- [x] Tests pass - VERIFIED (all 30 tests pass)
- [ ] Error handling works - NOT MET (missing retry logic)
- [x] Documentation updated - VERIFIED (README updated)
- [ ] Coverage above 80% - NOT MET (currently at 65%)

Blocking gaps:
- Retry logic not implemented
`;
      const findings = parseVerifierFindings(output);
      assert.equal(findings.verdict, 'fail');
      assert.deepEqual(findings.unmetCriteria, ['Error handling works', 'Coverage above 80%']);
      assert.deepEqual(findings.verifiedCriteria, ['Tests pass', 'Documentation updated']);
    });

    it('handles Criteria Status with bold header', () => {
      const output = `Verdict: FAIL

**Criteria Status**
- [x] First criterion - VERIFIED
- [ ] Second criterion - NOT MET (reason here)
`;
      const findings = parseVerifierFindings(output);
      assert.deepEqual(findings.unmetCriteria, ['Second criterion']);
      assert.deepEqual(findings.verifiedCriteria, ['First criterion']);
    });
  });

  describe('extractUncheckedItems', () => {
    it('extracts unchecked items', () => {
      const content = `- [ ] First task
- [x] Completed task
- [ ] Second task`;
      const items = extractUncheckedItems(content);
      assert.deepEqual(items, ['First task', 'Second task']);
    });

    it('handles asterisk bullets', () => {
      const content = `* [ ] Task one
* [x] Done
* [ ] Task two`;
      const items = extractUncheckedItems(content);
      assert.deepEqual(items, ['Task one', 'Task two']);
    });

    it('handles indented items', () => {
      const content = `- [ ] Parent task
  - [ ] Sub-task`;
      const items = extractUncheckedItems(content);
      assert.equal(items.length, 2);
      assert.ok(items.includes('Parent task'));
      assert.ok(items.includes('Sub-task'));
    });

    it('returns empty array for no checkboxes', () => {
      const content = 'Just some text without checkboxes';
      const items = extractUncheckedItems(content);
      assert.deepEqual(items, []);
    });
  });

  describe('extractCheckedItems', () => {
    it('extracts checked items', () => {
      const content = `- [ ] Unchecked
- [x] First done
- [X] Second done`;
      const items = extractCheckedItems(content);
      assert.deepEqual(items, ['First done', 'Second done']);
    });

    it('handles empty content', () => {
      const items = extractCheckedItems('');
      assert.deepEqual(items, []);
    });

    it('handles null content', () => {
      const items = extractCheckedItems(null);
      assert.deepEqual(items, []);
    });
  });

  describe('buildChecklist', () => {
    it('builds unchecked checklist', () => {
      const items = ['Task one', 'Task two'];
      const result = buildChecklist(items);
      assert.equal(result, '- [ ] Task one\n- [ ] Task two');
    });

    it('returns empty string for empty array', () => {
      const result = buildChecklist([]);
      assert.equal(result, '');
    });

    it('returns empty string for non-array', () => {
      const result = buildChecklist(null);
      assert.equal(result, '');
    });
  });

  describe('formatFollowUpIssue', () => {
    const verifierOutput = `Verdict: FAIL

The error handling is incomplete.

Blocking:
- Missing retry logic for rate limits
- No backoff delay implementation`;

    const prBody = `## Scope
Implement error handling.

## Tasks
- [x] Add error classifier
- [ ] Add retry logic
- [x] Add tests

## Acceptance Criteria
- [ ] Retry logic handles rate limits
- [ ] Tests cover all error paths`;

    const issue = {
      number: 100,
      title: 'Error handling',
      body: `## Why
We need better error handling.

## Non-Goals
- Changing existing behavior

## Scope
Error classification and recovery.

## Tasks
- [ ] Create error module
- [ ] Add retry wrapper

## Acceptance Criteria
- [ ] Errors are classified
- [ ] Retries use exponential backoff`,
    };

    it('generates title with PR number', () => {
      const result = formatFollowUpIssue({
        verifierOutput,
        prBody,
        issues: [issue],
        prNumber: 123,
      });
      assert.ok(result.title.includes('PR #123'));
      assert.ok(result.title.includes('Follow-up'));
    });

    it('includes source section with links', () => {
      const result = formatFollowUpIssue({
        verifierOutput,
        prBody,
        issues: [issue],
        prNumber: 123,
        prUrl: 'https://github.com/test/repo/pull/123',
        runUrl: 'https://github.com/test/repo/actions/runs/456',
      });
      assert.ok(result.body.includes('## Source'));
      assert.ok(result.body.includes('#123'));
      assert.ok(result.body.includes('#100'));
    });

    it('preserves Why section from parent issue', () => {
      const result = formatFollowUpIssue({
        verifierOutput,
        prBody,
        issues: [issue],
        prNumber: 123,
      });
      assert.ok(result.body.includes('## Why'));
      assert.ok(result.body.includes('better error handling'));
    });

    it('preserves Non-Goals section', () => {
      const result = formatFollowUpIssue({
        verifierOutput,
        prBody,
        issues: [issue],
        prNumber: 123,
      });
      assert.ok(result.body.includes('## Non-Goals'));
      assert.ok(result.body.includes('Changing existing behavior'));
    });

    it('includes unmet acceptance criteria', () => {
      const result = formatFollowUpIssue({
        verifierOutput,
        prBody,
        issues: [issue],
        prNumber: 123,
      });
      assert.ok(result.body.includes('## Acceptance Criteria'));
      assert.ok(result.body.includes('Retry logic handles rate limits'));
    });

    it('copies incomplete tasks', () => {
      const result = formatFollowUpIssue({
        verifierOutput,
        prBody,
        issues: [issue],
        prNumber: 123,
      });
      assert.ok(result.body.includes('## Tasks'));
      assert.ok(result.body.includes('Add retry logic'));
    });

    it('generates tasks from gaps when all tasks complete', () => {
      const allTasksComplete = `## Tasks
- [x] Task one
- [x] Task two

## Acceptance Criteria
- [ ] Criterion not met`;

      const result = formatFollowUpIssue({
        verifierOutput,
        prBody: allTasksComplete,
        issues: [],
        prNumber: 123,
      });
      // Should generate tasks from verifier gaps
      assert.ok(result.newTasks.length > 0);
    });

    it('includes implementation notes with summary', () => {
      const result = formatFollowUpIssue({
        verifierOutput,
        prBody,
        issues: [issue],
        prNumber: 123,
      });
      assert.ok(result.body.includes('## Implementation Notes'));
      assert.ok(result.body.includes('error handling is incomplete'));
    });

    it('returns parsed findings', () => {
      const result = formatFollowUpIssue({
        verifierOutput,
        prBody,
        issues: [issue],
        prNumber: 123,
      });
      assert.equal(result.findings.verdict, 'fail');
      assert.ok(result.findings.gaps.length > 0);
    });

    it('uses verifier unmet criteria to filter acceptance criteria', () => {
      // Verifier explicitly says which criteria are not met
      const structuredVerifierOutput = `Verdict: FAIL

## Criteria Status
- [x] Retry logic handles rate limits - VERIFIED (code exists)
- [ ] Tests cover all error paths - NOT MET (missing coverage)
- [x] Error messages are helpful - VERIFIED (messages include guidance)
`;

      const prBodyWithCriteria = `## Tasks
- [x] All tasks done

## Acceptance Criteria
- [ ] Retry logic handles rate limits
- [ ] Tests cover all error paths
- [ ] Error messages are helpful`;

      const result = formatFollowUpIssue({
        verifierOutput: structuredVerifierOutput,
        prBody: prBodyWithCriteria,
        issues: [],
        prNumber: 200,
      });

      // Should only include the criterion that was NOT MET in the refined list
      assert.deepEqual(result.unmetCriteria, ['Tests cover all error paths']);
      
      // The Acceptance Criteria section should only have the unmet criterion
      const acceptanceSection = result.body.split('## Acceptance Criteria')[1].split('## ')[0];
      assert.ok(acceptanceSection.includes('Tests cover all error paths'));
      assert.ok(!acceptanceSection.includes('- [ ] Retry logic handles rate limits'));
      assert.ok(!acceptanceSection.includes('- [ ] Error messages are helpful'));
      
      // Verified criteria should appear in Implementation Notes, not Acceptance Criteria
      const notesSection = result.body.split('## Implementation Notes')[1] || '';
      assert.ok(notesSection.includes('Retry logic handles rate limits'));
    });

    it('includes verified criteria in implementation notes', () => {
      const structuredVerifierOutput = `Verdict: FAIL

## Criteria Status
- [x] First criterion - VERIFIED (evidence)
- [ ] Second criterion - NOT MET (missing)
`;

      const prBodyWithCriteria = `## Tasks
- [x] Done

## Acceptance Criteria
- [ ] First criterion
- [ ] Second criterion`;

      const result = formatFollowUpIssue({
        verifierOutput: structuredVerifierOutput,
        prBody: prBodyWithCriteria,
        issues: [],
        prNumber: 201,
      });

      // Implementation notes should mention what was verified
      assert.ok(result.body.includes('Verifier confirmed these criteria were met'));
      assert.ok(result.body.includes('✓ First criterion'));
    });
  });

  describe('formatSimpleFollowUpIssue', () => {
    const verifierOutput = `Verdict: FAIL

Something went wrong.`;

    it('includes verifier output in code block', () => {
      const result = formatSimpleFollowUpIssue({
        verifierOutput,
        prNumber: 123,
      });
      assert.ok(result.body.includes('```'));
      assert.ok(result.body.includes('Something went wrong'));
    });

    it('includes basic tasks', () => {
      const result = formatSimpleFollowUpIssue({
        verifierOutput,
        prNumber: 123,
      });
      assert.ok(result.body.includes('## Tasks'));
      assert.ok(result.body.includes('Review verifier output'));
      assert.ok(result.body.includes('Address identified gaps'));
    });

    it('includes acceptance criteria for re-verification', () => {
      const result = formatSimpleFollowUpIssue({
        verifierOutput,
        prNumber: 123,
      });
      assert.ok(result.body.includes('## Acceptance Criteria'));
      assert.ok(result.body.includes('Verifier passes'));
    });

    it('generates appropriate title', () => {
      const result = formatSimpleFollowUpIssue({
        verifierOutput,
        prNumber: 123,
      });
      assert.ok(result.title.includes('PR #123'));
    });

    it('handles missing PR number', () => {
      const result = formatSimpleFollowUpIssue({
        verifierOutput,
      });
      assert.ok(result.title.includes('Verifier failure'));
      assert.ok(!result.title.includes('PR #'));
    });
  });
});
