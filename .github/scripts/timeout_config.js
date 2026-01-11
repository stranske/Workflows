'use strict';

function normalise(value) {
  return String(value ?? '').trim();
}

function parseNumber(value, fallback, { min = Number.NEGATIVE_INFINITY, max = Number.POSITIVE_INFINITY } = {}) {
  const candidate = Number(normalise(value));
  if (!Number.isFinite(candidate)) {
    return fallback;
  }
  if (candidate < min || candidate > max) {
    return fallback;
  }
  return candidate;
}

function parseOptionalNumber(value, { min = Number.NEGATIVE_INFINITY, max = Number.POSITIVE_INFINITY } = {}) {
  const candidate = Number(normalise(value));
  if (!Number.isFinite(candidate)) {
    return null;
  }
  if (candidate < min || candidate > max) {
    return null;
  }
  return candidate;
}

function resolveOverrideInput(inputs = {}, env = {}) {
  return (
    inputs.timeout_minutes ??
    inputs.timeoutMinutes ??
    inputs.timeout_override_minutes ??
    inputs.timeoutOverrideMinutes ??
    inputs.workflow_timeout_minutes ??
    inputs.workflowTimeoutMinutes ??
    env.WORKFLOW_TIMEOUT_OVERRIDE ??
    env.WORKFLOW_TIMEOUT_MINUTES ??
    env.TIMEOUT_MINUTES
  );
}

function parseTimeoutConfig({
  env = process.env,
  inputs = {},
  defaultMinutes = 45,
  extendedMultiplier = 2,
  minMinutes = 1,
  maxMinutes = 24 * 60,
} = {}) {
  const defaultValue = parseNumber(env.WORKFLOW_TIMEOUT_DEFAULT, defaultMinutes, {
    min: minMinutes,
    max: maxMinutes,
  });
  const extendedFallback = defaultValue * extendedMultiplier;
  const extendedValue = parseNumber(env.WORKFLOW_TIMEOUT_EXTENDED, extendedFallback, {
    min: minMinutes,
    max: maxMinutes,
  });
  const overrideValue = parseOptionalNumber(resolveOverrideInput(inputs, env), {
    min: minMinutes,
    max: maxMinutes,
  });
  const resolvedMinutes = overrideValue ?? defaultValue;
  const source = overrideValue !== null ? 'override' : 'default';

  return {
    defaultMinutes: defaultValue,
    extendedMinutes: extendedValue,
    overrideMinutes: overrideValue,
    resolvedMinutes,
    source,
  };
}

module.exports = {
  parseTimeoutConfig,
};
