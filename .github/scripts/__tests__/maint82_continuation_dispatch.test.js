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
test('changed key or failed attempt stays eligible, successful exact key is consumed', async () => {
  assert.equal((await dispatch([{status: 'in_progress', display_title: 'Merge Sync PRs [dev-tool]\nother-key'}])).length, 1);
  assert.equal((await dispatch([{status: 'completed', conclusion: 'success', display_title: 'Merge Sync PRs [dev-tool]\nsame-key'}])).length, 0);
  assert.equal((await dispatch([{status: 'completed', conclusion: 'failure', display_title: 'Merge Sync PRs [dev-tool]\nsame-key'}])).length, 1);
});
test('duplicate rows dispatch once and active delivery retains candidate priority', async () => {
  assert.equal((await dispatch([], [continuation, continuation])).length, 1);
  assert.equal((await dispatch([{status: 'queued', display_title: '  Merge Sync PRs [delivery]\nkey'}], [{...continuation, lane: 'candidate'}])).length, 0);
});
