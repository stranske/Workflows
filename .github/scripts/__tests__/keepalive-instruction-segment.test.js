'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  extractInstructionSegment,
  computeInstructionByteLength,
} = require('../../../scripts/keepalive_instruction_segment.js');

test('extractInstructionSegment strips status bundle and reports bytes', () => {
  const body = [
    '<!-- codex-keepalive-round: 1 -->',
    '<!-- keepalive-attempt: 1 -->',
    '<!-- codex-keepalive-marker -->',
    '<!-- codex-keepalive-trace: trace-123 -->',
    '@codex Continue working the checklist.',
    '',
    '## Automated Status Summary',
    '#### Scope',
    '- [ ] Do the thing.',
    '',
    '#### Tasks',
    '- [ ] Task A',
    '',
    '#### Acceptance criteria',
    '- [ ] Done when complete.',
    '',
    '**Head SHA:** deadbeef',
    '**Latest Runs:** 🟢',
    '| Workflow / Job | Result | Logs |',
    '| -- | -- | -- |',
  ].join('\n');

  const segment = extractInstructionSegment(body);
  assert.ok(segment.includes('#### Acceptance criteria'));
  assert.ok(!segment.includes('Head SHA'));
  assert.ok(!segment.includes('Workflow / Job'));

  const bytes = computeInstructionByteLength(segment);
  assert.equal(bytes, Buffer.byteLength(segment, 'utf8'));
});
