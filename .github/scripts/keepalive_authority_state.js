'use strict';

// This branch is the authority for challenge generations and receipts. PR comments
// are presentation only: a comment PATCH cannot provide a conditional write.
const crypto = require('node:crypto');
const BRANCH = 'keepalive-authority-state';
const HEX = /^[0-9a-f]{64}$/;
const HEAD = /^[0-9a-f]{40}$/;
const ATTEMPT = /^[a-z0-9_.-]+\/[a-z0-9_.-]+:\d+:\d+$/;

function exactTime(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value)) return false;
  return Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}

function validState(state, repository, prNumber) {
  return state && state.version === 2 &&
    state.repository === String(repository).toLowerCase() &&
    state.pr_number === Number(prNumber) &&
    HEX.test(state.generation) && HEX.test(state.boundary_fingerprint) &&
    exactTime(state.due_at) && exactTime(state.expires_at) &&
    Date.parse(state.expires_at) > Date.parse(state.due_at) &&
    Number.isSafeInteger(state.revision) && state.revision >= 1 &&
    ['available', 'consumed', 'confirmed'].includes(state.status) &&
    (state.status === 'available' ? state.receipt === null :
      validReceipt(state.receipt));
}

function validReceipt(receipt) {
  return receipt && HEX.test(receipt.id) && HEX.test(receipt.claim_digest) &&
    ATTEMPT.test(receipt.owner_attempt) && HEAD.test(receipt.head_sha) &&
    typeof receipt.provider === 'string' && /^[a-z][a-z0-9_-]*$/.test(receipt.provider) &&
    exactTime(receipt.consumed_at);
}

function pathFor(repository, prNumber) {
  if (!/^[a-z0-9_.-]+\/[a-z0-9_.-]+$/i.test(String(repository)) ||
      !Number.isSafeInteger(Number(prNumber)) || Number(prNumber) < 1) {
    throw new Error('Invalid challenge repository or PR number');
  }
  return `/repos/${String(repository).toLowerCase()}/contents/.github/keepalive-authority/${Number(prNumber)}.json`;
}

