'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const {
  TEMPLATE_PATH,
  FIX_TEMPLATE_PATH,
  VERIFY_TEMPLATE_PATH,
  getKeepaliveInstruction,
  getKeepaliveInstructionWithMention,
  clearCache,
} = require('../keepalive_instruction_template');

test.beforeEach(() => {
  clearCache();
});

test('getKeepaliveInstruction returns trimmed template content', () => {
  const expected = fs.readFileSync(TEMPLATE_PATH, 'utf8').trim();
  const result = getKeepaliveInstruction();
  assert.equal(result, expected);
});

test('getKeepaliveInstruction caches template content across calls', () => {
  const originalRead = fs.readFileSync;
  let readCount = 0;
  fs.readFileSync = (...args) => {
    readCount += 1;
    return originalRead(...args);
  };

  try {
    const first = getKeepaliveInstruction();
    const second = getKeepaliveInstruction();
    assert.equal(first, second);
    assert.equal(readCount, 1);
  } finally {
    fs.readFileSync = originalRead;
    clearCache();
  }
});

test('clearCache forces template reload on next call', () => {
  const originalRead = fs.readFileSync;
  let readCount = 0;
  fs.readFileSync = () => {
    readCount += 1;
    return `payload-${readCount}`;
  };

  try {
    const first = getKeepaliveInstruction();
    assert.equal(first, 'payload-1');
    clearCache();
    const second = getKeepaliveInstruction();
    assert.equal(second, 'payload-2');
  } finally {
    fs.readFileSync = originalRead;
    clearCache();
  }
});

test('getKeepaliveInstructionWithMention prefixes the provided alias', () => {
  const instruction = getKeepaliveInstruction();
  const result = getKeepaliveInstructionWithMention('keepalive-bot');
  assert.ok(result.startsWith('@keepalive-bot '));
  assert.ok(result.endsWith(instruction));
});

test('getKeepaliveInstructionWithMention defaults to codex when alias is blank', () => {
  const result = getKeepaliveInstructionWithMention('   ');
  assert.ok(result.startsWith('@codex '));
});

test('getKeepaliveInstruction routes to fix CI prompt when mode is fix_ci', () => {
  const expected = fs.readFileSync(FIX_TEMPLATE_PATH, 'utf8').trim();
  const result = getKeepaliveInstruction({ mode: 'fix_ci' });
  assert.equal(result, expected);
});

test('getKeepaliveInstruction routes to verify prompt when action requests verification', () => {
  const expected = fs.readFileSync(VERIFY_TEMPLATE_PATH, 'utf8').trim();
  const result = getKeepaliveInstruction({ action: 'verify' });
  assert.equal(result, expected);
});

test('getKeepaliveInstructionWithMention forwards routing options', () => {
  const expected = fs.readFileSync(FIX_TEMPLATE_PATH, 'utf8').trim();
  const result = getKeepaliveInstructionWithMention('codex', { reason: 'fix-test' });
  assert.ok(result.startsWith('@codex '));
  assert.ok(result.endsWith(expected));
});

test('getKeepaliveInstruction falls back to the default copy when template is missing', () => {
  const originalRead = fs.readFileSync;
  fs.readFileSync = () => {
    throw new Error('missing template');
  };

  try {
    const result = getKeepaliveInstruction();
    // Fallback includes example for checkbox updates and critical instructions
    assert.ok(result.includes('**Example:**'));
    assert.ok(result.includes('Review the Scope/Tasks/Acceptance'));
  } finally {
    fs.readFileSync = originalRead;
    clearCache();
  }
});
