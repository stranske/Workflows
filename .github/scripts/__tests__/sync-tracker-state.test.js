'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  DURABLE_TRACKER_LABEL,
  clearStuckWindowBody,
  findOrCreateTracker,
  isConsumerOpenPr,
  issueMatchesTracker,
  markStuckWindowBody,
  patternMatches,
  parseStuckWindow,
  preserveDurableTrackerHeader,
  updateTrackerBody,
} = require('../sync_tracker_state');

function mockGithub({ issues = [], issueDetails = null, pulls = [] } = {}) {
  const calls = {
    createdIssues: [],
    issueLists: [],
    updatedIssues: [],
    comments: [],
    labels: [],
  };
  const api = {
    paginate: async (method, params) => {
      if (method === api.rest.issues.listForRepo) {
        calls.issueLists.push(params);
        const labelSet = String(params.labels || '')
          .split(',')
          .map((label) => label.trim())
          .filter(Boolean);
        if (!labelSet.length) {
          return issues;
        }
        return issues.filter((issue) => {
          const names = (issue.labels || []).map((label) =>
            typeof label === 'string' ? label : label.name
          );
          return labelSet.every((label) => names.includes(label));
        });
      }
      if (method === api.rest.pulls.list) {
        return pulls;
      }
      return [];
    },
    rest: {
      issues: {
        listForRepo: async () => ({ data: issues }),
        get: async ({ issue_number }) => ({
          data: (issueDetails || issues).find((issue) => issue.number === issue_number),
        }),
        create: async (params) => {
          calls.createdIssues.push(params);
          return {
            data: {
              number: 99,
              title: params.title,
              body: params.body,
              labels: params.labels.map((name) => ({ name })),
            },
          };
        },
        update: async (params) => {
          calls.updatedIssues.push(params);
          return {
            data: {
              number: params.issue_number,
              title: params.title,
              body: params.body,
            },
          };
        },
        addLabels: async (params) => {
          calls.labels.push(params);
          return { data: params.labels.map((name) => ({ name })) };
        },
        createComment: async (params) => {
          calls.comments.push(params);
          return { data: { id: 1, body: params.body } };
        },
      },
      pulls: {
        list: async () => ({ data: pulls }),
      },
    },
    calls,
  };
  return api;
}

test('findOrCreateTracker discovers a tracker with the durable marker', async () => {
  const github = mockGithub({
    issues: [
      {
        number: 10,
        title: 'Other issue',
        body: '<!-- consumer-sync-drift:v1 {"schema":"consumer-sync-drift-issue/v1"} -->',
        labels: [{ name: DURABLE_TRACKER_LABEL }, { name: 'consumer-sync' }],
      },
    ],
  });

  const tracker = await findOrCreateTracker({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    label: 'consumer-sync',
    titlePattern: 'Consumer repo drift detected',
    markerPattern: /consumer-sync-drift:v1/,
    title: 'Consumer repo drift detected',
    body: 'new body',
  });

  assert.equal(tracker.number, 10);
  assert.equal(tracker.sync_tracker_created, false);
  assert.equal(github.calls.createdIssues.length, 0);
});

test('patternMatches handles invalid and stateful regex patterns deterministically', () => {
  const globalPattern = /sync\/workflows-/g;

  assert.equal(patternMatches('sync/workflows-abc123', globalPattern), true);
  assert.equal(patternMatches('sync/workflows-abc123', globalPattern), true);
  assert.equal(patternMatches('sync/workflows-abc123', '/[/'), false);
});

test('findOrCreateTracker discovers a tracker by durable label and title', async () => {
  const github = mockGithub({
    issues: [
      {
        number: 11,
        title: 'Sync/Dependabot campaign queue',
        body: 'queue body',
        labels: [{ name: DURABLE_TRACKER_LABEL }, { name: 'campaign:sync-dependabot' }],
      },
    ],
  });

  const tracker = await findOrCreateTracker({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    label: 'campaign:sync-dependabot',
    titlePattern: /^Sync\/Dependabot campaign queue$/,
  });

  assert.equal(tracker.number, 11);
  assert.equal(github.calls.createdIssues.length, 0);
});

test('findOrCreateTracker does not require durable and campaign labels together', async () => {
  const github = mockGithub({
    issues: [
      {
        number: 12,
        title: 'Sync/Dependabot campaign queue',
        body: 'queue body',
        labels: [{ name: 'campaign:sync-dependabot' }],
      },
    ],
  });

  const tracker = await findOrCreateTracker({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    label: 'campaign:sync-dependabot',
    titlePattern: /^Sync\/Dependabot campaign queue$/,
  });

  assert.equal(tracker.number, 12);
  assert.equal(
    github.calls.issueLists.some(
      (params) => params.labels === 'tracker:durable,campaign:sync-dependabot'
    ),
    false,
  );
});

