'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');

const root = path.resolve(__dirname, '../../..');
const before = 'a'.repeat(40);
const after = 'b'.repeat(40);
const sources = [
  '.github/scripts/autofix_metrics.js',
  'templates/consumer-repo/.github/scripts/autofix_metrics.js',
];

async function run(command, args, env) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'autofix-command-'));
  const stdoutPath = path.join(dir, 'stdout');
  const stderrPath = path.join(dir, 'stderr');
  const stdout = fs.openSync(stdoutPath, 'w');
  const stderr = fs.openSync(stderrPath, 'w');
  try {
    const status = await new Promise((resolve, reject) => {
      const child = spawn(command, args, { env, stdio: ['ignore', stdout, stderr] });
      child.on('error', reject);
      child.on('close', resolve);
    });
    return { status, stdout: fs.readFileSync(stdoutPath, 'utf8'),
      stderr: fs.readFileSync(stderrPath, 'utf8') };
  } finally {
    fs.closeSync(stdout);
    fs.closeSync(stderr);
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test('autofix metrics helper is delivered byte-for-byte to consumers', () => {
  assert.equal(fs.readFileSync(path.join(root, sources[0]), 'utf8'),
    fs.readFileSync(path.join(root, sources[1]), 'utf8'));
  assert.match(fs.readFileSync(path.join(root, '.github/sync-manifest.yml'), 'utf8'),
    /source: \.github\/scripts\/autofix_metrics\.js/);
});

for (const source of sources) {
  const scriptPath = path.join(root, source);
  const { observeAutofixHead, formatAutofixCompletion } = require(scriptPath);

  function setup({ head = before, prError = false, gateError = false, labelError = false,
    prNumber = 2490, runs = [{ conclusion: 'success' }] } = {}) {
    const outputs = {};
    const calls = [];
    const warnings = [];
    const github = { rest: {
      pulls: { get: async (params) => {
        calls.push(['pulls.get', params]);
        if (prError) throw new Error('API unavailable');
        return { data: { head: { sha: head }, labels: [{ name: 'autofix:escalated' }] } };
      } },
      issues: { removeLabel: async (params) => {
        calls.push(['removeLabel', params]);
        if (labelError) throw new Error('Label unavailable');
      } },
      actions: { listWorkflowRuns() {} },
    } };
    const options = {
      github, context: { repo: { owner: 'stranske', repo: 'consumer' } },
      core: { setOutput: (name, value) => { outputs[name] = value; },
        warning: (message) => warnings.push(message), info() {} },
      withRetry: (fn) => fn(github),
      paginateWithRetry: async (_method, params) => {
        calls.push(['listWorkflowRuns', params]);
        if (gateError) throw new Error('Gate unavailable');
        return runs;
      },
      prNumber, headShaBefore: before, gateConclusionBefore: 'failure',
    };
    return { options, outputs, calls, warnings };
  }

  test(`failed lookup cannot turn a pushed commit into no-work completion (${source})`, async () => {
    const f = setup({ head: after, prError: true });
    const metrics = { head_sha_before: before, autofix_result: 'success',
      ...await observeAutofixHead(f.options) };
    assert.equal(metrics.head_sha_after, '');
    assert.equal(metrics.fix_applied, false);
    assert.equal(metrics.head_observed, false);
    assert.equal(f.outputs.head_observed, 'false');
    assert.equal(f.calls.length, 1);
    assert.equal(f.warnings.length, 1);
    assert.throws(() => formatAutofixCompletion(metrics, before), /retain reservation/);
  });

  for (const head of [undefined, null, '', 'not-a-sha', 'c'.repeat(39)]) {
    test(`missing or malformed response head stays unobserved: ${head} (${source})`, async () => {
      const f = setup({ head });
      // An explicit undefined must override setup's default argument.
      f.options.github.rest.pulls.get = async () => ({ data: { head: { sha: head } } });
      const metrics = await observeAutofixHead(f.options);
      assert.equal(metrics.head_observed, false);
      assert.equal(f.outputs.head_observed, 'false');
      assert.equal(f.calls.length, 0);
    });
  }

  test(`no PR skips lookup and remains unobserved (${source})`, async () => {
    const f = setup({ prNumber: 0 });
    assert.equal((await observeAutofixHead(f.options)).head_observed, false);
    assert.equal(f.outputs.head_observed, 'false');
    assert.equal(f.calls.length, 0);
  });

  for (const recoveredHead of [before, after]) {
    test(`recovered observation replaces stale head evidence: ${recoveredHead} (${source})`, async () => {
      const f = setup({ head: after });
      async function measure() {
        return { head_sha_before: before, autofix_result: 'success',
          ...await observeAutofixHead(f.options) };
      }
      assert.equal(formatAutofixCompletion(await measure(), before), `${after} true 0\n`);
      assert.equal(f.outputs.head_observed, 'true');

      f.options.github.rest.pulls.get = async () => { throw new Error('API unavailable'); };
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const metrics = await measure();
        // A prior successful lookup cannot authorize a later fallback-only
        // measurement, including when the step output object is reused.
        assert.equal(f.outputs.head_observed, 'false');
        assert.equal(metrics.head_observed, false);
        assert.equal(metrics.head_sha_after, '');
        assert.equal(metrics.fix_applied, false);
        assert.throws(() => formatAutofixCompletion(metrics, before), /retain reservation/);
      }
      assert.equal(f.warnings.length, 2);

      f.options.github.rest.pulls.get = async () => ({ data: {
        head: { sha: recoveredHead }, labels: [],
      } });
      const recovered = await measure();
      assert.equal(f.outputs.head_observed, 'true');
      assert.equal(recovered.head_observed, true);
      assert.equal(recovered.head_sha_after, recoveredHead);
      assert.equal(recovered.fix_applied, recoveredHead !== before);
      assert.equal(formatAutofixCompletion(recovered, before),
        `${recoveredHead} ${recoveredHead !== before} 0\n`);
    });
  }

  for (const head of [before, after]) {
    for (const autofixResult of ['success', 'failure', 'cancelled']) {
      test(`observed ${head === before ? 'unchanged' : 'changed'} head, ${autofixResult} (${source})`, async () => {
        const f = setup({ head });
        const metrics = { head_sha_before: before, autofix_result: autofixResult,
          ...await observeAutofixHead(f.options) };
        assert.equal(metrics.head_observed, true);
        assert.equal(f.outputs.head_observed, 'true');
        assert.equal(metrics.fix_applied, head !== before);
        assert.equal(metrics.gate_result_after, 'success');
        assert.deepEqual(f.calls[0], ['pulls.get', {
          owner: 'stranske', repo: 'consumer', pull_number: 2490,
        }]);
        assert.equal(f.calls.at(-1)[1].head_sha, head);
        assert.equal(formatAutofixCompletion(metrics, before),
          `${head} ${head !== before} ${autofixResult === 'success' ? 0 : 1}\n`);
      });
    }
  }

  for (const options of [{ gateError: true }, { labelError: true },
    { gateError: true, labelError: true }, { runs: [] }, { runs: [{ status: 'queued' }] }]) {
    test(`telemetry failure/status preserves a valid head: ${JSON.stringify(options)} (${source})`, async () => {
      const f = setup({ head: after, ...options });
      const metrics = { head_sha_before: before, autofix_result: 'success',
        ...await observeAutofixHead(f.options) };
      assert.equal(metrics.head_observed, true);
      assert.equal(f.outputs.head_observed, 'true');
      assert.equal(formatAutofixCompletion(metrics, before), `${after} true 0\n`);
      assert.equal(metrics.gate_result_after, options.gateError ? 'failure'
        : options.runs?.length === 0 ? 'not-found'
          : options.runs?.[0]?.status || 'success');
    });
  }

  test(`completion rejects fallback-only, ambiguous and inconsistent measurements (${source})`, () => {
    const valid = { head_observed: true, head_sha_before: before, head_sha_after: before,
      fix_applied: false, autofix_result: 'success' };
    for (const head_observed of [undefined, false, 'true', 'false', 1, null]) {
      assert.throws(() => formatAutofixCompletion({ ...valid, head_observed }, before),
        /retain reservation/);
    }
    for (const patch of [{ head_sha_before: after }, { head_sha_after: '' },
      { fix_applied: 'false' }, { fix_applied: true }, { head_sha_after: after },
      { autofix_result: 'skipped' }, { autofix_result: 'unknown' }]) {
      assert.throws(() => formatAutofixCompletion({ ...valid, ...patch }, before),
        /retain reservation/);
    }
  });

  test(`completion shell retains reservation and retry budget on unavailable observation (${source})`, async (t) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'autofix-metrics-'));
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
    const reservationPath = path.join(dir, 'reservation.json');
    const reservation = JSON.stringify({ status: 'pending', unproductive_completions: 1 });
    fs.writeFileSync(reservationPath, reservation);
    const env = { ...process.env, HEAD_SHA: before, HELPER_PATH: scriptPath,
      RESERVATION_PATH: reservationPath };
    // Match the existing workflow's fail-fast read before its recording command.
    const shell = 'read -r OBSERVED_HEAD PRODUCED_WORK EXIT_CODE < <(node "$HELPER_PATH")\n' +
      'printf completed > "$RESERVATION_PATH"\n';
    for (const head_observed of [undefined, false, 'true']) {
      const result = await run('bash', ['-euo', 'pipefail', '-c', shell], {
        ...env, METRICS_JSON: JSON.stringify({ head_observed,
          head_sha_before: before, head_sha_after: before,
          fix_applied: false, autofix_result: 'success' }),
      });
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /retain reservation/);
      assert.equal(fs.readFileSync(reservationPath, 'utf8'), reservation);
    }
    const result = await run('node', [scriptPath], {
      ...env, METRICS_JSON: JSON.stringify({ head_observed: true,
        head_sha_before: before, head_sha_after: after,
        fix_applied: true, autofix_result: 'success' }),
    });
    assert.equal(result.status, 0);
    assert.equal(result.stdout, `${after} true 0\n`);
  });
}
