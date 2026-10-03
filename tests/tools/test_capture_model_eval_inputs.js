'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { captureModelEvalInputs } = require('../../tools/capture_model_eval_inputs.js');

test('read-only context capture records retrospective provenance and restores process state', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'maint78-capture-'));
  const previousDirectory = process.cwd();
  const previousPr = process.env.VERIFIER_PR_NUMBER;
  try {
    process.chdir(root);
    process.env.VERIFIER_PR_NUMBER = '99';
    const called = [];
    await captureModelEvalInputs({
      github: {},
      context: { repo: { owner: 'stranske', repo: 'Workflows' }, runId: 123 },
      core: {},
      targets: 'stranske/Workflows#10,stranske/Pension-Data#11',
      buildContext: async ({ context, ciWorkflows }) => {
        called.push({ pr: process.env.VERIFIER_PR_NUMBER, repo: context.repo.repo, ciWorkflows });
        fs.writeFileSync('verifier-context.md', `context ${process.env.VERIFIER_PR_NUMBER}`);
        fs.writeFileSync('verifier-diff-summary.md', 'summary');
        fs.writeFileSync('verifier-pr-diff.patch', 'full diff');
        return { shouldRun: true, targetSha: 'a'.repeat(40), chainDepth: 0 };
      },
    });
    assert.deepEqual(called.map((row) => row.pr), ['10', '11']);
    assert.deepEqual(called.map((row) => row.repo), ['Workflows', 'Pension-Data']);
    assert.deepEqual(called.map((row) => JSON.parse(row.ciWorkflows)), [
      ['pr-00-gate.yml', 'pr-11-ci-smoke.yml', 'selftest-ci.yml'],
      ['ci.yml', 'pr-00-gate.yml'],
    ]);
    assert.equal(process.env.VERIFIER_PR_NUMBER, '99');
    const manifest = JSON.parse(fs.readFileSync(path.join(root, 'captured-inputs/case-1/verifier-input-manifest.json')));
    assert.equal(manifest.capture_kind, 'retrospective');
    assert.equal(manifest.source_run_id, '123');
    assert.equal(
      manifest.diff_sha256,
      require('node:crypto').createHash('sha256').update('full diff').digest('hex'),
    );
    await assert.rejects(
      captureModelEvalInputs({
        github: {}, context: { repo: { owner: 'stranske', repo: 'Workflows' } }, core: {},
        targets: 'stranske/Workflows#10,stranske/Workflows#10', buildContext: async () => { throw new Error('unexpected call'); },
      }),
      /unique/,
    );
  } finally {
    process.chdir(previousDirectory);
    if (previousPr === undefined) delete process.env.VERIFIER_PR_NUMBER;
    else process.env.VERIFIER_PR_NUMBER = previousPr;
    fs.rmSync(root, { recursive: true, force: true });
  }
});
