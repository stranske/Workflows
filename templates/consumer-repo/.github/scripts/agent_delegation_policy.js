const { rateLimitExpired } = require('./rate_limit_receipt');

/**
 * Agent Delegation Policy
 *
 * System-driven policy for agent:auto label routing between Codex and Claude.
 * Determines which agent should run based on effectiveness metrics, prerequisites,
 * and anti-thrashing rules.
 *
 * See: docs/plans/phase-5d-delegation-policy.md
 */

/** Default Orchestrator route-weights export URL (overridable via ROUTE_WEIGHTS_URL). */
const DEFAULT_ROUTE_WEIGHTS_URL = (
  typeof process !== 'undefined' &&
  process.env &&
  process.env.ROUTE_WEIGHTS_URL
) ? process.env.ROUTE_WEIGHTS_URL : (
  'https://raw.githubusercontent.com/stranske/Orchestrator/exports/route-weights/config/route-weights.json'
);

const ROUTE_WEIGHTS_SCHEMA = 'orchestrator.route-weights/v1';
const ROUTE_WEIGHTS_SCHEMAS = new Set([
  'orchestrator.route-weights/v1',
  'orchestrator.route-weights/v2',
]);
const ROUTE_WEIGHTS_MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;
const ROUTE_WEIGHTS_MAX_CLOCK_SKEW_MS = 60 * 1000;
const ROUTE_WEIGHTS_FETCH_TIMEOUT_MS = 5000;

/**
 * Keepalive round kind → Orchestrator route-weights task type.
 *
 * - PR implementation-style rounds (`implement`, `run`, `fix`, `conflict`) → `implement`
 * - PR review rounds (`review`) → `review`
 * - PR test-writing rounds (`testgen`) → `testgen`
 * @type {Record<string, string>}
 */
const ROUTE_WEIGHT_TASK_TYPES = {
  implement: 'implement',
  run: 'implement',
  fix: 'implement',
  conflict: 'implement',
  review: 'review',
  testgen: 'testgen',
};

/**
 * Resolve the keepalive round kind used to look up a route-weights task type.
 *
 * `state.last_action` (the keepalive step: run/fix/conflict/review/wait/...)
 * never itself takes the value `testgen` — test-writing work is signalled by
 * the issue/PR `testgen` label instead (see docs/LABELS.md task-type
 * precedence). Without checking the label first, a testgen-labelled PR would
 * always be misclassified as `implement` when consulting route-weights.
 *
 * @param {Object} [options]
 * @param {Array<string>} [options.labels] - Normalized (lowercase) PR labels
 * @param {Object} [options.state] - Keepalive state
 * @returns {string}
 */
function resolveRoundKind({ labels = [], state = {} } = {}) {
  const normalizedLabels = labels.map((label) => String(label).toLowerCase());
  if (normalizedLabels.includes('testgen')) {
    return 'testgen';
  }
  return state.last_action || state.pending_action || 'implement';
}

/**
 * Check whether a route-weights document is within the freshness window.
 *
 * @param {Object|null|undefined} document
 * @param {Date|number|string} [now]
 * @returns {boolean}
 */
function isRouteWeightsFresh(document, now) {
  if (!document || typeof document !== 'object') {
    return false;
  }
  const referenceTime = now instanceof Date ? now.getTime() : new Date(now || Date.now()).getTime();
  if (!Number.isFinite(referenceTime)) {
    return false;
  }
  const generatedAt = Date.parse(document.generated_at || '');
  if (
    !Number.isFinite(generatedAt) ||
    referenceTime - generatedAt > ROUTE_WEIGHTS_MAX_AGE_MS ||
    generatedAt - referenceTime > ROUTE_WEIGHTS_MAX_CLOCK_SKEW_MS
  ) {
    return false;
  }
  return true;
}

/**
 * Fetch and validate the Orchestrator route-weights export. Never throws.
 *
 * @param {Object} [options]
 * @param {string} [options.url]
 * @param {typeof fetch} [options.fetchImpl]
 * @param {Date|number|string} [options.now]
 * @returns {Promise<Object|null>}
 */
async function loadRouteWeights({ url = DEFAULT_ROUTE_WEIGHTS_URL, fetchImpl, now } = {}) {
  const fetchFn = fetchImpl || (typeof fetch === 'function' ? fetch : null);
  if (!fetchFn || !url) {
    return null;
  }

  const referenceTime = now instanceof Date ? now.getTime() : new Date(now || Date.now()).getTime();
  if (!Number.isFinite(referenceTime)) {
    return null;
  }

  let timeoutId;

  try {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    let timedOut = false;

    const fetchPromise = Promise.resolve()
      .then(() => fetchFn(url, controller ? { signal: controller.signal } : undefined))
      // Prevent unhandled rejection if the timeout “wins” the race.
      .catch(() => null);

    const timeoutPromise = new Promise((resolve) => {
      timeoutId = setTimeout(() => {
        timedOut = true;
        if (controller) {
          try {
            controller.abort();
          } catch {
            // Ignore abort errors; treat it as timeout failure.
          }
        }
        resolve(null);
      }, ROUTE_WEIGHTS_FETCH_TIMEOUT_MS);
    });

    const response = await Promise.race([fetchPromise, timeoutPromise]);
    if (timedOut || !response || response.status !== 200) {
      return null;
    }

    let document;
    try {
      document = await response.json();
    } catch {
      return null;
    }

    if (!document || !ROUTE_WEIGHTS_SCHEMAS.has(document.schema)) {
      return null;
    }

    if (!isRouteWeightsFresh(document, referenceTime)) {
      return null;
    }

    return document;
  } catch {
    return null;
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }
}

