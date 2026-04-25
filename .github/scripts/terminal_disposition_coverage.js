const fs = require('fs');
const path = require('path');

const {
  normalizeTerminalDisposition,
  sourceKey,
} = require('./terminal_disposition.js');

const COVERAGE_SCHEMA = 'workflows-terminal-disposition-coverage/v1';
const TERMINAL_SCHEMA = 'workflows-terminal-disposition/v1';

function cleanString(value) {
  if (value === null || value === undefined) return '';
  return String(value).trim();
}

function cleanInt(value) {
  const text = cleanString(value);
  if (!text) return null;
  const parsed = Number.parseInt(text, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeExpectedSource(input = {}) {
  const sourceType = cleanString(input.source_type ?? input.sourceType) || 'review-thread';
  const prNumber = cleanInt(input.pr_number ?? input.prNumber ?? input.pr);
  const sourceId = cleanString(input.source_id ?? input.sourceId) || (
    prNumber === null ? 'unknown' : String(prNumber)
  );
  const key = sourceKey(sourceType, sourceId);
  return {
    source_type: key.split(':')[0],
    source_id: sourceId,
    source_key: key,
    pr_number: prNumber,
    reason: cleanString(input.reason) || 'expected-source',
  };
}

function isTerminalDispositionRecord(record) {
  return Boolean(record && typeof record === 'object' && record.schema === TERMINAL_SCHEMA);
}

function expectedReviewThreadSources(records = []) {
  const expected = new Map();
  for (const raw of records) {
    if (!isTerminalDispositionRecord(raw)) continue;
    const record = normalizeTerminalDisposition(raw);
    const prNumber = cleanInt(record.pr_number);
    if (prNumber === null) continue;
    const source = normalizeExpectedSource({
      source_type: 'review-thread',
      source_id: prNumber,
      pr_number: prNumber,
      reason: 'pr-terminal-disposition-activity',
    });
    expected.set(source.source_key, source);
  }
  return [...expected.values()].sort((a, b) => a.source_key.localeCompare(b.source_key));
}

function summarizeTerminalDispositionCoverage(records = [], options = {}) {
  const parseErrors = Number(options.parse_errors || options.parseErrors || 0);
  const terminalRecords = records
    .filter(isTerminalDispositionRecord)
    .map((record) => normalizeTerminalDisposition(record));
  const observed = new Map();

  for (const record of terminalRecords) {
    const existing = observed.get(record.source_key) || {
      source_type: record.source_type,
      source_id: record.source_id,
      source_key: record.source_key,
      count: 0,
      dispositions: {},
      pr_numbers: new Set(),
    };
    existing.count += 1;
    existing.dispositions[record.disposition] = (existing.dispositions[record.disposition] || 0) + 1;
    const prNumber = cleanInt(record.pr_number);
    if (prNumber !== null) existing.pr_numbers.add(prNumber);
    observed.set(record.source_key, existing);
  }

  const expectedSources = (
    Array.isArray(options.expected_sources) ? options.expected_sources : options.expectedSources
  ) || expectedReviewThreadSources(terminalRecords);
  const expected = expectedSources.map((source) => normalizeExpectedSource(source));
  const missing = expected.filter((source) => !observed.has(source.source_key));
  const covered = expected.filter((source) => observed.has(source.source_key));
  const observedSources = [...observed.values()]
    .map((source) => ({
      source_type: source.source_type,
      source_id: source.source_id,
      source_key: source.source_key,
      count: source.count,
      dispositions: source.dispositions,
      pr_numbers: [...source.pr_numbers].sort((a, b) => a - b),
    }))
    .sort((a, b) => a.source_key.localeCompare(b.source_key));

  let status = 'pass';
  if (terminalRecords.length === 0) {
    status = 'no-data';
  } else if (missing.length > 0 || parseErrors > 0) {
    status = 'warning';
  }

  return {
    schema: COVERAGE_SCHEMA,
    status,
    mode: 'warning-only',
    terminal_record_count: terminalRecords.length,
    observed_source_count: observedSources.length,
    expected_source_count: expected.length,
    covered_source_count: covered.length,
    missing_source_count: missing.length,
    parse_errors: parseErrors,
    observed_sources: observedSources,
    expected_sources: expected,
    missing_sources: missing,
  };
}

function formatDispositions(dispositions = {}) {
  const parts = Object.entries(dispositions)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([name, count]) => `${name} (${count})`);
  return parts.length ? parts.join(', ') : 'n/a';
}

function formatTerminalDispositionCoverageMarkdown(report) {
  const lines = [
    '## Terminal Disposition Coverage Preflight',
    '',
    '- Mode: warning-only (does not block merges or automation)',
    `- Status: ${report.status}`,
    `- Terminal disposition records: ${report.terminal_record_count}`,
    `- Observed sources: ${report.observed_source_count}`,
    `- Expected review-thread sources: ${report.expected_source_count}`,
    `- Missing review-thread sources: ${report.missing_source_count}`,
    `- Parse errors: ${report.parse_errors}`,
  ];

  if (report.missing_sources.length > 0) {
    lines.push('', '| Missing source | Reason |', '|----------------|--------|');
    for (const source of report.missing_sources) {
      lines.push(`| ${source.source_key} | ${source.reason} |`);
    }
  }

  if (report.observed_sources.length > 0) {
    lines.push('', '| Observed source | Records | Dispositions | PRs |', '|-----------------|---------|--------------|-----|');
    for (const source of report.observed_sources) {
      const prs = source.pr_numbers.length ? source.pr_numbers.map((value) => `#${value}`).join(', ') : 'n/a';
      lines.push(
        `| ${source.source_key} | ${source.count} | ${formatDispositions(source.dispositions)} | ${prs} |`
      );
    }
  }

  if (report.status === 'no-data') {
    lines.push('', '_No terminal disposition records were found in the metrics input._');
  }

  return `${lines.join('\n')}\n`;
}

function collectNdjsonFiles(root) {
  const files = [];
  const stack = [root];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current || !fs.existsSync(current)) continue;
    const stat = fs.statSync(current);
    if (stat.isFile()) {
      if (current.endsWith('.ndjson')) files.push(current);
      continue;
    }
    if (!stat.isDirectory()) continue;
    for (const entry of fs.readdirSync(current)) {
      stack.push(path.join(current, entry));
    }
  }
  return files.sort();
}

