'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { extractReferencedRunProvenance } = require('./agents_verifier_context');

// Test 1: Valid cross-repository evidence extraction
test('extractReferencedRunProvenance: valid cross-repository URLs', () => {
  const texts = [
    'https://github.com/stranske/trip-planner/actions/runs/42327976097',
    'https://github.com/stranske/Workflows/actions/runs/1234567890',
    'See run https://github.com/owner/repo/actions/runs/999',
  ];
  const provenance = extractReferencedRunProvenance(texts);
  
  assert.strictEqual(provenance.length, 3);
  assert.ok(provenance.some(p => p.runId === 42327976097 && p.repository === 'stranske/trip-planner'));
  assert.ok(provenance.some(p => p.runId === 1234567890 && p.repository === 'stranske/Workflows'));
  assert.ok(provenance.some(p => p.runId === 999 && p.repository === 'owner/repo'));
});

// Test 2: Extract run IDs with various URL formats
test('extractReferencedRunProvenance: various URL formats', () => {
  const texts = [
    'Run at https://github.com/stranske/trip-planner/actions/runs/42327976097/summary',
    'Check https://github.com/stranske/trip-planner/actions/runs/42327976098?foo=bar',
    'Link: https://github.com/stranske/trip-planner/actions/runs/42327976099#step',
    'Run ID 42327976097 without URL',
  ];
  const provenance = extractReferencedRunProvenance(texts);
  
  assert.strictEqual(provenance.length, 3);
  assert.ok(provenance.every(p => p.repository === 'stranske/trip-planner'));
  assert.ok(provenance.some(p => p.runId === 42327976097));
  assert.ok(provenance.some(p => p.runId === 42327976098));
  assert.ok(provenance.some(p => p.runId === 42327976099));
});

// Test 3: Duplicate run IDs from same repository
test('extractReferencedRunProvenance: deduplicates same run from same repo', () => {
  const texts = [
    'https://github.com/stranske/trip-planner/actions/runs/42327976097',
    'https://github.com/stranske/trip-planner/actions/runs/42327976097',
    'https://github.com/stranske/trip-planner/actions/runs/42327976097',
  ];
  const provenance = extractReferencedRunProvenance(texts);
  
  assert.strictEqual(provenance.length, 1);
  assert.strictEqual(provenance[0].runId, 42327976097);
  assert.strictEqual(provenance[0].repository, 'stranske/trip-planner');
});

// Test 4: Same run ID from different repositories
test('extractReferencedRunProvenance: same run ID from different repositories', () => {
  const texts = [
    'https://github.com/stranske/trip-planner/actions/runs/123',
    'https://github.com/stranske/Workflows/actions/runs/123',
  ];
  const provenance = extractReferencedRunProvenance(texts);
  
  assert.strictEqual(provenance.length, 2);
  assert.ok(provenance.some(p => p.runId === 123 && p.repository === 'stranske/trip-planner'));
  assert.ok(provenance.some(p => p.runId === 123 && p.repository === 'stranske/Workflows'));
});

// Test 5: Empty or invalid inputs
test('extractReferencedRunProvenance: handles empty and invalid inputs', () => {
  assert.strictEqual(extractReferencedRunProvenance([]).length, 0);
  assert.strictEqual(extractReferencedRunProvenance([null, undefined, '']).length, 0);
  assert.strictEqual(extractReferencedRunProvenance(['no url here']).length, 0);
  assert.strictEqual(extractReferencedRunProvenance(['https://github.com/org/repo']).length, 0);
});

// Test 6: Cross-repo run evidence with repository, run ID, and head SHA
test('extractReferencedRunProvenance: validates run identity with repository context', () => {
  const texts = [
    'Evidence from downstream run: https://github.com/stranske/trip-planner/actions/runs/42327976097',
    'Local run: https://github.com/stranske/Workflows/actions/runs/42380991219',
  ];
  const provenance = extractReferencedRunProvenance(texts);
  
  assert.strictEqual(provenance.length, 2);
  
  const tripPlannerRun = provenance.find(p => p.runId === 42327976097);
  assert.ok(tripPlannerRun);
  assert.strictEqual(tripPlannerRun.repository, 'stranske/trip-planner');
  
  const workflowsRun = provenance.find(p => p.runId === 42380991219);
  assert.ok(workflowsRun);
  assert.strictEqual(workflowsRun.repository, 'stranske/Workflows');
});

// Test 7: Downstream vs current-head provenance distinction
test('extractReferencedRunProvenance: distinguishes downstream from current repo', () => {
  const currentRepo = 'stranske/Workflows';
  const downstreamRepo = 'stranske/trip-planner';
  const runId = 42327976097;
  
  const texts = [
    `Downstream evidence: https://github.com/${downstreamRepo}/actions/runs/${runId}`,
    `Current repo evidence: https://github.com/${currentRepo}/actions/runs/${runId + 1}`,
  ];
  
  const provenance = extractReferencedRunProvenance(texts);
  assert.strictEqual(provenance.length, 2);
  
  const downstreamRun = provenance.find(p => p.repository === downstreamRepo);
  assert.ok(downstreamRun);
  assert.strictEqual(downstreamRun.runId, runId);
  
  const currentRun = provenance.find(p => p.repository === currentRepo);
  assert.ok(currentRun);
  assert.strictEqual(currentRun.runId, runId + 1);
});

