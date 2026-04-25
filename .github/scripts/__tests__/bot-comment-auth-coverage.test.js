const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  AUTH_SCHEMA,
  collectJsonFiles,
  formatBotCommentAuthCoverageMarkdown,
  isPotentialAuthCoverageFile,
  normalizeArtifactSelectionSummary,
  normalizePolicy,
  readArtifactSelectionReport,
  readJsonRecords,
  summarizeBotCommentAuthCoverage,
  summarizeOrganicEvidence,
} = require('../bot_comment_auth_coverage.js');

function record(component, authMode, runId, extra = {}) {
  return {
    schema: AUTH_SCHEMA,
    component,
    repository: 'stranske/Workflows',
    workflow: 'Agents Bot Comment Handler',
    run_id: String(runId),
    run_attempt: '1',
    event_name: 'workflow_dispatch',
    auth_mode: authMode,
    client_id_configured: authMode === 'client-id',
    legacy_app_id_configured: authMode === 'legacy-app-id',
    private_key_configured: authMode !== 'none',
    fallback_warning_active: authMode === 'legacy-app-id',
    ...extra,
  };
}

test('summarizes wrapper client-id and reusable none as passing warning-only coverage', () => {
  const report = summarizeBotCommentAuthCoverage([
    record('agents-bot-comment-handler-wrapper', 'client-id', 101),
    record('reusable-bot-comment-handler', 'none', 101),
  ]);
  const markdown = formatBotCommentAuthCoverageMarkdown(report);

  assert.equal(report.schema, 'workflows-bot-comment-auth-coverage-summary/v1');
  assert.equal(report.status, 'pass');
  assert.equal(report.mode, 'warning-only');
  assert.equal(report.auth_record_count, 2);
  assert.deepEqual(report.enforcement.blockers, []);
  assert.match(markdown, /agents-bot-comment-handler-wrapper \| client-id/);
  assert.match(markdown, /reusable-bot-comment-handler \| none/);
});

test('can require reusable caller client ID auth through policy', () => {
  const report = summarizeBotCommentAuthCoverage(
    [
      record('agents-bot-comment-handler-wrapper', 'client-id', 101),
      record('reusable-bot-comment-handler', 'none', 101),
    ],
    {
      reusable_expected_mode: 'client-id',
    }
  );

  const reusable = report.components.find(
    (component) => component.component === 'reusable-bot-comment-handler'
  );
  assert.equal(reusable.expected_mode, 'client-id');
  assert.deepEqual(reusable.blockers, ['expected-client-id-reusable-bot-comment-handler']);
  assert.equal(report.status, 'warning');
  assert.equal(report.enforcement.should_fail, false);
});

test('warns on invalid reusable expected auth mode policy', () => {
  const report = summarizeBotCommentAuthCoverage(
    [
      record('agents-bot-comment-handler-wrapper', 'client-id', 101),
      record('reusable-bot-comment-handler', 'none', 101),
    ],
    {
      reusable_expected_mode: 'client_id',
    }
  );

  const reusable = report.components.find(
    (component) => component.component === 'reusable-bot-comment-handler'
  );
  assert.equal(reusable.expected_mode, '');
  assert.equal(reusable.invalid_expected_mode, 'client_id');
  assert.ok(reusable.blockers.includes('invalid-reusable-bot-comment-handler-expected-auth-mode'));
  assert.equal(report.status, 'warning');
});

test('warns while the canonical wrapper still uses the legacy App ID fallback', () => {
  const report = summarizeBotCommentAuthCoverage([
    record('agents-bot-comment-handler-wrapper', 'legacy-app-id', 102),
    record('reusable-bot-comment-handler', 'none', 102),
  ]);

  assert.equal(report.status, 'warning');
  assert.deepEqual(report.components[0].blockers, [
    'disallowed-agents-bot-comment-handler-wrapper-auth-mode',
    'legacy-agents-bot-comment-handler-wrapper-fallback-active',
    'expected-client-id-agents-bot-comment-handler-wrapper',
  ]);
  assert.equal(report.enforcement.should_fail, false);
});

test('normalizes string boolean auth fields without false fallback warnings', () => {
  const report = summarizeBotCommentAuthCoverage([
    record('agents-bot-comment-handler-wrapper', 'client-id', 102, {
      client_id_configured: 'true',
      legacy_app_id_configured: 'false',
      private_key_configured: 'true',
      fallback_warning_active: 'false',
    }),
    record('reusable-bot-comment-handler', 'none', 102, {
      client_id_configured: 'false',
      legacy_app_id_configured: 'false',
      private_key_configured: 'false',
      fallback_warning_active: 'false',
    }),
  ]);

  assert.equal(report.status, 'pass');
  assert.equal(report.components[0].latest.fallback_warning_active, false);
  assert.equal(report.components[0].latest.legacy_app_id_configured, false);
  assert.deepEqual(report.enforcement.blockers, []);
});

