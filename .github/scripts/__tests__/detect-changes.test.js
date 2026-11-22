'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  detectChanges,
  classifyChanges,
  isDocumentationFile,
  isDockerRelated,
  isWorkflowFile,
} = require('../detect-changes');
const { classifyFiles, loadConfig } = require('../../actions/path-classifier/classify.js');
const { resolve } = require('node:path');

test('classifies documentation files', () => {
  assert.equal(isDocumentationFile('docs/README.md'), true);
  assert.equal(isDocumentationFile('guides/setup.txt'), true);
  assert.equal(isDocumentationFile('src/app.py'), false);
  assert.equal(isDocumentationFile('README'), true);
});

test('normal Gate selects each committed source-pin surface', () => {
  const config = loadConfig(resolve(__dirname, '../../path-classification.yml'));
  const pinPaths = [
    '.github/workflows/autofix-versions.env',
    '.pre-commit-config.yaml',
    'pyproject.toml',
    'requirements.lock',
    'templates/consumer-repo/.github/workflows/autofix-versions.env',
    'templates/integration-repo/.github/workflows/autofix-versions.env',
  ];
  for (const path of pinPaths) {
    assert.equal(classifyChanges([path]).docOnly, false, path);
    assert.equal(classifyFiles([path], config).outputs['is-docs-only'], 'false', path);
  }
  assert.equal(classifyChanges(['README.md']).docOnly, true);
  assert.equal(classifyFiles(['README.md'], config).outputs['is-docs-only'], 'true');
});

test('detects docker related files', () => {
  assert.equal(isDockerRelated('Dockerfile'), true);
  assert.equal(isDockerRelated('docker/Dockerfile'), true);
  assert.equal(isDockerRelated('.dockerignore'), true);
  assert.equal(isDockerRelated('src/app.py'), false);
});

test('detects workflow files', () => {
  assert.equal(isWorkflowFile('.github/workflows/example.yml'), true);
  assert.equal(isWorkflowFile('src/.github/workflows/example.yml'), false);
});

test('classify changes summary', () => {
  const result = classifyChanges(['docs/README.md', 'docs/guide.txt']);
  assert.equal(result.docOnly, true);
  assert.equal(result.dockerChanged, false);
  assert.equal(result.workflowChanged, false);
  assert.equal(result.reason, 'docs_only');

  const result2 = classifyChanges(['Dockerfile', 'src/app.py']);
  assert.equal(result2.docOnly, false);
  assert.equal(result2.dockerChanged, true);
  assert.equal(result2.workflowChanged, false);
  assert.equal(result2.reason, 'code_changes');

  const result3 = classifyChanges(['.github/workflows/changes.yml', 'docs/README.md']);
  assert.equal(result3.docOnly, false);
  assert.equal(result3.workflowChanged, true);
});

test('classify changes tolerates non-array and mixed input', () => {
  const single = classifyChanges('docs/README.md');
  assert.equal(single.docOnly, true);
  assert.equal(single.reason, 'docs_only');

  const mixed = classifyChanges(['src/app.py', null, 123, false]);
  assert.equal(mixed.docOnly, false);
  assert.equal(mixed.reason, 'code_changes');
});

test('detectChanges handles non pull request events', async () => {
  const result = await detectChanges({
    context: { eventName: 'push' },
  });
  assert.deepEqual(result.outputs, {
    doc_only: 'false',
    run_core: 'true',
    reason: 'non_pr_event',
    docker_changed: 'false',  // Don't assume docker changes - causes failures in repos without Dockerfile
    workflow_changed: 'true',
  });
});

test('detectChanges consumes provided files', async () => {
  const result = await detectChanges({
    context: { eventName: 'pull_request' },
    files: ['docs/README.md'],
  });
  assert.equal(result.outputs.doc_only, 'true');
  assert.equal(result.outputs.run_core, 'false');
  assert.equal(result.outputs.reason, 'docs_only');
  assert.equal(result.outputs.workflow_changed, 'false');
});

test('detectChanges fetches files via callback', async () => {
  const result = await detectChanges({
    context: { eventName: 'pull_request' },
    fetchFiles: async () => ['src/app.py', 'Dockerfile'],
  });
  assert.equal(result.outputs.doc_only, 'false');
  assert.equal(result.outputs.docker_changed, 'true');
  assert.equal(result.outputs.run_core, 'true');
  assert.equal(result.outputs.workflow_changed, 'false');
});

test('detectChanges falls back to conservative defaults when listFiles is inaccessible', async () => {
  const warnings = [];
  const result = await detectChanges({
    core: {
      warning(message) {
        warnings.push(String(message));
      },
      setOutput() {},
    },
    context: {
      eventName: 'pull_request',
      repo: { owner: 'octo', repo: 'demo' },
      payload: { pull_request: { number: 42 } },
    },
    github: {
      rest: {
        pulls: {
          listFiles: async () => ({ data: [] }),
        },
      },
      paginate: {
        iterator: () => {
          const error = new Error('Resource not accessible by integration');
          error.status = 403;
          throw error;
        },
      },
    },
  });

  assert.equal(result.outputs.doc_only, 'false');
  assert.equal(result.outputs.run_core, 'true');
  assert.equal(result.outputs.reason, 'rate_limited');
  assert.equal(result.outputs.docker_changed, 'false');
  assert.equal(result.outputs.workflow_changed, 'true');
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /Unable to determine changed files via API/);
});