// Test 8: Real-world scenario - #4509 capture evidence
test('extractReferencedRunProvenance: issue #4509 real-world URLs', () => {
  const texts = [
    ['gh', 'api repos/stranske/trip-planner/actions/runs/42327976097'].join(' '),
    'https://github.com/stranske/trip-planner/actions/runs/42327976097',
    'head_sha: 948406465cf7cd65d1ac92206b4514aaad455443',
    'Run ID: 42327976097',
  ];
  
  const provenance = extractReferencedRunProvenance(texts);
  assert.ok(provenance.length >= 1);
  
  const tripPlannerRun = provenance.find(p => p.runId === 42327976097);
  assert.ok(tripPlannerRun);
  assert.strictEqual(tripPlannerRun.repository, 'stranske/trip-planner');
});

// Test 9: Multiple downstream repositories
test('extractReferencedRunProvenance: handles multiple downstream repositories', () => {
  const texts = [
    'https://github.com/owner/repo1/actions/runs/100',
    'https://github.com/owner/repo2/actions/runs/200',
    'https://github.com/owner2/repo1/actions/runs/300',
  ];
  
  const provenance = extractReferencedRunProvenance(texts);
  assert.strictEqual(provenance.length, 3);
  
  assert.ok(provenance.some(p => p.runId === 100 && p.repository === 'owner/repo1'));
  assert.ok(provenance.some(p => p.runId === 200 && p.repository === 'owner/repo2'));
  assert.ok(provenance.some(p => p.runId === 300 && p.repository === 'owner2/repo1'));
});

// Test 10: Unavailable evidence - run IDs that cannot be resolved
test('extractReferencedRunProvenance: handles runs without repository context', () => {
  const texts = [
    'Run 42327976097 without URL',
    'Just a number: 12345',
  ];
  
  const provenance = extractReferencedRunProvenance(texts);
  assert.strictEqual(provenance.length, 0);
});

// Test 11: Wrong repository - mismatched URLs
test('extractReferencedRunProvenance: detects repository from URL', () => {
  const texts = [
    'https://github.com/wrong-owner/wrong-repo/actions/runs/42327976097',
  ];
  
  const provenance = extractReferencedRunProvenance(texts);
  assert.strictEqual(provenance.length, 1);
  assert.strictEqual(provenance[0].repository, 'wrong-owner/wrong-repo');
  assert.strictEqual(provenance[0].runId, 42327976097);
});

// Test 12: Mixed valid and invalid URLs
test('extractReferencedRunProvenance: mixed valid and invalid URLs', () => {
  const texts = [
    'Valid: https://github.com/stranske/trip-planner/actions/runs/42327976097',
    'Invalid: https://github.com/org/repo/issues/123',
    'Also valid: https://github.com/stranske/Workflows/actions/runs/42380991219',
    'Not a URL: just text',
  ];
  
  const provenance = extractReferencedRunProvenance(texts);
  assert.strictEqual(provenance.length, 2);
  assert.ok(provenance.some(p => p.runId === 42327976097));
  assert.ok(provenance.some(p => p.runId === 42380991219));
});

const collectors = [
  ['root', require('./agents_verifier_context')],
  ['consumer template', require('../../templates/consumer-repo/.github/scripts/agents_verifier_context')],
];
const currentHead = 'a'.repeat(40);
const downstreamHead = '948406465cf7cd65d1ac92206b4514aaad455443';
const downstreamRunId = 42327976097;
const downstreamUrl = `https://github.com/stranske/trip-planner/actions/runs/${downstreamRunId}`;
const nonPassText = '{"verdict":"UNVERIFIABLE_INPUT","reason":"unresolved extraction gap"}';

function mockEvidenceClient({ mismatch = false, missing = false } = {}) {
  const calls = [];
  const repository = { full_name: 'stranske/trip-planner' };
  const pull = { number: 42, merged: true, head: { sha: downstreamHead },
    merge_commit_sha: 'b'.repeat(40), base: { repo: repository } };
  const record = (method, params) => calls.push({ method, ...params });
  const github = { rest: {
    issues: { listComments: async () => ({ data: [] }) },
    pulls: {
      listReviewComments: async () => ({ data: [] }),
      listReviews: async () => ({ data: [] }),
      get: async params => { record('pull', params); return { data: pull }; },
    },
    repos: { listPullRequestsAssociatedWithCommit: async params => {
      record('association', params);
      return { data: [pull] };
    } },
    actions: {
      getWorkflowRun: async params => {
        record('run', params);
        if (missing || params.repo === 'Workflows') {
          throw Object.assign(new Error('Not Found'), { status: 404 });
        }
        return { data: { id: downstreamRunId, head_sha: downstreamHead,
          repository: mismatch ? { full_name: 'stranske/Workflows' } : repository,
          event: 'pull_request', status: 'completed', run_attempt: 1, pull_requests: [{ number: 42 }] } };
      },
      listWorkflowRunsForRepo: async params => {
        record('discovery', params);
        return { data: { total_count: 0, workflow_runs: [] } };
      },
      listWorkflowRunArtifacts: async params => {
        record('artifacts', params);
        return { data: { total_count: 1, artifacts: [
          { id: 7, name: 'verification-results', size_in_bytes: 3, expired: false },
        ] } };
      },
      downloadArtifact: async params => {
        record('download', params);
        return { data: Buffer.from('zip') };
      },
    },
  } };
  return { github, calls };
}

