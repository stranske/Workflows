const test = require('node:test');
const assert = require('node:assert/strict');

const {
  DOWNLOAD_MANIFEST_SCHEMA,
  buildInitialManifest,
  compactSelectionDetails,
  finalizeManifest,
  formatMarkdown,
  safeArtifactPathSegment,
  updateArtifactResult,
} = require('../weekly_metrics_download_manifest.js');

const selection = {
  schema: 'workflows-weekly-metrics-artifact-selection/v1',
  status: 'pass',
  candidate_count: 3,
  candidate_family_counts: {
    'codex-cli-freshness': 1,
    'keepalive-metrics': 1,
    'review-thread-terminal-disposition': 1,
  },
  selected_family_counts: {
    'keepalive-metrics': 1,
    'review-thread-terminal-disposition': 1,
  },
  missing_priority_families: ['bot-comment-auth-coverage-reusable'],
  latest_candidate_by_family: {
    'codex-cli-freshness': {
      id: 44,
      name: 'codex-cli-freshness-24965031474',
      created_at: '2026-04-26T01:01:00Z',
      updated_at: '2026-04-26T01:01:00Z',
    },
  },
  priority_family_statuses: [
    {
      family: 'codex-cli-freshness',
      status: 'available',
      candidate_count: 1,
      selected_count: 0,
      latest_candidate: {
        id: 44,
        name: 'codex-cli-freshness-24965031474',
        created_at: '2026-04-26T01:01:00Z',
        updated_at: '2026-04-26T01:01:00Z',
      },
      selected_artifact: null,
    },
  ],
  selected_artifacts: [
    {
      id: 42,
      name: 'keepalive-metrics',
      family: 'keepalive-metrics',
      created_at: '2026-04-26T01:00:00Z',
      updated_at: '2026-04-26T01:02:00Z',
    },
    {
      id: 43,
      name: 'review-thread-terminal-disposition-7',
      family: 'review-thread-terminal-disposition',
      created_at: '2026-04-26T01:03:00Z',
      updated_at: '2026-04-26T01:04:00Z',
    },
  ],
};

test('builds initial download manifest from selected artifacts', () => {
  const manifest = buildInitialManifest(selection, {
    artifacts_root: 'artifacts',
    selection_path: 'artifacts/metric-artifacts-selection.json',
    generated_at: '2026-04-26T01:05:00Z',
  });

  assert.equal(manifest.schema, DOWNLOAD_MANIFEST_SCHEMA);
  assert.equal(manifest.status, 'pending');
  assert.deepEqual(manifest.selection, {
    path: 'artifacts/metric-artifacts-selection.json',
    schema: 'workflows-weekly-metrics-artifact-selection/v1',
    status: 'pass',
    selected_count: 2,
    candidate_count: 3,
    candidate_family_counts: {
      'codex-cli-freshness': 1,
      'keepalive-metrics': 1,
      'review-thread-terminal-disposition': 1,
    },
    selected_family_counts: {
      'keepalive-metrics': 1,
      'review-thread-terminal-disposition': 1,
    },
    missing_priority_families: ['bot-comment-auth-coverage-reusable'],
    priority_family_statuses: [
      {
        family: 'codex-cli-freshness',
        status: 'available',
        candidate_count: 1,
        selected_count: 0,
        latest_candidate: {
          id: 44,
          name: 'codex-cli-freshness-24965031474',
          created_at: '2026-04-26T01:01:00Z',
          updated_at: '2026-04-26T01:01:00Z',
        },
        selected_artifact: null,
      },
    ],
    latest_candidate_by_family: {
      'codex-cli-freshness': {
        id: 44,
        name: 'codex-cli-freshness-24965031474',
        created_at: '2026-04-26T01:01:00Z',
        updated_at: '2026-04-26T01:01:00Z',
      },
    },
  });
  assert.deepEqual(manifest.stats, {
    selected_count: 2,
    download_pass_count: 0,
    download_failed_count: 0,
    unzip_pass_count: 0,
    unzip_failed_count: 0,
    unzip_skipped_count: 0,
  });
  assert.equal(manifest.artifacts[0].artifact_dir, 'artifacts/keepalive-metrics/42');
  assert.equal(manifest.artifacts[0].zip_path, 'artifacts/keepalive-metrics/42/42.zip');
  assert.equal(manifest.artifacts[0].download.status, 'pending');
  assert.equal(manifest.artifacts[0].unzip.status, 'pending');
});

test('preserves priority family state from the selector contract', () => {
  const details = compactSelectionDetails(selection, 'artifacts/metric-artifacts-selection.json');

  assert.equal(details.selected_count, 2);
  assert.equal(details.candidate_count, 3);
  assert.deepEqual(details.selected_family_counts, {
    'keepalive-metrics': 1,
    'review-thread-terminal-disposition': 1,
  });
  assert.deepEqual(details.latest_candidate_by_family['codex-cli-freshness'], {
    id: 44,
    name: 'codex-cli-freshness-24965031474',
    created_at: '2026-04-26T01:01:00Z',
    updated_at: '2026-04-26T01:01:00Z',
  });
  assert.equal(details.priority_family_statuses[0].status, 'available');
});

