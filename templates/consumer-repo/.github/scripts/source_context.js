'use strict';

const SOURCE_TYPES = Object.freeze({
  GITHUB_ISSUE: 'github_issue',
  LOCAL_REQUEST: 'local_request',
  AUTOMATION_RUN: 'automation_run',
  SYNC_CAMPAIGN: 'sync_campaign',
  DEPENDABOT: 'dependabot',
  REVIEW_FOLLOWUP: 'review_followup',
  MANUAL_REMOTE: 'manual_remote',
  UNKNOWN: 'unknown',
});

const VALID_SOURCE_TYPES = new Set(Object.values(SOURCE_TYPES).filter((type) => type !== SOURCE_TYPES.UNKNOWN));

const SOURCE_LABELS = Object.freeze({
  'workflow:source-issue': SOURCE_TYPES.GITHUB_ISSUE,
  workflow_source_issue: SOURCE_TYPES.GITHUB_ISSUE,
  'workflow:source-local-request': SOURCE_TYPES.LOCAL_REQUEST,
  workflow_source_local_request: SOURCE_TYPES.LOCAL_REQUEST,
  'workflow:source-automation': SOURCE_TYPES.AUTOMATION_RUN,
  workflow_source_automation: SOURCE_TYPES.AUTOMATION_RUN,
  'workflow:source-sync': SOURCE_TYPES.SYNC_CAMPAIGN,
  workflow_source_sync: SOURCE_TYPES.SYNC_CAMPAIGN,
  'workflow:source-maintenance': SOURCE_TYPES.SYNC_CAMPAIGN,
  workflow_source_maintenance: SOURCE_TYPES.SYNC_CAMPAIGN,
  'workflow:source-dependabot': SOURCE_TYPES.DEPENDABOT,
  workflow_source_dependabot: SOURCE_TYPES.DEPENDABOT,
  'workflow:source-review-followup': SOURCE_TYPES.REVIEW_FOLLOWUP,
  workflow_source_review_followup: SOURCE_TYPES.REVIEW_FOLLOWUP,
  'workflow:source-direct-pr': SOURCE_TYPES.MANUAL_REMOTE,
  workflow_source_direct_pr: SOURCE_TYPES.MANUAL_REMOTE,
  'workflow:no-automation': SOURCE_TYPES.MANUAL_REMOTE,
  workflow_no_automation: SOURCE_TYPES.MANUAL_REMOTE,
});

const CHECKBOX_SOURCE_PATTERNS = Object.freeze([
  [SOURCE_TYPES.GITHUB_ISSUE, /\bgithub\s+issue\b|\bsource\s+issue\b/i],
  [
    SOURCE_TYPES.MANUAL_REMOTE,
    /\bdirect\s+pr\b|\bremote\s+github\s+work\b|\bstarted\s+directly\b|\bdo\s+not\s+automate\b|\bhuman[- ]only\b/i,
  ],
  [SOURCE_TYPES.LOCAL_REQUEST, /\blocal\s+(?:codex|user)\s+request\b|\blocal\s+request\b/i],
  [SOURCE_TYPES.AUTOMATION_RUN, /\bautomation\s+run\b|\bworkflow\s+run\b/i],
  [SOURCE_TYPES.REVIEW_FOLLOWUP, /\breview\s+follow[- ]?up\b|\bfollow[- ]?up\s+from\s+pr\b/i],
  [SOURCE_TYPES.SYNC_CAMPAIGN, /\bsync\b|\bmaintenance\s+campaign\b|\bmaintenance\b/i],
  [SOURCE_TYPES.DEPENDABOT, /\bdependabot\b|\bdependency\s+update\b/i],
]);

function cleanString(value) {
  return String(value || '').trim();
}

