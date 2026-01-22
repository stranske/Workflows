/**
 * Token Load Balancer - Dynamic GitHub API token selection
 * 
 * This module provides intelligent token rotation across multiple PATs and GitHub Apps
 * to avoid API rate limit exhaustion. It:
 * 
 * 1. Maintains a registry of available tokens (PATs, Apps)
 * 2. Tracks rate limit status for each token
 * 3. Selects the token with highest available capacity
 * 4. Rotates proactively before limits are hit
 * 5. Provides graceful degradation when all tokens are low
 * 
 * Token Types:
 * - PAT: Personal Access Tokens (5000/hr each, tied to user account)
 * - APP: GitHub App installation tokens (5000/hr each, separate pool)
 * - GITHUB_TOKEN: Installation token (varies, repo-scoped only)
 * 
 * Usage:
 *   const { getOptimalToken, updateTokenUsage } = require('./token_load_balancer.js');
 *   const token = await getOptimalToken({ github, core, capabilities: ['cross-repo'] });
 */

// Token registry - tracks all available tokens and their metadata
const tokenRegistry = {
  // Each entry: { token, type, source, capabilities, rateLimit: { limit, remaining, reset, checked } }
  tokens: new Map(),
  
  // Last time we refreshed rate limits (avoid hammering the API)
  lastRefresh: 0,
  
  // Minimum interval between full refreshes (5 minutes)
  refreshInterval: 5 * 60 * 1000,
  
  // Threshold below which we consider a token "low" (20%)
  lowThreshold: 0.20,
  
  // Threshold below which we consider a token "critical" (5%)
  criticalThreshold: 0.05,
};

/**
 * Token capabilities - what each token type can do
 * Based on analysis of actual usage across workflows
 */
const TOKEN_CAPABILITIES = {
  GITHUB_TOKEN: ['read-repo', 'write-repo', 'pr-update', 'labels', 'comments'],
  PAT: ['read-repo', 'write-repo', 'pr-update', 'labels', 'comments', 'cross-repo', 'workflow-dispatch'],
  APP: ['read-repo', 'write-repo', 'pr-update', 'labels', 'comments', 'workflow-dispatch'],
};

/**
 * Token specializations - primary/exclusive tasks for each token
 * 
 * Analysis of token usage across the codebase:
 * 
 * | Token               | Account/App               | Primary Use Cases                                    | Exclusive? |
 * |---------------------|---------------------------|------------------------------------------------------|------------|
 * | GITHUB_TOKEN        | Installation              | Basic repo ops within same repo                      | No         |
 * | CODESPACES_WORKFLOWS| stranske (owner)          | Cross-repo sync, dependabot automerge, label sync    | No         |
 * | SERVICE_BOT_PAT     | stranske-automation-bot   | Bot comments, labels, autofix commits                | Primary    |
 * | ACTIONS_BOT_PAT     | stranske-automation-bot   | Workflow dispatch, belt conveyor                     | Primary    |
 * | OWNER_PR_PAT        | stranske (owner)          | PR creation on owner's behalf                        | Exclusive  |
 * | WORKFLOWS_APP       | GitHub App                | General workflow ops, autofix                        | No         |
 * | KEEPALIVE_APP       | GitHub App                | Keepalive loop - isolated rate limit pool            | Exclusive  |
 * | GH_APP              | GitHub App                | Bot comment handler, issue intake                    | Primary    |
 * 
 * Key insights:
 * - SERVICE_BOT_PAT: Used for bot account operations (separate 5000/hr from owner)
 * - ACTIONS_BOT_PAT: Specifically for workflow_dispatch triggers
 * - OWNER_PR_PAT: Creates PRs attributed to repo owner (required for ownership)
 * - KEEPALIVE_APP: Dedicated App to isolate keepalive from other operations
 * - GH_APP: Fallback general-purpose App for comment handling
 */
