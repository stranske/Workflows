'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { classifyReporterRun } = require('../keepalive_reporter_applicability.js');

const root = path.resolve(__dirname, '../../..');
const head = 'a'.repeat(40);
const run = { id: 12345, run_attempt: 2, head_sha: head, pull_requests: [] };
const sources = [
  '.github/workflows/agents-keepalive-loop.yml',
  'templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml',
];

function setup(source, title, overrides = {}) {
  const pathInRepo = source.replace(/^templates\/consumer-repo\//, '');
  const producer = fs.readFileSync(path.join(root, source));
  let reads = 0;
  const github = {
    rest: {
      actions: { getWorkflowRun: async () => {
        reads += 1;
        return { data: { ...run, event: 'workflow_dispatch', path: pathInRepo,
          display_title: title, ...overrides } };
      } },
      repos: { getContent: async () => {
        reads += 1;
        return { data: { encoding: 'base64', content: producer.toString('base64') } };
      } },
    },
  };
  return { github, reads: () => reads };
}

for (const source of sources) {
  test(`${source}: ordinary unassociated dispatch skips only after absent index`, async () => {
    const { github, reads } = setup(source, 'keepalive-dispatch/v1 ordinary');
    let lookups = 0;
    const result = await classifyReporterRun({ github, owner: 'stranske', repo: 'repo', run,
      lookupTarget: async () => { lookups += 1; return null; } });
    assert.deepEqual(result, { status: 'skip' });
    assert.equal(lookups, 1);
    assert.equal(reads(), 2);
  });

  test(`${source}: authority candidate without index fails closed`, async () => {
    const { github } = setup(source, 'keepalive-dispatch/v1 authority-candidate');
    await assert.rejects(classifyReporterRun({ github, owner: 'stranske', repo: 'repo', run,
      lookupTarget: async () => null }), /no immutable attempt index/);
  });

  test(`${source}: missing or misleading title cannot become ordinary`, async () => {
    for (const title of ['', 'ordinary', 'keepalive-dispatch/v2 ordinary']) {
      const { github } = setup(source, title);
      await assert.rejects(classifyReporterRun({ github, owner: 'stranske', repo: 'repo', run,
        lookupTarget: async () => null }), /no versioned classification/);
    }
  });
}

test('verified index wins over an ordinary title and needs no title lookup', async () => {
  const { github, reads } = setup(sources[0], 'keepalive-dispatch/v1 ordinary');
  const result = await classifyReporterRun({ github, owner: 'stranske', repo: 'repo', run,
    lookupTarget: async () => ({ prNumber: 42 }) });
  assert.deepEqual(result, { status: 'continue', prNumber: 42 });
  assert.equal(reads(), 0);
});

test('unavailable or corrupt index lookup never becomes an ordinary skip', async () => {
  const { github } = setup(sources[0], 'keepalive-dispatch/v1 ordinary');
  await assert.rejects(classifyReporterRun({ github, owner: 'stranske', repo: 'repo', run,
    lookupTarget: async () => { throw new Error('index 503'); } }), /index 503/);
});

test('wrong originating workflow or event cannot claim ordinary routing', async () => {
  for (const override of [{ path: '.github/workflows/other.yml' }, { event: 'push' },
    { run_attempt: 3 }, { head_sha: 'b'.repeat(40) }]) {
    const { github } = setup(sources[0], 'keepalive-dispatch/v1 ordinary', override);
    await assert.rejects(classifyReporterRun({ github, owner: 'stranske', repo: 'repo', run,
      lookupTarget: async () => null }), /no verified dispatch classification/);
  }
});

test('originating revision without the classification contract fails closed', async () => {
  const { github } = setup(sources[0], 'keepalive-dispatch/v1 ordinary');
  github.rest.repos.getContent = async () => ({ data: {
    encoding: 'base64', content: Buffer.from('name: Agents Keepalive Loop\n').toString('base64'),
  } });
  await assert.rejects(classifyReporterRun({ github, owner: 'stranske', repo: 'repo', run,
    lookupTarget: async () => null }), /lacks the dispatch classification contract/);
});

test('associated runs avoid the unassociated locator altogether', async () => {
  const result = await classifyReporterRun({ github: {}, owner: 'stranske', repo: 'repo',
    run: { ...run, pull_requests: [{ number: 42 }] },
    lookupTarget: async () => { throw new Error('unexpected lookup'); } });
  assert.deepEqual(result, { status: 'continue' });
});
