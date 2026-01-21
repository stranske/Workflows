'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const {
  extractScopeTasksAcceptanceSections,
  parseScopeTasksAcceptanceSections,
  hasNonPlaceholderScopeTasksAcceptanceContent,
} = require('./issue_scope_parser.js');
const { queryVerifierCiResults } = require('./verifier_ci_query.js');

const DEFAULT_BRANCH = process.env.DEFAULT_BRANCH || 'main';
const DEFAULT_DIFF_SUMMARY_PATH = 'verifier-diff-summary.md';
const DEFAULT_DIFF_PATH = 'verifier-pr-diff.patch';
const DEFAULT_DIFF_MAX_BYTES = 8 * 1024 * 1024;
const DEFAULT_DIFF_MAX_CHARS = 300000;
const SHA_PATTERN = /^[0-9a-f]{7,40}$/i;

const DIFF_SUMMARY_LIMITS = {
  maxFiles: 50,
  maxLines: 20000,
};

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

function summarizeDiff(diffText, { maxFiles, maxLines } = {}) {
  const summaryLines = ['## PR Diff Summary', ''];
  const diff = String(diffText || '').trim();
  if (!diff) {
    summaryLines.push('_Diff unavailable or empty._');
    return summaryLines.join('\n');
  }

  const fileSummaries = [];
  let current = null;
  let truncated = false;
  const lines = diff.split('\n');
  const lineLimit = Number.isFinite(maxLines) ? maxLines : DIFF_SUMMARY_LIMITS.maxLines;

  const pushCurrent = () => {
    if (current) {
      fileSummaries.push(current);
      current = null;
    }
  };

  for (let index = 0; index < lines.length; index += 1) {
    if (index >= lineLimit) {
      truncated = true;
      break;
    }
    const line = lines[index];
    if (line.startsWith('diff --git ')) {
      pushCurrent();
      const match = line.match(/^diff --git a\/(.+?) b\/(.+)$/);
      const fromPath = match ? match[1] : '';
      const toPath = match ? match[2] : '';
      current = {
        fromPath,
        toPath,
        status: 'modified',
        added: 0,
        removed: 0,
        binary: false,
      };
      continue;
    }
    if (!current) {
      continue;
    }
    if (line.startsWith('new file mode')) {
      current.status = 'added';
      continue;
    }
    if (line.startsWith('deleted file mode')) {
      current.status = 'deleted';
      continue;
    }
    if (line.startsWith('rename from ')) {
      current.status = 'renamed';
      current.fromPath = line.replace('rename from ', '').trim();
      continue;
    }
    if (line.startsWith('rename to ')) {
      current.status = 'renamed';
      current.toPath = line.replace('rename to ', '').trim();
      continue;
    }
    if (line.startsWith('Binary files ') || line.startsWith('GIT binary patch')) {
      current.binary = true;
      continue;
    }
    if (line.startsWith('+++') || line.startsWith('---')) {
      continue;
    }
    if (line.startsWith('+')) {
      current.added += 1;
    } else if (line.startsWith('-')) {
      current.removed += 1;
    }
  }
  pushCurrent();

  if (!fileSummaries.length) {
    summaryLines.push('_No file changes detected in diff._');
    return summaryLines.join('\n');
  }

  const totalAdded = fileSummaries.reduce((sum, file) => sum + file.added, 0);
  const totalRemoved = fileSummaries.reduce((sum, file) => sum + file.removed, 0);
  summaryLines.push(`- Files changed: ${fileSummaries.length}`);
  summaryLines.push(`- Total additions: ${totalAdded}`);
  summaryLines.push(`- Total deletions: ${totalRemoved}`);
  if (truncated) {
    summaryLines.push(`- Diff parsing truncated after ${lineLimit} lines.`);
  }
  summaryLines.push('', '### File changes');

  const fileLimit = Number.isFinite(maxFiles) ? maxFiles : DIFF_SUMMARY_LIMITS.maxFiles;
  const visible = fileSummaries.slice(0, fileLimit);
  for (const file of visible) {
    let label = file.toPath || file.fromPath || '(unknown file)';
    if (file.status === 'renamed' && file.fromPath) {
      label = `${file.fromPath} -> ${file.toPath || '(unknown)'}`;
    } else if (file.status === 'added') {
      label = `${label} (added)`;
    } else if (file.status === 'deleted') {
      label = `${label} (deleted)`;
    }
    const delta = file.binary ? 'binary' : `+${file.added}/-${file.removed}`;
    summaryLines.push(`- ${label} (${delta})`);
  }
  if (fileSummaries.length > visible.length) {
    summaryLines.push(`- ...and ${fileSummaries.length - visible.length} more files`);
  }

  return summaryLines.join('\n');
}

function isValidSha(value) {
  return SHA_PATTERN.test(String(value || ''));
}

