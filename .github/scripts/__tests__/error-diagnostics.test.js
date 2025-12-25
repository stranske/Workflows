'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  collectErrorDiagnostics,
  sanitizeObject,
} = require('../error_diagnostics');

test('collectErrorDiagnostics captures allowed env values and error info', () => {
  const env = {
    GITHUB_REPOSITORY: 'octo/workflows',
    GITHUB_RUN_ID: '123',
    GITHUB_WORKFLOW: 'Codex',
    ERROR_CATEGORY: 'auth',
    ERROR_MESSAGE: 'Bad credentials',
  };
  const diagnostics = collectErrorDiagnostics({ env });

  assert.equal(diagnostics.run.GITHUB_REPOSITORY, 'octo/workflows');
  assert.equal(diagnostics.run.GITHUB_RUN_ID, '123');
  assert.equal(diagnostics.run.GITHUB_WORKFLOW, 'Codex');
  assert.equal(diagnostics.error.ERROR_CATEGORY, 'auth');
  assert.equal(diagnostics.error.ERROR_MESSAGE, 'Bad credentials');
});

test('collectErrorDiagnostics sanitizes extra payloads', () => {
  const env = {
    GITHUB_REPOSITORY: 'octo/workflows',
  };
  const extra = {
    step: 'classify-error',
    token: 'secret-value',
    nested: {
      credential_hint: 'should-drop',
      info: 'safe',
    },
  };
  const diagnostics = collectErrorDiagnostics({ env, extra });

  assert.equal(diagnostics.extra.step, 'classify-error');
  assert.equal(diagnostics.extra.nested.info, 'safe');
  assert.equal(diagnostics.extra.token, undefined);
  assert.equal(diagnostics.extra.nested.credential_hint, undefined);
});

test('sanitizeObject removes secret-like keys from payloads', () => {
  const payload = {
    safe: true,
    TokenValue: 'redact',
    inner: {
      credential: 'drop',
      ok: 'keep',
    },
  };
  const sanitized = sanitizeObject(payload);

  assert.deepEqual(sanitized, { safe: true, inner: { ok: 'keep' } });
});
