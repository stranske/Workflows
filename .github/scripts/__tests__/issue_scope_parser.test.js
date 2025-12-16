'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  extractScopeTasksAcceptanceSections,
  parseScopeTasksAcceptanceSections,
  analyzeSectionPresence,
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
