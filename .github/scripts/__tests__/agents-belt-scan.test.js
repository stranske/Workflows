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

test('the Codex dispatcher filters other agents before its promotion limit', async () => {
  const pulls = ['claude/issue-42', 'codex/issue-4368'].map((ref, index) => ({
    number: index === 0 ? 1 : 4445,
    head: { ref, sha: 'head-' + index },
    labels: ['automerge'],
  }));
  const request = {
    github: { rest: {
      pulls: { list: async () => ({ data: pulls }) },
      repos: { getCombinedStatusForRef: async () => ({ data: { state: 'success' } }) },
    } },
    context: { repo: { owner: 'octo', repo: 'demo' } },
    core: { summary: createSummary(), setOutput() {} },
  };
  const scoped = await identifyReadyBeltPRs({ ...request, env: { MAX_PROMOTIONS: '1', BELT_AGENT: 'codex' } });
  assert.deepEqual(scoped.candidates.map(({ pr, issue }) => [pr, issue]), [[4445, 4368]]);
  const general = await identifyReadyBeltPRs({ ...request, env: { MAX_PROMOTIONS: '1' } });
  assert.deepEqual(general.candidates.map(({ pr, issue }) => [pr, issue]), [[1, 42]]);
});
