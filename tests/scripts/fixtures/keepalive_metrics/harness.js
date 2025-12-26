'use strict';

const path = require('path');

const keepaliveLoopPath = path.resolve(__dirname, '../../../../.github/scripts/keepalive_loop.js');
const keepaliveStatePath = path.resolve(__dirname, '../../../../.github/scripts/keepalive_state.js');
const { updateKeepaliveLoopSummary } = require(keepaliveLoopPath);
const { formatStateComment } = require(keepaliveStatePath);

const outputs = {};
const core = {
  info() {},
  setOutput(key, value) {
    outputs[key] = value;
  },
};

const stateComment = {
  id: 200,
  body: formatStateComment({
    trace: 'trace-metrics',
    iteration: 1,
    max_iterations: 5,
  }),
  html_url: 'https://example.test/200',
};

const github = {
  rest: {
    issues: {
      async listComments() {
        return { data: [stateComment] };
      },
      async updateComment() {
        return { data: { id: stateComment.id } };
      },
      async createComment() {
        return { data: { id: 300, html_url: 'https://example.test/300' } };
      },
    },
  },
  async paginate(fn, params) {
    const response = await fn(params);
    return Array.isArray(response?.data) ? response.data : [];
  },
};

const context = {
  repo: { owner: 'octo', repo: 'workflows' },
};

async function main() {
  await updateKeepaliveLoopSummary({
    github,
    context,
    core,
    inputs: {
      prNumber: 2468,
      action: 'run',
      runResult: 'success',
      gateConclusion: 'success',
      tasksTotal: 10,
      tasksUnchecked: 6,
      keepaliveEnabled: true,
      autofixEnabled: false,
      iteration: 1,
      maxIterations: 5,
      failureThreshold: 3,
      trace: 'trace-metrics',
      duration_ms: 1234,
    },
  });

  const record = outputs.metrics_record_json;
  if (!record) {
    throw new Error('metrics_record_json output not set');
  }
  process.stdout.write(record);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exitCode = 1;
});
