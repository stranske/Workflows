'use strict';

const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { mkdtempSync, rmSync, writeFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { fullPredecessor, releaseMetadataIssue } = require('../selftest-release-scope.js');
const script = path.resolve(__dirname, '../selftest-release-scope.js');
const manifest = '.release-please-manifest.json';
const changelog = 'CHANGELOG.md';
const repository = 'stranske/Workflows';
const oldManifest = '{"." : "1.52.9"}\n';
const newManifest = '{"." : "1.52.10"}\n';
const history = '## [1.52.9](https://github.com/stranske/Workflows/compare/v1.52.8...v1.52.9) (2026-11-26)\n\nPrevious fix.\n';
const release = '## [1.52.10](https://github.com/stranske/Workflows/compare/v1.52.9...v1.52.10) (2026-11-26)\n\nNew fix.\n\n';
const oldChangelog = '# Changelog\n\n' + history;
const newChangelog = '# Changelog\n\n' + release + history;

function gitFixture(t) {
  const cwd = mkdtempSync(path.join(tmpdir(), 'selftest-release-'));
  t.after(() => rmSync(cwd, { recursive: true, force: true }));
  const git = (...args) =>
    execFileSync('git', ['-c', 'commit.gpgsign=false', ...args], { cwd, encoding: 'utf8' }).trim();
  git('init', '-q');
  git('config', 'user.name', 'Selftest fixture');
  git('config', 'user.email', 'selftest@example.test');
  const write = (file, content) => writeFileSync(path.join(cwd, file), content);
  const commit = () => {
    git('add', '--all');
    git('commit', '-qm', 'Fixture');
    return git('rev-parse', 'HEAD');
  };
  const select = (before, after, overrides = {}) => {
    const env = {
      ...process.env,
      GITHUB_EVENT_NAME: 'push',
      GITHUB_REF: 'refs/heads/main',
      GITHUB_REPOSITORY: repository,
      GITHUB_SHA: after,
      SELFTEST_BEFORE: before,
      SELFTEST_FORCED: 'false',
      ...overrides,
    };
    delete env.GITHUB_OUTPUT;
    return execFileSync(process.execPath, [script], { cwd, env, stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8' }).trim();
  };
  write(manifest, oldManifest);
  write(changelog, oldChangelog);
  const before = commit();
  return { git, write, commit, select, before };
}

test('only the exact validated release push is eligible for predecessor lookup', (t) => {
  const { git, write, commit, select, before } = gitFixture(t);
  write(manifest, newManifest);
  write(changelog, newChangelog);
  const push = commit();
  assert.equal(select(before, push), 'release-scope=release-only');
  for (const overrides of [
    { GITHUB_EVENT_NAME: 'pull_request' }, { GITHUB_EVENT_NAME: 'workflow_dispatch' },
    { SELFTEST_FORCED: 'true' }, { SELFTEST_FORCED: '' }, { GITHUB_REF: 'refs/heads/other' },
  ]) {
    assert.equal(select(before, push, overrides), 'release-scope=full');
  }
  assert.equal(select('a'.repeat(40), push), 'release-scope=full');
  write('source.py', 'print("code change")\n');
  const mixed = commit();
  assert.equal(select(before, mixed), 'release-scope=full');
  git('reset', '--soft', before);
  const combined = commit();
  assert.equal(select(before, combined), 'release-scope=full');
});

test('singleton, replacement and incomplete release comparisons run normally', (t) => {
  const { git, write, commit, select, before } = gitFixture(t);
  write(manifest, newManifest);
  const single = commit();
  assert.equal(select(before, single), 'release-scope=full');
  git('mv', changelog, 'RELEASE-NOTES.md');
  const renamed = commit();
  assert.equal(select(before, renamed), 'release-scope=full');
  assert.equal(select(renamed, before), 'release-scope=full');
  assert.equal(select(before, before), 'release-scope=full');
});

test('malformed release and version or history mismatches are reported as invalid', (t) => {
  const { write, commit, select, before } = gitFixture(t);
  write(manifest, '{"." : "1.52.11"}');
  write(changelog, newChangelog);
  assert.equal(select(before, commit()), 'release-scope=invalid');
  assert.equal(releaseMetadataIssue(oldManifest, newManifest, oldChangelog, newChangelog, repository), '');
  for (const bad of ['{', '{"." : "1.52.10", "." : "1.52.10"}', '{"." : "1.52.8"}']) {
    assert.match(releaseMetadataIssue(oldManifest, bad, oldChangelog, newChangelog, repository), /manifest/);
  }
  assert.match(
    releaseMetadataIssue(oldManifest, newManifest, oldChangelog, newChangelog.replace('...v1.52.10', '...v1.52.11'), repository),
    /Changelog/,
  );
  assert.match(releaseMetadataIssue(oldManifest, newManifest, oldChangelog, release, repository), /Changelog/);
});

function predecessor() {
  const before = 'a'.repeat(40);
  const repo = { owner: 'stranske', repo: 'Workflows' };
  const run = {
    id: 45736181991,
    run_attempt: 2,
    head_sha: before,
    head_branch: 'main',
    event: 'push',
    path: '.github/workflows/selftest-ci.yml',
    status: 'completed',
    conclusion: 'success',
    repository: { full_name: repository },
    head_repository: { full_name: repository },
  };
  const jobs = ['3.13', '3.14'].map((version) => ({
    name: `canonical Python suite / python ${version}`,
    run_id: run.id,
    run_attempt: run.run_attempt,
    head_sha: before,
    status: 'completed',
    conclusion: 'success',
    steps: ['Pytest (unit tests with coverage)', 'Upload coverage artifact'].map((name) =>
      ({ name, status: 'completed', conclusion: 'success' })),
  }));
  const fixtures = { runs: { total_count: 1, workflow_runs: [run] }, results: { total_count: 2, jobs } };
  const calls = [];
  const github = { rest: { actions: {
    async listWorkflowRuns(args) {
      calls.push(['runs', args]);
      if (fixtures.denied) throw new Error('denied');
      return { data: fixtures.runs };
    },
    async listJobsForWorkflowRunAttempt(args) {
      calls.push(['jobs', args]);
      return { data: fixtures.results };
    },
  } } };
  const check = () => fullPredecessor({
    github, context: { repo }, before, core: { info() {}, warning() {} },
  });
  return { check, calls, fixtures, run, jobs, before, repo };
}

test('proof uses the exact default push and named attempt, testing and artifact steps', async () => {
  const { check, calls, before, repo } = predecessor();
  assert.equal(await check(), true);
  assert.deepEqual(calls, [
    ['runs', { ...repo, workflow_id: 'selftest-ci.yml', head_sha: before, branch: 'main', event: 'push', per_page: 2 }],
    ['jobs', { ...repo, run_id: 45736181991, attempt_number: 2, per_page: 100 }],
  ]);
});

test('interrupted, unknown and incomplete predecessor evidence keep the full matrix', async () => {
  for (const mutate of [
    ({ run }) => { run.conclusion = 'cancelled'; },
    ({ run }) => { run.status = 'in_progress'; run.conclusion = null; },
    ({ run }) => { run.head_sha = 'b'.repeat(40); },
    ({ run }) => { run.event = 'workflow_dispatch'; },
    ({ fixtures }) => { fixtures.runs.total_count = 2; },
    ({ fixtures }) => { fixtures.runs.workflow_runs = []; fixtures.runs.total_count = 0; },
    ({ fixtures }) => { fixtures.results.total_count = 102; },
    ({ fixtures }) => { fixtures.denied = true; },
    ({ jobs }) => { jobs[0].conclusion = 'skipped'; },
    ({ jobs }) => { jobs[0].name = 'operator guide tests (Python 3.13)'; },
    ({ jobs }) => { jobs[0].run_attempt = 1; },
    ({ jobs }) => { jobs[0].steps[1].conclusion = 'skipped'; },
  ]) {
    const fixture = predecessor();
    mutate(fixture);
    assert.equal(await fixture.check(), false, mutate.toString());
  }
});
