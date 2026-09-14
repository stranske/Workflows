'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { buildStatusBlock, collectStatusWorkflowRuns } = require('../agents_pr_meta_update_body.js');

const headSha = 'unchanged-implementation-head';
const gate = {
  name: 'Gate', head_sha: headSha, created_at: '2026-09-13T00:00:00Z',
  status: 'completed', conclusion: 'success', html_url: 'https://example.com/gate/42',
};
const observers = ['Agents PR meta manager', 'Agents PR Event Hub', 'PR 46 Dependency Repair Contract'];
function generation(id) {
  return observers.map((name, index) => ({
    name, head_sha: headSha, created_at: `2026-09-14T${id}:00:00Z`,
    status: index === 1 ? 'in_progress' : 'completed',
    conclusion: index === 1 ? null : 'skipped',
    html_url: `https://example.com/metadata/${id}/${index}`,
  }));
}
function render(runs, existingBody = '') {
  return buildStatusBlock({
    scope: 'Keep implementation scope.', tasks: '- [x] Preserve implemented task.',
    acceptance: '- [ ] Verify before merging.', headSha,
    workflowRuns: runs instanceof Map ? runs : new Map(runs.map(run => [run.name.toLowerCase(), run])),
    requiredChecks: ['gate'], existingBody, connectorStates: new Map(),
    agentType: '', owner: 'stranske', repo: 'Fine-Art-Archive', core: null,
  });
}

for (const conclusion of ['success', 'failure', null]) {
  test(`metadata-only generations are idempotent with a real Gate ${conclusion}`, () => {
    const realGate = { ...gate, conclusion, status: conclusion ? 'completed' : 'in_progress' };
    const first = render([...generation('10'), realGate]);
    const second = render([...generation('11'), realGate], first);
    assert.equal(second, first);
    assert.ok(first.includes(gate.html_url));
    assert.ok(!first.includes('/metadata/'));
    assert.ok(first.includes('- [x] Preserve implemented task.'));
    assert.ok(first.includes('- [ ] Verify before merging.'));
  });
}

test('metadata-only generations remain stable without inventing a Gate result', () => {
  const first = render(generation('10'));
  assert.equal(render(generation('11'), first), first);
  assert.ok(first.includes('gate: ⏸️ not started'));
  assert.ok(!first.includes('/metadata/'));
});

test('real Gate transitions still change the visible result', () => {
  const first = render([gate]);
  const second = render([{ ...gate, conclusion: 'failure', html_url: 'https://example.com/gate/43' }], first);
  assert.notEqual(second, first);
  assert.ok(second.includes('gate: ❌ failure'));
  assert.ok(second.includes('/gate/43'));
});

function client(recent, historical, calls = []) {
  return { rest: { actions: {
    listWorkflowRunsForRepo: async args => {
      calls.push(['recent', args]);
      return { data: { workflow_runs: recent } };
    },
    listWorkflowRuns: async args => {
      calls.push(['gate', args]);
      if (historical instanceof Error) throw historical;
      return { data: { workflow_runs: historical } };
    },
  } } };
}
const opts = { owner: 'stranske', repo: 'Fine-Art-Archive', headSha, core: { warning() {}, error() {} } };

test('an older exact-head Gate survives a full page of metadata churn', async () => {
  const calls = [];
  const recent = Array.from({ length: 100 }, (_, i) => generation('11')[i % 3]);
  const runs = await collectStatusWorkflowRuns({ ...opts, github: client(recent, [gate], calls) });
  assert.deepEqual([...runs.keys()], ['gate']);
  assert.ok(render(runs).includes('gate: ✅ success'));
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1][1], {
    owner: opts.owner, repo: opts.repo, workflow_id: 'pr-00-gate.yml', head_sha: headSha, per_page: 1,
  });
});

test('a Gate in the recent page avoids the recovery request', async () => {
  const calls = [];
  await collectStatusWorkflowRuns({ ...opts, github: client([...generation('11'), gate], [], calls) });
  assert.equal(calls.length, 1);
});

test('Gate recovery never uses another implementation head', async () => {
  const runs = await collectStatusWorkflowRuns({ ...opts,
    github: client(generation('11'), [{ ...gate, head_sha: 'other-head' }]),
  });
  assert.ok(render(runs).includes('gate: ⏸️ not started'));
});

test('a missing Gate workflow remains unknown', async () => {
  const error = Object.assign(new Error('Not Found'), { status: 404 });
  const runs = await collectStatusWorkflowRuns({ ...opts, github: client(generation('11'), error) });
  assert.ok(render(runs).includes('gate: ⏸️ not started'));
});

test('Gate API rate limits propagate instead of becoming a not-started result', async () => {
  const error = Object.assign(new Error('API rate limit exceeded'), { status: 403 });
  await assert.rejects(collectStatusWorkflowRuns({ ...opts,
    github: client(generation('11'), error),
  }), /rate limit/);
});
