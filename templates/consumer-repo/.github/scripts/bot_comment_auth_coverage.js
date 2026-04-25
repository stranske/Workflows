const fs = require('fs');
const path = require('path');

const COVERAGE_SCHEMA = 'workflows-bot-comment-auth-coverage-summary/v1';
const AUTH_SCHEMA = 'workflows-bot-comment-auth-coverage/v1';
const DEFAULT_MODE = 'warning-only';
const HARD_BLOCK_MODE = 'hard-block';
const AUTH_ARTIFACT_FAMILIES = new Set([
  'bot-comment-auth-coverage-wrapper',
  'bot-comment-auth-coverage-reusable',
]);

const COMPONENT_POLICIES = {
  'agents-bot-comment-handler-wrapper': {
    expected_mode: 'client-id',
    allowed_modes: ['client-id'],
    missing_record_severity: 'no-data',
  },
  'reusable-bot-comment-handler': {
    expected_mode: '',
    allowed_modes: ['client-id', 'none'],
    missing_record_severity: 'no-data',
  },
};

function cleanString(value) {
  if (value === null || value === undefined) return '';
  return String(value).trim();
}

function normalizeBoolean(value) {
  if (typeof value === 'boolean') return value;
  const text = cleanString(value).toLowerCase();
  return ['1', 'true', 'yes', 'y', 'approved', 'approve', 'on'].includes(text);
}

function normalizeRecordBoolean(value) {
  if (typeof value === 'boolean') return value;
  const text = cleanString(value).toLowerCase();
  if (['1', 'true', 'yes', 'y', 'on'].includes(text)) return true;
  if (['0', 'false', 'no', 'n', 'off', ''].includes(text)) return false;
  return Boolean(value);
}

function normalizeMode(value) {
  const text = cleanString(value).toLowerCase();
  if (['hard-block', 'hard_block', 'hard', 'block', 'blocking', 'enforce'].includes(text)) {
    return HARD_BLOCK_MODE;
  }
  return DEFAULT_MODE;
}

function normalizePolicy(options = {}) {
  const requestedMode = normalizeMode(
    options.mode ??
      options.enforcement_mode ??
      options.enforcementMode ??
      process.env.BOT_COMMENT_AUTH_COVERAGE_MODE
  );
  const hardBlockApproved = normalizeBoolean(
    options.hard_block_approved ??
      options.hardBlockApproved ??
      process.env.BOT_COMMENT_AUTH_HARD_BLOCK_APPROVED
  );
  const policyBlockers = [];
  let effectiveMode = requestedMode;

  if (requestedMode === HARD_BLOCK_MODE && !hardBlockApproved) {
    effectiveMode = DEFAULT_MODE;
    policyBlockers.push('hard-block-approval-required');
  }

  return {
    schema: 'workflows-bot-comment-auth-coverage-policy/v1',
    requested_mode: requestedMode,
    effective_mode: effectiveMode,
    default_mode: DEFAULT_MODE,
    hard_block_approved: hardBlockApproved,
    policy_blockers: policyBlockers,
  };
}

function normalizeAuthMode(value) {
  const text = cleanString(value).toLowerCase();
  return ['client-id', 'legacy-app-id', 'none'].includes(text) ? text : 'unknown';
}

function normalizeRecord(raw = {}, sourcePath = '') {
  return {
    schema: cleanString(raw.schema),
    component: cleanString(raw.component),
    repository: cleanString(raw.repository),
    workflow: cleanString(raw.workflow),
    run_id: cleanString(raw.run_id ?? raw.runId),
    run_attempt: cleanString(raw.run_attempt ?? raw.runAttempt),
    event_name: cleanString(raw.event_name ?? raw.eventName),
    auth_mode: normalizeAuthMode(raw.auth_mode ?? raw.authMode),
    client_id_configured: normalizeRecordBoolean(raw.client_id_configured ?? raw.clientIdConfigured),
    legacy_app_id_configured: normalizeRecordBoolean(
      raw.legacy_app_id_configured ?? raw.legacyAppIdConfigured
    ),
    private_key_configured: normalizeRecordBoolean(raw.private_key_configured ?? raw.privateKeyConfigured),
    fallback_warning_active: normalizeRecordBoolean(
      raw.fallback_warning_active ?? raw.fallbackWarningActive
    ),
    source_path: sourcePath,
  };
}

