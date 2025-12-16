'use strict';

/**
 * agents_pr_meta_update_body.js
 * 
 * External script for the agents-pr-meta workflow's update_body job.
 * This script handles:
 * - Discovering the PR context from various event types
 * - Extracting sections from linked issues
 * - Building and updating PR body with preamble and status blocks
 */

const path = require('path');
const fs = require('fs');

// ========== Utility Functions ==========

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function normalizeWhitespace(text) {
  return String(text || '')
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => line.trim())
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractSection(body, heading) {
  if (!body || !heading) {
    return '';
  }
  const pattern = new RegExp(`^\\s*${heading}\\s*\\n+([\\s\\S]*?)(?=^\\s*\\S|$)`, 'im');
  const match = String(body).match(pattern);
  return match && match[1] ? match[1].trim() : '';
}

function ensureChecklist(text) {
  const lines = String(text || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) {
    return '- [ ] —';
  }
  return lines
    .map((line) => (line.startsWith('- [') ? line : `- [ ] ${line}`))
    .join('\n');
}

function extractBlock(body, marker) {
  const start = `<!-- ${marker}:start -->`;
  const end = `<!-- ${marker}:end -->`;
  const startIndex = (body || '').indexOf(start);
  const endIndex = (body || '').indexOf(end);
  if (startIndex === -1 || endIndex === -1 || endIndex <= startIndex) {
    return '';
  }
  return body.slice(startIndex + start.length, endIndex).trim();
}

function parseCheckboxStates(block) {
  const states = new Map();
  const lines = String(block || '').split(/\r?\n/);
  for (const line of lines) {
    const match = line.match(/^- \[(x| )\]\s*(.+)$/i);
    if (match) {
      const checked = match[1].toLowerCase() === 'x';
      const text = match[2].trim();
      const normalized = text.replace(/^-\s*/, '').trim().toLowerCase();
      if (normalized && checked) {
        states.set(normalized, true);
      }
    }
  }
  return states;
}

/**
 * Merge checkbox states from existingStates into newContent.
 * Only unchecked items `- [ ]` in newContent get their state restored.
 * This is intentional: already checked items in newContent preserve their state,
 * while unchecked items can be restored from the previous body state.
 */
function mergeCheckboxStates(newContent, existingStates) {
  if (!existingStates || existingStates.size === 0) {
    return newContent;
  }
  const lines = String(newContent || '').split(/\r?\n/);
  // Only match unchecked `- [ ]` items - checked items preserve their state
  return lines.map((line) => {
    const match = line.match(/^- \[( )\]\s*(.+)$/);
    if (match) {
      const text = match[2].trim();
      const normalized = text.replace(/^-\s*/, '').trim().toLowerCase();
      if (existingStates.has(normalized)) {
        return `- [x] ${text}`;
      }
    }
    return line;
  }).join('\n');
}

/**
 * List of bot logins that report task completion via comments.
 * These bots post checked checkboxes that should be captured and
 * merged into the PR body's Automated Status Summary.
 */
const CONNECTOR_BOT_LOGINS = [
  'chatgpt-codex-connector[bot]',
  'github-actions[bot]',  // Sometimes used for automation
];

/**
 * Fetch comments from connector bots and extract checked checkbox states.
 * This enables the keepalive system to detect when agents report task completion.
 * 
 * @param {Object} github - GitHub API client
 * @param {string} owner - Repository owner
 * @param {string} repo - Repository name
 * @param {number} prNumber - Pull request number
 * @param {Object} core - GitHub Actions core object for logging
 * @returns {Promise<Map<string, boolean>>} Map of normalized checkbox text to checked state
 */