test('findOrCreateTracker discovers an unlabeled tracker by marker', async () => {
  const github = mockGithub({
    issues: [
      {
        number: 13,
        title: 'Consumer repo drift detected',
        body: '<!-- consumer-sync-drift:v1 {"schema":"consumer-sync-drift-issue/v1"} -->',
        labels: [],
      },
    ],
  });

  const tracker = await findOrCreateTracker({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    label: 'consumer-sync',
    markerPattern: /consumer-sync-drift:v1/,
  });

  assert.equal(tracker.number, 13);
  assert.equal(
    github.calls.issueLists.some((params) => !params.labels),
    true,
  );
});

test('issueMatchesTracker rejects unlabelled title-only issues', () => {
  const issue = {
    number: 14,
    title: 'Sync/Dependabot campaign queue',
    body: 'existing queue body',
    labels: [],
  };

  assert.equal(
    issueMatchesTracker(issue, {
      label: 'campaign:sync-dependabot',
      titlePattern: /^Sync\/Dependabot campaign queue$/,
    }),
    false,
  );
});

test('issueMatchesTracker preserves label-only tracker matching', () => {
  assert.equal(
    issueMatchesTracker({
      number: 15,
      title: 'Any title',
      body: 'existing tracker body',
      labels: [{ name: 'campaign:sync-dependabot' }],
    }, {
      label: 'campaign:sync-dependabot',
    }),
    true,
  );
  assert.equal(
    issueMatchesTracker({
      number: 16,
      title: 'Any title',
      body: '',
      labels: [],
    }, {
      markerPattern: /sync-dependabot-campaign:v1/,
      allowBodylessTitleCandidate: true,
    }),
    false,
  );
  assert.equal(
    issueMatchesTracker({
      number: 17,
      title: 'Any title',
      body: '',
      labels: [{ name: 'campaign:sync-dependabot' }],
    }, {
      label: 'campaign:sync-dependabot',
      markerPattern: /sync-dependabot-campaign:v1/,
    }),
    false,
  );
  assert.equal(
    issueMatchesTracker({
      number: 18,
      title: 'Any title',
      body: '<!-- sync-dependabot-campaign:v1 {} -->',
      labels: [{ name: 'campaign:sync-dependabot' }],
    }, {
      label: 'campaign:sync-dependabot',
      markerPattern: /sync-dependabot-campaign:v1/,
    }),
    true,
  );
});

test('issueMatchesTracker allows bodyless title candidates only for preliminary marker lookups', () => {
  const issue = {
    number: 15,
    title: 'Consumer repo drift detected',
    body: '',
    labels: [],
  };

  assert.equal(
    issueMatchesTracker(issue, {
      label: 'consumer-sync',
      titlePattern: 'Consumer repo drift detected',
      markerPattern: /consumer-sync-drift:v1/,
      allowBodylessTitleCandidate: true,
    }),
    true,
  );
  assert.equal(
    issueMatchesTracker(issue, {
      label: 'consumer-sync',
      titlePattern: 'Consumer repo drift detected',
      markerPattern: /consumer-sync-drift:v1/,
    }),
    false,
  );
  assert.equal(
    issueMatchesTracker(issue, {
      label: 'consumer-sync',
      markerPattern: /consumer-sync-drift:v1/,
      allowBodylessTitleCandidate: true,
    }),
    false,
  );
});

test('findOrCreateTracker fetches bodyless marker candidates before matching', async () => {
  const github = mockGithub({
    issues: [
      {
        number: 14,
        title: 'Consumer repo drift detected',
        body: '',
        labels: [],
      },
    ],
    issueDetails: [
      {
        number: 14,
        title: 'Consumer repo drift detected',
        body: '<!-- consumer-sync-drift:v1 {"schema":"consumer-sync-drift-issue/v1"} -->',
        labels: [],
      },
    ],
  });

  const tracker = await findOrCreateTracker({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    label: 'consumer-sync',
    titlePattern: 'Consumer repo drift detected',
    markerPattern: /consumer-sync-drift:v1/,
  });

  assert.equal(tracker.number, 14);
  assert.equal(tracker.sync_tracker_created, false);
  assert.equal(github.calls.createdIssues.length, 0);
  assert.equal(
    github.calls.issueLists.some((params) => !params.labels),
    true,
  );
});

