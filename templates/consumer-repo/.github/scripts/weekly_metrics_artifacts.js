const fs = require('fs');

const SELECTION_SCHEMA = 'workflows-weekly-metrics-artifact-selection/v1';
const DEFAULT_LOOKBACK_DAYS = 14;
const DEFAULT_MAX_TOTAL = 80;
const DEFAULT_MAX_PER_FAMILY = 20;
const DEFAULT_MAX_SCAN_PAGES = 5;
const DEFAULT_PER_PAGE = 100;
const DEFAULT_PRIORITY_WORKFLOW_RUNS_PER_SOURCE = 10;

const EXACT_METRICS_ARTIFACTS = new Set([
  'keepalive-metrics',
  'agents-autofix-metrics',
  'agents-verifier-metrics',
  'agents-verifier-disposition-metrics',
  'codex-cli-freshness',
  'pr-source-context',
]);

const PREFIXED_METRICS_ARTIFACTS = [
  'autopilot-metrics-',
  'issue-optimizer-metrics-',
  'issue-intake-format-metrics-',
  'codex-cli-freshness-',
  'verifier-terminal-disposition-',
  'review-thread-terminal-disposition-',
];

const PATTERNED_METRICS_ARTIFACTS = [
  {
    family: 'bot-comment-auth-coverage-wrapper',
    pattern: /^bot-comment-auth-coverage-wrapper(?:-[A-Za-z0-9][A-Za-z0-9._-]*)?$/,
  },
  {
    family: 'bot-comment-auth-coverage-reusable',
    pattern: /^bot-comment-auth-coverage-reusable(?:-[A-Za-z0-9][A-Za-z0-9._-]*)?$/,
  },
];

const PRIORITY_METRICS_FAMILIES = [
  'codex-cli-freshness',
  'verifier-terminal-disposition',
  'review-thread-terminal-disposition',
  'bot-comment-auth-coverage-wrapper',
  'bot-comment-auth-coverage-reusable',
  'pr-source-context',
];

const PRIORITY_WORKFLOW_ARTIFACT_SOURCES = [
  {
    workflow_id: 'health-76-codex-cli-freshness.yml',
    families: ['codex-cli-freshness'],
  },
  {
    workflow_id: 'reusable-agents-verifier.yml',
    families: ['verifier-terminal-disposition'],
  },
  {
    workflow_id: 'agents-verify-to-new-pr.yml',
    families: ['verifier-terminal-disposition'],
  },
  {
    workflow_id: 'agents-verify-to-issue-v2.yml',
    families: ['verifier-terminal-disposition'],
  },
  {
    workflow_id: 'agents-bot-comment-handler.yml',
    families: ['review-thread-terminal-disposition', 'bot-comment-auth-coverage-wrapper'],
  },
  {
    workflow_id: 'reusable-bot-comment-handler.yml',
    families: ['review-thread-terminal-disposition', 'bot-comment-auth-coverage-reusable'],
  },
  {
    workflow_id: 'pr-11-ci-smoke.yml',
    families: ['pr-source-context'],
  },
];

function cleanString(value) {
  if (value === null || value === undefined) return '';
  return String(value).trim();
}

