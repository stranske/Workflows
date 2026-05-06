'use strict';

const fs = require('node:fs');

function formatDate(date) {
  return date.toISOString().slice(0, 10);
}

function parseIsoDate(value) {
  if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value || '')) {
    return null;
  }
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) || formatDate(date) !== value ? null : date;
}

function addDays(date, days) {
  const next = new Date(date.getTime());
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function addMonths(date, months) {
  const next = new Date(date.getTime());
  next.setUTCMonth(next.getUTCMonth() + months);
  return next;
}

function resolveDateRange({ startInput = '1w', endInput = 'now', now = new Date() } = {}) {
  const endDate = endInput === 'now' || !endInput ? formatDate(now) : endInput;
  const end = parseIsoDate(endDate);
  if (!end) {
    throw new Error(`Invalid END_DATE format: '${endDate}'. Expected YYYY-MM-DD or 'now'.`);
  }

  let startDate;
  if (/^[0-9]+d$/.test(startInput)) {
    startDate = formatDate(addDays(end, -Number(startInput.slice(0, -1))));
  } else if (/^[0-9]+w$/.test(startInput)) {
    startDate = formatDate(addDays(end, -Number(startInput.slice(0, -1)) * 7));
  } else if (/^[0-9]+m$/.test(startInput)) {
    startDate = formatDate(addMonths(end, -Number(startInput.slice(0, -1))));
  } else {
    startDate = startInput;
  }

  const start = parseIsoDate(startDate);
  if (!start) {
    throw new Error(
      `Invalid START_DATE format: '${startDate}'. Expected YYYY-MM-DD or a supported relative value (e.g., 7d, 1w, 1m).`,
    );
  }
  if (start.getTime() > end.getTime()) {
    throw new Error(`START_DATE ('${startDate}') must not be after END_DATE ('${endDate}').`);
  }
  return { startDate, endDate };
}

function appendOutput(name, value, outputPath = process.env.GITHUB_OUTPUT) {
  if (!outputPath) {
    return;
  }
  fs.appendFileSync(outputPath, `${name}=${value}\n`);
}

function runParseDateRangeStep({
  startInput = process.env.START_INPUT,
  endInput = process.env.END_INPUT,
  outputPath = process.env.GITHUB_OUTPUT,
  exitOnError = true,
} = {}) {
  console.log('Parsing date range:');
  console.log(`- start='${startInput}'`);
  console.log(`- end='${endInput}'`);
  try {
    const range = resolveDateRange({ startInput, endInput });
    console.log(`Resolved date range: ${range.startDate} to ${range.endDate}`);
    appendOutput('start_date', range.startDate, outputPath);
    appendOutput('end_date', range.endDate, outputPath);
    return range;
  } catch (error) {
    console.log(`::error::${error.message}`);
    if (exitOnError) {
      process.exit(1);
    }
    process.exitCode = 1;
    throw error;
  }
}

async function fetchWorkflowId(token, {
  env = process.env,
  Octokit = require('@octokit/rest').Octokit,
  createTokenAwareRetry = require('../github-api-with-retry.js').createTokenAwareRetry,
} = {}) {
  const [owner, repo] = env.GITHUB_REPOSITORY.split('/');
  const core = { info: () => {}, warning: console.warn, debug: () => {} };
  const github = new Octokit({ auth: token });
  const { withRetry } = await createTokenAwareRetry({
    github,
    core,
    env,
    task: 'health-75-api-rate-diagnostic-history',
    capabilities: ['actions:read'],
  });
  const retryContext = {
    github,
    core,
    env,
    task: 'health-75-api-rate-diagnostic-history',
  };
  const response = await withRetry(
    () =>
      github.rest.actions.getWorkflow({
        owner,
        repo,
        workflow_id: 'health-75-api-rate-diagnostic.yml',
      }),
    retryContext,
  );
  return response?.data?.id || null;
}

async function resolveWorkflowIdWithFallback({
  primaryToken,
  fallbackToken,
  fetcher = fetchWorkflowId,
} = {}) {
  let workflowId = null;
  let tokenUsed = 'primary';
  try {
    if (primaryToken) {
      workflowId = await fetcher(primaryToken);
    }
  } catch (_error) {
    workflowId = null;
  }
  if (!workflowId && fallbackToken) {
    tokenUsed = 'fallback';
    workflowId = await fetcher(fallbackToken);
  }
  return { workflowId, tokenUsed };
}

async function fetchSuccessfulRuns({
  token,
  workflowId,
  startDate,
  env = process.env,
  Octokit = require('@octokit/rest').Octokit,
  createTokenAwareRetry = require('../github-api-with-retry.js').createTokenAwareRetry,
} = {}) {
  const [owner, repo] = env.GITHUB_REPOSITORY.split('/');
  const core = { info: () => {}, warning: console.warn, debug: () => {} };
  const github = new Octokit({ auth: token });
  const { withRetry } = await createTokenAwareRetry({
    github,
    core,
    env,
    task: 'health-75-api-rate-diagnostic-history-runs',
    capabilities: ['actions:read'],
  });
  const retryContext = {
    github,
    core,
    env,
    task: 'health-75-api-rate-diagnostic-history-runs',
  };
  const runs = await withRetry(
    () =>
      github.paginate(github.rest.actions.listWorkflowRuns, {
        owner,
        repo,
        workflow_id: workflowId,
        per_page: 100,
        status: 'completed',
        created: `>=${startDate}`,
      }),
    retryContext,
  );
  return (runs || [])
    .filter((run) => run.conclusion === 'success')
    .map((run) => ({
      id: run.id,
      created_at: run.created_at,
      run_number: run.run_number,
    }));
}

function filterRunsToEndDate(runs, endDate) {
  const endBound = String(endDate).includes('T') ? endDate : `${endDate}T23:59:59Z`;
  return runs.filter((run) => run.created_at <= endBound);
}

async function runFetchHistoricalRunsStep({
  env = process.env,
  outputPath = process.env.GITHUB_OUTPUT,
  runsPath = '/tmp/runs.json',
  workflowIdFetcher = fetchWorkflowId,
  runsFetcher = fetchSuccessfulRuns,
} = {}) {
  console.log(`Fetching Health 75 workflow runs from ${env.START_DATE} to ${env.END_DATE}`);
  let primaryToken = env.APP_GH_TOKEN || env.PRIMARY_GH_TOKEN || env.FALLBACK_GH_TOKEN;
  const { workflowId, tokenUsed } = await resolveWorkflowIdWithFallback({
    primaryToken,
    fallbackToken: env.FALLBACK_GH_TOKEN,
    fetcher: workflowIdFetcher,
  });
  if (tokenUsed === 'fallback') {
    primaryToken = env.FALLBACK_GH_TOKEN;
  }
  if (!workflowId) {
    console.log('::error::Could not find Health 75 workflow');
    throw new Error('Could not find Health 75 workflow');
  }
  console.log(`Workflow ID: ${workflowId}`);

  const runs = filterRunsToEndDate(
    await runsFetcher({
      token: primaryToken,
      workflowId,
      startDate: env.START_DATE,
      env,
    }),
    env.END_DATE,
  );
  console.log(`Found ${runs.length} successful runs in date range`);
  fs.writeFileSync(runsPath, JSON.stringify(runs));
  appendOutput('run_count', String(runs.length), outputPath);
  return runs;
}

function limitRunsForDisplay({ runsPath = '/tmp/runs.json', outputPath = process.env.GITHUB_OUTPUT, maxRuns = 50 } = {}) {
  const runs = JSON.parse(fs.readFileSync(runsPath, 'utf8'));
  console.log(`Found ${runs.length} successful runs in date range`);
  const limited = runs.length > maxRuns ? runs.slice(0, maxRuns) : runs;
  if (runs.length > maxRuns) {
    console.log(`Limiting display to ${maxRuns} most recent runs`);
    fs.writeFileSync(runsPath, JSON.stringify(limited));
  }
  appendOutput('processed_count', String(limited.length), outputPath);
  return limited;
}

module.exports = {
  addDays,
  addMonths,
  fetchSuccessfulRuns,
  fetchWorkflowId,
  filterRunsToEndDate,
  formatDate,
  limitRunsForDisplay,
  parseIsoDate,
  resolveDateRange,
  resolveWorkflowIdWithFallback,
  runFetchHistoricalRunsStep,
  runParseDateRangeStep,
};
