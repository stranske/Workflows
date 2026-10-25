'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { buildVerificationEvent, guardExistingEvent, completedEvent, inputRepairMarker, digest }
  = require('../../.github/scripts/verification_event.js');
const { fetchVerifierEvidence } = require('../../.github/scripts/agents_verifier_context.js');

// Retained #4231/#4235 shapes (head, merge, run, cause, identity) are real; the original
// request/material are rebuilt because the retained PR bodies are not stored here.
const FIXTURES = path.join(__dirname, '../fixtures/verification_input_repair');
const sha = c => c.repeat(64);
const bot = (n, id, body) => ({ author: 'github-actions[bot]', url: `https://github.com/stranske/workflows/pull/${n}#issuecomment-${id}`, body });
const proofUrl = n => `https://github.com/stranske/Workflows/pull/${n}#issuecomment-${n === 4231 ? '6390994169' : '6392557346'}`;
const MEMBERS = { result: { path: 'comparison.json', raw_sha256: sha('1'), bytes: 10 }, receipt: { path: 'comparison-execution.json', raw_sha256: sha('2') } };
const VERDICTS = [{ provider: 'anthropic', model: 'a', verdict: 'PASS' }, { provider: 'openai', model: 'o', verdict: 'UNVERIFIABLE_INPUT' }];

function scenario(n, retainedProof = false) {
  const stored = JSON.parse(fs.readFileSync(path.join(FIXTURES, `${n}-retained-states.json`), 'utf8'))
    .map(c => JSON.parse(c.body.match(/<!-- verifier-event-state\/v1 (\{[^\n]+\}) -->/)[1]));
  const incompleteRow = stored.find(r => r.status === 'incomplete');
  assert.equal(incompleteRow.retry_kind, 'recover_existing_evaluation');
  assert.equal(incompleteRow.retryable, false);
  const assessment = incompleteRow.assessment_identity;
  const base = (selectors, evidence = {}) => ({ repository: 'stranske/Workflows',
    pull: { number: n, body: `Release ${n} original request.`, head: { sha: incompleteRow.head_sha }, merge_commit_sha: incompleteRow.evaluated_sha },
    issues: [], fullDiffBytes: Buffer.from(`diff ${n}\n`), selectors,
    evidence: { comments: { records: [] }, event_history: { complete: true, records: [] }, diagnostics: { archive_inventory: [] }, ...evidence } });
  const retained = retainedProof ? { selectors: [{ kind: 'comment', url: proofUrl(n) }],
    evidence: { comments: { records: [{ url: proofUrl(n), body: 'canonical merge-guard proof' }] } } } : {};
  const original = buildVerificationEvent(base(retained.selectors, retained.evidence));
  const rows = stored.map(r => ({ ...r, verification_event: original.verification_event }));
  const state = rows.find(r => r.status === 'incomplete');
  const marker = (over = {}) => {
    const { input_repair_id, ...body } = inputRepairMarker({ state, material: original.material, repair: { ...MEMBERS, provider_verdicts: VERDICTS } });
    const next = { ...body, ...over };
    return { ...next, input_repair_id: digest(next) };
  };
  const stateComments = rows.map((r, i) => bot(n, 100 + i, `<!-- verifier-event-state/v1 ${JSON.stringify(r)} -->`));
  const markerComment = (m = marker()) => bot(n, 200, `<!-- verifier-input-repair/v1 ${JSON.stringify(m)} -->`);
  const inventory = () => [{ run_id: Number(state.run_id), artifact_id: 7, member_inventory_complete: true, members: [
    { path: MEMBERS.result.path, status: 'captured', raw_sha256: MEMBERS.result.raw_sha256 },
    { path: MEMBERS.receipt.path, status: 'captured', raw_sha256: MEMBERS.receipt.raw_sha256 }] }];
  const changed = (extra = {}) => {
    const input = base([{ kind: 'comment', url: proofUrl(n) }]);
    input.evidence.comments.records.push({ url: proofUrl(n), body: 'canonical merge-guard proof' });
    input.evidence.diagnostics.archive_inventory = inventory();
    input.evidence.event_history.records = [...stateComments, markerComment()];
    return { ...input, predecessorEventId: original.verification_event.event_id, assessmentIdentity: assessment, ...extra };
  };
  const withHistory = (records, over = {}) => { const input = changed(over); input.evidence.event_history.records = records; return input; };
  return { n, original, rows, state, assessment, marker, markerComment, stateComments, changed, withHistory, inventory, base };
}

