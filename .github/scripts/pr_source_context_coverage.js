'use strict';

const fs = require('node:fs');
const path = require('node:path');

const COVERAGE_SCHEMA = 'workflows-pr-source-context-coverage/v1';
const SOURCE_CONTEXT_SCHEMA = 'workflows-pr-source-context/v1';

function cleanString(value) {
  return String(value || '').trim();
}

function ensureParentDirectory(filePath) {
  if (!filePath) return;
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function increment(map, key) {
  const cleanKey = cleanString(key) || 'unknown';
  map.set(cleanKey, (map.get(cleanKey) || 0) + 1);
}

function sortedObject(map) {
  return Object.fromEntries([...map.entries()].sort((a, b) => a[0].localeCompare(b[0])));
}

function walkFiles(root) {
  if (!root || !fs.existsSync(root)) return [];
  const stat = fs.statSync(root);
  if (stat.isFile()) return [root];
  const files = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(fullPath));
    } else if (entry.isFile()) {
      files.push(fullPath);
    }
  }
  return files;
}

function readSourceContextReports(root) {
  const reports = [];
  const parse_errors = [];
  for (const file of walkFiles(root)) {
    if (path.basename(file) !== 'pr-source-context.json') {
      continue;
    }
    try {
      const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (parsed && parsed.schema === SOURCE_CONTEXT_SCHEMA) {
        reports.push({ path: file, report: parsed });
      }
    } catch (error) {
      parse_errors.push({
        path: file,
        reason: error instanceof Error ? error.message : String(error),
      });
    }
  }
  return { reports, parse_errors };
}

function buildCoverageReport(options = {}) {
  const root = cleanString(options.root || options.dir) || 'artifacts';
  const now = options.now || new Date().toISOString();
  const { reports, parse_errors } = readSourceContextReports(root);
  const statusCounts = new Map();
  const reasonCounts = new Map();
  const sourceTypeCounts = new Map();
  let explicitCount = 0;
  let inferredCount = 0;
  let validCount = 0;
  let unknownCount = 0;
  let taskListRecords = 0;
  let taskItemsTotal = 0;
  let taskItemsOpen = 0;
  let taskItemsCompleted = 0;
  const openTaskPrs = [];
  const unknownSourcePrs = [];

  for (const item of reports) {
    const report = item.report || {};
    const source = report.source_context || {};
    const taskList = report.task_list || {};
    const pr = report.pull_request || {};
    const status = cleanString(report.status) || 'unknown';
    const reason = cleanString(report.reason) || 'unknown';
    const sourceType = cleanString(source.sourceType) || 'unknown';
    increment(statusCounts, status);
    increment(reasonCounts, reason);
    increment(sourceTypeCounts, sourceType);
    if (source.isValid) validCount += 1;
    if (source.isExplicit) explicitCount += 1;
    else inferredCount += 1;
    if (sourceType === 'unknown' || !source.isValid) {
      unknownCount += 1;
      if (unknownSourcePrs.length < 20) {
        unknownSourcePrs.push({
          number: pr.number || null,
          title: cleanString(pr.title),
          head_ref: cleanString(pr.head_ref),
          report_path: item.path,
        });
      }
    }
    if (taskList.has_task_list) {
      taskListRecords += 1;
    }
    const total = Number(taskList.total || 0);
    const open = Number(taskList.open_item_count ?? taskList.unchecked ?? 0);
    const completed = Number(taskList.completed_item_count ?? taskList.checked ?? 0);
    taskItemsTotal += Number.isFinite(total) ? total : 0;
    taskItemsOpen += Number.isFinite(open) ? open : 0;
    taskItemsCompleted += Number.isFinite(completed) ? completed : 0;
    if (open > 0 && openTaskPrs.length < 20) {
      openTaskPrs.push({
        number: pr.number || null,
        title: cleanString(pr.title),
        open_item_count: open,
        total: Number.isFinite(total) ? total : 0,
        report_path: item.path,
      });
    }
  }

  const warningCount = (statusCounts.get('warning') || 0) + unknownCount + parse_errors.length;
  const status = parse_errors.length > 0 ? 'warning' : unknownCount > 0 ? 'warning' : 'pass';

  return {
    schema: COVERAGE_SCHEMA,
    generated_at: now,
    root,
    status,
    records: reports.length,
    parse_error_count: parse_errors.length,
    parse_errors,
    warning_count: warningCount,
    valid_source_context_count: validCount,
    unknown_source_context_count: unknownCount,
    explicit_source_context_count: explicitCount,
    inferred_source_context_count: inferredCount,
    task_list_records: taskListRecords,
    task_items_total: taskItemsTotal,
    task_items_open: taskItemsOpen,
    task_items_completed: taskItemsCompleted,
    status_counts: sortedObject(statusCounts),
    reason_counts: sortedObject(reasonCounts),
    source_type_counts: sortedObject(sourceTypeCounts),
    open_task_prs: openTaskPrs,
    unknown_source_prs: unknownSourcePrs,
  };
}

