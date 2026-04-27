const test = require('node:test');
const assert = require('node:assert/strict');

const {
  SELECTION_SCHEMA,
  artifactFamily,
  buildSelectionErrorReport,
  collectPriorityWorkflowArtifacts,
  collectRepoArtifacts,
  dedupeArtifacts,
  familiesSatisfied,
  formatArtifactTsv,
  formatSelectionMarkdown,
  latestCandidateByFamily,
  missingPriorityFamilies,
  normalizeSelectionOptions,
  priorityFamilyStatuses,
  selectMetricsArtifacts,
} = require('../weekly_metrics_artifacts.js');

const NOW = Date.parse('2026-04-25T12:00:00Z');

function artifact(id, name, createdAt, extra = {}) {
  return {
    id,
    name,
    created_at: createdAt,
    updated_at: createdAt,
    expired: false,
    ...extra,
  };
}

test('maps metrics artifact names to stable families', () => {
  assert.equal(artifactFamily('keepalive-metrics'), 'keepalive-metrics');
  assert.equal(artifactFamily('codex-cli-freshness'), 'codex-cli-freshness');
  assert.equal(artifactFamily('codex-cli-freshness-123'), 'codex-cli-freshness');
  assert.equal(artifactFamily('pr-source-context'), 'pr-source-context');
  assert.equal(artifactFamily('autopilot-metrics-42'), 'autopilot-metrics');
  assert.equal(
    artifactFamily('review-thread-terminal-disposition-123'),
    'review-thread-terminal-disposition'
  );
  assert.equal(
    artifactFamily('bot-comment-auth-coverage-wrapper-123'),
    'bot-comment-auth-coverage-wrapper'
  );
  assert.equal(
    artifactFamily('bot-comment-auth-coverage-wrapper-123-2'),
    'bot-comment-auth-coverage-wrapper'
  );
  assert.equal(
    artifactFamily('bot-comment-auth-coverage-reusable-123'),
    'bot-comment-auth-coverage-reusable'
  );
  assert.equal(
    artifactFamily('bot-comment-auth-coverage-reusable-123-2'),
    'bot-comment-auth-coverage-reusable'
  );
  assert.equal(
    artifactFamily('bot-comment-auth-coverage-wrapper-latest'),
    'bot-comment-auth-coverage-wrapper'
  );
  assert.equal(
    artifactFamily('bot-comment-auth-coverage-reusable-run-123'),
    'bot-comment-auth-coverage-reusable'
  );
  assert.equal(
    artifactFamily('bot-comment-auth-coverage-wrapper-123-extra'),
    'bot-comment-auth-coverage-wrapper'
  );
  assert.equal(
    artifactFamily('bot-comment-auth-coverage-reusable'),
    'bot-comment-auth-coverage-reusable'
  );
  assert.equal(artifactFamily('coverage-summary'), '');
});

