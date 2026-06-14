/**
 * Agent Delegation Policy
 *
 * System-driven policy for agent:auto label routing between Codex and Claude.
 * Determines which agent should run based on effectiveness metrics, prerequisites,
 * and anti-thrashing rules.
 *
 * See: docs/plans/phase-5d-delegation-policy.md
 */

/**
 * Decide which agent should run next round
 *
 * @param {Object} options
 * @param {Object} options.state - Current keepalive state with delegation history
 * @param {Array<string>} options.labels - PR labels (strings)
 * @param {Object} options.secrets - Available secrets (keys present = available)
 * @param {Object} options.registry - Agent registry (from agent_registry.js)
 * @param {Object} [options.core] - GitHub Actions core for logging
 * @returns {Object} - { agent, reason, shouldSwitch, alternatives }
 */
function decideNextAgent({ state = {}, labels = [], secrets = {}, registry = {}, core }) {
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
  const availableAgents = Object.keys(agents).filter((key) => agentPrereqs[key].available);

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

  // Current agent exists - check if we should continue or switch
  const effectiveness = calculateEffectiveness({ history, lookbackRounds: 3, core });
  const stall = detectStall({ history, threshold: 3, core });
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
    const nextAgent = alternatives[0] || currentAgent; // Fallback to current if no alternatives

    if (nextAgent === currentAgent) {
      core?.warning?.('Stalled but no alternative agents available');
      return {
        agent: currentAgent,
        reason: 'stalled-no-alternatives',
        shouldSwitch: false,
        alternatives: [],
      };
    }

    core?.info?.(`Switching from ${currentAgent} to ${nextAgent} due to stall`);
    return {
      agent: nextAgent,
      reason: `${currentAgent}-stalled (${stall.reason})`,
      shouldSwitch: true,
      previousAgent: currentAgent,
      alternatives: alternatives.filter((a) => a !== nextAgent),
    };
  }

  // Default: Continue with current agent
  return {
    agent: currentAgent,
    reason: 'continue-current',
    shouldSwitch: false,
    alternatives: availableAgents.filter((a) => a !== currentAgent),
  };
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

  // Agent is effective only when it produced real forward motion:
  // - Made at least 1 commit in lookback window, OR
  // - Completed at least 1 task in lookback window.
  // A green Gate with zero commits and zero tasks is NOT progress: a normal
  // `run` dispatch only happens on a green Gate (Activation Guardrail §2), so a
  // genuinely stuck agent records `gate: 'pass'` every round. Counting that as
  // effective made the stall detector unable to ever fire (#2268). `gatePassed`
  // is still returned/reported below, just not treated as progress.
  const effective = commits >= 1 || tasks >= 1;

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
 * @param {number} [options.threshold=3] - How many consecutive rounds qualify as stalled
 * @param {Object} [options.core] - GitHub Actions core for logging
 * @returns {Object} - { isStalled, consecutiveRounds, reason }
 */
function detectStall({ history = [], threshold = 3, core }) {
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
      (round.commits || 0) > 0 ||
      (round.tasks || 0) > 0;

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
  decideNextAgent,
  checkPrerequisites,
  calculateEffectiveness,
  detectStall,
  getExplicitAgentFromLabels,
  formatDelegationSummary,
};
