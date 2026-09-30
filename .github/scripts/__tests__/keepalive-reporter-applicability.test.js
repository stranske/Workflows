'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const {
  classifyReporterRun,
  recoverReporterAuthority,
} = require('../keepalive_reporter_applicability.js');
const {
  formatStateComment,
  loadKeepaliveState,
  projectRecoveredAuthorityState,
} = require('../keepalive_state.js');

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

function recoveryGithub(state) {
  const comments = [{
    id: 91,
    body: '<!-- keepalive-loop-summary -->\n' + formatStateComment(state),
    html_url: 'https://example.com/91',
    user: { login: 'agents-workflows-bot[bot]', type: 'Bot' },
  }];
  const actions = [];
  return {
    actions,
    rest: {
      issues: {
        listComments: async () => ({ data: comments }),
        getComment: async ({ comment_id: commentId }) => ({
          data: comments.find((comment) => comment.id === commentId),
        }),
        updateComment: async ({ comment_id: commentId, body }) => {
          comments.find((comment) => comment.id === commentId).body = body;
          actions.push({ type: 'update', commentId, body });
          return { data: { id: commentId } };
        },
        createComment: async ({ body }) => {
          actions.push({ type: 'create', body });
          return { data: { id: 92, html_url: 'https://example.com/92' } };
        },
      },
    },
    paginate: async (fn, params) => (await fn(params)).data,
  };
}

function settleRecovery(recovery) {
  const receiptName = recovery.status === 'released' ? 'released_receipt' : 'recovered_receipt';
  const ownerAttempt = recovery.state[receiptName].owner_attempt;
  const headSha = '1'.repeat(40);
  recovery.state = {
    ...recovery.state,
    status: 'available',
    head_sha: headSha,
    [receiptName]: {
      id: 'receipt-1', owner_attempt: ownerAttempt, claim_digest: '2'.repeat(64),
      head_sha: headSha, provider: 'codex',
    },
  };
  return recovery;
}

