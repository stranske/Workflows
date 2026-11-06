'use strict';

const fs = require('fs');
const path = require('path');

const {
  mergeEligibility,
  parseDeliveryRecord,
} = require(path.resolve(
  __dirname,
  '../../scripts/sync_pr_lease_contract.js',
));

const STABLE_DELIVERY_BRANCHES = new Set([
  'sync/workflows-candidate',
  'sync/workflows-delivery',
]);

function clean(value) {
  return String(value || '').trim();
}

function evaluateDeliverySeal(event = {}, repository = '', now = new Date().toISOString()) {
  const pullRequest = event.pull_request;
  const headRef = clean(pullRequest?.head?.ref);
  if (!pullRequest || !STABLE_DELIVERY_BRANCHES.has(headRef)) {
    return { required: false, valid: true, reason: '' };
  }

  const baseRepository = clean(repository || pullRequest?.base?.repo?.full_name);
  const headRepository = clean(pullRequest?.head?.repo?.full_name);
  if (!baseRepository || headRepository !== baseRepository) {
    return {
      required: true,
      valid: false,
      reason: 'stable delivery must originate from the base repository',
    };
  }

  const record = parseDeliveryRecord(pullRequest.body || '');
  const eligibility = mergeEligibility(record, {
    now,
    repository: baseRepository,
    requireSealed: true,
    headSha: pullRequest?.head?.sha,
  });
  return {
    required: true,
    valid: eligibility.eligible,
    reason: eligibility.reason,
  };
}

// The runner rewrites event.json before each action. Consume the resolved
// snapshot through the action input, while retaining the original identity.
function resolvedSealEvent(event, resolvedJson, { repository = '', eventName = '', sha = '' } = {}) {
  if (!resolvedJson || resolvedJson === 'null') return event;
  let resolved;
  try { resolved = JSON.parse(resolvedJson); } catch {
    throw new Error('Resolved Gate PR metadata is malformed');
  }
  if (!resolved || resolved.state !== 'open' || !Number.isSafeInteger(resolved.number)
      || resolved.number <= 0 || !resolved.head?.sha || !resolved.head?.repo?.full_name) {
    throw new Error('Resolved Gate PR metadata is incomplete');
  }
  const original = event.pull_request;
  if (original) {
    if (resolved.number !== original.number || resolved.head.sha !== original.head?.sha
        || resolved.head.repo.full_name !== original.head?.repo?.full_name
        || resolved.head.ref !== original.head?.ref
        || resolved.base?.ref !== original.base?.ref) {
      throw new Error('Resolved Gate PR identity differs from the event');
    }
  } else if (eventName !== 'workflow_dispatch' || resolved.head.sha !== sha
      || resolved.head.repo.full_name !== repository) {
    throw new Error('Resolved Gate PR identity differs from the dispatched head');
  }
  const pr = original ? { ...original, body: resolved.body, labels: resolved.labels,
    state: resolved.state } : resolved;
  return { ...event, pull_request: pr, number: pr.number };
}

function workflowCommandValue(value) {
  return String(value || '')
    .replaceAll('%', '%25')
    .replaceAll('\r', '%0D')
    .replaceAll('\n', '%0A');
}

function main() {
  const eventPath = clean(process.env.GITHUB_EVENT_PATH);
  if (!eventPath) throw new Error('GITHUB_EVENT_PATH is required');
  const event = JSON.parse(fs.readFileSync(eventPath, 'utf8'));
  const resolvedEvent = resolvedSealEvent(event, process.env.GATE_PR_JSON, {
    repository: process.env.GITHUB_REPOSITORY, eventName: process.env.GITHUB_EVENT_NAME,
    sha: process.env.GITHUB_SHA,
  });
  const result = evaluateDeliverySeal(resolvedEvent, process.env.GITHUB_REPOSITORY);
  if (!result.required) {
    console.log('Generated delivery seal is not required for this ref.');
    return;
  }
  if (!result.valid) {
    const message =
      `Mutable generated delivery is not mergeable: ${result.reason}. ` +
      'Maint 71 must seal this exact head after bounded reviewer settlement.';
    console.error(`::error title=Generated delivery seal::${workflowCommandValue(message)}`);
    process.exitCode = 1;
    return;
  }
  console.log('Exact-head generated delivery seal is valid.');
}

if (require.main === module) main();

module.exports = {
  STABLE_DELIVERY_BRANCHES,
  evaluateDeliverySeal,
  main,
  resolvedSealEvent,
  workflowCommandValue,
};
