const { Buffer } = require('node:buffer');
const { minimatch } = require('minimatch');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

async function fetchAllowlist(github, owner, repo, path, ref) {
  let found = false;
  let patterns = [];
  let maxLines;
  try {
    const response = await github.rest.repos.getContent({ owner, repo, path, ref });
    if (!Array.isArray(response.data)) {
      const encoding = response.data.encoding || 'base64';
      const raw = Buffer.from(response.data.content || '', encoding).toString('utf8');
      const parsed = JSON.parse(raw);
      found = true;
      if (Array.isArray(parsed.patterns)) {
        patterns = parsed.patterns.filter((item) => typeof item === 'string');
      }
      if (Object.prototype.hasOwnProperty.call(parsed, 'max_lines_changed')) {
        const numeric = Number(parsed.max_lines_changed);
        if (!Number.isNaN(numeric)) {
          maxLines = numeric;
        }
      }
    }
  } catch (error) {
    found = false;
  }
  return { found, patterns, maxLines };
}

function matchPattern(filename, pattern) {
  if (!pattern || !filename) {
    return false;
  }
  return minimatch(filename, pattern, {
    dot: true,
    nocomment: true,
    nonegate: true,
  });
}

async function computeCiStatus({ github, core, owner, repo, sha }) {
  const result = {
    hasSignals: false,
    pending: false,
    failing: false,
    green: false,
    checkRuns: {
      total: 0,
      pending: 0,
      failing: 0,
    },
    statuses: {
      total: 0,
      pending: 0,
      failing: 0,
    },
  };

  const warn = (message) => {
    if (core && typeof core.warning === 'function') {
      core.warning(message);
    } else {
      // eslint-disable-next-line no-console
      console.warn(message);
    }
  };

  try {
    const { data } = await github.rest.checks.listForRef({ owner, repo, ref: sha, per_page: 100 });
    result.checkRuns.total = data.total_count || 0;
    for (const run of data.check_runs || []) {
      if (run.status !== 'completed') {
        result.checkRuns.pending += 1;
        continue;
      }
      const conclusion = (run.conclusion || '').toLowerCase();
      if (!['success', 'neutral', 'skipped'].includes(conclusion)) {
        result.checkRuns.failing += 1;
      }
    }
  } catch (error) {
    warn(`Failed to list check runs for ${sha}: ${error.message}`);
  }

  try {
    const { data } = await github.rest.repos.getCombinedStatusForRef({ owner, repo, ref: sha, per_page: 100 });
    result.statuses.total = data.total_count || 0;
    for (const status of data.statuses || []) {
      const state = (status.state || '').toLowerCase();
      if (state === 'pending') {
        result.statuses.pending += 1;
      } else if (state === 'failure' || state === 'error') {
        result.statuses.failing += 1;
      }
    }
  } catch (error) {
    warn(`Failed to gather commit status for ${sha}: ${error.message}`);
  }

  result.hasSignals = (result.checkRuns.total + result.statuses.total) > 0;
  result.pending = result.checkRuns.pending > 0 || result.statuses.pending > 0;
  result.failing = result.checkRuns.failing > 0 || result.statuses.failing > 0;
  result.green = result.hasSignals && !result.pending && !result.failing;

  return result;
}

