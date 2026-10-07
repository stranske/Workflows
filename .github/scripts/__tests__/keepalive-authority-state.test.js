'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const {
  beginChallenge,
  confirmChallenge,
  consumeChallenge,
  finalizeChallenge,
  findAuthorityPrForAttempt,
  prepareChallenge,
  readAuthorityState,
  readAuthorityStateForReplay,
  reconcileFailedAuthorityAttempt,
  releasePreparedChallenge,
  reopenUnconfirmedChallenge,
} = require('../keepalive_authority_state');

const repository = 'owner/repo';
const prNumber = 42;
const fingerprint = 'a'.repeat(64);
const headSha = 'd'.repeat(40);
const ownerAttempt = 'owner/repo:100:1';
const { presenceServer } = require('./helpers/keepalive-presence-server.js');

for (const directory of ['..', '../../../templates/consumer-repo/.github/scripts']) {
  function freshHelper(filename) {
    const authority = require.resolve(`${directory}/keepalive_authority_state.js`);
    delete require.cache[authority];
    const target = require.resolve(`${directory}/${filename}`);
    delete require.cache[target];
    return require(target);
  }

  test(`${directory}: separate default reporters reuse positive and negative inventory`, async () => {
    const server = presenceServer();
    const replay = async (number) => {
      const { replayReporterAuthority } = freshHelper('keepalive_reporter_applicability.js');
      // Exercise both production defaults, including the real pinned ledger read.
      return replayReporterAuthority({ github: {}, context: { repo: { owner: 'owner', repo: 'repo' } },
        prNumber: number, makeRequest: () => server.request });
    };
    assert.deepEqual(await replay(42), { prNumber: 42, results: [] });
    assert.equal(server.stats().blobs, 1001);
    assert.equal(server.stats().writes, 1);
    for (const number of [43, 44, 9000, 45, 9000]) {
      const before = server.stats();
      if (number === 9000) await assert.rejects(replay(number), /ledger is missing/);
      else assert.deepEqual(await replay(number), { prNumber: number, results: [] });
      assert.equal(server.stats().blobs, before.blobs);
      assert.equal(server.stats().writes, before.writes);
      assert.ok(server.stats().calls - before.calls <= 15, 'warm calls must be bounded');
    }
    // An older writer only publishes an index; it knows nothing about inventories.
    server.addAttempt(44);
    await assert.rejects(replay(44), /ledger is missing/);
    assert.equal(server.stats().blobs, 2003);
    const settled = server.stats();
    await assert.rejects(replay(44), /ledger is missing/);
    await replay(45);
    assert.equal(server.stats().blobs, settled.blobs);
    assert.equal(server.stats().writes, settled.writes);
  });

  test(`${directory}: separate backfill writers converge on the same complete inventory`, async () => {
    const server = presenceServer({ count: 20 });
    const first = freshHelper('keepalive_authority_state.js');
    const second = freshHelper('keepalive_authority_state.js');
    assert.deepEqual(await Promise.all([
      first.hasAttemptIndexesForPr(server.request, repository, 44),
      second.hasAttemptIndexesForPr(server.request, repository, 9000),
    ]), [false, true]);
    assert.equal(server.stats().writes, 2, 'the second create must reconcile its 422');
    const before = server.stats();
    assert.equal(await freshHelper('keepalive_authority_state.js')
      .hasAttemptIndexesForPr(server.request, repository, 44), false);
    assert.equal(server.stats().blobs, before.blobs);
  });

  test(`${directory}: partial backfill and landed lost response deny the current read`, async () => {
    for (const phase of ['scan', 'publication']) {
      const server = presenceServer({ count: 20 });
      let failed = false;
      server.setHook(({ method, path }) => {
        if (!failed && (phase === 'scan' ? path.includes('/git/blobs/') : method === 'PUT')) {
          failed = true;
          throw status(503);
        }
      });
      await assert.rejects(freshHelper('keepalive_authority_state.js')
        .hasAttemptIndexesForPr(server.request, repository, 44), /HTTP 503/);
      assert.equal(server.stats().writes, phase === 'scan' ? 0 : 1);
      const before = server.stats();
      assert.equal(await freshHelper('keepalive_authority_state.js')
        .hasAttemptIndexesForPr(server.request, repository, 44), false);
      // A failed scan publishes nothing. A landed lost-response write is usable
      // only by a later independent reader that validates the settled snapshot.
      assert.equal(server.stats().blobs - before.blobs, phase === 'scan' ? 20 : 0);
    }
  });

  for (const missing of ['github', 'attempts']) {
    test(`${directory}: first older-writer index cannot hide behind absent ${missing}`, async () => {
      const server = presenceServer({ count: 0, missing });
      const { hasAttemptIndexesForPr } = freshHelper('keepalive_authority_state.js');
      assert.equal(await hasAttemptIndexesForPr(server.request, repository, 44), false);
      let advanced = false;
      server.setHook(({ path }) => {
        const absentTree = missing === 'github' ? 200001 : 300001;
        if (!advanced && path.endsWith(absentTree.toString(16).padStart(40, '0'))) {
          advanced = true;
          server.addAttempt(44);
        }
      });
      await assert.rejects(hasAttemptIndexesForPr(server.request, repository, 44), /changed during/);
      assert.equal(server.stats().writes, 0, 'uncertain absence must not be published');
      assert.equal(await hasAttemptIndexesForPr(server.request, repository, 44), true);
    });
  }
}

