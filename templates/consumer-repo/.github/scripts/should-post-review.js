#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { evaluateReviewResult, loadReviewResult } = require('./keepalive_review_guard');

function resolveFilePath(argv) {
  const candidate = argv && argv[2] ? argv[2] : null;
  if (candidate) {
    return candidate;
  }
  return path.join(process.cwd(), 'review_result.json');
}

function writeOutput(shouldPost) {
  const outputPath = process.env.GITHUB_OUTPUT;
  const line = `should_post_review=${shouldPost ? 'true' : 'false'}`;

  if (outputPath) {
    fs.writeFileSync(outputPath, `${line}\n`, 'utf8');
    return;
  }
  process.stdout.write(`${line}\n`);
}

function main() {
  const filePath = resolveFilePath(process.argv);
  const { payload, readError } = loadReviewResult(filePath);

  const shouldPost = readError ? false : evaluateReviewResult(payload).shouldPost;

  writeOutput(shouldPost);
}

if (require.main === module) {
  main();
}

module.exports = { main };