function isAuthCoverageRecord(record) {
  return Boolean(record && typeof record === 'object' && record.schema === AUTH_SCHEMA);
}

function parseAllowedModes(value, fallback) {
  const configured = cleanString(value)
    .split(',')
    .map((item) => normalizeAuthMode(item))
    .filter((item) => item !== 'unknown');
  return configured.length > 0 ? [...new Set(configured)] : fallback;
}

function parseExpectedMode(value, fallback) {
  const raw = cleanString(value);
  const normalized = normalizeAuthMode(raw);
  if (!raw) {
    return { expected_mode: fallback, invalid_expected_mode: '' };
  }
  if (normalized === 'unknown') {
    return { expected_mode: fallback, invalid_expected_mode: raw };
  }
  return { expected_mode: normalized, invalid_expected_mode: '' };
}

function parseCsvList(value) {
  if (Array.isArray(value)) {
    return value.map(cleanString).filter(Boolean);
  }
  return cleanString(value)
    .split(',')
    .map(cleanString)
    .filter(Boolean);
}

function summarizeOrganicEvidence(records = [], options = {}) {
  const requiredEvents = parseCsvList(
    options.required_organic_events ??
      options.requiredOrganicEvents ??
      process.env.BOT_COMMENT_AUTH_REQUIRED_ORGANIC_EVENTS
  );
  const requiredComponents = parseCsvList(
    options.organic_components ??
      options.organicComponents ??
      process.env.BOT_COMMENT_AUTH_ORGANIC_COMPONENTS
  );
  const expectedMode = normalizeAuthMode(
    options.organic_expected_mode ??
      options.organicExpectedMode ??
      process.env.BOT_COMMENT_AUTH_ORGANIC_EXPECTED_MODE
  );
  const components = requiredComponents.length > 0
    ? requiredComponents
    : Object.keys(COMPONENT_POLICIES);
  const eventCounts = Object.create(null);
  const latestByComponentEvent = Object.create(null);

  for (const record of records) {
    if (!record.component || !record.event_name) continue;
    eventCounts[record.component] ||= {};
    eventCounts[record.component][record.event_name] =
      (eventCounts[record.component][record.event_name] || 0) + 1;
    const key = `${record.component}:${record.event_name}`;
    const existing = latestByComponentEvent[key];
    if (!existing || compareRecords(record, existing) < 0) {
      latestByComponentEvent[key] = record;
    }
  }

  const blockers = [];
  for (const component of components) {
    for (const eventName of requiredEvents) {
      const latest = latestByComponentEvent[`${component}:${eventName}`];
      if (!latest) {
        blockers.push(`missing-organic-${component}-${eventName}`);
        continue;
      }
      if (latest.fallback_warning_active || latest.auth_mode === 'legacy-app-id') {
        blockers.push(`legacy-organic-${component}-${eventName}`);
      }
      if (expectedMode !== 'unknown' && latest.auth_mode !== expectedMode) {
        blockers.push(`expected-${expectedMode}-organic-${component}-${eventName}`);
      }
    }
  }

  return {
    schema: 'workflows-bot-comment-auth-organic-evidence/v1',
    required_events: requiredEvents,
    required_components: components,
    expected_mode: expectedMode === 'unknown' ? '' : expectedMode,
    event_counts: eventCounts,
    blockers,
    status: blockers.length > 0 ? 'warning' : 'pass',
  };
}

