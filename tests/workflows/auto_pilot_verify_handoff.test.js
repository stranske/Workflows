'use strict';

// Executable regressions for the auto-pilot verify -> done handoff (issue #4366).
// Each test extracts the real github-script body from agents-auto-pilot.yml and
// runs it against a mocked GitHub client, so a reverted guard fails a named test.

const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const ROOT = path.join(__dirname, '../..');
const SURFACES = [
  ['root', path.join(ROOT, '.github/workflows/agents-auto-pilot.yml')],
  ['consumer', path.join(ROOT, 'templates/consumer-repo/.github/workflows/agents-auto-pilot.yml')],
];

const ISSUE = 42;
const PR = 555;
const HEAD = 'c'.repeat(40);
const OTHER_HEAD = 'd'.repeat(40);
const PRE_CHANGE_MAX_PAGES = 10;

for (const [surface, workflowPath] of SURFACES) {
  const transitions = require(path.resolve(
    path.dirname(workflowPath), '../scripts/auto_pilot_transitions.js',
  ));
  const { determineNextStep } = transitions;

  function stepBlock(stepName) {
    const lines = fs.readFileSync(workflowPath, 'utf8').split('\n');
    const start = lines.findIndex((line) => line.trim() === `- name: ${stepName}`);
    assert.ok(start >= 0, `workflow no longer defines step "${stepName}"`);
    const indent = lines[start].indexOf('-');
    let end = start + 1;
    while (end < lines.length) {
      const line = lines[end];
      if (line.trim() && line.search(/\S/) <= indent) break;
      end += 1;
    }
    return lines.slice(start, end);
  }

  function stepScript(stepName) {
    const block = stepBlock(stepName);
    const at = block.findIndex((line) => /^\s+script: \|\s*$/.test(line));
    assert.ok(at >= 0, `step "${stepName}" has no inline script`);
    const scriptIndent = block[at].search(/\S/);
    const body = [];
    for (const line of block.slice(at + 1)) {
      if (line.trim() && line.search(/\S/) <= scriptIndent) break;
      body.push(line);
    }
    const bodyIndent = Math.min(
      ...body.filter((line) => line.trim()).map((line) => line.search(/\S/)),
    );
    return body.map((line) => line.slice(bodyIndent)).join('\n');
  }

  function stepCondition(stepName) {
    const block = stepBlock(stepName);
    const at = block.findIndex((line) => /^\s+if:/.test(line));
    assert.ok(at >= 0, `step "${stepName}" has no if: condition`);
    const inline = block[at].replace(/^\s+if:\s*/, '');
    if (inline !== '|') return inline;
    const ifIndent = block[at].search(/\S/);
    const body = [];
    for (const line of block.slice(at + 1)) {
      if (line.trim() && line.search(/\S/) <= ifIndent) break;
      body.push(line.trim());
    }
    return body.join(' ');
  }

  // Minimal evaluator for the GitHub expression subset used by the re-dispatch guard.
  function evaluateCondition(expression, steps) {
    const js = expression
      .replace(/fromJSON\('([^']*)'\)/g, (_m, json) => `JSON.parse(${JSON.stringify(json)})`)
      .replace(/contains\(/g, '__contains(')
      .replace(/steps\.([a-z_]+)\.(outputs\.[a-z_]+|outcome)/g, (_m, id, field) =>
        `__get(${JSON.stringify(id)}, ${JSON.stringify(field)})`)
      .replace(/'([^']*)'/g, (_m, text) => JSON.stringify(text));
    const get = (id, field) => {
      const step = steps[id] || {};
      if (field === 'outcome') return step.outcome || '';
      return (step.outputs || {})[field.slice('outputs.'.length)] || '';
    };
    const contains = (haystack, needle) => haystack.includes(needle);
    return Boolean(new Function('__get', '__contains', `return (${js});`)(get, contains));
  }

  function mergedPr(number, issue, { head = HEAD, body } = {}) {
    return {
      number,
      merged_at: '2026-02-01T00:00:00Z',
      title: `Implement work for issue ${issue}`,
      body: body ?? `<!-- meta:issue:${issue} -->\nCloses #${issue}`,
      head: { sha: head },
    };
  }

  function fillerPrs(count) {
    return Array.from({ length: count }, (_v, index) => ({
      number: 1000 + index,
      merged_at: '2026-01-01T00:00:00Z',
      title: `Unrelated ${1000 + index}`,
      body: 'Closes #9999',
      head: { sha: 'e'.repeat(40) },
    }));
  }

  function dispatchRun(prNumber, head, overrides = {}) {
    return {
      id: 7000 + prNumber,
      event: 'workflow_dispatch',
      display_title: `Verifier PR #${prNumber} head=${head} mode=evaluate`,
      status: 'queued',
      conclusion: null,
      pull_requests: [],
      ...overrides,
    };
  }

  function prTargetRun(prNumber, head, overrides = {}) {
    return {
      id: 8000 + prNumber,
      event: 'pull_request_target',
      display_title: 'Verifier',
      status: 'completed',
      conclusion: 'success',
      pull_requests: [{ number: prNumber, head: { sha: head } }],
      ...overrides,
    };
  }

  function createWorld(seed = {}) {
    return {
      prs: seed.prs || [],
      runs: seed.runs || [],
      knownLabels: new Set(seed.knownLabels || []),
      labelCreateRaces: new Set(seed.labelCreateRaces || []),
      prLabels: new Map(Object.entries(seed.prLabels || {}).map(([k, v]) => [Number(k), new Set(v)])),
      issueLabels: new Set(seed.issueLabels || ['agents:auto-pilot']),
      issueState: seed.issueState || 'open',
      timeline: seed.timeline || [],
      dispatchError: seed.dispatchError || null,
      dispatchCreatesRun: seed.dispatchCreatesRun !== false,
      calls: [],
      comments: [],
      dispatches: [],
      labelWrites: [],
      removed: [],
    };
  }

  function createClient(world, name, { denyLabelWrites = false } = {}) {
    const record = (method, params) => world.calls.push({ client: name, method, params });
    const denied = () => Object.assign(new Error(`${name} token cannot write labels`), { status: 403 });
    const client = {
      name,
      rest: {
        pulls: {
          list: async (params) => {
            record('pulls.list', params);
            const start = (params.page - 1) * params.per_page;
            return { data: world.prs.slice(start, start + params.per_page) };
          },
          get: async (params) => {
            record('pulls.get', params);
            const pr = world.prs.find((item) => item.number === params.pull_number);
            const labels = [...(world.prLabels.get(params.pull_number) || [])].map((n) => ({ name: n }));
            return { data: { ...pr, labels } };
          },
        },
        repos: {
          get: async (params) => {
            record('repos.get', params);
            return { data: { default_branch: 'main' } };
          },
        },
        actions: {
          listWorkflowRuns: async (params) => {
            record('actions.listWorkflowRuns', params);
            if (params.workflow_id === 'agents-auto-pilot.yml') {
              return { data: { workflow_runs: [{ id: 999999, status: 'queued' }] } };
            }
            return { data: { workflow_runs: [...world.runs] } };
          },
          createWorkflowDispatch: async (params) => {
            record('actions.createWorkflowDispatch', params);
            if (params.workflow_id === 'agents-verifier.yml' && world.dispatchError) {
              throw Object.assign(new Error(world.dispatchError), { status: 403 });
            }
            world.dispatches.push({ client: name, ...params });
            if (params.workflow_id === 'agents-verifier.yml' && world.dispatchCreatesRun) {
              world.runs.unshift(dispatchRun(Number(params.inputs.pr_number), params.inputs.pr_head_sha));
            }
            return { status: 204 };
          },
        },
        issues: {
          get: async (params) => {
            record('issues.get', params);
            return {
              data: {
                number: params.issue_number,
                title: 'Issue',
                state: world.issueState,
                labels: [...world.issueLabels].map((n) => ({ name: n })),
              },
            };
          },
          listComments: async (params) => {
            record('issues.listComments', params);
            return { data: [] };
          },
          listEventsForTimeline: async (params) => {
            record('issues.listEventsForTimeline', params);
            return { data: world.timeline };
          },
          createComment: async (params) => {
            record('issues.createComment', params);
            world.comments.push({ issue: params.issue_number, body: params.body });
            return { data: {} };
          },
          getLabel: async (params) => {
            record('issues.getLabel', params);
            if (world.knownLabels.has(params.name)) return { data: { name: params.name } };
            throw Object.assign(new Error('Not Found'), { status: 404 });
          },
          createLabel: async (params) => {
            record('issues.createLabel', params);
            if (denyLabelWrites) throw denied();
            if (world.labelCreateRaces.has(params.name)) {
              // another run created it between our 404 and this request
              world.knownLabels.add(params.name);
              throw Object.assign(new Error('Validation Failed: already_exists'), { status: 422 });
            }
            world.knownLabels.add(params.name);
            return { data: { name: params.name } };
          },
          addLabels: async (params) => {
            record('issues.addLabels', params);
            if (denyLabelWrites) throw denied();
            for (const label of params.labels) {
              if (!world.knownLabels.has(label)) {
                throw Object.assign(new Error(`Label not found: ${label}`), { status: 404 });
              }
            }
            world.labelWrites.push({ client: name, issue: params.issue_number, labels: [...params.labels] });
            const target = params.issue_number === ISSUE
              ? world.issueLabels
              : (world.prLabels.get(params.issue_number) || new Set());
            params.labels.forEach((label) => target.add(label));
            if (params.issue_number !== ISSUE) world.prLabels.set(params.issue_number, target);
            return { data: [] };
          },
          removeLabel: async (params) => {
            record('issues.removeLabel', params);
            world.removed.push({ issue: params.issue_number, name: params.name });
            world.issueLabels.delete(params.name);
            return { data: {} };
          },
        },
      },
    };
    return client;
  }

  function handoffLabelWrites(world) {
    return world.labelWrites.filter(
      (w) => w.labels.includes('verify:pr-handoff') || w.labels.includes('verify:evaluate'),
    );
  }

  async function runStep(stepName, {
    world,
    env = {},
    payload,
    denyLabelWrites = false,
    fallback = true,
    scriptOverride = null,
  }) {
    const github = createClient(world, 'triggering', { denyLabelWrites });
    const fallbackClient = fallback ? createClient(world, 'fallback') : null;
    const withRetry = async (fn) => {
      try {
        return await fn(github);
      } catch (error) {
        if (error?.status === 403 && fallbackClient && /label/i.test(error.message)) {
          return fn(fallbackClient);
        }
        throw error;
      }
    };
    const paginateWithRetry = async (method, params) => (await method(params)).data;
    const retryModule = {
      createTokenAwareRetry: async () => ({ withRetry, paginateWithRetry }),
      isRateLimitError: () => false,
    };
    const requireStub = (name) => {
      if (name.endsWith('/.github/scripts/github-api-with-retry.js')) return retryModule;
      if (name.endsWith('/.github/scripts/auto_pilot_transitions.js')) {
        return transitions;
      }
      throw new Error(`Unexpected require: ${name}`);
    };
    const outputs = {};
    const failures = [];
    const core = {
      setOutput: (key, value) => { outputs[key] = String(value); },
      setFailed: (message) => failures.push(String(message)),
      info: () => {},
      warning: () => {},
    };
    const context = {
      repo: { owner: 'stranske', repo: 'Workflows' },
      runId: 1,
      eventName: 'workflow_dispatch',
      payload: payload || { inputs: { issue_number: String(ISSUE) } },
    };
    const fakeProcess = {
      env: { WORKFLOWS_SCRIPTS_PATH: ROOT, GITHUB_WORKSPACE: ROOT, ISSUE_NUMBER: String(ISSUE), ...env },
    };
    const immediate = (resolve) => resolve();
    const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;
    const script = scriptOverride || stepScript(stepName);
    let error = null;
    try {
      const quiet = { log: () => {} };
      await new AsyncFunction(
        'require', 'github', 'context', 'core', 'process', 'setTimeout', 'console', script,
      )(requireStub, github, context, core, fakeProcess, immediate, quiet);
    } catch (err) {
      error = err;
    }
    const outcome = error || failures.length ? 'failure' : 'success';
    return { outputs, failures, error, outcome };
  }

  const runVerify = (world, options = {}) => runStep('Execute step - Verify', { world, ...options });
  const runDone = (world, env = {}) => runStep('Report - Done', { world, env });
  const pullsListPages = (world) =>
    world.calls.filter((call) => call.method === 'pulls.list').map((call) => call.params.page);
  const ownershipRemoved = (world) =>
    world.removed.some((entry) => entry.issue === ISSUE && entry.name === 'agents:auto-pilot');
  const completionPosted = (world) =>
    world.comments.some((comment) => comment.body.includes('Auto-Pilot Complete'));

  function redispatchFires(nextStep, verify) {
    return evaluateCondition(stepCondition('Re-dispatch for next step'), {
      context: { outputs: { should_continue: 'true' } },
      cycles: { outputs: { exceeded: 'false' } },
      next: { outputs: { next_step: nextStep } },
      verify_step: verify,
    });
  }

  // --- verify step: label handling and dispatch -----------------------------------------

  test(`${surface}: verify: already-present labels are not re-added to the merged PR`, async () => {
    const world = createWorld({
      prs: [mergedPr(PR, ISSUE)],
      knownLabels: ['verify:evaluate', 'verify:pr-handoff'],
      prLabels: { [PR]: ['verify:evaluate'] },
    });
    const result = await runVerify(world);
    assert.equal(result.outputs.verify_handoff, 'found');
    assert.equal(world.calls.filter((c) => c.method === 'issues.createLabel').length, 0);
    assert.ok(!world.labelWrites.some((w) => w.issue === PR), 'PR label rewritten');
    assert.ok(world.labelWrites.some((w) => w.issue === ISSUE && w.labels.includes('verify:pr-handoff')));
  });

  test(`${surface}: verify: a concurrent label creation (422) still completes the handoff`, async () => {
    // Workflows#4366 review finding: two runs both see the label missing; the loser's
    // createLabel answers 422. The handoff must re-read the label and continue.
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)], labelCreateRaces: ['verify:pr-handoff'] });
    const result = await runVerify(world);
    assert.equal(result.outcome, 'success', result.failures.join('; ') || result.error?.message);
    assert.ok(world.calls.some((c) => c.method === 'issues.createLabel' && c.params.name === 'verify:pr-handoff'));
    assert.ok(world.labelWrites.some((w) => w.issue === ISSUE && w.labels.includes('verify:pr-handoff')));
  });

  test(`${surface}: verify: label mutation falls back to the secondary token when the primary is denied`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)] });
    const result = await runVerify(world, { denyLabelWrites: true });
    assert.equal(result.outcome, 'success', result.failures.join('; ') || result.error?.message);
    assert.ok(world.labelWrites.length > 0);
    assert.ok(world.labelWrites.every((w) => w.client === 'fallback'));
    assert.ok(world.labelWrites.some((w) => w.issue === ISSUE && w.labels.includes('verify:pr-handoff')));
  });

  test(`${surface}: verify: failed dispatch with no matching run withholds markers and fails`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)], dispatchError: 'No triggering credential' });
    const result = await runVerify(world);
    assert.equal(result.outcome, 'failure');
    assert.notEqual(result.outputs.verify_handoff, 'found');
    assert.deepEqual(world.labelWrites, []);
    assert.equal(ownershipRemoved(world), false);
  });

  test(`${surface}: verify: pre-existing handoff labels do not authorize when dispatch is denied`, async () => {
    const world = createWorld({
      prs: [mergedPr(PR, ISSUE)],
      dispatchError: 'No triggering credential',
      knownLabels: ['verify:evaluate', 'verify:pr-handoff'],
      issueLabels: ['agents:auto-pilot', 'verify:evaluate', 'verify:pr-handoff'],
      prLabels: { [PR]: ['verify:evaluate', 'verify:pr-handoff'] },
    });
    const result = await runVerify(world);
    assert.equal(result.outcome, 'failure');
    assert.notEqual(result.outputs.verify_handoff, 'found');
    assert.equal(handoffLabelWrites(world).length, 0, 'verify:pr-handoff must not be (re)written');
    assert.equal(ownershipRemoved(world), false);
  });

  test(`${surface}: verify: fallback token label writes are withheld when dispatch is denied`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)], dispatchError: 'denied' });
    const result = await runVerify(world, { denyLabelWrites: true });
    assert.equal(result.outcome, 'failure');
    assert.notEqual(result.outputs.verify_handoff, 'found');
    assert.equal(handoffLabelWrites(world).length, 0);
    assert.equal(world.labelWrites.length, 0);
    assert.equal(ownershipRemoved(world), false);
  });

  test(`${surface}: deliberate-break gate: fallback-only marker authorization is rejected`, async () => {
    const seed = {
      prs: [mergedPr(PR, ISSUE)],
      dispatchError: 'denied',
      knownLabels: ['verify:evaluate', 'verify:pr-handoff'],
      issueLabels: ['agents:auto-pilot', 'verify:evaluate', 'verify:pr-handoff'],
      prLabels: { [PR]: ['verify:evaluate'] },
    };
    const defective = stepScript('Execute step - Verify').replace(
      'let verifierAuthorized = Boolean(await findExistingVerifierRun());',
      'let verifierAuthorized = true; // deliberate-break: fallback-only marker authorization',
    );
    const brokenWorld = createWorld(seed);
    const broken = await runStep('Execute step - Verify', {
      world: brokenWorld,
      scriptOverride: defective,
    });
    assert.equal(broken.outputs.verify_handoff, 'found', 'deliberate-break must simulate unauthorized success');
    assert.equal(broken.outcome, 'success');

    const realWorld = createWorld(seed);
    const fixed = await runVerify(realWorld);
    assert.equal(fixed.outcome, 'failure');
    assert.notEqual(fixed.outputs.verify_handoff, 'found');
    assert.equal(handoffLabelWrites(realWorld).length, 0);
  });

  test(`${surface}: verify: no matching merged PR reports absent and records no markers`, async () => {
    const world = createWorld({ prs: fillerPrs(3) });
    const result = await runVerify(world);
    assert.equal(result.outputs.verify_handoff, 'absent');
    assert.equal(result.outcome, 'failure');
    assert.deepEqual(world.labelWrites, []);
  });

  test(`${surface}: verify: accepted dispatch uses the existing triggering credentials`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)] });
    const result = await runVerify(world);
    assert.equal(result.outputs.verify_handoff, 'found');
    const verifier = world.dispatches.filter((d) => d.workflow_id === 'agents-verifier.yml');
    assert.equal(verifier.length, 1);
    assert.equal(verifier[0].client, 'triggering');
    assert.deepEqual(verifier[0].inputs, { pr_number: String(PR), pr_head_sha: HEAD, mode: 'evaluate' });
  });

  test(`${surface}: verify: exact PR/head existing run is reused without a new dispatch`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)], runs: [dispatchRun(PR, HEAD)] });
    const result = await runVerify(world);
    assert.equal(result.outputs.verify_handoff, 'found');
    assert.equal(world.dispatches.length, 0);
  });

  test(`${surface}: verify: mismatched PR/head runs do not count and failed dispatch fails`, async () => {
    const world = createWorld({
      prs: [mergedPr(PR, ISSUE)],
      runs: [prTargetRun(PR, OTHER_HEAD), dispatchRun(PR + 1, HEAD)],
      dispatchError: 'denied',
    });
    const result = await runVerify(world);
    assert.equal(result.outcome, 'failure');
    assert.notEqual(result.outputs.verify_handoff, 'found');
  });

  // --- Report - Done: PR/head-bound revalidation ----------------------------------------

  test(`${surface}: done: label-only handoff without a verifier run never records completion`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)] });
    const result = await runDone(world, { VERIFY_HANDOFF: '', VERIFY_HANDOFF_BOUND: 'true' });
    assert.equal(result.outcome, 'failure');
    assert.equal(ownershipRemoved(world), false);
    assert.equal(completionPosted(world), false);
  });

  test(`${surface}: done: mismatched PR/head runs never record completion`, async () => {
    const world = createWorld({
      prs: [mergedPr(PR, ISSUE)],
      runs: [
        prTargetRun(PR, OTHER_HEAD),
        prTargetRun(PR + 1, HEAD),
        dispatchRun(PR, OTHER_HEAD),
        prTargetRun(PR, HEAD, { conclusion: 'failure' }),
      ],
    });
    const result = await runDone(world, { VERIFY_HANDOFF: '', VERIFY_HANDOFF_BOUND: 'true' });
    assert.equal(result.outcome, 'failure');
    assert.equal(ownershipRemoved(world), false);
  });

  test(`${surface}: done: exact PR/head runs complete and release ownership`, async () => {
    for (const run of [dispatchRun(PR, HEAD)]) {
      const world = createWorld({ prs: [mergedPr(PR, ISSUE)], runs: [run] });
      const result = await runDone(world, { VERIFY_HANDOFF: '', VERIFY_HANDOFF_BOUND: 'true' });
      assert.equal(result.outcome, 'success', `${run.event}: ${result.failures.join('; ')}`);
      assert.equal(ownershipRemoved(world), true);
      assert.equal(completionPosted(world), true);
    }
  });

  test(`${surface}: no-op PR label runs cannot authorize verifier handoff or completion`, async () => {
    for (const status of ['queued', 'in_progress', 'completed']) {
      const world = createWorld({prs:[mergedPr(PR, ISSUE)], runs:[prTargetRun(PR,HEAD,{status})],
        dispatchError:'denied',knownLabels:['verify:evaluate','verify:pr-handoff']});
      const result = await runStep('Execute step - Verify',{world});
      assert.equal(result.outcome,'failure');
      assert.equal(handoffLabelWrites(world).length,0);
      const done = await runDone(world,{VERIFY_HANDOFF:'',VERIFY_HANDOFF_BOUND:'true'});
      assert.equal(done.outcome,'failure');
      assert.equal(completionPosted(world),false);
    }
  });

  // --- end-to-end routing: verify -> re-dispatch -> done --------------------------------

  test(`${surface}: routing: successful confirmed verify re-dispatches done and reaches guarded completion`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)] });
    const verify = await runVerify(world);
    assert.equal(verify.outputs.verify_handoff, 'found');
    assert.equal(redispatchFires('verify', verify), true, 're-dispatch guard skipped a confirmed handoff');

    const redispatch = await runStep('Re-dispatch for next step', {
      world,
      env: { CURRENT_STEP: 'verify' },
    });
    assert.equal(redispatch.outcome, 'success', redispatch.failures.join('; '));
    const autopilot = world.dispatches.filter((d) => d.workflow_id === 'agents-auto-pilot.yml');
    assert.equal(autopilot.length, 1);
    assert.equal(autopilot[0].inputs.force_step, 'done');

    const forced = determineNextStep({ issueState: 'closed', forceStep: autopilot[0].inputs.force_step });
    assert.equal(forced.nextStep, 'done');

    const done = await runDone(world, {
      VERIFY_HANDOFF: '',
      VERIFY_HANDOFF_BOUND: world.issueLabels.has('verify:pr-handoff') ? 'true' : 'false',
    });
    assert.equal(done.outcome, 'success', done.failures.join('; '));
    assert.equal(ownershipRemoved(world), true);
    assert.equal(completionPosted(world), true);
  });

  async function completeClosedIssue(world) {
    world.issueState = 'closed';
    const initialContext = await runStep('Determine context', { world });
    assert.equal(initialContext.outcome, 'success');
    assert.equal(initialContext.outputs.should_continue, 'true');
    assert.equal(initialContext.outputs.issue_number, String(ISSUE));
    const disposition = determineNextStep({
      issueState: initialContext.outputs.issue_state,
      hasVerify: initialContext.outputs.has_verify,
      verifyHandoffBound: initialContext.outputs.verify_handoff_bound,
    });
    assert.equal(disposition.nextStep, 'verify', 'historical labels cannot select done');

    const verify = await runVerify(world);
    assert.equal(verify.outcome, 'success', verify.failures.join('; ') || verify.error?.message);
    assert.equal(verify.outputs.verify_handoff, 'found');
    assert.equal(redispatchFires(disposition.nextStep, verify), true,
      'confirmed legacy handoff must automatically continue');

    const redispatch = await runStep('Re-dispatch for next step', {
      world,
      env: { CURRENT_STEP: disposition.nextStep },
    });
    assert.equal(redispatch.outcome, 'success', redispatch.failures.join('; '));
    const continuations = world.dispatches.filter((d) => d.workflow_id === 'agents-auto-pilot.yml');
    assert.equal(continuations.length, 1);
    assert.equal(continuations[0].inputs.issue_number, String(ISSUE));
    const forced = determineNextStep({ forceStep: continuations[0].inputs.force_step });
    assert.equal(forced.nextStep, 'done');

    // A new workflow run has no verify_step outputs. It must revalidate the
    // actual dispatched PR/head run, rather than inheriting same-run evidence.
    const continuationContext = await runStep('Determine context', { world });
    assert.equal(continuationContext.outcome, 'success');
    assert.equal(continuationContext.outputs.should_continue, 'true');
    const done = await runDone(world, {
      ISSUE_NUMBER: continuationContext.outputs.issue_number,
      VERIFY_HANDOFF: '',
      VERIFY_HANDOFF_BOUND: continuationContext.outputs.verify_handoff_bound,
    });
    assert.equal(done.outcome, 'success', done.failures.join('; ') || done.error?.message);
    assert.equal(world.issueLabels.has('agents:auto-pilot'), false);
    assert.ok(world.removed.some((r) => r.issue === ISSUE && r.name === 'agents:auto-pilot'));
    const reports = world.comments.filter((c) => c.body.includes('Auto-Pilot Complete'));
    assert.equal(reports.length, 1);
    assert.equal(reports[0].issue, ISSUE);
    assert.match(reports[0].body, /verification triggered on a merged source PR/);
  }

  test(`${surface}: issue 4365: legacy verify:evaluate automatically completes and releases ownership`, async () => {
    const world = createWorld({
      prs: [mergedPr(PR, ISSUE)],
      issueLabels: ['agents:auto-pilot', 'verify:evaluate'],
      knownLabels: ['verify:evaluate'],
    });
    await completeClosedIssue(world);
    const verifier = world.dispatches.filter((d) => d.workflow_id === 'agents-verifier.yml');
    assert.equal(verifier.length, 1);
    assert.deepEqual(verifier[0].inputs, {
      pr_number: String(PR), pr_head_sha: HEAD, mode: 'evaluate',
    });
  });

  test(`${surface}: issue 4365: delayed verifier visibility retains ownership until a bound run is observed`, async () => {
    const world = createWorld({
      prs: [mergedPr(PR, ISSUE)],
      issueState: 'closed',
      issueLabels: ['agents:auto-pilot', 'verify:evaluate'],
      dispatchCreatesRun: false,
    });
    const verify = await runVerify(world);
    assert.equal(verify.outcome, 'success');
    assert.equal(verify.outputs.verify_handoff, 'found');
    assert.equal(redispatchFires('verify', verify), true);
    const redispatch = await runStep('Re-dispatch for next step', {
      world,
      env: { CURRENT_STEP: 'verify' },
    });
    assert.equal(redispatch.outcome, 'success');
    const continuation = world.dispatches.find((d) => d.workflow_id === 'agents-auto-pilot.yml');
    assert.equal(continuation.inputs.force_step, 'done');

    // Dispatch acceptance is evidence in the verify run only. The separately
    // dispatched reporter has to observe the correlated run for itself.
    const context = await runStep('Determine context', { world });
    assert.equal(context.outcome, 'success');
    assert.equal(context.outputs.verify_handoff_bound, 'true');
    assert.deepEqual(world.runs, []);
    const done = await runDone(world, {
      VERIFY_HANDOFF: '',
      VERIFY_HANDOFF_BOUND: context.outputs.verify_handoff_bound,
    });
    assert.equal(done.outcome, 'failure');
    assert.match(done.failures.join('; '), /verification handoff missing/);
    assert.equal(completionPosted(world), false);
    assert.equal(ownershipRemoved(world), false);
    assert.ok(world.issueLabels.has('agents:auto-pilot'));

    // Once GitHub exposes the run, normal closed-issue routing must recover
    // without dispatching a second verifier or depending on a label event.
    world.runs.push(dispatchRun(PR, HEAD));
    world.dispatches = [];
    await completeClosedIssue(world);
    assert.equal(world.dispatches.filter((d) => d.workflow_id === 'agents-verifier.yml').length, 0);
  });

  test(`${surface}: issue 4365: reopening then closing with a different PR verifies the new PR`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)] });
    await completeClosedIssue(world);

    // Re-enable auto-pilot on reopening while retaining both old handoff labels
    // and the old verifier run. Neither is proof for the next closing PR.
    world.issueLabels.add('agents:auto-pilot');
    const reopened = determineNextStep({
      issueState: 'open', linkedPr: String(PR),
      hasVerify: true, verifyHandoffBound: true,
    });
    assert.equal(reopened.nextStep, 'monitor-pr');
    world.prs.unshift(mergedPr(PR + 1, ISSUE, { head: OTHER_HEAD }));
    world.dispatches = [];
    world.comments = [];
    world.removed = [];

    await completeClosedIssue(world);
    const verifier = world.dispatches.filter((d) => d.workflow_id === 'agents-verifier.yml');
    assert.equal(verifier.length, 1, 'old PR verifier run cannot satisfy the new closure');
    assert.deepEqual(verifier[0].inputs, {
      pr_number: String(PR + 1), pr_head_sha: OTHER_HEAD, mode: 'evaluate',
    });
  });

  test(`${surface}: issue 4365: failed new handoff after reopening retains ownership until retry completes`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)] });
    await completeClosedIssue(world);

    world.issueState = 'open';
    world.issueLabels.add('agents:auto-pilot');
    const reopened = await runStep('Determine context', { world });
    assert.equal(reopened.outputs.issue_state, 'open');
    assert.equal(reopened.outputs.verify_handoff_bound, 'true');
    world.issueState = 'closed';
    world.prs.unshift(mergedPr(PR + 1, ISSUE, { head: OTHER_HEAD }));
    world.dispatchError = 'verifier dispatch denied';
    world.dispatches = [];
    world.comments = [];
    world.removed = [];
    world.labelWrites = [];

    const reclosed = await runStep('Determine context', { world });
    const disposition = determineNextStep({
      issueState: reclosed.outputs.issue_state,
      hasVerify: reclosed.outputs.has_verify,
      verifyHandoffBound: reclosed.outputs.verify_handoff_bound,
    });
    assert.equal(disposition.nextStep, 'verify');
    const failed = await runVerify(world);
    assert.equal(failed.outcome, 'failure');
    assert.notEqual(failed.outputs.verify_handoff, 'found');
    assert.equal(redispatchFires(disposition.nextStep, failed), false);
    assert.deepEqual(world.dispatches, []);
    assert.deepEqual(handoffLabelWrites(world), []);
    assert.equal(completionPosted(world), false);
    assert.equal(ownershipRemoved(world), false);
    assert.ok(world.issueLabels.has('agents:auto-pilot'));
    assert.equal(world.runs.length, 1, 'only the previous closure has a verifier run');

    world.dispatchError = null;
    await completeClosedIssue(world);
    const verifier = world.dispatches.filter((d) => d.workflow_id === 'agents-verifier.yml');
    assert.equal(verifier.length, 1);
    assert.deepEqual(verifier[0].inputs, {
      pr_number: String(PR + 1), pr_head_sha: OTHER_HEAD, mode: 'evaluate',
    });
  });

  for (const [scenario, newPr, newHead] of [
    ['a different PR and head', PR + 1, OTHER_HEAD],
    ['a different PR with the same head', PR + 1, HEAD],
    ['the same PR with a different head', PR, OTHER_HEAD],
  ]) {
    test(`${surface}: issue 4365: delayed done after reopening rejects ${scenario}`, async () => {
      const world = createWorld({
        prs: [mergedPr(PR, ISSUE)],
        issueLabels: ['agents:auto-pilot', 'verify:evaluate'],
      });
      const verify = await runVerify(world);
      assert.equal(verify.outcome, 'success', verify.failures.join('; '));
      assert.equal(verify.outputs.verify_handoff, 'found');
      assert.equal(redispatchFires('verify', verify), true);
      const redispatch = await runStep('Re-dispatch for next step', {
        world,
        env: { CURRENT_STEP: 'verify' },
      });
      assert.equal(redispatch.outcome, 'success', redispatch.failures.join('; '));
      const delayed = world.dispatches.find((d) => d.workflow_id === 'agents-auto-pilot.yml');
      assert.equal(delayed.inputs.force_step, 'done');
      assert.equal(completionPosted(world), false);

      // Reopen and close again while the previous closure's continuation waits.
      // Keep its handoff labels and verifier run, including when only one part
      // of the PR/head identity changes.
      assert.equal(determineNextStep({
        issueState: 'open', linkedPr: String(PR),
        hasVerify: true, verifyHandoffBound: true,
      }).nextStep, 'monitor-pr');
      if (newPr === PR) world.prs[0] = mergedPr(newPr, ISSUE, { head: newHead });
      else world.prs.unshift(mergedPr(newPr, ISSUE, { head: newHead }));
      assert.equal(determineNextStep({
        issueState: 'closed', hasVerify: true, verifyHandoffBound: true,
      }).nextStep, 'verify');

      // A forced continuation bypasses state selection, so the reporter itself
      // must reject the old run. No verify outputs survive into this execution.
      assert.equal(determineNextStep({
        issueState: 'closed', forceStep: delayed.inputs.force_step,
      }).nextStep, 'done');
      const staleDone = await runDone(world, {
        VERIFY_HANDOFF: '',
        VERIFY_HANDOFF_BOUND: world.issueLabels.has('verify:pr-handoff') ? 'true' : 'false',
      });
      assert.equal(staleDone.outcome, 'failure');
      assert.match(staleDone.failures.join('; '), /verification handoff missing/);
      assert.equal(completionPosted(world), false);
      assert.equal(ownershipRemoved(world), false);
      assert.equal(world.issueLabels.has('agents:auto-pilot'), true);
      assert.equal(world.runs.length, 1, 'refused completion cannot invent verification');

      // The refused old continuation must not prevent the new closure completing.
      world.dispatches = [];
      await completeClosedIssue(world);
      const verifier = world.dispatches.filter((d) => d.workflow_id === 'agents-verifier.yml');
      assert.equal(verifier.length, 1, 'new closure requires its own verifier dispatch');
      assert.deepEqual(verifier[0].inputs, {
        pr_number: String(newPr), pr_head_sha: newHead, mode: 'evaluate',
      });
    });
  }

  test(`${surface}: routing: failed verify retains ownership and does not re-dispatch done`, async () => {
    const world = createWorld({ prs: [mergedPr(PR, ISSUE)], dispatchError: 'denied' });
    const verify = await runVerify(world);
    assert.equal(verify.outcome, 'failure');
    assert.equal(redispatchFires('verify', verify), false);
    assert.equal(ownershipRemoved(world), false);
    assert.ok(world.issueLabels.has('agents:auto-pilot'));
  });

  test(`${surface}: routing: unconfirmed verify outputs never fire the done re-dispatch`, () => {
    for (const handoff of ['', 'absent', 'incomplete']) {
      assert.equal(redispatchFires('verify', { outcome: 'success', outputs: { verify_handoff: handoff } }), false);
    }
    assert.equal(redispatchFires('format', {}), true);
  });

  test(`${surface}: routing: closed issue with verify:pr-handoff label still resolves to verify, not done`, () => {
    const result = determineNextStep({ issueState: 'closed', hasVerify: true, verifyHandoffBound: true });
    assert.equal(result.nextStep, 'verify');
  });

  test(`${surface}: routing: done is exposed as a manual force_step for recovery`, () => {
    const lines = fs.readFileSync(workflowPath, 'utf8').split('\n');
    const start = lines.findIndex((line) => line.trim() === 'force_step:');
    const options = lines.slice(start, start + 20).map((line) => line.trim());
    assert.ok(options.includes('- done'), 'workflow_dispatch force_step options omit done');
  });

  // --- pagination -----------------------------------------------------------------------

  test(`${surface}: pagination: first-page match costs exactly one pulls.list request in verify and done`, async () => {
    const verifyWorld = createWorld({ prs: [mergedPr(PR, ISSUE), ...fillerPrs(999)] });
    await runVerify(verifyWorld);
    assert.deepEqual(pullsListPages(verifyWorld), [1]);

    const doneWorld = createWorld({ prs: [mergedPr(PR, ISSUE), ...fillerPrs(999)], runs: [prTargetRun(PR, HEAD)] });
    await runDone(doneWorld, { VERIFY_HANDOFF: '', VERIFY_HANDOFF_BOUND: 'true' });
    assert.deepEqual(pullsListPages(doneWorld), [1]);
  });

  test(`${surface}: pagination: unsuccessful lookups keep the pre-change maximum page bound`, async () => {
    const pages = Array.from({ length: PRE_CHANGE_MAX_PAGES }, (_v, i) => i + 1);

    const verifyWorld = createWorld({ prs: fillerPrs(2000) });
    const verify = await runVerify(verifyWorld);
    assert.equal(verify.outputs.verify_handoff, 'incomplete');
    assert.deepEqual(pullsListPages(verifyWorld), pages);

    const doneWorld = createWorld({ prs: fillerPrs(2000) });
    const done = await runDone(doneWorld, { VERIFY_HANDOFF: '', VERIFY_HANDOFF_BOUND: 'true' });
    assert.equal(done.outcome, 'failure');
    assert.deepEqual(pullsListPages(doneWorld), pages);
  });

  // --- issue-marker identity ------------------------------------------------------------

  test(`${surface}: marker: meta:issue:123 cannot select a PR for issue #12 in verify or done`, async () => {
    const otherIssuePr = mergedPr(PR, 123, { body: '<!-- meta:issue:123 -->' });

    const verifyWorld = createWorld({ prs: [otherIssuePr] });
    const verify = await runVerify(verifyWorld, { env: { ISSUE_NUMBER: '12' } });
    assert.equal(verify.outputs.verify_handoff, 'absent');
    assert.equal(verifyWorld.dispatches.length, 0);

    const doneWorld = createWorld({ prs: [otherIssuePr], runs: [prTargetRun(PR, HEAD)] });
    const done = await runDone(doneWorld, {
      ISSUE_NUMBER: '12', VERIFY_HANDOFF: '', VERIFY_HANDOFF_BOUND: 'true',
    });
    assert.equal(done.outcome, 'failure');
    assert.equal(completionPosted(doneWorld), false);
  });

  test(`${surface}: marker: Determine context links only the PR whose meta:issue matches exactly`, async () => {
    const crossRef = (number, body) => ({
      event: 'cross-referenced',
      source: {
        issue: {
          number,
          body,
          title: 'Work',
          pull_request: {},
          repository: { full_name: 'stranske/Workflows' },
        },
      },
    });
    const prefixWorld = createWorld({
      issueLabels: [],
      timeline: [crossRef(901, '<!-- meta:issue:123 -->')],
    });
    const prefix = await runStep('Determine context', {
      world: prefixWorld,
      payload: { inputs: { issue_number: '12' } },
    });
    assert.equal(prefix.outputs.linked_pr, '');

    const exactWorld = createWorld({
      issueLabels: [],
      timeline: [crossRef(901, '<!-- meta:issue:123 -->'), crossRef(902, '<!-- meta:issue:12 -->')],
    });
    const exact = await runStep('Determine context', {
      world: exactWorld,
      payload: { inputs: { issue_number: '12' } },
    });
    assert.equal(exact.outputs.linked_pr, '902');
  });
}
