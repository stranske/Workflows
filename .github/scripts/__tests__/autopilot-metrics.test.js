'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildCycleMetricsRecord,
  countAutoPilotSteps,
  normaliseTimestamp,
} = require('../autopilot_metrics.js');

test('countAutoPilotSteps counts matching step comments', () => {
  const comments = [
    { body: 'Auto-pilot step 1: format issue' },
    { body: '**Auto-pilot step 2**: optimize issue' },
    { body: 'Other comment' },
    { body: null },
  ];

  assert.equal(countAutoPilotSteps(comments), 2);
});

test('countAutoPilotSteps handles non-arrays', () => {
  assert.equal(countAutoPilotSteps(null), 0);
});

test('buildCycleMetricsRecord returns required fields', () => {
  const record = buildCycleMetricsRecord({
    issueNumber: '42',
    cycleCount: 3,
    timestamp: '2025-01-01T00:00:00Z',
  });

  assert.deepEqual(record, {
    metric_type: 'cycle',
    issue_number: 42,
    cycle_count: 3,
    timestamp: '2025-01-01T00:00:00Z',
  });
});

test('buildCycleMetricsRecord includes optional fields', () => {
  const record = buildCycleMetricsRecord({
    issueNumber: 9,
    cycleCount: 2,
    timestamp: '2025-01-02T03:04:05Z',
    maxCycles: 5,
    stepsAttempted: '4',
    stepsCompleted: 3,
  });

  assert.deepEqual(record, {
    metric_type: 'cycle',
    issue_number: 9,
    cycle_count: 2,
    timestamp: '2025-01-02T03:04:05Z',
    max_cycles: 5,
    steps_attempted: 4,
    steps_completed: 3,
  });
});

test('buildCycleMetricsRecord rejects invalid integers', () => {
  assert.throws(
    () => buildCycleMetricsRecord({ issueNumber: 'nope', cycleCount: 1 }),
    /issue_number must be an integer/
  );
});

test('normaliseTimestamp defaults to ISO without milliseconds', () => {
  const value = normaliseTimestamp();
  assert.match(value, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
});
