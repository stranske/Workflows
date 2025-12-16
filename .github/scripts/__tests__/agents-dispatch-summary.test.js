'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { appendDispatchSummary } = require('../agents_dispatch_summary');

function createSummary() {
  return {
    entries: [],
    addRaw(text) {
      this.entries.push({ type: 'raw', text });
      return this;
    },
    addEOL() {
      this.entries.push({ type: 'eol' });
      return this;
    },
    addTable(rows) {
      this.entries.push({ type: 'table', rows });
      return this;
    },
    async write() {
      this.entries.push({ type: 'write' });
    }
  };
}

test('appendDispatchSummary reports counts and table row', async () => {
  const summary = createSummary();
  const env = {
    DISPATCH_RESULT: 'success',
    DISPATCH_ISSUE: '1234',
    DISPATCH_REASON: 'bootstrap',
    WORKER_RESULT: 'success',
    WORKER_ALLOWED: 'true',
    WORKER_PR_NUMBER: '42',
    WORKER_BRANCH: 'codex/issue-1234',
    WORKER_DRY_RUN: 'false'
  };

  const result = await appendDispatchSummary({
    core: { summary },
    context: { repo: { owner: 'octo', repo: 'demo' } },
    env
  });

  assert.deepEqual(result.counts, { success: 1, skipped: 0, failures: 0 });
  assert.ok(summary.entries.some((entry) => entry.type === 'table'));
  assert.ok(result.row[0].includes('#42'));
});
