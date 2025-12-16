'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { resolveOrchestratorParams } = require('../agents_orchestrator_resolve');

function createSummary() {
  return {
    entries: [],
    addHeading(text) {
      this.entries.push({ type: 'heading', text });
      return this;
    },
    addTable(rows) {
      this.entries.push({ type: 'table', rows });
      return this;
    },
    addRaw(text) {
      this.entries.push({ type: 'raw', text });
      return this;
    },
    addEOL() {
      this.entries.push({ type: 'eol' });
      return this;
    },
    async write() {
      this.entries.push({ type: 'write' });
    }
  };
}

function createCoreHarness() {
  const outputs = {};
  const info = [];
  const warnings = [];
  const summary = createSummary();
  const core = {
    setOutput(key, value) {
      outputs[key] = value;
    },
    info(message) {
      info.push(message);
    },
    warning(message) {
      warnings.push(message);
    },
    summary
  };
  return { outputs, info, warnings, summary, core };
}

test('resolveOrchestratorParams merges configuration and summaries outputs', async () => {
  const { outputs, info, warnings, summary, core } = createCoreHarness();

  const labelError = new Error('not found');
  labelError.status = 404;

  const github = {
    rest: {
      issues: {
        async getLabel() {
          throw labelError;
        }
      }
    }
  };

  const env = {
    PARAMS_JSON: JSON.stringify({
      readiness_agents: ['copilot', 'codex', 'helper'],
      worker: { max_parallel: 3 },
      conveyor: { max_merges: 2 }
    }),
    WORKFLOW_DRY_RUN: 'true',
    WORKFLOW_KEEPALIVE_ENABLED: 'true',
    WORKFLOW_OPTIONS_JSON: JSON.stringify({
      belt: {
        dispatcher: { force_issue: '42' },
        worker: { max_parallel: 3 },
        conveyor: { max_merges: 2 }
      }
    })
  };

  await resolveOrchestratorParams({
    github,
    context: { repo: { owner: 'octo', repo: 'demo' } },
    core,
    env
  });

  assert.equal(outputs.readiness_agents, 'copilot,codex,helper');
  assert.equal(outputs.dispatcher_force_issue, '42');
  assert.equal(outputs.worker_max_parallel, '3');
  assert.equal(outputs.dry_run, 'true');
  assert.equal(outputs.enable_keepalive, 'true');
  assert.ok(summary.entries.length > 0);
  assert.ok(info.some((message) => message.includes('keepalive')));
  assert.equal(warnings.length, 0);
});

test('resolveOrchestratorParams maps workflow_run payload to open pull request', async () => {
  const { outputs, info, warnings, core } = createCoreHarness();

  const labelError = new Error('not found');
  labelError.status = 404;

  const github = {
    rest: {
      issues: {
        async getLabel() {
          throw labelError;
        }
      },
      repos: {},
      pulls: {
        async get({ pull_number }) {
          return { data: { state: 'open', number: pull_number } };
        }
      }
    },
    async paginate() {
      return [];
    }
  };

  const context = {
    eventName: 'workflow_run',
    repo: { owner: 'octo', repo: 'demo' },
    payload: {
      workflow_run: {
        pull_requests: [
          { number: 3372, head: { sha: 'abc123', ref: 'codex/issue-3364' } }
        ],
        head_sha: 'abc123',
        head_branch: 'codex/issue-3364',
        head_repository: { owner: { login: 'octo' } },
        display_title: 'chore(codex): bootstrap PR for issue #3364'
      }
    }
  };

  await resolveOrchestratorParams({ github, context, core, env: {} });

  assert.equal(outputs.keepalive_pr, '3372');
  assert.ok(info.some((message) => message.includes('#3372')));
  assert.equal(warnings.length, 0);
});

test('resolveOrchestratorParams prefers open branch PR over closed commit match', async () => {
  const { outputs, warnings, core } = createCoreHarness();

  const labelError = new Error('not found');
  labelError.status = 404;

  const closedPr = {
    number: 3375,
    state: 'closed',
    head: { sha: 'deadbeef' },
    updated_at: '2025-11-07T19:24:02Z'
  };

  const openPr = {
    number: 3372,
    state: 'open',
    head: { ref: 'codex/issue-3364', sha: 'facefeed' },
    updated_at: '2025-11-07T19:41:55Z'
  };

  const pullGetCalls = [];

  const github = {
    rest: {
      issues: {
        async getLabel() {
          throw labelError;
        }
      },
      repos: {
        listPullRequestsAssociatedWithCommit: function listPullRequestsAssociatedWithCommit() {}
      },
      pulls: {
        list: function list() {},
        async get({ pull_number }) {
          pullGetCalls.push(pull_number);
          return { data: { state: pull_number === 3372 ? 'open' : 'closed' } };
        }
      }
    },
    async paginate(fn) {
      if (fn === this.rest.repos.listPullRequestsAssociatedWithCommit) {
        return [closedPr];
      }
      if (fn === this.rest.pulls.list) {
        return [openPr];
      }
      return [];
    }
  };

  const context = {
    eventName: 'workflow_run',
    repo: { owner: 'octo', repo: 'demo' },
    payload: {
      workflow_run: {
        pull_requests: [],
        head_sha: 'deadbeef',
        head_branch: 'codex/issue-3364',
        head_repository: { owner: { login: 'octo' } },
        display_title: 'Codex keepalive'
      }
    }
  };

  await resolveOrchestratorParams({ github, context, core, env: {} });

  assert.equal(outputs.keepalive_pr, '3372');
  assert.deepEqual(pullGetCalls, [3372]);
  assert.equal(warnings.length, 0);
});

test('resolveOrchestratorParams clears keepalive PR when only closed candidates exist', async () => {
  const { outputs, warnings, core } = createCoreHarness();

  const labelError = new Error('not found');
  labelError.status = 404;

  const closedPr = {
    number: 3375,
    state: 'closed',
    head: { sha: 'deadbeef' },
    updated_at: '2025-11-07T19:24:02Z'
  };

  const github = {
    rest: {
      issues: {
        async getLabel() {
          throw labelError;
        }
      },
      repos: {
        listPullRequestsAssociatedWithCommit: function listPullRequestsAssociatedWithCommit() {}
      },
      pulls: {
        list: function list() {},
        async get() {
          return { data: { state: 'closed' } };
        }
      }
    },
    async paginate(fn) {
      if (fn === this.rest.repos.listPullRequestsAssociatedWithCommit) {
        return [closedPr];
      }
      if (fn === this.rest.pulls.list) {
        return [];
      }
      return [];
    }
  };

  const context = {
    eventName: 'workflow_run',
    repo: { owner: 'octo', repo: 'demo' },
    payload: {
      workflow_run: {
        pull_requests: [],
        head_sha: 'deadbeef',
        head_branch: 'codex/issue-3364',
        head_repository: { owner: { login: 'octo' } },
        display_title: 'Codex keepalive'
      }
    }
  };

  await resolveOrchestratorParams({ github, context, core, env: {} });

  assert.equal(outputs.keepalive_pr, '');
  assert.ok(warnings.some((message) => message.includes('did not include a pull request number')));
});
