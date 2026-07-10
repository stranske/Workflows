'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');

const SCHEMA_VERSION = 'capability-bundle/v1';
const ALLOWED_TOP_LEVEL_KEYS = new Set([
  'schema_version',
  'capability_id',
  'version',
  'content_hash',
  'selector',
  'owner',
  'fragments',
  'gates',
  'playbooks',
  'expires_at',
  'rollback',
]);
const CAPABILITY_ID_PATTERN = /^[a-z0-9][a-z0-9._/-]*$/;
const VERSION_PATTERN = /^v?[0-9]+(\.[0-9]+){0,2}$/;
const FORBIDDEN_KEY_PATTERN = /(?:raw[_-]?prompt|credential|secret|api[_-]?key|local[_-]?weight|posterior[_-]?weight|command|control|exec)/i;

function normalise(value) {
  return String(value ?? '').trim();
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

function sha256Hex(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function bundleHashPayload(bundle) {
  const {
    content_hash: _contentHash,
    contentHash: _contentHashCamel,
    ...payload
  } = bundle || {};
  return payload;
}

function computeCapabilityBundleHash(bundle) {
  return `sha256:${sha256Hex(stableStringify(bundleHashPayload(bundle)))}`;
}

function walkForbiddenKeys(value, path = []) {
  const hits = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      hits.push(...walkForbiddenKeys(item, [...path, String(index)]));
    });
    return hits;
  }
  if (!value || typeof value !== 'object') {
    return hits;
  }
  for (const [key, child] of Object.entries(value)) {
    const childPath = [...path, key];
    if (FORBIDDEN_KEY_PATTERN.test(key)) {
      hits.push(childPath.join('.'));
    }
    hits.push(...walkForbiddenKeys(child, childPath));
  }
  return hits;
}

