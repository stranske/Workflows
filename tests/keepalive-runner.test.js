'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  resolveInstructionToken,
  resolveDispatchToken,
} = require('../scripts/keepalive-runner.js');

test('resolveInstructionToken prefers actions bot PAT over service bot PAT', () => {
  const env = {
    ACTIONS_BOT_PAT: 'actions-token',
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveInstructionToken(env), 'actions-token');
});

test('resolveInstructionToken falls back to service bot PAT when actions token missing', () => {
  const env = {
    ACTIONS_BOT_PAT: '',
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveInstructionToken(env), 'service-token');
});

test('resolveInstructionToken accepts lower-case env keys', () => {
  const env = {
    actions_bot_pat: 'actions-token',
  };
  assert.equal(resolveInstructionToken(env), 'actions-token');
});

test('resolveInstructionToken falls back to GITHUB_TOKEN', () => {
  const env = {
    GITHUB_TOKEN: 'github-token',
  };
  assert.equal(resolveInstructionToken(env), 'github-token');
});

test('resolveDispatchToken mirrors instruction token precedence', () => {
  const env = {
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveDispatchToken(env), 'service-token');
});

test('resolveDispatchToken accepts lower-case github_token', () => {
  const env = {
    github_token: 'github-token',
  };
  assert.equal(resolveDispatchToken(env), 'github-token');
});
