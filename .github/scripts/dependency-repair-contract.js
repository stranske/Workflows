// @ts-check
//
// Dependency repair provenance contract.
//
// Clean Renovate/Dependabot pull requests remain bot-owned. When a coding
// agent needs to repair a dependency failure, the repair moves to an
// agent-owned promotion PR whose first commit reproduces the selected bot
// dependency delta. Later commits may contain the repair. This module checks
// both sides of that boundary without executing code from the pull request.

const childProcess = require('child_process');
const path = require('path');

const PROMOTION_MARKER = 'dependency-repair-promotion:v1';
const DEPENDENCY_BOT_LOGINS = new Set([
  'renovate[bot]',
  'app/renovate',
  'dependabot[bot]',
  'app/dependabot',
]);
const GENERATED_BOT_LOGINS = new Set(['github-actions[bot]', 'app/github-actions']);
const GENERATED_COMMIT_SUBJECTS = [
  /^chore\(deps\): (?:refresh|regenerate|update) (?:the )?(?:dependency )?lockfiles?$/i,
  /^chore\(deps\): (?:refresh|regenerate|update) requirements(?:-dev)?\.lock$/i,
];
const GENERATED_PATHS = [
  /^(?:.+\/)?requirements(?:-dev)?\.lock$/,
  /^(?:.+\/)?(?:uv|poetry|pdm)\.lock$/,
  /^(?:.+\/)?(?:package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$/,
  /^(?:.+\/)?(?:Cargo|Gemfile)\.lock$/,
];

function normalizeLogin(value) {
  return String(value || '').trim().toLowerCase();
}

function isDependencyBotLogin(value) {
  return DEPENDENCY_BOT_LOGINS.has(normalizeLogin(value));
}

function isDependencyBotPullRequest(pr = {}) {
  const author = normalizeLogin(pr.user?.login || pr.authorLogin || pr.author);
  const headRef = String(pr.head?.ref || pr.headRef || '').toLowerCase();
  return (
    isDependencyBotLogin(author) ||
    headRef.startsWith('renovate/') ||
    headRef.startsWith('dependabot/')
  );
}

function commitSubject(commit = {}) {
  return String(commit.commit?.message || commit.message || '').split(/\r?\n/, 1)[0].trim();
}

function commitLogins(commit = {}) {
  return new Set(
    [
      commit.author?.login,
      commit.committer?.login,
      commit.authorLogin,
      commit.committerLogin,
    ]
      .map(normalizeLogin)
      .filter(Boolean),
  );
}

function isGeneratedPath(filePath) {
  return GENERATED_PATHS.some((pattern) => pattern.test(String(filePath || '')));
}

function classifyCommit(commit = {}, files = []) {
  const logins = commitLogins(commit);
  if ([...logins].some(isDependencyBotLogin)) {
    return { kind: 'dependency-bot', reason: 'dependency bot identity' };
  }

  const generatedIdentity = [...logins].some((login) => GENERATED_BOT_LOGINS.has(login));
  const generatedSubject = GENERATED_COMMIT_SUBJECTS.some((pattern) =>
    pattern.test(commitSubject(commit)),
  );
  const paths = (files || [])
    .map((file) => (typeof file === 'string' ? file : file.filename))
    .filter(Boolean);
  const generatedFilesOnly = paths.length > 0 && paths.every(isGeneratedPath);

  if (generatedIdentity && generatedSubject && generatedFilesOnly) {
    return {
      kind: 'generated-maintenance',
      reason: 'strict lockfile regeneration signature',
    };
  }

  return {
    kind: 'unclassified',
    reason: 'commit is neither dependency-bot-authored nor strict generated lockfile maintenance',
  };
}

function buildPromotionMarker(metadata) {
  return `<!-- ${PROMOTION_MARKER} ${JSON.stringify(metadata)} -->`;
}

function parsePromotionMarker(body) {
  const source = String(body || '');
  const escaped = PROMOTION_MARKER.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = source.match(new RegExp(`<!--\\s*${escaped}\\s+(\\{[^\\n]*\\})\\s*-->`));
  if (!match) {
    return null;
  }
  try {
    return JSON.parse(match[1]);
  } catch (error) {
    return { parseError: error.message };
  }
}

function validateMarker(metadata) {
  const errors = [];
  if (!metadata || metadata.parseError) {
    return [metadata?.parseError || 'promotion marker is missing'];
  }
  if (!Number.isInteger(Number(metadata.source_pr)) || Number(metadata.source_pr) <= 0) {
    errors.push('source_pr must be a positive pull request number');
  }
  for (const field of [
    'source_base_sha',
    'source_head_sha',
    'promotion_base_sha',
  ]) {
    if (!/^[0-9a-f]{40}$/i.test(String(metadata[field] || ''))) {
      errors.push(`${field} must be a full 40-character commit SHA`);
    }
  }
  return errors;
}

function runGit(repoPath, args, { input = undefined, allowFailure = false } = {}) {
  const result = childProcess.spawnSync('git', ['-C', repoPath, ...args], {
    encoding: 'utf8',
    input,
    maxBuffer: 20 * 1024 * 1024,
  });
  if (result.status !== 0 && !allowFailure) {
    throw new Error(
      `git ${args.join(' ')} failed: ${(result.stderr || result.stdout || '').trim()}`,
    );
  }
  return result;
}

function patchId(repoPath, baseSha, headSha) {
  const diff = runGit(repoPath, [
    'diff',
    '--binary',
    '--full-index',
    '--no-ext-diff',
    baseSha,
    headSha,
    '--',
  ]).stdout;
  if (!diff.trim()) {
    return '';
  }
  const result = runGit(repoPath, ['patch-id', '--stable'], { input: diff });
  return String(result.stdout || '').trim().split(/\s+/, 1)[0];
}

function changedPaths(repoPath, baseSha, headSha) {
  const output = runGit(repoPath, [
    'diff',
    '--name-only',
    '-z',
    baseSha,
    headSha,
    '--',
  ]).stdout;
  return output.split('\0').filter(Boolean).sort();
}

function sameStringArray(left, right) {
  return (
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  );
}

async function listPullCommits(apiContext, owner, repo, pullNumber) {
  const { github, paginateWithRetry } = apiContext;
  return paginateWithRetry(github.rest.pulls.listCommits, {
    owner,
    repo,
    pull_number: pullNumber,
    per_page: 100,
  });
}

async function classifyPullCommits(apiContext, owner, repo, commits) {
  const { withRetry } = apiContext;
  const classified = [];
  for (const commit of commits) {
    let files = [];
    const initial = classifyCommit(commit, files);
    if (initial.kind !== 'dependency-bot') {
      const detail = await withRetry((client) =>
        client.rest.repos.getCommit({
          owner,
          repo,
          ref: commit.sha,
        })
      );
      files = detail.data.files || [];
    }
    classified.push({
      sha: commit.sha,
      subject: commitSubject(commit),
      files: files.map((file) => file.filename),
      ...classifyCommit(commit, files),
    });
  }
  return classified;
}

async function addSummary(core, heading, lines) {
  if (!core?.summary) {
    return;
  }
  core.summary.addHeading(heading, 2);
  for (const line of lines) {
    core.summary.addRaw(`${line}\n`);
  }
  await core.summary.write();
}

async function evaluateDependencyRepairContract({
  github,
  context,
  core,
  repoPath,
  withRetry = (operation) => operation(github),
  paginateWithRetry = (method, params) => github.paginate(method, params),
}) {
  // Callers provide these functions from createTokenAwareRetry so every API
  // request uses the fleet token rotation and retry policy.
  const apiContext = { github, withRetry, paginateWithRetry };
  const { owner, repo } = context.repo;
  const pullNumber = Number(context.payload.pull_request?.number);
  if (!pullNumber) {
    return { blocked: false, kind: 'not-a-pull-request', reasons: [] };
  }

  const currentResponse = await withRetry((client) =>
    client.rest.pulls.get({
      owner,
      repo,
      pull_number: pullNumber,
    })
  );
  const current = currentResponse.data;
  const marker = parsePromotionMarker(current.body || '');

  if (!marker && !isDependencyBotPullRequest(current)) {
    return { blocked: false, kind: 'unrelated', reasons: [] };
  }

  if (!marker) {
    const commits = await listPullCommits(apiContext, owner, repo, pullNumber);
    const classified = await classifyPullCommits(apiContext, owner, repo, commits);
    const unclassified = classified.filter((item) => item.kind === 'unclassified');
    const reasons = unclassified.map(
      (item) => `${item.sha.slice(0, 12)} ${item.subject}: ${item.reason}`,
    );
    return {
      blocked: reasons.length > 0,
      kind: 'dependency-bot',
      reasons,
      classified,
    };
  }

  const reasons = validateMarker(marker);
  const headRef = String(current.head?.ref || '');
  if (isDependencyBotPullRequest(current)) {
    reasons.push('a promotion PR must be agent-owned, not dependency-bot-owned');
  }
  if (!headRef.startsWith('agent/deps-repair-')) {
    reasons.push('promotion branch must start with agent/deps-repair-');
  }
  if (reasons.length > 0) {
    return { blocked: true, kind: 'promotion', reasons, marker };
  }

  const sourceNumber = Number(marker.source_pr);
  const sourceResponse = await withRetry((client) =>
    client.rest.pulls.get({
      owner,
      repo,
      pull_number: sourceNumber,
    })
  );
  const source = sourceResponse.data;
  if (!isDependencyBotPullRequest(source)) {
    reasons.push(`source PR #${sourceNumber} is not dependency-bot-owned`);
  }

  const sourceCommits = await listPullCommits(apiContext, owner, repo, sourceNumber);
  const selectedIndex = sourceCommits.findIndex(
    (commit) => commit.sha === marker.source_head_sha,
  );
  if (selectedIndex < 0) {
    reasons.push('source_head_sha is not a commit in the source PR');
  } else {
    const selected = sourceCommits.slice(0, selectedIndex + 1);
    const firstSourceCommit = await withRetry((client) =>
      client.rest.repos.getCommit({
        owner,
        repo,
        ref: selected[0].sha,
      })
    );
    const sourceParent = firstSourceCommit.data.parents?.[0]?.sha || '';
    if (sourceParent !== marker.source_base_sha) {
      reasons.push(
        'source_base_sha must be the first parent of the source PR commit prefix',
      );
    }
    const classified = await classifyPullCommits(apiContext, owner, repo, selected);
    for (const item of classified.filter((entry) => entry.kind === 'unclassified')) {
      reasons.push(
        `selected source prefix contains unclassified commit ${item.sha.slice(0, 12)}: ${item.subject}`,
      );
    }
  }

  const promotionCommits = await listPullCommits(apiContext, owner, repo, pullNumber);
  if (promotionCommits.length === 0) {
    reasons.push('promotion PR has no commits');
    return { blocked: true, kind: 'promotion', reasons, marker };
  }

  const firstCommit = await withRetry((client) =>
    client.rest.repos.getCommit({
      owner,
      repo,
      ref: promotionCommits[0].sha,
    })
  );
  const firstParent = firstCommit.data.parents?.[0]?.sha || '';
  if (firstParent !== marker.promotion_base_sha) {
    reasons.push(
      'the first promotion commit must be based directly on promotion_base_sha',
    );
  }

  for (const sha of [
    marker.source_base_sha,
    marker.source_head_sha,
    marker.promotion_base_sha,
    promotionCommits[0].sha,
  ]) {
    const result = runGit(repoPath, ['cat-file', '-e', `${sha}^{commit}`], {
      allowFailure: true,
    });
    if (result.status !== 0) {
      reasons.push(`required commit ${sha} is not available in the checkout`);
    }
  }

  if (reasons.length === 0) {
    const sourcePatchId = patchId(
      repoPath,
      marker.source_base_sha,
      marker.source_head_sha,
    );
    const promotionPatchId = patchId(
      repoPath,
      marker.promotion_base_sha,
      promotionCommits[0].sha,
    );
    const sourcePaths = changedPaths(
      repoPath,
      marker.source_base_sha,
      marker.source_head_sha,
    );
    const promotionPaths = changedPaths(
      repoPath,
      marker.promotion_base_sha,
      promotionCommits[0].sha,
    );
    if (!sourcePatchId || sourcePatchId !== promotionPatchId) {
      reasons.push('first promotion commit does not reproduce the selected bot patch');
    }
    if (!sameStringArray(sourcePaths, promotionPaths)) {
      reasons.push('first promotion commit changes a different path set than the selected bot patch');
    }
  }

  return {
    blocked: reasons.length > 0,
    kind: 'promotion',
    reasons,
    marker,
    sourceNumber,
    repairCommitCount: Math.max(0, promotionCommits.length - 1),
  };
}

async function runDependencyRepairContract(options) {
  const result = await evaluateDependencyRepairContract(options);
  const { core } = options;
  if (result.kind === 'unrelated' || result.kind === 'not-a-pull-request') {
    core.info('Dependency repair contract is not applicable to this pull request.');
    return result;
  }

  if (result.blocked) {
    const lines = [
      'The dependency repair provenance contract failed:',
      ...result.reasons.map((reason) => `- ${reason}`),
      '',
      'Keep clean dependency PRs bot-owned. Preserve independent repairs in a companion PR,',
      'or create an agent/deps-repair-* promotion PR with a verified bot-delta first commit.',
    ];
    await addSummary(core, 'Dependency repair contract', lines);
    core.setFailed(result.reasons.join('; '));
    return result;
  }

  const detail =
    result.kind === 'promotion'
      ? `Promotion provenance is valid; repair commits: ${result.repairCommitCount}.`
      : 'Dependency-bot commits are classified and bot-owned.';
  await addSummary(core, 'Dependency repair contract', [detail]);
  core.info(detail);
  return result;
}

module.exports = {
  DEPENDENCY_BOT_LOGINS,
  PROMOTION_MARKER,
  buildPromotionMarker,
  changedPaths,
  classifyCommit,
  evaluateDependencyRepairContract,
  isDependencyBotLogin,
  isDependencyBotPullRequest,
  parsePromotionMarker,
  patchId,
  runDependencyRepairContract,
  validateMarker,
};