const TOKEN_SPECIALIZATIONS = {
  // PAT specializations
  SERVICE_BOT_PAT: {
    primaryTasks: ['bot-comments', 'labels', 'autofix-commits'],
    exclusive: false,
    description: 'Bot account for automation (separate rate limit pool from owner)',
  },
  ACTIONS_BOT_PAT: {
    primaryTasks: ['workflow-dispatch', 'belt-conveyor'],
    exclusive: false,
    description: 'Workflow dispatch triggers and belt conveyor operations',
  },
  CODESPACES_WORKFLOWS: {
    primaryTasks: ['cross-repo-sync', 'dependabot-automerge', 'label-sync'],
    exclusive: false,
    description: 'Owner PAT for cross-repo operations',
  },
  OWNER_PR_PAT: {
    primaryTasks: ['pr-creation-as-owner'],
    exclusive: true,
    description: 'Creates PRs attributed to repository owner',
  },
  // App specializations
  WORKFLOWS_APP: {
    primaryTasks: ['autofix', 'general-workflow'],
    exclusive: false,
    description: 'General-purpose GitHub App for workflow operations',
  },
  KEEPALIVE_APP: {
    primaryTasks: ['keepalive-loop'],
    exclusive: true,
    description: 'Dedicated App for keepalive - isolated rate limit pool',
  },
  GH_APP: {
    primaryTasks: ['bot-comment-handler', 'issue-intake'],
    exclusive: false,
    description: 'General-purpose App for comment handling and intake',
  },
};

/**
 * Initialize the token registry from environment/secrets
 * Call this once at workflow start
 * 
 * @param {Object} options
 * @param {Object} options.secrets - GitHub secrets object
 * @param {Object} options.github - GitHub API client
 * @param {Object} options.core - GitHub Actions core
 * @param {string} options.githubToken - Default GITHUB_TOKEN
 */
async function initializeTokenRegistry({ secrets, github, core, githubToken }) {
  // Validate inputs
  if (!secrets || typeof secrets !== 'object') {
    throw new Error('initializeTokenRegistry requires a valid secrets object');
  }
  
  tokenRegistry.tokens.clear();
  
  // Register GITHUB_TOKEN (always available)
  if (githubToken) {
    registerToken({
      id: 'GITHUB_TOKEN',
      token: githubToken,
      type: 'GITHUB_TOKEN',
      source: 'github.token',
      capabilities: TOKEN_CAPABILITIES.GITHUB_TOKEN,
      priority: 0, // Lowest priority (most restricted)
    });
  }
  
  // Register PATs (check for PAT1, PAT2, etc. pattern as well as named PATs)
  const patSources = [
    { id: 'SERVICE_BOT_PAT', env: secrets.SERVICE_BOT_PAT, account: 'stranske-automation-bot' },
    { id: 'ACTIONS_BOT_PAT', env: secrets.ACTIONS_BOT_PAT, account: 'stranske-automation-bot' },
    { id: 'CODESPACES_WORKFLOWS', env: secrets.CODESPACES_WORKFLOWS, account: 'stranske' },
    { id: 'OWNER_PR_PAT', env: secrets.OWNER_PR_PAT, account: 'stranske' },
    { id: 'AGENTS_AUTOMATION_PAT', env: secrets.AGENTS_AUTOMATION_PAT, account: 'unknown' },
    // Numbered PATs for future expansion
    { id: 'PAT_1', env: secrets.PAT_1, account: 'pool' },
    { id: 'PAT_2', env: secrets.PAT_2, account: 'pool' },
    { id: 'PAT_3', env: secrets.PAT_3, account: 'pool' },
  ];
  
  for (const pat of patSources) {
    if (pat.env) {
      registerToken({
        id: pat.id,
        token: pat.env,
        type: 'PAT',
        source: pat.id,
        account: pat.account,
        capabilities: TOKEN_CAPABILITIES.PAT,
        priority: 5, // Medium priority
      });
    }
  }
  
  // Register GitHub Apps
  const appSources = [
    { 
      id: 'WORKFLOWS_APP', 
      appId: secrets.WORKFLOWS_APP_ID, 
      privateKey: secrets.WORKFLOWS_APP_PRIVATE_KEY,
      purpose: 'general'
    },
    { 
      id: 'KEEPALIVE_APP', 
      appId: secrets.KEEPALIVE_APP_ID, 
      privateKey: secrets.KEEPALIVE_APP_PRIVATE_KEY,
      purpose: 'keepalive'
    },
    { 
      id: 'GH_APP', 
      appId: secrets.GH_APP_ID, 
      privateKey: secrets.GH_APP_PRIVATE_KEY,
      purpose: 'general'
    },
    // Numbered Apps for future expansion
    { 
      id: 'APP_1', 
      appId: secrets.APP_1_ID, 
      privateKey: secrets.APP_1_PRIVATE_KEY,
      purpose: 'pool'
    },
    { 
      id: 'APP_2', 
      appId: secrets.APP_2_ID, 
      privateKey: secrets.APP_2_PRIVATE_KEY,
      purpose: 'pool'
    },
  ];
  
  for (const app of appSources) {
    if (app.appId && app.privateKey) {
      registerToken({
        id: app.id,
        token: null, // Will be minted on demand
        type: 'APP',
        source: app.id,
        appId: app.appId,
        privateKey: app.privateKey,
        purpose: app.purpose,
        capabilities: TOKEN_CAPABILITIES.APP,
        priority: 10, // Highest priority (preferred)
      });
    }
  }
  
  core?.info?.(`Token registry initialized with ${tokenRegistry.tokens.size} tokens`);
  
  // Initial rate limit check for all tokens
  await refreshAllRateLimits({ github, core });
  
  return getRegistrySummary();
}

