'use strict';

const { execFileSync } = require('node:child_process');
const { appendFileSync } = require('node:fs');

const GUIDES = new Set([
  '.github/workflows/README.md',
  'docs/ci/WORKFLOW_SYSTEM.md',
]);
const SHA = /^[a-f0-9]{40}$/;
const REGULAR_FILE_EDIT = /^:100644 100644 [a-f0-9]{40} [a-f0-9]{40} M$/;

function isGuideOnlyPush(env) {
  const before = env.SELFTEST_BEFORE || '';
  const after = env.GITHUB_SHA || '';
  if (
    env.GITHUB_EVENT_NAME !== 'push' ||
    env.GITHUB_REF !== 'refs/heads/main' ||
    env.SELFTEST_FORCED !== 'false' ||
    !SHA.test(before) ||
    !SHA.test(after) ||
    before === after
  ) {
    return false;
  }

  const options = { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] };
  try {
    execFileSync('git', ['merge-base', '--is-ancestor', before, after], options);
    const diff = execFileSync(
      'git',
      ['diff', '--raw', '--no-abbrev', '--no-renames', '-z', before, after, '--'],
      options,
    );
    const [firstEdit, firstPath, secondEdit, secondPath, ...tail] = diff.split('\0');
    return tail.length === 1 && tail[0] === '' &&
      REGULAR_FILE_EDIT.test(firstEdit) && REGULAR_FILE_EDIT.test(secondEdit) &&
      GUIDES.has(firstPath) && GUIDES.has(secondPath) && firstPath !== secondPath;
  } catch {
    // An unavailable comparison keeps the canonical matrix.
    return false;
  }
}

const result = `guide-only=${isGuideOnlyPush(process.env)}\n`;
if (process.env.GITHUB_OUTPUT) {
  appendFileSync(process.env.GITHUB_OUTPUT, result);
} else {
  process.stdout.write(result);
}