test('keeps hard blocking disabled without explicit approval', () => {
  const report = summarizeBotCommentAuthCoverage(
    [record('agents-bot-comment-handler-wrapper', 'legacy-app-id', 103)],
    {
      mode: 'hard-block',
    }
  );

  assert.equal(report.status, 'warning');
  assert.equal(report.requested_mode, 'hard-block');
  assert.equal(report.mode, 'warning-only');
  assert.deepEqual(report.enforcement.policy_blockers, ['hard-block-approval-required']);
});

test('fails only when hard blocking is approved', () => {
  const report = summarizeBotCommentAuthCoverage(
    [record('agents-bot-comment-handler-wrapper', 'legacy-app-id', 104)],
    {
      mode: 'hard-block',
      hard_block_approved: true,
    }
  );

  assert.equal(report.status, 'fail');
  assert.equal(report.enforcement.hard_block_active, true);
  assert.equal(report.enforcement.should_fail, true);
});

test('summarizes selected auth artifacts from weekly artifact selection', () => {
  const summary = normalizeArtifactSelectionSummary({
    schema: 'workflows-weekly-metrics-artifact-selection/v1',
    status: 'pass',
    selected_artifacts: [
      { id: 1, name: 'keepalive-metrics', family: 'keepalive-metrics' },
      {
        id: 2,
        name: 'bot-comment-auth-coverage-wrapper-42',
        family: 'bot-comment-auth-coverage-wrapper',
      },
    ],
  });

  assert.equal(summary.selected_auth_artifact_count, 1);
  assert.equal(summary.selected_auth_artifacts[0].name, 'bot-comment-auth-coverage-wrapper-42');
});

test('warns when configured artifact selection report is missing', () => {
  const missing = readArtifactSelectionReport('/tmp/does-not-exist-bot-auth-selection.json');
  const report = summarizeBotCommentAuthCoverage([], {
    artifact_selection_report: missing,
  });
  const markdown = formatBotCommentAuthCoverageMarkdown(report);

  assert.equal(report.status, 'warning');
  assert.equal(report.artifact_selection.status, 'missing');
  assert.match(report.artifact_selection.error_message, /not found/);
  assert.ok(report.enforcement.blockers.includes('artifact-selection-warning'));
  assert.match(markdown, /Artifact selector error:/);
});

test('normalizes invalid artifact selection reports as parse errors', () => {
  const summary = normalizeArtifactSelectionSummary('not-json-object');

  assert.deepEqual(summary, {
    schema: 'workflows-weekly-metrics-artifact-selection/v1',
    status: 'parse-error',
    error_message: 'artifact selection report is not a JSON object',
    selected_auth_artifact_count: 0,
    selected_auth_artifacts: [],
  });
});

test('reports selected auth artifacts without readable input files', () => {
  const report = summarizeBotCommentAuthCoverage([], {
    artifact_selection_report: {
      schema: 'workflows-weekly-metrics-artifact-selection/v1',
      status: 'pass',
      selected_artifacts: [
        {
          id: 2,
          name: 'bot-comment-auth-coverage-wrapper-42',
          family: 'bot-comment-auth-coverage-wrapper',
        },
      ],
    },
    input_file_count: 0,
  });

  assert.equal(report.status, 'warning');
  assert.equal(report.auth_artifact_input_mismatch, true);
  assert.ok(report.enforcement.blockers.includes('selected-auth-artifacts-without-input-files'));
});

test('reads only valid auth coverage JSON records from downloaded artifacts', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bot-auth-coverage-'));
  fs.mkdirSync(path.join(dir, 'bot-comment-auth-coverage-wrapper-1'));
  fs.writeFileSync(
    path.join(dir, 'bot-comment-auth-coverage-wrapper-1', 'wrapper.json'),
    JSON.stringify(record('agents-bot-comment-handler-wrapper', 'client-id', 1)),
    'utf8'
  );
  fs.writeFileSync(path.join(dir, 'other.json'), '{"schema":"other"}', 'utf8');
  fs.writeFileSync(path.join(dir, 'broken.json'), '{"broken"', 'utf8');
  fs.writeFileSync(path.join(dir, 'metric-artifacts-selection.json'), '{}', 'utf8');

  const files = collectJsonFiles(dir);
  const result = readJsonRecords(files);

  assert.equal(files.length, 1);
  assert.equal(result.records.length, 1);
  assert.equal(result.parse_errors, 0);
  assert.equal(result.file_count, 1);
  assert.ok(files[0].endsWith('wrapper.json'));
});

