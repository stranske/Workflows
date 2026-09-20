'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { spawnSync } = require('node:child_process');

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
    assert.deepEqual(expand('{a,b}{c,d}', { maxLength: 4 }), ['ac', 'ad']);
  });
  test(`${prefix}: nesting and rewrite limits bound pathological inputs`, () => {
    // A subprocess timeout also bounds a regression that restores runaway work.
    const probe = spawnSync(process.execPath, ['-e', `
      const assert = require('node:assert/strict');
      const { expand } = require(${JSON.stringify(path.join(root, 'node_modules/brace-expansion'))});
      const nested = '{'.repeat(1024) + 'a,b' + '}'.repeat(1024);
      assert.deepEqual(expand(nested, { maxDepth: 2 }), [nested]);
      const tail = '{a},b}'.repeat(199);
      const rewriteHeavy = '{a},b}' + tail;
      assert.deepEqual(expand(rewriteHeavy, { maxRewrites: 0 }), [rewriteHeavy]);
      assert.deepEqual(expand(rewriteHeavy, { maxRewrites: 1 }), ['a}' + tail, 'b' + tail]);
    `], { encoding: 'utf8', timeout: 5000 });
    assert.equal(probe.error, undefined);
    assert.equal(probe.status, 0, probe.stdout + probe.stderr);
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
