'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const {
  TEMPLATE_PATH,
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

test('getKeepaliveInstruction falls back to the default copy when template is missing', () => {
  const originalRead = fs.readFileSync;
  fs.readFileSync = () => {
    throw new Error('missing template');
  };

  try {
    const result = getKeepaliveInstruction();
    assert.ok(result.includes('Example reply format'));
    assert.ok(result.includes('Review the Scope/Tasks/Acceptance'));
  } finally {
    fs.readFileSync = originalRead;
    clearCache();
  }
});
