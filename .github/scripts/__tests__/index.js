'use strict';

const { spawnSync } = require('node:child_process');
const { readdirSync } = require('node:fs');
const path = require('node:path');

// Node 24 resolves an explicit directory argument as a module. Keep the
// documented directory command equivalent to running the test-file glob,
// including one isolated process per file.
function runTestDirectory(directory = __dirname) {
  const files = readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.test.js'))
    .map((entry) => path.join(directory, entry.name))
    .sort();
  if (files.length === 0) {
    throw new Error(`No JavaScript test files found in ${directory}`);
  }

  // The entry point itself runs in a test worker with `node --test <directory>`.
  // The child runner needs its own context to discover and execute its files.
  const env = { ...process.env };
  delete env.NODE_TEST_CONTEXT;
  const result = spawnSync(process.execPath, ['--test', ...files], { stdio: 'inherit', env });
  if (result.error) throw result.error;
  return result.status ?? 1;
}

if (require.main === module) {
  process.exitCode = runTestDirectory();
}

module.exports = { runTestDirectory };
