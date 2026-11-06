'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, readFileSync, rmSync, writeFileSync } = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { runTestDirectory } = require('./index.js');

test('directory entry point runs tests and propagates a failed assertion', (t) => {
  const previousContext = process.env.NODE_TEST_CONTEXT;
  process.env.NODE_TEST_CONTEXT = 'child-v8';
  t.after(() => {
    if (previousContext === undefined) delete process.env.NODE_TEST_CONTEXT;
    else process.env.NODE_TEST_CONTEXT = previousContext;
  });
  const directory = mkdtempSync(path.join(os.tmpdir(), 'workflow-test-directory-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const file = path.join(directory, 'example.test.js');
  const receipt = path.join(directory, 'executed.txt');
  // Helpers and fixture files are not standalone test files.
  writeFileSync(path.join(directory, 'helper.js'), "throw new Error('fixture was executed');\n");
  writeFileSync(file, `require('node:test')('example', () => {
    require('node:fs').writeFileSync(${JSON.stringify(receipt)}, 'executed');
  });\n`);
  assert.equal(runTestDirectory(directory), 0);
  assert.equal(readFileSync(receipt, 'utf8'), 'executed');

  writeFileSync(file, "require('node:test')('example', () => { require('node:assert/strict').fail('expected probe failure'); });\n");
  assert.equal(runTestDirectory(directory), 1);
});

test('directory entry point rejects an empty suite instead of reporting success', (t) => {
  const directory = mkdtempSync(path.join(os.tmpdir(), 'workflow-empty-test-directory-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  assert.throws(() => runTestDirectory(directory), /No JavaScript test files found/);
});