test('findOrCreateTracker does not reuse unrelated title-only issues', async () => {
  const github = mockGithub({
    issues: [
      {
        number: 16,
        title: 'Sync/Dependabot campaign queue',
        body: 'unrelated discussion',
        labels: [],
      },
    ],
  });

  const tracker = await findOrCreateTracker({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    label: 'campaign:sync-dependabot',
    titlePattern: /^Sync\/Dependabot campaign queue$/,
    title: 'Sync/Dependabot campaign queue',
    body: 'new body',
  });

  assert.equal(tracker.number, 99);
  assert.equal(tracker.sync_tracker_created, true);
  assert.equal(github.calls.createdIssues.length, 1);
});

test('findOrCreateTracker creates a durable tracker when none is found', async () => {
  const github = mockGithub();
  const retryOptions = [];

  const tracker = await findOrCreateTracker({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    label: 'consumer-sync',
    titlePattern: 'Consumer repo drift detected',
    title: 'Consumer repo drift detected',
    body: '## Consumer Repo Drift Detected',
    markerComment: '<!-- consumer-sync-drift:v1 {"schema":"consumer-sync-drift-issue/v1"} -->',
    withRetry: async (fn, options) => {
      retryOptions.push(options);
      return fn();
    },
  });

  assert.equal(tracker.number, 99);
  assert.equal(tracker.sync_tracker_created, true);
  assert.equal(github.calls.createdIssues.length, 1);
  assert.deepEqual(github.calls.createdIssues[0].labels, [
    DURABLE_TRACKER_LABEL,
    'automated',
    'consumer-sync',
  ]);
  assert.match(github.calls.createdIssues[0].body, /consumer-sync-drift:v1/);
  assert.equal(retryOptions.at(-1).allowNonIdempotentRetries, false);
});

test('findOrCreateTracker can return null without creating', async () => {
  const github = mockGithub();

  const tracker = await findOrCreateTracker({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    label: 'campaign:sync-dependabot',
    titlePattern: /^Sync\/Dependabot campaign queue$/,
    createIfMissing: false,
  });

  assert.equal(tracker, null);
  assert.equal(github.calls.createdIssues.length, 0);
});

test('updateTrackerBody preserves the durable-tracker header', async () => {
  const existingBody = [
    '## Consumer Repo Drift Detected',
    '',
    '> **Durable tracker** - this issue stays open. Do not close it.',
    '',
    'Old generated content.',
  ].join('\n');
  const nextGeneratedBody = [
    '## Consumer Repo Drift Detected',
    '',
    'New generated content.',
    '<!-- consumer-sync-drift:v1 {"schema":"consumer-sync-drift-issue/v1"} -->',
  ].join('\n');
  const github = mockGithub();

  const updated = await updateTrackerBody({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    tracker: { number: 12, body: existingBody },
    newBody: nextGeneratedBody,
  });

  assert.match(updated.body, /> \*\*Durable tracker\*\* - this issue stays open/);
  assert.match(updated.body, /New generated content/);
  assert.equal(github.calls.updatedIssues[0].issue_number, 12);
});

test('preserveDurableTrackerHeader does not duplicate an existing generated header', () => {
  const existingBody = '> **Durable tracker** - old header\n\nOld body';
  const newBody = '> **Durable tracker** - new header\n\nNew body';

  const merged = preserveDurableTrackerHeader(existingBody, newBody);

  assert.equal((merged.match(/\*\*Durable tracker\*\*/g) || []).length, 1);
  assert.match(merged, /new header/);
});

test('isConsumerOpenPr matches open consumer PR branches by pattern', async () => {
  const github = mockGithub({
    pulls: [
      { number: 1, head: { ref: 'feature/manual-change' } },
      { number: 2, head: { ref: 'sync/workflows-abc123' } },
    ],
  });

  assert.equal(
    await isConsumerOpenPr({
      github,
      consumerRepo: 'stranske/Ready',
      branchPattern: /^sync\/workflows-/,
    }),
    true,
  );
  assert.equal(
    await isConsumerOpenPr({
      github,
      consumerRepo: 'stranske/Ready',
      branchPattern: /^dependabot\//,
    }),
    false,
  );
  assert.equal(
    await isConsumerOpenPr({
      github,
      consumerRepo: 'stranske/Ready',
      branchPattern: '',
    }),
    false,
  );
});