test('selects only recent matching artifacts with a machine-readable report', () => {
  const report = selectMetricsArtifacts(
    [
      artifact(1, 'keepalive-metrics', '2026-04-24T12:00:00Z'),
      artifact(2, 'coverage-summary', '2026-04-24T12:00:00Z'),
      artifact(3, 'agents-autofix-metrics', '2026-04-01T12:00:00Z'),
      artifact(4, 'autopilot-metrics-77', '2026-04-25T10:00:00Z'),
      artifact(5, 'review-thread-terminal-disposition-77', '2026-04-25T11:00:00Z'),
      artifact(6, 'agents-verifier-metrics', '2026-04-25T09:00:00Z', { expired: true }),
      artifact(7, 'bot-comment-auth-coverage-wrapper-latest', '2026-04-25T08:00:00Z'),
      artifact(8, 'bot-comment-auth-coverage-wrapper-77-2', '2026-04-25T08:30:00Z'),
      artifact(9, 'codex-cli-freshness-77', '2026-04-25T11:30:00Z'),
      artifact(10, 'pr-source-context', '2026-04-25T11:45:00Z'),
    ],
    { now_ms: NOW, lookback_days: 14 }
  );

  assert.equal(report.schema, SELECTION_SCHEMA);
  assert.equal(report.status, 'pass');
  assert.equal(report.scanned_count, 10);
  assert.equal(report.candidate_count, 7);
  assert.equal(report.selected_count, 7);
  assert.equal(report.ignored_name_count, 1);
  assert.equal(report.ignored_old_count, 1);
  assert.equal(report.ignored_expired_count, 1);
  assert.deepEqual(report.candidate_family_counts, {
    'autopilot-metrics': 1,
    'bot-comment-auth-coverage-wrapper': 2,
    'codex-cli-freshness': 1,
    'keepalive-metrics': 1,
    'pr-source-context': 1,
    'review-thread-terminal-disposition': 1,
  });
  assert.deepEqual(report.missing_priority_families, [
    'verifier-terminal-disposition',
    'bot-comment-auth-coverage-reusable',
  ]);
  assert.deepEqual(
    report.latest_candidate_by_family,
    {
      'codex-cli-freshness': {
        id: 9,
        name: 'codex-cli-freshness-77',
        created_at: '2026-04-25T11:30:00Z',
        updated_at: '2026-04-25T11:30:00Z',
      },
      'bot-comment-auth-coverage-wrapper': {
        id: 8,
        name: 'bot-comment-auth-coverage-wrapper-77-2',
        created_at: '2026-04-25T08:30:00Z',
        updated_at: '2026-04-25T08:30:00Z',
      },
      'review-thread-terminal-disposition': {
        id: 5,
        name: 'review-thread-terminal-disposition-77',
        created_at: '2026-04-25T11:00:00Z',
        updated_at: '2026-04-25T11:00:00Z',
      },
      'pr-source-context': {
        id: 10,
        name: 'pr-source-context',
        created_at: '2026-04-25T11:45:00Z',
        updated_at: '2026-04-25T11:45:00Z',
      },
    }
  );
  assert.deepEqual(
    report.priority_family_statuses.map((family) => ({
      family: family.family,
      status: family.status,
      candidate_count: family.candidate_count,
      selected_count: family.selected_count,
      selected_name: family.selected_artifact?.name || '',
    })),
    [
      {
        family: 'codex-cli-freshness',
        status: 'selected',
        candidate_count: 1,
        selected_count: 1,
        selected_name: 'codex-cli-freshness-77',
      },
      {
        family: 'verifier-terminal-disposition',
        status: 'missing',
        candidate_count: 0,
        selected_count: 0,
        selected_name: '',
      },
      {
        family: 'review-thread-terminal-disposition',
        status: 'selected',
        candidate_count: 1,
        selected_count: 1,
        selected_name: 'review-thread-terminal-disposition-77',
      },
      {
        family: 'bot-comment-auth-coverage-wrapper',
        status: 'selected',
        candidate_count: 2,
        selected_count: 2,
        selected_name: 'bot-comment-auth-coverage-wrapper-77-2',
      },
      {
        family: 'bot-comment-auth-coverage-reusable',
        status: 'missing',
        candidate_count: 0,
        selected_count: 0,
        selected_name: '',
      },
      {
        family: 'pr-source-context',
        status: 'selected',
        candidate_count: 1,
        selected_count: 1,
        selected_name: 'pr-source-context',
      },
    ]
  );
  assert.deepEqual(report.selected_family_counts, {
    'autopilot-metrics': 1,
    'bot-comment-auth-coverage-wrapper': 2,
    'codex-cli-freshness': 1,
    'keepalive-metrics': 1,
    'pr-source-context': 1,
    'review-thread-terminal-disposition': 1,
  });
  assert.deepEqual(
    report.selected_artifacts.map((selected) => selected.id),
    [9, 5, 8, 10, 4, 7, 1]
  );
});

test('builds an error report when artifact selection cannot query GitHub', () => {
  const report = buildSelectionErrorReport(
    { now_ms: NOW, max_total: 3 },
    new Error('API rate limit exceeded')
  );
  const markdown = formatSelectionMarkdown(report);

  assert.equal(report.schema, SELECTION_SCHEMA);
  assert.equal(report.status, 'error');
  assert.equal(report.error_message, 'API rate limit exceeded');
  assert.equal(report.selected_count, 0);
  assert.deepEqual(report.missing_priority_families, [
    'codex-cli-freshness',
    'verifier-terminal-disposition',
    'review-thread-terminal-disposition',
    'bot-comment-auth-coverage-wrapper',
    'bot-comment-auth-coverage-reusable',
    'pr-source-context',
  ]);
  assert.ok(report.priority_family_statuses.every((family) => family.status === 'missing'));
  assert.deepEqual(report.selected_artifacts, []);
  assert.match(markdown, /Status: error/);
  assert.match(markdown, /API rate limit exceeded/);
});

