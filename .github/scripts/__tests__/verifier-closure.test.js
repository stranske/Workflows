'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { sourceHash, closingRule, closureDecision, closeVerifiedSources } = require('../verifier_closure.js');
const mergeSha = 'a'.repeat(40);
const body = '## Acceptance Criteria\n- [ ] `pytest tests/test_gate.py` passes';
const command = { criterion: 0, command: 'pytest tests/test_gate.py' };
const plan = { issue_number: 123, repository: 'owner/repo', pr_number: 5,
  head_sha: mergeSha, source_hash: sourceHash(body), commands: [command] };
const result = { ...plan, results: [{ ...command, exit_code: 0 }] };
const ci = [{ head_sha: mergeSha, conclusion: 'success' }];
const input = { verdict: 'UNVERIFIABLE_INPUT', mergeSha, plan, result, ci, currentBody: body };

test('PASS closes; incomplete input closes only with exact merge gate and CI PASS', () => {
  assert.equal(closingRule({ ...input, verdict: 'PASS', result: undefined }), 'verifier-pass');
  assert.equal(closingRule(input), 'unverifiable-input+gate+ci');
});

test('PASS without merge CI refuses with pass-without-ci', () => {
  for (const ci of [undefined, [], [{ head_sha: 'b'.repeat(40), conclusion: 'success' }]]) {
    const candidate = { ...input, verdict: 'PASS', ci };
    assert.equal(closingRule(candidate), null);
    assert.equal(closureDecision(candidate).reason, 'pass-without-ci');
  }
});

test('PASS requires every CI row successful and bound to the merge SHA', () => {
  for (const row of [
    { head_sha: 'b'.repeat(40), conclusion: 'success' },
    { head_sha: mergeSha, conclusion: 'failure' },
    { head_sha: mergeSha, conclusion: 'success', error_category: 'permission' },
  ]) assert.equal(closingRule({ ...input, verdict: 'PASS', ci: [...ci, row] }), null);
});

const ciPlan = { ...plan, commands: [], gate_source: 'required-ci' };
const ciResult = { ...ciPlan, results: [] };
const ciInput = { ...input, plan: ciPlan, result: ciResult };
test('no acceptance commands uses required merge CI as the deterministic gate', () => {
  assert.equal(closingRule(ciInput), 'unverifiable-input+gate+ci');
  assert.equal(closureDecision(ciInput).gate_source, 'required-ci');
  assert.equal(closureDecision(input).gate_source, 'acceptance-commands');
});
for (const [name, changes] of Object.entries({
  'empty CI': { ci: [] },
  'stale CI': { ci: [{ head_sha: 'b'.repeat(40), conclusion: 'success' }] },
  'red CI': { ci: [{ head_sha: mergeSha, conclusion: 'failure' }] },
  'pending CI': { ci: [{ head_sha: mergeSha, conclusion: 'queued' }] },
  'missing result': { result: undefined },
  'changed source': { currentBody: body + 'more' },
  'unbound gate source': { result: { ...ciResult, gate_source: undefined } },
  'wrong PR': { result: { ...ciResult, pr_number: 999 } },
  'command gate failed': { plan, result: { ...result, results: [{ ...command, exit_code: 1 }] } },
})) {
  test(`required-CI fallback refuses ${name}`, () => assert.equal(closingRule({ ...ciInput, ...changes }), null));
}

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
  assert.match(writes[0].body, /unverifiable-input\+gate\+ci/);
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
test('PASS refuses even explicitly optional skipped CI: every supplied row must succeed', () => {
  assert.equal(closingRule({ ...input, verdict: 'PASS', ci: [{head_sha: mergeSha, conclusion: 'skipped', required: false}] }), null);
});

test('every linked issue logs its outcome, including when nothing closes', async () => {
  const messages = [], writes = [];
  const github = { rest: {
    pulls: { get: async () => ({ data: { merged: true, merge_commit_sha: mergeSha } }) },
    issues: {
      get: async ({issue_number}) => {
        if (issue_number === 126) throw new Error('API unavailable');
        return { data: { body, state: issue_number === 124 ? 'closed' : 'open' } };
      },
      createComment: async args => writes.push(args),
      update: async args => writes.push(args),
    },
  } };
  const options = { github, core: { info: message => messages.push(message) },
    context: { repo: { owner: 'owner', repo: 'repo' } }, verdict: 'PASS', mergeSha, prNumber: 5,
    plans: [plan, { ...plan, issue_number: 124 },
      { ...plan, issue_number: 125, plan_error: 'closure-plan-unavailable' },
      { ...plan, issue_number: 126 }], results: [], ci: [] };
  assert.deepEqual(await closeVerifiedSources(options), []);
  assert.deepEqual(writes, []);
  assert.deepEqual(messages, [
    'owner/repo#123: kept open — pass-without-ci',
    'owner/repo#124: unchanged — already-closed',
    'owner/repo#125: kept open — closure-plan-unavailable',
    'owner/repo#126: kept open — source-issue-unavailable',
  ]);
  messages.length = 0;
  assert.deepEqual(await closeVerifiedSources({ ...options, verdict: 'FAIL', ci }), []);
  assert.equal(messages[0], 'owner/repo#123: kept open — verdict-FAIL');
  messages.length = 0;
  assert.deepEqual(await closeVerifiedSources({ ...options, verdict: 'UNVERIFIABLE_INPUT',
    plans: [ciPlan], results: [ciResult], ci }), [123]);
  assert.match(messages[0], /closed — unverifiable-input\+gate\+ci; gate_source=required-ci/);
  assert.match(writes[0].body, /gate_source=required-ci/);
});
