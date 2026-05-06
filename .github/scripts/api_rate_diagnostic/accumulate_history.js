'use strict';

const fs = require('node:fs');

const RATE_ENV_KEYS = [
  ['github_token', 'GITHUB_TOKEN_RATE'],
  ['owner_pr_pat', 'PAT_RATE'],
  ['service_bot_pat', 'SERVICE_BOT_RATE'],
  ['workflows_app', 'APP_RATE'],
  ['keepalive_app', 'KEEPALIVE_APP_RATE'],
  ['gh_app', 'GH_APP_RATE'],
];

function safeJson(input, fallback = {}) {
  if (!input) {
    return fallback;
  }
  try {
    return JSON.parse(input);
  } catch (_error) {
    return fallback;
  }
}

function formatTimestamp(date = new Date()) {
  return date.toISOString().replace(/\.\d+Z$/, 'Z');
}

function buildSummaryFromRates(env = process.env, timestamp = formatTimestamp()) {
  const tokens = Object.fromEntries(
    RATE_ENV_KEYS.map(([tokenKey, envKey]) => [tokenKey, safeJson(env[envKey], {})]),
  );
  const tokenValues = Object.values(tokens);
  return {
    timestamp,
    tokens,
    total_pools: tokenValues.filter((token) => token && token.source).length,
    total_remaining: tokenValues.reduce((total, token) => total + (token?.core?.remaining || 0), 0),
    total_limit: tokenValues.reduce((total, token) => total + (token?.core?.limit || 0), 0),
  };
}

function logAggregationInputs(env = process.env, parsed = {}) {
  const serviceRate = env.SERVICE_BOT_RATE || '';
  const keepaliveRate = env.KEEPALIVE_APP_RATE || '';
  const ghRate = env.GH_APP_RATE || '';
  console.log('::group::Rate data aggregation');
  console.log('Raw env var lengths:');
  console.log(
    `  gt=${(env.GITHUB_TOKEN_RATE || '').length}, pat=${(env.PAT_RATE || '').length}, svc=${serviceRate.length}, app=${(env.APP_RATE || '').length}`,
  );
  console.log(`  ka=${keepaliveRate.length}, gh=${ghRate.length}`);
  console.log(`GITHUB_TOKEN_RATE first 100: ${(env.GITHUB_TOKEN_RATE || '').slice(0, 100)}`);
  console.log(`PAT_RATE first 100: ${(env.PAT_RATE || '').slice(0, 100)}`);
  console.log(`SERVICE_BOT_RATE first 100: ${(env.SERVICE_BOT_RATE || '').slice(0, 100)}`);
  console.log(`APP_RATE first 100: ${(env.APP_RATE || '').slice(0, 100)}`);
  console.log(`KEEPALIVE_APP_RATE first 100: ${(env.KEEPALIVE_APP_RATE || '').slice(0, 100)}`);
  console.log(`GH_APP_RATE first 100: ${(env.GH_APP_RATE || '').slice(0, 100)}`);
  console.log('Parsed JSON lengths:');
  console.log(
    `  gt=${JSON.stringify(parsed.github_token || {}).length}, pat=${JSON.stringify(parsed.owner_pr_pat || {}).length}, svc=${JSON.stringify(parsed.service_bot_pat || {}).length}, app=${JSON.stringify(parsed.workflows_app || {}).length}`,
  );
  console.log(
    `  ka=${JSON.stringify(parsed.keepalive_app || {}).length}, gh=${JSON.stringify(parsed.gh_app || {}).length}`,
  );
  console.log(`gt_json: ${JSON.stringify(parsed.github_token || {})}`);
  console.log(`pat_json: ${JSON.stringify(parsed.owner_pr_pat || {})}`);
  console.log(`svc_json: ${JSON.stringify(parsed.service_bot_pat || {})}`);
  console.log(`app_json: ${JSON.stringify(parsed.workflows_app || {})}`);
  console.log(`ka_json: ${JSON.stringify(parsed.keepalive_app || {})}`);
  console.log(`gh_json: ${JSON.stringify(parsed.gh_app || {})}`);
}

function appendOutput(name, value, outputPath = process.env.GITHUB_OUTPUT) {
  if (!outputPath) {
    return;
  }
  fs.appendFileSync(outputPath, `${name}=${value}\n`);
}

function runAggregateStep({ env = process.env, outputPath = process.env.GITHUB_OUTPUT } = {}) {
  const summary = buildSummaryFromRates(env);
  logAggregationInputs(env, summary.tokens);
  const json = JSON.stringify(summary);
  console.log(`Summary: ${json}`);
  console.log('::endgroup::');
  appendOutput('summary', json, outputPath);
  return summary;
}

module.exports = {
  RATE_ENV_KEYS,
  buildSummaryFromRates,
  formatTimestamp,
  runAggregateStep,
  safeJson,
};
