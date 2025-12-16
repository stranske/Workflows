#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const { resolveOrchestratorParams } = require('../../../../.github/scripts/agents_orchestrator_resolve.js');

async function main() {
  const scenarioPath = process.argv[2];
  if (!scenarioPath) {
    console.error('Usage: node resolve_harness.js <scenario.json>');
    process.exit(2);
  }

  let scenario;
  try {
    const resolved = path.resolve(process.cwd(), scenarioPath);
    scenario = JSON.parse(fs.readFileSync(resolved, 'utf8'));
  } catch (error) {
    console.error('Failed to load scenario:', error.message);
    process.exit(2);
  }

  const outputs = {};
  const infos = [];
  const warnings = [];
  const summaryLog = [];

  const core = {
    info(message) {
      infos.push(String(message));
    },
    warning(message) {
      warnings.push(String(message));
    },
    setOutput(key, value) {
      outputs[String(key)] = value;
    },
    summary: {
      addHeading(text) {
        summaryLog.push({ type: 'heading', text: String(text) });
        return this;
      },
      addTable(rows) {
        summaryLog.push({ type: 'table', rows });
        return this;
      },
      addRaw(text) {
        summaryLog.push({ type: 'raw', text: String(text) });
        return this;
      },
      addEOL() {
        summaryLog.push({ type: 'eol' });
        return this;
      },
      write() {
        return Promise.resolve();
      },
    },
  };

  const github = {
    rest: {
      issues: {
        async getLabel() {
          const error = new Error('Label not found');
          error.status = 404;
          throw error;
        },
      },
    },
  };

  const env = Object.assign({}, scenario.env || {});
  const context = Object.assign({ eventName: 'workflow_dispatch', repo: { owner: 'stranske', repo: 'Trend_Model_Project' } }, scenario.context || {});

  await resolveOrchestratorParams({ github, context, core, env });

  const payload = { outputs, infos, warnings, summary: summaryLog };
  process.stdout.write(JSON.stringify(payload));
}

main();
