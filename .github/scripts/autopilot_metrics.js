'use strict';

function coerceInt(value, field) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) {
    throw new Error(`${field} must be an integer`);
  }
  return parsed;
}

function normaliseTimestamp(value) {
  if (value) {
    return value;
  }
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function countAutoPilotSteps(comments) {
  if (!Array.isArray(comments)) {
    return 0;
  }
  return comments.filter(comment => {
    const body = typeof comment?.body === 'string' ? comment.body : '';
    return body.includes('Auto-pilot step');
  }).length;
}

function buildCycleMetricsRecord({
  issueNumber,
  cycleCount,
  timestamp,
  maxCycles,
  stepsAttempted,
  stepsCompleted,
}) {
  const record = {
    metric_type: 'cycle',
    issue_number: coerceInt(issueNumber, 'issue_number'),
    cycle_count: coerceInt(cycleCount, 'cycle_count'),
    timestamp: normaliseTimestamp(timestamp),
  };

  if (maxCycles !== undefined && maxCycles !== null) {
    record.max_cycles = coerceInt(maxCycles, 'max_cycles');
  }
  if (stepsAttempted !== undefined && stepsAttempted !== null) {
    record.steps_attempted = coerceInt(stepsAttempted, 'steps_attempted');
  }
  if (stepsCompleted !== undefined && stepsCompleted !== null) {
    record.steps_completed = coerceInt(stepsCompleted, 'steps_completed');
  }

  return record;
}

module.exports = {
  buildCycleMetricsRecord,
  countAutoPilotSteps,
  coerceInt,
  normaliseTimestamp,
};