async function fetchConnectorCheckboxStates(github, owner, repo, prNumber, core) {
  const states = new Map();
  
  try {
    const comments = await github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: prNumber,
      per_page: 100,
    });
    
    // Filter to connector bot comments only
    const connectorComments = comments.filter((c) => 
      c.user && CONNECTOR_BOT_LOGINS.includes(c.user.login)
    );
    
    if (connectorComments.length === 0) {
      return states;
    }
    
    // Parse checkbox states from all connector comments
    // Later comments override earlier ones (most recent state wins)
    for (const comment of connectorComments) {
      const commentStates = parseCheckboxStates(comment.body);
      for (const [key, value] of commentStates) {
        states.set(key, true);
      }
    }
    
    if (states.size > 0 && core) {
      core.info(`Found ${states.size} checked checkbox(es) from connector bot comments`);
    }
  } catch (error) {
    if (core) {
      core.warning(`Failed to fetch connector comments: ${error.message}`);
    }
  }
  
  return states;
}

function upsertBlock(body, marker, replacement) {
  const start = `<!-- ${marker}:start -->`;
  const end = `<!-- ${marker}:end -->`;

  const startIndex = body.indexOf(start);
  const endIndex = body.indexOf(end);
  if (startIndex !== -1 && endIndex !== -1 && endIndex > startIndex) {
    return `${body.slice(0, startIndex)}${replacement}${body.slice(endIndex + end.length)}`;
  }

  const trimmed = body.trimEnd();
  const prefix = trimmed ? `${trimmed}\n\n` : '';
  return `${prefix}${replacement}`;
}

// ========== API Helpers ==========

/**
 * Simple retry wrapper with linear backoff for general API errors.
 * 
 * Note: This differs from api-helpers.js `withBackoff` which specifically handles
 * rate limit errors (403/429) with exponential backoff and reset time extraction.
 * This function retries any error type with simple linear delay, suitable for
 * transient network/server errors during PR body updates.
 * 
 * @param {Function} fn - Async function to retry
 * @param {Object} options - Configuration options
 * @param {number} [options.attempts=3] - Number of attempts
 * @param {number} [options.delayMs=1000] - Base delay between attempts in ms
 * @param {string} [options.description] - Label for logging
 * @param {Object} [options.core] - GitHub Actions core object for logging
 * @returns {Promise<any>} Result of the function call
 */
async function withRetries(fn, options = {}) {
  const attempts = Number(options.attempts) || 3;
  const baseDelay = Number(options.delayMs) || 1000;
  const label = options.description || 'operation';
  const core = options.core;
  let lastError;
  
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      const status = error && typeof error.status === 'number' ? error.status : null;
      const message = error instanceof Error ? error.message : String(error);
      const headers = error?.response?.headers || {};
      const remainingRaw = headers['x-ratelimit-remaining'] ?? headers['X-RateLimit-Remaining'];
      const resetRaw = headers['x-ratelimit-reset'] ?? headers['X-RateLimit-Reset'];
      const remaining = typeof remainingRaw === 'string' ? Number(remainingRaw) : Number(remainingRaw);
      const reset = typeof resetRaw === 'string' ? Number(resetRaw) : Number(resetRaw);
      const isRateLimit = status === 403 && Number.isFinite(remaining) && remaining <= 0;
      const retryable = !status || status >= 500 || status === 429 || isRateLimit;
      
      if (!retryable || attempt === attempts) {
        if (core) core.error(`Failed ${label}: ${message}`);
        throw error;
      }
      
      let delay = baseDelay * attempt;
      if (isRateLimit && Number.isFinite(reset)) {
        const nowSeconds = Math.floor(Date.now() / 1000);
        const waitMs = Math.max((reset - nowSeconds) * 1000 + 500, delay);
        delay = Math.min(waitMs, 60000);
        if (core) core.warning(`Rate limit hit for ${label}; waiting ${delay}ms before retrying (attempt ${attempt + 1}/${attempts}).`);
      } else {
        if (core) core.warning(`Retrying ${label} after ${delay}ms (attempt ${attempt + 1}/${attempts}) due to ${status || 'error'}`);
      }
      await sleep(delay);
    }
  }
  throw lastError;
}

// ========== Status Block Functions ==========

function iconForStatus(status) {
  switch (status) {
    case 'success': return '✅';
    case 'skipped': return '⏭️';
    case 'cancelled': return '⏹️';
    case 'timed_out': return '⏱️';
    case 'failure': return '❌';
    case 'neutral': return '⚪';
    case 'pending':
    case 'waiting':
    case 'queued':
    case 'requested': return '⏳';
    default: return '❔';
  }
}