test('isConsumerOpenPr manually paginates when github.paginate is unavailable', async () => {
  const pageOne = Array.from({ length: 100 }, (_, index) => ({
    number: index + 1,
    head: { ref: `feature/manual-${index + 1}` },
  }));
  const calls = [];
  const github = {
    rest: {
      pulls: {
        list: async (params) => {
          calls.push(params);
          return {
            data: params.page === 1 ? pageOne : [{ number: 101, head: { ref: 'sync/workflows-next' } }],
          };
        },
      },
    },
  };

  assert.equal(
    await isConsumerOpenPr({
      github,
      consumerRepo: 'stranske/Ready',
      branchPattern: /^sync\/workflows-/,
    }),
    true,
  );
  assert.deepEqual(calls.map((params) => params.page), [1, 2]);
});

test('isConsumerOpenPr uses token-aware retry injected clients', async () => {
  const primary = mockGithub({ pulls: [] });
  delete primary.paginate;
  const injected = mockGithub({
    pulls: [{ number: 7, head: { ref: 'sync/workflows-injected-client' } }],
  });
  delete injected.paginate;
  const clients = [];

  assert.equal(
    await isConsumerOpenPr({
      github: primary,
      consumerRepo: 'stranske/Ready',
      branchPattern: /^sync\/workflows-/,
      withRetry: async (fn) => {
        clients.push(injected);
        return fn(injected);
      },
    }),
    true,
  );
  assert.equal(clients.length, 1);
});

test('findOrCreateTracker manually paginates open issue scans', async () => {
  const pageOne = Array.from({ length: 100 }, (_, index) => ({
    number: index + 1,
    title: `Other issue ${index + 1}`,
    body: '',
    labels: [],
  }));
  const trackerIssue = {
    number: 101,
    title: 'Consumer repo drift detected',
    body: '<!-- consumer-sync-drift:v1 {"schema":"consumer-sync-drift-issue/v1"} -->',
    labels: [],
  };
  const allIssues = [...pageOne, trackerIssue];
  const calls = [];
  const github = {
    rest: {
      issues: {
        listForRepo: async (params) => {
          calls.push(params);
          if (params.labels) {
            return { data: [] };
          }
          return { data: params.page === 1 ? pageOne : [trackerIssue] };
        },
        get: async ({ issue_number }) => ({
          data: allIssues.find((issue) => issue.number === issue_number) || null,
        }),
        addLabels: async (params) => ({ data: params.labels.map((name) => ({ name })) }),
      },
    },
  };

  const tracker = await findOrCreateTracker({
    github,
    owner: 'stranske',
    repo: 'Workflows',
    label: 'consumer-sync',
    titlePattern: /^Consumer repo drift detected$/,
    markerPattern: /consumer-sync-drift:v1/,
  });

  assert.equal(tracker.number, 101);
  assert.equal(calls.some((params) => !params.labels && params.page === 2), true);
});

test('markStuckWindowBody and clearStuckWindowBody manage the lifecycle marker', () => {
  const marked = markStuckWindowBody('## Sync Status\n\nStill failing.', '2026-05-01T00:00:00Z', {
    updatedAt: '2026-05-02T00:00:00Z',
    reason: 'missing-token',
  });
  const parsed = parseStuckWindow(marked);

  assert.equal(parsed.schema, 'sync-tracker-stuck-window/v1');
  assert.equal(parsed.since, '2026-05-01T00:00:00Z');
  assert.equal(parsed.reason, 'missing-token');
  assert.match(marked, /sync-tracker-stuck-window:v1/);

  const reasonWithBrace = markStuckWindowBody(marked, '2026-05-02T00:00:00Z', {
    updatedAt: '2026-05-02T01:00:00Z',
    reason: 'payload contained } in a message',
  });
  assert.equal(parseStuckWindow(reasonWithBrace).reason, 'payload contained } in a message');

  const refreshed = markStuckWindowBody(marked, '2026-05-03T00:00:00Z', {
    updatedAt: '2026-05-04T00:00:00Z',
  });
  assert.equal((refreshed.match(/sync-tracker-stuck-window:v1/g) || []).length, 1);
  assert.equal(parseStuckWindow(refreshed).since, '2026-05-03T00:00:00Z');

  const cleared = clearStuckWindowBody(refreshed);
  assert.equal(parseStuckWindow(cleared), null);
  assert.doesNotMatch(cleared, /sync-tracker-stuck-window:v1/);
  assert.match(cleared, /Still failing/);
});
