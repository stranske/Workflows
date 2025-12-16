'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  parseCheckboxStates,
  mergeCheckboxStates,
  ensureChecklist,
  extractBlock,
  fetchConnectorCheckboxStates,
} = require('../agents_pr_meta_update_body.js');

test('parseCheckboxStates extracts checked items from a checkbox list', () => {
  const block = `
- [x] Task one completed
- [ ] Task two pending
- [x] Task three completed
- [ ] Task four pending
  `.trim();

  const states = parseCheckboxStates(block);

  assert.strictEqual(states.size, 2);
  assert.strictEqual(states.get('task one completed'), true);
  assert.strictEqual(states.get('task three completed'), true);
  assert.strictEqual(states.has('task two pending'), false);
});

test('parseCheckboxStates normalizes text by stripping leading dashes', () => {
  const block = `
- [x] - Tests fail if weight bounds...
- [ ] - Existing functionality remains
  `.trim();

  const states = parseCheckboxStates(block);

  assert.strictEqual(states.size, 1);
  assert.strictEqual(states.get('tests fail if weight bounds...'), true);
});

test('parseCheckboxStates handles case-insensitive matching', () => {
  const block = `
- [X] UPPERCASE checked
- [x] lowercase checked
  `.trim();

  const states = parseCheckboxStates(block);

  assert.strictEqual(states.size, 2);
  assert.strictEqual(states.get('uppercase checked'), true);
  assert.strictEqual(states.get('lowercase checked'), true);
});

test('parseCheckboxStates returns empty map for empty input', () => {
  assert.deepStrictEqual(parseCheckboxStates(''), new Map());
  assert.deepStrictEqual(parseCheckboxStates(null), new Map());
  assert.deepStrictEqual(parseCheckboxStates(undefined), new Map());
});

test('mergeCheckboxStates restores checked state for unchecked items', () => {
  const newContent = `
- [ ] Task one
- [ ] Task two
- [ ] Task three
  `.trim();

  const existingStates = new Map([
    ['task one', true],
    ['task three', true],
  ]);

  const result = mergeCheckboxStates(newContent, existingStates);

  assert.ok(result.includes('- [x] Task one'));
  assert.ok(result.includes('- [ ] Task two'));
  assert.ok(result.includes('- [x] Task three'));
});

test('mergeCheckboxStates preserves already checked items in new content', () => {
  const newContent = `
- [x] Already checked in new content
- [ ] Unchecked in new
  `.trim();

  const existingStates = new Map([
    ['unchecked in new', true],
  ]);

  const result = mergeCheckboxStates(newContent, existingStates);

  // Already checked stays checked
  assert.ok(result.includes('- [x] Already checked in new content'));
  // Unchecked gets restored
  assert.ok(result.includes('- [x] Unchecked in new'));
});

test('mergeCheckboxStates handles items with leading dashes in text', () => {
  const newContent = `
- [ ] - Tests fail if bounds violated
- [ ] - Functionality remains unchanged
  `.trim();

  const existingStates = new Map([
    ['tests fail if bounds violated', true],
  ]);

  const result = mergeCheckboxStates(newContent, existingStates);

  assert.ok(result.includes('- [x] - Tests fail if bounds violated'));
  assert.ok(result.includes('- [ ] - Functionality remains unchanged'));
});

test('mergeCheckboxStates returns original content if no existing states', () => {
  const content = '- [ ] Task one\n- [ ] Task two';

  assert.strictEqual(mergeCheckboxStates(content, null), content);
  assert.strictEqual(mergeCheckboxStates(content, new Map()), content);
});

test('mergeCheckboxStates handles real-world acceptance criteria format', () => {
  const prBody = `
#### Acceptance criteria
- [ ] - Tests fail if weight bounds or turnover calculations allow negative weights
- [ ] - Existing functionality remains unchanged outside the stronger test coverage
  `.trim();

  // Agent completes first criterion and posts with checked box
  const agentReply = `
#### Acceptance criteria
- [x] - Tests fail if weight bounds or turnover calculations allow negative weights
- [ ] - Existing functionality remains unchanged outside the stronger test coverage
  `.trim();

  const existingStates = parseCheckboxStates(agentReply);
  assert.strictEqual(existingStates.size, 1);

  // PR-meta refreshes from issue (unchecked) and merges agent's checked state
  const merged = mergeCheckboxStates(prBody, existingStates);

  assert.ok(merged.includes('- [x] - Tests fail if weight bounds or turnover calculations allow negative weights'));
  assert.ok(merged.includes('- [ ] - Existing functionality remains unchanged outside the stronger test coverage'));
});

test('ensureChecklist adds checkbox prefix to plain text lines', () => {
  const text = 'Task one\nTask two\nTask three';
  const result = ensureChecklist(text);

  assert.strictEqual(result, '- [ ] Task one\n- [ ] Task two\n- [ ] Task three');
});