function componentPolicy(component, options = {}) {
  const base = COMPONENT_POLICIES[component] || {
    expected_mode: '',
    allowed_modes: ['client-id', 'none'],
    missing_record_severity: 'no-data',
  };
  if (component === 'agents-bot-comment-handler-wrapper') {
    const expectedMode = parseExpectedMode(
      options.wrapper_expected_mode ?? process.env.BOT_COMMENT_WRAPPER_EXPECTED_AUTH_MODE,
      base.expected_mode
    );
    return {
      ...base,
      ...expectedMode,
      allowed_modes: parseAllowedModes(
        options.wrapper_allowed_modes ?? process.env.BOT_COMMENT_WRAPPER_ALLOWED_AUTH_MODES,
        base.allowed_modes
      ),
    };
  }
  if (component === 'reusable-bot-comment-handler') {
    const expectedMode = parseExpectedMode(
      options.reusable_expected_mode ?? process.env.BOT_COMMENT_REUSABLE_EXPECTED_AUTH_MODE,
      base.expected_mode
    );
    return {
      ...base,
      ...expectedMode,
      allowed_modes: parseAllowedModes(
        options.reusable_allowed_modes ?? process.env.BOT_COMMENT_REUSABLE_ALLOWED_AUTH_MODES,
        base.allowed_modes
      ),
    };
  }
  return base;
}

function runSortKey(record) {
  const runId = Number.parseInt(record.run_id, 10);
  const runAttempt = Number.parseInt(record.run_attempt, 10);
  return [
    Number.isFinite(runId) ? runId : 0,
    Number.isFinite(runAttempt) ? runAttempt : 0,
    record.source_path,
  ];
}

function compareRecords(a, b) {
  const left = runSortKey(a);
  const right = runSortKey(b);
  if (left[0] !== right[0]) return right[0] - left[0];
  if (left[1] !== right[1]) return right[1] - left[1];
  return String(left[2]).localeCompare(String(right[2]));
}

function normalizeArtifactSelectionSummary(report) {
  if (!report) return null;
  if (report.status === 'missing' || report.status === 'parse-error') {
    return {
      schema: cleanString(report.schema) || 'workflows-weekly-metrics-artifact-selection/v1',
      status: report.status,
      error_message: cleanString(report.error_message),
      selected_auth_artifact_count: 0,
      selected_auth_artifacts: [],
    };
  }
  if (typeof report !== 'object' || Array.isArray(report)) {
    return {
      schema: 'workflows-weekly-metrics-artifact-selection/v1',
      status: 'parse-error',
      error_message: 'artifact selection report is not a JSON object',
      selected_auth_artifact_count: 0,
      selected_auth_artifacts: [],
    };
  }
  const selected = Array.isArray(report.selected_artifacts) ? report.selected_artifacts : [];
  const selectedAuthArtifacts = selected
    .map((artifact) => ({
      id: artifact.id ?? artifact.artifact_id ?? artifact.artifactId ?? null,
      name: cleanString(artifact.name),
      family: artifactFamilyFromSelection(artifact),
      created_at: cleanString(artifact.created_at ?? artifact.createdAt),
      updated_at: cleanString(artifact.updated_at ?? artifact.updatedAt),
    }))
    .filter((artifact) => AUTH_ARTIFACT_FAMILIES.has(artifact.family));
  return {
    schema: cleanString(report.schema) || 'workflows-weekly-metrics-artifact-selection/v1',
    status: cleanString(report.status) || 'pass',
    error_message: cleanString(report.error_message),
    selected_auth_artifact_count: selectedAuthArtifacts.length,
    selected_auth_artifacts: selectedAuthArtifacts,
  };
}

function artifactFamilyFromSelection(artifact = {}) {
  const family = cleanString(artifact.family);
  if (AUTH_ARTIFACT_FAMILIES.has(family)) return family;
  const name = cleanString(artifact.name);
  if (name.startsWith('bot-comment-auth-coverage-wrapper-')) {
    return 'bot-comment-auth-coverage-wrapper';
  }
  if (name.startsWith('bot-comment-auth-coverage-reusable-')) {
    return 'bot-comment-auth-coverage-reusable';
  }
  return '';
}

