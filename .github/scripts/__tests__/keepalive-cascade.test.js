'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  cascadeParentCheckboxes,
  countCheckboxes,
} = require('../keepalive_loop.js');

const {
  cascadeParentCheckboxes: runnerCascade,
  countCheckboxes: runnerCountCheckboxes,
} = require('../../../scripts/keepalive-runner.js');

// ─── cascadeParentCheckboxes (keepalive_loop.js) ────────────────────────────

test('cascade: checked parent cascades to indented children', () => {
  const input = [
    '- [x] Parent task',
    '  - [ ] Define scope for: Parent task',
    '  - [ ] Implement focused slice for: Parent task',
    '  - [ ] Validate focused slice for: Parent task',
  ].join('\n');

  const result = cascadeParentCheckboxes(input);
  assert.equal(result, [
    '- [x] Parent task',
    '  - [x] Define scope for: Parent task',
    '  - [x] Implement focused slice for: Parent task',
    '  - [x] Validate focused slice for: Parent task',
  ].join('\n'));
});

test('cascade: unchecked parent does NOT cascade', () => {
  const input = [
    '- [ ] Parent task',
    '  - [ ] Sub-task one',
    '  - [ ] Sub-task two',
  ].join('\n');

  const result = cascadeParentCheckboxes(input);
  assert.equal(result, input);
});

test('cascade: stops at same-indentation sibling', () => {
  const input = [
    '- [x] Parent A',
    '  - [ ] Child of A',
    '- [ ] Parent B',
    '  - [ ] Child of B',
  ].join('\n');

  const expected = [
    '- [x] Parent A',
    '  - [x] Child of A',
    '- [ ] Parent B',
    '  - [ ] Child of B',
  ].join('\n');

  assert.equal(cascadeParentCheckboxes(input), expected);
});

test('cascade: handles multiple checked parents', () => {
  const input = [
    '- [x] Task 1',
    '  - [ ] Sub 1a',
    '- [ ] Task 2',
    '  - [ ] Sub 2a',
    '- [x] Task 3',
    '  - [ ] Sub 3a',
    '  - [ ] Sub 3b',
  ].join('\n');

  const expected = [
    '- [x] Task 1',
    '  - [x] Sub 1a',
    '- [ ] Task 2',
    '  - [ ] Sub 2a',
    '- [x] Task 3',
    '  - [x] Sub 3a',
    '  - [x] Sub 3b',
  ].join('\n');

  assert.equal(cascadeParentCheckboxes(input), expected);
});

test('cascade: preserves already-checked children', () => {
  const input = [
    '- [x] Parent',
    '  - [x] Already done child',
    '  - [ ] Not done child',
  ].join('\n');

  const expected = [
    '- [x] Parent',
    '  - [x] Already done child',
    '  - [x] Not done child',
  ].join('\n');

  assert.equal(cascadeParentCheckboxes(input), expected);
});

test('cascade: deeply nested children', () => {
  const input = [
    '- [x] Level 0',
    '  - [ ] Level 1',
    '    - [ ] Level 2',
  ].join('\n');

  const expected = [
    '- [x] Level 0',
    '  - [x] Level 1',
    '    - [x] Level 2',
  ].join('\n');

  assert.equal(cascadeParentCheckboxes(input), expected);
});

test('cascade: heading resets cascade', () => {
  const input = [
    '- [x] Task under section A',
    '',
    '## Section B',
    '  - [ ] Should not cascade',
  ].join('\n');

  assert.equal(cascadeParentCheckboxes(input), input);
});

test('cascade: handles null/empty input', () => {
  assert.equal(cascadeParentCheckboxes(''), '');
  assert.equal(cascadeParentCheckboxes(null), null);
  assert.equal(cascadeParentCheckboxes(undefined), undefined);
});

// ─── countCheckboxes integration with cascade ───────────────────────────────

