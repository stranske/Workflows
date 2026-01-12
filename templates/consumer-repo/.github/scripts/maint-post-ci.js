'use strict';

const fs = require('fs');
const path = require('path');

async function discoverWorkflowRuns({ github, context, core }) {
  const { owner, repo } = context.repo;
  const workflowRun = context.payload.workflow_run || {};
  const prFromPayload = Array.isArray(workflowRun.pull_requests)
    ? workflowRun.pull_requests.find(item => item && item.head && item.head.sha)
    : null;
  const headSha = (prFromPayload?.head?.sha || workflowRun.head_sha || context.sha || '').trim();

  const parseJsonInput = (raw, fallback) => {
    if (!raw) {
      return fallback;
    }
    try {
      return JSON.parse(raw);
    } catch (error) {
      core.warning(`Failed to parse JSON input: ${error}`);
      return fallback;
    }
  };

  const defaultWorkflowTargets = [
    { key: 'gate', display_name: 'Gate', workflow_path: '.github/workflows/pr-00-gate.yml' },
  ];

  const workflowTargetsRaw = process.env.WORKFLOW_TARGETS_JSON;
  const workflowTargetsInput = parseJsonInput(workflowTargetsRaw, defaultWorkflowTargets);
  const workflowTargetsSource = Array.isArray(workflowTargetsInput) ? workflowTargetsInput : defaultWorkflowTargets;

  function normalizeTargetProps(target) {
    return {
      key: target.key,
      displayName: target.display_name || target.displayName || target.key || 'workflow',
      workflowPath: target.workflow_path || target.workflowPath || '',
      workflowFile: target.workflow_file || target.workflowFile || target.workflow_id || target.workflowId || '',
      workflowName: target.workflow_name || target.workflowName || '',
      workflowIds: Array.isArray(target.workflow_ids)
        ? target.workflow_ids
        : (target.workflowIds && Array.isArray(target.workflowIds) ? target.workflowIds : []),
    };
  }

  const workflowTargets = workflowTargetsSource
    .map(normalizeTargetProps)
    .filter(target => target && target.key);

  const normalizePath = (value) => {
    if (!value) return '';
    return String(value).replace(/^\.\//, '').replace(/^\/+/, '');
  };

  async function loadWorkflowRun(identifier) {
    if (!identifier) {
      return null;
    }
    try {
      const response = await github.rest.actions.listWorkflowRuns({
        owner,
        repo,
        workflow_id: identifier,
        head_sha: headSha || undefined,
        event: 'pull_request',
        per_page: 10,
      });
      const runs = response.data.workflow_runs || [];
      if (!runs.length) {
        return null;
      }
      if (!headSha) {
        return runs[0];
      }
      const exact = runs.find(item => item.head_sha === headSha);
      return exact || runs[0];
    } catch (error) {
      core.warning(`Failed to query workflow runs for "${identifier}": ${error}`);
      return null;
    }
  }

  async function loadJobs(runId) {
    if (!runId) {
      return [];
    }
    try {
      const jobs = await github.paginate(
        github.rest.actions.listJobsForWorkflowRun,
        {
          owner,
          repo,
          run_id: runId,
          per_page: 100,
        },
      );
      return jobs
        .filter(job => job)
        .map(job => ({
          name: job.name,
          conclusion: job.conclusion,
          status: job.status,
          html_url: job.html_url,
        }));
    } catch (error) {
      core.warning(`Failed to query jobs for workflow run ${runId}: ${error}`);
      return [];
    }
  }

  async function resolveRun(target) {
    const candidates = [];
    if (Array.isArray(target.workflowIds) && target.workflowIds.length) {
      for (const id of target.workflowIds) {
        if (id) {
          candidates.push(id);
        }
      }
    }
    if (target.workflowPath) {
      candidates.push(normalizePath(target.workflowPath));
    }
    if (target.workflowFile) {
      candidates.push(normalizePath(target.workflowFile));
    }
    if (target.workflowName) {
      candidates.push(target.workflowName);
    }
    if (!candidates.length) {
      candidates.push(target.key);
    }

    for (const identifier of candidates) {
      const run = await loadWorkflowRun(identifier);
      if (run) {
        return run;
      }
    }
    return null;
  }

  const collected = [];
  for (const target of workflowTargets) {
    const run = await resolveRun(target);
    if (run) {
      const jobs = await loadJobs(run.id);
      collected.push({
        key: target.key,
        displayName: target.displayName,
        present: true,
        id: run.id,
        run_attempt: run.run_attempt,
        conclusion: run.conclusion,
        status: run.status,
        html_url: run.html_url,
        jobs,
      });
    } else {
      collected.push({
        key: target.key,
        displayName: target.displayName,
        present: false,
        jobs: [],
      });
    }
  }

  const gateRun = collected.find(entry => entry.key === 'gate' && entry.present);
  const gateRunId = gateRun ? String(gateRun.id) : '';

  core.setOutput('runs', JSON.stringify(collected));
  core.setOutput('ci_run_id', gateRunId);
  core.setOutput('gate_run_id', gateRunId);
  core.setOutput('head_sha', headSha || '');
  core.notice(`Collected ${collected.filter(entry => entry.present).length} Gate workflow runs for head ${headSha}`);
}

async function propagateGateCommitStatus({ github, context, core }) {
  const { owner, repo } = context.repo;
  const sha = process.env.HEAD_SHA || '';
  if (!sha) {
    core.info('Head SHA missing; skipping Gate commit status update.');
    return;
  }

  const conclusion = (process.env.RUN_CONCLUSION || '').toLowerCase();
  const status = (process.env.RUN_STATUS || '').toLowerCase();
  let state = 'pending';
  let description = 'Gate workflow status pending.';

  if (conclusion === 'success') {
    state = 'success';
    description = 'Gate workflow succeeded.';
  } else if (conclusion === 'failure') {
    state = 'failure';
    description = 'Gate workflow failed.';
  } else if (conclusion === 'cancelled') {
    state = 'error';
    description = 'Gate workflow was cancelled.';
  } else if (conclusion === 'timed_out') {
    state = 'error';
    description = 'Gate workflow timed out.';
  } else if (conclusion === 'action_required') {
    state = 'pending';
    description = 'Gate workflow requires attention.';
  } else if (!conclusion) {
    if (status === 'completed') {
      description = 'Gate workflow completed with unknown result.';
    } else if (status === 'in_progress') {
      description = 'Gate workflow is still running.';
    } else if (status === 'queued') {
      description = 'Gate workflow is queued.';
    }
  } else {
    description = `Gate workflow concluded with ${conclusion}.`;
  }

  const MAX_DESCRIPTION_LENGTH = 140;
  const trimmed = description.length > MAX_DESCRIPTION_LENGTH
    ? `${description.slice(0, MAX_DESCRIPTION_LENGTH - 3)}...`
    : description;
  const runId = context.payload?.workflow_run?.id || context.runId;
  const baseUrl = process.env.GITHUB_SERVER_URL || 'https://github.com';
  const targetUrl = process.env.GATE_RUN_URL || `${baseUrl.replace(/\/$/, '')}/${owner}/${repo}/actions/runs/${runId}`;

  try {
    await github.rest.repos.createCommitStatus({
      owner,
      repo,
      sha,
      state,
      context: 'Gate / gate',
      description: trimmed,
      target_url: targetUrl,
    });
    core.info(`Propagated Gate commit status (${state}) for ${sha}.`);
  } catch (error) {
    core.warning(`Failed to propagate Gate commit status: ${error.message}`);
  }
}

async function resolveAutofixContext({ github, context, core }) {
  const run = context.payload.workflow_run;
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const prefix = process.env.COMMIT_PREFIX || 'chore(autofix):';
  const payloadPr = run && Array.isArray(run.pull_requests)
    ? run.pull_requests.find(item => item && typeof item.number === 'number')
    : null;
  const branch = (payloadPr?.head?.ref || run?.head_branch || '').trim();
  const headSha = (payloadPr?.head?.sha || run?.head_sha || '').trim();

  const result = {
    found: 'false',
    pr: '',
    head_ref: branch || '',
    head_sha: headSha || '',
    same_repo: 'false',
    loop_skip: 'false',
    small_eligible: 'false',
    file_count: '0',
    change_count: '0',
    safe_paths: '',
    unsafe_paths: '',
    safe_file_count: '0',
    unsafe_file_count: '0',
    safe_change_count: '0',
    unsafe_change_count: '0',
    all_safe: 'false',
    has_opt_in: 'false',
    has_patch_label: 'false',
    is_draft: run.event === 'pull_request' && run.head_repository ? (run.pull_requests?.[0]?.draft ? 'true' : 'false') : 'false',
    run_conclusion: run.conclusion || '',
    actor: (run.triggering_actor?.login || run.actor?.login || '').toLowerCase(),
    head_subject: '',
    failure_tracker_skip: 'false',
  };

  if (!branch || !headSha) {
    core.info('Workflow run missing branch or head SHA; skipping.');
    for (const [key, value] of Object.entries(result)) {
      core.setOutput(key, value);
    }
    return;
  }

  const headShaLower = (headSha || '').toLowerCase();
  let pr = null;
  let prNumber = null;

  if (payloadPr) {
    prNumber = Number(payloadPr.number);
    if (!Number.isNaN(prNumber)) {
      try {
        const prResponse = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
        pr = prResponse.data;
      } catch (error) {
        core.warning(`Failed to load PR #${prNumber} from workflow payload: ${error.message}`);
      }
    }
  }

  let openPrs = [];
  if (!pr) {
    openPrs = await github.paginate(github.rest.pulls.list, {
      owner,
      repo,
      state: 'open',
      per_page: 100,
    });

    if (headShaLower) {
      pr = openPrs.find(item => (item.head?.sha || '').toLowerCase() === headShaLower) || null;
    }

    if (!pr && branch) {
      const branchLower = branch.toLowerCase();
      pr = openPrs.find(item => (item.head?.ref || '').toLowerCase() === branchLower) || null;
    }

    if (!pr && openPrs.length) {
      pr = openPrs[0];
    }
  }

  if (!pr) {
    core.info(`Unable to locate an open PR for workflow run (head_sha=${headSha}, branch=${branch || 'n/a'})`);
    for (const [key, value] of Object.entries(result)) {
      core.setOutput(key, value);
    }
    return;
  }

  prNumber = Number(pr.number);
  result.found = 'true';
  result.pr = String(prNumber);
  result.head_ref = pr.head?.ref || branch;
  result.head_sha = pr.head?.sha || headSha;
  result.same_repo = pr.head?.repo?.full_name === `${owner}/${repo}` ? 'true' : 'false';
  result.is_draft = pr.draft ? 'true' : 'false';

  const resolvedHeadRef = result.head_ref || branch || 'unknown-ref';
  const resolvedHeadSha = result.head_sha || headSha || 'unknown-sha';
  const gateRunId = run?.id ? String(run.id) : 'unknown-run';
  core.notice(
    `Resolved PR #${result.pr} (${resolvedHeadRef} @ ${resolvedHeadSha}) for Gate run ${gateRunId}.`,
  );

  const failureTrackerSkipPrs = new Set([10, 12]);
  if (failureTrackerSkipPrs.has(prNumber)) {
    core.info(`PR #${prNumber} flagged to skip failure tracker updates (legacy duplicate).`);
    result.failure_tracker_skip = 'true';
  }

  const labels = Array.isArray(pr.labels)
    ? pr.labels
        .filter(label => label && typeof label.name === 'string')
        .map(label => label.name)
    : [];
  const optLabel = process.env.AUTOFIX_LABEL || 'autofix:clean';
  const patchLabel = process.env.AUTOFIX_PATCH_LABEL || 'autofix:patch';
  result.has_opt_in = labels.includes(optLabel) ? 'true' : 'false';
  result.has_patch_label = labels.includes(patchLabel) ? 'true' : 'false';
  try {
    result.labels_json = JSON.stringify(labels);
  } catch (error) {
    core.warning(`Failed to serialise label list: ${error}`);
    result.labels_json = '[]';
  }
  result.title = pr.title || '';

  try {
    const commit = await github.rest.repos.getCommit({ owner, repo, ref: result.head_sha });
    const subject = (commit.data.commit.message || '').split('\n')[0];
    result.head_subject = subject;
    const actor = result.actor;
    const isAutomation = actor === 'github-actions' || actor === 'github-actions[bot]';
    const subjectLower = subject.toLowerCase();
    const prefixLower = prefix.toLowerCase();
    if (isAutomation && prefixLower && subjectLower.startsWith(prefixLower)) {
      core.info(`Loop guard engaged for actor ${actor}: detected prior autofix commit.`);
      result.loop_skip = 'true';
    }
  } catch (error) {
    core.warning(`Unable to inspect commit message for loop guard: ${error.message}`);
  }

  if (result.found === 'true') {
    const files = await github.paginate(github.rest.pulls.listFiles, {
      owner,
      repo,
      pull_number: pr.number,
      per_page: 100,
    });
    const safeSuffixes = ['.py', '.pyi', '.toml', '.cfg', '.ini'];
    const safeBasenames = new Set([
      'pyproject.toml',
      'ruff.toml',
      '.ruff.toml',
      'mypy.ini',
      '.pre-commit-config.yaml',
      'pytest.ini',
      '.coveragerc',
    ].map(name => name.toLowerCase()));
    const isSafePath = (filepath) => {
      const lower = filepath.toLowerCase();
      if (safeSuffixes.some(suffix => lower.endsWith(suffix))) {
        return true;
      }
      for (const name of safeBasenames) {
        if (lower === name || lower.endsWith(`/${name}`)) {
          return true;
        }
      }
      return false;
    };
    const totalFiles = files.length;
    const totalChanges = files.reduce((acc, file) => acc + (file.changes || 0), 0);
    const safeFiles = files.filter(file => isSafePath(file.filename));
    const unsafeFiles = files.filter(file => !isSafePath(file.filename));
    const safeChanges = safeFiles.reduce((acc, file) => acc + (file.changes || 0), 0);
    const unsafeChanges = totalChanges - safeChanges;
    const allSafe = unsafeFiles.length === 0;
    const limitFiles = Number(process.env.AUTOFIX_MAX_FILES || 40);
    const limitChanges = Number(process.env.AUTOFIX_MAX_CHANGES || 800);
    const baseEligible = labels.includes(optLabel);
    const safeEligible = baseEligible && safeFiles.length > 0 && safeFiles.length <= limitFiles && safeChanges <= limitChanges;
    result.small_eligible = safeEligible ? 'true' : 'false';
    result.file_count = String(totalFiles);
    result.change_count = String(totalChanges);
    result.safe_paths = safeFiles.map(file => file.filename).join('\n');
    result.unsafe_paths = unsafeFiles.map(file => file.filename).join('\n');
    result.safe_file_count = String(safeFiles.length);
    result.unsafe_file_count = String(unsafeFiles.length);
    result.safe_change_count = String(safeChanges);
    result.unsafe_change_count = String(unsafeChanges);
    result.all_safe = allSafe ? 'true' : 'false';
  }

  for (const [key, value] of Object.entries(result)) {
    core.setOutput(key, value ?? '');
  }
}

async function inspectFailingJobs({ github, context, core }) {
  const run = context.payload.workflow_run;
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const conclusion = (run.conclusion || '').toLowerCase();

  const setOutputs = ({
    trivial = 'false',
    names = '',
    count = '0',
    incomplete = 'false',
    hasJobs = 'false',
  } = {}) => {
    core.setOutput('trivial', trivial);
    core.setOutput('names', names);
    core.setOutput('count', count);
    core.setOutput('incomplete', incomplete);
    core.setOutput('has_jobs', hasJobs);
  };

  if (!run.id) {
    setOutputs({ incomplete: 'true' });
    return;
  }

  if (conclusion === 'success') {
    setOutputs();
    return;
  }

  if (conclusion && conclusion !== 'failure') {
    setOutputs({ incomplete: 'true' });
    return;
  }

  const keywords = (process.env.AUTOFIX_TRIVIAL_KEYWORDS || 'lint,format,style,doc,ruff,mypy,type,black,isort,label,test').split(',')
    .map(str => str.trim().toLowerCase())
    .filter(Boolean);

  const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
    owner,
    repo,
    run_id: run.id,
    per_page: 100,
  });

  const failing = jobs.filter(job => {
    const c = (job.conclusion || '').toLowerCase();
    return c && c !== 'success' && c !== 'skipped';
  });

  if (!failing.length) {
    setOutputs();
    return;
  }

  const actionableConclusions = new Set(['failure']);
  const incomplete = failing.some(job => !actionableConclusions.has((job.conclusion || '').toLowerCase()));
  const allTrivial = failing.every(job => {
    const name = (job.name || '').toLowerCase();
    return keywords.some(keyword => name.includes(keyword));
  });

  setOutputs({
    trivial: allTrivial ? 'true' : 'false',
    names: failing.map(job => job.name).join(', '),
    count: String(failing.length),
    incomplete: incomplete ? 'true' : 'false',
    hasJobs: 'true',
  });
}

