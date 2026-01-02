#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const { evaluateKeepaliveLoop } = require('../../../../.github/scripts/keepalive_loop.js');

function loadScenario(scenarioPath) {
  const resolved = path.resolve(process.cwd(), scenarioPath);
  return JSON.parse(fs.readFileSync(resolved, 'utf8'));
}

function buildMockGithub({ pr, gateConclusion, runId, jobs, logs }) {
  return {
    rest: {
      pulls: {
        get: async () => ({ data: pr }),
      },
      actions: {
        listWorkflowRuns: async () => ({
          data: {
            workflow_runs: [
              {
                conclusion: gateConclusion,
                id: runId,
                head_sha: pr.head.sha,
              },
            ],
          },
        }),
        listJobsForWorkflowRun: async () => ({
          data: {
            jobs,
          },
        }),
        downloadJobLogsForWorkflowRun: async () => ({
          data: logs,
        }),
      },
    },
  };
}

async function main() {
  const scenarioPath = process.argv[2];
  if (!scenarioPath) {
    console.error('Usage: node harness.js <scenario.json>');
    process.exit(2);
  }

  let scenario;
  try {
    scenario = loadScenario(scenarioPath);
  } catch (error) {
    console.error('Failed to load scenario:', error.message);
    process.exit(2);
  }

  const prNumber = Number(scenario.pr_number) || 101;
  const pr = {
    number: prNumber,
    head: {
      ref: scenario.pr_ref || 'feature/keepalive-rate-limit',
      sha: scenario.pr_sha || 'abc123def456',
    },
    labels: (scenario.labels || ['agent:codex']).map((label) => ({ name: label })),
    body: scenario.body || [
      '### Scope',
      'Keepalive continues until tasks are done.',
      '',
      '### Tasks',
      '- [ ] Check rate limits',
      '',
      '### Acceptance Criteria',
      '- [ ] Rate limit handling verified',
    ].join('\n'),
  };

  const runId = Number(scenario.run_id) || 404;
  const gateConclusion = scenario.gate_conclusion || 'cancelled';
  const jobs = Array.isArray(scenario.jobs)
    ? scenario.jobs
    : [{ id: 9001 }];
  const logs = scenario.logs || 'Rate limit exceeded while fetching workflow logs.';

  const github = buildMockGithub({ pr, gateConclusion, runId, jobs, logs });
  const context = {
    repo: { owner: 'octo-org', repo: 'octo-repo' },
    eventName: 'pull_request',
    payload: { pull_request: { number: prNumber } },
  };
  const core = {
    info: () => {},
    warning: () => {},
  };

  const result = await evaluateKeepaliveLoop({ github, context, core });
  process.stdout.write(JSON.stringify(result));
}

main();
