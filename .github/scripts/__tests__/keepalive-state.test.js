'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { selectDueAuthorityChallenge } = require('../keepalive_challenge_due.js');

const {
  parseStateComment,
  formatStateComment,
  deepMerge,
  formatTimestamp,
  createKeepaliveStateManager,
  loadKeepaliveState,
  projectRecoveredAuthorityState,
  calculateElapsedTime,
  isTrustedKeepaliveStateComment,
} = require('../keepalive_state.js');

const buildGithubStub = ({ comments = [] } = {}) => {
  const actions = [];
  const commentStore = comments.map((comment) => ({
    user: { login: 'agents-workflows-bot[bot]', type: 'Bot' },
    ...comment,
  }));
  let nextId = 101 + commentStore.length;
  const github = {
    actions,
    rest: {
      issues: {
        listComments: async () => ({ data: commentStore }),
        getComment: async ({ comment_id: commentId }) => {
          const match = commentStore.find((comment) => comment.id === commentId);
          return { data: match || { id: commentId, body: '' } };
        },
        createComment: async ({ body }) => {
          const id = nextId++;
          const record = {
            id,
            body,
            html_url: `https://example.com/${id}`,
            user: { login: 'agents-workflows-bot[bot]', type: 'Bot' },
          };
          commentStore.push(record);
          actions.push({ type: 'create', body });
          return { data: { id, html_url: record.html_url } };
        },
        updateComment: async ({ body, comment_id: commentId }) => {
          const match = commentStore.find((comment) => comment.id === commentId);
          if (match) {
            match.body = body;
          } else {
            commentStore.push({ id: commentId, body, html_url: `https://example.com/${commentId}` });
          }
          actions.push({ type: 'update', body, commentId });
          return { data: { id: commentId } };
        },
      },
    },
    paginate: async (fn, params) => {
      const result = await fn(params);
      return Array.isArray(result?.data) ? result.data : [];
    },
  };
  return github;
};

function settleRecovery(recovery) {
  const receiptField = recovery.status === 'released' ? 'released_receipt' : 'recovered_receipt';
  const ownerAttempt = recovery.state[receiptField].owner_attempt;
  const headSha = '1'.repeat(40);
  recovery.state = {
    ...recovery.state,
    status: 'available',
    head_sha: headSha,
    [receiptField]: {
      id: 'receipt-1',
      owner_attempt: ownerAttempt,
      claim_digest: '2'.repeat(64),
      head_sha: headSha,
      provider: 'codex',
    },
  };
  return recovery;
}

function authorityReader(states) {
  const sequence = Array.isArray(states) ? states : [states, states];
  let index = 0;
  return async () => ({
    sha: '3'.repeat(40),
    state: sequence[Math.min(index++, sequence.length - 1)],
  });
}

test('parseStateComment extracts JSON payload', () => {
  const body = formatStateComment({ trace: 'abc', head_sha: '123', version: 'v1' });
  const parsed = parseStateComment(body);
  assert.deepEqual(parsed, { version: 'v1', data: { trace: 'abc', head_sha: '123', version: 'v1' } });
});

test('deepMerge performs shallow + nested merge', () => {
  const merged = deepMerge({ a: 1, nested: { x: 1, y: 2 } }, { b: 2, nested: { y: 3, z: 4 } });
  assert.deepEqual(merged, { a: 1, b: 2, nested: { x: 1, y: 3, z: 4 } });
});

test('formatTimestamp omits milliseconds by default', () => {
  const date = new Date('2024-01-02T03:04:05.678Z');
  assert.equal(formatTimestamp(date), '2024-01-02T03:04:05Z');
});

test('formatTimestamp omits milliseconds when debug is false', () => {
  const date = new Date('2024-01-02T03:04:05.678Z');
  assert.equal(formatTimestamp(date, { debug: false }), '2024-01-02T03:04:05Z');
});

test('formatTimestamp includes milliseconds in debug mode', () => {
  const date = new Date('2024-01-02T03:04:05.678Z');
  assert.equal(formatTimestamp(date, { debug: true }), '2024-01-02T03:04:05.678Z');
});

