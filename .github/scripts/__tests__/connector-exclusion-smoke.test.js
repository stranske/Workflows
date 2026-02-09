'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert');

const { filterPaths } = require('../connector-exclusion-smoke');

describe('connector-exclusion-smoke', () => {
  it('filters .agents ledger files using default ignore rules', () => {
    const input = [
      '.agents/issue-1234-ledger.yml',
      '.agents/notes.txt',
      'src/index.js'
    ];

    const result = filterPaths(input);

    assert.deepStrictEqual(result.ignored, [
      '.agents/issue-1234-ledger.yml',
      '.agents/notes.txt'
    ]);
    assert.deepStrictEqual(result.kept, ['src/index.js']);
  });

  it('excludes .agents paths even when include patterns are broad', () => {
    const input = [
      '.agents/issue-test-ledger.yml',
      'src/app.ts'
    ];

    const result = filterPaths(input, { PR_CONTEXT_INCLUDE_PATTERNS: '**/*' });

    assert.deepStrictEqual(result.ignored, ['.agents/issue-test-ledger.yml']);
    assert.deepStrictEqual(result.kept, ['src/app.ts']);
  });
});
