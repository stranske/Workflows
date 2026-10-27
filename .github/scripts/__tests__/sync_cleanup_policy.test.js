'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { buildMergeReport } = require('../sync_pr_merge_contract');
const { normalizeDeliveryHandoff, planMaint71Continuations } = require('../sync_dependency_campaign');
const { dispatchCanaryPromotion, dispatchCanaryRefresh, dispatchDeliveryRefresh } = require('../maint71_merge_sync_prs');

const now = '2026-10-27T12:00:00Z';
function result() {
  return { owner: 'stranske', repo: 'Ready', pr: 1, branch: 'sync/workflows-delivery',
    head_sha: 'a'.repeat(40), delivery_generation: 'g', plan_id: 'p',
    plan_scope: 'full', source_commit: 'b'.repeat(40), status: 'checks_pending',
    blocker_owner: 'ci', next_command: 'await-required-checks', review_state: 'clear' };
}
function core() { return { notice() {}, summary: { addRaw() { return { write: async () => {} }; } } }; }

for (const enabled of [false, true]) {
  test(`actual post-merge deletion boundary honors cleanup=${enabled}`, async () => {
    const source = fs.readFileSync(path.join(__dirname, '../maint71_merge_sync_prs.js'), 'utf8');
    const start = source.indexOf('// Delete the branch');
    const tail = source.slice(start);
    const end = tail.search(/\n\s*results\.push\(\{\s*\.\.\.deliveryContext,\s*status: 'merged'/);
    assert.ok(start >= 0 && end > 0, 'exercise the actual production post-merge block');
    const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
    const execute = new AsyncFunction('cleanupBranches', 'withRetry', 'owner', 'repo',
      'pr', 'results', 'deliveryContext', 'rethrowPrimaryRateLimit', 'console', tail.slice(0, end));
    let deletes = 0;
    const client = { rest: { git: { deleteRef: async ({ ref }) => {
      deletes++; assert.equal(ref, 'heads/sync/workflows-delivery');
    } } } };
    const rows = [];
    await execute(enabled, fn => fn(client), 'stranske', 'Ready',
      { head: { ref: 'sync/workflows-delivery' } }, rows, {}, e => { throw e; }, { log() {} });
    assert.equal(deletes, enabled ? 1 : 0);
    assert.equal(rows.length, enabled ? 1 : 0);
  });
}

test('explicit false survives real report, normalized handoff and continuation planner', () => {
  const report = buildMergeReport({ results: [result()], cleanupBranches: false, generatedAt: now });
  assert.equal(report.inputs.cleanup_branches, false);
  assert.equal(report.handoff_records.length, 1);
  assert.equal(report.handoff_records[0].cleanup_branches, false);
  const handoff = normalizeDeliveryHandoff(report.handoff_records[0]);
  assert.equal(handoff.cleanup_branches, false);
  const [continuation] = planMaint71Continuations([handoff], { now: '2026-10-28T12:00:00Z' });
  assert.equal(continuation.cleanup_branches, false);
});

test('legacy report keeps existing cleanup default and malformed policy is not admitted', () => {
  const report = buildMergeReport({ results: [result()], generatedAt: now });
  assert.equal(report.inputs.cleanup_branches, true);
  assert.equal(normalizeDeliveryHandoff({ ...report.handoff_records[0], cleanup_branches: 'false' }), null);
});

for (const enabled of [false, true]) {
  test(`native canary producer dispatch preserves cleanup=${enabled}`, async () => {
    const calls = [];
    await dispatchCanaryRefresh({ cleanupBranches: enabled,
      refreshState: { eligible: true, sha: 'a'.repeat(40), candidates: ['stranske/Ready'] },
      withRetry: fn => fn({ rest: { actions: { createWorkflowDispatch: async args => calls.push(args) } } }),
      context: { repo: { owner: 'stranske', repo: 'Workflows' }, payload: { repository: { default_branch: 'main' } } },
      core: core(), expectedCanaries: ['stranske/Ready'] });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].inputs.cleanup_branches, String(enabled));
  });
  test(`authenticated canary promotion preserves cleanup=${enabled}`, async () => {
    const repo = 'stranske/Ready', source = 'b'.repeat(40), calls = [];
    const row = { repo, plan_id: 'p', source_commit: source, head_sha: 'a'.repeat(40),
      plan_scope: 'full', scope_base_sha: '', evidence_source: 'no-change-canary',
      required_check_state: 'success', active_review_thread_count: 0 };
    const report = { inputs: { auto_merge: true, dry_run: false, sync_hash: 'candidate', cleanup_branches: enabled },
      results: [{ owner: 'stranske', repo: 'Ready', branch: 'sync/workflows-candidate',
        status: 'evidence_recovered', plan_id: 'p', source_commit: source, head_sha: row.head_sha }] };
    const client = { rest: { repos: { getCommit: async () => ({ data: { commit: { committer: { date: now } } } }) },
      actions: { listWorkflowRuns: async () => ({ data: { workflow_runs: [] } }),
        createWorkflowDispatch: async args => calls.push(args) } } };
    const outcome = await dispatchCanaryPromotion({ report, evidence: { results: [row] }, expectedCanaries: [repo],
      withRetry: fn => fn(client), context: { repo: { owner: 'stranske', repo: 'Workflows' },
        payload: { repository: { default_branch: 'main' } } }, core: core() });
    assert.equal(outcome.status, 'dispatched');
    assert.equal(calls[0].inputs.cleanup_branches, String(enabled));
  });
}

