'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');
const assert = require('node:assert/strict');

const {
  FORCED_STEPS,
  NEXT_STEPS,
  STATES,
  TRANSITION_CONTRACT,
  buildDetermineNextStepEventFromEnv,
  determineNextStep,
  findLatestClosureEvent,
  findLatestVerifyHandoff,
  formatVerifyHandoffMarker,
  isKeepaliveTasksComplete,
  normalizeForceStep,
  redispatchForceStep,
  resolveCurrentState,
  transition,
} = require('../auto_pilot_transitions.js');

const fixtures = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, 'fixtures', 'auto-pilot-transitions.json'),
    'utf8',
  ),
);

test('transition contract documents every state and next step', () => {
  assert.deepEqual(Object.keys(TRANSITION_CONTRACT.transitions).sort(), Object.values(STATES).sort());
  assert.deepEqual(
    Object.values(TRANSITION_CONTRACT.transitions).sort(),
    [
      NEXT_STEPS.APPLY,
      NEXT_STEPS.CAPABILITY_CHECK,
      NEXT_STEPS.CHECK_COMPLETION,
      NEXT_STEPS.CREATE_PR,
      NEXT_STEPS.DONE,
      NEXT_STEPS.FORMAT,
      NEXT_STEPS.MONITOR_PR,
      NEXT_STEPS.OPTIMIZE,
      NEXT_STEPS.VERIFY,
    ].sort(),
  );
  assert.match(TRANSITION_CONTRACT.guards.join('\n'), /PR-bound verify handoff/);
  assert.match(TRANSITION_CONTRACT.guards.join('\n'), /optimizer suggestions comment/);
  assert.match(TRANSITION_CONTRACT.guards.join('\n'), /keepalive state/);
});

for (const scenario of fixtures.validTransitions) {
  test(`valid transition: ${scenario.name}`, () => {
    assert.equal(resolveCurrentState(scenario.event), scenario.state);
    assert.equal(transition(scenario.state, scenario.event), scenario.nextStep);
    const result = determineNextStep(scenario.event);
    assert.equal(result.currentState, scenario.state);
    assert.equal(result.nextStep, scenario.nextStep);
    assert.equal(result.forced, false);
  });
}

for (const scenario of fixtures.guardCases) {
  test(`guard condition: ${scenario.name}`, () => {
    const result = determineNextStep(scenario.event);
    assert.equal(result.currentState, scenario.state);
    assert.equal(result.nextStep, scenario.nextStep);
  });
}

for (const scenario of fixtures.incidentEdges) {
  test(`incident edge: ${scenario.name}`, () => {
    const result = determineNextStep(scenario.event);
    assert.equal(result.currentState, scenario.state);
    assert.equal(result.nextStep, scenario.nextStep);
  });
}

test('invalid transition state throws', () => {
  assert.throws(
    () => transition('needs-teleport', {}),
    /Invalid auto-pilot state transition: needs-teleport/,
  );
});

test('empty transition state throws', () => {
  assert.throws(
    () => transition('', {}),
    /Invalid auto-pilot state transition: <empty>/,
  );
});

test('invalid force step throws instead of silently producing an unsupported step', () => {
  assert.throws(
    () => determineNextStep({ forceStep: 'unknown-step' }),
    /Invalid auto-pilot force step: unknown-step/,
  );
});

test('valid force steps bypass state detection', () => {
  for (const forcedStep of FORCED_STEPS) {
    const result = determineNextStep({
      forceStep: forcedStep,
      issueState: 'closed',
      hasVerify: true,
    });
    assert.equal(result.currentState, 'forced');
    assert.equal(result.nextStep, forcedStep);
    assert.equal(result.forced, true);
  }
});

test('linked PR with completed keepalive state advances to completion check', () => {
  const result = determineNextStep({
    linkedPr: '123',
    keepaliveState: '<!-- keepalive-state:v1 {"last_action":"stop","last_reason":"tasks-complete"} -->',
  });

  assert.equal(result.currentState, STATES.PR_TASKS_COMPLETE);
  assert.equal(result.nextStep, NEXT_STEPS.CHECK_COMPLETION);
  assert.match(result.message, /PR tasks complete/);
});

