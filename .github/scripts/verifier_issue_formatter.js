'use strict';

const {
  parseScopeTasksAcceptanceSections,
} = require('./issue_scope_parser.js');

/**
 * Default section order and structure for follow-up issues.
 * This mirrors the template in docs/templates/AGENT_ISSUE_TEMPLATE.md
 */
const SECTION_ORDER = ['source', 'why', 'scope', 'nonGoals', 'tasks', 'acceptance', 'notes'];

/**
 * Formats a "Source" section with references to the original PR and issue.
 *
 * @param {Object} options
 * @param {number} [options.prNumber] - Original PR number
 * @param {string} [options.prUrl] - URL to the PR
 * @param {number[]} [options.issueNumbers] - Parent issue numbers
 * @param {string} [options.verdict] - Verifier verdict (pass/fail)
 * @param {string} [options.runUrl] - URL to the verifier workflow run
 * @returns {string} Formatted source section
 */
function formatSourceSection({ prNumber, prUrl, issueNumbers, verdict, runUrl }) {
  const lines = ['## Source', ''];

  if (prNumber) {
    const prLink = prUrl ? `[#${prNumber}](${prUrl})` : `#${prNumber}`;
    lines.push(`- Original PR: ${prLink}`);
  }

  if (Array.isArray(issueNumbers) && issueNumbers.length > 0) {
    const issueLinks = issueNumbers.map((n) => `#${n}`).join(', ');
    lines.push(`- Parent issue${issueNumbers.length > 1 ? 's' : ''}: ${issueLinks}`);
  }

  if (verdict) {
    lines.push(`- Verifier verdict: ${verdict.toUpperCase()}`);
  }

  if (runUrl) {
    lines.push(`- Verifier run: [workflow run](${runUrl})`);
  }

  return lines.join('\n');
}

/**
 * Parse verifier output to extract unmet acceptance criteria and task gaps.
 *
 * @param {string} verifierOutput - Raw output from the verifier (codex-output.md)
 * @returns {Object} Parsed findings
 */