function projectCurrentRecovery(recovery) {
  return (input) => projectRecoveredAuthorityState({
    ...input,
    readAuthority: async () => ({ sha: '3'.repeat(40), state: recovery.state }),
    makeRequest: () => 'request',
  });
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

for (const status of ['released', 'reopened']) {
  test(`delayed ${status} recovery is located, reconciled, and projected after summary retry`, async () => {
    const previousGeneration = 'b'.repeat(64);
    const nextGeneration = 'c'.repeat(64);
    const ownerAttempt = 'stranske/repo:12345:2';
    const github = recoveryGithub({
      running: false,
      attention: {
        owner: 'automation', disposition: 'automation-retry', generation: '',
        boundary_fingerprint: '', challenge_due_at: null, expires_at: '',
        recovery_generation: previousGeneration, recovery_owner_attempt: ownerAttempt,
      },
    });
    const receiptName = status === 'released' ? 'released_receipt' : 'recovered_receipt';
    const recovery = settleRecovery({
      status,
      previousGeneration,
      state: {
        generation: nextGeneration,
        boundary_fingerprint: 'd'.repeat(64),
        [receiptName]: { owner_attempt: ownerAttempt },
        due_at: '2026-09-30T01:00:00Z',
        expires_at: '2026-09-30T13:00:00Z',
      },
    });
    const context = { repo: { owner: 'stranske', repo: 'repo' } };
    const args = {
      github, context, run, workerEvidence: 'not-started',
      writerLogin: 'agents-workflows-bot[bot]',
      makeRequest: () => 'request',
      lookupTarget: async ({ repository, ownerAttempt: attempt }) => {
        assert.equal(repository, 'stranske/repo');
        assert.equal(attempt, ownerAttempt);
        return { prNumber: 42 };
      },
      reconcileAttempt: async (input) => {
        assert.equal(input.request, 'request');
        assert.equal(input.ownerAttempt, ownerAttempt);
        assert.equal(input.prNumber, 42);
        return recovery;
      },
      projectRecovery: projectCurrentRecovery(recovery),
    };
    const first = await recoverReporterAuthority(args);
    assert.equal(first.status, 'projected');
    assert.equal(first.projection.reason, 'recovered-summary-projected');
    const second = await recoverReporterAuthority(args);
    assert.equal(second.projection.reason, 'already-projected');
    assert.equal(github.actions.filter((action) => action.type === 'update').length, 1);
    const loaded = await loadKeepaliveState({ github, context, prNumber: 42, trace: '' });
    assert.equal(loaded.state.attention.disposition, 'challenge-due');
    assert.equal(loaded.state.attention.generation, nextGeneration);
    assert.equal(loaded.state.attention.recovery_owner_attempt, ownerAttempt);
  });
}

test('404 reconciliation preserves the owner-attempt binding for normal reporting', async () => {
  const missing = new Error('not found');
  missing.status = 404;
  const result = await recoverReporterAuthority({
    github: {}, context: { repo: { owner: 'stranske', repo: 'repo' } }, run,
    workerEvidence: 'started', writerLogin: 'agents-workflows-bot[bot]', prNumber: 42,
    makeRequest: () => 'request',
    reconcileAttempt: async () => { throw missing; },
  });
  assert.equal(result.status, 'continue');
  assert.equal(result.ownerAttempt, 'stranske/repo:12345:2');
});

test('non-released reconciliation preserves the owner-attempt binding for normal reporting', async () => {
  const result = await recoverReporterAuthority({
    github: {}, context: { repo: { owner: 'stranske', repo: 'repo' } }, run,
    workerEvidence: 'started', writerLogin: 'agents-workflows-bot[bot]', prNumber: 42,
    makeRequest: () => 'request',
    reconcileAttempt: async () => ({ status: 'owned' }),
  });
  assert.equal(result.status, 'continue');
  assert.equal(result.ownerAttempt, 'stranske/repo:12345:2');
});

test('recovery rejects unknown worker evidence before authority mutation', async () => {
  await assert.rejects(recoverReporterAuthority({
    github: {}, context: { repo: { owner: 'stranske', repo: 'repo' } }, run,
    workerEvidence: 'unknown', writerLogin: 'agents-workflows-bot[bot]',
    makeRequest: () => { throw new Error('must not request'); },
  }), /execution evidence is unknown/);
});

test('recovery rejects a delayed summary marker for a different attempt or generation', async () => {
  const github = recoveryGithub({
    running: false,
    attention: {
      owner: 'automation', disposition: 'automation-retry', generation: '',
      recovery_generation: 'e'.repeat(64),
      recovery_owner_attempt: 'stranske/repo:999:1',
    },
  });
  const recovery = settleRecovery({
    status: 'released', previousGeneration: 'b'.repeat(64), state: {
      generation: 'c'.repeat(64), boundary_fingerprint: 'd'.repeat(64),
      released_receipt: { owner_attempt: 'stranske/repo:12345:2' },
      due_at: '2026-09-30T01:00:00Z', expires_at: '2026-09-30T13:00:00Z',
    },
  });
  await assert.rejects(recoverReporterAuthority({
    github,
    context: { repo: { owner: 'stranske', repo: 'repo' } },
    run,
    workerEvidence: 'not-started',
    writerLogin: 'agents-workflows-bot[bot]',
    makeRequest: () => 'request',
    lookupTarget: async () => ({ prNumber: 42 }),
    reconcileAttempt: async () => recovery,
    projectRecovery: projectCurrentRecovery(recovery),
  }), /does not match the recovered generation/);
  assert.equal(github.actions.length, 0);
});

test('superseded recovery stops reporter processing without comment mutation', async () => {
  const github = recoveryGithub({ running: false, attention: {} });
  const result = await recoverReporterAuthority({
    github, context: { repo: { owner: 'stranske', repo: 'repo' } }, run,
    workerEvidence: 'not-started', writerLogin: 'agents-workflows-bot[bot]', prNumber: 42,
    makeRequest: () => 'request',
    reconcileAttempt: async () => ({ status: 'released', state: {} }),
    projectRecovery: async () => ({ projected: false, reason: 'recovery-superseded' }),
  });
  assert.equal(result.status, 'superseded');
  assert.equal(result.projection.reason, 'recovery-superseded');
  assert.equal(github.actions.length, 0);
});
