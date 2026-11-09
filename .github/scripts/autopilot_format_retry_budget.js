'use strict';

// Retry budget for the auto-pilot format-pause wakeup (agents-auto-pilot.yml,
// job `format-pause-wakeup`, root workflow and consumer template).
//
// Before this module the wakeup cleared `agents:auto-pilot-pause` and
// re-dispatched `force_step: format` every ~30 minutes for as long as the issue
// stayed open: a dispatched run is always enabled, so nothing ever ended the
// cycle. stranske/Orchestrator#1257 cycled 7 times in 3.5 hours on 2026-11-08.
// Measured 2026-10-25..2026-11-08 across the 16 lane-fleet repos: retry #1
// recovered 1 of 2 paused issues; retries #2 and later recovered 0 of 5.
//
// Gate contract (latched-gate-check):
//  1. Decrement: the budget counts bot retry comments since the latest
//     CAP_MARKER comment. Writing CAP_MARKER (on exhaustion) resets it, so a
//     re-armed issue gets a fresh budget.
//  2. Drain while closed: an exhausted issue keeps the pause and gets a comment
//     carrying CAP_MARKER. CAP_MARKER contains `format-guard:`, which is what
//     opener-core (~/.codex/opener-core, blocked_reason) requires before it will
//     rewrite a paused issue; on a validating rewrite it removes the pause
//     itself. Removing the pause and re-applying `agents:auto-pilot` also works.
//  3. One window: MAX_FORMAT_RETRIES is defined once here and consumed by both
//     the decision and every rendered count.
//  4. Drained voice: `clear` / `skip` decisions print `blocking 0` and say the
//     pause is gone; see renderSummary and its tests.

// Every GitHub API call here goes through the `withRetry` the calling step
// builds with createTokenAwareRetry (github-api-with-retry.js); this module
// never constructs a client of its own.

const MAX_FORMAT_RETRIES = 2;
const PAUSE_LABEL = 'agents:auto-pilot-pause';
const AUTOPILOT_LABEL = 'agents:auto-pilot';
const RETRY_PHRASE = 'Auto-pilot format retry scheduled';
const RETRY_MARKER_PREFIX = '<!-- autopilot-format-retry:';
const CAP_MARKER = '<!-- format-guard:autopilot-retry-cap -->';
// Mirrors opener-core HOLD_LABELS: an issue carrying one is skipped by the
// opener-core rewrite, so its drain is that label's owner, not opener-core.
const OPENER_HOLD_LABELS = ['needs-human', 'agents:paused', 'intake:held', 'do-not-merge'];

function labelNames(labels) {
  return (labels || [])
    .map((label) => (typeof label === 'string' ? label : label?.name))
    .filter(Boolean);
}

function isBotComment(comment) {
  const login = String(comment?.user?.login || '');
  return comment?.user?.type === 'Bot' || /\[bot\]$/.test(login);
}

// Retries charged to the current arming: bot retry comments after the latest
// bot CAP_MARKER comment. Human comments never move the budget either way.
function countRetriesSinceCap(comments) {
  const ordered = [...(comments || [])].sort((a, b) =>
    String(a?.created_at || '').localeCompare(String(b?.created_at || '')));
  let used = 0;
  let capSeen = false;
  for (const comment of ordered) {
    if (!isBotComment(comment)) continue;
    const body = String(comment?.body || '');
    if (body.includes(CAP_MARKER)) {
      used = 0;
      capSeen = true;
      continue;
    }
    if (body.includes(RETRY_MARKER_PREFIX) || body.includes(RETRY_PHRASE)) used += 1;
  }
  return { used, capSeen };
}

