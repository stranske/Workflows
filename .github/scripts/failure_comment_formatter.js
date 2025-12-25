'use strict';

const COMMENT_MARKER = '<!-- codex-failure-notification -->';

/**
 * Format a failure comment for a PR
 * @param {Object} params - Comment parameters
 * @param {string} params.mode - Codex mode (keepalive/autofix/verifier)
 * @param {string} params.exitCode - Exit code from Codex
 * @param {string} params.errorCategory - Error category (transient/auth/resource/logic/unknown)
 * @param {string} params.errorType - Error type (codex/infrastructure/auth/unknown)
 * @param {string} params.recovery - Recovery guidance
 * @param {string} params.summary - Output summary (truncated)
 * @param {string} params.runUrl - URL to the workflow run
 * @returns {string} Formatted comment body
 */
function formatFailureComment({
  mode = 'unknown',
  exitCode = 'unknown',
  errorCategory = 'unknown',
  errorType = 'unknown',
  recovery = 'Check logs for details.',
  summary = 'No output captured',
  runUrl = '',
}) {
  const runLink = runUrl ? `[View logs](${runUrl})` : 'N/A';
  const truncatedSummary = summary.length > 500 ? summary.slice(0, 500) + '...' : summary;

  return `${COMMENT_MARKER}
## ⚠️ Codex ${mode} run failed

| Field | Value |
|-------|-------|
| Exit Code | \`${exitCode}\` |
| Error Category | \`${errorCategory}\` |
| Error Type | \`${errorType}\` |
| Run | ${runLink} |

### 🔧 Suggested Recovery

${recovery}

### 📝 What to do

1. Check the [workflow logs](${runUrl || '#'}) for detailed error output
2. If this is a configuration issue, update the relevant settings
3. If the error persists, consider adding the \`needs-human\` label for manual review
4. Re-run the workflow once the issue is resolved

<details>
<summary>Output summary</summary>

\`\`\`
${truncatedSummary}
\`\`\`

</details>`;
}

/**
 * Check if a comment body contains the failure marker
 * @param {string} body - Comment body to check
 * @returns {boolean} True if this is a failure notification comment
 */
function isFailureComment(body) {
  return typeof body === 'string' && body.includes(COMMENT_MARKER);
}

module.exports = {
  COMMENT_MARKER,
  formatFailureComment,
  isFailureComment,
};
