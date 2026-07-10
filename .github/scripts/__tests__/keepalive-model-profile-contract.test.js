'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', '..', '..');

function readWorkflow(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), 'utf8');
}

test('profile reaches codex runner', () => {
  const keepalive = readWorkflow('.github/workflows/agents-keepalive-loop.yml');
  assert.match(
    keepalive,
    /execution_profile:\s*\$\{\{\s*steps\.evaluate\.outputs\.execution_profile\s*\}\}/,
    'expected execution profile to be exposed from evaluate',
  );
  assert.match(
    keepalive,
    /worker_requested_model:\s*\$\{\{\s*steps\.evaluate\.outputs\.worker_requested_model\s*\}\}/,
    'expected requested worker model evaluate output',
  );
  assert.match(
    keepalive,
    /codex_model:\s*\$\{\{\s*needs\.evaluate\.outputs\.worker_requested_model\s*\}\}/,
    'expected selected profile model in reusable runner inputs',
  );
  assert.match(
    keepalive,
    /codex_fallback_models:\s*\$\{\{\s*needs\.evaluate\.outputs\.worker_fallback_model\s*\}\}/,
    'expected selected profile fallback chain in reusable runner inputs',
  );
});

test('reusable codex runner exposes worker model telemetry outputs', () => {
  const reusable = readWorkflow('.github/workflows/reusable-codex-run.yml');
  for (const outputName of [
    'worker-profile-id',
    'worker-requested-model',
    'worker-selected-model',
    'worker-model-selection-reason',
  ]) {
    assert.match(reusable, new RegExp(`${outputName}:`), `missing ${outputName} output`);
  }
  assert.match(
    reusable,
    /worker-selected-model:\s*\$\{\{\s*steps\.run_codex\.outputs\.model\s*\}\}/,
    'expected selected model to come from Run Codex step output',
  );
});