async function evaluateAutofixRerunGuard({ github, context, core }) {
  const prNumber = Number(process.env.PR_NUMBER || '0');
  const headSha = (process.env.HEAD_SHA || '').toLowerCase();
  const sameRepo = (process.env.SAME_REPO || '').toLowerCase() === 'true';
  const hasPatchLabel = (process.env.HAS_PATCH_LABEL || '').toLowerCase() === 'true';
  const markerPrefix = '<!-- autofix-meta:';

  const setOutputs = (skip, reason = '') => {
    core.setOutput('skip', skip ? 'true' : 'false');
    core.setOutput('reason', reason);
  };

  if (!prNumber || !headSha) {
    setOutputs(false);
    return;
  }

  if (sameRepo || !hasPatchLabel) {
    setOutputs(false);
    return;
  }

  const comments = await github.paginate(github.rest.issues.listComments, {
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: prNumber,
    per_page: 100,
  });

  for (const comment of comments) {
    const body = comment.body || '';
    if (!body.includes(markerPrefix)) {
      continue;
    }
    const match = body.match(/<!--\s*autofix-meta:[^>]*head=([0-9a-f]+)/i);
    if (!match) {
      continue;
    }
    const storedHead = (match[1] || '').toLowerCase();
    if (storedHead && storedHead === headSha) {
      core.info(`Autofix patch already generated for commit ${headSha}; skipping rerun.`);
      setOutputs(true, 'duplicate-patch');
      return;
    }
  }

  setOutputs(false);
}

