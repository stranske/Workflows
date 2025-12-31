'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  extractScopeTasksAcceptanceSections,
  parseScopeTasksAcceptanceSections,
  analyzeSectionPresence,
  hasNonPlaceholderScopeTasksAcceptanceContent,
} = require('../issue_scope_parser');

test('extracts sections inside auto-status markers', () => {
  const issue = [
    'Intro text',
    '<!-- auto-status-summary:start -->',
    '## Scope',
    '- item a',
    '',
    '## Tasks',
    '- [ ] first',
    '',
    '## Acceptance Criteria',
    '- pass',
    '<!-- auto-status-summary:end -->',
    'Footer',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    ['#### Scope', '- item a', '', '#### Tasks', '- [ ] first', '', '#### Acceptance Criteria', '- [ ] pass'].join('\n')
  );
});

test('parses plain headings without markdown hashes', () => {
  const issue = [
    'Issue Scope',
    '- summary',
    '',
    'Tasks:',
    '- [ ] alpha',
    '',
    'Acceptance criteria',
    '- ok',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    ['#### Scope', '- summary', '', '#### Tasks', '- [ ] alpha', '', '#### Acceptance Criteria', '- [ ] ok'].join('\n')
  );
});

test('parseScopeTasksAcceptanceSections preserves structured sections', () => {
  const issue = [
    '## Issue Scope',
    '- overview line',
    '',
    '**Task List**',
    '- [ ] do one',
    '- [x] done two',
    '',
    'Acceptance criteria:',
    '- ✅ verified',
  ].join('\n');

  const parsed = parseScopeTasksAcceptanceSections(issue);
  assert.deepEqual(parsed, {
    scope: '- overview line',
    tasks: ['- [ ] do one', '- [x] done two'].join('\n'),
    acceptance: '- ✅ verified',
  });
});

test('parses blockquoted sections exported into PR bodies', () => {
  const issue = [
    '> ## Scope',
    '> ensure detection survives quoting',
    '>',
    '> ## Tasks',
    '> - [ ] first task',
    '> - [ ] second task',
    '>',
    '> ## Acceptance criteria',
    '> - two tasks completed',
  ].join('\n');

  const extracted = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    extracted,
    [
      '#### Scope',
      'ensure detection survives quoting',
      '',
      '#### Tasks',
      '- [ ] first task',
      '- [ ] second task',
      '',
      '#### Acceptance Criteria',
      '- [ ] two tasks completed',
    ].join('\n')
  );
});

test('returns empty string when no headings present', () => {
  const issue = 'No structured content here.';
  assert.equal(extractScopeTasksAcceptanceSections(issue), '');
});

test('includes placeholders when requested', () => {
  const issue = [
    'Tasks:',
    '- [ ] implement fast path',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue, { includePlaceholders: true });
  assert.equal(
    result,
    [
      '#### Scope',
      '_No scope information provided_',
      '',
      '#### Tasks',
      '- [ ] implement fast path',
      '',
      '#### Acceptance Criteria',
      '- [ ] _No acceptance criteria defined_',
    ].join('\n')
  );
});

test('normalises bullet lists into checkboxes for tasks and acceptance', () => {
  const issue = [
    'Tasks',
    '- finish vectorisation',
    '-  add docs',
    '',
    'Acceptance criteria',
    '- confirm coverage > 90%',
    '-  ensure no regressions',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue, { includePlaceholders: true });
  assert.equal(
    result,
    [
      '#### Scope',
      '_No scope information provided_',
      '',
      '#### Tasks',
      '- [ ] finish vectorisation',
      '- [ ] add docs',
      '',
      '#### Acceptance Criteria',
      '- [ ] confirm coverage > 90%',
      '- [ ] ensure no regressions',
    ].join('\n')
  );
});

test('analyzeSectionPresence flags missing sections', () => {
  const issue = [
    '## Scope',
    'ready to go',
    '',
    '## Tasks',
    '- [ ] build warning',
  ].join('\n');

  const status = analyzeSectionPresence(issue);
  assert.deepEqual(status.entries, [
    { key: 'scope', label: 'Scope', present: true, optional: true },
    { key: 'tasks', label: 'Tasks', present: true, optional: false },
    { key: 'acceptance', label: 'Acceptance Criteria', present: false, optional: false },
  ]);
  // Only non-optional missing sections are reported
  assert.deepEqual(status.missing, ['Acceptance Criteria']);
  assert.equal(status.hasAllRequired, false);
});

test('analyzeSectionPresence recognises canonical template', () => {
  const issue = [
    '## Scope',
    '- new feature',
    '',
    '## Tasks',
    '- [ ] scaffold ui',
    '',
    '## Acceptance Criteria',
    '- [ ] demo recorded',
  ].join('\n');

  const status = analyzeSectionPresence(issue);
  assert.equal(status.hasAllRequired, true);
  assert.deepEqual(status.missing, []);
});

