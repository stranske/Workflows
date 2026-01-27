'use strict';

/**
 * Conflict detector module for keepalive pipeline.
 * Detects merge conflicts on PRs to trigger conflict-specific prompts.
 */

const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

/**
 * Files to exclude from conflict detection.
 * These files have special merge strategies (e.g., merge=ours in .gitattributes)
 * or are .gitignored and should not block PR mergeability.
 */
const IGNORED_CONFLICT_FILES = [
  'pr_body.md',
  'ci/autofix/history.json',
  'keepalive-metrics.ndjson',
  'coverage-trend-history.ndjson',
  'metrics-history.ndjson',
  'residual-trend-history.ndjson',
];

// Comments from automation often mention "conflict" but should not block execution.
const IGNORED_COMMENT_AUTHORS = new Set([
  'github-actions[bot]',
  'github-merge-queue[bot]',
  'dependabot[bot]',
  'github',
]);

const IGNORED_COMMENT_MARKERS = [
  '<!-- keepalive-state',
  'keepalive-loop-summary',
  'auto-status-summary',
];

function isIgnoredComment(comment) {
  if (!comment) {
    return false;
  }

  const author = comment.user?.login || '';
  if (comment.user?.type === 'Bot' || IGNORED_COMMENT_AUTHORS.has(author)) {
    return true;
  }

  const body = comment.body || '';
  return IGNORED_COMMENT_MARKERS.some((marker) => body.includes(marker));
}

/**
 * Check if a file should be excluded from conflict detection.
 * @param {string} filename - File path to check
 * @returns {boolean} True if file should be ignored
 */
function shouldIgnoreConflictFile(filename) {
  return IGNORED_CONFLICT_FILES.some((ignored) => {
    // Exact match or ends with the ignored pattern
    return filename === ignored || filename.endsWith(`/${ignored}`);
  });
}

// Only match definitive merge conflict markers, not general text mentioning conflicts.
// The phrase "merge conflict" can appear in commit messages, comments, and other text
// without indicating an actual active conflict. We require git-generated markers.
const CONFLICT_PATTERNS = [
  // Git conflict markers (highly reliable)
  /<<<<<<< HEAD/,
  />>>>>>> [a-f0-9]{7,40}/,  // Conflict marker with SHA
  />>>>>>> origin\//,         // Conflict marker with remote branch
  // Git merge failure messages (from actual merge operations, not log text)
  /CONFLICT \(content\):/,    // Note: requires colon to be more specific
  /CONFLICT \(add\/add\):/,
  /CONFLICT \(modify\/delete\):/,
  /Automatic merge failed; fix conflicts and then commit/,  // Full message
];

/**
 * Check if a PR has merge conflicts via GitHub API.
 * @param {object} github - Octokit instance
 * @param {object} context - GitHub Actions context
 * @param {number} prNumber - PR number to check
 * @returns {Promise<{hasConflict: boolean, source: string, files: string[]}>}
 */
async function checkGitHubMergeability(github, context, prNumber) {
  try {
    const { data: pr } = await github.rest.pulls.get({
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: prNumber,
    });

    // mergeable_state can be: 'clean', 'dirty', 'unstable', 'blocked', 'behind', 'unknown'
    // 'dirty' indicates merge conflicts
    if (pr.mergeable_state === 'dirty' || pr.mergeable === false) {
      // Try to get conflict files from the PR
      const files = await getConflictFiles(github, context, prNumber);
      return {
        hasConflict: true,
        source: 'github-api',
        mergeableState: pr.mergeable_state,
        files,
      };
    }

    return {
      hasConflict: false,
      source: 'github-api',
      mergeableState: pr.mergeable_state,
      files: [],
    };
  } catch (error) {
    console.error(`Error checking PR mergeability: ${error.message}`);
    return {
      hasConflict: false,
      source: 'error',
      error: error.message,
      files: [],
    };
  }
}

/**
 * Get list of files that might have conflicts.
 * Note: GitHub doesn't directly expose conflict files, so we check changed files.
 * Filters out files with special merge strategies that should not block mergeability.
 * @param {object} github - Octokit instance
 * @param {object} context - GitHub Actions context
 * @param {number} prNumber - PR number
 * @returns {Promise<string[]>}
 */
