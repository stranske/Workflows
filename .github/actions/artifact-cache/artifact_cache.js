'use strict';

const fs = require('node:fs');
const path = require('node:path');

const VALID_WINDOW_RESOLUTIONS = new Set(['daily', 'weekly', 'run']);
const DEFAULT_GITHUB_API_URL = ['https://api', 'github', 'com'].join('.');

function parseBoolean(value, defaultValue = false) {
  if (value === undefined || value === null || String(value).trim() === '') {
    return defaultValue;
  }
  const normalized = String(value).trim().toLowerCase();
  if (['1', 'true', 'yes', 'y', 'on'].includes(normalized)) {
    return true;
  }
  if (['0', 'false', 'no', 'n', 'off'].includes(normalized)) {
    return false;
  }
  throw new Error(`Invalid boolean value: ${value}`);
}

function sanitizeSegment(value) {
  const sanitized = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return sanitized || 'artifact';
}

function toUtcDate(input) {
  const date = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(date.getTime())) {
    throw new Error(`Invalid date: ${input}`);
  }
  return date;
}

function startOfUtcDay(date) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
}

function addDays(date, days) {
  const copy = new Date(date.getTime());
  copy.setUTCDate(copy.getUTCDate() + days);
  return copy;
}

function isoWeekParts(dateInput) {
  const date = startOfUtcDay(toUtcDate(dateInput));
  const day = date.getUTCDay() || 7;
  const thursday = addDays(date, 4 - day);
  const year = thursday.getUTCFullYear();
  const yearStart = new Date(Date.UTC(year, 0, 1));
  const week = Math.ceil((((thursday - yearStart) / 86400000) + 1) / 7);
  const start = addDays(date, 1 - day);
  const end = addDays(start, 7);
  return { year, week, start, end };
}

function deriveWindow({ resolution = 'weekly', now = new Date(), runId = '' } = {}) {
  const normalized = String(resolution || 'weekly').trim().toLowerCase();
  if (!VALID_WINDOW_RESOLUTIONS.has(normalized)) {
    throw new Error(
      `Invalid window-resolution "${resolution}". Expected daily, weekly, or run.`,
    );
  }

  const date = toUtcDate(now);
  if (normalized === 'daily') {
    const start = startOfUtcDay(date);
    const end = addDays(start, 1);
    const label = start.toISOString().slice(0, 10);
    return { resolution: normalized, label, start, end };
  }

  if (normalized === 'run') {
    const id = String(runId || '').trim();
    if (!id) {
      throw new Error('GITHUB_RUN_ID is required when window-resolution is run.');
    }
    return { resolution: normalized, label: `run-${id}`, start: null, end: null };
  }

  const { year, week, start, end } = isoWeekParts(date);
  return {
    resolution: normalized,
    label: `${year}-W${String(week).padStart(2, '0')}`,
    start,
    end,
  };
}

function deriveCachePlan({
  cacheKeyBase,
  windowResolution = 'weekly',
  artifactName,
  artifactPath = '',
  now = new Date(),
  runId = '',
  workspace = process.cwd(),
} = {}) {
  const base = String(cacheKeyBase || '').trim();
  const name = String(artifactName || '').trim();
  if (!base) {
    throw new Error('cache-key-base is required.');
  }
  if (!name) {
    throw new Error('artifact-name is required.');
  }

  const window = deriveWindow({ resolution: windowResolution, now, runId });
  const safeBase = sanitizeSegment(base);
  const safeName = sanitizeSegment(name);
  const resolvedArtifactPath = artifactPath && String(artifactPath).trim()
    ? String(artifactPath).trim()
    : path.join('.artifact-cache', safeBase, window.label, safeName);

  return {
    cacheKey: `${base}-${window.label}`,
    artifactPath: resolvedArtifactPath,
    window,
    artifactName: name,
    workspace,
  };
}

function artifactCreatedAt(artifact) {
  const raw = artifact?.created_at || artifact?.updated_at;
  return raw ? toUtcDate(raw) : null;
}

function artifactInWindow(artifact, window, runId = '') {
  if (window.resolution === 'run') {
    const artifactRunId = artifact?.workflow_run?.id || artifact?.workflow_run?.run_id;
    return String(artifactRunId || '') === String(runId || '');
  }

  const createdAt = artifactCreatedAt(artifact);
  if (!createdAt) {
    return false;
  }
  return createdAt >= window.start && createdAt < window.end;
}

function artifactRunId(artifact) {
  return artifact?.workflow_run?.id || artifact?.workflow_run?.run_id || '';
}

function artifactHeadBranch(artifact) {
  return artifact?.workflow_run?.head_branch || '';
}

function artifactMatchesProducer(artifact, { producerRunId = '', producerBranch = '' } = {}) {
  const expectedRunId = String(producerRunId || '').trim();
  if (expectedRunId && String(artifactRunId(artifact) || '') !== expectedRunId) {
    return false;
  }

  const expectedBranch = String(producerBranch || '').trim();
  if (expectedBranch && artifactHeadBranch(artifact) !== expectedBranch) {
    return false;
  }

  return true;
}

function selectArtifact(
  artifacts,
  { artifactName, window, runId = '', producerRunId = '', producerBranch = '' },
) {
  return [...(artifacts || [])]
    .filter((artifact) => artifact && artifact.name === artifactName)
    .filter((artifact) => !artifact.expired)
    .filter((artifact) => artifactInWindow(artifact, window, runId))
    .filter((artifact) => artifactMatchesProducer(artifact, { producerRunId, producerBranch }))
    .sort((a, b) => artifactCreatedAt(b) - artifactCreatedAt(a))[0] || null;
}

