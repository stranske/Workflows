'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { identifyReadyCodexPRs, isCodexBranch } = require('../agents_belt_scan');

function createSummary() {
  return {
    entries: [],
    addHeading(text) {
      this.entries.push({ type: 'heading', text });
      return this;
    },
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

test('isCodexBranch recognises codex issues', () => {
  assert.equal(isCodexBranch('codex/issue-123'), true);
  assert.equal(isCodexBranch('feature-branch'), false);
});

test('identifyReadyCodexPRs filters and summarises ready PRs', async () => {
  const pulls = [
    {
      number: 10,
      head: { ref: 'codex/issue-101', sha: 'abc' },
      draft: false,
      labels: [{ name: 'automerge' }]
    },
    {
      number: 20,
      head: { ref: 'feature', sha: 'def' },
      draft: false,
      labels: []
    },
    {
      number: 30,
      head: { ref: 'codex/issue-102', sha: 'ghi' },
      draft: true,
      labels: [{ name: 'automerge' }]
    }
  ];

  const github = {
    rest: {
      pulls: {
        async list() {
          return { data: pulls };
        }
      },
      repos: {
        async getCombinedStatusForRef({ ref }) {
          return {
            data: { state: ref === 'abc' ? 'success' : 'failure' }
          };
        }
      }
    }
  };

  const summary = createSummary();
  const outputs = {};

  const result = await identifyReadyCodexPRs({
    github,
    context: { repo: { owner: 'octo', repo: 'demo' } },
    core: {
      summary,
      setOutput(key, value) {
        outputs[key] = value;
      }
    },
    env: { MAX_PROMOTIONS: '5' }
  });

  assert.equal(result.candidates.length, 1);
  assert.ok(summary.entries.some((entry) => entry.type === 'table'));
  const items = JSON.parse(outputs.items);
  assert.equal(items[0].pr, 10);
});
