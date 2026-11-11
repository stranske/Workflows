'use strict';

const HEAD_SHA = /^[0-9a-f]{40}$/;

// Keep head observation separate from best-effort Gate/label telemetry. A
// fallback SHA is useful for reporting, but cannot authorize a completion.
async function observeAutofixHead({
  github, context, core, withRetry, paginateWithRetry,
  prNumber, headShaBefore, gateConclusionBefore,
}) {
  const metrics = {
    head_observed: false,
    // An unavailable PR read is unmeasured, never proof of no work.
    head_sha_after: '',
    fix_applied: false,
    gate_result_after: gateConclusionBefore || 'unknown',
  };
  core.setOutput('head_observed', 'false');
  if (!prNumber) return metrics;

  const { owner, repo } = context.repo;
  let pr;
  try {
    ({ data: pr } = await withRetry((client) => client.rest.pulls.get({
      owner, repo, pull_number: prNumber,
    })));
    if (typeof pr?.head?.sha !== 'string' || !HEAD_SHA.test(pr.head.sha)) {
      throw new Error('PR response has no valid head SHA');
    }
  } catch {
    core.warning('Failed to observe PR head; retain autofix reservation.');
    return metrics;
  }

  metrics.head_sha_after = pr.head.sha;
  metrics.head_observed = true;
  metrics.fix_applied = Boolean(headShaBefore && headShaBefore !== pr.head.sha);
  core.setOutput('head_observed', 'true');

  // Label cleanup and Gate status are telemetry, not head-observation evidence.
  if (metrics.fix_applied && pr.labels?.some((label) => label.name === 'autofix:escalated')) {
    try {
      await withRetry((client) => client.rest.issues.removeLabel({
        owner, repo, issue_number: prNumber, name: 'autofix:escalated',
      }));
      core.info('Removed autofix:escalated label - allows re-escalation if Gate fails again');
    } catch {
      core.warning('Failed to remove autofix:escalated label.');
    }
  }

  try {
    const runs = await paginateWithRetry(github.rest.actions.listWorkflowRuns, {
      owner, repo, workflow_id: 'pr-00-gate.yml', head_sha: pr.head.sha, per_page: 20,
    });
    metrics.gate_result_after = runs[0]
      ? runs[0].conclusion || runs[0].status || 'unknown'
      : 'not-found';
  } catch {
    core.warning('Failed to resolve Gate status after observing PR head.');
  }
  return metrics;
}

// The completion shell must validate before calling runner_lib record-completion.
// Reject legacy fallback-only metrics too: absence of evidence is not no work.
function formatAutofixCompletion(metrics, reservedHead) {
  if (!metrics || metrics.head_observed !== true ||
      !HEAD_SHA.test(reservedHead || '') ||
      metrics.head_sha_before !== reservedHead ||
      typeof metrics.head_sha_after !== 'string' || !HEAD_SHA.test(metrics.head_sha_after) ||
      typeof metrics.fix_applied !== 'boolean' ||
      metrics.fix_applied !== (metrics.head_sha_after !== reservedHead) ||
      !['success', 'failure', 'cancelled'].includes(metrics.autofix_result)) {
    throw new Error('Autofix completion measurement is incomplete; retain reservation.');
  }
  return `${metrics.head_sha_after} ${metrics.fix_applied} ${metrics.autofix_result === 'success' ? 0 : 1}\n`;
}

module.exports = { observeAutofixHead, formatAutofixCompletion };

if (require.main === module) {
  try {
    process.stdout.write(formatAutofixCompletion(
      JSON.parse(process.env.METRICS_JSON), process.env.HEAD_SHA,
    ));
  } catch {
    process.stderr.write('Autofix completion measurement is incomplete; retain reservation.\n');
    process.exitCode = 1;
  }
}
