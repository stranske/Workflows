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

function cleanBool(value) {
  if (typeof value === 'boolean') return value;
  const text = cleanString(value).toLowerCase();
  if (['true', '1', 'yes', 'on'].includes(text)) return true;
  if (['false', '0', 'no', 'off'].includes(text)) return false;
  return null;
}

function normalizeToken(value, fallback = 'unknown') {
  const text = cleanString(value).toLowerCase().replace(/_/g, '-');
  const normalized = text.replace(/[^a-z0-9_.:-]+/g, '-').replace(/^-+|-+$/g, '');
  return normalized || fallback;
}

function normalizeSourceType(value) {
  const text = cleanString(value).toLowerCase();
  if (!text) return 'unknown';
  return text.replace(/[^a-z0-9_.:-]+/g, '-').replace(/^-+|-+$/g, '') || 'unknown';
}

function normalizeSourceId(value, fallback) {
  const text = cleanString(value);
  if (text) return text;
  const fallbackText = cleanString(fallback);
  return fallbackText || 'unknown';
}

function sourceKey(sourceType, sourceId) {
  return `${normalizeSourceType(sourceType)}:${normalizeSourceId(sourceId)}`;
}

function cleanIntArray(value) {
  const rawItems = Array.isArray(value) ? value : [value];
  return [...new Set(
    rawItems
      .flatMap((item) => {
        if (Array.isArray(item)) return item;
        if (typeof item === 'string') return item.split(',');
        return [item];
      })
      .map((item) => cleanInt(item))
      .filter((item) => item !== null && item > 0)
  )].sort((a, b) => a - b);
}

function normalizeLedgerDisposition(input = {}) {
  const explicit = cleanString(input.disposition ?? input.terminal_disposition);
  const normalized = explicit.toLowerCase().replace(/_/g, '-');
  const allowed = new Set(['merge', 'supersede', 'follow-up', 'accept-risk', 'needs-human']);
  if (allowed.has(normalized)) return normalized;

  const terminalDisposition = cleanString(input.terminal_state ?? input.terminalState).toLowerCase();
  if (terminalDisposition.includes('follow-up')) return 'follow-up';
  if (terminalDisposition.includes('needs-human') || terminalDisposition.includes('verifier-error')) {
    return 'needs-human';
  }
  if (terminalDisposition.includes('verified-pass')) return 'merge';

  const verdict = cleanString(input.verdict).toLowerCase();
  const hasFollowup = cleanInt(input.followup_issue_number ?? input.followupIssueNumber) !== null ||
    cleanInt(input.followup_pr_number ?? input.followupPrNumber) !== null;
  if (hasFollowup) return 'follow-up';
  if (input.needs_human === true || input.needsHuman === true) return 'needs-human';
  if (['pass', 'passed'].includes(verdict)) return 'merge';
  if (['fail', 'failed', 'concerns', 'error'].includes(verdict)) return 'needs-human';
  return 'needs-human';
}

function normalizeVerifierFollowupPolicy(input = {}) {
  const embedded = input.followup_policy ?? input.followupPolicy ?? {};
  const policy = embedded && typeof embedded === 'object' ? embedded : {};
  const disposition = normalizeLedgerDisposition(input);
  const followupIssue = cleanInt(
    input.followup_issue_number ?? input.followupIssueNumber ?? input.created_issue_number
  );
  const followupPr = cleanInt(input.followup_pr_number ?? input.followupPrNumber);
  const needsHuman = cleanBool(input.needs_human ?? input.needsHuman);
  const chainDepth = cleanInt(policy.chain_depth ?? input.chain_depth ?? input.chainDepth);
  const maxChainDepth = cleanInt(
    policy.max_chain_depth ??
      policy.maxChainDepth ??
      input.max_chain_depth ??
      input.maxChainDepth
  );
  const nextChainDepth = cleanInt(
    policy.next_chain_depth ??
      policy.nextChainDepth ??
      input.next_chain_depth ??
      input.nextChainDepth
  );

  let action = normalizeToken(
    policy.action ??
      input.followup_policy_action ??
      input.followupPolicyAction ??
      input.policy_action ??
      input.policyAction,
    ''
  );
  const allowedActions = new Set([
    'create-follow-up',
    'needs-human',
    'skip-follow-up',
    'accept-risk',
    'no-op',
    'unknown',
  ]);
  if (!allowedActions.has(action)) action = '';
  if (!action) {
    if (needsHuman === true || disposition === 'needs-human') {
      action = 'needs-human';
    } else if (followupIssue !== null || followupPr !== null || disposition === 'follow-up') {
      action = 'create-follow-up';
    } else if (disposition === 'merge') {
      action = 'no-op';
    } else if (disposition === 'accept-risk') {
      action = 'accept-risk';
    } else {
      action = 'skip-follow-up';
    }
  }

  const reason = cleanString(
    policy.reason ??
      input.followup_policy_reason ??
      input.followupPolicyReason ??
      input.policy_reason ??
      input.policyReason
  );
  const trigger = normalizeToken(
    policy.trigger ??
      input.followup_policy_trigger ??
      input.followupPolicyTrigger ??
      input.policy_trigger ??
      input.policyTrigger,
    ''
  );
  const depthLimitExceeded = cleanBool(
    policy.depth_limit_exceeded ??
      policy.depthLimitExceeded ??
      input.depth_limit_exceeded ??
      input.depthLimitExceeded
  );

  const record = {
    schema: 'workflows-verifier-followup-policy/v1',
    action,
  };
  if (reason) record.reason = reason;
  if (trigger) record.trigger = trigger;
  if (chainDepth !== null) record.chain_depth = chainDepth;
  if (maxChainDepth !== null) record.max_chain_depth = maxChainDepth;
  if (nextChainDepth !== null) record.next_chain_depth = nextChainDepth;
  if (depthLimitExceeded !== null) record.depth_limit_exceeded = depthLimitExceeded;
  return record;
}

