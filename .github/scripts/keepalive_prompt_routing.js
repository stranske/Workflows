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

const FEATURE_SCENARIOS = new Set([
  'feature',
  'feature-work',
  'feature_work',
  'task',
  'next-task',
  'next_task',
  'nexttask',
]);

const FIX_MODES = new Set(['fix', 'fix-ci', 'fix_ci', 'ci', 'ci-failure']);
const VERIFY_MODES = new Set(['verify', 'verification', 'verify-acceptance', 'acceptance']);

function resolvePromptMode({ scenario, mode, action, reason } = {}) {
  const modeValue = normalise(mode);
  if (modeValue) {
    if (FIX_MODES.has(modeValue)) {
      return 'fix_ci';
    }
    if (VERIFY_MODES.has(modeValue)) {
      return 'verify';
    }
  }

  const actionValue = normalise(action);
  const reasonValue = normalise(reason);
  if (actionValue === 'fix' || reasonValue.startsWith('fix-')) {
    return 'fix_ci';
  }
  if (actionValue === 'verify' || reasonValue === 'verify-acceptance') {
    return 'verify';
  }

  const scenarioValue = normalise(scenario);
  if (scenarioValue) {
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