async function getConflictFiles(github, context, prNumber) {
  try {
    const { data: files } = await github.rest.pulls.listFiles({
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: prNumber,
      per_page: 100,
    });

    // Filter out files that have special merge strategies or should be ignored
    const relevantFiles = files
      .map((f) => f.filename)
      .filter((filename) => !shouldIgnoreConflictFile(filename));

    if (relevantFiles.length < files.length) {
      const ignored = files.length - relevantFiles.length;
      console.log(`Filtered ${ignored} file(s) from conflict detection (special merge strategy)`);
    }

    return relevantFiles;
  } catch (error) {
    console.error(`Error getting PR files: ${error.message}`);
    return [];
  }
}

/**
 * Check CI logs for conflict indicators.
 * @param {object} github - Octokit instance
 * @param {object} context - GitHub Actions context
 * @param {number} prNumber - PR number
 * @param {string} headSha - Head commit SHA
 * @returns {Promise<{hasConflict: boolean, source: string, matchedPatterns: string[]}>}
 */
async function checkCILogsForConflicts(github, context, prNumber, headSha) {
  try {
    // Get recent workflow runs for this PR's head SHA
    const { data: runs } = await github.rest.actions.listWorkflowRunsForRepo({
      owner: context.repo.owner,
      repo: context.repo.repo,
      head_sha: headSha,
      per_page: 10,
    });

    const failedRuns = runs.workflow_runs.filter(
      (run) => run.conclusion === 'failure'
    );

    if (failedRuns.length === 0) {
      return { hasConflict: false, source: 'ci-logs', matchedPatterns: [] };
    }

    // Check job logs for conflict patterns
    for (const run of failedRuns.slice(0, 3)) {
      // Limit to 3 most recent
      try {
        const { data: jobs } = await github.rest.actions.listJobsForWorkflowRun(
          {
            owner: context.repo.owner,
            repo: context.repo.repo,
            run_id: run.id,
          }
        );

        for (const job of jobs.jobs.filter((j) => j.conclusion === 'failure')) {
          // Get job logs
          try {
            const { data: logs } =
              await github.rest.actions.downloadJobLogsForWorkflowRun({
                owner: context.repo.owner,
                repo: context.repo.repo,
                job_id: job.id,
              });

            const logText = typeof logs === 'string' ? logs : String(logs);
            const matchedPatterns = [];

            for (const pattern of CONFLICT_PATTERNS) {
              if (pattern.test(logText)) {
                matchedPatterns.push(pattern.source || pattern.toString());
              }
            }

            if (matchedPatterns.length > 0) {
              return {
                hasConflict: true,
                source: 'ci-logs',
                workflowRun: run.name,
                job: job.name,
                matchedPatterns,
              };
            }
          } catch (logError) {
            // Log download might fail for old runs, continue
            console.debug(`Could not download logs for job ${job.id}: ${logError.message}`);
            continue;
          }
        }
      } catch (jobError) {
        console.debug(`Could not list jobs for run ${run.id}: ${jobError.message}`);
        continue;
      }
    }

    return { hasConflict: false, source: 'ci-logs', matchedPatterns: [] };
  } catch (error) {
    console.error(`Error checking CI logs: ${error.message}`);
    return { hasConflict: false, source: 'error', error: error.message };
  }
}

/**
 * Check PR comments for conflict mentions.
 * @param {object} github - Octokit instance
 * @param {object} context - GitHub Actions context
 * @param {number} prNumber - PR number
 * @returns {Promise<{hasConflict: boolean, source: string}>}
 */
async function checkCommentsForConflicts(github, context, prNumber) {
  try {
    const { data: comments } = await github.rest.issues.listComments({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: prNumber,
      per_page: 20,
    });

    // Check recent comments (last 10) and ignore bot/system noise
    const recentComments = comments
      .filter((comment) => !isIgnoredComment(comment))
      .slice(-10);

    for (const comment of recentComments) {
      for (const pattern of CONFLICT_PATTERNS) {
        if (pattern.test(comment.body)) {
          return {
            hasConflict: true,
            source: 'pr-comments',
            commentId: comment.id,
            commentAuthor: comment.user.login,
          };
        }
      }
    }

    return { hasConflict: false, source: 'pr-comments' };
  } catch (error) {
    console.error(`Error checking PR comments: ${error.message}`);
    return { hasConflict: false, source: 'error', error: error.message };
  }
}

