'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const {
  beginChallenge,
  confirmChallenge,
  consumeChallenge,
  finalizeChallenge,
  prepareChallenge,
  readAuthorityState,
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
  let beforePut = null;
  let afterPut = null;
  let prHead = headSha;
  let prLabels = ['agent:needs-attention'];
  let prUnavailable = false;
  const request = async (method, path, body) => {
    if (path.includes('/git/ref/heads/main') && method === 'GET') {
      return { object: { sha: '1'.repeat(40) } };
    }
    if (path.endsWith('/pulls/42') && method === 'GET') {
      if (prUnavailable) throw status(503);
      return { state: 'open', head: { sha: prHead }, labels: prLabels.map((name) => ({ name })) };
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
    setPrHead(sha) { prHead = sha; },
    setPrLabels(labels) { prLabels = labels; },
    setPrUnavailable(value) { prUnavailable = value; },
    expireChallenge() {
      const state = JSON.parse(Buffer.from(content, 'base64').toString('utf8'));
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

test('expired consumed generation can be replaced after confirmation was omitted', async () => {
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
  assert.equal(replacement.status, 'available');
  assert.notEqual(replacement.generation, first.generation);
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
