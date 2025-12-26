'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const promptPath = path.join(
  __dirname,
  '..',
  '..',
  'codex',
  'prompts',
  'verifier_acceptance_check.md'
);

test('verifier prompt relies on CI results for test verification', () => {
  const content = fs.readFileSync(promptPath, 'utf8');

  assert.ok(content.includes('CI Verification'));
  assert.ok(content.includes('Use the "CI Verification" section'));
  assert.ok(content.includes('Do not run test suites locally'));
  assert.ok(content.includes('Only run local checks for file existence'));
});
