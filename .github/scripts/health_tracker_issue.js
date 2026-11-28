'use strict';

// One tracker issue for repository health failures (cohesion review A5a).
//
// Health 40's self-check owns the issue titled TRACKER_TITLE. Before this
// module, Health 41 failed eight Mondays in a row (2026-09-21..11-09) and
// nothing was filed, because Health 41 had no failure path at all. Health 41
// now calls recordTrackerFailure() from a failure-only job so each failed run
// produces exactly one update on the same issue: a comment on an open issue,
// or a reopen plus comment on a closed one, or a new issue when none exists.

const TRACKER_TITLE = '[health] repository self-check failed';
const TRACKER_LABEL = 'health:repo';

const passthrough = (fn) => fn();

function labelNames(issue) {
  return (issue?.labels || []).map((label) => (typeof label === 'string' ? label : label?.name));
}

function pickTracker(issues = [], title = TRACKER_TITLE) {
  const matches = issues.filter((issue) => issue && issue.title === title && !issue.pull_request);
  const open = matches.find((issue) => issue.state === 'open');
  if (open) return open;
  return [...matches].sort((a, b) => Number(b.number) - Number(a.number))[0] || null;
}

function failureComment({ source, detail, runUrl }) {
  const lines = [`### ${source} failed`, ''];
  lines.push(detail ? String(detail).trim() : 'No failure detail was captured; open the run.');
  if (runUrl) lines.push('', `Run: ${runUrl}`);
  lines.push(
    '',
    '_Routed here so that a failing health check always has an open issue. ' +
      'The issue is closed by the self-check once its own checks pass; the next ' +
      'failure of either workflow reopens it._'
  );
  return lines.join('\n');
}

async function recordTrackerFailure({
  github,
  owner,
  repo,
  source,
  detail = '',
  runUrl = '',
  withRetry = passthrough,
  title = TRACKER_TITLE,
  label = TRACKER_LABEL,
}) {
  if (!source) throw new Error('source is required');
  // One page, filtered by the tracker label: the issue always carries it.
  const listed = await withRetry(() =>
    github.rest.issues.listForRepo({ owner, repo, labels: label, state: 'all', per_page: 100 })
  );
  const target = pickTracker(listed?.data || [], title);
  const body = failureComment({ source, detail, runUrl });

  if (!target) {
    const created = await withRetry(() =>
      github.rest.issues.create({ owner, repo, title, body, labels: [label] })
    );
    return { action: 'created', number: created?.data?.number ?? null };
  }

  let action = 'commented';
  if (target.state !== 'open') {
    const labels = new Set(labelNames(target).filter(Boolean));
    labels.add(label);
    await withRetry(() =>
      github.rest.issues.update({
        owner,
        repo,
        issue_number: target.number,
        state: 'open',
        labels: [...labels],
      })
    );
    action = 'reopened';
  }
  await withRetry(() =>
    github.rest.issues.createComment({ owner, repo, issue_number: target.number, body })
  );
  return { action, number: target.number };
}

module.exports = {
  TRACKER_LABEL,
  TRACKER_TITLE,
  failureComment,
  pickTracker,
  recordTrackerFailure,
};