function renderMarkdown(report) {
  const lines = [
    '## PR Source Context Coverage',
    '',
    `- Schema: ${report.schema || COVERAGE_SCHEMA}`,
    `- Status: ${report.status || 'unknown'}`,
    `- Records: ${report.records || 0}`,
    `- Valid source contexts: ${report.valid_source_context_count || 0}`,
    `- Unknown source contexts: ${report.unknown_source_context_count || 0}`,
    `- Explicit/inferred: ${report.explicit_source_context_count || 0}/${report.inferred_source_context_count || 0}`,
    `- Task-list records: ${report.task_list_records || 0}`,
    `- Task items open/completed/total: ${report.task_items_open || 0}/${report.task_items_completed || 0}/${report.task_items_total || 0}`,
    `- Parse errors: ${report.parse_error_count || 0}`,
  ];

  if (report.open_task_prs?.length) {
    lines.push('', '| PR | Open | Total | Title |', '|----|------|-------|-------|');
    for (const pr of report.open_task_prs) {
      lines.push(`| #${pr.number || 'unknown'} | ${pr.open_item_count || 0} | ${pr.total || 0} | ${cleanString(pr.title).replace(/\|/g, '\\|')} |`);
    }
  }

  if (report.unknown_source_prs?.length) {
    lines.push('', '### Unknown Source Contexts');
    for (const pr of report.unknown_source_prs) {
      lines.push(`- #${pr.number || 'unknown'} ${cleanString(pr.title) || '(untitled)'}`);
    }
  }

  return `${lines.join('\n')}\n`;
}

function writeCoverageReport(report, options = {}) {
  if (options.outputJson) {
    ensureParentDirectory(options.outputJson);
    fs.writeFileSync(options.outputJson, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  }
  if (options.outputMd) {
    ensureParentDirectory(options.outputMd);
    fs.writeFileSync(options.outputMd, renderMarkdown(report), 'utf8');
  }
}

function shouldFail(report, env = process.env) {
  const mode = cleanString(env.PR_SOURCE_CONTEXT_COVERAGE_MODE || 'warning-only').toLowerCase();
  const hardBlockApproved = cleanString(env.PR_SOURCE_CONTEXT_HARD_BLOCK_APPROVED || 'false').toLowerCase() === 'true';
  return report.status !== 'pass' && mode === 'hard-block' && hardBlockApproved;
}

function parseArgs(argv = process.argv.slice(2)) {
  const args = {
    root: process.env.PR_SOURCE_CONTEXT_COVERAGE_DIR || 'artifacts',
    outputJson: process.env.PR_SOURCE_CONTEXT_COVERAGE_JSON || 'pr-source-context-coverage.json',
    outputMd: process.env.PR_SOURCE_CONTEXT_COVERAGE_MD || 'pr-source-context-coverage.md',
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === '--root') {
      args.root = next || '';
      index += 1;
    } else if (arg === '--output-json') {
      args.outputJson = next || '';
      index += 1;
    } else if (arg === '--output-md') {
      args.outputMd = next || '';
      index += 1;
    }
  }
  return args;
}

function main() {
  const args = parseArgs();
  const report = buildCoverageReport(args);
  writeCoverageReport(report, args);
  process.stdout.write(renderMarkdown(report));
  return shouldFail(report) ? 1 : 0;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  COVERAGE_SCHEMA,
  SOURCE_CONTEXT_SCHEMA,
  buildCoverageReport,
  parseArgs,
  renderMarkdown,
  shouldFail,
  writeCoverageReport,
};
