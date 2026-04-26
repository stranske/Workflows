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
  formatCampaignRunSummaryMarkdown,
  formatDryRunSummary,
  isDependabotPullRequest,
  isSyncPullRequest,
  mergeCampaignState,
  paginateWithRetry,
  parseCampaignMarker,
  replaceCampaignMarker,
  verboseDryRunLoggingEnabled,
  validateCampaignState,
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
    currentSyncHash: 'abc123',
  });

  assert.match(item.id, /^sync-review-comments:stranske\/TPP#850:/);
  assert.equal(item.status, 'needs-local-codex');
  assert.equal(item.source_repo, 'stranske/Workflows');
  assert.equal(item.preferred_workdir, 'Workflows');
  assert.deepEqual(item.source_sync, {
    schema: 'sync-dependabot-campaign-source-sync/v1',
    current_sync_hash: 'abc123',
    pr_sync_hash: 'abc123',
    status: 'current',
  });
  assert.match(item.review_signature, /^[0-9a-f]{20}$/);
  assert.match(item.source_review_key, /^stranske\/Workflows:sync:[0-9a-f]{20}$/);
  assert.equal(item.review_thread_count, 1);
});

test('buildQueueItem marks old sync branches as superseded by the current template hash', () => {
  const item = buildQueueItem({
    repoFullName: 'stranske/TPP',
    defaultOwner: 'stranske',
    now: '2026-04-21T05:52:00Z',
    currentSyncHash: 'newhash123456',
    pr: {
      number: 851,
      title: 'chore: sync workflow templates',
      html_url: 'https://github.com/stranske/TPP/pull/851',
      head: { ref: 'sync/workflows-oldhash123456', sha: 'abcdef123456' },
      base: { ref: 'main' },
    },
    threads: [
      {
        id: 'thread-1',
        path: '.github/scripts/bot_comment_auth_coverage.js',
        line: 12,
        url: 'https://github.test/comment-1',
        author: 'Copilot',
        body_preview: 'Please tighten this condition.',
        comments_count: 1,
      },
    ],
  });
  const state = mergeCampaignState(
    {},
    [item],
    '2026-04-21T05:52:00Z',
    { reposRequested: 1, reposChecked: 1, currentSyncHash: 'newhash123456' },
  );
  const body = formatCampaignBody(state);
  const marker = parseCampaignMarker(formatCampaignMarker(state));

  assert.equal(state.current_sync_hash, 'newhash123456');
  assert.equal(item.source_sync.status, 'superseded');
  assert.equal(item.source_sync.pr_sync_hash, 'oldhash123456');
  assert.equal(state.items[0].status, 'local-codex-superseded-sync-candidate');
  assert.equal(state.items[0].local_codex_queue_state, 'superseded-sync-candidate');
  assert.equal(state.items[0].local_codex_actionable, false);
  assert.equal(state.items[0].local_codex_claimable, false);
  assert.equal(state.stats.items_needing_local_codex, 0);
  assert.equal(state.stats.items_actionable_local_codex, 0);
  assert.equal(state.stats.items_claimable_local_codex, 0);
  assert.equal(state.stats.items_superseded_sync_candidates, 1);
  assert.equal(state.stats.status_counts['local-codex-superseded-sync-candidate'], 1);
  assert.deepEqual(state.stats.local_codex_queue_state_counts, {
    'superseded-sync-candidate': 1,
  });
  assert.deepEqual(state.stats.source_sync_status_counts, { superseded: 1 });
  assert.equal(marker.current_sync_hash, 'newhash123456');
  assert.deepEqual(marker.stats.source_sync_status_counts, { superseded: 1 });
  assert.equal(marker.stats.items_superseded_sync_candidates, 1);
  assert.equal(marker.stats.marker_items_retained, 0);
  assert.equal(marker.stats.marker_items_omitted, 1);
  assert.deepEqual(marker.items, []);
  assert.match(body, /No local Codex work is queued/);
  assert.match(body, /Current sync hash: newhash123456/);
  assert.match(body, /Superseded sync candidates: 1/);
  assert.match(body, /Source sync states: superseded=1/);
  assert.match(body, /Source sync state: superseded/);
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
  const body = formatCampaignBody(state);
  const marker = parseCampaignMarker(formatCampaignMarker(state));
  const validation = validateCampaignState(state);

  assert.equal(byId.get(futureClaim.id).status, 'local-codex-claimed');
  assert.equal(byId.get(expiredClaim.id).status, 'needs-local-codex');
  assert.equal(byId.get(stalePrevious.id).status, 'stale');
  assert.equal(state.stats.items_needing_local_codex, 1);
  assert.equal(state.stats.items_claimed, 1);
  assert.deepEqual(state.stats.local_codex_claims, {
    count: 1,
    leases_with_expires_at: 1,
    missing_lease_count: 0,
    next_expires_at: '2026-04-21T06:30:00Z',
    items: [
      {
        id: futureClaim.id,
        repo: 'stranske/TPP',
        pr_number: 850,
        claimed_at: '',
        lease_owner: 'host:123',
        lease_expires_at: '2026-04-21T06:30:00Z',
      },
    ],
  });
  assert.equal(marker.stats.local_codex_claims.next_expires_at, '2026-04-21T06:30:00Z');
  assert.equal(marker.items[0].local_codex_queue_state, 'claimed');
  assert.equal(marker.items[0].local_codex_actionable, false);
  assert.equal(validation.status, 'pass');
  assert.match(body, /Claimed local Codex items: 1/);
  assert.match(body, /Next claim lease expires: 2026-04-21T06:30:00Z/);
});

