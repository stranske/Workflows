'use strict';

// This branch is the authority for challenge generations and receipts. PR comments
// are presentation only: a comment PATCH cannot provide a conditional write.
const crypto = require('node:crypto');
const { createGithubFetchRequester, withRetry } = require('./github-api-with-retry.js');
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
    (state.released_generation == null || HEX.test(state.released_generation)) &&
    (state.released_generation_lineage == null ||
      (Array.isArray(state.released_generation_lineage) &&
        state.released_generation_lineage.every((generation) => HEX.test(generation)))) &&
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

function attemptPath(repository, ownerAttempt) {
  if (!ATTEMPT.test(String(ownerAttempt)) ||
      !String(ownerAttempt).startsWith(`${String(repository).toLowerCase()}:`)) {
    throw new Error('Invalid authority attempt repository');
  }
  const key = crypto.createHash('sha256').update(ownerAttempt).digest('hex');
  return `/repos/${String(repository).toLowerCase()}/contents/.github/keepalive-authority-attempts/${key}.json`;
}

function validAttemptIndex(index, repository, ownerAttempt) {
  return index?.version === 1 && index.repository === String(repository).toLowerCase() &&
    index.owner_attempt === ownerAttempt && Number.isSafeInteger(index.pr_number) &&
    index.pr_number > 0 && HEX.test(index.generation) && validReceipt(index.receipt) &&
    index.receipt.owner_attempt === ownerAttempt;
}

async function readAttemptIndex(request, repository, ownerAttempt, { allowMissing = false } = {}) {
  let file;
  try {
    file = await request('GET', `${attemptPath(repository, ownerAttempt)}?ref=${BRANCH}`);
  } catch (error) {
    if (allowMissing && error.status === 404) return null;
    throw error;
  }
  if (!/^[0-9a-f]{40}$/.test(String(file?.sha)) || file?.encoding !== 'base64') {
    throw new Error('Invalid authority attempt index metadata');
  }
  let index;
  try {
    index = JSON.parse(Buffer.from(String(file.content).replace(/\s/g, ''), 'base64').toString('utf8'));
  } catch (error) {
    throw new Error(`Malformed authority attempt index: ${error.message}`);
  }
  if (!validAttemptIndex(index, repository, ownerAttempt)) {
    throw new Error('Invalid authority attempt index');
  }
  return index;
}