// Pure decision. `linkedOpenPrs` is an array of PR numbers, or null when the
// lookup failed (unknown is not "no PR": it never stops a retry by itself, and
// the budget still bounds the loop).
function decideFormatWakeup({
  state,
  labels,
  comments,
  linkedOpenPrs = [],
  maxRetries = MAX_FORMAT_RETRIES,
} = {}) {
  const names = labelNames(labels);
  const { used } = countRetriesSinceCap(comments);
  const base = {
    used,
    max: maxRetries,
    linkedOpenPrs: Array.isArray(linkedOpenPrs) ? linkedOpenPrs : null,
    holdLabels: OPENER_HOLD_LABELS.filter((label) => names.includes(label)),
  };
  if (String(state || '').toLowerCase() === 'closed') {
    return { ...base, action: 'clear', reason: 'issue-closed' };
  }
  if (!names.includes(PAUSE_LABEL)) {
    return { ...base, action: 'skip', reason: 'pause-already-cleared' };
  }
  if (!names.includes(AUTOPILOT_LABEL)) {
    return { ...base, action: 'clear', reason: 'auto-pilot-disarmed' };
  }
  if (Array.isArray(linkedOpenPrs) && linkedOpenPrs.length > 0) {
    return { ...base, action: 'clear', reason: 'linked-open-pr' };
  }
  if (used >= maxRetries) {
    return { ...base, action: 'cap', reason: 'retry-budget-exhausted' };
  }
  return { ...base, action: 'retry', reason: 'retry-within-budget', attempt: used + 1 };
}

// One line with the blocking AND drainable quantity, for logs and comments.
function renderSummary(decision) {
  const budget = `format retry budget ${decision.used}/${decision.max}`;
  switch (decision.action) {
    case 'retry':
      return `${budget}; blocking 1 (pause), drainable 1: this wakeup clears the pause and runs format retry ${decision.attempt}/${decision.max} after the backoff`;
    case 'cap':
      if (decision.holdLabels.length > 0) {
        return `${budget} exhausted; blocking 1 (pause), drainable 0 by opener-core: held by ${decision.holdLabels.join(', ')}, which that label's owner clears`;
      }
      return `${budget} exhausted; blocking 1 (pause), drainable 1: opener-core rewrites this body and lifts the pause when it validates`;
    case 'clear':
      return `${budget}; blocking 0, drainable 0: fully drained, pause cleared (${decision.reason})`;
    case 'skip':
      return `${budget}; blocking 0, drainable 0: fully drained, pause already cleared`;
    default:
      throw new Error(`unknown format wakeup action: ${decision.action}`);
  }
}

function renderComment(decision) {
  const summary = renderSummary(decision);
  if (decision.action === 'retry') {
    return [
      `${RETRY_MARKER_PREFIX}${decision.attempt}/${decision.max} -->`,
      `🤖 **${RETRY_PHRASE}** (${decision.attempt} of ${decision.max}).`,
      '',
      'Cleared `agents:auto-pilot-pause` after the bounded backoff and re-dispatched the format step.',
      '',
      `Counts: ${summary}.`,
    ].join('\n');
  }
  if (decision.action === 'cap') {
    return [
      CAP_MARKER,
      `🤖 **Auto-pilot format retries stopped** after ${decision.used} automatic retries (budget ${decision.max} per arming); the formatter still cannot produce a body that passes the issue-format contract.`,
      '',
      '`agents:auto-pilot-pause` stays on so auto-pilot does not run on a body that does not validate. No further timed retries will run for this arming.',
      '',
      'What clears it (no human step required): the opener lane (opener-core) rewrites paused issues that carry this format-guard marker and removes the pause once the rewritten body validates. Removing `agents:auto-pilot-pause` and re-applying `agents:auto-pilot` also starts a fresh retry budget.',
      '',
      `Counts: ${summary}.`,
    ].join('\n');
  }
  if (decision.action === 'clear') {
    const why = {
      'issue-closed': 'the issue is closed',
      'auto-pilot-disarmed': '`agents:auto-pilot` is no longer on the issue, so auto-pilot will not run on it',
      'linked-open-pr': `open pull request(s) ${(decision.linkedOpenPrs || []).map((n) => `#${n}`).join(', ')} already work this issue`,
    }[decision.reason] || decision.reason;
    return [
      '🤖 **Auto-pilot format retry not scheduled.**',
      '',
      `Cleared \`agents:auto-pilot-pause\` without re-dispatching the format step because ${why}.`,
      '',
      `Counts: ${summary}.`,
    ].join('\n');
  }
  return '';
}

