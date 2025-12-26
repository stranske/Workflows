'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const repoRoot = path.resolve(__dirname, '../../..');
const issueFormPath = path.join(repoRoot, '.github/ISSUE_TEMPLATE/agent_task.yml');
const issueTemplatePath = path.join(repoRoot, '.github/ISSUE_TEMPLATE/agent-task.md');

const readFile = (filePath) => fs.readFileSync(filePath, 'utf8');

test('agent task issue form includes Scope/Tasks/Acceptance sections', () => {
  const content = readFile(issueFormPath);

  assert.match(content, /label:\s*Scope\b/i);
  assert.match(content, /label:\s*Tasks\b/i);
  assert.match(content, /label:\s*Acceptance criteria\b/i);
});

test('agent task markdown template includes Scope/Tasks/Acceptance sections', () => {
  const content = readFile(issueTemplatePath);

  assert.match(content, /^##\s+Scope\b/m);
  assert.match(content, /^##\s+Tasks\b/m);
  assert.match(content, /^##\s+Acceptance criteria\b/m);
});