function parsePositiveInt(value, fallback) {
  const parsed = Number.parseInt(cleanString(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseDateMs(value) {
  const text = cleanString(value);
  if (!text) return 0;
  const parsed = Date.parse(text);
  return Number.isFinite(parsed) ? parsed : 0;
}

function artifactTimestampMs(artifact = {}) {
  return Math.max(
    parseDateMs(artifact.created_at ?? artifact.createdAt),
    parseDateMs(artifact.updated_at ?? artifact.updatedAt)
  );
}

function artifactFamily(name) {
  const cleaned = cleanString(name);
  if (EXACT_METRICS_ARTIFACTS.has(cleaned)) return cleaned;
  const patterned = PATTERNED_METRICS_ARTIFACTS.find((candidate) =>
    candidate.pattern.test(cleaned)
  );
  if (patterned) return patterned.family;
  const prefix = PREFIXED_METRICS_ARTIFACTS.find((candidate) => cleaned.startsWith(candidate));
  return prefix ? prefix.replace(/-$/, '') : '';
}

function normalizeSelectionOptions(options = {}) {
  const nowMs = Number.isFinite(options.now_ms) ? options.now_ms : Date.now();
  const lookbackDays = parsePositiveInt(
    options.lookback_days ?? options.lookbackDays ?? process.env.METRICS_ARTIFACT_LOOKBACK_DAYS,
    DEFAULT_LOOKBACK_DAYS
  );
  const maxTotal = parsePositiveInt(
    options.max_total ?? options.maxTotal ?? process.env.METRICS_ARTIFACT_MAX_TOTAL,
    DEFAULT_MAX_TOTAL
  );
  const maxPerFamily = parsePositiveInt(
    options.max_per_family ?? options.maxPerFamily ?? process.env.METRICS_ARTIFACT_MAX_PER_FAMILY,
    DEFAULT_MAX_PER_FAMILY
  );
  const maxScanPages = parsePositiveInt(
    options.max_scan_pages ?? options.maxScanPages ?? process.env.METRICS_ARTIFACT_MAX_SCAN_PAGES,
    DEFAULT_MAX_SCAN_PAGES
  );
  const perPage = parsePositiveInt(
    options.per_page ?? options.perPage ?? process.env.METRICS_ARTIFACTS_PER_PAGE,
    DEFAULT_PER_PAGE
  );
  const priorityWorkflowRunsPerSource = parsePositiveInt(
    options.priority_workflow_runs_per_source ??
      options.priorityWorkflowRunsPerSource ??
      process.env.METRICS_PRIORITY_WORKFLOW_RUNS_PER_SOURCE,
    DEFAULT_PRIORITY_WORKFLOW_RUNS_PER_SOURCE
  );
  const cutoffMs = nowMs - lookbackDays * 24 * 60 * 60 * 1000;
  return {
    now_ms: nowMs,
    lookback_days: lookbackDays,
    max_total: maxTotal,
    max_per_family: maxPerFamily,
    max_scan_pages: maxScanPages,
    per_page: perPage,
    priority_workflow_runs_per_source: priorityWorkflowRunsPerSource,
    cutoff_ms: cutoffMs,
  };
}

function normalizeArtifact(raw = {}) {
  const id = raw.id ?? raw.artifact_id ?? raw.artifactId;
  return {
    id,
    name: cleanString(raw.name),
    expired: Boolean(raw.expired),
    created_at: cleanString(raw.created_at ?? raw.createdAt),
    updated_at: cleanString(raw.updated_at ?? raw.updatedAt),
    family: artifactFamily(raw.name),
    timestamp_ms: artifactTimestampMs(raw),
  };
}

function sortedCountObject(counts) {
  return Object.fromEntries(
    [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  );
}

function missingPriorityFamilies(candidateFamilyCounts = new Map()) {
  return PRIORITY_METRICS_FAMILIES.filter((family) => !candidateFamilyCounts.has(family));
}

function priorityFamilyStatuses({
  candidates = [],
  selected = [],
  candidateFamilyCounts = new Map(),
  selectedFamilyCounts = new Map(),
} = {}) {
  return PRIORITY_METRICS_FAMILIES.map((family) => {
    const latestCandidate = candidates.find((candidate) => candidate.family === family);
    const selectedArtifact = selected.find((artifact) => artifact.family === family);
    return {
      family,
      status: selectedArtifact ? 'selected' : candidateFamilyCounts.has(family) ? 'available' : 'missing',
      candidate_count: candidateFamilyCounts.get(family) || 0,
      selected_count: selectedFamilyCounts.get(family) || 0,
      latest_candidate: latestCandidate
        ? {
            id: latestCandidate.id,
            name: latestCandidate.name,
            created_at: latestCandidate.created_at,
            updated_at: latestCandidate.updated_at,
          }
        : null,
      selected_artifact: selectedArtifact
        ? {
            id: selectedArtifact.id,
            name: selectedArtifact.name,
            created_at: selectedArtifact.created_at,
            updated_at: selectedArtifact.updated_at,
          }
        : null,
    };
  });
}

function latestCandidateByFamily(candidates = []) {
  const latestByFamily = new Map();
  for (const candidate of candidates) {
    const family = cleanString(candidate.family);
    if (!PRIORITY_METRICS_FAMILIES.includes(family)) continue;
    const existing = latestByFamily.get(family);
    const candidateTimestamp = Number(candidate.timestamp_ms) || artifactTimestampMs(candidate);
    const existingTimestamp = existing ? Number(existing.timestamp_ms) || artifactTimestampMs(existing) : -1;
    const candidateId = Number(candidate.id) || 0;
    const existingId = existing ? Number(existing.id) || 0 : -1;
    if (
      !existing ||
      candidateTimestamp > existingTimestamp ||
      (candidateTimestamp === existingTimestamp && candidateId > existingId)
    ) {
      latestByFamily.set(family, candidate);
    }
  }
  const entries = [];
  for (const family of PRIORITY_METRICS_FAMILIES) {
    const latestCandidate = latestByFamily.get(family);
    if (!latestCandidate) continue;
    entries.push([
      family,
      {
        id: latestCandidate.id,
        name: latestCandidate.name,
        created_at: latestCandidate.created_at,
        updated_at: latestCandidate.updated_at,
      },
    ]);
  }
  return Object.fromEntries(entries);
}

function selectMetricsArtifacts(artifacts = [], options = {}) {
  const config = normalizeSelectionOptions(options);
  const stats = {
    scanned_count: artifacts.length,
    candidate_count: 0,
    selected_count: 0,
    ignored_expired_count: 0,
    ignored_name_count: 0,
    ignored_old_count: 0,
    ignored_family_limit_count: 0,
    ignored_total_limit_count: 0,
  };

  const candidates = [];
  const candidateFamilyCounts = new Map();
  for (const raw of artifacts) {
    const artifact = normalizeArtifact(raw);
    if (!artifact.id || !artifact.name) {
      stats.ignored_name_count += 1;
      continue;
    }
    if (artifact.expired) {
      stats.ignored_expired_count += 1;
      continue;
    }
    if (!artifact.family) {
      stats.ignored_name_count += 1;
      continue;
    }
    if (artifact.timestamp_ms > 0 && artifact.timestamp_ms < config.cutoff_ms) {
      stats.ignored_old_count += 1;
      continue;
    }
    stats.candidate_count += 1;
    candidateFamilyCounts.set(artifact.family, (candidateFamilyCounts.get(artifact.family) || 0) + 1);
    candidates.push(artifact);
  }

  candidates.sort((a, b) => {
    if (b.timestamp_ms !== a.timestamp_ms) return b.timestamp_ms - a.timestamp_ms;
    return Number(b.id) - Number(a.id);
  });

  const familyCounts = new Map();
  const selected = [];
  const selectedIds = new Set();

  function selectArtifact(artifact) {
    if (selected.length >= config.max_total) {
      return false;
    }
    const familyCount = familyCounts.get(artifact.family) || 0;
    if (familyCount >= config.max_per_family) {
      return false;
    }
    selected.push(artifact);
    selectedIds.add(String(artifact.id));
    familyCounts.set(artifact.family, familyCount + 1);
    return true;
  }

  for (const family of PRIORITY_METRICS_FAMILIES) {
    const artifact = candidates.find((candidate) => candidate.family === family);
    if (artifact) selectArtifact(artifact);
  }

  for (const artifact of candidates) {
    if (selectedIds.has(String(artifact.id))) continue;
    if (selected.length >= config.max_total) {
      stats.ignored_total_limit_count += 1;
      continue;
    }
    const familyCount = familyCounts.get(artifact.family) || 0;
    if (familyCount >= config.max_per_family) {
      stats.ignored_family_limit_count += 1;
      continue;
    }
    selectArtifact(artifact);
  }

  stats.selected_count = selected.length;
  return {
    schema: SELECTION_SCHEMA,
    status: 'pass',
    config: {
      lookback_days: config.lookback_days,
      max_total: config.max_total,
      max_per_family: config.max_per_family,
      max_scan_pages: config.max_scan_pages,
      per_page: config.per_page,
      priority_workflow_runs_per_source: config.priority_workflow_runs_per_source,
      cutoff_iso: new Date(config.cutoff_ms).toISOString(),
    },
    ...stats,
    candidate_family_counts: sortedCountObject(candidateFamilyCounts),
    selected_family_counts: sortedCountObject(familyCounts),
    latest_candidate_by_family: latestCandidateByFamily(candidates),
    missing_priority_families: missingPriorityFamilies(candidateFamilyCounts),
    priority_family_statuses: priorityFamilyStatuses({
      candidates,
      selected,
      candidateFamilyCounts,
      selectedFamilyCounts: familyCounts,
    }),
    selected_artifacts: selected.map((artifact) => ({
      id: artifact.id,
      name: artifact.name,
      family: artifact.family,
      created_at: artifact.created_at,
      updated_at: artifact.updated_at,
    })),
  };
}

function buildSelectionErrorReport(options = {}, error = {}) {
  const config = normalizeSelectionOptions(options);
  return {
    schema: SELECTION_SCHEMA,
    status: 'error',
    error_message: cleanString(error?.message || error) || 'Unknown artifact selection error',
    config: {
      lookback_days: config.lookback_days,
      max_total: config.max_total,
      max_per_family: config.max_per_family,
      max_scan_pages: config.max_scan_pages,
      per_page: config.per_page,
      priority_workflow_runs_per_source: config.priority_workflow_runs_per_source,
      cutoff_iso: new Date(config.cutoff_ms).toISOString(),
    },
    scanned_count: 0,
    candidate_count: 0,
    selected_count: 0,
    ignored_expired_count: 0,
    ignored_name_count: 0,
    ignored_old_count: 0,
    ignored_family_limit_count: 0,
    ignored_total_limit_count: 0,
    candidate_family_counts: {},
    selected_family_counts: {},
    latest_candidate_by_family: {},
    missing_priority_families: [...PRIORITY_METRICS_FAMILIES],
    priority_family_statuses: priorityFamilyStatuses(),
    selected_artifacts: [],
  };
}

function formatArtifactTsv(artifacts = []) {
  return artifacts.map((artifact) => `${artifact.id}\t${artifact.name}`).join('\n');
}

function formatSelectionMarkdown(report) {
  const candidateFamilyCounts = report.candidate_family_counts || {};
  const selectedFamilyCounts = report.selected_family_counts || {};
  const familyNames = [...new Set([
    ...Object.keys(candidateFamilyCounts),
    ...Object.keys(selectedFamilyCounts),
  ])].sort((a, b) => a.localeCompare(b));
  const lines = [
    '## Weekly Metrics Artifact Selection',
    '',
    `- Schema: ${report.schema}`,
    `- Status: ${report.status || 'pass'}`,
    `- Lookback days: ${report.config.lookback_days}`,
    `- Scan cap: ${report.config.max_scan_pages} pages x ${report.config.per_page} artifacts`,
    `- Priority producer scan cap: ${report.config.priority_workflow_runs_per_source} runs per source workflow`,
    `- Download cap: ${report.config.max_total} total, ${report.config.max_per_family} per family`,
    `- Scanned artifacts: ${report.scanned_count}`,
    `- Candidate artifacts: ${report.candidate_count}`,
    `- Selected artifacts: ${report.selected_count}`,
    `- Missing priority families: ${(report.missing_priority_families || []).join(', ') || 'none'}`,
    `- Ignored: ${report.ignored_old_count} old, ${report.ignored_expired_count} expired, ` +
      `${report.ignored_name_count} non-metrics, ${report.ignored_family_limit_count} over family cap, ` +
      `${report.ignored_total_limit_count} over total cap`,
  ];

  if (report.status === 'error') {
    lines.push(`- Error: ${report.error_message || 'Unknown artifact selection error'}`);
  }

  if (familyNames.length > 0) {
    lines.push('', '| Artifact family | Candidates | Selected |', '|-----------------|------------|----------|');
    for (const family of familyNames) {
      lines.push(`| ${family} | ${candidateFamilyCounts[family] || 0} | ${selectedFamilyCounts[family] || 0} |`);
    }
  }

  if (Array.isArray(report.priority_family_statuses) && report.priority_family_statuses.length > 0) {
    lines.push('', '| Priority family | Status | Candidates | Selected artifact |');
    lines.push('|-----------------|--------|------------|-------------------|');
    for (const family of report.priority_family_statuses) {
      lines.push([
        family.family,
        family.status,
        family.candidate_count || 0,
        family.selected_artifact?.name || 'none',
      ].join(' | ').replace(/^/, '| ').replace(/$/, ' |'));
    }
  }

  return `${lines.join('\n')}\n`;
}

function dedupeArtifacts(artifacts = []) {
  const seen = new Set();
  const deduped = [];
  for (const artifact of artifacts) {
    const id = artifact?.id ?? artifact?.artifact_id ?? artifact?.artifactId;
    const key = id
      ? `id:${id}`
      : `name:${cleanString(artifact?.name)}:${cleanString(artifact?.created_at ?? artifact?.createdAt)}`;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    deduped.push(artifact);
  }
  return deduped;
}

function familiesSatisfied(artifacts = [], families = [], config = normalizeSelectionOptions()) {
  const found = new Set();
  for (const raw of artifacts) {
    const artifact = normalizeArtifact(raw);
    if (!artifact.id || artifact.expired || !artifact.family || !families.includes(artifact.family)) {
      continue;
    }
    if (artifact.timestamp_ms > 0 && artifact.timestamp_ms < config.cutoff_ms) {
      continue;
    }
    found.add(artifact.family);
  }
  return families.every((family) => found.has(family));
}

function isNotFoundError(error) {
  return Number(error?.status) === 404 || Number(error?.response?.status) === 404;
}

async function collectPriorityWorkflowArtifacts({
  github,
  owner,
  repo,
  withRetry,
  options,
  sources = PRIORITY_WORKFLOW_ARTIFACT_SOURCES,
}) {
  const config = normalizeSelectionOptions(options);
  const artifacts = [];
  for (const source of sources) {
    const workflowId = cleanString(source.workflow_id ?? source.workflowId);
    const families = (source.families || []).map(cleanString).filter(Boolean);
    if (!workflowId || families.length === 0) continue;
    let runsResponse;
    try {
      runsResponse = await withRetry((client) => client.rest.actions.listWorkflowRuns({
        owner,
        repo,
        workflow_id: workflowId,
        per_page: config.priority_workflow_runs_per_source,
      }));
    } catch (error) {
      if (isNotFoundError(error)) continue;
      throw error;
    }
    const runs = runsResponse?.data?.workflow_runs || [];
    for (const run of runs) {
      const runTimestamp = Math.max(
        parseDateMs(run.created_at ?? run.createdAt),
        parseDateMs(run.updated_at ?? run.updatedAt)
      );
      if (runTimestamp > 0 && runTimestamp < config.cutoff_ms) {
        continue;
      }
      let artifactResponse;
      try {
        artifactResponse = await withRetry((client) =>
          client.rest.actions.listWorkflowRunArtifacts({
            owner,
            repo,
            run_id: run.id,
            per_page: config.per_page,
          })
        );
      } catch (error) {
        if (isNotFoundError(error)) continue;
        throw error;
      }
      const matchingArtifacts = (artifactResponse?.data?.artifacts || []).filter((artifact) =>
        families.includes(artifactFamily(artifact.name))
      );
      artifacts.push(...matchingArtifacts);
      if (familiesSatisfied(artifacts, families, config)) {
        break;
      }
    }
  }
  return dedupeArtifacts(artifacts);
}

async function collectRepoArtifacts({ github, owner, repo, withRetry, options }) {
  const artifacts = [];
  const config = normalizeSelectionOptions(options);
  for (let page = 1; page <= config.max_scan_pages; page += 1) {
    const response = await withRetry((client) => client.rest.actions.listArtifactsForRepo({
      owner,
      repo,
      per_page: config.per_page,
      page,
    }));
    const pageArtifacts = response?.data?.artifacts || [];
    artifacts.push(...pageArtifacts);
    if (pageArtifacts.length < config.per_page) break;
    if (
      pageArtifacts.length > 0 &&
      pageArtifacts.every((artifact) => {
        const timestamp = artifactTimestampMs(artifact);
        return timestamp > 0 && timestamp < config.cutoff_ms;
      })
    ) {
      break;
    }
  }
  const priorityArtifacts = await collectPriorityWorkflowArtifacts({
    github,
    owner,
    repo,
    withRetry,
    options,
  });
  return dedupeArtifacts([...artifacts, ...priorityArtifacts]);
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    output: process.env.METRICS_ARTIFACT_LIST || 'artifacts/metric-artifacts.tsv',
    report: process.env.METRICS_ARTIFACT_SELECTION_JSON || 'artifacts/metric-artifacts-selection.json',
    markdown: process.env.METRICS_ARTIFACT_SELECTION_MD || '',
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === '--output') {
      options.output = next;
      index += 1;
    } else if (arg === '--report') {
      options.report = next;
      index += 1;
    } else if (arg === '--markdown') {
      options.markdown = next;
      index += 1;
    } else if (arg === '--lookback-days') {
      options.lookback_days = next;
      index += 1;
    } else if (arg === '--max-total') {
      options.max_total = next;
      index += 1;
    } else if (arg === '--max-per-family') {
      options.max_per_family = next;
      index += 1;
    } else if (arg === '--max-scan-pages') {
      options.max_scan_pages = next;
      index += 1;
    } else if (arg === '--priority-workflow-runs-per-source') {
      options.priority_workflow_runs_per_source = next;
      index += 1;
    }
  }

  return options;
}

async function main() {
  const options = parseArgs();
  const { Octokit } = require('@octokit/rest');
  const { createTokenAwareRetry } = require('./github-api-with-retry.js');
  const core = { info: () => {}, warning: console.warn, debug: () => {} };
  const [owner, repo] = process.env.GITHUB_REPOSITORY.split('/');
  const github = new Octokit({ auth: process.env.GH_TOKEN || process.env.GITHUB_TOKEN });
  const { withRetry } = await createTokenAwareRetry({
    github,
    core,
    env: process.env,
    task: 'agents-weekly-metrics-artifacts',
    capabilities: ['actions:read'],
  });
  const artifacts = await collectRepoArtifacts({ github, owner, repo, withRetry, options });
  const selection = selectMetricsArtifacts(artifacts, options);
  fs.writeFileSync(options.output, formatArtifactTsv(selection.selected_artifacts));
  if (selection.selected_artifacts.length > 0) {
    fs.appendFileSync(options.output, '\n');
  }
  fs.writeFileSync(options.report, `${JSON.stringify(selection, null, 2)}\n`);
  if (options.markdown) {
    fs.writeFileSync(options.markdown, formatSelectionMarkdown(selection));
  }
  process.stdout.write(`${JSON.stringify(selection, null, 2)}\n`);
}

if (require.main === module) {
  main().catch((error) => {
    const options = parseArgs();
    const selection = buildSelectionErrorReport(options, error);
    try {
      const path = require('path');
      fs.mkdirSync(path.dirname(options.output), { recursive: true });
      fs.mkdirSync(path.dirname(options.report), { recursive: true });
      if (options.markdown) {
        fs.mkdirSync(path.dirname(options.markdown), { recursive: true });
      }
      fs.writeFileSync(options.output, '');
      fs.writeFileSync(options.report, `${JSON.stringify(selection, null, 2)}\n`);
      if (options.markdown) {
        fs.writeFileSync(options.markdown, formatSelectionMarkdown(selection));
      }
    } catch (writeError) {
      console.error(writeError);
    }
    console.error(error);
    process.exit(1);
  });
}

module.exports = {
  DEFAULT_LOOKBACK_DAYS,
  DEFAULT_MAX_PER_FAMILY,
  DEFAULT_MAX_SCAN_PAGES,
  DEFAULT_MAX_TOTAL,
  DEFAULT_PRIORITY_WORKFLOW_RUNS_PER_SOURCE,
  PRIORITY_METRICS_FAMILIES,
  PRIORITY_WORKFLOW_ARTIFACT_SOURCES,
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
};
