'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {createHash} = require('crypto');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
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
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

function withJsonInput(value, run) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'verifier-test-input-'));
  let descriptor;
  try {
    const filename = path.join(directory, 'input.json');
    fs.writeFileSync(filename, JSON.stringify(value));
    descriptor = fs.openSync(filename, 'r');
    return run(descriptor);
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    fs.rmSync(directory, {recursive: true, force: true});
  }
}

// Synthetic archive bytes exercise the real extractor; only the API identity
// comes from the native observation. This is not the exact #4509 input capture.
function makeArchive(entries) {
  return withJsonInput(entries, descriptor => execFileSync('python3', ['-I', '-c', [
    'import io,json,sys,zipfile',
    'output=io.BytesIO()',
    'with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as archive:',
    ' for name,text in json.load(sys.stdin).items(): archive.writestr(name,text)',
    'sys.stdout.buffer.write(output.getvalue())',
  ].join('\n')], {stdio: [descriptor, 'pipe', 'pipe'], timeout: 10000}));
}

// This is the exact two-file merge patch, not a reconstruction of the unavailable
// original input bundle. The large proof members below are explicitly synthetic.
const mergeFixture = require('./fixtures/verifier-4509-merge.json');
const mergePatch = mergeFixture.patch;
const changedPaths = ['scripts/ci_history.py', 'tests/scripts/test_ci_history.py'];

test('retained #4509 merge patch preserves the exact two-file review input', () => {
  // git diff --no-ext-diff --no-color --no-renames --full-index MERGE^1 MERGE
  // The retained bytes work in a clean checkout without fetching historical refs.
  assert.equal(mergeFixture.repository, 'stranske/Workflows');
  assert.equal(mergeFixture.pr_number, 4509);
  assert.equal(mergeFixture.head_sha, HEAD);
  assert.equal(mergeFixture.evaluated_sha, MERGE);
  assert.equal(sha256(mergePatch), 'fe6672ef4ff28986e3fe79f91575f60092dbc45ec9e2d3fd9f322adb4885bc8a');
  assert.equal(mergeFixture.patch_sha256, sha256(mergePatch));
  assert.deepEqual([...mergePatch.matchAll(/^\+\+\+ b\/(.+)$/gm)].map(match => match[1]), changedPaths);
});

function captureContext(collector, evidence) {
  const plan = '### Acceptance criteria\n- [ ] Attach consumer validation artifacts.';
  const coverage = collector.buildContextSourceCoverage({
    planSources: [{source: 'Pull request #4509', body: plan}], diffText: mergePatch, evidence,
  });
  coverage.acceptance_source_discovery = {required: false, status: 'included'};
  assert.deepEqual(coverage.changed_code_sources.map(row => row.source), changedPaths);
  return '# Verifier context\n\n## Context source coverage\n\n```json\n'
    + JSON.stringify(coverage) + '\n```\n\n## CI Information\n\n| CI | success |\n\n'
    + '## Plan sources (scope, tasks, acceptance)\n\n' + plan + '\n\n'
    + collector.formatVerifierEvidence(evidence) + '\n\n## PR Diff (full)\n\n```diff\n'
    + mergePatch + '```\n';
}

function checkCapture(context, directory) {
  return withJsonInput({context, directory, diff: mergePatch}, descriptor =>
    JSON.parse(execFileSync('python3', ['-S', '-c', [
    'import json,sys',
    'from pathlib import Path',
    'from tools.verifier_artifact_capture import load_artifact_capture',
    'from tools.verifier_capture_obligation_manifest import build_capture_obligation_manifest,parse_context_source_coverage',
    'data=json.load(sys.stdin)',
    'context=data["context"]',
    'manifest=build_capture_obligation_manifest(context,full_diff_bytes=data["diff"].encode())',
    'inputs={}',
    'if manifest["sufficient"]:',
    ' inputs,_=load_artifact_capture(parse_context_source_coverage(context),Path(data["directory"]))',
    'print(json.dumps({"manifest":manifest,"input_lengths":{key:len(value) for key,value in inputs.items()}}))',
  ].join('\n')], {stdio: [descriptor, 'pipe', 'pipe'], encoding: 'utf8', timeout: 30000})));
}

