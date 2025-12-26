'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { evaluateGuard, validatePullRequestTargetSafety } = require('../agents-guard');

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

test('allows protected workflow edits with codeowner review approval', () => {
  const result = evaluateGuard({
    files: [protectedFile],
    codeownersContent,
    authorLogin: 'someone',
    reviews: [{
      user: { login: 'owner' },
      state: 'APPROVED',
    }],
  });

  assert.equal(result.blocked, false);
  assert.equal(result.hasCodeownerApproval, true);
  assert.equal(result.needsLabel, false);
  assert.equal(result.needsApproval, false);
  assert.equal(result.hasAllowLabel, false);
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

test('blocks renames of protected workflows that are not allowlisted', () => {
  const result = evaluateGuard({
    files: [{
      filename: '.github/workflows/agents-foo-new.yml',
      previous_filename: '.github/workflows/agents-foo.yml',
      status: 'renamed',
    }],
  });

  assert.equal(result.blocked, true);
  assert.ok(result.fatalViolations.some((reason) => reason.includes('was renamed')));
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

test('validatePullRequestTargetSafety skips checks for non pull_request_target events', () => {
  const result = validatePullRequestTargetSafety({
    eventName: 'pull_request',
    fsModule: {
      readFileSync() {
        throw new Error('unexpected read');
      },
    },
  });

  assert.deepEqual(result, { checked: false, violations: [] });
});

test('validatePullRequestTargetSafety blocks unsafe checkout and secrets usage', () => {
  const workflowSource = [
    'on: pull_request_target',
    'jobs:',
    '  test:',
    '    runs-on: ubuntu-latest',
    '    steps:',
    '      - uses: actions/checkout@v4',
    '        with:',
    '          ref: ${{ github.event.pull_request.head.sha }}',
    '      - run: |',
    '          echo ${{ secrets.MY_SECRET }}',
  ].join('\n');

  assert.throws(
    () => validatePullRequestTargetSafety({
      eventName: 'pull_request_target',
      workflowPath: '.github/workflows/agents-guard.yml',
      workspaceRoot: process.cwd(),
      fsModule: { readFileSync: () => workflowSource },
    }),
    /Unsafe pull_request_target usage detected/,
  );
});

test('validatePullRequestTargetSafety allows safe pull_request_target workflow', () => {
  const workflowSource = [
    'on: pull_request_target',
    'jobs:',
    '  test:',
    '    runs-on: ubuntu-latest',
    '    steps:',
    '      - uses: actions/checkout@v4',
    '        with:',
    '          fetch-depth: 1',
    '      - run: echo "hello"',
  ].join('\n');

  const result = validatePullRequestTargetSafety({
    eventName: 'pull_request_target',
    workflowPath: '.github/workflows/agents-guard.yml',
    workspaceRoot: process.cwd(),
    fsModule: { readFileSync: () => workflowSource },
  });

  assert.deepEqual(result, { checked: true, violations: [] });
});

test('validatePullRequestTargetSafety throws when workflow file cannot be read', () => {
  assert.throws(
    () => validatePullRequestTargetSafety({
      eventName: 'pull_request_target',
      workflowPath: '.github/workflows/agents-guard.yml',
      workspaceRoot: process.cwd(),
      fsModule: { readFileSync: () => { throw new Error('no access'); } },
    }),
    /Failed to read \.github\/workflows\/agents-guard\.yml: no access/,
  );
});
