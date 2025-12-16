'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { makeTrace, renderInstruction } = require('../keepalive_contract.js');

test('makeTrace generates unique lowercase trace tokens', () => {
  const samples = new Set();
  for (let i = 0; i < 10; i += 1) {
    const trace = makeTrace();
    assert.match(trace, /^[a-z0-9]{10,16}$/);
    assert(!samples.has(trace), 'Trace tokens should be unique within sample set');
    samples.add(trace);
  }
});

test('renderInstruction emits required markers and mention', () => {
  const output = renderInstruction({ round: 3, trace: 'abc123', body: '@codex please sync' });
  const lines = output.trim().split(/\n/);
  assert.equal(lines[0], '<!-- codex-keepalive-marker -->');
  assert.equal(lines[1], '<!-- codex-keepalive-round: 3 -->');
  assert.equal(lines[2], '<!-- codex-keepalive-trace: abc123 -->');
  assert.equal(lines[3], '@codex please sync');
});

test('renderInstruction prefixes missing @codex', () => {
  const output = renderInstruction({ round: 1, trace: 'trace', body: 'review scope' });
  const lines = output.trim().split(/\n/);
  assert.equal(lines[3], '@codex review scope');
});

test('renderInstruction normalises to requested agent alias', () => {
  const output = renderInstruction({
    round: 5,
    trace: 'trace',
    body: '@codex please continue with scope',
    agent: 'alpha',
  });
  const lines = output.trim().split(/\n/);
  assert.equal(lines[3], '@alpha please continue with scope');
});

test('renderInstruction rejects invalid inputs', () => {
  assert.throws(() => renderInstruction({ round: 0, trace: 'trace', body: '@codex hi' }));
  assert.throws(() => renderInstruction({ round: 2, trace: '', body: '@codex hi' }));
  assert.throws(() => renderInstruction({ round: 2, trace: 'trace', body: '' }));
});