function friendlyStatus(status) {
  return (status || 'unknown').replace(/_/g, ' ');
}

function combineStatus(run) {
  if (!run) {
    return {icon: '❔', label: 'unknown'};
  }
  if (run.conclusion) {
    const normalized = run.conclusion.toLowerCase();
    return {icon: iconForStatus(normalized), label: friendlyStatus(normalized)};
  }
  if (run.status) {
    const normalized = run.status.toLowerCase();
    return {icon: iconForStatus(normalized), label: friendlyStatus(normalized)};
  }
  return {icon: '❔', label: 'unknown'};
}

function selectLatestWorkflows(runs) {
  const latest = new Map();
  for (const run of runs) {
    const name = run.name || 'Unnamed workflow';
    const key = name.toLowerCase();
    const existing = latest.get(key);
    if (!existing) {
      latest.set(key, run);
      continue;
    }
    if (new Date(run.created_at) > new Date(existing.created_at)) {
      latest.set(key, run);
    }
  }
  return latest;
}

function fallbackChecklist(message) {
  return `- [ ] ${message}`;
}

function buildPreamble(sections) {
  const lines = ['<!-- pr-preamble:start -->'];
  
  if (sections.summary && sections.summary.trim()) {
    lines.push('## Summary', sections.summary, '');
  }
  
  if (sections.testing && sections.testing.trim()) {
    lines.push('## Testing', sections.testing, '');
  }
  
  if (sections.ci && sections.ci.trim()) {
    lines.push('## CI readiness', sections.ci, '');
  }
  
  lines.push('<!-- pr-preamble:end -->');
  return lines.join('\n');
}

function buildStatusBlock({scope, tasks, acceptance, headSha, workflowRuns, requiredChecks, existingBody, connectorStates, core}) {
  const statusLines = ['<!-- auto-status-summary:start -->', '## Automated Status Summary'];

  const existingBlock = extractBlock(existingBody || '', 'auto-status-summary');
  const existingStates = parseCheckboxStates(existingBlock);
  
  // Merge existing PR body states with connector bot comment states
  // Connector states take precedence (they represent actual completion signals from agents)
  const mergedStates = new Map(existingStates);
  if (connectorStates && connectorStates.size > 0) {
    for (const [key, value] of connectorStates) {
      if (value) {
        mergedStates.set(key, true);
      }
    }
    if (core) {
      core.info(`Merged ${connectorStates.size} connector checkbox state(s) with ${existingStates.size} existing state(s) → ${mergedStates.size} total`);
    }
  } else if (existingStates.size > 0 && core) {
    core.info(`Preserving ${existingStates.size} checked item(s) from existing status summary`);
  }

  statusLines.push('#### Scope');
  let scopeFormatted = scope ? ensureChecklist(scope) : fallbackChecklist('Scope section missing from source issue.');
  scopeFormatted = mergeCheckboxStates(scopeFormatted, mergedStates);
  statusLines.push(scopeFormatted);
  statusLines.push('');

  statusLines.push('#### Tasks');
  let tasksFormatted = tasks ? ensureChecklist(tasks) : fallbackChecklist('Tasks section missing from source issue.');
  tasksFormatted = mergeCheckboxStates(tasksFormatted, mergedStates);
  statusLines.push(tasksFormatted);
  statusLines.push('');

  statusLines.push('#### Acceptance criteria');
  let acceptanceFormatted = acceptance ? ensureChecklist(acceptance) : fallbackChecklist('Acceptance criteria section missing from source issue.');
  acceptanceFormatted = mergeCheckboxStates(acceptanceFormatted, mergedStates);
  statusLines.push(acceptanceFormatted);
  statusLines.push('');

  statusLines.push(`**Head SHA:** ${headSha}`);

  const latestRuns = Array.from(workflowRuns.values()).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  let latestLine = '—';
  if (latestRuns.length > 0) {
    const gate = latestRuns.find((run) => (run.name || '').toLowerCase() === 'gate');
    const chosen = gate || latestRuns[0];
    const status = combineStatus(chosen);
    latestLine = `${status.icon} ${status.label} — ${chosen.name}`;
  }
  statusLines.push(`**Latest Runs:** ${latestLine}`);

  const requiredParts = [];
  for (const name of requiredChecks) {
    const run = Array.from(workflowRuns.values()).find((item) => (item.name || '').toLowerCase() === name.toLowerCase());
    if (!run) {
      requiredParts.push(`${name}: ⏸️ not started`);
    } else {
      const status = combineStatus(run);
      requiredParts.push(`${name}: ${status.icon} ${status.label}`);
    }
  }
  statusLines.push(`**Required:** ${requiredParts.length > 0 ? requiredParts.join(', ') : '—'}`);
  statusLines.push('');

  const table = ['| Workflow / Job | Result | Logs |', '|----------------|--------|------|'];
  const runs = Array.from(workflowRuns.values()).sort((a, b) => (a.name || '').localeCompare(b.name || ''));

  if (runs.length === 0) {
    table.push('| _(no workflow runs yet for this commit)_ | — | — |');
  } else {
    for (const run of runs) {
      const status = combineStatus(run);
      const link = run.html_url ? `[View run](${run.html_url})` : '—';
      table.push(`| ${run.name || 'Unnamed workflow'} | ${status.icon} ${status.label} | ${link} |`);
    }
  }

  statusLines.push(...table);
  statusLines.push('<!-- auto-status-summary:end -->');

  return statusLines.join('\n');
}

