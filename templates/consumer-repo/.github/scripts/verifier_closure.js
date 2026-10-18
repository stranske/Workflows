'use strict';

const { createHash } = require('crypto');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

function sourceHash(markdown) {
  return createHash('sha256').update(markdown || '').digest('hex');
}

function closureDecision({ verdict, mergeSha, plan, result, ci, currentBody }) {
  const refuse = reason => ({ rule: null, reason });
  if (!/^[a-f0-9]{40}$/.test(mergeSha || '')) return refuse('invalid-merge-sha');
  if (!plan || plan.head_sha !== mergeSha || plan.source_hash !== sourceHash(currentBody)) {
    return refuse('stale-source-plan');
  }
  const exactCi = Array.isArray(ci) && ci.length > 0
    && ci.every(run => run.head_sha === mergeSha);
  const greenCi = exactCi && ci.every(run => run.conclusion === 'success' && !run.error_category);
  if (verdict === 'PASS') {
    if (!exactCi) return refuse('pass-without-ci');
    if (!greenCi) return refuse('pass-ci-not-successful');
    return { rule: 'verifier-pass', reason: 'verifier-pass' };
  }
  if (verdict !== 'UNVERIFIABLE_INPUT') return refuse(`verdict-${verdict}`);
  if (!plan || !result || plan.head_sha !== mergeSha || result.head_sha !== mergeSha
      || plan.issue_number !== result.issue_number || plan.repository !== result.repository
      || result.pr_number !== plan.pr_number
      || plan.source_hash !== sourceHash(currentBody) || result.source_hash !== plan.source_hash) {
    return refuse('missing-or-stale-gate');
  }
  // Empty, stale, partial or failed command sets do not establish gate PASS.
  const commands = plan.commands;
  if (!Array.isArray(commands) || !Array.isArray(result.results)
      || result.results.length !== commands.length) return refuse('incomplete-gate');
  const gateSource = commands.length ? 'acceptance-commands' : 'required-ci';
  if (!commands.length && (plan.gate_source !== gateSource || result.gate_source !== gateSource)) {
    return refuse('gate: no commands');
  }
  if (!commands.every((command, i) => result.results[i].command === command.command
      && result.results[i].criterion === command.criterion && result.results[i].exit_code === 0)) {
    return refuse('gate-command-failed-or-changed');
  }
  if (!greenCi) return refuse('gate-ci-missing-stale-or-not-successful');
  return { rule: 'unverifiable-input+gate+ci', reason: 'unverifiable-input+gate+ci', gate_source: gateSource };
}

function closingRule(input) {
  return closureDecision(input).rule;
}

async function closeVerifiedSources({ github, context, core, verdict, mergeSha, prNumber, plans, results, ci }) {
  github = await ensureRateLimitWrapped({ github });
  const { data: pr } = await github.rest.pulls.get({ ...context.repo, pull_number: prNumber });
  if (!pr.merged || pr.merge_commit_sha !== mergeSha) throw new Error('Merged target changed or unavailable');
  const closed = [];
  for (const plan of plans) {
    const report = (outcome, reason) => (core?.info || console.log)(
      `${context.repo.owner}/${context.repo.repo}#${plan.issue_number}: ${outcome} — ${reason}`);
    if (plan.repository !== `${context.repo.owner}/${context.repo.repo}` || plan.pr_number !== prNumber) {
      report('kept open', 'source-pr-mismatch');
      continue;
    }
    if (plan.plan_error) {
      report('kept open', 'closure-plan-unavailable');
      continue;
    }
    let issue;
    try {
      ({ data: issue } = await github.rest.issues.get({ ...context.repo, issue_number: plan.issue_number }));
    } catch {
      report('kept open', 'source-issue-unavailable');
      continue;
    }
    if (issue.pull_request || issue.state === 'closed') {
      report('unchanged', issue.pull_request ? 'linked-item-is-pr' : 'already-closed');
      continue;
    }
    const { rule, reason, gate_source: gateSource } = closureDecision({ verdict, mergeSha, plan,
      result: results.find(r => r.issue_number === plan.issue_number), ci, currentBody: issue.body });
    if (!rule) {
      report('kept open', reason);
      continue;
    }
    await github.rest.issues.createComment({ ...context.repo, issue_number: plan.issue_number,
      body: `Verification closure rule: **${rule}**. PR #${prNumber}, merge commit \`${mergeSha}\`, verdict **${verdict}**. `
        + (verdict === 'PASS' ? 'The verifier and every configured merge CI workflow passed.'
          : `Deterministic gate passed (gate_source=${gateSource}) on this merge commit and every configured CI workflow is green. The provider verdict remains UNVERIFIABLE_INPUT.`) });
    await github.rest.issues.update({ ...context.repo, issue_number: plan.issue_number, state: 'closed', state_reason: 'completed' });
    closed.push(plan.issue_number);
    report('closed', reason + (gateSource ? `; gate_source=${gateSource}` : ''));
  }
  return closed;
}

module.exports = { sourceHash, closingRule, closureDecision, closeVerifiedSources };