test('detectChanges supports clients without paginate.iterator', async () => {
  const result = await detectChanges({
    context: {
      eventName: 'pull_request',
      repo: { owner: 'octo', repo: 'demo' },
      payload: { pull_request: { number: 1 } },
    },
    github: {
      rest: {
        pulls: {
          listFiles: async () => ({ data: [] }),
        },
      },
      paginate: async () => [{ filename: 'docs/README.md' }],
    },
  });

  assert.equal(result.outputs.doc_only, 'true');
  assert.equal(result.outputs.run_core, 'false');
  assert.equal(result.outputs.reason, 'docs_only');
  assert.equal(result.outputs.workflow_changed, 'false');
});

test('detectChanges falls back to raw github when wrapper initialization fails', async () => {
  const warnings = [];
  const github = {};
  Object.defineProperty(github, 'request', {
    get() {
      throw new Error('request getter boom');
    },
  });
  github.hook = {};

  const result = await detectChanges({
    github,
    core: {
      warning(message) {
        warnings.push(String(message));
      },
      setOutput() {},
    },
    context: { eventName: 'pull_request' },
    files: ['src/app.py'],
  });

  assert.equal(result.outputs.doc_only, 'false');
  assert.equal(result.outputs.run_core, 'true');
  assert.equal(result.outputs.reason, 'code_changes');
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /Failed to enable rate-limit wrapper for detect-changes/);
});

test('detectChanges preserves non-error wrapper initialization failures', async () => {
  const warnings = [];
  const github = {};
  Object.defineProperty(github, 'request', {
    get() {
      throw 'string boom';
    },
  });
  github.hook = {};

  await detectChanges({
    github,
    core: {
      warning(message) {
        warnings.push(String(message));
      },
      setOutput() {},
    },
    context: { eventName: 'pull_request' },
    files: ['src/app.py'],
  });

  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /string boom/);
});


test('opt-in app-baseline-kit detection preserves normal paths and includes either rename side', async () => {
  const inputCases = [
    [[{ filename: 'packages/app-baseline-kit/baseline_kit/manifest.py' }], 'true'],
    [[{ filename: 'packages/app-baseline-kit/tests/test_snapshot/golden.yml', status: 'removed' }], 'true'],
    [[{ filename: 'packages/app-baseline-kit/pyproject.toml' }], 'true'],
    [[{ filename: 'docs/golden.yml', previous_filename: 'packages/app-baseline-kit/tests/golden.yml' }], 'true'],
    [[{ filename: '.github/workflows/pr-00-gate.yml' }], 'true'],
    [[{ filename: 'packages/app-baseline-kit/README.md' }], 'false'],
    [[{ filename: 'packages/app-baseline-kit/README.md' }, { filename: '.github/path-classification.yml' }], 'false'],
    [[{ filename: 'packages/app-baseline-kit/README.md' }, { filename: '.github/workflows/pr-00-gate.yml' }], 'true'],
    [[{ filename: 'packages/stranske_pdf_extract/pyproject.toml' }], 'false'],
    [[{ filename: 'scripts/unrelated.py' }], 'false'],
  ];
  for (const [records, expected] of inputCases) {
    const result = await detectChanges({
      checkAppBaselineKit: true,
      context: {
        eventName: 'pull_request',
        repo: { owner: 'octo', repo: 'demo' },
        payload: { pull_request: { number: 1, changed_files: records.length } },
      },
      github: {
        rest: { pulls: { listFiles: async () => ({ data: records }) } },
        paginate: { iterator: async function* () { yield { data: records }; } },
      },
    });
    assert.equal(result.outputs.app_baseline_kit_changed, expected, records[0].filename);
    assert.deepEqual(result.details.changedFiles, records.map(file => file.filename));
  }
});

test('opt-in app-baseline-kit detection selects unknown, partial and deliberate full runs', async () => {
  const unavailable = await detectChanges({
    checkAppBaselineKit: true,
    context: { eventName: 'pull_request' },
    fetchFiles: async () => null,
    core: { warning() {}, setOutput() {} },
  });
  const incomplete = await detectChanges({
    checkAppBaselineKit: true,
    context: { eventName: 'pull_request', payload: { pull_request: { changed_files: 2 } } },
    files: ['docs/README.md'],
  });
  const dispatch = await detectChanges({
    checkAppBaselineKit: true,
    context: { eventName: 'workflow_dispatch' },
  });
  for (const result of [unavailable, incomplete, dispatch]) {
    assert.equal(result.outputs.app_baseline_kit_changed, 'true');
  }
});
