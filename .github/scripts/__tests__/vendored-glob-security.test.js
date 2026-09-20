'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

for (const prefix of ['.github/scripts', 'templates/consumer-repo/.github/scripts']) {
  const root = path.resolve(__dirname, '../../..', prefix);
  test(`${prefix}: stable patched vendored releases and bounded expansion`, () => {
    const minimatchPackage = require(path.join(root, 'node_modules/minimatch/package.json'));
    const bracePackage = require(path.join(root, 'node_modules/brace-expansion/package.json'));
    assert.equal(minimatchPackage.version, '10.2.6');
    assert.equal(bracePackage.version, '5.0.12');
    assert.equal(minimatchPackage.scripts, undefined);
    assert.equal(bracePackage.scripts, undefined);
    const { minimatch } = require(path.join(root, 'node_modules/minimatch'));
    const { expand } = require(path.join(root, 'node_modules/brace-expansion'));
    assert.equal(minimatch('src/test7.js', 'src/{test,check}[0-9].js'), true);
    assert.deepEqual(expand('{a,b}{c,d}', { max: 2 }), ['ac', 'ad']);
    assert.ok(expand('{a,b}{c,d}', { maxLength: 4 }).join('').length <= 4);
  });
}

test('lock metadata matches the actual vendored versions without prerelease suffixes', () => {
  const root = path.resolve(__dirname, '..');
  const lock = JSON.parse(fs.readFileSync(path.join(root, 'package-lock.json'), 'utf8'));
  for (const name of ['minimatch', 'brace-expansion']) {
    const metadata = require(path.join(root, 'node_modules', name, 'package.json'));
    assert.equal(lock.packages[`node_modules/${name}`].version, metadata.version);
    assert.match(metadata.version, /^\d+\.\d+\.\d+$/);
  }
  assert.equal(lock.packages[''].dependencies.minimatch, 'file:node_modules/minimatch');
});
