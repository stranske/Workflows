'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');

// Keep immutable snapshots: a cache publication changes the branch commit, while
// only an index writer changes the attempt subtree. No process-local helper state.
function presenceServer({ count = 1001, missing = null } = {}) {
  const sha = (value) => value.toString(16).padStart(40, '0');
  const inventories = new Map();
  const commits = new Map();
  const trees = new Map();
  const blobs = new Map();
  const calls = [];
  let hook = () => {};
  let version = 0;
  let indexVersion = 0;
  const entries = [];
  function addIndex(prNumber, runId) {
    const ownerAttempt = `owner/repo:${runId}:1`;
    const index = { version: 1, repository: 'owner/repo', owner_attempt: ownerAttempt,
      pr_number: prNumber, generation: 'a'.repeat(64),
      receipt: { id: 'b'.repeat(64), claim_digest: 'c'.repeat(64), owner_attempt: ownerAttempt,
        head_sha: 'd'.repeat(40), provider: 'codex', consumed_at: '2026-10-01T00:00:00.000Z' } };
    const blobSha = sha(500000 + runId);
    blobs.set(blobSha, { sha: blobSha, encoding: 'base64',
      content: Buffer.from(JSON.stringify(index)).toString('base64') });
    entries.push({ path: crypto.createHash('sha256').update(ownerAttempt).digest('hex') + '.json',
      type: 'blob', sha: blobSha });
    indexVersion += 1;
  }
  for (let i = 1; i <= count; i += 1) addIndex(9000, i);
  function publish() {
    version += 1;
    const indexTree = sha(400000 + indexVersion);
    trees.set(indexTree, { truncated: false, tree: entries.map((entry) => ({ ...entry })) });
    const githubTree = sha(300000 + version);
    trees.set(githubTree, { truncated: false, tree: missing === 'attempts' ? [] :
      [{ path: 'keepalive-authority-attempts', type: 'tree', sha: indexTree },
       ...(inventories.size ? [{ path: 'keepalive-authority-presence-v2', type: 'tree', sha: sha(700000 + version) }] : [])] });
    const rootTree = sha(200000 + version);
    trees.set(rootTree, { truncated: false, tree: missing === 'github' ? [] :
      [{ path: '.github', type: 'tree', sha: githubTree }] });
    commits.set(sha(100000 + version), { tree: { sha: rootTree }, inventories: new Map(inventories) });
  }
  publish();
  const request = async (method, path, body) => {
    calls.push({ method, path });
    let response;
    if (path.includes('/contents/.github/keepalive-authority-presence-v2/')) {
      const key = path.split('keepalive-authority-presence-v2/')[1].split('?')[0];
      if (method === 'PUT') {
        const old = inventories.get(key);
        if (key === 'checkpoint.json') {
          if ((old?.sha || undefined) !== body.sha) throw Object.assign(new Error('CAS conflict'), { status: 409 });
        } else {
          assert.equal(body.sha, undefined, 'inventory must be create-only');
          if (old) throw Object.assign(new Error('existing'), { status: 422 });
        }
        inventories.set(key, { content: body.content, sha: sha(600000 + version) });
        publish();
        response = {};
      } else {
        assert.equal(method, 'GET');
        const ref = path.split('?ref=')[1];
        const snapshot = ref === 'keepalive-authority-state' ? inventories : commits.get(ref)?.inventories;
        if (!snapshot?.has(key)) throw Object.assign(new Error('missing'), { status: 404 });
        response = { ...snapshot.get(key), encoding: 'base64' };
      }
    } else {
      assert.equal(method, 'GET');
      const key = path.split('/').pop();
      if (path.includes('/git/ref/')) response = { object: { type: 'commit', sha: sha(100000 + version) } };
      else if (path.includes('/git/commits/')) response = { tree: commits.get(key)?.tree };
      else if (path.includes('/git/trees/')) response = trees.get(key);
      else if (path.includes('/git/blobs/')) response = blobs.get(key);
      assert.ok(response, `Unexpected request ${method} ${path}`);
    }
    await hook({ method, path, body });
    return response;
  };
  return {
    request,
    calls,
    setHook(value) { hook = value; },
    addAttempt(prNumber = 44, runId = 9999) {
      missing = null;
      addIndex(prNumber, runId);
      publish();
    },
    removeAttempt(runId) {
      const path = crypto.createHash('sha256').update(`owner/repo:${runId}:1`).digest('hex') + '.json';
      entries.splice(entries.findIndex((entry) => entry.path === path), 1);
      indexVersion += 1; publish();
    },
    replaceAttempt(runId, prNumber) {
      const path = crypto.createHash('sha256').update(`owner/repo:${runId}:1`).digest('hex') + '.json';
      entries.splice(entries.findIndex((entry) => entry.path === path), 1);
      addIndex(prNumber, runId + 20000);
      // Replacement keeps the original owner/filename but changes immutable blob bytes.
      const entry = entries.pop();
      const blob = blobs.get(entry.sha);
      const index = JSON.parse(Buffer.from(blob.content, 'base64').toString('utf8'));
      index.owner_attempt = `owner/repo:${runId}:1`; index.receipt.owner_attempt = index.owner_attempt;
      blob.content = Buffer.from(JSON.stringify(index)).toString('base64');
      entries.push({ ...entry, path }); publish();
    },
    corruptInventory(edit) {
      for (const [key, file] of inventories) {
        if (key === 'checkpoint.json') continue;
        const value = JSON.parse(Buffer.from(file.content, 'base64').toString('utf8'));
        edit(value); inventories.set(key, { ...file, content: Buffer.from(JSON.stringify(value)).toString('base64') });
      }
      publish();
    },
    dropCheckpoint() { inventories.delete('checkpoint.json'); inventories.delete('bootstrap.json'); publish(); },
    stats() {
      return { blobs: calls.filter((call) => call.path.includes('/git/blobs/')).length,
        writes: calls.filter((call) => call.method === 'PUT').length, calls: calls.length };
    },
  };
}

module.exports = { presenceServer };