test('keeps selector JSON out of auth input counts for mismatch enforcement', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bot-auth-coverage-'));
  fs.writeFileSync(path.join(dir, 'metric-artifacts-selection.json'), '{}', 'utf8');

  const files = collectJsonFiles(dir);
  const report = summarizeBotCommentAuthCoverage([], {
    input_files: files,
    input_file_count: files.length,
    artifact_selection_report: {
      schema: 'workflows-weekly-metrics-artifact-selection/v1',
      status: 'pass',
      selected_artifacts: [
        {
          id: 2,
          name: 'bot-comment-auth-coverage-wrapper-42',
          family: 'bot-comment-auth-coverage-wrapper',
        },
      ],
    },
  });

  assert.deepEqual(files, []);
  assert.equal(report.status, 'warning');
  assert.equal(report.auth_artifact_input_mismatch, true);
});

test('identifies only bot-comment auth coverage candidate files', () => {
  assert.equal(
    isPotentialAuthCoverageFile('/tmp/artifacts/bot-comment-auth-coverage-wrapper-1/wrapper.json'),
    true
  );
  assert.equal(
    isPotentialAuthCoverageFile('/tmp/artifacts/bot-comment-auth-coverage-reusable-1/reusable.json'),
    true
  );
  assert.equal(
    isPotentialAuthCoverageFile('/tmp/artifacts/bot-comment-auth-coverage-wrapper-1/123.zip'),
    false
  );
  assert.equal(isPotentialAuthCoverageFile('/tmp/artifacts/metric-artifacts-selection.json'), false);
  assert.equal(isPotentialAuthCoverageFile('/tmp/artifacts/run-view.json'), false);
});

test('normalizes bot auth coverage enforcement policy', () => {
  assert.deepEqual(normalizePolicy({ mode: 'enforce', hard_block_approved: 'yes' }), {
    schema: 'workflows-bot-comment-auth-coverage-policy/v1',
    requested_mode: 'hard-block',
    effective_mode: 'hard-block',
    default_mode: 'warning-only',
    hard_block_approved: true,
    policy_blockers: [],
  });
});

test('warns when required organic bot auth evidence is missing', () => {
  const report = summarizeBotCommentAuthCoverage(
    [
      record('agents-bot-comment-handler-wrapper', 'client-id', 301),
      record('reusable-bot-comment-handler', 'client-id', 301),
    ],
    {
      required_organic_events: 'pull_request,workflow_run',
      organic_components: 'agents-bot-comment-handler-wrapper,reusable-bot-comment-handler',
      organic_expected_mode: 'client-id',
    }
  );

  assert.equal(report.status, 'warning');
  assert.equal(report.organic_evidence.status, 'warning');
  assert.ok(
    report.enforcement.blockers.includes(
      'missing-organic-agents-bot-comment-handler-wrapper-pull_request'
    )
  );
  assert.ok(
    report.enforcement.blockers.includes(
      'missing-organic-reusable-bot-comment-handler-workflow_run'
    )
  );
});

test('passes required organic bot auth evidence when real triggers use client-id', () => {
  const records = [
    record('agents-bot-comment-handler-wrapper', 'client-id', 401, { event_name: 'pull_request' }),
    record('reusable-bot-comment-handler', 'client-id', 401, { event_name: 'pull_request' }),
    record('agents-bot-comment-handler-wrapper', 'client-id', 402, { event_name: 'workflow_run' }),
    record('reusable-bot-comment-handler', 'client-id', 402, { event_name: 'workflow_run' }),
  ];

  const organic = summarizeOrganicEvidence(records, {
    required_organic_events: ['pull_request', 'workflow_run'],
    organic_expected_mode: 'client-id',
  });
  const report = summarizeBotCommentAuthCoverage(records, {
    required_organic_events: ['pull_request', 'workflow_run'],
    organic_expected_mode: 'client-id',
  });

  assert.equal(organic.status, 'pass');
  assert.equal(organic.event_counts['agents-bot-comment-handler-wrapper'].pull_request, 1);
  assert.equal(report.status, 'pass');
  assert.deepEqual(report.enforcement.blockers, []);
});
