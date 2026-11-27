'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { cleanupPullBody, openCleanupPullRequest } = require('../maint72-pr-body-cleanup.js');
const { resolvePrSourceContext } = require('../source_context.js');

const OWNER = 'stranske';
const REPO = 'Portable-Alpha-Extension-Model';
const BASE = 'c2a82327843f8b9c2db78244b7f9f1b7fa455bae';
const HEAD = '592dc3a3d73e75713399db654ebfdaf486a51254';
const PR_BODY = [
  '<!-- workflows-maint72-pr-body/v1 -->',
  '',
  `This PR applies the Maint 72 cleanup plan from \`${BASE}\`. It removes tracked PR-body content and adds the ignore rule when missing. Review the exact diff and required checks before merging.`,
].join('\n');

function tree(entries) {
  return entries.map(({ path, mode, type, sha }) => ({ path, mode, type, sha }));
}

function fixture({ existing = true } = {}) {
  const baseEntries = tree([
    { path: '.gitignore', mode: '100644', type: 'blob', sha: 'ignore-sha' },
    { path: 'pr_body.md', mode: '100644', type: 'blob', sha: 'body-sha' },
  ]);
  const repairedEntries = tree([
    { path: '.gitignore', mode: '100644', type: 'blob', sha: 'ignore-sha' },
  ]);
  const pull = {
    number: 2540, state: 'open', draft: false, base: { ref: 'main' },
    head: { ref: 'maintenance/maint72-pr-body', sha: HEAD, repo: { full_name: `${OWNER}/${REPO}` } },
    body: PR_BODY, labels: [], html_url: `https://github.com/${OWNER}/${REPO}/pull/2540`,
  };
  let currentHead = existing ? HEAD : null;
  let currentPull = existing ? pull : null;
  const writes = [];
  const client = { rest: { git: {
    getRef: async () => {
      if (!currentHead) {
        const error = new Error('not found'); error.status = 404; throw error;
      }
      return { data: { ref: 'refs/heads/maintenance/maint72-pr-body', object: { sha: currentHead } } };
    },
    getCommit: async ({ commit_sha }) => ({ data: {
      message: `chore: clean up tracked PR body\n\n<!-- workflows-maint72-pr-body/v1 -->\nBase: ${BASE}`,
      parents: [{ sha: BASE }], tree: { sha: commit_sha === BASE ? 'base-tree' : 'repaired-tree' },
    } }),
    getTree: async ({ tree_sha }) => ({ data: { truncated: false,
      tree: tree_sha === 'base-tree' ? baseEntries : repairedEntries } }),
    createTree: async () => { writes.push('tree'); return { data: { sha: 'repaired-tree' } }; },
    createCommit: async () => { writes.push('commit'); return { data: { sha: HEAD } }; },
    createRef: async ({ sha }) => { writes.push('ref'); currentHead = sha; return { data: {} }; },
  }, repos: {
    getBranch: async () => ({ data: { commit: { sha: BASE }, protected: true } }),
  }, pulls: {
    list: async () => ({ data: currentPull ? [currentPull] : [] }),
    create: async (args) => {
      writes.push('create'); Object.assign(pull, {
        ...args, number: 2540, state: 'open', draft: false,
        head: { ref: args.head, sha: HEAD, repo: { full_name: `${OWNER}/${REPO}` } },
        base: { ref: args.base }, labels: [], html_url: `https://github.com/${OWNER}/${REPO}/pull/2540`,
      });
      currentPull = pull;
      return { data: pull };
    },
    update: async ({ body }) => { writes.push('update'); pull.body = body; return { data: pull }; },
  }, issues: {
    addLabels: async ({ labels }) => { writes.push('labels'); pull.labels.push(...labels.map((name) => ({ name }))); return { data: pull.labels }; },
  } } };
  const github = { ...client, paginate: async (method, params) => (await method(params)).data };
  return { pull, writes, github };
}

test('new Maint 72 cleanup bodies carry explicit automation provenance', () => {
  const body = cleanupPullBody(BASE);
  const source = resolvePrSourceContext({ body, labels: [] });
  assert.equal(source.sourceType, 'automation_run');
  assert.equal(source.isValid, true);
  assert.equal(source.requiresIssue, false);
  assert.match(body, /<!-- workflows-maint72-pr-body\/v1 -->\n<!-- workflow-source:automation_run -->/);
});

test('real Maint 72 PR body is unknown before correction and repaired provenance is idempotent', async () => {
  const f = fixture();
  assert.equal(resolvePrSourceContext(f.pull).sourceType, 'unknown');
  const input = {
    github: f.github, core: {}, owner: OWNER, repo: REPO, baseSha: BASE,
    prBodySha: 'body-sha', gitignoreSha: 'ignore-sha', newIgnore: null,
  };
  assert.equal(await openCleanupPullRequest(input), f.pull.html_url);
  assert.deepEqual(f.writes, ['update', 'labels']);
  const source = resolvePrSourceContext(f.pull);
  assert.equal(source.sourceType, 'automation_run');
  assert.equal(source.isValid, true);
  assert.equal(source.requiresIssue, false);
  assert.match(f.pull.body, /<!-- workflow-source:automation_run -->/);
  assert.deepEqual(f.pull.labels, [{ name: 'workflow:source-automation' }]);
  assert.equal(await openCleanupPullRequest(input), f.pull.html_url);
  assert.deepEqual(f.writes, ['update', 'labels']);
});

test('new protected cleanup PR creates source marker and source label', async () => {
  const f = fixture({ existing: false });
  const input = {
    github: f.github, core: {}, owner: OWNER, repo: REPO, baseSha: BASE,
    prBodySha: 'body-sha', gitignoreSha: 'ignore-sha', newIgnore: null,
  };
  assert.equal(await openCleanupPullRequest(input), f.pull.html_url);
  assert.deepEqual(f.writes, ['tree', 'commit', 'ref', 'create', 'labels']);
  assert.equal(resolvePrSourceContext(f.pull).sourceType, 'automation_run');
  assert.deepEqual(f.pull.labels, [{ name: 'workflow:source-automation' }]);
});

test('unowned pull is never edited while repairing provenance', async () => {
  const f = fixture();
  f.pull.head.ref = 'other-automation-branch';
  await assert.rejects(
    openCleanupPullRequest({
      github: f.github, core: {}, owner: OWNER, repo: REPO, baseSha: BASE,
      prBodySha: 'body-sha', gitignoreSha: 'ignore-sha', newIgnore: null,
    }),
    /cleanup PR is closed or differs from this plan/,
  );
  assert.deepEqual(f.writes, []);
});