function formatDiffForContext(diffText, maxChars) {
  const diff = String(diffText || '').trim();
  if (!diff) {
    return '_Diff unavailable or empty._';
  }
  const limit = Number.isFinite(maxChars) ? maxChars : DEFAULT_DIFF_MAX_CHARS;
  if (diff.length <= limit) {
    return diff;
  }
  return `${diff.slice(0, limit)}\n\n...diff truncated after ${limit} characters.`;
}

function fetchLocalGitDiff({ baseSha, headSha, maxBytes, core, execFile = execFileSync }) {
  if (!baseSha || !headSha) {
    return '';
  }
  if (!isValidSha(baseSha) || !isValidSha(headSha)) {
    core?.warning?.('Refusing to generate git diff: invalid SHA value.');
    return '';
  }
  try {
    const buffer = execFile('git', ['diff', '--no-color', `${baseSha}...${headSha}`], {
      maxBuffer: Number.isFinite(maxBytes) ? maxBytes : DEFAULT_DIFF_MAX_BYTES,
    });
    return buffer.toString('utf8');
  } catch (error) {
    core?.warning?.(`Failed to generate git diff locally: ${error.message}`);
    return '';
  }
}

async function fetchPullRequestDiff({ github, core, owner, repo, pullNumber }) {
  if (!github?.rest?.pulls?.get) {
    return '';
  }
  try {
    const response = await github.rest.pulls.get({
      owner,
      repo,
      pull_number: pullNumber,
      mediaType: { format: 'diff' },
    });
    if (typeof response?.data === 'string') {
      return response.data;
    }
    return '';
  } catch (error) {
    core?.warning?.(`Failed to fetch PR diff: ${error.message}`);
    return '';
  }
}

