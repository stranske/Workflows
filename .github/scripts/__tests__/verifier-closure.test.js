'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { sourceHash, closingRule, closeVerifiedSources } = require('../verifier_closure.js');
const mergeSha = 'a'.repeat(40);
const body = '## Acceptance Criteria\n- [ ] `pytest tests/test_gate.py` passes';
const command = { criterion: 0, command: 'pytest tests/test_gate.py' };
const plan = { issue_number: 123, repository: 'owner/repo', pr_number: 5,
  head_sha: mergeSha, source_hash: sourceHash(body), commands: [command] };
const result = { ...plan, results: [{ ...command, exit_code: 0 }] };
const ci = [{ head_sha: mergeSha, conclusion: 'success' }];
const input = { verdict: 'UNVERIFIABLE_INPUT', mergeSha, plan, result, ci, currentBody: body };

test('PASS closes; incomplete input closes only with exact merge gate and CI PASS', () => {
  assert.equal(closingRule({ ...input, verdict: 'PASS', result: undefined, ci: [] }), 'verifier-pass');
  assert.equal(closingRule(input), 'unverifiable-input-merged-head-gates-and-ci');
});

for (const verdict of ['CONCERNS', 'FAIL', 'ERROR', 'unknown']) {
  test(`${verdict} never closes despite green gates and CI`, () => {
    assert.equal(closingRule({ ...input, verdict }), null);
  });
}
for (const [name, changes] of Object.entries({
  'missing gate': { result: undefined },
  'failed gate': { result: { ...result, results: [{ ...command, exit_code: 1 }] } },
  'stale gate': { result: { ...result, head_sha: 'b'.repeat(40) } },
  'partial gate': { result: { ...result, results: [] } },
  'wrong command': { result: { ...result, results: [{ ...command, command: 'true', exit_code: 0 }] } },
  'no extracted commands': { plan: { ...plan, commands: [] } },
  'changed acceptance': { currentBody: body + '\nNew requirement' },
  'failed CI': { ci: [{ head_sha: mergeSha, conclusion: 'failure' }] },
  'stale CI': { ci: [{ head_sha: 'b'.repeat(40), conclusion: 'success' }] },
  'pending CI': { ci: [{ head_sha: mergeSha, conclusion: 'in_progress' }] },
  'missing CI': { ci: [] },
})) {
  test(`incomplete input stays open with ${name}`, () => assert.equal(closingRule({ ...input, ...changes }), null));
}

test('closure posts the named rule before changing issue state, preserves provider verdict', async () => {
  const writes = [];
  const github = { rest: {
    pulls: { get: async () => ({ data: { merged: true, merge_commit_sha: mergeSha } }) },
    issues: {
      get: async () => ({ data: { body, state: 'open' } }),
      createComment: async args => writes.push(args),
      update: async args => writes.push(args),
    },
  } };
  const options = { github, context: { repo: { owner: 'owner', repo: 'repo' } },
    verdict: 'UNVERIFIABLE_INPUT', mergeSha, prNumber: 5, plans: [plan], results: [result], ci };
  assert.deepEqual(await closeVerifiedSources(options), [123]);
  assert.match(writes[0].body, /unverifiable-input-merged-head-gates-and-ci/);
  assert.match(writes[0].body, /provider verdict remains UNVERIFIABLE_INPUT/);
  assert.equal(writes[1].state, 'closed');
  writes.length = 0;
  assert.deepEqual(await closeVerifiedSources({ ...options, verdict: 'CONCERNS' }), []);
  assert.deepEqual(writes, []);
});


test('PASS cannot close acceptance text changed since context capture or fresh red merge CI', () => {
  assert.equal(closingRule({ ...input, verdict: 'PASS', currentBody: body + 'new requirement' }), null);
  assert.equal(closingRule({ ...input, verdict: 'PASS', ci: [{head_sha: mergeSha, conclusion: 'failure'}] }), null);
});

for (const conclusion of ['failure', 'timed_out', 'cancelled', 'startup_failure', 'action_required']) {
  test(`PASS cannot close with red merge CI ${conclusion}`, () => {
    assert.equal(closingRule({ ...input, verdict: 'PASS', ci: [{head_sha: mergeSha, conclusion}] }), null);
  });
}

for (const conclusion of ['skipped', 'in_progress', 'queued', 'unknown', null]) {
  test(`PASS refuses non-green required merge CI ${conclusion}`, () => {
    assert.equal(closingRule({ ...input, verdict: 'PASS', ci: [{head_sha: mergeSha, conclusion, required: true}] }), null);
  });
}
test('PASS permits explicitly optional skipped CI', () => {
  assert.equal(closingRule({ ...input, verdict: 'PASS', ci: [{head_sha: mergeSha, conclusion: 'skipped', required: false}] }), 'verifier-pass');
});
