'use strict';

const { parseStateComment } = require('./keepalive_state.js');

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
    'closed issues require a PR-bound verify handoff matching the current closure before done',
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
  if (step === 'agent') {
    return NEXT_STEPS.CAPABILITY_CHECK;
  }
  if (!FORCED_STEPS.includes(step)) {
    throw new Error(`Invalid auto-pilot force step: ${step}`);
  }
  return step;
}

const VERIFY_HANDOFF_MARKER_LINE = new RegExp(
  '^<!--\\s*auto-pilot-verify-handoff:v1\\s+(\\{[^]*\\})\\s*-->$',
);

function lineOutsideStructuralContext(line, { inFence, fenceDelim }) {
  const t = String(line ?? '');
  const trimmed = t.trim();
  if (!trimmed) {
    return { inFence, fenceDelim, usable: false };
  }
  if (inFence) {
    if (fenceDelim && trimmed === fenceDelim) {
      return { inFence: false, fenceDelim: '', usable: false };
    }
    return { inFence, fenceDelim, usable: false };
  }
  if (/^(`{3,}|~{3,})/.test(trimmed)) {
    const delim = trimmed.match(/^(`{3,}|~{3,})/)[0];
    return { inFence: true, fenceDelim: delim, usable: false };
  }
  if (trimmed.startsWith('>')) {
    return { inFence, fenceDelim, usable: false };
  }
  return { inFence, fenceDelim, usable: true };
}

function findStandaloneVerifyHandoffMarkerLine(body) {
  const text = String(body ?? '');
  let inFence = false;
  let fenceDelim = '';
  const lines = text.split(/\r?\n/);
  let latestMatch = null;
  for (let i = 0; i < lines.length; i += 1) {
    const ctx = lineOutsideStructuralContext(lines[i], { inFence, fenceDelim });
    inFence = ctx.inFence;
    fenceDelim = ctx.fenceDelim;
    if (!ctx.usable) {
      continue;
    }
    const trimmed = lines[i].trim();
    const match = trimmed.match(VERIFY_HANDOFF_MARKER_LINE);
    if (match) {
      latestMatch = match[1];
    }
  }
  return latestMatch;
}

function isKeepaliveTasksComplete(body) {
  const text = String(body ?? '');
  let inFence = false;
  let fenceDelim = '';
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const ctx = lineOutsideStructuralContext(lines[i], { inFence, fenceDelim });
    inFence = ctx.inFence;
    fenceDelim = ctx.fenceDelim;
    if (!ctx.usable) {
      continue;
    }
    const trimmed = lines[i].trim();
    const parsed = parseStateComment(trimmed);
    if (!parsed || !parsed.data || typeof parsed.data !== 'object') {
      continue;
    }
    const data = parsed.data;
    if (data.last_action === 'stop' && data.last_reason === 'tasks-complete') {
      return true;
    }
  }
  return false;
}

function hasCurrentVerifyHandoff(event) {
  // A label is only a signal. The workflow must supply the current closure
  // from the issue timeline and the identity recorded after the PR handoff.
  // Closure event IDs change even when the same PR closes a reopened issue.
  const closure = event.closure;
  const handoff = event.verifyHandoff;
  const isId = (value) =>
    (typeof value === 'string' || Number.isSafeInteger(value)) &&
    /^[1-9]\d*$/.test(normalizeText(value));
  return normalizeBoolean(event.verifyHandoffBound) &&
    isId(closure?.id) &&
    isId(closure?.sourcePr) &&
    isId(handoff?.closureId) &&
    isId(handoff?.sourcePr) &&
    normalizeText(closure.id) === normalizeText(handoff.closureId) &&
    normalizeText(closure.sourcePr) === normalizeText(handoff.sourcePr);
}

function resolveCurrentState(event = {}) {
  const issueState = normalizeText(event.issueState).toLowerCase();
  const linkedPr = hasLinkedPr(event.linkedPr);

  if (issueState === 'closed') {
    // Label-only verify:pr-handoff cannot bypass verification. Completion
    // requires the persisted handoff identity to match the current closure.
    return hasCurrentVerifyHandoff(event)
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
    // Only dispatched after verify_step confirms a PR/head-bound handoff;
    // Report - Done re-validates that evidence before completing.
    [NEXT_STEPS.VERIFY]: NEXT_STEPS.DONE,
  };
  return nextStepMap[step] || 'auto';
}

const VERIFY_HANDOFF_MARKER_PREFIX = '<!-- auto-pilot-verify-handoff:v1 ';

// Same automation-owned writer class as keepalive state. Bot and user
// logins stay in separate sets so a non-bot account cannot satisfy a bot login.
const TRUSTED_VERIFY_HANDOFF_BOT_LOGINS = new Set([
  'agents-workflows-bot[bot]',
  'stranske-keepalive[bot]',
  'github-actions[bot]',
]);
const TRUSTED_VERIFY_HANDOFF_USER_LOGINS = new Set([
  'stranske',
  'stranske-automation-bot',
]);

function isPositiveId(value) {
  return (typeof value === 'string' || Number.isSafeInteger(value)) &&
    /^[1-9]\d*$/.test(normalizeText(value));
}

