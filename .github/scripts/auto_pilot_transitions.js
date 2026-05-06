'use strict';

const STATES = Object.freeze({
  CLOSED_VERIFIED: 'closed-verified',
  CLOSED_NEEDS_VERIFY: 'closed-needs-verify',
  NEEDS_FORMAT: 'needs-format',
  NEEDS_OPTIMIZE: 'needs-optimize',
  NEEDS_APPLY: 'needs-apply',
  NEEDS_CAPABILITY_CHECK: 'needs-capability-check',
  NEEDS_CREATE_PR: 'needs-create-pr',
  PR_MONITORING: 'pr-monitoring',
  PR_TASKS_COMPLETE: 'pr-tasks-complete',
});

const NEXT_STEPS = Object.freeze({
  DONE: 'done',
  VERIFY: 'verify',
  FORMAT: 'format',
  OPTIMIZE: 'optimize',
  APPLY: 'apply',
  CAPABILITY_CHECK: 'capability-check',
  CREATE_PR: 'create-pr',
  MONITOR_PR: 'monitor-pr',
  CHECK_COMPLETION: 'check-completion',
});

const FORCED_STEPS = Object.freeze([
  NEXT_STEPS.FORMAT,
  NEXT_STEPS.OPTIMIZE,
  NEXT_STEPS.APPLY,
  NEXT_STEPS.CAPABILITY_CHECK,
  'agent',
  NEXT_STEPS.VERIFY,
  NEXT_STEPS.CREATE_PR,
  NEXT_STEPS.MONITOR_PR,
  NEXT_STEPS.CHECK_COMPLETION,
  NEXT_STEPS.DONE,
]);

const TRANSITION_CONTRACT = Object.freeze({
  states: STATES,
  nextSteps: NEXT_STEPS,
  guards: Object.freeze([
    'closed issues require verify:evaluate before done',
    'format requires agents:formatted, not the old agents:format trigger label',
    'optimize advances only after an optimizer suggestions comment exists',
    'apply advances only after agents:apply-suggestions is present',
    'create-pr advances only after a routing agent:* label is present',
    'linked PRs advance to check-completion only when keepalive state marks tasks complete',
  ]),
  transitions: Object.freeze({
    [STATES.CLOSED_VERIFIED]: NEXT_STEPS.DONE,
    [STATES.CLOSED_NEEDS_VERIFY]: NEXT_STEPS.VERIFY,
    [STATES.NEEDS_FORMAT]: NEXT_STEPS.FORMAT,
    [STATES.NEEDS_OPTIMIZE]: NEXT_STEPS.OPTIMIZE,
    [STATES.NEEDS_APPLY]: NEXT_STEPS.APPLY,
    [STATES.NEEDS_CAPABILITY_CHECK]: NEXT_STEPS.CAPABILITY_CHECK,
    [STATES.NEEDS_CREATE_PR]: NEXT_STEPS.CREATE_PR,
    [STATES.PR_MONITORING]: NEXT_STEPS.MONITOR_PR,
    [STATES.PR_TASKS_COMPLETE]: NEXT_STEPS.CHECK_COMPLETION,
  }),
});

function normalizeBoolean(value) {
  if (typeof value === 'boolean') {
    return value;
  }
  return String(value ?? '').trim().toLowerCase() === 'true';
}

function normalizeText(value) {
  return String(value ?? '').trim();
}

function hasLinkedPr(value) {
  return normalizeText(value) !== '';
}

function normalizeForceStep(forceStep) {
  const step = normalizeText(forceStep);
  if (!step || step === 'auto') {
    return '';
  }
  if (!FORCED_STEPS.includes(step)) {
    throw new Error(`Invalid auto-pilot force step: ${step}`);
  }
  return step;
}

function isKeepaliveTasksComplete(body) {
  const text = String(body ?? '');
  return text.includes('"last_action":"stop"') &&
    text.includes('"last_reason":"tasks-complete"');
}

