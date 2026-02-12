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

test('classifies documentation files', () => {
  assert.equal(isDocumentationFile('docs/README.md'), true);
  assert.equal(isDocumentationFile('guides/setup.txt'), true);
  assert.equal(isDocumentationFile('src/app.py'), false);
  assert.equal(isDocumentationFile('README'), true);
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