test('auto and blank force steps are ignored', () => {
  assert.equal(normalizeForceStep('auto'), '');
  assert.equal(normalizeForceStep(''), '');
  assert.equal(normalizeForceStep(null), '');
});

test('legacy agent force step maps to implemented capability-check step', () => {
  assert.equal(normalizeForceStep('agent'), NEXT_STEPS.CAPABILITY_CHECK);
  assert.equal(
    determineNextStep({ forceStep: 'agent' }).nextStep,
    NEXT_STEPS.CAPABILITY_CHECK,
  );
});

test('keepalive completion guard matches compact state marker currently emitted by keepalive', () => {
  assert.equal(
    isKeepaliveTasksComplete('<!-- keepalive-state:v1 {"last_action":"stop","last_reason":"tasks-complete"} -->'),
    true,
  );
  assert.equal(
    isKeepaliveTasksComplete('<!-- keepalive-state:v1 {"last_action": "stop", "last_reason": "tasks-complete"} -->'),
    false,
  );
});

test('redispatch map preserves current workflow force_step contract', () => {
  assert.equal(redispatchForceStep('format'), 'optimize');
  assert.equal(redispatchForceStep('optimize'), 'apply');
  assert.equal(redispatchForceStep('apply'), 'capability-check');
  assert.equal(redispatchForceStep('capability-check'), 'auto');
  assert.equal(redispatchForceStep('create-pr'), 'auto');
  assert.equal(redispatchForceStep('monitor-pr'), 'auto');
  // Only dispatched after a confirmed PR/head verify handoff (issue #4366).
  assert.equal(redispatchForceStep('verify'), 'done');
});

test('a handoff from an earlier closure cannot complete a reopened issue closed by another PR', () => {
  const original = {
    issueState: 'closed',
    verifyHandoffBound: true,
    closure: { id: 1001, sourcePr: 2454 },
    verifyHandoff: { closureId: 1001, sourcePr: 2454 },
  };
  assert.equal(determineNextStep(original).nextStep, NEXT_STEPS.DONE);
  assert.equal(
    determineNextStep({ ...original, issueState: 'open' }).nextStep,
    NEXT_STEPS.FORMAT,
  );

  const reclosed = { ...original, closure: { id: 1002, sourcePr: 2455 } };
  assert.equal(determineNextStep(reclosed).currentState, STATES.CLOSED_NEEDS_VERIFY);
  assert.equal(determineNextStep(reclosed).nextStep, NEXT_STEPS.VERIFY);

  // Only a new handoff for the new closure may complete the issue.
  assert.equal(
    determineNextStep({
      ...reclosed,
      verifyHandoff: { closureId: 1002, sourcePr: 2455 },
    }).nextStep,
    NEXT_STEPS.DONE,
  );
});

test('a new closure by the same PR still requires a new handoff', () => {
  assert.equal(determineNextStep({
    issueState: 'closed',
    verifyHandoffBound: true,
    closure: { id: 1002, sourcePr: 2454 },
    verifyHandoff: { closureId: 1001, sourcePr: 2454 },
  }).nextStep, NEXT_STEPS.VERIFY);
});

test('matching closure ID with a different source PR cannot complete the issue', () => {
  assert.equal(determineNextStep({
    issueState: 'closed',
    verifyHandoffBound: true,
    closure: { id: 1001, sourcePr: 2455 },
    verifyHandoff: { closureId: 1001, sourcePr: 2454 },
  }).nextStep, NEXT_STEPS.VERIFY);
});

test('handoff marker helpers round-trip persisted identity', () => {
  const marker = formatVerifyHandoffMarker({ closureId: 3001, sourcePr: 2454 });
  assert.match(marker, /auto-pilot-verify-handoff:v1/);
  const comments = [{
    body: `note\n${marker}`,
    user: { login: 'github-actions[bot]', type: 'Bot' },
  }];
  assert.deepEqual(findLatestVerifyHandoff(comments), {
    closureId: '3001',
    sourcePr: '2454',
  });
  assert.equal(findLatestClosureEvent([
    { event: 'closed', id: 1001 },
    { event: 'reopened' },
    { event: 'closed', id: 1002 },
  ])?.id, 1002);
});

