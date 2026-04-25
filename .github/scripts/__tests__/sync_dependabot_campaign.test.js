'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildQueueItem,
  collectActiveBotThreads,
  discoverRepoWork,
  findCampaignIssue,
  formatCampaignBody,
  formatCampaignMarker,
  formatDryRunSummary,
  isDependabotPullRequest,
  isSyncPullRequest,
  mergeCampaignState,
  paginateWithRetry,
  parseCampaignMarker,
  replaceCampaignMarker,
  verboseDryRunLoggingEnabled,
} = require('../sync_dependabot_campaign.js');

test('formats and parses campaign marker', () => {
  const state = {
    schema: 'sync-dependabot-campaign/v1',
    updated_at: '2026-04-21T05:52:00Z',
    stats: { items_needing_local_codex: 1 },
    items: [{ id: 'sync-review-comments:stranske/TPP#850:abc', status: 'needs-local-codex' }],
  };

  const marker = formatCampaignMarker(state);
  const parsed = parseCampaignMarker(`body\n\n${marker}`);

  assert.equal(parsed.updated_at, '2026-04-21T05:52:00Z');
  assert.equal(parsed.items[0].id, 'sync-review-comments:stranske/TPP#850:abc');
  assert.equal(parseCampaignMarker('no marker'), null);
});

test('replaceCampaignMarker updates an existing marker in place', () => {
  const oldState = {
    schema: 'sync-dependabot-campaign/v1',
    updated_at: 'old',
    stats: {},
    items: [],
  };
  const newState = {
    schema: 'sync-dependabot-campaign/v1',
    updated_at: 'new',
    stats: {},
    items: [],
  };

  const body = `prefix\n${formatCampaignMarker(oldState)}\nsuffix`;
  const updated = replaceCampaignMarker(body, newState);

  assert.equal(parseCampaignMarker(updated).updated_at, 'new');
  assert.match(updated, /^prefix/);
  assert.match(updated, /suffix$/);
});

test('detects sync and dependabot pull requests', () => {
  assert.equal(isSyncPullRequest({ head: { ref: 'sync/workflows-abc123' } }), true);
  assert.equal(isSyncPullRequest({ title: 'chore: sync workflow templates' }), true);
  assert.equal(isSyncPullRequest({ labels: [{ name: 'sync' }] }), true);
  assert.equal(isSyncPullRequest({ head: { ref: 'codex/issue-1' } }), false);

  assert.equal(isDependabotPullRequest({ user: { login: 'dependabot[bot]' } }), true);
  assert.equal(isDependabotPullRequest({ head: { ref: 'dependabot/npm/lodash-5' } }), true);
  assert.equal(isDependabotPullRequest({ user: { login: 'stranske' } }), false);
});

test('collectActiveBotThreads keeps active bot review threads only', () => {
  const threads = collectActiveBotThreads([
    {
      id: 'thread-1',
      isResolved: false,
      isOutdated: false,
      path: '.github/workflows/ci.yml',
      line: 12,
      comments: {
        nodes: [
          {
            id: 'comment-1',
            url: 'https://github.test/comment-1',
            body: 'Please tighten this condition.',
            author: { login: 'Copilot' },
            createdAt: '2026-04-20T10:00:00Z',
          },
        ],
      },
    },
    {
      id: 'thread-2',
      isResolved: true,
      path: '.github/workflows/ci.yml',
      comments: { nodes: [{ body: 'resolved', author: { login: 'Copilot' } }] },
    },
    {
      id: 'thread-3',
      isResolved: false,
      isOutdated: false,
      path: '.agents/generated.md',
      comments: { nodes: [{ body: 'ignored path', author: { login: 'Copilot' } }] },
    },
    {
      id: 'thread-4',
      isResolved: false,
      isOutdated: false,
      path: 'README.md',
      comments: { nodes: [{ body: 'human comment', author: { login: 'stranske' } }] },
    },
  ]);

  assert.equal(threads.length, 1);
  assert.equal(threads[0].id, 'thread-1');
  assert.equal(threads[0].path, '.github/workflows/ci.yml');
  assert.equal(threads[0].author, 'Copilot');
});