async function updateFailureTracker({ github, context, core }) {
  const run = context.payload.workflow_run;
  const { owner, repo } = context.repo;
  const runId = run.id;
  const prNumberParsed = parseInt(process.env.PR_NUMBER || '', 10);
  const prNumber = Number.isFinite(prNumberParsed) && prNumberParsed > 0 ? prNumberParsed : null;
  const prTag = prNumber ? `<!-- tracked-pr: ${prNumber} -->` : null;
  const prLine = prNumber ? `Tracked PR: #${prNumber}` : null;

  const slugify = (value) => {
    if (!value) {
      return 'unknown-workflow';
    }
    const slug = String(value)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .replace(/--+/g, '-')
      .trim();
    return slug ? slug.slice(0, 80) : 'unknown-workflow';
  };

  const RATE_LIMIT_MINUTES = parseInt(process.env.RATE_LIMIT_MINUTES || '15', 10);
  const STACK_TOKENS_ENABLED = /^true$/i.test(process.env.STACK_TOKENS_ENABLED || 'true');
  const STACK_TOKEN_MAX_LEN = parseInt(process.env.STACK_TOKEN_MAX_LEN || '160', 10);
  const FAILURE_INACTIVITY_HEAL_HOURS = parseFloat(process.env.FAILURE_INACTIVITY_HEAL_HOURS || '0');
  const HEAL_THRESHOLD_DESC = `Auto-heal after ${process.env.AUTO_HEAL_INACTIVITY_HOURS || '24'}h stability (success path)`;

  const jobsResp = await github.rest.actions.listJobsForWorkflowRun({ owner, repo, run_id: runId, per_page: 100 });
  const failedJobs = jobsResp.data.jobs.filter(j => (j.conclusion || '').toLowerCase() !== 'success');
  if (!failedJobs.length) {
    core.info('No failed jobs found despite run-level failure — aborting.');
    return;
  }

  let stackTokenNote = 'Stack tokens disabled';
  let stackToken = null;
  if (STACK_TOKENS_ENABLED) {
    const zlib = require('zlib');
    const STACK_TOKEN_RAW = /^true$/i.test(process.env.STACK_TOKEN_RAW || 'false');
    function normalizeToken(raw, maxLen) {
      if (STACK_TOKEN_RAW) return (raw || 'no-stack').slice(0, maxLen);
      if (!raw) return 'no-stack';
      let t = raw;
      const ISO_TIMESTAMP_START_REGEX = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s*/;
      t = t.replace(ISO_TIMESTAMP_START_REGEX, '');
      t = t.replace(/\s+\[[0-9]{1,3}%\]\s*/g, ' ');
      t = t.replace(/\s+/g, ' ').trim();
      const m = t.match(/^[^:]+: [^:]+/);
      if (m) t = m[0];
      if (!t) t = 'no-stack';
      return t.slice(0, maxLen);
    }
    async function extractStackToken(job) {
      try {
        const logs = await github.rest.actions.downloadJobLogsForWorkflowRun({ owner, repo, job_id: job.id });
        const buffer = Buffer.from(logs.data);
        const text = job.name.includes('test')
          ? zlib.gunzipSync(buffer).toString('utf8')
          : buffer.toString('utf8');
        const lines = text.split(/\r?\n/);
        for (const line of lines) {
          if (line.includes('Traceback') || line.includes('Error:')) {
            return normalizeToken(line, STACK_TOKEN_MAX_LEN);
          }
        }
      } catch (error) {
        core.info(`Failed to extract stack token for job ${job.id}: ${error.message}`);
      }
      return null;
    }

    for (const job of failedJobs) {
      stackToken = await extractStackToken(job);
      if (stackToken) {
        break;
      }
    }

    if (stackToken) {
      stackTokenNote = `Stack token: ${stackToken}`;
    } else {
      stackTokenNote = 'Stack token unavailable';
    }
  }

  const signatureParts = failedJobs.map(job => `${job.name} (${job.conclusion || job.status || 'unknown'})`);
  const title = `${slugify(run.name || run.display_title || 'Gate')} failure: ${signatureParts.join(', ')}`;
  const descriptionLines = [
    `Workflow: ${run.name || run.display_title || 'Gate'}`,
    `Run ID: ${runId}`,
    `Run URL: ${run.html_url || ''}`,
    prLine,
    stackTokenNote,
  ].filter(Boolean);

  const labels = ['ci-failure'];
  const cooldownHours = parseFloat(process.env.NEW_ISSUE_COOLDOWN_HOURS || '12');
  const retryMs = parseInt(process.env.COOLDOWN_RETRY_MS || '3000', 10);

  async function attemptCooldownAppend(stage) {
    try {
      const listName = `failure-cooldown-${slugify(run.name || 'gate')}`;
      const response = await github.rest.actions.getEnvironmentVariable({ owner, repo, name: listName });
      const lastEntries = response.data.value ? JSON.parse(response.data.value) : [];
      const now = Date.now();
      const recent = lastEntries.find(entry => now - entry.timestamp < cooldownHours * 3600_000);
      if (recent) {
        core.info(`Cooldown active (${stage}); skipping failure issue creation.`);
        return true;
      }
      lastEntries.push({ timestamp: now, run_id: runId });
      await github.rest.actions.updateEnvironmentVariable({ owner, repo, name: listName, value: JSON.stringify(lastEntries.slice(-25)) });
      core.info(`Recorded cooldown entry for run ${runId} (${stage}).`);
      return true;
    } catch (error) {
      core.info(`Cooldown list retrieval failed (${stage}): ${error.message}`);
    }
    return false;
  }

  let appendedViaCooldown = await attemptCooldownAppend('initial');
  if (!appendedViaCooldown && cooldownHours > 0 && retryMs > 0) {
    await new Promise(r => setTimeout(r, retryMs));
    appendedViaCooldown = await attemptCooldownAppend('retry');
  }
  if (appendedViaCooldown) return;

  const nowIso = new Date().toISOString();
  const headerMeta = [
    'Occurrences: 1',
    `Last seen: ${nowIso}`,
    `Healing threshold: ${HEAL_THRESHOLD_DESC}`,
    '',
  ].join('\n');
  const bodyBlock = [
    '## Failure summary',
    ...failedJobs.map(job => `- ${job.name} (${job.conclusion || job.status || 'unknown'})`),
    '',
    stackTokenNote,
    '',
    ...(prTag ? [prTag] : []),
  ].join('\n');
  const created = await github.rest.issues.create({ owner, repo, title, body: headerMeta + bodyBlock, labels });
  core.info(`Created new failure issue #${created.data.number}`);
}

