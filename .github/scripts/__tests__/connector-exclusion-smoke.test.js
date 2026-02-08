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
});
