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
  reconcileFailedAuthorityAttempt,
  releasePreparedChallenge,
  reopenUnconfirmedChallenge,
} = require('../keepalive_authority_state');

const repository = 'owner/repo';
const prNumber = 42;
const fingerprint = 'a'.repeat(64);
const headSha = 'd'.repeat(40);
const ownerAttempt = 'owner/repo:100:1';

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
