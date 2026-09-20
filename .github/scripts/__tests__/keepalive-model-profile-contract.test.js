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
  assert.match(
    keepalive,
    /codex_reasoning_effort:\s*\$\{\{\s*needs\.evaluate\.outputs\.worker_reasoning_effort\s*\|\|\s*'high'\s*\}\}/,
    'expected selected profile effort, defaulting old registries to high, in reusable runner inputs',
  );
});

test('consumer keepalive forwards registry model and effort for explicit escalation', () => {
  const consumer = readWorkflow(
    'templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml',
  );
  assert.match(consumer, /INPUT_EXECUTION_PROFILE:\s*\$\{\{\s*github\.event\.inputs\.execution_profile/);
  assert.match(consumer, /codex_model:\s*\$\{\{\s*needs\.evaluate\.outputs\.worker_requested_model\s*\}\}/);
  assert.match(consumer, /codex_reasoning_effort:\s*\$\{\{\s*needs\.evaluate\.outputs\.worker_reasoning_effort\s*\|\|\s*'high'\s*\}\}/);
});

test('workflow dispatch profile input is honored when PR body omits a profile', () => {
  const keepaliveLoop = readWorkflow('.github/scripts/keepalive_loop.js');
  assert.match(
    keepaliveLoop,
    /normalise\(config\.execution_profile\)\s*\|\|\s*normalise\(process\.env\.INPUT_EXECUTION_PROFILE\)/,
    'expected blank PR config to fall back to workflow_dispatch INPUT_EXECUTION_PROFILE',
  );
});

test('ordinary keepalive execution rejects lifecycle trial profiles', () => {
  const registry = readWorkflow('.github/scripts/agent_registry.js');
  assert.match(
    registry,
    /String\(profile\.lifecycle \|\| ''\)\.trim\(\) !== 'active'/,
    'expected the shared resolver to fail closed before Keepalive can use a trial profile',
  );
  assert.match(
    registry,
    /ordinary agent execution accepts active profiles only/,
    'expected an explicit lifecycle rejection rather than a normal runner fallback',
  );
});

test('profile validation is limited to codex execution actions', () => {
  const keepaliveLoop = readWorkflow('.github/scripts/keepalive_loop.js');
  assert.match(
    keepaliveLoop,
    /if\s*\(\s*AGENT_EXECUTION_ACTIONS\.has\(action\)\s*&&\s*resolvedAgentType\s*===\s*'codex'\s*\)/,
    'expected wait/skip/stop paths not to hard-fail on execution profile validation',
  );
});

test('reusable codex runner exposes worker model telemetry outputs', () => {
  const reusable = readWorkflow('.github/workflows/reusable-codex-run.yml');
  for (const outputName of [
    'worker-profile-id',
    'worker-requested-model',
    'worker-reasoning-effort',
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
  assert.match(reusable, /-c "model_reasoning_effort=\\"\$REASONING_EFFORT\\""/);
});

test('reusable codex runner attempts selected profile fallback models', () => {
  const reusable = readWorkflow('.github/workflows/reusable-codex-run.yml');
  assert.match(
    reusable,
    /printf '%s\\n' "\$model" "\$\{fallback_models\[@\]\}"/,
    'expected non-default profile fallback models to be included in candidate order',
  );
  assert.doesNotMatch(
    reusable,
    /if \[ "\$model" = "\$DEFAULT_CODEX_MODEL" \]; then\s*candidates="\$DEFAULT_CODEX_MODEL \$FALLBACK_CODEX_MODELS"/,
    'fallback candidates must not be limited to the default model',
  );
});

test('reusable codex runner emits worker langsmith fleet artifact', () => {
  const reusable = readWorkflow('.github/workflows/reusable-codex-run.yml');
  assert.match(
    reusable,
    /"schema": "langsmith-fleet\/v1"/,
    'expected worker telemetry artifact schema marker',
  );
  assert.match(
    reusable,
    /"operation_role": "worker"/,
    'expected worker operation role in telemetry artifact',
  );
  assert.match(
    reusable,
    /name: langsmith-fleet-v1-worker-attempt-/,
    'expected uploaded worker attempt artifact',
  );
});