/**
 * Fetch the Orchestrator route-weights export for intake and delegation callers.
 *
 * @param {Object} [options]
 * @returns {Promise<Object|null>}
 */
async function fetchRouteWeights(options = {}) {
  return loadRouteWeights(options);
}

/**
 * Return the reserved agent names for a route-weights task type.
 *
 * The export currently stores reservations by task type as rows, while an
 * array of strings is accepted for backward-compatible fixtures and exports.
 *
 * @param {Object|Array|string[]|undefined} reserve
 * @param {string} taskType
 * @returns {string[]}
 */
function getRouteWeightReserveAgents(reserve, taskType) {
  const entries = Array.isArray(reserve)
    ? reserve
    : (Array.isArray(reserve?.[taskType]) ? reserve[taskType] : []);

  return entries
    .map((entry) => (typeof entry === 'string' ? entry : entry?.agent))
    .filter(Boolean)
    .map((agent) => String(agent).toLowerCase());
}

/**
 * Deterministic unit interval draw for exploration routing (tests pass an explicit seed).
 *
 * @param {number} seed
 * @returns {number}
 */
function explorationDraw(seed) {
  // Seed 0 is the empty-state fallback; map it away so a zero seed cannot force
  // exploration for every positive rate (draw(0) would otherwise be exactly 0).
  let t = (Number(seed) >>> 0) || 0xa5a5a5a5;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

/**
 * Stable exploration draw seed from keepalive state (PR + iteration).
 *
 * @param {Object} [state]
 * @returns {number}
 */
function explorationSeedFromState(state = {}) {
  const pr = Number(state.pr_number) || 0;
  const iteration = Number(state.iteration) || 0;
  return Math.imul(pr, 10007) + iteration;
}

/**
 * @param {Object} options
 * @returns {{ agent: string|null, delegationSource: 'route_weights'|'route_weights_exploration'|'static', staticReason?: string, policy_version?: string }}
 */
function selectAgentFromRouteWeights({
  routeWeights,
  taskType,
  currentAgent,
  availableAgents,
  agents,
  reserve = routeWeights?.reserve,
  seed,
}) {
  const reserveSet = new Set(getRouteWeightReserveAgents(reserve, taskType));
  const taskEntry = routeWeights?.task_types?.[taskType];
  const normalizedCurrentAgent = String(currentAgent || '').toLowerCase();

  if (!routeWeights || !taskEntry || taskEntry.evidence_ok !== true) {
    return {
      agent: null,
      delegationSource: 'static',
      staticReason: !routeWeights ? 'route-weights-unavailable' : 'route-weights-insufficient-evidence',
    };
  }

  const exploration = routeWeights.exploration;
  const explorationRate = Number(exploration?.rate);
  if (exploration && Number.isFinite(explorationRate) && explorationRate > 0) {
    const draw = explorationDraw(seed ?? 0);
    if (draw < explorationRate) {
      const challenger = String(exploration.challengers?.[taskType] || '').toLowerCase();
      if (
        challenger &&
        challenger !== normalizedCurrentAgent &&
        !reserveSet.has(challenger) &&
        availableAgents.includes(challenger) &&
        hasKeepaliveRunner(agents[challenger])
      ) {
        return {
          agent: challenger,
          delegationSource: 'route_weights_exploration',
          policy_version: exploration.policy_version,
        };
      }
    }
  }

  const ranking = Array.isArray(taskEntry.ranking) ? taskEntry.ranking : [];
  for (const row of ranking) {
    const candidate = String(row?.agent || '').toLowerCase();
    if (!candidate || candidate === normalizedCurrentAgent || reserveSet.has(candidate)) {
      continue;
    }
    if (!availableAgents.includes(candidate)) {
      continue;
    }
    if (!hasKeepaliveRunner(agents[candidate])) {
      continue;
    }
    return { agent: candidate, delegationSource: 'route_weights' };
  }

  return {
    agent: null,
    delegationSource: 'static',
    staticReason: 'route-weights-no-eligible-agent',
  };
}

/**
 * Decide which agent should run next round
 *
 * @param {Object} options
 * @param {Object} options.state - Current keepalive state with delegation history
 * @param {Array<string>} options.labels - PR labels (strings)
 * @param {Object} options.secrets - Available secrets (keys present = available)
 * @param {Object} options.registry - Agent registry (from agent_registry.js)
 * @param {string[]} [options.runnableAgents] - Agents with runners in the current tree
 * @param {Object|null} [options.routeWeights] - Preloaded route-weights document
 * @param {string} [options.roundKind='implement'] - Keepalive round kind for task-type mapping
 * @param {Object} [options.core] - GitHub Actions core for logging
 * @returns {Object} - { agent, reason, shouldSwitch, alternatives, delegationSource }
 */
function decideNextAgent({
  state = {},
  completion = null,
  labels = [],
  secrets = {},
  registry = {},
  runnableAgents,
  routeWeights = null,
  roundKind = 'implement',
  core,
}) {
  const agents = registry.agents || {};
  const defaultAgent = registry.default_agent || 'codex';

  // Check if agent:auto is present
  const hasAutoLabel = labels.some((label) => normalizeLabel(label) === 'agent:auto');

  // If no agent:auto, use explicit agent labels or default
  if (!hasAutoLabel) {
    const explicitAgent = getExplicitAgentFromLabels(labels, agents);
    return {
      agent: explicitAgent || defaultAgent,
      reason: explicitAgent ? 'explicit-label' : 'default',
      shouldSwitch: false,
      alternatives: [],
      delegationSource: 'static',
    };
  }

  // agent:auto is present - run delegation logic
  core?.info?.('agent:auto detected - running delegation policy');

  const explicitAgents = getExplicitAgentsFromLabels(labels, agents);
  if (explicitAgents.length > 1) {
    core?.warning?.(`Multiple concrete agent labels are invalid: ${explicitAgents.join(', ')}`);
    return {
      agent: '',
      reason: 'multiple-agent-labels',
      shouldSwitch: false,
      alternatives: [],
      delegationSource: 'static',
    };
  }

  const currentAgent = state.current_agent ||
    (completion?.completion?.reason === 'rate_limited' ? completion.provider : '');
  const expired = rateLimitExpired(completion);
  const rateLimited = !expired && completion?.completion?.reason === 'rate_limited' &&
    completion.provider === currentAgent;
  const lastSwitchIteration = state.last_switch_iteration || 0;
  const currentIteration = state.iteration || 0;
  const switchCount = state.switch_count || 0;
  const history = state.effectiveness_history || [];

  // Check prerequisites for all agents
  const agentPrereqs = {};
  for (const [agentKey, agentConfig] of Object.entries(agents)) {
    agentPrereqs[agentKey] = checkPrerequisites({
      agent: agentKey,
      agentConfig,
      secrets,
      core,
    });
  }

  const taskType = ROUTE_WEIGHT_TASK_TYPES[roundKind] || ROUTE_WEIGHT_TASK_TYPES.implement;
  const ranking = Array.isArray(routeWeights?.task_types?.[taskType]?.ranking)
    ? routeWeights.task_types[taskType].ranking : [];

  // Receipts survive a later provider failure; route exports can still report
  // that provider's pool as healthy. Only expiry or loader-observed progress
  // drains this persisted backoff, including before a current agent is chosen.
  const activeRateLimited = new Set((completion?.rate_limit_receipts || [])
    .filter((record) => record?.completion?.reason === 'rate_limited' &&
      !rateLimitExpired(record))
    .map((record) => record.provider));

  // Initial selection has no completion to trigger the rate-limit switch path.
  // Apply pool availability before concrete-label, weighted and default choices.
  const availableAgents = Object.keys(agents).filter((key) => (
    agentPrereqs[key].available && hasKeepaliveRunner(agents[key]) &&
    !activeRateLimited.has(key) &&
    (!Array.isArray(runnableAgents) || runnableAgents.includes(key)) &&
    (currentAgent || getAgentPoolState(
      routeWeights, key, ranking.find((row) => row?.agent === key),
    ) === 'ok')
  ));

  if (availableAgents.length === 0) {
    core?.warning?.('No agents available (prerequisites, runners or pool capacity)');
    return {
      agent: '',
      reason: rateLimited ? 'rate-limited-no-alternatives' : 'no-agents-available',
      shouldSwitch: false,
      alternatives: [],
      delegationSource: 'static',
    };
  }

  // Time alone reopens an exhausted provider gate; dispatch does not drain it.
  if (expired && availableAgents.includes(completion.provider)) {
    core?.info?.(`rate_limited receipt expired; ${completion.provider} eligible`);
    return { agent: completion.provider, reason: 'rate-limit-receipt-expired',
      shouldSwitch: currentAgent !== completion.provider, previousAgent: currentAgent,
      alternatives: availableAgents.filter(agent => agent !== completion.provider),
      delegationSource: 'static' };
  }

  // If no current agent, preserve an explicit opener choice first, then use
  // evidence-bearing route weights, and finally fall back to the registry
  // default. The explicit label intentionally ignores reserve because it is
  // the seat that opened the PR; agent:auto governs subsequent delegation.
  if (!currentAgent) {
    const explicitAgent = getExplicitAgentFromLabels(labels, agents);
    if (explicitAgent && availableAgents.includes(explicitAgent)) {
      core?.info?.(`Initial agent selection from concrete label: ${explicitAgent}`);
      return {
        agent: explicitAgent,
        reason: 'initial-selection-label',
        shouldSwitch: false,
        alternatives: availableAgents.filter((agent) => agent !== explicitAgent),
        delegationSource: 'static',
      };
    }

    const weighted = selectAgentFromRouteWeights({
      routeWeights,
      taskType,
      currentAgent: '',
      availableAgents,
      agents,
      reserve: routeWeights?.reserve,
      seed: explorationSeedFromState(state),
    });
    if (weighted.agent) {
      const sourceLabel = weighted.delegationSource || 'route_weights';
      core?.info?.(`Initial agent selection from route weights: ${weighted.agent} (${sourceLabel})`);
      if (weighted.policy_version) {
        core?.info?.(`Route-weights policy version: ${weighted.policy_version}`);
      }
      return {
        agent: weighted.agent,
        reason: 'initial-selection-route-weights',
        shouldSwitch: false,
        alternatives: availableAgents.filter((agent) => agent !== weighted.agent),
        delegationSource: sourceLabel,
        policy_version: weighted.policy_version,
      };
    }

    const initialAgent = availableAgents.includes(defaultAgent) ? defaultAgent : availableAgents[0];
    core?.info?.(`Initial agent selection: ${initialAgent}`);
    return {
      agent: initialAgent,
      reason: 'initial-selection',
      shouldSwitch: false,
      alternatives: availableAgents.filter((a) => a !== initialAgent),
      delegationSource: 'static',
    };
  }

  if (!rateLimited && !availableAgents.includes(currentAgent)) {
    const nextAgent = availableAgents.includes(defaultAgent) ? defaultAgent : availableAgents[0];
    core?.info?.(`Switching from unavailable ${currentAgent} to ${nextAgent}`);
    return {
      agent: nextAgent,
      reason: `${currentAgent}-unavailable`,
      shouldSwitch: true,
      previousAgent: currentAgent,
      alternatives: availableAgents.filter((agent) => agent !== nextAgent),
      delegationSource: 'static',
    };
  }

  // Current agent exists - check if we should continue or switch
  const effectiveness = calculateEffectiveness({ history, lookbackRounds: 3, core });
  const stall = detectStall({ history, threshold: 2, core });
  const roundsSinceSwitch = currentIteration - lastSwitchIteration;
  const inCooldown = roundsSinceSwitch < 5;

  core?.debug?.(`Effectiveness: ${JSON.stringify(effectiveness)}`);
  core?.debug?.(`Stall: ${stall}, Cooldown: ${inCooldown}, Rounds since switch: ${roundsSinceSwitch}`);

  // Rule: Continue if effective
  if (!rateLimited && effectiveness.effective) {
    return {
      agent: currentAgent,
      reason: `effective (${effectiveness.summary})`,
      shouldSwitch: false,
      alternatives: availableAgents.filter((a) => a !== currentAgent),
      delegationSource: 'static',
    };
  }

  // Rule: Continue if in cooldown (anti-thrash)
  if (!rateLimited && inCooldown) {
    return {
      agent: currentAgent,
      reason: `cooldown (${5 - roundsSinceSwitch} rounds remaining)`,
      shouldSwitch: false,
      alternatives: availableAgents.filter((a) => a !== currentAgent),
      delegationSource: 'static',
    };
  }

  // Rule: Switch if stalled
  if (rateLimited || stall.isStalled) {
    const tried = new Set(labels.map(normalizeLabel)
      .filter((label) => label.startsWith('agents:tried-'))
      .map((label) => label.slice('agents:tried-'.length)));
    const alternatives = availableAgents.filter((agent) => agent !== currentAgent &&
      !tried.has(agent) && (!rateLimited || getAgentPoolState(
        routeWeights, agent, ranking.find((row) => row.agent === agent),
      ) === 'ok'));
    const reservedAgents = new Set(getRouteWeightReserveAgents(routeWeights?.reserve, taskType));
    const weighted = selectAgentFromRouteWeights({
      routeWeights: rateLimited && routeWeights ? { ...routeWeights, exploration: null } : routeWeights,
      taskType,
      currentAgent,
      availableAgents: alternatives,
      agents,
      reserve: routeWeights?.reserve,
      seed: explorationSeedFromState(state),
    });

    // A valid evidence-bearing export may never be bypassed to select one of
    // its explicitly reserved seats. The ordinary static fallback remains
    // unchanged when the export is absent or lacks sufficient evidence.
    const eligibleStaticAlternatives = routeWeights?.task_types?.[taskType]?.evidence_ok === true
      ? alternatives.filter((agent) => !reservedAgents.has(String(agent).toLowerCase()))
      : alternatives;
    const nextAgent = weighted.agent || eligibleStaticAlternatives[0] || currentAgent;
    const delegationSource = weighted.agent ? weighted.delegationSource : 'static';

    const sourceSuffix =
      delegationSource === 'route_weights' || delegationSource === 'route_weights_exploration'
        ? `delegation_source: ${delegationSource}`
        : `delegation_source: static (${weighted.staticReason || 'preference-order'})`;

    if (nextAgent === currentAgent) {
      core?.warning?.('Stalled but no alternative agents available');
      return {
        agent: rateLimited ? '' : currentAgent,
        reason: rateLimited ? 'rate-limited-no-alternatives' : `stalled-no-alternatives (${sourceSuffix})`,
        shouldSwitch: false,
        alternatives: [],
        delegationSource,
      };
    }
    core?.info?.(`Switching from ${currentAgent} to ${nextAgent} due to ${rateLimited ? 'rate limit' : 'stall'} (${sourceSuffix})`);
    if (weighted.policy_version) {
      core?.info?.(`Route-weights policy version: ${weighted.policy_version}`);
    }
    return {
      agent: nextAgent,
      reason: rateLimited
        ? `${currentAgent}-rate-limited (${sourceSuffix})`
        : `${currentAgent}-stalled (${stall.reason}; ${sourceSuffix})`,
      shouldSwitch: true,
      previousAgent: currentAgent,
      alternatives: alternatives.filter((a) => a !== nextAgent),
      delegationSource,
      policy_version: weighted.policy_version,
    };
  }

  // Default: Continue with current agent
  return {
    agent: currentAgent,
    reason: 'continue-current',
    shouldSwitch: false,
    alternatives: availableAgents.filter((a) => a !== currentAgent),
    delegationSource: 'static',
  };
}

function hasKeepaliveRunner(agentConfig = {}) {
  return Boolean(agentConfig.runner_workflow) && agentConfig.enabled !== false &&
    agentConfig.capabilities?.pr_keepalive === true;
}

/**
 * Check if prerequisites are met for an agent to run
 *
 * @param {Object} options
 * @param {string} options.agent - Agent key (codex, claude, etc.)
 * @param {Object} options.agentConfig - Agent config from registry
 * @param {Object} options.secrets - Available secrets
 * @param {Object} [options.core] - GitHub Actions core for logging
 * @returns {Object} - { available, reason }
 */
function checkPrerequisites({ agent, agentConfig, secrets, core }) {
  if (agentConfig.enabled === false) {
    core?.debug?.(`Agent ${agent} disabled in registry`);
    return {
      available: false,
      reason: 'agent-disabled',
    };
  }

  const requiredSecrets = agentConfig.required_secrets || [];
  const mode = agentConfig.required_secrets_mode || 'all';

  if (mode === 'any') {
    // At least one of the listed secrets must be present
    const hasAny = requiredSecrets.some((key) => !!secrets[key]);
    if (!hasAny && requiredSecrets.length > 0) {
      core?.debug?.(
        `Agent ${agent} missing all secrets (need at least one): ${requiredSecrets.join(', ')}`
      );
      return {
        available: false,
        reason: 'missing-any-required-secret',
      };
    }
  } else {
    // Check if all required secrets are present
    for (const secretKey of requiredSecrets) {
      if (!secrets[secretKey]) {
        core?.debug?.(`Agent ${agent} missing secret: ${secretKey}`);
        return {
          available: false,
          reason: `missing-secret-${secretKey}`,
        };
      }
    }
  }

  return {
    available: true,
    reason: 'prerequisites-met',
  };
}

/**
 * Calculate effectiveness score for current agent
 *
 * @param {Object} options
 * @param {Array<Object>} options.history - Effectiveness history (last N rounds)
 * @param {number} [options.lookbackRounds=3] - How many rounds to analyze
 * @param {Object} [options.core] - GitHub Actions core for logging
 * @returns {Object} - { effective, commits, tasks, gatePassed, summary }
 */
function calculateEffectiveness({ history = [], lookbackRounds = 3, core }) {
  const recentRounds = history.slice(-lookbackRounds);

  if (recentRounds.length === 0) {
    return {
      effective: false,
      commits: 0,
      tasks: 0,
      gatePassed: false,
      summary: 'no history',
    };
  }

  const commits = recentRounds.reduce((sum, round) => sum + (round.commits || 0), 0);
  const tasks = recentRounds.reduce((sum, round) => sum + (round.tasks || 0), 0);
  const gatePassed = recentRounds.some((round) => round.gate === 'pass');

  // Agent is effective only when it produced verified forward motion:
  // - Completed at least 1 task in the lookback window, OR
  // - Made commits and has a green Gate signal in the lookback window.
  // Bare commits with no checkbox progress and a non-green Gate are churn, not
  // progress; otherwise an agent can commit indefinitely without advancing
  // acceptance criteria or CI and never trip delegation.
  const effective = tasks >= 1 || (commits >= 1 && gatePassed);

  const summary = [
    commits > 0 ? `${commits} commits` : null,
    tasks > 0 ? `${tasks} tasks` : null,
    gatePassed ? 'gate passed' : null,
  ]
    .filter(Boolean)
    .join(', ') || 'no progress';

  core?.debug?.(`Effectiveness (last ${lookbackRounds} rounds): ${summary}`);

  return {
    effective,
    commits,
    tasks,
    gatePassed,
    summary,
  };
}

/**
 * Detect stall condition (consecutive rounds with no progress)
 *
 * @param {Object} options
 * @param {Array<Object>} options.history - Effectiveness history
 * @param {number} [options.threshold=2] - How many consecutive rounds qualify as stalled
 * @param {Object} [options.core] - GitHub Actions core for logging
 * @returns {Object} - { isStalled, consecutiveRounds, reason }
 */
function detectStall({ history = [], threshold = 2, core }) {
  if (history.length < threshold) {
    return {
      isStalled: false,
      consecutiveRounds: history.length,
      reason: 'insufficient-history',
    };
  }

  // Count consecutive rounds with no progress from the end
  let consecutiveNoProgress = 0;
  for (let i = history.length - 1; i >= 0; i--) {
    const round = history[i];
    // Progress = real forward motion only. A commit-less green Gate must NOT
    // reset the consecutive-no-progress counter, otherwise a stuck agent that
    // keeps a green Gate while making zero commits never trips the stall
    // threshold and `agent:auto` delegation can never switch (#2268).
    const hasProgress =
      (round.tasks || 0) > 0 ||
      ((round.commits || 0) > 0 && round.gate === 'pass');

    if (hasProgress) {
      break; // Found progress, stop counting
    }
    consecutiveNoProgress++;
  }

  const isStalled = consecutiveNoProgress >= threshold;

  if (isStalled) {
    core?.warning?.(`Stall detected: ${consecutiveNoProgress} consecutive rounds with no progress`);
  }

  return {
    isStalled,
    consecutiveRounds: consecutiveNoProgress,
    reason: isStalled ? `${consecutiveNoProgress} rounds, no progress` : 'progress-detected',
  };
}

/**
 * Get explicit agent from labels (agent:codex, agent:claude, etc.)
 * Skips agent:auto and non-routing control labels while finding a concrete agent.
 *
 * @param {Array<string>} labels - PR labels
 * @param {Object} agents - Registry agents object
 * @returns {string|null} - Agent key or null
 */
function getExplicitAgentFromLabels(labels, agents) {
  const explicitAgents = getExplicitAgentsFromLabels(labels, agents);
  return explicitAgents.length === 1 ? explicitAgents[0] : null;
}

/**
 * Get all distinct recognized concrete agents from labels.
 *
 * @param {Array<string>} labels - PR labels
 * @param {Object} agents - Registry agents object
 * @returns {Array<string>} - Distinct concrete agent keys
 */
function getExplicitAgentsFromLabels(labels, agents) {
  const agentPrefix = 'agent:';
  const agentKeys = Object.keys(agents || {});
  const explicitAgents = new Set();

  for (const label of labels) {
    const normalized = normalizeLabel(label);
    if (normalized.startsWith(agentPrefix)) {
      const agentKey = normalized.slice(agentPrefix.length);
      // Skip 'auto' and non-routing labels
      if (agentKey === 'auto' || ['needs-attention', 'rate-limited', 'retry'].includes(agentKey)) {
        continue;
      }
      if (agentKeys.includes(agentKey)) {
        explicitAgents.add(agentKey);
      }
    }
  }

  return [...explicitAgents];
}

/**
 * Normalize label for consistent comparison
 * @param {string|Object} label - Label string or {name: string}
 * @returns {string} - Normalized lowercase label
 */
function normalizeLabel(label) {
  if (typeof label === 'object' && label.name) {
    return String(label.name || '').trim().toLowerCase();
  }
  return String(label || '').trim().toLowerCase();
}

/**
 * Format delegation decision for PR comment display
 *
 * @param {Object} decision - Decision from decideNextAgent()
 * @param {Object} effectiveness - Effectiveness from calculateEffectiveness()
 * @param {Object} state - Current keepalive state
 * @returns {string} - Markdown formatted summary
 */
function formatDelegationSummary({ decision, effectiveness, state = {} }) {
  const switchHistory = state.delegation_log || [];
  const lastSwitch = switchHistory[switchHistory.length - 1];
  const switchCount = state.switch_count || 0;
  const roundsSinceSwitch = (state.iteration || 0) - (state.last_switch_iteration || 0);

  const lines = [];
  lines.push('## Agent Selection (auto mode)');
  lines.push('');
  lines.push(`**Chosen:** ${decision.agent}`);
  lines.push(`**Reason:** ${decision.reason}`);
  if (decision.delegationSource) {
    lines.push(`**Delegation source:** ${decision.delegationSource}`);
  }
  if (decision.policy_version) {
    lines.push(`**Policy version:** ${decision.policy_version}`);
  }

  if (decision.alternatives && decision.alternatives.length > 0) {
    lines.push(`**Alternatives considered:** ${decision.alternatives.join(', ')} (not selected: ${decision.reason})`);
  }

  if (effectiveness) {
    lines.push('');
    lines.push('**Effectiveness Metrics:**');
    lines.push(`- Commits (last 3 rounds): ${effectiveness.commits || 0}`);
    lines.push(`- Tasks completed (last 3 rounds): ${effectiveness.tasks || 0}`);
    lines.push(`- Gate status: ${effectiveness.gatePassed ? 'pass' : 'not passed'}`);
    lines.push(`- Overall: ${effectiveness.summary}`);
  }

  if (switchCount > 0) {
    lines.push('');
    lines.push('**Switch History:**');
    lines.push(`- Total switches: ${switchCount}`);
    if (lastSwitch) {
      const switchReason = lastSwitch.reason || 'unknown';
      const switchFrom = lastSwitch.previous_agent || 'unknown';
      const switchTo = lastSwitch.chosen_agent || 'unknown';
      lines.push(`- Last switch: Round ${lastSwitch.iteration} (${switchFrom} → ${switchTo}, reason: ${switchReason})`);
    }
    if (roundsSinceSwitch < 5) {
      lines.push(`- Cooldown remaining: ${5 - roundsSinceSwitch} rounds`);
    }
  }

  return lines.join('\n');
}

/**
 * Lightweight helper for tests and CLI checks of route-weights exploration routing.
 *
 * @param {Object} options
 * @returns {ReturnType<typeof selectAgentFromRouteWeights>}
 */
function pickAgent({
  taskType = 'implement',
  routeWeights,
  seed = 0,
  currentAgent = '',
  availableAgents,
  agents,
}) {
  const registryAgents = agents || {
    codex: { runner_workflow: '.github/workflows/reusable-codex-run.yml', capabilities: { pr_keepalive: true } },
    claude: { runner_workflow: '.github/workflows/reusable-claude-run.yml', capabilities: { pr_keepalive: true } },
    cursor: { runner_workflow: '.github/workflows/reusable-cursor-run.yml', capabilities: { pr_keepalive: true } },
    muse: { runner_workflow: '.github/workflows/reusable-muse-run.yml', capabilities: { pr_keepalive: true } },
    gemini: { runner_workflow: '.github/workflows/reusable-gemini-run.yml', capabilities: { pr_keepalive: true } },
  };
  const eligible = availableAgents || Object.keys(registryAgents);
  return selectAgentFromRouteWeights({
    routeWeights,
    taskType,
    currentAgent,
    availableAgents: eligible,
    agents: registryAgents,
    reserve: routeWeights?.reserve,
    seed,
  });
}

function hasIntakeRunner(agentConfig = {}) {
  if (!agentConfig || typeof agentConfig !== 'object') {
    return false;
  }
  if (agentConfig.enabled === false || agentConfig.preflight?.enabled === false) {
    return false;
  }
  if (agentConfig.capabilities && agentConfig.capabilities.pr_keepalive === false) {
    return false;
  }
  return Boolean(agentConfig.runner_workflow || agentConfig.runner);
}

function getAgentPoolState(routeWeights, agent, row) {
  const key = String(agent || '').trim().toLowerCase();
  const candidates = [
    row?.pool_state,
    row?.poolState,
    row?.capacity?.state,
    row?.capacity_state,
    row?.state,
    routeWeights?.capacity?.[key]?.state,
    typeof routeWeights?.capacity?.[key] === 'string' ? routeWeights.capacity[key] : undefined,
    routeWeights?.pools?.[key]?.state,
    typeof routeWeights?.pools?.[key] === 'string' ? routeWeights.pools[key] : undefined,
    routeWeights?.pool_capacity?.[key]?.state,
    typeof routeWeights?.pool_capacity?.[key] === 'string' ? routeWeights.pool_capacity[key] : undefined,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate.trim().toLowerCase();
    }
  }
  // Until Orchestrator#645 publishes capacity in schema v2, treat every pool as ok.
  return 'ok';
}

