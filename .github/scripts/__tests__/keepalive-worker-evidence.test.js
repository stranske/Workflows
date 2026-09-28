'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { classifyWorkerExecution, getWorkerExecutionEvidence } = require('../keepalive_worker_evidence');

const name = 'Keepalive next task (Codex) / Codex (keepalive)';

test('exact worker attempt distinguishes started, definitely absent, and unknown', () => {
  const job = (conclusion, steps) => ({ name, status: 'completed', conclusion, steps });
  assert.equal(classifyWorkerExecution([job('skipped')]), 'not-started');
  assert.equal(classifyWorkerExecution([job('failure', [
    { name: 'Run Codex', status: 'completed', conclusion: 'skipped' },
  ])]), 'not-started');
  assert.equal(classifyWorkerExecution([job('failure', [
    { name: 'Run Codex', status: 'completed', conclusion: 'failure' },
  ])]), 'started');
  assert.equal(classifyWorkerExecution([job('success', [
    { name: 'Run Codex', status: 'completed', conclusion: 'success' },
  ])]), 'started');
  assert.equal(classifyWorkerExecution([job('failure', [])]), 'unknown');
  assert.equal(classifyWorkerExecution([]), 'unknown');
  assert.equal(classifyWorkerExecution(null), 'unknown');
  assert.equal(classifyWorkerExecution([{ name, status: 'in_progress' }]), 'unknown');
});

test('new keepalive-capable registry agent is classified without a provider list', () => {
  const registry = { agents: {
    nova: { capabilities: { pr_keepalive: true } },
  } };
  const job = { name: 'Keepalive next task (Nova) / Nova (keepalive)',
    status: 'completed', conclusion: 'failure', steps: [
      { name: 'Run Nova', status: 'completed', conclusion: 'failure' },
    ] };
  assert.equal(classifyWorkerExecution([job], registry), 'started');
  job.steps[0].conclusion = 'skipped';
  assert.equal(classifyWorkerExecution([job], registry), 'not-started');
});

test('job API failure is unknown and the query is attempt-bound', async () => {
  const calls = [];
  const headSha = 'a'.repeat(40);
  const registryYaml = 'version: 1\ndefault_agent: codex\nagents:\n  codex:\n    capabilities:\n      pr_keepalive: true\n';
  const github = {
    rest: {
      actions: { listJobsForWorkflowRunAttempt: () => {} },
      repos: { getContent: async (args) => {
        calls.push(args);
        return { data: { type: 'file', encoding: 'base64',
          content: Buffer.from(registryYaml).toString('base64') } };
      } },
    },
    paginate: async (_endpoint, args) => { calls.push(args); return [{ name, status: 'completed', conclusion: 'skipped' }]; },
  };
  assert.equal(await getWorkerExecutionEvidence(github, 'stranske', 'Workflows', 123, 2, headSha), 'not-started');
  assert.deepEqual(calls[0], { owner: 'stranske', repo: 'Workflows',
    path: '.github/agents/registry.yml', ref: headSha });
  assert.deepEqual(calls[1], { owner: 'stranske', repo: 'Workflows', run_id: 123, attempt_number: 2, per_page: 100 });
  github.paginate = async () => { throw new Error('rate-limited'); };
  assert.equal(await getWorkerExecutionEvidence(github, 'stranske', 'Workflows', 123, 2, headSha), 'unknown');
  github.rest.repos.getContent = async () => { throw new Error('registry unavailable'); };
  assert.equal(await getWorkerExecutionEvidence(github, 'stranske', 'Workflows', 123, 2, headSha), 'unknown');
});

test('originating registry revision classifies a removed provider rather than refunding from current config', async () => {
  const headSha = 'b'.repeat(40);
  const registryYaml = 'version: 1\ndefault_agent: nova\nagents:\n  nova:\n    capabilities:\n      pr_keepalive: true\n';
  const github = {
    rest: {
      actions: { listJobsForWorkflowRunAttempt: () => {} },
      repos: { getContent: async ({ ref }) => {
        assert.equal(ref, headSha);
        return { data: { type: 'file', encoding: 'base64',
          content: Buffer.from(registryYaml).toString('base64') } };
      } },
    },
    paginate: async () => [
      { name: 'Keepalive next task (Codex)', status: 'completed', conclusion: 'skipped' },
      { name: 'Keepalive next task (Nova) / Nova (keepalive)', status: 'completed',
        conclusion: 'failure', steps: [{ name: 'Run Nova', status: 'completed', conclusion: 'failure' }] },
    ],
  };
  assert.equal(await getWorkerExecutionEvidence(github, 'stranske', 'Workflows', 124, 1, headSha), 'started');
});