async function resolveFailureIssuesForRecoveredPR({ github, context, core }) {
  const pr = parseInt(process.env.PR_NUMBER || '', 10);
  if (!Number.isFinite(pr) || pr <= 0) {
    core.info('No PR number detected; skipping failure issue resolution.');
    return;
  }
  const { owner, repo } = context.repo;
  const tag = `<!-- tracked-pr: ${pr} -->`;
  const query = `repo:${owner}/${repo} is:issue is:open label:ci-failure "${tag}"`;
  const search = await github.rest.search.issuesAndPullRequests({ q: query, per_page: 10 });
  if (!search.data.items.length) {
    core.info(`No open failure issues tagged for PR #${pr}.`);
    return;
  }
  const runUrl = process.env.RUN_URL || (context.payload.workflow_run && context.payload.workflow_run.html_url) || '';
  const nowIso = new Date().toISOString();
  for (const item of search.data.items) {
    const issue_number = item.number;
    const issue = await github.rest.issues.get({ owner, repo, issue_number });
    let body = issue.data.body || '';
    body = body
      .replace(/^Resolved:.*$/gim, '')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/^\n+/, '')
      .replace(/\s+$/, '');
    body = `Resolved: ${nowIso}\n${body}`.replace(/\n{3,}/g, '\n\n').replace(/\s+$/, '');
    if (body) {
      body = `${body}\n`;
    }

    const commentLines = [
      `Resolution: Gate run succeeded for PR #${pr}.`,
      runUrl ? `Success run: ${runUrl}` : null,
      `Timestamp: ${nowIso}`,
    ].filter(Boolean);
    if (commentLines.length) {
      await github.rest.issues.createComment({
        owner,
        repo,
        issue_number,
        body: commentLines.join('\n'),
      });
    }
    await github.rest.issues.update({ owner, repo, issue_number, state: 'closed', body });
    core.info(`Closed failure issue #${issue_number} for PR #${pr}.`);
  }
}

