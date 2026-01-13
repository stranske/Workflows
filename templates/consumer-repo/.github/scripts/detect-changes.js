'use strict';

const DOC_EXTENSIONS = [
  '.md',
  '.mdx',
  '.markdown',
  '.rst',
  '.txt',
  '.qmd',
  '.adoc',
];

const DOC_BASENAMES = new Set([
  'readme',
  'changelog',
  'contributing',
  'code_of_conduct',
  'code-of-conduct',
  'security',
  'guidelines',
  'mkdocs',
  'docfx',
  'antora-playbook',
]);

const DOC_PREFIXES = [
  'docs/',
  'docs\\',
  'docs_',
  'doc/',
  'doc\\',
  'assets/docs/',
  'assets/docs\\',
  'documentation/',
  'documentation\\',
  'guides/',
  'handbook/',
  'manual/',
];

const DOC_SEGMENTS = [
  '/docs/',
  '/doc/',
  '/documentation/',
  '/manual/',
  '/design-docs/',
  '/handbook/',
  '/guide/',
  '/guides/',
  '/adr/',
  '/rfcs/',
  '/specs/',
  '/notes/',
  '\\docs\\',
  '\\doc\\',
  '\\documentation\\',
  '\\manual\\',
  '\\design-docs\\',
  '\\handbook\\',
  '\\guide\\',
  '\\guides\\',
  '\\adr\\',
  '\\rfcs\\',
  '\\specs\\',
  '\\notes\\',
];

const DOCKER_PREFIXES = ['docker/', 'docker\\', '.docker/', '.docker\\'];
const DOCKER_SEGMENTS = ['/docker/', '\\docker\\', '/.docker/', '\\.docker\\'];
const DOCKERFILE_SUFFIXES = ['/dockerfile', '\\dockerfile'];
const WORKFLOW_PREFIX = '.github/workflows/';

function normalizeCase(value) {
  return (value || '').toLowerCase();
}

function normalizeSlashes(value) {
  return normalizeCase(value).replace(/\\/g, '/');
}

function basenameWithoutExtension(filename) {
  const normalized = normalizeSlashes(filename);
  const parts = normalized.split('/');
  const base = parts.length ? parts[parts.length - 1] : normalized;
  if (!base) {
    return '';
  }
  const lastDot = base.lastIndexOf('.');
  return lastDot === -1 ? base : base.slice(0, lastDot);
}

function isDocumentationFile(filename) {
  const normalized = normalizeCase(filename);
  if (!normalized) {
    return false;
  }

  if (DOC_EXTENSIONS.some(ext => normalized.endsWith(ext))) {
    return true;
  }

  const base = basenameWithoutExtension(filename);
  if (base && DOC_BASENAMES.has(base)) {
    return true;
  }

  if (DOC_PREFIXES.some(prefix => normalized.startsWith(prefix))) {
    return true;
  }

  if (DOC_SEGMENTS.some(segment => normalized.includes(segment))) {
    return true;
  }

  return false;
}

function isDockerRelated(filename) {
  const normalized = normalizeCase(filename);
  if (!normalized) {
    return false;
  }

  if (normalized === 'dockerfile') {
    return true;
  }

  if (DOCKERFILE_SUFFIXES.some(suffix => normalized.endsWith(suffix))) {
    return true;
  }

  const base = basenameWithoutExtension(filename);
  if (normalizeCase(base).startsWith('dockerfile')) {
    return true;
  }

  if (normalized === '.dockerignore') {
    return true;
  }

  if (DOCKER_PREFIXES.some(prefix => normalized.startsWith(prefix))) {
    return true;
  }

  if (DOCKER_SEGMENTS.some(segment => normalized.includes(segment))) {
    return true;
  }

  return false;
}

function isWorkflowFile(filename) {
  const normalized = normalizeSlashes(filename);
  return normalized.startsWith(WORKFLOW_PREFIX);
}