test('formatTimestamp includes milliseconds for string input in debug mode', () => {
  const timestamp = '2024-01-02T03:04:05.678Z';
  assert.equal(formatTimestamp(timestamp, { debug: true }), '2024-01-02T03:04:05.678Z');
});

test('createKeepaliveStateManager creates hidden comment when missing', async () => {
  const github = buildGithubStub();
  const manager = await createKeepaliveStateManager({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 42,
    trace: 'trace-1',
    round: '3',
  });
  assert.equal(manager.state.trace, 'trace-1');
  await manager.save({ head_sha: 'abc123' });
  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'create');
  assert.match(github.actions[0].body, /keepalive-state:v1/);
  assert.match(github.actions[0].body, /"head_sha":"abc123"/);
});

test('createKeepaliveStateManager updates existing comment', async () => {
  const initialBody = formatStateComment({ trace: 'trace-1', round: '7', pr_number: 42 });
  const github = buildGithubStub({
    comments: [
      { id: 55, body: initialBody, html_url: 'https://example.com/55' },
    ],
  });
  const manager = await createKeepaliveStateManager({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 42,
    trace: 'trace-1',
    round: '7',
  });
  await manager.save({ result: { status: 'success' } });
  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'update');
  assert.equal(github.actions[0].commentId, 55);
  assert.match(github.actions[0].body, /"status":"success"/);
});

