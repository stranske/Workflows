'use strict';

const normaliseRepo = (value) => {
  if (!value) {
    return '';
  }
  if (typeof value === 'string') {
    return value.trim();
  }
  const owner = value.owner?.login || value.owner?.name || '';
  const name = value.name || '';
  return String(value.full_name || value.fullName || (owner && name ? `${owner}/${name}` : ''));
};

const normaliseSha = (value) => (typeof value === 'string' && value.trim()) || '';

function resolveCheckoutSource({ core, context, fallbackRepo, fallbackRef }) {
  const warnings = [];
  const fallbackRepository = normaliseRepo(fallbackRepo) || `${context.repo.owner}/${context.repo.repo}`;
  const fallbackSha = normaliseSha(fallbackRef) || context.sha || '';

  let repository = fallbackRepository;
  let ref = fallbackSha;

  const pull = context.payload?.pull_request;
  const workflowRun = context.payload?.workflow_run;

  if (pull) {
    const repoCandidate = normaliseRepo(pull.head?.repo);
    const refCandidate = normaliseSha(pull.head?.sha);

    repository = repoCandidate || fallbackRepository;
    ref = refCandidate || fallbackSha;

    if (!repoCandidate) {
      warnings.push('pull_request head repository missing; defaulting to base repository.');
    }
    if (!refCandidate) {
      warnings.push('pull_request head SHA missing; defaulting to workflow SHA.');
    }
  } else if (workflowRun) {
    const pullRequests = Array.isArray(workflowRun.pull_requests) ? workflowRun.pull_requests : [];
    const primaryPull = pullRequests.length > 0 ? workflowRun.pull_requests[0] : null;

    const repoCandidate =
      normaliseRepo(primaryPull?.head?.repo) || normaliseRepo(workflowRun.head_repository);
    const refCandidate = normaliseSha(primaryPull?.head?.sha) || normaliseSha(workflowRun.head_sha);

    repository = repoCandidate || fallbackRepository;
    ref = refCandidate || fallbackSha;

    if (!repoCandidate) {
      warnings.push('workflow_run head repository missing; defaulting to base repository.');
    }
    if (!refCandidate) {
      warnings.push('workflow_run head SHA missing; defaulting to workflow SHA.');
    }
  } else {
    warnings.push('No pull_request or workflow_run context; defaulting checkout to base repository.');
  }

  return { repository, ref, warnings };
}

module.exports = { resolveCheckoutSource };
