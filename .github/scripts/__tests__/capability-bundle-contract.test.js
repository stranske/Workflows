'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  computeCapabilityBundleHash,
  renderCapabilityFragments,
  selectCapabilityBundles,
  validateCapabilityBundle,
} = require('../capability_bundle');
const { composePrompt } = require('../keepalive_prompt_composer');
const { buildMetricsRecord } = require('../keepalive_loop');

function validBundle(overrides = {}) {
  const bundle = {
    schema_version: 'capability-bundle/v1',
    capability_id: 'keepalive/static-spa',
    version: '1.0.0',
    selector: {
      repo: 'stranske/Inv-Man-Intake',
      agent: 'codex',
      mode: 'normal',
      labels: ['agents:keepalive'],
    },
    owner: 'stranske/Workflows',
    fragments: {
      task: 'Exercise the static SPA packet upload before claiming UI parity.',
      acceptance: 'Report the frontend_verify gate ID and the offline-bundle assertion.',
    },
    gates: ['frontend_verify@1', 'offline_bundle@1'],
    playbooks: ['docs/keepalive/KEEPALIVE_TROUBLESHOOTING.md'],
    expires_at: '2099-01-01T00:00:00Z',
    rollback: 'Remove the bundle from the registry and rerun keepalive without prompt fragments.',
    ...overrides,
  };
  return {
    ...bundle,
    content_hash: overrides.content_hash || computeCapabilityBundleHash(bundle),
  };
}

test('valid bundle passes content-hash and safety validation', () => {
  assert.equal(
    validateCapabilityBundle(validBundle(), {
      knownCapabilities: ['keepalive/static-spa'],
      now: new Date('2026-01-01T00:00:00Z'),
    }),
    true,
  );
});

test('hash mismatch blocks dispatch', () => {
  const bundle = validBundle({ content_hash: 'sha256:deadbeef' });
  assert.throws(
    () => validateCapabilityBundle(bundle, { knownCapabilities: ['keepalive/static-spa'] }),
    /hash mismatch/,
  );
});

test('unknown capability id is rejected', () => {
  const bundle = validBundle({ capability_id: 'local/unknown' });
  assert.throws(
    () => validateCapabilityBundle(bundle, { knownCapabilities: ['keepalive/static-spa'] }),
    /unknown capability id/,
  );
});

test('unsafe inline prompt or credential fields are rejected', () => {
  const bundle = validBundle({ raw_prompt: 'do local hidden work' });
  assert.throws(() => validateCapabilityBundle(bundle), /unsafe inline fields: raw_prompt/);
});

test('prompt composer applies matching capability and reports exact id and hash', () => {
  const bundle = validBundle();
  const result = composePrompt({
    knownCapabilities: ['keepalive/static-spa'],
    capabilityBundles: [bundle],
    context: {
      repo: 'stranske/Inv-Man-Intake',
      agent: 'codex',
      labels: ['agents:keepalive'],
    },
    mode: 'normal',
    segments: [{ id: 'base', text: 'Base instructions' }],
  });

  assert.match(result.text, /Capability: keepalive\/static-spa@1\.0\.0/);
  assert.match(result.text, /Base instructions/);
  assert.deepEqual(result.segments, ['capability-bundle', 'base']);
  assert.equal(result.capability_bundles.applied[0].content_hash, bundle.content_hash);
});

test('nonmatching bundle reports rejection reason and applies no fragment', () => {
  const bundle = validBundle();
  const selected = selectCapabilityBundles(
    [bundle],
    { repo: 'stranske/Workflows', agent: 'codex', mode: 'normal', labels: ['agents:keepalive'] },
    { knownCapabilities: ['keepalive/static-spa'] },
  );

  assert.deepEqual(selected.applied, []);
  assert.equal(selected.rejected[0].reason, 'repo');
  assert.equal(renderCapabilityFragments(selected.applied), '');
});

test('keepalive metrics carry applied bundle metadata and rejection reasons', () => {
  const bundle = validBundle();
  const capabilityBundles = {
    applied: [
      {
        capability_id: bundle.capability_id,
        content_hash: bundle.content_hash,
        gate_versions: bundle.gates,
      },
    ],
    rejected: [{ capability_id: 'keepalive/other', reason: 'repo' }],
  };

  const record = buildMetricsRecord({
    prNumber: 123,
    iteration: 2,
    action: 'run',
    errorCategory: 'none',
    durationMs: 10,
    tasksTotal: 3,
    tasksComplete: 1,
    capabilityBundles,
  });

  assert.deepEqual(record.capability_bundle_ids, ['keepalive/static-spa']);
  assert.deepEqual(record.capability_bundle_hashes, [bundle.content_hash]);
  assert.deepEqual(record.capability_gate_versions, ['frontend_verify@1', 'offline_bundle@1']);
  assert.deepEqual(record.capability_rejection_reasons, ['repo']);
});
