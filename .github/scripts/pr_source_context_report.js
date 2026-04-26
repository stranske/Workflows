'use strict';

const fs = require('node:fs');
const path = require('node:path');

const {
  SOURCE_TYPES,
  formatSourceContextForLog,
  resolvePrSourceContext,
} = require('./source_context.js');

const REPORT_SCHEMA = 'workflows-pr-source-context/v1';

function cleanString(value) {
  return String(value || '').trim();
}

function ensureParentDirectory(filePath) {
  if (!filePath) {
    return;
  }
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function readEventFile(eventPath) {
  if (!eventPath) {
    return {};
  }
  const raw = fs.readFileSync(eventPath, 'utf8');
  return JSON.parse(raw);
}

function labelNames(pull = {}) {
  return Array.isArray(pull.labels)
    ? pull.labels
        .map((label) => cleanString(typeof label === 'string' ? label : label?.name || ''))
        .filter(Boolean)
    : [];
}

function analyzeTaskList(body = '') {
  const sections = new Map();
  let currentSection = 'PR body';
  let total = 0;
  let checked = 0;
  let unchecked = 0;
  let inCodeBlock = false;

  function sectionState(name) {
    const key = cleanString(name) || 'PR body';
    if (!sections.has(key)) {
      sections.set(key, {
        heading: key,
        total: 0,
        checked: 0,
        unchecked: 0,
      });
    }
    return sections.get(key);
  }

  for (const line of String(body || '').split(/\r?\n/)) {
    if (/^\s*```/.test(line)) {
      inCodeBlock = !inCodeBlock;
      continue;
    }
    if (inCodeBlock) {
      continue;
    }

    const heading = line.match(/^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$/);
    if (heading) {
      currentSection = cleanString(heading[1]) || currentSection;
      continue;
    }

    const checkbox = line.match(/^\s*(?:[-*+]|\d+[.)])\s+\[( |x|X)\]\s+(.+?)\s*$/);
    if (!checkbox) {
      continue;
    }

    total += 1;
    const section = sectionState(currentSection);
    section.total += 1;
    if (checkbox[1].toLowerCase() === 'x') {
      checked += 1;
      section.checked += 1;
    } else {
      unchecked += 1;
      section.unchecked += 1;
    }
  }

  return {
    has_task_list: total > 0,
    total,
    checked,
    unchecked,
    open_item_count: unchecked,
    completed_item_count: checked,
    sections: Array.from(sections.values()),
  };
}

function buildPrSourceContextReport(options = {}) {
  const event = options.event && typeof options.event === 'object' ? options.event : {};
  const pull = event.pull_request && typeof event.pull_request === 'object' ? event.pull_request : null;
  const now = options.now || new Date().toISOString();
  const repository =
    cleanString(options.repository) ||
    cleanString(event.repository?.full_name) ||
    cleanString(process.env.GITHUB_REPOSITORY);

  const report = {
    schema: REPORT_SCHEMA,
    generated_at: now,
    repository,
    event_name: cleanString(options.eventName) || cleanString(process.env.GITHUB_EVENT_NAME),
    run_id: cleanString(options.runId) || cleanString(process.env.GITHUB_RUN_ID),
    run_attempt: cleanString(options.runAttempt) || cleanString(process.env.GITHUB_RUN_ATTEMPT),
    status: 'skipped',
    reason: 'not-pull-request',
    pull_request: null,
    source_context: {
      sourceType: SOURCE_TYPES.UNKNOWN,
      issueNumber: null,
      sourceRef: '',
      lifecycle: '',
      automation: '',
      isKnown: false,
      isValid: false,
      isExplicit: false,
      requiresIssue: false,
    },
    task_list: {
      has_task_list: false,
      total: 0,
      checked: 0,
      unchecked: 0,
      open_item_count: 0,
      completed_item_count: 0,
      sections: [],
    },
    warnings: [],
  };

  if (!pull) {
    return report;
  }

  const context = resolvePrSourceContext(pull);
  const valid = Boolean(context.isValid);
  const explicit = Boolean(context.isExplicit);

  report.status = valid ? 'pass' : 'warning';
  report.reason = valid ? 'source-context-detected' : 'source-context-unknown';
  report.pull_request = {
    number: pull.number || event.number || null,
    title: cleanString(pull.title),
    author: cleanString(pull.user?.login),
    head_ref: cleanString(pull.head?.ref),
    base_ref: cleanString(pull.base?.ref),
    labels: labelNames(pull),
  };
  report.source_context = context;
  report.task_list = analyzeTaskList(pull.body || '');

  if (!valid) {
    report.warnings.push(
      'No source issue, workflow-source marker, workflow source label, or recognized maintenance origin was found.',
    );
  } else if (!explicit) {
    report.warnings.push(
      `Source context was inferred from PR metadata (${formatSourceContextForLog(context)}).`,
    );
  }

  return report;
}

function renderMarkdown(report) {
  const lines = [
    '# PR Source Context',
    '',
    `- Schema: \`${report.schema || REPORT_SCHEMA}\``,
    `- Status: \`${report.status || 'unknown'}\``,
    `- Reason: \`${report.reason || 'unknown'}\``,
  ];

  if (report.pull_request) {
    lines.push(
      `- PR: #${report.pull_request.number || 'unknown'}`,
      `- Source: \`${formatSourceContextForLog(report.source_context)}\``,
      `- Explicit source marker: \`${report.source_context?.isExplicit ? 'true' : 'false'}\``,
      `- Task list: \`${report.task_list?.total || 0}\` items, \`${report.task_list?.unchecked || 0}\` open`,
    );
  }

  if (Array.isArray(report.warnings) && report.warnings.length > 0) {
    lines.push('', '## Warnings');
    for (const warning of report.warnings) {
      lines.push(`- ${warning}`);
    }
  }

  return `${lines.join('\n')}\n`;
}

function writeReport(report, options = {}) {
  if (options.outputJson) {
    ensureParentDirectory(options.outputJson);
    fs.writeFileSync(options.outputJson, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  }
  if (options.outputMd) {
    ensureParentDirectory(options.outputMd);
    fs.writeFileSync(options.outputMd, renderMarkdown(report), 'utf8');
  }
}

function parseArgs(argv = process.argv.slice(2)) {
  const args = {
    eventPath: process.env.GITHUB_EVENT_PATH || '',
    eventName: process.env.GITHUB_EVENT_NAME || '',
    outputJson: 'pr-source-context.json',
    outputMd: 'pr-source-context.md',
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--event-path') {
      args.eventPath = argv[++index] || '';
    } else if (arg === '--event-name') {
      args.eventName = argv[++index] || '';
    } else if (arg === '--output-json') {
      args.outputJson = argv[++index] || '';
    } else if (arg === '--output-md') {
      args.outputMd = argv[++index] || '';
    }
  }

  return args;
}

function main() {
  const args = parseArgs();
  let event = {};
  let readError = '';
  try {
    event = readEventFile(args.eventPath);
  } catch (error) {
    readError = error instanceof Error ? error.message : String(error);
  }

  const report = buildPrSourceContextReport({
    event,
    eventName: args.eventName,
  });

  if (readError) {
    report.status = 'warning';
    report.reason = 'event-read-error';
    report.warnings.push(`Unable to read GitHub event payload: ${readError}`);
  }

  writeReport(report, {
    outputJson: args.outputJson,
    outputMd: args.outputMd,
  });

  console.log(renderMarkdown(report));
  return 0;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  REPORT_SCHEMA,
  analyzeTaskList,
  buildPrSourceContextReport,
  parseArgs,
  renderMarkdown,
  writeReport,
};
