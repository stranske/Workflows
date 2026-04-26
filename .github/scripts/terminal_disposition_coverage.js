const fs = require('fs');
const path = require('path');

const {
  normalizeTerminalDisposition,
  sourceKey,
} = require('./terminal_disposition.js');

const COVERAGE_SCHEMA = 'workflows-terminal-disposition-coverage/v1';
const TERMINAL_SCHEMA = 'workflows-terminal-disposition/v1';
const TERMINAL_ARTIFACT_FAMILIES = new Set([
  'verifier-terminal-disposition',
  'review-thread-terminal-disposition',
]);
const DEFAULT_UNSUPPORTED_CODEX_MODELS = ['gpt-5.2-codex'];
const DEFAULT_VERIFIER_MODEL_METADATA_REQUIRED_AFTER = '';
const DEFAULT_ENFORCEMENT_MODE = 'warning-only';
const HARD_BLOCK_MODE = 'hard-block';

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

function parseTimestampMs(value) {
  const text = cleanString(value);
  if (!text) return null;
  const parsed = Date.parse(text);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeBoolean(value) {
  const text = cleanString(value).toLowerCase();
  return ['1', 'true', 'yes', 'y', 'approved', 'approve', 'on'].includes(text);
}

function normalizeEnforcementMode(value) {
  const text = cleanString(value).toLowerCase();
  if (['hard-block', 'hard_block', 'hard', 'block', 'blocking', 'enforce'].includes(text)) {
    return HARD_BLOCK_MODE;
  }
  return DEFAULT_ENFORCEMENT_MODE;
}

function normalizeEnforcementPolicy(options = {}) {
  const requestedMode = normalizeEnforcementMode(
    options.mode ??
      options.enforcement_mode ??
      options.enforcementMode ??
      process.env.TERMINAL_DISPOSITION_COVERAGE_MODE
  );
  const hardBlockApproved = normalizeBoolean(
    options.hard_block_approved ??
      options.hardBlockApproved ??
      process.env.TERMINAL_DISPOSITION_HARD_BLOCK_APPROVED
  );
  const policyBlockers = [];
  let effectiveMode = requestedMode;

  if (requestedMode === HARD_BLOCK_MODE && !hardBlockApproved) {
    effectiveMode = DEFAULT_ENFORCEMENT_MODE;
    policyBlockers.push('hard-block-approval-required');
  }

  return {
    schema: 'workflows-terminal-disposition-enforcement-policy/v1',
    requested_mode: requestedMode,
    effective_mode: effectiveMode,
    default_mode: DEFAULT_ENFORCEMENT_MODE,
    hard_block_approved: hardBlockApproved,
    policy_blockers: policyBlockers,
  };
}

function normalizeUnsupportedCodexModels(value) {
  const raw = value ??
    process.env.TERMINAL_DISPOSITION_UNSUPPORTED_CODEX_MODELS ??
    DEFAULT_UNSUPPORTED_CODEX_MODELS.join(',');
  const items = Array.isArray(raw) ? raw : String(raw).split(',');
  return [...new Set(items.map((item) => cleanString(item).toLowerCase()).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));
}

function normalizeVerifierModelMetadataContract(value) {
  const raw = value ??
    process.env.TERMINAL_DISPOSITION_VERIFIER_MODEL_METADATA_REQUIRED_AFTER ??
    DEFAULT_VERIFIER_MODEL_METADATA_REQUIRED_AFTER;
  const text = cleanString(raw);
  if (['', '0', 'false', 'none', 'off', 'disabled'].includes(text.toLowerCase())) {
    return {
      required_after: '',
      required_after_epoch_ms: null,
      model_metadata_required: false,
      suppress_pre_contract_missing_metadata: false,
    };
  }
  const epochMs = parseTimestampMs(text);
  return {
    required_after: text,
    required_after_epoch_ms: epochMs,
    model_metadata_required: true,
    suppress_pre_contract_missing_metadata: epochMs !== null,
  };
}

function runIdFromArtifactName(name) {
  const match = cleanString(name).match(/-(\d+)$/);
  return match ? match[1] : '';
}

function artifactMetadataByRunId(artifactSelection) {
  const byRunId = new Map();
  const artifacts = artifactSelection?.selected_terminal_artifacts || [];
  for (const artifact of artifacts) {
    if (artifact?.family !== 'verifier-terminal-disposition') continue;
    const runId = runIdFromArtifactName(artifact.name);
    if (!runId) continue;
    byRunId.set(runId, {
      artifact_name: cleanString(artifact.name),
      created_at: cleanString(artifact.created_at),
      updated_at: cleanString(artifact.updated_at),
    });
  }
  return byRunId;
}

function isPreContractVerifierModelRecord(record, artifactMetadata, contract) {
  if (!contract.suppress_pre_contract_missing_metadata) return false;
  const requiredAfter = contract.required_after_epoch_ms;
  const candidates = [
    record.created_at,
    record.timestamp,
    artifactMetadata?.created_at,
    artifactMetadata?.updated_at,
  ];
  return candidates.some((value) => {
    const epochMs = parseTimestampMs(value);
    return epochMs !== null && epochMs < requiredAfter;
  });
}

function summarizeVerifierModelCompatibility(records = [], options = {}) {
  const unsupportedModels = normalizeUnsupportedCodexModels(
    options.unsupported_codex_models ?? options.unsupportedCodexModels
  );
  const modelMetadataContract = normalizeVerifierModelMetadataContract(
    options.model_metadata_required_after ?? options.modelMetadataRequiredAfter
  );
  const artifactMetadata = artifactMetadataByRunId(options.artifact_selection);
  const unsupportedSet = new Set(unsupportedModels);
  const selectedModels = {};
  const modelSelectionReasons = {};
  const unsupportedRecords = [];
  const missingModelRecords = [];
  const legacyMissingModelRecords = [];
  let verifierRecordCount = 0;

  for (const raw of records) {
    if (!isTerminalDispositionRecord(raw)) continue;
    const record = normalizeTerminalDisposition(raw);
    const isVerifierRecord = record.artifact_family === 'verifier-terminal-disposition' ||
      Boolean(record.verifier_mode) ||
      cleanString(record.workflow).toLowerCase().includes('verifier');
    if (!isVerifierRecord) continue;
    verifierRecordCount += 1;

    const model = cleanString(record.llm_model ?? record.model).toLowerCase();
    const reason = cleanString(record.model_selection_reason);
    const verifierMode = cleanString(record.verifier_mode).toLowerCase();
    const requiresCodexModel = verifierMode !== 'evaluate';
    if (model) selectedModels[model] = (selectedModels[model] || 0) + 1;
    if (reason) modelSelectionReasons[reason] = (modelSelectionReasons[reason] || 0) + 1;
    if (!model && requiresCodexModel && modelMetadataContract.model_metadata_required) {
      const runId = cleanString(record.run_id);
      const metadata = artifactMetadata.get(runId);
      const missingRecord = {
        source_key: record.source_key,
        pr_number: record.pr_number || null,
        run_id: runId,
        disposition: record.disposition,
        verifier_mode: verifierMode || 'unknown',
      };
      if (metadata?.created_at) missingRecord.artifact_created_at = metadata.created_at;
      if (isPreContractVerifierModelRecord(record, metadata, modelMetadataContract)) {
        legacyMissingModelRecords.push(missingRecord);
      } else {
        missingModelRecords.push(missingRecord);
      }
    }
    if (model && unsupportedSet.has(model)) {
      unsupportedRecords.push({
        source_key: record.source_key,
        pr_number: record.pr_number || null,
        run_id: cleanString(record.run_id),
        model,
        disposition: record.disposition,
        model_selection_reason: reason,
      });
    }
  }

  return {
    schema: 'workflows-verifier-model-compatibility/v1',
    status: unsupportedRecords.length > 0 || missingModelRecords.length > 0 ? 'warning' : 'pass',
    model_metadata_contract: modelMetadataContract,
    verifier_record_count: verifierRecordCount,
    unsupported_models: unsupportedModels,
    unsupported_record_count: unsupportedRecords.length,
    missing_model_record_count: missingModelRecords.length,
    legacy_missing_model_record_count: legacyMissingModelRecords.length,
    selected_models: Object.fromEntries(
      Object.entries(selectedModels).sort((a, b) => a[0].localeCompare(b[0]))
    ),
    model_selection_reasons: Object.fromEntries(
      Object.entries(modelSelectionReasons).sort((a, b) => a[0].localeCompare(b[0]))
    ),
    unsupported_records: unsupportedRecords.sort((a, b) =>
      `${a.source_key}:${a.run_id}`.localeCompare(`${b.source_key}:${b.run_id}`)
    ),
    missing_model_records: missingModelRecords.sort((a, b) =>
      `${a.source_key}:${a.run_id}`.localeCompare(`${b.source_key}:${b.run_id}`)
    ),
    legacy_missing_model_records: legacyMissingModelRecords.sort((a, b) =>
      `${a.source_key}:${a.run_id}`.localeCompare(`${b.source_key}:${b.run_id}`)
    ),
  };
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
    if (record.artifact_family === 'verifier-terminal-disposition') continue;
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
  const policy = normalizeEnforcementPolicy(
    options.enforcement_policy ?? options.enforcementPolicy ?? options
  );
  const parseErrors = Number(options.parse_errors || options.parseErrors || 0);
  const artifactSelection = normalizeArtifactSelectionSummary(
    options.artifact_selection_report ?? options.artifactSelectionReport
  );
  const terminalRecords = records
    .filter(isTerminalDispositionRecord)
    .map((record) => normalizeTerminalDisposition(record));
  const verifierModelCompatibility = summarizeVerifierModelCompatibility(terminalRecords, {
    ...options,
    artifact_selection: artifactSelection,
  });
  const scannedRecordCount = records.length;
  const nonTerminalRecordCount = scannedRecordCount - terminalRecords.length;
  const inputFiles = Array.isArray(options.input_files) ? options.input_files.map(cleanString).filter(Boolean) : [];
  const inputFileCount = Number.isFinite(options.input_file_count)
    ? options.input_file_count
    : inputFiles.length;
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

  const artifactSelectionWarning = artifactSelection &&
    artifactSelection.status !== 'pass' &&
    artifactSelection.status !== 'not-configured';
  const selectedTerminalArtifactCount = artifactSelection?.selected_terminal_artifact_count || 0;
  const terminalArtifactInputMismatch = selectedTerminalArtifactCount > 0 && inputFileCount === 0;

  let status = 'pass';
  if (terminalRecords.length === 0) {
    status = parseErrors > 0 ||
      nonTerminalRecordCount > 0 ||
      artifactSelectionWarning ||
      terminalArtifactInputMismatch
      ? 'warning'
      : 'no-data';
  } else if (
    missing.length > 0 ||
    parseErrors > 0 ||
    artifactSelectionWarning ||
    verifierModelCompatibility.status !== 'pass'
  ) {
    status = 'warning';
  }

  const enforcementBlockers = [];
  if (terminalRecords.length === 0) enforcementBlockers.push('no-terminal-disposition-records');
  if (terminalArtifactInputMismatch) {
    enforcementBlockers.push('selected-terminal-artifacts-without-input-files');
  }
  if (missing.length > 0) enforcementBlockers.push('missing-review-thread-sources');
  if (parseErrors > 0) enforcementBlockers.push('parse-errors');
  if (artifactSelectionWarning) enforcementBlockers.push('artifact-selection-warning');
  if (verifierModelCompatibility.unsupported_record_count > 0) {
    enforcementBlockers.push('unsupported-verifier-model');
  }
  if (verifierModelCompatibility.missing_model_record_count > 0) {
    enforcementBlockers.push('missing-verifier-model-metadata');
  }

  const hardBlockEligible = enforcementBlockers.length === 0;
  const hardBlockActive = policy.effective_mode === HARD_BLOCK_MODE;
  const shouldFail = hardBlockActive && status !== 'pass';
  const finalStatus = shouldFail ? 'fail' : status;

  return {
    schema: COVERAGE_SCHEMA,
    status: finalStatus,
    coverage_status: status,
    mode: policy.effective_mode,
    requested_mode: policy.requested_mode,
    policy,
    enforcement: {
      mode: policy.effective_mode,
      requested_mode: policy.requested_mode,
      hard_block_approved: policy.hard_block_approved,
      hard_block_eligible: hardBlockEligible,
      hard_block_active: hardBlockActive,
      should_fail: shouldFail,
      blockers: enforcementBlockers,
      policy_blockers: policy.policy_blockers,
    },
    input_file_count: inputFileCount,
    input_files: inputFiles,
    scanned_record_count: scannedRecordCount,
    terminal_record_count: terminalRecords.length,
    non_terminal_record_count: nonTerminalRecordCount,
    observed_source_count: observedSources.length,
    expected_source_count: expected.length,
    covered_source_count: covered.length,
    missing_source_count: missing.length,
    parse_errors: parseErrors,
    terminal_artifact_input_mismatch: terminalArtifactInputMismatch,
    artifact_selection: artifactSelection,
    verifier_model_compatibility: verifierModelCompatibility,
    observed_sources: observedSources,
    expected_sources: expected,
    missing_sources: missing,
  };
}

function artifactFamilyFromSelection(artifact = {}) {
  const family = cleanString(artifact.family);
  if (family) return family;
  const name = cleanString(artifact.name);
  if (name.startsWith('verifier-terminal-disposition-')) return 'verifier-terminal-disposition';
  if (name.startsWith('review-thread-terminal-disposition-')) {
    return 'review-thread-terminal-disposition';
  }
  return '';
}

function terminalFamilyCount(counts = {}) {
  if (!counts || typeof counts !== 'object' || Array.isArray(counts)) return 0;
  return [...TERMINAL_ARTIFACT_FAMILIES].reduce(
    (total, family) => total + (Number(counts[family]) || 0),
    0
  );
}

function normalizeSelectionArtifact(artifact = {}) {
  if (!artifact || typeof artifact !== 'object' || Array.isArray(artifact)) return null;
  const name = cleanString(artifact.name);
  const normalized = {
    id: artifact.id ?? artifact.artifact_id ?? artifact.artifactId ?? null,
    name,
  };
  const createdAt = cleanString(artifact.created_at ?? artifact.createdAt);
  const updatedAt = cleanString(artifact.updated_at ?? artifact.updatedAt);
  if (createdAt) normalized.created_at = createdAt;
  if (updatedAt) normalized.updated_at = updatedAt;
  return normalized;
}

function latestCandidateFromSelectionReport(report = {}, family = '') {
  const candidateMaps = [
    report.latest_candidate_by_family,
    report.latest_candidates_by_family,
  ];
  for (const candidatesByFamily of candidateMaps) {
    if (!candidatesByFamily || typeof candidatesByFamily !== 'object' || Array.isArray(candidatesByFamily)) {
      continue;
    }
    const candidate = normalizeSelectionArtifact(candidatesByFamily[family]);
    if (candidate) return candidate;
  }
  return null;
}

function normalizeTerminalPriorityFamilyStatuses(report = {}, selectedArtifacts = []) {
  const rawStatuses = Array.isArray(report.priority_family_statuses)
    ? report.priority_family_statuses
    : [];
  const byFamily = new Map();

  for (const status of rawStatuses) {
    if (!status || typeof status !== 'object' || Array.isArray(status)) continue;
    const family = cleanString(status.family);
    if (!TERMINAL_ARTIFACT_FAMILIES.has(family)) continue;
    byFamily.set(family, {
      family,
      status: cleanString(status.status) || 'missing',
      candidate_count: Number(status.candidate_count) || 0,
      selected_count: Number(status.selected_count) || 0,
      latest_candidate: normalizeSelectionArtifact(status.latest_candidate),
      selected_artifact: normalizeSelectionArtifact(status.selected_artifact),
    });
  }

  for (const family of TERMINAL_ARTIFACT_FAMILIES) {
    if (byFamily.has(family)) continue;
    const candidateCount = Number(report.candidate_family_counts?.[family]) || 0;
    const selectedCount = Number(report.selected_family_counts?.[family]) ||
      selectedArtifacts.filter((artifact) => artifact.family === family).length;
    const selectedArtifact = selectedArtifacts.find((artifact) => artifact.family === family) || null;
    const latestCandidate = latestCandidateFromSelectionReport(report, family) ||
      (selectedArtifact ? normalizeSelectionArtifact(selectedArtifact) : null);
    byFamily.set(family, {
      family,
      status: selectedCount > 0 ? 'selected' : (candidateCount > 0 ? 'available' : 'missing'),
      candidate_count: candidateCount,
      selected_count: selectedCount,
      latest_candidate: latestCandidate,
      selected_artifact: selectedArtifact ? normalizeSelectionArtifact(selectedArtifact) : null,
    });
  }

  return [...byFamily.values()].sort((a, b) => a.family.localeCompare(b.family));
}

function normalizeArtifactSelectionSummary(report) {
  if (!report) return null;
  if (report.status === 'missing' || report.status === 'parse-error') {
    return {
      schema: cleanString(report.schema) || 'workflows-weekly-metrics-artifact-selection/v1',
      status: report.status,
      error_message: cleanString(report.error_message),
      candidate_terminal_artifact_count: 0,
      selected_terminal_artifact_count: 0,
      selected_terminal_artifacts: [],
      terminal_priority_family_statuses: [],
      missing_terminal_priority_families: [],
    };
  }
  if (typeof report !== 'object' || Array.isArray(report)) {
    return {
      schema: 'workflows-weekly-metrics-artifact-selection/v1',
      status: 'parse-error',
      error_message: 'artifact selection report is not a JSON object',
      candidate_terminal_artifact_count: 0,
      selected_terminal_artifact_count: 0,
      selected_terminal_artifacts: [],
      terminal_priority_family_statuses: [],
      missing_terminal_priority_families: [],
    };
  }

  const selectedArtifacts = Array.isArray(report.selected_artifacts)
    ? report.selected_artifacts
      .map((artifact) => {
        const normalized = {
          id: artifact.id ?? artifact.artifact_id ?? artifact.artifactId ?? null,
          name: cleanString(artifact.name),
          family: artifactFamilyFromSelection(artifact),
        };
        const createdAt = cleanString(artifact.created_at ?? artifact.createdAt);
        const updatedAt = cleanString(artifact.updated_at ?? artifact.updatedAt);
        if (createdAt) normalized.created_at = createdAt;
        if (updatedAt) normalized.updated_at = updatedAt;
        return normalized;
      })
      .filter((artifact) => TERMINAL_ARTIFACT_FAMILIES.has(artifact.family))
    : [];
  const terminalFamilyStatuses = normalizeTerminalPriorityFamilyStatuses(report, selectedArtifacts);

  return {
    schema: cleanString(report.schema) || 'workflows-weekly-metrics-artifact-selection/v1',
    status: cleanString(report.status) || 'pass',
    error_message: cleanString(report.error_message),
    candidate_terminal_artifact_count: terminalFamilyCount(report.candidate_family_counts),
    selected_terminal_artifact_count: terminalFamilyCount(report.selected_family_counts) ||
      selectedArtifacts.length,
    selected_terminal_artifacts: selectedArtifacts,
    terminal_priority_family_statuses: terminalFamilyStatuses,
    missing_terminal_priority_families: terminalFamilyStatuses
      .filter((status) => status.status === 'missing')
      .map((status) => status.family),
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
    report.enforcement?.hard_block_active
      ? '- Mode: hard-block (approved terminal coverage enforcement)'
      : '- Mode: warning-only (does not block merges or automation)',
    `- Requested mode: ${report.requested_mode || report.enforcement?.requested_mode || report.mode || DEFAULT_ENFORCEMENT_MODE}`,
    `- Status: ${report.status}`,
    `- Coverage status: ${report.coverage_status || report.status}`,
    `- Hard block eligible: ${report.enforcement?.hard_block_eligible ? 'true' : 'false'}`,
    `- Hard block active: ${report.enforcement?.hard_block_active ? 'true' : 'false'}`,
    `- Input files: ${report.input_file_count || 0}`,
    `- Scanned records: ${report.scanned_record_count || 0}`,
    `- Terminal disposition records: ${report.terminal_record_count}`,
    `- Non-terminal records: ${report.non_terminal_record_count || 0}`,
    `- Observed sources: ${report.observed_source_count}`,
    `- Expected review-thread sources: ${report.expected_source_count}`,
    `- Missing review-thread sources: ${report.missing_source_count}`,
    `- Parse errors: ${report.parse_errors}`,
  ];

  if (report.artifact_selection) {
    const selection = report.artifact_selection;
    lines.push(
      `- Artifact selector status: ${selection.status}`,
      `- Terminal artifacts selected: ${selection.selected_terminal_artifact_count}`,
      `- Terminal artifacts candidates: ${selection.candidate_terminal_artifact_count}`
    );
    if (selection.error_message) {
      lines.push(`- Artifact selector error: ${selection.error_message}`);
    }
    if (selection.missing_terminal_priority_families?.length > 0) {
      lines.push(
        `- Missing terminal artifact families: ${selection.missing_terminal_priority_families.join(', ')}`
      );
    }
  }

  if (report.terminal_artifact_input_mismatch) {
    lines.push(
      '- Terminal artifact input mismatch: selected terminal artifacts did not yield terminal NDJSON input files'
    );
  }

  const modelCompatibility = report.verifier_model_compatibility;
  if (modelCompatibility) {
    lines.push(
      `- Verifier model compatibility: ${modelCompatibility.status}`,
      `- Unsupported verifier model records: ${modelCompatibility.unsupported_record_count}`,
      `- Missing verifier model metadata records: ${modelCompatibility.missing_model_record_count}`,
      `- Legacy missing verifier model metadata records: ${modelCompatibility.legacy_missing_model_record_count || 0}`
    );
    if (modelCompatibility.model_metadata_contract?.required_after) {
      lines.push(
        `- Verifier model metadata required after: ${modelCompatibility.model_metadata_contract.required_after}`
      );
    }
    if (modelCompatibility.unsupported_models?.length > 0) {
      lines.push(`- Unsupported verifier models: ${modelCompatibility.unsupported_models.join(', ')}`);
    }
  }

  const policyBlockers = report.enforcement?.policy_blockers || [];
  if (policyBlockers.length > 0) {
    lines.push(`- Policy blockers: ${policyBlockers.join(', ')}`);
  }

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

  const terminalFamilyStatuses = report.artifact_selection?.terminal_priority_family_statuses || [];
  if (terminalFamilyStatuses.length > 0) {
    lines.push(
      '',
      '| Terminal artifact family | Status | Candidates | Selected | Latest artifact |',
      '|--------------------------|--------|------------|----------|-----------------|'
    );
    for (const familyStatus of terminalFamilyStatuses) {
      const latest = familyStatus.selected_artifact?.name ||
        familyStatus.latest_candidate?.name ||
        'n/a';
      lines.push(
        `| ${familyStatus.family} | ${familyStatus.status} | ${familyStatus.candidate_count} | ${familyStatus.selected_count} | ${latest} |`
      );
    }
  }

  const unsupportedRecords = modelCompatibility?.unsupported_records || [];
  if (unsupportedRecords.length > 0) {
    lines.push(
      '',
      '| Unsupported verifier model source | Model | Disposition | PR | Run |',
      '|-----------------------------------|-------|-------------|----|-----|'
    );
    for (const record of unsupportedRecords) {
      const pr = record.pr_number ? `#${record.pr_number}` : 'n/a';
      const run = record.run_id || 'n/a';
      lines.push(
        `| ${record.source_key} | ${record.model} | ${record.disposition} | ${pr} | ${run} |`
      );
    }
  }

  const missingModelRecords = modelCompatibility?.missing_model_records || [];
  if (missingModelRecords.length > 0) {
    lines.push(
      '',
      '| Missing verifier model source | Disposition | Mode | PR | Run |',
      '|-------------------------------|-------------|------|----|-----|'
    );
    for (const record of missingModelRecords) {
      const pr = record.pr_number ? `#${record.pr_number}` : 'n/a';
      const run = record.run_id || 'n/a';
      lines.push(
        `| ${record.source_key} | ${record.disposition} | ${record.verifier_mode} | ${pr} | ${run} |`
      );
    }
  }

  const legacyMissingModelRecords = modelCompatibility?.legacy_missing_model_records || [];
  if (legacyMissingModelRecords.length > 0) {
    lines.push(
      '',
      '| Legacy missing verifier model source | Disposition | Mode | PR | Run | Artifact created |',
      '|--------------------------------------|-------------|------|----|-----|------------------|'
    );
    for (const record of legacyMissingModelRecords) {
      const pr = record.pr_number ? `#${record.pr_number}` : 'n/a';
      const run = record.run_id || 'n/a';
      const createdAt = record.artifact_created_at || 'n/a';
      lines.push(
        `| ${record.source_key} | ${record.disposition} | ${record.verifier_mode} | ${pr} | ${run} | ${createdAt} |`
      );
    }
  }

  if (report.status === 'no-data') {
    lines.push('', '_No terminal disposition records were found in the metrics input._');
  } else if (report.terminal_record_count === 0 && (report.non_terminal_record_count || 0) > 0) {
    lines.push('', '_Terminal disposition files were found, but they did not contain valid terminal disposition records._');
  }

  return `${lines.join('\n')}\n`;
}

function isTerminalDispositionNdjsonFile(filePath) {
  const name = path.basename(cleanString(filePath));
  return name === 'verifier-terminal-disposition.ndjson' ||
    name === 'review-thread-terminal-disposition.ndjson';
}

function collectNdjsonFiles(root) {
  const files = [];
  const stack = [root];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current || !fs.existsSync(current)) continue;
    const stat = fs.statSync(current);
    if (stat.isFile()) {
      if (current.endsWith('.ndjson') && isTerminalDispositionNdjsonFile(current)) files.push(current);
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
  let readErrors = 0;
  for (const file of files) {
    let text = '';
    try {
      text = fs.readFileSync(file, 'utf8');
    } catch (_error) {
      parseErrors += 1;
      readErrors += 1;
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
  return {
    records,
    parse_errors: parseErrors,
    read_errors: readErrors,
    file_count: files.length,
  };
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    metrics_dir: process.env.TERMINAL_DISPOSITION_METRICS_DIR || 'artifacts',
    artifact_selection_json: process.env.TERMINAL_DISPOSITION_ARTIFACT_SELECTION_JSON || '',
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
    } else if (arg === '--artifact-selection-json') {
      options.artifact_selection_json = next;
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

function readArtifactSelectionReport(filePath) {
  const cleaned = cleanString(filePath);
  if (!cleaned) return null;
  if (!fs.existsSync(cleaned)) {
    return {
      status: 'missing',
      error_message: `artifact selection report not found: ${cleaned}`,
    };
  }
  try {
    return JSON.parse(fs.readFileSync(cleaned, 'utf8'));
  } catch (error) {
    return {
      status: 'parse-error',
      error_message: error?.message || 'failed to parse artifact selection report',
    };
  }
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
  const {
    records,
    parse_errors: parseErrors,
    file_count: inputFileCount,
  } = readNdjsonFiles(inputFiles);
  const expectedSources = parseExpectedSources(options);
  const artifactSelectionReport = readArtifactSelectionReport(options.artifact_selection_json);
  const report = summarizeTerminalDispositionCoverage(records, {
    parse_errors: parseErrors,
    expected_sources: expectedSources,
    artifact_selection_report: artifactSelectionReport,
    input_file_count: inputFileCount,
    input_files: inputFiles,
    enforcement_mode: options.enforcement_mode,
    hard_block_approved: options.hard_block_approved,
  });
  const markdown = formatTerminalDispositionCoverageMarkdown(report);
  fs.writeFileSync(options.output_json, `${JSON.stringify(report, null, 2)}\n`);
  fs.writeFileSync(options.output_md, markdown);
  process.stdout.write(markdown);
  if (report.enforcement.should_fail) {
    process.exitCode = 1;
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  COVERAGE_SCHEMA,
  collectNdjsonFiles,
  expectedReviewThreadSources,
  formatTerminalDispositionCoverageMarkdown,
  isTerminalDispositionNdjsonFile,
  normalizeExpectedSource,
  normalizeEnforcementMode,
  normalizeEnforcementPolicy,
  normalizeArtifactSelectionSummary,
  normalizeTerminalPriorityFamilyStatuses,
  normalizeUnsupportedCodexModels,
  normalizeVerifierModelMetadataContract,
  readNdjsonFiles,
  readArtifactSelectionReport,
  summarizeVerifierModelCompatibility,
  summarizeTerminalDispositionCoverage,
};