function replayTreeRequest({ missingRef = false, truncated = false,
  ledgerPresent = false, blobUnavailable = false, malformedBase64 = false,
  rootEntries = null, authorityEntries = null, stateMutator = null } = {}) {
  const commitSha = '2'.repeat(40);
  const rootTree = '3'.repeat(40);
  const githubTree = '4'.repeat(40);
  const authorityTree = '5'.repeat(40);
  const ledgerBlob = '6'.repeat(40);
  return async (method, path) => {
    assert.equal(method, 'GET');
    if (path.endsWith('/git/ref/heads/keepalive-authority-state')) {
      if (missingRef) throw status(404);
      return { object: { type: 'commit', sha: commitSha } };
    }
    if (path.endsWith(`/git/commits/${commitSha}`)) return { tree: { sha: rootTree } };
    if (path.endsWith(`/git/trees/${rootTree}`)) {
      return { truncated, tree: rootEntries ||
        [{ path: '.github', type: 'tree', sha: githubTree }] };
    }
    if (path.endsWith(`/git/trees/${githubTree}`)) {
      return { truncated: false,
        tree: [{ path: 'keepalive-authority', type: 'tree', sha: authorityTree }] };
    }
    if (path.endsWith(`/git/trees/${authorityTree}`)) {
      return { truncated: false, tree: authorityEntries || (ledgerPresent
        ? [{ path: `${prNumber}.json`, type: 'blob', sha: ledgerBlob }]
        : []) };
    }
    if (path.endsWith(`/git/blobs/${ledgerBlob}`)) {
      if (blobUnavailable) throw status(404);
      const state = {
        version: 2,
        repository,
        pr_number: prNumber,
        generation: 'a'.repeat(64),
        boundary_fingerprint: 'b'.repeat(64),
        due_at: '2026-10-01T00:00:00.000Z',
        expires_at: '2026-10-02T00:00:00.000Z',
        head_sha: headSha,
        revision: 1,
        status: 'available',
        receipt: null,
      };
      if (stateMutator) stateMutator(state);
      const content = Buffer.from(`${JSON.stringify(state)}\n`).toString('base64');
      return { sha: ledgerBlob, encoding: 'base64',
        content: malformedBase64 ? `${content}!` : content };
    }
    throw new Error(`unexpected replay tree request: ${path}`);
  };
}

test('replay proves an absent PR ledger from a complete pinned authority tree', async () => {
  const result = await readAuthorityStateForReplay(replayTreeRequest(), repository, prNumber);
  assert.equal(result, null);
});

test('replay does not reinterpret an unavailable authority branch as no ledger', async () => {
  await assert.rejects(
    readAuthorityStateForReplay(replayTreeRequest({ missingRef: true }), repository, prNumber),
    /HTTP 404/,
  );
});

test('replay rejects a truncated authority tree instead of proving absence', async () => {
  await assert.rejects(
    readAuthorityStateForReplay(replayTreeRequest({ truncated: true }), repository, prNumber),
    /incomplete or malformed/,
  );
});

test('replay rejects malformed entries instead of treating them as proof of absence', async () => {
  for (const rootEntries of [
    [null],
    [{ path: '.github', type: 'tree', sha: 'not-a-sha' }],
    [{ path: 'nested/path', type: 'tree', sha: '4'.repeat(40) }],
  ]) {
    await assert.rejects(
      readAuthorityStateForReplay(replayTreeRequest({ rootEntries }), repository, prNumber),
      /invalid entry/,
    );
  }
});

test('replay accepts valid unrelated entries beside the authority path', async () => {
  const result = await readAuthorityStateForReplay(replayTreeRequest({ rootEntries: [
    { path: 'README.md', type: 'blob', sha: '7'.repeat(40) },
    { path: '.github', type: 'tree', sha: '4'.repeat(40) },
  ] }), repository, prNumber);
  assert.equal(result, null);
});

test('replay reads a present ledger from the pinned blob', async () => {
  const result = await readAuthorityStateForReplay(
    replayTreeRequest({ ledgerPresent: true }), repository, prNumber,
  );
  assert.equal(result.sha, '6'.repeat(40));
  assert.equal(result.state.pr_number, prNumber);
});

test('replay does not reinterpret an unreadable pinned ledger as absent', async () => {
  await assert.rejects(
    readAuthorityStateForReplay(
      replayTreeRequest({ ledgerPresent: true, blobUnavailable: true }), repository, prNumber,
    ),
    /HTTP 404/,
  );
});

test('replay rejects non-canonical base64 in a present pinned ledger', async () => {
  await assert.rejects(
    readAuthorityStateForReplay(
      replayTreeRequest({ ledgerPresent: true, malformedBase64: true }), repository, prNumber,
    ),
    /non-canonical base64/,
  );
});

test('replay rejects invalid receipts in every ledger slot', async () => {
  const receipt = {
    id: 'c'.repeat(64),
    claim_digest: 'e'.repeat(64),
    owner_attempt: 'other/repo:100:1',
    head_sha: headSha,
    provider: 'codex',
    consumed_at: '2026-10-01T00:00:00.000Z',
  };
  for (const stateMutator of [
    (state) => { state.status = 'consumed'; state.receipt = receipt; },
    (state) => {
      state.released_generation = state.generation;
      state.released_receipt = { ...receipt };
    },
    (state) => {
      state.recovered_generation = state.generation;
      state.recovered_receipt = { ...receipt };
    },
    (state) => {
      state.released_generation = state.generation;
      state.released_receipt = {};
    },
  ]) {
    await assert.rejects(
      readAuthorityStateForReplay(
        replayTreeRequest({ ledgerPresent: true, stateMutator }), repository, prNumber,
      ),
      /Invalid authoritative challenge state/,
    );
  }
});

function status(code) {
  const error = new Error(`HTTP ${code}`);
  error.status = code;
  return error;
}

