'use strict';

const DEFAULT_MARKER = '<!-- gate-docs-only -->';
const BASE_MESSAGE = 'Gate fast-pass: docs-only change detected; heavy checks skipped.';
const NO_CHANGES_MESSAGE = 'Gate fast-pass: no changes detected; heavy checks skipped.';

function normalizeReason(reason) {
  if (reason === null || reason === undefined) {
    return '';
  }
  if (typeof reason === 'string') {
    return reason.trim();
  }
  return String(reason).trim();
}

function buildDocsOnlyMessage(reason) {
  const normalized = normalizeReason(reason);
  if (!normalized || normalized === 'docs_only') {
    return BASE_MESSAGE;
  }
  if (normalized === 'no_changes') {
    return NO_CHANGES_MESSAGE;
  }
  return `${BASE_MESSAGE} Reason: ${normalized}.`;
}

async function handleDocsOnlyFastPass({ core, reason, marker = DEFAULT_MARKER, summaryHeading = 'Gate docs-only fast-pass' } = {}) {
  const message = buildDocsOnlyMessage(reason);
  const outputs = {
    state: 'success',
    description: message,
    comment_body: `${message}\n\n${marker}`,
    marker,
    base_message: BASE_MESSAGE,
  };

  if (core && typeof core.setOutput === 'function') {
    for (const [key, value] of Object.entries(outputs)) {
      core.setOutput(key, value);
    }
  }

  if (core && typeof core.info === 'function') {
    core.info(message);
  }

  const summary = core?.summary;
  if (summary && typeof summary.addHeading === 'function' && typeof summary.addRaw === 'function' && typeof summary.write === 'function') {
    await summary.addHeading(summaryHeading, 3).addRaw(`${message}\n`).write();
  }

  return {
    message,
    outputs,
    marker,
    baseMessage: BASE_MESSAGE,
  };
}

module.exports = {
  handleDocsOnlyFastPass,
  buildDocsOnlyMessage,
  DEFAULT_MARKER,
  BASE_MESSAGE,
  NO_CHANGES_MESSAGE,
};