const NOT_AUTH = /not an authenticated|Predecessor has newer|Incomplete predecessor|existing execution recovery|Malformed/;

for (const n of [4231, 4235]) {
  test(`#${n}: authenticated changed necessary proof admits retained mixed outcome with lineage`, () => {
    const s = scenario(n);
    const built = buildVerificationEvent(s.changed());
    assert.equal(built.predecessor_event_id, s.original.verification_event.event_id);
    assert.notEqual(built.verification_event.event_id, s.original.verification_event.event_id);
    assert.equal(built.verification_event.request_sha256, s.original.verification_event.request_sha256);
    assert.equal(built.verification_event.head_sha, s.original.verification_event.head_sha);
    assert.equal(built.verification_event.evaluated_sha, s.original.verification_event.evaluated_sha);
  });

  test(`#${n}: original event stays nonretryable and nonaccepting`, () => {
    const s = scenario(n), e = s.original.verification_event;
    const records = [...s.stateComments, s.markerComment()];
    assert.throws(() => guardExistingEvent(e, records, s.assessment), /incomplete/);
    assert.equal(completedEvent(e, records, s.assessment), false);
  });

  test(`#${n}: repeating the changed event deduplicates and preserves predecessor lineage`, () => {
    const s = scenario(n);
    const child = buildVerificationEvent(s.changed());
    const terminal = bot(n, 300, `<!-- verifier-corpus-decision/v1 ${JSON.stringify({ schema: 'verifier-corpus-decision/v1',
      repo: child.verification_event.repo, pr: child.verification_event.pr, head_sha: child.verification_event.head_sha,
      evaluated_sha: child.verification_event.evaluated_sha, run_id: String(Number(s.state.run_id) + 1), run_attempt: '1',
      ci_failed: false, provider_verdicts: ['CONCERNS'], verdict: 'NON_PASS', verification_event: child.verification_event,
      predecessor_event_id: child.predecessor_event_id, assessment_identity: s.assessment })} -->`);
    assert.equal(completedEvent(child.verification_event, [terminal], s.assessment), true);
    const repeated = buildVerificationEvent(s.withHistory([...s.stateComments, s.markerComment(), terminal]));
    assert.deepEqual(repeated.verification_event, child.verification_event);
    assert.equal(repeated.predecessor_event_id, s.original.verification_event.event_id);
  });
}

test('same event, unchanged material, optional-only and model-alias changes are rejected', () => {
  const s = scenario(4231);
  const same = s.changed({ selectors: undefined });
  assert.throws(() => buildVerificationEvent(same), NOT_AUTH);
  const optional = s.changed({ selectors: undefined });
  optional.evidence.gzip_assets = [{ source: 'docs/x.log.gz', status: 'captured', git_blob_sha: 'c'.repeat(40), raw_sha256: sha('d'), text_sha256: sha('e') }];
  optional.evidence.comments.records.push({ url: 'incidental', body: 'optional log noise' });
  assert.throws(() => buildVerificationEvent(optional), NOT_AUTH);
  assert.throws(() => buildVerificationEvent(s.changed({ assessmentIdentity: { ...s.assessment, model: 'alias-of-same-model' } })), NOT_AUTH);
  assert.throws(() => buildVerificationEvent(s.changed({ assessmentIdentity: undefined })), NOT_AUTH);
  assert.throws(() => buildVerificationEvent(s.changed({ predecessorEventId: sha('c') })), NOT_AUTH);
});

