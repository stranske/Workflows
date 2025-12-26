'use strict';

const { test, describe } = require('node:test');
const assert = require('node:assert');

const {
  COMPLETION_COMMENT_MARKER,
  extractCheckedItems,
  extractSection,
  buildCompletionComment,
  findExistingComment,
} = require('../post_completion_comment.js');

describe('extractCheckedItems', () => {
  test('extracts checked items from markdown', () => {
    const content = `
- [x] First completed task
- [ ] Incomplete task
- [X] Second completed (uppercase X)
* [x] Asterisk style
+ [x] Plus style
- [x] —
- [x] _(placeholder)_
`;
    const items = extractCheckedItems(content);
    assert.deepStrictEqual(items, [
      'First completed task',
      'Second completed (uppercase X)',
      'Asterisk style',
      'Plus style',
    ]);
  });

  test('returns empty array for no checkboxes', () => {
    const content = 'Just some text\nNo checkboxes here';
    const items = extractCheckedItems(content);
    assert.deepStrictEqual(items, []);
  });

  test('handles nested checkboxes', () => {
    const content = `
- [x] Parent task
  - [x] Child task
    - [x] Grandchild task
`;
    const items = extractCheckedItems(content);
    assert.strictEqual(items.length, 3);
    assert.ok(items.includes('Parent task'));
    assert.ok(items.includes('Child task'));
    assert.ok(items.includes('Grandchild task'));
  });
});

describe('extractSection', () => {
  test('extracts Tasks section', () => {
    const content = `
## Some Header

### Tasks
- [x] Task one
- [ ] Task two

### Acceptance Criteria
- [x] Criterion one
`;
    const section = extractSection(content, 'Tasks');
    assert.ok(section.includes('Task one'));
    assert.ok(section.includes('Task two'));
    assert.ok(!section.includes('Criterion one'));
  });

  test('extracts Acceptance Criteria section', () => {
    const content = `
### Tasks
- [x] Task one

### Acceptance Criteria
- [x] Tests pass
- [ ] Docs updated
`;
    const section = extractSection(content, 'Acceptance [Cc]riteria');
    assert.ok(section.includes('Tests pass'));
    assert.ok(section.includes('Docs updated'));
    assert.ok(!section.includes('Task one'));
  });

  test('returns empty string for missing section', () => {
    const content = '# No matching sections';
    const section = extractSection(content, 'Tasks');
    assert.strictEqual(section, '');
  });
});

describe('buildCompletionComment', () => {
  test('builds comment with tasks and acceptance criteria', () => {
    const tasks = ['Implement feature A', 'Add tests for feature A'];
    const acceptance = ['Feature A works correctly'];
    const metadata = { iteration: '3', commitSha: 'abc123def456' };
    
    const comment = buildCompletionComment(tasks, acceptance, metadata);
    
    assert.ok(comment.includes(COMPLETION_COMMENT_MARKER));
    assert.ok(comment.includes('## ✅ Codex Completion Checkpoint'));
    assert.ok(comment.includes('**Iteration:** 3'));
    assert.ok(comment.includes('`abc123d`'));
    assert.ok(comment.includes('### Tasks Completed'));
    assert.ok(comment.includes('- [x] Implement feature A'));
    assert.ok(comment.includes('- [x] Add tests for feature A'));
    assert.ok(comment.includes('### Acceptance Criteria Met'));
    assert.ok(comment.includes('- [x] Feature A works correctly'));
  });

  test('handles empty completions', () => {
    const comment = buildCompletionComment([], [], {});
    
    assert.ok(comment.includes(COMPLETION_COMMENT_MARKER));
    assert.ok(comment.includes('_No new completions recorded this round._'));
    assert.ok(!comment.includes('### Tasks Completed'));
    assert.ok(!comment.includes('### Acceptance Criteria Met'));
  });

  test('includes only tasks when no acceptance criteria', () => {
    const comment = buildCompletionComment(['Task one'], [], {});
    
    assert.ok(comment.includes('### Tasks Completed'));
    assert.ok(comment.includes('- [x] Task one'));
    assert.ok(!comment.includes('### Acceptance Criteria Met'));
  });
});

describe('findExistingComment', () => {
  test('finds comment with marker', () => {
    const comments = [
      { id: 1, body: 'Random comment' },
      { id: 2, body: `${COMPLETION_COMMENT_MARKER}\n## Completion` },
      { id: 3, body: 'Another comment' },
    ];
    
    const found = findExistingComment(comments);
    assert.strictEqual(found.id, 2);
  });

  test('returns null when no marker found', () => {
    const comments = [
      { id: 1, body: 'Random comment' },
      { id: 2, body: 'Another comment' },
    ];
    
    const found = findExistingComment(comments);
    assert.strictEqual(found, null);
  });

  test('handles empty array', () => {
    const found = findExistingComment([]);
    assert.strictEqual(found, null);
  });

  test('handles null/undefined', () => {
    assert.strictEqual(findExistingComment(null), null);
    assert.strictEqual(findExistingComment(undefined), null);
  });
});
