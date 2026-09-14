"use strict";
const test = require('node:test');
const assert = require('node:assert/strict');
const { buildStatusBlock, collectStatusWorkflowRuns } = require('../agents_pr_meta_update_body.js');
const headSha = 'implementation-head';
const contractName = 'PR 46 Dependency Repair Contract';
const contract = { name: contractName, head_sha: headSha, status: 'completed', conclusion: 'success', created_at: '2026-09-14T10:00:00Z', html_url: 'https://example.com/runs/1' };
const gate = { ...contract, name: 'Gate', html_url: 'https://example.com/gate' };
function render(runs) {
  return buildStatusBlock({ scope: 'scope', tasks: '- [x] task', acceptance: '- [ ] verify', headSha,
    workflowRuns: runs instanceof Map ? runs : new Map(runs.map(r => [r.name.toLowerCase(), r])),
    requiredChecks: ['gate', contractName], existingBody: '', connectorStates: new Map(),
    agentType: '', owner: 'stranske', repo: 'Workflows' });
}
function client(recent, completed = []) {
  const calls = [];
  return { calls, rest: { actions: {
    listWorkflowRunsForRepo: async args => { calls.push(args); return {data:{workflow_runs:recent}}; },
    listWorkflowRuns: async args => { calls.push(args); return {data:{workflow_runs:completed}}; },
  }}};
}
for (const conclusion of ['success', 'failure', 'skipped', 'cancelled']) {
  test(`dependency contract ${conclusion} is visible without the changing run URL`, () => {
    const summary = render([gate, {...contract, conclusion}]);
    assert.ok(summary.includes(`${contractName}:`));
    assert.ok(!summary.includes(`${contractName}: ⏸️ not started`));
    assert.ok(summary.includes(`| ${contractName} |`));
    assert.ok(summary.includes(conclusion));
    assert.ok(!summary.includes(contract.html_url));
    assert.equal(summary, render([gate, {...contract, conclusion, created_at:'2026-09-14T11:00:00Z', html_url:'https://example.com/runs/2'}]));
  });
}
test('real dependency contract failure changes the summary', () => {
  assert.notEqual(render([gate, contract]), render([gate, {...contract, conclusion:'failure'}]));
});
test('new pending metadata run retains latest completed contract evidence on the same head', async () => {
  const github = client([gate, contract, {...contract, status:'in_progress', conclusion:null, created_at:'2026-09-14T11:00:00Z'}]);
  const runs = await collectStatusWorkflowRuns({github, owner:'stranske', repo:'Workflows', headSha});
  assert.equal(render(runs), render([gate, contract]));
  assert.equal(github.calls.length, 1);
});
test('flooded completed contract lookup is bounded and exact-head', async () => {
  const github = client([gate, {...contract, status:'in_progress', conclusion:null}], [contract]);
  const runs = await collectStatusWorkflowRuns({github, owner:'stranske', repo:'Workflows', headSha});
  assert.equal(render(runs), render([gate, contract]));
  assert.equal(github.calls.length, 2);
  assert.deepEqual(github.calls[1], { owner:'stranske', repo:'Workflows', workflow_id:'pr-46-dependency-repair-contract.yml', head_sha:headSha, status:'completed', per_page:1 });
});
test('wrong-head or absent contract evidence cannot claim success or not-started', async () => {
  for (const evidence of [[], [{...contract, head_sha:'other-head'}]]) {
    const github = client([gate, {...contract, status:'in_progress', conclusion:null}], evidence);
    const runs = await collectStatusWorkflowRuns({github, owner:'stranske', repo:'Workflows', headSha});
    const summary = render(runs);
    assert.ok(!summary.includes(`${contractName}: ✅ success`));
    assert.ok(!summary.includes(`${contractName}: ⏸️ not started`));
    assert.ok(summary.includes('reported separately in PR checks'));
  }
});
test('renamed dependency contract is still represented through its workflow path', () => {
  const summary = render([gate, {...contract, name:'Renamed provenance', path:'.github/workflows/pr-46-dependency-repair-contract.yml@refs/heads/main', conclusion:'failure'}]);
  assert.ok(summary.includes(`${contractName}: ❌ failure`));
  assert.ok(!summary.includes(contract.html_url));
});

for (const status of [401, 403, 429, 500]) {
  test(`contract lookup ${status} propagates after one attempt`, async () => {
    const github = client([gate, {...contract, status:'queued', conclusion:null}]);
    github.rest.actions.listWorkflowRuns = async args => {
      github.calls.push(args);
      throw Object.assign(new Error('contract lookup failed'), {status});
    };
    await assert.rejects(collectStatusWorkflowRuns({github, owner:'stranske', repo:'Workflows', headSha}), /contract lookup failed/);
    assert.equal(github.calls.length, 2);
  });
}
test('missing contract workflow remains explicit unknown rather than preserving stale success', async () => {
  const github = client([gate, {...contract, status:'queued', conclusion:null}]);
  github.rest.actions.listWorkflowRuns = async () => { throw Object.assign(new Error('missing'), {status:404}); };
  const runs = await collectStatusWorkflowRuns({github, owner:'stranske', repo:'Workflows', headSha});
  assert.ok(render(runs).includes(`${contractName}: reported separately in PR checks`));
});
test('failure stays visible while a later metadata rerun is pending', async () => {
  const failed = {...contract, conclusion:'failure'};
  const github = client([gate, failed, {...contract, status:'in_progress', conclusion:null, created_at:'2026-09-14T11:00:00Z'}]);
  const runs = await collectStatusWorkflowRuns({github, owner:'stranske', repo:'Workflows', headSha});
  assert.equal(render(runs), render([gate, failed]));
});
