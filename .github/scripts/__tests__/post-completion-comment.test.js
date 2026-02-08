'use strict';

const { test, describe } = require('node:test');
const assert = require('node:assert');

const {
  COMPLETION_COMMENT_MARKER,
  extractCheckedItems,
  extractSection,
  buildCompletionComment,
  findExistingComment,
  postCompletionComment,
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

  test('ignores fenced code blocks', () => {
    const content = `
- [x] Real task
\`\`\`md
- [x] Not a task
\`\`\`
- [x] Another task
~~~md
- [x] Tilde task
~~~
- [x] Final task
`;
    const items = extractCheckedItems(content);
    assert.deepStrictEqual(items, ['Real task', 'Another task', 'Final task']);
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

describe('postCompletionComment', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const os = require('node:os');

  function createCore() {
    return {
      info: () => {},
      warning: () => {},
      debug: () => {},
    };
  }

  function createGithub() {
    return {
      __testMock: true,
      rest: {
        issues: {
          listComments: async () => ({ data: [] }),
          updateComment: async () => ({ data: { id: 123 } }),
          createComment: async () => ({ data: { id: 456 } }),
        },
      },
    };
  }

  test('returns early without API calls when no completions', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'completion-comment-'));
    const promptPath = path.join(tempDir, 'codex-prompt.md');
    fs.writeFileSync(promptPath, '## Tasks\n- [ ] Not done\n\n## Acceptance Criteria\n- [ ] Not done\n', 'utf8');

    const github = createGithub();
    let listCalls = 0;
    let updateCalls = 0;
    let createCalls = 0;
    github.rest.issues.listComments = async () => {
      listCalls += 1;
      return { data: [] };
    };
    github.rest.issues.updateComment = async () => {
      updateCalls += 1;
      return { data: { id: 123 } };
    };
    github.rest.issues.createComment = async () => {
      createCalls += 1;
      return { data: { id: 456 } };
    };

    const result = await postCompletionComment({
      github,
      context: { repo: { owner: 'owner', repo: 'repo' } },
      core: createCore(),
      inputs: {
        pr_number: 123,
        prompt_file: promptPath,
      },
    });

    assert.deepStrictEqual(result, { posted: false, reason: 'no-completions' });
    assert.strictEqual(listCalls, 0);
    assert.strictEqual(updateCalls, 0);
    assert.strictEqual(createCalls, 0);
  });
});
