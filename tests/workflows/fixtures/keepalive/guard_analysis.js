#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const { analyseSkipComments } = require('../../../../.github/scripts/keepalive_guard_utils.js');

function main() {
  const scenarioPath = process.argv[2];
  if (!scenarioPath) {
    console.error('Usage: node guard_analysis.js <scenario.json>');
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

  const rawComments = Array.isArray(scenario.comments) ? scenario.comments : [];
  const comments = rawComments.map((body) => ({ body: String(body ?? '') }));

  const result = analyseSkipComments(comments);
  process.stdout.write(JSON.stringify(result));
}

main();
