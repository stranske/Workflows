'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {createHash} = require('crypto');
const native = require('./fixtures/verifier-4509-run-identity.json');
const modules = [
  require('../agents_verifier_context'),
  require('../../../templates/consumer-repo/.github/scripts/agents_verifier_context'),
];
const HEAD = 'aa7fe9537cb9c448a50b51ff6eb5da162fd819b1';
const MERGE = '37e230009cdba04743376410c9f72356b85fb64f';
const RUN = native.consumer.data.id;
const URL = native.consumer.data.html_url;
const payload = Buffer.from('bounded archive transport fixture');
const digest = 'sha256:' + createHash('sha256').update(payload).digest('hex');

function setup(defect) {
  const calls = [];
  const run = structuredClone(native.consumer.data);
  const artifact = {id: 42, name: 'consumer-proof', size_in_bytes: payload.length,
    expired: false, digest, workflow_run: {id: RUN, head_sha: run.head_sha,
      repository_id: run.repository.id, head_repository_id: run.head_repository.id}};
  const changes = {
    'wrong-run': () => {run.id += 1;},
    'missing-repository': () => {delete run.repository;},
    'wrong-repository': () => {run.repository.full_name = 'stranske/Workflows';},
    'missing-repository-id': () => {delete run.repository.id;},
    'wrong-head-repository': () => {run.head_repository.id += 1;},
    'wrong-head-repository-name': () => {run.head_repository.full_name = 'stranske/Other';},
    'short-head': () => {run.head_sha = '9484064';},
    'missing-attempt': () => {delete run.run_attempt;},
    'pending': () => {run.status = 'in_progress';},
    'missing-conclusion': () => {run.conclusion = null;},
    'artifact-run': () => {artifact.workflow_run.id += 1;},
    'artifact-head': () => {artifact.workflow_run.head_sha = HEAD;},
    'artifact-repository': () => {artifact.workflow_run.repository_id += 1;},
    'artifact-head-repository': () => {artifact.workflow_run.head_repository_id += 1;},
    'artifact-missing-digest': () => {delete artifact.digest;},
    'artifact-missing-expiration': () => {delete artifact.expired;},
    'artifact-digest': () => {artifact.digest = 'sha256:' + '0'.repeat(64);},
  };
  changes[defect]?.();
  const record = (operation, args) => {
    calls.push({operation, ...args});
    if (args.repo !== 'trip-planner') throw Object.assign(new Error('Not Found'), {status: 404});
  };
  const empty = async () => ({data: [], headers: {}});
  const github = {rest: {
    issues: {listComments: empty},
    pulls: {listReviewComments: empty, listReviews: empty},
    actions: {
      getWorkflowRun: async args => {
        record('run', args);
        if ([401, 403, 404].includes(defect)) throw Object.assign(new Error('inaccessible'), {status: defect});
        return {data: run};
      },
      listWorkflowRunsForRepo: async args => {
        calls.push({operation: 'discovery', ...args});
        return {data: {total_count: 0, workflow_runs: []}, headers: {}};
      },
      listWorkflowRunArtifacts: async args => {
        record('artifacts', args);
        return {data: {total_count: 1, artifacts: [artifact]}, headers: {}};
      },
      downloadArtifact: async args => {record('download', args); return {data: payload};},
    },
  }};
  return {github, calls};
}