async function resolvePullRequest({ github, context, core }) {
  const { owner, repo } = context.repo;

  // Handle pull_request and pull_request_target events (both have PR in payload)
  if (context.eventName === 'pull_request' || context.eventName === 'pull_request_target') {
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

async function buildVerifierContext({ github, context, core, ciWorkflows }) {
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
    core?.setOutput?.('diff_summary_path', '');
    core?.setOutput?.('diff_path', '');
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
    core?.setOutput?.('diff_summary_path', '');
    core?.setOutput?.('diff_path', '');
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
    core?.setOutput?.('diff_summary_path', '');
    core?.setOutput?.('diff_path', '');
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
  // Use hasNonPlaceholderScopeTasksAcceptanceContent to detect real content vs placeholders
  let hasAcceptanceContent = false;
  let hasTasksContent = false;

  const pullSections = parseScopeTasksAcceptanceSections(pull.body || '');
  acceptanceCount += countCheckboxes(pullSections.acceptance);
  // Check for real acceptance content (not placeholders) from PR body
  if (hasNonPlaceholderScopeTasksAcceptanceContent(pull.body || '')) {
    // Check which specific sections have real content
    if (pullSections.acceptance && String(pullSections.acceptance).trim()) {
      hasAcceptanceContent = true;
    }
    if (pullSections.tasks && String(pullSections.tasks).trim()) {
      hasTasksContent = true;
    }
  }
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
    // Check for real acceptance/tasks content (not placeholders) from linked issues
    if (hasNonPlaceholderScopeTasksAcceptanceContent(issue.body || '')) {
      if (issueSectionsParsed.acceptance && String(issueSectionsParsed.acceptance).trim()) {
        hasAcceptanceContent = true;
      }
      if (issueSectionsParsed.tasks && String(issueSectionsParsed.tasks).trim()) {
        hasTasksContent = true;
      }
    }
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
  const ciTargetShas = [pull.merge_commit_sha, pull.head?.sha, context.sha].filter(Boolean);
  const targetSha = ciTargetShas[0] || '';
  if (targetSha) {
    content.push(`- Target commit: \`${targetSha}\``);
  }
  content.push(`- Pull request: [#${pull.number}](${pull.html_url || ''})`);
  content.push('');

  // Parse ciWorkflows if provided (can be array or JSON string)
  let workflows = null;
  if (Array.isArray(ciWorkflows)) {
    workflows = ciWorkflows.map((w) =>
      typeof w === 'string' ? { workflow_id: w, workflow_name: w } : w
    );
  } else if (typeof ciWorkflows === 'string') {
    const trimmed = ciWorkflows.trim();
    if (trimmed) {
      try {
        const parsed = JSON.parse(trimmed);
        workflows = Array.isArray(parsed)
          ? parsed.map((w) =>
              typeof w === 'string' ? { workflow_id: w, workflow_name: w } : w
            )
          : null;
      } catch {
        // Not valid JSON, treat as single workflow name
        workflows = [{ workflow_id: trimmed, workflow_name: trimmed }];
      }
    }
  }

  const ciResults = await queryVerifierCiResults({
    github,
    context,
    core,
    targetShas: ciTargetShas,
    workflows,
  });
  content.push('## CI Information (Reference Only)');
  content.push('');
  content.push('**Note:** This verification runs post-merge. CI status is irrelevant - focus on evaluating the code changes against acceptance criteria.');
  content.push('The CI results below are provided only to confirm which test suites ran, not for status evaluation.');
  content.push('');
  if (ciResults.length) {
    content.push('| Workflow | Conclusion | Run |');
    content.push('| --- | --- | --- |');
    for (const result of ciResults) {
      const runLink = result.run_url ? `[run](${result.run_url})` : 'n/a';
      content.push(`| ${result.workflow_name} | ${result.conclusion} | ${runLink} |`);
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

  // Skip verifier early if there are no acceptance criteria to verify
  // Check for any acceptance content (not just checkboxes) to handle plain-text criteria
  // Also require tasks content - PRs without both are likely bug fixes or simple changes
  // that weren't intended for structured agent verification
  if (!hasAcceptanceContent || !hasTasksContent) {
    const missingParts = [];
    if (!hasTasksContent) missingParts.push('tasks');
    if (!hasAcceptanceContent) missingParts.push('acceptance criteria');
    const skipReason = `No ${missingParts.join(' and ')} found in PR or linked issues; skipping verifier.`;
    core?.notice?.(skipReason);
    core?.setOutput?.('should_run', 'false');
    core?.setOutput?.('skip_reason', skipReason);
    core?.setOutput?.('pr_number', String(pull.number || ''));
    core?.setOutput?.('issue_numbers', '[]');
    core?.setOutput?.('pr_html_url', pull.html_url || '');
    core?.setOutput?.('target_sha', targetSha);
    core?.setOutput?.('context_path', '');
    core?.setOutput?.('acceptance_count', '0');
    core?.setOutput?.('ci_results', JSON.stringify(ciResults));
    core?.setOutput?.('diff_summary_path', '');
    core?.setOutput?.('diff_path', '');
    return { shouldRun: false, reason: skipReason, ciResults };
  }

  const diffMaxBytes = Number.parseInt(process.env.VERIFIER_DIFF_MAX_BYTES || '', 10);
  const diffMaxChars = Number.parseInt(process.env.VERIFIER_DIFF_MAX_CHARS || '', 10);
  const baseSha = pull.base?.sha;
  const headSha = pull.merge_commit_sha || pull.head?.sha || targetSha;
  let diffText = fetchLocalGitDiff({
    baseSha,
    headSha,
    maxBytes: Number.isFinite(diffMaxBytes) ? diffMaxBytes : DEFAULT_DIFF_MAX_BYTES,
    core,
  });
  if (!diffText) {
    diffText = await fetchPullRequestDiff({
      github,
      core,
      owner,
      repo,
      pullNumber: pull.number,
    });
  }
  const diffSummary = summarizeDiff(diffText, DIFF_SUMMARY_LIMITS);
  content.push('');
  content.push(diffSummary);
  if (diffText) {
    content.push('');
    content.push('## PR Diff (full)');
    content.push('');
    content.push('```diff');
    content.push(formatDiffForContext(diffText, Number.isFinite(diffMaxChars) ? diffMaxChars : DEFAULT_DIFF_MAX_CHARS));
    content.push('```');
  }

  const markdown = content.join('\n').trimEnd() + '\n';
  const contextPath = path.join(process.cwd(), 'verifier-context.md');
  fs.writeFileSync(contextPath, markdown, 'utf8');
  const diffSummaryPath = path.join(process.cwd(), DEFAULT_DIFF_SUMMARY_PATH);
  fs.writeFileSync(diffSummaryPath, diffSummary + '\n', 'utf8');
  const diffPath = path.join(process.cwd(), DEFAULT_DIFF_PATH);
  if (diffText) {
    fs.writeFileSync(diffPath, diffText + '\n', 'utf8');
  }

  core?.setOutput?.('should_run', 'true');
  core?.setOutput?.('skip_reason', '');
  core?.setOutput?.('pr_number', String(pull.number || ''));
  core?.setOutput?.('issue_numbers', JSON.stringify(issueNumbers));
  core?.setOutput?.('pr_html_url', pull.html_url || '');
  core?.setOutput?.('target_sha', targetSha);
  core?.setOutput?.('context_path', contextPath);
  core?.setOutput?.('acceptance_count', String(acceptanceCount));
  core?.setOutput?.('ci_results', JSON.stringify(ciResults));
  core?.setOutput?.('diff_summary_path', diffSummaryPath);
  core?.setOutput?.('diff_path', diffText ? diffPath : '');

  return {
    shouldRun: true,
    markdown,
    contextPath,
    diffSummary,
    diffSummaryPath,
    diffPath: diffText ? diffPath : '',
    issueNumbers,
    targetSha,
    acceptanceCount,
    ciResults,
  };
}

module.exports = {
  buildVerifierContext,
  formatDiffForContext,
  fetchLocalGitDiff,
  isValidSha,
};