function componentCoverageStatus(blockers, policy, latest) {
  if (blockers.length === 0) return 'pass';
  if (!latest && policy.missing_record_severity === 'no-data') return 'no-data';
  return 'warning';
}

function isComponentMissingBlocker(blocker) {
  return Object.keys(COMPONENT_POLICIES).some((component) => blocker === `missing-${component}`);
}

function summarizeBotCommentAuthCoverage(records = [], options = {}) {
  const policy = normalizePolicy(options);
  const parseErrors = Number(options.parse_errors ?? options.parseErrors ?? 0);
  const artifactSelection = normalizeArtifactSelectionSummary(
    options.artifact_selection_report ?? options.artifactSelectionReport
  );
  const inputFiles = Array.isArray(options.input_files) ? options.input_files.map(cleanString).filter(Boolean) : [];
  const inputFileCount = Number.isFinite(options.input_file_count)
    ? options.input_file_count
    : inputFiles.length;
  const authRecords = records
    .filter(isAuthCoverageRecord)
    .map((record) => normalizeRecord(record, record.source_path || ''))
    .sort(compareRecords);
  const organicEvidence = summarizeOrganicEvidence(authRecords, options);
  const byComponent = new Map();

  for (const record of authRecords) {
    if (!record.component) continue;
    if (!byComponent.has(record.component)) byComponent.set(record.component, []);
    byComponent.get(record.component).push(record);
  }

  const componentSummaries = Object.keys(COMPONENT_POLICIES).map((component) => {
    const componentRecords = (byComponent.get(component) || []).sort(compareRecords);
    const latest = componentRecords[0] || null;
    const componentPolicyConfig = componentPolicy(component, options);
    const blockers = [];
    if (componentPolicyConfig.invalid_expected_mode) {
      blockers.push(`invalid-${component}-expected-auth-mode`);
    }
    if (!latest) {
      blockers.push(`missing-${component}`);
    } else {
      if (!componentPolicyConfig.allowed_modes.includes(latest.auth_mode)) {
        blockers.push(`disallowed-${component}-auth-mode`);
      }
      if (latest.fallback_warning_active || latest.auth_mode === 'legacy-app-id') {
        blockers.push(`legacy-${component}-fallback-active`);
      }
      if (
        componentPolicyConfig.expected_mode &&
        latest.auth_mode !== componentPolicyConfig.expected_mode
      ) {
        blockers.push(`expected-${componentPolicyConfig.expected_mode}-${component}`);
      }
    }
    return {
      component,
      record_count: componentRecords.length,
      latest,
      expected_mode: componentPolicyConfig.expected_mode,
      invalid_expected_mode: componentPolicyConfig.invalid_expected_mode,
      allowed_modes: componentPolicyConfig.allowed_modes,
      status: componentCoverageStatus(blockers, componentPolicyConfig, latest),
      blockers,
    };
  });

  const artifactSelectionWarning = artifactSelection &&
    artifactSelection.status !== 'pass' &&
    artifactSelection.status !== 'not-configured';
  const selectedAuthArtifactCount = artifactSelection?.selected_auth_artifact_count || 0;
  const authArtifactInputMismatch = selectedAuthArtifactCount > 0 && inputFileCount === 0;
  const blockers = componentSummaries.flatMap((summary) => summary.blockers);
  if (parseErrors > 0) blockers.push('parse-errors');
  if (artifactSelectionWarning) blockers.push('artifact-selection-warning');
  if (authArtifactInputMismatch) blockers.push('selected-auth-artifacts-without-input-files');
  blockers.push(...organicEvidence.blockers);

  let coverageStatus = 'pass';
  if (authRecords.length === 0) {
    const nonMissingBlockers = blockers.filter((blocker) => !isComponentMissingBlocker(blocker));
    coverageStatus = nonMissingBlockers.length > 0 ? 'warning' : 'no-data';
  } else if (blockers.length > 0) {
    coverageStatus = 'warning';
  }

  const hardBlockActive = policy.effective_mode === HARD_BLOCK_MODE;
  const shouldFail = hardBlockActive && coverageStatus !== 'pass';
  return {
    schema: COVERAGE_SCHEMA,
    status: shouldFail ? 'fail' : coverageStatus,
    coverage_status: coverageStatus,
    mode: policy.effective_mode,
    requested_mode: policy.requested_mode,
    policy,
    enforcement: {
      mode: policy.effective_mode,
      requested_mode: policy.requested_mode,
      hard_block_approved: policy.hard_block_approved,
      hard_block_active: hardBlockActive,
      should_fail: shouldFail,
      blockers,
      policy_blockers: policy.policy_blockers,
    },
    input_file_count: inputFileCount,
    input_files: inputFiles,
    scanned_record_count: records.length,
    auth_record_count: authRecords.length,
    parse_errors: parseErrors,
    auth_artifact_input_mismatch: authArtifactInputMismatch,
    artifact_selection: artifactSelection,
    organic_evidence: organicEvidence,
    components: componentSummaries,
  };
}

