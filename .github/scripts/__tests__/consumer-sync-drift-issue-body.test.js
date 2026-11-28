const assert = require('node:assert/strict');
const test = require('node:test');

const {
  compactMarkerPayload,
  countsLine,
  coverageLedger,
  parseIssueMarker,
  formatIssueBody,
  formatIssueComment,
  formatIssueMarker,
  mergeIssueBody,
} = require('../consumer_sync_drift_issue_body');

const report = {
  counts: { drift: 27, missing: 73, errors: 0, obsolete: 0, unmeasured_create_only: 68 },
  unmeasured_create_only: [
    'owner/a: .github/workflows/pr-00-gate.yml',
    'owner/b: .github/workflows/pr-00-gate.yml',
  ],
  top_repo_gaps: [
    { repo: 'owner/a', total: 100, drift: 27, missing: 73, errors: 0, obsolete: 0 },
    { repo: 'owner/b', total: 4, drift: 4, missing: 0, errors: 0, obsolete: 0 },
  ],
  path_prefix_counts: {
    drift: { '.github/workflows': 11, 'scripts/langchain': 16 },
    missing: { '.github/scripts': 60, '.github/actions': 13 },
  },
  follow_up: {
    all_repos_command: 'gh workflow run maint-68-sync-consumer-repos.yml --repo stranske/Workflows --ref main',
    targeted_repos_command: 'gh workflow run maint-68-sync-consumer-repos.yml --repo stranske/Workflows --ref main -f repos=owner/a,owner/b',
  },
  sync_remediation: {
    state: 'pending_sync_prs',
    open_pr_count: 1,
    repo_count: 1,
    latest_open_pr: {
      repo: 'owner/a',
      number: 42,
      branch: 'sync/workflows-abc123',
      url: 'https://github.com/owner/a/pull/42',
    },
    stale_open_pr_count: 0,
    open_prs: [
      {
        repo: 'owner/a',
        number: 42,
        branch: 'sync/workflows-abc123',
        url: 'https://github.com/owner/a/pull/42',
      },
    ],
    lookup_errors: [],
  },
};

test('countsLine renders stable drift counts', () => {
  assert.equal(countsLine(report), 'drift=27, missing=73, errors=0, obsolete=0, unmeasured_create_only=68');
});

