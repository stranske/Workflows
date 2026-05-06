const {
  extractScopeTasksAcceptanceSections,
  analyzeSectionPresence,
} = require('./issue_scope_parser.js');
const childProcess = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

// Note: Scope is optional; only Tasks and Acceptance Criteria are required
const EXPECTED_SECTIONS = ['Tasks', 'Acceptance Criteria'];
const ALL_SECTIONS = ['Scope', 'Tasks', 'Acceptance Criteria'];

function buildCappedIssuePayload(issueBody, options = {}) {
  const body = String(issueBody || '');
  if (!body.trim()) {
    return { formattedBody: body, truncated: false };
  }

  try {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'workflows-issue-context-'));
    const inputPath = path.join(tmpDir, 'issue.md');
    fs.writeFileSync(inputPath, body, 'utf8');
    const args = [
      'scripts/langchain/issue_pr_context.py',
      '--kind',
      'issue',
      '--input-file',
      inputPath,
      '--json',
      '--token-budget',
      String(options.tokenBudget || process.env.ISSUE_PR_CONTEXT_TOKEN_BUDGET || 4000),
      '--downstream-workflow',
      options.downstreamWorkflow || process.env.ISSUE_PR_CONTEXT_WORKFLOW || 'issue_context_utils',
    ];
    const output = childProcess.execFileSync('python3', args, { encoding: 'utf8' });
    const payload = JSON.parse(output);
    return {
      formattedBody: String(payload.formatted_body || body),
      truncated: Boolean(payload.truncated),
      estimatedTokens: payload.estimated_tokens,
      tokenBudget: payload.token_budget,
    };
  } catch (_error) {
    return { formattedBody: body, truncated: false };
  }
}

function buildIssueContext(issueBody, options = {}) {
  const cappedPayload = buildCappedIssuePayload(issueBody, options);
  const body = cappedPayload.formattedBody || '';
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
    formattedBody: body,
    contextTruncated: cappedPayload.truncated,
    estimatedTokens: cappedPayload.estimatedTokens,
    tokenBudget: cappedPayload.tokenBudget,
  };
}

module.exports = {
  EXPECTED_SECTIONS,
  ALL_SECTIONS,
  buildCappedIssuePayload,
  buildIssueContext,
};
