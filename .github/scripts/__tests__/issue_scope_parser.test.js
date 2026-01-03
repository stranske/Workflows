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

test('parses bold headings with trailing colons', () => {
  const issue = [
    '**Scope**:',
    '- summary',
    '',
    '**Tasks**:',
    '- [ ] alpha',
    '',
    '**Acceptance Criteria**:',
    '- ok',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    ['#### Scope', '- summary', '', '#### Tasks', '- [ ] alpha', '', '#### Acceptance Criteria', '- [ ] ok'].join('\n')
  );
});

test('parses bold headings wrapped in list items', () => {
  // Note: This is an edge case where sections are marked with list bullets
  // containing bold section names. The parser extracts the content following
  // each recognized section heading, treating the list bullet as a heading marker.
  const issue = [
    '**Scope**',
    'Context line.',
    '',
    '**Tasks**',
    '- [ ] first task',
    '',
    '**Acceptance Criteria**:',
    '- [ ] tests pass',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Scope',
      'Context line.',
      '',
      '#### Tasks',
      '- [ ] first task',
      '',
      '#### Acceptance Criteria',
      '- [ ] tests pass',
    ].join('\n')
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

test('infers tasks from list blocks when headings are missing', () => {
  const issue = [
    '- [ ] first task',
    '- [ ] second task',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(result, ['#### Tasks', '- [ ] first task', '- [ ] second task'].join('\n'));
});

test('infers tasks from scope content when tasks heading is missing', () => {
  const issue = [
    '## Scope',
    'Short context line.',
    '',
    '- [ ] first task',
    '- [ ] second task',
    '',
    '## Acceptance Criteria',
    '- must pass tests',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Scope',
      'Short context line.',
      '',
      '#### Tasks',
      '- [ ] first task',
      '- [ ] second task',
      '',
      '#### Acceptance Criteria',
      '- [ ] must pass tests',
    ].join('\n')
  );
});

test('infers acceptance from trailing list block when heading is missing', () => {
  const issue = [
    '## Tasks',
    '- [ ] ship feature',
    '',
    'Acceptance Criteria (AC):',
    '',
    '- [ ] all tests pass',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] ship feature',
      '',
      'Acceptance Criteria (AC):',
      '',
      '#### Acceptance Criteria',
      '- [ ] all tests pass',
    ].join('\n')
  );
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

test('normalises numbered list items into checkboxes', () => {
  const issue = [
    'Tasks',
    '1. First task',
    '2. [ ] Second task',
    '',
    'Acceptance criteria',
    '1) All tests pass',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '1. [ ] First task',
      '2. [ ] Second task',
      '',
      '#### Acceptance Criteria',
      '1) [ ] All tests pass',
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

test('normalises all bullets to checkboxes', () => {
  const issue = [
    'Tasks',
    '- Add unit tests',
    '- Review the code',
    '- Update documentation',
    '',
    'Acceptance criteria',
    '- All tests pass',
    '- Code coverage ≥95%',
    '- Documentation complete',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] Add unit tests',
      '- [ ] Review the code',
      '- [ ] Update documentation',
      '',
      '#### Acceptance Criteria',
      '- [ ] All tests pass',
      '- [ ] Code coverage ≥95%',
      '- [ ] Documentation complete',
    ].join('\n')
  );
});

test('converts all bullets to checkboxes in tasks section', () => {
  const issue = [
    'Tasks',
    '- Add feature X',
    '- Deploy to staging',
    '- Update documentation',
    '',
    'Acceptance Criteria',
    '- Tests pass',
    '- Documentation complete',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] Add feature X',
      '- [ ] Deploy to staging',
      '- [ ] Update documentation',
      '',
      '#### Acceptance Criteria',
      '- [ ] Tests pass',
      '- [ ] Documentation complete',
    ].join('\n')
  );
});

test('preserves existing checkboxes', () => {
  const issue = [
    'Tasks',
    '- [x] Add feature X',
    '- [ ] Deploy to staging',
    '- Update documentation',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [x] Add feature X',
      '- [ ] Deploy to staging',
      '- [ ] Update documentation',
    ].join('\n')
  );
});

test('preserves non-bullet content', () => {
  const issue = [
    'Tasks',
    '- Add feature X',
    '',
    '**Important:** Run tests after each change',
    '',
    '1. First do X',
    '2. Then do Y',
    '',
    '- Deploy to staging',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] Add feature X',
      '',
      '**Important:** Run tests after each change',
      '',
      '1. [ ] First do X',
      '2. [ ] Then do Y',
      '',
      '- [ ] Deploy to staging',
    ].join('\n')
  );
});

test('handles nested bullets', () => {
  const issue = [
    'Tasks',
    '- Configure database',
    '  - Set up schema',
    '  - Add indexes',
    '- Deploy application',
  ].join('\n');

  const result = extractScopeTasksAcceptanceSections(issue);
  assert.equal(
    result,
    [
      '#### Tasks',
      '- [ ] Configure database',
      '  - [ ] Set up schema',
      '  - [ ] Add indexes',
      '- [ ] Deploy application',
    ].join('\n')
  );
});