test('bounds selected artifacts by total and per-family limits', () => {
  const report = selectMetricsArtifacts(
    [
      artifact(1, 'autopilot-metrics-1', '2026-04-25T11:00:00Z'),
      artifact(2, 'autopilot-metrics-2', '2026-04-25T10:00:00Z'),
      artifact(3, 'autopilot-metrics-3', '2026-04-25T09:00:00Z'),
      artifact(4, 'keepalive-metrics', '2026-04-25T08:00:00Z'),
      artifact(5, 'agents-verifier-metrics', '2026-04-25T07:00:00Z'),
    ],
    {
      now_ms: NOW,
      max_per_family: 2,
      max_total: 3,
    }
  );

  assert.deepEqual(
    report.selected_artifacts.map((selected) => selected.id),
    [1, 2, 4]
  );
  assert.equal(report.ignored_family_limit_count, 1);
  assert.equal(report.ignored_total_limit_count, 1);
});

test('reserves priority telemetry artifacts before filling the total cap', () => {
  const report = selectMetricsArtifacts(
    [
      artifact(1, 'keepalive-metrics', '2026-04-25T11:59:00Z'),
      artifact(2, 'agents-autofix-metrics', '2026-04-25T11:58:00Z'),
      artifact(3, 'verifier-terminal-disposition-77', '2026-04-25T09:00:00Z'),
      artifact(4, 'review-thread-terminal-disposition-77', '2026-04-25T08:00:00Z'),
      artifact(5, 'bot-comment-auth-coverage-wrapper-77', '2026-04-25T07:00:00Z'),
      artifact(6, 'bot-comment-auth-coverage-reusable-77', '2026-04-25T06:00:00Z'),
      artifact(7, 'codex-cli-freshness-77', '2026-04-25T05:00:00Z'),
      artifact(8, 'pr-source-context', '2026-04-25T04:00:00Z'),
    ],
    {
      now_ms: NOW,
      max_total: 6,
    }
  );

  assert.deepEqual(
    report.selected_artifacts.map((selected) => selected.name),
    [
      'codex-cli-freshness-77',
      'verifier-terminal-disposition-77',
      'review-thread-terminal-disposition-77',
      'bot-comment-auth-coverage-wrapper-77',
      'bot-comment-auth-coverage-reusable-77',
      'pr-source-context',
    ]
  );
  assert.equal(report.ignored_total_limit_count, 2);
  assert.deepEqual(report.selected_family_counts, {
    'bot-comment-auth-coverage-reusable': 1,
    'bot-comment-auth-coverage-wrapper': 1,
    'codex-cli-freshness': 1,
    'pr-source-context': 1,
    'review-thread-terminal-disposition': 1,
    'verifier-terminal-disposition': 1,
  });
  assert.deepEqual(report.missing_priority_families, []);
});

test('reports priority telemetry families that are absent from the scan', () => {
  const counts = new Map([
    ['bot-comment-auth-coverage-wrapper', 2],
    ['keepalive-metrics', 5],
  ]);

  assert.deepEqual(missingPriorityFamilies(counts), [
    'codex-cli-freshness',
    'verifier-terminal-disposition',
    'review-thread-terminal-disposition',
    'bot-comment-auth-coverage-reusable',
    'pr-source-context',
  ]);
});

test('maps latest candidate artifacts by priority family', () => {
  const candidates = [
    artifact(1, 'review-thread-terminal-disposition-older', '2026-04-25T10:00:00Z'),
    artifact(2, 'review-thread-terminal-disposition-newer', '2026-04-25T11:00:00Z'),
    artifact(3, 'keepalive-metrics', '2026-04-25T12:00:00Z'),
  ].map((raw) => ({
    id: raw.id,
    name: raw.name,
    family: artifactFamily(raw.name),
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  }));

  assert.deepEqual(latestCandidateByFamily(candidates), {
    'review-thread-terminal-disposition': {
      id: 2,
      name: 'review-thread-terminal-disposition-newer',
      created_at: '2026-04-25T11:00:00Z',
      updated_at: '2026-04-25T11:00:00Z',
    },
  });
});

