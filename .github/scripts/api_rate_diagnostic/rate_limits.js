'use strict';

const fs = require('node:fs');

const DEFAULT_TOKEN_KEYS = [
  'OWNER_PR_PAT',
  'SERVICE_BOT_PAT',
  'ACTIONS_BOT_PAT',
  'AGENTS_AUTOMATION_PAT',
  'WORKFLOWS_APP_ID',
  'WORKFLOWS_APP_PRIVATE_KEY',
  'KEEPALIVE_APP_ID',
  'KEEPALIVE_APP_PRIVATE_KEY',
  'GH_APP_ID',
  'GH_APP_PRIVATE_KEY',
  'APP_1_ID',
  'APP_1_PRIVATE_KEY',
  'APP_2_ID',
  'APP_2_PRIVATE_KEY',
  'TOKEN_ROTATION_JSON',
  'TOKEN_ROTATION_ENV_KEYS',
  'TOKEN_ROTATION_KEYS',
  'PAT_1',
  'PAT_2',
  'PAT_3',
];

function pctUsed(used, limit) {
  const numericUsed = Number(used) || 0;
  const numericLimit = Number(limit) || 0;
  if (numericLimit <= 0) {
    return '0';
  }
  const truncated = Math.trunc(((numericUsed * 100) / numericLimit) * 10) / 10;
  return truncated === 0 ? '0' : truncated.toFixed(1);
}

function formatResetTime(resetEpoch) {
  const reset = Number(resetEpoch) || 0;
  try {
    return new Date(reset * 1000).toISOString().replace('.000Z', 'Z');
  } catch (_error) {
    return 'unknown';
  }
}

function normalizeResource(resource = {}) {
  const limit = Number(resource.limit) || 0;
  const remaining = Number(resource.remaining) || 0;
  const used = Number(resource.used) || 0;
  return {
    limit,
    remaining,
    used,
    pct: pctUsed(used, limit),
  };
}

function normalizeRateLimitData(rateData, source) {
  const resources = rateData?.resources || {};
  const core = normalizeResource(resources.core);
  return {
    source,
    core,
    graphql: normalizeResource(resources.graphql),
    search: normalizeResource(resources.search),
    reset: formatResetTime(resources.core?.reset || 0),
  };
}

function hasRateData(rateData) {
  return Boolean(rateData && Object.keys(rateData).length > 0);
}

function logRateLimitSummary(summary, displayName = summary.source) {
  console.log(displayName);
  console.log(`  Core API: ${summary.core.used}/${summary.core.limit} (${summary.core.pct}% used)`);
  console.log(
    `  GraphQL:  ${summary.graphql.used}/${summary.graphql.limit} (${summary.graphql.pct}% used)`,
  );
  console.log(
    `  Search:   ${summary.search.used}/${summary.search.limit} (${summary.search.pct}% used)`,
  );
  console.log(`  Reset at: ${summary.reset}`);
}

function appendOutput(name, value, outputPath = process.env.GITHUB_OUTPUT) {
  if (!outputPath) {
    return;
  }
  fs.appendFileSync(outputPath, `${name}=${value}\n`);
}

function buildSecretsFromEnv(env = process.env, keys = DEFAULT_TOKEN_KEYS) {
  return Object.fromEntries(keys.map((key) => [key, env[key] || '']));
}

async function fetchRateLimitData({ token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN } = {}) {
  const { Octokit } = require('@octokit/rest');
  const { createTokenAwareRetry } = require('../github-api-with-retry.js');
  const core = { info: () => {}, warning: console.warn, debug: () => {} };
  const github = new Octokit({ auth: token });
  const { withRetry } = await createTokenAwareRetry({
    github,
    core,
    env: process.env,
    task: 'health-75-api-rate-diagnostic',
    capabilities: ['rate_limit:read'],
  });
  const response = await withRetry((client) => client.rest.rateLimit.get());
  return response.data || {};
}

