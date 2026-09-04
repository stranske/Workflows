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

    if (!document || document.schema !== ROUTE_WEIGHTS_SCHEMA) {
      return null;
    }

    const generatedAt = Date.parse(document.generated_at || '');
    if (
      !Number.isFinite(generatedAt) ||
      referenceTime - generatedAt > ROUTE_WEIGHTS_MAX_AGE_MS ||
      generatedAt - referenceTime > ROUTE_WEIGHTS_MAX_CLOCK_SKEW_MS
    ) {
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
 * @param {Object} options
 * @returns {{ agent: string|null, delegationSource: 'route_weights'|'static', staticReason?: string }}
 */
function selectAgentFromRouteWeights({
  routeWeights,
  taskType,
  currentAgent,
  availableAgents,
  agents,
  reserve = routeWeights?.reserve,
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
    };
  }

  // agent:auto is present - run delegation logic
  core?.info?.('agent:auto detected - running delegation policy');

  const currentAgent = state.current_agent || '';
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

  // Filter to available agents
  const availableAgents = Object.keys(agents).filter((key) => (
    agentPrereqs[key].available && hasKeepaliveRunner(agents[key]) &&
    (!Array.isArray(runnableAgents) || runnableAgents.includes(key))
  ));

  if (availableAgents.length === 0) {
    core?.warning?.('No agents available (missing secrets)');
    return {
      agent: '',
      reason: 'no-agents-available',
      shouldSwitch: false,
      alternatives: [],
    };
  }

  // If no current agent, select default if available
  if (!currentAgent) {
    const initialAgent = availableAgents.includes(defaultAgent) ? defaultAgent : availableAgents[0];
    core?.info?.(`Initial agent selection: ${initialAgent}`);
    return {
      agent: initialAgent,
      reason: 'initial-selection',
      shouldSwitch: false,
      alternatives: availableAgents.filter((a) => a !== initialAgent),
    };
  }

  if (!availableAgents.includes(currentAgent)) {
    const nextAgent = availableAgents.includes(defaultAgent) ? defaultAgent : availableAgents[0];
    core?.info?.(`Switching from unavailable ${currentAgent} to ${nextAgent}`);
    return {
      agent: nextAgent,
      reason: `${currentAgent}-unavailable`,
      shouldSwitch: true,
      previousAgent: currentAgent,
      alternatives: availableAgents.filter((agent) => agent !== nextAgent),
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
  if (effectiveness.effective) {
    return {
      agent: currentAgent,
      reason: `effective (${effectiveness.summary})`,
      shouldSwitch: false,
      alternatives: availableAgents.filter((a) => a !== currentAgent),
    };
  }

  // Rule: Continue if in cooldown (anti-thrash)
  if (inCooldown) {
    return {
      agent: currentAgent,
      reason: `cooldown (${5 - roundsSinceSwitch} rounds remaining)`,
      shouldSwitch: false,
      alternatives: availableAgents.filter((a) => a !== currentAgent),
    };
  }

  // Rule: Switch if stalled
  if (stall.isStalled) {
    const alternatives = availableAgents.filter((a) => a !== currentAgent);
    const taskType = ROUTE_WEIGHT_TASK_TYPES[roundKind] || ROUTE_WEIGHT_TASK_TYPES.implement;
    const reservedAgents = new Set(getRouteWeightReserveAgents(routeWeights?.reserve, taskType));
    const weighted = selectAgentFromRouteWeights({
      routeWeights,
      taskType,
      currentAgent,
      availableAgents,
      agents,
      reserve: routeWeights?.reserve,
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
      delegationSource === 'route_weights'
        ? 'delegation_source: route_weights'
        : `delegation_source: static (${weighted.staticReason || 'preference-order'})`;

    if (nextAgent === currentAgent) {
      core?.warning?.('Stalled but no alternative agents available');
      return {
        agent: currentAgent,
        reason: `stalled-no-alternatives (${sourceSuffix})`,
        shouldSwitch: false,
        alternatives: [],
        delegationSource: 'static',
      };
    }
    core?.info?.(`Switching from ${currentAgent} to ${nextAgent} due to stall (${sourceSuffix})`);
    return {
      agent: nextAgent,
      reason: `${currentAgent}-stalled (${stall.reason}; ${sourceSuffix})`,
      shouldSwitch: true,
      previousAgent: currentAgent,
      alternatives: alternatives.filter((a) => a !== nextAgent),
      delegationSource,
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
 * Returns null if agent:auto is present (auto mode takes precedence)
 *
 * @param {Array<string>} labels - PR labels
 * @param {Object} agents - Registry agents object
 * @returns {string|null} - Agent key or null
 */
function getExplicitAgentFromLabels(labels, agents) {
  const agentPrefix = 'agent:';
  const agentKeys = Object.keys(agents || {});

  for (const label of labels) {
    const normalized = normalizeLabel(label);
    if (normalized.startsWith(agentPrefix)) {
      const agentKey = normalized.slice(agentPrefix.length);
      // Skip 'auto' and non-routing labels
      if (agentKey === 'auto' || ['needs-attention', 'rate-limited', 'retry'].includes(agentKey)) {
        continue;
      }
      if (agentKeys.includes(agentKey)) {
        return agentKey;
      }
    }
  }

  return null;
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

module.exports = {
  DEFAULT_ROUTE_WEIGHTS_URL,
  ROUTE_WEIGHT_TASK_TYPES,
  resolveRoundKind,
  loadRouteWeights,
  selectAgentFromRouteWeights,
  getRouteWeightReserveAgents,
  decideNextAgent,
  checkPrerequisites,
  calculateEffectiveness,
  detectStall,
  getExplicitAgentFromLabels,
  formatDelegationSummary,
  hasKeepaliveRunner,
};
