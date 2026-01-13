'use strict';

/**
 * GraphQL-based PR Context Fetcher
 * 
 * MEDIUM EFFORT OPTIMIZATION: Replace multiple REST API calls with a single
 * GraphQL query to fetch all PR context data at once.
 * 
 * Typical REST pattern (4+ calls):
 *   - GET /pulls/{number}
 *   - GET /pulls/{number}/files
 *   - GET /issues/{number}/labels
 *   - GET /issues/{number}/comments
 * 
 * GraphQL pattern (1 call):
 *   - Single query fetches all data
 *   - 60-80% reduction in API calls
 */

/**
 * GraphQL query to fetch comprehensive PR context
 * Fetches: body, title, files, labels, reviews, last commit, merge status
 */
const PR_CONTEXT_QUERY = `
query PRContext($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      id
      number
      title
      body
      state
      isDraft
      mergeable
      merged
      mergedAt
      headRefName
      baseRefName
      headRefOid
      
      author {
        login
      }
      
      labels(first: 50) {
        nodes {
          name
          color
        }
      }
      
      files(first: 100) {
        totalCount
        nodes {
          path
          additions
          deletions
          changeType
        }
      }
      
      reviews(last: 10, states: [APPROVED, CHANGES_REQUESTED, COMMENTED]) {
        nodes {
          state
          author { login }
          body
          submittedAt
        }
      }
      
      comments(last: 20) {
        totalCount
        nodes {
          author { login }
          body
          createdAt
          isMinimized
        }
      }
      
      commits(last: 1) {
        nodes {
          commit {
            oid
            message
            statusCheckRollup {
              state
              contexts(first: 50) {
                nodes {
                  ... on CheckRun {
                    name
                    conclusion
                    status
                  }
                  ... on StatusContext {
                    context
                    state
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
`;

/**
 * Lighter query for basic PR info (when full context isn't needed)
 */
const PR_BASIC_QUERY = `
query PRBasic($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      title
      body
      state
      isDraft
      merged
      headRefName
      baseRefName
      headRefOid
      author { login }
      labels(first: 30) {
        nodes { name }
      }
    }
  }
}
`;

/**
 * PAGINATION LIMITS:
 * The GraphQL queries above use fixed pagination limits:
 * - labels: 50 (most PRs have <10 labels)
 * - files: 100 (large PRs may exceed this - check filesCount vs files.length)
 * - reviews: 10 (last 10 reviews, most recent first)
 * - comments: 20 (last 20 comments, filtering minimized)
 * - contexts (CI checks): 50 (sufficient for most repos)
 *
 * For PRs exceeding these limits, the data will be truncated.
 * The filesCount field indicates total files; compare with files.length to detect truncation.
 */

/**
 * Fetch comprehensive PR context using GraphQL
 * 
 * @param {Object} github - Octokit client (with graphql method)
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {number} number - PR number
 * @returns {Object} PR context data
 */
async function fetchPRContext(github, owner, repo, number) {
  try {
    const result = await github.graphql(PR_CONTEXT_QUERY, {
      owner,
      repo,
      number: parseInt(number, 10)
    });
    
    const pr = result.repository.pullRequest;
    if (!pr) {
      throw new Error(`PR #${number} not found in ${owner}/${repo}`);
    }
    
    // Transform to a more usable format
    return {
      id: pr.id,
      number: pr.number,
      title: pr.title,
      body: pr.body || '',
      state: pr.state,
      isDraft: pr.isDraft,
      mergeable: pr.mergeable,
      merged: pr.merged,
      mergedAt: pr.mergedAt,
      headRef: pr.headRefName,
      baseRef: pr.baseRefName,
      headSha: pr.headRefOid,
      author: pr.author?.login || 'unknown',
      
      labels: (pr.labels?.nodes || []).map(l => l.name),
      labelsDetailed: pr.labels?.nodes || [],
      
      files: {
        total: pr.files?.totalCount || 0,
        paths: (pr.files?.nodes || []).map(f => f.path),
        detailed: pr.files?.nodes || []
      },
      
      reviews: (pr.reviews?.nodes || []).map(r => ({
        state: r.state,
        author: r.author?.login,
        body: r.body,
        submittedAt: r.submittedAt
      })),
      
      comments: {
        total: pr.comments?.totalCount || 0,
        recent: (pr.comments?.nodes || [])
          .filter(c => !c.isMinimized)
          .map(c => ({
            author: c.author?.login,
            body: c.body,
            createdAt: c.createdAt
          }))
      },
      
      lastCommit: pr.commits?.nodes?.[0]?.commit ? {
        sha: pr.commits.nodes[0].commit.oid,
        message: pr.commits.nodes[0].commit.message,
        status: pr.commits.nodes[0].commit.statusCheckRollup?.state || 'UNKNOWN',
        checks: (pr.commits.nodes[0].commit.statusCheckRollup?.contexts?.nodes || [])
          .map(c => ({
            name: c.name || c.context,
            status: c.status || c.state,
            conclusion: c.conclusion
          }))
      } : null,
      
      // Computed helpers
      hasLabel: (label) => (pr.labels?.nodes || []).some(l => l.name === label),
      hasAnyLabel: (labels) => (pr.labels?.nodes || []).some(l => labels.includes(l.name)),
      hasAllLabels: (labels) => labels.every(label => 
        (pr.labels?.nodes || []).some(l => l.name === label)
      )
    };
  } catch (error) {
    // Enhance error with context
    error.message = `Failed to fetch PR context for ${owner}/${repo}#${number}: ${error.message}`;
    throw error;
  }
}