function fakeGitHub() {
  let branch = false;
  let content = null;
  const attemptFiles = new Map();
  let beforePut = null;
  let afterPut = null;
  let afterIndexPut = null;
  let prHead = headSha;
  let prLabels = ['agent:needs-attention'];
  let prState = 'open';
  let prUnavailable = false;
  const request = async (method, path, body) => {
    if (path.includes('/git/ref/heads/main') && method === 'GET') {
      return { object: { sha: '1'.repeat(40) } };
    }
    if (path.endsWith('/pulls/42') && method === 'GET') {
      if (prUnavailable) throw status(503);
      return { state: prState, head: { sha: prHead }, labels: prLabels.map((name) => ({ name })) };
    }
    if (path.includes('/git/ref/heads/keepalive-authority-state') && method === 'GET') {
      if (!branch) throw status(404);
      return { object: { sha: '2'.repeat(40) } };
    }
    if (path.endsWith('/git/refs') && method === 'POST') {
      if (branch) throw status(422);
      branch = true;
      return {};
    }
    if (path.includes('/contents/.github/keepalive-authority-attempts/')) {
      const key = path.split('/').pop().split('?')[0];
      if (method === 'GET') {
        if (!attemptFiles.has(key)) throw status(404);
        const encoded = attemptFiles.get(key);
        return { sha: crypto.createHash('sha1').update(encoded).digest('hex'),
          encoding: 'base64', content: encoded };
      }
      if (method === 'PUT') {
        if (attemptFiles.has(key)) throw status(422);
        attemptFiles.set(key, body.content);
        if (afterIndexPut) await afterIndexPut();
        return {};
      }
    }
    if (!path.includes('/contents/.github/keepalive-authority/42.json')) {
      throw new Error(`Unexpected ${method} ${path}`);
    }
    if (method === 'GET') {
      if (!branch || !content) throw status(404);
      return { sha: crypto.createHash('sha1').update(content).digest('hex'), encoding: 'base64', content };
    }
    if (method === 'PUT') {
      if (beforePut) await beforePut();
      const sha = content ? crypto.createHash('sha1').update(content).digest('hex') : undefined;
      if (body.sha !== sha) throw status(409);
      content = body.content;
      if (afterPut) await afterPut();
      return {};
    }
    throw new Error(`Unexpected ${method} ${path}`);
  };
  return {
    request,
    setBeforePut(fn) { beforePut = fn; },
    setAfterPut(fn) { afterPut = fn; },
    setAfterIndexPut(fn) { afterIndexPut = fn; },
    setPrHead(sha) { prHead = sha; },
    setPrLabels(labels) { prLabels = labels; },
    setPrState(value) { prState = value; },
    setPrUnavailable(value) { prUnavailable = value; },
    corruptAttemptIndex() {
      const key = `${crypto.createHash('sha256').update(ownerAttempt).digest('hex')}.json`;
      attemptFiles.set(key, Buffer.from('{invalid json').toString('base64'));
    },
    mutateAttemptIndex(fn, attempt = ownerAttempt) {
      const key = `${crypto.createHash('sha256').update(attempt).digest('hex')}.json`;
      const index = JSON.parse(Buffer.from(attemptFiles.get(key), 'base64').toString('utf8'));
      fn(index);
      attemptFiles.set(key, Buffer.from(JSON.stringify(index)).toString('base64'));
    },
    deleteAttemptIndex(attempt = ownerAttempt) {
      const key = `${crypto.createHash('sha256').update(attempt).digest('hex')}.json`;
      attemptFiles.delete(key);
    },
    mutateAuthorityState(fn) {
      const state = JSON.parse(Buffer.from(content, 'base64').toString('utf8'));
      fn(state);
      content = Buffer.from(JSON.stringify(state)).toString('base64');
    },
    expireChallenge() {
      const state = JSON.parse(Buffer.from(content, 'base64').toString('utf8'));
      state.due_at = new Date(Date.now() - 60_000).toISOString();
      state.expires_at = new Date(Date.now() - 1).toISOString();
      content = Buffer.from(JSON.stringify(state)).toString('base64');
    },
    get content() { return content; },
  };
}

function boundary() {
  const dueAt = new Date(Date.now() - 60_000).toISOString();
  const expiresAt = new Date(Date.now() + 3_600_000).toISOString();
  return { dueAt, expiresAt };
}

function boundaryAt(now, durationMs = 1_000) {
  return {
    dueAt: new Date(now.getTime() - 1_000).toISOString(),
    expiresAt: new Date(now.getTime() + durationMs).toISOString(),
  };
}

function claim(state, nonce = 'b'.repeat(64)) {
  return {
    generation: state.generation,
    boundary_fingerprint: fingerprint,
    due_at: state.due_at,
    expires_at: state.expires_at,
    head_sha: headSha,
    nonce,
    sweep_run_id: '90',
    sweep_run_attempt: '1',
  };
}

test('one generation grants once across attempts, providers, heads and nonces', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const signed = claim(state);
  const first = await consumeChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  });
  assert.equal(first.granted, true);
  for (const options of [
    { ownerAttempt },
    { ownerAttempt: 'owner/repo:101:1' },
    { ownerAttempt: 'owner/repo:102:1', provider: 'claude' },
    { ownerAttempt: 'owner/repo:103:1', headSha: 'e'.repeat(40) },
    { ownerAttempt: 'owner/repo:104:1', claim: claim(state, 'c'.repeat(64)) },
  ]) {
    const result = await consumeChallenge({
      request: api.request, repository, prNumber, claim: signed,
      ownerAttempt, provider: 'codex', headSha, ...options,
    });
    assert.equal(result.granted, false);
  }
  const repeated = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  assert.equal(repeated.generation, state.generation);
  assert.equal(repeated.status, 'consumed');
  assert.equal(await confirmChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt: 'owner/repo:999:1', headSha,
    provider: 'codex',
  }), false);
  api.setPrLabels(['needs-human']);
  assert.equal(await confirmChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  }), true);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'confirmed');
  const afterConfirmation = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  assert.equal(afterConfirmation.generation, state.generation);
  assert.equal(afterConfirmation.status, 'confirmed');
});

test('preparation is non-authorizing and can be conditionally released before reservation', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const signed = claim(state);
  const prepared = await prepareChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  });
  assert.equal(prepared.prepared, true);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'prepared');
  assert.equal((await finalizeChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt: 'owner/repo:101:1', provider: 'codex', headSha,
  })).granted, false);
  assert.equal((await releasePreparedChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  })).released, true);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'available');
});

test('an exact release retry is idempotent but cannot release a replacement receipt', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const signed = claim(state);
  const options = { request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha };
  assert.equal((await prepareChallenge(options)).prepared, true);
  assert.equal((await releasePreparedChallenge(options)).released, true);
  assert.equal((await releasePreparedChallenge(options)).reason,
    'challenge-preparation-already-released');
  assert.equal((await prepareChallenge(options)).reason, 'attempt-already-settled');
  const replacement = { ...options, ownerAttempt: 'owner/repo:101:1' };
  assert.equal((await prepareChallenge(replacement)).prepared, true);
  assert.equal((await releasePreparedChallenge({ ...options,
    ownerAttempt: 'owner/repo:999:1' })).released, false);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'prepared');
});

