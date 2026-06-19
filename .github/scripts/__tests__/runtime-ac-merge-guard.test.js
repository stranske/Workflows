'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  assertRuntimeAcMergeAllowed,
  hasRuntimeAcRequirement,
  normalizeLabelName,
  runtimeAcRequirement,
} = require('../runtime_ac_merge_guard');

function githubWithLabels(labels, calls = []) {
  return {
    rest: {
      issues: {
        listLabelsOnIssue: async (params) => {
          calls.push(params);
          return { data: labels };
        },
      },
    },
  };
}

test('normalizes string and object labels', () => {
  assert.equal(normalizeLabelName(' Runtime-AC '), 'runtime-ac');
  assert.equal(normalizeLabelName({ name: 'Verify:Runtime-Checks' }), 'verify:runtime-checks');
  assert.equal(normalizeLabelName({}), '');
});

test('allows PRs without runtime AC labels', async () => {
  const result = await assertRuntimeAcMergeAllowed({
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 123,
    labels: [{ name: 'automerge' }, { name: 'risk:low' }],
  });

  assert.deepEqual(result, { allowed: true, labels: [] });
  assert.equal(hasRuntimeAcRequirement(['automerge']), false);
});

test('blocks exact runtime AC labels', async () => {
  await assert.rejects(
    () =>
      assertRuntimeAcMergeAllowed({
        owner: 'stranske',
        repo: 'Workflows',
        prNumber: 124,
        labels: [{ name: 'runtime-ac' }],
        source: 'test lane',
      }),
    (error) => {
      assert.equal(error.code, 'runtime_ac_merge_blocked');
      assert.match(error.message, /Runtime AC merge guard blocked test lane/);
      assert.deepEqual(error.labels, ['runtime-ac']);
      return true;
    },
  );
});

test('blocks prefixed labels using Orchestrator suffix semantics', () => {
  const requirement = runtimeAcRequirement([
    { name: 'verify:runtime-checks' },
    { name: 'team:blue' },
  ]);

  assert.deepEqual(requirement, {
    required: true,
    labels: ['verify:runtime-checks'],
  });
});

test('trims first-colon suffixes to match Orchestrator semantics', () => {
  const requirement = runtimeAcRequirement([{ name: 'verify: runtime-ac ' }]);

  assert.deepEqual(requirement, {
    required: true,
    labels: ['verify: runtime-ac'],
  });
});

test('does not match runtime labels after a second colon', () => {
  const requirement = runtimeAcRequirement([{ name: 'runner:verify:runtime-ac' }]);

  assert.deepEqual(requirement, {
    required: false,
    labels: [],
  });
});

test('fetches labels through the supplied retry wrapper when labels are absent', async () => {
  const calls = [];
  let retryCalls = 0;
  const github = githubWithLabels([{ name: 'automerge' }], calls);
  const result = await assertRuntimeAcMergeAllowed({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    prNumber: 125,
    withRetry: async (fn) => {
      retryCalls += 1;
      return fn(github);
    },
  });

  assert.deepEqual(result, { allowed: true, labels: [] });
  assert.equal(retryCalls, 1);
  assert.deepEqual(calls, [
    {
      owner: 'stranske',
      repo: 'Workflows',
      issue_number: 125,
      per_page: 100,
    },
  ]);
});

test('fails closed when labels cannot be fetched', async () => {
  const github = {
    rest: {
      issues: {
        listLabelsOnIssue: async () => {
          throw new Error('rate limited');
        },
      },
    },
  };

  await assert.rejects(
    () =>
      assertRuntimeAcMergeAllowed({
        github,
        owner: 'stranske',
        repo: 'Workflows',
        prNumber: 126,
      }),
    /Unable to evaluate runtime AC merge labels for PR #126: rate limited/,
  );
});