async function autoHealFailureIssues({ github, context, core }) {
  const { owner, repo } = context.repo;
  const INACTIVITY_HOURS = parseFloat(process.env.AUTO_HEAL_INACTIVITY_HOURS || '24');
  const now = Date.now();
  const q = `repo:${owner}/${repo} is:issue is:open label:ci-failure`;
  const search = await github.rest.search.issuesAndPullRequests({ q, per_page: 100 });
  for (const item of search.data.items) {
    const issue_number = item.number;
    const issue = await github.rest.issues.get({ owner, repo, issue_number });
    const body = issue.data.body || '';
    const m = body.match(/Last seen:\s*(.+)/i);
    if (!m) continue;
    const lastSeenTs = Date.parse(m[1].trim());
    if (Number.isNaN(lastSeenTs)) continue;
    const hours = (now - lastSeenTs) / 3_600_000;
    if (hours >= INACTIVITY_HOURS) {
      const comment = `Auto-heal: no reoccurrence for ${hours.toFixed(1)}h (>= ${INACTIVITY_HOURS}h). Closing.`;
      await github.rest.issues.createComment({ owner, repo, issue_number, body: comment });
      await github.rest.issues.update({ owner, repo, issue_number, state: 'closed' });
      core.info(`Closed healed failure issue #${issue_number}`);
    }
  }
  core.summary.addHeading('Success Run Summary');
  core.summary.addRaw('Checked for stale failure issues and applied auto-heal where applicable.');
  await core.summary.write();
}

