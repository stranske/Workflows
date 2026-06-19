'use strict';

const RUNTIME_AC_REQUIRED_LABELS = new Set([
  'runtime-ac',
  'runtime-verification',
  'acceptance-criteria',
  'verification-spec',
  'verification-plan',
  'ac-checks',
  'runtime-checks',
]);

function labelName(label) {
  if (typeof label === 'string') {
    return label;
  }
  if (label && typeof label.name === 'string') {
    return label.name;
  }
  return '';
}

function normalizeLabelName(label) {
  return labelName(label).trim().toLowerCase();
}

function runtimeAcRequirement(labels = []) {
  const matched = [];
  const seen = new Set();

  for (const label of labels || []) {
    const normalized = normalizeLabelName(label);
    if (!normalized) {
      continue;
    }
    const colonIndex = normalized.indexOf(':');
    const suffix =
      colonIndex >= 0 && colonIndex < normalized.length - 1
        ? normalized.slice(colonIndex + 1).trim()
        : '';
    if (
      RUNTIME_AC_REQUIRED_LABELS.has(normalized) ||
      (suffix && RUNTIME_AC_REQUIRED_LABELS.has(suffix))
    ) {
      if (!seen.has(normalized)) {
        matched.push(normalized);
        seen.add(normalized);
      }
    }
  }

  return {
    required: matched.length > 0,
    labels: matched,
  };
}

function hasRuntimeAcRequirement(labels = []) {
  return runtimeAcRequirement(labels).required;
}

// Workflow callers should pass the withRetry function produced by createTokenAwareRetry.
async function fetchPullRequestLabels({ github, owner, repo, prNumber, withRetry }) {
  if (!github || !github.rest || !github.rest.issues) {
    throw new Error('GitHub client is required to evaluate runtime AC merge labels.');
  }
  const call = (client = github) =>
    client.rest.issues.listLabelsOnIssue({
      owner,
      repo,
      issue_number: prNumber,
      per_page: 100,
    });

  try {
    const response = withRetry ? await withRetry(call) : await call();
    return Array.isArray(response && response.data) ? response.data : [];
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(
      `Unable to evaluate runtime AC merge labels for PR #${prNumber}: ${message}`,
    );
  }
}

async function assertRuntimeAcMergeAllowed({
  github,
  core,
  owner,
  repo,
  prNumber,
  labels,
  withRetry,
  source = 'external merge lane',
} = {}) {
  if (!owner || !repo || !prNumber) {
    throw new Error('owner, repo, and prNumber are required for runtime AC merge guard.');
  }

  const labelItems = Array.isArray(labels)
    ? labels
    : await fetchPullRequestLabels({ github, owner, repo, prNumber, withRetry });
  const requirement = runtimeAcRequirement(labelItems);

  if (!requirement.required) {
    if (core && typeof core.info === 'function') {
      core.info(`Runtime AC merge guard passed for PR #${prNumber}.`);
    }
    return {
      allowed: true,
      labels: [],
    };
  }

  const labelList = requirement.labels.join(', ');
  const message =
    `Runtime AC merge guard blocked ${source} for PR #${prNumber}: ` +
    `label(s) ${labelList} require local Orchestrator runtime acceptance checks. ` +
    'Merge through Code/Orchestrator/merge_guard.py after the runtime AC spec passes.';

  if (core && typeof core.warning === 'function') {
    core.warning(message);
  }

  const error = new Error(message);
  error.code = 'runtime_ac_merge_blocked';
  error.labels = requirement.labels;
  throw error;
}

module.exports = {
  RUNTIME_AC_REQUIRED_LABELS,
  assertRuntimeAcMergeAllowed,
  hasRuntimeAcRequirement,
  normalizeLabelName,
  runtimeAcRequirement,
};
