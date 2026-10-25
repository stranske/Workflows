'use strict';
// Provenance-only publication for an already-retained, pre-marker mixed result.
// The original comparison/receipt/event bytes and the two retained state markers are the real
// #4238 attempt (run 40170272788); the GitHub API around them is a fake.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const zlib = require('zlib');
const { createHash } = require('crypto');
const { buildVerificationEvent, guardExistingEvent, completedEvent, digest } = require('../../.github/scripts/verification_event.js');
const { publishInputRepairProvenance, readRetainedArchive, acquireRetainedExecution } = require('../../.github/scripts/verifier_pending_execution.js');
const { retainedExecutionFixture } = require('./fixtures/retained_execution');

const ROOT = path.join(__dirname, '../..');
const FIXTURES = path.join(ROOT, 'tests/fixtures/verification_input_repair');
const original = name => fs.readFileSync(path.join(FIXTURES, '4238-original', name));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const RUN = 40170272788, ARTIFACT = 12590118120, CURRENT = 40170999999;
const selector = { run_id: RUN, run_attempt: 1, artifact_id: ARTIFACT };
const assessment = { mode: 'compare', provider: '', model: '', model2: '', canonical: true };
const REAL_MANIFEST = JSON.parse(original('verification-event-manifest.json'));
const REAL_STATES = JSON.parse(fs.readFileSync(path.join(FIXTURES, '4238-retained-states.json'), 'utf8'));
const stateRow = comment => JSON.parse(comment.body.match(/<!-- verifier-event-state\/v1 (\{[^\n]+\}) -->/)[1]);
const stateComment = (row, base) => ({ ...base, body: `<!-- verifier-event-state/v1 ${JSON.stringify(row)} -->` });

