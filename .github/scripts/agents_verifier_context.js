'use strict';

const fs = require('fs');
const path = require('path');

const {
  extractScopeTasksAcceptanceSections,
  parseScopeTasksAcceptanceSections,
} = require('./issue_scope_parser.js');
const { queryVerifierCiResults } = require('./verifier_ci_query.js');

const DEFAULT_BRANCH = process.env.DEFAULT_BRANCH || 'main';

function uniqueNumbers(values) {
  return Array.from(
    new Set(
      (values || [])
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value) && value > 0)
    )
  );
}

/**
 * Count markdown checkboxes within acceptance-criteria content.
 *
 * This helper is intended to be used on the "Acceptance criteria"
 * section(s) extracted from issues or pull requests, not on arbitrary
 * markdown content.
 *
 * @param {string} acceptanceContent - The acceptance-criteria text to scan.
 * @returns {number} The number of checkbox items found.
 */
function countCheckboxes(acceptanceContent) {
  const matches = String(acceptanceContent || '').match(/(^|\n)\s*[-*]\s+\[[ xX]\]/gi);
  return matches ? matches.length : 0;
}

function isForkPullRequest(pr) {
  const headRepo = pr?.head?.repo;
  const baseRepo = pr?.base?.repo;
  if (headRepo?.fork === true) {
    return true;
  }
  const headFullName = headRepo?.full_name;
  const baseFullName = baseRepo?.full_name;
  if (headFullName && baseFullName && headFullName !== baseFullName) {
    return true;
  }
  const headOwner = headRepo?.owner?.login;
  const baseOwner = baseRepo?.owner?.login;
  if (headOwner && baseOwner && headOwner !== baseOwner) {
    return true;
  }
  return false;
}

function formatSections({ heading, url, body }) {
  const lines = [];
  lines.push(`### ${heading}`);
  if (url) {
    lines.push(`Source: ${url}`);
  }
  if (body) {
    lines.push('', body);
  } else {
    lines.push('', '_No scope/tasks/acceptance criteria found in this source._');
  }
  return lines.join('\n');
}

async function resolvePullRequest({ github, context, core }) {
  const { owner, repo } = context.repo;

  if (context.eventName === 'pull_request') {
    const pr = context.payload?.pull_request;
    if (!pr || pr.merged !== true) {
      return { pr: null, reason: 'Pull request is not merged; skipping verifier.' };
    }
    return { pr };
  }

  const sha = process.env.VERIFIER_TARGET_SHA || context.payload?.after || context.sha;
  if (!sha) {
    return { pr: null, reason: 'Missing commit SHA for push event; skipping verifier.' };
  }

  try {
    const { data } = await github.rest.repos.listPullRequestsAssociatedWithCommit({
      owner,
      repo,
      commit_sha: sha,
    });
    const merged = (data || []).find((pr) => pr.merged_at);
    const pr = merged || (data || [])[0] || null;
    if (!pr) {
      return { pr: null, reason: 'No pull request associated with push; skipping verifier.' };
    }
    return { pr };
  } catch (error) {
    core?.warning?.(`Failed to resolve pull request from push commit: ${error.message}`);
    return { pr: null, reason: 'Unable to resolve pull request from push event.' };
  }
}

async function fetchClosingIssues({ github, core, owner, repo, prNumber }) {
  const query = `
    query($owner: String!, $repo: String!, $prNumber: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
          closingIssuesReferences(first: 20) {
            nodes {
              number
              title
              body
              state
              url
            }
          }
        }
      }
    }
  `;

  try {
    const data = await github.graphql(query, { owner, repo, prNumber });
    const nodes =
      data?.repository?.pullRequest?.closingIssuesReferences?.nodes?.filter(Boolean) || [];
    return nodes.map((issue) => ({
      number: issue.number,
      title: issue.title || '',
      body: issue.body || '',
      state: issue.state || 'UNKNOWN',
      url: issue.url || '',
    }));
  } catch (error) {
    core?.warning?.(`Failed to fetch closing issues: ${error.message}`);
    return [];
  }
}

