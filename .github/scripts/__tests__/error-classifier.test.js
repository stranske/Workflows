'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  ERROR_CATEGORIES,
  classifyError,
  suggestRecoveryAction,
} = require('../error_classifier.js');

test('classifyError returns transient for rate limit errors', () => {
  const result = classifyError({ status: 429, message: 'Rate limit exceeded' });
  assert.equal(result.category, ERROR_CATEGORIES.transient);
  assert.match(result.recovery, /retry/i);
});

test('classifyError returns transient for timeout messages', () => {
  const result = classifyError({ message: 'Request timed out after 30s' });
  assert.equal(result.category, ERROR_CATEGORIES.transient);
});

test('classifyError returns auth for credential failures', () => {
  const result = classifyError({ status: 401, message: 'Bad credentials' });
  assert.equal(result.category, ERROR_CATEGORIES.auth);
});

test('classifyError uses error code for transient failures', () => {
  const result = classifyError({ code: 'ETIMEDOUT' });
  assert.equal(result.category, ERROR_CATEGORIES.transient);
});

test('classifyError uses error code for network lookup failures', () => {
  const result = classifyError({ code: 'ENOTFOUND' });
  assert.equal(result.category, ERROR_CATEGORIES.transient);
});

test('classifyError returns resource for not found errors', () => {
  const result = classifyError({ status: 404, message: 'Not Found' });
  assert.equal(result.category, ERROR_CATEGORIES.resource);
});

test('classifyError returns auth for unauthorized messages', () => {
  const result = classifyError({ message: 'Unauthorized' });
  assert.equal(result.category, ERROR_CATEGORIES.auth);
});

test('classifyError returns logic for validation errors', () => {
  const result = classifyError({ status: 422, message: 'Validation failed' });
  assert.equal(result.category, ERROR_CATEGORIES.logic);
});

test('classifyError inspects nested API error details', () => {
  const result = classifyError({
    status: 400,
    response: { data: { errors: [{ message: 'Missing required field: title' }] } },
  });
  assert.equal(result.category, ERROR_CATEGORIES.logic);
});

test('classifyError returns unknown when no signals are present', () => {
  const result = classifyError({ message: '' });
  assert.equal(result.category, ERROR_CATEGORIES.unknown);
});

test('suggestRecoveryAction falls back to unknown guidance', () => {
  const result = suggestRecoveryAction('missing');
  assert.equal(result, suggestRecoveryAction(ERROR_CATEGORIES.unknown));
});

test('classifyError provides category-specific recovery guidance', () => {
  const cases = [
    {
      error: { status: 429, message: 'Rate limit exceeded' },
      category: ERROR_CATEGORIES.transient,
      recoveryPattern: /retry/i,
    },
    {
      error: { status: 401, message: 'Bad credentials' },
      category: ERROR_CATEGORIES.auth,
      recoveryPattern: /credentials|token|permission/i,
    },
    {
      error: { status: 404, message: 'Not found' },
      category: ERROR_CATEGORIES.resource,
      recoveryPattern: /resource|repository|branch|workflow/i,
    },
    {
      error: { status: 422, message: 'Validation failed' },
      category: ERROR_CATEGORIES.logic,
      recoveryPattern: /request|inputs|logic/i,
    },
    {
      error: { message: '' },
      category: ERROR_CATEGORIES.unknown,
      recoveryPattern: /logs|retry|escalate/i,
    },
  ];

  for (const entry of cases) {
    const result = classifyError(entry.error);
    assert.equal(result.category, entry.category);
    assert.match(result.recovery, entry.recoveryPattern);
  }
});
