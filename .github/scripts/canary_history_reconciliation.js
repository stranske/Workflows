'use strict';

const { createHash } = require('node:crypto');
const { parseDeliveryRecord } = require('./sync_pr_lease_contract');
const { isTrustedGeneratedDeliveryPr } = require('./sync_pr_merge_contract');
const ACTIVE = ['queued', 'in_progress', 'waiting', 'pending', 'requested'];
const BRANCH = 'sync/workflows-candidate';
const ACTORS = ['stranske', 'stranske-automation-bot', 'github-actions[bot]'];
// API-derived admission observations never survive JSON transport or caching.
// The historical receipt and its UNKNOWN grade are left untouched.
const coverage = new WeakMap();
const sha = value => /^[a-f0-9]{40}$/.test(value || '');
const need = (value, reason) => { if (!value) throw new Error(reason); };
const version = run => JSON.stringify([run.id, run.run_attempt, run.head_sha,
  run.updated_at, run.status, run.conclusion]);
const key = (request, digest) => JSON.stringify([request?.plan_id, request?.plan_scope,
  request?.scope_base_sha, request?.source_commit, digest]);
const openIdentity = rows => JSON.stringify(rows.map(pr => [pr.number, pr.head?.sha, pr.body]));

function coveredByCurrentBaseline(run, request, digest) {
  const observation = coverage.get(run);
  return Boolean(observation && observation.version === version(run)
    && observation.request === key(request, digest));
}

function currentBaselineOwnerConflict(runs, request, digest) {
  for (const run of runs) {
    if (coveredByCurrentBaseline(run, request, digest)) {
      const conflict = coverage.get(run).owner_conflicts[0];
      if (conflict) return conflict;
    }
  }
  return null;
}