/**
 * Register a single token in the registry
 */
function registerToken(tokenInfo) {
  tokenRegistry.tokens.set(tokenInfo.id, {
    ...tokenInfo,
    rateLimit: {
      limit: 5000,
      remaining: 5000,
      used: 0,
      reset: Date.now() + 3600000,
      checked: 0,
      percentUsed: 0,
    },
  });
}

/**
 * Refresh rate limits for all registered tokens
 */
async function refreshAllRateLimits({ github, core }) {
  const now = Date.now();
  
  // Skip if we refreshed recently
  if (now - tokenRegistry.lastRefresh < tokenRegistry.refreshInterval) {
    core?.debug?.('Skipping rate limit refresh - too recent');
    return;
  }
  
  const results = [];
  
  for (const [id, tokenInfo] of tokenRegistry.tokens) {
    try {
      const rateLimit = await checkTokenRateLimit({ tokenInfo, github, core });
      tokenInfo.rateLimit = rateLimit;
      results.push({ id, ...rateLimit });
    } catch (error) {
      core?.warning?.(`Failed to check rate limit for ${id}: ${error.message}`);
      // Mark as unknown but don't remove from registry
      tokenInfo.rateLimit.checked = now;
      tokenInfo.rateLimit.error = error.message;
    }
  }
  
  tokenRegistry.lastRefresh = now;
  return results;
}

/**
 * Check rate limit for a specific token
 */
async function checkTokenRateLimit({ tokenInfo, github, core }) {
  const { Octokit } = await import('@octokit/rest');
  
  let token = tokenInfo.token;
  
  // For Apps, we need to mint a token first
  if (tokenInfo.type === 'APP' && !token) {
    token = await mintAppToken({ tokenInfo, core });
    tokenInfo.token = token;
    tokenInfo.tokenMinted = Date.now();
  }
  
  if (!token) {
    throw new Error('No token available');
  }
  
  const octokit = new Octokit({ auth: token });
  
  const { data } = await octokit.rateLimit.get();
  const core_limit = data.resources.core;
  
  const percentUsed = core_limit.limit > 0 
    ? (core_limit.used / core_limit.limit) * 100
    : 0;
  
  return {
    limit: core_limit.limit,
    remaining: core_limit.remaining,
    used: core_limit.used,
    reset: core_limit.reset * 1000,
    checked: Date.now(),
    percentUsed,
    percentRemaining: 100 - percentUsed,
  };
}

