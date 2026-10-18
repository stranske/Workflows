'use strict';

const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const path = require('node:path');

// One renderer/digest implementation for refresh, producer preparation and seal.
// Cache immutable snapshots only; failures remain visible to the caller.
const snapshots = new Map();
async function readDeliveryPayload(sha, repositories) {
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
  return snapshots.get(key);
}

module.exports = { readDeliveryPayload };
