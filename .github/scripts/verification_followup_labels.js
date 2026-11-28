'use strict';

// Single definition of the labels a verification follow-up issue is created with.
// Used by both agents-80-pr-event-hub.yml (verify_to_issue) and
// agents-verify-to-issue-v2.yml, so the two cannot drift again. The hub used to
// apply the retired Auto-Pilot label plus `from:verification`, which intake skipped, so its
// follow-ups were never picked up.
//
// Labels: `follow-up`, the agent that produced the PR (`agent:<key>` and
// `from:<key>`), and `agents:optimize` so the optimizer formats the issue and
// intake/the opener can start an agent on it.

const DEFAULT_REGISTRY_PATH = './.github/agents/registry.yml';
const FALLBACK_AGENT = 'codex';

function resolveAgentKey(prLabels, { registryPath = DEFAULT_REGISTRY_PATH, warn = () => {} } = {}) {
  let defaultAgent = FALLBACK_AGENT;
  const registryModule = require('./agent_registry.js');
  try {
    const registry = registryModule.loadAgentRegistry({ registryPath });
    defaultAgent = registry.default_agent || FALLBACK_AGENT;
  } catch (_) {
    // The registry is optional here; fall back to the built-in default.
  }
  let agentKey = defaultAgent;
  try {
    agentKey = registryModule.resolveAgentFromLabels(prLabels || [], { registryPath });
  } catch (error) {
    warn(`Failed to resolve agent from PR labels; defaulting to ${defaultAgent}: ${error.message}`);
    agentKey = defaultAgent;
  }
  return String(agentKey || defaultAgent).trim().toLowerCase() || defaultAgent;
}

function buildVerificationFollowupLabels(prLabels, options = {}) {
  const agent = resolveAgentKey(prLabels, options);
  return ['follow-up', `agent:${agent}`, `from:${agent}`, 'agents:optimize'];
}

module.exports = { buildVerificationFollowupLabels, resolveAgentKey };
