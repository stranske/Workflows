'use strict';

// Read the existing native Maint68 plan artifact; this is not a new receipt
// publisher or an authority supplied by the refresh caller.
const { createHash } = require('node:crypto');
const { readRetainedArchive } = require('./verifier_pending_execution');
const WORKFLOW = '.github/workflows/maint-68-sync-consumer-repos.yml';
const ARTIFACT = 'sync-plan-and-prospective-diffs';
const PREPARE = 'Prepare sync from manifest';
const UPLOAD = 'Upload plan and prospective-diff evidence';
const AUTHORIZE = 'Authorize canary payload mutation';
const MAX_BYTES = 4 * 1024 * 1024;
// Controllers inject withRetry from createTokenAwareRetry using their existing
// authenticated client. Bound outer retries as well as each native request.
const READ_RETRY = Object.freeze({ maxRetries: 2, initialDelay: 250, maxDelay: 1000 });
const sha = value => createHash('sha256').update(value).digest('hex');
const commit = value => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const hash = value => typeof value === 'string' && /^sha256:[a-f0-9]{64}$/.test(value);
const positive = value => Number.isSafeInteger(value) && value > 0;
const need = (value, reason) => { if (!value) throw new Error(reason); };

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort()
    .map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}
const ascii = text => text.replace(/[\u007f-\uffff]/g, char => `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`);
function sorted(value) {
  if (Array.isArray(value)) return value.map(sorted);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, sorted(value[key])]));
  return value;
}
function producerJson(bytes) {
  const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  const value = JSON.parse(text);
  // All four fixed members are emitted by the existing sorted Python JSON
  // producer. Exact reserialization also rejects duplicate JSON members.
  need(text === ascii(JSON.stringify(sorted(value), null, 2)) + '\n', 'noncanonical_native_plan_json');
  return value;
}
function validatePlan(plan) {
  need(plan && Object.keys(plan).sort().join(',') === 'entries,manifest_sha256,plan_id,removals,schema,version'
    && plan.schema === 'workflows.consumer-sync-plan/v1' && plan.version === 1
    && hash(plan.plan_id) && hash(plan.manifest_sha256) && Array.isArray(plan.entries)
    && Array.isArray(plan.removals), 'invalid_native_plan');
  const { plan_id: id, ...core } = plan;
  need(id === `sha256:${sha(Buffer.from('consumer-sync-plan\0' + ascii(canonical(core))))}`, 'native_plan_digest_mismatch');
  const targets = [...plan.entries, ...plan.removals].map(row => row?.target);
  need(targets.every(target => typeof target === 'string' && target && !target.startsWith('/')
    && !target.includes('\\') && target.split('/').every(part => part && part !== '.' && part !== '..'))
    && new Set(targets).size === targets.length, 'invalid_native_plan_targets');
  return targets.sort();
}
function repositories(rows) {
  need(Array.isArray(rows) && rows.every(row => typeof row === 'string' && /^[\w.-]+\/[\w.-]+$/.test(row))
    && new Set(rows).size === rows.length, 'invalid_native_phase_repositories');
  return [...rows].sort();
}
// Whole reviewed producer versions, including source consumption after the
// initial validation. An inserted checkout/effect step must not preserve this
// positive exclusion proof merely by leaving the initial checks unchanged.
const SOURCE_WORKFLOWS = new Set([
  '038ff08fed8ca2ff28e036ba4ebe03b6d1291232e66ae7d39b90432cb4df0f77',
  // Reviewed historical producers preserve the same resolved source checkout.
  'd52252dab8a2322021b39a68651592c4e212cdbb98e807750e5db75c00b99235',
  'e24c6413cf57f7e1c3ff536cc581164044afb74aa11fd048caf5b96f099313e9',
  '5684f184111d02e8c9ee270d47c9f59c593da686b9155360ae6eba3f18348579',
  'dc9bf6ee45d4d8527bce8e75d721d8922189bd3f85eac23a9b5f9d7c7226ec98',
  'c8ed3fdd00ca577b9f8d5d9c58670ed6c2e389d81cc2a515876678ec76864f91',
]);

