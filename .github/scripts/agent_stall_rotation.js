'use strict';

/**
 * Agent stall rotation
 *
 * When auto-pilot's stall handler is about to escalate a stuck issue to
 * `needs-human`, this decides whether to first rotate to a DIFFERENT eligible
 * agent (bounded) and try again. It is registry- and capability-driven — it never
 * hard-codes an agent list — so it uses whatever agents the registry marks capable
 * for the relevant lane (e.g. `belt` for create-PR, `pr_keepalive` for monitor-PR),
 * and it extends automatically as more agents gain those capabilities.
 *
 * Bounded by construction: the current (stalled) agent is recorded as "tried" (via a
 * label), so each rotation shrinks the candidate set; once every eligible agent has
 * been tried, rotation stops and the caller escalates to `needs-human` as before.
 *
 * Pure decision logic (no I/O) so it is unit-testable; the workflow performs the
 * resulting label/dispatch side effects.
 */

const TRIED_PREFIX = 'agents:tried-';

function normalizeLabel(label) {
  if (label && typeof label === 'object' && label.name) {
    return String(label.name).trim().toLowerCase();
  }
  return String(label || '').trim().toLowerCase();
}

/**
 * Agents that may run a given lane: enabled in the registry, carrying the required
 * capability, and — when a secrets map is supplied — having their required secrets.
 */
function eligibleAgents({ registry = {}, capability = null, secrets = null } = {}) {
  const agents = registry.agents || {};
  const eligible = [];
  for (const [key, config] of Object.entries(agents)) {
    if (!config || config.enabled === false) {
      continue;
    }
    if (capability) {
      const capabilities = config.capabilities || {};
      if (capabilities[capability] !== true) {
        continue;
      }
    }
    if (secrets) {
      const required = config.required_secrets || [];
      const mode = config.required_secrets_mode || 'all';
      const present =
        mode === 'any'
          ? required.length === 0 || required.some((secret) => Boolean(secrets[secret]))
          : required.every((secret) => Boolean(secrets[secret]));
      if (!present) {
        continue;
      }
    }
    eligible.push(key);
  }
  return eligible;
}

function currentAgentFromLabels(labels, agentKeys) {
  for (const label of labels) {
    const normalized = normalizeLabel(label);
    if (normalized.startsWith('agent:')) {
      const key = normalized.slice('agent:'.length);
      if (key !== 'auto' && agentKeys.includes(key)) {
        return key;
      }
    }
  }
  return '';
}

function triedAgentsFromLabels(labels) {
  const tried = new Set();
  for (const label of labels) {
    const normalized = normalizeLabel(label);
    if (normalized.startsWith(TRIED_PREFIX)) {
      tried.add(normalized.slice(TRIED_PREFIX.length));
    }
  }
  return tried;
}

/**
 * Decide the stall response.
 *
 * @returns {{
 *   rotate: boolean,
 *   currentAgent: string,
 *   nextAgent: string,
 *   triedMarker: string,
 *   remaining: string[],
 *   reason: string,
 * }}
 * When `rotate` is true the caller should: add `agent:<nextAgent>` (removing
 * `agent:<currentAgent>`), add `triedMarker`, withhold `needs-human`, and re-dispatch.
 * When false, escalate to `needs-human` (every eligible agent has been tried, or none
 * are eligible).
 */
function decideStallRotation({
  registry = {},
  labels = [],
  capability = null,
  secrets = null,
} = {}) {
  const agents = registry.agents || {};
  const agentKeys = Object.keys(agents);
  const eligible = eligibleAgents({ registry, capability, secrets });
  const current = currentAgentFromLabels(labels, agentKeys) || registry.default_agent || '';
  const tried = triedAgentsFromLabels(labels);
  // The agent that just stalled is, by definition, tried.
  if (current) {
    tried.add(current);
  }
  const remaining = eligible.filter((agent) => !tried.has(agent));
  const triedMarker = current ? `${TRIED_PREFIX}${current}` : '';

  if (remaining.length === 0) {
    return {
      rotate: false,
      currentAgent: current,
      nextAgent: '',
      triedMarker,
      remaining: [],
      reason: eligible.length === 0 ? 'no-eligible-agents' : 'all-eligible-agents-tried',
    };
  }

  const nextAgent = remaining[0];
  return {
    rotate: true,
    currentAgent: current,
    nextAgent,
    triedMarker,
    remaining: remaining.slice(1),
    reason: `rotate ${current || '(none)'} -> ${nextAgent} (${remaining.length} untried)`,
  };
}

module.exports = {
  TRIED_PREFIX,
  decideStallRotation,
  eligibleAgents,
  currentAgentFromLabels,
  triedAgentsFromLabels,
};