/**
 * Mint a GitHub App installation token
 */
async function mintAppToken({ tokenInfo, core }) {
  try {
    const { createAppAuth } = await import('@octokit/auth-app');
    const { Octokit } = await import('@octokit/rest');
    
    const auth = createAppAuth({
      appId: tokenInfo.appId,
      privateKey: tokenInfo.privateKey,
    });
    
    // Get installation ID (assuming org-wide installation)
    const appOctokit = new Octokit({
      authStrategy: createAppAuth,
      auth: {
        appId: tokenInfo.appId,
        privateKey: tokenInfo.privateKey,
      },
    });
    
    const { data: installations } = await appOctokit.apps.listInstallations();
    
    if (installations.length === 0) {
      throw new Error('No installations found for app');
    }
    
    // Use first installation (typically the org)
    const installationId = installations[0].id;
    
    const { token } = await auth({
      type: 'installation',
      installationId,
    });
    
    core?.debug?.(`Minted token for ${tokenInfo.id}`);
    return token;
  } catch (error) {
    core?.warning?.(`Failed to mint app token for ${tokenInfo.id}: ${error.message}`);
    return null;
  }
}

/**
 * Get the optimal token for a given operation
 * 
 * @param {Object} options
 * @param {Object} options.github - GitHub API client
 * @param {Object} options.core - GitHub Actions core
 * @param {string[]} options.capabilities - Required capabilities
 * @param {string} options.preferredType - Prefer APP or PAT
 * @param {string} options.task - Specific task name for specialization matching
 * @param {number} options.minRemaining - Minimum remaining calls needed
 * @returns {Object} { token, source, remaining, percentUsed }
 */
async function getOptimalToken({ github, core, capabilities = [], preferredType = null, task = null, minRemaining = 100 }) {
  // Refresh if stale
  const now = Date.now();
  if (now - tokenRegistry.lastRefresh > tokenRegistry.refreshInterval) {
    await refreshAllRateLimits({ github, core });
  }
  
  // If a specific task is requested, first check for exclusive tokens
  if (task) {
    for (const [id, spec] of Object.entries(TOKEN_SPECIALIZATIONS)) {
      if (spec.exclusive && spec.primaryTasks.includes(task)) {
        const tokenInfo = tokenRegistry.tokens.get(id);
        if (tokenInfo && (tokenInfo.rateLimit?.remaining ?? 0) >= minRemaining) {
          core?.info?.(`Using exclusive token ${id} for task '${task}'`);
          let token = tokenInfo.token;
          if (tokenInfo.type === 'APP' && !token) {
            token = await mintAppToken({ tokenInfo, core });
            if (!token) {
              // Failed to mint token for exclusive task - don't fall through to general tokens
              core?.warning?.(
                `Failed to mint app token for exclusive task '${task}'. ` +
                  `Token ${id} is required but unavailable.`
              );
              return null;
            }
            tokenInfo.token = token;
          }
          if (token) {
            return {
              token,
              source: id,
              type: tokenInfo.type,
              remaining: tokenInfo.rateLimit?.remaining ?? 0,
              percentRemaining: tokenInfo.rateLimit?.percentRemaining ?? 0,
              percentUsed: tokenInfo.rateLimit?.percentUsed ?? 0,
              exclusive: true,
              task,
            };
          }
        }
      }
    }
  }
  
  // Filter tokens by capability
  const candidates = [];
  
  for (const [id, tokenInfo] of tokenRegistry.tokens) {
    // Check capabilities
    const hasCapabilities = capabilities.every(cap => 
      tokenInfo.capabilities.includes(cap)
    );
    
    if (!hasCapabilities) {
      continue;
    }
    
    // Check if token has enough remaining capacity
    const remaining = tokenInfo.rateLimit?.remaining ?? 0;
    if (remaining < minRemaining) {
      core?.debug?.(`Skipping ${id}: only ${remaining} remaining (need ${minRemaining})`);
      continue;
    }
    
    // Calculate score based on remaining capacity, priority, and task match
    const percentRemaining = tokenInfo.rateLimit?.percentRemaining ?? 0;
    const priorityBonus = tokenInfo.priority * 10;
    const typeBonus = preferredType && tokenInfo.type === preferredType ? 20 : 0;
    
    // Boost score if token is primary for this task
    let taskBonus = 0;
    const spec = TOKEN_SPECIALIZATIONS[id];
    if (task && spec && spec.primaryTasks.includes(task)) {
      taskBonus = 30; // Strong preference for primary tokens
      core?.debug?.(`${id} is primary for task '${task}', +30 bonus`);
    }
    
    const score = percentRemaining + priorityBonus + typeBonus + taskBonus;
    
    candidates.push({
      id,
      tokenInfo,
      score,
      remaining,
      percentRemaining,
      isPrimary: taskBonus > 0,
    });
  }
  
  if (candidates.length === 0) {
    core?.warning?.('No tokens available with required capabilities and capacity');
    return null;
  }
  
  // Sort by score (highest first)
  candidates.sort((a, b) => b.score - a.score);

  while (candidates.length > 0) {
    const best = candidates[0];

    // Ensure token is available (mint if App)
    let token = best.tokenInfo.token;
    if (best.tokenInfo.type === 'APP' && !token) {
      token = await mintAppToken({ tokenInfo: best.tokenInfo, core });
      best.tokenInfo.token = token;
    }

    if (!token) {
      core?.warning?.(
        `Failed to mint app token for ${best.id}, trying next candidate`
      );
      candidates.shift();
      continue;
    }

    core?.info?.(`Selected token: ${best.id} (${best.remaining} remaining, ${best.percentRemaining.toFixed(1)}% capacity)${best.isPrimary ? ' [primary]' : ''}`);

    return {
      token,
      source: best.id,
      type: best.tokenInfo.type,
      remaining: best.remaining,
      percentRemaining: best.percentRemaining,
      percentUsed: best.tokenInfo.rateLimit?.percentUsed ?? 0,
      isPrimary: best.isPrimary,
      task,
    };
  }

  core?.warning?.('No tokens available after attempting to mint app tokens');
  return null;
}

