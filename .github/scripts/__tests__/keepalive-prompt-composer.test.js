'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { createPromptComposer, composePrompt, createRoundHistorySegment } = require('../keepalive_prompt_composer');
const { computeCapabilityBundleHash } = require('../capability_bundle');

test('round history tolerates legacy and malformed state without inventing outcomes', () => {
  for (const attempts of [undefined, null, {}, [], [null, 'invalid', { action: 'wait' }]]) {
    const result = composePrompt({ state: { attempts }, segments: [createRoundHistorySegment()] });
    assert.equal(result.text, '');
    assert.deepEqual(result.segments, []);
  }
  const result = composePrompt({
    state: { attempts: [{ iteration: 1, action: 'run', reason: 'ready' }] },
    segments: [createRoundHistorySegment()],
  });
  assert.match(result.text, /Round 1: run; result=unknown; reason=ready/);
  assert.ok(!result.text.includes('task='));
});

test('round history keeps the last three agent rounds and includes progress and errors', () => {
  const attempts = [
    { iteration: 1, action: 'run', run_result: 'success' },
    { iteration: 2, action: 'run', run_result: 'failure', focus_task: 'Add\n parser', error_type: 'tests' },
    { iteration: 2, action: 'wait', reason: 'gate-pending' },
    { iteration: 3, action: 'fix', run_result: 'failure', prompt_mode: 'fix_ci' },
    { iteration: 4, action: 'run', run_result: 'success', tasks_completed_delta: 1 },
  ];
  const before = JSON.stringify(attempts);
  const result = composePrompt({ state: { attempts }, segments: [createRoundHistorySegment()] });
  assert.ok(!result.text.includes('Round 1:'));
  assert.ok(!result.text.includes('gate-pending'));
  assert.match(result.text, /Round 2: run; result=failure; task=Add parser; error_type=tests/);
  assert.match(result.text, /Round 3: fix; result=failure; strategy=fix_ci/);
  assert.match(result.text, /Round 4: run; result=success; tasks_completed=1/);
  assert.equal(JSON.stringify(attempts), before);
});

test('createPromptComposer composes segments in order with default separator', () => {
  const composer = createPromptComposer({
    segments: [
      { id: 'alpha', build: () => 'First block' },
      { id: 'beta', build: () => 'Second block' },
    ],
  });

  const result = composer.compose();
  assert.equal(result.text, 'First block\n\nSecond block');
  assert.deepEqual(result.segments, ['alpha', 'beta']);
});

test('composePrompt skips segments when condition is false', () => {
  const result = composePrompt({
    segments: [
      { id: 'alpha', build: () => 'Keep me' },
      { id: 'beta', when: () => false, build: () => 'Drop me' },
      { id: 'gamma', build: () => 'Also keep' },
    ],
  });

  assert.equal(result.text, 'Keep me\n\nAlso keep');
  assert.deepEqual(result.segments, ['alpha', 'gamma']);
});

test('composePrompt supports static text segments', () => {
  const result = composePrompt({
    segments: [
      { id: 'static', text: 'Static block' },
      { id: 'dynamic', build: () => 'Dynamic block' },
    ],
  });

  assert.equal(result.text, 'Static block\n\nDynamic block');
  assert.deepEqual(result.segments, ['static', 'dynamic']);
});

test('composePrompt ignores empty segment content', () => {
  const result = composePrompt({
    segments: [
      { id: 'empty', build: () => '   ' },
      { id: 'ok', build: () => 'Visible' },
    ],
  });

  assert.equal(result.text, 'Visible');
  assert.deepEqual(result.segments, ['ok']);
});

test('composePrompt respects an explicit empty capability bundle override', () => {
  const bundle = {
    schema_version: 'capability-bundle/v1',
    capability_id: 'keepalive/default',
    version: '1.0.0',
    selector: { repo: 'stranske/Workflows', agent: 'codex' },
    owner: 'stranske/Workflows',
    fragments: { task: 'Default task fragment' },
    gates: ['default-gate@1'],
    rollback: 'Remove default bundle.',
  };
  bundle.content_hash = computeCapabilityBundleHash(bundle);

  const composer = createPromptComposer({
    capabilityBundles: [bundle],
    segments: [{ id: 'base', text: 'Base instructions' }],
  });
  const result = composer.compose({
    capabilityBundles: [],
    context: { repo: 'stranske/Workflows', agent: 'codex' },
  });

  assert.equal(result.text, 'Base instructions');
  assert.deepEqual(result.segments, ['base']);
  assert.deepEqual(result.capability_bundles.applied, []);
});

test('composePrompt treats empty-string capability bundles as absent', () => {
  const result = composePrompt({
    capabilityBundles: '',
    segments: [{ id: 'base', text: 'Base instructions' }],
  });

  assert.equal(result.text, 'Base instructions');
  assert.deepEqual(result.capability_bundles.applied, []);
});

test('composePrompt treats false capability inputs as absent', () => {
  const result = composePrompt({
    capabilityBundles: false,
    knownCapabilities: false,
    segments: [{ id: 'base', text: 'Base instructions' }],
  });

  assert.equal(result.text, 'Base instructions');
  assert.deepEqual(result.capability_bundles.applied, []);
});