test('CI-only progress is not repaired necessary proof', () => {
  const s = scenario(4231, true);
  const ci = s.changed({ ciResults: [{ workflow_id: 'ci.yml', binding_status: 'bound',
    head_sha: s.state.evaluated_sha, run_id: 9, run_attempt: 1, conclusion: 'success' }] });
  assert.throws(() => buildVerificationEvent(ci), NOT_AUTH);
});

test('missing, truncated, duplicate and wrong selected proof cannot mint a repaired event', () => {
  const s = scenario(4231);
  const missing = s.changed(); missing.evidence.comments.records = [];
  assert.throws(() => buildVerificationEvent(missing), /absent/);
  const truncated = s.changed(); truncated.evidence.comments.records[0].truncated = true;
  assert.throws(() => buildVerificationEvent(truncated), /absent|incomplete/);
  const duplicate = s.changed(); duplicate.evidence.comments.records.push({ ...duplicate.evidence.comments.records[0] });
  assert.throws(() => buildVerificationEvent(duplicate), /ambiguous/);
  const wrong = s.changed({ selectors: [{ kind: 'comment', url: proofUrl(4235) }] });
  assert.throws(() => buildVerificationEvent(wrong), /absent/);
});

test('wrong subject, event, run, attempt, assessment and original material are rejected', () => {
  const s = scenario(4231);
  const other = scenario(4235).original.verification_event;
  const cases = {
    subject: { pr: '4235' }, event: { verification_event: other }, run: { run_id: '1' }, attempt: { run_attempt: '2' },
    assessment: { assessment_identity: { ...s.assessment, mode: 'evaluate' } },
    advisory: { assessment_identity: { ...s.assessment, canonical: false } },
    originalMaterial: { original_material: { ...s.original.material, required_evidence: [{ kind: 'forged' }] } },
    verdicts: { provider_verdicts: [{ provider: 'anthropic', model: 'a', verdict: 'PASS' }] },
    receiptPath: { receipt: { ...MEMBERS.receipt, path: 'other.json' } },
  };
  for (const [name, over] of Object.entries(cases)) {
    assert.throws(() => buildVerificationEvent(s.withHistory([...s.stateComments, s.markerComment(s.marker(over))])), NOT_AUTH, name);
  }
});

test('wrong artifact digest is rejected', () => {
  const s = scenario(4231);
  const result = s.changed(); result.evidence.diagnostics.archive_inventory[0].members[0].raw_sha256 = sha('9');
  assert.throws(() => buildVerificationEvent(result), NOT_AUTH);
  const receipt = s.changed(); receipt.evidence.diagnostics.archive_inventory[0].members[1].raw_sha256 = sha('9');
  assert.throws(() => buildVerificationEvent(receipt), NOT_AUTH);
  const claimed = s.withHistory([...s.stateComments, s.markerComment(s.marker({ result: { ...MEMBERS.result, raw_sha256: sha('8') } }))]);
  assert.throws(() => buildVerificationEvent(claimed), NOT_AUTH);
  const absent = s.changed(); absent.evidence.diagnostics.archive_inventory = [];
  assert.throws(() => buildVerificationEvent(absent), NOT_AUTH);
  const ambiguous = s.changed(); ambiguous.evidence.diagnostics.archive_inventory.push({ ...s.inventory()[0], artifact_id: 8 });
  assert.throws(() => buildVerificationEvent(ambiguous), NOT_AUTH);
  const incomplete = s.changed(); incomplete.evidence.diagnostics.archive_inventory[0].member_inventory_complete = false;
  assert.throws(() => buildVerificationEvent(incomplete), NOT_AUTH);
});

