'use strict';
// Read-only live probe. The token remains in memory and is never retained.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../../..');
const { fetchVerifierEvidence } = require(path.join(root, '.github/scripts/agents_verifier_context.js'));
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const output = process.argv[2];
if (!output) throw new Error('Pass a new output directory');
fs.mkdirSync(output, { recursive: false });
const calls = [];
const started = new Date().toISOString();
const token = execFileSync('gh', ['auth', 'token'], { encoding: 'utf8' }).trim();
async function get(route, params = {}, binary = false) {
  if (params.owner && `${params.owner}/${params.repo}`.toLowerCase() !== 'stranske/workflows') {
    throw new Error('Probe scope is restricted to stranske/Workflows');
  }
  const url = new URL(`https://api.github.com${route}`);
  for (const [key, value] of Object.entries(params)) {
    if (!['owner', 'repo', 'request', 'run_id', 'artifact_id', 'issue_number', 'pull_number', 'comment_id'].includes(key)) {
      url.searchParams.set(key, value);
    }
  }
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' },
    signal: AbortSignal.timeout(15000) });
  calls.push({ method: 'GET', url: url.href, status: response.status, at: new Date().toISOString() });
  if (!response.ok) {
    const body = await response.json();
    throw Object.assign(new Error(body.message || response.statusText), { status: response.status });
  }
  return { data: binary ? Buffer.from(await response.arrayBuffer()) : await response.json() };
}
const base = '/repos/stranske/Workflows';
const github = { rest: {
  issues: {
    getComment: p => get(`${base}/issues/comments/${p.comment_id}`, p),
    listComments: p => get(`${base}/issues/${p.issue_number}/comments`, p),
  },
  pulls: {
    listReviewComments: p => get(`${base}/pulls/${p.pull_number}/comments`, p),
    listReviews: p => get(`${base}/pulls/${p.pull_number}/reviews`, p),
  },
  actions: {
    getWorkflowRun: p => get(`${base}/actions/runs/${p.run_id}`, p),
    listWorkflowRunArtifacts: p => get(`${base}/actions/runs/${p.run_id}/artifacts`, p),
    getArtifact: p => get(`${base}/actions/artifacts/${p.artifact_id}`, p),
    downloadArtifact: p => get(`${base}/actions/artifacts/${p.artifact_id}/zip`, {}, true),
    listWorkflowRunsForRepo: p => get(`${base}/actions/runs`, p),
  },
} };
(async () => {
  const subjects = [];
  for (const [pr, comment, run, artifact] of [
    [4231, 6390994169, 40143755394, 12579928048],
    [4235, 6392557346, 40155311407, 12584318436],
  ]) {
    const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, `${pr}-original/verification-event-manifest.json`)));
    const selectors = [
      { kind: 'comment', url: `https://github.com/stranske/Workflows/pull/${pr}#issuecomment-${comment}` },
      ...['comparison.json', 'comparison-execution.json'].map(member =>
        ({ kind: 'artifact_member', run_id: run, artifact_id: artifact, path: member })),
    ];
    process.env.VERIFICATION_MATERIAL = JSON.stringify(selectors);
    process.env.VERIFIER_EVIDENCE_RUN_LIMIT = '1';
    process.env.VERIFIER_EVIDENCE_ARTIFACT_LIMIT = '1';
    const subject = { pr, comment, run_id: run, artifact_id: artifact, selectors };
    try {
      const pull = (await get(`${base}/pulls/${pr}`)).data;
      const result = await fetchVerifierEvidence({ github, owner: 'stranske', repo: 'Workflows',
        pullNumber: pr, pullRequest: pull, pullRequestBody: pull.body,
        associatedCommitShas: [manifest.verification_event.head_sha, manifest.verification_event.evaluated_sha],
        evaluatedSha: manifest.verification_event.evaluated_sha });
      const raw = JSON.stringify(result, null, 2) + '\n';
      subject.output = `${pr}-collector.json`;
      subject.sha256 = hash(raw);
      fs.writeFileSync(path.join(output, subject.output), raw);
      console.log(`#${pr}: retained collector JSON; ${result.diagnostics.failures.length} diagnostics`);
    } catch (error) {
      subject.collection_failure = { name: error.name, message: error.message, status: error.status ?? null };
      console.log(`#${pr}: collection failed: ${error.message}`);
    }
    subjects.push(subject);
  }
  const provenance = { schema: 'retained-collector-execution/v1', started, finished: new Date().toISOString(),
    source_head: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    collector_sha256: hash(fs.readFileSync(path.join(root, '.github/scripts/agents_verifier_context.js'))),
    harness_sha256: hash(fs.readFileSync(__filename)), node: process.version,
    transport: 'Node fetch, authenticated with gh auth token; GET only; no provider adapter',
    command: `node tests/fixtures/verification_input_repair/collect-retained-evidence.cjs ${output}`,
    subjects, calls };
  fs.writeFileSync(path.join(output, 'execution.json'), JSON.stringify(provenance, null, 2) + '\n');
})().catch(error => { console.error(error.message); process.exitCode = 1; });
