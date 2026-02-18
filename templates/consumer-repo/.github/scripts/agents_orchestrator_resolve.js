'use strict';

const { makeTrace } = require('./keepalive_contract.js');
const { getKeepaliveInstructionWithMention } = require('./keepalive_instruction_template.js');
const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

const DEFAULT_READINESS_AGENTS = 'copilot,codex';
const DEFAULT_VERIFY_ISSUE_ASSIGNEES =
  'copilot,chatgpt-codex-connector,stranske-automation-bot';

// Resolve default agent from registry (falls back to 'codex')
let _defaultAgentKey = 'codex';
try {
  const { loadAgentRegistry } = require('./agent_registry.js');
  const registry = loadAgentRegistry();
  _defaultAgentKey = registry.default_agent || 'codex';
} catch (_) { /* registry not available — use codex default */ }

// Instruction loaded from .github/templates/keepalive-instruction.md
const DEFAULT_KEEPALIVE_INSTRUCTION = getKeepaliveInstructionWithMention(_defaultAgentKey);
const DEFAULT_OPTIONS_JSON = '{}';
const KEEPALIVE_PAUSE_LABEL = 'keepalive:paused';

const DEFAULTS = {
  enable_readiness: 'false',
  readiness_agents: DEFAULT_READINESS_AGENTS,
  readiness_custom_logins: '',
  require_all: 'false',
  enable_preflight: 'false',
  codex_user: '',
  codex_command_phrase: '',
  enable_verify_issue: 'false',
  verify_issue_number: '',
  verify_issue_valid_assignees: DEFAULT_VERIFY_ISSUE_ASSIGNEES,
  enable_watchdog: 'true',
  enable_keepalive: 'true',
  enable_bootstrap: 'false',
  bootstrap_issues_label: `agent:${_defaultAgentKey}`,
  draft_pr: 'false',
  diagnostic_mode: 'off',
  options_json: DEFAULT_OPTIONS_JSON,
  dry_run: 'false',
  dispatcher_force_issue: '',
  worker_max_parallel: '2',
  conveyor_max_merges: '2',
  keepalive_max_retries: '5',
};

const toString = (value, fallback = '') => {
  if (value === undefined || value === null) {
    return fallback;
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean).join(',');
  }
  return String(value);
};

const toBoolString = (value, fallback) => {
  const candidate = value === undefined ? fallback : value;
  if (typeof candidate === 'boolean') {
    return candidate ? 'true' : 'false';
  }
  if (typeof candidate === 'number') {
    return candidate !== 0 ? 'true' : 'false';
  }
  if (typeof candidate === 'string') {
    const norm = candidate.trim().toLowerCase();
    if (['true', '1', 'yes', 'y', 'on'].includes(norm)) {
      return 'true';
    }
    if (['false', '0', 'no', 'n', 'off', ''].includes(norm)) {
      return 'false';
    }
  }
  return fallback === 'true' || fallback === true ? 'true' : 'false';
};

const toCsv = (value, fallback = '') => {
  if (value === undefined || value === null) {
    return fallback;
  }
  const raw = Array.isArray(value)
    ? value
    : typeof value === 'string'
      ? value.split(',')
      : [];
  const cleaned = raw
    .map((entry) => String(entry).trim())
    .filter(Boolean);
  if (!cleaned.length) {
    return fallback;
  }
  return cleaned.join(',');
};

const nested = (value) => (value && typeof value === 'object' ? value : {});

const toBoundedIntegerString = (value, fallback, bounds = {}) => {
  const { min, max } = bounds;
  const fallbackNumber = Number(fallback);
  let candidate = Number(value);
  if (!Number.isFinite(candidate)) {
    candidate = Number.isFinite(fallbackNumber) ? fallbackNumber : 0;
  }
  if (Number.isFinite(min) && candidate < min) {
    candidate = min;
  }
  if (Number.isFinite(max) && candidate > max) {
    candidate = max;
  }
  if (!Number.isFinite(candidate)) {
    candidate = 0;
  }
  return String(Math.max(0, Math.floor(candidate)));
};

const sanitiseOptions = (core, value) => {
  if (value === undefined || value === null || value === '') {
    return DEFAULT_OPTIONS_JSON;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return DEFAULT_OPTIONS_JSON;
    }
    try {
      const parsed = JSON.parse(trimmed);
      return JSON.stringify(parsed);
    } catch (error) {
      core.warning(`options_json is not valid JSON (${error.message}); using default.`);
      return DEFAULT_OPTIONS_JSON;
    }
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch (error) {
      core.warning(`options_json could not be serialised (${error.message}); using default.`);
      return DEFAULT_OPTIONS_JSON;
    }
  }
  return DEFAULT_OPTIONS_JSON;
};