/**
 * Update token usage after making API calls
 * This helps track usage between full refreshes
 * 
 * @param {string} tokenId - Token identifier
 * @param {number} callsMade - Number of API calls made
 */
function updateTokenUsage(tokenId, callsMade = 1) {
  const tokenInfo = tokenRegistry.tokens.get(tokenId);
  if (tokenInfo && tokenInfo.rateLimit) {
    tokenInfo.rateLimit.remaining = Math.max(0, tokenInfo.rateLimit.remaining - callsMade);
    tokenInfo.rateLimit.used += callsMade;
    tokenInfo.rateLimit.percentUsed = tokenInfo.rateLimit.limit > 0
      ? ((tokenInfo.rateLimit.used / tokenInfo.rateLimit.limit) * 100).toFixed(1)
      : 0;
    tokenInfo.rateLimit.percentRemaining = 100 - tokenInfo.rateLimit.percentUsed;
  }
}

/**
 * Update token rate limit from response headers
 * More accurate than estimating
 * 
 * @param {string} tokenId - Token identifier
 * @param {Object} headers - Response headers with x-ratelimit-* values
 */
function updateFromHeaders(tokenId, headers) {
  const tokenInfo = tokenRegistry.tokens.get(tokenId);
  if (!tokenInfo) return;
  
  const remaining = parseInt(headers['x-ratelimit-remaining'], 10);
  const limit = parseInt(headers['x-ratelimit-limit'], 10);
  const used = parseInt(headers['x-ratelimit-used'], 10);
  const reset = parseInt(headers['x-ratelimit-reset'], 10);
  
  if (!isNaN(remaining) && !isNaN(limit)) {
    tokenInfo.rateLimit = {
      limit,
      remaining,
      used: used || (limit - remaining),
      reset: reset ? reset * 1000 : tokenInfo.rateLimit.reset,
      checked: Date.now(),
      percentUsed: (limit - remaining) / limit * 100,
      percentRemaining: (remaining / limit) * 100,
    };
  }
}

