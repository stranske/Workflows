'use strict';

const fs = require('node:fs');

function parseRegisteredRepos(input = '') {
  return input
    .split(/\r?\n/)
    .map((repo) => repo.trim())
    .filter(Boolean);
}

function summarizeRuns(repo, runsData = {}) {
  const workflowRuns = Array.isArray(runsData.workflow_runs) ? runsData.workflow_runs : [];
  const counts = new Map();
  for (const run of workflowRuns) {
    counts.set(run.name, (counts.get(run.name) || 0) + 1);
  }
  return {
    repo,
    runs_last_hour: Number(runsData.total_count) || 0,
    in_progress: workflowRuns.filter((run) => run.status === 'in_progress').length,
    queued: workflowRuns.filter((run) => run.status === 'queued').length,
    completed: workflowRuns.filter((run) => run.status === 'completed').length,
    top_workflows: [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5),
  };
}

function appendOutput(name, value, outputPath = process.env.GITHUB_OUTPUT) {
  if (!outputPath) {
    return;
  }
  fs.appendFileSync(outputPath, `${name}=${value}\n`);
}

function oneHourAgoIso(now = new Date()) {
  return new Date(now.getTime() - 60 * 60 * 1000).toISOString().replace(/\.\d+Z$/, 'Z');
}

async function fetchRunsForRepo({
  repoSlug,
  since,
  token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN,
  Octokit = require('@octokit/rest').Octokit,
  createTokenAwareRetry = require('../github-api-with-retry.js').createTokenAwareRetry,
  env = process.env,
} = {}) {
  const [owner, repo] = repoSlug.split('/');
  const core = { info: () => {}, warning: console.warn, debug: () => {} };
  const github = new Octokit({ auth: token });
  const { withRetry } = await createTokenAwareRetry({
    github,
    core,
    env,
    task: 'health-75-api-rate-diagnostic-consumer-activity',
    capabilities: ['actions:read'],
  });
  const response = await withRetry((client) =>
    client.rest.actions.listWorkflowRunsForRepo({
      owner,
      repo,
      per_page: 100,
      created: `>=${since}`,
    }),
  );
  return response.data || { workflow_runs: [] };
}

async function collectConsumerActivity({
  env = process.env,
  fetcher = fetchRunsForRepo,
  now = new Date(),
} = {}) {
  if (env.RUN_CONSUMER_CHECKS !== 'true' || !env.GH_TOKEN) {
    console.log('::notice::Consumer repo diagnostics disabled for this run.');
    return [];
  }

  const repos = parseRegisteredRepos(env.REGISTERED_CONSUMER_REPOS || '');
  if (repos.length === 0) {
    console.log('::notice::No registered consumer repos resolved; returning empty payload.');
    return [];
  }

  console.log('::group::Consumer Repo Activity');
  const since = oneHourAgoIso(now);
  const activity = [];
  for (const repo of repos) {
    console.log(`Checking ${repo}...`);
    let runsData;
    try {
      runsData = await fetcher({ repoSlug: repo, since, env });
    } catch (_error) {
      runsData = { workflow_runs: [] };
    }
    const summary = summarizeRuns(repo, runsData);
    activity.push(summary);
    console.log(
      `  Runs (last hour): ${summary.runs_last_hour} (in_progress: ${summary.in_progress}, queued: ${summary.queued})`,
    );
  }
  console.log('::endgroup::');
  return activity;
}

async function runConsumerActivityStep({
  env = process.env,
  outputPath = process.env.GITHUB_OUTPUT,
  fetcher = fetchRunsForRepo,
} = {}) {
  const activity = await collectConsumerActivity({ env, fetcher });
  appendOutput('activity_json', JSON.stringify(activity), outputPath);
  return activity;
}

module.exports = {
  collectConsumerActivity,
  fetchRunsForRepo,
  oneHourAgoIso,
  parseRegisteredRepos,
  runConsumerActivityStep,
  summarizeRuns,
};
