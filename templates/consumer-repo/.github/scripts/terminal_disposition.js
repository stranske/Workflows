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
    actor: input.actor,
    comment_url: input.comment_url ?? input.commentUrl,
    followup_issue_number:
      input.followup_issue_number ?? input.followupIssueNumber ?? input.created_issue_number,
    followup_issue_url:
      input.followup_issue_url ?? input.followupIssueUrl ?? input.created_issue_url,
    needs_human: input.needs_human ?? input.needsHuman,
    dispatch_outcome: input.dispatch_outcome ?? input.dispatchOutcome,
  };

  for (const [key, value] of Object.entries(optional)) {
    if (value === null || value === undefined) continue;
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
  summarizeTerminalDispositionSources,
  formatTerminalDispositionMarkdown,
  sourceKey,
};
