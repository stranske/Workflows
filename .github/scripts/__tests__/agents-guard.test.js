'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { evaluateGuard } = require('../agents-guard');

const protectedFile = {
  filename: '.github/workflows/agents-foo.yml',
  status: 'modified',
};

const codeownersContent = '.github/workflows/agents-foo.yml @owner';

test('blocks protected workflow edits without label or approval', () => {
  const result = evaluateGuard({
    files: [protectedFile],
    codeownersContent,
    authorLogin: 'someone',
  });

  assert.equal(result.blocked, true);
  assert.equal(result.needsLabel, true);
  assert.equal(result.needsApproval, true);
  assert.equal(result.hasAllowLabel, false);
  assert.ok(result.failureReasons.some((reason) => reason.includes('Missing `agents:allow-change` label.')));
  assert.ok(result.failureReasons.some((reason) => reason.includes('@owner')));
});

test('allows protected workflow edits when the author is a codeowner', () => {
  const result = evaluateGuard({
    files: [protectedFile],
    codeownersContent,
    authorLogin: 'owner',
  });

  assert.equal(result.blocked, false);
  assert.equal(result.hasCodeownerApproval, true);
  assert.equal(result.needsLabel, false);
  assert.equal(result.needsApproval, false);
});

test('blocks deletion of protected workflows that are not allowlisted', () => {
  const result = evaluateGuard({
    files: [{
      filename: '.github/workflows/agents-foo.yml',
      status: 'removed',
    }],
  });

  assert.equal(result.blocked, true);
  assert.ok(result.fatalViolations.some((reason) => reason.includes('was deleted')));
});

test('allows removal of allowlisted workflow paths', () => {
  const result = evaluateGuard({
    files: [{
      filename: '.github/workflows/agents-75-keepalive-on-gate.yml',
      status: 'removed',
    }],
  });

  assert.equal(result.blocked, false);
  assert.equal(result.fatalViolations.length, 0);
});

test('does not allow label-only bypass without codeowner approval', () => {
  const result = evaluateGuard({
    files: [protectedFile],
    codeownersContent,
    labels: [{ name: 'agents:allow-change' }],
    authorLogin: 'someone',
  });

  assert.equal(result.blocked, true);
  assert.equal(result.hasAllowLabel, true);
  assert.equal(result.needsApproval, true);
  assert.ok(result.failureReasons.some((reason) => reason.includes('Request approval from a CODEOWNER')));
});
