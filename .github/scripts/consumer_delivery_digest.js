'use strict';

const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const path = require('node:path');
const { createHash } = require('node:crypto');

function scopedDeliveryPayload(payload, request) {
  if (!request || request.plan_scope === 'full') return payload;
  if (request.plan_scope !== 'source-delta'
    || !/^sha256:[a-f0-9]{64}$/.test(request.plan_id || '')
    || !/^[a-f0-9]{40}$/.test(request.scope_base_sha || '')
    || !/^[a-f0-9]{40}$/.test(request.source_commit || '')
    || request.plan?.plan_id !== request.plan_id
    || !Array.isArray(request.plan.entries) || !Array.isArray(request.plan.removals)
    || request.plan.removals.length) throw new Error('canary_refresh_scoped_plan_unknown');
  const files = Object.create(null);
  for (const [repository, rendered] of Object.entries(payload.files || {})) {
    const applicable = request.plan.entries.filter(entry =>
      (!entry.include_repos?.length || entry.include_repos.includes(repository))
      && !entry.skip_repos?.includes(repository));
    const selected = Object.create(null);
    for (const [name, value] of Object.entries(rendered)) {
      if (applicable.some(entry => name === entry.target
        || (entry.is_directory && name.startsWith(`${entry.target}/`)))) selected[name] = value;
    }
    for (const entry of applicable) {
      if (!entry.is_directory && !Object.hasOwn(selected, entry.target)) {
        throw new Error('canary_refresh_scoped_payload_missing');
      }
    }
    files[repository] = selected;
  }
  // The compiler-produced tuple constrains scope; this local digest does not
  // authenticate a historical run or grant writer/merge authority.
  const identity = [request.plan_id, request.plan_scope, request.scope_base_sha,
    request.source_commit, files];
  return { digest: `sha256:${createHash('sha256').update('consumer-delivery-scoped/v1\0')
    .update(JSON.stringify(identity)).digest('hex')}`, files };
}

// One renderer/digest implementation for refresh, producer preparation and seal.
// Cache immutable snapshots only; failures remain visible to the caller.
const snapshots = new Map();
async function readDeliveryPayload(sha, repositories, refreshPlan = null) {
  if (refreshPlan && refreshPlan.source_commit !== sha) throw new Error('canary_refresh_scoped_source_changed');
  const repos = [...new Set(repositories)].sort();
  const key = `${sha}:${repos.join(',')}`;
  if (!snapshots.has(key)) snapshots.set(key, (async () => {
    const root = path.resolve(__dirname, '../..');
    const { stdout } = await promisify(execFile)(process.env.PYTHON || 'python3', [
      path.join(root, 'scripts/consumer_delivery_digest.py'), '--ref', sha,
      '--repos', repos.join(','),
    ], { cwd: root, maxBuffer: 16 * 1024 * 1024, timeout: 120000 });
    const payload = JSON.parse(stdout);
    if (!/^sha256:[a-f0-9]{64}$/.test(payload.digest) || !payload.files) {
      throw new Error('canary_delivery_digest_invalid');
    }
    return payload;
  })());
  return scopedDeliveryPayload(await snapshots.get(key), refreshPlan);
}

module.exports = { readDeliveryPayload, scopedDeliveryPayload };