for (const [name, collector] of collectors) {
  async function collect(options = {}) {
    const { github, calls } = mockEvidenceClient(options);
    if (options.local404) {
      const { rest: { actions } } = github;
      await assert.rejects(actions.getWorkflowRun({
        owner: 'stranske', repo: 'Workflows', run_id: downstreamRunId,
      }), { status: 404 });
    }
    const result = await collector.fetchVerifierEvidence({
      github, owner: 'stranske', repo: 'Workflows', pullNumber: 4532,
      pullRequestBody: `Historical baseline evidence: ${downstreamUrl}`,
      referenceTexts: ['https://github.com/stranske/trip-planner/pull/42'],
      associatedCommitShas: [currentHead],
      extractArtifactText: () => ({ text: nonPassText, truncated: Boolean(options.incomplete) }),
    });
    return { result, calls };
  }

  test(`${name}: fetches authenticated downstream evidence with a distinct head SHA`, async () => {
    const { result, calls } = await collect();
    assert.notEqual(downstreamHead, currentHead);
    assert.equal(result.artifacts.complete, true, result.artifacts.reason);
    assert.deepEqual(result.referencedRunIds, [downstreamRunId]);
    assert.equal(result.artifacts.records[0].historical_binding.run_head_sha, downstreamHead);
    assert.equal(result.artifacts.records[0].evidence_role, 'historical-baseline');
    for (const method of ['run', 'association', 'pull', 'artifacts', 'download']) {
      const requests = calls.filter(call => call.method === method);
      assert.equal(requests.length, 1, method);
      assert.equal(requests[0].owner, 'stranske');
      assert.equal(requests[0].repo, 'trip-planner');
    }
    assert.equal(calls.find(call => call.method === 'run').run_id, downstreamRunId);
    assert.equal(calls.find(call => call.method === 'artifacts').run_id, downstreamRunId);
    assert.equal(calls.find(call => call.method === 'download').artifact_id, 7);
  });

  test(`${name}: Workflows 404 does not override retrieved downstream evidence`, async () => {
    const { result, calls } = await collect({ local404: true });
    assert.ok(calls.some(call => call.method === 'run' && call.repo === 'Workflows'
      && call.run_id === downstreamRunId));
    assert.equal(result.artifacts.records.length, 1);
    assert.equal(result.artifacts.records[0].runId, downstreamRunId);
    assert.equal(result.artifacts.complete, true, result.artifacts.reason);
    assert.equal(result.diagnostics.counters.provenance_failures, 0);
    assert.equal(calls.filter(call => call.method === 'download').length, 1);
  });

  test(`${name}: downstream 404 remains unavailable without downloading artifacts`, async () => {
    const { result, calls } = await collect({ missing: true });
    assert.equal(result.artifacts.complete, false);
    assert.equal(result.artifacts.records.length, 0);
    assert.ok(result.diagnostics.failures.some(row => row.kind === 'provenance' && /Not Found/.test(row.detail)));
    assert.ok(!calls.some(call => ['artifacts', 'download'].includes(call.method)));
  });

  test(`${name}: rejects downstream repository mismatch as provenance failure`, async () => {
    const { result, calls } = await collect({ mismatch: true });
    assert.equal(result.artifacts.complete, false);
    assert.ok(result.diagnostics.failures.some(row => row.kind === 'provenance' && /repository mismatch/.test(row.detail)));
    assert.equal(result.diagnostics.counters.provenance_failures, 1);
    assert.equal(result.artifacts.records.length, 0);
    assert.ok(!calls.some(call => ['artifacts', 'download'].includes(call.method)));
  });

  test(`${name}: incomplete extraction retains non-PASS verdict and unavailable coverage`, async () => {
    const { result } = await collect({ incomplete: true });
    assert.equal(result.artifacts.complete, false);
    assert.equal(result.artifacts.records[0].text, nonPassText);
    assert.equal(JSON.parse(result.artifacts.records[0].text).verdict, 'UNVERIFIABLE_INPUT');
    assert.equal(result.artifacts.records[0].truncated, true);
    assert.ok(result.diagnostics.failures.some(row => row.kind === 'extraction_incomplete'));
    const coverage = collector.buildContextSourceCoverage({ planSources: [], diffText: '', evidence: result });
    assert.ok(coverage.acceptance_evidence_sources.some(row => row.channel === 'artifacts'
      && row.status === 'unavailable' && row.failure_kinds.includes('extraction_incomplete')));
    assert.match(collector.formatVerifierEvidence(result), /UNVERIFIABLE_INPUT/);
  });
}