const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
const crc32 = bytes => { let c = 0xffffffff; for (const b of bytes) c = CRC[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
function makeZip(entries) {
  const locals = [], central = [];
  let offset = 0;
  for (const [name, data, o = {}] of entries) {
    const method = o.method ?? 8, nameBytes = Buffer.from(name), packed = method === 8 ? zlib.deflateRawSync(data) : data;
    const crc = o.crc ?? crc32(data), flags = o.flags ?? 0;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(flags, 6); local.writeUInt16LE(method, 8);
    local.writeUInt32LE(crc, 14); local.writeUInt32LE(packed.length, 18); local.writeUInt32LE(data.length, 22); local.writeUInt16LE(nameBytes.length, 26);
    const cd = Buffer.alloc(46);
    cd.writeUInt32LE(0x02014b50, 0); cd.writeUInt16LE(20, 4); cd.writeUInt16LE(20, 6); cd.writeUInt16LE(flags, 8); cd.writeUInt16LE(method, 10);
    cd.writeUInt32LE(crc, 16); cd.writeUInt32LE(packed.length, 20); cd.writeUInt32LE(data.length, 24); cd.writeUInt16LE(nameBytes.length, 28);
    cd.writeUInt32LE((o.attributes ?? 0) >>> 0, 38); cd.writeUInt32LE(offset, 42);
    locals.push(local, nameBytes, packed); central.push(cd, nameBytes);
    offset += 30 + nameBytes.length + packed.length;
  }
  const directory = Buffer.concat(central), end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(entries.length, 8); end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(directory.length, 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}

// A result whose bytes, receipt sha and byte count stay mutually consistent.
function rewriteResult(mutateRows, mutateReceipt = () => {}) {
  const result = JSON.parse(original('comparison.json'));
  mutateRows(result.results);
  const bytes = Buffer.from(JSON.stringify(result, null, 2));
  const receipt = JSON.parse(original('comparison-execution.json'));
  receipt.outputs['comparison.json'] = { sha256: sha(bytes), bytes: bytes.length };
  mutateReceipt(receipt);
  return { comparison: bytes, receipt: Buffer.from(JSON.stringify(receipt, null, 2)) };
}

// `real` replays the retained #4238 event as-is; otherwise a rebuilt original (same subject) lets the
// consumer admission run end to end, because the retained PR body is not stored in this repository.
const REBUILT_INPUT = (selectors, evidence = {}) => ({ repository: 'stranske/Workflows',
  pull: { number: 4238, body: 'Release 4238 original request.', head: { sha: REAL_MANIFEST.verification_event.head_sha }, merge_commit_sha: REAL_MANIFEST.verification_event.evaluated_sha },
  issues: [], fullDiffBytes: Buffer.from('diff 4238\n'), selectors,
  evidence: { comments: { records: [] }, event_history: { complete: true, records: [] }, diagnostics: { archive_inventory: [] }, ...evidence } });

function world({ real = true, comparison = original('comparison.json'), receipt = original('comparison-execution.json'), manifestChange = () => {},
  entries, stateChange = rows => rows, extra = [], change = () => {}, pull = {}, createComment, dispatchRun = false, diverged } = {}) {
  const built = real ? null : buildVerificationEvent(REBUILT_INPUT());
  const manifest = real ? structuredClone(REAL_MANIFEST) : { verification_event: built.verification_event, request: built.request, material: built.material,
    assessment_identity: assessment, execution_binding: REAL_MANIFEST.execution_binding };
  manifestChange(manifest);
  const event = manifest.verification_event;
  const files = [['verification-event-manifest.json', Buffer.from(JSON.stringify(manifest, null, 2) + '\n')], ['comparison.json', comparison], ['comparison-execution.json', receipt]];
  const zip = makeZip(entries ? entries(files) : files);
  const fixture = retainedExecutionFixture({ repo: REAL_MANIFEST.verification_event.repo }, d => {
    d.run.id = RUN; d.job.run_id = RUN;
    // The retained runs were label-triggered: the API reports the PR head, which a squash merge leaves off main.
    d.run.event = dispatchRun ? 'workflow_dispatch' : 'pull_request_target'; d.run.created_at = '2026-10-24T01:00:00Z';
    for (const holder of [d.run, d.job, d.artifact.workflow_run]) holder.head_sha = event.head_sha;
    d.job.steps[2].name = 'Run multi-provider comparison'; d.job.steps[3].name = 'Upload comparison artifacts';
    d.artifact.id = ARTIFACT; d.artifact.name = `comparison-results-${RUN}`; d.artifact.workflow_run.id = RUN;
    d.archive = zip; d.artifact.size_in_bytes = zip.length; d.artifact.digest = `sha256:${sha(zip)}`;
    change(d);
  });
  const rows = stateChange(REAL_STATES.map(comment => {
    const row = stateRow(comment);
    return stateComment(real ? row : { ...row, verification_event: event }, comment);
  }));
  const comments = [...rows, ...extra].map((comment, index) => ({ id: index + 1, user: { login: comment.author }, html_url: comment.url, body: comment.body }));
  const posts = [];
  fixture.github.rest.pulls = { get: async () => ({ data: { merged: true, merged_at: '2026-10-23T23:59:00Z', head: { sha: event.head_sha }, merge_commit_sha: event.evaluated_sha,
    base: { ref: 'main', repo: { full_name: 'stranske/Workflows' } }, ...pull } }) };
  const compare = fixture.github.rest.repos.compareCommitsWithBasehead;
  const offMain = diverged ?? [event.head_sha];
  fixture.github.rest.repos.compareCommitsWithBasehead = async params => {
    const commit = params.basehead.split('...')[0];
    return offMain.includes(commit) ? { data: { status: 'diverged', base_commit: { sha: commit }, merge_base_commit: { sha: '0'.repeat(40) } } } : compare(params);
  };
  fixture.github.rest.issues = {
    listComments: async () => ({ data: comments, headers: {} }),
    createComment: async params => {
      posts.push(params);
      if (createComment) return createComment(params, comments);
      comments.push({ id: comments.length + 1, user: { login: 'github-actions[bot]' }, html_url: `https://github.com/stranske/Workflows/pull/4238#issuecomment-${9000 + comments.length}`, body: params.body });
      return { data: { id: comments.length } };
    },
  };
  const members = Object.fromEntries(files.map(([name, bytes]) => [name, sha(bytes)]));
  return { github: fixture.github, event, manifest, posts, comments, members, built, zip };
}

async function publish(w, over = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'provenance-'));
  try {
    return await publishInputRepairProvenance({ github: w.github, owner: 'stranske', repo: 'Workflows', prNumber: '4238', assessment, selector,
      currentRun: CURRENT, directory, ...over });
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
}
const postedMarker = w => JSON.parse(w.posts[0].body.match(/<!-- verifier-input-repair\/v1 (\{[^\n]+\}) -->/)[1]);

test('real #4238 shape: posts only original-execution provenance bound to its retained bytes', async () => {
  const w = world();
  const result = await publish(w);
  assert.equal(result.published, true);
  assert.equal(result.duplicate, false);
  assert.equal(w.posts.length, 1);
  assert.equal(w.posts[0].issue_number, 4238);
  const marker = postedMarker(w);
  assert.equal(marker.schema, 'verifier-input-repair/v1');
  assert.equal(marker.run_id, String(RUN));
  assert.equal(marker.run_attempt, '1');
  assert.equal(marker.verification_event.event_id, '1a7f8a950a7e88598e54e4a99bae8754f9be80f192f9a87c3d2083b98e9a60ca');
  assert.equal(marker.result.raw_sha256, 'aedba47ba2a5e12a74718e9781e59b057fe62dc0f01a6ab0c93ce195d45df5b5');
  assert.equal(marker.result.bytes, 12712);
  assert.equal(marker.receipt.raw_sha256, sha(original('comparison-execution.json')));
  assert.deepEqual(marker.provider_verdicts, [
    { provider: 'anthropic', model: 'claude-sonnet-5-5', verdict: 'PASS' },
    { provider: 'openai', model: 'gpt-5.6-terra', verdict: 'UNVERIFIABLE_INPUT' }]);
  assert.deepEqual(marker.original_material, REAL_MANIFEST.material);
  const { input_repair_id, ...body } = marker;
  assert.equal(input_repair_id, digest(body));
  // No verifier lifecycle state is created: the original attempt stays the latest canonical work.
  assert.doesNotMatch(w.posts[0].body, /verifier-event-state|verifier-corpus-decision/);
  const lineage = JSON.parse(w.posts[0].body.match(/<!-- verifier-input-repair-publication\/v1 (\{[^\n]+\}) -->/)[1]);
  assert.deepEqual({ ...lineage, archive_sha256: undefined }, { schema: 'verifier-input-repair-publication/v1', input_repair_id,
    source_run_id: String(RUN), source_run_attempt: '1', artifact_id: ARTIFACT, archive_sha256: undefined, publisher_run_id: String(CURRENT),
    publisher_run_attempt: '1', provider_generation_performed: false, verdict_authority: false, acceptance_authority: false, retry_authority: false });
});

test('existing recovery acquisition still refuses a squash-merged pull_request_target origin unless the provenance operation opts in', async () => {
  const w = world();
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'acquire-'));
  try {
    await assert.rejects(acquireRetainedExecution({ github: w.github, event: w.event, assessment, selector, currentRun: CURRENT, directory }), /not canonical merged source/);
    assert.equal(fs.existsSync(path.join(directory, 'verification-recovery-origin.json')), false);
    const proof = await acquireRetainedExecution({ github: w.github, event: w.event, assessment, selector, currentRun: CURRENT, directory, pullRequestTargetOrigin: true });
    assert.equal(proof.source_run_id, String(RUN));
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});

test('published provenance lets the existing consumer authenticate the retained mixed outcome, and nothing else', async () => {
  const w = world({ real: false });
  await publish(w);
  const comments = w.comments.map(row => ({ author: row.user.login, url: row.html_url, body: row.body }));
  const proof = 'https://github.com/stranske/Workflows/pull/4238#issuecomment-6392557346';
  const changed = records => ({ ...REBUILT_INPUT([{ kind: 'comment', url: proof }], { comments: { records: [{ url: proof, body: 'merge-guard proof' }] },
    event_history: { complete: true, records }, diagnostics: { archive_inventory: [{ run_id: RUN, artifact_id: ARTIFACT, member_inventory_complete: true,
      members: ['comparison.json', 'comparison-execution.json'].map(name => ({ path: name, status: 'captured', raw_sha256: w.members[name] })) }] } }),
    predecessorEventId: w.event.event_id, assessmentIdentity: assessment });
  const admitted = buildVerificationEvent(changed(comments));
  assert.equal(admitted.predecessor_event_id, w.event.event_id);
  assert.notEqual(admitted.verification_event.event_id, w.event.event_id);
  // The pre-marker history is exactly the historical defect.
  assert.throws(() => buildVerificationEvent(changed(comments.filter(row => !row.body.includes('verifier-input-repair/v1')))), /not an authenticated/);
  // Same-event retry and acceptance remain closed; the original stays incomplete.
  assert.throws(() => guardExistingEvent(w.event, comments, assessment), /incomplete/);
  assert.equal(completedEvent(w.event, comments, assessment), false);
});

test('exact repeat is an idempotent no-post; conflicting or malformed provenance fails closed', async () => {
  const w = world();
  await publish(w);
  const again = await publish(w);
  assert.equal(again.duplicate, true);
  assert.equal(w.posts.length, 1);
  const other = { ...postedMarker(w), provider_verdicts: [{ provider: 'openai', model: 'x', verdict: 'UNVERIFIABLE_INPUT' }] };
  delete other.input_repair_id;
  const conflicting = world({ extra: [{ author: 'github-actions[bot]', url: 'https://github.com/stranske/Workflows/pull/4238#issuecomment-7000',
    body: `<!-- verifier-input-repair/v1 ${JSON.stringify({ ...other, input_repair_id: digest(other) })} -->` }] });
  await assert.rejects(publish(conflicting), /Conflicting input-repair provenance/);
  const malformed = world({ extra: [{ author: 'github-actions[bot]', url: 'https://github.com/stranske/Workflows/pull/4238#issuecomment-7001',
    body: '<!-- verifier-input-repair/v1 {broken -->' }] });
  await assert.rejects(publish(malformed), /malformed/);
  // Another author's marker is not history authority.
  const untrusted = world({ extra: [{ author: 'mallory', url: 'https://github.com/stranske/Workflows/pull/4238#issuecomment-7002', body: 'x' }] });
  assert.equal((await publish(untrusted)).published, true);
  assert.equal(conflicting.posts.length + malformed.posts.length, 0);
});

test('lost POST response reconciles to the written comment; an unwritten POST stays uncertain and unretried', async () => {
  let attempts = 0;
  const written = world({ createComment: (params, comments) => {
    attempts += 1;
    comments.push({ id: 99, user: { login: 'github-actions[bot]' }, html_url: 'https://github.com/stranske/Workflows/pull/4238#issuecomment-8000', body: params.body });
    throw new Error('response lost');
  } });
  const result = await publish(written);
  assert.deepEqual([result.duplicate, result.reconciled_after_uncertain_post, attempts], [true, true, 1]);
  let flagged = 0;
  const lost = world({ createComment: () => { throw new Error('network'); } });
  await assert.rejects(publish(lost, { onPostAttempt: () => { flagged += 1; } }), { code: 'VERIFIER_INPUT_REPAIR_PUBLICATION_UNCERTAIN' });
  assert.deepEqual([lost.posts.length, flagged], [1, 1]);
});

const row = (comments, status) => comments.find(comment => stateRow(comment).status === status);
const incompleteChange = patch => rows => rows.map(comment => stateRow(comment).status === 'incomplete' ? stateComment({ ...stateRow(comment), ...patch }, comment) : comment);
const foreign = (id, body) => ({ author: 'github-actions[bot]', url: `https://github.com/stranske/Workflows/pull/4238#issuecomment-${id}`, body });
const decision = { schema: 'verifier-corpus-decision/v1', repo: REAL_MANIFEST.verification_event.repo, pr: '4238', head_sha: REAL_MANIFEST.verification_event.head_sha,
  evaluated_sha: REAL_MANIFEST.verification_event.evaluated_sha, run_id: String(RUN), run_attempt: '1', verdict: 'PASS', provider_verdicts: ['PASS'], ci_failed: false };
const rejectedCases = {
  'wrong head/merge subject': [{ pull: { head: { sha: 'f'.repeat(40) } } }, /Original attempt/],
  'pending without the incomplete state': [{ stateChange: rows => rows.filter(comment => stateRow(comment).status === 'pending') }, /exactly one incomplete/],
  'incomplete state from an untrusted author': [{ stateChange: rows => rows.map(comment => stateRow(comment).status === 'incomplete' ? { ...comment, author: 'mallory' } : comment) }, /exactly one incomplete/],
  'genuine no-evaluation (retryable) state': [{ stateChange: incompleteChange({ retry_kind: 'known_no_evaluation', retryable: true, failure_cause: 'validated_no_evaluation' }) }, /nonretryable retained provider/],
  'retryable retained evaluation': [{ stateChange: incompleteChange({ retryable: true }) }, /nonretryable retained provider/],
  'state that already carries a repair': [{ stateChange: incompleteChange({ input_repair: {} }) }, /nonretryable retained provider/],
  'contradictory terminal decision at the same attempt': [{ extra: [foreign(7100, `<!-- verifier-corpus-decision/v1 ${JSON.stringify(decision)} -->`)] }, /exactly one nonterminal/],
  'newer canonical pending work': [{ extra: [foreign(7101, `<!-- verifier-event-state/v1 ${JSON.stringify({ ...stateRow(REAL_STATES[0]), run_id: String(RUN + 1) })} -->`)] }, /superseded/],
  'newer attempt of the original run': [{ extra: [foreign(7102, `<!-- verifier-event-state/v1 ${JSON.stringify({ ...stateRow(REAL_STATES[0]), run_attempt: '2' })} -->`)] }, /superseded/],
  'archive replaced after the Actions digest': [{ change: d => { d.archive = Buffer.concat([d.archive, Buffer.from('x')]); } }, /digest mismatch/],
  'pull_request_target run for a different head': [{ change: d => { for (const holder of [d.run, d.job, d.artifact.workflow_run]) holder.head_sha = '1'.repeat(40); } }, /pull_request_target run is not this merged pull request/],
  'pull_request_target run that predates the merge': [{ pull: { merged_at: '2026-10-24T02:00:00Z' } }, /pull_request_target run is not this merged pull request/],
  'pull_request_target merge commit not on the default branch': [{ diverged: ['5961404e44a3f8c0e6e9d0c56ab4ba275b42f8b0', '29578c8d30a36a0196d8facc95115e6ed4eb1773'] }, /not canonical merged source/],
  'dispatch run from an off-main head': [{ dispatchRun: true }, /not canonical merged source/],
  'wrong artifact identity': [{ change: d => { d.artifact.name = 'comparison-results-1'; } }, /Retained artifact/],
  'manifest names a different event': [{ manifestChange: m => { m.verification_event = { ...m.verification_event, material_sha256: 'a'.repeat(64) }; } }, /Invalid verification event|not the original/],
  'manifest material no longer matches its digest': [{ manifestChange: m => { m.material.required_evidence = [{ kind: 'x' }]; } }, /not the original/],
  'manifest request no longer matches its digest': [{ manifestChange: m => { m.request.sources = []; } }, /not the original/],
  'result bytes differ from the receipt': [{ comparison: Buffer.from(original('comparison.json').toString().replace('"PASS"', '"FAIL"')) }, /does not join/],
  'receipt for another run': [{ receipt: Buffer.from(original('comparison-execution.json').toString().replace('"40170272788"', '"1"')) }, /does not join/],
  'receipt for another mode': [{ receipt: Buffer.from(original('comparison-execution.json').toString().replace('"mode": "compare"', '"mode": "evaluate"')) }, /does not join/],
  'archive lacks its receipt': [{ entries: files => files.filter(([name]) => name !== 'comparison-execution.json') }, /members missing/],
  'archive has a duplicate member': [{ entries: files => [...files, files[1]] }, /unsafe or incomplete/],
  'archive has a nested member': [{ entries: files => [...files, ['sub/comparison.json', Buffer.from('{}')]] }, /unsafe or incomplete/],
  'archive member fails its CRC': [{ entries: files => [[files[0][0], files[0][1], { crc: 1 }], ...files.slice(1)] }, /unsafe or incomplete/],
  'archive is truncated': [{ entries: () => [], change: d => { d.archive = d.archive.subarray(0, 40); d.artifact.size_in_bytes = 40; d.artifact.digest = `sha256:${sha(d.archive)}`; } }, /unsafe or incomplete/],
};
for (const [name, [options, pattern]] of Object.entries(rejectedCases)) {
  test(`fails closed: ${name}`, async () => {
    const w = world(options);
    await assert.rejects(publish(w), pattern);
    assert.equal(w.posts.length, 0);
  });
}
for (const [name, mutate, receiptMutate] of [
  ['receipt output marked truncated', rows => rows, receipt => { receipt.outputs['comparison.json'].truncated = true; }],
  ['receipt status output_truncated', rows => rows, receipt => { receipt.status = 'output_truncated'; }],
  ['receipt exit code nonzero', rows => rows, receipt => { receipt.exit_code = 1; }],
  ['no provider reported UNVERIFIABLE_INPUT', rows => { rows[0].verdict = 'PASS'; }, () => {}],
  ['a provider slot never ran', rows => { rows[1].used_llm = false; }, () => {}],
  ['a provider slot errored', rows => { rows[1].error = 'boom'; }, () => {}],
  ['an unknown provider verdict', rows => { rows[1].verdict = 'MAYBE'; }, () => {}],
]) {
  test(`fails closed: ${name}`, async () => {
    const { comparison, receipt } = rewriteResult(mutate, receiptMutate);
    const w = world({ comparison, receipt });
    await assert.rejects(publish(w), /does not join|completed mixed provider outcome/);
    assert.equal(w.posts.length, 0);
  });
}

test('selector, assessment and ordering misuse never reach GitHub writes', async () => {
  const w = world();
  const wrongAssessment = { mode: 'evaluate', provider: 'anthropic', model: '', model2: '', canonical: true };
  for (const over of [
    { selector: JSON.stringify({ ...selector, sha256: 'a'.repeat(64) }) }, { selector: JSON.stringify({ ...selector, run_id: String(RUN) }) },
    { selector: '{}' }, { currentRun: RUN }, { currentRun: RUN - 1 }, { prNumber: '04238' }, { prNumber: '0' },
    { assessment: wrongAssessment }, { assessment: { ...assessment, canonical: false } }, { assessment: { ...assessment, mode: 'checkbox' } },
  ]) await assert.rejects(publish(w, over));
  const unmerged = world({ pull: { merged: false } });
  await assert.rejects(publish(unmerged), /not a merged pull request/);
  assert.equal(w.posts.length + unmerged.posts.length, 0);
});

test('reader refuses unsafe archive structure that a digest alone would not', () => {
  const ok = makeZip([['a.json', Buffer.from('{}')], ['b.json', Buffer.from('x'.repeat(1000)), { method: 0 }]]);
  assert.deepEqual([...readRetainedArchive(ok).keys()], ['a.json', 'b.json']);
  for (const bad of [
    makeZip([['a', Buffer.from('1')], ['a', Buffer.from('2')]]), makeZip([['../a', Buffer.from('1')]]), makeZip([['d/', Buffer.alloc(0)]]),
    makeZip([['a', Buffer.from('1'), { flags: 1 }]]), makeZip([['a', Buffer.from('1'), { attributes: 0o120777 << 16 }]]),
    makeZip([['a', Buffer.from('1'), { crc: 0 }]]), Buffer.concat([ok, Buffer.from('trailing')]), ok.subarray(0, ok.length - 5), Buffer.alloc(0),
  ]) assert.throws(() => readRetainedArchive(bad), /Retained archive inventory/);
  assert.throws(() => readRetainedArchive(ok, { maxEntries: 1 }), /Retained archive inventory/);
  assert.throws(() => readRetainedArchive(ok, { maxBytes: 10 }), /Retained archive inventory/);
});

test('reader accepts the actual downloaded #4238 artifact when supplied', { skip: !process.env.VERIFIER_REAL_4238_ARCHIVE }, () => {
  const files = readRetainedArchive(fs.readFileSync(process.env.VERIFIER_REAL_4238_ARCHIVE));
  assert.equal(sha(files.get('comparison.json')), 'aedba47ba2a5e12a74718e9781e59b057fe62dc0f01a6ab0c93ce195d45df5b5');
  for (const name of ['comparison.json', 'comparison-execution.json', 'verification-event-manifest.json']) {
    assert.deepEqual(files.get(name), original(name));
  }
});

// The workflow step is run as written, not re-implemented here.
const workflow = fs.readFileSync(path.join(ROOT, '.github/workflows/reusable-agents-verifier.yml'), 'utf8');
const jobText = workflow.slice(workflow.indexOf('\n  input-repair-provenance:'));
function stepScript() {
  const lines = jobText.slice(jobText.indexOf('- name: Publish original-execution input-repair provenance')).split('\n');
  const start = lines.findIndex(line => line.trim() === 'script: |') + 1;
  const body = [];
  for (const line of lines.slice(start)) { if (line.trim() && !line.startsWith(' '.repeat(12))) break; body.push(line.slice(12)); }
  return body.join('\n');
}
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
async function runStep(w, env) {
  const outputs = {}, summary = [];
  const core = { setOutput: (key, value) => { outputs[key] = value; }, summary: { addRaw(text) { summary.push(text); return this; }, async write() {} } };
  const stepRequire = id => require(id.startsWith('./.workflows-lib/') ? path.join(ROOT, id.slice('./.workflows-lib/'.length)) : id);
  await new AsyncFunction('github', 'context', 'core', 'require', 'process', stepScript())(w.github,
    { repo: { owner: 'stranske', repo: 'Workflows' }, runId: CURRENT }, core, stepRequire,
    { env: { RUNNER_TEMP: os.tmpdir(), GITHUB_RUN_ATTEMPT: '1', ...env } });
  return { outputs, summary };
}
const dispatch = { PR_NUMBER: '4238', VERIFIER_MODE: 'compare', VERIFIER_PROVIDER: 'auto', VERIFIER_MODEL: '', VERIFIER_MODEL2: '',
  VERIFIER_EVIDENCE_PROFILE: 'standard', VERIFICATION_PROVENANCE: JSON.stringify(selector),
  VERIFICATION_RECOVERY: '', VERIFICATION_EVENT: '', VERIFICATION_MATERIAL: '', VERIFICATION_PREDECESSOR: '' };

test('the real workflow step publishes once for the #4238 dispatch contract', async () => {
  const w = world();
  const { outputs, summary } = await runStep(w, dispatch);
  assert.equal(w.posts.length, 1);
  assert.deepEqual([outputs.publication_effect, outputs.duplicate, outputs.input_repair_id], ['published', 'false', postedMarker(w).input_repair_id]);
  assert.match(summary.join(''), /No provider ran; no verdict, acceptance or retry authority/);
  const repeat = await runStep(w, dispatch);
  assert.deepEqual([repeat.outputs.publication_effect, repeat.outputs.duplicate, w.posts.length], ['none', 'true', 1]);
});

test('the real workflow step rejects mixed operations, expanded evidence and an assessment other than the original', async () => {
  for (const env of [{ VERIFICATION_RECOVERY: JSON.stringify(selector) }, { VERIFICATION_EVENT: '{}' }, { VERIFICATION_MATERIAL: '[]' },
    { VERIFICATION_PREDECESSOR: 'a'.repeat(64) }, { VERIFIER_EVIDENCE_PROFILE: 'expanded' }, { VERIFIER_MODE: 'evaluate' },
    { VERIFIER_MODE: 'checkbox' }, { VERIFIER_MODEL: 'gpt-x' }, { VERIFIER_MODEL2: 'claude-x' }]) {
    const w = world();
    await assert.rejects(runStep(w, { ...dispatch, ...env }));
    assert.equal(w.posts.length, 0);
  }
});

test('workflow wiring keeps provenance off the verifier execution path and out of provider capability', () => {
  const callerInput = /verification_provenance:\n(?: {8}.*\n)+?/;
  assert.match(workflow, /\n {2}verifier:\n {4}name: Run post-merge verifier\n(?: {4}#.*\n)+ {4}if: inputs\.verification_provenance == ''\n/);
  assert.match(jobText, /\n {4}if: inputs\.verification_provenance != ''\n/);
  assert.doesNotMatch(jobText, /secrets\.|OPENAI|CLAUDE|CODEX|models: |LANGSMITH/);
  assert.doesNotMatch(jobText, /verifier-event-state|verifier-corpus-decision|createComment/);
  const inputs = ['.github/workflows/agents-verifier.yml', 'templates/consumer-repo/.github/workflows/agents-verifier.yml'].map(file => fs.readFileSync(path.join(ROOT, file), 'utf8'));
  const description = text => text.match(/\n {6}verification_provenance:\n {8}description: (.*)\n/)[1];
  for (const text of inputs) {
    assert.match(text, callerInput);
    assert.ok(text.includes("      verification_provenance: ${{ inputs.verification_provenance || '' }}\n"));
    assert.equal(description(text), description(workflow));
  }
});


for (const [name, base] of [
  ['non-default base', { ref: 'release', repo: { full_name: 'stranske/Workflows' } }],
  ['foreign base repository', { ref: 'main', repo: { full_name: 'other/Workflows' } }],
]) {
  test(`pull_request_target origin rejects ${name}`, async () => {
    const w = world({ pull: { base } });
    await assert.rejects(publish(w), /post-merge verification/);
    assert.equal(w.posts.length, 0);
  });
}

function afterArchive(w, effect) {
  const originalDownload = w.github.rest.actions.downloadArtifact;
  w.github.rest.actions.downloadArtifact = async (...args) => {
    const response = await originalDownload(...args);
    effect();
    return response;
  };
}

test('newer canonical work arriving during archive authentication blocks publication', async () => {
  const w = world();
  const newer = { ...stateRow(REAL_STATES[0]), run_id: String(RUN + 1) };
  afterArchive(w, () => w.comments.push({ id: 900001, user: { login: 'github-actions[bot]' },
    html_url: 'https://github.com/stranske/Workflows/pull/4238#issuecomment-900001',
    body: `<!-- verifier-event-state/v1 ${JSON.stringify(newer)} -->` }));
  await assert.rejects(publish(w), /superseded/);
  assert.equal(w.posts.length, 0);
});

test('subject changing during archive authentication blocks publication', async () => {
  const w = world();
  let changed = false;
  afterArchive(w, () => { changed = true; });
  const originalPull = w.github.rest.pulls.get;
  w.github.rest.pulls.get = async (...args) => {
    const response = await originalPull(...args);
    return changed ? { ...response, data: { ...response.data, head: { sha: 'f'.repeat(40) } } } : response;
  };
  await assert.rejects(publish(w), /target changed during authentication/);
  assert.equal(w.posts.length, 0);
});

test('an exact provenance publication arriving during authentication is an idempotent no-post', async () => {
  const previous = world();
  await publish(previous);
  const w = world();
  afterArchive(w, () => w.comments.push({ id: 900002, user: { login: 'github-actions[bot]' },
    html_url: 'https://github.com/stranske/Workflows/pull/4238#issuecomment-900002', body: previous.posts[0].body }));
  const result = await publish(w);
  assert.equal(result.duplicate, true);
  assert.equal(w.posts.length, 0);
});