function isRateLimitError(error) {
  if (!error) {
    return false;
  }
  const status = error.status || error?.response?.status;
  if (status !== 403) {
    return false;
  }
  const message = String(error.message || error?.response?.data?.message || '').toLowerCase();
  return message.includes('rate limit') || message.includes('ratelimit');
}

async function listChangedFiles({ github, context }) {
  const pull = context?.payload?.pull_request;
  const number = pull?.number;
  if (!github || !context || !number) {
    return [];
  }
  try {
    const iterator = github.paginate.iterator(github.rest.pulls.listFiles, {
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: number,
      per_page: 100,
    });
    const files = [];
    for await (const page of iterator) {
      if (Array.isArray(page.data)) {
        for (const item of page.data) {
          if (item && typeof item.filename === 'string') {
            files.push(item.filename);
          }
        }
      }
    }
    return files;
  } catch (error) {
    if (isRateLimitError(error)) {
      return null;
    }
    throw error;
  }
}

function classifyChanges(filenames) {
  const changedFiles = Array.from(new Set(filenames.filter(Boolean)));
  const hasChanges = changedFiles.length > 0;
  const nonDocFiles = changedFiles.filter(filename => !isDocumentationFile(filename));
  const docOnly = hasChanges ? nonDocFiles.length === 0 : true;
  const dockerChanged = changedFiles.some(filename => isDockerRelated(filename));
  const workflowChanged = changedFiles.some(filename => isWorkflowFile(filename));
  let reason = 'code_changes';
  if (!hasChanges) {
    reason = 'no_changes';
  } else if (docOnly) {
    reason = 'docs_only';
  }

  return {
    changedFiles,
    hasChanges,
    nonDocFiles,
    docOnly,
    dockerChanged,
    workflowChanged,
    reason,
  };
}

async function detectChanges({ github, context, core, files, fetchFiles } = {}) {
  const eventName = context?.eventName;
  if (eventName !== 'pull_request') {
    const outputs = {
      doc_only: 'false',
      run_core: 'true',
      reason: 'non_pr_event',
      docker_changed: 'false',  // Don't assume docker changes - causes failures in repos without Dockerfile
      workflow_changed: 'true',
    };
    if (core) {
      for (const [key, value] of Object.entries(outputs)) {
        core.setOutput(key, value);
      }
    }
    return { outputs, details: null };
  }

  let changedFiles = Array.isArray(files) ? files : null;
  if (!changedFiles) {
    if (typeof fetchFiles === 'function') {
      changedFiles = await fetchFiles();
    } else {
      changedFiles = await listChangedFiles({ github, context });
    }
  }

  if (changedFiles === null) {
    const outputs = {
      doc_only: 'false',
      run_core: 'true',
      reason: 'rate_limited',
      docker_changed: 'false',  // Don't assume docker changes - causes failures in repos without Dockerfile
      workflow_changed: 'true',
    };
    const warn = core?.warning ? core.warning.bind(core) : console.warn.bind(console);
    warn('Rate limit reached while determining changed files; assuming code changes (but not docker).');
    if (core) {
      for (const [key, value] of Object.entries(outputs)) {
        core.setOutput(key, value);
      }
    }
    return { outputs, details: null };
  }

  const { docOnly, dockerChanged, workflowChanged, reason } = classifyChanges(changedFiles);
  const outputs = {
    doc_only: docOnly ? 'true' : 'false',
    run_core: docOnly ? 'false' : 'true',
    reason,
    docker_changed: dockerChanged ? 'true' : 'false',
    workflow_changed: workflowChanged ? 'true' : 'false',
  };

  if (core) {
    for (const [key, value] of Object.entries(outputs)) {
      core.setOutput(key, value);
    }
  }

  return {
    outputs,
    details: {
      changedFiles,
      docOnly,
      dockerChanged,
      workflowChanged,
      reason,
    },
  };
}

module.exports = {
  detectChanges,
  classifyChanges,
  isDocumentationFile,
  isDockerRelated,
  isWorkflowFile,
};
