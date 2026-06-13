'use strict';

const fs = require('fs');
const path = require('path');

function retryHelperCandidates(env = process.env, cwd = process.cwd()) {
  const actionPath = env.GITHUB_ACTION_PATH || '';
  const resolverActionPath = env.RESOLVE_DEFAULT_BRANCH_ACTION_PATH || '';
  return [
    resolverActionPath
      ? path.resolve(resolverActionPath, '..', '..', 'scripts', 'github-api-with-retry.js')
      : '',
    actionPath ? path.resolve(actionPath, '..', '..', 'scripts', 'github-api-with-retry.js') : '',
    path.resolve(cwd, '.github/scripts/github-api-with-retry.js'),
    path.resolve(cwd, 'consumer/.github/scripts/github-api-with-retry.js'),
    path.resolve(cwd, 'workflows-lib/.github/scripts/github-api-with-retry.js'),
    path.resolve(cwd, '.workflows-lib/.github/scripts/github-api-with-retry.js'),
  ].filter(Boolean);
}

function loadRetryHelper({ env = process.env, cwd = process.cwd(), loader = require } = {}) {
  for (const candidate of retryHelperCandidates(env, cwd)) {
    if (!fs.existsSync(candidate)) {
      continue;
    }
    return loader(candidate);
  }
  return null;
}

async function resolveDefaultBranch({
  github,
  core,
  owner = 'stranske',
  repo = 'Workflows',
  fallbackRef = '',
  failOnError = true,
  task = 'resolve-default-branch',
  env = process.env,
  cwd = process.cwd(),
  loader = require,
}) {
  const fallback = String(fallbackRef || '').trim();
  const target = `${owner}/${repo}`;
  let withRetry = (fn) => fn(github);

  const retryHelper = loadRetryHelper({ env, cwd, loader });
  if (retryHelper?.createTokenAwareRetry) {
    const retry = await retryHelper.createTokenAwareRetry({
      github,
      core,
      env,
      task,
      capabilities: ['contents:read'],
    });
    if (retry?.withRetry) {
      withRetry = retry.withRetry;
    }
  }

  const setResolvedRef = (ref) => {
    core.setOutput('ref', ref);
    return ref;
  };

  try {
    const { data } = await withRetry((client) =>
      client.rest.repos.get({
        owner,
        repo,
      }),
    );
    if (data?.default_branch) {
      return setResolvedRef(data.default_branch);
    }
    if (fallback) {
      core.warning(`${target} default branch missing; falling back to ${fallback}`);
      return setResolvedRef(fallback);
    }
    core.setFailed(`Could not determine ${target} default branch`);
    return setResolvedRef('');
  } catch (error) {
    const message = error?.message || String(error);
    if (fallback) {
      core.warning(`Failed to resolve ${target} default branch; using ${fallback}. ${message}`);
      return setResolvedRef(fallback);
    }
    if (failOnError) {
      core.setFailed(`Failed to resolve ${target} default branch: ${message}`);
    } else {
      core.warning(`Failed to resolve ${target} default branch: ${message}`);
    }
    return setResolvedRef('');
  }
}

module.exports = {
  loadRetryHelper,
  resolveDefaultBranch,
  retryHelperCandidates,
};
