'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const {
  collectStagedChanges,
  createSignedCommit,
  parseArgs,
} = require('../create_signed_sync_commit');

const blobOid = (contents) => crypto
  .createHash('sha1')
  .update(`blob ${contents.length}\0`)
  .update(contents)
  .digest('hex');

function fakeGit({ addition = Buffer.from('#!/bin/sh\necho ok\n'), baseSha, baseTreeSha }) {
  const additionSha = blobOid(addition);
  const calls = [];
  const runGit = (args) => {
    calls.push(args);
    const key = args.join(' ');
    if (key.includes('--diff-filter=ACMRTUXB')) return Buffer.from('scripts/check.sh\0');
    if (key.includes('--diff-filter=D')) return Buffer.from('docs/old.md\0');
    if (args[0] === 'ls-files') {
      return Buffer.from(`100755 ${additionSha} 0\tscripts/check.sh\0`);
    }
    if (args[0] === 'cat-file') return addition;
    if (args[0] === 'ls-tree') {
      return Buffer.from(`100644 blob ${'b'.repeat(40)}\tdocs/old.md\0`);
    }
    if (key === 'rev-parse HEAD') return Buffer.from(`${baseSha}\n`);
    if (key === `rev-parse ${baseSha}^{tree}`) return Buffer.from(`${baseTreeSha}\n`);
    throw new Error(`Unexpected git call: ${key}`);
  };
  return { addition, additionSha, calls, runGit };
}

test('collectStagedChanges preserves executable mode and explicit deletions', () => {
  const baseSha = 'a'.repeat(40);
  const fixture = fakeGit({ baseSha, baseTreeSha: 'c'.repeat(40) });
  const changes = collectStagedChanges({ baseSha, runGit: fixture.runGit, cwd: '/tmp/repo' });

  assert.equal(changes.additions[0].path, 'scripts/check.sh');
  assert.equal(changes.additions[0].mode, '100755');
  assert.deepEqual(changes.additions[0].contents, fixture.addition);
  assert.deepEqual(changes.deletions, [{
    mode: '100644',
    type: 'blob',
    path: 'docs/old.md',
    sha: null,
  }]);
});

test('createSignedCommit requires an App token and publishes only a verified exact tree', async () => {
  const baseSha = 'a'.repeat(40);
  const baseTreeSha = 'c'.repeat(40);
  const expectedTreeSha = 'd'.repeat(40);
  const commitSha = 'e'.repeat(40);
  const fixture = fakeGit({ baseSha, baseTreeSha });
  const requests = [];
  const request = async (path, options = {}) => {
    requests.push({ path, options });
    if (path === '/installation/repositories?per_page=100') {
      return {
        total_count: 1,
        repositories: [{ full_name: 'stranske/Ready' }],
      };
    }
    if (path.endsWith('/git/blobs')) return { sha: fixture.additionSha };
    if (path.endsWith('/git/trees')) return { sha: expectedTreeSha };
    if (path.endsWith('/git/commits')) {
      assert.deepEqual(Object.keys(options.body).sort(), ['message', 'parents', 'tree']);
      return {
        sha: commitSha,
        html_url: `https://github.com/stranske/Ready/commit/${commitSha}`,
        verification: { verified: true, reason: 'valid' },
      };
    }
    throw new Error(`Unexpected request: ${path}`);
  };

  const result = await createSignedCommit({
    repository: 'stranske/Ready',
    baseSha,
    expectedTreeSha,
    message: 'chore: signed sync',
    token: 'installation-token',
    runGit: fixture.runGit,
    request,
  });

  assert.equal(result.sha, commitSha);
  assert.equal(result.verified, true);
  assert.equal(result.credential, 'github-app-installation');
  assert.equal(requests[0].path, '/installation/repositories?per_page=100');
  assert.equal(requests.at(-1).path, '/repos/stranske/Ready/git/commits');
});

test('createSignedCommit fails closed when GitHub does not verify the commit', async () => {
  const baseSha = 'a'.repeat(40);
  const expectedTreeSha = 'd'.repeat(40);
  const fixture = fakeGit({ baseSha, baseTreeSha: 'c'.repeat(40) });
  const request = async (path) => {
    if (path === '/installation/repositories?per_page=100') {
      return {
        total_count: 1,
        repositories: [{ full_name: 'stranske/Ready' }],
      };
    }
    if (path.endsWith('/git/blobs')) return { sha: fixture.additionSha };
    if (path.endsWith('/git/trees')) return { sha: expectedTreeSha };
    if (path.endsWith('/git/commits')) {
      return { sha: 'e'.repeat(40), verification: { verified: false, reason: 'unsigned' } };
    }
    throw new Error(`Unexpected request: ${path}`);
  };

  await assert.rejects(
    createSignedCommit({
      repository: 'stranske/Ready',
      baseSha,
      expectedTreeSha,
      message: 'chore: signed sync',
      token: 'installation-token',
      runGit: fixture.runGit,
      request,
    }),
    /did not verify the generated commit signature.*unsigned/,
  );
});

test('createSignedCommit rejects credentials without access to the target repository', async () => {
  const baseSha = 'a'.repeat(40);
  const fixture = fakeGit({ baseSha, baseTreeSha: 'c'.repeat(40) });
  const request = async (path) => {
    assert.equal(path, '/installation/repositories?per_page=100');
    return {
      total_count: 1,
      repositories: [{ full_name: 'stranske/Another-Repo' }],
    };
  };

  await assert.rejects(
    createSignedCommit({
      repository: 'stranske/Ready',
      baseSha,
      expectedTreeSha: 'd'.repeat(40),
      message: 'chore: signed sync',
      token: 'wrong-installation-token',
      runGit: fixture.runGit,
      request,
    }),
    /not a GitHub App installation token/,
  );
});

test('parseArgs rejects incomplete CLI arguments', () => {
  assert.deepEqual(parseArgs(['--repository', 'stranske/Ready']), {
    repository: 'stranske/Ready',
  });
  assert.throws(() => parseArgs(['--repository']), /Invalid argument/);
});

test('Maint 68 publishes generated heads only through the signed commit helper', () => {
  const workflow = fs.readFileSync(
    path.join(__dirname, '..', '..', 'workflows', 'maint-68-sync-consumer-repos.yml'),
    'utf8',
  );
  assert.match(workflow, /Mint Workflows App commit token/);
  assert.match(workflow, /create_signed_sync_commit\.js/);
  assert.match(workflow, /published_verified/);
  assert.doesNotMatch(workflow, /git config user\.name "github-actions\[bot\]"/);
  assert.doesNotMatch(workflow, /git commit -m "chore: sync workflow templates/);
});