for (const [index, collector] of modules.entries()) {
  const collect = async (defect, body = `Validation evidence: ${URL}`) => {
    const fixture = setup(defect);
    const evidence = await collector.fetchVerifierEvidence({github: fixture.github,
      owner: 'stranske', repo: 'Workflows', pullNumber: 4509, pullRequestBody: body,
      associatedCommitShas: [HEAD, MERGE], evaluatedSha: MERGE,
      // Extraction has its own archive tests; this regression isolates native API identity.
      extractArtifactText: () => ({text: 'consumer test results', truncated: false,
        extractedBytes: 21, entryCount: 1})});
    return {...fixture, evidence};
  };

  test(`source/template ${index}: real #4509 topology preserves consumer provenance`, {timeout: 120000}, async () => {
    const started = performance.now();
    const {evidence, calls} = await collect();
    assert.equal(evidence.artifacts.complete, true, evidence.artifacts.reason);
    assert.deepEqual(calls.map(call => call.operation), ['run', 'artifacts', 'download']);
    assert.ok(calls.every(call => call.owner === 'stranske' && call.repo === 'trip-planner'));
    const proof = evidence.artifacts.records[0];
    assert.equal(proof.repository, 'stranske/trip-planner');
    assert.equal(proof.head_sha, native.consumer.data.head_sha);
    assert.equal(proof.evidence_role, 'downstream-evidence');
    assert.equal(proof.downstream_binding.current_head_proof, false);
    assert.equal(proof.downstream_binding.evaluated_sha, MERGE);
    assert.equal(proof.downstream_binding.conclusion, 'success');
    assert.equal(proof.downstream_binding.referenced_workflows[0].sha, MERGE);
    assert.equal(evidence.diagnostics.references.run_lookups[0].status, 'authenticated');
    assert.equal(evidence.diagnostics.archive_inventory[0].repository, proof.repository);
    const coverage = collector.buildContextSourceCoverage({planSources: [], diffText: '', evidence});
    assert.deepEqual(coverage.acceptance_evidence_sources[0].downstream_binding, proof.downstream_binding);
    assert.match(collector.formatVerifierEvidence(evidence), /Downstream evidence: stranske\/trip-planner at .*not current-revision proof/);
    assert.ok(performance.now() - started < 120000);
  });

  test(`source/template ${index}: wrong-repository 404 cannot determine consumer absence`, async () => {
    const {github} = setup();
    await assert.rejects(github.rest.actions.getWorkflowRun({owner: 'stranske', repo: 'Workflows', run_id: RUN}), {status: 404});
    const {evidence} = await collect();
    assert.equal(native.wrong_repository.authoritative_for_consumer, false);
    assert.equal(evidence.artifacts.status, 'present');
  });

  for (const defect of [401, 403, 404, 'wrong-run', 'missing-repository', 'wrong-repository',
    'missing-repository-id', 'wrong-head-repository', 'wrong-head-repository-name',
    'short-head', 'missing-attempt', 'pending', 'missing-conclusion', 'artifact-run',
    'artifact-head', 'artifact-repository', 'artifact-head-repository', 'artifact-missing-digest',
    'artifact-missing-expiration', 'artifact-digest']) {
    test(`source/template ${index}: fails closed on ${defect}`, async () => {
      const {evidence, calls} = await collect(defect);
      assert.equal(evidence.artifacts.complete, false);
      assert.equal(evidence.artifacts.status, 'unavailable');
      assert.equal(evidence.artifacts.records.length, 0);
      assert.ok(evidence.diagnostics.failures.some(row => ['provenance', 'archive_integrity'].includes(row.kind)));
      if (![ 'artifact-digest' ].includes(defect)) assert.ok(!calls.some(call => call.operation === 'download'));
      if (typeof defect === 'number') assert.equal(evidence.diagnostics.references.run_lookups[0].http_status, defect);
    });
  }

  test(`source/template ${index}: local discovery cannot replace a failed foreign identity gate`, async () => {
    const {github, calls} = setup(403);
    github.rest.actions.listWorkflowRunsForRepo = async () => ({data: {
      total_count: 1, workflow_runs: [{id: RUN, head_sha: HEAD}],
    }, headers: {}});
    const evidence = await collector.fetchVerifierEvidence({github, owner: 'stranske', repo: 'Workflows',
      pullNumber: 4509, pullRequestBody: `Evidence: ${URL}`, associatedCommitShas: [HEAD]});
    assert.equal(evidence.artifacts.complete, false);
    assert.equal(evidence.artifacts.records.length, 0);
    assert.ok(!calls.some(call => call.operation === 'download'));
  });

  test(`source/template ${index}: repository identity stays downstream even for an equal head`, async () => {
    const fixture = setup();
    const evidence = await collector.fetchVerifierEvidence({github: fixture.github, owner: 'stranske', repo: 'Workflows',
      pullNumber: 4509, pullRequestBody: `Evidence: ${URL}`, associatedCommitShas: [native.consumer.data.head_sha],
      extractArtifactText: () => ({text: 'proof', truncated: false, extractedBytes: 5})});
    assert.equal(evidence.artifacts.records[0].evidence_role, 'downstream-evidence');
    assert.equal(evidence.artifacts.records[0].downstream_binding.current_head_proof, false);
  });

  for (const body of [`Evidence: ${URL} and /actions/runs/${RUN}`,
    `Evidence: ${URL.replace('github.com', 'example.invalid')}`,
    `Evidence: ${URL.replace('github.com', 'user@github.com')}`]) {
    test(`source/template ${index}: rejects ambiguous or untrusted URL ${body}`, async () => {
      const {evidence, calls} = await collect(undefined, body);
      assert.equal(evidence.artifacts.complete, false);
      assert.equal(evidence.artifacts.records.length, 0);
      assert.ok(!calls.some(call => call.operation === 'download'));
    });
  }
}
