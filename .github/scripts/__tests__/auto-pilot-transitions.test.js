'use strict';

const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const {
  FORCED_STEPS,
  NEXT_STEPS,
  STATES,
  TRANSITION_CONTRACT,
  determineNextStep,
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
  assert.equal(redispatchForceStep('verify'), 'auto');
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

    // Exercise the helper's redispatch contract, without claiming the workflow
    // schedules it: that requires its protected stage allowlist to admit verify.
    const handedOff = {
      ...labeled,
      verifyHandoff: { closureId: 2001, sourcePr: 2454 },
    };
    const continuation = {
      ...handedOff,
      forceStep: transitions.redispatchForceStep(initial.nextStep),
    };
    const completed = transitions.determineNextStep(continuation);
    assert.equal(completed.forced, false);
    assert.equal(completed.currentState, STATES.CLOSED_VERIFIED);
    assert.equal(completed.nextStep, NEXT_STEPS.DONE);
    assert.equal(transitions.determineNextStep(continuation).nextStep, NEXT_STEPS.DONE);
  });

  test(`${surface}: failed or stale legacy handoffs stay retryable until fresh proof exists`, () => {
    const issue = {
      issueState: 'closed',
      hasVerify: true,
      verifyHandoffBound: false,
      closure: { id: 2002, sourcePr: 2455 },
      verifyHandoff: { closureId: 2001, sourcePr: 2454 },
    };
    const forceStep = transitions.redispatchForceStep(NEXT_STEPS.VERIFY);
    const next = (event) => transitions.determineNextStep({ ...event, forceStep }).nextStep;

    assert.equal(next(issue), NEXT_STEPS.VERIFY);
    assert.equal(next({ ...issue, verifyHandoffBound: true }), NEXT_STEPS.VERIFY);

    const freshProof = { ...issue, verifyHandoff: { closureId: 2002, sourcePr: 2455 } };
    assert.equal(next(freshProof), NEXT_STEPS.VERIFY);
    assert.equal(next({ ...freshProof, verifyHandoffBound: true }), NEXT_STEPS.DONE);
  });
}