test('released availability rotates for a changed boundary while retaining receipt lineage', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const options = { request: api.request, repository, prNumber, claim: claim(first),
    ownerAttempt, provider: 'codex', headSha };
  assert.equal((await prepareChallenge(options)).prepared, true);
  assert.equal((await releasePreparedChallenge(options)).released, true);

  const changedFingerprint = 'f'.repeat(64);
  const rotated = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint: changedFingerprint, headSha, ...boundary(),
  });
  assert.notEqual(rotated.generation, first.generation);
  assert.equal(rotated.boundary_fingerprint, changedFingerprint);
  assert.equal(rotated.released_generation, first.generation);
  assert.deepEqual(rotated.released_generation_lineage, [first.generation]);
  assert.equal(rotated.released_receipt.owner_attempt, ownerAttempt);
  assert.equal((await prepareChallenge(options)).reason, 'challenge-not-current');
  const currentClaim = {
    ...claim(rotated),
    boundary_fingerprint: changedFingerprint,
    due_at: rotated.due_at,
    expires_at: rotated.expires_at,
  };
  assert.equal((await prepareChallenge({ ...options, claim: currentClaim })).reason,
    'attempt-already-settled');
});

test('released availability rotates an expired window while retaining receipt lineage', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const options = { request: api.request, repository, prNumber, claim: claim(first),
    ownerAttempt, provider: 'codex', headSha };
  assert.equal((await prepareChallenge(options)).prepared, true);
  assert.equal((await releasePreparedChallenge(options)).released, true);
  api.expireChallenge();

  const rotated = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  assert.notEqual(rotated.generation, first.generation);
  assert.equal(rotated.released_generation, first.generation);
  assert.deepEqual(rotated.released_generation_lineage, [first.generation]);
  assert.equal(rotated.released_receipt.owner_attempt, ownerAttempt);
  assert.ok(Date.parse(rotated.expires_at) > Date.now());
});

test('beginChallenge reaps an expired orphaned preparation with exact index and PR evidence', async () => {
  const api = fakeGitHub();
  const started = new Date('2030-01-01T00:00:00.000Z');
  const first = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundaryAt(started), now: started,
  });
  const signed = claim(first);
  const options = { request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha, now: started };
  assert.equal((await prepareChallenge(options)).prepared, true);

  const afterExpiry = new Date(started.getTime() + 2_000);
  const recovered = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, expectedGeneration: first.generation,
    ...boundaryAt(afterExpiry), now: afterExpiry,
  });
  assert.equal(recovered.status, 'available');
  assert.notEqual(recovered.generation, first.generation);
  assert.equal(recovered.released_generation, first.generation);
  assert.deepEqual(recovered.released_generation_lineage, [first.generation]);
  assert.equal(recovered.released_receipt.owner_attempt, ownerAttempt);

  const retry = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, expectedGeneration: first.generation,
    ...boundaryAt(afterExpiry), now: afterExpiry,
  });
  assert.equal(retry.generation, recovered.generation);
  assert.equal(retry.revision, recovered.revision);

  assert.equal((await finalizeChallenge(options)).granted, false);
  const freshAttempt = 'owner/repo:101:1';
  const freshClaim = claim(recovered);
  assert.equal((await consumeChallenge({ request: api.request, repository, prNumber,
    claim: freshClaim, ownerAttempt: freshAttempt, provider: 'codex', headSha,
    now: new Date(afterExpiry.getTime() + 1) })).granted, true);
});

test('beginChallenge migrates an expired legacy preparation after exact index backfill', async () => {
  const api = fakeGitHub();
  const started = new Date('2030-01-01T00:00:00.000Z');
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundaryAt(started), now: started });
  assert.equal((await prepareChallenge({ request: api.request, repository, prNumber,
    claim: claim(first), ownerAttempt, provider: 'codex', headSha, now: started })).prepared,
  true);
  api.mutateAuthorityState((state) => { delete state.prepared_claim; });
  api.deleteAttemptIndex();
  const afterExpiry = new Date(started.getTime() + 2_000);

  const recovered = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, expectedGeneration: first.generation,
    ...boundaryAt(afterExpiry), now: afterExpiry });
  assert.equal(recovered.status, 'available');
  assert.notEqual(recovered.generation, first.generation);
  assert.equal(recovered.released_generation, first.generation);
  assert.deepEqual(recovered.released_generation_lineage, [first.generation]);
  assert.equal(recovered.released_receipt.owner_attempt, ownerAttempt);

  const target = await findAuthorityPrForAttempt({
    request: api.request, repository, ownerAttempt,
  });
  assert.equal(target.prNumber, prNumber);
  assert.equal(target.state.generation, recovered.generation);
});

test('legacy preparation migration accepts an exact index retry but rejects conflicts', async () => {
  const started = new Date('2030-01-01T00:00:00.000Z');
  const afterExpiry = new Date(started.getTime() + 2_000);
  for (const [block, recovers] of [
    [() => {}, true],
    [(api) => api.mutateAttemptIndex((index) => { index.generation = 'f'.repeat(64); }), false],
    [(api) => api.mutateAttemptIndex((index) => {
      index.owner_attempt = 'other/repo:100:1';
    }), false],
    [(api) => api.setPrHead('e'.repeat(40)), false],
    [(api) => api.setPrLabels([]), false],
    [(api) => api.setPrLabels(['agent:needs-attention', 'needs-human']), false],
  ]) {
    const api = fakeGitHub();
    const first = await beginChallenge({ request: api.request, repository, prNumber,
      defaultBranch: 'main', fingerprint, headSha, ...boundaryAt(started), now: started });
    assert.equal((await prepareChallenge({ request: api.request, repository, prNumber,
      claim: claim(first), ownerAttempt, provider: 'codex', headSha, now: started })).prepared,
    true);
    api.mutateAuthorityState((state) => { delete state.prepared_claim; });
    block(api);

    const result = await beginChallenge({ request: api.request, repository, prNumber,
      defaultBranch: 'main', fingerprint, headSha, expectedGeneration: first.generation,
      ...boundaryAt(afterExpiry), now: afterExpiry });
    if (recovers) {
      assert.equal(result.status, 'available');
      assert.notEqual(result.generation, first.generation);
    } else {
      assert.equal(result.status, 'prepared');
      assert.equal(result.generation, first.generation);
    }
  }
});