async function evaluatePullRequest({ github: rawGithub, core, owner, repo, prNumber, config }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  } catch (error) {
    core?.warning?.(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
  const labels = pr.labels.map((label) => label.name);
  const labelSet = new Set(labels);

  const allowlistPath = config.allowlistPath || '.github/autoapprove-allowlist.json';
  const allowlist = await fetchAllowlist(github, owner, repo, allowlistPath, pr.base.sha);

  const overridePatterns = (config.approvePatterns || '')
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0);

  const effectivePatterns = overridePatterns.length > 0 ? overridePatterns : allowlist.patterns;
  const patternSource = overridePatterns.length > 0 ? 'env' : (allowlist.found ? 'allowlist' : 'none');
  const patternCount = effectivePatterns.length;

  const listFiles = github?.rest?.pulls?.listFiles || github?.pulls?.listFiles;
  const files = listFiles ? await github.paginate(listFiles, { owner, repo, pull_number: prNumber }) : [];
  const allowlistOk = patternCount > 0
    ? files.every((file) => effectivePatterns.some((pattern) => matchPattern(file.filename, pattern)))
    : false;

  const totalChanges = files.reduce((sum, file) => sum + (file.changes || 0), 0);
  let maxLinesCandidate;
  if (config.maxLinesOverride !== undefined && String(config.maxLinesOverride).trim() !== '') {
    const overrideValue = Number(config.maxLinesOverride);
    if (!Number.isNaN(overrideValue)) {
      maxLinesCandidate = overrideValue;
    }
  }
  if (maxLinesCandidate === undefined && Number.isFinite(allowlist.maxLines)) {
    maxLinesCandidate = allowlist.maxLines;
  }
  const maxLines = Number.isFinite(maxLinesCandidate) ? maxLinesCandidate : 1000;
  const sizeOk = totalChanges <= maxLines;

  const labelsConfig = config.labels || {};
  const fromLabelName = labelsConfig.from || 'from:copilot';
  const fromLabelAltName = labelsConfig.fromAlt || 'from:codex';
  const automergeLabelName = labelsConfig.automerge || 'automerge';
  const riskLabelName = labelsConfig.risk || 'risk:low';
  const ciLabelName = labelsConfig.ci || 'ci:green';

  const hasAutomerge = labelSet.has(automergeLabelName);
  const hasFrom = labelSet.has(fromLabelName) || labelSet.has(fromLabelAltName);
  const hasRisk = labelSet.has(riskLabelName);
  const hasCi = labelSet.has(ciLabelName);

  const ciStatus = await computeCiStatus({ github, core, owner, repo, sha: pr.head.sha });
  const ciReady = ciStatus.green;
  const safe = Boolean(allowlist.found && patternCount > 0 && allowlistOk && sizeOk);

  const outputs = {
    pr_number: String(prNumber),
    automerge_label: String(hasAutomerge),
    from_label: String(hasFrom),
    risk_label: String(hasRisk),
    ci_label: String(hasCi),
    ci_label_desired: String(ciReady),
    ci_ready: String(ciReady),
    ci_green: String(ciStatus.green),
    ci_pending: String(ciStatus.pending),
    ci_failing: String(ciStatus.failing),
    ci_signal: String(ciStatus.hasSignals),
    ci_checks_total: String(ciStatus.checkRuns.total),
    ci_statuses_total: String(ciStatus.statuses.total),
    draft: String(pr.draft),
    head_sha: pr.head.sha,
    base_sha: pr.base.sha,
    allowlist_found: String(allowlist.found),
    allowlist_ok: String(allowlistOk),
    size_ok: String(sizeOk),
    safe: String(safe),
    lines_changed: String(totalChanges),
    max_lines: String(maxLines),
    pattern_count: String(patternCount),
    pattern_source: patternSource,
    should_auto_approve: String(safe && hasFrom && hasRisk && !pr.draft),
    label_gate_ok: String(hasFrom && hasRisk && ciReady),
    should_run: String(hasAutomerge),
  };

  for (const [key, value] of Object.entries(outputs)) {
    core.setOutput(key, value);
  }

  return {
    pr,
    labels,
    allowlist,
    effectivePatterns,
    ciStatus,
    outputs,
  };
}

async function upsertDecisionComment({ github: rawGithub, owner, repo, prNumber, marker, body }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, env: process.env });
  } catch (error) {
    console.warn(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  const comments = await github.rest.issues.listComments({ owner, repo, issue_number: prNumber, per_page: 100 });
  const existing = comments.data.find((comment) => typeof comment.body === 'string' && comment.body.includes(marker));

  if (!body) {
    if (existing) {
      await github.rest.issues.deleteComment({ owner, repo, comment_id: existing.id });
      return 'deleted';
    }
    return 'none';
  }

  if (existing) {
    if (existing.body.trim() === body.trim()) {
      return 'unchanged';
    }
    await github.rest.issues.updateComment({ owner, repo, comment_id: existing.id, body });
    return 'updated';
  }

  await github.rest.issues.createComment({ owner, repo, issue_number: prNumber, body });
  return 'created';
}

async function syncCiStatusLabel({ github: rawGithub, owner, repo, prNumber, labelName, desired, present }) {
  // Wrap github client with rate-limit-aware retry
  let github;
  try {
    github = await ensureRateLimitWrapped({ github: rawGithub, env: process.env });
  } catch (error) {
    console.warn(`Failed to wrap GitHub client: ${error.message} - using raw client`);
    github = rawGithub;
  }

  if (!prNumber || !labelName) {
    return 'skipped';
  }

  if (desired) {
    if (present) {
      return 'unchanged';
    }
    await github.rest.issues.addLabels({ owner, repo, issue_number: prNumber, labels: [labelName] });
    return 'added';
  }

  if (!present) {
    return 'unchanged';
  }

  try {
    await github.rest.issues.removeLabel({ owner, repo, issue_number: prNumber, name: labelName });
    return 'removed';
  } catch (error) {
    if (error.status === 404) {
      return 'missing';
    }
    throw error;
  }
}

module.exports = {
  evaluatePullRequest,
  upsertDecisionComment,
  syncCiStatusLabel,
};