/**
 * Get a summary of all registered tokens and their status
 */
function getRegistrySummary() {
  const summary = [];
  
  for (const [id, tokenInfo] of tokenRegistry.tokens) {
    summary.push({
      id,
      type: tokenInfo.type,
      source: tokenInfo.source,
      account: tokenInfo.account,
      capabilities: tokenInfo.capabilities,
      rateLimit: {
        remaining: tokenInfo.rateLimit?.remaining ?? 'unknown',
        limit: tokenInfo.rateLimit?.limit ?? 'unknown',
        percentUsed: tokenInfo.rateLimit?.percentUsed ?? 'unknown',
        percentRemaining: tokenInfo.rateLimit?.percentRemaining ?? 'unknown',
        reset: tokenInfo.rateLimit?.reset 
          ? new Date(tokenInfo.rateLimit.reset).toISOString()
          : 'unknown',
      },
      status: getTokenStatus(tokenInfo),
    });
  }
  
  return summary;
}

/**
 * Check if the token registry has been initialized
 * @returns {boolean} True if registry contains tokens
 */
function isInitialized() {
  return tokenRegistry.tokens.size > 0;
}

/**
 * Get status label for a token based on remaining capacity
 */
function getTokenStatus(tokenInfo) {
  const remaining = tokenInfo.rateLimit?.remaining ?? 0;
  const limit = tokenInfo.rateLimit?.limit ?? 5000;
  const ratio = remaining / limit;
  
  if (ratio <= tokenRegistry.criticalThreshold) {
    return 'critical';
  } else if (ratio <= tokenRegistry.lowThreshold) {
    return 'low';
  } else if (ratio <= 0.5) {
    return 'moderate';
  } else {
    return 'healthy';
  }
}

/**
 * Check if any tokens are in critical state
 */
function hasHealthyTokens() {
  for (const [, tokenInfo] of tokenRegistry.tokens) {
    const status = getTokenStatus(tokenInfo);
    if (status === 'healthy' || status === 'moderate') {
      return true;
    }
  }
  return false;
}

/**
 * Get the token with most remaining capacity
 */
function getBestAvailableToken() {
  let best = null;
  let bestRemaining = -1;
  
  for (const [id, tokenInfo] of tokenRegistry.tokens) {
    const remaining = tokenInfo.rateLimit?.remaining ?? 0;
    if (remaining > bestRemaining) {
      best = { id, tokenInfo };
      bestRemaining = remaining;
    }
  }
  
  return best;
}

/**
 * Calculate estimated time until rate limits reset
 */
function getTimeUntilReset() {
  let earliestReset = Infinity;
  
  for (const [, tokenInfo] of tokenRegistry.tokens) {
    const reset = tokenInfo.rateLimit?.reset ?? Infinity;
    if (reset < earliestReset) {
      earliestReset = reset;
    }
  }
  
  if (earliestReset === Infinity) {
    return null;
  }
  
  const msUntilReset = earliestReset - Date.now();
  return Math.max(0, Math.ceil(msUntilReset / 1000 / 60)); // Minutes
}

/**
 * Should we defer operations due to rate limit pressure?
 */
function shouldDefer(minRemaining = 100) {
  for (const [, tokenInfo] of tokenRegistry.tokens) {
    if ((tokenInfo.rateLimit?.remaining ?? 0) >= minRemaining) {
      return false;
    }
  }
  return true;
}

module.exports = {
  initializeTokenRegistry,
  registerToken,
  refreshAllRateLimits,
  checkTokenRateLimit,
  getOptimalToken,
  isInitialized,
  updateTokenUsage,
  updateFromHeaders,
  getRegistrySummary,
  getTokenStatus,
  hasHealthyTokens,
  getBestAvailableToken,
  getTimeUntilReset,
  shouldDefer,
  TOKEN_CAPABILITIES,
  TOKEN_SPECIALIZATIONS,
  tokenRegistry, // Export for testing/debugging
};