test('legacy preparation migration converges on a concurrent valid release', async () => {
  const api = fakeGitHub();
  const started = new Date('2030-01-01T00:00:00.000Z');
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundaryAt(started), now: started });
  assert.equal((await prepareChallenge({ request: api.request, repository, prNumber,
    claim: claim(first), ownerAttempt, provider: 'codex', headSha, now: started })).prepared,
  true);
  api.mutateAuthorityState((state) => { delete state.prepared_claim; });

  const winnerGeneration = 'c'.repeat(64);
  const afterExpiry = new Date(started.getTime() + 2_000);
  let raced = false;
  api.setBeforePut(() => {
    if (raced) return;
    raced = true;
    api.mutateAuthorityState((state) => {
      const releasedReceipt = state.receipt;
      state.generation = winnerGeneration;
      state.due_at = afterExpiry.toISOString();
      state.expires_at = new Date(afterExpiry.getTime() + 24 * 60 * 60 * 1000).toISOString();
      state.status = 'available';
      state.receipt = null;
      state.prepared_claim = null;
      state.released_receipt = releasedReceipt;
      state.released_generation = first.generation;
      state.released_generation_lineage = [first.generation];
      state.revision += 1;
    });
  });

  const recovered = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, expectedGeneration: first.generation,
    ...boundaryAt(afterExpiry), now: afterExpiry });
  assert.equal(recovered.status, 'available');
  assert.equal(recovered.generation, winnerGeneration);
});

test('lost preparation response remains recoverable after expiry', async () => {
  const api = fakeGitHub();
  const started = new Date('2030-01-01T00:00:00.000Z');
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundaryAt(started), now: started });
  let lost = true;
  api.setAfterPut(() => {
    if (lost) { lost = false; throw status(503); }
  });
  const uncertain = await prepareChallenge({ request: api.request, repository, prNumber,
    claim: claim(first), ownerAttempt, provider: 'codex', headSha, now: started });
  assert.equal(uncertain.reason, 'challenge-write-uncertain');
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status,
    'prepared');
  api.setAfterPut(null);

  const afterExpiry = new Date(started.getTime() + 2_000);
  const recovered = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, expectedGeneration: first.generation,
    ...boundaryAt(afterExpiry), now: afterExpiry });
  assert.equal(recovered.status, 'available');
  assert.equal(recovered.released_receipt.owner_attempt, ownerAttempt);
});

test('expired preparation stays fail-closed without exact index or eligible PR evidence', async () => {
  const started = new Date('2030-01-01T00:00:00.000Z');
  const afterExpiry = new Date(started.getTime() + 2_000);
  for (const block of [
    (api) => api.deleteAttemptIndex(),
    (api) => api.corruptAttemptIndex(),
    (api) => api.setPrHead('e'.repeat(40)),
    (api) => api.setPrLabels(['agent:needs-attention', 'needs-human']),
    (api) => api.setPrState('closed'),
    (api) => api.setPrUnavailable(true),
  ]) {
    const api = fakeGitHub();
    const first = await beginChallenge({ request: api.request, repository, prNumber,
      defaultBranch: 'main', fingerprint, headSha, ...boundaryAt(started), now: started });
    assert.equal((await prepareChallenge({ request: api.request, repository, prNumber,
      claim: claim(first), ownerAttempt, provider: 'codex', headSha, now: started })).prepared,
    true);
    block(api);
    const preserved = await beginChallenge({ request: api.request, repository, prNumber,
      defaultBranch: 'main', fingerprint, headSha, expectedGeneration: first.generation,
      ...boundaryAt(afterExpiry), now: afterExpiry });
    assert.equal(preserved.status, 'prepared');
    assert.equal(preserved.generation, first.generation);
  }
});

test('expired preparation stays fail-closed when its persisted claim is inconsistent', async () => {
  const api = fakeGitHub();
  const started = new Date('2030-01-01T00:00:00.000Z');
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundaryAt(started), now: started });
  assert.equal((await prepareChallenge({ request: api.request, repository, prNumber,
    claim: claim(first), ownerAttempt, provider: 'codex', headSha, now: started })).prepared,
  true);
  api.mutateAuthorityState((state) => { state.prepared_claim.due_at = first.expires_at; });
  const afterExpiry = new Date(started.getTime() + 2_000);
  const preserved = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, expectedGeneration: first.generation,
    ...boundaryAt(afterExpiry), now: afterExpiry });
  assert.equal(preserved.status, 'prepared');
  assert.equal(preserved.generation, first.generation);
});

test('finalization winning the expired-preparation race preserves the consumed receipt', async () => {
  const api = fakeGitHub();
  const started = new Date('2030-01-01T00:00:00.000Z');
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundaryAt(started), now: started });
  const options = { request: api.request, repository, prNumber, claim: claim(first),
    ownerAttempt, provider: 'codex', headSha, now: started };
  assert.equal((await prepareChallenge(options)).prepared, true);
  api.setBeforePut(async () => {
    api.setBeforePut(null);
    assert.equal((await finalizeChallenge(options)).granted, true);
  });
  const afterExpiry = new Date(started.getTime() + 2_000);
  const settled = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, expectedGeneration: first.generation,
    ...boundaryAt(afterExpiry), now: afterExpiry });
  assert.equal(settled.status, 'consumed');
  assert.equal(settled.generation, first.generation);
});

