'use strict';

// A generated PR is a short-lived delivery attempt.  The durable campaign issue
// retains coordination history; this marker lets the producer and merger agree
// on which attempt is current without treating an arbitrary open PR as current.
const DELIVERY_RECORD_SCHEMA = 'sync-pr-delivery-record/v1';
const DELIVERY_RECORD_MARKER = 'sync-pr-delivery-record:v1';
const DELIVERY_STATES = new Set(['staging', 'reviewing', 'sealed']);

function clean(value) {
  return String(value || '').trim();
}

function unique(values) {
  return [...new Set((values || []).map(clean).filter(Boolean))];
}

function normalizeRecord(record = {}) {
  const normalized = {
    schema: clean(record.schema) || DELIVERY_RECORD_SCHEMA,
    durable_issue_url: clean(record.durable_issue_url),
    plan_id: clean(record.plan_id),
    generation: clean(record.generation),
    repository: clean(record.repository),
    desired_tree_hash: clean(record.desired_tree_hash),
    source_commit: clean(record.source_commit),
    head_observed_sha: clean(record.head_observed_sha),
    head_observed_at: clean(record.head_observed_at),
    lease_expires_at: clean(record.lease_expires_at),
    predecessor_prs: unique(record.predecessor_prs),
    successor_prs: unique(record.successor_prs),
    delivery_state: clean(record.delivery_state),
    review_started_at: clean(record.review_started_at),
    sealed_at: clean(record.sealed_at),
    sealed_head_sha: clean(record.sealed_head_sha),
    review_evidence:
      record.review_evidence && typeof record.review_evidence === 'object'
        ? record.review_evidence
        : {},
    terminal_disposition: clean(record.terminal_disposition),
  };
  return normalized;
}

function deliveryRecordErrors(record = {}) {
  const normalized = normalizeRecord(record);
  const required = [
    'durable_issue_url', 'plan_id', 'generation', 'repository',
    'desired_tree_hash', 'source_commit', 'lease_expires_at',
  ];
  const errors = [];
  if (normalized.schema !== DELIVERY_RECORD_SCHEMA) errors.push('schema');
  for (const field of required) if (!normalized[field]) errors.push(field);
  if (normalized.terminal_disposition && !['merged', 'superseded', 'expired', 'blocked'].includes(normalized.terminal_disposition)) {
    errors.push('terminal_disposition');
  }
  if (normalized.delivery_state && !DELIVERY_STATES.has(normalized.delivery_state)) {
    errors.push('delivery_state');
  }
  if (normalized.lease_expires_at && Number.isNaN(Date.parse(normalized.lease_expires_at))) {
    errors.push('lease_expires_at');
  }
  if (Boolean(normalized.head_observed_sha) !== Boolean(normalized.head_observed_at)) {
    errors.push('head_observation_pair');
  }
  if (normalized.head_observed_at && Number.isNaN(Date.parse(normalized.head_observed_at))) {
    errors.push('head_observed_at');
  }
  for (const field of ['review_started_at', 'sealed_at']) {
    if (normalized[field] && Number.isNaN(Date.parse(normalized[field]))) errors.push(field);
  }
  if (
    ['reviewing', 'sealed'].includes(normalized.delivery_state)
    && !normalized.review_started_at
  ) {
    errors.push('review_started_at');
  }
  if (normalized.delivery_state === 'sealed') {
    if (!normalized.sealed_at) errors.push('sealed_at');
    if (!normalized.sealed_head_sha) errors.push('sealed_head_sha');
  }
  return errors;
}

function formatDeliveryRecord(record = {}) {
  const normalized = normalizeRecord(record);
  const errors = deliveryRecordErrors(normalized);
  if (errors.length) throw new Error(`Invalid delivery record: ${errors.join(', ')}`);
  return `<!-- ${DELIVERY_RECORD_MARKER} ${JSON.stringify(normalized)} -->`;
}

function parseDeliveryRecord(body = '') {
  const match = String(body || '').match(new RegExp(`<!--\\s*${DELIVERY_RECORD_MARKER}\\s+([\\s\\S]*?)\\s*-->`));
  if (!match) return null;
  try {
    const record = normalizeRecord(JSON.parse(match[1]));
    return deliveryRecordErrors(record).length ? null : record;
  } catch (_) {
    return null;
  }
}

function replaceDeliveryRecord(body = '', changes = {}) {
  const current = parseDeliveryRecord(body);
  if (!current) throw new Error('Missing or invalid delivery record');
  const marker = formatDeliveryRecord({ ...current, ...changes });
  const expression = new RegExp(`<!--\\s*${DELIVERY_RECORD_MARKER}\\s+[\\s\\S]*?\\s*-->`);
  return String(body).replace(expression, () => marker);
}

function mergeEligibility(
  record,
  {
    now = new Date().toISOString(),
    planId = '',
    repository = '',
    desiredTreeHash = '',
    requireSealed = false,
    headSha = '',
  } = {},
) {
  const normalized = normalizeRecord(record);
  const errors = deliveryRecordErrors(normalized);
  if (errors.length) return { eligible: false, reason: `invalid:${errors.join(',')}` };
  if (normalized.terminal_disposition) return { eligible: false, reason: `terminal:${normalized.terminal_disposition}` };
  if (Date.parse(normalized.lease_expires_at) <= Date.parse(now)) return { eligible: false, reason: 'lease_expired' };
  if (clean(planId) && normalized.plan_id !== clean(planId)) return { eligible: false, reason: 'plan_mismatch' };
  if (clean(repository) && normalized.repository !== clean(repository)) return { eligible: false, reason: 'repository_mismatch' };
  if (clean(desiredTreeHash) && normalized.desired_tree_hash !== clean(desiredTreeHash)) return { eligible: false, reason: 'desired_tree_mismatch' };
  if (requireSealed && normalized.delivery_state !== 'sealed') {
    return {
      eligible: false,
      reason: `delivery_not_sealed:${normalized.delivery_state || 'legacy'}`,
    };
  }
  if (requireSealed && clean(headSha) && normalized.sealed_head_sha !== clean(headSha)) {
    return { eligible: false, reason: 'sealed_head_mismatch' };
  }
  return { eligible: true, reason: 'current_unexpired' };
}

module.exports = {
  DELIVERY_RECORD_SCHEMA,
  DELIVERY_RECORD_MARKER,
  DELIVERY_STATES,
  normalizeRecord,
  deliveryRecordErrors,
  formatDeliveryRecord,
  parseDeliveryRecord,
  replaceDeliveryRecord,
  mergeEligibility,
};
