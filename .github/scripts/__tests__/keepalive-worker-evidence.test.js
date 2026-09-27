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

test('job API failure is unknown and the query is attempt-bound', async () => {
  const calls = [];
  const github = {
    rest: { actions: { listJobsForWorkflowRunAttempt: () => {} } },
    paginate: async (_endpoint, args) => { calls.push(args); return [{ name, status: 'completed', conclusion: 'skipped' }]; },
  };
  assert.equal(await getWorkerExecutionEvidence(github, 'stranske', 'Workflows', 123, 2), 'not-started');
  assert.deepEqual(calls[0], { owner: 'stranske', repo: 'Workflows', run_id: 123, attempt_number: 2, per_page: 100 });
  github.paginate = async () => { throw new Error('rate-limited'); };
  assert.equal(await getWorkerExecutionEvidence(github, 'stranske', 'Workflows', 123, 2), 'unknown');
});
