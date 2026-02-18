'use strict';

const crypto = require('crypto');

function makeTrace() {
  const timestamp = Date.now().toString(36);
  const random = crypto.randomBytes(5).toString('base64').replace(/[^a-zA-Z0-9]/g, '').slice(0, 6);
  const suffix = random.toLowerCase().padEnd(6, '0');
  const trace = `${timestamp}${suffix}`.slice(0, 16);
  return trace.toLowerCase();
}

function escapeForRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function _resolveDefaultAgent() {
  try {
    const { loadAgentRegistry } = require('./agent_registry.js');
    const reg = loadAgentRegistry();
    return reg.default_agent || 'codex';
  } catch (_) { return 'codex'; }
}

function ensureAgentPreface(body, agentAlias) {
  const trimmed = body.replace(/\r\n/g, '\n').trim();
  if (!trimmed) {
    throw new Error('Keepalive instruction body is required.');
  }

  const alias = String(agentAlias || '').trim() || _resolveDefaultAgent();
  const aliasPattern = new RegExp(`^@${escapeForRegex(alias)}\b`, 'i');
  if (aliasPattern.test(trimmed)) {
    return trimmed;
  }

  let remainder = trimmed;
  const leadingMention = remainder.match(/^@\S+/);
  if (leadingMention) {
    remainder = remainder.slice(leadingMention[0].length).trimStart();
  }

  if (!remainder) {
    throw new Error('Keepalive instruction body is required.');
  }

  return `@${alias} ${remainder}`;
}

function renderInstruction({ round, trace, body, agent }) {
  const parsedRound = Number.parseInt(round, 10);
  if (!Number.isFinite(parsedRound) || parsedRound <= 0) {
    throw new Error('Keepalive round must be a positive integer.');
  }
  const normalisedTrace = String(trace || '').trim();
  if (!normalisedTrace) {
    throw new Error('Keepalive trace token is required.');
  }
  const instructionBody = ensureAgentPreface(String(body ?? ''), agent);
  // NOTE: These HTML comment markers are API contracts embedded in existing PR
  // bodies. Do NOT rename them — keepalive_gate.js, pr_meta_keepalive, and
  // consumers all match on the exact `codex-keepalive-*` prefix.
  const lines = [
    '<!-- codex-keepalive-marker -->',
    `<!-- codex-keepalive-round: ${parsedRound} -->`,
    `<!-- codex-keepalive-trace: ${normalisedTrace} -->`,
    instructionBody,
  ];
  return `${lines.join('\n')}\n`;
}

module.exports = {
  makeTrace,
  renderInstruction,
};