function normalizeTerminalDisposition(input = {}) {
  const prNumber = cleanInt(input.pr_number ?? input.prNumber ?? input.pr);
  const issueNumber = cleanInt(input.issue_number ?? input.issueNumber ?? input.issue);
  const sourceType = normalizeSourceType(input.source_type ?? input.sourceType);
  const sourceId = normalizeSourceId(
    input.source_id ?? input.sourceId,
    issueNumber ?? prNumber ?? input.run_id ?? input.runId
  );
  const disposition = cleanString(
    input.disposition ?? input.terminal_state ?? input.terminalState ?? input.status
  ) || 'unknown';
  const timestamp = cleanString(input.timestamp) || new Date().toISOString();

  const record = {
    schema: 'workflows-terminal-disposition/v1',
    metric_type: 'verifier_terminal_disposition',
    timestamp,
    source_type: sourceType,
    source_id: sourceId,
    source_key: sourceKey(sourceType, sourceId),
    disposition,
  };

  const optional = {
    source_title: input.source_title ?? input.sourceTitle,
    pr_number: prNumber,
    issue_number: issueNumber,
    verdict: input.verdict,
    reason: input.reason,
    workflow: input.workflow,
    run_id: input.run_id ?? input.runId,
    run_attempt: input.run_attempt ?? input.runAttempt,
    artifact_name: input.artifact_name ?? input.artifactName,
    artifact_family: input.artifact_family ?? input.artifactFamily,
    actor: input.actor,
    comment_url: input.comment_url ?? input.commentUrl,
    followup_issue_number:
      input.followup_issue_number ?? input.followupIssueNumber ?? input.created_issue_number,
    followup_issue_url:
      input.followup_issue_url ?? input.followupIssueUrl ?? input.created_issue_url,
    needs_human: input.needs_human ?? input.needsHuman,
    dispatch_outcome: input.dispatch_outcome ?? input.dispatchOutcome,
    llm_model: input.llm_model ?? input.llmModel ?? input.model,
    model_selection_reason: input.model_selection_reason ?? input.modelSelectionReason,
    verifier_mode: input.verifier_mode ?? input.verifierMode,
  };

  for (const [key, value] of Object.entries(optional)) {
    if (value === null || value === undefined) continue;
    const cleaned = typeof value === 'boolean' ? value : cleanString(value);
    if (cleaned === '') continue;
    record[key] = typeof value === 'string' ? cleaned : value;
  }

  return record;
}

