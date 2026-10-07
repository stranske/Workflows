'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');

function fixture({ count = 1, target = 42, truncate = false, mutate = () => {},
  missingDirectory = false, unreadable = false, wrongBlob = false, badBase64 = false,
  malformedTree = false, missingBranch = false, putStatus = 0, corruptPresence = false } = {}) {
  const calls = [];
  const hashes = ['1', '2', '3', '4'].map((x) => x.repeat(40));
  const blobs = new Map();
  const inventories = new Map();
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
  const request = async (method, path, body) => {
    calls.push(path);
    if (path.includes('/contents/.github/keepalive-authority-presence/')) {
      const key = path.split('keepalive-authority-presence/')[1].split('?')[0];
      if (method === 'PUT') {
        if (putStatus) {
          const attempted = JSON.parse(Buffer.from(body.content, 'base64').toString('utf8'));
          if (putStatus === 409) inventories.set(key, { ...attempted, positive_prs: [999] });
          throw Object.assign(new Error('write failed'), { status: putStatus });
        }
        inventories.set(key, JSON.parse(Buffer.from(body.content, 'base64').toString('utf8')));
        return {};
      }
      assert.equal(method, 'GET');
      if (!inventories.has(key)) throw Object.assign(new Error('missing inventory'), { status: 404 });
      return { sha: 'e'.repeat(40), encoding: 'base64',
        content: corruptPresence ? 'not base64!' : Buffer.from(JSON.stringify(inventories.get(key))).toString('base64') };
    }
    assert.equal(method, 'GET');
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
    const blobReads = calls.filter((p) => p.includes('/git/blobs/')).length;
    assert.equal(await hasAttemptIndexesForPr(request, 'owner/repo', 42), true);
    assert.equal(await hasAttemptIndexesForPr(request, 'owner/repo', 43), true);
    assert.equal(await hasAttemptIndexesForPr(request, 'owner/repo', 44), false);
    assert.equal(calls.filter((p) => p.includes('/git/blobs/')).length, blobReads);
    assert.ok(calls.filter((p) => p.includes('/git/ref/')).length >= 1);
    assert.ok(calls.every((p) => !p.includes('/contents/.github/keepalive-authority-attempts/')));
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
  test(`${surface}: rejects lost, conflicting, or malformed inventory publication`, async () => {
    for (const options of [{ putStatus: 500 }, { putStatus: 409 }, { corruptPresence: true }]) {
      await assert.rejects(hasAttemptIndexesForPr(fixture(options).request, 'owner/repo', 42));
    }
  });
}
