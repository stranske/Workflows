'use strict';

function normalise(value) {
  return String(value ?? '').trim().toLowerCase();
}

const FIX_SCENARIOS = new Set([
  'ci',
  'ci-failure',
  'ci_failure',
  'fix',
  'fix-ci',
  'fix_ci',
  'fix-ci-failure',
]);

const VERIFY_SCENARIOS = new Set([
  'verify',
  'verification',
  'verify-acceptance',
  'acceptance',
]);

const CONFLICT_SCENARIOS = new Set([
  'conflict',
  'merge-conflict',
  'merge_conflict',
  'conflicts',
  'fix-conflict',
  'fix_conflict',
  'resolve-conflict',
  'resolve_conflict',
]);

const FEATURE_SCENARIOS = new Set([
  'feature',
  'feature-work',
  'feature_work',
  'task',
  'next-task',
  'next_task',
  'nexttask',
]);

const FIX_MODES = new Set(['fix', 'fix-ci', 'fix_ci', 'ci', 'ci-failure', 'ci_failure', 'fix-ci-failure']);
const VERIFY_MODES = new Set(['verify', 'verification', 'verify-acceptance', 'acceptance']);
const CONFLICT_MODES = new Set(['conflict', 'merge-conflict', 'merge_conflict', 'fix-conflict', 'fix_conflict']);

function resolvePromptMode({ scenario, mode, action, reason } = {}) {
  const modeValue = normalise(mode);
  if (modeValue) {
    // Conflict mode takes highest priority - merge conflicts block all other work
    if (CONFLICT_MODES.has(modeValue)) {
      return 'conflict';
    }
    if (FIX_MODES.has(modeValue)) {
      return 'fix_ci';
    }
    if (VERIFY_MODES.has(modeValue)) {
      return 'verify';
    }
  }

  const actionValue = normalise(action);
  const reasonValue = normalise(reason);
  
  // Check for conflict-related actions/reasons first
  if (actionValue === 'conflict' || reasonValue.startsWith('conflict') || reasonValue.includes('merge-conflict')) {
    return 'conflict';
  }
  if (actionValue === 'fix' || reasonValue.startsWith('fix-')) {
    return 'fix_ci';
  }
  if (actionValue === 'verify' || reasonValue === 'verify-acceptance') {
    return 'verify';
  }

  const scenarioValue = normalise(scenario);
  if (scenarioValue) {
    if (CONFLICT_SCENARIOS.has(scenarioValue)) {
      return 'conflict';
    }
    if (FIX_SCENARIOS.has(scenarioValue)) {
      return 'fix_ci';
    }
    if (VERIFY_SCENARIOS.has(scenarioValue)) {
      return 'verify';
    }
    if (FEATURE_SCENARIOS.has(scenarioValue)) {
      return 'normal';
    }
  }

  return 'normal';
}

module.exports = {
  resolvePromptMode,
};
