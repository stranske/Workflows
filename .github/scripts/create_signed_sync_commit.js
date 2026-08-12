'use strict';

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const { withGithubApiRetry } = require('./github-api-with-retry.js');

const SUPPORTED_BLOB_MODES = new Set(['100644', '100755', '120000']);

function splitNul(buffer) {
  return Buffer.from(buffer)
    .toString('utf8')
    .split('\0')
    .filter(Boolean);
}

function defaultRunGit(args, { cwd, encoding = 'buffer' } = {}) {
  return execFileSync('git', args, {
    cwd,
    encoding: encoding === 'buffer' ? null : encoding,
    maxBuffer: 64 * 1024 * 1024,
  });
}

function stagedPaths(runGit, cwd, diffFilter) {
  return splitNul(runGit([
    'diff',
    '--cached',
    '--name-only',
    '--no-renames',
    `--diff-filter=${diffFilter}`,
    '-z',
    '--',
  ], { cwd }));
}

function indexEntry(runGit, cwd, path) {
  const output = Buffer.from(runGit(
    ['ls-files', '--stage', '-z', '--', path],
    { cwd },
  )).toString('utf8');
  const match = output.match(/^(\d{6}) ([0-9a-f]{40,64}) 0\t([^\0]+)\0$/);
  if (!match || match[3] !== path) {
    throw new Error(`Unable to resolve staged index entry for ${path}`);
  }
  const [, mode, oid] = match;
  if (!SUPPORTED_BLOB_MODES.has(mode)) {
    throw new Error(`Unsupported staged mode ${mode} for ${path}`);
  }
  return { mode, oid, path, type: 'blob' };
}

function baseEntry(runGit, cwd, baseSha, path) {
  const output = Buffer.from(runGit(
    ['ls-tree', '-z', baseSha, '--', path],
    { cwd },
  )).toString('utf8');
  const match = output.match(/^(\d{6}) ([a-z]+) ([0-9a-f]{40,64})\t([^\0]+)\0$/);
  if (!match || match[4] !== path) {
    throw new Error(`Unable to resolve base tree entry for deleted path ${path}`);
  }
  return { mode: match[1], type: match[2], path, sha: null };
}

function collectStagedChanges({ cwd = process.cwd(), baseSha, runGit = defaultRunGit } = {}) {
  if (!baseSha) throw new Error('baseSha is required');
  const additionPaths = stagedPaths(runGit, cwd, 'ACMRTUXB');
  const deletionPaths = stagedPaths(runGit, cwd, 'D');
  const duplicates = additionPaths.filter((path) => deletionPaths.includes(path));
  if (duplicates.length > 0) {
    throw new Error(`Staged paths cannot be both additions and deletions: ${duplicates.join(', ')}`);
  }
  if (additionPaths.length === 0 && deletionPaths.length === 0) {
    throw new Error('No staged file changes were found');
  }
  return {
    additions: additionPaths.map((path) => {
      const entry = indexEntry(runGit, cwd, path);
      return {
        ...entry,
        contents: Buffer.from(runGit(['cat-file', 'blob', entry.oid], { cwd })),
      };
    }),
    deletions: deletionPaths.map((path) => baseEntry(runGit, cwd, baseSha, path)),
  };
}

async function githubRequest(path, {
  token,
  method = 'GET',
  body,
  fetchImpl = globalThis.fetch,
  apiUrl = process.env.GITHUB_API_URL,
} = {}) {
  if (!token) throw new Error('A GitHub token is required');
  if (typeof fetchImpl !== 'function') throw new Error('fetch is unavailable');
  if (!apiUrl) throw new Error('GITHUB_API_URL is required');
  const operation = method === 'GET' ? 'read' : 'write';
  return withGithubApiRetry(async () => {
    const response = await fetchImpl(`${apiUrl}${path}`, {
      method,
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    let data = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        throw new Error(`GitHub API returned non-JSON content for ${method} ${path}`);
      }
    }
    if (response.ok) return data;

    const error = new Error(
      `GitHub API ${method} ${path} failed (${response.status}): ${data.message || 'unknown error'}`,
    );
    error.status = response.status;
    error.request = { method };
    error.response = {
      status: response.status,
      headers: response.headers && typeof response.headers.entries === 'function'
        ? Object.fromEntries(response.headers.entries())
        : {},
    };
    throw error;
  }, {
    operation,
    label: `GitHub API ${method} ${path}`,
  });
}

function validateRepository(repository) {
  if (!/^[^/]+\/[^/]+$/.test(repository || '')) {
    throw new Error('repository must be in owner/name form');
  }
}

function validateCommitSha(commitSha, label = 'commitSha') {
  if (!/^[0-9a-f]{40,64}$/.test(commitSha || '')) {
    throw new Error(`${label} must be a full commit oid`);
  }
}

function validateHeadRef(ref) {
  const valid = /^refs\/heads\/[A-Za-z0-9][A-Za-z0-9._\/-]*$/.test(ref || '')
    && !ref.includes('..')
    && !ref.includes('//')
    && !ref.endsWith('/');
  if (!valid) throw new Error('ref must be a valid refs/heads/* name');
}

async function verifyCommit({ repository, commitSha, token, request = githubRequest } = {}) {
  validateRepository(repository);
  validateCommitSha(commitSha);
  const commit = await request(`/repos/${repository}/commits/${commitSha}`, { token });
  const verification = commit?.commit?.verification || {};
  return {
    sha: commit?.sha || commitSha,
    verified: verification.verified === true,
    verification_reason: verification.reason || 'missing',
  };
}