test('untrusted, truncated, absent and contradictory provenance supply no authority', () => {
  const s = scenario(4231);
  const comment = s.markerComment();
  for (const bad of [{ ...comment, author: 'stranske' }, { ...comment, url: comment.url.replace('/4231#', '/4235#') }]) {
    assert.throws(() => buildVerificationEvent(s.withHistory([...s.stateComments, bad])), NOT_AUTH);
  }
  assert.throws(() => buildVerificationEvent(s.withHistory([...s.stateComments, { ...comment, truncated: true }])), NOT_AUTH);
  assert.throws(() => buildVerificationEvent(s.withHistory(s.stateComments)), NOT_AUTH);
  const second = { ...s.markerComment(s.marker({ provider_verdicts: [...VERDICTS, { provider: 'x', model: 'y', verdict: 'FAIL' }] })), url: comment.url.replace('200', '201') };
  assert.throws(() => buildVerificationEvent(s.withHistory([...s.stateComments, comment, second])), NOT_AUTH);
  // Identical duplicates are one authority value.
  assert.doesNotThrow(() => buildVerificationEvent(s.withHistory([...s.stateComments, comment, { ...comment, url: comment.url.replace('200', '202') }])));
});

test('contradictory receipts, unresolved provider attempts and newer canonical work are rejected', () => {
  const s = scenario(4231);
  const row = (over, id) => bot(4231, id, `<!-- verifier-event-state/v1 ${JSON.stringify({ ...s.state, ...over })} -->`);
  const history = extra => s.withHistory([...s.stateComments, s.markerComment(), ...extra]);
  // A different incomplete cause in the same attempt contradicts the retained receipt.
  assert.throws(() => buildVerificationEvent(history([row({ failure_cause: 'execution_payload_missing', retry_kind: 'uncertain_execution' }, 301)])), NOT_AUTH);
  // Retryable flag contradicting the retained classification.
  assert.throws(() => buildVerificationEvent(history([row({ retryable: true }, 302)])), NOT_AUTH);
  // A terminal in the original attempt makes the incomplete marker contradictory.
  const terminal = bot(4231, 303, `<!-- verifier-corpus-decision/v1 ${JSON.stringify({ schema: 'verifier-corpus-decision/v1', repo: s.state.repo,
    pr: s.state.pr, head_sha: s.state.head_sha, evaluated_sha: s.state.evaluated_sha, run_id: s.state.run_id, run_attempt: s.state.run_attempt,
    ci_failed: false, provider_verdicts: ['PASS'], verdict: 'PASS', verification_event: s.state.verification_event,
    assessment_identity: s.assessment })} -->`);
  assert.throws(() => buildVerificationEvent(history([terminal])), NOT_AUTH);
  // Unresolved newer child execution of the changed event.
  const child = buildVerificationEvent(s.changed()).verification_event;
  const childRow = (status, id, over = {}) => row({ status, verification_event: child, run_id: String(Number(s.state.run_id) + 1),
    predecessor_event_id: s.original.verification_event.event_id, failure_cause: undefined, retry_kind: undefined, retryable: undefined, ...over }, id);
  assert.throws(() => buildVerificationEvent(history([childRow('incomplete', 304, { failure_cause: 'execution_payload_missing', retry_kind: 'uncertain_execution', retryable: false })])), NOT_AUTH);
  // Newer canonical work for a third event.
  const third = scenario(4235).original.verification_event;
  assert.throws(() => buildVerificationEvent(history([row({ status: 'pending', verification_event: { ...child, event_id: sha('7') }, run_id: String(Number(s.state.run_id) + 5) }, 305)])), NOT_AUTH);
  assert.ok(third);
});

test('UNVERIFIABLE_INPUT is never accepted as completion', () => {
  const s = scenario(4231);
  const e = s.original.verification_event;
  assert.equal(completedEvent(e, [...s.stateComments, s.markerComment()], s.assessment), false);
  assert.throws(() => guardExistingEvent(e, [...s.stateComments, s.markerComment()], s.assessment), /incomplete/);
});

