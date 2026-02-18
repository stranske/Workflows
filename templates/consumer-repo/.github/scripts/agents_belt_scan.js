'use strict';

const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

/**
 * Check if a branch matches any known agent belt branch pattern.
 * Tries the registry first, falls back to the default codex/issue-<n> pattern.
 */
function isAgentBeltBranch(branch) {
  if (!branch) return false;
  try {
    const { loadAgentRegistry } = require('./agent_registry.js');
    const registry = loadAgentRegistry();
    const agents = registry.agents || {};
    for (const key of Object.keys(agents)) {
      const prefix = agents[key].branch_prefix;
      if (prefix && branch.startsWith(prefix)) {
        const suffix = branch.slice(prefix.length);
        if (/^\d+$/.test(suffix)) return true;
      }
    }
  } catch (_) { /* registry not available */ }
  // Fallback: match any pattern like <agent>/issue-<n>
  return /^[a-z]+\/issue-\d+$/.test(branch);
}

// Backwards-compat alias
const isCodexBranch = isAgentBeltBranch;

/**
 * Extract issue number from a belt branch name.
 * Supports any prefix pattern (codex/issue-<n>, claude/issue-<n>, etc.)
 */
function extractIssueFromBranch(branch) {
  if (!branch) return null;
  const match = branch.match(/\/issue-(\d+)$/);
  return match ? Number(match[1]) : null;
}

async function identifyReadyBeltPRs({ github, context, core, env = process.env }) {
  const maxPromotionsRaw = env.MAX_PROMOTIONS || '0';
  const maxPromotions = Math.max(0, Math.floor(Number(maxPromotionsRaw || '0')));
  const automergeLabel = (env.AUTOMERGE_LABEL || 'automerge').trim().toLowerCase();
  const { owner, repo } = context.repo;

  const { data: pulls } = await github.rest.pulls.list({ owner, repo, state: 'open', per_page: 50 });
  const candidates = [];
  const skipped = [];

  for (const pr of pulls) {
    if (!pr || typeof pr !== 'object') {
      continue;
    }
    const branch = pr.head && pr.head.ref ? pr.head.ref : '';
    if (!isAgentBeltBranch(branch)) {
      continue;
    }
    if (pr.draft) {
      skipped.push({ pr: pr.number, reason: 'draft' });
      continue;
    }

    // Check for automerge label
    const labels = (pr.labels || [])
      .map((label) => {
        if (!label) return '';
        if (typeof label === 'string') return label.toLowerCase();
        if (typeof label.name === 'string') return label.name.toLowerCase();
        return '';
      })
      .filter(Boolean);

    if (!labels.includes(automergeLabel)) {
      skipped.push({ pr: pr.number, reason: `missing '${automergeLabel}' label` });
      continue;
    }

    const headSha = pr.head && pr.head.sha ? pr.head.sha : '';
    if (!headSha) {
      skipped.push({ pr: pr.number, reason: 'no head SHA' });
      continue;
    }
    const { data: status } = await github.rest.repos.getCombinedStatusForRef({ owner, repo, ref: headSha });
    if (!status || status.state !== 'success') {
      skipped.push({ pr: pr.number, reason: `status: ${status?.state || 'unknown'}` });
      continue;
    }
    const issue = extractIssueFromBranch(branch);
    candidates.push({
      pr: pr.number,
      issue,
      branch,
      head_sha: headSha
    });
    if (maxPromotions && candidates.length >= maxPromotions) {
      break;
    }
  }

  const summary = core.summary;
  summary
    .addHeading('Belt conveyor scan')
    .addRaw(`Automerge label: \`${automergeLabel}\``)
    .addEOL()
    .addRaw(`Ready pull requests: ${candidates.length}`)
    .addEOL();
  if (candidates.length) {
    summary.addTable([
      [{ data: 'PR', header: true }, { data: 'Issue', header: true }, { data: 'Branch', header: true }],
      ...candidates.map((entry) => [
        `#${entry.pr}`,
        entry.issue ? `#${entry.issue}` : '(unknown)',
        entry.branch
      ])
    ]);
  }
  if (skipped.length) {
    summary
      .addHeading('Skipped PRs', 3)
      .addTable([
        [{ data: 'PR', header: true }, { data: 'Reason', header: true }],
        ...skipped.map((entry) => [`#${entry.pr}`, entry.reason])
      ]);
  }
  await summary.write();

  core.setOutput('items', JSON.stringify(candidates));
  return { candidates };
}

module.exports = {
  // New names
  identifyReadyBeltPRs: async function ({ github: rawGithub, context, core, env = process.env }) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env });
    return identifyReadyBeltPRs({ github, context, core, env });
  },
  isAgentBeltBranch,
  extractIssueFromBranch,
  // Backwards-compat aliases (used by orchestrator-main and tests)
  identifyReadyCodexPRs: async function ({ github: rawGithub, context, core, env = process.env }) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env });
    return identifyReadyBeltPRs({ github, context, core, env });
  },
  isCodexBranch,
};