function normalizeToken(value) {
  return cleanString(value)
    .toLowerCase()
    .replace(/[`*~]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function normalizeSourceType(value) {
  const token = normalizeToken(value);
  if (!token) {
    return SOURCE_TYPES.UNKNOWN;
  }

  const aliases = new Map([
    ['issue', SOURCE_TYPES.GITHUB_ISSUE],
    ['github_issue', SOURCE_TYPES.GITHUB_ISSUE],
    ['source_issue', SOURCE_TYPES.GITHUB_ISSUE],
    ['local', SOURCE_TYPES.LOCAL_REQUEST],
    ['local_request', SOURCE_TYPES.LOCAL_REQUEST],
    ['local_codex_request', SOURCE_TYPES.LOCAL_REQUEST],
    ['local_user_request', SOURCE_TYPES.LOCAL_REQUEST],
    ['automation', SOURCE_TYPES.AUTOMATION_RUN],
    ['automation_run', SOURCE_TYPES.AUTOMATION_RUN],
    ['workflow_run', SOURCE_TYPES.AUTOMATION_RUN],
    ['sync', SOURCE_TYPES.SYNC_CAMPAIGN],
    ['sync_campaign', SOURCE_TYPES.SYNC_CAMPAIGN],
    ['maintenance', SOURCE_TYPES.SYNC_CAMPAIGN],
    ['maintenance_sync', SOURCE_TYPES.SYNC_CAMPAIGN],
    ['dependabot', SOURCE_TYPES.DEPENDABOT],
    ['dependency_update', SOURCE_TYPES.DEPENDABOT],
    ['review_followup', SOURCE_TYPES.REVIEW_FOLLOWUP],
    ['review_follow_up', SOURCE_TYPES.REVIEW_FOLLOWUP],
    ['followup', SOURCE_TYPES.REVIEW_FOLLOWUP],
    ['follow_up', SOURCE_TYPES.REVIEW_FOLLOWUP],
    ['manual', SOURCE_TYPES.MANUAL_REMOTE],
    ['manual_remote', SOURCE_TYPES.MANUAL_REMOTE],
    ['direct', SOURCE_TYPES.MANUAL_REMOTE],
    ['direct_pr', SOURCE_TYPES.MANUAL_REMOTE],
    ['remote', SOURCE_TYPES.MANUAL_REMOTE],
    ['remote_github_work', SOURCE_TYPES.MANUAL_REMOTE],
    ['no_automation', SOURCE_TYPES.MANUAL_REMOTE],
  ]);

  return aliases.get(token) || SOURCE_TYPES.UNKNOWN;
}

function labelNames(pull = {}) {
  return Array.isArray(pull.labels)
    ? pull.labels
        .map((label) => cleanString(typeof label === 'string' ? label : label?.name || ''))
        .filter(Boolean)
    : [];
}

function hasExplicitIssueReferencePrefix(value) {
  const prefix = cleanString(value)
    .replace(/[>_[\]()`*~]/g, ' ')
    .replace(/\s+/g, ' ');

  if (/\b(?:pr|pull\s+request)\s*[:#-]?\s*$/i.test(prefix)) {
    return false;
  }

  return /\b(?:close[sd]?|closing|fix(?:e[sd])?|fixing|resolve[sd]?|resolving|address(?:e[sd])?|addressing|relate[sd]?\s+to|refs?|references?|issue|source\s+issue|github\s+issue)\s*[:#-]?\s*$/i.test(
    prefix
  );
}

function extractIssueNumberFromText(text) {
  const value = String(text || '');
  for (const match of value.matchAll(/#([0-9]+)/g)) {
    if (!match[1]) {
      continue;
    }
    const before = value.slice(Math.max(0, match.index - 200), match.index);
    const token = before.split(/\s/).pop() || '';
    if (token.includes('/')) {
      continue;
    }
    if (match.index > 0 && /\w/.test(value[match.index - 1])) {
      continue;
    }
    const preceding = value.slice(Math.max(0, match.index - 20), match.index);
    if (/\b(?:run|attempt|step|job|check|version|v)\s*$/i.test(preceding)) {
      continue;
    }
    if (!hasExplicitIssueReferencePrefix(value.slice(Math.max(0, match.index - 80), match.index))) {
      continue;
    }
    const parsed = Number.parseInt(match[1], 10);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  return null;
}

function extractIssueNumberFromPull(pull = {}) {
  const bodyText = String(pull?.body || '');
  const metaMatch = bodyText.match(/<!--\s*meta:issue:([0-9]+)\s*-->/i);
  if (metaMatch) {
    return Number.parseInt(metaMatch[1], 10);
  }

  const branch = String(pull?.head?.ref || '');
  const branchMatch = branch.match(/issue-#?([0-9]+)/i) || branch.match(/-issue-#([0-9]+)(?:$|[^0-9])/i);
  if (branchMatch) {
    return Number.parseInt(branchMatch[1], 10);
  }

  const titleNumber = extractIssueNumberFromText(pull?.title || '');
  if (titleNumber) {
    return titleNumber;
  }

  return extractIssueNumberFromText(bodyText);
}

function parseHtmlMarker(body, name) {
  const pattern = new RegExp(`<!--\\s*${name}\\s*:\\s*([\\s\\S]*?)\\s*-->`, 'i');
  const match = String(body || '').match(pattern);
  return match ? cleanString(match[1]) : '';
}

function parseWorkflowSourceBlock(body) {
  const match = String(body || '').match(
    /<!--\s*workflow-source:start\s*-->([\s\S]*?)<!--\s*workflow-source:end\s*-->/i,
  );
  if (!match) {
    return {};
  }

  const result = {};
  for (const line of match[1].split(/\r?\n/)) {
    const fieldMatch = line.match(/^\s*[-*]?\s*([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.+?)\s*$/);
    if (!fieldMatch) {
      continue;
    }
    const key = normalizeToken(fieldMatch[1]);
    const value = cleanString(fieldMatch[2]);
    if (key && value) {
      result[key] = value;
    }
  }
  return result;
}

function sourceTypeFromCheckedTemplate(body) {
  const lines = String(body || '').split(/\r?\n/);
  const start = lines.findIndex((line) => /^#{1,6}\s+Workflow Source\s*$/i.test(line));
  if (start < 0) {
    return SOURCE_TYPES.UNKNOWN;
  }
  const sectionLines = [];
  for (const line of lines.slice(start + 1)) {
    if (/^#{1,6}\s+\S/.test(line)) {
      break;
    }
    sectionLines.push(line);
  }
  const text = sectionLines.join('\n');
  const checkedTypes = new Set();
  for (const line of text.split(/\r?\n/)) {
    const checkbox = line.match(/^\s*[-*]\s+\[[xX]\]\s+(.+?)\s*$/);
    if (!checkbox) {
      continue;
    }
    const label = checkbox[1];
    for (const [sourceType, pattern] of CHECKBOX_SOURCE_PATTERNS) {
      if (pattern.test(label)) {
        checkedTypes.add(sourceType);
        break;
      }
    }
  }
  return checkedTypes.size === 1 ? Array.from(checkedTypes)[0] : SOURCE_TYPES.UNKNOWN;
}

function sourceTypeFromLabels(pull = {}) {
  for (const label of labelNames(pull)) {
    const sourceType = SOURCE_LABELS[label.toLowerCase()] || SOURCE_LABELS[normalizeToken(label)];
    if (sourceType) {
      return sourceType;
    }
  }
  return SOURCE_TYPES.UNKNOWN;
}

function inferredSourceType(pull = {}) {
  const branch = cleanString(pull?.head?.ref).toLowerCase();
  const title = cleanString(pull?.title).toLowerCase();
  const author = cleanString(pull?.user?.login).toLowerCase();
  const labels = labelNames(pull).map((label) => label.toLowerCase());

  if (author.startsWith('dependabot') || branch.startsWith('dependabot/')) {
    return SOURCE_TYPES.DEPENDABOT;
  }
  if (
    branch.startsWith('sync/') ||
    branch.startsWith('sync-') ||
    labels.includes('campaign:sync-dependabot') ||
    /\bsync\b/.test(title)
  ) {
    return SOURCE_TYPES.SYNC_CAMPAIGN;
  }
  if (/review[-/ ]follow/.test(branch) || /\breview\s+follow[- ]?up\b/.test(title)) {
    return SOURCE_TYPES.REVIEW_FOLLOWUP;
  }
  return SOURCE_TYPES.UNKNOWN;
}

function resolvePrSourceContext(pull = {}) {
  const body = String(pull?.body || '');
  const block = parseWorkflowSourceBlock(body);
  const issueNumber = extractIssueNumberFromPull(pull);

  const markerType = normalizeSourceType(parseHtmlMarker(body, 'workflow-source'));
  const blockType = normalizeSourceType(block.origin || block.source || block.type);
  const checkboxType = sourceTypeFromCheckedTemplate(body);
  const labelType = sourceTypeFromLabels(pull);
  const inferredType = inferredSourceType(pull);
  const sourceType = issueNumber
    ? SOURCE_TYPES.GITHUB_ISSUE
    : [markerType, blockType, checkboxType, labelType, inferredType].find((type) => type !== SOURCE_TYPES.UNKNOWN)
      || SOURCE_TYPES.UNKNOWN;

  const sourceRef =
    cleanString(parseHtmlMarker(body, 'workflow-source-ref')) ||
    cleanString(block.source_ref || block.ref || block.reference) ||
    (issueNumber ? `#${issueNumber}` : '');
  const lifecycle =
    cleanString(parseHtmlMarker(body, 'workflow-lifecycle')) ||
    cleanString(block.lifecycle || block.intended_lifecycle);
  const automation =
    cleanString(parseHtmlMarker(body, 'workflow-automation')) ||
    cleanString(block.automation || block.automation_intent);

  return {
    sourceType,
    issueNumber,
    sourceRef,
    lifecycle,
    automation,
    isKnown: sourceType !== SOURCE_TYPES.UNKNOWN,
    isValid: VALID_SOURCE_TYPES.has(sourceType),
    isExplicit: Boolean(
      issueNumber ||
        markerType !== SOURCE_TYPES.UNKNOWN ||
        blockType !== SOURCE_TYPES.UNKNOWN ||
        checkboxType !== SOURCE_TYPES.UNKNOWN ||
        labelType !== SOURCE_TYPES.UNKNOWN
    ),
    requiresIssue: sourceType === SOURCE_TYPES.GITHUB_ISSUE,
  };
}

function hasValidNonIssueSourceContext(pull = {}) {
  const context = resolvePrSourceContext(pull);
  return context.isValid && !context.requiresIssue;
}

function formatSourceContextForLog(context = {}) {
  const parts = [`origin=${context.sourceType || SOURCE_TYPES.UNKNOWN}`];
  if (context.sourceRef) {
    parts.push(`ref=${context.sourceRef}`);
  }
  if (context.lifecycle) {
    parts.push(`lifecycle=${context.lifecycle}`);
  }
  if (context.automation) {
    parts.push(`automation=${context.automation}`);
  }
  return parts.join(' ');
}

module.exports = {
  SOURCE_TYPES,
  VALID_SOURCE_TYPES,
  normalizeSourceType,
  extractIssueNumberFromPull,
  parseWorkflowSourceBlock,
  sourceTypeFromCheckedTemplate,
  sourceTypeFromLabels,
  resolvePrSourceContext,
  hasValidNonIssueSourceContext,
  formatSourceContextForLog,
};
