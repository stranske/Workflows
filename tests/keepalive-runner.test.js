'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  resolveInstructionToken,
  resolveDispatchToken,
} = require('../scripts/keepalive-runner.js');

test('resolveInstructionToken prefers service bot PAT over actions bot PAT', () => {
  const env = {
    ACTIONS_BOT_PAT: 'actions-token',
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveInstructionToken(env), 'service-token');
});

test('resolveInstructionToken falls back to actions bot PAT when service token missing', () => {
  const env = {
    ACTIONS_BOT_PAT: 'actions-token',
    SERVICE_BOT_PAT: '',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveInstructionToken(env), 'actions-token');
});

test('resolveInstructionToken accepts lower-case service_bot_pat', () => {
  const env = {
    service_bot_pat: 'service-token',
  };
  assert.equal(resolveInstructionToken(env), 'service-token');
});

test('resolveInstructionToken falls back to GITHUB_TOKEN', () => {
  const env = {
    GITHUB_TOKEN: 'github-token',
  };
  assert.equal(resolveInstructionToken(env), 'github-token');
});

test('resolveDispatchToken prefers actions bot PAT over instruction tokens', () => {
  const env = {
    ACTIONS_BOT_PAT: 'actions-token',
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveDispatchToken(env), 'actions-token');
});

test('resolveDispatchToken falls back to instruction token when actions token missing', () => {
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
