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
  assert.match(TRANSITION_CONTRACT.guards.join('\n'), /verify:evaluate/);
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
