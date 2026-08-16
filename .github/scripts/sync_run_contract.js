'use strict';

const REPORT_SCHEMA = 'workflows-consumer-sync-run/v1';
const CANARY_EVIDENCE_SCHEMA = 'workflows.consumer-sync-canary-evidence/v1';

function buildNoChangeCanaryEvidence({
  results = [],
  expectedCanaries = [],
  planId = '',
  planScope = '',
  scopeBaseSha = '',
  sourceCommit = '',
} = {}) {
  const expected = new Set(
    (expectedCanaries || []).map((repo) => String(repo || '').trim()).filter(Boolean),
  );
  const rows = [];
  const errors = [];
  const seen = new Set();
  const normalizedPlanId = String(planId || '').trim();
  const normalizedPlanScope = String(planScope || '').trim() || 'full';
  const normalizedScopeBaseSha = String(scopeBaseSha || '').trim().toLowerCase();
  const normalizedSourceCommit = String(sourceCommit || '').trim().toLowerCase();
  const shaPattern = /^[0-9a-f]{40}$/;

  for (const result of results || []) {
    const repo = String(result?.repo || '').trim();
    if (!expected.has(repo) || result?.status !== 'no_changes') continue;
    if (seen.has(repo)) {
      errors.push(`duplicate_no_change_canary:${repo}`);
      continue;
    }
    seen.add(repo);
    const resultPlanId = String(result?.plan_id || '').trim();
    const resultPlanScope = String(result?.plan_scope || '').trim() || 'full';
    const resultScopeBaseSha = String(result?.scope_base_sha || '').trim().toLowerCase();
    const resultSourceCommit = String(result?.source_commit || '').trim().toLowerCase();
    const consumerHeadSha = String(result?.consumer_head_sha || '').trim().toLowerCase();
    if (!normalizedPlanId || resultPlanId !== normalizedPlanId) {
      errors.push(`no_change_canary_plan_mismatch:${repo}`);
    }
    if (resultPlanScope !== normalizedPlanScope) {
      errors.push(`no_change_canary_scope_mismatch:${repo}`);
    }
    if (resultScopeBaseSha !== normalizedScopeBaseSha) {
      errors.push(`no_change_canary_scope_base_mismatch:${repo}`);
    }
    if (!normalizedSourceCommit || resultSourceCommit !== normalizedSourceCommit) {
      errors.push(`no_change_canary_source_mismatch:${repo}`);
    }
    if (!shaPattern.test(consumerHeadSha)) {
      errors.push(`no_change_canary_head_invalid:${repo}`);
    }
    rows.push({
      repo,
      plan_id: resultPlanId,
      plan_scope: resultPlanScope,
      scope_base_sha: resultScopeBaseSha,
      source_commit: resultSourceCommit,
      head_sha: consumerHeadSha,
      evidence_source: 'no-change-canary',
      required_check_state: 'success',
      active_review_thread_count: 0,
    });
  }

  return {
    ok: errors.length === 0,
    errors,
    evidence: {
      schema: CANARY_EVIDENCE_SCHEMA,
      version: 1,
      results: rows,
    },
  };
}

function summarizeResults(results) {
  const counts = {
    no_changes: 0,
    dry_run_changes: 0,
    existing_pr: 0,
    refreshed_pr: 0,
    created_pr: 0,
    no_committed_changes: 0,
    create_pr_failed: 0,
    sync_failed: 0,
    label_failed: 0,
    error: 0,
  };
  for (const result of results || []) {
    const status = result.status || 'error';
    if (Object.prototype.hasOwnProperty.call(counts, status)) {
      counts[status] += 1;
    } else {
      counts.error += 1;
    }
  }
  return counts;
}

function buildSyncRunReport({
  results = [],
  targetRepos = [],
  registeredRepos = [],
  templateHash = '',
  dryRun = false,
  force = false,
  run = {},
  generatedAt = new Date().toISOString(),
} = {}) {
  return {
    schema: REPORT_SCHEMA,
    generated_at: generatedAt,
    run,
    inputs: {
      repos: targetRepos,
      registered_repos: registeredRepos,
      template_hash: templateHash,
      expected_branch: templateHash ? `sync/workflows-${templateHash}` : '',
      dry_run: Boolean(dryRun),
      force: Boolean(force),
    },
    summary: summarizeResults(results),
    results,
  };
}

function buildMarkdownSummary(report) {
  const inputs = report.inputs || {};
  const summary = report.summary || {};
  const lines = [
    '## Consumer Repo Sync Summary',
    '',
    `Schema: \`${report.schema || REPORT_SCHEMA}\``,
    `Template hash: \`${inputs.template_hash || ''}\``,
    `Expected branch: \`${inputs.expected_branch || ''}\``,
    `Processed repos: ${Array.isArray(inputs.repos) ? inputs.repos.length : 0}`,
    `Dry run: ${inputs.dry_run ? 'true' : 'false'}`,
    `Force: ${inputs.force ? 'true' : 'false'}`,
    '',
    '| Status | Count |',
    '| --- | ---: |',
  ];
  for (const [status, count] of Object.entries(summary)) {
    if (count) {
      lines.push(`| ${status} | ${count} |`);
    }
  }
  lines.push('', 'Artifact: `consumer-sync-run-report`');
  return `${lines.join('\n')}\n`;
}

module.exports = {
  REPORT_SCHEMA,
  CANARY_EVIDENCE_SCHEMA,
  buildNoChangeCanaryEvidence,
  summarizeResults,
  buildSyncRunReport,
  buildMarkdownSummary,
};
