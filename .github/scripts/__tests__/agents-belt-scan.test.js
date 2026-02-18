'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { identifyReadyCodexPRs, identifyReadyBeltPRs, isCodexBranch, isAgentBeltBranch } = require('../agents_belt_scan');

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

test('isCodexBranch recognises codex issues (backwards compat)', () => {
  assert.equal(isCodexBranch('codex/issue-123'), true);
  assert.equal(isCodexBranch('feature-branch'), false);
});

test('isAgentBeltBranch recognises any agent belt branch', () => {
  assert.equal(isAgentBeltBranch('codex/issue-123'), true);
  assert.equal(isAgentBeltBranch('claude/issue-456'), true);
  assert.equal(isAgentBeltBranch('auto/issue-789'), true);
  assert.equal(isAgentBeltBranch('feature-branch'), false);
  assert.equal(isAgentBeltBranch(null), false);
  assert.equal(isAgentBeltBranch(''), false);
});

test('identifyReadyBeltPRs is the same function as identifyReadyCodexPRs', () => {
  assert.equal(typeof identifyReadyBeltPRs, 'function');
  assert.equal(typeof identifyReadyCodexPRs, 'function');
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
