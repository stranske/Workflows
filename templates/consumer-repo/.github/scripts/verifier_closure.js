'use strict';

const { createHash } = require('crypto');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

function sourceHash(markdown) {
  return createHash('sha256').update(markdown || '').digest('hex');
}

function closingRule({ verdict, mergeSha, plan, result, ci, currentBody }) {
  if (!/^[a-f0-9]{40}$/.test(mergeSha || '')) return null;
  if (!plan || plan.head_sha !== mergeSha || plan.source_hash !== sourceHash(currentBody)) return null;
  if (verdict === 'PASS') {
    return Array.isArray(ci) && ci.some(run => run.head_sha === mergeSha && (run.conclusion !== 'success' && !(run.conclusion === 'skipped' && run.required === false)))
      ? null : 'verifier-pass';
  }
  if (verdict !== 'UNVERIFIABLE_INPUT') return null;
  if (!plan || !result || plan.head_sha !== mergeSha || result.head_sha !== mergeSha
      || plan.issue_number !== result.issue_number || plan.repository !== result.repository
      || plan.source_hash !== sourceHash(currentBody) || result.source_hash !== plan.source_hash) return null;
  // Empty, stale, partial or failed command sets do not establish gate PASS.
  const commands = plan.commands;
  if (!Array.isArray(commands) || !commands.length || !Array.isArray(result.results)
      || result.results.length !== commands.length) return null;
  if (!commands.every((command, i) => result.results[i].command === command.command
      && result.results[i].criterion === command.criterion && result.results[i].exit_code === 0)) return null;
  if (!Array.isArray(ci) || !ci.length || !ci.every(run => run.head_sha === mergeSha
      && run.conclusion === 'success' && !run.error_category)) return null;
  return 'unverifiable-input+gate+ci';
}

async function closeVerifiedSources({ github, context, verdict, mergeSha, prNumber, plans, results, ci }) {
  github = await ensureRateLimitWrapped({ github });
  const { data: pr } = await github.rest.pulls.get({ ...context.repo, pull_number: prNumber });
  if (!pr.merged || pr.merge_commit_sha !== mergeSha) throw new Error('Merged target changed or unavailable');
  const closed = [];
  for (const plan of plans) {
    if (plan.repository !== `${context.repo.owner}/${context.repo.repo}` || plan.pr_number !== prNumber) continue;
    const { data: issue } = await github.rest.issues.get({ ...context.repo, issue_number: plan.issue_number });
    if (issue.pull_request || issue.state === 'closed') continue;
    const rule = closingRule({ verdict, mergeSha, plan, result: results.find(r => r.issue_number === plan.issue_number), ci, currentBody: issue.body });
    if (!rule) continue;
    await github.rest.issues.createComment({ ...context.repo, issue_number: plan.issue_number,
      body: `Verification closure rule: **${rule}**. PR #${prNumber}, merge commit \`${mergeSha}\`, verdict **${verdict}**. `
        + (verdict === 'PASS' ? 'The verifier passed.' : 'The named deterministic acceptance gates passed on this merge commit and every configured CI workflow is green. The provider verdict remains UNVERIFIABLE_INPUT.') });
    await github.rest.issues.update({ ...context.repo, issue_number: plan.issue_number, state: 'closed', state_reason: 'completed' });
    closed.push(plan.issue_number);
  }
  return closed;
}

module.exports = { sourceHash, closingRule, closeVerifiedSources };
