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

test('verify step documents absent handoff without issue-only verify label', () => {
  const workflow = fs.readFileSync(workflowPath, 'utf8');
  assert.match(workflow, /verify_handoff['"],\s*'absent'/);
  assert.doesNotMatch(
    workflow,
    /couldn't find linked merged PR[\s\S]*labels: \['verify:evaluate'\]/,
  );
  assert.match(workflow, /verify:pr-handoff/);
  assert.match(workflow, /paginateWithRetry\(\s*\n\s*github\.rest\.pulls\.list/);
});

test('closed issue with verify:evaluate only remains on verify step', () => {
  const result = determineNextStep({
    issueState: 'closed',
    hasVerify: true,
    verifyHandoffBound: false,
  });
  assert.equal(result.nextStep, 'verify');
});
