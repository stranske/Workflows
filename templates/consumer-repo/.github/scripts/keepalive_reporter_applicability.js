'use strict';

const {
  findAuthorityPrForAttempt,
  readAuthorityState,
  reconcileFailedAuthorityAttempt,
  requester,
} = require('./keepalive_authority_state.js');
const { loadKeepaliveState, projectRecoveredAuthorityState } = require('./keepalive_state.js');
const { getWorkerExecutionEvidence } = require('./keepalive_worker_evidence.js');
const { withRetry } = require('./github-api-with-retry.js');

const CONTRACT = /^run-name: \$\{\{ github\.event_name == 'workflow_dispatch' && format\('keepalive-dispatch\/v2 \{0\} pr=\{1\}', \(inputs\.authority_challenge_claim != '' \|\| inputs\.authority_challenge_fingerprint != ''\) && 'authority-candidate' \|\| 'ordinary', inputs\.pr_number\) \|\| 'Agents (?:Keepalive Loop|Gate Followups)' \}\}$/;
const TITLE_CONTRACT = /^keepalive-dispatch\/v2 (ordinary|authority-candidate) pr=([1-9][0-9]*)$/;
const PRODUCERS = new Set([
  '.github/workflows/agents-keepalive-loop.yml',
  '.github/workflows/agents-81-gate-followups.yml',
]);

async function classifyReporterRun({ github, owner, repo, run, lookupTarget = findAuthorityPrForAttempt }) {
  if (Number(run.pull_requests?.[0]?.number || 0) > 0) return { status: 'continue' };
  const repository = `${owner}/${repo}`;
  const ownerAttempt = `${repository}:${run.id}:${run.run_attempt || 1}`.toLowerCase();
  // The immutable index, if present, always wins over a display title.
  const target = await lookupTarget({
    request: requester(github), repository, ownerAttempt,
  });
  if (target) return { status: 'continue', prNumber: target.prNumber };

  const { data: origin } = await withRetry((client) => client.rest.actions.getWorkflowRun({
    owner, repo, run_id: run.id,
  }), { github, maxRetries: 2, task: 'keepalive-reporter-run' });
  if (Number(origin.id) !== Number(run.id) ||
      Number(origin.run_attempt) !== Number(run.run_attempt || 1) ||
      String(origin.head_sha) !== String(run.head_sha) ||
      origin.event !== 'workflow_dispatch' || !PRODUCERS.has(origin.path)) {
    throw new Error('Unassociated run has no verified dispatch classification');
  }
  const { data: producer } = await withRetry((client) => client.rest.repos.getContent({
    owner, repo, path: origin.path, ref: origin.head_sha,
  }), { github, maxRetries: 2, task: 'keepalive-reporter-producer' });
  const producerText = producer.encoding === 'base64'
    ? Buffer.from(String(producer.content).replace(/\s/g, ''), 'base64').toString('utf8')
    : '';
  const producerLines = producerText.split(/\r?\n/);
  if (!producerText || !CONTRACT.test(producerLines[1] || '') ||
      producerLines.filter((line) => CONTRACT.test(line)).length !== 1) {
    throw new Error('Originating workflow revision lacks the dispatch classification contract');
  }
  const title = String(origin.display_title || '');
  const titleMatch = TITLE_CONTRACT.exec(title);
  if (!titleMatch) {
    throw new Error('Unassociated dispatch has no canonical versioned PR binding');
  }
  const classification = titleMatch[1];
  const prText = titleMatch[2];
  const prNumber = Number(prText);
  if (!Number.isSafeInteger(prNumber) || prNumber <= 0 || String(prNumber) !== prText) {
    throw new Error('Unassociated dispatch has a non-canonical PR binding');
  }
  if (classification === 'authority-candidate') {
    throw new Error('Authority-candidate dispatch has no immutable attempt index');
  }
  return { status: 'continue', prNumber, targetSource: 'ordinary-run-name' };
}

async function recoverReporterAuthority({
  github,
  context,
  run,
  workerEvidence,
  writerLogin,
  prNumber = Number(run.pull_requests?.[0]?.number || 0),
  lookupTarget = findAuthorityPrForAttempt,
  reconcileAttempt = reconcileFailedAuthorityAttempt,
  projectRecovery = projectRecoveredAuthorityState,
  makeRequest = requester,
}) {
  if (!['started', 'not-started'].includes(workerEvidence)) {
    throw new Error('Originating worker execution evidence is unknown');
  }
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const repository = `${owner}/${repo}`;
  const ownerAttempt = `${repository}:${run.id}:${run.run_attempt || 1}`.toLowerCase();
  const request = makeRequest(github);
  let authorityTarget;
  if (!prNumber) {
    authorityTarget = await lookupTarget({ request, repository, ownerAttempt });
    prNumber = Number(authorityTarget?.prNumber || 0);
  }
  if (!prNumber) {
    throw new Error('No PR association or authoritative attempt target for failed run');
  }
  let reconciliation;
  try {
    reconciliation = await reconcileAttempt({
      request, repository, prNumber, ownerAttempt, workerEvidence,
    });
  } catch (error) {
    if (error.status === 404) {
      const loaded = await loadKeepaliveState({ github, context, prNumber, trace: '' });
      if (loaded.state.running === true && loaded.state.running_owner_attempt &&
          loaded.state.running_owner_attempt !== ownerAttempt) {
        return { status: 'superseded', prNumber, ownerAttempt, authorityTarget,
          projection: { projected: false, reason: 'running-attempt-superseded' } };
      }
      return { status: 'continue', prNumber, ownerAttempt, authorityTarget };
    }
    throw error;
  }
  if (['released', 'reopened'].includes(reconciliation.status)) {
    const projection = await projectRecovery({
      github, context, prNumber, recovery: reconciliation, writerLogin,
    });
    if (projection.projected === false) {
      return {
        status: 'superseded', prNumber, ownerAttempt, authorityTarget, reconciliation, projection,
      };
    }
    return {
      status: 'projected', prNumber, ownerAttempt, authorityTarget, reconciliation, projection,
    };
  }
  const loaded = await loadKeepaliveState({ github, context, prNumber, trace: '' });
  if (loaded.state.running === true && loaded.state.running_owner_attempt &&
      loaded.state.running_owner_attempt !== ownerAttempt) {
    return { status: 'superseded', prNumber, ownerAttempt, authorityTarget, reconciliation,
      projection: { projected: false, reason: 'running-attempt-superseded' } };
  }
  return { status: 'continue', prNumber, ownerAttempt, authorityTarget, reconciliation };
}

