'use strict';

const { buildIgnoredPathMatchers, filterPaths: filterPathList } = require('./pr-context-graphql');

function filterPaths(paths, env = process.env) {
  const matchers = buildIgnoredPathMatchers(env);
  return filterPathList(paths, matchers);
}

function readPathsFromEnv() {
  if (process.env.PATHS_JSON) {
    const parsed = JSON.parse(process.env.PATHS_JSON);
    if (Array.isArray(parsed)) {
      return parsed;
    }
  }
  if (process.env.PATHS_CSV) {
    return process.env.PATHS_CSV.split(',').map((entry) => entry.trim()).filter(Boolean);
  }
  return null;
}

if (require.main === module) {
  const cliPaths = process.argv.slice(2);
  const envPaths = readPathsFromEnv();
  const paths = cliPaths.length ? cliPaths : envPaths;

  if (!paths || !paths.length) {
    console.error('Usage: node connector-exclusion-smoke.js <path...>');
    console.error('Or set PATHS_JSON (JSON array) or PATHS_CSV (comma-separated).');
    process.exit(2);
  }

  const result = filterPaths(paths);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

module.exports = {
  filterPaths
};
