const test = require('node:test');
const assert = require('node:assert/strict');

const {
  SELECTION_SCHEMA,
  artifactFamily,
  collectRepoArtifacts,
  formatArtifactTsv,
  formatSelectionMarkdown,
  normalizeSelectionOptions,
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
  assert.equal(artifactFamily('autopilot-metrics-42'), 'autopilot-metrics');
  assert.equal(
    artifactFamily('review-thread-terminal-disposition-123'),
    'review-thread-terminal-disposition'
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
    ],
    { now_ms: NOW, lookback_days: 14 }
  );

  assert.equal(report.schema, SELECTION_SCHEMA);
  assert.equal(report.scanned_count, 6);
  assert.equal(report.candidate_count, 3);
  assert.equal(report.selected_count, 3);
  assert.equal(report.ignored_name_count, 1);
  assert.equal(report.ignored_old_count, 1);
  assert.equal(report.ignored_expired_count, 1);
  assert.deepEqual(
    report.selected_artifacts.map((selected) => selected.id),
    [5, 4, 1]
  );
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
  assert.match(markdown, /Selected artifacts: 2/);
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

  assert.equal(artifacts.length, 4);
  assert.deepEqual(
    calls.map((call) => call.page),
    [1, 2]
  );
  assert.ok(calls.every((call) => call.per_page === 2));
});
