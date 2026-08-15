'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const crypto = require('crypto');
const vm = require('node:vm');

// The first delivery to an older consumer may add this contract to a base
// branch that does not contain it yet.  The classifier must never execute an
// arbitrary module supplied by that PR: accept only the exact source contract
// published by Workflows.  Subsequent deliveries read the trusted base copy.
const BOOTSTRAP_DELIVERY_CONTRACT_SHA256 = 'b61558cca342ffffbdfc22453e585e252a7465a2d3407020e10e4bda73065023';

const OUTPUT_NAMES = {
  'docs-only': 'is-docs-only',
  'python-code': 'is-python-code',
  'workflow-change': 'is-workflow-change',
  'security-relevant': 'is-security-relevant',
  'template-change': 'is-template-change',
  'test-only': 'is-test-only',
};

const DEFAULT_CATEGORIES = {
  'docs-only': { paths: ['docs/**', '*.md', 'README.md'], requireAll: true },
  'python-code': { paths: ['**/*.py', 'pyproject.toml', 'requirements*.txt'], requireAll: false },
  'workflow-change': { paths: ['.github/workflows/**', '.github/actions/**'], requireAll: false },
  'security-relevant': {
    paths: ['scripts/**', 'tools/**', '.github/workflows/**', 'pyproject.toml'],
    requireAll: false,
  },
  'template-change': { paths: ['templates/**'], requireAll: false },
  'test-only': { paths: ['tests/**', '**/test_*.py', '**/*.test.js'], requireAll: true },
};

const STABLE_SYNC_BRANCHES = new Set([
  'sync/workflows-candidate',
  'sync/workflows-delivery',
]);

function isStableDeliveryPullRequest(githubContext) {
  const branch = githubContext?.event?.pull_request?.head?.ref || '';
  return githubContext?.event_name === 'pull_request' && STABLE_SYNC_BRANCHES.has(branch);
}

function normalizePath(value) {
  return String(value || '').replace(/\\/g, '/').replace(/^\.\/+/, '');
}

function escapeRegExp(value) {
  return value.replace(/[|\\{}()[\]^$+?.]/g, '\\$&');
}

function globToRegExp(glob) {
  const pattern = normalizePath(glob);
  let out = '^';
  for (let index = 0; index < pattern.length; index += 1) {
    const char = pattern[index];
    const next = pattern[index + 1];
    if (char === '*') {
      if (next === '*') {
        const after = pattern[index + 2];
        if (after === '/') {
          out += '(?:.*/)?';
          index += 2;
        } else {
          out += '.*';
          index += 1;
        }
      } else {
        out += '[^/]*';
      }
    } else if (char === '?') {
      out += '[^/]';
    } else {
      out += escapeRegExp(char);
    }
  }
  out += '$';
  return new RegExp(out);
}

function matchesAny(filePath, patterns) {
  const normalized = normalizePath(filePath);
  return patterns.some((pattern) => globToRegExp(pattern).test(normalized));
}

