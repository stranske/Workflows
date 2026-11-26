'use strict';

function scopedRefreshRepositories(decision, expectedCanaries) {
  const requested = decision.repositories;
  if (!requested?.length) return [];
  const deliveryRepos = (decision.registeredRepositories || []).filter((repo) =>
    !expectedCanaries.includes(repo) && repo.toLowerCase() !== 'stranske/collab-admin');
  const unique = [...new Set(requested)].sort();
  if (unique.some((repo) => !deliveryRepos.includes(repo))) {
    throw new Error('delivery_refresh_requires_registered_delivery_repositories');
  }
  return unique.length < deliveryRepos.length ? unique : [];
}

async function dispatchDeliveryRefresh({ decision, expectedCanaries, withRetry, context, core,
  now, cleanupBranches, readCanaryRefreshState, listPromotionRuns, fullPromotionMatches,
  activeStates, debounceMs }) {
  const repos = scopedRefreshRepositories(decision, expectedCanaries);
  const held = new Set(decision.repositories || []).size;
  const state = await readCanaryRefreshState({ withRetry, context, expectedCanaries, now, writerOnly: true });
  if (['writer-active', ...activeStates].includes(state.state)) {
    core.notice(`Delivery refresh held ${held}; drain after Maint 68 writer ${state.run_id} finishes`);
    return { dispatched: false };
  }
  const rows = Array.isArray(decision.evidence) ? decision.evidence : decision.evidence.results;
  const binding = rows[0];
  const location = { owner: context.repo.owner, repo: context.repo.repo };
  const branch = context.payload.repository?.default_branch || 'main';
  const { data: source } = await withRetry((client) => client.rest.repos.getCommit({
    ...location, ref: binding.source_commit,
  }));
  const created = source.commit?.committer?.date;
  if (!Number.isFinite(Date.parse(created))) throw new Error('promotion_source_date_unknown');
  const runs = await listPromotionRuns({ withRetry, context, created });
  // The unfiltered history can see a just-queued run omitted from the status scans.
  const active = runs.find((run) => activeStates.includes(run.status)
    && /^Maint 68 (canary|promote) /.test(run.display_title || ''));
  if (active) {
    core.notice(`Delivery refresh held ${held}; drain after Maint 68 writer ${active.id} finishes`);
    return { dispatched: false };
  }
  if (repos.length === 0) {
    const recent = runs.find((run) => fullPromotionMatches(run, binding, branch)
      && now - Date.parse(run.updated_at || run.created_at) < debounceMs);
    if (recent) {
      const remaining = debounceMs - (now - Date.parse(recent.updated_at || recent.created_at));
      core.notice(`Delivery refresh held ${held}; exact-plan promote ${recent.id}; debounce_remaining_ms=${remaining}; drain when debounce ends`);
      return { dispatched: false };
    }
  }
  const inputs = { phase: 'promote', canary_evidence_json: JSON.stringify(decision.evidence),
    delivery_scope: 'auto', dry_run: 'false', force: 'false', cleanup_branches: String(cleanupBranches) };
  if (repos.length) {
    inputs.repos = repos.join(',');
    if (decision.priorNoChangeEvidence) {
      inputs.prior_campaign_no_change_evidence_json = decision.priorNoChangeEvidence;
    }
  }
  if (Buffer.byteLength(JSON.stringify(inputs), 'utf8') > 60000) throw new Error('promotion_inputs_too_large');
  await withRetry((client) => client.rest.actions.createWorkflowDispatch({
    ...location,
    workflow_id: 'maint-68-sync-consumer-repos.yml',
    ref: branch,
    inputs,
  }));
  core.notice(repos.length
    ? `Delivery refresh dispatched for ${repos.length} repositories: ${repos.join(', ')}; awaiting Maint 68`
    : `Replayed exact-plan promotion ${decision.plan_id}`);
  return { dispatched: true };
}

module.exports = { dispatchDeliveryRefresh };
