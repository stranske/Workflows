const assert = require('node:assert/strict');
const test = require('node:test');

const {
  compactMarkerPayload,
  countsLine,
  formatIssueBody,
  formatIssueComment,
  formatIssueMarker,
  mergeIssueBody,
} = require('../consumer_sync_drift_issue_body');

const report = {
  counts: { drift: 27, missing: 73, errors: 0, obsolete: 0 },
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
  assert.equal(countsLine(report), 'drift=27, missing=73, errors=0, obsolete=0');
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
  assert.match(body, /Top repos first: `gh workflow run maint-68-sync-consumer-repos.yml/);
  assert.match(body, /Open sync PRs/);
  assert.match(body, /owner\/a#42: `sync\/workflows-abc123`/);
  assert.match(body, /consumer-sync-drift-report/);
  assert.match(body, /<!-- consumer-sync-drift:v1 /);
  assert.match(body, /"schema":"consumer-sync-drift-issue\/v1"/);
  assert.match(body, /"run_id":"1"/);
  assert.match(body, /"missing":73/);
});

test('formatIssueComment stays compact for existing issue updates', () => {
  const body = formatIssueComment(report, {
    runUrl: 'https://github.com/owner/repo/actions/runs/1',
    runNumber: '124',
  });

  assert.match(body, /Drift still detected in \[run #124\]/);
  assert.match(body, /Counts: drift=27, missing=73, errors=0, obsolete=0/);
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
  assert.deepEqual(payload.counts, { drift: 27, missing: 73, errors: 0, obsolete: 0 });
  assert.equal(payload.top_repo_gaps.length, 2);
  assert.equal(payload.sync_remediation.state, 'pending_sync_prs');
  assert.equal(payload.sync_remediation.open_pr_count, 1);
  assert.equal(payload.sync_remediation.latest_open_pr.number, 42);
  assert.equal(payload.sync_remediation.stale_open_pr_count, 0);
  assert.equal(payload.sync_remediation.open_prs[0].number, 42);
  assert.equal(payload.follow_up.workflow, 'maint-68-sync-consumer-repos.yml');
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
