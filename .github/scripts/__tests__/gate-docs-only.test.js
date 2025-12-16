'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  handleDocsOnlyFastPass,
  buildDocsOnlyMessage,
  DEFAULT_MARKER,
  BASE_MESSAGE,
  NO_CHANGES_MESSAGE,
} = require('../gate-docs-only');

test('buildDocsOnlyMessage returns base message for docs_only reason', () => {
  assert.equal(buildDocsOnlyMessage('docs_only'), BASE_MESSAGE);
  assert.equal(buildDocsOnlyMessage(undefined), BASE_MESSAGE);
  assert.equal(buildDocsOnlyMessage(''), BASE_MESSAGE);
});

test('buildDocsOnlyMessage includes custom reason', () => {
  const message = buildDocsOnlyMessage('typo fix');
  assert.equal(message, `${BASE_MESSAGE} Reason: typo fix.`);
});

test('buildDocsOnlyMessage returns no changes message', () => {
  assert.equal(buildDocsOnlyMessage('no_changes'), NO_CHANGES_MESSAGE);
});

test('handleDocsOnlyFastPass sets outputs and summary', async () => {
  const outputs = {};
  const summary = {
    entries: [],
    addHeading(text, level) {
      this.entries.push({ type: 'heading', text, level });
      return this;
    },
    addRaw(text) {
      this.entries.push({ type: 'raw', text });
      return this;
    },
    async write() {
      this.written = true;
    },
  };
  const infoMessages = [];
  const core = {
    setOutput(key, value) {
      outputs[key] = value;
    },
    info(message) {
      infoMessages.push(message);
    },
    summary,
  };

  const result = await handleDocsOnlyFastPass({ core, reason: 'formatting tweak' });

  assert.equal(outputs.state, 'success');
  assert.equal(outputs.description, `${BASE_MESSAGE} Reason: formatting tweak.`);
  assert.equal(outputs.comment_body, `${BASE_MESSAGE} Reason: formatting tweak.\n\n${DEFAULT_MARKER}`);
  assert.equal(outputs.marker, DEFAULT_MARKER);
  assert.equal(outputs.base_message, BASE_MESSAGE);
  assert.equal(infoMessages.length, 1);
  assert.equal(infoMessages[0], `${BASE_MESSAGE} Reason: formatting tweak.`);
  assert.equal(summary.entries.length, 2);
  assert.deepEqual(summary.entries[0], { type: 'heading', text: 'Gate docs-only fast-pass', level: 3 });
  assert.deepEqual(summary.entries[1], { type: 'raw', text: `${BASE_MESSAGE} Reason: formatting tweak.\n` });
  assert.equal(summary.written, true);
  assert.equal(result.outputs.comment_body, outputs.comment_body);
  assert.equal(result.baseMessage, BASE_MESSAGE);
});

test('handleDocsOnlyFastPass works without core', async () => {
  const result = await handleDocsOnlyFastPass({ reason: 'no_changes' });
  assert.equal(result.outputs.description, NO_CHANGES_MESSAGE);
  assert.equal(result.outputs.marker, DEFAULT_MARKER);
});