function parseScalar(value) {
  const trimmed = String(value || '').trim();
  if (trimmed === 'true') {
    return true;
  }
  if (trimmed === 'false') {
    return false;
  }
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function parseInlineList(value) {
  const trimmed = String(value || '').trim();
  if (!trimmed.startsWith('[') || !trimmed.endsWith(']')) {
    return null;
  }
  const body = trimmed.slice(1, -1).trim();
  if (!body) {
    return [];
  }
  return body.split(',').map((entry) => parseScalar(entry));
}

function parseClassificationConfig(raw) {
  const categories = {};
  const lines = String(raw || '').split(/\r?\n/);
  let section = null;
  let category = null;
  let listKey = null;

  for (const line of lines) {
    const withoutComment = line.replace(/\s+#.*$/, '');
    if (!withoutComment.trim()) {
      continue;
    }
    const indent = withoutComment.match(/^ */)[0].length;
    const trimmed = withoutComment.trim();

    if (indent === 0 && trimmed.endsWith(':')) {
      section = trimmed.slice(0, -1);
      category = null;
      listKey = null;
      continue;
    }

    if (section !== 'categories') {
      continue;
    }

    if (indent === 2 && trimmed.endsWith(':')) {
      category = trimmed.slice(0, -1);
      categories[category] = categories[category] || {};
      listKey = null;
      continue;
    }

    if (!category) {
      continue;
    }

    if (indent === 4 && trimmed.includes(':')) {
      const [key, ...rest] = trimmed.split(':');
      const value = rest.join(':').trim();
      const normalizedKey = key === 'require-all' ? 'requireAll' : key;
      if (!value) {
        categories[category][normalizedKey] = [];
        listKey = normalizedKey;
        continue;
      }
      const inlineList = parseInlineList(value);
      categories[category][normalizedKey] = inlineList === null ? parseScalar(value) : inlineList;
      listKey = null;
      continue;
    }

    if (indent >= 6 && listKey && trimmed.startsWith('- ')) {
      categories[category][listKey].push(parseScalar(trimmed.slice(2)));
    }
  }

  return { categories };
}

function loadConfig(configPath) {
  const resolved = path.resolve(process.env.GITHUB_WORKSPACE || process.cwd(), configPath);
  if (!fs.existsSync(resolved)) {
    return { categories: DEFAULT_CATEGORIES, configPath: resolved, usedDefault: true };
  }
  const parsed = parseClassificationConfig(fs.readFileSync(resolved, 'utf8'));
  const categories = {};
  for (const [name, fallback] of Object.entries(DEFAULT_CATEGORIES)) {
    const configured = parsed.categories[name] || {};
    categories[name] = {
      paths: Array.isArray(configured.paths) ? configured.paths : fallback.paths,
      requireAll:
        typeof configured.requireAll === 'boolean' ? configured.requireAll : fallback.requireAll,
    };
  }
  return { categories, configPath: resolved, usedDefault: false };
}

function parseGithubContext() {
  try {
    return JSON.parse(process.env.GITHUB_CONTEXT_JSON || '{}');
  } catch {
    return {};
  }
}

function stableDeliverySealStatus(githubContext, { contract, now } = {}) {
  const event = githubContext?.event || {};
  const pullRequest = event.pull_request;
  if (!isStableDeliveryPullRequest(githubContext)) {
    return { required: false, valid: true, reason: '' };
  }

  const headRepository = pullRequest?.head?.repo?.full_name || '';
  const baseRepository = pullRequest?.base?.repo?.full_name || '';
  if (!headRepository || !baseRepository || headRepository !== baseRepository) {
    return {
      required: true,
      valid: false,
      reason: 'stable delivery must originate from the base repository',
    };
  }
  if (!contract) {
    return { required: true, valid: false, reason: 'delivery contract is unavailable' };
  }

  const record = contract.parseDeliveryRecord(pullRequest?.body || '');
  const eligibility = contract.mergeEligibility(record, {
    now: now || new Date().toISOString(),
    repository: baseRepository,
    requireSealed: true,
    headSha: pullRequest?.head?.sha || '',
  });
  return {
    required: true,
    valid: Boolean(eligibility.eligible),
    reason: eligibility.reason,
  };
}

function compileDeliveryContract(source, filename) {
  const module = { exports: {} };
  const sandbox = { module, exports: module.exports };
  vm.runInNewContext(String(source), sandbox, { filename });
  return module.exports;
}

function readContractAtRef(ref, contractPath) {
  // Keep the object bytes intact: the bootstrap allowlist digest is calculated
  // from the canonical tracked file, including its trailing newline.
  return readGit(['show', `${ref}:${contractPath}`]);
}

function readGit(args) {
  return execFileSync('git', args, {
    cwd: process.env.GITHUB_WORKSPACE || process.cwd(),
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

function runGit(args) {
  return readGit(args).trim();
}

function isAddOnlyContractDiff(diffText, contractPath) {
  return String(diffText || '')
    .split(/\r?\n/)
    .some((line) => line === `A\t${contractPath}`);
}

function contractAddedBetweenRefs(baseSha, headSha, contractPath) {
  const added = runGit([
    'diff',
    '--name-status',
    '--diff-filter=A',
    baseSha,
    headSha,
    '--',
    contractPath,
  ]);
  return isAddOnlyContractDiff(added, contractPath);
}

function loadDeliveryContract(
  githubContext = {},
  {
    readTrustedContract = readContractAtRef,
    readBootstrapContract = readContractAtRef,
    isBootstrapAddition = contractAddedBetweenRefs,
  } = {},
) {
  const workspace = process.env.GITHUB_WORKSPACE || process.cwd();
  const relativeContractPath = '.github/scripts/sync_pr_lease_contract.js';
  const pullRequest = githubContext?.event?.pull_request;

  if (isStableDeliveryPullRequest(githubContext)) {
    const baseSha = pullRequest?.base?.sha || '';
    if (!baseSha) {
      return null;
    }
    try {
      const source = readTrustedContract(baseSha, relativeContractPath);
      return compileDeliveryContract(source, `${baseSha}:${relativeContractPath}`);
    } catch {
      // A consumer's first stable-delivery rollout necessarily predates the
      // lease contract on its base. Permit only that exact add-only bootstrap:
      // same repository, exact observed head, and the contract path added (not
      // modified or renamed) between base and head. Maint 71 remains the final
      // boundary and independently requires the exact generated head to carry
      // a valid GitHub-recognized signature before it can merge.
      const headSha = pullRequest?.head?.sha || '';
      const headRepository = pullRequest?.head?.repo?.full_name || '';
      const baseRepository = pullRequest?.base?.repo?.full_name || '';
      if (!headSha || !headRepository || headRepository !== baseRepository) {
        return null;
      }
      try {
        if (!isBootstrapAddition(baseSha, headSha, relativeContractPath)) {
          return null;
        }
        const source = readBootstrapContract(headSha, relativeContractPath);
        const digest = crypto.createHash('sha256').update(String(source)).digest('hex');
        if (digest !== BOOTSTRAP_DELIVERY_CONTRACT_SHA256) {
          return null;
        }
        return compileDeliveryContract(source, `${headSha}:${relativeContractPath}`);
      } catch {
        return null;
      }
    }
  }

  const contractPath = path.resolve(workspace, relativeContractPath);
  if (!fs.existsSync(contractPath)) {
    return null;
  }
  return require(contractPath);
}

function tryGit(args) {
  try {
    return runGit(args);
  } catch {
    return '';
  }
}

function resolveBaseRef(inputBaseRef, githubContext) {
  if (inputBaseRef) {
    return inputBaseRef;
  }
  if (githubContext.event_name === 'pull_request' && githubContext.base_ref) {
    return `origin/${githubContext.base_ref}`;
  }
  const event = githubContext.event || {};
  if (event.before && !/^0+$/.test(event.before)) {
    return event.before;
  }
  return '';
}

function fetchBaseRef(baseRef, githubContext, fetchGit = tryGit) {
  if (!baseRef || !baseRef.startsWith('origin/')) {
    return;
  }
  const branch = baseRef.slice('origin/'.length);
  const refs = [branch];
  const prBaseSha = githubContext.event?.pull_request?.base?.sha;
  if (prBaseSha) {
    refs.push(prBaseSha);
  }
  // actions/checkout uses a depth-one synthetic merge commit for pull_request
  // events, so the exact head object is not guaranteed to exist locally. The
  // add-only first-delivery bootstrap compares and reads that exact head.
  const pullRequest = githubContext.event?.pull_request;
  const prHeadSha = pullRequest?.head?.sha;
  const headRepository = pullRequest?.head?.repo?.full_name || '';
  const baseRepository = pullRequest?.base?.repo?.full_name || '';
  if (
    isStableDeliveryPullRequest(githubContext)
    && prHeadSha
    && headRepository
    && headRepository === baseRepository
  ) {
    refs.push(prHeadSha);
  }
  fetchGit(['fetch', '--no-tags', '--depth=1', 'origin', ...new Set(refs)]);
}

function listChangedFiles({
  baseRef,
  githubContext,
  baseAlreadyFetched = false,
  fetchBase = fetchBaseRef,
  diffGit = tryGit,
} = {}) {
  const envFiles = process.env.PATH_CLASSIFIER_FILES_JSON;
  if (envFiles) {
    const parsed = JSON.parse(envFiles);
    if (!Array.isArray(parsed)) {
      throw new Error('PATH_CLASSIFIER_FILES_JSON must be a JSON array');
    }
    return parsed.map(normalizePath).filter(Boolean);
  }

  if (!baseAlreadyFetched) {
    fetchBase(baseRef, githubContext);
  }
  const head = githubContext.sha || 'HEAD';
  const ranges = [];
  if (baseRef) {
    ranges.push(`${baseRef}...${head}`);
    ranges.push(`${baseRef}..${head}`);
  }
  const prBaseSha = githubContext.event?.pull_request?.base?.sha;
  if (prBaseSha) {
    ranges.push(`${prBaseSha}...${head}`);
    ranges.push(`${prBaseSha}..${head}`);
  }

  for (const range of ranges) {
    const output = diffGit(['diff', '--name-only', range]);
    if (output) {
      return output.split(/\r?\n/).map(normalizePath).filter(Boolean);
    }
  }
  return [];
}

function classifyFiles(files, config, { forceFull = false, conservativeFull = false } = {}) {
  const changedFiles = Array.from(new Set((files || []).map(normalizePath).filter(Boolean)));
  const outputs = {};
  const matched = {};

  for (const [category, rule] of Object.entries(config.categories)) {
    const outputName = OUTPUT_NAMES[category] || `is-${category}`;
    const patterns = Array.isArray(rule.paths) ? rule.paths : [];
    const matches = changedFiles.filter((filePath) => matchesAny(filePath, patterns));
    let enabled;
    if (forceFull || conservativeFull) {
      enabled = true;
    } else if (changedFiles.length === 0) {
      enabled = false;
    } else if (rule.requireAll) {
      enabled = matches.length === changedFiles.length;
    } else {
      enabled = matches.length > 0;
    }
    outputs[outputName] = enabled ? 'true' : 'false';
    matched[category] = matches;
  }

  outputs['affected-consumers'] = '[]';
  const trueOutputs = Object.entries(outputs)
    .filter(([key, value]) => key.startsWith('is-') && value === 'true')
    .map(([key]) => key.replace(/^is-/, ''));
  const mode = forceFull ? 'force-full' : conservativeFull ? 'conservative-full' : 'classified';
  outputs['classification-rationale'] =
    `${mode}: ${changedFiles.length} changed file(s); ` +
    (trueOutputs.length ? `matched ${trueOutputs.join(', ')}` : 'no categories matched');

  return { outputs, changedFiles, matched };
}

function writeOutputs(outputs) {
  const outputPath = process.env.GITHUB_OUTPUT;
  for (const [key, value] of Object.entries(outputs)) {
    console.log(`${key}=${value}`);
  }
  if (!outputPath) {
    return;
  }
  const lines = [];
  for (const [key, value] of Object.entries(outputs)) {
    if (String(value).includes('\n')) {
      lines.push(`${key}<<PATH_CLASSIFIER_EOF\n${value}\nPATH_CLASSIFIER_EOF`);
    } else {
      lines.push(`${key}=${value}`);
    }
  }
  fs.appendFileSync(outputPath, `${lines.join('\n')}\n`, 'utf8');
}

function main() {
  const githubContext = parseGithubContext();
  const baseRef = resolveBaseRef(process.env.INPUT_BASE_REF || '', githubContext);
  // The stable-delivery contract is loaded from the exact trusted base SHA.
  // Fetch it before evaluating a stable delivery seal, then reuse that fetch
  // for changed-file classification. Ordinary PRs defer the same fetch until
  // classification so every run fetches the base at most once.
  const baseAlreadyFetched = isStableDeliveryPullRequest(githubContext);
  if (baseAlreadyFetched) {
    fetchBaseRef(baseRef, githubContext);
  }
  const seal = stableDeliverySealStatus(githubContext, {
    contract: loadDeliveryContract(githubContext),
  });
  if (seal.required && !seal.valid) {
    throw new Error(
      `Mutable generated delivery is not mergeable: ${seal.reason}. ` +
      'Maint 71 must seal this exact head after bounded reviewer settlement.',
    );
  }
  const forceFull = String(process.env.INPUT_FORCE_FULL || '').toLowerCase() === 'true';
  const configPath = process.env.INPUT_CONFIG_PATH || '.github/path-classification.yml';
  const config = loadConfig(configPath);
  let files = [];
  let conservativeFull = false;

  try {
    files = listChangedFiles({ baseRef, githubContext, baseAlreadyFetched });
  } catch (error) {
    conservativeFull = true;
    console.warn(`::warning::Unable to list changed files; forcing full classification: ${error.message}`);
  }

  const result = classifyFiles(files, config, { forceFull, conservativeFull });
  writeOutputs(result.outputs);
  console.log(`Changed files: ${result.changedFiles.join(', ') || '(none)'}`);
  console.log(`Config: ${config.configPath}${config.usedDefault ? ' (default fallback)' : ''}`);
}

if (require.main === module) {
  main();
}

module.exports = {
  DEFAULT_CATEGORIES,
  OUTPUT_NAMES,
  classifyFiles,
  fetchBaseRef,
  globToRegExp,
  isAddOnlyContractDiff,
  isStableDeliveryPullRequest,
  listChangedFiles,
  loadConfig,
  loadDeliveryContract,
  matchesAny,
  normalizePath,
  parseClassificationConfig,
  stableDeliverySealStatus,
};