async function snapshotFailureIssues({ github, context, core }) {
  const { owner, repo } = context.repo;
  const q = `repo:${owner}/${repo} is:issue is:open label:ci-failure`;
  const search = await github.rest.search.issuesAndPullRequests({ q, per_page: 100 });
  const issues = [];
  for (const item of search.data.items) {
    const issue = await github.rest.issues.get({ owner, repo, issue_number: item.number });
    const body = issue.data.body || '';
    const occ = (body.match(/Occurrences:\s*(\d+)/i) || [])[1] || null;
    const lastSeen = (body.match(/Last seen:\s*(.*)/i) || [])[1] || null;
    issues.push({
      number: issue.data.number,
      title: issue.data.title,
      occurrences: occ ? parseInt(occ, 10) : null,
      last_seen: lastSeen,
      url: issue.data.html_url,
      created_at: issue.data.created_at,
      updated_at: issue.data.updated_at,
    });
  }
  fs.mkdirSync('artifacts', { recursive: true });
  fs.writeFileSync(
    path.join('artifacts', 'ci_failures_snapshot.json'),
    JSON.stringify({ generated_at: new Date().toISOString(), issues }, null, 2),
  );
  core.info(`Snapshot written with ${issues.length} open failure issues.`);
}

function parsePullNumber(value) {
  const pr = Number(value || 0);
  return Number.isFinite(pr) && pr > 0 ? pr : null;
}