/**
 * Main conflict detection function.
 * Checks multiple sources for merge conflict indicators.
 * @param {object} github - Octokit instance
 * @param {object} context - GitHub Actions context
 * @param {number} prNumber - PR number to check
 * @param {string} [headSha] - Optional head SHA for CI log check
 * @returns {Promise<object>} Conflict detection result
 */
async function detectConflicts(rawGithub, context, prNumber, headSha) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, env: process.env });
  } catch (error) {
    console.warn(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const results = {
    hasConflict: false,
    detectionSources: [],
    files: [],
    details: {},
  };

  // Method 1: Check GitHub mergeability (most reliable)
  const githubResult = await checkGitHubMergeability(
    github,
    context,
    prNumber
  );
  results.detectionSources.push({
    source: 'github-api',
    result: githubResult,
  });

  if (githubResult.hasConflict) {
    results.hasConflict = true;
    results.files = githubResult.files;
    results.primarySource = 'github-api';
    results.details.mergeableState = githubResult.mergeableState;
  }

  // Method 2: Check CI logs (if head SHA provided)
  if (headSha) {
    const ciResult = await checkCILogsForConflicts(
      github,
      context,
      prNumber,
      headSha
    );
    results.detectionSources.push({
      source: 'ci-logs',
      result: ciResult,
    });

    if (ciResult.hasConflict && !results.hasConflict) {
      results.hasConflict = true;
      results.primarySource = 'ci-logs';
      results.details.matchedPatterns = ciResult.matchedPatterns;
    }
  }

  // Method 3: Check PR comments
  const commentResult = await checkCommentsForConflicts(
    github,
    context,
    prNumber
  );
  results.detectionSources.push({
    source: 'pr-comments',
    result: commentResult,
  });

  if (commentResult.hasConflict && !results.hasConflict) {
    results.hasConflict = true;
    results.primarySource = 'pr-comments';
  }

  return results;
}

/**
 * Post a conflict detection comment on the PR.
 * @param {object} github - Octokit instance
 * @param {object} context - GitHub Actions context
 * @param {number} prNumber - PR number
 * @param {object} conflictResult - Result from detectConflicts
 * @returns {Promise<void>}
 */
async function postConflictComment(github, context, prNumber, conflictResult) {
  if (!conflictResult.hasConflict) {
    return;
  }

  const files = conflictResult.files.slice(0, 10); // Limit to 10 files
  const fileList =
    files.length > 0
      ? `\n\n**Potentially affected files:**\n${files.map((f) => `- \`${f}\``).join('\n')}`
      : '';

  const body = `### ⚠️ Merge Conflict Detected

This PR has merge conflicts that need to be resolved before it can be merged.

**Detection source:** ${conflictResult.primarySource}${fileList}

<details>
<summary>How to resolve</summary>

1. Fetch the latest changes from the base branch
2. Merge or rebase your branch
3. Resolve any conflicts in affected files
4. Commit and push the resolved changes

Or wait for the agent to attempt automatic resolution.
</details>

---
*Auto-detected by conflict detector*`;

  // Check for existing conflict comment
  const { data: comments } = await github.rest.issues.listComments({
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: prNumber,
    per_page: 30,
  });

  const existingComment = comments.find(
    (c) =>
      c.body.includes('### ⚠️ Merge Conflict Detected') && c.user.type === 'Bot'
  );

  if (existingComment) {
    // Update existing comment
    await github.rest.issues.updateComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      comment_id: existingComment.id,
      body,
    });
  } else {
    // Create new comment
    await github.rest.issues.createComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: prNumber,
      body,
    });
  }
}

module.exports = {
  detectConflicts,
  checkGitHubMergeability,
  checkCILogsForConflicts,
  checkCommentsForConflicts,
  postConflictComment,
  shouldIgnoreConflictFile,
  CONFLICT_PATTERNS,
  IGNORED_CONFLICT_FILES,
};
