'use strict';

// Use the workflow's source resolver rather than duplicating its precedence rules.
const { extractIssueNumberFromPull } = require('../.github/scripts/source_context.js');

function validateReceipt({ pull, comment, repo, number, runId }) {
  const issue = extractIssueNumberFromPull(pull);
  if (!Number.isSafeInteger(issue) || issue <= 0) {
    throw new Error('Target PR has no unambiguous source issue');
  }
  const issueUrl = `https://api.github.com/repos/${repo}/issues/${issue}`;
  const receiptUrl = `https://github.com/${repo}/issues/${issue}#issuecomment-${comment.id}`;
  if (
    comment.user?.login !== 'github-actions[bot]' ||
    comment.user?.type !== 'Bot' ||
    comment.issue_url?.toLowerCase() !== issueUrl.toLowerCase() ||
    comment.html_url?.toLowerCase() !== receiptUrl.toLowerCase()
  ) {
    throw new Error('Receipt is not a workflow comment on the resolved source issue');
  }
  const lines = comment.body?.split('\n');
  const header = [
    `<!-- cursor-target-closed:${number}:${runId} -->`,
    'skipped: target PR merged/closed mid-run',
    '',
    `Target PR: #${number}`,
    `Run: https://github.com/${repo}/actions/runs/${runId}`,
    '',
    'Unpushed commits created during this run:',
  ];
  if (!lines || !header.every((line, index) => lines[index] === line)) {
    throw new Error('Receipt does not identify this target and run');
  }
  const commits = lines.slice(header.length);
  const noCommits = commits.length === 1 && commits[0] === '- None.';
  if (!noCommits && (!commits.length || commits.some(line => !/^- `[a-f0-9]{40}`$/.test(line)))) {
    throw new Error('Receipt has missing or malformed commit evidence');
  }
  const shas = noCommits ? [] : commits.map(line => line.slice(3, -1));
  if (new Set(shas).size !== shas.length) {
    throw new Error('Receipt repeats a commit');
  }
  return {
    source_issue: `${repo}#${issue}`,
    receipt_url: comment.html_url,
    reported_unpushed_commit_shas: shas,
  };
}

module.exports = { validateReceipt };

if (require.main === module) {
  try {
    const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
    process.stdout.write(JSON.stringify(validateReceipt(input)));
  } catch {
    // Never echo API responses or subprocess diagnostics into evidence logs.
    process.stderr.write('Cursor source-issue receipt is unavailable or invalid\n');
    process.exitCode = 1;
  }
}