async function runFetchRateLimitStep({
  source,
  displayName,
  groupName,
  failureMessage,
  fetcher = fetchRateLimitData,
  outputPath = process.env.GITHUB_OUTPUT,
} = {}) {
  console.log(`::group::${groupName || `${source} Rate Limits`}`);
  const rateData = await fetcher();
  if (hasRateData(rateData)) {
    const summary = normalizeRateLimitData(rateData, source);
    logRateLimitSummary(summary, displayName || source);
    appendOutput('rate_json', JSON.stringify(summary), outputPath);
  } else {
    console.log(failureMessage || `Failed to retrieve ${source} rate limits`);
    appendOutput('rate_json', '{}', outputPath);
  }
  console.log('::endgroup::');
}

async function validateLoadSharing({
  env = process.env,
  tokenBalancer = require('../token_load_balancer.js'),
  core = {
    info: (message) => console.log(message),
    warning: (message) => console.warn(message),
    debug: () => undefined,
  },
} = {}) {
  const githubToken = env.GITHUB_TOKEN || '';
  if (!githubToken) {
    throw new Error('GITHUB_TOKEN is required for load-sharing verification.');
  }

  const summary = await tokenBalancer.initializeTokenRegistry({
    secrets: buildSecretsFromEnv(env),
    github: null,
    core,
    githubToken,
  });

  if (!summary || summary.length < 2) {
    throw new Error('Expected at least two tokens in the registry to verify load sharing.');
  }

  const hasPat = summary.some((token) => token.type === 'PAT');
  const hasApp = summary.some((token) => token.type === 'APP');
  if (!hasPat || !hasApp) {
    throw new Error('Expected both PAT and APP capacity pools for load sharing.');
  }

  const registryById = new Map(summary.map((token) => [token.id, token]));
  if (registryById.has('KEEPALIVE_APP')) {
    const keepaliveToken = await tokenBalancer.getOptimalToken({
      github: null,
      core,
      task: 'keepalive-loop',
      minRemaining: 100,
    });
    if (!keepaliveToken || keepaliveToken.source !== 'KEEPALIVE_APP') {
      throw new Error('KEEPALIVE_APP was expected to handle keepalive-loop tasks.');
    }
  }

  if (registryById.has('OWNER_PR_PAT')) {
    const ownerToken = await tokenBalancer.getOptimalToken({
      github: null,
      core,
      task: 'pr-creation-as-owner',
      minRemaining: 100,
    });
    if (!ownerToken || ownerToken.source !== 'OWNER_PR_PAT') {
      throw new Error('OWNER_PR_PAT was expected to handle owner PR creation.');
    }
  }

  const workflowDispatchCandidates = summary.filter(
    (token) => Array.isArray(token.capabilities) && token.capabilities.includes('workflow-dispatch'),
  );

  if (workflowDispatchCandidates.length >= 2) {
    const first = await tokenBalancer.getOptimalToken({
      github: null,
      core,
      task: 'workflow-dispatch',
      capabilities: ['workflow-dispatch'],
      minRemaining: 100,
    });
    if (!first) {
      throw new Error('Failed to select a token for workflow-dispatch.');
    }

    const callsToSimulate =
      typeof first.remaining === 'number' && first.remaining > 50 ? first.remaining - 50 : 1;
    tokenBalancer.updateTokenUsage(first.source, callsToSimulate);

    const second = await tokenBalancer.getOptimalToken({
      github: null,
      core,
      task: 'workflow-dispatch',
      capabilities: ['workflow-dispatch'],
      minRemaining: 100,
    });
    if (!second || second.source === first.source) {
      throw new Error('Expected token rotation to switch to a different source.');
    }
    core.info(`Load-sharing switch verified: ${first.source} -> ${second.source}`);
  } else {
    core.warning('Not enough workflow-dispatch candidates to validate switching.');
  }

  return summary;
}

module.exports = {
  DEFAULT_TOKEN_KEYS,
  appendOutput,
  buildSecretsFromEnv,
  fetchRateLimitData,
  formatResetTime,
  hasRateData,
  logRateLimitSummary,
  normalizeRateLimitData,
  pctUsed,
  runFetchRateLimitStep,
  validateLoadSharing,
};
