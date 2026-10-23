'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const modules = [
  require('../agents_verifier_context.js'),
  require('../../../templates/consumer-repo/.github/scripts/agents_verifier_context.js'),
];
const head = 'a'.repeat(40);
const baseline = '2fe7ef8a0205816ad31b986f76e77f569a8145bd';
const merge = '2a5fc881d3758136bf9818783d62999c1ab05ca4';
const citation = '#853 provenance: full combined coverage evidence remains CI run [39545834989](https://github.com/stranske/Orchestrator/actions/runs/39545834989) (success on `2fe7ef8a`).';
function setup(defect) {
  const calls = [];
  const repository = {full_name: 'stranske/Orchestrator'};
  const pull = {number: 854, merged: true, head: {sha: baseline}, merge_commit_sha: merge, base: {repo: repository}};
  if (defect === 'wrong-owner') pull.head.sha = 'b'.repeat(40);
  if (defect === 'short-owner-sha') pull.merge_commit_sha = 'abcdef0';
  if (defect === 'same-target') pull.number = 872;
  if (defect === 'unmerged') pull.merged = false;
  if (defect === 'owner-repository') pull.base = {repo: {full_name: 'stranske/Other'}};
  const github = {rest: {
    issues: {listComments: async () => ({data: []})},
    pulls: {listReviewComments: async () => ({data: []}), listReviews: async () => ({data: []}),
      get: async () => {if (defect === 'owner-api-error') throw new Error('owner unavailable'); return {data: pull};}},
    repos: {listPullRequestsAssociatedWithCommit: async () => ({
      data: defect === 'malformed-association' ? null : defect === 'ambiguous-association' ? [pull, pull] : ['multiple-associated-one-cited', 'explicit-run-owner'].includes(defect) ? [pull, {...pull, number: 855}] : [{number: defect === 'unassociated' ? 855 : 854, base: {repo: repository}}],
      headers: defect === 'incomplete-association' ? {link: '<https://api.github.com/page2>; rel="next"'} : {},
    })},
    actions: {
      getWorkflowRun: async () => ({data: {id: 39545834989, head_sha: defect === 'current-head' ? head : baseline, event: 'pull_request', status: 'completed', run_attempt: 1,
        pull_requests: defect === 'explicit-run-owner' ? [{number: 854}] : defect === 'run-owner-mismatch' ? [{number: 855}] : defect === 'malformed-run-owners' ? {} : defect === 'multiple-run-owners' ? [{number: 854}, {number: 855}] : [],
        repository: defect === 'run-repository' ? {full_name: 'stranske/Other'} : repository}}),
      listWorkflowRunsForRepo: async () => ({data: {total_count: 0, workflow_runs: []}}),
      listWorkflowRunArtifacts: async () => ({data: {total_count: 1, artifacts: [{id: 7, name: 'combined', size_in_bytes: 3, expired: defect === 'expired'}]}}),
      downloadArtifact: async () => {calls.push('download'); return {data: Buffer.from('zip')};},
    },
  }};
  return {github, calls};
}
for (const [index, mod] of modules.entries()) {
  async function collect(defect, body = citation) {
    const {github, calls} = setup(defect);
    const result = await mod.fetchVerifierEvidence({github, owner: 'stranske', repo: 'Orchestrator', pullNumber: 872,
      pullRequestBody: body, referenceTexts: ['Follow-up to https://github.com/stranske/Orchestrator/pull/854'],
      associatedCommitShas: [head], extractArtifactText: () => ({text: 'historical measurement', truncated: false})});
    return {result, calls};
  }
  test(`historical baseline authenticates actual #872 citation and keeps a distinct role (${index})`, async () => {
    const {result} = await collect();
    assert.equal(result.artifacts.complete, true, result.artifacts.reason);
    const record = result.artifacts.records[0];
    assert.equal(record.evidence_role, 'historical-baseline');
    assert.equal(record.historical_binding.pull_number, 854);
    assert.equal(record.historical_binding.run_head_sha, baseline);
    assert.equal(record.historical_binding.ownership_basis, 'unique-commit-association');
    assert.equal(record.historical_binding.merge_sha, merge);
    assert.match(mod.formatVerifierEvidence(result), /Historical baseline.*not current-revision proof/);
    const coverage = mod.buildContextSourceCoverage({planSources: [], diffText: '', evidence: result});
    assert.equal(coverage.acceptance_evidence_sources[0].evidence_role, 'historical-baseline');
    assert.equal(coverage.artifact_capture_inventory[0].historical_binding.pull_number, 854);
  });
  test(`explicit native run owner resolves several commit associations (${index})`, async () => {
    const {result} = await collect('explicit-run-owner');
    assert.equal(result.artifacts.complete, true, result.artifacts.reason);
    assert.equal(result.artifacts.records[0].historical_binding.pull_number, 854);
    assert.equal(result.artifacts.records[0].historical_binding.ownership_basis, 'run-pr-and-commit-association');
  });
  for (const defect of ['wrong-owner', 'unmerged', 'owner-repository', 'unassociated', 'run-repository', 'same-target', 'owner-api-error', 'malformed-association', 'incomplete-association', 'ambiguous-association', 'short-owner-sha', 'multiple-associated-one-cited', 'run-owner-mismatch', 'malformed-run-owners', 'multiple-run-owners']) {
    test(`historical baseline rejects ${defect} (${index})`, async () => {
      const {result, calls} = await collect(defect);
      assert.ok(result.diagnostics.failures.some(row => row.kind === 'provenance'));
      assert.deepEqual(calls, []);
    });
  }
  const runLink = '[run](https://github.com/stranske/Orchestrator/actions/runs/39545834989)';
  for (const body of [
    `Validation evidence: ${runLink} is not a historical baseline`,
    `Historical baseline evidence: ${runLink} is not a historical baseline`,
    `Not historical baseline evidence: ${runLink}`,
    `Historical baseline evidence: ${runLink} isn't a historical baseline`,
    `Historical baseline evidence: ${runLink} is never a historical baseline`,
    `Historical baseline evidence: ${runLink} should not be used as a baseline`,
    `Validation evidence: ${runLink} may be a historical baseline`,
    `Possible historical baseline evidence: ${runLink}`,
    `Historical baseline evidence: ${runLink} may be a historical baseline`,
    `Historical baseline evidence: ${runLink} is possibly a baseline`,
    `Historical baseline evidence: ${runLink} is \`not\` a baseline`,
    `Historical baseline evidence: ${runLink} is "not" a baseline`,
    `Historical baseline evidence: ${runLink} is 'not' a baseline`,
    `Historical baseline evidence: ${runLink} is “not” a baseline`,
    `Historical baseline evidence: ${runLink} is ‘not’ a baseline`,
    `Historical baseline evidence: ${runLink} is *not* a baseline`,
    `Historical baseline evidence: ${runLink} is **not** a baseline`,
    `Historical baseline evidence: ${runLink} is _not_ a baseline`,
    `Historical baseline evidence: ${runLink} is __not__ a baseline`,
    `Historical baseline evidence: ${runLink} is \`possibly\` a baseline`,
    `Historical baseline evidence: ${runLink} is "possibly" a baseline`,
    `Validation evidence: For example, ${runLink} is a historical baseline`,
    `Historical baseline evidence: ${runLink} is probably a baseline`,
    `Historical baseline evidence: ${runLink} is allegedly a historical baseline`,
    `Historical baseline evidence: ${runLink} could certainly be a baseline`,
    `Historical baseline evidence: Example: ${runLink} is a historical baseline`,
    `Example validation evidence: ${runLink} is a historical baseline`,
    `Historical baseline evidence: ${runLink} is a potential baseline`,
    `Historical baseline evidence: ${runLink} might serve as a baseline`,
    `Validation evidence: if ${runLink} is a historical baseline`,
    `Validation evidence: ${runLink} is "a historical baseline"`,
    `Validation evidence: ${runLink} is 'a historical baseline'`,
    `Historical baseline evidence: ${runLink} is "not a historical baseline"`,
    `> Historical baseline evidence: ${runLink}`,
    `\`\`\`text\nHistorical baseline evidence: ${runLink}\n\`\`\``,
    `    Historical baseline evidence: ${runLink}`,
    `"Historical baseline evidence: ${runLink}"`,
  ]) {
    test(`historical role is not granted by negated, uncertain or quoted prose: ${body} (${index})`, async () => {
      const {result, calls} = await collect(undefined, body);
      assert.equal(result.artifacts.records.length, 0);
      assert.deepEqual(calls, []);
    });
  }
  for (const body of [
    `Historical baseline evidence: ${runLink}`,
    `Validation evidence: ${runLink} is a historical baseline`,
    `Validation evidence: ${runLink} serves as a historical baseline`,
    `Historical baseline evidence: ${runLink} is a historical baseline`,
  ]) {
    test(`affirmative historical role remains supported: ${body} (${index})`, async () => {
      const {result} = await collect(undefined, body);
      assert.equal(result.artifacts.complete, true, result.artifacts.reason);
      assert.equal(result.artifacts.records[0].evidence_role, 'historical-baseline');
    });
  }
  test(`negative historical role does not reject exact current-head proof (${index})`, async () => {
    const {result} = await collect('current-head', `Validation evidence: ${runLink} is not a historical baseline`);
    assert.equal(result.artifacts.complete, true, result.artifacts.reason);
    assert.equal(result.artifacts.records[0].evidence_role, undefined);
  });
  test(`current-head mismatch is not promoted by a historical PR elsewhere (${index})`, async () => {
    const {result, calls} = await collect(undefined, citation.replace('#853 provenance:', 'Validation:'));
    assert.ok(result.diagnostics.failures.some(row => row.kind === 'provenance'));
    assert.deepEqual(calls, []);
  });
  test(`historical baseline reports expired optional material honestly (${index})`, async () => {
    const {result} = await collect('expired');
    assert.equal(result.artifacts.complete, false);
    assert.ok(result.diagnostics.failures.some(row => row.kind === 'expired'));
    assert.ok(!result.diagnostics.failures.some(row => row.kind === 'provenance'));
    assert.equal(result.artifacts.records.length, 0);
  });
  test(`foreign run citation cannot establish a same-repository baseline (${index})`, async () => {
    const {result, calls} = await collect(undefined, citation.replace('/Orchestrator/actions/', '/Other/actions/'));
    assert.ok(result.diagnostics.failures.some(row => row.kind === 'provenance'));
    assert.deepEqual(calls, []);
  });
}
