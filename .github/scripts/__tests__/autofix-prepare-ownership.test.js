'use strict';

// Runs the real inline "prepare" scripts of both hosted autofix lanes (consumer agents-81 and
// the Workflows-local agents-autofix-loop) against a stubbed GitHub client, so the ownership and
// eligibility stops are proven on the code that ships, not on a copy.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '../../..');
const LANES = [
  {
    name: 'consumer agents-81',
    file: 'templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml',
    step: 'Evaluate workflow_run',
  },
  {
    name: 'Workflows agents-autofix-loop',
    file: '.github/workflows/agents-autofix-loop.yml',
    step: 'Evaluate gate run',
  },
];

function stepScript(file, stepName) {
  const text = fs.readFileSync(path.join(ROOT, file), 'utf8');
  const step = text.split(`      - name: ${stepName}\n`)[1];
  assert.ok(step, `${file} must keep the "${stepName}" step`);
  const block = step.split('          script: |\n')[1].split('\n      - name:')[0];
  return block
    .split('\n')
    .map((line) => {
      if (!line.trim()) return '';
      assert.ok(line.startsWith('            '), `unexpected indentation in ${file}: ${line}`);
      return line.slice(12);
    })
    .join('\n');
}

async function runPrepare(lane, labels) {
  const headSha = 'a'.repeat(40);
  const run = {
    id: 77,
    run_attempt: 1,
    workflow_id: 9,
    status: 'completed',
    conclusion: 'failure',
    event: 'pull_request',
    head_sha: headSha,
    html_url: 'https://example.test/runs/77',
    pull_requests: [{ number: 12 }],
    actor: { login: 'someone' },
  };
  const pr = {
    number: 12,
    state: 'open',
    draft: false,
    body: '',
    head: { sha: headSha, ref: 'codex/issue-1', repo: { full_name: 'octo/repo' } },
    labels: labels.map((name) => ({ name })),
  };
  const calls = [];
  const named = (name, value) => {
    const fn = async () => {
      calls.push(name);
      return value;
    };
    fn.apiName = name;
    return fn;
  };
  const github = {
    rest: {
      actions: {
        getWorkflowRun: named('actions.getWorkflowRun', { data: run }),
        listJobsForWorkflowRun: named('actions.listJobsForWorkflowRun', {}),
        listJobsForWorkflowRunAttempt: named('actions.listJobsForWorkflowRunAttempt', {}),
        listWorkflowRuns: named('actions.listWorkflowRuns', {}),
      },
      pulls: { get: named('pulls.get', { data: pr }) },
      issues: {
        addLabels: named('issues.addLabels', {}),
        removeLabel: named('issues.removeLabel', {}),
        createComment: named('issues.createComment', {}),
      },
    },
    paginate: async (method) => {
      calls.push(`paginate:${method.apiName}`);
      if (method.apiName === 'actions.listJobsForWorkflowRun'
        || method.apiName === 'actions.listJobsForWorkflowRunAttempt') {
        return [{ id: 1, name: 'python ci', conclusion: 'failure', steps: [{ name: 'pytest', conclusion: 'failure' }] }];
      }
      if (method.apiName === 'actions.listWorkflowRuns') {
        return [run];
      }
      return [];
    },
  };
  const retry = {
    withRetry: (fn) => fn(github),
    paginateWithRetry: (...args) => (args.length >= 3
      ? args[0].paginate(args[1], args[2])
      : github.paginate(args[0], args[1])),
  };
  retry.createTokenAwareRetry = async () => retry;
  const fakeRequire = (id) => {
    if (id === 'fs') return { ...fs, existsSync: () => true };
    if (id.endsWith('github-api-with-retry.js')) return retry;
    if (id.endsWith('agent_registry.js')) return require(path.join(ROOT, '.github/scripts/agent_registry.js'));
    return require(id);
  };
  const outputs = {};
  const core = {
    info: () => {},
    warning: () => {},
    debug: () => {},
    setFailed: (message) => { outputs.__failed = message; },
    setOutput: (key, value) => { outputs[key] = value; },
  };
  const fakeProcess = { env: { MANUAL_GATE_RUN_ID: String(run.id) } };
  const context = {
    repo: { owner: 'octo', repo: 'repo' },
    payload: { workflow_run: run },
    actor: 'someone',
    eventName: 'workflow_run',
  };
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const execute = new AsyncFunction(
    'require', 'github', 'context', 'core', 'process', stepScript(lane.file, lane.step),
  );
  const cwd = process.cwd();
  process.chdir(ROOT);
  try {
    await execute(fakeRequire, github, context, core, fakeProcess);
  } finally {
    process.chdir(cwd);
  }
  return { outputs, calls };
}

for (const lane of LANES) {
  test(`${lane.name}: an agent PR with a failing Gate reaches the runner reservation`, async () => {
    // Positive control: proves the harness drives the script to the point where the
    // workflow's "Check runner dispatch debounce" step (the reservation) would run.
    const { outputs } = await runPrepare(lane, ['agent:codex']);
    assert.equal(outputs.__failed, undefined);
    assert.equal(outputs.should_run, 'true');
    assert.equal(outputs.agent_type, 'codex');
  });

  test(`${lane.name}: agents:local-loop stops autofix before any write or reservation`, async () => {
    const { outputs, calls } = await runPrepare(lane, ['agent:gemini', 'agents:local-loop']);
    assert.equal(outputs.__failed, undefined);
    assert.equal(outputs.should_run, 'false');
    assert.equal(outputs.stop_reason, 'local_loop');
    assert.deepEqual(
      calls.filter((name) => name.startsWith('issues.') || name.includes('listJobs')),
      [],
    );
  });
}
