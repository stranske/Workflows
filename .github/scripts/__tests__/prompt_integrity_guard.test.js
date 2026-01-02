/**
 * Tests for prompt_integrity_guard.js
 */

const fs = require('fs');
const path = require('path');
const { before, after, describe, test } = require('node:test');
const assert = require('node:assert/strict');
const { checkPromptIntegrity, TASK_CONTENT_PATTERNS } = require('../prompt_integrity_guard');

// Create temp directory for test files
const TEST_DIR = path.join(__dirname, '.test-fixtures');

before(() => {
  if (!fs.existsSync(TEST_DIR)) {
    fs.mkdirSync(TEST_DIR, { recursive: true });
  }
});

after(() => {
  // Clean up test files
  if (fs.existsSync(TEST_DIR)) {
    fs.rmSync(TEST_DIR, { recursive: true });
  }
});

function writeTestFile(name, content) {
  const filePath = path.join(TEST_DIR, name);
  fs.writeFileSync(filePath, content);
  return filePath;
}

describe('checkPromptIntegrity', () => {
  test('clean template passes validation', () => {
    const content = `# Keepalive Next Task

You are an expert coding agent. Your job is to complete the next task.

**The Tasks and Acceptance Criteria are provided in the appendix below.**

<!-- 
  DO NOT ADD TASK CONTENT BELOW THIS LINE
  Task content is dynamically injected via appendix.
-->`;

    const filePath = writeTestFile('clean-template.md', content);
    const result = checkPromptIntegrity(filePath);

    assert.equal(result.clean, true);
    assert.equal(result.violations.length, 0);
  });

  test('detects PR Tasks header', () => {
    const content = `# Keepalive Next Task

## PR Tasks and Acceptance Criteria

### Tasks
- [ ] Do something`;

    const filePath = writeTestFile('with-pr-tasks-header.md', content);
    const result = checkPromptIntegrity(filePath);

    assert.equal(result.clean, false);
    assert.ok(result.violations.some(v => v.description.includes('PR Tasks header')));
  });

  test('detects Progress counter', () => {
    const content = `# Keepalive Next Task

**Progress:** 4/7 tasks complete`;

    const filePath = writeTestFile('with-progress.md', content);
    const result = checkPromptIntegrity(filePath);

    assert.equal(result.clean, false);
    assert.ok(result.violations.some(v => v.description.includes('Progress counter')));
  });

  test('detects checked checkboxes', () => {
    const content = `# Keepalive Next Task

- [x] Completed task
- [ ] Pending task`;

    const filePath = writeTestFile('with-checked-boxes.md', content);
    const result = checkPromptIntegrity(filePath);

    assert.equal(result.clean, false);
    assert.ok(result.violations.some(v => v.description.includes('Checked checkbox')));
  });

  test('detects task checkboxes with action verbs', () => {
    const content = `# Keepalive Next Task

- [ ] Extend the API with new endpoint
- [ ] Add tests for the feature`;

    const filePath = writeTestFile('with-action-tasks.md', content);
    const result = checkPromptIntegrity(filePath);

    assert.equal(result.clean, false);
    assert.ok(result.violations.some(v => v.description.includes('action verb')));
  });

  test('detects content after guard marker', () => {
    const content = `# Keepalive Next Task

<!-- 
  DO NOT ADD TASK CONTENT BELOW THIS LINE
-->

### Stale Tasks
- [ ] This should not be here`;

    const filePath = writeTestFile('content-after-marker.md', content);
    const result = checkPromptIntegrity(filePath);

    assert.equal(result.clean, false);
    assert.ok(result.violations.some(v => v.description.includes('after guard marker')));
  });

  test('strict mode detects issue references', () => {
    const content = `# Keepalive Next Task

This task relates to issue-453.`;

    const filePath = writeTestFile('with-issue-ref.md', content);
    
    // Non-strict should pass
    const normalResult = checkPromptIntegrity(filePath, false);
    assert.equal(normalResult.clean, true);

    // Strict should fail
    const strictResult = checkPromptIntegrity(filePath, true);
    assert.equal(strictResult.clean, false);
    assert.ok(strictResult.violations.some(v => v.description.includes('Issue number')));
  });

  test('strict mode detects PR number references', () => {
    const content = `# Keepalive Next Task

Working on PR #458`;

    const filePath = writeTestFile('with-pr-ref.md', content);
    
    const strictResult = checkPromptIntegrity(filePath, true);
    assert.equal(strictResult.clean, false);
    assert.ok(strictResult.violations.some(v => v.description.includes('PR number')));
  });

  test('allows example checkboxes in instruction section', () => {
    const content = `# Keepalive Next Task

When you complete a task, mark it like this:
- [x] Example completed task

Then move to the next one.

<!-- 
  DO NOT ADD TASK CONTENT BELOW THIS LINE
-->`;

    const filePath = writeTestFile('with-example.md', content);
    const result = checkPromptIntegrity(filePath);
    
    // Example checkboxes before the guard marker are allowed (they're instructions)
    assert.equal(result.clean, true);
  });
});

describe('TASK_CONTENT_PATTERNS', () => {
  test('all patterns are valid regex', () => {
    for (const { pattern, description } of TASK_CONTENT_PATTERNS) {
      assert.doesNotThrow(() => new RegExp(pattern));
      assert.ok(description);
    }
  });
});