function normalizeHandoffIdentity(identity) {
  if (!identity || typeof identity !== 'object') {
    return null;
  }
  const closureId = identity.closureId ?? identity.id;
  const sourcePr = identity.sourcePr;
  if (!isPositiveId(closureId) || !isPositiveId(sourcePr)) {
    return null;
  }
  return {
    closureId: normalizeText(closureId),
    sourcePr: normalizeText(sourcePr),
  };
}

function formatVerifyHandoffMarker(identity) {
  const normalized = normalizeHandoffIdentity(identity);
  if (!normalized) {
    throw new Error('Invalid verify handoff identity for marker');
  }
  return `${VERIFY_HANDOFF_MARKER_PREFIX}${JSON.stringify(normalized)} -->`;
}

function parseVerifyHandoffMarker(text) {
  const jsonSlice = findStandaloneVerifyHandoffMarkerLine(text);
  if (!jsonSlice) {
    return null;
  }
  try {
    return normalizeHandoffIdentity(JSON.parse(jsonSlice));
  } catch {
    return null;
  }
}

function isTrustedVerifyHandoffAuthor(comment) {
  const type = normalizeText(comment?.user?.type).toLowerCase();
  const login = normalizeText(comment?.user?.login).toLowerCase();
  return (type === 'bot' && TRUSTED_VERIFY_HANDOFF_BOT_LOGINS.has(login))
    || (type === 'user' && TRUSTED_VERIFY_HANDOFF_USER_LOGINS.has(login));
}

function findLatestVerifyHandoff(comments) {
  const entries = Array.isArray(comments) ? [...comments].reverse() : [];
  for (const comment of entries) {
    // A marker is automation-owned state only when its author is in the
    // trusted writer class. Any other commenter is ignored.
    if (!isTrustedVerifyHandoffAuthor(comment)) {
      continue;
    }
    const parsed = parseVerifyHandoffMarker(comment?.body);
    if (parsed) {
      return parsed;
    }
  }
  return null;
}

function textReferencesIssue(text, issueNumber) {
  const num = normalizeText(issueNumber);
  if (!/^[1-9]\d*$/.test(num)) {
    return false;
  }
  const body = String(text ?? '');
  const meta = new RegExp(`meta:issue:${num}(?!\\d)`);
  const closing = new RegExp(
    `\\b(close[sd]?|fixe?[sd]?|resolve[sd]?)\\s+#${num}\\b`,
    'i',
  );
  return meta.test(body) || closing.test(body);
}

function selectMergedClosingPr(pulls, issueNumber) {
  const batch = Array.isArray(pulls) ? pulls : [];
  return batch.find((pr) =>
    Boolean(pr?.merged_at) && (
      textReferencesIssue(pr.body, issueNumber) ||
      textReferencesIssue(pr.title, issueNumber)
    )
  ) || null;
}

function findLatestClosureEvent(timelineEvents) {
  let latest = null;
  for (const entry of timelineEvents || []) {
    if (entry?.event === 'closed' && entry.id != null) {
      latest = entry;
    }
  }
  if (!latest) {
    return null;
  }
  return { id: latest.id };
}

function buildDetermineNextStepEventFromEnv(env = process.env) {
  const readId = (name) => {
    const value = normalizeText(env[name]);
    return isPositiveId(value) ? value : undefined;
  };
  const closureId = readId('CLOSURE_ID');
  const closureSourcePr = readId('CLOSURE_SOURCE_PR');
  const handoffClosureId = readId('VERIFY_HANDOFF_CLOSURE_ID');
  const handoffSourcePr = readId('VERIFY_HANDOFF_SOURCE_PR');
  const event = {
    issueState: env.ISSUE_STATE,
    hasFormat: env.HAS_FORMAT,
    hasOptimizerOutput: env.HAS_OPTIMIZER_OUTPUT,
    hasApply: env.HAS_APPLY,
    hasAgent: env.HAS_AGENT,
    linkedPr: env.LINKED_PR,
    hasVerify: env.HAS_VERIFY,
    verifyHandoffBound: env.VERIFY_HANDOFF_BOUND,
    keepaliveState: env.KEEPALIVE_STATE,
    prStateFetchFailed: env.PR_STATE_FETCH_FAILED === 'true',
    forceStep: env.FORCE_STEP,
  };
  if (closureId && closureSourcePr) {
    event.closure = { id: closureId, sourcePr: closureSourcePr };
  }
  if (handoffClosureId && handoffSourcePr) {
    event.verifyHandoff = { closureId: handoffClosureId, sourcePr: handoffSourcePr };
  }
  return event;
}

module.exports = {
  STATES,
  NEXT_STEPS,
  FORCED_STEPS,
  TRANSITION_CONTRACT,
  buildDetermineNextStepEventFromEnv,
  determineNextStep,
  findLatestClosureEvent,
  findLatestVerifyHandoff,
  formatVerifyHandoffMarker,
  selectMergedClosingPr,
  hasLinkedPr,
  isKeepaliveTasksComplete,
  normalizeForceStep,
  parseVerifyHandoffMarker,
  redispatchForceStep,
  resolveCurrentState,
  transition,
};
