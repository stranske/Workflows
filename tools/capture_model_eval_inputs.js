'use strict';

// Rebuild the production verifier context without invoking a model. Historical
// replays are explicitly marked retrospective because issue bodies may drift.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { buildVerifierContext } = require('../.github/scripts/agents_verifier_context.js');

async function captureModelEvalInputs({
  github, context, core, targets, outputRoot = 'captured-inputs', buildContext = buildVerifierContext,
}) {
  const entries = String(targets || '').trim().split(',');
  if (
    entries.length > 8 ||
    new Set(entries).size !== entries.length ||
    entries.some((entry) => !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+#[1-9]\d*$/.test(entry))
  ) {
    throw new Error('capture_targets must contain 1-8 unique owner/repo#PR entries');
  }
  const root = process.cwd();
  const priorPr = process.env.VERIFIER_PR_NUMBER;
  const ciWorkflows = '["pr-00-gate.yml", "pr-11-ci-smoke.yml", "selftest-ci.yml"]';
  try {
    for (const entry of entries) {
      const [fullName, pr] = entry.split('#');
      const [owner, repo] = fullName.split('/');
      const number = Number(pr);
      const target = path.resolve(root, outputRoot, `${owner}-${repo}-pr-${number}`);
      fs.mkdirSync(target, { recursive: true });
      process.env.VERIFIER_PR_NUMBER = String(number);
      process.chdir(target);
      const repoContext = { ...context, repo: { owner, repo } };
      const result = await buildContext({ github, context: repoContext, core, ciWorkflows });
      if (!result.shouldRun) {
        throw new Error(`PR #${number} has no usable verifier context: ${result.reason}`);
      }
      const contextBytes = fs.readFileSync('verifier-context.md');
      const summaryBytes = fs.readFileSync('verifier-diff-summary.md');
      const manifest = {
        schema: 'workflows-verifier-input-snapshot/v1',
        capture_kind: 'retrospective',
        repository: fullName,
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
