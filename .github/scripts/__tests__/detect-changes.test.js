'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  detectChanges,
  classifyChanges,
  isDocumentationFile,
  isDockerRelated,
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

test('classify changes summary', () => {
  const result = classifyChanges(['docs/README.md', 'docs/guide.txt']);
  assert.equal(result.docOnly, true);
  assert.equal(result.dockerChanged, false);
  assert.equal(result.reason, 'docs_only');

  const result2 = classifyChanges(['Dockerfile', 'src/app.py']);
  assert.equal(result2.docOnly, false);
  assert.equal(result2.dockerChanged, true);
  assert.equal(result2.reason, 'code_changes');
});

test('detectChanges handles non pull request events', async () => {
  const result = await detectChanges({
    context: { eventName: 'push' },
  });
  assert.deepEqual(result.outputs, {
    doc_only: 'false',
    run_core: 'true',
    reason: 'non_pr_event',
    docker_changed: 'true',
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
});

test('detectChanges fetches files via callback', async () => {
  const result = await detectChanges({
    context: { eventName: 'pull_request' },
    fetchFiles: async () => ['src/app.py', 'Dockerfile'],
  });
  assert.equal(result.outputs.doc_only, 'false');
  assert.equal(result.outputs.docker_changed, 'true');
  assert.equal(result.outputs.run_core, 'true');
});