function formatBotCommentAuthCoverageMarkdown(report) {
  const lines = [
    '## Bot Comment App Auth Coverage',
    '',
    `- Schema: ${report.schema}`,
    `- Status: ${report.status}`,
    `- Coverage status: ${report.coverage_status}`,
    `- Mode: ${report.mode}`,
    `- Hard block active: ${report.enforcement.hard_block_active}`,
    `- Input files: ${report.input_file_count}`,
    `- Auth records: ${report.auth_record_count}`,
    `- Parse errors: ${report.parse_errors}`,
  ];

  if (report.artifact_selection) {
    lines.push(`- Selected auth artifacts: ${report.artifact_selection.selected_auth_artifact_count}`);
    if (report.artifact_selection.error_message) {
      lines.push(`- Artifact selector error: ${report.artifact_selection.error_message}`);
    }
  }
  if (report.organic_evidence?.required_events?.length > 0) {
    lines.push(`- Required organic events: ${report.organic_evidence.required_events.join(', ')}`);
    lines.push(`- Organic evidence status: ${report.organic_evidence.status}`);
  }
  if (report.enforcement.blockers.length > 0) {
    lines.push(`- Blockers: ${report.enforcement.blockers.join(', ')}`);
  }
  if (report.enforcement.policy_blockers.length > 0) {
    lines.push(`- Policy blockers: ${report.enforcement.policy_blockers.join(', ')}`);
  }

  lines.push('', '| Component | Latest mode | Records | Expected | Allowed | Blockers |');
  lines.push('|-----------|-------------|---------|----------|---------|----------|');
  for (const component of report.components) {
    lines.push([
      component.component,
      component.latest?.auth_mode || 'missing',
      component.record_count,
      component.expected_mode || 'any',
      component.allowed_modes.join(', '),
      component.blockers.join(', ') || 'none',
    ].join(' | ').replace(/^/, '| ').replace(/$/, ' |'));
  }

  return `${lines.join('\n')}\n`;
}

function collectJsonFiles(rootDir) {
  const files = [];
  if (!rootDir || !fs.existsSync(rootDir)) return files;
  const stack = [rootDir];
  while (stack.length > 0) {
    const current = stack.pop();
    const stat = fs.statSync(current);
    if (stat.isDirectory()) {
      for (const entry of fs.readdirSync(current)) {
        stack.push(path.join(current, entry));
      }
    } else if (stat.isFile() && isPotentialAuthCoverageFile(current)) {
      files.push(current);
    }
  }
  return files.sort((a, b) => a.localeCompare(b));
}

