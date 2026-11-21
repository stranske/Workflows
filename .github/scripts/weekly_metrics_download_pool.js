const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const { safeArtifactPathSegment } = require('./weekly_metrics_download_manifest');

const MAX_ACTIVE_DOWNLOADS = 3;
const manifestScript = path.join(__dirname, 'weekly_metrics_download_manifest.js');

function runCommand(command, args, stdio = 'inherit') {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio });
    child.once('error', reject);
    child.once('close', (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited with ${signal || code}`));
    });
  });
}

async function processInOrder(rows, processRow, publish) {
  const results = rows.map(() => Promise.withResolvers());
  let nextRow = 0;
  let stopped = false;
  const workers = Promise.all(Array.from({ length: Math.min(MAX_ACTIVE_DOWNLOADS, rows.length) }, async () => {
    while (!stopped && nextRow < rows.length) {
      const index = nextRow++;
      try {
        results[index].resolve({ value: await processRow(rows[index]) });
      } catch (error) {
        stopped = true;
        results[index].resolve({ error });
      }
    }
  }));

  try {
    for (const result of results) {
      const outcome = await result.promise;
      if (Object.hasOwn(outcome, 'error')) throw outcome.error;
      await publish(outcome.value);
    }
  } finally {
    stopped = true;
    await workers;
  }
}

async function fetchOne(id, zipPath) {
  const { Octokit } = require('@octokit/rest');
  const { createTokenAwareRetry } = require('./github-api-with-retry.js');
  const core = { info: () => {}, warning: console.warn, debug: () => {} };
  const [owner, repo] = process.env.GITHUB_REPOSITORY.split('/');
  const github = new Octokit({ auth: process.env.GH_TOKEN || process.env.GITHUB_TOKEN });
  const { withRetry } = await createTokenAwareRetry({
    github,
    core,
    env: process.env,
    task: 'agents-weekly-metrics-download',
    capabilities: ['actions:read'],
  });
  const response = await withRetry((client) => client.rest.actions.downloadArtifact({
    owner,
    repo,
    artifact_id: Number(id),
    archive_format: 'zip',
  }));
  const data = response.data;
  const buffer = Buffer.isBuffer(data)
    ? data
    : Buffer.from(data instanceof ArrayBuffer ? new Uint8Array(data) : data);
  await fs.writeFile(zipPath, buffer);
}

async function downloadAndUnzip({ id, name }) {
  const artifactDir = path.posix.join('artifacts', safeArtifactPathSegment(name), id);
  const zipPath = path.posix.join(artifactDir, `${id}.zip`);
  const args = ['--id', id, '--name', name, '--artifact-dir', artifactDir, '--zip-path', zipPath];
  await fs.mkdir(artifactDir, { recursive: true });
  console.log(`Downloading artifact ${id} (${name})`);
  try {
    // Isolate the retry/token registry in a fresh child, as in the original serial loop.
    await runCommand(process.execPath, [__filename, '--fetch-one', id, zipPath]);
  } catch (_error) {
    console.warn(`Warning: Could not download artifact ${id} (${name})`);
    return [...args, '--download-status', 'failed', '--download-error', 'download-command-failed',
      '--unzip-status', 'skipped', '--unzip-error', 'download-failed'];
  }
  const { size } = await fs.stat(zipPath);
  args.push('--zip-bytes', String(size), '--download-status', 'pass');
  try {
    await runCommand('unzip', ['-o', zipPath, '-d', artifactDir], ['ignore', 'ignore', 'inherit']);
    return [...args, '--unzip-status', 'pass'];
  } catch (_error) {
    console.warn(`Warning: Could not unzip artifact ${id} (${name})`);
    return [...args, '--unzip-status', 'failed', '--unzip-error', 'unzip-command-failed'];
  }
}

async function downloadList(listPath, manifest, markdown) {
  const input = await fs.readFile(listPath, 'utf8');
  const rows = input.split('\n').filter(Boolean).map((line) => {
    const tab = line.indexOf('\t');
    const id = line.slice(0, tab);
    if (tab < 1 || !/^[1-9][0-9]*$/.test(id)) {
      throw new Error('Invalid artifact ID in the weekly metrics download list');
    }
    return { id, name: line.slice(tab + 1) };
  });
  if (new Set(rows.map(({ id }) => id)).size !== rows.length) {
    throw new Error('Duplicate artifact ID in the weekly metrics download list');
  }

  await processInOrder(rows, downloadAndUnzip, (args) => (
    runCommand(process.execPath, [manifestScript, '--record', '--manifest', manifest,
      '--markdown', markdown, ...args])
  ));
}

if (require.main === module) {
  const [mode, ...args] = process.argv.slice(2);
  const work = mode === '--fetch-one' ? fetchOne(...args) : downloadList(mode, ...args);
  work.catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

module.exports = { processInOrder };