// Production path: the verifier collector (not a hand-built event_history) must retain the
// repair provenance, or the predecessor check can never see it. Only the artifact archive
// inventory is injected; comments, authors, URLs and event_history come from the collector.
async function collected(s, comments) {
  const rows = comments.map(c => ({ id: Number(c.url.split('issuecomment-')[1]), html_url: c.url, user: { login: c.author, type: 'Bot' }, body: c.body }));
  const github = { rest: { issues: { listComments: async () => ({ data: rows }) },
    pulls: { listReviewComments: async () => ({ data: [] }), listReviews: async () => ({ data: [] }) } } };
  const evidence = await fetchVerifierEvidence({ github, owner: 'stranske', repo: 'workflows', pullNumber: s.n, pullRequestBody: `Release ${s.n} original request.` });
  const input = s.changed();
  input.evidence = { ...input.evidence, event_history: evidence.event_history };
  return { evidence, input };
}

for (const n of [4231, 4235]) {
  test(`#${n}: collector-retained input-repair provenance admits the changed event end to end`, async () => {
    const s = scenario(n);
    const { evidence, input } = await collected(s, [...s.stateComments, s.markerComment()]);
    assert.equal(evidence.event_history.complete, true);
    assert.equal(evidence.event_history.records.filter(r => r.body.includes('verifier-input-repair/v1')).length, 1);
    const built = buildVerificationEvent(input);
    assert.equal(built.predecessor_event_id, s.original.verification_event.event_id);
    assert.notEqual(built.verification_event.event_id, s.original.verification_event.event_id);
    // Without the marker in collected history there is no changed-input authority.
    const absent = await collected(s, s.stateComments);
    assert.throws(() => buildVerificationEvent(absent.input), NOT_AUTH);
  });
}

test('collector-retained provenance keeps untrusted, malformed, digest, subject, execution and newer-work failures', async () => {
  const s = scenario(4231);
  const comment = s.markerComment();
  const row = (over, id) => bot(4231, id, `<!-- verifier-event-state/v1 ${JSON.stringify({ ...s.state, ...over })} -->`);
  const cases = {
    untrustedAuthor: [{ ...comment, author: 'stranske' }],
    otherPullUrl: [{ ...comment, url: comment.url.replace('/4231#', '/4235#') }],
    digest: [s.markerComment({ ...s.marker(), input_repair_id: sha('0') })],
    subject: [s.markerComment(s.marker({ pr: '4235' }))],
    execution: [s.markerComment(s.marker({ run_attempt: '2' }))],
    newerWork: [comment, row({ status: 'pending', verification_event: { ...buildVerificationEvent(s.changed()).verification_event, event_id: sha('7') }, run_id: String(Number(s.state.run_id) + 5) }, 301)],
  };
  for (const [name, extra] of Object.entries(cases)) {
    const { input } = await collected(s, [...s.stateComments, ...extra]);
    assert.throws(() => buildVerificationEvent(input), NOT_AUTH, name);
  }
  // Malformed marker JSON: the collector marks history incomplete, so nothing is admitted.
  const malformed = bot(4231, 201, '<!-- verifier-input-repair/v1 {not json} -->');
  const { evidence } = await collected(s, [...s.stateComments, comment, malformed]);
  assert.equal(evidence.event_history.complete, false);
  assert.match(evidence.event_history.reason, /malformed/);
  // Schema mismatch inside an otherwise well-formed repair marker is also malformed history.
  const wrong = bot(4231, 202, `<!-- verifier-input-repair/v1 ${JSON.stringify({ ...JSON.parse(JSON.stringify(s.marker())), schema: 'verifier-event-state/v1' })} -->`);
  assert.equal((await collected(s, [...s.stateComments, comment, wrong])).evidence.event_history.complete, false);
});
