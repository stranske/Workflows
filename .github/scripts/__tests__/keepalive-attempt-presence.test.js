'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');

function fixture({ count = 1, target = 42, truncate = false, mutate = () => {},
  missingDirectory = false, unreadable = false, wrongBlob = false, badBase64 = false,
  malformedTree = false, missingBranch = false } = {}) {
  const calls = [];
  const hashes = ['1', '2', '3', '4'].map((x) => x.repeat(40));
  const blobs = new Map();
  const entries = Array.from({ length: count }, (_, i) => {
    const owner = `owner/repo:${i + 1}:1`;
    const name = crypto.createHash('sha256').update(owner).digest('hex') + '.json';
    const sha = (i + 10).toString(16).padStart(40, '0');
    const index = { version: 1, repository: 'owner/repo', owner_attempt: owner,
      pr_number: i === count - 1 ? target : 43, generation: 'a'.repeat(64),
      receipt: { id: 'b'.repeat(64), claim_digest: 'c'.repeat(64), owner_attempt: owner,
        head_sha: 'd'.repeat(40), provider: 'codex', consumed_at: '2026-10-01T00:00:00.000Z' } };
    mutate(index);
    blobs.set(sha, { sha: wrongBlob ? 'f'.repeat(40) : sha, encoding: 'base64',
      content: Buffer.from(JSON.stringify(index)).toString('base64') + (badBase64 ? '!' : '') });
    return { path: name, type: 'blob', sha };
  });
  const request = async (method, path) => {
    assert.equal(method, 'GET');
    calls.push(path);
    if (path.endsWith('/git/ref/heads/keepalive-authority-state')) {
      if (missingBranch) throw Object.assign(new Error('unavailable branch'), { status: 404 });
      return { object: { type: 'commit', sha: hashes[0] } };
    }
    if (path.endsWith(`/git/commits/${hashes[0]}`)) return { tree: { sha: hashes[1] } };
    if (path.endsWith(`/git/trees/${hashes[1]}`)) return { truncated: false,
      tree: [{ path: '.github', type: 'tree', sha: hashes[2] }] };
    if (path.endsWith(`/git/trees/${hashes[2]}`)) return { truncated: false,
      tree: missingDirectory ? [] : [{ path: 'keepalive-authority-attempts', type: 'tree', sha: hashes[3] }] };
    if (path.endsWith(`/git/trees/${hashes[3]}`)) return { truncated: truncate,
      tree: malformedTree ? [...entries, { path: 'bad', type: 'blob', sha: 'invalid' }] : entries };
    const sha = path.split('/git/blobs/')[1];
    if (blobs.has(sha)) {
      if (unreadable) throw Object.assign(new Error('unavailable blob'), { status: 404 });
      return blobs.get(sha);
    }
    throw new Error(`Unexpected request ${path}`);
  };
  return { request, calls };
}

for (const surface of ['../keepalive_authority_state.js',
  '../../../templates/consumer-repo/.github/scripts/keepalive_authority_state.js']) {
  const { hasAttemptIndexesForPr } = require(surface);
  test(`${surface}: finds an index beyond the Contents API directory limit`, async () => {
    const { request, calls } = fixture({ count: 1001 });
    assert.equal(await hasAttemptIndexesForPr(request, 'owner/repo', 42), true);
    assert.equal(calls.filter((p) => p.includes('/git/ref/')).length, 1);
    assert.ok(calls.every((p) => !p.includes('/contents/')));
  });
  test(`${surface}: proves absence only from complete validated evidence`, async () => {
    for (const options of [{ target: 43 }, { count: 0 }, { missingDirectory: true }]) {
      assert.equal(await hasAttemptIndexesForPr(fixture(options).request, 'owner/repo', 42), false);
    }
  });
  test(`${surface}: rejects incomplete, unreadable, or malformed evidence`, async () => {
    for (const options of [
      { truncate: true }, { malformedTree: true }, { unreadable: true }, { wrongBlob: true },
      { badBase64: true }, { missingBranch: true },
      { mutate: (index) => { index.repository = 'other/repo'; } },
      { mutate: (index) => { index.pr_number = '42'; } },
      { mutate: (index) => { index.receipt = null; } },
      { mutate: (index) => { index.owner_attempt = 'owner/repo:999:1'; index.receipt.owner_attempt = index.owner_attempt; } },
    ]) {
      await assert.rejects(hasAttemptIndexesForPr(fixture(options).request, 'owner/repo', 42));
    }
  });
}
