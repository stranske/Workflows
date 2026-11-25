'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '../../..');
const workflowPath = '.github/workflows/agents-verify-to-new-pr.yml';
const workflow = fs.readFileSync(path.join(root, workflowPath), 'utf8');
const issues = JSON.parse(fs.readFileSync(path.join(root,
  'tests/fixtures/verifier_correction/ordinary-followup-issues.json'), 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const repo = {owner: 'stranske', repo: 'Workflows'};
const url = `https://github.com/${repo.owner}/${repo.repo}`;
const prUrl = number => `${url}/pull/${number}`;
const fallbackScope = number => `Address verification concerns from [PR #${number}](${prUrl(number)}).`;
const issueUrl = number => `${url}/issues/${number}`;
const contextFor = number => ({repo, payload: {
  pull_request: {number, html_url: prUrl(number), labels: []},
}});

function workflowScript(name) {
  const step = workflow.split(`      - name: ${name}\n`)[1].split(/^      - name: /m)[0];
  const script = step.split('          script: |\n')[1];
  return script.trimEnd().split('\n').map(line => line.slice(12)).join('\n');
}

const createIssue = new AsyncFunction('require', 'context', 'github', 'core',
  workflowScript('Create follow-up issue'));
const buildFallback = new AsyncFunction('require', 'context', 'core',
  workflowScript('Fallback to simple extraction'));

function openCopy(issue) {
  return {...issue, html_url: issue.url, state: 'open'};
}

const renamed = openCopy(issues[3383]);
const standard = openCopy(issues[3624]);

function example(number, title, body, extras = {}) {
  return {...standard, number, title, body, html_url: issueUrl(number), ...extras};
}

async function generatedFallback() {
  let title;
  let encodedBody;
  const fsMock = {
    readFileSync(name) {
      assert.equal(name, 'verification_data.txt');
      return '### Concerns\n- Retain the historical acceptance contract.\n';
    },
    appendFileSync(name, value) {
      assert.equal(name, 'memory-workflow-output');
      encodedBody = value;
    },
  };
  process.env.GITHUB_OUTPUT = 'memory-workflow-output';
  process.env.EXTRACTED_VERDICT = 'CONCERNS';
  process.env.FOLLOW_UP_DEPTH = '1';
  await buildFallback(name => {
    assert.equal(name, 'fs');
    return fsMock;
  }, contextFor(3564), {
    warning: assert.fail,
    setOutput(key, value) {
      assert.equal(key, 'issue_title');
      title = value;
    },
  });
  const body = encodedBody.match(/^issue_body<<EOF_BODY\n([\s\S]+)\nEOF_BODY\n$/)[1];
  assert.doesNotMatch(body, /Original PR:/);
  return {title, body};
}

async function invoke(source, inventory, generated) {
  let reads = 0;
  const creations = [];
  const outputs = {};
  const listForRepo = Symbol('listForRepo');
  const github = {
    rest: {issues: {listForRepo, async create(params) {
      creations.push(params);
      return {data: {number: 99000, html_url: issueUrl(99000)}};
    }}},
    async paginate(method, params) {
      assert.equal(method, listForRepo);
      assert.deepEqual(params, {...repo, state: 'open', labels: 'follow-up', per_page: 100});
      reads++;
      return inventory;
    },
  };
  const core = {info() {}, warning: assert.fail, setFailed: assert.fail,
    setOutput(key, value) { outputs[key] = value; }};
  process.env.ISSUE_TITLE = generated.title;
  process.env.ISSUE_BODY = generated.body;
  await createIssue(name => {
    if (name === 'fs') return {existsSync: () => true};
    if (name === './.github/scripts/github-api-with-retry.js') {
      return {withRetry: fn => fn(), paginateWithRetry: (client, ...args) => client.paginate(...args)};
    }
    assert.equal(name, './.github/scripts/agent_registry.js');
    return {loadAgentRegistry: () => ({default_agent: 'codex'}), resolveAgentFromLabels: () => 'codex'};
  }, contextFor(source), github, core);
  assert.equal(outputs.issue_url, issueUrl(outputs.issue_number));
  for (const request of creations) {
    assert.deepEqual(request, {...repo, ...generated,
      labels: ['follow-up', 'agent:codex', 'from:codex', 'runner:codex', 'agents:auto-pilot']});
  }
  return [outputs.issue_number, creations.length, reads];
}

const tests = [
  ['reuses the real retitled #3383 from #3376', 3376, () => [renamed], [3383, 0, 1]],
  ['retains recognition of the real #3624 structured source without a current auto-pilot label', 3564, () => [standard], [3624, 0, 1]],
  ['reuses the Python scope from #1299 even when the parent title names another PR', 1297, () => [
    example(1299, 'Retitled follow-up', '- Original PR: #1297\nAddress verification concerns from PR #1297 related to [Follow-up] Address verification concerns from PR #1279.'),
  ], [1299, 0, 1]],
  ['rejects a Python scope for a different PR despite an exact Original PR line', 1297, () => [
    example(916, 'Follow-up', '- Original PR: #1297\nAddress verification concerns from PR #12970 related to this issue.'),
  ], [99000, 1, 1]],
  ['requires an Original PR line for a Python scope even when a fallback footer is present', 1297, () => [
    example(917, 'Follow-up', 'Address verification concerns from PR #1297 related to this issue.\n*Auto-generated by verify-to-new-pr workflow (fallback mode)*'),
  ], [99000, 1, 1]],
  ['ignores a numeric prefix for a different PR', 3564, () => [example(907, 'Follow-up PR #35640', '- Original PR: #35640'), standard], [3624, 0, 1]],
  ['returns the same issue that matched instead of an earlier title-only row', 3564, () => [example(902, 'Follow-up PR #3564', 'Different source'), standard], [3624, 0, 1]],
  ['ignores PR-shaped rows in the issues API', 3564, () => [example(904, 'Follow-up PR #3564', standard.body, {pull_request: {}}), standard], [3624, 0, 1]],
  ['ignores incidental mentions when the explicit source belongs to another PR', 3564, () => [example(903, 'Follow-up PR #3564', 'Mentions PR #3564\n- Original PR: #35640'), standard], [3624, 0, 1]],
  ['ignores a row with conflicting explicit sources', 3564, () => [example(909, 'Follow-up PR #3564', `${standard.body}\n- Original PR: #35640`), standard], [3624, 0, 1]],
  ['reuses the actual fallback-rendered body after retitling', 3564, ({body}) => [example(901, 'Investigate the existing published report', body)], [901, 0, 1]],
  ['prefers the exact structured source over an earlier fallback', 3564, ({title, body}) => [example(901, title, body), standard], [3624, 0, 1]],
  ['rejects fallback scope linked to another repository', 3564, ({title, body}) => [example(905, title, body.replace(prUrl(3564), 'https://github.com/example/local-fixture/pull/3564')), standard], [3624, 0, 1]],
  ['rejects fallback with an invalid continuation depth marker', 3564, ({title, body}) => [example(906, title, body.replace('<!-- follow-up-depth: 1 -->', '<!-- follow-up-depth: 0 -->')), standard], [3624, 0, 1]],
  ['reuses the retitled fallback rendered before continuation depth existed', 3564, () => [example(911, 'Investigate the old report', issues.legacyFallback.body)], [911, 0, 1]],
  ['rejects fallback containing an explicit contrary source', 3564, ({title, body}) => [example(910, title, `${body}\n- Original PR: #35640`), standard], [3624, 0, 1]],
  ['creates a fresh issue when the only fallback claims two PRs', 3564, ({title, body}) => [
    example(912, title, body.replace(fallbackScope(3564), fallbackScope(3564) + '\n' + fallbackScope(35640))),
  ], [99000, 1, 1]],
  ['rejects a structured match when the fallback identifies another PR', 3564, ({title, body}) => [
    example(913, title, body.replace(fallbackScope(3564), fallbackScope(35640)) + '\n- Original PR: #3564'),
    standard,
  ], [3624, 0, 1]],
  ['rejects a structured match with invalid explicit depth', 3564, () => [
    example(914, standard.title, standard.body.replace('<!-- follow-up-depth: 1 -->', '<!-- follow-up-depth: 0 -->')),
    standard,
  ], [3624, 0, 1]],
  ['accepts a retitled issue when both source declarations agree', 3564, ({body}) => [
    example(915, 'Retitled', body + '\n- Original PR: #3564'),
  ], [915, 0, 1]],
  ['keeps typed correction effects outside ordinary continuation selection', 3564, () => [example(908, 'Follow-up PR #3564', `${standard.body}\n<!-- closer-correction-effect/v1 {} -->`), standard], [3624, 0, 1]],
  ['creates exactly one issue when only unrelated candidates exist', 3564, () => [example(903, 'Follow-up PR #3564', 'Mentions PR #3564\n- Original PR: #35640')], [99000, 1, 1]],
  ['creates exactly one issue on a genuinely empty inventory', 3564, () => [], [99000, 1, 1]],
];

for (const [name, source, inventory, expected] of tests) {
  test(`ordinary continuation ${name}`, async () => {
    const generated = await generatedFallback();
    assert.deepEqual(await invoke(source, inventory(generated), generated), expected);
  });
}

for (const [name, getTitle] of [
  ['reuses a newly created issue on repeat', generated => generated.title],
  ['reuses a newly created issue after a retitle', () => 'Track the remaining checks'],
]) {
  test(`ordinary continuation ${name}`, async () => {
    const generated = await generatedFallback();
    assert.deepEqual(await invoke(3564, [], generated), [99000, 1, 1]);
    const retained = example(99000, getTitle(generated), generated.body);
    assert.deepEqual(await invoke(3564, [retained], generated), [99000, 0, 1]);
  });
}
