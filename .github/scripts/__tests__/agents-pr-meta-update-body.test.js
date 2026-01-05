'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { buildStatusBlock } = require('../agents_pr_meta_update_body');

test('buildStatusBlock inserts context between scope and tasks', () => {
  const result = buildStatusBlock({
    scope: 'Scope text',
    contextSection: '## Context for Agent\n- Related #123',
    tasks: '- [ ] Task one',
    acceptance: '- [ ] Done',
    headSha: 'abc123',
    workflowRuns: new Map(),
    requiredChecks: [],
    existingBody: '',
    connectorStates: new Map(),
    core: null,
    agentType: 'codex',
  });

  const scopeIndex = result.indexOf('#### Scope');
  const contextIndex = result.indexOf('<!-- context:start -->');
  const tasksIndex = result.indexOf('#### Tasks');

  assert.ok(scopeIndex !== -1, 'scope header missing');
  assert.ok(contextIndex !== -1, 'context markers missing');
  assert.ok(tasksIndex !== -1, 'tasks header missing');
  assert.ok(scopeIndex < contextIndex, 'context should appear after scope');
  assert.ok(contextIndex < tasksIndex, 'context should appear before tasks');
  assert.ok(result.includes('## Context for Agent'));
});

test('buildStatusBlock omits context markers when empty', () => {
  const result = buildStatusBlock({
    scope: 'Scope text',
    contextSection: '',
    tasks: '- [ ] Task one',
    acceptance: '- [ ] Done',
    headSha: 'abc123',
    workflowRuns: new Map(),
    requiredChecks: [],
    existingBody: '',
    connectorStates: new Map(),
    core: null,
    agentType: 'codex',
  });

  assert.ok(!result.includes('<!-- context:start -->'));
  assert.ok(!result.includes('<!-- context:end -->'));
});