test('buildDetermineNextStepEventFromEnv maps closure-bound env inputs', () => {
  const event = buildDetermineNextStepEventFromEnv({
    ISSUE_STATE: 'closed',
    HAS_VERIFY: 'true',
    VERIFY_HANDOFF_BOUND: 'true',
    CLOSURE_ID: '1001',
    CLOSURE_SOURCE_PR: '2454',
    VERIFY_HANDOFF_CLOSURE_ID: '1001',
    VERIFY_HANDOFF_SOURCE_PR: '2454',
  });
  assert.equal(determineNextStep(event).nextStep, NEXT_STEPS.DONE);
});

test('label-only handoffs from the current workflow stay pending verification', () => {
  // The current workflow supplies this boolean but no source identity.
  assert.equal(determineNextStep({
    issueState: 'closed',
    hasVerify: true,
    verifyHandoffBound: 'true',
  }).nextStep, NEXT_STEPS.VERIFY);
});

test('handoff identities accept serialized positive IDs and reject absent or malformed IDs', () => {
  const event = {
    issueState: 'closed',
    verifyHandoffBound: 'true',
    closure: { id: 1001, sourcePr: 2454 },
    verifyHandoff: { closureId: '1001', sourcePr: '2454' },
  };
  assert.equal(determineNextStep(event).nextStep, NEXT_STEPS.DONE);
  assert.equal(
    determineNextStep({ ...event, verifyHandoffBound: false }).nextStep,
    NEXT_STEPS.VERIFY,
  );
  for (const field of ['closure', 'verifyHandoff']) {
    assert.equal(
      determineNextStep({ ...event, [field]: undefined }).nextStep,
      NEXT_STEPS.VERIFY,
    );
    for (const key of Object.keys(event[field])) {
      for (const value of [
        undefined, null, '', 0, -1, 1.5, 'not-an-id', true,
        [], [1001], [2454], {}, Number.MAX_SAFE_INTEGER + 1,
      ]) {
        assert.equal(determineNextStep({
          ...event,
          [field]: { ...event[field], [key]: value },
        }).nextStep, NEXT_STEPS.VERIFY, `${field}.${key}=${value}`);
      }
    }
  }
});