function workflowScript(file, stepName) {
  const text = fs.readFileSync(path.join(__dirname, '../../workflows', file), 'utf8');
  const start = text.indexOf(`      - name: ${stepName}\n`);
  assert.ok(start >= 0, 'actual workflow step exists');
  const lines = text.slice(start).split('\n');
  const at = lines.findIndex(line => /^\s+script: \|$/.test(line));
  assert.ok(at >= 0);
  const script = [];
  const indent = lines[at].match(/^\s*/)[0].length + 2;
  for (const line of lines.slice(at + 1)) {
    if (line.trim() && !line.startsWith(' '.repeat(indent))) break;
    script.push(line.slice(indent));
  }
  return { text: text.slice(start, start + lines.join('\n').length), script: script.join('\n') };
}

for (const input of ['false', 'true', '']) {
  test(`actual Maint68 dispatch step transports cleanup input ${JSON.stringify(input)}`, async () => {
    const { text, script } = workflowScript('maint-68-sync-consumer-repos.yml', 'Dispatch Maint 71 for the generated lane');
    assert.match(text, /CLEANUP_BRANCHES_INPUT: \$\{\{ inputs\.cleanup_branches \}\}/);
    const calls = [], client = { rest: { actions: { createWorkflowDispatch: async args => calls.push(args) } } };
    const fakeRequire = name => {
      assert.equal(name, './.github/scripts/github-api-with-retry.js');
      return { createTokenAwareRetry: async () => ({ withRetry: fn => fn(client) }) };
    };
    const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
    await new AsyncFunction('require', 'process', 'context', 'core', 'github', script)(fakeRequire,
      { env: { SYNC_PHASE: 'canary', PLAN_ID: 'p', PLAN_SCOPE: 'full', SOURCE_COMMIT: 'b'.repeat(40),
        CLEANUP_BRANCHES_INPUT: input, REGISTERED_CONSUMER_REPOS: 'stranske/Ready' } },
      { repo: { owner: 'stranske', repo: 'Workflows' }, payload: { repository: { default_branch: 'main' } } },
      core(), client);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].inputs.cleanup_branches, input || 'true');
  });
}

test('same-plan grouped continuation never widens a later false policy', () => {
  const a = buildMergeReport({ results: [result()], cleanupBranches: true, generatedAt: now }).handoff_records[0];
  const b = { ...a, repository: 'stranske/Other', pr: 2, cleanup_branches: false,
    observed_at: '2026-10-27T12:01:00Z' };
  const [next] = planMaint71Continuations([a, b], { now: '2026-10-28T12:00:00Z' });
  assert.equal(next.cleanup_branches, false);
  const otherPlan = { ...b, plan_id: 'another-plan', source_commit: 'd'.repeat(40) };
  const [separate] = planMaint71Continuations([a, otherPlan], { now: '2026-10-28T12:00:00Z' });
  assert.equal(separate.cleanup_branches, true, 'another plan does not rewrite the selected plan policy');
});

for (const enabled of [false, true, undefined]) {
  test(`actual Maint82 continuation input construction preserves ${enabled}`, () => {
    const source = fs.readFileSync(path.join(__dirname, '../../workflows/maint-82-sync-dependency-campaign.yml'), 'utf8');
    const start = source.indexOf("              const inputs = {\n                auto_merge: 'true'");
    const end = source.indexOf('\n              inputs.active_sync_hash', start);
    assert.ok(start >= 0 && end > start);
    const construct = new Function('continuation', `${source.slice(start, end)}\nreturn inputs;`);
    assert.equal(construct({ cleanup_branches: enabled }).cleanup_branches, enabled === false ? 'false' : 'true');
  });
}

for (const enabled of [false, true]) {
  test(`native delivery refresh preserves cleanup=${enabled}`, async () => {
    const calls = [], repo = 'stranske/Ready';
    const client = { rest: { repos: {
      getCommit: async () => ({ data: { sha: 'b'.repeat(40), commit: { committer: { date: now } } } }),
      getContent: async () => ({ data: { content: Buffer.from(JSON.stringify({ canaries: [{ repo }] })).toString('base64') } }),
    }, actions: { listWorkflowRuns: async () => ({ data: { workflow_runs: [] } }),
      createWorkflowDispatch: async args => calls.push(args) } } };
    const outcome = await dispatchDeliveryRefresh({ cleanupBranches: enabled,
      decision: { evidence: { results: [{ repo, plan_id: 'p', source_commit: 'b'.repeat(40) }] } },
      expectedCanaries: [repo], withRetry: fn => fn(client), core: core(),
      context: { repo: { owner: 'stranske', repo: 'Workflows' }, payload: { repository: { default_branch: 'main' } } } });
    assert.equal(outcome.dispatched, true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].inputs.cleanup_branches, String(enabled));
  });
}
