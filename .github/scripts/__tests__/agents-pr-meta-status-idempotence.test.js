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

test('recovered Gate summaries stay stable across flooded pages and expose real transitions', async () => {
  async function recoverSummary(id, recoveredGate, existingBody = '') {
    const calls = [];
    const recent = Array.from({ length: 100 }, (_, i) => generation(id)[i % 3]);
    const runs = await collectStatusWorkflowRuns({
      ...opts, github: client(recent, [recoveredGate], calls),
    });
    assert.equal(calls.filter(([kind]) => kind === 'gate').length, 1);
    return render(runs, existingBody);
  }

  const first = await recoverSummary('10', gate);
  const second = await recoverSummary('11', gate, first);
  assert.equal(second, first);
  assert.ok(second.includes('gate: ✅ success'));
  assert.ok(!second.includes('/metadata/'));

  const failedGate = { ...gate, conclusion: 'failure', html_url: 'https://example.com/gate/43' };
  const third = await recoverSummary('12', failedGate, second);
  assert.notEqual(third, second);
  assert.ok(third.includes('gate: ❌ failure'));
  assert.ok(third.includes(failedGate.html_url));
  assert.ok(!third.includes(gate.html_url));
  assert.equal(await recoverSummary('13', failedGate, third), third);
});

test('an empty Gate recovery cannot preserve an earlier successful result', async () => {
  const calls = [];
  const runs = await collectStatusWorkflowRuns({
    ...opts, github: client(generation('11'), [], calls),
  });
  const summary = render(runs, render([gate]));
  assert.equal(runs.size, 0);
  assert.equal(calls.filter(([kind]) => kind === 'gate').length, 1);
  assert.ok(summary.includes('gate: ⏸️ not started'));
  assert.ok(!summary.includes('gate: ✅ success'));
  assert.ok(!summary.includes(gate.html_url));
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

for (const workflowPath of [
  '.github/workflows/agents-pr-meta-v4.yml',
  '.github/workflows/agents-80-pr-event-hub.yml',
  '.github/workflows/pr-46-dependency-repair-contract.yml',
]) {
  test(`renamed observer ${workflowPath} cannot change derived status`, () => {
    const observer = { ...generation('10')[0], name: 'Renamed metadata observer', path: workflowPath };
    const first = render([gate, observer]);
    const second = render([gate, {
      ...observer, path: `${workflowPath}@refs/heads/main`,
      conclusion: 'failure', html_url: 'https://example.com/metadata/new-run',
    }], first);
    assert.equal(first, render([gate]));
    assert.equal(second, first);
  });
}

test('ordinary CI transitions remain visible alongside excluded observers', () => {
  const ci = { ...gate, name: 'CI', path: '.github/workflows/ci.yml' };
  const first = render([gate, ci, ...generation('10')]);
  const second = render([gate, { ...ci, conclusion: 'failure' }, ...generation('11')], first);
  assert.notEqual(first, second);
  assert.ok(second.includes('| CI | ❌ failure |'));
});

test('a wrong-head Gate on the recent page cannot suppress exact-head recovery', async () => {
  const calls = [];
  const runs = await collectStatusWorkflowRuns({ ...opts,
    github: client([{ ...gate, head_sha: 'other-head', conclusion: 'failure' }], [gate], calls),
  });
  assert.equal(calls.length, 2);
  assert.equal(runs.get('gate'), gate);
  assert.ok(render(runs).includes('gate: ✅ success'));
});

test('runs without head evidence are rejected on both pages', async () => {
  const runs = await collectStatusWorkflowRuns({ ...opts,
    github: client([{ ...gate, head_sha: undefined }], [{ ...gate, head_sha: undefined }]),
  });
  assert.equal(runs.size, 0);
});

for (const missingHead of ['', undefined, '  ']) {
  test(`missing head ${JSON.stringify(missingHead)} never performs an unconstrained lookup`, async () => {
    const calls = [];
    const runs = await collectStatusWorkflowRuns({ ...opts, headSha: missingHead,
      github: client([gate], [gate], calls),
    });
    assert.equal(runs.size, 0);
    assert.deepEqual(calls, []);
  });
}

for (const status of [401, 403, 429, 500]) {
  test(`Gate recovery error ${status} propagates after one lookup`, async () => {
    const calls = [];
    const error = Object.assign(new Error('Gate lookup failed'), { status });
    await assert.rejects(collectStatusWorkflowRuns({ ...opts,
      github: client(generation('11'), error, calls),
    }), /Gate lookup failed/);
    assert.equal(calls.filter(([kind]) => kind === 'gate').length, 1);
  });
}