test('formatIssueBody includes actionable repo, prefix, and command details', () => {
  const body = formatIssueBody(report, {
    runUrl: 'https://github.com/owner/repo/actions/runs/1',
    runId: '1',
    runNumber: '123',
    updatedAt: '2026-04-26T00:00:00.000Z',
  });

  assert.match(body, /Run #123/);
  assert.match(body, /owner\/a: total=100, drift=27, missing=73/);
  assert.match(body, /\.github\/scripts=60/);
  assert.doesNotMatch(body, /gh workflow run/);
  assert.match(body, /\*\*Coverage:\*\* unmeasured/);
  assert.match(body, /Open sync PRs/);
  assert.match(body, /owner\/a#42: `sync\/workflows-abc123`/);
  assert.match(body, /consumer-sync-drift-report/);
  assert.match(body, /\*\*Transient alert\*\*/);
  assert.match(body, /closes this issue automatically after a clean or fully covered comparison/);
  assert.doesNotMatch(body, /\*\*Durable tracker\*\*/);
  assert.match(body, /<!-- consumer-sync-drift:v1 /);
  assert.match(body, /"schema":"consumer-sync-drift-issue\/v1"/);
  assert.match(body, /"run_id":"1"/);
  assert.match(body, /"missing":73/);
  assert.match(body, /68 positions are not measured \(.github\/workflows\/pr-00-gate.yml\)/);
});

test('formatIssueComment stays compact for existing issue updates', () => {
  const body = formatIssueComment(report, {
    runUrl: 'https://github.com/owner/repo/actions/runs/1',
    runNumber: '124',
  });

  assert.match(body, /Drift still detected in \[run #124\]/);
  assert.match(body, /Counts: drift=27, missing=73, errors=0, obsolete=0, unmeasured_create_only=68/);
  assert.match(body, /Highest-impact repos:/);
  assert.match(body, /Open sync PRs:/);
});

test('compactMarkerPayload exposes the current drift checkpoint', () => {
  const payload = compactMarkerPayload(report, {
    runUrl: 'https://github.com/owner/repo/actions/runs/1',
    runId: '1',
    runNumber: '124',
    updatedAt: '2026-04-26T00:00:00.000Z',
  });

  assert.equal(payload.schema, 'consumer-sync-drift-issue/v1');
  assert.equal(payload.artifact, 'consumer-sync-drift-report');
  assert.equal(payload.run_id, '1');
  assert.deepEqual(payload.counts, { drift: 27, missing: 73, errors: 0, obsolete: 0, unmeasured_create_only: 68 });
  assert.equal(payload.top_repo_gaps.length, 2);
  assert.equal(payload.sync_remediation.state, 'pending_sync_prs');
  assert.equal(payload.sync_remediation.open_pr_count, 1);
  assert.equal(payload.sync_remediation.latest_open_pr.number, 42);
  assert.equal(payload.sync_remediation.stale_open_pr_count, 0);
  assert.equal(payload.sync_remediation.open_prs[0].number, 42);
  assert.equal(payload.follow_up, undefined);
  assert.equal(payload.coverage.measured, false);
  assert.equal(payload.coverage.uncovered, null);
});

test('formatIssueComment suppresses covered-state noise', () => {
  assert.equal(formatIssueComment({ ...report, status: 'covered' }), '');
});

test('formatIssueBody renders coverage details while preserving actionable output', () => {
  const covered = formatIssueBody({
    ...report,
    status: 'covered',
    sync_remediation: {
      ...report.sync_remediation,
      expected_branch: 'sync/workflows-aaaaaaaaaaaa',
      coverage_lease_hours: 36,
    },
  });
  assert.match(covered, /covered by current, unexpired compiler-plan sync PRs/);
  assert.match(covered, /Current plan branch: `sync\/workflows-aaaaaaaaaaaa`/);
  assert.match(covered, /Coverage lease: 36 hours/);

  const actionable = formatIssueBody(report);
  assert.match(actionable, /One or more consumer repos have actionable drift/);
  assert.doesNotMatch(actionable, /Current plan branch:/);
});

test('mergeIssueBody refreshes generated issue bodies', () => {
  const oldBody = formatIssueBody({
    counts: { drift: 1, missing: 0, errors: 0, obsolete: 0 },
  }, {
    runUrl: 'https://github.com/owner/repo/actions/runs/1',
    runId: '1',
    runNumber: '123',
    updatedAt: '2026-04-26T00:00:00.000Z',
  });
  const merged = mergeIssueBody(oldBody, report, {
    runUrl: 'https://github.com/owner/repo/actions/runs/2',
    runId: '2',
    runNumber: '124',
    updatedAt: '2026-04-26T00:05:00.000Z',
  });

  assert.match(merged, /Run #124/);
  assert.match(merged, /Counts:\*\* drift=27, missing=73/);
  assert.match(merged, /"run_id":"2"/);
  assert.doesNotMatch(merged, /"run_id":"1"/);
});

test('mergeIssueBody preserves custom human issue content while updating marker', () => {
  const marker = formatIssueMarker({ counts: { drift: 1, missing: 0, errors: 0, obsolete: 0 } }, {
    runId: '1',
    updatedAt: '2026-04-26T00:00:00.000Z',
  });
  const customBody = `# Human task list\n\n- [ ] Keep this note\n\n${marker}`;
  const merged = mergeIssueBody(customBody, report, {
    runId: '2',
    updatedAt: '2026-04-26T00:05:00.000Z',
  });

  assert.match(merged, /# Human task list/);
  assert.match(merged, /- \[ \] Keep this note/);
  assert.match(merged, /"run_id":"2"/);
  assert.doesNotMatch(merged, /"run_id":"1"/);
});

// --- Coverage ledger (cohesion review A6) -------------------------------------------

const NOW = '2026-11-28T12:00:00.000Z';
const hoursBefore = (hours) => new Date(Date.parse(NOW) - hours * 3600000).toISOString();

function inFlight(repoStates) {
  return {
    status: 'drift',
    counts: { drift: 8, missing: 0, errors: 0, obsolete: 0, unmeasured_create_only: 0 },
    sync_remediation: {
      state: 'drift',
      coverage_lease_hours: 36,
      expected_branch: 'sync/workflows-delivery',
      repo_states: repoStates,
      open_prs: [],
    },
  };
}

const coveredPr = (repo, number) => ({
  state: 'covered',
  pr: { repo, number, branch: 'sync/workflows-delivery' },
});

test('in-flight delivery with every drifting repo covered reports uncovered 0 and no action', () => {
  const report = inFlight({
    'o/a': coveredPr('o/a', 1),
    'o/b': coveredPr('o/b', 2),
    'o/c': { state: 'converged' },
  });
  const body = formatIssueBody(report, { now: NOW });
  assert.match(
    body,
    /\*\*Coverage:\*\* covered by an open delivery PR: 2, uncovered: 0 \(blocking, past the 36h lease: 0; draining, within the lease: 0\)/,
  );
  assert.match(body, /### Required Actions\n- None\./);
  assert.doesNotMatch(body, /gh workflow run/);
  assert.equal(formatIssueComment(report, { now: NOW }), '');
});

test('uncovered drift younger than the lease drains without asking anyone', () => {
  const report = inFlight({
    'o/a': coveredPr('o/a', 1),
    'o/b': { state: 'untracked_drift', reason: 'no open sync PR matches the current compiler plan' },
  });
  const previousMarker = parseIssueMarker(formatIssueBody(report, { now: hoursBefore(10) }));
  assert.equal(previousMarker.coverage.uncovered_since['o/b'], hoursBefore(10));
  const body = formatIssueBody(report, { now: NOW, previousMarker });
  assert.match(body, /covered by an open delivery PR: 1, uncovered: 1 \(blocking, past the 36h lease: 0; draining, within the lease: 1\)/);
  assert.match(body, /- o\/b: untracked_drift, uncovered since .* \(10h, draining\)/);
  assert.match(body, /### Required Actions\n- None\./);
  assert.equal(formatIssueComment(report, { now: NOW, previousMarker }), '');
});

test('uncovered drift older than the lease becomes blocking and names the repo, not a dispatch', () => {
  const report = inFlight({
    'o/a': coveredPr('o/a', 1),
    'o/b': { state: 'untracked_drift', reason: 'no open sync PR matches the current compiler plan' },
  });
  const previousMarker = parseIssueMarker(formatIssueBody(report, { now: hoursBefore(40) }));
  const ledger = coverageLedger(report, { now: NOW, previousMarker });
  assert.equal(ledger.blocking.length, 1);
  assert.equal(ledger.draining.length, 0);
  const body = formatIssueBody(report, { now: NOW, previousMarker });
  assert.match(body, /uncovered: 1 \(blocking, past the 36h lease: 1; draining, within the lease: 0\)/);
  assert.match(body, /- `o\/b`: drift with no delivery PR for the current plan for 40h, although Maint 68 runs daily/);
  assert.doesNotMatch(body, /gh workflow run/);
  // The age survives a further refresh: uncovered_since is carried, not reset.
  assert.equal(parseIssueMarker(body).coverage.uncovered_since['o/b'], hoursBefore(40));
  const comment = formatIssueComment(report, { now: NOW, previousMarker });
  assert.match(comment, /blocking, past the 36h lease: 1/);
});

test('a stale delivery PR is blocking at once and a covered repo drops its age', () => {
  const report = inFlight({
    'o/a': { state: 'stale', pr: { repo: 'o/a', number: 7 } },
    'o/b': coveredPr('o/b', 2),
  });
  const previousMarker = { schema: 'consumer-sync-drift-issue/v1', coverage: { uncovered_since: { 'o/b': hoursBefore(50) } } };
  const ledger = coverageLedger(report, { now: NOW, previousMarker });
  assert.deepEqual(ledger.blocking.map((item) => item.repo), ['o/a']);
  assert.deepEqual(Object.keys(ledger.uncoveredSince), ['o/a']);
  assert.match(formatIssueBody(report, { now: NOW, previousMarker }), /- `o\/a#7`: the delivery PR has not moved/);
});

test('a future or malformed carried timestamp restarts the age at now', () => {
  const report = inFlight({ 'o/b': { state: 'untracked_drift' } });
  for (const bad of ['not-a-date', '2099-01-01T00:00:00Z']) {
    const ledger = coverageLedger(report, {
      now: NOW,
      previousMarker: { coverage: { uncovered_since: { 'o/b': bad } } },
    });
    assert.equal(ledger.uncoveredSince['o/b'], NOW);
    assert.equal(ledger.blocking.length, 0);
  }
});
