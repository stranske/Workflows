'use strict';

const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { mkdirSync, mkdtempSync, rmSync, writeFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const test = require('node:test');

const script = path.resolve(__dirname, '../selftest-guide-scope.js');
const workflowGuide = '.github/workflows/README.md';
const systemGuide = 'docs/ci/WORKFLOW_SYSTEM.md';

function repository(t) {
  const cwd = mkdtempSync(path.join(tmpdir(), 'selftest-guide-'));
  t.after(() => rmSync(cwd, { recursive: true, force: true }));
  const git = (...args) =>
    execFileSync('git', ['-c', 'commit.gpgsign=false', ...args], { cwd, encoding: 'utf8' }).trim();
  git('init', '-q');
  git('config', 'user.name', 'Selftest fixture');
  git('config', 'user.email', 'selftest@example.test');
  function write(file, content) {
    const full = path.join(cwd, file);
    mkdirSync(path.dirname(full), { recursive: true });
    writeFileSync(full, content);
  }
  function commit() {
    git('add', '--all');
    git('commit', '-qm', 'Fixture commit');
    return git('rev-parse', 'HEAD');
  }
  function selected(before, after, overrides = {}) {
    const env = {
      ...process.env,
      GITHUB_EVENT_NAME: 'push',
      GITHUB_REF: 'refs/heads/main',
      GITHUB_SHA: after,
      SELFTEST_BEFORE: before,
      SELFTEST_FORCED: 'false',
      ...overrides,
    };
    delete env.GITHUB_OUTPUT;
    return execFileSync(process.execPath, [script], { cwd, env, encoding: 'utf8' }).trim();
  }
  return { git, write, commit, selected };
}

test('only proven in-place edits to both guides select the guide scope', (t) => {
  const repo = repository(t);
  repo.write(workflowGuide, 'Original README');
  repo.write(systemGuide, 'Original guide');
  const before = repo.commit();
  repo.write(workflowGuide, 'Revised README');
  const oneGuide = repo.commit();
  repo.write(systemGuide, 'Revised guide');
  const bothGuides = repo.commit();
  assert.equal(repo.selected(before, bothGuides), 'guide-only=true');
  assert.equal(repo.selected(before, oneGuide), 'guide-only=false');
  assert.equal(repo.selected(before, before), 'guide-only=false');
  assert.equal(repo.selected('a'.repeat(40), bothGuides), 'guide-only=false');
  assert.equal(repo.selected('unknown', bothGuides), 'guide-only=false');
  assert.equal(repo.selected(before, bothGuides, { GITHUB_EVENT_NAME: 'workflow_dispatch' }), 'guide-only=false');
  assert.equal(repo.selected(before, bothGuides, { SELFTEST_FORCED: 'true' }), 'guide-only=false');
  assert.equal(repo.selected(before, bothGuides, { SELFTEST_FORCED: '' }), 'guide-only=false');
  assert.equal(repo.selected(before, bothGuides, { GITHUB_REF: 'refs/heads/other' }), 'guide-only=false');

  repo.write('.github/workflows/entry.yml', 'name: Added job');
  const mixed = repo.commit();
  assert.equal(repo.selected(before, mixed), 'guide-only=false');
});

test('moving a workflow to the README stays on the full matrix', (t) => {
  const repo = repository(t);
  repo.write('.github/workflows/entry.yml', 'name: Workflow');
  repo.write(systemGuide, 'Original guide');
  const before = repo.commit();
  repo.git('mv', '.github/workflows/entry.yml', workflowGuide);
  repo.write(systemGuide, 'Revised guide');
  const renamed = repo.commit();
  assert.equal(repo.selected(before, renamed), 'guide-only=false');
});
