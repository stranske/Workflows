'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const workflow = fs.readFileSync(path.resolve(__dirname, '../../workflows/maint-82-sync-dependency-campaign.yml'), 'utf8');
const step = workflow.split('- name: Dispatch due Maint 71 continuations')[1]
  .split('\n      - name: Upload campaign state')[0];
const script = step.split('          script: |\n')[1].split('\n')
  .map((line) => line.replace(/^ {12}/, '')).join('\n');
const execute = new (Object.getPrototypeOf(async function () {}).constructor)(
  'require', 'process', 'github', 'context', 'core', script,
);
const continuation = {lane: 'dev-tool', continuation_key: 'same-key', repository: 'stranske/Ready', pr: 1};

async function dispatch(runs, continuations = [continuation]) {
  const dispatched = [];
  const github = {rest: {actions: {
    listWorkflowRuns: async () => ({data: {workflow_runs: runs}}),
    createWorkflowDispatch: async (params) => dispatched.push(params),
  }}};
  await execute((name) => name.includes('github-api-with-retry')
    ? {createTokenAwareRetry: async () => ({withRetry: (call) => call(github)})}
    : {...require('../sync_dependency_campaign'), selectMaint71ContinuationRepos: () => ['stranske/Ready']},
  {env: {CONTINUATIONS_JSON: JSON.stringify(continuations), REGISTERED_REPOS: 'stranske/Ready'}},
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
