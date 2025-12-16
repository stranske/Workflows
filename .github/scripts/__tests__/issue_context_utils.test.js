const test = require('node:test');
const assert = require('node:assert/strict');

const { buildIssueContext, EXPECTED_SECTIONS, ALL_SECTIONS } = require('../issue_context_utils.js');

const COMPLETE_BODY = `
## Scope
- Evaluate automation bridge

## Tasks
- [ ] add invite metadata step

## Acceptance Criteria
- [ ] issue context posts on PR
`;

const TASKS_AND_ACCEPTANCE_ONLY = `
## Tasks
- [ ] implement the feature

## Acceptance Criteria
- [ ] tests pass
`;

const TASKS_ONLY = `
## Tasks
- [ ] missing acceptance criteria
`;

const WHY_INSTEAD_OF_SCOPE = `
## Why
Explains the motivation.

## Tasks
- [ ] do the thing

## Acceptance Criteria
- [ ] thing is done
`;

test('buildIssueContext returns summary without warnings when all sections exist', () => {
  const result = buildIssueContext(COMPLETE_BODY);
  assert.equal(result.summaryNeedsWarning, false);
  assert.equal(result.warningLines.length, 0);
  assert.ok(result.statusSummaryBlock.includes('Automated Status Summary'));
  assert.ok(!result.statusSummaryBlock.includes('Summary Unavailable'));
  assert.ok(result.scopeBlock.includes('#### Scope'));
  assert.ok(result.hasActionableContent);
});

test('buildIssueContext accepts Tasks and Acceptance without Scope', () => {
  const result = buildIssueContext(TASKS_AND_ACCEPTANCE_ONLY);
  // Scope is optional, so no warning when Tasks and Acceptance are present
  assert.equal(result.summaryNeedsWarning, false);
  assert.ok(!result.statusSummaryBlock.includes('Summary Unavailable'));
  assert.ok(result.hasActionableContent);
  assert.ok(result.scopeBlock.includes('#### Tasks'));
  assert.ok(result.scopeBlock.includes('#### Acceptance Criteria'));
});

test('buildIssueContext flags warnings when Acceptance is missing', () => {
  const result = buildIssueContext(TASKS_ONLY);
  // Has Tasks but missing Acceptance - should warn but still have actionable content
  assert.equal(result.hasActionableContent, true);
  // Missing required non-optional section
  assert.ok(result.missingSections.includes('Acceptance Criteria'));
});

test('buildIssueContext accepts "Why" as Scope alias', () => {
  const result = buildIssueContext(WHY_INSTEAD_OF_SCOPE);
  assert.equal(result.summaryNeedsWarning, false);
  assert.ok(result.hasActionableContent);
  // Should extract Why content under Scope heading
  assert.ok(result.scopeBlock.includes('Explains the motivation'));
});

test('EXPECTED_SECTIONS does not include Scope (optional)', () => {
  assert.ok(!EXPECTED_SECTIONS.includes('Scope'));
  assert.ok(EXPECTED_SECTIONS.includes('Tasks'));
  assert.ok(EXPECTED_SECTIONS.includes('Acceptance Criteria'));
});

test('ALL_SECTIONS includes all section names', () => {
  assert.ok(ALL_SECTIONS.includes('Scope'));
  assert.ok(ALL_SECTIONS.includes('Tasks'));
  assert.ok(ALL_SECTIONS.includes('Acceptance Criteria'));
});
