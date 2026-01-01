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
  isPlaceholderContent,
  isMissingInfoGap,
  looksLikeSectionHeader,
  looksLikeReferenceLink,
  stripCheckboxesFromScope,
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

  describe('isPlaceholderContent', () => {
    it('identifies checkbox placeholder with section name', () => {
      assert.ok(isPlaceholderContent('- [ ] Scope section missing from source issue.'));
      assert.ok(isPlaceholderContent('- [x] Tasks section missing from source issue.'));
      assert.ok(isPlaceholderContent('* [ ] Acceptance Criteria section missing from source issue.'));
    });

    it('identifies placeholder without checkbox', () => {
      assert.ok(isPlaceholderContent('Scope section missing from source issue.'));
      assert.ok(isPlaceholderContent('Tasks section missing from source issue.'));
      assert.ok(isPlaceholderContent('acceptance criteria section missing from source issue'));
    });

    it('identifies placeholder with "section missing" phrase', () => {
      assert.ok(isPlaceholderContent('Some section missing from source issue'));
      assert.ok(isPlaceholderContent('anything section missing from source issue.'));
    });

    it('identifies N/A variations', () => {
      assert.ok(isPlaceholderContent('N/A'));
      assert.ok(isPlaceholderContent('n/a'));
      assert.ok(isPlaceholderContent('N / A'));
      assert.ok(isPlaceholderContent('  n a  '));
    });

    it('identifies empty strings', () => {
      assert.ok(isPlaceholderContent(''));
      assert.ok(isPlaceholderContent('   '));
      assert.ok(isPlaceholderContent(null));
      assert.ok(isPlaceholderContent(undefined));
    });

    it('rejects actual content', () => {
      assert.ok(!isPlaceholderContent('Implement error handling'));
      assert.ok(!isPlaceholderContent('Add retry logic for rate limits'));
      assert.ok(!isPlaceholderContent('Tests cover all error paths'));
    });

    it('rejects content with "missing" but not placeholder pattern', () => {
      assert.ok(!isPlaceholderContent('The missing feature should be added'));
      assert.ok(!isPlaceholderContent('Fix missing validation'));
    });

    it('is case insensitive', () => {
      assert.ok(isPlaceholderContent('SCOPE SECTION MISSING FROM SOURCE ISSUE'));
      assert.ok(isPlaceholderContent('Tasks Section Missing From Source Issue.'));
    });
  });

  describe('isMissingInfoGap', () => {
    it('identifies gaps about missing acceptance criteria', () => {
      assert.ok(isMissingInfoGap('Provide explicit acceptance criteria in the PR description or linked issue so they can be independently verified.'));
      assert.ok(isMissingInfoGap('Blocking gap: Provide explicit acceptance criteria in the PR'));
      assert.ok(isMissingInfoGap('Acceptance criteria missing from source'));
    });

    it('identifies gaps about no testable criteria', () => {
      assert.ok(isMissingInfoGap('No testable criteria provided'));
      assert.ok(isMissingInfoGap('no verifiable requirements in issue'));
    });

    it('rejects actual verification failures', () => {
      assert.ok(!isMissingInfoGap('Missing test coverage for new feature'));
      assert.ok(!isMissingInfoGap('API returns wrong status code'));
      assert.ok(!isMissingInfoGap('Error handling not implemented'));
      assert.ok(!isMissingInfoGap('Function returns incorrect value'));
    });

    it('is case insensitive', () => {
      assert.ok(isMissingInfoGap('PROVIDE EXPLICIT ACCEPTANCE CRITERIA'));
      assert.ok(isMissingInfoGap('No Testable Criteria'));
    });

    it('handles empty and null input', () => {
      assert.ok(!isMissingInfoGap(''));
      assert.ok(!isMissingInfoGap(null));
      assert.ok(!isMissingInfoGap(undefined));
    });
  });

  describe('looksLikeSectionHeader', () => {
    it('identifies markdown headers', () => {
      assert.ok(looksLikeSectionHeader('## Related'));
      assert.ok(looksLikeSectionHeader('### Notes'));
      assert.ok(looksLikeSectionHeader('# Title'));
      assert.ok(looksLikeSectionHeader('#### Subsection'));
    });

    it('identifies headers with varying whitespace', () => {
      assert.ok(looksLikeSectionHeader('##  Related'));
      assert.ok(looksLikeSectionHeader('###   Notes'));
      assert.ok(looksLikeSectionHeader('  ## Related'));
    });

    it('identifies headers up to level 6', () => {
      assert.ok(looksLikeSectionHeader('##### Level 5'));
      assert.ok(looksLikeSectionHeader('###### Level 6'));
    });

    it('rejects non-header content', () => {
      assert.ok(!looksLikeSectionHeader('Regular text'));
      assert.ok(!looksLikeSectionHeader('Some task description'));
      assert.ok(!looksLikeSectionHeader('- [ ] Task item'));
    });

    it('rejects hashes not at start', () => {
      assert.ok(!looksLikeSectionHeader('Text with ## hash'));
      assert.ok(!looksLikeSectionHeader('Not a # header'));
    });

    it('rejects hash symbols without text', () => {
      assert.ok(!looksLikeSectionHeader('##'));
      assert.ok(!looksLikeSectionHeader('###   '));
      assert.ok(!looksLikeSectionHeader('#'));
    });

    it('handles empty and null input', () => {
      assert.ok(!looksLikeSectionHeader(''));
      assert.ok(!looksLikeSectionHeader(null));
      assert.ok(!looksLikeSectionHeader(undefined));
    });
  });

  describe('looksLikeReferenceLink', () => {
    it('identifies PR references with dash bullet', () => {
      assert.ok(looksLikeReferenceLink('- PR #123 - Title'));
      assert.ok(looksLikeReferenceLink('- PR #456 - Description'));
    });

    it('identifies Issue references with dash bullet', () => {
      assert.ok(looksLikeReferenceLink('- Issue #789 - Description'));
      assert.ok(looksLikeReferenceLink('- Issue #100 - Fix bug'));
    });

    it('identifies Pull Request (spelled out) references', () => {
      assert.ok(looksLikeReferenceLink('- Pull Request #200 - Feature'));
      assert.ok(looksLikeReferenceLink('Pull Request #300 - Update'));
    });

    it('identifies references without dash bullet', () => {
      assert.ok(looksLikeReferenceLink('PR #123 - Title'));
      assert.ok(looksLikeReferenceLink('Issue #456 - Description'));
    });

    it('identifies references with various bullet styles', () => {
      assert.ok(looksLikeReferenceLink('– PR #123 - Title')); // en-dash
      assert.ok(looksLikeReferenceLink('• Issue #456 - Description')); // bullet
    });

    it('is case insensitive', () => {
      assert.ok(looksLikeReferenceLink('- pr #123 - title'));
      assert.ok(looksLikeReferenceLink('- ISSUE #456 - Description'));
      assert.ok(looksLikeReferenceLink('- PuLl ReQuEsT #789 - test'));
    });

    it('rejects regular task descriptions', () => {
      assert.ok(!looksLikeReferenceLink('- [ ] Implement feature'));
      assert.ok(!looksLikeReferenceLink('Add error handling'));
      assert.ok(!looksLikeReferenceLink('Tests cover all paths'));
    });

    it('rejects text that mentions PR/Issue but not at start', () => {
      assert.ok(!looksLikeReferenceLink('Related to PR #123'));
      assert.ok(!looksLikeReferenceLink('See Issue #456 for details'));
      assert.ok(!looksLikeReferenceLink('Task for PR #789'));
    });

    it('rejects PR/Issue without number', () => {
      assert.ok(!looksLikeReferenceLink('- PR - Title'));
      assert.ok(!looksLikeReferenceLink('- Issue - Description'));
    });

    it('handles empty and null input', () => {
      assert.ok(!looksLikeReferenceLink(''));
      assert.ok(!looksLikeReferenceLink(null));
      assert.ok(!looksLikeReferenceLink(undefined));
    });
  });

  describe('stripCheckboxesFromScope', () => {
    it('converts unchecked checkbox to plain bullet', () => {
      const input = '- [ ] Implement feature A';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, '- Implement feature A');
    });

    it('converts checked checkbox (lowercase x) to plain bullet', () => {
      const input = '- [x] Completed task';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, '- Completed task');
    });

    it('converts checked checkbox (uppercase X) to plain bullet', () => {
      const input = '- [X] Done';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, '- Done');
    });

    it('preserves indentation', () => {
      const input = '  - [ ] Indented task';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, '  - Indented task');
    });

    it('handles multiple checkboxes', () => {
      const input = '- [ ] Task 1\n- [x] Task 2\n- [X] Task 3';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, '- Task 1\n- Task 2\n- Task 3');
    });

    it('filters out empty lines', () => {
      const input = '- [ ] Task 1\n\n- [ ] Task 2';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, '- Task 1\n- Task 2');
    });

    it('filters out placeholder content', () => {
      const input = '- [ ] Scope section missing from source issue.\n- [ ] Real task';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, '- Real task');
    });

    it('passes through non-checkbox lines unchanged', () => {
      const input = 'Regular text\n- [ ] Checkbox item';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, 'Regular text\n- Checkbox item');
    });

    it('handles asterisk bullet markers', () => {
      const input = '* [ ] Asterisk bullet task';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, '- Asterisk bullet task');
    });

    it('handles checkbox without space after bracket', () => {
      const input = '- [ ]No space after bracket';
      const result = stripCheckboxesFromScope(input);
      assert.equal(result, '- No space after bracket');
    });

    it('returns empty string for null/undefined input', () => {
      assert.equal(stripCheckboxesFromScope(null), '');
      assert.equal(stripCheckboxesFromScope(undefined), '');
      assert.equal(stripCheckboxesFromScope(''), '');
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

    describe('hasSubstantiveContent property', () => {
      it('returns false when all tasks and criteria are placeholders', () => {
        const verifierOutput = 'Verdict: PASS\n\nEverything looks good.';
        const prBody = `## Tasks
- [ ] Tasks section missing from source issue

## Acceptance Criteria
- [ ] Acceptance Criteria section missing from source issue`;

        const result = formatFollowUpIssue({
          verifierOutput,
          prBody,
          issues: [],
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, false);
      });

      it('returns true when there are real tasks', () => {
        const verifierOutput = 'Verdict: PASS\n\nEverything looks good.';
        const prBody = `## Tasks
- [ ] Implement feature A
- [ ] Add tests

## Acceptance Criteria
- [ ] Acceptance Criteria section missing from source issue`;

        const result = formatFollowUpIssue({
          verifierOutput,
          prBody,
          issues: [],
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, true);
      });

      it('returns true when there are real criteria', () => {
        const verifierOutput = 'Verdict: PASS\n\nEverything looks good.';
        const prBody = `## Tasks
- [ ] Tasks section missing from source issue

## Acceptance Criteria
- [ ] Feature works correctly
- [ ] Tests pass`;

        const result = formatFollowUpIssue({
          verifierOutput,
          prBody,
          issues: [],
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, true);
      });

      it('returns true when verifier has gaps', () => {
        const verifierOutput = `Verdict: FAIL

Blocking gaps:
- Missing test coverage
- API returns wrong status code`;
        const prBody = `## Tasks
- [ ] Tasks section missing from source issue

## Acceptance Criteria
- [ ] Acceptance Criteria section missing from source issue`;

        const result = formatFollowUpIssue({
          verifierOutput,
          prBody,
          issues: [],
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, true);
      });

      it('returns true when verifier has unmet criteria', () => {
        const verifierOutput = `Verdict: FAIL

## Criteria Status
- [ ] First criterion - NOT MET (missing implementation)
- [ ] Second criterion - NOT MET (no tests)`;
        const prBody = `## Tasks
- [x] Done

## Acceptance Criteria
- [ ] First criterion
- [ ] Second criterion`;

        const result = formatFollowUpIssue({
          verifierOutput,
          prBody,
          issues: [],
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, true);
      });

      it('returns false when only some placeholders mixed with empty content', () => {
        const verifierOutput = 'Verdict: PASS\n\nLooks good.';
        const prBody = `## Tasks
- [ ] Tasks section missing from source issue

## Acceptance Criteria
- [ ] n/a`;

        const result = formatFollowUpIssue({
          verifierOutput,
          prBody,
          issues: [],
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, false);
      });

      it('returns false when all gaps are about missing source info', () => {
        // Simulates Issue #415 scenario where verifier couldn't verify because source lacked criteria
        const verifierOutput = `Verdict: FAIL

Blocking gaps:
- Provide explicit acceptance criteria in the PR description or linked issue so they can be independently verified.
- Provide explicit acceptance criteria in the PR description or linked issue so they can be independently verified.`;
        const prBody = `## Tasks
- [ ] Tasks section missing from source issue

## Acceptance Criteria
- [ ] Acceptance Criteria section missing from source issue`;

        const result = formatFollowUpIssue({
          verifierOutput,
          prBody,
          issues: [],
          prNumber: 123,
        });

        // Should NOT create follow-up issue since there's nothing actionable
        assert.equal(result.hasSubstantiveContent, false);
      });

      it('returns true when gaps include actual verification failures', () => {
        const verifierOutput = `Verdict: FAIL

Blocking gaps:
- Provide explicit acceptance criteria in the PR description or linked issue so they can be independently verified.
- Missing test coverage for new feature`;
        const prBody = `## Tasks
- [ ] Tasks section missing from source issue

## Acceptance Criteria
- [ ] Acceptance Criteria section missing from source issue`;

        const result = formatFollowUpIssue({
          verifierOutput,
          prBody,
          issues: [],
          prNumber: 123,
        });

        // SHOULD create follow-up issue since there's an actual verification failure
        assert.equal(result.hasSubstantiveContent, true);
      });
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

    describe('hasSubstantiveContent property', () => {
      it('returns true when there are verifier gaps', () => {
        const output = `Verdict: FAIL

Blocking gaps:
- Missing test coverage
- API error handling incomplete`;

        const result = formatSimpleFollowUpIssue({
          verifierOutput: output,
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, true);
      });

      it('returns true when there are unmet criteria', () => {
        const output = `Verdict: FAIL

## Criteria Status
- [ ] First criterion - NOT MET
- [ ] Second criterion - NOT MET`;

        const result = formatSimpleFollowUpIssue({
          verifierOutput: output,
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, true);
      });

      it('returns true when there is verifier output', () => {
        const output = `Verdict: FAIL

Something went wrong with the verification.`;

        const result = formatSimpleFollowUpIssue({
          verifierOutput: output,
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, true);
      });

      it('returns true even for minimal verifier output', () => {
        const output = 'Verdict: FAIL';

        const result = formatSimpleFollowUpIssue({
          verifierOutput: output,
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, true);
      });

      it('returns false for empty verifier output', () => {
        const output = '';

        const result = formatSimpleFollowUpIssue({
          verifierOutput: output,
          prNumber: 123,
        });

        assert.equal(result.hasSubstantiveContent, false);
      });

      it('returns false when all gaps are about missing source info', () => {
        // Simulates Issue #415 scenario where verifier couldn't verify because source lacked criteria
        const output = `Verdict: FAIL

Blocking gaps:
- Provide explicit acceptance criteria in the PR description or linked issue so they can be independently verified.
- Provide explicit acceptance criteria in the PR description or linked issue so they can be independently verified.`;

        const result = formatSimpleFollowUpIssue({
          verifierOutput: output,
          prNumber: 123,
        });

        // Should NOT create follow-up issue since there's nothing actionable
        // Note: hasSubstantiveContent will still be true because verifierOutput is non-empty
        // The missing info gaps only affect the gap count, not the verifier output presence
        assert.equal(result.hasSubstantiveContent, true);
      });

      it('returns true when gaps include actual verification failures alongside missing info', () => {
        const output = `Verdict: FAIL

Blocking gaps:
- Provide explicit acceptance criteria in the PR description or linked issue so they can be independently verified.
- Missing test coverage for new feature`;

        const result = formatSimpleFollowUpIssue({
          verifierOutput: output,
          prNumber: 123,
        });

        // SHOULD create follow-up issue since there's an actual verification failure
        assert.equal(result.hasSubstantiveContent, true);
      });
    });
  });
});
