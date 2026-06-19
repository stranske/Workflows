'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { evaluateGuard, validatePullRequestTargetSafety } = require('../agents-guard');

const protectedFile = {
  filename: '.github/workflows/agents-foo.yml',
  status: 'modified',
};

const codeownersContent = '.github/workflows/agents-foo.yml @owner';
const actionVersionPatch = [
  '@@ -1,3 +1,3 @@',
  ' steps:',
  '   - name: Checkout',
  '-    uses: actions/checkout@v6',
  '+    uses: actions/checkout@v7',
].join('\n');
const workflowLogicPatch = [
  '@@ -1,3 +1,3 @@',
  ' steps:',
  '-  - run: echo old',
  '+  - run: echo new',
].join('\n');
const usesCommentOnlyPatch = [
  '@@ -1,3 +1,3 @@',
  ' steps:',
  '-    uses: actions/checkout@v7 # old note',
  '+    uses: actions/checkout@v7 # new note',
].join('\n');
const swappedActionPatch = [
  '@@ -1,4 +1,4 @@',
  ' steps:',
  '-    uses: actions/checkout@v6',
  '-    uses: actions/setup-node@v4',
  '+    uses: actions/setup-node@v4',
  '+    uses: actions/checkout@v7',
].join('\n');

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

test('blocks protected edits with a comment body that lists next steps', () => {
  const result = evaluateGuard({
    files: [protectedFile],
    codeownersContent,
    authorLogin: 'someone',
  });

  assert.ok(result.commentBody);
  assert.ok(result.commentBody.startsWith(result.marker));
  assert.ok(result.commentBody.includes('**Next steps**'));
  assert.ok(result.commentBody.includes('Apply the `agents:allow-change` label'));
  assert.ok(result.commentBody.includes('Ask a CODEOWNER'));
  assert.ok(result.commentBody.includes('.github/workflows/agents-foo.yml (modified)'));
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

test('treats allow-change labels as case-insensitive', () => {
  const result = evaluateGuard({
    files: [protectedFile],
    codeownersContent,
    authorLogin: 'someone',
    labels: [{ name: 'Agents:Allow-Change' }],
    reviews: [{
      user: { login: 'owner' },
      state: 'APPROVED',
    }],
  });

  assert.equal(result.blocked, false);
  assert.equal(result.hasAllowLabel, true);
  assert.equal(result.hasCodeownerApproval, true);
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
  const allowlistedPaths = [
    '.github/workflows/agents-75-keepalive-on-gate.yml',
    '.github/workflows/agents-keepalive-pr.yml',
    '.github/workflows/agents-63-chatgpt-issue-sync.yml',
    '.github/workflows/agents-63-issue-intake.yml',
    '.github/workflows/agents-64-pr-comment-commands.yml',
    '.github/workflows/agents-74-pr-body-writer.yml',
    '.github/workflows/agents-pr-meta.yml',
    '.github/workflows/agents-pr-meta-v2.yml',
    '.github/workflows/agents-pr-meta-v3.yml',
    '.github/workflows/agents-verify-to-issue.yml',
    '.github/workflows/agents-belt-dispatcher.yml',
    '.github/workflows/agents-belt-worker.yml',
    '.github/workflows/agents-belt-conveyor.yml',
  ];

  for (const filename of allowlistedPaths) {
    const result = evaluateGuard({
      files: [{
        filename,
        status: 'removed',
      }],
    });

    assert.equal(result.blocked, false, filename);
    assert.equal(result.fatalViolations.length, 0, filename);
  }
});

test('blocks consumer-only allowlisted workflow removals in Workflows repo', () => {
  const result = evaluateGuard({
    repository: 'stranske/Workflows',
    files: [{
      filename: '.github/workflows/agents-autofix-loop.yml',
      status: 'removed',
    }],
  });

  assert.equal(result.blocked, true);
  assert.ok(result.fatalViolations.some((reason) => reason.includes('was deleted')));
});

test('uses GITHUB_REPOSITORY when evaluating consumer-only removals', () => {
  const previousRepository = process.env.GITHUB_REPOSITORY;
  process.env.GITHUB_REPOSITORY = 'stranske/Workflows';

  try {
    const result = evaluateGuard({
      files: [{
        filename: '.github/workflows/agents-autofix-loop.yml',
        status: 'removed',
      }],
    });

    assert.equal(result.blocked, true);
    assert.ok(result.fatalViolations.some((reason) => reason.includes('was deleted')));
  } finally {
    if (previousRepository === undefined) {
      delete process.env.GITHUB_REPOSITORY;
    } else {
      process.env.GITHUB_REPOSITORY = previousRepository;
    }
  }
});

test('allows consumer-only allowlisted workflow removals in consumer repos', () => {
  const result = evaluateGuard({
    repository: 'stranske/Template',
    files: [{
      filename: '.github/workflows/agents-autofix-loop.yml',
      status: 'removed',
    }],
  });

  assert.equal(result.blocked, false);
  assert.equal(result.fatalViolations.length, 0);
});

test('blocks renames of allowlisted removal paths', () => {
  const result = evaluateGuard({
    repository: 'stranske/Template',
    files: [{
      filename: '.github/workflows/agents-new-entrypoint.yml',
      previous_filename: '.github/workflows/agents-autofix-loop.yml',
      status: 'renamed',
    }],
  });

  assert.equal(result.blocked, true);
  assert.ok(result.fatalViolations.some((reason) => reason.includes('was renamed')));
});

test('allows archive renames of allowlisted removal paths', () => {
  const result = evaluateGuard({
    repository: 'stranske/Template',
    files: [{
      filename: 'archives/deprecated-workflows/agents-autofix-loop.yml',
      previous_filename: '.github/workflows/agents-autofix-loop.yml',
      status: 'renamed',
    }],
  });

  assert.equal(result.blocked, false);
  assert.equal(result.fatalViolations.length, 0);
});

test('allows renames into retired workflow archive directory', () => {
  const result = evaluateGuard({
    repository: 'stranske/Template',
    files: [{
      filename: '.github/workflows/archive/agents-autofix-loop.yml',
      previous_filename: '.github/workflows/agents-autofix-loop.yml',
      status: 'renamed',
    }],
  });

  assert.equal(result.blocked, false);
  assert.equal(result.fatalViolations.length, 0);
});

test('allows renames into legacy workflows-archive directory', () => {
  const result = evaluateGuard({
    repository: 'stranske/Travel-Plan-Permission',
    files: [{
      filename: '.github/workflows-archive/agents-autofix-loop.yml',
      previous_filename: '.github/workflows/agents-autofix-loop.yml',
      status: 'renamed',
    }],
  });

  assert.equal(result.blocked, false);
  assert.equal(result.fatalViolations.length, 0);
});

test('blocks consumer-only archive renames in Workflows repo', () => {
  const result = evaluateGuard({
    repository: 'stranske/Workflows',
    files: [{
      filename: 'archives/deprecated-workflows/agents-autofix-loop.yml',
      previous_filename: '.github/workflows/agents-autofix-loop.yml',
      status: 'renamed',
    }],
  });

  assert.equal(result.blocked, true);
  assert.ok(result.fatalViolations.some((reason) => reason.includes('was renamed')));
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

test('allows dependency bot action version updates with allow-change label', () => {
  const result = evaluateGuard({
    files: [{ ...protectedFile, patch: actionVersionPatch }],
    codeownersContent: '.github/workflows/agents-foo.yml @octo/security',
    labels: [{ name: 'agents:allow-change' }],
    authorLogin: 'renovate[bot]',
  });

  assert.equal(result.blocked, false);
  assert.equal(result.hasAllowLabel, true);
  assert.equal(result.hasDependencyUpgradeBypass, true);
  assert.equal(result.protectedChangesAreDependencyOnly, true);
  assert.equal(result.needsApproval, false);
});

test('allows maintainer action version updates with allow-change label', () => {
  const result = evaluateGuard({
    files: [{ ...protectedFile, patch: actionVersionPatch }],
    codeownersContent: '.github/workflows/agents-foo.yml @octo/security',
    labels: [{ name: 'agents:allow-change' }],
    authorLogin: 'stranske',
    authorAssociation: 'OWNER',
  });

  assert.equal(result.blocked, false);
  assert.equal(result.hasAllowLabel, true);
  assert.equal(result.hasDependencyUpgradeBypass, true);
  assert.equal(result.protectedChangesAreDependencyOnly, true);
  assert.equal(result.needsApproval, false);
});

test('blocks labeled maintainer edits that change workflow logic', () => {
  const result = evaluateGuard({
    files: [{ ...protectedFile, patch: workflowLogicPatch }],
    codeownersContent: '.github/workflows/agents-foo.yml @octo/security',
    labels: [{ name: 'agents:allow-change' }],
    authorLogin: 'stranske',
    authorAssociation: 'OWNER',
  });

  assert.equal(result.blocked, true);
  assert.equal(result.hasAllowLabel, true);
  assert.equal(result.hasDependencyUpgradeBypass, false);
  assert.equal(result.protectedChangesAreDependencyOnly, false);
  assert.equal(result.needsApproval, true);
  assert.ok(result.failureReasons.some((reason) => reason.includes('Request approval from a CODEOWNER')));
});

test('blocks labeled maintainer edits that only change uses-line comments', () => {
  const result = evaluateGuard({
    files: [{ ...protectedFile, patch: usesCommentOnlyPatch }],
    codeownersContent: '.github/workflows/agents-foo.yml @octo/security',
    labels: [{ name: 'agents:allow-change' }],
    authorLogin: 'stranske',
    authorAssociation: 'OWNER',
  });

  assert.equal(result.blocked, true);
  assert.equal(result.hasDependencyUpgradeBypass, false);
  assert.equal(result.protectedChangesAreDependencyOnly, false);
  assert.equal(result.needsApproval, true);
});

test('blocks labeled maintainer edits that swap actions between uses lines', () => {
  const result = evaluateGuard({
    files: [{ ...protectedFile, patch: swappedActionPatch }],
    codeownersContent: '.github/workflows/agents-foo.yml @octo/security',
    labels: [{ name: 'agents:allow-change' }],
    authorLogin: 'stranske',
    authorAssociation: 'OWNER',
  });

  assert.equal(result.blocked, true);
  assert.equal(result.hasDependencyUpgradeBypass, false);
  assert.equal(result.protectedChangesAreDependencyOnly, false);
  assert.equal(result.needsApproval, true);
});

test('requires explicit approval when codeowners only list a team', () => {
  const result = evaluateGuard({
    files: [protectedFile],
    codeownersContent: '.github/workflows/agents-foo.yml @octo/security',
    labels: [{ name: 'agents:allow-change' }],
    authorLogin: 'someone',
  });

  assert.equal(result.blocked, true);
  assert.equal(result.hasAllowLabel, true);
  assert.equal(result.needsApproval, true);
  assert.ok(result.failureReasons.some((reason) => reason.includes('Request approval from a CODEOWNER.')));
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