async function applyCiFailureLabel({ github, context, core, prNumber, label }) {
  const pr = parsePullNumber(prNumber ?? process.env.PR_NUMBER);
  if (!pr) {
    core.info('No PR number detected; skipping ci-failure label application.');
    return;
  }

  const { owner, repo } = context.repo;
  const targetLabel = label || 'ci-failure';
  try {
    await github.rest.issues.addLabels({ owner, repo, issue_number: pr, labels: [targetLabel] });
    core.info(`Applied ${targetLabel} label to PR #${pr}.`);
  } catch (error) {
    if (error?.status === 422) {
      core.info(`${targetLabel} label already present on PR #${pr}.`);
    } else {
      throw error;
    }
  }
}

async function removeCiFailureLabel({ github, context, core, prNumber, label }) {
  const pr = parsePullNumber(prNumber ?? process.env.PR_NUMBER);
  if (!pr) {
    core.info('No PR number detected; skipping ci-failure label removal.');
    return;
  }

  const { owner, repo } = context.repo;
  const targetLabel = label || 'ci-failure';
  try {
    await github.rest.issues.removeLabel({ owner, repo, issue_number: pr, name: targetLabel });
    core.info(`Removed ${targetLabel} label from PR #${pr}.`);
  } catch (error) {
    if (error?.status === 404) {
      core.info(`${targetLabel} label not present on PR #${pr}.`);
    } else {
      throw error;
    }
  }
}

