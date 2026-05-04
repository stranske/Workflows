'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const fs = require('node:fs');
const path = require('node:path');

const { evaluateEligibility, extractLabels } = require('../../actions/agent-event-eligibility/eligibility');

const issuePayload = (overrides = {}) => ({
  action: 'labeled',
  sender: { login: 'maintainer' },
  issue: {
    labels: [{ name: 'agents:auto-pilot' }, { name: 'agent:codex' }],
  },
  ...overrides,
});

test('allows when an expected label matches', () => {
  const result = evaluateEligibility({
    payload: issuePayload(),
    eventName: 'issues',
    expectedLabels: 'agents:auto-pilot',
  });

  assert.equal(result.shouldRun, true);
  assert.equal(result.matchedLabel, 'agents:auto-pilot');
});

test('denies when expected labels do not match', () => {
  const result = evaluateEligibility({
    payload: issuePayload(),
    eventName: 'issues',
    expectedLabels: 'autofix',
  });

  assert.equal(result.shouldRun, false);
  assert.equal(result.reason, 'expected label not present');
});

test('allows and denies actors by allow-list', () => {
  assert.equal(evaluateEligibility({
    payload: issuePayload(),
    expectedActors: 'maintainer,github-actions[bot]',
  }).shouldRun, true);

  const denied = evaluateEligibility({
    payload: issuePayload(),
    expectedActors: 'trusted-bot[bot]',
  });

  assert.equal(denied.shouldRun, false);
  assert.match(denied.reason, /actor not allowed/);
});

test('allows and denies event actions by allow-list', () => {
  assert.equal(evaluateEligibility({
    payload: issuePayload({ action: 'opened' }),
    eventName: 'issues',
    expectedActions: 'opened,reopened,labeled',
  }).shouldRun, true);

  const denied = evaluateEligibility({
    payload: issuePayload({ action: 'closed' }),
    eventName: 'issues',
    expectedActions: 'opened,reopened,labeled',
  });

  assert.equal(denied.shouldRun, false);
  assert.match(denied.reason, /event action not allowed/);
});

test('evaluates custom predicate truthy and falsy results', () => {
  assert.equal(evaluateEligibility({
    payload: issuePayload(),
    customPredicate: "issue && contains(issue.labels[].name, 'agent:codex')",
  }).shouldRun, true);

  const denied = evaluateEligibility({
    payload: issuePayload(),
    customPredicate: "pull_request && contains(pull_request.labels[].name, 'agent:codex')",
  });

  assert.equal(denied.shouldRun, false);
  assert.equal(denied.reason, 'custom predicate evaluated falsy');
});

test('evaluates grouped custom predicate expressions', () => {
  const result = evaluateEligibility({
    payload: issuePayload(),
    customPredicate: "(action == 'opened' || action == 'labeled') && issue",
  });

  assert.equal(result.shouldRun, true);
});

test('exposes event_name to custom predicates', () => {
  const result = evaluateEligibility({
    payload: issuePayload({ action: undefined }),
    eventName: 'workflow_dispatch',
    customPredicate: "event_name == 'workflow_dispatch'",
  });

  assert.equal(result.shouldRun, true);
});

test('warning mode bypasses denied decisions', () => {
  const result = evaluateEligibility({
    payload: issuePayload(),
    expectedLabels: 'autofix',
    mode: 'warning',
  });

  assert.equal(result.shouldRun, true);
  assert.equal(result.warningModeBypassed, true);
  assert.match(result.reason, /warning mode bypassed denial/);
});

test('unlabeled events do not keep the removed label in the current set', () => {
  const labels = extractLabels(issuePayload({
    action: 'unlabeled',
    label: { name: 'agent:codex' },
    issue: { labels: [{ name: 'agents:auto-pilot' }] },
  }));

  assert.deepEqual(labels, ['agents:auto-pilot']);
});

test('event-name input default stays blank so runtime env fallback is used', () => {
  const actionMetadata = fs.readFileSync(
    path.join(__dirname, '../../actions/agent-event-eligibility/action.yml'),
    'utf8',
  );

  assert.match(actionMetadata, /event-name:[\s\S]*?default: ''/);
  assert.doesNotMatch(actionMetadata, /default: \$\{\{ github\.event_name \}\}/);
});

test('denies forbidden labels before expected label allow-list', () => {
  const result = evaluateEligibility({
    payload: issuePayload({ issue: { labels: [{ name: 'autofix' }, { name: 'needs-human' }] } }),
    expectedLabels: 'autofix',
    forbiddenLabels: 'needs-human',
  });

  assert.equal(result.shouldRun, false);
  assert.equal(result.matchedLabel, 'needs-human');
});
