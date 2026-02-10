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

  it('filters a repo-style file list before downstream processing', () => {
    const input = [
      '.agents/issue-test-ledger.yml',
      'src/app.ts',
      'src/other.ts'
    ];

    const result = filterPaths(input);

    assert.deepStrictEqual(result.kept, ['src/app.ts', 'src/other.ts']);
    assert.deepStrictEqual(result.ignored, ['.agents/issue-test-ledger.yml']);
  });

  it('respects minimatch semantics for include patterns', () => {
    const input = [
      'src/a.ts',
      'src/b.ts',
      'src/c.ts',
      '.agents/issue-1234-ledger.yml'
    ];

    const result = filterPaths(input, { PR_CONTEXT_INCLUDE_PATTERNS: 'src/[ab].ts' });

    assert.deepStrictEqual(result.kept, ['src/a.ts', 'src/b.ts']);
    assert.deepStrictEqual(result.ignored, ['src/c.ts', '.agents/issue-1234-ledger.yml']);
  });

  it('supports brace expansion include patterns', () => {
    const input = [
      'src/app.ts',
      'src/view.tsx',
      'src/app.js',
      '.agents/issue-1234-ledger.yml'
    ];

    const result = filterPaths(input, { PR_CONTEXT_INCLUDE_PATTERNS: 'src/*.{ts,tsx}' });

    assert.deepStrictEqual(result.kept, ['src/app.ts', 'src/view.tsx']);
    assert.deepStrictEqual(result.ignored, ['src/app.js', '.agents/issue-1234-ledger.yml']);
  });

  it('supports escaped metacharacters in include patterns', () => {
    const input = [
      'docs/[draft].md',
      'docs/draft.md',
      '.agents/issue-1234-ledger.yml'
    ];

    const result = filterPaths(input, { PR_CONTEXT_INCLUDE_PATTERNS: 'docs/\\[draft\\].md' });

    assert.deepStrictEqual(result.kept, ['docs/[draft].md']);
    assert.deepStrictEqual(result.ignored, ['docs/draft.md', '.agents/issue-1234-ledger.yml']);
  });
});
