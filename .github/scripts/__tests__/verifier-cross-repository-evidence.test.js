'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {createHash} = require('crypto');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {acquireRetainedExecution, readRetainedArchive} = require('../verifier_pending_execution');
const {validateEvent} = require('../verification_event');
const native = require('./fixtures/verifier-4509-run-identity.json');
const retained = require('./fixtures/verifier-4509-capture-identity.json');
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

// These are the unchanged authenticated production ZIPs, not synthetic stand-ins.
const originalCapture = fs.readFileSync(path.join(__dirname, 'fixtures/verifier-4509-capture.zip'));
const originalAutofix = fs.readFileSync(path.join(__dirname, 'fixtures/verifier-4509-selftest-autofix-3.13.zip'));

test('exact #4509 retained capture preserves event, extraction gaps and zero provider coverage', () => {
  assert.equal(`sha256:${sha256(originalCapture)}`, retained.capture.digest);
  assert.equal(originalCapture.length, retained.capture.size_in_bytes);
  const files = readRetainedArchive(originalCapture);
  const snapshot = JSON.parse(files.get('verifier-input-manifest.json'));
  const manifest = JSON.parse(files.get('verification-event-manifest.json'));
  const comparison = JSON.parse(files.get('comparison.json'));
  const receipt = JSON.parse(files.get('comparison-execution.json'));
  const event = validateEvent(manifest.verification_event);
  assert.equal(event.event_id, '872cfa6b5cc9d664566f1aa1ecb5dbeaf303b27bd5a96288414318455a343e9c');
  assert.equal(event.evaluated_sha, MERGE);
  const [consumer, wrongRepository, verifier] = retained.authenticated_gets;
  assert.equal(consumer.http_status, 200);
  assert.deepEqual(consumer.data.repository, {id: 993784438, full_name: 'stranske/trip-planner'});
  assert.equal(consumer.data.head_sha, native.consumer.data.head_sha);
  assert.equal(consumer.data.status, 'completed');
  assert.equal(consumer.data.conclusion, 'success');
  assert.equal(consumer.data.referenced_workflows[0].sha, MERGE);
  assert.equal(wrongRepository.http_status, 404);
  assert.equal(wrongRepository.authoritative_for_consumer, false);
  assert.equal(verifier.data.id, retained.capture.workflow_run.id);
  assert.equal(verifier.data.head_sha, event.head_sha);
  assert.equal(verifier.data.run_attempt, 1);
  assert.equal(snapshot.pr, 4509);
  assert.equal(snapshot.source_run_id, '42330898168');
  for (const [name, field] of [['verifier-context.md', 'context_sha256'],
    ['verifier-pr-diff.patch', 'diff_sha256'], ['verifier-diff-summary.md', 'diff_summary_sha256']]) {
    assert.equal(sha256(files.get(name)), snapshot[field]);
  }
  assert.equal(sha256(files.get('comparison.json')), receipt.outputs['comparison.json'].sha256);
  const context = files.get('verifier-context.md').toString('utf8');
  const diagnostics = JSON.parse(context.match(/### Retrieval diagnostics\n\n```json\n([\s\S]*?)\n```/)[1]);
  assert.deepEqual(diagnostics, retained.original_diagnostics);
  const first = diagnostics.archive_inventory.find(archive => archive.status === 'incomplete');
  assert.equal(first.repository, 'stranske/Workflows');
  assert.equal(first.run_id, 42326161711);
  assert.equal(first.artifact_id, 13556090021);
  assert.deepEqual(first.members.find(member => member.status === 'unavailable'), {
    name: 'coverage.xml', occurrence: 1, status: 'unavailable', reason: 'extraction_byte',
  });
  assert.equal(snapshot.capture_obligations.sufficient, false);
  assert.equal(snapshot.capture_reassembly_contract.sufficient, false);
  assert.equal(comparison.results.length, 2);
  for (const result of comparison.results) {
    assert.equal(result.used_llm, false);
    assert.equal(result.verdict, 'UNVERIFIABLE_INPUT');
    assert.deepEqual(result.files_not_reviewed, ['scripts/ci_history.py', 'tests/scripts/test_ci_history.py']);
    assert.equal(result.files_reviewed, null);
  }
});

test('exact #4509 replay refuses noncanonical origin before acquiring recovery authority', {timeout: 10000}, async () => {
  const files = readRetainedArchive(originalCapture);
  const manifest = JSON.parse(files.get('verification-event-manifest.json'));
  const run = retained.authenticated_gets[2].data;
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'verifier-4509-origin-'));
  const calls = [];
  const respond = (endpoint, data) => {
    calls.push(endpoint);
    return Promise.resolve({data: structuredClone(data)});
  };
  // Replay the selected native observations documented in the evidence report.
  // This adapter has no provider, artifact-download, or publication capability.
  const canonicalHead = 'e99195408b0d916c14c2c2f34a4b7a0a91ef8fb9';
  const github = {rest: {
    actions: {
      getWorkflowRun: ({owner, repo, run_id}) =>
        respond(`repos/${owner}/${repo}/actions/runs/${run_id}`, run),
      getWorkflowRunAttempt: ({owner, repo, run_id, attempt_number}) =>
        respond(`repos/${owner}/${repo}/actions/runs/${run_id}/attempts/${attempt_number}`, run),
    },
    repos: {
      get: ({owner, repo}) => respond(`repos/${owner}/${repo}`,
        {full_name: 'stranske/Workflows', default_branch: 'main'}),
      getCommit: ({owner, repo, ref}) => respond(`repos/${owner}/${repo}/commits/${ref}`,
        {sha: canonicalHead}),
      compareCommitsWithBasehead: ({owner, repo, basehead}) =>
        respond(`repos/${owner}/${repo}/compare/${basehead}`, {status: 'diverged',
          base_commit: {sha: HEAD},
          merge_base_commit: {sha: '75d4c8360c7a31db51366ca08d736cf4be1bc894'},
        }),
    },
  }};
  try {
    await assert.rejects(acquireRetainedExecution({github,
      event: manifest.verification_event, assessment: manifest.assessment_identity,
      selector: {run_id: run.id, run_attempt: run.run_attempt, artifact_id: retained.capture.id},
      // A local ordering sentinel, never a claim of an authenticated Actions job.
      currentRun: run.id + 1, directory,
    }), {message: retained.recovery_validation.error});
    assert.deepEqual(calls, retained.recovery_validation.calls);
    assert.deepEqual(fs.readdirSync(directory), []);
    assert.equal(`sha256:${sha256(originalCapture)}`, retained.capture.digest);
  } finally {
    fs.rmSync(directory, {recursive: true, force: true});
  }
});

