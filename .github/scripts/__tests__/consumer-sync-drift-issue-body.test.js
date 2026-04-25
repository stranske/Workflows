const assert = require('node:assert/strict');
const test = require('node:test');

const {
  countsLine,
  formatIssueBody,
  formatIssueComment,
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
};

test('countsLine renders stable drift counts', () => {
  assert.equal(countsLine(report), 'drift=27, missing=73, errors=0, obsolete=0');
});

test('formatIssueBody includes actionable repo, prefix, and command details', () => {
  const body = formatIssueBody(report, {
    runUrl: 'https://github.com/owner/repo/actions/runs/1',
    runNumber: '123',
  });

  assert.match(body, /Run #123/);
  assert.match(body, /owner\/a: total=100, drift=27, missing=73/);
  assert.match(body, /\.github\/scripts=60/);
  assert.match(body, /Top repos first: `gh workflow run maint-68-sync-consumer-repos.yml/);
  assert.match(body, /consumer-sync-drift-report/);
});

test('formatIssueComment stays compact for existing issue updates', () => {
  const body = formatIssueComment(report, {
    runUrl: 'https://github.com/owner/repo/actions/runs/1',
    runNumber: '124',
  });

  assert.match(body, /Drift still detected in \[run #124\]/);
  assert.match(body, /Counts: drift=27, missing=73, errors=0, obsolete=0/);
  assert.match(body, /Highest-impact repos:/);
});