test('expired prepared release creates a fresh due window without refunding its attempt', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundary() });
  const signed = claim(first);
  const options = { request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha };
  assert.equal((await prepareChallenge(options)).prepared, true);
  api.expireChallenge();
  const released = await reconcileFailedAuthorityAttempt({
    request: api.request, repository, prNumber, ownerAttempt, workerEvidence: 'not-started',
  });
  assert.equal(released.status, 'released');
  assert.notEqual(released.state.generation, first.generation);
  assert.equal(released.state.released_generation, first.generation);
  assert.deepEqual(released.previousGenerations, [first.generation]);
  assert.ok(Date.parse(released.state.expires_at) > Date.now());
  const replay = await reconcileFailedAuthorityAttempt({
    request: api.request, repository, prNumber, ownerAttempt, workerEvidence: 'not-started',
  });
  assert.equal(replay.state.generation, released.state.generation);
  assert.equal(replay.state.revision, released.state.revision);
  assert.equal((await prepareChallenge(options)).prepared, false);
});

test('expired earlier release refreshes once and retains the original receipt lineage', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundary() });
  const signed = claim(first);
  const options = { request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha };
  assert.equal((await prepareChallenge(options)).prepared, true);
  assert.equal((await releasePreparedChallenge(options)).released, true);
  api.expireChallenge();
  const refreshed = await reconcileFailedAuthorityAttempt({
    request: api.request, repository, prNumber, ownerAttempt, workerEvidence: 'not-started',
  });
  assert.equal(refreshed.status, 'released');
  assert.notEqual(refreshed.state.generation, first.generation);
  assert.equal(refreshed.state.released_generation, first.generation);
  assert.deepEqual(refreshed.previousGenerations, [first.generation]);
  api.expireChallenge();
  const twice = await reconcileFailedAuthorityAttempt({
    request: api.request, repository, prNumber, ownerAttempt, workerEvidence: 'not-started',
  });
  assert.equal(twice.status, 'released');
  assert.deepEqual(twice.previousGenerations, [first.generation, refreshed.state.generation]);
  assert.equal((await releasePreparedChallenge(options)).released, true);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.generation,
    twice.state.generation);
});

test('expired preparation cannot rotate while the exact-head PR has a human blocker', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundary() });
  const options = { request: api.request, repository, prNumber, claim: claim(first),
    ownerAttempt, provider: 'codex', headSha };
  assert.equal((await prepareChallenge(options)).prepared, true);
  api.expireChallenge();
  api.setPrLabels(['agent:needs-attention', 'needs-human']);
  assert.equal((await releasePreparedChallenge(options)).released, false);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'prepared');
});

test('lost response after expired release is accepted only from settled exact ledger state', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundary() });
  const options = { request: api.request, repository, prNumber, claim: claim(first),
    ownerAttempt, provider: 'codex', headSha };
  assert.equal((await prepareChallenge(options)).prepared, true);
  api.expireChallenge();
  let lost = false;
  api.setAfterPut(async () => {
    if (!lost) { lost = true; throw status(503); }
  });
  const release = await releasePreparedChallenge(options);
  assert.equal(release.released, true);
  const settled = await readAuthorityState(api.request, repository, prNumber);
  assert.equal(settled.state.status, 'available');
  assert.notEqual(settled.state.generation, first.generation);
  assert.equal((await releasePreparedChallenge(options)).released, true);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.revision,
    settled.state.revision);
});

test('a generation is never reused for a different originating head', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const changedHead = 'e'.repeat(40);
  const second = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha: changedHead, expectedGeneration: first.generation, ...boundary(),
  });
  assert.notEqual(second.generation, first.generation);
  assert.equal(second.head_sha, changedHead);
});

test('head changed during consumption spends receipt but denies grant', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  api.setAfterPut(async () => api.setPrHead('e'.repeat(40)));
  const result = await consumeChallenge({
    request: api.request, repository, prNumber, claim: claim(state),
    ownerAttempt, provider: 'codex', headSha,
  });
  assert.equal(result.granted, false);
  assert.equal(result.reason, 'challenge-pr-state-changed');
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'consumed');
});

test('head changed before the ledger PUT still denies the grant', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  api.setBeforePut(async () => api.setPrHead('e'.repeat(40)));
  const result = await consumeChallenge({
    request: api.request, repository, prNumber, claim: claim(state),
    ownerAttempt, provider: 'codex', headSha,
  });
  assert.equal(result.granted, false);
  assert.equal(result.reason, 'challenge-pr-state-changed');
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'consumed');
});

test('routing label changed during consumption denies the grant', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  api.setAfterPut(async () => api.setPrLabels(['needs-human']));
  const result = await consumeChallenge({
    request: api.request, repository, prNumber, claim: claim(state),
    ownerAttempt, provider: 'codex', headSha,
  });
  assert.equal(result.granted, false);
  assert.equal(result.reason, 'challenge-pr-state-changed');
});

test('head changed during confirmation never reports trusted confirmation', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const signed = claim(state);
  assert.equal((await consumeChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  })).granted, true);
  api.setPrLabels(['needs-human']);
  api.setAfterPut(async () => api.setPrHead('e'.repeat(40)));
  assert.equal(await confirmChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  }), false);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'confirmed');
  assert.equal(await confirmChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  }), false);
  assert.equal((await reopenUnconfirmedChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  })).status, 'uncertain');
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'confirmed');
});

test('reconciliation rejects a replacement available head before reading its null receipt', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const changedHead = 'e'.repeat(40);
  const replacement = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha: changedHead, expectedGeneration: first.generation, ...boundary(),
  });
  assert.equal(replacement.status, 'available');
  assert.equal(replacement.receipt, null);
  const result = await reopenUnconfirmedChallenge({
    request: api.request, repository, prNumber, claim: claim(first),
    ownerAttempt, provider: 'codex', headSha,
  });
  assert.equal(result.status, 'uncertain');
  assert.equal(result.state.head_sha, changedHead);
});

