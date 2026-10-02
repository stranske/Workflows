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
      prNumbers: '10,11',
      buildContext: async ({ ciWorkflows }) => {
        called.push({ pr: process.env.VERIFIER_PR_NUMBER, ciWorkflows });
        fs.writeFileSync('verifier-context.md', `context ${process.env.VERIFIER_PR_NUMBER}`);
        fs.writeFileSync('verifier-diff-summary.md', 'summary');
        return { shouldRun: true, targetSha: 'a'.repeat(40), chainDepth: 0 };
      },
    });
    assert.deepEqual(called.map((row) => row.pr), ['10', '11']);
    assert.equal(process.env.VERIFIER_PR_NUMBER, '99');
    const manifest = JSON.parse(fs.readFileSync(path.join(root, 'captured-inputs/pr-10/verifier-input-manifest.json')));
    assert.equal(manifest.capture_kind, 'retrospective');
    assert.equal(manifest.source_run_id, '123');
    await assert.rejects(
      captureModelEvalInputs({
        github: {}, context: { repo: { owner: 'stranske', repo: 'Workflows' } }, core: {},
        prNumbers: '10,10', buildContext: async () => { throw new Error('unexpected call'); },
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
