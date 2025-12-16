'use strict';

function normalise(value) {
  if (!value) {
    return 'unknown';
  }
  return value.toLowerCase();
}

async function appendDispatchSummary({ core, context, env = process.env }) {
  const dispatchResult = normalise((env.DISPATCH_RESULT || '').trim());
  const workerResult = normalise((env.WORKER_RESULT || '').trim());
  const workerAllowed = normalise((env.WORKER_ALLOWED || '').trim());
  const dispatchedIssue = (env.DISPATCH_ISSUE || '').trim();
  const dispatchReason = (env.DISPATCH_REASON || '').trim() || 'unknown';
  const workerDryRun = normalise((env.WORKER_DRY_RUN || '').trim());
  const prNumber = (env.WORKER_PR_NUMBER || '').trim();
  const workerBranch = (env.WORKER_BRANCH || '').trim();
  const keepaliveActionRaw = (env.KEEPALIVE_ACTION || '').trim();
  const keepaliveAction = normalise(keepaliveActionRaw);
  const keepaliveReasonRaw = (env.KEEPALIVE_REASON || '').trim();

  let success = 0;
  let skipped = 0;
  let failures = 0;

  if (dispatchResult === 'success' && dispatchedIssue) {
    if (workerResult === 'success') {
      success += 1;
    } else if (['failure', 'cancelled'].includes(workerResult)) {
      failures += 1;
    } else if (workerResult === 'skipped' || workerAllowed === 'false') {
      skipped += 1;
    } else {
      skipped += 1;
    }
  } else if (dispatchResult === 'success') {
    skipped += 1;
  } else if (dispatchResult === 'skipped' || dispatchResult === 'cancelled') {
    skipped += 1;
  } else if (dispatchResult === 'failure') {
    failures += 1;
  } else {
    skipped += 1;
  }

  const summary = core.summary;
  summary
    .addRaw(`Dispatch succeeded for ${success} PRs; ${skipped} skipped; ${failures} failures.`)
    .addEOL();

  const rows = [
    [
      { data: 'PR', header: true },
      { data: 'Issue', header: true },
      { data: 'Reason', header: true },
      { data: 'Worker Result', header: true },
      { data: 'Branch', header: true }
    ]
  ];

  const { owner, repo } = context.repo;

  const prLink = () => {
    if (!prNumber) {
      return workerDryRun === 'true' || workerAllowed === 'false' ? '— (preview)' : '—';
    }
    const url = `https://github.com/${owner}/${repo}/pull/${prNumber}`;
    return `<a href="${url}">#${prNumber}</a>`;
  };

  const issueLink = () => {
    if (!dispatchedIssue) {
      return '—';
    }
    const url = `https://github.com/${owner}/${repo}/issues/${dispatchedIssue}`;
    return `<a href="${url}">#${dispatchedIssue}</a>`;
  };

  const branchInfo = workerBranch ? `\`${workerBranch}\`` : '—';
  let workerLabel = workerAllowed === 'false' ? 'blocked' : workerResult;
  if (keepaliveAction === 'skip') {
    workerLabel = 'keepalive-skip';
  } else if (keepaliveAction && keepaliveAction !== 'execute' && keepaliveAction !== 'unknown' && workerLabel === 'success') {
    workerLabel = `keepalive-${keepaliveAction}`;
  }

  let reasonDetail = dispatchReason || 'unknown';
  if (keepaliveActionRaw || keepaliveReasonRaw) {
    const keepaliveDetail = keepaliveReasonRaw
      ? `${keepaliveActionRaw || 'keepalive'}:${keepaliveReasonRaw}`
      : (keepaliveActionRaw || 'keepalive');
    reasonDetail = dispatchReason && dispatchReason !== 'unknown'
      ? `${dispatchReason} / ${keepaliveDetail}`
      : keepaliveDetail;
  }

  rows.push([
    prLink(),
    issueLink(),
    reasonDetail,
    workerDryRun === 'true' ? 'preview' : workerLabel,
    branchInfo
  ]);

  summary.addTable(rows);
  await summary.write();

  return {
    counts: { success, skipped, failures },
    row: rows[1]
  };
}

module.exports = { appendDispatchSummary };