test('extracts "Why" section as Scope alias', () => {
  const issue = [
    '## Why',
    'This explains the motivation.',
    '',
    '## Tasks',
    '- [ ] implement feature',
    '',
    '## Acceptance Criteria',
    '- [ ] tests pass',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Scope',
      'This explains the motivation.',
      '',
      '#### Tasks',
      '- [ ] implement feature',
      '',
      '#### Acceptance Criteria',
      '- [ ] tests pass',
    ].join('\n')
  );
});

test('extracts Tasks and Acceptance without Scope', () => {
  const issue = [
    '## Tasks',
    '- [ ] first task',
    '- [ ] second task',
    '',
    '## Acceptance Criteria',
    '- All tasks complete',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] first task',
      '- [ ] second task',
      '',
      '#### Acceptance Criteria',
      '- [ ] All tasks complete',
    ].join('\n')
  );
});

test('analyzeSectionPresence treats Scope as optional', () => {
  const issue = [
    '## Tasks',
    '- [ ] scaffold ui',
    '',
    '## Acceptance Criteria',
    '- [ ] demo recorded',
  ].join('\n');

  const status = analyzeSectionPresence(issue);
  // Scope is optional, so only Tasks and Acceptance are required
  assert.equal(status.hasAllRequired, true);
  assert.deepEqual(status.missing, []);
  assert.equal(status.hasActionableContent, true);
});

test('analyzeSectionPresence reports missing required sections only', () => {
  const issue = [
    '## Scope',
    'Some background info',
    '',
    '## Tasks',
    '- [ ] do something',
  ].join('\n');

  const status = analyzeSectionPresence(issue);
  // Scope is present but optional; Acceptance is required and missing
  assert.deepEqual(status.missing, ['Acceptance Criteria']);
  assert.equal(status.hasAllRequired, false);
  assert.equal(status.hasActionableContent, true);
});

test('analyzeSectionPresence flags hasActionableContent correctly', () => {
  const issue = [
    '## Scope',
    'Just some context',
  ].join('\n');

  const status = analyzeSectionPresence(issue);
  // No Tasks or Acceptance, so no actionable content
  assert.equal(status.hasActionableContent, false);
  // But Scope is present and optional
  assert.deepEqual(status.entries[0], { key: 'scope', label: 'Scope', present: true, optional: true });
});

