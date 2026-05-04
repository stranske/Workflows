'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');

const {
  DEFAULT_CATEGORIES,
  classifyFiles,
  matchesAny,
} = require('../../actions/path-classifier/classify.js');

const CONFIG = { categories: DEFAULT_CATEGORIES };
const SINCE = '2026-02-03';

function runGh(args) {
  return execFileSync('gh', args, {
    cwd: process.cwd(),
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

function requireGh() {
  try {
    runGh(['auth', 'status']);
  } catch (error) {
    throw new Error(`gh authentication is required for path-classifier replay: ${error.message}`);
  }
}

function listRecentMergedPullRequests() {
  const raw = runGh([
    'pr',
    'list',
    '--repo',
    'stranske/Workflows',
    '--state',
    'merged',
    '--limit',
    '200',
    '--search',
    `merged:>=${SINCE}`,
    '--json',
    'number,mergedAt,files',
  ]);
  return JSON.parse(raw);
}

function expectRequireAll(files, patterns) {
  return files.length > 0 && files.every((filePath) => matchesAny(filePath, patterns));
}

function expectAny(files, patterns) {
  return files.some((filePath) => matchesAny(filePath, patterns));
}

test('historical merged PR replay matches classification expectations for last 90 days', {
  skip: process.env.PATH_CLASSIFIER_REPLAY !== '1'
    ? 'set PATH_CLASSIFIER_REPLAY=1 to run live GitHub replay'
    : false,
}, () => {
  requireGh();
  const pullRequests = listRecentMergedPullRequests();
  assert.ok(pullRequests.length > 0, 'expected at least one merged PR in replay window');

  const failures = [];
  for (const pr of pullRequests) {
    const files = (pr.files || []).map((file) => file.path).filter(Boolean);
    const outputs = classifyFiles(files, CONFIG).outputs;
    const expected = {
      'is-docs-only': expectRequireAll(files, CONFIG.categories['docs-only'].paths),
      'is-python-code': expectAny(files, CONFIG.categories['python-code'].paths),
      'is-workflow-change': expectAny(files, CONFIG.categories['workflow-change'].paths),
      'is-security-relevant': expectAny(files, CONFIG.categories['security-relevant'].paths),
      'is-template-change': expectAny(files, CONFIG.categories['template-change'].paths),
      'is-test-only': expectRequireAll(files, CONFIG.categories['test-only'].paths),
    };

    for (const [name, expectedValue] of Object.entries(expected)) {
      if (outputs[name] !== String(expectedValue)) {
        failures.push(
          `PR #${pr.number} ${name}: expected ${expectedValue}, got ${outputs[name]} for ${files.join(', ')}`,
        );
      }
    }
  }

  assert.deepEqual(failures, []);
});