test('createKeepaliveStateManager preserves summary body when updating state', async () => {
  const initialBody = [
    '## Keepalive Summary',
    '',
    formatStateComment({ trace: 'trace-1', round: '7', pr_number: 42 }),
  ].join('\n');
  const github = buildGithubStub({
    comments: [
      { id: 77, body: initialBody, html_url: 'https://example.com/77' },
    ],
  });
  const manager = await createKeepaliveStateManager({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 42,
    trace: 'trace-1',
    round: '7',
  });
  await manager.save({ result: { status: 'success' } });
  assert.equal(github.actions.length, 1);
  assert.equal(github.actions[0].type, 'update');
  assert.match(github.actions[0].body, /## Keepalive Summary/);
  assert.match(github.actions[0].body, /"status":"success"/);
});

test('loadKeepaliveState returns stored payload when present', async () => {
  const storedBody = formatStateComment({ trace: 'trace-x', head_sha: 'def', version: 'v1' });
  const github = buildGithubStub({ comments: [{ id: 99, body: storedBody, html_url: 'https://example.com/99' }] });
  const result = await loadKeepaliveState({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 99,
    trace: 'trace-x',
  });
  assert.equal(result.commentId, 99);
  assert.equal(result.commentUrl, 'https://example.com/99');
  assert.equal(result.state.head_sha, 'def');
  assert.ok(Number.isFinite(Date.parse(result.state.current_iteration_at)));
});

for (const [author, user] of [
  ['untrusted', { login: 'untrusted-reviewer', type: 'User' }],
  ['unattributed', undefined],
]) {
  test(`loadKeepaliveState ignores a later ${author} marker and recovers trusted state`, async () => {
    const trustedBody = formatStateComment({
      trace: 'trace-x',
      iteration: 2,
      recovery_lease: { status: 'issued' },
    });
    const forgedBody = formatStateComment({
      trace: 'trace-x',
      iteration: 99,
      recovery_lease: { status: 'consumed' },
    });
    const github = buildGithubStub({
      comments: [
        { id: 99, body: trustedBody, html_url: 'https://example.com/99' },
        { id: 100, body: forgedBody, html_url: 'https://example.com/100', user },
      ],
    });
    const result = await loadKeepaliveState({
      github,
      context: { repo: { owner: 'o', repo: 'r' } },
      prNumber: 99,
      trace: 'trace-x',
    });

    assert.equal(result.commentId, 99);
    assert.equal(result.state.iteration, 2);
    assert.equal(result.state.recovery_lease.status, 'issued');
  });
}

test('trusted keepalive state writers include identity-checked PAT fallbacks', () => {
  assert.equal(isTrustedKeepaliveStateComment({
    user: { login: 'stranske', type: 'User' },
  }), true);
  assert.equal(isTrustedKeepaliveStateComment({
    user: { login: 'stranske-automation-bot', type: 'User' },
  }), true);
  assert.equal(isTrustedKeepaliveStateComment({
    user: { login: 'untrusted-reviewer', type: 'User' },
  }), false);
  assert.equal(isTrustedKeepaliveStateComment({
    user: { login: 'agents-workflows-bot[bot]', type: 'User' },
  }), false);
});

test('loadKeepaliveState prefers loop state when trace is empty', async () => {
  const nonLoopBody = formatStateComment({ trace: 'trace-x', head_sha: 'abc', version: 'v1' });
  const loopBody = formatStateComment({ trace: 'trace-y', iteration: 2, tasks: { total: 3 }, version: 'v1' });
  const github = buildGithubStub({
    comments: [
      { id: 41, body: loopBody, html_url: 'https://example.com/41' },
      { id: 42, body: nonLoopBody, html_url: 'https://example.com/42' },
    ],
  });
  const result = await loadKeepaliveState({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 41,
    trace: '',
  });
  assert.equal(result.commentId, 41);
  assert.equal(result.state.iteration, 2);
});

test('loadKeepaliveState falls back to latest non-loop state when trace is empty', async () => {
  const nonLoopBody = formatStateComment({ trace: 'trace-x', head_sha: 'abc', version: 'v1' });
  const github = buildGithubStub({
    comments: [
      { id: 52, body: nonLoopBody, html_url: 'https://example.com/52' },
    ],
  });
  const result = await loadKeepaliveState({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 52,
    trace: '',
  });
  assert.equal(result.commentId, 52);
  assert.equal(result.state.head_sha, 'abc');
});

test('parseStateComment returns empty data for malformed payload', () => {
  const body = '<!-- keepalive-state:v1 {"trace":"x", } -->';
  const parsed = parseStateComment(body);
  assert.deepEqual(parsed, { version: 'v1', data: {} });
});

test('parseStateComment returns null when marker missing', () => {
  const parsed = parseStateComment('no marker here');
  assert.equal(parsed, null);
});

test('loadKeepaliveState returns empty state when comment missing', async () => {
  const github = buildGithubStub({ comments: [] });
  const result = await loadKeepaliveState({
    github,
    context: { repo: { owner: 'o', repo: 'r' } },
    prNumber: 88,
    trace: 'trace-y',
  });
  assert.deepEqual(result, { state: {}, commentId: 0, commentUrl: '' });
});

test('recovered authority projects generation and clears running state on trusted summary', async () => {
  const oldGeneration = 'a'.repeat(64);
  const newGeneration = 'b'.repeat(64);
  const initial = { running: true, running_owner_attempt: 'owner/repo:123:1', attention: {
    owner: 'automation', disposition: 'challenge-due', generation: oldGeneration,
  } };
  const github = buildGithubStub({ comments: [{
    id: 91, body: '<!-- keepalive-loop-summary -->\n' + formatStateComment(initial),
  }] });
  const context = { repo: { owner: 'owner', repo: 'repo' } };
  const recovery = settleRecovery({ status: 'reopened', previousGeneration: oldGeneration, state: {
    generation: newGeneration, boundary_fingerprint: 'c'.repeat(64),
    recovered_receipt: { owner_attempt: 'owner/repo:123:1' },
    due_at: '2026-09-27T17:00:00.000Z', expires_at: '2026-09-28T17:00:00.000Z',
  } });
  const first = await projectRecoveredAuthorityState({
    github, context, prNumber: 42, recovery, writerLogin: 'agents-workflows-bot[bot]',
    readAuthority: authorityReader(recovery.state), makeRequest: () => 'request',
  });
  assert.equal(first.reason, 'recovered-summary-projected');
  const loaded = await loadKeepaliveState({ github, context, prNumber: 42, trace: '' });
  assert.equal(loaded.state.running, false);
  assert.equal(loaded.state.running_owner_attempt, null);
  assert.equal(loaded.state.attention.generation, newGeneration);
  assert.equal(loaded.state.attention.challenge_due_at, recovery.state.due_at);
  const second = await projectRecoveredAuthorityState({
    github, context, prNumber: 42, recovery, writerLogin: 'agents-workflows-bot[bot]',
    readAuthority: authorityReader(recovery.state), makeRequest: () => 'request',
  });
  assert.equal(second.reason, 'already-projected');
  assert.equal(github.actions.filter((action) => action.type === 'update').length, 1);
});

test('attempt-bound recovery projects after summary rewrites attention to automation retry', async () => {
  const oldGeneration = 'a'.repeat(64);
  const newGeneration = 'b'.repeat(64);
  const attempt = 'owner/repo:123:1';
  const initial = { running: false, attention: {
    owner: 'automation', disposition: 'automation-retry', generation: '',
    boundary_fingerprint: '', challenge_due_at: null, expires_at: '',
    recovery_generation: oldGeneration, recovery_owner_attempt: attempt,
  } };
  const github = buildGithubStub({ comments: [{
    id: 91, body: '<!-- keepalive-loop-summary -->\n' + formatStateComment(initial),
  }] });
  const context = { repo: { owner: 'owner', repo: 'repo' } };
  const recovery = settleRecovery({ status: 'released', previousGeneration: oldGeneration, state: {
    generation: newGeneration, boundary_fingerprint: 'c'.repeat(64),
    released_receipt: { owner_attempt: attempt },
    due_at: '2026-09-27T17:00:00.000Z', expires_at: '2026-09-28T17:00:00.000Z',
  } });
  const result = await projectRecoveredAuthorityState({
    github, context, prNumber: 42, recovery, writerLogin: 'agents-workflows-bot[bot]',
    readAuthority: authorityReader(recovery.state), makeRequest: () => 'request',
  });
  assert.equal(result.reason, 'recovered-summary-projected');
  const loaded = await loadKeepaliveState({ github, context, prNumber: 42, trace: '' });
  assert.equal(loaded.state.attention.disposition, 'challenge-due');
  assert.equal(loaded.state.attention.generation, newGeneration);
  assert.equal(loaded.state.attention.recovery_owner_attempt, attempt);
});

test('same-generation prepared release projection is idempotent for the exact owner attempt', async () => {
  const generation = 'a'.repeat(64);
  const attempt = 'owner/repo:123:1';
  const github = buildGithubStub({ comments: [{
    id: 91, body: '<!-- keepalive-loop-summary -->\n' + formatStateComment({
      running: true, running_owner_attempt: attempt, attention: { generation },
    }),
  }] });
  const context = { repo: { owner: 'owner', repo: 'repo' } };
  const recovery = settleRecovery({ status: 'released', state: {
    generation, released_receipt: { owner_attempt: attempt },
    boundary_fingerprint: 'c'.repeat(64),
    due_at: '2026-09-27T17:00:00.000Z', expires_at: '2026-09-28T17:00:00.000Z',
  } });
  const args = { github, context, prNumber: 42, recovery,
    writerLogin: 'agents-workflows-bot[bot]', readAuthority: authorityReader(recovery.state),
    makeRequest: () => 'request' };
  assert.equal((await projectRecoveredAuthorityState(args)).reason, 'recovered-summary-projected');
  assert.equal((await projectRecoveredAuthorityState(args)).reason, 'already-projected');
  assert.equal(github.actions.filter((action) => action.type === 'update').length, 1);
});

test('released receipt projection accepts an exact earlier lineage after multiple refreshes', async () => {
  const original = 'a'.repeat(64);
  const intermediate = 'b'.repeat(64);
  const current = 'c'.repeat(64);
  const github = buildGithubStub({ comments: [{ id: 91,
    body: '<!-- keepalive-loop-summary -->\n' + formatStateComment({
      running: true, running_owner_attempt: 'owner/repo:123:1',
      attention: { owner: 'automation', generation: original },
    }) }] });
  const recovery = settleRecovery({ status: 'released', previousGenerations: [original, intermediate], state: {
    generation: current, released_receipt: { owner_attempt: 'owner/repo:123:1' },
    boundary_fingerprint: 'd'.repeat(64),
    due_at: '2026-09-27T18:00:00.000Z', expires_at: '2026-09-28T18:00:00.000Z',
  } });
  const context = { repo: { owner: 'owner', repo: 'repo' } };
  assert.equal((await projectRecoveredAuthorityState({ github, context, prNumber: 42, recovery,
    writerLogin: 'agents-workflows-bot[bot]', readAuthority: authorityReader(recovery.state),
    makeRequest: () => 'request' })).reason, 'recovered-summary-projected');
  const loaded = await loadKeepaliveState({ github, context, prNumber: 42, trace: '' });
  assert.equal(loaded.state.attention.generation, current);
  assert.equal(loaded.state.attention.expires_at, recovery.state.expires_at);
  assert.equal(selectDueAuthorityChallenge({
    labels: ['agent:needs-attention'],
    comments: [{ user: { login: 'agents-workflows-bot[bot]', type: 'Bot' },
      body: '<!-- keepalive-loop-summary -->\n' + formatStateComment(loaded.state) }],
    now: new Date('2026-09-27T18:01:00.000Z'),
  })?.generation, current);
});

test('reopened receipt projection accepts an exact recovered lineage after expiry refreshes', async () => {
  const original = 'a'.repeat(64);
  const intermediate = 'b'.repeat(64);
  const current = 'c'.repeat(64);
  const attempt = 'owner/repo:123:1';
  const github = buildGithubStub({ comments: [{ id: 91,
    body: '<!-- keepalive-loop-summary -->\n' + formatStateComment({
      running: true, running_owner_attempt: attempt,
      attention: { owner: 'automation', generation: intermediate },
    }) }] });
  const recovery = settleRecovery({ status: 'reopened', previousGeneration: original,
    previousGenerations: [original, intermediate], state: {
      generation: current, recovered_generation: original,
      recovered_generation_lineage: [original, intermediate],
      recovered_receipt: { owner_attempt: attempt },
      boundary_fingerprint: 'd'.repeat(64),
      head_sha: 'e'.repeat(40),
      due_at: '2026-09-27T18:00:00.000Z', expires_at: '2026-09-28T18:00:00.000Z',
    } });
  const context = { repo: { owner: 'owner', repo: 'repo' } };
  assert.equal((await projectRecoveredAuthorityState({
    github, context, prNumber: 42, recovery,
    writerLogin: 'agents-workflows-bot[bot]', readAuthority: authorityReader(recovery.state),
    makeRequest: () => 'request',
  })).reason, 'recovered-summary-projected');
  const loaded = await loadKeepaliveState({ github, context, prNumber: 42, trace: '' });
  assert.equal(loaded.state.attention.generation, current);
  assert.equal(loaded.state.attention.recovery_owner_attempt, attempt);
});

test('same-generation recovery cannot overwrite a newer running owner attempt', async () => {
  const generation = 'a'.repeat(64);
  const recovery = settleRecovery({ status: 'released', state: {
    generation, boundary_fingerprint: 'c'.repeat(64),
    released_receipt: { owner_attempt: 'owner/repo:123:1' },
    due_at: '2026-09-27T17:00:00.000Z', expires_at: '2026-09-28T17:00:00.000Z',
  } });
  const github = buildGithubStub({ comments: [{ id: 91,
    body: '<!-- keepalive-loop-summary -->\n' + formatStateComment({
      running: true, running_owner_attempt: 'owner/repo:456:1', attention: { generation },
    }) }] });

  await assert.rejects(projectRecoveredAuthorityState({
    github, context: { repo: { owner: 'owner', repo: 'repo' } }, prNumber: 42, recovery,
    writerLogin: 'agents-workflows-bot[bot]', readAuthority: authorityReader(recovery.state),
    makeRequest: () => 'request',
  }), /does not match the recovered generation/);
  assert.equal(github.actions.length, 0);
});

test('recovery projection stops when the live ledger advances before comment mutation', async () => {
  const generation = 'a'.repeat(64);
  const attempt = 'owner/repo:123:1';
  const recovery = settleRecovery({ status: 'released', state: {
    generation, boundary_fingerprint: 'c'.repeat(64),
    released_receipt: { owner_attempt: attempt },
    due_at: '2026-09-27T17:00:00.000Z', expires_at: '2026-09-28T17:00:00.000Z',
  } });
  const github = buildGithubStub({ comments: [{ id: 91,
    body: '<!-- keepalive-loop-summary -->\n' + formatStateComment({
      running: true, running_owner_attempt: attempt, attention: { generation },
    }) }] });
  const superseding = { ...recovery.state, status: 'prepared', generation: 'b'.repeat(64) };
  const result = await projectRecoveredAuthorityState({
    github, context: { repo: { owner: 'owner', repo: 'repo' } }, prNumber: 42, recovery,
    writerLogin: 'agents-workflows-bot[bot]',
    readAuthority: authorityReader([recovery.state, superseding]), makeRequest: () => 'request',
  });

  assert.deepEqual(result, { projected: false, reason: 'recovery-superseded' });
  assert.equal(github.actions.length, 0);
});

test('createKeepaliveStateManager returns inert manager with invalid input', async () => {
  const github = buildGithubStub();
  const manager = await createKeepaliveStateManager({
    github,
    context: { repo: { owner: '', repo: '' } },
    prNumber: 0,
    trace: 'trace-1',
    round: '1',
  });
  assert.deepEqual(manager.state, {});
  const result = await manager.save({ head_sha: 'abc' });
  assert.deepEqual(result, { state: {}, commentId: 0, commentUrl: '' });
});

test('deepMerge ignores undefined values', () => {
  const merged = deepMerge({ a: 1, nested: { x: 1 } }, { a: undefined, nested: { x: undefined, y: 2 } });
  assert.deepEqual(merged, { a: 1, nested: { x: 1, y: 2 } });
});

const documentedStart = '2026-01-10T20:00:00Z';
const documentedNow = '2026-01-10T20:05:23Z';
const now = Date.parse(documentedNow);
const nowIso = new Date(now).toISOString();
const previousFirstIteration = '2026-01-10T19:00:00.000Z';

for (const [name, id, trace, iteration, storedFirst, expectedFirst] of [
  ['sets first_iteration_at on the first iteration', 124, '', 1, undefined, nowIso],
  ['sets first_iteration_at with a matching explicit trace', 11, 'trace-x', 1, undefined, nowIso],
  ['sets current_iteration_at on the second iteration', 123, '', 2, undefined, undefined],
  ['preserves stored first_iteration_at on a later iteration', 125, '', 2, previousFirstIteration, previousFirstIteration],
  ['leaves first_iteration_at unset after the first iteration', 12, 'trace-x', 3, undefined, undefined],
  ['leaves first_iteration_at unset before the first iteration', 13, 'trace-x', 0, undefined, undefined],
]) {
  test(`loadKeepaliveState ${name}`, async (t) => {
    t.mock.method(Date, 'now', () => now);
    const body = formatStateComment({
      trace: 'trace-x',
      iteration,
      first_iteration_at: storedFirst,
      current_iteration_at: storedFirst && documentedStart,
    });
    const github = buildGithubStub({ comments: [{ id, body }] });
    const result = await loadKeepaliveState({
      github,
      context: { repo: { owner: 'o', repo: 'r' } },
      prNumber: 42,
      trace,
    });

    assert.equal(result.commentId, id);
    assert.equal(result.state.iteration, iteration);
    assert.equal(result.state.first_iteration_at, expectedFirst);
    assert.equal(result.state.current_iteration_at, nowIso);
  });
}

for (const [name, elapsedMs, updates, expectedDuration] of [
  ['without updates', 65_000, {}, '1m 5s'],
  ['with an iteration update', 125_000, { iteration: 2 }, '2m 5s'],
]) {
  test(`createKeepaliveStateManager saves iteration_duration from current_iteration_at ${name}`, async (t) => {
    let clock = now;
    t.mock.method(Date, 'now', () => clock);
    const github = buildGithubStub();
    const manager = await createKeepaliveStateManager({
      github,
      context: { repo: { owner: 'o', repo: 'r' } },
      prNumber: 42,
      trace: 'trace-1',
      round: '3',
    });
    clock += elapsedMs;
    const saved = await manager.save(updates);

    assert.equal(saved.state.iteration_duration, expectedDuration);
    assert.equal(saved.state.current_iteration_at, nowIso);
    assert.equal(saved.state.iteration, updates.iteration);
    assert.deepEqual(parseStateComment(github.actions[0].body).data, saved.state);
  });
}

for (const [name, start, end] of [
  ['null start', null],
  ['undefined start', undefined],
  ['invalid start string', 'invalid'],
  ['invalid start string with a valid now', 'invalid', now],
  ['blank start string', '  '],
  ['invalid Date start', new Date(NaN)],
  ['NaN start', Number.NaN],
]) {
  test(`calculateElapsedTime returns 0s for ${name}`, () => {
    assert.equal(calculateElapsedTime(start, end), '0s');
  });
}

const isoBeforeNow = (elapsedMs) => new Date(now - elapsedMs).toISOString();

for (const [name, start, end, expected] of [
  ['formats minutes and seconds for the documented example with numeric now', documentedStart, now, '5m 23s'],
  ['accepts numeric string now', isoBeforeNow(12_000), String(now), '12s'],
  ['accepts Date now', isoBeforeNow(18_000), new Date(now), '18s'],
  ['trims ISO string now', documentedStart, `  ${documentedNow}  `, '5m 23s'],
  ['trims numeric string now', isoBeforeNow(45_000), `  ${now}  `, '45s'],
  ['accepts Date start with numeric string now', new Date(now - 30_000), String(now), '30s'],
]) {
  test(`calculateElapsedTime ${name}`, () => {
    assert.equal(calculateElapsedTime(start, end), expected);
  });
}

for (const [name, start, expected] of [
  ['trims ISO string start', `  ${isoBeforeNow(4_000)}  `, '4s'],
  ['formats whole minutes', isoBeforeNow(60_000), '1m 0s'],
  ['returns 0s for zero duration', nowIso, '0s'],
  ['matches the documented example with Date.now', documentedStart, '5m 23s'],
  ['truncates fractional seconds', isoBeforeNow(1_999), '1s'],
  ['returns 0s for a future start', isoBeforeNow(-60_000), '0s'],
  ['formats hours, minutes and seconds', isoBeforeNow(7_384_000), '2h 3m 4s'],
  ['accepts Date start', new Date(now - 9_000), '9s'],
  ['accepts numeric start', now - 12_000, '12s'],
  ['accepts numeric string start', String(now - 15_000), '15s'],
  ['trims numeric string start', `  ${now - 8_000}  `, '8s'],
  ['accepts decimal numeric string start', String(now - 1_500.5), '1s'],
]) {
  test(`calculateElapsedTime ${name}`, (t) => {
    t.mock.method(Date, 'now', () => now);
    assert.equal(calculateElapsedTime(start), expected);
  });
}

for (const [name, end, elapsedMs, expected] of [
  ['invalid string now', 'invalid', 7_000, '7s'],
  ['invalid Date now', new Date(NaN), 11_000, '11s'],
]) {
  test(`calculateElapsedTime falls back to Date.now for ${name}`, (t) => {
    t.mock.method(Date, 'now', () => now);
    assert.equal(calculateElapsedTime(isoBeforeNow(elapsedMs), end), expected);
  });
}
