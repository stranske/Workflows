'use strict';

const fs = require('fs');

const SAFE_ENV_KEYS = [
  'GITHUB_REPOSITORY',
  'GITHUB_RUN_ID',
  'GITHUB_RUN_ATTEMPT',
  'GITHUB_RUN_NUMBER',
  'GITHUB_WORKFLOW',
  'GITHUB_JOB',
  'GITHUB_ACTOR',
  'GITHUB_SHA',
  'GITHUB_REF',
  'GITHUB_EVENT_NAME',
  'GITHUB_SERVER_URL',
];

const ERROR_ENV_KEYS = [
  'ERROR_CATEGORY',
  'ERROR_TYPE',
  'ERROR_MESSAGE',
  'ERROR_RECOVERY',
  'ERROR_SUMMARY',
  'ERROR_EXIT_CODE',
  'ERROR_STEP',
  'ERROR_OPERATION',
];

const REDACT_KEYS_PATTERN = /(secret|token|credential)/i;

function pickEnv(keys, env) {
  return keys.reduce((acc, key) => {
    const value = env[key];
    if (value !== undefined && value !== null && value !== '') {
      acc[key] = String(value);
    }
    return acc;
  }, {});
}

function pruneEmpty(value) {
  if (Array.isArray(value)) {
    const pruned = value.map(pruneEmpty).filter((item) => item !== undefined);
    return pruned.length ? pruned : undefined;
  }
  if (value && typeof value === 'object') {
    const result = {};
    for (const [key, entry] of Object.entries(value)) {
      const prunedEntry = pruneEmpty(entry);
      if (prunedEntry !== undefined) {
        result[key] = prunedEntry;
      }
    }
    return Object.keys(result).length ? result : undefined;
  }
  if (value === undefined || value === null || value === '') {
    return undefined;
  }
  return value;
}

function sanitizeObject(value) {
  if (Array.isArray(value)) {
    return value.map(sanitizeObject);
  }
  if (value && typeof value === 'object') {
    const sanitized = {};
    for (const [key, entry] of Object.entries(value)) {
      if (REDACT_KEYS_PATTERN.test(key)) {
        continue;
      }
      sanitized[key] = sanitizeObject(entry);
    }
    return sanitized;
  }
  return value;
}

function parseExtraJson({ json, file }) {
  if (json) {
    return JSON.parse(json);
  }
  if (file) {
    const raw = fs.readFileSync(file, 'utf8');
    return JSON.parse(raw);
  }
  return null;
}

function collectErrorDiagnostics({ env = process.env, extra = null } = {}) {
  const run = pickEnv(SAFE_ENV_KEYS, env);
  const error = pickEnv(ERROR_ENV_KEYS, env);

  const diagnostics = {
    generated_at: new Date().toISOString(),
    run,
    error,
  };

  const sanitizedExtra = extra ? sanitizeObject(extra) : null;
  if (sanitizedExtra && Object.keys(sanitizedExtra).length > 0) {
    diagnostics.extra = sanitizedExtra;
  }

  return pruneEmpty(diagnostics) || {};
}

function writeErrorDiagnostics({ outputPath, env = process.env, extra = null }) {
  const diagnostics = collectErrorDiagnostics({ env, extra });
  fs.writeFileSync(outputPath, `${JSON.stringify(diagnostics, null, 2)}\n`, 'utf8');
  return diagnostics;
}

function parseArgs(args) {
  const result = {};
  for (let i = 0; i < args.length; i += 1) {
    const token = args[i];
    if (token === '--output') {
      result.output = args[i + 1];
      i += 1;
    } else if (token === '--json') {
      result.json = args[i + 1];
      i += 1;
    } else if (token === '--input') {
      result.input = args[i + 1];
      i += 1;
    }
  }
  return result;
}

if (require.main === module) {
  const args = parseArgs(process.argv.slice(2));
  const outputPath = args.output || 'error_diagnostics.json';
  let extra = null;
  if (args.json || args.input) {
    try {
      extra = parseExtraJson({ json: args.json, file: args.input });
    } catch (error) {
      console.error(`Failed to parse diagnostics input: ${error.message}`);
      process.exitCode = 1;
    }
  }

  if (process.exitCode !== 1) {
    writeErrorDiagnostics({ outputPath, extra });
  }
}

module.exports = {
  collectErrorDiagnostics,
  parseExtraJson,
  sanitizeObject,
  writeErrorDiagnostics,
};