test('mergeCampaignState flags repeated source-fixed review signatures without hiding the item', () => {
  const now = '2026-04-21T05:52:00Z';
  const finished = buildQueueItem({
    repoFullName: 'stranske/TPP',
    defaultOwner: 'stranske',
    now: '2026-04-21T05:20:00Z',
    pr: {
      number: 850,
      title: 'chore: sync workflow templates',
      html_url: 'https://github.com/stranske/TPP/pull/850',
      head: { ref: 'sync/workflows-old', sha: 'old-sha' },
      base: { ref: 'main' },
    },
    threads: [
      {
        id: 'thread-old',
        path: '.github/scripts/bot_comment_auth_coverage.js',
        line: 12,
        url: 'https://github.test/thread-old',
        author: 'copilot-pull-request-reviewer',
        body_preview: 'Please tighten this auth coverage condition.',
        comments_count: 1,
      },
    ],
  });
  const repeated = buildQueueItem({
    repoFullName: 'stranske/TPP',
    defaultOwner: 'stranske',
    now,
    pr: {
      number: 851,
      title: 'chore: sync workflow templates',
      html_url: 'https://github.com/stranske/TPP/pull/851',
      head: { ref: 'sync/workflows-new', sha: 'new-sha' },
      base: { ref: 'main' },
    },
    threads: [
      {
        id: 'thread-new',
        path: '.github/scripts/bot_comment_auth_coverage.js',
        line: 30,
        url: 'https://github.test/thread-new',
        author: 'copilot-pull-request-reviewer',
        body_preview: 'Please tighten this auth coverage condition.',
        comments_count: 1,
      },
    ],
  });

  const state = mergeCampaignState(
    {
      items: [
        {
          ...finished,
          status: 'local-codex-finished',
          finished_at: '2026-04-21T05:30:00Z',
          result: {
            exit_code: 0,
            summary: 'Handled through the Workflows source path.',
          },
        },
      ],
    },
    [repeated],
    now,
    { reposRequested: 1, reposChecked: 1 },
  );
  const repeatedItem = state.items.find((item) => item.id === repeated.id);
  const marker = parseCampaignMarker(formatCampaignMarker(state));
  const markerItem = marker.items.find((item) => item.id === repeated.id);
  const body = formatCampaignBody(state);

  assert.equal(repeatedItem.status, 'local-codex-source-fixed-candidate');
  assert.equal(repeatedItem.local_codex_queue_state, 'source-fixed-candidate');
  assert.equal(repeatedItem.local_codex_actionable, false);
  assert.equal(repeatedItem.local_codex_claimable, false);
  assert.equal(repeatedItem.source_fixed_candidate.matching_item_id, finished.id);
  assert.equal(repeatedItem.source_fixed_candidate.finished_at, '2026-04-21T05:30:00Z');
  assert.equal(state.source_review_history.length, 1);
  assert.equal(state.source_review_history[0].source_review_key, finished.source_review_key);
  assert.equal(state.stats.items_needing_local_codex, 0);
  assert.equal(state.stats.items_actionable_local_codex, 0);
  assert.equal(state.stats.items_source_fixed_candidates, 1);
  assert.equal(state.stats.status_counts['local-codex-source-fixed-candidate'], 1);
  assert.deepEqual(state.stats.local_codex_queue_state_counts, {
    'source-fixed-candidate': 1,
    finished: 1,
  });
  assert.equal(markerItem, undefined);
  assert.equal(marker.stats.items_source_fixed_candidates, 1);
  assert.equal(marker.stats.marker_items_retained, 0);
  assert.equal(marker.stats.marker_items_omitted, 2);
  assert.equal(marker.source_review_history[0].matching_item_id, finished.id);
  assert.match(body, /No local Codex work is queued/);
  assert.match(body, /Source-fixed candidates: 1/);
  assert.match(body, /Prior source-fix match:/);
});