function parseOwnerAttempt(repository, ownerAttempt) {
  const normalized = String(ownerAttempt || '').toLowerCase();
  const prefix = `${String(repository || '').toLowerCase()}:`;
  if (!normalized.startsWith(prefix)) return null;
  const match = /:(\d+):(\d+)$/.exec(normalized);
  if (!match) return null;
  const runId = Number(match[1]);
  const runAttempt = Number(match[2]);
  if (!Number.isSafeInteger(runId) || runId <= 0 ||
      !Number.isSafeInteger(runAttempt) || runAttempt <= 0) return null;
  return { ownerAttempt: normalized, runId, runAttempt };
}

async function replayReporterAuthority({
  github,
  context,
  prNumber,
  writerLogin,
  maxPasses = 3,
  readAuthority = readAuthorityState,
  lookupTarget = findAuthorityPrForAttempt,
  reconcileAttempt = reconcileFailedAuthorityAttempt,
  projectRecovery = projectRecoveredAuthorityState,
  workerEvidenceForAttempt = getWorkerExecutionEvidence,
  makeRequest = requester,
}) {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const repository = `${owner}/${repo}`.toLowerCase();
  const number = Number(prNumber);
  if (!Number.isSafeInteger(number) || number <= 0) {
    throw new Error('Replay requires a positive PR number');
  }
  const request = makeRequest(github);
  const results = [];
  const seen = new Set();
  for (let pass = 0; pass < maxPasses; pass += 1) {
    const authority = await readAuthority(request, repository, number, { allowMissing: true });
    // Most keepalive PRs never enter the challenge path and have no ledger.
    // Only a confirmed 404 is an empty replay; all other read failures remain fatal.
    if (authority === null) break;
    const { state } = authority;
    const attempts = [state.receipt, state.released_receipt, state.recovered_receipt]
      .map((receipt) => parseOwnerAttempt(repository, receipt?.owner_attempt))
      .filter(Boolean)
      .filter((attempt) => !seen.has(attempt.ownerAttempt));
    if (attempts.length === 0) break;
    let changed = false;
    for (const attempt of attempts) {
      seen.add(attempt.ownerAttempt);
      const indexed = await lookupTarget({
        request, repository, ownerAttempt: attempt.ownerAttempt,
      });
      if (Number(indexed?.prNumber || 0) !== number) {
        throw new Error(`Replay attempt ${attempt.ownerAttempt} is not indexed to PR #${number}`);
      }
      const runResponse = await github.request(
        'GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}',
        { owner, repo, run_id: attempt.runId, attempt_number: attempt.runAttempt },
      );
      const run = runResponse?.data || {};
      if (run.status !== 'completed' ||
          Number(run.id) !== attempt.runId ||
          Number(run.run_attempt || 0) !== attempt.runAttempt ||
          !/^[0-9a-f]{40}$/.test(String(run.head_sha || ''))) {
        throw new Error(`Replay run identity is unavailable for ${attempt.ownerAttempt}`);
      }
      const workerEvidence = await workerEvidenceForAttempt(
        github, owner, repo, attempt.runId, attempt.runAttempt, run.head_sha,
      );
      if (workerEvidence === 'unknown') {
        throw new Error(`Replay worker evidence is unknown for ${attempt.ownerAttempt}`);
      }
      const reconciliation = await reconcileAttempt({
        request, repository, prNumber: number,
        ownerAttempt: attempt.ownerAttempt, workerEvidence,
      });
      let projection = null;
      if (['released', 'reopened'].includes(reconciliation.status)) {
        projection = await projectRecovery({
          github, context, prNumber: number, recovery: reconciliation, writerLogin,
        });
        if (projection?.projected === false &&
            projection.reason !== 'recovery-superseded') {
          throw new Error(
            `Replay projection is unresolved for ${attempt.ownerAttempt}: ` +
            `${projection.reason || 'unknown'}`,
          );
        }
        changed = changed || projection?.projected !== false;
      }
      results.push({
        ownerAttempt: attempt.ownerAttempt, workerEvidence,
        status: reconciliation.status, projection,
      });
    }
    if (!changed) break;
  }
  return { prNumber: number, results };
}

module.exports = {
  classifyReporterRun,
  parseOwnerAttempt,
  recoverReporterAuthority,
  replayReporterAuthority,
};
