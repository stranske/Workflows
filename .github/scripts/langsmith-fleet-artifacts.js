const { withRetry: defaultRetry } = require('./github-api-with-retry.js');

// Bounded artifact discovery: exact-name query first, legacy suffixes second.
// A search-limit result is UNKNOWN, never proof that no artifact exists.
async function findFleetArtifact({ github, core, withRetry = defaultRetry, owner, repo, name,
  trustedWorkflowPaths, maxRequests = 30 }) {
  let requests = 0;
  const runCache = new Map();
  async function search(exact) {
    let pageSize = 30;
    let offset = 0;
    while (requests < maxRequests) {
      requests += 1;
      let response;
      try {
        response = await withRetry(() => github.rest.actions.listArtifactsForRepo({
          owner, repo, per_page: pageSize, page: offset / pageSize + 1,
          ...(exact ? { name } : {}),
        }), { maxRetries: 0 });
      } catch (error) {
        if (![500, 502, 503, 504].includes(Number(error.status)) || pageSize === 1) {
          throw error;
        }
        // 30 -> 10 -> 1 preserves the offset when a later page fails.
        pageSize = pageSize === 30 ? 10 : 1;
        core.warning(`Artifact listing ${owner}/${repo} failed; reducing page size to ${pageSize}`);
        continue;
      }
      const artifacts = response.data.artifacts;
      if (!Array.isArray(artifacts)) throw new Error('Invalid artifact listing');
      const candidates = artifacts.filter(item => !item.expired &&
        (exact ? item.name === name : item.name !== name && item.name.endsWith(name)))
        .sort((left, right) => new Date(right.created_at) - new Date(left.created_at));
      for (const candidate of candidates) {
        if (exact) return candidate;
        const runId = candidate.workflow_run && candidate.workflow_run.id;
        if (!runId) continue;
        if (!runCache.has(runId)) {
          if (requests >= maxRequests) throw new Error(`Artifact discovery search limit reached for ${owner}/${repo}; result UNKNOWN`);
          requests += 1;
          const run = await withRetry(() => github.rest.actions.getWorkflowRun({
            owner, repo, run_id: runId,
          }), { maxRetries: 2 });
          // Workflow-run paths may include a ref; trust the filename, not that ref.
          const workflowPath = run.data.path;
          const refIndex = typeof workflowPath === 'string' ? workflowPath.lastIndexOf('@') : -1;
          runCache.set(runId, refIndex >= 0 ? workflowPath.slice(0, refIndex) : workflowPath);
        }
        if (trustedWorkflowPaths.has(runCache.get(runId))) return candidate;
      }
      offset += pageSize;
      if (artifacts.length < pageSize || offset >= response.data.total_count) return null;
    }
    throw new Error(`Artifact discovery search limit reached for ${owner}/${repo}; result UNKNOWN`);
  }
  return await search(true) || await search(false);
}
module.exports = { findFleetArtifact };