test('mergeCampaignState marks finished local results without published source changes', () => {
  const now = '2026-04-21T06:52:00Z';
  const state = mergeCampaignState(
    {
      items: [
        {
          id: 'sync-review-comments:stranske/TPP#902:finished',
          status: 'local-codex-finished',
          kind: 'sync-review-comments',
          classification: 'sync',
          repo: 'stranske/TPP',
          pr_number: 902,
          pr_title: 'chore: sync workflow templates',
          pr_url: 'https://github.com/stranske/TPP/pull/902',
          source_repo: 'stranske/Workflows',
          source_sync: {
            schema: 'sync-dependabot-campaign-source-sync/v1',
            current_sync_hash: 'current',
            pr_sync_hash: 'old',
            status: 'superseded',
          },
          result: {
            exit_code: 0,
            summary: 'Implemented locally but did not commit or push because the worktree was dirty.',
          },
          finished_at: now,
          updated_at: now,
        },
      ],
    },
    [],
    now,
    { reposRequested: 1, reposChecked: 1 },
  );

  const item = state.items[0];
  const marker = parseCampaignMarker(formatCampaignMarker(state));
  const body = formatCampaignBody(state);
  const runSummary = formatCampaignRunSummaryMarkdown(state, {
    html_url: 'https://github.com/stranske/Workflows/issues/1836',
  });

  assert.equal(item.local_codex_result_state, 'unpublished-source-work');
  assert.equal(state.stats.items_unpublished_source_results, 1);
  assert.equal(marker.stats.items_unpublished_source_results, 1);
  assert.equal(marker.items[0].local_codex_result_state, 'unpublished-source-work');
  assert.equal(validateCampaignState(state).status, 'pass');
  assert.match(body, /Finished local results without published source changes: 1/);
  assert.match(body, /Local result state: unpublished-source-work/);
  assert.match(runSummary, /Finished local results without published source changes: 1/);
});