for (const [surface, transitions] of [
  ['source', require('../auto_pilot_transitions.js')],
  ['consumer template', require('../../../templates/consumer-repo/.github/scripts/auto_pilot_transitions.js')],
]) {
  test(`${surface}: untrusted handoff markers cannot authorize a closure`, () => {
    const marker = transitions.formatVerifyHandoffMarker({ closureId: 3001, sourcePr: 2454 });
    const trusted = {
      body: marker,
      user: { login: 'agents-workflows-bot[bot]', type: 'Bot' },
    };
    const forged = {
      body: transitions.formatVerifyHandoffMarker({ closureId: 3002, sourcePr: 2455 }),
      user: { login: 'someone', type: 'User' },
    };
    assert.equal(transitions.findLatestVerifyHandoff([forged]), null);
    assert.equal(transitions.findLatestVerifyHandoff([{ body: marker }]), null);
    assert.equal(
      transitions.findLatestVerifyHandoff([{
        body: marker,
        user: { login: 'github-actions[bot]', type: 'User' },
      }]),
      null,
    );
    assert.deepEqual(transitions.findLatestVerifyHandoff([trusted, forged]), {
      closureId: '3001',
      sourcePr: '2454',
    });
    const newerTrusted = {
      body: transitions.formatVerifyHandoffMarker({ closureId: 3002, sourcePr: 2455 }),
      user: { login: 'stranske-automation-bot', type: 'User' },
    };
    assert.deepEqual(transitions.findLatestVerifyHandoff([trusted, newerTrusted]), {
      closureId: '3002',
      sourcePr: '2455',
    });
  });

  test(`${surface}: merged closing PR selection skips newer unmerged and prefix issue refs`, () => {
    const pulls = [
      { number: 101, merged_at: null, title: 'later', body: 'Closes #12' },
      { number: 123, merged_at: '2026-03-01T00:00:00Z', body: '<!-- meta:issue:123 -->' },
      { number: 100, merged_at: '2026-02-01T00:00:00Z', title: 'Fix', body: 'Fixes #12' },
    ];
    assert.equal(transitions.selectMergedClosingPr(pulls, 12)?.number, 100);
    assert.equal(transitions.selectMergedClosingPr(pulls, '12')?.number, 100);
    assert.equal(transitions.selectMergedClosingPr([{ number: 9, merged_at: null }], 12), null);
  });

  test(`${surface}: serialized false handoff status cannot authorize matching closure proof`, () => {
    const issue = {
      issueState: 'closed',
      hasVerify: true,
      closure: { id: 3001, sourcePr: 2454 },
      verifyHandoff: { closureId: 3001, sourcePr: 2454 },
    };
    // Workflow callers supply environment strings. Even matching identities do
    // not prove success when the handoff flag is false or absent.
    for (const verifyHandoffBound of [false, 'false', ' FALSE ', '', undefined, null]) {
      const result = transitions.determineNextStep({ ...issue, verifyHandoffBound });
      assert.equal(result.currentState, STATES.CLOSED_NEEDS_VERIFY, String(verifyHandoffBound));
      assert.equal(result.nextStep, NEXT_STEPS.VERIFY, String(verifyHandoffBound));
    }
    for (const verifyHandoffBound of [true, 'true', ' TRUE ']) {
      const result = transitions.determineNextStep({ ...issue, verifyHandoffBound });
      assert.equal(result.currentState, STATES.CLOSED_VERIFIED, String(verifyHandoffBound));
      assert.equal(result.nextStep, NEXT_STEPS.DONE, String(verifyHandoffBound));
    }
  });

  test(`${surface}: matching invalid handoff identities cannot authorize completion`, () => {
    const issue = {
      issueState: 'closed',
      hasVerify: true,
      verifyHandoffBound: true,
      closure: { id: 3001, sourcePr: 2454 },
      verifyHandoff: { closureId: 3001, sourcePr: 2454 },
    };
    for (const [closureKey, handoffKey] of [['id', 'closureId'], ['sourcePr', 'sourcePr']]) {
      for (const value of [
        undefined, null, '', 0, '0', -1, '-1', 1.5, '1.5', '1e3', 'not-an-id',
        true, [], [3001], {}, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1,
      ]) {
        // Equality alone is insufficient: neither record proves a real identity.
        const result = transitions.determineNextStep({
          ...issue,
          closure: { ...issue.closure, [closureKey]: value },
          verifyHandoff: { ...issue.verifyHandoff, [handoffKey]: value },
        });
        assert.equal(result.currentState, STATES.CLOSED_NEEDS_VERIFY, `${closureKey}=${value}`);
        assert.equal(result.nextStep, NEXT_STEPS.VERIFY, `${closureKey}=${value}`);
      }
    }
  });

  test(`${surface}: reopening requires fresh proof even when the same PR closes the issue again`, () => {
    let issue = {
      issueState: 'closed',
      hasVerify: true,
      verifyHandoffBound: true,
      closure: { id: '3001', sourcePr: '2454' },
      verifyHandoff: { closureId: '3001', sourcePr: '2454' },
    };
    // Redispatch after verify forces done at the workflow boundary. This helper
    // check is the unforced re-evaluation that still requires fresh proof.
    const next = () => transitions.determineNextStep({ ...issue, forceStep: 'auto' });
    assert.equal(next().nextStep, NEXT_STEPS.DONE);

    // Reopening leaves both legacy labels and the recorded handoff in place.
    issue = { ...issue, issueState: 'open' };
    assert.equal(next().currentState, STATES.NEEDS_FORMAT);
    assert.equal(next().nextStep, NEXT_STEPS.FORMAT);

    // The PR number is unchanged, but a later closure is a new verification target.
    issue = { ...issue, issueState: 'closed', closure: { id: '3002', sourcePr: '2454' } };
    assert.equal(next().currentState, STATES.CLOSED_NEEDS_VERIFY);
    assert.equal(next().nextStep, NEXT_STEPS.VERIFY);

    issue = { ...issue, verifyHandoff: { closureId: '3002', sourcePr: '2454' } };
    assert.equal(next().currentState, STATES.CLOSED_VERIFIED);
    assert.equal(next().nextStep, NEXT_STEPS.DONE);

    // A matching closure alone also cannot authorize a different source PR.
    issue = { ...issue, verifyHandoff: { closureId: '3002', sourcePr: '2455' } };
    assert.equal(next().nextStep, NEXT_STEPS.VERIFY);
  });

  test(`${surface}: legacy verify:evaluate reaches done after a current PR handoff`, () => {
    const issue = {
      issueState: 'closed',
      hasVerify: true,
      verifyHandoffBound: false,
      closure: { id: 2001, sourcePr: 2454 },
    };
    const initial = transitions.determineNextStep(issue);
    assert.equal(initial.nextStep, NEXT_STEPS.VERIFY);

    // Adding the handoff label alone must not turn legacy tracking into proof.
    const labeled = { ...issue, verifyHandoffBound: true };
    assert.equal(transitions.determineNextStep(labeled).nextStep, NEXT_STEPS.VERIFY);

    // Matching closure identity completes on the next unforced evaluation.
    // The workflow separately redispatches verify to done, which Report - Done
    // accepts only after re-checking that same identity.
    const handedOff = {
      ...labeled,
      verifyHandoff: { closureId: 2001, sourcePr: 2454 },
    };
    const completed = transitions.determineNextStep(handedOff);
    assert.equal(completed.forced, false);
    assert.equal(completed.currentState, STATES.CLOSED_VERIFIED);
    assert.equal(completed.nextStep, NEXT_STEPS.DONE);
    assert.equal(transitions.redispatchForceStep(initial.nextStep), NEXT_STEPS.DONE);
  });

  test(`${surface}: failed or stale legacy handoffs stay retryable until fresh proof exists`, () => {
    const issue = {
      issueState: 'closed',
      hasVerify: true,
      verifyHandoffBound: false,
      closure: { id: 2002, sourcePr: 2455 },
      verifyHandoff: { closureId: 2001, sourcePr: 2454 },
    };
    const next = (event) => transitions.determineNextStep(event).nextStep;

    assert.equal(transitions.redispatchForceStep(NEXT_STEPS.VERIFY), NEXT_STEPS.DONE);
    assert.equal(next(issue), NEXT_STEPS.VERIFY);
    assert.equal(next({ ...issue, verifyHandoffBound: true }), NEXT_STEPS.VERIFY);

    const freshProof = { ...issue, verifyHandoff: { closureId: 2002, sourcePr: 2455 } };
    assert.equal(next(freshProof), NEXT_STEPS.VERIFY);
    assert.equal(next({ ...freshProof, verifyHandoffBound: true }), NEXT_STEPS.DONE);
  });
}