async function fetchRequiredChecks(github, owner, repo, baseRef, core) {
  const qualified = baseRef.startsWith('refs/') ? baseRef : `refs/heads/${baseRef}`;
  try {
    const result = await withRetries(
      () => github.graphql(
        `query($owner: String!, $repo: String!, $qualified: String!) {
          repository(owner: $owner, name: $repo) {
            ref(qualifiedName: $qualified) {
              branchProtectionRule {
                requiresStatusChecks
                requiredStatusCheckContexts
              }
            }
          }
        }`,
        {owner, repo, qualified},
      ),
      {description: 'branch protection graphql', core},
    );
    const rule = result?.repository?.ref?.branchProtectionRule;
    if (rule && rule.requiresStatusChecks && Array.isArray(rule.requiredStatusCheckContexts)) {
      return rule.requiredStatusCheckContexts.filter((item) => typeof item === 'string' && item.trim());
    }
  } catch (error) {
    const status = error && typeof error.status === 'number' ? error.status : null;
    if (status === 403) {
      if (core) core.info('Branch protection lookup unauthorized; skipping required check enrichment.');
      return [];
    }
    if (core) core.info(`Branch protection lookup failed: ${error.message}`);
  }
  return [];
}

// ========== PR Discovery ==========

async function discoverPr({github, context, core, inputs}) {
  const {owner, repo} = context.repo;
  
  if (context.eventName === 'workflow_dispatch') {
    const prNumber = inputs?.pr_number || '';
    if (prNumber && prNumber.trim()) {
      const num = Number.parseInt(prNumber.trim(), 10);
      if (!Number.isNaN(num)) {
        core.info(`Manual trigger: using PR #${num}`);
        const response = await withRetries(
          () => github.rest.pulls.get({owner, repo, pull_number: num}),
          {description: `pulls.get #${num}`, core},
        );
        return {number: num, headSha: response.data.head.sha};
      }
    }
    core.warning('workflow_dispatch without valid pr_number; skipping');
    return null;
  }

  if (context.eventName === 'pull_request') {
    const pr = context.payload.pull_request;
    return {number: pr.number, headSha: pr.head.sha};
  }

  if (context.eventName === 'workflow_run') {
    const run = context.payload.workflow_run;
    if (!run || run.event !== 'pull_request') {
      core.info('Workflow run not associated with a pull request.');
      return null;
    }

    const headSha = run.head_sha || '';
    const directMatch = Array.isArray(run.pull_requests)
      ? run.pull_requests.find((item) => item && item.head_sha === headSha) || run.pull_requests.find((item) => item && item.head_sha)
      : null;

    if (directMatch) {
      return { number: Number(directMatch.number), headSha: directMatch.head_sha || headSha };
    }

    if (headSha) {
      try {
        const { data } = await withRetries(
          () => github.rest.repos.listPullRequestsAssociatedWithCommit({ owner, repo, commit_sha: headSha }),
          { description: `list pull requests for ${headSha.slice(0, 7)}`, core },
        );

        const pr = Array.isArray(data) ? data.find((entry) => entry && entry.number) : null;
        if (pr) {
          return { number: pr.number, headSha };
        }
      } catch (error) {
        core.warning(`Failed to resolve PR for head ${headSha}: ${error.message}`);
      }
    }

    core.info('Unable to match workflow_run payload to a PR.');
    return null;
  }

  return null;
}

