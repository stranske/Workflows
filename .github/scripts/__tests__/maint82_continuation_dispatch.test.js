'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const workflow = fs.readFileSync(path.resolve(__dirname, '../../workflows/maint-82-sync-dependency-campaign.yml'), 'utf8');
const step = workflow.split('- name: Dispatch due Maint 71 continuations')[1]
  .split('\n      - name: Upload campaign state')[0];
const refreshStep = workflow.split('        id: campaign\n')[1].split('\n      - name: Dispatch due Maint 71 continuations')[0];
function compile(stepSource) {
  const script = stepSource.split('          script: |\n')[1].split('\n')
    .map(line => line.replace(/^ {12}/, '')).join('\n');
  return new (Object.getPrototypeOf(async function () {}).constructor)(
    'require', 'process', 'github', 'context', 'core', script,
  );
}
const execute = compile(step);
const refresh = compile(refreshStep);
const continuation = {lane: 'dev-tool', continuation_key: 'same-key', repository: 'stranske/Ready', pr: 1};

async function dispatch(runs, continuations = [continuation], scopedState = null) {
  const dispatched = [];
  const github = {rest: {actions: {
    listWorkflowRuns: async () => ({data: {workflow_runs: runs}}),
    createWorkflowDispatch: async (params) => dispatched.push(params),
  }}};
  await execute((name) => name.includes('github-api-with-retry')
    ? {createTokenAwareRetry: async () => ({withRetry: (call) => call(github)})}
    : scopedState ? require('../sync_dependency_campaign')
      : {...require('../sync_dependency_campaign'), selectMaint71ContinuationRepos: () => ['stranske/Ready']},
  {env: {CONTINUATIONS_JSON: JSON.stringify(continuations),
    DELIVERY_HANDOFFS_JSON: JSON.stringify(scopedState?.handoffs || []),
    REGISTERED_REPOS: scopedState?.registered.join(',') || 'stranske/Ready' }},
  github, {repo: {owner: 'stranske', repo: 'Workflows'}, payload: {}},
  {notice() {}, warning() {}});
  return dispatched;
}

test('native multiline active title suppresses duplicate continuation dispatch', async () => {
  assert.equal((await dispatch([{status: 'in_progress', display_title: 'Merge Sync PRs [dev-tool]\nsame-key'}])).length, 0);
});
test('changed key waits for the incumbent, failed attempt remains eligible and successful key is consumed', async () => {
  assert.equal((await dispatch([{status: 'in_progress', display_title: 'Merge Sync PRs [dev-tool]\nother-key'}])).length, 0);
  assert.equal((await dispatch([{status: 'completed', conclusion: 'success', display_title: 'Merge Sync PRs [dev-tool]\nother-key'}])).length, 1);
  assert.equal((await dispatch([{status: 'completed', conclusion: 'success', display_title: 'Merge Sync PRs [dev-tool]\nsame-key'}])).length, 0);
  assert.equal((await dispatch([{status: 'completed', conclusion: 'failure', display_title: 'Merge Sync PRs [dev-tool]\nsame-key'}])).length, 1);
});
test('duplicate rows dispatch once and active delivery retains candidate priority', async () => {
  assert.equal((await dispatch([], [continuation, continuation])).length, 1);
  assert.equal((await dispatch([{status: 'queued', display_title: '  Merge Sync PRs [delivery]\nkey'}], [{...continuation, lane: 'candidate'}])).length, 0);
});

test('different due keys submit one writer so the pending queue cannot replace an earlier intent', async () => {
  assert.equal((await dispatch([], [continuation, {...continuation, continuation_key: 'other-key'}])).length, 1);
});