for (const [surface, root] of [
  ['source', path.resolve(__dirname, '../../..')],
  ['consumer template', path.resolve(__dirname, '../../../templates/consumer-repo')],
]) {
  test(`${surface} done report: handoff status controls completion and label cleanup`, (t) => {
    const workflow = fs.readFileSync(
      path.join(root, '.github/workflows/agents-auto-pilot.yml'),
      'utf8',
    );
    const reportStep = workflow.split('      - name: Report - Done\n')[1]
      ?.split('      - name: Expose format pause wakeup flag\n')[0];
    const script = reportStep?.split('          script: |\n')[1];
    assert.ok(script, 'workflow must define the completion reporter');

    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-pilot-report-'));
    t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
    const stubDir = path.join(temp, '.github/scripts');
    fs.mkdirSync(stubDir, { recursive: true });
    fs.writeFileSync(path.join(stubDir, 'github-api-with-retry.js'), `
      exports.createTokenAwareRetry = async ({ github }) => ({
        withRetry: async (operation) => operation(github),
      });
    `);
    const scriptPath = path.join(temp, 'report.cjs');
    const outputPath = path.join(temp, 'result.json');
    const patchedScript = script
      .replace(/^ {12}/gm, '')
      .replace(
        /require\('\.\/\.github\/scripts\/auto_pilot_transitions\.js'\)/g,
        `require(${JSON.stringify(path.join(root, '.github/scripts/auto_pilot_transitions.js'))})`,
      )
      .replace(
        /require\('\.\/\.github\/scripts\/github-api-with-retry\.js'\)/g,
        `require(${JSON.stringify(path.join(stubDir, 'github-api-with-retry.js'))})`,
      );
    fs.writeFileSync(scriptPath, `
      const calls = [];
      const failures = [];
      const context = { repo: { owner: 'stranske', repo: 'Workflows' } };
      const core = {
        info() {},
        warning() {},
        setFailed(message) { failures.push(message); },
      };
      const github = { rest: { issues: {
        async createComment(params) { calls.push({ action: 'comment', ...params }); },
        async removeLabel(params) { calls.push({ action: 'remove', ...params }); },
      } } };
      async function report() {
        ${patchedScript}
      }
      report().then(() => require('node:fs').writeFileSync(
        process.env.RESULT_PATH, JSON.stringify({ calls, failures }),
      ))
        .catch((error) => { console.error(error); process.exitCode = 1; });
    `);

    const run = (bound, handoff, identity = {}) => {
      const child = spawnSync(process.execPath, [scriptPath], {
        cwd: temp,
        env: {
          ISSUE_NUMBER: '42',
          VERIFY_HANDOFF_BOUND: bound,
          VERIFY_HANDOFF: handoff,
          CLOSURE_ID: identity.closureId ?? '',
          CLOSURE_SOURCE_PR: identity.sourcePr ?? '',
          VERIFY_HANDOFF_CLOSURE_ID: identity.handoffClosureId ?? '',
          VERIFY_HANDOFF_SOURCE_PR: identity.handoffSourcePr ?? '',
          RESULT_PATH: outputPath,
        },
        stdio: 'inherit',
        timeout: 10_000,
      });
      assert.ifError(child.error);
      assert.equal(child.status, 0, 'workflow reporter must execute successfully');
      return JSON.parse(fs.readFileSync(outputPath, 'utf8'));
    };

    for (const handoff of ['', 'absent', 'incomplete']) {
      const result = run('false', handoff);
      assert.equal(result.failures.length, 1, handoff);
      assert.match(result.failures[0], /verification handoff missing or stale/);
      assert.equal(result.calls.length, 1, 'missing handoff must retain auto-pilot');
      assert.equal(result.calls[0].action, 'comment');
      assert.equal(result.calls[0].issue_number, 42);
      assert.match(result.calls[0].body, /agents:auto-pilot.*remains for retry/);
      assert.doesNotMatch(result.calls[0].body, /Auto-Pilot Complete/);
    }

    const stale = run('true', 'found', {
      closureId: '1002',
      sourcePr: '2455',
      handoffClosureId: '1001',
      handoffSourcePr: '2454',
    });
    assert.equal(stale.failures.length, 1);
    assert.match(stale.failures[0], /stale/);
    assert.equal(stale.calls.length, 1);

    const result = run('true', 'found', {
      closureId: '1001',
      sourcePr: '2454',
      handoffClosureId: '1001',
      handoffSourcePr: '2454',
    });
    assert.deepEqual(result.failures, []);
    assert.deepEqual(result.calls.map(({ action }) => action), ['remove', 'comment']);
    assert.equal(result.calls[0].name, 'agents:auto-pilot');
    for (const call of result.calls) {
      assert.equal(call.issue_number, 42);
      assert.equal(call.owner, 'stranske');
      assert.equal(call.repo, 'Workflows');
    }
    assert.match(result.calls[1].body, /Auto-Pilot Complete/);
    assert.match(result.calls[1].body, /verification triggered on a merged source PR/);
  });

  test(`${surface} workflow caller: retained handoff labels cannot complete a new closure`, (t) => {
    const workflow = fs.readFileSync(
      path.join(root, '.github/workflows/agents-auto-pilot.yml'),
      'utf8',
    );
    const nextStep = workflow.split('      - name: Determine next step\n')[1]
      ?.split('      - name: Metrics - Start format timer\n')[0];
    assert.ok(nextStep, 'workflow must define the next-step caller');
    const scripts = [...nextStep.matchAll(/node - <<'NODE'[^\n]*\n([\s\S]*?)^\s*NODE\s*$/gm)];
    assert.equal(scripts.length, 3, 'expected forced, PR lookup, and automatic callers');

    // Execute the actual automatic caller with its label-derived inputs. Testing
    // a fabricated closure object alone does not cover the production boundary.
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-pilot-caller-'));
    t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
    const scriptPath = path.join(temp, 'next-step.cjs');
    const outputPath = path.join(temp, 'outputs');
    const statePath = path.join(temp, 'keepalive-state');
    fs.writeFileSync(scriptPath, scripts.at(-1)[1].replace(/^ {10}/gm, ''));
    fs.writeFileSync(statePath, '<!-- keepalive-state:v1 {"last_action":"continue"} -->');

    const run = (issueState, linkedPr, handoffBound, identity = {}) => {
      fs.writeFileSync(outputPath, '');
      const child = spawnSync(process.execPath, [scriptPath], {
        // No API access or inherited authentication is needed by this caller.
        env: {
          WORKFLOWS_SCRIPTS_PATH: root,
          GITHUB_OUTPUT: outputPath,
          ISSUE_STATE: issueState,
          LINKED_PR: String(linkedPr),
          HAS_VERIFY: 'true',
          VERIFY_HANDOFF_BOUND: String(handoffBound),
          CLOSURE_ID: identity.closureId ?? '',
          CLOSURE_SOURCE_PR: identity.sourcePr ?? '',
          VERIFY_HANDOFF_CLOSURE_ID: identity.handoffClosureId ?? '',
          VERIFY_HANDOFF_SOURCE_PR: identity.handoffSourcePr ?? '',
          PR_STATE_FILE: statePath,
          PR_STATE_FETCH_FAILED: 'false',
        },
        stdio: 'inherit',
        timeout: 10_000,
      });
      assert.ifError(child.error);
      assert.equal(child.status, 0, 'workflow caller must execute successfully');
      return fs.readFileSync(outputPath, 'utf8').trim();
    };

    const matching = {
      closureId: '1001',
      sourcePr: '2454',
      handoffClosureId: '1001',
      handoffSourcePr: '2454',
    };
    assert.equal(run('closed', 2454, true, matching), 'next_step=done');
    assert.equal(run('closed', 2454, true), 'next_step=verify');
    assert.equal(run('open', 2454, true, matching), 'next_step=monitor-pr');
    assert.equal(run('closed', 2455, true, {
      ...matching,
      closureId: '1002',
      sourcePr: '2455',
    }), 'next_step=verify');
    // Legacy verify:evaluate also stays pending without a current PR-bound handoff.
    assert.equal(run('closed', 2455, false), 'next_step=verify');
  });

  test(`${surface} workflow: admits verify:pr-handoff label events with auto-pilot`, () => {
    const workflow = fs.readFileSync(
      path.join(root, '.github/workflows/agents-auto-pilot.yml'),
      'utf8',
    );
    assert.match(
      workflow,
      /label\.name == 'verify:pr-handoff'[\s\S]*contains\(issue\.labels\[\]\.name, 'agents:auto-pilot'\)/,
    );
  });

  test(`${surface} workflow: redispatches after successful verify handoff`, () => {
    const workflow = fs.readFileSync(
      path.join(root, '.github/workflows/agents-auto-pilot.yml'),
      'utf8',
    );
    const redispatch = workflow.split('      - name: Re-dispatch for next step\n')[1]
      ?.split('      - name: Report - Done\n')[0];
    assert.ok(redispatch, 'workflow must define verify continuation redispatch');
    assert.match(redispatch, /steps\.next\.outputs\.next_step == 'verify'/);
    assert.match(redispatch, /steps\.verify_step\.outputs\.verify_handoff == 'found'/);
  });
}
