'use strict';

const { execFileSync } = require('node:child_process');
const { appendFileSync } = require('node:fs');

const MANIFEST = '.release-please-manifest.json';
const CHANGELOG = 'CHANGELOG.md';
const RELEASE_FILES = new Set([MANIFEST, CHANGELOG]);
const SHA = /^[a-f0-9]{40}$/;
const REGULAR_EDIT = /^:100644 100644 [a-f0-9]{40} [a-f0-9]{40} M$/;
const COMPONENT = '(?:0|[1-9][0-9]*)';
const VERSION = `${COMPONENT}\\.${COMPONENT}\\.${COMPONENT}`;
const MANIFEST_VERSION = new RegExp(`^\\s*\\{\\s*"\\."\\s*:\\s*"(${VERSION})"\\s*\\}\\s*$`);
const RUNTIMES = ['3.13', '3.14'];
const COVERAGE_STEPS = ['Pytest (unit tests with coverage)', 'Upload coverage artifact'];
const SELFTEST_PATH = '.github/workflows/selftest-ci.yml';

function git(...args) {
  return execFileSync('git', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
}

function manifestVersion(text) {
  // Match the generated single-key shape as well as parsing JSON: JSON.parse
  // alone would accept duplicate keys, keeping only the last one.
  try {
    JSON.parse(text);
    return MANIFEST_VERSION.exec(text)?.[1];
  } catch {
    return undefined;
  }
}

function laterVersion(before, after) {
  const previous = before.split('.').map(BigInt);
  const current = after.split('.').map(BigInt);
  const change = current.findIndex((part, index) => part !== previous[index]);
  return change !== -1 && current[change] > previous[change];
}

function releaseMetadataIssue(oldManifest, newManifest, oldChangelog, newChangelog, repository) {
  const before = manifestVersion(oldManifest);
  const after = manifestVersion(newManifest);
  if (!before || !after || !laterVersion(before, after)) {
    return 'Release manifest must advance its single root version using valid numeric versions.';
  }
  const oldHeading = oldChangelog.indexOf('\n## ') + 1;
  const newHeading = newChangelog.indexOf('\n## ') + 1;
  const heading = newChangelog.slice(newHeading).split('\n', 1)[0];
  const expected = `## [${after}](https://github.com/${repository}/compare/v${before}...v${after})`;
  if (
    !oldHeading ||
    !newHeading ||
    !oldChangelog.startsWith(`## [${before}](`, oldHeading) ||
    !heading.startsWith(`${expected} `) ||
    !/^\(\d{4}-\d{2}-\d{2}\)$/.test(heading.slice(expected.length + 1)) ||
    oldChangelog.slice(0, oldHeading) !== newChangelog.slice(0, newHeading) ||
    !newChangelog.endsWith(`\n${oldChangelog.slice(oldHeading)}`)
  ) {
    return 'Changelog must add the matching release heading and compare range above its existing history.';
  }
  return '';
}

function inspectReleaseScope(env = process.env) {
  const before = env.SELFTEST_BEFORE || '';
  const after = env.GITHUB_SHA || '';
  if (
    env.GITHUB_EVENT_NAME !== 'push' ||
    env.GITHUB_REF !== 'refs/heads/main' ||
    env.SELFTEST_FORCED !== 'false' ||
    !SHA.test(before) ||
    !SHA.test(after) ||
    before === after
  ) {
    return 'full';
  }

  let issue;
  try {
    if (git('rev-list', '--parents', '-1', after).trim() !== `${after} ${before}`) {
      return 'full';
    }
    const diff = git('diff', '--raw', '--no-abbrev', '--no-renames', '-z', before, after, '--');
    const [firstEdit, firstPath, secondEdit, secondPath, ...tail] = diff.split('\0');
    if (
      tail.length !== 1 || tail[0] !== '' ||
      !REGULAR_EDIT.test(firstEdit) || !REGULAR_EDIT.test(secondEdit) ||
      firstPath === secondPath || !RELEASE_FILES.has(firstPath) || !RELEASE_FILES.has(secondPath)
    ) {
      return 'full';
    }
    issue = releaseMetadataIssue(
      git('show', `${before}:${MANIFEST}`), git('show', `${after}:${MANIFEST}`),
      git('show', `${before}:${CHANGELOG}`), git('show', `${after}:${CHANGELOG}`),
      env.GITHUB_REPOSITORY,
    );
  } catch {
    // Missing Git objects or an unavailable comparison retain the full suite.
    return 'full';
  }
  if (issue) {
    console.error(`::error::${issue}`);
    return 'invalid';
  }
  return 'release-only';
}

async function fullPredecessor({ github, context, before, core }) {
  if (!SHA.test(before)) return false;
  const identity = `${context.repo.owner}/${context.repo.repo}`;
  try {
    const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');
    const client = await ensureRateLimitWrapped({ github, core, env: process.env });
    const { data: runs } = await client.rest.actions.listWorkflowRuns({
      ...context.repo, workflow_id: 'selftest-ci.yml', head_sha: before, branch: 'main',
      event: 'push', per_page: 2,
    });
    if (runs.total_count !== 1 || runs.workflow_runs.length !== 1) return false;
    const [run] = runs.workflow_runs;
    if (
      !Number.isSafeInteger(run.id) || !Number.isSafeInteger(run.run_attempt) ||
      run.run_attempt < 1 || run.head_sha !== before || run.event !== 'push' ||
      run.head_branch !== 'main' || run.path !== SELFTEST_PATH ||
      run.head_repository?.full_name !== identity || run.repository?.full_name !== identity ||
      run.status !== 'completed' || run.conclusion !== 'success'
    ) {
      return false;
    }
    const { data } = await client.rest.actions.listJobsForWorkflowRunAttempt({
      ...context.repo, run_id: run.id, attempt_number: run.run_attempt, per_page: 100,
    });
    if (data.total_count !== data.jobs.length) return false;
    const verified = RUNTIMES.every((version) => {
      const jobs = data.jobs.filter((job) => job.name === `canonical Python suite / python ${version}`);
      if (jobs.length !== 1) return false;
      const [job] = jobs;
      return job.run_id === run.id && job.run_attempt === run.run_attempt && job.head_sha === before &&
        job.status === 'completed' && job.conclusion === 'success' &&
        COVERAGE_STEPS.every((name) => job.steps?.some((step) =>
          step.name === name && step.status === 'completed' && step.conclusion === 'success'));
    });
    if (verified) {
      core.info(`Verified preceding Selftest run ${run.id} (attempt ${run.run_attempt}) at ${before}.`);
    }
    return verified;
  } catch {
    core.warning('Could not confirm the exact predecessor Selftest; running the full Python suite.');
    return false;
  }
}

if (require.main === module) {
  const result = `release-scope=${inspectReleaseScope()}\n`;
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(process.env.GITHUB_OUTPUT, result);
  } else {
    process.stdout.write(result);
  }
}

module.exports = { fullPredecessor, inspectReleaseScope, releaseMetadataIssue };
