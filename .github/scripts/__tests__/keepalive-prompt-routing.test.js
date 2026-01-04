'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { resolvePromptMode } = require('../keepalive_prompt_routing');

test('resolvePromptMode routes ci failure scenarios to fix_ci', () => {
  assert.equal(resolvePromptMode({ scenario: 'ci-failure' }), 'fix_ci');
  assert.equal(resolvePromptMode({ scenario: 'fix-ci' }), 'fix_ci');
});

test('resolvePromptMode routes feature scenarios to normal', () => {
  assert.equal(resolvePromptMode({ scenario: 'feature-work' }), 'normal');
  assert.equal(resolvePromptMode({ scenario: 'next-task' }), 'normal');
});

test('resolvePromptMode routes verification scenarios to verify', () => {
  assert.equal(resolvePromptMode({ scenario: 'verification' }), 'verify');
  assert.equal(resolvePromptMode({ scenario: 'verify-acceptance' }), 'verify');
});

test('resolvePromptMode falls back to action or reason when scenario/mode missing', () => {
  assert.equal(resolvePromptMode({ action: 'fix' }), 'fix_ci');
  assert.equal(resolvePromptMode({ reason: 'fix-build' }), 'fix_ci');
  assert.equal(resolvePromptMode({ action: 'verify' }), 'verify');
  assert.equal(resolvePromptMode({ reason: 'verify-acceptance' }), 'verify');
});

test('resolvePromptMode prioritizes fix/verify actions over scenario', () => {
  assert.equal(resolvePromptMode({ scenario: 'feature-work', action: 'fix' }), 'fix_ci');
  assert.equal(resolvePromptMode({ scenario: 'feature-work', reason: 'verify-acceptance' }), 'verify');
});