async function listArtifacts({
  token,
  owner,
  repo,
  apiUrl = process.env.GITHUB_API_URL || DEFAULT_GITHUB_API_URL,
  fetchImpl = global.fetch,
}) {
  if (!fetchImpl) {
    throw new Error('Global fetch is not available; use Node.js 18 or newer.');
  }
  if (!token) {
    throw new Error('GITHUB_TOKEN is required to discover workflow artifacts.');
  }
  if (!owner || !repo) {
    throw new Error('GITHUB_REPOSITORY must be set as owner/repo.');
  }

  const artifacts = [];
  let page = 1;
  while (true) {
    const baseUrl = String(apiUrl || DEFAULT_GITHUB_API_URL).replace(/\/+$/, '');
    const response = await fetchImpl(
      `${baseUrl}/repos/${owner}/${repo}/actions/artifacts?per_page=100&page=${page}`,
      {
        headers: {
          accept: 'application/vnd.github+json',
          authorization: `Bearer ${token}`,
          'x-github-api-version': '2022-11-28',
          'user-agent': 'artifact-cache-action',
        },
      },
    );
    if (!response.ok) {
      const error = new Error(`Failed to list artifacts: ${response.status} ${response.statusText}`);
      error.status = response.status;
      throw error;
    }
    const payload = await response.json();
    const pageArtifacts = Array.isArray(payload.artifacts) ? payload.artifacts : [];
    artifacts.push(...pageArtifacts);
    const linkHeader = response.headers?.get?.('link') || '';
    const hasNextPage = linkHeader.includes('rel="next"');
    if (!hasNextPage && pageArtifacts.length < 100) {
      break;
    }
    page += 1;
  }
  return artifacts;
}

function writeArtifactMissOutputs() {
  writeOutputs({
    'artifact-found': 'false',
    'artifact-id': '',
    'run-id': '',
  });
}

function writeOutputs(outputs) {
  const outputPath = process.env.GITHUB_OUTPUT;
  if (!outputPath) {
    for (const [key, value] of Object.entries(outputs)) {
      process.stdout.write(`${key}=${value}\n`);
    }
    return;
  }

  const lines = [];
  for (const [key, value] of Object.entries(outputs)) {
    lines.push(`${key}=${value}`);
  }
  fs.appendFileSync(outputPath, `${lines.join('\n')}\n`, 'utf8');
}

function buildPlanFromEnv() {
  return deriveCachePlan({
    cacheKeyBase: process.env.INPUT_CACHE_KEY_BASE,
    windowResolution: process.env.INPUT_WINDOW_RESOLUTION || 'weekly',
    artifactName: process.env.INPUT_ARTIFACT_NAME,
    artifactPath: process.env.INPUT_ARTIFACT_PATH || '',
    now: process.env.ARTIFACT_CACHE_NOW || new Date(),
    runId: process.env.GITHUB_RUN_ID || '',
    workspace: process.env.GITHUB_WORKSPACE || process.cwd(),
  });
}

async function prepareCommand() {
  const plan = buildPlanFromEnv();
  fs.mkdirSync(plan.artifactPath, { recursive: true });
  writeOutputs({
    'cache-key': plan.cacheKey,
    'artifact-path': plan.artifactPath,
    'window-label': plan.window.label,
    'window-start': plan.window.start ? plan.window.start.toISOString() : '',
    'window-end': plan.window.end ? plan.window.end.toISOString() : '',
  });
}

async function discoverCommand() {
  const plan = buildPlanFromEnv();
  const failFast = parseBoolean(process.env.INPUT_FAIL_FAST, false);
  const [owner, repo] = String(process.env.GITHUB_REPOSITORY || '').split('/');
  let artifacts;
  try {
    artifacts = await listArtifacts({
      token: process.env.GITHUB_TOKEN,
      owner,
      repo,
    });
  } catch (error) {
    const message = `Artifact discovery failed: ${error.message || error}`;
    if (failFast) {
      console.error(`::error title=Artifact discovery failed::${message}`);
      throw error;
    }
    console.log(`::warning::${message} Producer steps may repopulate ${plan.artifactPath}.`);
    writeArtifactMissOutputs();
    return;
  }

  const artifact = selectArtifact(artifacts, {
    artifactName: plan.artifactName,
    window: plan.window,
    runId: process.env.GITHUB_RUN_ID || '',
    producerRunId: process.env.INPUT_PRODUCER_RUN_ID || '',
    producerBranch: process.env.INPUT_PRODUCER_BRANCH || process.env.GITHUB_REF_NAME || '',
  });

  if (!artifact) {
    const message = [
      `Artifact "${plan.artifactName}" was not found in ${plan.window.resolution}`,
      `window "${plan.window.label}".`,
    ].join(' ');
    if (failFast) {
      console.error(`::error title=Required artifact missing::${message}`);
      throw new Error(message);
    }
    console.log(`::notice::${message} Producer steps may repopulate ${plan.artifactPath}.`);
    writeArtifactMissOutputs();
    return;
  }

  const runId = artifactRunId(artifact);
  writeOutputs({
    'artifact-found': 'true',
    'artifact-id': String(artifact.id || ''),
    'run-id': String(runId),
  });
}

async function main() {
  const command = process.argv[2] || 'prepare';
  if (command === 'prepare') {
    await prepareCommand();
    return;
  }
  if (command === 'discover') {
    await discoverCommand();
    return;
  }
  throw new Error(`Unknown artifact_cache command: ${command}`);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
  });
}

module.exports = {
  deriveCachePlan,
  deriveWindow,
  discoverCommand,
  isoWeekParts,
  listArtifacts,
  parseBoolean,
  sanitizeSegment,
  selectArtifact,
};