test('mergeCampaignState matches source-fixed candidates from compact retained history', () => {
  const now = '2026-04-21T06:52:00Z';
  const repeated = buildQueueItem({
    repoFullName: 'stranske/TPP',
    defaultOwner: 'stranske',
    now,
    pr: {
      number: 852,
      title: 'chore: sync workflow templates',
      html_url: 'https://github.com/stranske/TPP/pull/852',
      head: { ref: 'sync/workflows-new', sha: 'new-sha' },
      base: { ref: 'main' },
    },
    threads: [
      {
        id: 'thread-new',
        path: '.github/scripts/bot_comment_auth_coverage.js',
        line: 30,
        url: 'https://github.test/thread-new',
        author: 'copilot-pull-request-reviewer',
        body_preview: 'Please tighten this auth coverage condition.',
        comments_count: 1,
      },
    ],
  });
  const state = mergeCampaignState(
    {
      source_review_history: [
        {
          source_review_key: repeated.source_review_key,
          review_signature: repeated.review_signature,
          matching_item_id: 'sync-review-comments:stranske/TPP#850:old',
          matching_pr_url: 'https://github.com/stranske/TPP/pull/850',
          finished_at: '2026-04-21T05:30:00Z',
          result_summary: 'Handled through the Workflows source path.',
        },
      ],
      items: Array.from({ length: 3 }, (_value, index) => ({
        id: `active-${index}`,
        status: 'needs-local-codex',
        repo: 'stranske/Other',
        pr_number: index + 1,
      })),
    },
    [repeated],
    now,
    { reposRequested: 1, reposChecked: 1, maxRetainedItems: 1 },
  );
  const repeatedItem = state.items.find((item) => item.id === repeated.id);

  assert.equal(repeatedItem.source_fixed_candidate.matching_item_id, 'sync-review-comments:stranske/TPP#850:old');
  assert.equal(state.source_review_history.length, 1);
  assert.equal(state.items.some((item) => item.status === 'local-codex-finished'), false);
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

test('formatCampaignBody keeps source-fixed candidates out of the visible local queue', () => {
  const state = {
    schema: 'sync-dependabot-campaign/v1',
    updated_at: '2026-04-21T05:52:00Z',
    stats: {
      repos_requested: 1,
      repos_checked: 1,
      active_review_threads: 3,
      items_needing_local_codex: 1,
      items_actionable_local_codex: 1,
      items_source_fixed_candidates: 1,
      items_superseded_sync_candidates: 0,
      status_counts: { 'needs-local-codex': 2 },
    },
    items: [
      {
        id: 'sync-review-comments:stranske/App#22:abc',
        status: 'needs-local-codex',
        kind: 'sync-review-comments',
        classification: 'sync',
        repo: 'stranske/App',
        pr_number: 22,
        pr_title: 'source fixed already',
        pr_url: 'https://github.com/stranske/App/pull/22',
        source_repo: 'stranske/Workflows',
        preferred_workdir: 'Workflows',
        review_thread_count: 2,
        source_fixed_candidate: {
          matching_item_id: 'sync-review-comments:stranske/App#20:old',
          matching_pr_url: 'https://github.com/stranske/App/pull/20',
          finished_at: '2026-04-21T05:30:00Z',
          result_summary: 'Handled in Workflows source.',
        },
        review_threads: [],
      },
      {
        id: 'sync-review-comments:stranske/App#23:def',
        status: 'needs-local-codex',
        kind: 'sync-review-comments',
        classification: 'sync',
        repo: 'stranske/App',
        pr_number: 23,
        pr_title: 'needs source work',
        pr_url: 'https://github.com/stranske/App/pull/23',
        source_repo: 'stranske/Workflows',
        preferred_workdir: 'Workflows',
        review_thread_count: 1,
        review_threads: [],
      },
    ],
  };

  const body = formatCampaignBody(state);

  assert.equal(state.stats.items_needing_local_codex, 1);
  assert.equal(state.stats.items_source_fixed_candidates, 1);
  assert.match(body, /Items needing local Codex: 1/);
  assert.match(body, /Source-fixed candidates: 1/);
  assert.match(body, /\| needs-local-codex \| \[stranske\/App#23\]/);
  assert.doesNotMatch(body, /\| needs-local-codex \| \[stranske\/App#22\]/);
  assert.match(body, /### stranske\/App#22/);
});

test('formatCampaignBody keeps superseded sync candidates out of the visible local queue', () => {
  const state = {
    schema: 'sync-dependabot-campaign/v1',
    updated_at: '2026-04-21T05:52:00Z',
    stats: {
      repos_requested: 1,
      repos_checked: 1,
      active_review_threads: 2,
      items_needing_local_codex: 1,
      items_actionable_local_codex: 1,
      items_source_fixed_candidates: 0,
      items_superseded_sync_candidates: 1,
      status_counts: { 'needs-local-codex': 2 },
    },
    items: [
      {
        id: 'sync-review-comments:stranske/App#22:abc',
        status: 'needs-local-codex',
        kind: 'sync-review-comments',
        classification: 'sync',
        repo: 'stranske/App',
        pr_number: 22,
        pr_title: 'old sync branch',
        pr_url: 'https://github.com/stranske/App/pull/22',
        source_repo: 'stranske/Workflows',
        preferred_workdir: 'Workflows',
        source_sync: {
          schema: 'sync-dependabot-campaign-source-sync/v1',
          current_sync_hash: 'newhash',
          pr_sync_hash: 'oldhash',
          status: 'superseded',
        },
        review_thread_count: 1,
        review_threads: [],
      },
      {
        id: 'sync-review-comments:stranske/App#23:def',
        status: 'needs-local-codex',
        kind: 'sync-review-comments',
        classification: 'sync',
        repo: 'stranske/App',
        pr_number: 23,
        pr_title: 'current sync branch',
        pr_url: 'https://github.com/stranske/App/pull/23',
        source_repo: 'stranske/Workflows',
        preferred_workdir: 'Workflows',
        source_sync: {
          schema: 'sync-dependabot-campaign-source-sync/v1',
          current_sync_hash: 'newhash',
          pr_sync_hash: 'newhash',
          status: 'current',
        },
        review_thread_count: 1,
        review_threads: [],
      },
    ],
  };

  const body = formatCampaignBody(state);

  assert.match(body, /Items needing local Codex: 1/);
  assert.match(body, /Superseded sync candidates: 1/);
  assert.match(body, /\| needs-local-codex \| \[stranske\/App#23\]/);
  assert.doesNotMatch(body, /\| needs-local-codex \| \[stranske\/App#22\]/);
  assert.match(body, /### stranske\/App#22/);
  assert.match(body, /Source sync state: superseded/);
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

test('findCampaignIssue falls back to active campaign labels', async () => {
  const markerBody = formatCampaignBody(mergeCampaignState({}, [], '2026-04-21T05:52:00Z'));
  const github = {
    rest: {
      issues: {
        listForRepo: function issueList() {},
        get: async ({ issue_number: issueNumber }) => ({
          data: {
            number: issueNumber,
            title: 'Sync/Dependabot campaign queue',
            body: markerBody,
            labels: [
              { name: 'campaign:sync-dependabot' },
              { name: 'campaign:active' },
            ],
          },
        }),
      },
    },
    paginate: async (method, params) => {
      if (params.labels === 'campaign:sync-dependabot,campaign:active') {
        return [
          {
            number: 1836,
            title: 'Sync/Dependabot campaign queue',
            pull_request: null,
            labels: [
              { name: 'campaign:sync-dependabot' },
              { name: 'campaign:active' },
            ],
          },
        ];
      }
      return [];
    },
  };

  const issue = await findCampaignIssue(github, 'stranske', 'Workflows', console);

  assert.equal(issue.number, 1836);
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

test('formats campaign run summary as compact artifact markdown', () => {
  const claimed = {
    id: 'sync-review-comments:stranske/App#21:claimed',
    status: 'local-codex-claimed',
    kind: 'sync-review-comments',
    classification: 'sync',
    repo: 'stranske/App',
    pr_number: 21,
    lease: { owner: 'host:123', expires_at: '2026-04-21T06:30:00Z' },
    review_thread_count: 1,
    review_threads: [],
  };
  const state = mergeCampaignState(
    { items: [claimed] },
    [
      { ...claimed, status: 'needs-local-codex' },
      {
        id: 'sync-review-comments:stranske/App#22:abc',
        status: 'needs-local-codex',
        kind: 'sync-review-comments',
        classification: 'sync',
        repo: 'stranske/App',
        pr_number: 22,
        review_thread_count: 2,
        review_threads: [],
      },
    ],
    '2026-04-21T05:52:00Z',
    { runId: 12345, reposRequested: 3, reposChecked: 2, reposFailed: 1, syncPrsOpen: 1 },
  );
  state.errors = [{ repo: 'stranske/Broken', error: 'GraphQL rate limit boundary hit' }];

  const summary = formatCampaignRunSummaryMarkdown(state, {
    html_url: 'https://github.com/stranske/Workflows/issues/99',
  });

  assert.match(summary, /Sync\/Dependabot Campaign Run/);
  assert.match(summary, /Run ID: 12345/);
  assert.match(summary, /Campaign issue: https:\/\/github.com\/stranske\/Workflows\/issues\/99/);
  assert.match(summary, /Repos checked: 2\/3/);
  assert.match(summary, /Items needing local Codex: 1/);
  assert.match(summary, /Actionable local Codex items: 1/);
  assert.match(summary, /Claimable local Codex items: 1/);
  assert.match(summary, /Items claimed: 1/);
  assert.match(summary, /Next claim lease expires: 2026-04-21T06:30:00Z/);
  assert.match(summary, /State validation: pass/);
  assert.match(summary, /stranske\/Broken: GraphQL rate limit boundary hit/);
});

test('validates campaign item stats against retained queue state', () => {
  const state = {
    schema: 'sync-dependabot-campaign/v1',
    stats: {
      items_needing_local_codex: 2,
      items_claimable_local_codex: 2,
      items_claimed: 0,
      items_finished: 0,
      items_blocked: 0,
      status_counts: { 'needs-local-codex': 2 },
      source_sync_status_counts: { current: 1 },
    },
    items: [
      { id: 'one', status: 'needs-local-codex' },
      {
        id: 'two',
        status: 'local-codex-finished',
        local_codex_queue_state: 'claimed',
        local_codex_actionable: true,
        local_codex_claimable: true,
      },
    ],
  };

  const validation = validateCampaignState(state);

  assert.equal(validation.status, 'warning');
  assert.ok(validation.blockers.includes('stats-mismatch-items_needing_local_codex'));
  assert.ok(validation.blockers.includes('stats-mismatch-items_claimable_local_codex'));
  assert.ok(validation.blockers.includes('stats-mismatch-items_finished'));
  assert.ok(validation.blockers.includes('status-count-mismatch-local-codex-finished'));
  assert.ok(validation.blockers.includes('local-codex-queue-state-count-mismatch-actionable'));
  assert.ok(validation.blockers.includes('local-codex-queue-state-count-mismatch-finished'));
  assert.ok(validation.blockers.includes('source-sync-status-count-mismatch-current'));
  assert.ok(validation.blockers.includes('item-local-codex-queue-state-annotation-mismatch'));
  assert.ok(validation.blockers.includes('item-local-codex-actionable-annotation-mismatch'));
  assert.ok(validation.blockers.includes('item-local-codex-claimable-annotation-mismatch'));
});

test('formatCampaignBody remains below GitHub issue body limit for large queues', () => {
  const items = Array.from({ length: 60 }, (_, index) => ({
    id: `sync-review-comments:stranske/App#${index + 1}:abc${index}`,
    status: 'needs-local-codex',
    kind: 'sync-review-comments',
    classification: 'sync',
    repo: 'stranske/App',
    pr_number: index + 1,
    pr_title: 'chore: sync workflow templates',
    pr_url: `https://github.com/stranske/App/pull/${index + 1}`,
    source_repo: 'stranske/Workflows',
    preferred_workdir: 'Workflows',
    review_thread_count: 4,
    review_threads: Array.from({ length: 4 }, (_, threadIndex) => ({
      id: `thread-${index}-${threadIndex}`,
      path: '.github/scripts/example.js',
      line: 100 + threadIndex,
      url: `https://github.test/thread-${index}-${threadIndex}`,
      author: 'copilot-pull-request-reviewer',
      body_preview: 'A'.repeat(400),
      comments_count: 1,
      bot_comments_count: 1,
    })),
  }));
  const state = mergeCampaignState(
    {},
    items,
    '2026-04-21T05:52:00Z',
    { reposRequested: 11, reposChecked: 11, syncPrsOpen: 60 },
  );

  const body = formatCampaignBody(state);

  assert.ok(body.length <= 60000, `body length ${body.length} should fit GitHub issue limit`);
  assert.equal(parseCampaignMarker(body).items.length, 60);
});

test('formatCampaignBody omits inactive superseded details from issue marker', () => {
  const items = Array.from({ length: 150 }, (_, index) => ({
    id: `sync-review-comments:stranske/App#${index + 1}:abc${index}`,
    status: 'needs-local-codex',
    kind: 'sync-review-comments',
    classification: 'sync',
    repo: 'stranske/App',
    pr_number: index + 1,
    pr_title: 'chore: sync workflow templates',
    pr_url: `https://github.com/stranske/App/pull/${index + 1}`,
    source_repo: 'stranske/Workflows',
    preferred_workdir: 'Workflows',
    source_sync: {
      schema: 'sync-dependabot-campaign-source-sync/v1',
      current_sync_hash: 'new-sync-hash',
      pr_sync_hash: 'old-sync-hash',
      status: 'superseded',
    },
    review_thread_count: 4,
    review_threads: Array.from({ length: 4 }, (_, threadIndex) => ({
      id: `thread-${index}-${threadIndex}`,
      path: '.github/scripts/example.js',
      line: 100 + threadIndex,
      url: `https://github.test/thread-${index}-${threadIndex}`,
      author: 'copilot-pull-request-reviewer',
      body_preview: 'A'.repeat(400),
    })),
  }));
  const state = mergeCampaignState(
    {},
    items,
    '2026-04-21T05:52:00Z',
    { reposRequested: 11, reposChecked: 11, syncPrsOpen: 150, currentSyncHash: 'new-sync-hash' },
  );

  const body = formatCampaignBody(state);
  const marker = parseCampaignMarker(body);

  assert.ok(body.length <= 60000, `body length ${body.length} should fit GitHub issue limit`);
  assert.equal(marker.stats.items_superseded_sync_candidates, 120);
  assert.equal(marker.current_sync_hash, 'new-sync-hash');
  assert.deepEqual(marker.stats.source_sync_status_counts, { superseded: 120 });
  assert.equal(marker.stats.marker_items_retained, 0);
  assert.equal(marker.stats.marker_items_omitted, 120);
  assert.deepEqual(marker.items, []);
});