function parseVerifierFindings(verifierOutput) {
  const output = String(verifierOutput || '');
  const findings = {
    verdict: 'unknown',
    unmetCriteria: [],
    gaps: [],
    summary: '',
  };

  // Extract verdict
  const verdictMatch = output.match(/verdict:\s*(pass|fail)/i);
  if (verdictMatch) {
    findings.verdict = verdictMatch[1].toLowerCase();
  }

  // Look for bullet points that describe failures or gaps
  const lines = output.split('\n');
  let inGapsSection = false;

  for (const line of lines) {
    const trimmed = line.trim();

    // Detect sections that indicate gaps
    if (/^(blocking|gap|missing|fail|unmet)/i.test(trimmed)) {
      inGapsSection = true;
      continue;
    }

    // Capture bullet points describing issues
    if (inGapsSection && /^[-*•]/.test(trimmed)) {
      const content = trimmed.replace(/^[-*•]\s*/, '').trim();
      if (content) {
        findings.gaps.push(content);
      }
    }

    // Reset section tracking on blank lines or new headings
    if (!trimmed || /^#/.test(trimmed)) {
      inGapsSection = false;
    }
  }

  // Build summary from the first paragraph after verdict
  const afterVerdict = output.split(/verdict:\s*(pass|fail)/i)[2] || '';
  const summaryLines = [];
  for (const line of afterVerdict.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (summaryLines.length > 0) break;
      continue;
    }
    if (/^[-*•#]/.test(trimmed)) break;
    summaryLines.push(trimmed);
  }
  findings.summary = summaryLines.join(' ').trim();

  return findings;
}

/**
 * Extract unchecked items from a checkbox section.
 *
 * @param {string} content - Section content with checkboxes
 * @returns {string[]} Array of unchecked item texts
 */
function extractUncheckedItems(content) {
  const items = [];
  const lines = String(content || '').split('\n');

  for (const line of lines) {
    // Match unchecked boxes: - [ ] or * [ ]
    const match = line.match(/^\s*[-*]\s+\[\s\]\s+(.+)$/);
    if (match) {
      items.push(match[1].trim());
    }
  }

  return items;
}

/**
 * Extract checked items from a checkbox section.
 *
 * @param {string} content - Section content with checkboxes
 * @returns {string[]} Array of checked item texts
 */
function extractCheckedItems(content) {
  const items = [];
  const lines = String(content || '').split('\n');

  for (const line of lines) {
    // Match checked boxes: - [x] or - [X] or * [x]
    const match = line.match(/^\s*[-*]\s+\[[xX]\]\s+(.+)$/);
    if (match) {
      items.push(match[1].trim());
    }
  }

  return items;
}

/**
 * Build a checklist from items, all unchecked.
 *
 * @param {string[]} items - List of task/criteria descriptions
 * @returns {string} Formatted checklist
 */
function buildChecklist(items) {
  if (!Array.isArray(items) || items.length === 0) {
    return '';
  }
  return items.map((item) => `- [ ] ${item}`).join('\n');
}

/**
 * Format a follow-up issue body based on verifier failure.
 *
 * This function:
 * 1. Copies unmet acceptance criteria from the original issue/PR
 * 2. Generates new tasks based on verifier findings
 * 3. Preserves context (Why, Scope, Non-Goals) from the original
 * 4. Adds implementation notes with verifier details
 *
 * @param {Object} options
 * @param {string} options.verifierOutput - Raw verifier output
 * @param {string} [options.prBody] - Original PR body
 * @param {Object[]} [options.issues] - Array of linked issues with {number, title, body}
 * @param {number} [options.prNumber] - PR number
 * @param {string} [options.prUrl] - PR URL
 * @param {string} [options.runUrl] - Verifier workflow run URL
 * @returns {Object} { title: string, body: string }
 */
function formatFollowUpIssue({
  verifierOutput,
  prBody,
  issues = [],
  prNumber,
  prUrl,
  runUrl,
}) {
  const findings = parseVerifierFindings(verifierOutput);
  const issueNumbers = issues.map((i) => i.number).filter(Boolean);

  // Parse sections from PR and all linked issues
  const prSections = parseScopeTasksAcceptanceSections(prBody || '');
  const issueSectionsList = issues.map((issue) =>
    parseScopeTasksAcceptanceSections(issue.body || '')
  );

  // Merge sections, preferring the first non-empty value found
  const merged = {
    scope: '',
    tasks: '',
    acceptance: '',
  };

  // Check PR first, then issues in order
  const allSources = [prSections, ...issueSectionsList];
  for (const source of allSources) {
    if (!merged.scope && source.scope) merged.scope = source.scope;
    if (!merged.tasks && source.tasks) merged.tasks = source.tasks;
    if (!merged.acceptance && source.acceptance) merged.acceptance = source.acceptance;
  }

  // Extract Why/Goals section (look for common patterns)
  let why = '';
  for (const issue of issues) {
    const body = issue.body || '';
    // Look for ## Why, ## Goals, ## Summary sections
    const whyMatch = body.match(/##\s*(?:Why|Goals?|Summary|Motivation)\s*\n([\s\S]*?)(?=\n##|\n---|\n\n\n|$)/i);
    if (whyMatch) {
      why = whyMatch[1].trim();
      break;
    }
  }
  // Also check PR body
  if (!why && prBody) {
    const whyMatch = prBody.match(/##\s*(?:Why|Goals?|Summary|Motivation)\s*\n([\s\S]*?)(?=\n##|\n---|\n\n\n|$)/i);
    if (whyMatch) {
      why = whyMatch[1].trim();
    }
  }

  // Extract Non-Goals section
  let nonGoals = '';
  for (const issue of issues) {
    const body = issue.body || '';
    const ngMatch = body.match(/##\s*(?:Non-Goals?|Out of Scope|Constraints)\s*\n([\s\S]*?)(?=\n##|\n---|\n\n\n|$)/i);
    if (ngMatch) {
      nonGoals = ngMatch[1].trim();
      break;
    }
  }
  if (!nonGoals && prBody) {
    const ngMatch = prBody.match(/##\s*(?:Non-Goals?|Out of Scope|Constraints)\s*\n([\s\S]*?)(?=\n##|\n---|\n\n\n|$)/i);
    if (ngMatch) {
      nonGoals = ngMatch[1].trim();
    }
  }

  // Determine unmet acceptance criteria
  const uncheckedAcceptance = extractUncheckedItems(merged.acceptance);
  const completedTasks = extractCheckedItems(merged.tasks);
  const incompleteTasks = extractUncheckedItems(merged.tasks);

  // Build new task list based on scenario:
  // 1. If there are incomplete tasks, copy them
  // 2. If all tasks are complete but acceptance criteria aren't met,
  //    generate new tasks from the gaps
  let newTasks = [];
  if (incompleteTasks.length > 0) {
    // Scenario 1: Copy incomplete tasks
    newTasks = incompleteTasks;
  } else if (completedTasks.length > 0 && uncheckedAcceptance.length > 0) {
    // Scenario 2: All tasks done but criteria not met - need new tasks
    // Generate tasks from verifier findings or acceptance criteria
    if (findings.gaps.length > 0) {
      newTasks = findings.gaps.map((gap) => `Address: ${gap}`);
    } else {
      // Fall back to creating tasks from unmet acceptance criteria
      newTasks = uncheckedAcceptance.map((criterion) => `Satisfy: ${criterion}`);
    }
  }

  // Build implementation notes
  const notesLines = [];
  if (findings.summary) {
    notesLines.push(findings.summary);
  }
  if (findings.gaps.length > 0 && incompleteTasks.length === 0) {
    notesLines.push('');
    notesLines.push('Verifier identified the following gaps:');
    for (const gap of findings.gaps) {
      notesLines.push(`- ${gap}`);
    }
  }
  if (prNumber) {
    notesLines.push('');
    notesLines.push(`Original implementation in PR #${prNumber}.`);
  }

  // Assemble the issue body
  const sections = [];

  // Source section
  sections.push(formatSourceSection({
    prNumber,
    prUrl,
    issueNumbers,
    verdict: findings.verdict,
    runUrl,
  }));

  // Why section (if available)
  if (why) {
    sections.push(['## Why', '', `<!-- Preserved from parent issue -->`, why].join('\n'));
  }

  // Scope section
  if (merged.scope) {
    sections.push(['## Scope', '', `<!-- Updated scope for this follow-up -->`, `Address unmet acceptance criteria from PR #${prNumber || 'N/A'}.`, '', 'Original scope:', merged.scope].join('\n'));
  } else {
    sections.push(['## Scope', '', `Address unmet acceptance criteria from PR #${prNumber || 'N/A'}.`].join('\n'));
  }

  // Non-Goals section (if available)
  if (nonGoals) {
    sections.push(['## Non-Goals', '', `<!-- Preserved from parent issue -->`, nonGoals].join('\n'));
  }

  // Tasks section
  if (newTasks.length > 0) {
    const taskHeader = incompleteTasks.length > 0
      ? '<!-- Incomplete tasks from original issue -->'
      : '<!-- New tasks to address unmet acceptance criteria -->';
    sections.push(['## Tasks', '', taskHeader, buildChecklist(newTasks)].join('\n'));
  } else {
    sections.push(['## Tasks', '', '<!-- Determine tasks needed to satisfy unmet criteria -->', '- [ ] _Task to be determined_'].join('\n'));
  }

  // Acceptance Criteria section
  if (uncheckedAcceptance.length > 0) {
    sections.push(['## Acceptance Criteria', '', '<!-- Unmet criteria from original issue -->', buildChecklist(uncheckedAcceptance)].join('\n'));
  } else {
    sections.push(['## Acceptance Criteria', '', '<!-- Verify the original acceptance criteria are now met -->', '- [ ] All original acceptance criteria satisfied'].join('\n'));
  }

  // Implementation Notes section
  if (notesLines.length > 0) {
    sections.push(['## Implementation Notes', '', notesLines.join('\n')].join('\n'));
  }

  // Build title
  const title = prNumber
    ? `[Follow-up] Unmet criteria from PR #${prNumber}`
    : '[Follow-up] Verifier failure - unmet acceptance criteria';

  return {
    title,
    body: sections.join('\n\n'),
    findings,
    unmetCriteria: uncheckedAcceptance,
    newTasks,
  };
}

/**
 * Generate a simple follow-up issue when detailed parsing isn't needed.
 * Used as a fallback when the source PR/issues don't have parseable sections.
 *
 * @param {Object} options
 * @param {string} options.verifierOutput - Raw verifier output
 * @param {number} [options.prNumber] - PR number
 * @param {string} [options.prUrl] - PR URL
 * @param {number[]} [options.issueNumbers] - Linked issue numbers
 * @param {string} [options.runUrl] - Verifier workflow run URL
 * @returns {Object} { title: string, body: string }
 */
function formatSimpleFollowUpIssue({
  verifierOutput,
  prNumber,
  prUrl,
  issueNumbers = [],
  runUrl,
}) {
  const findings = parseVerifierFindings(verifierOutput);

  const lines = [];

  // Source section
  lines.push(formatSourceSection({
    prNumber,
    prUrl,
    issueNumbers,
    verdict: findings.verdict,
    runUrl,
  }));

  lines.push('');
  lines.push('## Verifier Output');
  lines.push('');
  lines.push('```');
  lines.push(verifierOutput.trim());
  lines.push('```');

  lines.push('');
  lines.push('## Tasks');
  lines.push('');
  lines.push('- [ ] Review verifier output above');
  lines.push('- [ ] Address identified gaps');
  lines.push('- [ ] Re-run verifier after fixes');

  lines.push('');
  lines.push('## Acceptance Criteria');
  lines.push('');
  lines.push('- [ ] Verifier passes on the follow-up PR');

  const title = prNumber
    ? `Verifier failure for PR #${prNumber}`
    : 'Verifier failure on merged commit';

  return {
    title,
    body: lines.join('\n'),
    findings,
  };
}

module.exports = {
  formatFollowUpIssue,
  formatSimpleFollowUpIssue,
  formatSourceSection,
  parseVerifierFindings,
  extractUncheckedItems,
  extractCheckedItems,
  buildChecklist,
};
