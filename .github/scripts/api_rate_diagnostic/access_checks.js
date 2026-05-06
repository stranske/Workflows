'use strict';

function normalizeHeader(headers, key) {
  if (!headers) return '';
  const lowerKey = key.toLowerCase();
  return headers[lowerKey] || headers[key] || '';
}

function buildTokenList(env = process.env) {
  return [
    ['GITHUB_TOKEN', env.GITHUB_TOKEN_VALUE],
    ['OWNER_PR_PAT', env.OWNER_PR_PAT_TOKEN],
    ['SERVICE_BOT_PAT', env.SERVICE_BOT_TOKEN],
    ['WORKFLOWS_APP', env.WORKFLOWS_APP_TOKEN],
    ['KEEPALIVE_APP', env.KEEPALIVE_APP_TOKEN],
    ['GH_APP', env.GH_APP_TOKEN],
  ];
}

async function checkActionsRunsAccess({
  env = process.env,
  tokens = buildTokenList(env),
  workflowId = 'health-75-api-rate-diagnostic.yml',
  Octokit = require('@octokit/rest').Octokit,
  createTokenAwareRetry = require('../github-api-with-retry.js').createTokenAwareRetry,
  core = { info: console.log, warning: console.warn, debug: () => {} },
} = {}) {
  const [owner, repo] = env.GITHUB_REPOSITORY.split('/');
  const listRunsRoute = 'GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs';
  const results = [];

  console.log('::group::Actions runs access checks');
  for (const [label, token] of tokens) {
    if (!token) {
      const line = `${label}: not set`;
      console.log(line);
      results.push(line);
      continue;
    }
    const github = new Octokit({ auth: token });
    try {
      const { withRetry } = await createTokenAwareRetry({
        github,
        core,
        env,
        task: 'health-75-api-rate-diagnostic-access-check',
        capabilities: ['actions:read'],
        tokenRegistry: { isInitialized: () => false },
      });
      const retryContext = {
        github,
        core,
        env,
        task: 'health-75-api-rate-diagnostic-access-check',
      };
      const response = await withRetry(
        () =>
          github.request(listRunsRoute, {
            owner,
            repo,
            workflow_id: workflowId,
            per_page: 1,
          }),
        retryContext,
      );
      const accepted = normalizeHeader(response?.headers, 'x-accepted-github-permissions');
      const statusLine = `HTTP ${response?.status || 'unknown'}`;
      const line = accepted ? `${label}: ${statusLine} | perms: ${accepted}` : `${label}: ${statusLine}`;
      console.log(line);
      results.push(line);
    } catch (error) {
      const status = error?.status || error?.response?.status || 'error';
      const line = `${label}: HTTP ${status}`;
      console.log(line);
      results.push(line);
    }
  }
  console.log('::endgroup::');
  return results;
}

module.exports = {
  buildTokenList,
  checkActionsRunsAccess,
  normalizeHeader,
};