async function ensureAutofixComment({ github, context, core }) {
  const prNumber = parsePullNumber(process.env.PR_NUMBER);
  const headShaRaw = (process.env.HEAD_SHA || '').trim();
  if (!prNumber || !headShaRaw) {
    core.info('Autofix comment prerequisites missing; skipping.');
    return;
  }

  const headShaLower = headShaRaw.toLowerCase();
  const fileListRaw = process.env.FILE_LIST || '';
  const gateUrl = (process.env.GATE_RUN_URL || '').trim();
  const rerunTriggered = /^true$/i.test(process.env.GATE_RERUN_TRIGGERED || '');
  const runId = context.payload?.workflow_run?.id;

  const markerParts = [`head=${headShaLower}`];
  if (runId) {
    markerParts.push(`run=${runId}`);
  }
  const marker = `<!-- autofix-meta: ${markerParts.join(' ')} -->`;

  const { owner, repo } = context.repo;
  const comments = await github.paginate(github.rest.issues.listComments, {
    owner,
    repo,
    issue_number: prNumber,
    per_page: 100,
  });

  const existing = comments.find(comment => {
    const body = (comment.body || '').toLowerCase();
    if (!body.includes('<!-- autofix-meta:')) {
      return false;
    }
    return body.includes(`head=${headShaLower}`);
  });

  if (existing) {
    core.info(`Autofix comment already present for head ${headShaLower}; skipping.`);
    return;
  }

  const files = fileListRaw
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
  const fileLines = [];
  const MAX_FILES = 30;
  for (const [index, file] of files.entries()) {
    if (index >= MAX_FILES) {
      fileLines.push(`- _${files.length - MAX_FILES} more file(s) omitted_`);
      break;
    }
    fileLines.push(`- \`${file}\``);
  }
  if (!fileLines.length) {
    fileLines.push('- _None reported_');
  }

  const shortSha = headShaRaw.slice(0, 12) || headShaLower.slice(0, 12);
  const lines = [
    marker,
    '### Autofix applied',
    '',
    `* Commit: \`${shortSha}\``,
  ];

  if (gateUrl) {
    lines.push(`* Gate rerun: [View Gate run](${gateUrl})`);
  } else if (rerunTriggered) {
    lines.push('* Gate rerun: triggered (awaiting URL)');
  } else {
    lines.push('* Gate rerun: not triggered');
  }

  lines.push('');
  lines.push('**Files touched**');
  lines.push('');
  lines.push(...fileLines);
  lines.push('');
  lines.push('_Posted automatically by Gate summary._');

  const body = lines.join('\n');
  await github.rest.issues.createComment({ owner, repo, issue_number: prNumber, body });
  core.info(`Posted autofix comment for PR #${prNumber} (${shortSha}).`);
}

module.exports = {
  discoverWorkflowRuns,
  propagateGateCommitStatus,
  resolveAutofixContext,
  inspectFailingJobs,
  evaluateAutofixRerunGuard,
  ensureAutofixComment,
  updateFailureTracker,
  resolveFailureIssuesForRecoveredPR,
  autoHealFailureIssues,
  snapshotFailureIssues,
  applyCiFailureLabel,
  removeCiFailureLabel,
};