function readNdjsonFiles(files = []) {
  const records = [];
  let parseErrors = 0;
  for (const file of files) {
    let text = '';
    try {
      text = fs.readFileSync(file, 'utf8');
    } catch (_error) {
      parseErrors += 1;
      continue;
    }
    for (const line of text.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          records.push(parsed);
        } else {
          parseErrors += 1;
        }
      } catch (_error) {
        parseErrors += 1;
      }
    }
  }
  return { records, parse_errors: parseErrors };
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    metrics_dir: process.env.TERMINAL_DISPOSITION_METRICS_DIR || 'artifacts',
    output_json: process.env.TERMINAL_DISPOSITION_COVERAGE_JSON || 'terminal-disposition-coverage.json',
    output_md: process.env.TERMINAL_DISPOSITION_COVERAGE_MD || 'terminal-disposition-coverage.md',
    inputs: [],
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === '--metrics-dir') {
      options.metrics_dir = next;
      index += 1;
    } else if (arg === '--output-json') {
      options.output_json = next;
      index += 1;
    } else if (arg === '--output-md') {
      options.output_md = next;
      index += 1;
    } else if (arg === '--input') {
      options.inputs.push(next);
      index += 1;
    } else if (arg === '--required-sources-json') {
      options.required_sources_json = next;
      index += 1;
    }
  }

  return options;
}

function parseExpectedSources(options = {}) {
  const raw = options.required_sources_json || process.env.TERMINAL_DISPOSITION_REQUIRED_SOURCES || '';
  if (!raw.trim()) return undefined;
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed)) {
    throw new Error('required sources must be a JSON array');
  }
  return parsed;
}

function main() {
  const options = parseArgs();
  const inputFiles = options.inputs.length > 0
    ? options.inputs
    : collectNdjsonFiles(options.metrics_dir);
  const { records, parse_errors: parseErrors } = readNdjsonFiles(inputFiles);
  const expectedSources = parseExpectedSources(options);
  const report = summarizeTerminalDispositionCoverage(records, {
    parse_errors: parseErrors,
    expected_sources: expectedSources,
  });
  const markdown = formatTerminalDispositionCoverageMarkdown(report);
  fs.writeFileSync(options.output_json, `${JSON.stringify(report, null, 2)}\n`);
  fs.writeFileSync(options.output_md, markdown);
  process.stdout.write(markdown);
}

if (require.main === module) {
  main();
}

module.exports = {
  COVERAGE_SCHEMA,
  expectedReviewThreadSources,
  formatTerminalDispositionCoverageMarkdown,
  normalizeExpectedSource,
  readNdjsonFiles,
  summarizeTerminalDispositionCoverage,
};
