const {
  extractScopeTasksAcceptanceSections,
  analyzeSectionPresence,
} = require('./issue_scope_parser.js');

// Note: Scope is optional; only Tasks and Acceptance Criteria are required
const EXPECTED_SECTIONS = ['Tasks', 'Acceptance Criteria'];
const ALL_SECTIONS = ['Scope', 'Tasks', 'Acceptance Criteria'];

function buildIssueContext(issueBody) {
  const body = issueBody || '';
  const scopeBlockWithPlaceholders = extractScopeTasksAcceptanceSections(body, {
    includePlaceholders: true,
  });
  const scopeBlockStrict = extractScopeTasksAcceptanceSections(body, {
    includePlaceholders: false,
  });
  const presence = analyzeSectionPresence(body);
  const missingSections = Array.isArray(presence?.missing) ? presence.missing : [];
  const hasActionableContent = Boolean(presence?.hasActionableContent);
  const summaryContentBlock = (scopeBlockStrict || '').trim();
  
  // Show warning if any required (non-optional) sections are missing
  const summaryNeedsWarning = missingSections.length > 0;
  
  const missingDescription = missingSections.length
    ? `Problem detected: ${missingSections.join(', ')} ${missingSections.length === 1 ? 'is' : 'are'} missing or empty in the source issue.`
    : !hasActionableContent
      ? 'Problem detected: The parser could not find any Tasks or Acceptance Criteria in the source issue.'
      : '';
  const warningDetails = summaryNeedsWarning
    ? [
        'Automated Status Summary expects the following sections in the source issue:',
        ...EXPECTED_SECTIONS.map((section) => `- ${section}`),
        '',
        '(Scope/Why/Background is optional but recommended)',
        '',
        missingDescription,
        '',
        'Please edit the issue to add `## Tasks` and `## Acceptance Criteria`, then rerun the agent workflow so keepalive can parse your plan.',
      ]
    : [];
  const warningLines = summaryNeedsWarning ? ['#### ⚠️ Template Warning', '', ...warningDetails] : [];
  const summaryLines = ['<!-- auto-status-summary:start -->', '## Automated Status Summary'];
  
  // Include content if we have actionable content OR a non-empty strict block
  if (hasActionableContent || summaryContentBlock) {
    summaryLines.push(summaryContentBlock || scopeBlockWithPlaceholders);
  } else {
    summaryLines.push('#### ⚠️ Summary Unavailable', '', ...warningDetails);
  }
  summaryLines.push('<!-- auto-status-summary:end -->');

  return {
    scopeBlock: (scopeBlockWithPlaceholders || '').trim(),
    statusSummaryBlock: summaryLines.join('\n'),
    warningLines,
    warningDetails,
    summaryNeedsWarning,
    missingSections,
    summaryContentBlock,
    hasActionableContent,
  };
}

module.exports = {
  EXPECTED_SECTIONS,
  ALL_SECTIONS,
  buildIssueContext,
};
