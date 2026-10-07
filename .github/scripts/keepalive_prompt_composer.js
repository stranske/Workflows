'use strict';

const DEFAULT_SEPARATOR = '\n\n';
const {
  renderCapabilityFragments,
  selectCapabilityBundles,
} = require('./capability_bundle');

function normalise(value) {
  return String(value ?? '').trim();
}

function normaliseSegmentId(value, fallback) {
  const id = normalise(value);
  if (id) {
    return id;
  }
  return normalise(fallback) || 'segment';
}

function coerceSegments(value) {
  if (value === undefined || value === null || value === '' || value === false) {
    return [];
  }
  if (Array.isArray(value)) {
    return value;
  }
  return [value];
}

/**
 * @typedef {object} PromptSegment
 * @property {string} [id] - Stable ID reported when this segment renders
 * @property {string} [text] - Static content, used when build is absent
 * @property {function({state: object, context: object, mode: string}): string} [build]
 * @property {function({state: object, context: object, mode: string}): boolean} [when]
 */

/**
 * Creates a synchronous, ordered composer. Callbacks should treat state/context
 * as read-only inputs; persistence belongs to the caller. Empty content and
 * excluded segments are omitted from both text and the returned segment IDs.
 *
 * @param {object} [options]
 * @param {PromptSegment[]} [options.segments]
 * @returns {{segments: PromptSegment[], separator: string, compose: function}}
 */
function createPromptComposer(options = {}) {
  const segments = coerceSegments(options.segments);
  const separator = normalise(options.separator) || DEFAULT_SEPARATOR;
  const capabilityBundles = coerceSegments(options.capabilityBundles);
  const knownCapabilities = coerceSegments(options.knownCapabilities).map(normalise).filter(Boolean);

  const compose = (params = {}) => {
    const state = params.state && typeof params.state === 'object' ? params.state : {};
    const context = params.context && typeof params.context === 'object' ? params.context : {};
    const mode = normalise(params.mode);
    const rendered = [];
    const usedSegments = [];
    const capabilityResult = selectCapabilityBundles(
      Object.prototype.hasOwnProperty.call(params, 'capabilityBundles')
        ? coerceSegments(params.capabilityBundles)
        : capabilityBundles,
      { ...context, mode },
      { knownCapabilities },
    );
    const capabilityText = renderCapabilityFragments(capabilityResult.applied);
    if (capabilityText) {
      rendered.push(capabilityText);
      usedSegments.push('capability-bundle');
    }

    segments.forEach((segment, index) => {
      if (!segment || typeof segment !== 'object') {
        return;
      }
      const id = normaliseSegmentId(segment.id, `segment-${index + 1}`);
      const include = typeof segment.when === 'function'
        ? Boolean(segment.when({ state, context, mode }))
        : true;
      if (!include) {
        return;
      }

      let content = '';
      if (typeof segment.build === 'function') {
        content = segment.build({ state, context, mode }) ?? '';
      } else if (typeof segment.text === 'string') {
        content = segment.text;
      }

      const trimmed = normalise(content);
      if (!trimmed) {
        return;
      }

      rendered.push(trimmed);
      usedSegments.push(id);
    });

    return {
      text: rendered.join(separator).trim(),
      segments: usedSegments,
      separator,
      capability_bundles: capabilityResult,
    };
  };

  return {
    segments,
    separator,
    compose,
  };
}

function composePrompt(params = {}) {
  const composer = createPromptComposer(params);
  return composer.compose(params);
}

module.exports = {
  createPromptComposer,
  composePrompt,
};