const summarise = (value) => {
  const text = String(value ?? '');
  const limit = 120;
  const separator = ' … ';
  if (text.length <= limit) {
    return text;
  }
  const available = limit - separator.length;
  const headLen = Math.ceil(available / 2);
  const tailLen = Math.floor(available / 2);
  const head = text.slice(0, headLen).trimEnd();
  const tail = text.slice(-tailLen).trimStart();
  return `${head}${separator}${tail}`;
};

const normalisePullRequestCandidates = (pullRequests) => {
  if (!Array.isArray(pullRequests)) {
    return [];
  }
  return pullRequests
    .map((pr) => {
      const rawNumber = pr?.number;
      const number = Number.parseInt(rawNumber, 10);
      if (!Number.isFinite(number)) {
        return null;
      }
      const state = typeof pr?.state === 'string' ? pr.state.trim().toLowerCase() : '';
      const headSha = toString(pr?.head?.sha || '', '');
      let updatedAt = Number.NaN;
      if (typeof pr?.updated_at === 'string' && pr.updated_at.trim()) {
        const parsed = Date.parse(pr.updated_at);
        if (!Number.isNaN(parsed)) {
          updatedAt = parsed;
        }
      }
      return {
        number,
        state,
        headSha,
        updatedAt,
      };
    })
    .filter(Boolean);
};

const choosePullRequestNumber = (pullRequests, { headSha = '', allowClosed = true } = {}) => {
  const candidates = normalisePullRequestCandidates(pullRequests);
  const usable = allowClosed
    ? candidates
    : candidates.filter((entry) => !entry.state || entry.state === 'open');

  if (!usable.length) {
    return '';
  }

  const prefer = headSha
    ? usable.filter((entry) => entry.headSha && entry.headSha === headSha)
    : [];
  const pool = prefer.length ? prefer : usable;

  let chosen = pool[0];
  for (const entry of pool) {
    if (Number.isFinite(entry.updatedAt) && (!Number.isFinite(chosen.updatedAt) || entry.updatedAt > chosen.updatedAt)) {
      chosen = entry;
    }
  }

  return chosen ? String(chosen.number) : '';
};

