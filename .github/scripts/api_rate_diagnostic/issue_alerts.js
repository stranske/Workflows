'use strict';

const {
  composeHighUsageIssueBody,
  composeHighUsageUpdateBody,
  composeRepeatedFailureIssueBody,
  composeRepeatedFailureUpdateBody,
  formatIssueTimestamp,
  runUrlFromEnv,
} = require('./compose_issue_body.js');

function retryCore() {
  return {
    info: console.log,
    warning: console.warn,
    debug: () => {},
  };
}

async function createOrUpdateHighUsageIssue({
  env = process.env,
  Octokit = require('@octokit/rest').Octokit,
  createTokenAwareRetry = require('../github-api-with-retry.js').createTokenAwareRetry,
} = {}) {
  const [owner, repo] = env.GITHUB_REPOSITORY.split('/');
  const runUrl = runUrlFromEnv(env);
  const now = formatIssueTimestamp();
  const github = new Octokit({ auth: env.GH_TOKEN || env.GITHUB_TOKEN });
  const { withRetry } = await createTokenAwareRetry({
    github,
    core: retryCore(),
    env,
    task: 'health-75-api-rate-diagnostic-high-usage',
    capabilities: ['issues:write'],
  });

  const issuesResp = await withRetry((client) =>
    client.rest.issues.listForRepo({
      owner,
      repo,
      labels: 'api-rate-limit',
      state: 'open',
      per_page: 1,
    }),
  );
  const existing = issuesResp?.data?.[0]?.number;
  if (!existing) {
    await withRetry((client) =>
      client.rest.issues.create({
        owner,
        repo,
        title: '⚠️ API Rate Limit Alert: High utilization',
        labels: ['api-rate-limit', 'automated'],
        body: composeHighUsageIssueBody({ now, runUrl }),
      }),
    );
    console.log('Created new alert issue');
    return { action: 'created' };
  }

  await withRetry((client) =>
    client.rest.issues.createComment({
      owner,
      repo,
      issue_number: existing,
      body: composeHighUsageUpdateBody({ now, runUrl }),
    }),
  );
  console.log(`Updated existing issue #${existing}`);
  return { action: 'updated', issue: existing };
}

async function createOrUpdateRepeatedFailureIssue({
  env = process.env,
  Octokit = require('@octokit/rest').Octokit,
  createTokenAwareRetry = require('../github-api-with-retry.js').createTokenAwareRetry,
} = {}) {
  const [owner, repo] = env.GITHUB_REPOSITORY.split('/');
  const runId = Number(env.GITHUB_RUN_ID);
  const runUrl = runUrlFromEnv(env);
  const github = new Octokit({ auth: env.GH_TOKEN || env.GITHUB_TOKEN });
  const { withRetry } = await createTokenAwareRetry({
    github,
    core: retryCore(),
    env,
    task: 'health-75-api-rate-diagnostic-alert',
    capabilities: ['actions:read', 'issues:write'],
  });

  // This job runs inside the run it would judge, so that run is still
  // in_progress and its conclusion is always empty: reading it meant the alert
  // could never fire (cohesion review round 2, A3). Judge the last two
  // COMPLETED runs instead, never this one. Two failures in a row are reported
  // by the run after the second one.
  const workflowResp = await withRetry((client) =>
    client.rest.actions.getWorkflow({
      owner,
      repo,
      workflow_id: 'health-75-api-rate-diagnostic.yml',
    }),
  );
  const workflowId = workflowResp?.data?.id;
  if (!workflowId) {
    console.log('Could not resolve workflow id; skipping repeat failure check.');
    return { action: 'skipped', reason: 'missing-workflow-id' };
  }

  const runsResp = await withRetry((client) =>
    client.rest.actions.listWorkflowRuns({
      owner,
      repo,
      workflow_id: workflowId,
      status: 'completed',
      per_page: 3,
    }),
  );
  const runs = (runsResp?.data?.workflow_runs || []).filter(
    (run) => Number(run?.id) !== runId && run?.status === 'completed',
  );
  const first = runs[0]?.conclusion || '';
  const second = runs[1]?.conclusion || '';
  console.log(
    `Last two completed runs: ${runs[0]?.id || 'none'}=${first || 'none'}, ` +
      `${runs[1]?.id || 'none'}=${second || 'none'}.`,
  );
  if (first !== 'failure' || second !== 'failure') {
    console.log(`No consecutive failures (latest: ${first}, previous: ${second}).`);
    return { action: 'skipped', reason: 'not-consecutive' };
  }

  const issueTitle = '⚠️ Health 75 API Rate Diagnostic failing repeatedly';
  const labels = ['workflow-failure', 'automated', 'api-rate-limit'];
  const now = formatIssueTimestamp();
  const issuesResp = await withRetry((client) =>
    client.rest.issues.listForRepo({
      owner,
      repo,
      // Both labels: another workflow's open workflow-failure issue is not ours.
      labels: 'workflow-failure,api-rate-limit',
      state: 'open',
      per_page: 1,
    }),
  );
  const existing = issuesResp?.data?.[0]?.number;
  if (!existing) {
    await withRetry((client) =>
      client.rest.issues.create({
        owner,
        repo,
        title: issueTitle,
        labels,
        body: composeRepeatedFailureIssueBody({ now, runUrl }),
      }),
    );
    console.log('Created failure alert issue.');
    return { action: 'created' };
  }

  await withRetry((client) =>
    client.rest.issues.createComment({
      owner,
      repo,
      issue_number: existing,
      body: composeRepeatedFailureUpdateBody({ runUrl }),
    }),
  );
  console.log(`Updated existing failure alert issue #${existing}.`);
  return { action: 'updated', issue: existing };
}

module.exports = {
  createOrUpdateHighUsageIssue,
  createOrUpdateRepeatedFailureIssue,
};
