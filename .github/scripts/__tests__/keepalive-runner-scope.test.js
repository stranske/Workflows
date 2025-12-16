'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  extractScopeTasksAcceptanceSections,
  findScopeTasksAcceptanceBlock,
} = require('../../../scripts/keepalive-runner.js');

test('extractScopeTasksAcceptanceSections accepts varied heading styles', () => {
  const block = [
    '<!-- auto-status-summary:start -->',
    '## Automated Status Summary',
    '## Scope',
    '- [ ] alpha',
    '### Tasks',
    '- [ ] beta',
    '#### Acceptance criteria',
    '- [ ] gamma',
    '<!-- auto-status-summary:end -->',
  ].join('\n');

  const extracted = extractScopeTasksAcceptanceSections(block);
  const expected = [
    '#### Scope',
    '- [ ] alpha',
    '',
    '#### Tasks',
    '- [ ] beta',
    '',
    '#### Acceptance Criteria',
    '- [ ] gamma',
  ].join('\n');

  assert.equal(extracted, expected);
});

test('findScopeTasksAcceptanceBlock falls back to bold headings in PR body', () => {
  const prBody = [
    '**Scope**',
    '- [ ] keep the UI optional',
    '',
    '**Tasks**',
    '- [ ] gate heavy imports behind availability checks',
    '',
    '**Acceptance criteria**',
    '- [ ] pipeline executes without widget dependencies',
  ].join('\n');

  const extracted = findScopeTasksAcceptanceBlock({ prBody, comments: [], override: '' });
  const expected = [
    '#### Scope',
    '- [ ] keep the UI optional',
    '',
    '#### Tasks',
    '- [ ] gate heavy imports behind availability checks',
    '',
    '#### Acceptance Criteria',
    '- [ ] pipeline executes without widget dependencies',
  ].join('\n');

  assert.equal(extracted, expected);
});

test('findScopeTasksAcceptanceBlock accepts plain headings with colons', () => {
  const prBody = [
    'Scope:',
    '- [ ] headline summary',
    '',
    'Tasks',
    '- [ ] do the actual implementation',
    '',
    'Acceptance criteria',
    '- [ ] passes the regression suite',
  ].join('\n');

  const extracted = findScopeTasksAcceptanceBlock({ prBody, comments: [], override: '' });
  const expected = [
    '#### Scope',
    '- [ ] headline summary',
    '',
    '#### Tasks',
    '- [ ] do the actual implementation',
    '',
    '#### Acceptance Criteria',
    '- [ ] passes the regression suite',
  ].join('\n');

  assert.equal(extracted, expected);
});

test('extractScopeTasksAcceptanceSections tolerates missing scope heading', () => {
  const prBody = [
    'Tasks:',
    '- [ ] add fast path',
    '',
    'Acceptance Criteria:',
    '- [ ] prove it works',
  ].join('\n');

  const extracted = extractScopeTasksAcceptanceSections(prBody);
  const expected = [
    '#### Scope',
    '_No scope information provided_',
    '',
    '#### Tasks',
    '- [ ] add fast path',
    '',
    '#### Acceptance Criteria',
    '- [ ] prove it works',
  ].join('\n');

  assert.equal(extracted, expected);
});

test('findScopeTasksAcceptanceBlock preserves Task List label when provided', () => {
  const prBody = [
    'Task List',
    '- [ ] preserve historical label',
    '',
    'Scope',
    '- [ ] ensure backwards compatibility',
    '',
    'Acceptance Criteria',
    '- [ ] parser returns task list heading',
  ].join('\n');

  const extracted = findScopeTasksAcceptanceBlock({ prBody, comments: [], override: '' });
  assert.match(extracted, /#### Task List/);
});

test('findScopeTasksAcceptanceBlock parses blockquoted PR bodies', () => {
  const prBody = [
    '### Source Issue',
    '',
    '> ## Scope',
    '> - [ ] blockquoted scope item',
    '>',
    '> ## Tasks',
    '> - [ ] task alpha',
    '> - [ ] task beta',
    '>',
    '> ## Acceptance criteria',
    '> - all tasks done',
  ].join('\n');

  const extracted = findScopeTasksAcceptanceBlock({ prBody, comments: [], override: '' });
  assert.equal(
    extracted,
    [
      '#### Scope',
      '- [ ] blockquoted scope item',
      '',
      '#### Tasks',
      '- [ ] task alpha',
      '- [ ] task beta',
      '',
      '#### Acceptance Criteria',
      '- [ ] all tasks done',
    ].join('\n')
  );
});

test('findScopeTasksAcceptanceBlock recognises Task List blocks without Scope', () => {
  const comments = [
    {
      body: [
        '#### Task List',
        '- [ ] enforce guard',
        '',
        '#### Acceptance Criteria',
        '- [ ] guard exercised',
      ].join('\n'),
    },
  ];

  const extracted = findScopeTasksAcceptanceBlock({ prBody: '', comments, override: '' });
  const expected = [
    '#### Scope',
    '_No scope information provided_',
    '',
    '#### Task List',
    '- [ ] enforce guard',
    '',
    '#### Acceptance Criteria',
    '- [ ] guard exercised',
  ].join('\n');

  assert.equal(extracted, expected);
});