async function resolveOrchestratorParams({ github, context, core, env = process.env }) {
  let user = {};
  try {
    const parsed = JSON.parse(env.PARAMS_JSON || '{}');
    if (parsed && typeof parsed === 'object') {
      user = parsed;
    }
  } catch (error) {
    core.warning(`Bad params_json; using defaults. Parse error: ${error.message}`);
  }

  const merged = { ...DEFAULTS, ...user };

  const workflowDryRun = env.WORKFLOW_DRY_RUN;
  if (workflowDryRun !== undefined && workflowDryRun !== null && workflowDryRun !== '') {
    merged.dry_run = workflowDryRun;
  }

  const workflowOptionsJson = env.WORKFLOW_OPTIONS_JSON;
  if (workflowOptionsJson !== undefined && workflowOptionsJson !== null && workflowOptionsJson.trim() !== '') {
    merged.options_json = workflowOptionsJson;
  }

  const workflowKeepaliveEnabled = env.WORKFLOW_KEEPALIVE_ENABLED;
  if (workflowKeepaliveEnabled !== undefined && workflowKeepaliveEnabled !== null && workflowKeepaliveEnabled !== '') {
    merged.enable_keepalive = workflowKeepaliveEnabled;
  }

  const workflowKeepalivePr = env.WORKFLOW_KEEPALIVE_PR;
  if (workflowKeepalivePr !== undefined && workflowKeepalivePr !== null && workflowKeepalivePr !== '') {
    merged.keepalive_pr = workflowKeepalivePr;
  }

  const readinessAgents = toCsv(merged.readiness_agents, DEFAULTS.readiness_agents);
  const readinessCustom = toCsv(
    merged.readiness_custom_logins ?? merged.readiness_custom ?? merged.custom_logins,
    DEFAULTS.readiness_custom_logins
  );
  const codexUser = toString(merged.codex_user, DEFAULTS.codex_user);
  const codexCommand = toString(merged.codex_command_phrase, DEFAULTS.codex_command_phrase);
  const verifyIssueNumber = toString(merged.verify_issue_number, DEFAULTS.verify_issue_number).trim();
  const verifyIssueAssignees = toCsv(
    merged.verify_issue_valid_assignees ?? merged.valid_assignees,
    DEFAULT_VERIFY_ISSUE_ASSIGNEES
  );

  const bootstrap = nested(merged.bootstrap);
  const keepalive = nested(merged.keepalive);

  const dryRun = toBoolString(merged.dry_run, DEFAULTS.dry_run);

  const diagnosticModeRaw = toString(merged.diagnostic_mode, DEFAULTS.diagnostic_mode).trim().toLowerCase();
  const diagnosticMode = ['full', 'dry-run'].includes(diagnosticModeRaw) ? diagnosticModeRaw : 'off';

  const enableVerifyIssue = toBoolString(
    merged.enable_verify_issue,
    verifyIssueNumber !== '' ? 'true' : DEFAULTS.enable_verify_issue
  );

  const optionsSource = merged.options_json ?? merged.options ?? DEFAULT_OPTIONS_JSON;
  const sanitisedOptions = sanitiseOptions(core, optionsSource);

  let parsedOptions = {};
  try {
    parsedOptions = JSON.parse(sanitisedOptions);
  } catch (error) {
    core.warning(`options_json could not be parsed (${error.message}); using defaults.`);
  }

  const { owner, repo } = context.repo;

  // Inject default keepalive instruction if not already present
  // Also detect if this orchestrator run was triggered by the Gate workflow
  const triggeredByGate = context.eventName === 'workflow_run';

  let workflowRunPr = '';
  if (triggeredByGate) {
    const runPayload = context.payload?.workflow_run;
    if (runPayload) {
      const pullRequests = Array.isArray(runPayload.pull_requests) ? runPayload.pull_requests : [];
      const headSha = toString(runPayload.head_sha || '', '').trim();
      const headBranch = toString(runPayload.head_branch || '', '').trim();
      const headRepoOwner = toString(runPayload.head_repository?.owner?.login || owner, owner).trim();

      const directMatch = choosePullRequestNumber(pullRequests, { headSha, allowClosed: false });
      if (directMatch) {
        workflowRunPr = directMatch;
      }

      if (!workflowRunPr && headSha) {
        try {
          const associated = await github.paginate(
            github.rest.repos.listPullRequestsAssociatedWithCommit,
            {
              owner,
              repo,
              commit_sha: headSha,
              per_page: 100,
            }
          );
          const matched = choosePullRequestNumber(associated, { headSha, allowClosed: false });
          if (matched) {
            workflowRunPr = matched;
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          core.warning(`Unable to map workflow_run head ${headSha} to pull request: ${message}`);
        }
      }

      if (!workflowRunPr && headBranch) {
        try {
          const pullsByBranch = await github.paginate(github.rest.pulls.list, {
            owner,
            repo,
            state: 'open',
            per_page: 100,
            head: `${headRepoOwner}:${headBranch}`,
          });
          const matched = choosePullRequestNumber(pullsByBranch, { headSha, allowClosed: false });
          if (matched) {
            workflowRunPr = matched;
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          core.warning(`Unable to map workflow_run head branch ${headBranch} to pull request: ${message}`);
        }
      }

      if (!workflowRunPr) {
        const displayTitle = toString(runPayload.display_title || '', '');
        const titleMatch = displayTitle.match(/#(\d+)/);
        if (titleMatch && Number.isFinite(Number.parseInt(titleMatch[1], 10))) {
          const prNumber = Number.parseInt(titleMatch[1], 10);
          try {
            const prResponse = await github.rest.pulls.get({
              owner,
              repo,
              pull_number: prNumber,
            });
            if (prResponse && prResponse.data && prResponse.data.state === 'open') {
              workflowRunPr = String(prNumber);
            } else {
              core.info(`PR #${prNumber} extracted from display_title is not open or does not exist.`);
            }
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            core.info(`PR #${prNumber} extracted from display_title could not be validated: ${message}`);
          }
        }
      }
    }
  }

  const finalParsedOptions = {
    ...parsedOptions,
    ...( (!parsedOptions.keepalive_instruction && !parsedOptions.keepalive_instruction_template)
          ? { keepalive_instruction: DEFAULT_KEEPALIVE_INSTRUCTION }
          : {} ),
    ...(triggeredByGate ? { triggered_by_gate: true } : {})
  };

  if (workflowRunPr && !finalParsedOptions.pr) {
    finalParsedOptions.pr = workflowRunPr;
  }

  // Re-serialize with injected defaults
  const finalOptionsJson = JSON.stringify(finalParsedOptions);

  const beltOptions = nested(parsedOptions.belt ?? parsedOptions.codex_belt);
  const dispatcherOptions = nested(beltOptions.dispatcher ?? parsedOptions.dispatcher);
  const workerOptions = nested(beltOptions.worker ?? parsedOptions.worker);
  const conveyorOptions = nested(beltOptions.conveyor ?? parsedOptions.conveyor);

  let keepaliveTrace = toString(
    finalParsedOptions.keepalive_trace ?? parsedOptions.keepalive_trace,
    ''
  ).trim();
  let keepaliveRound = toString(
    finalParsedOptions.round ?? finalParsedOptions.keepalive_round ?? parsedOptions.round ?? parsedOptions.keepalive_round,
    ''
  ).trim();
  let keepalivePr = toString(
    finalParsedOptions.pr ??
      finalParsedOptions.keepalive_pr ??
      parsedOptions.pr ??
      parsedOptions.keepalive_pr ??
      merged.keepalive_pr ??
      workflowRunPr,
    ''
  ).trim();
  if (!keepalivePr && workflowRunPr) {
    keepalivePr = workflowRunPr;
  }

  const dispatcherForceIssue = toString(
    dispatcherOptions.force_issue ?? merged.dispatcher_force_issue,
    DEFAULTS.dispatcher_force_issue
  );

  const workerMaxParallel = toBoundedIntegerString(
    keepalive.max_parallel ??
      keepalive.cap ??
      workerOptions.max_parallel ??
      workerOptions.parallel ??
      merged.worker_max_parallel,
    DEFAULTS.worker_max_parallel,
    { min: 0, max: 5 }
  );

  const conveyorMaxMerges = toBoundedIntegerString(
    conveyorOptions.max_merges ?? conveyorOptions.limit ?? merged.conveyor_max_merges,
    DEFAULTS.conveyor_max_merges,
    { min: 0, max: 5 }
  );

  const keepaliveRequested = toBoolString(
    merged.enable_keepalive ?? keepalive.enabled,
    DEFAULTS.enable_keepalive
  );

  const keepaliveMaxRetries = toBoundedIntegerString(
    keepalive.max_retries ?? merged.keepalive_max_retries ?? finalParsedOptions.keepalive_max_retries,
    DEFAULTS.keepalive_max_retries,
    { min: 1, max: 10 }
  );

  let keepalivePaused = false;

  if (keepaliveRequested === 'true') {
    try {
      await github.rest.issues.getLabel({ owner, repo, name: KEEPALIVE_PAUSE_LABEL });
      keepalivePaused = true;
      core.info(`keepalive skipped: repository label "${KEEPALIVE_PAUSE_LABEL}" is present.`);
    } catch (error) {
      if (error && error.status === 404) {
        core.info(`Keepalive pause label "${KEEPALIVE_PAUSE_LABEL}" not present; keepalive remains enabled.`);
      } else {
        const message = error instanceof Error ? error.message : String(error);
        core.warning(`Unable to resolve keepalive pause label (${message}); proceeding with keepalive.`);
      }
    }
  } else {
    core.info('Keepalive disabled via configuration; skipping pause label check.');
  }

  const keepaliveEffective = keepalivePaused ? 'false' : keepaliveRequested;
  if (!keepaliveRound && keepaliveEffective === 'true') {
    keepaliveRound = '1';
  }

  if (!keepaliveTrace && keepaliveEffective === 'true') {
    keepaliveTrace = makeTrace();
  }

  if (triggeredByGate) {
    if (keepalivePr) {
      core.info(`Keepalive workflow_run mapped to pull request #${keepalivePr}.`);
      const prNumber = Number.parseInt(keepalivePr, 10);
      if (Number.isFinite(prNumber) && github?.rest?.pulls?.get) {
        try {
          const { data: prData } = await github.rest.pulls.get({
            owner,
            repo,
            pull_number: prNumber,
          });
          const prState = toString(prData?.state, '').trim().toLowerCase();
          if (prState && prState !== 'open') {
            core.warning(`Keepalive target pull request #${keepalivePr} is ${prState}; skipping it.`);
            keepalivePr = '';
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          core.warning(`Unable to verify pull request #${keepalivePr}: ${message}`);
          keepalivePr = '';
        }
      }
    }

    if (!keepalivePr) {
      core.warning('Keepalive workflow_run payload did not include a pull request number.');
    }
  }

  const outputs = {
    enable_readiness: toBoolString(merged.enable_readiness, DEFAULTS.enable_readiness),
    readiness_agents: readinessAgents,
    readiness_custom_logins: readinessCustom,
    require_all: toBoolString(merged.require_all, DEFAULTS.require_all),
    enable_preflight: toBoolString(merged.enable_preflight, DEFAULTS.enable_preflight),
    codex_user: codexUser,
    codex_command_phrase: codexCommand,
    enable_diagnostic: diagnosticMode === 'off' ? 'false' : 'true',
    diagnostic_attempt_branch: diagnosticMode === 'full' ? 'true' : 'false',
    diagnostic_dry_run: diagnosticMode === 'full' ? 'false' : 'true',
    enable_verify_issue: enableVerifyIssue,
    verify_issue_number: verifyIssueNumber,
    verify_issue_valid_assignees: verifyIssueAssignees,
    enable_watchdog: toBoolString(merged.enable_watchdog, DEFAULTS.enable_watchdog),
    enable_keepalive: keepaliveEffective,
    keepalive_requested: keepaliveRequested,
    keepalive_paused_label: keepalivePaused ? 'true' : 'false',
    keepalive_pause_label: KEEPALIVE_PAUSE_LABEL,
  keepalive_max_retries: keepaliveMaxRetries,
    enable_bootstrap: toBoolString(merged.enable_bootstrap ?? bootstrap.enable, DEFAULTS.enable_bootstrap),
    bootstrap_issues_label: toString(
      merged.bootstrap_issues_label ?? bootstrap.label,
      DEFAULTS.bootstrap_issues_label
    ),
    draft_pr: toBoolString(merged.draft_pr, DEFAULTS.draft_pr),
    dry_run: dryRun,
    options_json: finalOptionsJson,
    dispatcher_force_issue: dispatcherForceIssue,
    worker_max_parallel: workerMaxParallel,
    conveyor_max_merges: conveyorMaxMerges,
    keepalive_trace: keepaliveTrace,
    keepalive_round: keepaliveRound,
    keepalive_pr: keepalivePr
  };

  const orderedKeys = [
    'enable_readiness',
    'readiness_agents',
    'readiness_custom_logins',
    'require_all',
    'enable_preflight',
    'codex_user',
    'codex_command_phrase',
    'enable_diagnostic',
    'diagnostic_attempt_branch',
    'diagnostic_dry_run',
    'enable_verify_issue',
    'verify_issue_number',
    'verify_issue_valid_assignees',
    'enable_watchdog',
    'enable_keepalive',
    'keepalive_requested',
    'keepalive_paused_label',
    'keepalive_pause_label',
  'keepalive_max_retries',
    'enable_bootstrap',
    'bootstrap_issues_label',
    'draft_pr',
    'dry_run',
    'options_json',
    'dispatcher_force_issue',
    'worker_max_parallel',
    'conveyor_max_merges',
    'keepalive_trace',
    'keepalive_round',
    'keepalive_pr'
  ];

  for (const key of orderedKeys) {
    if (Object.prototype.hasOwnProperty.call(outputs, key)) {
      core.setOutput(key, outputs[key]);
    }
  }

  const summary = core.summary;
  summary.addHeading('Agents orchestrator parameters');
  summary.addTable([
    [{ data: 'Parameter', header: true }, { data: 'Value', header: true }],
    ...orderedKeys.map((key) => [key, summarise(outputs[key])])
  ]);
  if (keepalivePaused) {
    summary.addRaw(`keepalive skipped because the ${KEEPALIVE_PAUSE_LABEL} label is present.`).addEOL();
  } else if (keepaliveRequested !== keepaliveEffective) {
    summary
      .addRaw('keepalive disabled via configuration overrides (input or params).')
      .addEOL();
  }
  await summary.write();

  return { outputs };
}

module.exports = {
  resolveOrchestratorParams: async function ({ github: rawGithub, context, core, env = process.env }) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env });
    return resolveOrchestratorParams({ github, context, core, env });
  },
  __internals: {
    toString,
    toBoolString,
    toCsv,
    nested,
    toBoundedIntegerString,
    sanitiseOptions,
    summarise,
    normalisePullRequestCandidates,
    choosePullRequestNumber,
    KEEPALIVE_PAUSE_LABEL,
    DEFAULTS
  }
};