test('workflow reporter reopens with the persisted claim and failed run identity', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const signed = claim(state);
  assert.equal((await consumeChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  })).granted, true);
  assert.deepEqual(
    (await readAuthorityState(api.request, repository, prNumber)).state.consumed_claim,
    signed,
  );

  assert.equal((await reopenUnconfirmedChallenge({
    request: api.request, repository, prNumber, claim: null,
    ownerAttempt: 'owner/repo:101:1', provider: 'codex', headSha,
  })).status, 'uncertain');
  assert.equal((await reopenUnconfirmedChallenge({
    request: api.request, repository, prNumber, claim: null,
    ownerAttempt, provider: 'codex', headSha,
  })).status, 'uncertain');
  const reopened = await reopenUnconfirmedChallenge({
    request: api.request, repository, prNumber, claim: null,
    ownerAttempt, provider: 'codex', headSha, workerEvidence: 'not-started',
  });
  assert.equal(reopened.status, 'reopened');
  assert.equal(reopened.state.consumed_claim, null);
});

test('failed-run reconciliation is independent of summary state and requires positive non-start', async () => {
  const api = fakeGitHub();
  assert.equal(await findAuthorityPrForAttempt({ request: api.request, repository, ownerAttempt }), null);
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const signed = claim(state);
  assert.equal((await prepareChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  })).prepared, true);
  const args = { request: api.request, repository, prNumber, ownerAttempt };
  assert.equal((await reconcileFailedAuthorityAttempt({
    ...args, workerEvidence: 'unknown',
  })).status, 'execution-not-disproved');
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'prepared');
  assert.equal((await reconcileFailedAuthorityAttempt({
    ...args, ownerAttempt: 'owner/repo:101:1', workerEvidence: 'not-started',
  })).status, 'attempt-not-current');
  const released = await reconcileFailedAuthorityAttempt({
    ...args, workerEvidence: 'not-started',
  });
  assert.equal(released.status, 'released');
  assert.equal(released.state.status, 'available');
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'available');
  const target = await findAuthorityPrForAttempt({
    request: api.request, repository, ownerAttempt,
  });
  assert.equal(target.prNumber, prNumber);
  assert.equal(target.state.status, 'available');
});

test('a corrupted direct attempt index denies finalization and missing-PR recovery', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const signed = claim(state);
  const args = { request: api.request, repository, prNumber,
    claim: signed, ownerAttempt, provider: 'codex', headSha };
  assert.equal((await prepareChallenge(args)).prepared, true);
  api.corruptAttemptIndex();
  assert.equal((await finalizeChallenge(args)).reason, 'attempt-index-unavailable');
  await assert.rejects(findAuthorityPrForAttempt({
    request: api.request, repository, ownerAttempt,
  }), /Malformed authority attempt index/);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'prepared');
});

test('lost index-create response denies this preparation but permits exact later retry', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const args = { request: api.request, repository, prNumber,
    claim: claim(state), ownerAttempt, provider: 'codex', headSha };
  api.setAfterIndexPut(() => { throw status(503); });
  assert.equal((await prepareChallenge(args)).reason, 'attempt-index-uncertain');
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'available');
  api.setAfterIndexPut(null);
  assert.equal((await prepareChallenge(args)).prepared, true);
  assert.equal((await finalizeChallenge(args)).granted, true);
});

test('consumed receipt only reopens for its exact attempt with a proven unstarted worker', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  assert.equal((await consumeChallenge({
    request: api.request, repository, prNumber, claim: claim(state),
    ownerAttempt, provider: 'codex', headSha,
  })).granted, true);
  const args = { request: api.request, repository, prNumber, ownerAttempt };
  assert.equal((await reconcileFailedAuthorityAttempt({
    ...args, workerEvidence: 'started',
  })).status, 'execution-not-disproved');
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'consumed');
  assert.equal((await reconcileFailedAuthorityAttempt({
    ...args, workerEvidence: 'not-started',
  })).status, 'reopened');
});

test('recovered retry revalidates PR state and refreshes an expired window', async () => {
  async function recoveredApi() {
    const api = fakeGitHub();
    const first = await beginChallenge({
      request: api.request, repository, prNumber, defaultBranch: 'main',
      fingerprint, headSha, ...boundary(),
    });
    assert.equal((await consumeChallenge({
      request: api.request, repository, prNumber, claim: claim(first),
      ownerAttempt, provider: 'codex', headSha,
    })).granted, true);
    const recovered = await reconcileFailedAuthorityAttempt({
      request: api.request, repository, prNumber, ownerAttempt,
      workerEvidence: 'not-started',
    });
    assert.equal(recovered.status, 'reopened');
    return { api, first, recovered };
  }

  const { api, first, recovered } = await recoveredApi();
  const stable = await reconcileFailedAuthorityAttempt({
    request: api.request, repository, prNumber, ownerAttempt,
    workerEvidence: 'not-started',
  });
  assert.equal(stable.status, 'reopened');
  assert.equal(stable.reason, 'already-current');
  assert.equal(stable.state.generation, recovered.state.generation);
  assert.equal(stable.state.revision, recovered.state.revision);

  api.expireChallenge();
  const refreshed = await reconcileFailedAuthorityAttempt({
    request: api.request, repository, prNumber, ownerAttempt,
    workerEvidence: 'not-started',
  });
  assert.equal(refreshed.status, 'reopened');
  assert.equal(refreshed.reason, 'recovered-window-refreshed');
  assert.notEqual(refreshed.state.generation, recovered.state.generation);
  assert.equal(refreshed.state.recovered_generation, first.generation);
  assert.deepEqual(refreshed.state.recovered_generation_lineage,
    [first.generation, recovered.state.generation]);
  assert.equal(refreshed.state.revision, recovered.state.revision + 1);
  assert.equal(refreshed.state.recovered_receipt.id, recovered.state.recovered_receipt.id);
  assert.ok(Date.parse(refreshed.state.expires_at) > Date.now());

  for (const block of [
    (candidate) => candidate.setPrHead('e'.repeat(40)),
    (candidate) => candidate.setPrLabels([]),
    (candidate) => candidate.setPrLabels(['agent:needs-attention', 'needs-human']),
    (candidate) => candidate.setPrState('closed'),
    (candidate) => candidate.setPrUnavailable(true),
    (candidate) => candidate.deleteAttemptIndex(),
    (candidate) => candidate.corruptAttemptIndex(),
    (candidate) => candidate.mutateAttemptIndex((index) => {
      index.generation = 'f'.repeat(64);
    }),
  ]) {
    const candidate = await recoveredApi();
    const before = candidate.api.content;
    block(candidate.api);
    const denied = await reconcileFailedAuthorityAttempt({
      request: candidate.api.request, repository, prNumber, ownerAttempt,
      workerEvidence: 'not-started',
    });
    assert.equal(denied.status, 'uncertain');
    assert.equal(candidate.api.content, before);
  }
});