async function buildVerifierContext({ github, context, core }) {
  const { owner, repo } = context.repo;
  const { pr, reason: resolveReason } = await resolvePullRequest({ github, context, core });
  if (!pr) {
    core?.notice?.(resolveReason || 'No pull request detected; skipping verifier.');
    core?.setOutput?.('should_run', 'false');
    core?.setOutput?.('skip_reason', resolveReason || 'No pull request detected.');
    core?.setOutput?.('pr_number', '');
    core?.setOutput?.('issue_numbers', '[]');
    core?.setOutput?.('pr_html_url', '');
    core?.setOutput?.('target_sha', context.sha || '');
    core?.setOutput?.('context_path', '');
    core?.setOutput?.('acceptance_count', '0');
    core?.setOutput?.('ci_results', '[]');
    return {
      shouldRun: false,
      reason: resolveReason || 'No pull request detected.',
      ciResults: [],
    };
  }

  const baseRef = pr.base?.ref || '';
  const defaultBranch = context.payload?.repository?.default_branch || DEFAULT_BRANCH;
  if (baseRef && baseRef !== defaultBranch) {
    const skipReason = `Pull request base ref ${baseRef} does not match default branch ${defaultBranch}; skipping verifier.`;
    core?.notice?.(skipReason);
    core?.setOutput?.('should_run', 'false');
    core?.setOutput?.('skip_reason', skipReason);
    core?.setOutput?.('pr_number', String(pr.number || ''));
    core?.setOutput?.('issue_numbers', '[]');
    core?.setOutput?.('pr_html_url', pr.html_url || '');
    core?.setOutput?.('target_sha', pr.merge_commit_sha || pr.head?.sha || context.sha || '');
    core?.setOutput?.('context_path', '');
    core?.setOutput?.('acceptance_count', '0');
    core?.setOutput?.('ci_results', '[]');
    return { shouldRun: false, reason: skipReason, ciResults: [] };
  }

  const prDetails = await github.rest.pulls.get({ owner, repo, pull_number: pr.number });
  const pull = prDetails?.data || pr;

  if (isForkPullRequest(pull)) {
    const skipReason = 'Pull request is from a fork; skipping verifier.';
    core?.notice?.(skipReason);
    core?.setOutput?.('should_run', 'false');
    core?.setOutput?.('skip_reason', skipReason);
    core?.setOutput?.('pr_number', String(pull.number || ''));
    core?.setOutput?.('issue_numbers', '[]');
    core?.setOutput?.('pr_html_url', pull.html_url || '');
    core?.setOutput?.('target_sha', pull.merge_commit_sha || pull.head?.sha || context.sha || '');
    core?.setOutput?.('context_path', '');
    core?.setOutput?.('acceptance_count', '0');
    core?.setOutput?.('ci_results', '[]');
    return { shouldRun: false, reason: skipReason, ciResults: [] };
  }

  const closingIssues = await fetchClosingIssues({
    github,
    core,
    owner,
    repo,
    prNumber: pull.number,
  });
  const issueNumbers = uniqueNumbers(closingIssues.map((issue) => issue.number));

  const sections = [];
  let acceptanceCount = 0;

  const pullSections = parseScopeTasksAcceptanceSections(pull.body || '');
  acceptanceCount += countCheckboxes(pullSections.acceptance);
  const prSections = extractScopeTasksAcceptanceSections(pull.body || '', {
    includePlaceholders: true,
  });
  sections.push(
    formatSections({
      heading: `Pull request #${pull.number}${pull.title ? `: ${pull.title}` : ''}`,
      url: pull.html_url || '',
      body: prSections,
    })
  );

  for (const issue of closingIssues) {
    const issueSectionsParsed = parseScopeTasksAcceptanceSections(issue.body || '');
    acceptanceCount += countCheckboxes(issueSectionsParsed.acceptance);
    const issueSections = extractScopeTasksAcceptanceSections(issue.body || '', {
      includePlaceholders: true,
    });
    sections.push(
      formatSections({
        heading: `Issue #${issue.number}${issue.title ? `: ${issue.title}` : ''} (${issue.state})`,
        url: issue.url || '',
        body: issueSections,
      })
    );
  }

  const content = [];
  content.push('# Verifier context');
  content.push('');
  content.push(`- Repository: ${owner}/${repo}`);
  content.push(`- Base branch: ${baseRef || defaultBranch}`);
  const targetSha = pull.merge_commit_sha || pull.head?.sha || context.sha || '';
  if (targetSha) {
    content.push(`- Target commit: \`${targetSha}\``);
  }
  content.push(`- Pull request: [#${pull.number}](${pull.html_url || ''})`);
  content.push('');
  const ciResults = await queryVerifierCiResults({ github, context, core, targetSha });
  content.push('## CI Verification');
  content.push('');
  content.push('Use these CI results to verify test-related criteria; do not rerun test suites locally.');
  content.push('');
  if (ciResults.length) {
    for (const result of ciResults) {
      const runLink = result.run_url ? `[run](${result.run_url})` : 'no run link';
      content.push(`- ${result.workflow_name}: ${result.conclusion} (${runLink})`);
    }
  } else {
    content.push('_No CI workflow runs were found for the target commit._');
  }
  content.push('');
  content.push('## Plan sources (scope, tasks, acceptance)');
  content.push('');
  if (sections.length) {
    content.push(sections.join('\n\n---\n\n'));
  } else {
    content.push('_No scope, tasks, or acceptance criteria were found in the pull request or linked issues._');
  }

  const markdown = content.join('\n').trimEnd() + '\n';
  const contextPath = path.join(process.cwd(), 'verifier-context.md');
  fs.writeFileSync(contextPath, markdown, 'utf8');

  core?.setOutput?.('should_run', 'true');
  core?.setOutput?.('skip_reason', '');
  core?.setOutput?.('pr_number', String(pull.number || ''));
  core?.setOutput?.('issue_numbers', JSON.stringify(issueNumbers));
  core?.setOutput?.('pr_html_url', pull.html_url || '');
  core?.setOutput?.('target_sha', targetSha);
  core?.setOutput?.('context_path', contextPath);
  core?.setOutput?.('acceptance_count', String(acceptanceCount));
  core?.setOutput?.('ci_results', JSON.stringify(ciResults));

  return {
    shouldRun: true,
    markdown,
    contextPath,
    issueNumbers,
    targetSha,
    acceptanceCount,
    ciResults,
  };
}

module.exports = {
  buildVerifierContext,
};
