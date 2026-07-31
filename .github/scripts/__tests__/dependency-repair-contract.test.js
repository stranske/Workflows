const assert = require('node:assert/strict');
const test = require('node:test');

const {
  buildPromotionMarker,
  classifyCommit,
  isDependencyBotPullRequest,
  parsePromotionMarker,
  validateMarker,
} = require('../dependency-repair-contract.js');

test('recognizes Renovate and legacy Dependabot identities and branches', () => {
  assert.equal(
    isDependencyBotPullRequest({ user: { login: 'renovate[bot]' }, head: { ref: 'x' } }),
    true,
  );
  assert.equal(
    isDependencyBotPullRequest({ user: { login: 'stranske' }, head: { ref: 'dependabot/pip/x' } }),
    true,
  );
  assert.equal(
    isDependencyBotPullRequest({ user: { login: 'stranske' }, head: { ref: 'feature/x' } }),
    false,
  );
});

test('classifies strict lockfile regeneration but not arbitrary agent work', () => {
  const generated = classifyCommit(
    {
      committer: { login: 'github-actions[bot]' },
      commit: { message: 'chore(deps): regenerate requirements.lock' },
    },
    [{ filename: 'requirements.lock' }],
  );
  assert.equal(generated.kind, 'generated-maintenance');

  const arbitrary = classifyCommit(
    {
      author: { login: 'stranske' },
      commit: { message: 'fix CI and copy workflow templates' },
    },
    [{ filename: 'templates/consumer-repo/.github/workflows/agents-guard.yml' }],
  );
  assert.equal(arbitrary.kind, 'unclassified');
});

test('does not let a generated-looking message authorize source edits', () => {
  const result = classifyCommit(
    {
      committer: { login: 'github-actions[bot]' },
      commit: { message: 'chore(deps): update lockfile' },
    },
    [{ filename: '.github/workflows/agents-guard.yml' }],
  );
  assert.equal(result.kind, 'unclassified');
});

test('round-trips a valid promotion marker', () => {
  const metadata = {
    source_pr: 2795,
    source_base_sha: '1'.repeat(40),
    source_head_sha: '2'.repeat(40),
    promotion_base_sha: '3'.repeat(40),
  };
  const marker = buildPromotionMarker(metadata);
  assert.deepEqual(parsePromotionMarker(`Context\n\n${marker}\n`), metadata);
  assert.deepEqual(validateMarker(metadata), []);
});

test('reports malformed promotion metadata', () => {
  const errors = validateMarker({
    source_pr: 0,
    source_base_sha: 'short',
    source_head_sha: '',
    promotion_base_sha: 'not-a-sha',
  });
  assert.equal(errors.length, 4);
});
