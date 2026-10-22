'use strict';

const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const { determineNextStep } = require('../../.github/scripts/auto_pilot_transitions.js');

const workflowPath = path.join(
  __dirname,
  '../../.github/workflows/agents-auto-pilot.yml',
);

test('verify step documents absent/incomplete handoff without issue-only verify label', () => {
  const workflow = fs.readFileSync(workflowPath, 'utf8');
  assert.match(workflow, /verify_handoff['"],\s*handoffState/);
  assert.match(workflow, /truncated \? 'incomplete' : 'absent'/);
  assert.doesNotMatch(
    workflow,
    /couldn't find linked merged PR[\s\S]*labels: \['verify:evaluate'\]/,
  );
  assert.match(workflow, /verify:pr-handoff/);
  assert.match(workflow, /for \(let page = 1; page <= maxPages; page \+= 1\)/);
  assert.match(workflow, /client\.rest\.pulls\.list\(\{/);
  assert.match(workflow, /verification triggered on a merged source PR/);
});

test('closed issue with verify:evaluate only remains on verify step', () => {
  const result = determineNextStep({
    issueState: 'closed',
    hasVerify: true,
    verifyHandoffBound: false,
  });
  assert.equal(result.nextStep, 'verify');
});