// ========== Main Entry Point ==========

async function run({github, context, core, inputs}) {
  const {owner, repo} = context.repo;
  const workspace = process.env.GITHUB_WORKSPACE || process.cwd();
  
  // Load external helper scripts
  let extractIssueNumberFromPull;
  let parseScopeTasksAcceptanceSections;

  try {
    const keepalivePath = path.resolve(workspace, '.github/scripts/agents_pr_meta_keepalive.js');
    const parserPath = path.resolve(workspace, '.github/scripts/issue_scope_parser.js');

    if (!fs.existsSync(keepalivePath)) {
      throw new Error(`Keepalive script not found at ${keepalivePath}`);
    }
    if (!fs.existsSync(parserPath)) {
      throw new Error(`Parser script not found at ${parserPath}`);
    }

    extractIssueNumberFromPull = require(keepalivePath).extractIssueNumberFromPull;
    parseScopeTasksAcceptanceSections = require(parserPath).parseScopeTasksAcceptanceSections;
    
    if (typeof extractIssueNumberFromPull !== 'function') {
      throw new Error('extractIssueNumberFromPull is not exported from keepalive script');
    }
    if (typeof parseScopeTasksAcceptanceSections !== 'function') {
      throw new Error('parseScopeTasksAcceptanceSections is not exported from parser script');
    }
  } catch (error) {
    core.setFailed(`Failed to load required scripts: ${error.message}`);
    return;
  }

  const prInfo = await discoverPr({github, context, core, inputs});
  if (!prInfo) {
    core.info('No pull request context detected; skipping update.');
    return;
  }

  const prResponse = await withRetries(
    () => github.rest.pulls.get({owner, repo, pull_number: prInfo.number}),
    {description: `pulls.get #${prInfo.number}`, core},
  );
  const pr = prResponse.data;
  
  if (pr.state === 'closed') {
    core.info(`Pull request #${pr.number} is closed; skipping update.`);
    return;
  }

  if (prInfo.headSha && pr.head && pr.head.sha && pr.head.sha !== prInfo.headSha) {
    core.info(`Skipping update for PR #${pr.number} because workflow run head ${prInfo.headSha} does not match current head ${pr.head.sha}.`);
    return;
  }

  const issueNumber = extractIssueNumberFromPull(pr);
  if (!issueNumber) {
    const warningMsg = `Unable to determine source issue for PR #${pr.number}. The PR title, branch name, or body must contain the issue number (e.g. #123, branch: issue-123, or the hidden marker <!-- meta:issue:123 -->).`;
    core.warning(warningMsg);

    try {
      const comments = await github.paginate(github.rest.issues.listComments, {
        owner,
        repo,
        issue_number: pr.number,
      });
      const alreadyWarned = comments.some((c) => c.body && c.body.includes('Unable to determine source issue'));
      
      if (!alreadyWarned) {
        await github.rest.issues.createComment({
          owner,
          repo,
          issue_number: pr.number,
          body: `⚠️ **Action Required**: ${warningMsg}`
        });
      }
    } catch (error) {
      core.warning(`Failed to post warning comment: ${error.message}`);
    }
    return;
  }

  core.info(`Fetching content from issue #${issueNumber} for PR #${pr.number}`);
  const issueResponse = await withRetries(
    () => github.rest.issues.get({owner, repo, issue_number: issueNumber}),
    {description: `issues.get #${issueNumber}`, core},
  );
  const issueBody = issueResponse.data.body || '';

  if (!issueBody) {
    core.warning(`Issue #${issueNumber} has no body content`);
  } else {
    core.debug(`Issue body length: ${issueBody.length} characters`);
  }

  function extractWithAliases(body, aliases) {
    for (const alias of aliases) {
      const content = extractSection(body, alias);
      if (content) return content;
    }
    return '';
  }

  function buildRichSummary(body) {
    core.info('Building rich summary from issue sections...');
    const why = normalizeWhitespace(extractSection(body, 'Why'));
    const scopeRaw = normalizeWhitespace(extractSection(body, 'Scope'));
    const nonGoals = normalizeWhitespace(extractSection(body, 'Non-Goals'));
    const goal = normalizeWhitespace(extractSection(body, 'Goal'));

    const parts = [];
    if (why) parts.push(why);
    if (goal) parts.push(goal);
    if (scopeRaw) parts.push(`\n**Scope:** ${scopeRaw}`);
    if (nonGoals) parts.push(`**Non-Goals:** ${nonGoals}`);

    return parts.join('\n\n');
  }

  const summaryRich = buildRichSummary(issueBody);
  const summary = summaryRich || normalizeWhitespace(extractWithAliases(issueBody, ['Summary', 'Description', 'Overview']));
  const testing = normalizeWhitespace(extractWithAliases(issueBody, ['Testing', 'Test Plan', 'Validation']));
  const ci = normalizeWhitespace(extractWithAliases(issueBody, ['CI readiness', 'Implementation notes', 'Technical notes']));

  const parsedSections = parseScopeTasksAcceptanceSections(issueBody);
  const scope = parsedSections.scope || extractSection(issueBody, 'Scope') || '';
  const tasks = parsedSections.tasks || extractSection(issueBody, 'Tasks') || '';
  const acceptance =
    parsedSections.acceptance
    || extractWithAliases(issueBody, ['Acceptance criteria', 'Success criteria', 'Definition of done'])
    || '';

  const preamble = buildPreamble({summary, testing, ci});

  const workflowRunResponse = await withRetries(
    () => github.rest.actions.listWorkflowRunsForRepo({
      owner,
      repo,
      head_sha: pr.head.sha,
      per_page: 100,
    }),
    {description: 'list workflow runs', core},
  );
  const workflowRuns = selectLatestWorkflows(workflowRunResponse.data.workflow_runs || []);

  const requiredChecksRaw = await fetchRequiredChecks(github, owner, repo, pr.base.ref, core);
  // Avoid mutating the returned array - create a new one with 'gate' appended if needed
  const requiredChecks = (!requiredChecksRaw.includes('gate') && pr.base.ref)
    ? [...requiredChecksRaw, 'gate']
    : requiredChecksRaw;

  // Fetch checkbox states from connector bot comments to merge into status summary
  const connectorStates = await fetchConnectorCheckboxStates(github, owner, repo, pr.number, core);

  const statusBlock = buildStatusBlock({
    scope,
    tasks,
    acceptance,
    headSha: prInfo.headSha,
    workflowRuns,
    requiredChecks,
    existingBody: pr.body,
    connectorStates,
    core,
  });

  const bodyWithPreamble = upsertBlock(pr.body || '', 'pr-preamble', preamble);
  const newBody = upsertBlock(bodyWithPreamble, 'auto-status-summary', statusBlock);

  if (newBody !== (pr.body || '')) {
    await withRetries(
      () => github.rest.pulls.update({
        owner,
        repo,
        pull_number: pr.number,
        body: newBody,
      }),
      {description: `pulls.update #${pr.number}`, delayMs: 1500, core},
    );
    core.info(`Updated PR #${pr.number} body with synchronized sections from issue #${issueNumber}.`);
    return;
  }

  core.info('PR body already up to date; no changes required.');
}

module.exports = {
  run,
  // Export utilities for testing
  normalizeWhitespace,
  extractSection,
  ensureChecklist,
  extractBlock,
  parseCheckboxStates,
  mergeCheckboxStates,
  fetchConnectorCheckboxStates,
  upsertBlock,
  buildPreamble,
  buildStatusBlock,
  withRetries,
  discoverPr,
};