async function fetchRequest(method, path, body, token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN) {
  if (!token) throw new Error('Authority state token unavailable');
  const response = await fetch(`https://api.github.com${path}`, {
    method,
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const error = new Error(`GitHub authority state ${method} failed: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function requestWithOctokit(github, method, path, body) {
  try {
    const response = await github.request(`${method} ${path}`, body || {});
    return response.data;
  } catch (error) {
    error.status = error.status || error.response?.status;
    throw error;
  }
}

function requester(github) {
  return github
    ? (method, path, body) => requestWithOctokit(github, method, path, body)
    : fetchRequest;
}

async function ensureBranch(request, repository, defaultBranch) {
  const repo = String(repository).toLowerCase();
  try {
    await request('GET', `/repos/${repo}/git/ref/heads/${BRANCH}`);
    return;
  } catch (error) {
    if (error.status !== 404) throw error;
  }
  const base = await request('GET', `/repos/${repo}/git/ref/heads/${encodeURIComponent(defaultBranch)}`);
  const sha = base?.object?.sha;
  if (!/^[0-9a-f]{40}$/.test(String(sha))) throw new Error('Default branch SHA unavailable');
  try {
    await request('POST', `/repos/${repo}/git/refs`, { ref: `refs/heads/${BRANCH}`, sha });
  } catch (error) {
    // Another PR may have initialized the shared branch concurrently.
    if (![409, 422].includes(error.status)) throw error;
    await request('GET', `/repos/${repo}/git/ref/heads/${BRANCH}`);
  }
}

async function readAuthorityState(request, repository, prNumber, { allowMissing = false } = {}) {
  let file;
  try {
    file = await request('GET', `${pathFor(repository, prNumber)}?ref=${BRANCH}`);
  } catch (error) {
    if (allowMissing && error.status === 404) return null;
    throw error;
  }
  let state;
  try {
    if (!/^[0-9a-f]{40}$/.test(String(file?.sha)) || file?.encoding !== 'base64') {
      throw new Error('Invalid authority file metadata');
    }
    state = JSON.parse(Buffer.from(String(file.content).replace(/\s/g, ''), 'base64').toString('utf8'));
  } catch (error) {
    throw new Error(`Malformed authoritative challenge state: ${error.message}`);
  }
  if (!validState(state, repository, prNumber)) throw new Error('Invalid authoritative challenge state');
  return { state, sha: file.sha };
}

async function writeAuthorityState(request, repository, prNumber, state, priorSha) {
  if (!validState(state, repository, prNumber)) throw new Error('Refusing invalid authoritative challenge state');
  const body = {
    branch: BRANCH,
    message: `keepalive authority PR #${Number(prNumber)} revision ${state.revision}`,
    content: Buffer.from(`${JSON.stringify(state)}\n`).toString('base64'),
    ...(priorSha ? { sha: priorSha } : {}),
  };
  return request('PUT', pathFor(repository, prNumber), body);
}

async function beginChallenge({ request, repository, prNumber, defaultBranch, fingerprint, dueAt, expiresAt, expectedGeneration = null }) {
  if (!HEX.test(String(fingerprint)) || !exactTime(dueAt) || !exactTime(expiresAt) ||
      Date.parse(expiresAt) <= Date.parse(dueAt)) throw new Error('Invalid challenge boundary');
  await ensureBranch(request, repository, defaultBranch);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const prior = await readAuthorityState(request, repository, prNumber, { allowMissing: true });
    if (expectedGeneration && (!prior || prior.state.generation !== expectedGeneration)) {
      throw new Error('Previously initialized challenge generation is missing or superseded');
    }
    if (prior && prior.state.boundary_fingerprint === fingerprint &&
        (['consumed', 'confirmed'].includes(prior.state.status) ||
          (prior.state.status === 'available' && Date.parse(prior.state.expires_at) > Date.now()))) {
      return prior.state;
    }
    const state = {
      version: 2,
      repository: String(repository).toLowerCase(),
      pr_number: Number(prNumber),
      generation: crypto.randomBytes(32).toString('hex'),
      boundary_fingerprint: fingerprint,
      due_at: dueAt,
      expires_at: expiresAt,
      status: 'available',
      receipt: null,
      revision: (prior?.state.revision || 0) + 1,
    };
    try {
      await writeAuthorityState(request, repository, prNumber, state, prior?.sha);
      return state;
    } catch (error) {
      if (![409, 422].includes(error.status)) throw error;
    }
  }
  throw new Error('Concurrent challenge generation updates did not settle');
}

function claimMatchesState(claim, state, now = new Date()) {
  return state.status === 'available' &&
    claim.generation === state.generation &&
    claim.boundary_fingerprint === state.boundary_fingerprint &&
    claim.due_at === state.due_at && claim.expires_at === state.expires_at &&
    Number.isFinite(now.getTime()) && Date.parse(state.due_at) <= now.getTime() &&
    now.getTime() < Date.parse(state.expires_at);
}

async function consumeChallenge({ request, repository, prNumber, claim, ownerAttempt, provider, headSha, now = new Date() }) {
  const prior = await readAuthorityState(request, repository, prNumber);
  if (!claimMatchesState(claim, prior.state, now) || !ATTEMPT.test(String(ownerAttempt)) ||
      !HEAD.test(String(headSha)) || claim.head_sha !== headSha) {
    return { granted: false, reason: 'challenge-not-current' };
  }
  const receipt = {
    id: crypto.randomBytes(32).toString('hex'),
    claim_digest: crypto.createHash('sha256').update(JSON.stringify(claim)).digest('hex'),
    owner_attempt: ownerAttempt,
    provider,
    head_sha: headSha,
    consumed_at: now.toISOString(),
  };
  const next = { ...prior.state, status: 'consumed', receipt, revision: prior.state.revision + 1 };
  try {
    await writeAuthorityState(request, repository, prNumber, next, prior.sha);
  } catch (error) {
    // A conflict or an ambiguous write never grants an execution. If the write
    // actually landed, its receipt stays consumed for every later attempt.
    return { granted: false, reason: [409, 422].includes(error.status) ? 'challenge-conflict' : 'challenge-write-uncertain' };
  }
  return { granted: true, reason: 'due-authority-challenge', receipt };
}

async function confirmChallenge({ request, repository, prNumber, claim, ownerAttempt, provider, headSha }) {
  const prior = await readAuthorityState(request, repository, prNumber);
  const receipt = prior.state.receipt;
  if (prior.state.status !== 'consumed' || !receipt ||
      Date.now() >= Date.parse(prior.state.expires_at) ||
      prior.state.generation !== claim.generation ||
      prior.state.boundary_fingerprint !== claim.boundary_fingerprint ||
      prior.state.due_at !== claim.due_at || prior.state.expires_at !== claim.expires_at ||
      receipt.claim_digest !== crypto.createHash('sha256').update(JSON.stringify(claim)).digest('hex') ||
      receipt.owner_attempt !== ownerAttempt || receipt.provider !== provider ||
      receipt.head_sha !== headSha) return false;
  const pr = await request('GET', `/repos/${String(repository).toLowerCase()}/pulls/${Number(prNumber)}`);
  const labels = new Set((pr?.labels || []).map((label) => String(label.name || '').toLowerCase()));
  if (pr?.state !== 'open' || pr?.head?.sha !== headSha ||
      !labels.has('agent:needs-attention') || labels.has('needs-human')) return false;
  const next = { ...prior.state, status: 'confirmed', revision: prior.state.revision + 1 };
  try {
    await writeAuthorityState(request, repository, prNumber, next, prior.sha);
    return true;
  } catch (_) {
    return false;
  }
}

module.exports = {
  BRANCH,
  beginChallenge,
  claimMatchesState,
  confirmChallenge,
  consumeChallenge,
  readAuthorityState,
  requester,
  validState,
};

if (require.main === module) {
  (async () => {
    if (process.argv[2] !== 'consume') throw new Error('Unsupported authority state command');
    const { verifyAuthorityChallengeEnvelope } = require('./keepalive_challenge_due');
    const repository = String(process.env.GITHUB_REPOSITORY || '').toLowerCase();
    const prNumber = Number(process.env.AUTHORITY_PR_NUMBER || '');
    const headSha = String(process.env.AUTHORITY_HEAD_SHA || '').toLowerCase();
    const provider = String(process.env.AUTHORITY_PROVIDER || '').toLowerCase();
    const claimJson = process.env.AUTHORITY_CHALLENGE_CLAIM;
    const ownerAttempt = `${repository}:${process.env.GITHUB_RUN_ID || ''}:${process.env.GITHUB_RUN_ATTEMPT || ''}`;
    const verified = verifyAuthorityChallengeEnvelope({
      claimJson,
      signingKey: process.env.AUTHORITY_CHALLENGE_SIGNING_KEY,
      repository,
      prNumber,
      boundaryFingerprint: process.env.AUTHORITY_CHALLENGE_FINGERPRINT,
      headSha,
    });
    if (!verified || !ATTEMPT.test(ownerAttempt) ||
        process.env.GITHUB_EVENT_NAME !== 'workflow_dispatch' ||
        process.env.GITHUB_ACTOR !== 'github-actions[bot]') {
      process.stdout.write(JSON.stringify({ granted: false, reason: 'invalid-signed-challenge' }));
      return;
    }
    const request = requester();
    const pr = await request('GET', `/repos/${repository}/pulls/${prNumber}`);
    const labels = new Set((pr?.labels || []).map((label) => String(label.name || '').toLowerCase()));
    if (pr?.state !== 'open' || pr?.head?.sha !== headSha ||
        !labels.has('agent:needs-attention') || labels.has('needs-human')) {
      process.stdout.write(JSON.stringify({ granted: false, reason: 'challenge-pr-state-changed' }));
      return;
    }
    const claim = JSON.parse(claimJson);
    const result = await consumeChallenge({
      request, repository, prNumber, claim: {
        generation: claim.generation,
        boundary_fingerprint: process.env.AUTHORITY_CHALLENGE_FINGERPRINT,
        due_at: claim.due_at,
        expires_at: claim.expires_at,
        head_sha: claim.head_sha,
        nonce: claim.nonce,
        sweep_run_id: claim.sweep_run_id,
        sweep_run_attempt: claim.sweep_run_attempt,
      }, ownerAttempt, provider, headSha,
    });
    process.stdout.write(JSON.stringify(result));
  })().catch((error) => {
    process.stderr.write(`Authority challenge unavailable: ${error.message}\n`);
    process.stdout.write(JSON.stringify({ granted: false, reason: 'authority-state-unavailable' }));
  });
}
