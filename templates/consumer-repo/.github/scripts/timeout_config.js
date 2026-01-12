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

function normaliseLabels(value) {
  if (Array.isArray(value)) {
    return value.map((label) => normalise(label).toLowerCase()).filter(Boolean);
  }
  if (value === undefined || value === null) {
    return [];
  }
  return normalise(value)
    .toLowerCase()
    .split(',')
    .map((label) => label.trim())
    .filter(Boolean);
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

function resolveEnvValue(env, variables, key) {
  const envValue = normalise(env?.[key]);
  if (envValue) {
    return envValue;
  }
  const variableValue = normalise(variables?.[key]);
  if (variableValue) {
    return variableValue;
  }
  return '';
}

function parseTimeoutConfig({
  env = process.env,
  inputs = {},
  labels,
  variables = {},
  defaultMinutes = 45,
  extendedMultiplier = 2,
  minMinutes = 1,
  maxMinutes = 24 * 60,
} = {}) {
  const defaultValue = parseNumber(
    resolveEnvValue(env, variables, 'WORKFLOW_TIMEOUT_DEFAULT'),
    defaultMinutes,
    {
      min: minMinutes,
      max: maxMinutes,
    }
  );
  const extendedFallback = defaultValue * extendedMultiplier;
  const extendedValue = parseNumber(
    resolveEnvValue(env, variables, 'WORKFLOW_TIMEOUT_EXTENDED'),
    extendedFallback,
    {
      min: minMinutes,
      max: maxMinutes,
    }
  );
  const resolvedLabels = normaliseLabels(
    labels ??
      inputs.timeout_labels ??
      inputs.timeoutLabels ??
      inputs.labels ??
      env.WORKFLOW_TIMEOUT_LABELS ??
      env.WORKFLOW_LABELS ??
      variables.WORKFLOW_TIMEOUT_LABELS ??
      variables.WORKFLOW_LABELS
  );
  const extendedLabel = 'timeout:extended';
  const hasExtendedLabel = resolvedLabels.includes(extendedLabel);
  const labelMinutes = hasExtendedLabel ? extendedValue : null;
  const overrideValue = parseOptionalNumber(resolveOverrideInput(inputs, env), {
    min: minMinutes,
    max: maxMinutes,
  });
  const resolvedMinutes = overrideValue ?? labelMinutes ?? defaultValue;
  const source = overrideValue !== null ? 'override' : labelMinutes !== null ? 'label' : 'default';

  return {
    defaultMinutes: defaultValue,
    extendedMinutes: extendedValue,
    overrideMinutes: overrideValue,
    label: hasExtendedLabel ? extendedLabel : null,
    labelMinutes,
    resolvedMinutes,
    source,
  };
}

module.exports = {
  parseTimeoutConfig,
};