test('builds priority family statuses for available but unselected artifacts', () => {
  const candidates = [
    artifact(1, 'bot-comment-auth-coverage-wrapper-1', '2026-04-25T11:00:00Z'),
    artifact(2, 'bot-comment-auth-coverage-reusable-1', '2026-04-25T10:00:00Z'),
  ].map((raw) => ({
    id: raw.id,
    name: raw.name,
    family: raw.name.includes('reusable')
      ? 'bot-comment-auth-coverage-reusable'
      : 'bot-comment-auth-coverage-wrapper',
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  }));
  const statuses = priorityFamilyStatuses({
    candidates,
    selected: [candidates[0]],
    candidateFamilyCounts: new Map([
      ['bot-comment-auth-coverage-wrapper', 1],
      ['bot-comment-auth-coverage-reusable', 1],
    ]),
    selectedFamilyCounts: new Map([['bot-comment-auth-coverage-wrapper', 1]]),
  });

  const reusable = statuses.find(
    (family) => family.family === 'bot-comment-auth-coverage-reusable'
  );
  assert.equal(reusable.status, 'available');
  assert.equal(reusable.candidate_count, 1);
  assert.equal(reusable.selected_count, 0);
  assert.equal(reusable.latest_candidate.name, 'bot-comment-auth-coverage-reusable-1');
  assert.equal(reusable.selected_artifact, null);
});

test('formats selected artifacts for the workflow download loop', () => {
  const tsv = formatArtifactTsv([
    { id: 42, name: 'keepalive-metrics' },
    { id: 43, name: 'autopilot-metrics-7' },
  ]);

  assert.equal(tsv, '42\tkeepalive-metrics\n43\tautopilot-metrics-7');
});

test('formats a human-visible selector summary for weekly metrics', () => {
  const report = selectMetricsArtifacts(
    [
      artifact(1, 'keepalive-metrics', '2026-04-25T11:00:00Z'),
      artifact(2, 'autopilot-metrics-7', '2026-04-25T10:00:00Z'),
      artifact(3, 'coverage-summary', '2026-04-25T09:00:00Z'),
    ],
    { now_ms: NOW }
  );
  const markdown = formatSelectionMarkdown(report);

  assert.match(markdown, /Weekly Metrics Artifact Selection/);
  assert.match(markdown, /Scan cap: 5 pages x 100 artifacts/);
  assert.match(markdown, /Priority producer scan cap: 10 runs per source workflow/);
  assert.match(markdown, /Selected artifacts: 2/);
  assert.match(
    markdown,
    /Missing priority families: codex-cli-freshness, verifier-terminal-disposition, review-thread-terminal-disposition, bot-comment-auth-coverage-wrapper, bot-comment-auth-coverage-reusable, pr-source-context/
  );
  assert.match(markdown, /Artifact family \| Candidates \| Selected/);
  assert.match(markdown, /Priority family \| Status \| Candidates \| Selected artifact/);
  assert.match(markdown, /autopilot-metrics/);
  assert.match(markdown, /keepalive-metrics/);
});

test('normalizes invalid environment-like limits to defaults', () => {
  const options = normalizeSelectionOptions({
    now_ms: NOW,
    lookback_days: 'bad',
    max_total: '-1',
    max_per_family: '0',
    max_scan_pages: '',
  });

  assert.equal(options.lookback_days, 14);
  assert.equal(options.max_total, 80);
  assert.equal(options.max_per_family, 20);
  assert.equal(options.max_scan_pages, 5);
  assert.equal(options.priority_workflow_runs_per_source, 10);
});

test('deduplicates artifacts by stable id before selection', () => {
  const artifacts = dedupeArtifacts([
    artifact(1, 'codex-cli-freshness-77', '2026-04-25T11:00:00Z'),
    artifact(1, 'codex-cli-freshness-77', '2026-04-25T11:00:00Z'),
    artifact(null, 'bot-comment-auth-coverage-reusable-1', '2026-04-25T10:00:00Z'),
    artifact(null, 'bot-comment-auth-coverage-reusable-1', '2026-04-25T10:00:00Z'),
  ]);

  assert.deepEqual(
    artifacts.map((selected) => selected.name),
    ['codex-cli-freshness-77', 'bot-comment-auth-coverage-reusable-1']
  );
});