function isPotentialAuthCoverageFile(file) {
  const normalized = cleanString(file).split(path.sep).join('/');
  const basename = path.basename(normalized);
  if (!normalized.endsWith('.json')) return false;
  const segments = normalized.split('/');
  const hasWrapperArtifactDir = segments.some((segment) =>
    segment.startsWith('bot-comment-auth-coverage-wrapper-')
  );
  const hasReusableArtifactDir = segments.some((segment) =>
    segment.startsWith('bot-comment-auth-coverage-reusable-')
  );
  return (basename === 'wrapper.json' && hasWrapperArtifactDir) ||
    (basename === 'reusable.json' && hasReusableArtifactDir);
}

function readJsonRecords(files = []) {
  const records = [];
  let parseErrors = 0;
  for (const file of files) {
    try {
      const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (isAuthCoverageRecord(parsed)) {
        records.push({ ...parsed, source_path: file });
      }
    } catch (_error) {
      parseErrors += 1;
    }
  }
  return { records, parse_errors: parseErrors, file_count: files.length };
}

function readArtifactSelectionReport(file) {
  const selectionPath = cleanString(file);
  if (!selectionPath) return null;
  if (!fs.existsSync(selectionPath)) {
    return {
      schema: 'workflows-weekly-metrics-artifact-selection/v1',
      status: 'missing',
      error_message: `artifact selection report not found: ${selectionPath}`,
      selected_artifacts: [],
    };
  }
  try {
    return JSON.parse(fs.readFileSync(selectionPath, 'utf8'));
  } catch (error) {
    return {
      schema: 'workflows-weekly-metrics-artifact-selection/v1',
      status: 'parse-error',
      error_message: error?.message || 'failed to parse artifact selection report',
      selected_artifacts: [],
    };
  }
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    dir: process.env.BOT_COMMENT_AUTH_COVERAGE_DIR || 'artifacts',
    output: process.env.BOT_COMMENT_AUTH_COVERAGE_JSON || 'bot-comment-auth-coverage-summary.json',
    markdown: process.env.BOT_COMMENT_AUTH_COVERAGE_MD || 'bot-comment-auth-coverage-summary.md',
    artifact_selection_report: process.env.BOT_COMMENT_AUTH_ARTIFACT_SELECTION_JSON || '',
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === '--dir') {
      options.dir = next;
      index += 1;
    } else if (arg === '--output') {
      options.output = next;
      index += 1;
    } else if (arg === '--markdown') {
      options.markdown = next;
      index += 1;
    } else if (arg === '--artifact-selection-report') {
      options.artifact_selection_report = next;
      index += 1;
    } else if (arg === '--mode') {
      options.enforcement_mode = next;
      index += 1;
    } else if (arg === '--hard-block-approved') {
      options.hard_block_approved = next;
      index += 1;
    }
  }
  return options;
}

function main() {
  const options = parseArgs();
  const files = collectJsonFiles(options.dir);
  const readResult = readJsonRecords(files);
  const report = summarizeBotCommentAuthCoverage(readResult.records, {
    parse_errors: readResult.parse_errors,
    input_files: files,
    input_file_count: readResult.file_count,
    artifact_selection_report: readArtifactSelectionReport(options.artifact_selection_report),
    enforcement_mode: options.enforcement_mode,
    hard_block_approved: options.hard_block_approved,
  });
  const markdownSummary = formatBotCommentAuthCoverageMarkdown(report);
  fs.writeFileSync(options.output, `${JSON.stringify(report, null, 2)}\n`);
  fs.writeFileSync(options.markdown, markdownSummary);
  process.stdout.write(markdownSummary);
  return report.status === 'fail' ? 1 : 0;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  AUTH_SCHEMA,
  COMPONENT_POLICIES,
  COVERAGE_SCHEMA,
  collectJsonFiles,
  componentPolicy,
  formatBotCommentAuthCoverageMarkdown,
  isPotentialAuthCoverageFile,
  normalizeArtifactSelectionSummary,
  normalizePolicy,
  parseArgs,
  readArtifactSelectionReport,
  readJsonRecords,
  summarizeOrganicEvidence,
  summarizeBotCommentAuthCoverage,
};
