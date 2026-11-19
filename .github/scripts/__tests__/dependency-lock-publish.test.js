'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {createRequire} = require('node:module');
const test = require('node:test');

const root = path.resolve(__dirname, '../../..');
const workflow = fs.readFileSync(path.join(root, '.github/workflows/maint-auto-lock-deps.yml'), 'utf8');
const script = workflow.split('      - name: Commit only to the checked bot PR head\n')[1].split('script: |\n')[1];
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const publish = new AsyncFunction('context', 'github', 'core', 'require', 'process', script);

test('publish a lock only against the original open bot PR and its exact head', async t => {
  const expected = {
    number: 2372, state: 'open', user: {login: 'dependabot[bot]'}, base: {ref: 'main'},
    head: {ref: 'dependabot/pip/updates', sha: 'recorded-head', repo: {full_name: 'stranske/Workflows'}},
  };
  const repo = {owner: 'stranske', repo: 'Workflows'};
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'lock-publish-'));
  t.after(() => fs.rmSync(temp, {recursive: true, force: true}));
  fs.mkdirSync(path.join(temp, 'regenerated-lock'));
  const lock = 'example-package==1.0\n';
  fs.writeFileSync(path.join(temp, 'regenerated-lock/requirements.lock'), lock);
  const sent = [];
  let live = expected;
  const github = {
    rest: {pulls: {get: async args => {
      assert.deepEqual(args, {...repo, pull_number: expected.number});
      return {data: live};
    }}},
    graphql: async (query, {input}) => {
      assert.match(query, /createCommitOnBranch\(input: \$input\)/);
      sent.push(input);
      return {createCommitOnBranch: {commit: {oid: 'new-commit'}}};
    },
  };
  const run = () => publish({repo, payload: {pull_request: expected}}, github,
    {info() {}, notice() {}}, createRequire(path.join(root, 'package.json')), {env: {RUNNER_TEMP: temp}});
  await run();
  assert.deepEqual(sent[0].branch, {repositoryNameWithOwner: 'stranske/Workflows', branchName: expected.head.ref});
  assert.equal(sent[0].expectedHeadOid, expected.head.sha);
  assert.deepEqual(sent[0].fileChanges, {additions: [{path: 'requirements.lock', contents: Buffer.from(lock).toString('base64')}]});
  for (const changes of [
    {state: 'closed'}, {base: {ref: 'release'}}, {user: {login: 'different-author'}},
    {head: {...expected.head, ref: 'different-branch'}}, {head: {...expected.head, sha: 'newer-head'}},
    {head: {...expected.head, repo: {full_name: 'another-owner/Workflows'}}},
    {head: {...expected.head, repo: null}},
  ]) {
    live = {...expected, ...changes};
    await run();
  }
  assert.equal(sent.length, 1);
  live = expected;
  let attempts = 0;
  github.graphql = async () => { attempts++; throw new Error('Head advanced before commit'); };
  await assert.rejects(run, /Head advanced before commit/);
  assert.equal(attempts, 1);
});