test('countCheckboxes counts cascaded children as checked', () => {
  const markdown = [
    '- [x] Parent task',
    '  - [ ] Sub-task 1',
    '  - [ ] Sub-task 2',
    '  - [ ] Sub-task 3',
    '- [ ] Unchecked parent',
    '  - [ ] Sub unchecked',
  ].join('\n');

  const counts = countCheckboxes(markdown);
  // Parent checked + 3 cascaded children = 4 checked; unchecked parent + its child = 2 unchecked
  assert.equal(counts.total, 6);
  assert.equal(counts.checked, 4);
  assert.equal(counts.unchecked, 2);
});

test('countCheckboxes: all parents checked means allComplete', () => {
  const markdown = [
    '- [x] Task 1',
    '  - [ ] Define scope for: Task 1',
    '  - [ ] Implement focused slice for: Task 1',
    '  - [ ] Validate focused slice for: Task 1',
    '- [x] Task 2',
    '  - [ ] Define scope for: Task 2',
    '  - [ ] Implement focused slice for: Task 2',
    '  - [ ] Validate focused slice for: Task 2',
  ].join('\n');

  const counts = countCheckboxes(markdown);
  assert.equal(counts.unchecked, 0, 'all sub-tasks should cascade from parents');
  assert.equal(counts.checked, 8);
});

// ─── Code fence awareness ───────────────────────────────────────────────────

test('cascade: does not bleed through fenced code blocks', () => {
  const input = [
    '- [x] Checked parent',
    '```',
    '- [ ] Example inside fence',
    '```',
    '- [ ] Real task after fence',
  ].join('\n');

  // The fenced checkbox must NOT be cascaded, and the real task after the
  // fence must NOT be cascaded either because the fence resets parentIndent.
  assert.equal(cascadeParentCheckboxes(input), input);
});

test('cascade: fenced block resets parent state', () => {
  const input = [
    '- [x] Parent before fence',
    '  - [ ] Child before fence',
    '```markdown',
    '- [x] Example',
    '```',
    '  - [ ] Should NOT cascade (fence reset parent)',
  ].join('\n');

  const expected = [
    '- [x] Parent before fence',
    '  - [x] Child before fence',
    '```markdown',
    '- [x] Example',
    '```',
    '  - [ ] Should NOT cascade (fence reset parent)',
  ].join('\n');

  assert.equal(cascadeParentCheckboxes(input), expected);
});

test('cascade: tilde fences are also handled', () => {
  const input = [
    '- [x] Parent',
    '~~~',
    '  - [ ] Fenced child',
    '~~~',
    '  - [ ] After fence',
  ].join('\n');

  // Fenced child is untouched, after-fence child is not cascaded (fence reset)
  assert.equal(cascadeParentCheckboxes(input), input);
});

test('runner cascade: fenced code blocks handled', () => {
  const input = [
    '- [x] Parent',
    '```',
    '  - [ ] Fenced',
    '```',
    '  - [ ] After fence',
  ].join('\n');

  assert.equal(runnerCascade(input), input);
});

// ─── keepalive-runner.js cascade (parallel implementation) ──────────────────

test('runner cascade: matches keepalive_loop cascade behavior', () => {
  const input = [
    '- [x] Parent task',
    '  - [ ] Sub-task 1',
    '  - [ ] Sub-task 2',
  ].join('\n');

  assert.equal(
    runnerCascade(input),
    cascadeParentCheckboxes(input),
    'Both implementations should produce identical output'
  );
});

test('runner countCheckboxes: counts cascaded children as checked', () => {
  const markdown = [
    '- [x] Parent',
    '  - [ ] Child 1',
    '  - [ ] Child 2',
    '- [ ] Unchecked',
  ].join('\n');

  const counts = runnerCountCheckboxes(markdown);
  assert.equal(counts.checked, 3); // parent + 2 cascaded
  assert.equal(counts.unchecked, 1);
});