async function reconcileLegacyCanaryHistory({ withRetry, context, runs, candidates,
  refreshPlan, payload, verifyPlan, ignoreRunId, ignoreRunAttempt }) {
  const unknown = runs.filter(run => run.refresh_unknown);
  for (const run of unknown) coverage.delete(run);
  const result = { schema: 'workflows.canary-history-reconciliation/v1',
    historical_unknowns: unknown.length, covered: [], blocking: [], baselines: [], owner_conflicts: [],
    blocking_count: unknown.length, drainable: 0 };
  if (!unknown.length) return result;
  const read = async (group, method, args) =>
    (await withRetry(client => client.rest[group][method](args))).data;
  const location = context.repo;
  const repository = `${location.owner}/${location.repo}`;
  try {
    need(refreshPlan?.plan_scope === 'source-delta'
      && refreshPlan.plan?.plan_id === refreshPlan.plan_id
      && Array.isArray(refreshPlan.plan.entries) && Array.isArray(refreshPlan.plan.removals)
      && !refreshPlan.plan.removals.length
      && payload?.digest && typeof verifyPlan === 'function', 'scoped_payload_required');
    need(Array.isArray(candidates) && candidates.length > 0
      && candidates.every(repo => /^[\w.-]+\/[\w.-]+$/.test(repo)
        && repo.toLowerCase() !== 'stranske/collab-admin'), 'baseline_candidates_invalid');
    const current = [];
    for (const run of unknown) {
      // A newer attempt, active run or unreadable identity cannot be covered
      // by an older baseline, even if its ID was once observed as cancelled.
      const actual = await read('actions', 'getWorkflowRun', { ...location, run_id: run.id });
      need(version(actual) === version(run) && actual.status === 'completed'
        && actual.path === '.github/workflows/maint-68-sync-consumer-repos.yml'
        && actual.head_branch === (context.payload.repository?.default_branch || 'main')
        && ['workflow_dispatch', 'schedule'].includes(actual.event)
        && actual.repository?.full_name === repository
        && actual.head_repository?.id === actual.repository.id
        && Number.isFinite(Date.parse(actual.updated_at)), 'historical_attempt_changed_or_unreadable');
      current.push(actual);
    }
    const latestUnknown = Math.max(...current.map(run => Date.parse(run.updated_at)));
    const observations = [];
    let baselinePlan;
    for (const repositoryName of candidates) {
      const [owner, repo] = repositoryName.split('/');
      const target = { owner, repo };
      const open = await read('pulls', 'list', { ...target, state: 'open',
        head: `${owner}:${BRANCH}`, per_page: 100, page: 1 });
      need(Array.isArray(open) && open.length < 100, 'open_candidate_inventory_incomplete');
      for (const current of open) {
        let owned = false;
        let currentBinding;
        try {
          const markers = [...String(current.body || '').matchAll(/<!-- workflows-consumer-sync:v1 ([\s\S]*?) -->/g)];
          const metadata = markers.length === 1 && JSON.parse(markers[0][1]);
          const record = parseDeliveryRecord(current.body);
          need(isTrustedGeneratedDeliveryPr(current, ACTORS)
            && current.head?.repo?.full_name === repositoryName
            && metadata?.consumer_repo === repositoryName, 'open_candidate_binding_invalid');
          const binding = await verifyPlan({ ...target, pr: current, record, metadata, withRetry });
          currentBinding = binding;
          owned = key(binding, '') === key(refreshPlan, '');
        } catch (_) { /* Unknown current ownership blocks admission, not the historical grade. */ }
        if (!owned) result.owner_conflicts.push({ repository: repositoryName, pr: current.number,
          head_sha: current.head?.sha, ...(currentBinding || {}), reason: 'another_current_delivery' });
      }
      const closed = [];
      for (let page = 1; page <= 10; page++) {
        const rows = await read('pulls', 'list', { ...target, state: 'closed',
          head: `${owner}:${BRANCH}`, per_page: 100, page });
        need(Array.isArray(rows), 'closed_candidate_inventory_unreadable');
        closed.push(...rows);
        if (rows.length < 100) break;
        need(page < 10, 'closed_candidate_inventory_bound');
      }
      need(new Set(closed.map(pr => pr.number)).size === closed.length, 'closed_candidate_inventory_changed');
      const latest = closed.filter(pr => pr.merged_at)
        .sort((a, b) => Date.parse(b.merged_at) - Date.parse(a.merged_at))[0];
      need(latest?.number, 'merged_native_baseline_missing');
      const pr = await read('pulls', 'get', { ...target, pull_number: latest.number });
      need(pr.state === 'closed' && pr.merged === true && pr.draft === false
        && pr.head?.ref === BRANCH && pr.head.repo?.full_name === repositoryName
        && pr.base?.repo?.full_name === repositoryName
        && isTrustedGeneratedDeliveryPr(pr, ACTORS)
        && sha(pr.head.sha) && sha(pr.merge_commit_sha)
        && Date.parse(pr.merged_at) > latestUnknown, 'merged_native_baseline_invalid_or_older');
      const matches = [...String(pr.body || '').matchAll(/<!-- workflows-consumer-sync:v1 ([\s\S]*?) -->/g)];
      need(matches.length === 1
        && [...String(pr.body || '').matchAll(/<!-- sync-pr-delivery-record:v1 /g)].length === 1,
      'baseline_metadata_ambiguous');
      const metadata = JSON.parse(matches[0][1]);
      const record = parseDeliveryRecord(pr.body);
      need(metadata.consumer_repo === repositoryName && metadata.source_repository === repository
        && metadata.sync_phase === 'canary' && metadata.sync_branch === BRANCH
        && record?.repository === repositoryName && record.delivery_state === 'sealed'
        && record.sealed_head_sha === pr.head.sha, 'baseline_delivery_binding_invalid');
      const head = await read('repos', 'getCommit', { ...target, ref: pr.head.sha });
      const binding = await verifyPlan({ ...target, pr, record, metadata, nativeHead: head, withRetry });
      const tuple = key(binding, '');
      need(!baselinePlan || baselinePlan === tuple, 'mixed_native_baselines'); baselinePlan = tuple;
      const producer = runs.find(run => String(run.id) === String(metadata.run_id)
        && String(run.run_attempt) === String(metadata.run_attempt)
        && run.status === 'completed' && run.conclusion === 'success'
        && run.refresh_receipt?.state === 'completed' && !run.refresh_unknown && !run.refresh_not_started
        && key(run.refresh_plan, '') === tuple);
      need(producer, 'authenticated_baseline_producer_missing');
      const repoState = await read('repos', 'get', target);
      need(repoState.full_name === repositoryName && repoState.default_branch, 'default_branch_unknown');
      const tip = await read('repos', 'getCommit', { ...target, ref: repoState.default_branch });
      need(sha(tip.sha) && head.sha === pr.head.sha && sha(tip.commit?.tree?.sha)
        && sha(head.commit?.tree?.sha), 'baseline_tree_unknown');
      const comparison = await read('repos', 'compareCommitsWithBasehead', {
        ...target, basehead: `${pr.merge_commit_sha}...${tip.sha}` });
      need(comparison.merge_base_commit?.sha === pr.merge_commit_sha, 'baseline_not_in_default_history');
      const trees = [];
      for (const tree_sha of [head.commit.tree.sha, tip.commit.tree.sha]) {
        const tree = await read('git', 'getTree', { ...target, tree_sha, recursive: '1' });
        need(tree.sha === tree_sha && tree.truncated === false && Array.isArray(tree.tree), 'baseline_tree_incomplete');
        need(new Set(tree.tree.map(entry => entry.path)).size === tree.tree.length, 'baseline_tree_duplicate_paths');
        trees.push(new Map(tree.tree.map(entry => [entry.path, entry])));
      }
      const paths = Object.keys(payload.files?.[repositoryName] || {});
      need(paths.length > 0, 'baseline_payload_missing');
      const producerPlan = producer.refresh_plan?.plan;
      need(producerPlan?.plan_id === binding.plan_id && Array.isArray(producerPlan.entries),
        'baseline_compiled_projection_missing');
      const blobs = {};
      for (const file of paths) {
        need(producerPlan.entries.some(entry => entry.delivery === 'copy'
          && (!entry.include_repos?.length || entry.include_repos.includes(repositoryName))
          && !entry.skip_repos?.includes(repositoryName)
          && (entry.sync_mode !== 'create_only' || entry.overwrite_repos?.includes(repositoryName))
          && (entry.target === file || (entry.is_directory && file.startsWith(`${entry.target}/`)))),
        'baseline_did_not_deliver_selected_file');
        const old = trees[0].get(file), actual = trees[1].get(file);
        need(old?.type === 'blob' && actual?.type === 'blob' && old.sha === actual.sha
          && old.mode === actual.mode, 'baseline_selected_file_changed_or_retired');
        blobs[file] = actual.sha;
      }
      let observedRef = null;
      try {
        const ref = await read('git', 'getRef', { ...target, ref: `heads/${BRANCH}` });
        observedRef = ref.object?.sha;
        if (ref.object?.sha !== pr.head.sha && !open.some(row => row.head?.sha === ref.object?.sha)) {
          result.owner_conflicts.push({ repository: repositoryName,
            head_sha: ref.object?.sha, reason: 'candidate_ref_has_another_owner' });
        }
      } catch (error) {
        if (Number(error?.status || error?.response?.status) !== 404) throw error;
        // Both current repo/default reads above succeeded; this is a missing
        // stable ref, not a repository-level denial masquerading as absence.
        if (open.length) result.owner_conflicts.push({ repository: repositoryName,
          reason: 'open_candidate_ref_absent' });
      }
      result.baselines.push({ repository: repositoryName, pr: pr.number,
        head_sha: pr.head.sha, merge_sha: pr.merge_commit_sha, merged_at: pr.merged_at,
        default_sha: tip.sha, ...binding, blobs });
      observations.push({ target, branch: repoState.default_branch, tip: tip.sha,
        open: openIdentity(open), ref: observedRef });
    }
    // No time-based release: recheck original attempt versions and all active
    // writers after collecting baseline evidence before admitting this read.
    for (const observation of observations) {
      const { target } = observation;
      const tip = await read('repos', 'getCommit', { ...target, ref: observation.branch });
      const open = await read('pulls', 'list', { ...target, state: 'open',
        head: `${target.owner}:${BRANCH}`, per_page: 100, page: 1 });
      need(tip.sha === observation.tip && Array.isArray(open)
        && openIdentity(open) === observation.open, 'current_baseline_or_owner_changed');
      let ref = null;
      try { ref = (await read('git', 'getRef', { ...target, ref: `heads/${BRANCH}` })).object?.sha; }
      catch (error) { if (Number(error?.status || error?.response?.status) !== 404) throw error; }
      need(ref === observation.ref, 'candidate_ref_changed_during_reconciliation');
    }
    for (const run of unknown) {
      const actual = await read('actions', 'getWorkflowRun', { ...location, run_id: run.id });
      need(version(actual) === version(run), 'historical_attempt_changed_during_reconciliation');
    }
    for (const status of ACTIVE) {
      const data = await read('actions', 'listWorkflowRuns', { ...location,
        workflow_id: 'maint-68-sync-consumer-repos.yml', status, per_page: 100 });
      need(Array.isArray(data.workflow_runs) && data.total_count === data.workflow_runs.length
        && data.workflow_runs.length < 100, 'active_writer_inventory_incomplete');
      const active = data.workflow_runs.filter(run => Number(run.id) !== Number(ignoreRunId)
        || Number(run.run_attempt) !== Number(ignoreRunAttempt));
      if (active.length) {
        runs.push(...active);
        throw new Error('native_writer_active');
      }
    }
    for (const run of unknown) {
      coverage.set(run, { version: version(run), request: key(refreshPlan, payload.digest),
        owner_conflicts: result.owner_conflicts });
      result.covered.push({ run_id: run.id, run_attempt: run.run_attempt,
        head_sha: run.head_sha, updated_at: run.updated_at, historical_state: 'unknown' });
    }
    result.blocking_count = 0; result.drainable = 1;
    result.baseline_sha256 = createHash('sha256').update(JSON.stringify(result.baselines)).digest('hex');
  } catch (error) {
    result.blocking = unknown.map(run => ({ run_id: run.id, run_attempt: run.run_attempt }));
    result.reason = /^[a-z][a-z0-9_]+$/.test(error?.message || '')
      ? error.message : 'baseline_read_failed';
    const status = Number(error?.status || error?.response?.status);
    if (status >= 100 && status <= 599) result.http_status = status;
    result.next_action = 'reconcile-current-native-baseline-and-original-attempt-state';
  }
  return result;
}

module.exports = { reconcileLegacyCanaryHistory, coveredByCurrentBaseline, currentBaselineOwnerConflict };
