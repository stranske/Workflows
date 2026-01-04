'use strict';

const DEFAULT_SEPARATOR = '\n\n';

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
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value;
  }
  return [value];
}

function createPromptComposer(options = {}) {
  const segments = coerceSegments(options.segments);
  const separator = normalise(options.separator) || DEFAULT_SEPARATOR;

  const compose = (params = {}) => {
    const state = params.state && typeof params.state === 'object' ? params.state : {};
    const context = params.context && typeof params.context === 'object' ? params.context : {};
    const mode = normalise(params.mode);
    const rendered = [];
    const usedSegments = [];

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