test('recovered window refresh settles an exact committed write after response loss', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  assert.equal((await consumeChallenge({
    request: api.request, repository, prNumber, claim: claim(first),
    ownerAttempt, provider: 'codex', headSha,
  })).granted, true);
  const args = { request: api.request, repository, prNumber, ownerAttempt,
    workerEvidence: 'not-started' };
  assert.equal((await reconcileFailedAuthorityAttempt(args)).status, 'reopened');
  api.expireChallenge();
  let lost = true;
  api.setAfterPut(() => {
    if (lost) { lost = false; throw status(503); }
  });
  const settled = await reconcileFailedAuthorityAttempt(args);
  assert.equal(settled.status, 'reopened');
  assert.equal(settled.reason, 'recovered-window-refreshed');
  api.setAfterPut(null);

  api.expireChallenge();
  api.setBeforePut(() => { throw status(503); });
  const uncertain = await reconcileFailedAuthorityAttempt(args);
  assert.equal(uncertain.status, 'uncertain');
  assert.equal(uncertain.reason, 'recovered-window-write-uncertain');
});

test('unavailable PR read after confirmation preserves the confirmed challenge', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const signed = claim(state);
  assert.equal((await consumeChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  })).granted, true);
  api.setPrLabels(['needs-human']);
  api.setAfterPut(async () => api.setPrUnavailable(true));
  await assert.rejects(confirmChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  }), /HTTP 503/);
  await assert.rejects(reopenUnconfirmedChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  }), /HTTP 503/);
  api.setPrUnavailable(false);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'confirmed');
});

test('confirmed receipt never reopens after a same-head hard label removal', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const signed = claim(state);
  assert.equal((await consumeChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  })).granted, true);
  api.setPrLabels(['needs-human']);
  assert.equal(await confirmChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  }), true);
  api.setPrLabels(['agent:needs-attention']);
  const recovered = await reopenUnconfirmedChallenge({
    request: api.request, repository, prNumber, claim: signed,
    ownerAttempt, provider: 'codex', headSha,
  });
  assert.equal(recovered.status, 'uncertain');
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'confirmed');
});

test('expired consumed generation cannot be replaced without positive non-start', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const consumed = await consumeChallenge({
    request: api.request, repository, prNumber, claim: claim(first),
    ownerAttempt, provider: 'codex', headSha,
  });
  assert.equal(consumed.granted, true);
  api.expireChallenge();
  const replacement = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, expectedGeneration: first.generation, ...boundary(),
  });
  assert.equal(replacement.status, 'consumed');
  assert.equal(replacement.generation, first.generation);
});

test('expired confirmed generation cannot be reopened by initialization', async () => {
  const api = fakeGitHub();
  const first = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, ...boundary() });
  const signed = claim(first);
  assert.equal((await consumeChallenge({ request: api.request, repository, prNumber,
    claim: signed, ownerAttempt, provider: 'codex', headSha })).granted, true);
  api.setPrLabels(['agent:needs-attention', 'needs-human']);
  assert.equal(await confirmChallenge({ request: api.request, repository, prNumber,
    claim: signed, ownerAttempt, provider: 'codex', headSha }), true);
  api.expireChallenge();
  const after = await beginChallenge({ request: api.request, repository, prNumber,
    defaultBranch: 'main', fingerprint, headSha, expectedGeneration: first.generation, ...boundary() });
  assert.equal(after.status, 'confirmed');
  assert.equal(after.generation, first.generation);
});

test('two racing consumers produce at most one grant through the conditional SHA', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  let waiting = 0;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  api.setBeforePut(async () => {
    waiting += 1;
    if (waiting === 2) release();
    await gate;
  });
  const results = await Promise.all([100, 101].map((run) => consumeChallenge({
    request: api.request, repository, prNumber, claim: claim(state),
    ownerAttempt: `owner/repo:${run}:1`, provider: 'codex', headSha,
  })));
  assert.equal(results.filter((result) => result.granted).length, 1);
  assert.equal((await readAuthorityState(api.request, repository, prNumber)).state.status, 'consumed');
});

test('ambiguous write consumes if it landed but never grants a second execution', async () => {
  const api = fakeGitHub();
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  let failOnce = true;
  api.setAfterPut(async () => {
    if (failOnce) {
      failOnce = false;
      throw status(503);
    }
  });
  const first = await consumeChallenge({
    request: api.request, repository, prNumber, claim: claim(state),
    ownerAttempt, provider: 'codex', headSha,
  });
  assert.equal(first.granted, false);
  const second = await consumeChallenge({
    request: api.request, repository, prNumber, claim: claim(state),
    ownerAttempt: 'owner/repo:101:1', provider: 'codex', headSha,
  });
  assert.equal(second.granted, false);
});

test('missing or corrupt authoritative state never grants', async () => {
  const api = fakeGitHub();
  await assert.rejects(readAuthorityState(api.request, repository, prNumber));
  await assert.rejects(beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, expectedGeneration: 'c'.repeat(64), ...boundary(),
  }), /previously initialized/i);
  const state = await beginChallenge({
    request: api.request, repository, prNumber, defaultBranch: 'main',
    fingerprint, headSha, ...boundary(),
  });
  const stale = { ...claim(state), generation: 'f'.repeat(64) };
  assert.equal((await consumeChallenge({
    request: api.request, repository, prNumber, claim: stale,
    ownerAttempt, provider: 'codex', headSha,
  })).granted, false);
});