function makeIntakeDecision({
  agent,
  posterior = null,
  poolState = 'static',
  delegationSource = 'static',
  reason = 'static-default',
}) {
  const result = {
    agent,
    posterior,
    poolState,
    pool_state: poolState,
    delegationSource,
    reason,
  };
  Object.defineProperties(result, {
    toString: {
      value() {
        return this.agent;
      },
      enumerable: false,
    },
    valueOf: {
      value() {
        return this.agent;
      },
      enumerable: false,
    },
  });
  return result;
}

/**
 * Choose an intake agent from route weights and pool capacity.
 *
 * Returns the first agent in posterior order whose registry entry has a runner
 * and whose pool state is `ok`, or falls back to the static default (`codex`)
 * when route weights are absent, stale, or yield no eligible candidate.
 *
 * @param {string|Object} [taskType='implement']
 * @param {Object|null} [routeWeights=null]
 * @param {Object} [registryAgents={}]
 * @param {Object} [options={}]
 * @returns {{ agent: string, posterior: number|null, poolState: string, pool_state: string, delegationSource: 'route_weights'|'static', reason: string }}
 */
function chooseAgentForIntake(taskType = 'implement', routeWeights = null, registryAgents = {}, options = {}) {
  if (taskType && typeof taskType === 'object' && !Array.isArray(taskType)) {
    const opts = taskType;
    return chooseAgentForIntake(
      opts.taskType || 'implement',
      opts.routeWeights ?? null,
      opts.registryAgents || opts.agents || opts.registry || {},
      opts
    );
  }

  const normalizedTaskType =
    ROUTE_WEIGHT_TASK_TYPES[taskType] || String(taskType || 'implement').trim().toLowerCase() || 'implement';
  const agentsMap = (
    registryAgents &&
    typeof registryAgents === 'object' &&
    registryAgents.agents &&
    typeof registryAgents.agents === 'object'
  )
    ? registryAgents.agents
    : (registryAgents || {});
  const defaultAgent = String(
    options?.defaultAgent ||
    (registryAgents && typeof registryAgents.default_agent === 'string' && registryAgents.default_agent) ||
    'codex'
  ).trim().toLowerCase() || 'codex';

  if (!routeWeights || typeof routeWeights !== 'object') {
    return makeIntakeDecision({
      agent: defaultAgent,
      reason: 'route-weights-unavailable',
    });
  }

  if (routeWeights.schema !== undefined && !ROUTE_WEIGHTS_SCHEMAS.has(routeWeights.schema)) {
    return makeIntakeDecision({
      agent: defaultAgent,
      reason: 'route-weights-invalid-schema',
    });
  }

  if (routeWeights.generated_at !== undefined && !isRouteWeightsFresh(routeWeights, options?.now)) {
    return makeIntakeDecision({
      agent: defaultAgent,
      reason: 'route-weights-stale',
    });
  }

  const taskEntry = routeWeights.task_types?.[normalizedTaskType] || routeWeights.task_types?.[taskType];
  if (!taskEntry || taskEntry.evidence_ok !== true) {
    return makeIntakeDecision({
      agent: defaultAgent,
      reason: taskEntry?.evidence_ok === false
        ? 'route-weights-insufficient-evidence'
        : 'route-weights-evidence-not-affirmed',
    });
  }

  const reserveSet = new Set(getRouteWeightReserveAgents(routeWeights.reserve, normalizedTaskType));
  const ranking = Array.isArray(taskEntry.ranking) ? taskEntry.ranking : [];
  const orderedRanking = ranking
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const postA = Number(a.row?.posterior);
      const postB = Number(b.row?.posterior);
      const validA = Number.isFinite(postA);
      const validB = Number.isFinite(postB);
      if (validA && validB && postB !== postA) {
        return postB - postA;
      }
      if (validA !== validB) {
        return validA ? -1 : 1;
      }
      return a.index - b.index;
    })
    .map((entry) => entry.row);

  for (const row of orderedRanking) {
    const candidate = String(row?.agent || '').trim().toLowerCase();
    if (!candidate || reserveSet.has(candidate)) {
      continue;
    }
    if (!hasIntakeRunner(agentsMap[candidate])) {
      continue;
    }
    const poolState = getAgentPoolState(routeWeights, candidate, row);
    if (poolState !== 'ok') {
      continue;
    }
    const posterior = Number.isFinite(Number(row?.posterior)) ? Number(row.posterior) : null;
    return makeIntakeDecision({
      agent: candidate,
      posterior,
      poolState,
      delegationSource: 'route_weights',
      reason: 'route-weights',
    });
  }

  return makeIntakeDecision({
    agent: defaultAgent,
    reason: 'route-weights-no-eligible-agent',
  });
}

module.exports = {
  DEFAULT_ROUTE_WEIGHTS_URL,
  ROUTE_WEIGHT_TASK_TYPES,
  resolveRoundKind,
  loadRouteWeights,
  fetchRouteWeights,
  chooseAgentForIntake,
  explorationDraw,
  explorationSeedFromState,
  selectAgentFromRouteWeights,
  pickAgent,
  getRouteWeightReserveAgents,
  decideNextAgent,
  checkPrerequisites,
  calculateEffectiveness,
  detectStall,
  getExplicitAgentFromLabels,
  formatDelegationSummary,
  hasKeepaliveRunner,
};
