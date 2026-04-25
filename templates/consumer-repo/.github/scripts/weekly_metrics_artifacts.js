const fs = require('fs');

const SELECTION_SCHEMA = 'workflows-weekly-metrics-artifact-selection/v1';
const DEFAULT_LOOKBACK_DAYS = 14;
const DEFAULT_MAX_TOTAL = 80;
const DEFAULT_MAX_PER_FAMILY = 20;
const DEFAULT_MAX_SCAN_PAGES = 5;
const DEFAULT_PER_PAGE = 100;

const EXACT_METRICS_ARTIFACTS = new Set([
  'keepalive-metrics',
  'agents-autofix-metrics',
  'agents-verifier-metrics',
  'agents-verifier-disposition-metrics',
]);

const PREFIXED_METRICS_ARTIFACTS = [
  'autopilot-metrics-',
  'issue-optimizer-metrics-',
  'issue-intake-format-metrics-',
  'verifier-terminal-disposition-',
  'review-thread-terminal-disposition-',
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
  const cutoffMs = nowMs - lookbackDays * 24 * 60 * 60 * 1000;
  return {
    now_ms: nowMs,
    lookback_days: lookbackDays,
    max_total: maxTotal,
    max_per_family: maxPerFamily,
    max_scan_pages: maxScanPages,
    per_page: perPage,
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
    candidates.push(artifact);
  }

  candidates.sort((a, b) => {
    if (b.timestamp_ms !== a.timestamp_ms) return b.timestamp_ms - a.timestamp_ms;
    return Number(b.id) - Number(a.id);
  });

  const familyCounts = new Map();
  const selected = [];
  for (const artifact of candidates) {
    if (selected.length >= config.max_total) {
      stats.ignored_total_limit_count += 1;
      continue;
    }
    const familyCount = familyCounts.get(artifact.family) || 0;
    if (familyCount >= config.max_per_family) {
      stats.ignored_family_limit_count += 1;
      continue;
    }
    selected.push(artifact);
    familyCounts.set(artifact.family, familyCount + 1);
  }

  stats.selected_count = selected.length;
  return {
    schema: SELECTION_SCHEMA,
    config: {
      lookback_days: config.lookback_days,
      max_total: config.max_total,
      max_per_family: config.max_per_family,
      max_scan_pages: config.max_scan_pages,
      per_page: config.per_page,
      cutoff_iso: new Date(config.cutoff_ms).toISOString(),
    },
    ...stats,
    selected_artifacts: selected.map((artifact) => ({
      id: artifact.id,
      name: artifact.name,
      family: artifact.family,
      created_at: artifact.created_at,
      updated_at: artifact.updated_at,
    })),
  };
}

function formatArtifactTsv(artifacts = []) {
  return artifacts.map((artifact) => `${artifact.id}\t${artifact.name}`).join('\n');
}

function formatSelectionMarkdown(report) {
  const familyCounts = new Map();
  for (const artifact of report.selected_artifacts || []) {
    familyCounts.set(artifact.family, (familyCounts.get(artifact.family) || 0) + 1);
  }
  const lines = [
    '## Weekly Metrics Artifact Selection',
    '',
    `- Schema: ${report.schema}`,
    `- Lookback days: ${report.config.lookback_days}`,
    `- Scan cap: ${report.config.max_scan_pages} pages x ${report.config.per_page} artifacts`,
    `- Download cap: ${report.config.max_total} total, ${report.config.max_per_family} per family`,
    `- Scanned artifacts: ${report.scanned_count}`,
    `- Candidate artifacts: ${report.candidate_count}`,
    `- Selected artifacts: ${report.selected_count}`,
    `- Ignored: ${report.ignored_old_count} old, ${report.ignored_expired_count} expired, ` +
      `${report.ignored_name_count} non-metrics, ${report.ignored_family_limit_count} over family cap, ` +
      `${report.ignored_total_limit_count} over total cap`,
  ];

  if (familyCounts.size > 0) {
    lines.push('', '| Artifact family | Selected |', '|-----------------|----------|');
    for (const [family, count] of [...familyCounts.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      lines.push(`| ${family} | ${count} |`);
    }
  }

  return `${lines.join('\n')}\n`;
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
  return artifacts;
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
    console.error(error);
    process.exit(1);
  });
}

module.exports = {
  DEFAULT_LOOKBACK_DAYS,
  DEFAULT_MAX_PER_FAMILY,
  DEFAULT_MAX_SCAN_PAGES,
  DEFAULT_MAX_TOTAL,
  SELECTION_SCHEMA,
  artifactFamily,
  collectRepoArtifacts,
  formatArtifactTsv,
  formatSelectionMarkdown,
  normalizeSelectionOptions,
  selectMetricsArtifacts,
};