async function readScopedCanaryReceipt({ withRetry, context, run, defaultBranch = 'main', candidates }) {
  const proof = {};
  let source, sourceMode;
  const location = { owner: context.repo.owner, repo: context.repo.repo };
  const repository = `${location.owner}/${location.repo}`.toLowerCase();
  const read = async (method, args) => {
    proof.last_read = `actions.${method}`;
    return (await withRetry(client => client.rest.actions[method]({
      ...location, ...args, request: { timeout: 15000, retries: 0 },
    }), READ_RETRY)).data;
  };
  const pages = async (method, args, key) => {
    const result = [], seen = new Set(); let total;
    for (let page = 1; page <= 10; page++) {
      const data = await read(method, { ...args, per_page: 100, page });
      need(Array.isArray(data?.[key]) && Number.isSafeInteger(data.total_count) && data.total_count >= 0,
        'native_scope_inventory_unreadable');
      need(total === undefined || total === data.total_count, 'native_scope_inventory_changed'); total = data.total_count;
      for (const row of data[key]) { need(positive(row.id) && !seen.has(row.id), 'native_scope_inventory_duplicate'); seen.add(row.id); result.push(row); }
      if (result.length === total) return result;
      need(data[key].length && result.length < total, 'native_scope_inventory_incomplete');
    }
    throw new Error('native_scope_inventory_bound');
  };
  try {
    need(positive(run?.id) && positive(run.run_attempt) && commit(run.head_sha), 'native_scope_run_identity_absent');
    const actual = await read('getWorkflowRunAttempt', { run_id: run.id, attempt_number: run.run_attempt });
    need(actual.id === run.id && actual.run_attempt === run.run_attempt && actual.head_sha === run.head_sha
      && actual.path === WORKFLOW && ['workflow_dispatch', 'schedule'].includes(actual.event) && actual.head_branch === defaultBranch
      && actual.repository?.full_name?.toLowerCase() === repository && positive(actual.repository?.id)
      && actual.head_repository?.id === actual.repository.id, 'native_scope_run_mismatch');
    proof.run_id = actual.id; proof.run_attempt = actual.run_attempt; proof.head_sha = actual.head_sha;
    const jobs = await pages('listJobsForWorkflowRunAttempt', { run_id: actual.id, attempt_number: actual.run_attempt }, 'jobs');
    const prepares = jobs.filter(job => job.name === PREPARE);
    need(prepares.length === 1 && prepares[0].run_id === actual.id && prepares[0].head_sha === actual.head_sha,
      'native_scope_prepare_mismatch');
    const prepare = prepares[0];
    const step = name => { const found = (prepare.steps || []).filter(row => row.name === name); need(found.length === 1, 'native_scope_step_ambiguous'); return found[0]; };
    const readSourceFile = async filePath => {
      proof.last_read = filePath === WORKFLOW ? 'repos.getContent.workflow' : 'repos.getContent.report';
      const response = await withRetry(client => client.rest.repos.getContent({ ...location, path: filePath,
        ref: actual.head_sha, request: { timeout: 15000, retries: 0 } }), READ_RETRY);
      const file = response.data;
      need(file?.encoding === 'base64' && typeof file.content === 'string', 'native_scope_workflow_source_unreadable');
      const bytes = Buffer.from(file.content, 'base64');
      need(file.sha === createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex'), 'native_scope_workflow_blob_mismatch');
      return { bytes, blob: file.sha };
    };
    const workflow = await readSourceFile(WORKFLOW), workflowDigest = sha(workflow.bytes);
    const knownWorkflow = SOURCE_WORKFLOWS.has(workflowDigest);
    const title = String(actual.display_title || '').trim().replace(/\s+/g, ' ');
    if (actual.event === 'schedule') {
      need(knownWorkflow, 'native_scope_schedule_workflow_unverified');
      const guard = workflowDigest === '5684f184111d02e8c9ee270d47c9f59c593da686b9155360ae6eba3f18348579' ? '' : ' guard=delivery-v1';
      need(title === `Maint 68 canary auto source=${actual.head_sha} candidates=* dry=false${guard}`,
        'native_scope_schedule_identity_mismatch');
    }
    // This exact reviewed DAG cannot admit any consumer job without prepare
    // outputs. Positive native bootstrap evidence is required; missing fields
    // and general cancellation are not no-start proof. Summary's only executed
    // module is independently fixed to its reviewed pure report implementation.
    const names = ['Prepare sync from manifest', 'Validate sync files', 'Sync ${{ matrix.repo }}',
      'Start generated delivery reconciliation', 'Create failure issue', 'Generate summary'];
    const bootstrap = workflowDigest === 'd52252dab8a2322021b39a68651592c4e212cdbb98e807750e5db75c00b99235'
      // This exact native tree also closes the cancelled local setup composite
      // and its transitive fs-only helper; a same-workflow future tree is not proof.
      && actual.head_sha === '67829b6145644352661b56f5251344cf952d0a64'
      && actual.run_attempt === 1 && actual.status === 'completed' && actual.conclusion === 'cancelled'
      && prepare.status === 'completed' && prepare.conclusion === 'cancelled'
      && prepare.runner_id === 0 && prepare.runner_name === '' && Array.isArray(prepare.steps) && prepare.steps.length === 0
      && jobs.length === names.length && names.every(name => jobs.filter(job => job.name === name).length === 1)
      && jobs.every(job => job.run_id === actual.id && job.head_sha === actual.head_sha && job.status === 'completed')
      && jobs.filter(job => !['Prepare sync from manifest','Generate summary'].includes(job.name)).every(job =>
        job.conclusion === 'cancelled' && Array.isArray(job.steps) && job.steps.length === 0
        && Object.hasOwn(job,'runner_id') && [null,0].includes(job.runner_id))
      && (() => { const summary=jobs.find(job => job.name === 'Generate summary');
        const expected = [
          ['Set up job','success'], ['Checkout','success'], ['Download sync result artifacts','success'],
          ['Build sync run report','success'], ['Generate summary','success'],
          ['Setup promotion health API client','cancelled'],
          ['Report sealed plans awaiting promotion','skipped'], ['Upload sync run report','skipped'],
          ['Post Checkout','skipped'], ['Complete job',null],
        ];
        return summary.conclusion === 'cancelled' && Array.isArray(summary.steps)
          && summary.steps.length === expected.length && expected.every(([name,conclusion],index) =>
            summary.steps[index]?.name === name && summary.steps[index]?.conclusion === conclusion);
      })();
    if (bootstrap) {
      const reportModule = await readSourceFile('.github/scripts/sync_run_contract.js');
      need(sha(reportModule.bytes) === '10d28ca1485d2e3cf8630b915d3964c7f7103983511e2088a1135bc5e79ead46', 'native_scope_bootstrap_report_source_unverified');
      const emptyArtifacts = await pages('listWorkflowRunArtifacts', { run_id: actual.id }, 'artifacts');
      need(emptyArtifacts.length === 0, 'native_scope_bootstrap_artifacts_present');
      const fresh = await read('getWorkflowRun', { run_id: actual.id });
      need(fresh.id === actual.id && fresh.run_attempt === 1 && fresh.head_sha === actual.head_sha
        && fresh.status === 'completed' && fresh.conclusion === 'cancelled', 'native_scope_attempt_changed');
      return { state: 'not_started', reason: 'native_scope_bootstrap_not_started', proof: { ...proof,
        workflow_blob_sha: workflow.blob, report_module_sha256: sha(reportModule.bytes), bootstrap_not_started: true } };
    }
    const sourceSteps = ['Resolve immutable plan scope', 'Checkout', 'Validate immutable source reachability'];
    if (sourceSteps.every(name => step(name).conclusion === 'success') && knownWorkflow) {
      const match = title.match(/^Maint 68 canary (full|auto|source-delta)\s+source=([a-f0-9]{40}) candidates=\S+ dry=false(?: drift=[a-f0-9]{64})?(?: guard=delivery-v1)?$/);
      if (match) { source = match[2]; sourceMode = match[1] === 'source-delta' ? 'source-delta' : 'full'; proof.source_identity_bound = true; proof.workflow_blob_sha = workflow.blob; }
    }
    const artifacts = await pages('listWorkflowRunArtifacts', { run_id: actual.id }, 'artifacts');
    const selected = artifacts.filter(artifact => artifact.name === ARTIFACT);
    need(selected.length === 1, 'native_scope_artifact_absent_or_ambiguous');
    const artifact = await read('getArtifact', { artifact_id: selected[0].id });
    need(artifact.id === selected[0].id && artifact.name === ARTIFACT && artifact.expired === false
      && artifact.size_in_bytes > 0 && artifact.size_in_bytes <= MAX_BYTES && hash(artifact.digest)
      && artifact.workflow_run?.id === actual.id && artifact.workflow_run.head_sha === actual.head_sha
      && artifact.workflow_run.head_branch === defaultBranch && artifact.workflow_run.repository_id === actual.repository.id
      && artifact.workflow_run.head_repository_id === actual.repository.id, 'native_scope_artifact_identity_mismatch');
    const upload = step(UPLOAD), at = Date.parse(artifact.created_at);
    need(upload.conclusion === 'success' && Number.isFinite(at) && at >= Date.parse(upload.started_at)
      && at <= Date.parse(upload.completed_at) + 1000, 'native_scope_artifact_attempt_window');
    const archive = Buffer.from(await read('downloadArtifact', { artifact_id: artifact.id, archive_format: 'zip' }));
    need(archive.length > 0 && archive.length <= MAX_BYTES && `sha256:${sha(archive)}` === artifact.digest,
      'native_scope_archive_digest');
    const files = readRetainedArchive(archive, { maxEntries: 4, maxBytes: MAX_BYTES });
    need(files.size === 4 && ['manifest.json', 'manifest.full.json', 'sync-plan-scope.json', 'sync-phase-selection.json'].every(name => files.has(name)), 'native_scope_archive_members');
    const plan = producerJson(files.get('manifest.json')), full = producerJson(files.get('manifest.full.json'));
    const scope = producerJson(files.get('sync-plan-scope.json')), phase = producerJson(files.get('sync-phase-selection.json'));
    const targets = validatePlan(plan); validatePlan(full);
    need(scope.schema === 'workflows.consumer-sync-plan-scope/v1' && ['full', 'source-delta'].includes(scope.mode)
      && scope.plan_id === plan.plan_id && scope.full_plan_id === full.plan_id && plan.manifest_sha256 === full.manifest_sha256
      && commit(scope.source_commit) && (!source || source === scope.source_commit)
      && (!sourceMode || sourceMode === scope.mode)
      && (scope.mode === 'source-delta' ? commit(scope.base_sha) : scope.base_sha === '')
      && scope.selected_entry_count === plan.entries.length && scope.selected_removal_count === plan.removals.length
      && canonical(scope.selected_targets) === canonical(targets), 'native_scope_plan_binding');
    const expected = repositories(candidates), selectedRepos = repositories(phase.selected_repos);
    need(phase.schema === 'workflows.consumer-sync-phase-selection/v1' && phase.phase === 'canary'
      && phase.plan_id === plan.plan_id && canonical(expected) === canonical(selectedRepos), 'native_scope_phase_binding');
    const refreshed = await read('getWorkflowRun', { run_id: actual.id });
    need(refreshed.id === actual.id && refreshed.run_attempt === actual.run_attempt && refreshed.head_sha === actual.head_sha
      && refreshed.status === actual.status && refreshed.conclusion === actual.conclusion, 'native_scope_attempt_changed');
    Object.assign(proof, { artifact_id: artifact.id, archive_sha256: sha(archive), prepare_job_id: prepare.id });
    const auth = step(AUTHORIZE), consumers = jobs.filter(job => /^Sync /.test(job.name));
    let state = 'unknown';
    if (actual.status === 'completed' && actual.conclusion === 'success') {
      // A skipped latest rerun cannot erase an earlier attempt's possible
      // effects. Only the original native attempt can establish no start.
      if (actual.run_attempt === 1 && auth.conclusion === 'skipped' && consumers.length && consumers.every(job => job.run_id === actual.id
        && job.head_sha === actual.head_sha && job.status === 'completed' && job.conclusion === 'skipped')) state = 'not_started';
      if (auth.conclusion === 'success' && consumers.length === expected.length
        && expected.every(repo => consumers.filter(job => job.name === `Sync ${repo}` && job.run_id === actual.id
          && job.head_sha === actual.head_sha && job.status === 'completed' && job.conclusion === 'success').length === 1)) state = 'completed';
    }
    return { state, ...(state === 'unknown' ? { reason: 'native_scope_effect_disposition_unknown' } : {}),
      plan_id: plan.plan_id, plan_scope: scope.mode, scope_base_sha: scope.base_sha,
      source_commit: scope.source_commit, plan, candidates: expected, proof };
  } catch (error) {
    if (Number.isSafeInteger(error?.status) && error.status >= 100 && error.status <= 599) proof.http_status = error.status;
    return { state: 'unknown', ...(source ? { source_commit: source } : {}), reason: String(error.message || error), proof };
  }
}

module.exports = { readScopedCanaryReceipt };
