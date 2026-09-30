'use strict';

const {
  findAuthorityPrForAttempt,
  reconcileFailedAuthorityAttempt,
  requester,
} = require('./keepalive_authority_state.js');
const { loadKeepaliveState, projectRecoveredAuthorityState } = require('./keepalive_state.js');
const { withRetry } = require('./github-api-with-retry.js');

const DISPATCH_TITLE = 'keepalive-dispatch/v1 ';
const CONTRACT = /^run-name: \$\{\{ github\.event_name == 'workflow_dispatch' && format\('keepalive-dispatch\/v1 \{0\}', \(inputs\.authority_challenge_claim != '' \|\| inputs\.authority_challenge_fingerprint != ''\) && 'authority-candidate' \|\| 'ordinary'\) \|\| 'Agents (?:Keepalive Loop|Gate Followups)' \}\}$/m;
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
  const title = String(origin.display_title || '');
  if (title !== `${DISPATCH_TITLE}ordinary` &&
      title !== `${DISPATCH_TITLE}authority-candidate`) {
    throw new Error('Unassociated dispatch has no versioned classification');
  }
  const { data: producer } = await withRetry((client) => client.rest.repos.getContent({
    owner, repo, path: origin.path, ref: origin.head_sha,
  }), { github, maxRetries: 2, task: 'keepalive-reporter-producer' });
  if (producer.encoding !== 'base64' ||
      !CONTRACT.test(Buffer.from(String(producer.content).replace(/\s/g, ''), 'base64').toString('utf8'))) {
    throw new Error('Originating workflow revision lacks the dispatch classification contract');
  }
  if (title === `${DISPATCH_TITLE}authority-candidate`) {
    throw new Error('Authority-candidate dispatch has no immutable attempt index');
  }
  return { status: 'skip' };
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

module.exports = { classifyReporterRun, recoverReporterAuthority };