function setup(defect, archive = payload) {
  const calls = [];
  const run = structuredClone(native.consumer.data);
  const artifact = {id: 42, name: 'consumer-proof', size_in_bytes: archive.length,
    expired: false, digest: `sha256:${sha256(archive)}`, workflow_run: {id: RUN, head_sha: run.head_sha,
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
        if (defect === 'artifact-list-denied') throw Object.assign(new Error('Forbidden'), {status: 403});
        return {data: {total_count: 1, artifacts: [artifact]}, headers: {}};
      },
      downloadArtifact: async args => {
        record('download', args);
        if (defect === 'artifact-download-denied') throw Object.assign(new Error('Forbidden'), {status: 403});
        return {data: archive};
      },
    },
  }};
  return {github, calls};
}

for (const [index, collector] of modules.entries()) {
  const collect = async (defect, body = `Validation evidence: ${URL}`, options = {}) => {
    const fixture = setup(defect, options.archive);
    if (options.legacyRouting) {
      const getRun = fixture.github.rest.actions.getWorkflowRun;
      // Reproduce the old adapter's local numeric-ID lookup through the collector.
      fixture.github.rest.actions.getWorkflowRun = args => getRun({...args, repo: 'Workflows'});
    }
    const evidence = await collector.fetchVerifierEvidence({github: fixture.github,
      owner: 'stranske', repo: 'Workflows', pullNumber: 4509, pullRequestBody: body,
      associatedCommitShas: [HEAD, MERGE], evaluatedSha: MERGE,
      // Keep the identity matrix fast, but use production extraction for ZIP cases.
      ...(options.archive ? {extractArtifactText: args => collector.extractArtifactArchiveText({...args,
        // unzip reads the archive path, never the test runner's stdin.
        execFile: (command, argv, settings) => execFileSync(command, argv,
          {...settings, stdio: ['ignore', 'pipe', 'pipe']}),
      })} : {extractArtifactText: () => ({text: 'consumer test results', truncated: false,
        extractedBytes: 21, entryCount: 1})})});
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
    const before = await collect(undefined, native.source_evidence, {legacyRouting: true});
    assert.equal(before.evidence.artifacts.complete, false);
    assert.equal(before.evidence.artifacts.records.length, 0);
    assert.equal(before.evidence.diagnostics.references.run_lookups[0].http_status, 404);
    assert.deepEqual(before.calls.filter(call => call.operation === 'run')
      .map(call => call.repo), ['Workflows']);
    assert.ok(!before.calls.some(call => call.operation === 'download'));
    const {evidence, calls} = await collect(undefined, native.source_evidence);
    assert.equal(native.wrong_repository.authoritative_for_consumer, false);
    assert.equal(evidence.artifacts.status, 'present');
    assert.equal(evidence.artifacts.complete, true, evidence.artifacts.reason);
    assert.deepEqual(calls.filter(call => call.operation !== 'discovery').map(call => [call.operation, call.repo]),
      [['run', 'trip-planner'], ['artifacts', 'trip-planner'], ['download', 'trip-planner']]);
    const lookup = evidence.diagnostics.references.run_lookups[0];
    assert.equal(lookup.repository, 'stranske/trip-planner');
    assert.equal(lookup.head_sha, '948406465cf7cd65d1ac92206b4514aaad455443');
    assert.equal(lookup.conclusion, 'success');
    assert.equal(lookup.downstream_binding.status, 'completed');
    assert.equal(lookup.downstream_binding.current_head_proof, false);
  });

  test(`source/template ${index}: real ZIP retains authenticated downstream member identities`, {timeout: 120000}, async () => {
    const entries = {'results.ndjson': '{"tests":9,"failures":0}\n', 'summary.md': 'Consumer CI completed.'};
    const archive = makeArchive(entries);
    const {evidence, calls} = await collect(undefined, native.source_evidence, {archive});
    assert.equal(evidence.artifacts.complete, true, evidence.artifacts.reason);
    assert.deepEqual(evidence.diagnostics.failures, []);
    assert.ok(calls.every(call => call.operation === 'discovery' || call.repo === 'trip-planner'));
    const capture = evidence.diagnostics.archive_inventory[0];
    assert.equal(capture.archive_sha256, sha256(archive));
    assert.equal(capture.member_inventory_complete, true);
    assert.equal(capture.member_count, 2);
    assert.equal(capture.status, 'rendered');
    assert.deepEqual(capture.members.map(member => [member.name, member.status, member.raw_sha256]),
      Object.entries(entries).map(([name, text]) => [name, 'included', sha256(Buffer.from(text))]));
    const proof = evidence.artifacts.records[0];
    assert.match(proof.text, /### results\.ndjson/);
    assert.match(proof.text, /Consumer CI completed/);
    assert.equal(proof.head_sha, native.consumer.data.head_sha);
    assert.equal(proof.downstream_binding.repository_id, native.consumer.data.repository.id);
    assert.equal(proof.downstream_binding.current_head_proof, false);
    assert.notEqual(proof.head_sha, MERGE);
    const coverage = collector.buildContextSourceCoverage({planSources: [], diffText: '', evidence});
    assert.equal(coverage.acceptance_evidence_sources[0].status, 'included');
    assert.equal(coverage.acceptance_evidence_sources[0].evidence_role, 'downstream-evidence');
    assert.deepEqual(coverage.acceptance_evidence_sources[0].downstream_binding, proof.downstream_binding);
  });

  test(`source/template ${index}: real ZIP keeps unsupported siblings as an unresolved capture gap`, async () => {
    const archive = makeArchive({'results.ndjson': '{"tests":9}\n', 'unknown.bin': 'unsupported payload'});
    const {evidence} = await collect(undefined, native.source_evidence, {archive});
    assert.equal(evidence.artifacts.status, 'unavailable');
    assert.equal(evidence.artifacts.complete, false);
    // Useful text is retained, but cannot hide the sibling's extraction gap.
    assert.equal(evidence.artifacts.records.length, 1);
    assert.equal(evidence.artifacts.records[0].truncated, true);
    assert.equal(evidence.artifacts.records[0].downstream_binding.current_head_proof, false);
    const capture = evidence.diagnostics.archive_inventory[0];
    assert.equal(capture.archive_sha256, sha256(archive));
    assert.equal(capture.status, 'incomplete');
    assert.equal(capture.members.find(member => member.name === 'unknown.bin').status, 'unsupported');
    const coverage = collector.buildContextSourceCoverage({planSources: [], diffText: '', evidence});
    const gap = coverage.acceptance_evidence_sources.find(source => source.status === 'unavailable');
    assert.equal(gap.channel, 'artifacts');
    assert.ok(gap.failure_kinds.includes('unsupported_payload'));
    assert.ok(gap.failure_kinds.includes('extraction_incomplete'));
  });

  test(`source/template ${index}: matching archive digest cannot hide a corrupt ZIP`, async () => {
    const archive = makeArchive({'results.ndjson': '{"tests":9}\n'}).subarray(0, 32);
    const {evidence} = await collect(undefined, native.source_evidence, {archive});
    assert.equal(evidence.artifacts.status, 'unavailable');
    assert.equal(evidence.artifacts.complete, false);
    assert.equal(evidence.artifacts.records.length, 0);
    assert.equal(evidence.diagnostics.references.run_lookups[0].status, 'authenticated');
    const capture = evidence.diagnostics.archive_inventory[0];
    assert.equal(capture.archive_sha256, sha256(archive));
    assert.equal(capture.members, null);
    assert.equal(capture.status, 'unavailable');
    const coverage = collector.buildContextSourceCoverage({planSources: [], diffText: '', evidence});
    assert.ok(coverage.acceptance_evidence_sources.some(source => source.channel === 'artifacts'
      && source.status === 'unavailable'));
  });

  test(`source/template ${index}: bounded raw capture crosses collector/native admission without inventing review`,
    {timeout: 120000}, async () => {
      const started = performance.now();
      const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'verifier-4509-capture-'));
      const names = ['VERIFIER_SEMANTIC_MODE', 'VERIFIER_EVIDENCE_CAPTURE_DIR',
        'VERIFIER_EVIDENCE_TOTAL_EXTRACT_BYTES'];
      const previous = names.map(name => process.env[name]);
      // The original log records coverage.xml/json extraction-byte gaps and a
      // 102351-byte index.ndjson rendering omission. Exercise both failure types
      // with synthetic, compressible members larger than the ordinary preview.
      const entries = {'pytest-junit.xml': '<testsuite tests="9" failures="0"/>',
        'coverage.xml': '<coverage>' + 'x'.repeat(600000) + '</coverage>',
        'coverage.json': JSON.stringify({payload: 'y'.repeat(600000)}),
        'index.ndjson': '0'.repeat(102350) + '\n'};
      const archive = makeArchive(entries);
      try {
        process.env.VERIFIER_SEMANTIC_MODE = '0';
        process.env.VERIFIER_EVIDENCE_CAPTURE_DIR = directory;
        delete process.env.VERIFIER_EVIDENCE_TOTAL_EXTRACT_BYTES;
        const preview = await collect(undefined, native.source_evidence, {archive});
        assert.equal(preview.evidence.artifacts.complete, false);
        assert.ok(preview.evidence.diagnostics.failures.some(row => row.kind === 'extraction_byte'));
        const incomplete = checkCapture(captureContext(collector, preview.evidence), directory);
        assert.equal(incomplete.manifest.sufficient, false);

        process.env.VERIFIER_SEMANTIC_MODE = '1';
        const full = await collect(undefined, native.source_evidence, {archive});
        assert.equal(full.evidence.artifacts.complete, true, full.evidence.artifacts.reason);
        const inventory = full.evidence.diagnostics.archive_inventory[0];
        assert.equal(inventory.status, 'captured');
        assert.equal(inventory.downstream_binding.current_head_proof, false);
        assert.equal(inventory.head_sha, native.consumer.data.head_sha);
        assert.deepEqual(inventory.members.map(row => row.name), Object.keys(entries));
        assert.ok(inventory.members.slice(1).every(row => row.status === 'captured'));
        assert.equal(full.evidence.diagnostics.counters.extracted_bytes,
          Object.values(entries).reduce((total, value) => total + Buffer.byteLength(value), 0));
        const context = captureContext(collector, full.evidence);
        const complete = checkCapture(context, directory);
        assert.equal(complete.manifest.sufficient, true, complete.manifest.gaps.join('; '));
        assert.deepEqual(Object.values(complete.input_lengths), Object.values(entries).map(Buffer.byteLength));
        assert.deepEqual(complete.manifest.obligations.filter(row => row.kind === 'changed_code')
          .map(row => row.source), changedPaths);

        // A complete collector ledger alone cannot admit missing/tampered bytes.
        const lateMember = inventory.members.at(-1);
        const sidecar = path.join(directory, `${lateMember.raw_sha256}.txt`);
        const original = fs.readFileSync(sidecar);
        for (const defect of ['tampered', 'missing']) {
          if (defect === 'tampered') fs.writeFileSync(sidecar, Buffer.alloc(original.length, 120));
          else fs.unlinkSync(sidecar);
          const rejected = checkCapture(context, directory);
          assert.equal(rejected.manifest.sufficient, false, defect);
          assert.ok(rejected.manifest.gaps.some(gap => gap.startsWith('artifact_raw_capture:')), defect);
          fs.writeFileSync(sidecar, original);
        }

        process.env.VERIFIER_EVIDENCE_TOTAL_EXTRACT_BYTES = '1000';
        const bounded = await collect(undefined, native.source_evidence, {archive});
        assert.equal(bounded.evidence.artifacts.complete, false);
        assert.notEqual(bounded.evidence.diagnostics.archive_inventory[0].status, 'captured');
        const refused = checkCapture(captureContext(collector, bounded.evidence), directory);
        assert.equal(refused.manifest.sufficient, false);
        assert.ok(performance.now() - started < 120000);
      } finally {
        names.forEach((name, offset) => {
          if (previous[offset] === undefined) delete process.env[name];
          else process.env[name] = previous[offset];
        });
        fs.rmSync(directory, {recursive: true, force: true});
      }
    });

  for (const defect of ['artifact-list-denied', 'artifact-download-denied']) {
    test(`source/template ${index}: authenticated run cannot hide ${defect}`, async () => {
      const {evidence} = await collect(defect);
      assert.equal(evidence.diagnostics.references.run_lookups[0].status, 'authenticated');
      assert.equal(evidence.artifacts.status, 'unavailable');
      assert.equal(evidence.artifacts.complete, false);
      assert.equal(evidence.artifacts.records.length, 0);
      assert.match(evidence.artifacts.reason, /Forbidden/);
    });
  }

  test(`source/template ${index}: a negative Workflows lookup citation does not rebind consumer proof`, async () => {
    const diagnostic = `https://github.com/stranske/Workflows/actions/runs/${RUN} is not evidence of consumer absence (404).`;
    const {evidence, calls} = await collect(undefined, `${diagnostic}\n\n${native.source_evidence}`);
    assert.equal(evidence.artifacts.complete, true, evidence.artifacts.reason);
    assert.equal(evidence.artifacts.records[0].head_sha, native.consumer.data.head_sha);
    assert.ok(calls.filter(call => call.operation !== 'discovery').every(call => call.repo === 'trip-planner'));
  });

  test(`source/template ${index}: negative consumer prose never enters fallback discovery`, async () => {
    const {evidence, calls} = await collect(undefined, `${URL} is not current validation evidence.`);
    assert.equal(evidence.artifacts.records.length, 0);
    assert.ok(calls.every(call => call.operation === 'discovery'));
    assert.deepEqual(evidence.diagnostics.references.requested_run_ids, []);
  });

  test(`source/template ${index}: a labelled union still excludes unselected foreign citations`, async () => {
    const {evidence, calls} = await collect(undefined, `Evidence: ${URL}\nUnrelated history: https://github.com/stranske/Other/actions/runs/123`);
    assert.equal(evidence.artifacts.complete, true, evidence.artifacts.reason);
    assert.deepEqual(evidence.diagnostics.references.requested_run_ids, [RUN]);
    assert.ok(calls.every(call => call.repo === 'trip-planner'));
  });

  for (const defect of [401, 403, 404, 'wrong-run', 'missing-repository', 'wrong-repository',
    'missing-repository-id', 'wrong-head-repository', 'wrong-head-repository-name',
    'short-head', 'missing-attempt', 'pending', 'missing-conclusion', 'artifact-run',
    'artifact-head', 'artifact-repository', 'artifact-head-repository', 'artifact-missing-digest',
    'artifact-missing-expiration', 'artifact-digest']) {
    for (const body of [`Validation evidence: ${URL}`, native.source_evidence]) {
      test(`source/template ${index}: fails closed on ${defect}, narrative=${body === native.source_evidence}`, async () => {
        const {evidence, calls} = await collect(defect, body);
        assert.equal(evidence.artifacts.complete, false);
        assert.equal(evidence.artifacts.status, 'unavailable');
        assert.equal(evidence.artifacts.records.length, 0);
        assert.ok(evidence.diagnostics.failures.some(row => ['provenance', 'archive_integrity'].includes(row.kind)));
        if (![ 'artifact-digest' ].includes(defect)) assert.ok(!calls.some(call => call.operation === 'download'));
        if (typeof defect === 'number') assert.equal(evidence.diagnostics.references.run_lookups[0].http_status, defect);
      });
    }
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
