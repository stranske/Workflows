'use strict';

// Read-only native acquisition. Reuse the collector's canonical origin checks;
// retained JSON and offline observation fixtures cannot supply API authority.
const fs = require('fs');
const path = require('path');
const {createRequire} = require('module');
const {acquireRetainedExecution} = require('../.github/scripts/verifier_pending_execution');
const {digest} = require('../.github/scripts/verification_event');

async function admitOrigin({github, manifest, selector, currentRun, directory}) {
  const event = manifest.verification_event;
  const assessment = manifest.assessment_identity;
  const proof = await acquireRetainedExecution({
    github, event, assessment, selector, currentRun, directory,
    pullRequestTargetOrigin: true,
  });
  proof.recovery_key = digest({
    schema: 'retained-revalidation-key/v1', event_id: event.event_id,
    assessment, selector,
  });
  fs.writeFileSync(path.join(directory, 'verification-recovery-origin.json'),
    JSON.stringify(proof, null, 2) + '\n');
  return proof;
}

async function main() {
  const directory = process.cwd();
  const manifest = JSON.parse(fs.readFileSync(path.join(directory, 'verification-event-manifest.json')));
  const requireScripts = createRequire(path.resolve(__dirname, '../.github/scripts/package.json'));
  const {Octokit} = requireScripts('@octokit/rest');
  const github = new Octokit({auth: process.env.GH_TOKEN || process.env.GITHUB_TOKEN});
  await admitOrigin({github, manifest,
    selector: JSON.parse(process.env.VERIFICATION_RECOVERY),
    currentRun: Number(process.env.GITHUB_RUN_ID), directory});
}

if (require.main === module) {
  main().catch(() => {
    // Do not dump authenticated request objects or headers on transport errors.
    process.stderr.write('Authenticated retained origin acquisition failed\n');
    process.exitCode = 1;
  });
}

module.exports = {admitOrigin};