test('extracts "Background" as Scope alias', () => {
  const issue = [
    '## Background',
    'Historical context here.',
    '',
    '## Tasks',
    '- [ ] do the thing',
    '',
    '## Acceptance Criteria',
    '- [ ] thing is done',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.ok(result.includes('Historical context here.'));
  assert.ok(result.includes('#### Scope'));
});

test('extracts "Implementation notes" as Tasks alias', () => {
  const issue = [
    '## Why',
    'Motivation here.',
    '',
    '## Implementation notes',
    '- Target specific function',
    '',
    '## Acceptance criteria',
    '- Tests pass',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.ok(result.includes('Target specific function'));
  assert.ok(result.includes('#### Tasks'));
});

test('extracts "Task" as Tasks alias', () => {
  const issue = [
    '## Task',
    '- [ ] first item',
    '',
    '## Acceptance Criteria',
    '- [ ] ok',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.ok(result.includes('first item'));
  assert.ok(result.includes('#### Tasks'));
});

test('extracts "To Do" as Tasks alias', () => {
  const issue = [
    '## To Do',
    '- [ ] second item',
    '',
    '## Acceptance Criteria',
    '- [ ] ok',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.ok(result.includes('second item'));
  assert.ok(result.includes('#### Tasks'));
});

test('hasNonPlaceholderScopeTasksAcceptanceContent detects PR meta fallback placeholders', () => {
  // Content with only PR meta manager fallback placeholders should return false
  // Note: scope uses italicized text (not checkbox) since it's informational
  const prMetaPlaceholders = [
    '## Scope',
    '_Scope section missing from source issue._',
    '',
    '## Tasks',
    '- [ ] Tasks section missing from source issue.',
    '',
    '## Acceptance Criteria',
    '- [ ] Acceptance criteria section missing from source issue.',
  ].join('\n');

  assert.equal(
    hasNonPlaceholderScopeTasksAcceptanceContent(prMetaPlaceholders),
    false,
    'PR meta fallback placeholders should not be treated as real content'
  );

  // Content with standard placeholders should also return false
  const standardPlaceholders = [
    '## Scope',
    '_No scope information provided_',
    '',
    '## Tasks',
    '- [ ] _No tasks defined_',
    '',
    '## Acceptance Criteria',
    '- [ ] _No acceptance criteria defined_',
  ].join('\n');

  assert.equal(
    hasNonPlaceholderScopeTasksAcceptanceContent(standardPlaceholders),
    false,
    'Standard placeholders should not be treated as real content'
  );

  // Real content should return true
  const realContent = [
    '## Scope',
    'Update coverage tool version.',
    '',
    '## Tasks',
    '- [ ] Bump coverage to 7.13.1',
    '',
    '## Acceptance Criteria',
    '- [ ] CI passes with new version',
  ].join('\n');

  assert.equal(
    hasNonPlaceholderScopeTasksAcceptanceContent(realContent),
    true,
    'Real content should be treated as real content'
  );
});

test('normalises bullets but skips instructional lines', () => {
  const issue = [
    'Tasks',
    '- Add unit tests',
    '- Before implementing, review the code',
    '- Update documentation',
    '- To verify, run pytest',
    '- Remember to check coverage',
    '',
    'Acceptance criteria',
    '- All tests pass',
    '- Before marking complete, run pytest',
    '- Code coverage ≥95%',
    '- 1. Run tests',
    '- 2. Check output',
    '- Make sure all edge cases are covered',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] Add unit tests',
      '- Before implementing, review the code',
      '- [ ] Update documentation',
      '- To verify, run pytest',
      '- Remember to check coverage',
      '',
      '#### Acceptance Criteria',
      '- [ ] All tests pass',
      '- Before marking complete, run pytest',
      '- [ ] Code coverage ≥95%',
      '- 1. Run tests',
      '- 2. Check output',
      '- Make sure all edge cases are covered',
    ].join('\n')
  );
});

test('skips lines with instructional keywords', () => {
  const issue = [
    'Tasks',
    '- Add feature X',
    '- When ready, deploy to staging',
    '- If tests fail, check logs',
    '- After completion, notify team',
    '- While testing, monitor metrics',
    '- For production, use feature flag',
    '- Ensure all tests pass',
    '',
    'Acceptance Criteria',
    '- Tests pass',
    '- Ensure that error handling works',
    '- Verify the API responses',
    '- Check that performance meets SLA',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] Add feature X',
      '- When ready, deploy to staging',
      '- If tests fail, check logs',
      '- After completion, notify team',
      '- While testing, monitor metrics',
      '- For production, use feature flag',
      '- [ ] Ensure all tests pass',
      '',
      '#### Acceptance Criteria',
      '- [ ] Tests pass',
      '- Ensure that error handling works',
      '- Verify the API responses',
      '- Check that performance meets SLA',
    ].join('\n')
  );
});

test('skips lines with numbered list format', () => {
  const issue = [
    'Tasks',
    '- Configure database',
    '- 1. First step',
    '- 2. Second step',
    '- Deploy application',
    '',
    'Acceptance Criteria',
    '- All services running',
    '- 1. Check service A',
    '- 2. Check service B',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] Configure database',
      '- 1. First step',
      '- 2. Second step',
      '- [ ] Deploy application',
      '',
      '#### Acceptance Criteria',
      '- [ ] All services running',
      '- 1. Check service A',
      '- 2. Check service B',
    ].join('\n')
  );
});

test('skips lines with "you must" and similar phrases', () => {
  const issue = [
    'Tasks',
    '- Implement feature',
    '- You must run tests after',
    '- Make sure to update docs',
    "- Don't forget to tag the release",
    '',
    'Acceptance Criteria',
    '- Feature works correctly',
    '- You should verify edge cases',
    '- Be sure to check performance',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] Implement feature',
      '- You must run tests after',
      '- Make sure to update docs',
      "- Don't forget to tag the release",
      '',
      '#### Acceptance Criteria',
      '- [ ] Feature works correctly',
      '- You should verify edge cases',
      '- Be sure to check performance',
    ].join('\n')
  );
});

test('skips lines with IMPORTANT/NOTE/WARNING prefixes', () => {
  const issue = [
    'Tasks',
    '- Add logging',
    '- IMPORTANT: Check with team first',
    '- Note: requires approval',
    '- WARNING: This will affect production',
    '- **IMPORTANT:** Read the docs',
    '',
    'Acceptance Criteria',
    '- Logging enabled',
    '- Tip: use the debug flag',
    '- Hint: check the config file',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] Add logging',
      '- IMPORTANT: Check with team first',
      '- Note: requires approval',
      '- WARNING: This will affect production',
      '- **IMPORTANT:** Read the docs',
      '',
      '#### Acceptance Criteria',
      '- [ ] Logging enabled',
      '- Tip: use the debug flag',
      '- Hint: check the config file',
    ].join('\n')
  );
});