async function readLinkedOpenPrs({ withRetry, owner, repo, issueNumber, core }) {
  const query = `query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
      issue(number: $number) {
        closedByPullRequestsReferences(first: 20, includeClosedPrs: false) {
          nodes { number state }
        }
      }
    }
  }`;
  try {
    const data = await withRetry((client) => client.graphql(query, { owner, repo, number: issueNumber }));
    const nodes = data?.repository?.issue?.closedByPullRequestsReferences?.nodes || [];
    return nodes.filter((node) => node && node.state === 'OPEN').map((node) => node.number);
  } catch (error) {
    core?.warning?.(`Linked-PR lookup failed; treating as unknown: ${error?.message || error}`);
    return null;
  }
}

// Reads live state, decides, and applies a non-retry decision. On `retry` it
// only removes the pause, dispatches and comments when `dispatch` is true (the
// post-backoff phase); the pre-backoff phase returns the decision so the job
// can skip the 30-minute sleep whenever no retry will follow.
async function runFormatWakeup({ withRetry, core, owner, repo, issueNumber, dispatch, maxRetries }) {
  const { data: issue } = await withRetry((client) =>
    client.rest.issues.get({ owner, repo, issue_number: issueNumber }));
  const comments = await withRetry((client) =>
    client.paginate(client.rest.issues.listComments, { owner, repo, issue_number: issueNumber, per_page: 100 }));
  const names = labelNames(issue.labels);
  const needsLinkLookup = String(issue.state).toLowerCase() !== 'closed'
    && names.includes(PAUSE_LABEL) && names.includes(AUTOPILOT_LABEL);
  const linkedOpenPrs = needsLinkLookup
    ? await readLinkedOpenPrs({ withRetry, owner, repo, issueNumber, core })
    : [];
  const decision = decideFormatWakeup({
    state: issue.state, labels: issue.labels, comments, linkedOpenPrs, maxRetries,
  });
  core?.info?.(`Format wakeup decision for #${issueNumber}: ${decision.action} (${decision.reason}); ${renderSummary(decision)}`);

  const removePause = async () => {
    try {
      await withRetry((client) => client.rest.issues.removeLabel({
        owner, repo, issue_number: issueNumber, name: PAUSE_LABEL,
      }));
    } catch (error) {
      if (error?.status !== 404) throw error;
    }
  };
  const comment = (body) => withRetry((client) => client.rest.issues.createComment({
    owner, repo, issue_number: issueNumber, body,
  }));

  if (decision.action === 'skip') return decision;
  if (decision.action === 'clear') {
    await removePause();
    if (decision.reason !== 'issue-closed') await comment(renderComment(decision));
    return decision;
  }
  if (decision.action === 'cap') {
    await comment(renderComment(decision));
    return decision;
  }
  if (!dispatch) return decision;

  await removePause();
  const { data: repoInfo } = await withRetry((client) => client.rest.repos.get({ owner, repo }));
  await withRetry((client) => client.rest.actions.createWorkflowDispatch({
    owner,
    repo,
    workflow_id: 'agents-auto-pilot.yml',
    ref: repoInfo.default_branch || 'main',
    inputs: { issue_number: String(issueNumber), force_step: 'format' },
  }));
  await comment(renderComment(decision));
  return decision;
}

module.exports = {
  MAX_FORMAT_RETRIES,
  CAP_MARKER,
  RETRY_PHRASE,
  RETRY_MARKER_PREFIX,
  OPENER_HOLD_LABELS,
  countRetriesSinceCap,
  decideFormatWakeup,
  renderSummary,
  renderComment,
  runFormatWakeup,
};