for (const [index, collector] of modules.entries()) {
  for (const observation of retained.authenticated_gets) {
    test(`source/template ${index}: retained native GET ${observation.endpoint} cannot clear missing capture`, async () => {
      const calls = [];
      const empty = async () => ({data: [], headers: {}});
      const unavailable = async () => {
        throw new Error('No retained artifact-list or discovery observation; completeness is unknown');
      };
      const github = {rest: {
        issues: {listComments: empty},
        pulls: {listReviewComments: empty, listReviews: empty},
        actions: {
          getWorkflowRun: async ({owner, repo, run_id}) => {
            const endpoint = `repos/${owner}/${repo}/actions/runs/${run_id}`;
            calls.push(endpoint);
            assert.equal(endpoint, observation.endpoint);
            if (observation.http_status !== 200) {
              throw Object.assign(new Error('Not Found'), {status: observation.http_status});
            }
            return {data: structuredClone(observation.data)};
          },
          listWorkflowRunArtifacts: unavailable,
          listWorkflowRunsForRepo: unavailable,
          downloadArtifact: async () => assert.fail('GET identity cannot supply missing archive bytes'),
        },
      }};
      // Replay only recorded GET observations. Unknown artifact/discovery responses
      // stay unavailable rather than inventing an empty, complete evidence set.
      const evidence = await collector.fetchVerifierEvidence({github,
        owner: 'stranske', repo: 'Workflows', pullNumber: 4509,
        pullRequestBody: `Evidence: https://github.com/${observation.endpoint.replace('repos/', '')}`,
        associatedCommitShas: [HEAD, MERGE], evaluatedSha: MERGE,
      });
      assert.deepEqual(calls, [observation.endpoint]);
      const [lookup] = evidence.diagnostics.references.run_lookups;
      const [, owner, repo, , , runId] = observation.endpoint.split('/');
      assert.equal(lookup.repository, `${owner}/${repo}`);
      assert.equal(lookup.run_id, Number(runId));
      if (observation.http_status === 200) {
        assert.equal(lookup.status, 'authenticated');
        assert.equal(lookup.head_sha, observation.data.head_sha);
        assert.equal(lookup.run_attempt, observation.data.run_attempt);
        assert.equal(lookup.conclusion, observation.data.conclusion);
        if (repo === 'trip-planner') {
          assert.equal(lookup.evidence_role, 'downstream-evidence');
          assert.equal(lookup.downstream_binding.status, observation.data.status);
          assert.equal(lookup.downstream_binding.repository_id, observation.data.repository.id);
          assert.deepEqual(lookup.downstream_binding.referenced_workflows, observation.data.referenced_workflows);
          assert.equal(lookup.downstream_binding.current_head_proof, false);
        } else {
          assert.equal(lookup.evidence_role, 'exact-source');
          assert.equal(lookup.downstream_binding, undefined);
        }
      } else {
        assert.equal(lookup.status, 'unavailable');
        assert.equal(lookup.http_status, 404);
        assert.equal(observation.authoritative_for_consumer, false);
      }
      assert.equal(evidence.artifacts.complete, false);
      assert.equal(evidence.artifacts.status, 'unavailable');
      assert.deepEqual(evidence.artifacts.records, []);
      const coverage = collector.buildContextSourceCoverage({planSources: [], diffText: '', evidence});
      assert.ok(coverage.acceptance_evidence_sources.some(source =>
        source.channel === 'artifacts' && source.status === 'unavailable'));
    });
  }

  test(`source/template ${index}: exact #4509 archive reproduces first extraction gap`, {timeout: 10000}, () => {
    const artifact = retained.first_failing_artifact;
    assert.equal(`sha256:${sha256(originalAutofix)}`, artifact.digest);
    assert.equal(originalAutofix.length, artifact.size_in_bytes);
    const extracted = collector.extractArtifactArchiveText({archiveBuffer: originalAutofix,
      maxEntries: 20, maxChars: 60000, maxBytes: 240000,
      execFile: (command, argv, settings) => execFileSync(command, argv,
        {...settings, stdio: ['ignore', 'pipe', 'pipe']}),
    });
    const original = retained.original_diagnostics.archive_inventory.find(row => row.artifact_id === artifact.id);
    assert.equal(extracted.archiveSha256, original.archive_sha256);
    assert.equal(extracted.listingSha256, original.listing_sha256);
    assert.deepEqual(extracted.members, original.members);
    assert.equal(extracted.memberInventoryComplete, true);
    assert.equal(extracted.rawCaptureComplete, false);
    assert.equal(extracted.truncated, true);
    assert.ok(extracted.failures.includes('extraction_byte'));
    assert.equal(retained.first_archive_members[1].bytes, 2551782);
    assert.ok(retained.first_archive_members[1].bytes > 240000);
  });

  test(`source/template ${index}: existing raw capture retains exact #4509 members without claiming rendered completeness`, {timeout: 10000}, () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'verifier-4509-'));
    try {
      const extracted = collector.extractArtifactArchiveText({archiveBuffer: originalAutofix,
        maxEntries: 20, maxChars: 60000, maxBytes: 67108864, captureDirectory: directory,
        execFile: (command, argv, settings) => execFileSync(command, argv,
          {...settings, stdio: ['ignore', 'pipe', 'pipe']}),
      });
      assert.equal(extracted.rawCaptureComplete, true);
      // Recoverable raw bytes do not upgrade the immutable original capture or render budget.
      assert.equal(extracted.truncated, true);
      assert.ok(extracted.failures.includes('character'));
      for (const [index, member] of extracted.members.entries()) {
        const expected = retained.first_archive_members[index];
        assert.equal(member.name, expected.name);
        assert.equal(member.raw_bytes, expected.bytes);
        assert.equal(member.raw_sha256, expected.sha256);
        assert.equal(sha256(fs.readFileSync(path.join(directory, `${expected.sha256}.txt`))), expected.sha256);
      }
    } finally {
      fs.rmSync(directory, {recursive: true, force: true});
    }
  });
}

// Synthetic archive bytes exercise the real extractor; only the API identity
// comes from the native observation. This is not the exact #4509 input capture.
function makeArchive(entries) {
  return execFileSync('python3', ['-I', '-c', [
    'import io,json,sys,zipfile',
    'output=io.BytesIO()',
    'with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_STORED) as archive:',
    ' for name,text in json.loads(sys.argv[1]).items(): archive.writestr(name,text)',
    'sys.stdout.buffer.write(output.getvalue())',
  ].join('\n'), JSON.stringify(entries)], {stdio: ['ignore', 'pipe', 'pipe'], timeout: 10000});
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