function asArray(value) {
  if (!value) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function requireNonEmpty(value, fieldName) {
  if (!normalise(value)) {
    throw new Error(`capability bundle missing ${fieldName}`);
  }
}

function validateCapabilityBundle(bundle, options = {}) {
  const knownCapabilities = new Set(asArray(options.knownCapabilities));
  const now = options.now instanceof Date ? options.now : new Date();

  if (!bundle || typeof bundle !== 'object' || Array.isArray(bundle)) {
    throw new Error('capability bundle must be an object');
  }
  if (normalise(bundle.schema_version) !== SCHEMA_VERSION) {
    throw new Error(`capability bundle schema_version must be ${SCHEMA_VERSION}`);
  }
  const unknownKeys = Object.keys(bundle).filter((key) => !ALLOWED_TOP_LEVEL_KEYS.has(key));
  if (unknownKeys.length > 0) {
    throw new Error(`capability bundle has unknown top-level fields: ${unknownKeys.join(', ')}`);
  }
  const capabilityId = normalise(bundle.capability_id);
  if (!capabilityId) {
    throw new Error('capability bundle missing capability_id');
  }
  if (!CAPABILITY_ID_PATTERN.test(capabilityId)) {
    throw new Error(`capability bundle has invalid capability_id: ${capabilityId}`);
  }
  if (knownCapabilities.size > 0 && !knownCapabilities.has(capabilityId)) {
    throw new Error(`unknown capability id: ${capabilityId}`);
  }
  const version = normalise(bundle.version);
  if (!version) {
    throw new Error('capability bundle missing version');
  }
  if (!VERSION_PATTERN.test(version)) {
    throw new Error(`capability bundle has invalid version: ${version}`);
  }
  requireNonEmpty(bundle.owner, 'owner');
  requireNonEmpty(bundle.rollback, 'rollback');
  if (!bundle.selector || typeof bundle.selector !== 'object' || Array.isArray(bundle.selector)) {
    throw new Error('capability bundle missing selector object');
  }
  if (!bundle.fragments || typeof bundle.fragments !== 'object' || Array.isArray(bundle.fragments)) {
    throw new Error('capability bundle missing fragments object');
  }
  if (!normalise(bundle.fragments.task) && !normalise(bundle.fragments.acceptance)) {
    throw new Error('capability bundle must include a task or acceptance fragment');
  }
  if (!Array.isArray(bundle.gates) || bundle.gates.length === 0 || bundle.gates.some((gate) => !normalise(gate))) {
    throw new Error('capability bundle must include at least one gate ref');
  }
  const forbidden = walkForbiddenKeys(bundle);
  if (forbidden.length > 0) {
    throw new Error(`capability bundle contains unsafe inline fields: ${forbidden.join(', ')}`);
  }
  const expiresAt = normalise(bundle.expires_at);
  if (expiresAt) {
    const expiry = new Date(expiresAt);
    if (Number.isNaN(expiry.getTime())) {
      throw new Error(`capability bundle has invalid expires_at: ${expiresAt}`);
    }
    if (expiry.getTime() <= now.getTime()) {
      throw new Error(`capability bundle expired at ${expiresAt}`);
    }
  }
  const expectedHash = normalise(bundle.content_hash);
  if (!expectedHash) {
    throw new Error('capability bundle missing content_hash');
  }
  const actualHash = computeCapabilityBundleHash(bundle);
  if (expectedHash !== actualHash) {
    throw new Error(`capability bundle hash mismatch: expected ${expectedHash}, computed ${actualHash}`);
  }
  return true;
}

function loadCapabilityBundles(bundlePath, options = {}) {
  const raw = fs.readFileSync(bundlePath, 'utf8');
  const parsed = JSON.parse(raw);
  const bundles = Array.isArray(parsed)
    ? parsed
    : Array.isArray(parsed?.bundles)
      ? parsed.bundles
      : [parsed];
  bundles.forEach((bundle) => validateCapabilityBundle(bundle, options));
  return bundles;
}

function predicateMatches(expected, actual) {
  if (expected === undefined || expected === null) {
    return true;
  }
  if (Array.isArray(expected)) {
    return expected.map(normalise).filter(Boolean).includes(normalise(actual));
  }
  return normalise(expected) === normalise(actual);
}

function selectorMatches(selector = {}, context = {}) {
  const labels = new Set(asArray(context.labels).map((label) => normalise(label).toLowerCase()));
  if (!predicateMatches(selector.repo, context.repo)) {
    return [false, 'repo'];
  }
  if (!predicateMatches(selector.agent, context.agent)) {
    return [false, 'agent'];
  }
  if (!predicateMatches(selector.mode, context.mode)) {
    return [false, 'mode'];
  }
  for (const requiredLabel of asArray(selector.labels)) {
    if (!labels.has(normalise(requiredLabel).toLowerCase())) {
      return [false, `label:${requiredLabel}`];
    }
  }
  return [true, 'matched'];
}

function selectCapabilityBundles(bundles, context = {}, options = {}) {
  const applied = [];
  const rejected = [];
  for (const bundle of asArray(bundles)) {
    try {
      validateCapabilityBundle(bundle, options);
      const [matched, reason] = selectorMatches(bundle.selector, context);
      if (!matched) {
        rejected.push({
          capability_id: normalise(bundle.capability_id),
          content_hash: normalise(bundle.content_hash),
          reason,
        });
        continue;
      }
      applied.push({
        capability_id: normalise(bundle.capability_id),
        version: normalise(bundle.version),
        content_hash: normalise(bundle.content_hash),
        gate_versions: asArray(bundle.gates).map((gate) => normalise(gate)).filter(Boolean),
        playbooks: asArray(bundle.playbooks).map((playbook) => normalise(playbook)).filter(Boolean),
        fragments: {
          task: normalise(bundle.fragments?.task),
          acceptance: normalise(bundle.fragments?.acceptance),
        },
      });
    } catch (error) {
      rejected.push({
        capability_id: normalise(bundle?.capability_id) || 'unknown',
        content_hash: normalise(bundle?.content_hash),
        reason: error.message,
      });
    }
  }
  return { applied, rejected };
}

function renderCapabilityFragments(applied = []) {
  const blocks = asArray(applied)
    .map((bundle) => {
      const lines = [
        `Capability: ${bundle.capability_id}@${bundle.version}`,
        `Hash: ${bundle.content_hash}`,
      ];
      if (bundle.fragments?.task) {
        lines.push(`Task fragment: ${bundle.fragments.task}`);
      }
      if (bundle.fragments?.acceptance) {
        lines.push(`Acceptance fragment: ${bundle.fragments.acceptance}`);
      }
      if (bundle.gate_versions?.length) {
        lines.push(`Gates: ${bundle.gate_versions.join(', ')}`);
      }
      return lines.join('\n');
    })
    .filter(Boolean);
  return blocks.join('\n\n');
}

module.exports = {
  SCHEMA_VERSION,
  computeCapabilityBundleHash,
  loadCapabilityBundles,
  renderCapabilityFragments,
  selectCapabilityBundles,
  stableStringify,
  validateCapabilityBundle,
};