test('checks whether priority workflow artifacts satisfy configured families', () => {
  const config = normalizeSelectionOptions({ now_ms: NOW, lookback_days: 14 });

  assert.equal(
    familiesSatisfied(
      [artifact(1, 'bot-comment-auth-coverage-reusable-1', '2026-04-25T10:00:00Z')],
      ['bot-comment-auth-coverage-reusable'],
      config
    ),
    true
  );
  assert.equal(
    familiesSatisfied(
      [artifact(2, 'bot-comment-auth-coverage-reusable-old', '2026-03-25T10:00:00Z')],
      ['bot-comment-auth-coverage-reusable'],
      config
    ),
    false
  );
});

test('collects priority artifacts from their producer workflows', async () => {
  const calls = [];
  const client = {
    rest: {
      actions: {
        listWorkflowRuns: async (params) => {
          calls.push(['runs', params.workflow_id, params.per_page]);
          return {
            data: {
              workflow_runs: [
                { id: 101, created_at: '2026-04-25T11:00:00Z', updated_at: '2026-04-25T11:00:00Z' },
                { id: 102, created_at: '2026-04-25T10:00:00Z', updated_at: '2026-04-25T10:00:00Z' },
              ],
            },
          };
        },
        listWorkflowRunArtifacts: async (params) => {
          calls.push(['artifacts', params.run_id, params.per_page]);
          return {
            data: {
              artifacts: [
                artifact(
                  params.run_id,
                  params.run_id === 101
                    ? 'bot-comment-auth-coverage-reusable-101'
                    : 'keepalive-metrics',
                  '2026-04-25T11:00:00Z'
                ),
              ],
            },
          };
        },
      },
    },
  };

  const artifacts = await collectPriorityWorkflowArtifacts({
    github: client,
    owner: 'owner',
    repo: 'repo',
    options: {
      now_ms: NOW,
      priority_workflow_runs_per_source: 2,
      per_page: 50,
    },
    sources: [
      {
        workflow_id: 'reusable-bot-comment-handler.yml',
        families: ['bot-comment-auth-coverage-reusable'],
      },
    ],
    withRetry: (fn) => fn(client),
  });

  assert.deepEqual(
    artifacts.map((selected) => selected.name),
    ['bot-comment-auth-coverage-reusable-101']
  );
  assert.deepEqual(calls, [
    ['runs', 'reusable-bot-comment-handler.yml', 2],
    ['artifacts', 101, 50],
  ]);
});

test('skips missing priority producer workflows without failing selection', async () => {
  const client = {
    rest: {
      actions: {
        listWorkflowRuns: async () => {
          const error = new Error('Not Found');
          error.status = 404;
          throw error;
        },
      },
    },
  };

  const artifacts = await collectPriorityWorkflowArtifacts({
    github: client,
    owner: 'owner',
    repo: 'repo',
    options: { now_ms: NOW },
    sources: [
      {
        workflow_id: 'health-76-codex-cli-freshness.yml',
        families: ['codex-cli-freshness'],
      },
    ],
    withRetry: (fn) => fn(client),
  });

  assert.deepEqual(artifacts, []);
});

test('collects repo artifacts within the configured scan page cap', async () => {
  const calls = [];
  const client = {
    rest: {
      actions: {
        listArtifactsForRepo: async (params) => {
          calls.push(params);
          return {
            data: {
              artifacts: [
                artifact(params.page * 10 + 1, 'keepalive-metrics', '2026-04-25T11:00:00Z'),
                artifact(params.page * 10 + 2, 'autopilot-metrics-7', '2026-04-25T10:00:00Z'),
              ],
            },
          };
        },
        listWorkflowRuns: async () => ({
          data: {
            workflow_runs: [
              {
                id: 9001,
                created_at: '2026-04-25T09:00:00Z',
                updated_at: '2026-04-25T09:00:00Z',
              },
            ],
          },
        }),
        listWorkflowRunArtifacts: async () => ({
          data: {
            artifacts: [
              artifact(9001, 'codex-cli-freshness-9001', '2026-04-25T09:00:00Z'),
            ],
          },
        }),
      },
    },
  };

  const artifacts = await collectRepoArtifacts({
    github: client,
    owner: 'owner',
    repo: 'repo',
    options: {
      now_ms: NOW,
      max_scan_pages: 2,
      per_page: 2,
    },
    withRetry: (fn) => fn(client),
  });

  assert.equal(artifacts.length, 5);
  assert.ok(artifacts.some((candidate) => candidate.name === 'codex-cli-freshness-9001'));
  assert.deepEqual(
    calls.map((call) => call.page),
    [1, 2]
  );
  assert.ok(calls.every((call) => call.per_page === 2));
});
