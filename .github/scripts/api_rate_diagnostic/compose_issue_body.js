'use strict';

function formatIssueTimestamp(date = new Date()) {
  return date.toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC');
}

function runUrlFromEnv(env = process.env) {
  return `${env.GITHUB_SERVER_URL}/${env.GITHUB_REPOSITORY}/actions/runs/${env.GITHUB_RUN_ID}`;
}

function composeHighUsageIssueBody({ now = formatIssueTimestamp(), runUrl } = {}) {
  return [
    '## API Rate Limit Alert',
    '',
    'Health 75 API Rate Diagnostic detected high API utilization (>85%).',
    '',
    `**Detected at:** ${now}`,
    `**Workflow Run:** ${runUrl}`,
    '',
    '### Recommended Actions',
    '',
    '1. Review recent workflow activity for unusual patterns',
    '2. Check for workflows making excessive API calls',
    '3. Consider implementing caching or reducing polling frequency',
    '4. Verify load is properly distributed across authentication methods',
    '',
    'This issue was automatically created and will be referenced if high usage persists.',
  ].join('\n');
}

function composeHighUsageUpdateBody({ now = formatIssueTimestamp(), runUrl } = {}) {
  return [
    '🔄 **Update:** High API utilization continues.',
    '',
    `**Checked at:** ${now}`,
    `**Workflow Run:** ${runUrl}`,
  ].join('\n');
}

function composeRepeatedFailureIssueBody({ now = formatIssueTimestamp(), runUrl } = {}) {
  return [
    '## Repeated workflow failures detected',
    '',
    'The Health 75 API Rate Diagnostic workflow has failed in two consecutive runs.',
    '',
    `- **Current run:** ${runUrl}`,
    `- **Detected at:** ${now}`,
    '',
    '### Next steps',
    '1. Review the run logs to identify the failing step(s).',
    '2. Validate that API credentials and required secrets are configured.',
    '3. Re-run the workflow after applying fixes.',
    '',
    'This issue was created automatically to ensure repeated failures are tracked.',
  ].join('\n');
}

function composeRepeatedFailureUpdateBody({ runUrl } = {}) {
  return ['Repeated failure detected again.', `Latest run: ${runUrl}`].join('\n');
}

module.exports = {
  composeHighUsageIssueBody,
  composeHighUsageUpdateBody,
  composeRepeatedFailureIssueBody,
  composeRepeatedFailureUpdateBody,
  formatIssueTimestamp,
  runUrlFromEnv,
};