/**
 * Fetch basic PR info using GraphQL (lighter query)
 * 
 * @param {Object} github - Octokit client
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {number} number - PR number
 * @returns {Object} Basic PR data
 */
async function fetchPRBasic(github, owner, repo, number) {
  const result = await github.graphql(PR_BASIC_QUERY, {
    owner,
    repo,
    number: parseInt(number, 10)
  });
  
  const pr = result.repository.pullRequest;
  if (!pr) {
    throw new Error(`PR #${number} not found in ${owner}/${repo}`);
  }
  
  return {
    number: pr.number,
    title: pr.title,
    body: pr.body || '',
    state: pr.state,
    isDraft: pr.isDraft,
    merged: pr.merged,
    headRef: pr.headRefName,
    baseRef: pr.baseRefName,
    headSha: pr.headRefOid,
    author: pr.author?.login || 'unknown',
    labels: (pr.labels?.nodes || []).map(l => l.name),
    hasLabel: (label) => (pr.labels?.nodes || []).some(l => l.name === label)
  };
}

/**
 * Serialize PR context for passing between jobs via outputs
 * 
 * @param {Object} prContext - PR context from fetchPRContext
 * @returns {string} JSON string safe for GitHub Actions outputs
 */
function serializeForOutput(prContext) {
  // Create a serializable version without functions
  // Includes all fields returned by fetchPRContext for full round-trip support
  const serializable = {
    id: prContext.id,
    number: prContext.number,
    title: prContext.title,
    body: prContext.body,
    state: prContext.state,
    isDraft: prContext.isDraft,
    mergeable: prContext.mergeable,
    merged: prContext.merged,
    mergedAt: prContext.mergedAt,
    headRef: prContext.headRef,
    baseRef: prContext.baseRef,
    headSha: prContext.headSha,
    author: prContext.author,
    labels: prContext.labels,
    labelsDetailed: prContext.labelsDetailed,
    filesCount: prContext.filesCount,
    files: prContext.files,
    reviews: prContext.reviews,
    comments: prContext.comments,
    lastCommit: prContext.lastCommit
  };
  
  return JSON.stringify(serializable);
}

/**
 * Deserialize PR context from job output
 * 
 * @param {string} json - JSON string from job output
 * @returns {Object} PR context with helper methods restored
 */
function deserializeFromOutput(json) {
  const data = JSON.parse(json);
  
  // Restore helper methods
  data.hasLabel = (label) => data.labels.includes(label);
  data.hasAnyLabel = (labels) => data.labels.some(l => labels.includes(l));
  data.hasAllLabels = (labels) => labels.every(l => data.labels.includes(l));
  
  return data;
}

/**
 * Create a caching wrapper for PR context
 * Useful when multiple scripts need the same PR data
 */
function createPRContextCache() {
  const cache = new Map();
  
  return {
    async get(github, owner, repo, number) {
      const key = `${owner}/${repo}#${number}`;
      
      if (cache.has(key)) {
        return cache.get(key);
      }
      
      const context = await fetchPRContext(github, owner, repo, number);
      cache.set(key, context);
      return context;
    },
    
    set(owner, repo, number, context) {
      const key = `${owner}/${repo}#${number}`;
      cache.set(key, context);
    },
    
    has(owner, repo, number) {
      const key = `${owner}/${repo}#${number}`;
      return cache.has(key);
    },
    
    clear() {
      cache.clear();
    }
  };
}

module.exports = {
  PR_CONTEXT_QUERY,
  PR_BASIC_QUERY,
  fetchPRContext,
  fetchPRBasic,
  serializeForOutput,
  deserializeFromOutput,
  createPRContextCache
};