async function createCommitRef({ repository, ref, commitSha, token, request = githubRequest } = {}) {
  validateRepository(repository);
  validateHeadRef(ref);
  validateCommitSha(commitSha);
  const created = await request(`/repos/${repository}/git/refs`, {
    token,
    method: 'POST',
    body: { ref, sha: commitSha },
  });
  const createdSha = created?.object?.sha || '';
  if (created?.ref !== ref || createdSha !== commitSha) {
    throw new Error(`Created ref ${created?.ref || '<missing>'} did not target ${commitSha}`);
  }
  return { ref: created.ref, sha: createdSha };
}

async function createSignedCommit({
  repository,
  baseSha,
  expectedTreeSha,
  message,
  token,
  cwd = process.cwd(),
  runGit = defaultRunGit,
  request = githubRequest,
} = {}) {
  validateRepository(repository);
  validateCommitSha(baseSha, 'baseSha');
  if (!/^[0-9a-f]{40,64}$/.test(expectedTreeSha || '')) {
    throw new Error('expectedTreeSha must be a full tree oid');
  }
  if (!String(message || '').trim()) throw new Error('message is required');

  const localHeadSha = Buffer.from(runGit(
    ['rev-parse', 'HEAD'],
    { cwd },
  )).toString('utf8').trim();
  if (localHeadSha !== baseSha) {
    throw new Error(`Local HEAD ${localHeadSha} does not match base commit ${baseSha}`);
  }

  // This endpoint is available only to GitHub App installation tokens. The
  // workflow mints a token scoped to exactly the consumer repository, so also
  // prove that the intended target is inside the credential's installation
  // scope before uploading any objects.
  const installationRepositories = await request(
    '/installation/repositories?per_page=100',
    { token },
  );
  const repositoryIsAccessible = installationRepositories?.repositories?.some(
    (candidate) => candidate?.full_name === repository,
  );
  if (!Number.isInteger(installationRepositories?.total_count) || !repositoryIsAccessible) {
    throw new Error('Commit credential is not a GitHub App installation token');
  }

  const changes = collectStagedChanges({ cwd, baseSha, runGit });
  const tree = [];
  for (const addition of changes.additions) {
    const blob = await request(`/repos/${repository}/git/blobs`, {
      token,
      method: 'POST',
      body: { content: addition.contents.toString('base64'), encoding: 'base64' },
    });
    if (blob.sha !== addition.oid) {
      throw new Error(`Uploaded blob oid mismatch for ${addition.path}`);
    }
    tree.push({
      path: addition.path,
      mode: addition.mode,
      type: addition.type,
      sha: blob.sha,
    });
  }
  tree.push(...changes.deletions);

  const baseTreeSha = Buffer.from(runGit(
    ['rev-parse', `${baseSha}^{tree}`],
    { cwd },
  )).toString('utf8').trim();
  const createdTree = await request(`/repos/${repository}/git/trees`, {
    token,
    method: 'POST',
    body: { base_tree: baseTreeSha, tree },
  });
  if (createdTree.sha !== expectedTreeSha) {
    throw new Error(
      `Created tree ${createdTree.sha || '<missing>'} does not match staged tree ${expectedTreeSha}`,
    );
  }

  // GitHub signs Git Database commits for authenticated GitHub Apps only when
  // custom author, committer, and signature fields are omitted.
  const commit = await request(`/repos/${repository}/git/commits`, {
    token,
    method: 'POST',
    body: { message, tree: createdTree.sha, parents: [baseSha] },
  });
  const verification = commit.verification || {};
  if (verification.verified !== true || verification.reason !== 'valid') {
    throw new Error(
      `GitHub did not verify the generated commit signature (reason=${verification.reason || 'missing'})`,
    );
  }
  return {
    sha: commit.sha,
    url: commit.html_url || '',
    tree: createdTree.sha,
    verified: true,
    verification_reason: verification.reason,
    credential: 'github-app-installation',
  };
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith('--') || value === undefined) {
      throw new Error(`Invalid argument near ${key || '<end>'}`);
    }
    args[key.slice(2).replaceAll('-', '_')] = value;
  }
  return args;
}

async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const operation = args.operation || 'create-commit';
  let result;
  if (operation === 'create-commit') {
    const message = fs.readFileSync(args.message_file, 'utf8');
    result = await createSignedCommit({
      repository: args.repository,
      baseSha: args.base_sha,
      expectedTreeSha: args.expected_tree_sha,
      message,
      token: process.env.GH_TOKEN,
      cwd: args.cwd || process.cwd(),
    });
  } else if (operation === 'verify-commit') {
    result = await verifyCommit({
      repository: args.repository,
      commitSha: args.commit_sha,
      token: process.env.GH_TOKEN,
    });
  } else if (operation === 'create-ref') {
    result = await createCommitRef({
      repository: args.repository,
      ref: args.ref,
      commitSha: args.commit_sha,
      token: process.env.GH_TOKEN,
    });
  } else {
    throw new Error(`Unsupported operation: ${operation}`);
  }
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error.stack || error.message}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  collectStagedChanges,
  createCommitRef,
  createSignedCommit,
  githubRequest,
  parseArgs,
  splitNul,
  verifyCommit,
};
