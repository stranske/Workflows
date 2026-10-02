'use strict';

// Rebuild the production verifier context without invoking a model. Historical
// replays are explicitly marked retrospective because issue bodies may drift.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { buildVerifierContext } = require('../.github/scripts/agents_verifier_context.js');

async function captureModelEvalInputs({
  github, context, core, prNumbers, outputRoot = 'captured-inputs', buildContext = buildVerifierContext,
}) {
  const raw = String(prNumbers || '').trim();
  if (!raw || !/^\d+(,\d+)*$/.test(raw)) {
    throw new Error('capture_prs must be comma-separated merged PR numbers');
  }
  const numbers = raw.split(',').map(Number);
  if (numbers.length > 8 || new Set(numbers).size !== numbers.length || numbers.some((n) => n <= 0)) {
    throw new Error('capture_prs must contain 1-8 unique positive PR numbers');
  }
  const root = process.cwd();
  const priorPr = process.env.VERIFIER_PR_NUMBER;
  const ciWorkflows = '["pr-00-gate.yml", "pr-11-ci-smoke.yml", "selftest-ci.yml"]';
  try {
    for (const number of numbers) {
      const target = path.resolve(root, outputRoot, `pr-${number}`);
      fs.mkdirSync(target, { recursive: true });
      process.env.VERIFIER_PR_NUMBER = String(number);
      process.chdir(target);
      const result = await buildContext({ github, context, core, ciWorkflows });
      if (!result.shouldRun) {
        throw new Error(`PR #${number} has no usable verifier context: ${result.reason}`);
      }
      const contextBytes = fs.readFileSync('verifier-context.md');
      const summaryBytes = fs.readFileSync('verifier-diff-summary.md');
      const manifest = {
        schema: 'workflows-verifier-input-snapshot/v1',
        capture_kind: 'retrospective',
        repository: `${context.repo.owner}/${context.repo.repo}`,
        pr: number,
        merge_sha: result.targetSha,
        source_run_id: String(context.runId || process.env.GITHUB_RUN_ID),
        chain_depth: result.chainDepth,
        context_sha256: crypto.createHash('sha256').update(contextBytes).digest('hex'),
        diff_summary_sha256: crypto.createHash('sha256').update(summaryBytes).digest('hex'),
      };
      fs.writeFileSync('verifier-input-manifest.json', `${JSON.stringify(manifest, null, 2)}\n`);
      process.chdir(root);
    }
  } finally {
    process.chdir(root);
    if (priorPr === undefined) delete process.env.VERIFIER_PR_NUMBER;
    else process.env.VERIFIER_PR_NUMBER = priorPr;
  }
}

module.exports = { captureModelEvalInputs };