async function createAttemptIndex(request, repository, ownerAttempt, index) {
  const existing = await readAttemptIndex(request, repository, ownerAttempt, { allowMissing: true });
  if (existing) return existing;
  try {
    await request('PUT', attemptPath(repository, ownerAttempt), {
      branch: BRANCH,
      message: `keepalive authority attempt ${ownerAttempt}`,
      content: Buffer.from(`${JSON.stringify(index)}\n`).toString('base64'),
    });
    return index;
  } catch (error) {
    if (![409, 422].includes(error.status)) throw error;
    return readAttemptIndex(request, repository, ownerAttempt);
  }
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
  if (github) {
    return (method, path, body) => requestWithOctokit(github, method, path, body);
  }
  const token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
  if (!token) throw new Error('Authority state token unavailable');
  try {
    const { Octokit } = require('@octokit/rest');
    const octokit = new Octokit({ auth: token });
    return (method, path, body) => requestWithOctokit(octokit, method, path, body);
  } catch {
    return createGithubFetchRequester({ token });
  }
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

function expectedGenerationMatches(state, expectedGeneration, headSha) {
  if (!expectedGeneration) return true;
  if (state?.generation === expectedGeneration) return true;
  return state?.status === 'available' && state.receipt === null &&
    state.head_sha === headSha && state.released_receipt &&
    (state.released_generation === expectedGeneration ||
      state.released_generation_lineage?.includes(expectedGeneration));
}

function preparedAttemptMatchesIndex(state, index, repository, prNumber) {
  const receipt = state?.receipt;
  const claim = state?.prepared_claim;
  return state?.status === 'prepared' && claim && receipt &&
    claim.generation === state.generation &&
    claim.boundary_fingerprint === state.boundary_fingerprint &&
    claim.due_at === state.due_at && claim.expires_at === state.expires_at &&
    claim.head_sha === state.head_sha &&
    receiptMatches(receipt, claim, receipt.owner_attempt, receipt.provider, state.head_sha) &&
    index.repository === String(repository).toLowerCase() &&
    index.pr_number === Number(prNumber) && index.owner_attempt === receipt.owner_attempt &&
    index.generation === state.generation && index.receipt.id === receipt.id &&
    index.receipt.claim_digest === receipt.claim_digest &&
    index.receipt.provider === receipt.provider && index.receipt.head_sha === state.head_sha;
}

async function recoverExpiredPreparation({ request, repository, prNumber, prior, now }) {
  const state = prior.state;
  if (state.status !== 'prepared' || now.getTime() < Date.parse(state.expires_at)) {
    return { outcome: 'preserve' };
  }
  let index;
  try {
    index = await readAttemptIndex(request, repository, state.receipt?.owner_attempt);
  } catch (_) {
    return { outcome: 'preserve' };
  }
  if (!preparedAttemptMatchesIndex(state, index, repository, prNumber) ||
      !await prMatches(request, repository, prNumber, state.head_sha,
        'agent:needs-attention', 'needs-human').catch(() => false)) {
    return { outcome: 'preserve' };
  }
  const released = await releasePreparedChallenge({
    request, repository, prNumber, claim: state.prepared_claim,
    ownerAttempt: state.receipt.owner_attempt, provider: state.receipt.provider,
    headSha: state.head_sha, now,
  });
  if (!released.released) {
    return { outcome: ['challenge-conflict', 'challenge-preparation-not-current']
      .includes(released.reason) ? 'retry' : 'preserve' };
  }
  const settled = await readAuthorityState(request, repository, prNumber).catch(() => null);
  const exactRelease = settled?.state.status === 'available' && settled.state.receipt === null &&
    settled.state.head_sha === state.head_sha &&
    settled.state.released_generation === state.generation &&
    settled.state.released_receipt?.id === state.receipt.id &&
    settled.state.released_receipt?.owner_attempt === state.receipt.owner_attempt;
  if (!exactRelease || !await prMatches(request, repository, prNumber, state.head_sha,
    'agent:needs-attention', 'needs-human').catch(() => false)) {
    return { outcome: 'preserve' };
  }
  return { outcome: 'recovered' };
}

async function beginChallenge({ request, repository, prNumber, defaultBranch, fingerprint, dueAt, expiresAt, headSha, expectedGeneration = null, now = new Date() }) {
  if (!HEX.test(String(fingerprint)) || !HEAD.test(String(headSha)) ||
      !exactTime(dueAt) || !exactTime(expiresAt) ||
      Date.parse(expiresAt) <= Date.parse(dueAt) ||
      !(now instanceof Date) || !Number.isFinite(now.getTime())) {
    throw new Error('Invalid challenge boundary');
  }
  await ensureBranch(request, repository, defaultBranch);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const prior = await readAuthorityState(request, repository, prNumber, { allowMissing: true });
    if (expectedGeneration && (!prior ||
        !expectedGenerationMatches(prior.state, expectedGeneration, headSha))) {
      throw new Error('Previously initialized challenge generation is missing or superseded');
    }
    // Consumed and confirmed receipts remain spent on expiry. A prepared receipt
    // is non-authorizing and can be reaped only after its exact immutable attempt
    // index and current PR routing state have both been verified.
    if (prior && prior.state.head_sha === headSha && prior.state.status !== 'available') {
      if (prior.state.status === 'prepared' &&
          now.getTime() >= Date.parse(prior.state.expires_at)) {
        const recovery = await recoverExpiredPreparation({
          request, repository, prNumber, prior, now,
        });
        if (['recovered', 'retry'].includes(recovery.outcome)) continue;
      }
      return prior.state;
    }
    if (prior && prior.state.boundary_fingerprint === fingerprint &&
        prior.state.head_sha === headSha) {
      if (Date.parse(prior.state.expires_at) > now.getTime()) {
        return prior.state;
      }
    }
    const releasedState = prior?.state.head_sha === headSha &&
      prior.state.status === 'available' && prior.state.released_receipt
      ? {
          released_receipt: prior.state.released_receipt,
          released_generation: prior.state.released_generation || prior.state.generation,
          released_generation_lineage: [...new Set([
            ...(prior.state.released_generation_lineage || []),
            prior.state.released_generation || prior.state.generation,
            prior.state.generation,
          ])],
        }
      : {};
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
      ...releasedState,
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
  if (prior.state.released_receipt?.owner_attempt === ownerAttempt ||
      prior.state.recovered_receipt?.owner_attempt === ownerAttempt) {
    return { prepared: false, reason: 'attempt-already-settled' };
  }
  const receipt = {
    id: crypto.randomBytes(32).toString('hex'),
    claim_digest: crypto.createHash('sha256').update(JSON.stringify(claim)).digest('hex'),
    owner_attempt: ownerAttempt,
    provider,
    head_sha: headSha,
    consumed_at: now.toISOString(),
  };
  const candidate = { version: 1, repository: String(repository).toLowerCase(),
    owner_attempt: ownerAttempt, pr_number: Number(prNumber),
    generation: prior.state.generation, receipt };
  let index;
  try {
    index = await createAttemptIndex(request, repository, ownerAttempt, candidate);
  } catch (_) {
    return { prepared: false, reason: 'attempt-index-uncertain' };
  }
  if (index.pr_number !== Number(prNumber) || index.generation !== prior.state.generation ||
      index.receipt.claim_digest !== receipt.claim_digest ||
      index.receipt.provider !== provider || index.receipt.head_sha !== headSha) {
    return { prepared: false, reason: 'attempt-index-conflict' };
  }
  const next = { ...prior.state, status: 'prepared', receipt: index.receipt,
    prepared_claim: claim, recovered_receipt: null, recovered_generation: null,
    released_receipt: null, released_generation: null, released_generation_lineage: [],
    revision: prior.state.revision + 1 };
  try {
    await writeAuthorityState(request, repository, prNumber, next, prior.sha);
  } catch (error) {
    return { prepared: false, reason: [409, 422].includes(error.status) ? 'challenge-conflict' : 'challenge-write-uncertain' };
  }
  return { prepared: true, reason: 'challenge-prepared', receipt: index.receipt };
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
  let index;
  try {
    index = await readAttemptIndex(request, repository, ownerAttempt);
  } catch (_) {
    return { granted: false, reason: 'attempt-index-unavailable' };
  }
  if (index.pr_number !== Number(prNumber) || index.generation !== prior.state.generation ||
      index.receipt.id !== prior.state.receipt.id ||
      index.receipt.claim_digest !== prior.state.receipt.claim_digest ||
      index.receipt.provider !== provider || index.receipt.head_sha !== headSha) {
    return { granted: false, reason: 'attempt-index-conflict' };
  }
  // Persist the exact claim beside its receipt. A workflow_run reporter may need to
  // reopen this reservation after the owning run fails before an agent starts, and
  // the nonce/sweep identity cannot be reconstructed from presentation state.
  const next = {
    ...prior.state,
    status: 'consumed',
    consumed_claim: claim,
    revision: prior.state.revision + 1,
  };
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

async function releasePreparedChallenge({ request, repository, prNumber, claim, ownerAttempt, provider, headSha,
  now = new Date() }) {
  if (!(now instanceof Date) || !Number.isFinite(now.getTime())) {
    return { released: false, reason: 'challenge-time-invalid' };
  }
  const prior = await readAuthorityState(request, repository, prNumber);
  if (prior.state.status === 'available' && prior.state.receipt === null &&
      prior.state.head_sha === headSha &&
      (prior.state.released_generation || prior.state.generation) === claim.generation &&
      receiptMatches(prior.state.released_receipt, claim, ownerAttempt, provider, headSha)) {
    // The conditional PUT may have committed even when its response was lost.
    // An exact retry is settled; a newer preparation is never refunded.
    if (now.getTime() >= Date.parse(prior.state.expires_at)) {
      const refreshed = await refreshReleasedChallenge({
        request, repository, prNumber, ownerAttempt, prior, now,
      });
      return { released: refreshed.status === 'released', reason: refreshed.reason };
    }
    return { released: true, reason: 'challenge-preparation-already-released' };
  }
  if (prior.state.status !== 'prepared' || prior.state.head_sha !== headSha ||
      prior.state.generation !== claim.generation ||
      !receiptMatches(prior.state.receipt, claim, ownerAttempt, provider, headSha)) {
    return { released: false, reason: 'challenge-preparation-not-current' };
  }
  const expired = now.getTime() >= Date.parse(prior.state.expires_at);
  if (expired && !await prMatches(request, repository, prNumber, headSha,
    'agent:needs-attention', 'needs-human').catch(() => false)) {
    return { released: false, reason: 'challenge-pr-state-unavailable' };
  }
  const nowMs = now.getTime();
  const next = { ...prior.state, status: 'available', receipt: null,
    prepared_claim: null, released_receipt: prior.state.receipt,
    released_generation: claim.generation,
    released_generation_lineage: [claim.generation],
    ...(expired ? { generation: crypto.randomBytes(32).toString('hex'),
      due_at: new Date(nowMs).toISOString(),
      expires_at: new Date(nowMs + 24 * 60 * 60 * 1000).toISOString() } : {}),
    revision: prior.state.revision + 1 };
  try {
    await writeAuthorityState(request, repository, prNumber, next, prior.sha);
    return { released: true, reason: expired ? 'challenge-preparation-released-refreshed' :
      'challenge-preparation-released' };
  } catch (error) {
    const settled = await readAuthorityState(request, repository, prNumber).catch(() => null);
    if (settled?.state.status === 'available' && settled.state.generation === next.generation &&
        settled.state.released_generation === claim.generation &&
        settled.state.released_receipt?.id === prior.state.receipt.id) {
      return { released: true, reason: 'challenge-preparation-already-released' };
    }
    return { released: false, reason: [409, 422].includes(error.status) ?
      'challenge-conflict' : 'challenge-write-uncertain' };
  }
}

async function refreshReleasedChallenge({ request, repository, prNumber, ownerAttempt, prior = null,
  now = new Date() }) {
  if (!(now instanceof Date) || !Number.isFinite(now.getTime())) {
    return { status: 'uncertain', reason: 'challenge-time-invalid' };
  }
  const current = prior || await readAuthorityState(request, repository, prNumber);
  const state = current.state;
  if (state.status !== 'available' || state.receipt !== null ||
      state.released_receipt?.owner_attempt !== ownerAttempt) {
    return { status: 'uncertain', reason: 'released-attempt-not-current' };
  }
  const target = await findAuthorityPrForAttempt({ request, repository, ownerAttempt }).catch(() => null);
  if (target?.prNumber !== Number(prNumber)) {
    return { status: 'uncertain', reason: 'released-attempt-index-unavailable' };
  }
  if (!await prMatches(request, repository, prNumber, state.head_sha,
    'agent:needs-attention', 'needs-human').catch(() => false)) {
    return { status: 'uncertain', reason: 'challenge-pr-state-unavailable' };
  }
  if (now.getTime() < Date.parse(state.expires_at)) {
    return { status: 'released', reason: 'already-current', state,
      previousGenerations: state.released_generation_lineage ||
        [state.released_generation || state.generation] };
  }
  const nowMs = now.getTime();
  const lineage = [...new Set([...(state.released_generation_lineage || []),
    state.released_generation || state.generation, state.generation])];
  const next = { ...state, generation: crypto.randomBytes(32).toString('hex'),
    due_at: new Date(nowMs).toISOString(),
    expires_at: new Date(nowMs + 24 * 60 * 60 * 1000).toISOString(),
    released_generation: state.released_generation || state.generation,
    released_generation_lineage: lineage, revision: state.revision + 1 };
  try {
    await writeAuthorityState(request, repository, prNumber, next, current.sha);
    return { status: 'released', reason: 'released-window-refreshed', state: next,
      previousGenerations: lineage };
  } catch (_) {
    const settled = await readAuthorityState(request, repository, prNumber).catch(() => null);
    if (settled?.state.status === 'available' && settled.state.receipt === null &&
        settled.state.released_receipt?.id === state.released_receipt.id &&
        settled.state.generation === next.generation) {
      return { status: 'released', reason: 'released-window-refreshed', state: settled.state,
        previousGenerations: settled.state.released_generation_lineage };
    }
    return { status: 'uncertain', reason: 'released-window-write-uncertain' };
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

async function reopenUnconfirmedChallenge({ request, repository, prNumber, claim, ownerAttempt, provider, headSha,
  workerEvidence = 'unknown' }) {
  const prior = await readAuthorityState(request, repository, prNumber);
  if (prior.state.head_sha !== headSha) return { status: 'uncertain', state: prior.state };
  const receipt = prior.state.receipt;
  const recoveryClaim = claim && typeof claim === 'object' ? claim : prior.state.consumed_claim;
  const matches = recoveryClaim &&
    prior.state.generation === recoveryClaim.generation &&
    prior.state.boundary_fingerprint === recoveryClaim.boundary_fingerprint &&
    receipt?.claim_digest ===
      crypto.createHash('sha256').update(JSON.stringify(recoveryClaim)).digest('hex') &&
    receipt.owner_attempt === ownerAttempt && receipt.provider === provider && receipt.head_sha === headSha;
  const pr = await readPrState(request, repository, prNumber);
  if (!pr.open || pr.headSha !== headSha) return { status: 'uncertain', state: prior.state };
  if (matches && pr.labels.has('needs-human')) {
    return { status: prior.state.status === 'confirmed' ? 'confirmed' : 'uncertain', state: prior.state };
  }
  // A confirmed receipt has already crossed the hard-human boundary. An
  // absent label (or a stale PR read) must never rotate it into fresh grant
  // authority; only an unconfirmed consumed receipt is recoverable here.
  if (!matches || prior.state.status !== 'consumed' || workerEvidence !== 'not-started') {
    return { status: 'uncertain', state: prior.state };
  }
  const now = Date.now();
  const state = {
    ...prior.state,
    generation: crypto.randomBytes(32).toString('hex'),
    due_at: new Date(now).toISOString(),
    expires_at: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
    status: 'available', receipt: null, prepared_claim: null, consumed_claim: null,
    recovered_receipt: receipt, recovered_generation: prior.state.generation,
    revision: prior.state.revision + 1,
  };
  try {
    await writeAuthorityState(request, repository, prNumber, state, prior.sha);
    return { status: 'reopened', state };
  } catch (_) {
    const settled = await readAuthorityState(request, repository, prNumber).catch(() => null);
    if (recoveryClaim && settled?.state.status === 'confirmed' &&
        settled.state.generation === recoveryClaim.generation &&
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

async function authorityAttemptOwnsRecoveryReceipt({
  request,
  repository,
  prNumber,
  ownerAttempt,
}) {
  const normalized = String(ownerAttempt || '').toLowerCase();
  if (!normalized || !/^[a-z0-9_.-]+\/[a-z0-9_.-]+:\d+:\d+$/.test(normalized)) {
    return false;
  }
  const { state } = await readAuthorityState(request, repository, prNumber);
  const receipts = [state.receipt, state.released_receipt, state.recovered_receipt].filter(Boolean);
  return receipts.some((receipt) => receipt.owner_attempt === normalized &&
    receipt.head_sha === state.head_sha &&
    Boolean(receipt.provider));
}

async function reconcileFailedAuthorityAttempt({ request, repository, prNumber, ownerAttempt, workerEvidence }) {
  if (workerEvidence !== 'not-started') return { status: 'execution-not-disproved' };
  const { state } = await readAuthorityState(request, repository, prNumber);
  if (state.status === 'available' && state.recovered_receipt?.owner_attempt === ownerAttempt) {
    return { status: 'reopened', state, previousGeneration: state.recovered_generation };
  }
  if (state.status === 'available' && state.released_receipt?.owner_attempt === ownerAttempt) {
    return refreshReleasedChallenge({ request, repository, prNumber, ownerAttempt });
  }
  const receipt = state.receipt;
  if (!receipt || receipt.owner_attempt !== ownerAttempt ||
      receipt.head_sha !== state.head_sha || !receipt.provider) {
    return { status: 'attempt-not-current' };
  }
  const claim = state.status === 'prepared' ? state.prepared_claim : state.consumed_claim;
  if (!claim || claim.head_sha !== state.head_sha ||
      !receiptMatches(receipt, claim, ownerAttempt, receipt.provider, state.head_sha)) {
    return { status: 'claim-not-current' };
  }
  const options = { request, repository, prNumber, claim, ownerAttempt,
    provider: receipt.provider, headSha: state.head_sha, workerEvidence };
  if (state.status === 'prepared') {
    const result = await releasePreparedChallenge(options);
    if (!result.released) return { status: 'uncertain', reason: result.reason };
    const settled = await readAuthorityState(request, repository, prNumber);
    if (settled.state.status !== 'available' ||
        !receiptMatches(settled.state.released_receipt, claim, ownerAttempt,
          receipt.provider, state.head_sha)) return { status: 'uncertain' };
    if (!await prMatches(request, repository, prNumber, state.head_sha,
      'agent:needs-attention', 'needs-human').catch(() => false)) {
      return { status: 'uncertain', reason: 'challenge-pr-state-unavailable' };
    }
    return { status: 'released', reason: result.reason, state: settled.state,
      previousGenerations: settled.state.released_generation_lineage || [claim.generation] };
  }
  if (state.status === 'consumed') {
    const result = await reopenUnconfirmedChallenge(options);
    return { ...result, previousGeneration: state.generation };
  }
  return { status: 'receipt-not-recoverable' };
}

async function findAuthorityPrForAttempt({ request, repository, ownerAttempt }) {
  const index = await readAttemptIndex(request, repository, ownerAttempt, { allowMissing: true });
  if (!index) return null;
  const { state } = await readAuthorityState(request, repository, index.pr_number);
  const receipts = [state.receipt, state.released_receipt, state.recovered_receipt];
  if (!receipts.some((receipt) => receipt?.id === index.receipt.id &&
      receipt.owner_attempt === ownerAttempt && receipt.claim_digest === index.receipt.claim_digest &&
      receipt.head_sha === index.receipt.head_sha && receipt.provider === index.receipt.provider)) {
    throw new Error('Authority attempt index does not match PR ledger receipt');
  }
  return { prNumber: index.pr_number, state };
}

module.exports = {
  authorityAttemptOwnsRecoveryReceipt,
  findAuthorityPrForAttempt,
  reconcileFailedAuthorityAttempt,
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
