'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  DEFAULT_CATEGORIES,
  classifyFiles,
  globToRegExp,
  matchesAny,
  parseClassificationConfig,
} = require('../../actions/path-classifier/classify.js');

const CONFIG = { categories: DEFAULT_CATEGORIES };

function outputsFor(files, options) {
  return classifyFiles(files, CONFIG, options).outputs;
}

test('glob matcher handles root and nested patterns', () => {
  assert.match('README.md', globToRegExp('*.md'));
  assert.doesNotMatch('docs/README.md', globToRegExp('*.md'));
  assert.equal(matchesAny('pkg/module.py', ['**/*.py']), true);
  assert.equal(matchesAny('module.py', ['**/*.py']), true);
  assert.equal(matchesAny('.github/actions/path-classifier/action.yml', ['.github/actions/**']), true);
});

test('classifies docs-only changes when every path matches docs rules', () => {
  const outputs = outputsFor(['README.md', 'docs/usage.md']);
  assert.equal(outputs['is-docs-only'], 'true');
  assert.equal(outputs['is-python-code'], 'false');
  assert.equal(outputs['is-security-relevant'], 'false');
});

test('classifies python code changes', () => {
  const outputs = outputsFor(['src/app.py', 'requirements-dev.txt']);
  assert.equal(outputs['is-python-code'], 'true');
  assert.equal(outputs['is-docs-only'], 'false');
});

test('classifies workflow and security relevant changes', () => {
  const outputs = outputsFor(['.github/workflows/pr-00-gate.yml']);
  assert.equal(outputs['is-workflow-change'], 'true');
  assert.equal(outputs['is-security-relevant'], 'true');
});

test('classifies security relevant tool and pyproject changes', () => {
  const outputs = outputsFor(['tools/enforce_gate_branch_protection.py', 'pyproject.toml']);
  assert.equal(outputs['is-security-relevant'], 'true');
  assert.equal(outputs['is-python-code'], 'true');
});

test('classifies template changes', () => {
  const outputs = outputsFor(['templates/consumer-repo/.github/workflows/pr-00-gate.yml']);
  assert.equal(outputs['is-template-change'], 'true');
  assert.equal(outputs['is-workflow-change'], 'false');
});

test('classifies test-only changes when every path is a test', () => {
  const outputs = outputsFor([
    'tests/workflows/test_gate.py',
    '.github/scripts/__tests__/path-classifier.test.js',
  ]);
  assert.equal(outputs['is-test-only'], 'true');
  assert.equal(outputs['is-python-code'], 'true');
});

test('mixed docs and code changes are not docs-only or test-only', () => {
  const outputs = outputsFor(['docs/usage.md', 'scripts/sync_dev_dependencies.py']);
  assert.equal(outputs['is-docs-only'], 'false');
  assert.equal(outputs['is-test-only'], 'false');
  assert.equal(outputs['is-python-code'], 'true');
  assert.equal(outputs['is-security-relevant'], 'true');
});

test('empty diff does not enable categories', () => {
  const outputs = outputsFor([]);
  assert.equal(outputs['is-docs-only'], 'false');
  assert.equal(outputs['is-python-code'], 'false');
  assert.equal(outputs['is-workflow-change'], 'false');
  assert.equal(outputs['is-security-relevant'], 'false');
  assert.equal(outputs['is-template-change'], 'false');
  assert.equal(outputs['is-test-only'], 'false');
  assert.equal(outputs['affected-consumers'], '[]');
});

test('force-full override enables every category output', () => {
  const outputs = outputsFor(['README.md'], { forceFull: true });
  assert.equal(outputs['is-docs-only'], 'true');
  assert.equal(outputs['is-python-code'], 'true');
  assert.equal(outputs['is-workflow-change'], 'true');
  assert.equal(outputs['is-security-relevant'], 'true');
  assert.equal(outputs['is-template-change'], 'true');
  assert.equal(outputs['is-test-only'], 'true');
});

test('parses classification YAML config', () => {
  const parsed = parseClassificationConfig(`
categories:
  docs-only:
    require-all: true
    paths:
      - docs/**
      - "*.md"
  python-code:
    require-all: false
    paths: ["**/*.py", pyproject.toml]
`);
  assert.deepEqual(parsed.categories['docs-only'], {
    requireAll: true,
    paths: ['docs/**', '*.md'],
  });
  assert.deepEqual(parsed.categories['python-code'], {
    requireAll: false,
    paths: ['**/*.py', 'pyproject.toml'],
  });
});
