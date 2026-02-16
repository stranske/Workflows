'use strict';

const fs = require('node:fs');

function stripTrailingComment(rawLine) {
  const line = String(rawLine ?? '');
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('#')) {
    return '';
  }

  // Keep this intentionally simple: our registry YAML should not rely on inline comments.
  const match = line.match(/^(.*?)(\s+#.*)?$/);
  return (match?.[1] ?? line).replace(/\s+$/, '');
}

function parseScalar(value) {
  const raw = String(value ?? '').trim();
  if (!raw) {
    return '';
  }

  if (raw === 'true') {
    return true;
  }
  if (raw === 'false') {
    return false;
  }

  if (/^-?\d+$/.test(raw)) {
    return Number(raw);
  }

  const quoted = raw.match(/^(['"])(.*)\1$/);
  if (quoted) {
    return quoted[2];
  }

  return raw;
}

function countIndent(line) {
  // Match all leading horizontal whitespace (spaces and tabs).
  const match = String(line).match(/^([ \t]*)/);
  const indentPrefix = match?.[1] ?? '';
  if (indentPrefix.includes('\t')) {
    throw new Error('Registry YAML must use spaces only (tabs are not allowed)');
  }
  if (indentPrefix.length % 2 !== 0) {
    throw new Error(
      `Registry YAML indentation must be multiples of 2 spaces (got ${indentPrefix.length})`,
    );
  }
  return indentPrefix.length;
}

function findNextMeaningfulLine(lines, startIndex) {
  for (let index = startIndex; index < lines.length; index += 1) {
    const stripped = stripTrailingComment(lines[index]);
    if (!stripped.trim()) {
      continue;
    }
    return {
      index,
      indent: countIndent(stripped),
      trimmed: stripped.trim(),
    };
  }
  return null;
}

// Minimal YAML parser for the registry file.
// Supported features:
// - nested mappings via indentation (2 spaces)
// - scalar values (strings, booleans, integers)
// - sequences using "- item" lines (scalar items only)
// Unsupported (intentionally): anchors, multiline strings, flow maps, complex quoting.
function parseRegistryYaml(text) {
  const rawLines = String(text ?? '').split(/\r?\n/);
  const lines = rawLines.map(stripTrailingComment);

  const root = {};
  const stack = [{ indent: -1, container: root }];

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const rawLine = lines[lineIndex];
    if (!rawLine.trim()) {
      continue;
    }

    const indent = countIndent(rawLine);
    const trimmed = rawLine.trim();

    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) {
      stack.pop();
    }

    const parent = stack[stack.length - 1].container;

    if (trimmed.startsWith('- ')) {
      if (!Array.isArray(parent)) {
        throw new Error(`Unexpected list item at line ${lineIndex + 1}; parent is not a list`);
      }
      parent.push(parseScalar(trimmed.slice(2)));
      continue;
    }

    const sepIndex = trimmed.indexOf(':');
    if (sepIndex <= 0) {
      throw new Error(`Invalid registry YAML line ${lineIndex + 1}: expected "key: value"`);
    }

    const key = trimmed.slice(0, sepIndex).trim();
    const rest = trimmed.slice(sepIndex + 1).trim();

    if (!key) {
      throw new Error(`Invalid registry YAML line ${lineIndex + 1}: empty key`);
    }
    if (typeof parent !== 'object' || parent === null || Array.isArray(parent)) {
      throw new Error(`Invalid registry YAML line ${lineIndex + 1}: cannot assign key under a list`);
    }

    if (rest) {
      parent[key] = parseScalar(rest);
      continue;
    }

    const next = findNextMeaningfulLine(lines, lineIndex + 1);
    const shouldBeList = Boolean(next && next.indent > indent && next.trimmed.startsWith('- '));
    const child = shouldBeList ? [] : {};
    parent[key] = child;
    stack.push({ indent, container: child });
  }

  return root;
}

function loadAgentRegistry({ registryPath } = {}) {
  const path = registryPath || '.github/agents/registry.yml';
  const raw = fs.readFileSync(path, 'utf8');
  const registry = parseRegistryYaml(raw);
  if (!registry || typeof registry !== 'object') {
    throw new Error('Agent registry did not parse into an object');
  }
  if (!registry.agents || typeof registry.agents !== 'object') {
    throw new Error('Agent registry missing required "agents" mapping');
  }
  if (!registry.default_agent || typeof registry.default_agent !== 'string') {
    throw new Error('Agent registry missing required "default_agent" string');
  }
  return registry;
}

function normalizeLabel(label) {
  if (!label) {
    return '';
  }
  if (typeof label === 'string') {
    return label.trim().toLowerCase();
  }
  if (typeof label === 'object' && typeof label.name === 'string') {
    return label.name.trim().toLowerCase();
  }
  return '';
}

function resolveAgentFromLabels(labels, { registryPath } = {}) {
  const registry = loadAgentRegistry({ registryPath });
  const labelList = Array.isArray(labels) ? labels : [];
  const agentLabels = labelList
    .map(normalizeLabel)
    .filter(Boolean)
    .filter((value) => value.startsWith('agent:'));

  const uniqueAgents = new Set(agentLabels.map((value) => value.slice('agent:'.length)));

  if (uniqueAgents.size > 1) {
    throw new Error(`Multiple agent labels present: ${Array.from(uniqueAgents).join(', ')}`);
  }

  const explicit = Array.from(uniqueAgents)[0];
  const agentKey = explicit || registry.default_agent;
  if (!registry.agents[agentKey]) {
    const known = Object.keys(registry.agents).sort();
    throw new Error(`Unknown agent key: ${agentKey}. Known agents: ${known.join(', ') || '(none)'}`);
  }
  return agentKey;
}

function getAgentConfig(agentKey, { registryPath } = {}) {
  const registry = loadAgentRegistry({ registryPath });
  const key = String(agentKey || '').trim() || registry.default_agent;
  const config = registry.agents[key];
  if (!config) {
    const known = Object.keys(registry.agents).sort();
    throw new Error(`Unknown agent key: ${key}. Known agents: ${known.join(', ') || '(none)'}`);
  }
  return config;
}

function getRunnerWorkflow(agentKey, { registryPath } = {}) {
  const config = getAgentConfig(agentKey, { registryPath });
  const workflow = String(config.runner_workflow || '').trim();
  if (!workflow) {
    throw new Error(`Agent config missing runner_workflow for agent: ${agentKey}`);
  }
  return workflow;
}

module.exports = {
  getAgentConfig,
  getRunnerWorkflow,
  loadAgentRegistry,
  parseRegistryYaml,
  resolveAgentFromLabels,
};