test('ensureChecklist preserves existing checkbox formatting', () => {
  const text = '- [x] Completed task\n- [ ] Pending task';
  const result = ensureChecklist(text);

  assert.strictEqual(result, '- [x] Completed task\n- [ ] Pending task');
});

test('ensureChecklist returns placeholder for empty input', () => {
  assert.strictEqual(ensureChecklist(''), '- [ ] —');
  assert.strictEqual(ensureChecklist('   '), '- [ ] —');
  assert.strictEqual(ensureChecklist(null), '- [ ] —');
});

test('extractBlock extracts content between markers', () => {
  const body = `
Some preamble text

<!-- auto-status-summary:start -->
#### Tasks
- [ ] Task one
- [x] Task two
<!-- auto-status-summary:end -->

Some footer text
  `.trim();

  const block = extractBlock(body, 'auto-status-summary');

  assert.ok(block.includes('#### Tasks'));
  assert.ok(block.includes('- [ ] Task one'));
  assert.ok(block.includes('- [x] Task two'));
});

test('extractBlock returns empty string if markers not found', () => {
  assert.strictEqual(extractBlock('no markers here', 'auto-status-summary'), '');
  assert.strictEqual(extractBlock('', 'auto-status-summary'), '');
  assert.strictEqual(extractBlock(null, 'auto-status-summary'), '');
});

// ========== fetchConnectorCheckboxStates tests ==========

test('fetchConnectorCheckboxStates extracts checked boxes from connector bot comments', async () => {
  const mockGithub = {
    paginate: async (method, params) => {
      assert.strictEqual(params.issue_number, 123);
      return [
        {
          user: { login: 'chatgpt-codex-connector[bot]' },
          body: `
## Work Summary

- [x] Implemented feature A
- [ ] Feature B pending
- [x] Added tests for feature A
          `.trim(),
        },
      ];
    },
    rest: {
      issues: {
        listComments: {},
      },
    },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 123, null);

  assert.strictEqual(states.size, 2);
  assert.strictEqual(states.get('implemented feature a'), true);
  assert.strictEqual(states.get('added tests for feature a'), true);
  assert.strictEqual(states.has('feature b pending'), false);
});

test('fetchConnectorCheckboxStates ignores non-connector comments', async () => {
  const mockGithub = {
    paginate: async () => [
      {
        user: { login: 'regular-user' },
        body: '- [x] User checked something',
      },
      {
        user: { login: 'chatgpt-codex-connector[bot]' },
        body: '- [x] Connector checked this',
      },
    ],
    rest: { issues: { listComments: {} } },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, null);

  assert.strictEqual(states.size, 1);
  assert.strictEqual(states.get('connector checked this'), true);
  assert.strictEqual(states.has('user checked something'), false);
});

test('fetchConnectorCheckboxStates returns empty map when no connector comments exist', async () => {
  const mockGithub = {
    paginate: async () => [
      { user: { login: 'user1' }, body: '- [x] Task done' },
      { user: { login: 'user2' }, body: 'LGTM!' },
    ],
    rest: { issues: { listComments: {} } },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, null);

  assert.strictEqual(states.size, 0);
});

test('fetchConnectorCheckboxStates aggregates checked boxes from multiple connector comments', async () => {
  const mockGithub = {
    paginate: async () => [
      {
        user: { login: 'chatgpt-codex-connector[bot]' },
        body: '- [x] Task A completed',
      },
      {
        user: { login: 'github-actions[bot]' },
        body: '- [x] Task B done\n- [x] Task C done',
      },
      {
        user: { login: 'chatgpt-codex-connector[bot]' },
        body: '- [x] Task D finished',
      },
    ],
    rest: { issues: { listComments: {} } },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, null);

  assert.strictEqual(states.size, 4);
  assert.strictEqual(states.get('task a completed'), true);
  assert.strictEqual(states.get('task b done'), true);
  assert.strictEqual(states.get('task c done'), true);
  assert.strictEqual(states.get('task d finished'), true);
});

test('fetchConnectorCheckboxStates handles API errors gracefully', async () => {
  const mockGithub = {
    paginate: async () => {
      throw new Error('API rate limit exceeded');
    },
    rest: { issues: { listComments: {} } },
  };

  const mockCore = {
    warning: () => {},
    info: () => {},
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, mockCore);

  assert.strictEqual(states.size, 0);
});

test('fetchConnectorCheckboxStates handles comments with null user', async () => {
  const mockGithub = {
    paginate: async () => [
      { user: null, body: '- [x] Orphaned comment' },
      { user: { login: 'chatgpt-codex-connector[bot]' }, body: '- [x] Valid task' },
    ],
    rest: { issues: { listComments: {} } },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, null);

  assert.strictEqual(states.size, 1);
  assert.strictEqual(states.get('valid task'), true);
});