test('records download and unzip outcomes and finalizes warning status', () => {
  const manifest = buildInitialManifest(selection);

  updateArtifactResult(manifest, {
    id: '42',
    artifact_dir: 'artifacts/keepalive-metrics/42',
    zip_path: 'artifacts/keepalive-metrics/42/42.zip',
    zip_bytes: '512',
    download_status: 'pass',
    unzip_status: 'pass',
  });
  updateArtifactResult(manifest, {
    id: '43',
    artifact_dir: 'artifacts/review-thread-terminal-disposition-7/43',
    zip_path: 'artifacts/review-thread-terminal-disposition-7/43/43.zip',
    download_status: 'failed',
    download_error: 'download-command-failed',
    unzip_status: 'skipped',
    unzip_error: 'download-failed',
  });
  finalizeManifest(manifest);

  assert.equal(manifest.status, 'warning');
  assert.deepEqual(manifest.stats, {
    selected_count: 2,
    download_pass_count: 1,
    download_failed_count: 1,
    unzip_pass_count: 1,
    unzip_failed_count: 0,
    unzip_skipped_count: 1,
  });
  assert.equal(manifest.artifacts[0].download.bytes, 512);
  assert.equal(manifest.artifacts[1].download.error, 'download-command-failed');
  assert.equal(manifest.artifacts[1].unzip.error, 'download-failed');
});

test('records outcomes against legacy manifest entries missing result objects', () => {
  const manifest = buildInitialManifest(selection);
  delete manifest.artifacts[0].download;
  delete manifest.artifacts[0].unzip;

  updateArtifactResult(manifest, {
    id: '42',
    artifact_dir: 'artifacts/keepalive-metrics/42',
    download_status: 'pass',
    unzip_status: 'pass',
  });
  finalizeManifest(manifest);

  assert.equal(manifest.status, 'warning');
  assert.equal(manifest.artifacts[0].download.status, 'pass');
  assert.equal(manifest.artifacts[0].download.bytes, null);
  assert.equal(manifest.artifacts[0].unzip.status, 'pass');
  assert.equal(manifest.artifacts[0].unzip.path, 'artifacts/keepalive-metrics/42');
  assert.equal(manifest.stats.download_pass_count, 1);
  assert.equal(manifest.stats.unzip_pass_count, 1);
});

test('finalizes legacy manifest entries into canonical result object shape', () => {
  const manifest = buildInitialManifest(selection);
  delete manifest.artifacts[0].download;
  delete manifest.artifacts[0].unzip;

  finalizeManifest(manifest);

  assert.equal(manifest.status, 'warning');
  assert.deepEqual(manifest.artifacts[0].download, {
    status: 'pending',
    bytes: null,
    error: '',
  });
  assert.deepEqual(manifest.artifacts[0].unzip, {
    status: 'pending',
    path: 'artifacts/keepalive-metrics/42',
    error: '',
  });
  assert.equal(manifest.stats.download_pass_count, 0);
  assert.equal(manifest.stats.unzip_skipped_count, 0);
});

test('finalizes pass when every selected artifact downloads and extracts', () => {
  const manifest = buildInitialManifest(selection);
  for (const artifact of manifest.artifacts) {
    updateArtifactResult(manifest, {
      id: artifact.id,
      download_status: 'pass',
      unzip_status: 'pass',
    });
  }

  finalizeManifest(manifest);

  assert.equal(manifest.status, 'pass');
  assert.equal(manifest.stats.download_pass_count, 2);
  assert.equal(manifest.stats.unzip_pass_count, 2);
});

test('does not fall back to name when artifact id mismatches', () => {
  const manifest = buildInitialManifest(selection);

  assert.throws(
    () => updateArtifactResult(manifest, {
      id: 'missing-id',
      name: 'keepalive-metrics',
      download_status: 'pass',
    }),
    /Artifact is not present in manifest: missing-id/
  );
});

test('sanitizes artifact names used in extraction paths', () => {
  const manifest = buildInitialManifest({
    ...selection,
    selected_artifacts: [
      {
        id: 44,
        name: '../bad/name with spaces',
        family: 'keepalive-metrics',
      },
    ],
  });

  assert.equal(safeArtifactPathSegment('../bad/name with spaces'), '__bad_name_with_spaces');
  assert.equal(manifest.artifacts[0].name, '../bad/name with spaces');
  assert.equal(manifest.artifacts[0].artifact_dir, 'artifacts/__bad_name_with_spaces/44');
  assert.equal(manifest.artifacts[0].zip_path, 'artifacts/__bad_name_with_spaces/44/44.zip');
});

test('formats human-visible markdown without replacing the JSON contract', () => {
  const manifest = buildInitialManifest(selection);
  updateArtifactResult(manifest, {
    id: '42',
    download_status: 'pass',
    unzip_status: 'failed',
    unzip_error: 'unzip-command-failed',
  });
  finalizeManifest(manifest);
  const markdown = formatMarkdown(manifest);

  assert.match(markdown, /Weekly Metrics Artifact Downloads/);
  assert.match(markdown, /Status: warning/);
  assert.match(markdown, /Downloads: 1 passed, 0 failed/);
  assert.match(markdown, /unzip-command-failed/);
  assert.match(markdown, /keepalive-metrics/);
});

test('escapes markdown table cells in human-visible manifest', () => {
  const manifest = buildInitialManifest({
    ...selection,
    selected_artifacts: [
      {
        id: '44|45',
        name: 'keepalive|metrics\nlatest',
        family: 'keepalive-metrics',
      },
    ],
  });
  updateArtifactResult(manifest, {
    id: '44|45',
    artifact_dir: 'artifacts/keepalive|metrics\nlatest/44|45',
    download_status: 'failed',
    download_error: 'bad|download\nreason',
    unzip_status: 'skipped',
    unzip_error: 'download|failed',
  });
  finalizeManifest(manifest);

  const markdown = formatMarkdown(manifest);

  assert.match(markdown, /keepalive\\\|metrics latest/);
  assert.match(markdown, /44\\\|45/);
  assert.match(markdown, /bad\\\|download reason/);
  assert.match(markdown, /artifacts\/keepalive\\\|metrics latest\/44\\\|45/);
});