test('a completed key covers only observations through its completion time', async () => {
  const intent = {...continuation, resume_after: '2026-11-19T17:55:15.099Z'};
  const run = {status: 'completed', conclusion: 'success', display_title: 'Merge Sync PRs [dev-tool]\nsame-key'};
  const earlier = {...run, updated_at: '2026-11-19T17:52:00Z'};
  const atObservation = {...run, updated_at: intent.resume_after};
  assert.equal((await dispatch([earlier], [intent])).length, 1);
  assert.equal((await dispatch([atObservation, earlier], [intent])).length, 0);
  assert.equal((await dispatch([{...run, updated_at: '2026-11-19T18:04:30Z'}], [intent])).length, 0);
  assert.equal((await dispatch([run], [intent])).length, 0);
  assert.equal((await dispatch([earlier], [continuation])).length, 0);
});


test('review recovery dispatches once and a terminal failure does not reauthorize it', async () => {
  const recovered = { ...continuation, lane: 'campaign', reason: 'review_recovered',
    continuation_key: 'review-1234567890abcdefabcd', resume_after: '2026-11-26T15:22:00Z' };
  const title = `Merge Sync PRs [campaign] ${recovered.continuation_key}`;
  assert.equal((await dispatch([], [recovered, recovered])).length, 1);
  assert.equal((await dispatch([{ status: 'queued', display_title: title }], [recovered])).length, 0);
  assert.equal((await dispatch([{
    status: 'completed', conclusion: 'failure', display_title: title,
    updated_at: '2026-11-26T15:23:00Z',
  }], [recovered])).length, 0);
});


test('authored refresh holds blocked peers and dispatches only verified receiver scope', async () => {
  const campaign = require('../sync_dependency_campaign');
  const registered = ['stranske/Ready', 'stranske/Template'];
  const ready = { schema: 'workflows-generated-delivery-handoff/v1',
    repository: registered[0], pr: 701, head_sha: 'a'.repeat(40),
    branch: 'sync/workflows-delivery', delivery_generation: 'generation', plan_id: 'plan',
    plan_scope: 'full', source_commit: 'b'.repeat(40),
    disposition: 'current', blocker_owner: 'maint-71', next_command: 'await-checks',
    check_state: 'pending', review_state: 'clear',
    continuation: { class: 'transient', lane: 'delivery', key: 'ready',
      reason: 'checks_pending', resume_after: '2026-11-26T08:48:00Z' } };
  const blocked = { ...ready, repository: registered[1], pr: 1122 };
  const excluded = { ...ready, repository: 'stranske/Collab-Admin' };
  const recovered = { ...ready, continuation: { ...ready.continuation, lane: 'campaign',
    key: 'review-1234567890abcdefabcd', reason: 'review_recovered' } };

  const observe = async (records, blockedKeys = [], dry = false) => {
    const outputs = {};
    await refresh(name => name === 'fs' ? { writeFileSync() {} } : {
      ...campaign,
      runCampaign: async options => {
        assert.equal(options.observeContinuations, !dry);
        return { state: { delivery_handoffs: records, handoff_verification_blocked_keys: blockedKeys } };
      },
    }, { env: { REGISTERED_REPOS: registered.join(','), CAMPAIGN_DRY_RUN: String(dry) } },
    {}, { payload: {} }, {
      setOutput(key, value) { outputs[key] = JSON.parse(value); },
      summary: { addHeading() { return this; }, addList() { return this; }, async write() {} },
    });
    const handoffs = outputs.maint71_delivery_handoffs;
    const posts = dry ? [] : await dispatch([], outputs.maint71_continuations, { handoffs, registered });
    return { handoffs, posts };
  };

  const blockedKey = `${blocked.repository}#${blocked.pr}`;
  assert.deepEqual((await observe([recovered, blocked], [blockedKey])).posts, []);
  assert.deepEqual(await observe([excluded]), { handoffs: [], posts: [] });
  assert.deepEqual((await observe([recovered], [], true)).posts, []);
  const scoped = await observe([ready, blocked], [blockedKey]);
  assert.deepEqual(scoped.handoffs.map(record => record.repository), [ready.repository]);
  assert.deepEqual(scoped.posts.map(request => request.inputs.repos), [ready.repository]);
  const full = await observe([recovered]);
  assert.deepEqual(full.posts.map(request => request.inputs.repos), [registered.join(',')]);
});
