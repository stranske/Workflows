'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const {
  TEMPLATE_PATH,
  NEXT_TASK_TEMPLATE_PATH,
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
  const expected = fs.readFileSync(NEXT_TASK_TEMPLATE_PATH, 'utf8').trim();
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
    const first = getKeepaliveInstruction({ mode: 'verify' });
    assert.equal(first, 'payload-1');
    clearCache();
    const second = getKeepaliveInstruction({ mode: 'verify' });
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

test('getKeepaliveInstruction routes to fix prompt when scenario is ci-failure', () => {
  const expected = fs.readFileSync(FIX_TEMPLATE_PATH, 'utf8').trim();
  const result = getKeepaliveInstruction({ scenario: 'ci-failure' });
  assert.equal(result, expected);
});

test('getKeepaliveInstruction routes to next-task prompt for feature scenarios', () => {
  const expected = fs.readFileSync(NEXT_TASK_TEMPLATE_PATH, 'utf8').trim();
  const result = getKeepaliveInstruction({ scenario: 'feature-work' });
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

for (const [surface, builder] of [
  ['root', require('../keepalive_instruction_template')],
  ['consumer', require('../../../templates/consumer-repo/.github/scripts/keepalive_instruction_template')],
]) {
  test(`${surface}: composition exposes routed mode and renders segments with mock state`, () => {
    const state = Object.freeze({ iteration: 3, previous_task: 'Add parser' });
    const context = Object.freeze({ task: 'Test parser' });
    const inputs = [];
    const result = builder.composeKeepaliveInstruction({
      scenario: 'ci-failure',
      state,
      context,
      segments: [
        {
          id: 'round-context',
          when: (input) => {
            inputs.push(input);
            return input.state.iteration > 1;
          },
          build: (input) => {
            inputs.push(input);
            return `Round ${input.state.iteration}: ${input.context.task}`;
          },
        },
        { id: 'excluded', when: () => false, build: () => assert.fail('excluded build ran') },
        { id: 'empty', text: '  ' },
      ],
    });

    assert.equal(result.mode, 'fix_ci');
    assert.deepEqual(result.segments, ['instruction', 'round-context']);
    assert.equal(result.text, `${builder.getKeepaliveInstruction({ mode: 'fix_ci' })}\n\nRound 3: Test parser`);
    for (const input of inputs) {
      assert.equal(input.state, state);
      assert.equal(input.context, context);
      assert.equal(input.mode, 'fix_ci');
    }
    assert.equal(inputs.length, 2);
    builder.clearCache();
  });

  test(`${surface}: composition reevaluates segments while the directive is cached`, () => {
    builder.clearCache();
    const options = {
      segments: [{ id: 'task', build: ({ context }) => context.task }],
    };
    const first = builder.composeKeepaliveInstruction({ ...options, context: { task: 'First task' } });
    const second = builder.composeKeepaliveInstruction({ ...options, context: { task: 'Next task' } });

    assert.equal(first.text, `${builder.getKeepaliveInstruction()}\n\nFirst task`);
    assert.equal(second.text, `${builder.getKeepaliveInstruction()}\n\nNext task`);
    assert.deepEqual(second.segments, ['instruction', 'task']);
    assert.equal(second.mode, 'normal');
    builder.clearCache();
  });

  test(`${surface}: formatting preflight is composed only for work modes missing it`, () => {
    const originalRead = fs.readFileSync;
    fs.readFileSync = () => 'Directive without formatting instructions';
    builder.clearCache();
    try {
      for (const mode of ['normal', 'fix_ci', 'verify', 'conflict']) {
        const result = builder.composeKeepaliveInstruction({ mode });
        const needsPreflight = mode === 'normal' || mode === 'fix_ci';
        assert.deepEqual(result.segments, needsPreflight
          ? ['black-preflight', 'instruction'] : ['instruction']);
        assert.equal(result.text.includes('## Pre-Commit Formatting Gate (Black)'), needsPreflight);
        assert.ok(result.text.endsWith('Directive without formatting instructions'));
        assert.equal(result.mode, mode);
      }
    } finally {
      fs.readFileSync = originalRead;
      builder.clearCache();
    }
  });

  test(`${surface}: custom templates and mention wrappers support additional segments`, () => {
    const options = {
      templatePath: builder.VERIFY_TEMPLATE_PATH,
      segments: [{ id: 'evidence', text: 'Check the recorded evidence.' }],
    };
    const result = builder.composeKeepaliveInstruction(options);
    const expected = `${fs.readFileSync(builder.VERIFY_TEMPLATE_PATH, 'utf8').trim()}\n\nCheck the recorded evidence.`;
    assert.equal(result.text, expected);
    assert.equal(result.mode, 'custom');
    assert.deepEqual(result.segments, ['instruction', 'evidence']);
    assert.equal(builder.getKeepaliveInstructionWithMention({ ...options, agent: 'test-agent' }),
      `@test-agent ${expected}`);
    builder.clearCache();
  });
}
