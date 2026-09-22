'use strict';

// This branch is the authority for challenge generations and receipts. PR comments
// are presentation only: a comment PATCH cannot provide a conditional write.
const crypto = require('node:crypto');
const { withRetry } = require('./github-api-with-retry.js');
const BRANCH = 'keepalive-authority-state';
const HEX = /^[0-9a-f]{64}$/;
const HEAD = /^[0-9a-f]{40}$/;
const ATTEMPT = /^[a-z0-9_.-]+\/[a-z0-9_.-]+:\d+:\d+$/;

function exactTime(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value)) return false;
  return Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}

function validState(state, repository, prNumber, { allowLegacyHead = false } = {}) {
  return state && state.version === 2 &&
    state.repository === String(repository).toLowerCase() &&
    state.pr_number === Number(prNumber) &&
    HEX.test(state.generation) && HEX.test(state.boundary_fingerprint) &&
    exactTime(state.due_at) && exactTime(state.expires_at) &&
    Date.parse(state.expires_at) > Date.parse(state.due_at) &&
    (HEAD.test(state.head_sha) || (allowLegacyHead && state.head_sha === undefined)) &&
    Number.isSafeInteger(state.revision) && state.revision >= 1 &&
    ['available', 'prepared', 'consumed', 'confirmed'].includes(state.status) &&
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

async function requestWithOctokit(github, method, path, body) {
  try {
    // Writes are conditional and intentionally get no automatic retry. An
    // uncertain result must deny the grant even if GitHub committed the write.
    const response = await withRetry(
      (client) => client.request(`${method} ${path}`, body || {}),
      { github, maxRetries: method === 'GET' ? 2 : 0,
        tokenRegistry: null, task: 'keepalive-authority-state' },
    );
    return response.data;
  } catch (error) {
    error.status = error.status || error.response?.status;
    throw error;
  }
}

function requester(github) {
  if (!github) {
    const token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
    if (!token) throw new Error('Authority state token unavailable');
    const { Octokit } = require('@octokit/rest');
    github = new Octokit({ auth: token });
  }
  return (method, path, body) => requestWithOctokit(github, method, path, body);
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
  if (!validState(state, repository, prNumber, { allowLegacyHead: true })) {
    throw new Error('Invalid authoritative challenge state');
  }
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

async function beginChallenge({ request, repository, prNumber, defaultBranch, fingerprint, dueAt, expiresAt, headSha, expectedGeneration = null }) {
  if (!HEX.test(String(fingerprint)) || !HEAD.test(String(headSha)) ||
      !exactTime(dueAt) || !exactTime(expiresAt) ||
      Date.parse(expiresAt) <= Date.parse(dueAt)) throw new Error('Invalid challenge boundary');
  await ensureBranch(request, repository, defaultBranch);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const prior = await readAuthorityState(request, repository, prNumber, { allowMissing: true });
    if (expectedGeneration && (!prior || prior.state.generation !== expectedGeneration)) {
      throw new Error('Previously initialized challenge generation is missing or superseded');
    }
    if (prior && prior.state.boundary_fingerprint === fingerprint &&
        prior.state.head_sha === headSha) {
      if (Date.parse(prior.state.expires_at) > Date.now()) {
        return prior.state;
      }
    }
    const state = {
      version: 2,
      repository: String(repository).toLowerCase(),
      pr_number: Number(prNumber),
      generation: crypto.randomBytes(32).toString('hex'),
      boundary_fingerprint: fingerprint,
      head_sha: headSha,
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
    claim.head_sha === state.head_sha &&
    Number.isFinite(now.getTime()) && Date.parse(state.due_at) <= now.getTime() &&
    now.getTime() < Date.parse(state.expires_at);
}

async function prepareChallenge({ request, repository, prNumber, claim, ownerAttempt, provider, headSha, now = new Date() }) {
  const prior = await readAuthorityState(request, repository, prNumber);
  if (!claimMatchesState(claim, prior.state, now) || !ATTEMPT.test(String(ownerAttempt)) ||
      !HEAD.test(String(headSha)) || claim.head_sha !== headSha) {
    return { prepared: false, reason: 'challenge-not-current' };
  }
  const receipt = {
    id: crypto.randomBytes(32).toString('hex'),
    claim_digest: crypto.createHash('sha256').update(JSON.stringify(claim)).digest('hex'),
    owner_attempt: ownerAttempt,
    provider,
    head_sha: headSha,
    consumed_at: now.toISOString(),
  };
  const next = { ...prior.state, status: 'prepared', receipt, revision: prior.state.revision + 1 };
  try {
    await writeAuthorityState(request, repository, prNumber, next, prior.sha);
  } catch (error) {
    return { prepared: false, reason: [409, 422].includes(error.status) ? 'challenge-conflict' : 'challenge-write-uncertain' };
  }
  return { prepared: true, reason: 'challenge-prepared', receipt };
}

function receiptMatches(receipt, claim, ownerAttempt, provider, headSha) {
  return receipt &&
    receipt.claim_digest === crypto.createHash('sha256').update(JSON.stringify(claim)).digest('hex') &&
    receipt.owner_attempt === ownerAttempt && receipt.provider === provider &&
    receipt.head_sha === headSha;
}

async function finalizeChallenge({ request, repository, prNumber, claim, ownerAttempt, provider, headSha }) {
  const prior = await readAuthorityState(request, repository, prNumber);
  if (prior.state.status !== 'prepared' || prior.state.head_sha !== headSha ||
      prior.state.generation !== claim.generation ||
      !receiptMatches(prior.state.receipt, claim, ownerAttempt, provider, headSha)) {
    return { granted: false, reason: 'challenge-preparation-not-current' };
  }
  const next = { ...prior.state, status: 'consumed', revision: prior.state.revision + 1 };
  try {
    await writeAuthorityState(request, repository, prNumber, next, prior.sha);
  } catch (error) {
    return { granted: false, reason: [409, 422].includes(error.status) ? 'challenge-conflict' : 'challenge-write-uncertain' };
  }
  // The ledger is the single-use authority, but PR metadata is a separate
  // resource. Deny a grant if the head or routing labels changed during PUT.
  // The receipt remains spent even when this final read is unavailable.
  if (!await prMatches(request, repository, prNumber, headSha, 'agent:needs-attention', 'needs-human')) {
    return { granted: false, reason: 'challenge-pr-state-changed' };
  }
  return { granted: true, reason: 'due-authority-challenge', receipt: prior.state.receipt };
}

async function releasePreparedChallenge({ request, repository, prNumber, claim, ownerAttempt, provider, headSha }) {
  const prior = await readAuthorityState(request, repository, prNumber);
  if (prior.state.status !== 'prepared' || prior.state.head_sha !== headSha ||
      prior.state.generation !== claim.generation ||
      !receiptMatches(prior.state.receipt, claim, ownerAttempt, provider, headSha)) {
    return { released: false, reason: 'challenge-preparation-not-current' };
  }
  const next = { ...prior.state, status: 'available', receipt: null, revision: prior.state.revision + 1 };
  try {
    await writeAuthorityState(request, repository, prNumber, next, prior.sha);
    return { released: true, reason: 'challenge-preparation-released' };
  } catch (error) {
    return { released: false, reason: [409, 422].includes(error.status) ? 'challenge-conflict' : 'challenge-write-uncertain' };
  }
}

async function consumeChallenge(options) {
  const prepared = await prepareChallenge(options);
  if (!prepared.prepared) return { granted: false, reason: prepared.reason };
  return finalizeChallenge(options);
}

async function readPrState(request, repository, prNumber) {
  const pr = await request('GET', `/repos/${String(repository).toLowerCase()}/pulls/${Number(prNumber)}`);
  if (!pr || !Array.isArray(pr.labels) || typeof pr?.head?.sha !== 'string') {
    throw new Error('PR state response is incomplete');
  }
  const labels = new Set(pr.labels.map((label) => String(label.name || '').toLowerCase()));
  return { open: pr.state === 'open', headSha: pr.head.sha, labels };
}

async function prMatches(request, repository, prNumber, headSha, requiredLabel, excludedLabel = null) {
  const pr = await readPrState(request, repository, prNumber);
  return pr.open && pr.headSha === headSha &&
    pr.labels.has(requiredLabel) && (!excludedLabel || !pr.labels.has(excludedLabel));
}

async function confirmChallenge({ request, repository, prNumber, claim, ownerAttempt, provider, headSha }) {
  const prior = await readAuthorityState(request, repository, prNumber);
  const receipt = prior.state.receipt;
  if (!receipt ||
      Date.now() >= Date.parse(prior.state.expires_at) ||
      prior.state.generation !== claim.generation ||
      prior.state.boundary_fingerprint !== claim.boundary_fingerprint ||
      prior.state.due_at !== claim.due_at || prior.state.expires_at !== claim.expires_at ||
      prior.state.head_sha !== headSha || claim.head_sha !== headSha ||
      receipt.claim_digest !== crypto.createHash('sha256').update(JSON.stringify(claim)).digest('hex') ||
      receipt.owner_attempt !== ownerAttempt || receipt.provider !== provider ||
      receipt.head_sha !== headSha) return false;
  if (prior.state.status === 'confirmed') {
    return prMatches(request, repository, prNumber, headSha, 'needs-human');
  }
  if (prior.state.status !== 'consumed') return false;
  if (!await prMatches(request, repository, prNumber, headSha, 'needs-human')) return false;
  const next = { ...prior.state, status: 'confirmed', revision: prior.state.revision + 1 };
  try {
    await writeAuthorityState(request, repository, prNumber, next, prior.sha);
    return prMatches(request, repository, prNumber, headSha, 'needs-human');
  } catch (_) {
    const settled = await readAuthorityState(request, repository, prNumber).catch(() => null);
    return settled?.state.status === 'confirmed' &&
      settled.state.generation === claim.generation &&
      settled.state.receipt?.id === receipt.id &&
      await prMatches(request, repository, prNumber, headSha, 'needs-human');
  }
}

async function reopenUnconfirmedChallenge({ request, repository, prNumber, claim, ownerAttempt, provider, headSha }) {
  const prior = await readAuthorityState(request, repository, prNumber);
  if (prior.state.head_sha !== headSha) return { status: 'uncertain', state: prior.state };
  const receipt = prior.state.receipt;
  const matches = prior.state.generation === claim.generation &&
    prior.state.boundary_fingerprint === claim.boundary_fingerprint &&
    receipt?.claim_digest === crypto.createHash('sha256').update(JSON.stringify(claim)).digest('hex') &&
    receipt.owner_attempt === ownerAttempt && receipt.provider === provider && receipt.head_sha === headSha;
  const pr = await readPrState(request, repository, prNumber);
  if (!pr.open || pr.headSha !== headSha) return { status: 'uncertain', state: prior.state };
  if (matches && pr.labels.has('needs-human')) {
    return { status: prior.state.status === 'confirmed' ? 'confirmed' : 'uncertain', state: prior.state };
  }
  if (!matches || !['consumed', 'confirmed'].includes(prior.state.status)) {
    return { status: 'uncertain', state: prior.state };
  }
  const now = Date.now();
  const state = {
    ...prior.state,
    generation: crypto.randomBytes(32).toString('hex'),
    due_at: new Date(now).toISOString(),
    expires_at: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
    status: 'available', receipt: null, revision: prior.state.revision + 1,
  };
  try {
    await writeAuthorityState(request, repository, prNumber, state, prior.sha);
    return { status: 'reopened', state };
  } catch (_) {
    const settled = await readAuthorityState(request, repository, prNumber).catch(() => null);
    if (settled?.state.status === 'confirmed' && settled.state.generation === claim.generation &&
        settled.state.receipt?.id === receipt.id &&
        await prMatches(request, repository, prNumber, headSha, 'needs-human')) {
      return { status: 'confirmed', state: settled.state };
    }
    if (settled?.state.status === 'available' && settled.state.generation === state.generation) {
      return { status: 'reopened', state: settled.state };
    }
    return { status: 'uncertain', state: settled?.state };
  }
}

module.exports = {
  BRANCH,
  beginChallenge,
  claimMatchesState,
  confirmChallenge,
  consumeChallenge,
  finalizeChallenge,
  prepareChallenge,
  readAuthorityState,
  releasePreparedChallenge,
  reopenUnconfirmedChallenge,
  requester,
  validState,
};

if (require.main === module) {
  (async () => {
    const command = process.argv[2];
    if (!['prepare', 'finalize', 'release'].includes(command)) {
      throw new Error('Unsupported authority state command');
    }
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
    const options = {
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
    };
    const result = command === 'prepare'
      ? await prepareChallenge(options)
      : command === 'finalize'
        ? await finalizeChallenge(options)
        : await releasePreparedChallenge(options);
    process.stdout.write(JSON.stringify(result));
  })().catch((error) => {
    process.stderr.write(`Authority challenge unavailable: ${error.message}\n`);
    process.stdout.write(JSON.stringify({ granted: false, reason: 'authority-state-unavailable' }));
  });
}
