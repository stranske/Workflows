'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  resolveInstructionToken,
  resolveDispatchToken,
} = require(path.join(__dirname, '../../../scripts/keepalive-runner.js'));

test('resolveInstructionToken prefers actions bot token', () => {
  const token = resolveInstructionToken({
    ACTIONS_BOT_PAT: 'actions-token',
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  });

  assert.equal(token, 'actions-token');
});

test('resolveInstructionToken falls back to service bot token', () => {
  const token = resolveInstructionToken({
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  });

  assert.equal(token, 'service-token');
});

test('resolveInstructionToken falls back to gh token', () => {
  const token = resolveInstructionToken({
    GH_TOKEN: 'gh-token',
  });

  assert.equal(token, 'gh-token');
});

test('resolveDispatchToken prefers actions bot token', () => {
  const token = resolveDispatchToken({
    ACTIONS_BOT_PAT: 'actions-token',
    GH_TOKEN: 'gh-token',
  });

  assert.equal(token, 'actions-token');
});

test('resolveDispatchToken falls back to gh token', () => {
  const token = resolveDispatchToken({
    GH_TOKEN: 'gh-token',
  });

  assert.equal(token, 'gh-token');
});

test('resolveDispatchToken returns empty string when unset', () => {
  const token = resolveDispatchToken({});

  assert.equal(token, '');
});