test('buildQueueItem creates stable PR-scoped work items', () => {
  const item = buildQueueItem({
    repoFullName: 'stranske/TPP',
    defaultOwner: 'stranske',
    now: '2026-04-21T05:52:00Z',
    pr: {
      number: 850,
      title: 'chore: sync workflow templates',
      html_url: 'https://github.com/stranske/TPP/pull/850',
      head: { ref: 'sync/workflows-abc123', sha: 'abcdef123456' },
      base: { ref: 'main' },
    },
    threads: [
      {
        id: 'thread-1',
        path: '.github/workflows/ci.yml',
        line: 12,
        url: 'https://github.test/comment-1',
        author: 'Copilot',
        body_preview: 'Please tighten this condition.',
        comments_count: 1,
      },
    ],
  });

  assert.match(item.id, /^sync-review-comments:stranske\/TPP#850:/);
  assert.equal(item.status, 'needs-local-codex');
  assert.equal(item.source_repo, 'stranske/Workflows');
  assert.equal(item.preferred_workdir, 'Workflows');
  assert.equal(item.review_thread_count, 1);
});

test('mergeCampaignState preserves active items when repo discovery fails', () => {
  const active = {
    id: 'sync-review-comments:stranske/TPP#850:abc',
    status: 'needs-local-codex',
    repo: 'stranske/TPP',
    pr_number: 850,
    updated_at: '2026-04-21T05:30:00Z',
  };

  const state = mergeCampaignState(
    { items: [active] },
    [],
    '2026-04-21T05:52:00Z',
    { reposRequested: 1, reposChecked: 0, reposFailed: 1, failedRepos: ['stranske/TPP'] },
  );

  assert.equal(state.items[0].status, 'needs-local-codex');
  assert.equal(state.items[0].preserved_after_scan_error_at, '2026-04-21T05:52:00Z');
  assert.equal(state.stats.items_needing_local_codex, 1);
});

test('mergeCampaignState preserves claims, expires old leases, and stales missing items', () => {
  const futureClaim = {
    id: 'sync-review-comments:stranske/TPP#850:abc',
    status: 'local-codex-claimed',
    repo: 'stranske/TPP',
    pr_number: 850,
    lease: { owner: 'host:123', expires_at: '2026-04-21T06:30:00Z' },
    attempts: 1,
    updated_at: '2026-04-21T05:30:00Z',
  };
  const expiredClaim = {
    id: 'sync-review-comments:stranske/TPP#851:def',
    status: 'local-codex-claimed',
    repo: 'stranske/TPP',
    pr_number: 851,
    lease: { owner: 'host:123', expires_at: '2026-04-21T05:00:00Z' },
    attempts: 1,
    updated_at: '2026-04-21T05:30:00Z',
  };
  const stalePrevious = {
    id: 'sync-review-comments:stranske/TPP#849:old',
    status: 'needs-local-codex',
    repo: 'stranske/TPP',
    pr_number: 849,
    updated_at: '2026-04-21T05:00:00Z',
  };

  const state = mergeCampaignState(
    { items: [futureClaim, expiredClaim, stalePrevious] },
    [
      { ...futureClaim, status: 'needs-local-codex', review_thread_count: 2 },
      { ...expiredClaim, status: 'needs-local-codex', review_thread_count: 1 },
    ],
    '2026-04-21T05:52:00Z',
    { reposRequested: 1, reposChecked: 1 },
  );

  const byId = new Map(state.items.map((item) => [item.id, item]));
  assert.equal(byId.get(futureClaim.id).status, 'local-codex-claimed');
  assert.equal(byId.get(expiredClaim.id).status, 'needs-local-codex');
  assert.equal(byId.get(stalePrevious.id).status, 'stale');
  assert.equal(state.stats.items_needing_local_codex, 1);
  assert.equal(state.stats.items_claimed, 1);
});

test('formatCampaignBody renders queue rows and marker', () => {
  const state = mergeCampaignState(
    {},
    [
      {
        id: 'dependabot-review-comments:stranske/App#10:abc',
        status: 'needs-local-codex',
        kind: 'dependabot-review-comments',
        classification: 'dependabot',
        repo: 'stranske/App',
        pr_number: 10,
        pr_title: 'Bump package',
        pr_url: 'https://github.com/stranske/App/pull/10',
        source_repo: 'stranske/App',
        preferred_workdir: 'App',
        review_thread_count: 1,
        review_threads: [],
      },
    ],
    '2026-04-21T05:52:00Z',
    { reposRequested: 1, reposChecked: 1, dependabotPrsOpen: 1 },
  );

  const body = formatCampaignBody(state);

  assert.match(body, /Sync\/Dependabot Campaign Queue/);
  assert.match(body, /stranske\/App#10/);
  assert.equal(parseCampaignMarker(body).stats.items_needing_local_codex, 1);
});

test('paginateWithRetry uses the paginated GitHub API', async () => {
  const endpoint = function listForRepo() {};
  const github = {
    paginate: async (method, params) => {
      assert.equal(method, endpoint);
      assert.deepEqual(params, { owner: 'stranske', repo: 'Workflows', per_page: 100 });
      return [{ number: 101 }, { number: 102 }];
    },
  };

  const items = await paginateWithRetry({
    github,
    core: console,
    method: () => endpoint,
    params: { owner: 'stranske', repo: 'Workflows', per_page: 100 },
    label: 'test pagination',
  });

  assert.deepEqual(items.map((item) => item.number), [101, 102]);
});

test('discoverRepoWork scans paginated PR results', async () => {
  const pullsList = function pullsList() {};
  const calls = [];
  const github = {
    rest: { pulls: { list: pullsList } },
    paginate: async (method, params) => {
      calls.push({ method, params });
      return [
        {
          number: 101,
          title: 'human PR',
          user: { login: 'stranske' },
          head: { ref: 'feature/human', sha: 'human-sha' },
        },
        {
          number: 102,
          title: 'Bump package',
          html_url: 'https://github.com/stranske/App/pull/102',
          user: { login: 'dependabot[bot]' },
          head: { ref: 'dependabot/npm/pkg-2', sha: 'dep-sha' },
          base: { ref: 'main' },
        },
      ];
    },
    graphql: async (_query, variables) => {
      assert.equal(variables.number, 102);
      return {
        repository: {
          pullRequest: {
            reviewThreads: {
              pageInfo: { hasNextPage: false, endCursor: null },
              nodes: [
                {
                  id: 'thread-102',
                  isResolved: false,
                  isOutdated: false,
                  path: 'package.json',
                  line: 12,
                  comments: {
                    nodes: [
                      {
                        id: 'comment-102',
                        url: 'https://github.test/comment-102',
                        body: 'Please update the lockfile.',
                        author: { login: 'Copilot' },
                      },
                    ],
                  },
                },
              ],
            },
          },
        },
      };
    },
  };

  const result = await discoverRepoWork({
    github,
    core: console,
    repoEntry: { owner: 'stranske', repo: 'App', fullName: 'stranske/App' },
    now: '2026-04-21T05:52:00Z',
    defaultOwner: 'stranske',
  });

  assert.equal(calls[0].method, pullsList);
  assert.equal(calls[0].params.per_page, 100);
  assert.equal(result.dependabotPrsOpen, 1);
  assert.equal(result.items.length, 1);
  assert.equal(result.items[0].pr_number, 102);
});

test('findCampaignIssue only returns marker-backed campaign issues', async () => {
  const issueList = function issueList() {};
  const markerBody = formatCampaignBody(mergeCampaignState({}, [], '2026-04-21T05:52:00Z'));
  const github = {
    rest: {
      issues: {
        listForRepo: issueList,
        get: async ({ issue_number: issueNumber }) => ({
          data: {
            number: issueNumber,
            body: issueNumber === 12 ? 'matching title without marker' : markerBody,
            html_url: `https://github.test/issues/${issueNumber}`,
          },
        }),
      },
    },
    paginate: async (method, params) => {
      assert.equal(method, issueList);
      assert.equal(params.per_page, 100);
      return [
        { number: 12, title: 'Sync/Dependabot campaign queue - old', pull_request: null },
        { number: 13, title: 'Sync/Dependabot campaign queue', pull_request: null },
      ];
    },
  };

  const issue = await findCampaignIssue(github, 'stranske', 'Workflows', console);

  assert.equal(issue.number, 13);
});

test('findCampaignIssue does not fall back to unmarked title matches', async () => {
  const github = {
    rest: {
      issues: {
        listForRepo: function issueList() {},
        get: async ({ issue_number: issueNumber }) => ({
          data: { number: issueNumber, body: 'no marker' },
        }),
      },
    },
    paginate: async () => [
      { number: 12, title: 'Sync/Dependabot campaign queue', pull_request: null },
    ],
  };

  const issue = await findCampaignIssue(github, 'stranske', 'Workflows', console);

  assert.equal(issue, null);
});

test('dry-run summary avoids logging generated issue body by default', () => {
  const state = mergeCampaignState({}, [], '2026-04-21T05:52:00Z', {
    reposRequested: 2,
    reposChecked: 1,
    reposFailed: 1,
  });
  const summary = formatDryRunSummary(state);

  assert.match(summary, /Campaign issue update suppressed/);
  assert.match(summary, /repos_checked=1\/2/);
  assert.doesNotMatch(summary, /sync-dependabot-campaign:v1/);
  assert.equal(verboseDryRunLoggingEnabled({}), false);
  assert.equal(verboseDryRunLoggingEnabled({ ACTIONS_STEP_DEBUG: 'true' }), true);
  assert.equal(verboseDryRunLoggingEnabled({ RUNNER_DEBUG: '1' }), true);
  assert.equal(verboseDryRunLoggingEnabled({ SYNC_DEPENDABOT_CAMPAIGN_DEBUG_BODY: 'true' }), true);
});