function normalizeVerifierFollowupLedger(input = {}) {
  const prNumber = cleanInt(input.pr_number ?? input.prNumber ?? input.pr);
  const verificationRunId = normalizeSourceId(
    input.verification_run_id ?? input.verificationRunId ?? input.run_id ?? input.runId,
    prNumber ?? input.timestamp
  );
  const timestamp = cleanString(input.timestamp) || new Date().toISOString();
  const sourceIssueNumbers = cleanIntArray(
    input.source_issue_numbers ?? input.sourceIssueNumbers ?? input.issue_numbers ?? input.issueNumbers
  );
  const disposition = normalizeLedgerDisposition(input);
  const stateKey = `pr:${prNumber || 'unknown'}:run:${verificationRunId}`;

  const record = {
    schema: 'workflows-verifier-followup-ledger/v1',
    metric_type: 'verifier_followup_ledger',
    timestamp,
    state_key: stateKey,
    pr_number: prNumber,
    verification_run_id: verificationRunId,
    verdict: cleanString(input.verdict) || 'unknown',
    disposition,
    source_issue_numbers: sourceIssueNumbers,
    followup_policy: normalizeVerifierFollowupPolicy({ ...input, disposition }),
  };

  const optional = {
    verification_run_attempt:
      input.verification_run_attempt ??
      input.verificationRunAttempt ??
      input.run_attempt ??
      input.runAttempt,
    concerns_hash: input.concerns_hash ?? input.concernsHash,
    followup_issue_number:
      input.followup_issue_number ?? input.followupIssueNumber ?? input.created_issue_number,
    followup_issue_url:
      input.followup_issue_url ?? input.followupIssueUrl ?? input.created_issue_url,
    followup_pr_number: input.followup_pr_number ?? input.followupPrNumber,
    followup_pr_url: input.followup_pr_url ?? input.followupPrUrl,
    chain_depth: input.chain_depth ?? input.chainDepth,
    workflow: input.workflow,
    actor: input.actor,
    terminal_disposition_artifact:
      input.terminal_disposition_artifact ?? input.terminalDispositionArtifact,
    dispatch_outcome: input.dispatch_outcome ?? input.dispatchOutcome,
    needs_human: input.needs_human ?? input.needsHuman,
  };

  for (const [key, value] of Object.entries(optional)) {
    if (value === null || value === undefined) continue;
    if (key.endsWith('_number') || key === 'chain_depth' || key === 'verification_run_attempt') {
      const parsed = cleanInt(value);
      if (parsed !== null) record[key] = parsed;
      continue;
    }
    const cleaned = typeof value === 'boolean' ? value : cleanString(value);
    if (cleaned === '') continue;
    record[key] = typeof value === 'string' ? cleaned : value;
  }

  return record;
}

function dispositionFromRecord(record = {}) {
  return cleanString(record.disposition ?? record.terminal_state ?? record.status) || 'unknown';
}

function summarizeTerminalDispositionSources(records = []) {
  const grouped = new Map();

  for (const raw of records) {
    if (!raw || typeof raw !== 'object') continue;
    const record = normalizeTerminalDisposition(raw);
    const key = record.source_key;
    if (!grouped.has(key)) {
      grouped.set(key, {
        source_type: record.source_type,
        source_id: record.source_id,
        total: 0,
        dispositions: new Map(),
        pr_numbers: new Set(),
        issue_numbers: new Set(),
      });
    }
    const group = grouped.get(key);
    group.total += 1;
    const disposition = dispositionFromRecord(record);
    group.dispositions.set(disposition, (group.dispositions.get(disposition) || 0) + 1);
    if (record.pr_number) group.pr_numbers.add(Number(record.pr_number));
    if (record.issue_number) group.issue_numbers.add(Number(record.issue_number));
  }

  return [...grouped.values()]
    .map((group) => ({
      source_type: group.source_type,
      source_id: group.source_id,
      total: group.total,
      dispositions: Object.fromEntries(
        [...group.dispositions.entries()].sort((a, b) => a[0].localeCompare(b[0]))
      ),
      pr_numbers: [...group.pr_numbers].sort((a, b) => a - b),
      issue_numbers: [...group.issue_numbers].sort((a, b) => a - b),
    }))
    .sort((a, b) => {
      const typeOrder = a.source_type.localeCompare(b.source_type);
      return typeOrder || String(a.source_id).localeCompare(String(b.source_id));
    });
}

function formatTerminalDispositionMarkdown(records = []) {
  const summary = summarizeTerminalDispositionSources(records);
  if (summary.length === 0) {
    return 'No terminal disposition records found.';
  }

  const lines = [
    '| Source | Dispositions | PRs | Issues |',
    '|--------|--------------|-----|--------|',
  ];
  for (const item of summary) {
    const dispositions = Object.entries(item.dispositions)
      .map(([name, count]) => `${name} (${count})`)
      .join(', ');
    const prs = item.pr_numbers.length ? item.pr_numbers.map((value) => `#${value}`).join(', ') : 'n/a';
    const issues = item.issue_numbers.length
      ? item.issue_numbers.map((value) => `#${value}`).join(', ')
      : 'n/a';
    lines.push(`| ${item.source_type}:${item.source_id} | ${dispositions} | ${prs} | ${issues} |`);
  }
  return lines.join('\n');
}

module.exports = {
  normalizeTerminalDisposition,
  normalizeVerifierFollowupLedger,
  normalizeVerifierFollowupPolicy,
  normalizeLedgerDisposition,
  summarizeTerminalDispositionSources,
  formatTerminalDispositionMarkdown,
  sourceKey,
};