function resolveCurrentState(event = {}) {
  const issueState = normalizeText(event.issueState).toLowerCase();
  const linkedPr = hasLinkedPr(event.linkedPr);

  if (issueState === 'closed') {
    return normalizeBoolean(event.hasVerify)
      ? STATES.CLOSED_VERIFIED
      : STATES.CLOSED_NEEDS_VERIFY;
  }

  if (!linkedPr) {
    if (!normalizeBoolean(event.hasFormat)) {
      return STATES.NEEDS_FORMAT;
    }
    if (!normalizeBoolean(event.hasOptimizerOutput)) {
      return STATES.NEEDS_OPTIMIZE;
    }
    if (!normalizeBoolean(event.hasApply)) {
      return STATES.NEEDS_APPLY;
    }
    if (!normalizeBoolean(event.hasAgent)) {
      return STATES.NEEDS_CAPABILITY_CHECK;
    }
    return STATES.NEEDS_CREATE_PR;
  }

  if (event.prStateFetchFailed || !normalizeText(event.keepaliveState)) {
    return STATES.PR_MONITORING;
  }

  return isKeepaliveTasksComplete(event.keepaliveState)
    ? STATES.PR_TASKS_COMPLETE
    : STATES.PR_MONITORING;
}

function transition(currentState, event = {}) {
  const state = normalizeText(currentState);
  const nextStep = TRANSITION_CONTRACT.transitions[state];
  if (!nextStep) {
    throw new Error(`Invalid auto-pilot state transition: ${state || '<empty>'}`);
  }
  return nextStep;
}

function messageFor({ currentState, nextStep, event = {}, forced = false }) {
  if (forced) {
    return `Forced step: ${nextStep}`;
  }
  if (event.prStateFetchFailed) {
    return 'Warning: Failed to fetch PR state, defaulting to monitor-pr';
  }
  if (hasLinkedPr(event.linkedPr) && !normalizeText(event.keepaliveState)) {
    return 'No keepalive state found, defaulting to monitor-pr';
  }
  switch (currentState) {
    case STATES.CLOSED_VERIFIED:
      return 'Issue closed with verification - auto-pilot complete';
    case STATES.CLOSED_NEEDS_VERIFY:
      return 'Issue closed - triggering verification';
    case STATES.NEEDS_FORMAT:
      return 'Step 1: Format issue';
    case STATES.NEEDS_OPTIMIZE:
      return 'Step 2: Run optimizer (inline)';
    case STATES.NEEDS_APPLY:
      return 'Step 3: Apply suggestions';
    case STATES.NEEDS_CAPABILITY_CHECK:
      return 'Step 4: Run capability check and assign agent';
    case STATES.NEEDS_CREATE_PR:
      return 'Step 5: All prep complete, checking for branch to create PR';
    case STATES.PR_TASKS_COMPLETE:
      return 'Step 6.5: PR tasks complete - checking for merge';
    case STATES.PR_MONITORING:
      return `PR #${normalizeText(event.linkedPr)} exists - monitoring via keepalive`;
    default:
      return `Next step: ${nextStep}`;
  }
}

function determineNextStep(event = {}) {
  const forcedStep = normalizeForceStep(event.forceStep);
  if (forcedStep) {
    return {
      currentState: 'forced',
      forced: true,
      nextStep: forcedStep,
      message: messageFor({ nextStep: forcedStep, forced: true }),
    };
  }

  const currentState = resolveCurrentState(event);
  const nextStep = transition(currentState, event);
  return {
    currentState,
    forced: false,
    nextStep,
    message: messageFor({ currentState, nextStep, event }),
  };
}

function redispatchForceStep(currentStep) {
  const step = normalizeText(currentStep);
  const nextStepMap = {
    [NEXT_STEPS.FORMAT]: NEXT_STEPS.OPTIMIZE,
    [NEXT_STEPS.OPTIMIZE]: NEXT_STEPS.APPLY,
    [NEXT_STEPS.APPLY]: NEXT_STEPS.CAPABILITY_CHECK,
    [NEXT_STEPS.CAPABILITY_CHECK]: 'auto',
    [NEXT_STEPS.CREATE_PR]: 'auto',
    [NEXT_STEPS.MONITOR_PR]: 'auto',
  };
  return nextStepMap[step] || 'auto';
}

module.exports = {
  STATES,
  NEXT_STEPS,
  FORCED_STEPS,
  TRANSITION_CONTRACT,
  determineNextStep,
  hasLinkedPr,
  isKeepaliveTasksComplete,
  normalizeForceStep,
  redispatchForceStep,
  resolveCurrentState,
  transition,
};
