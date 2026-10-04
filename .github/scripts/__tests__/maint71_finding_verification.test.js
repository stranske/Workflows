'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { sha256, validateIndependentFindingVerification: validate } = require('../maint71_finding_verification');
const { validateReviewResolutionProof } = require('../maint71_merge_sync_prs');

function fixture() {
  const head = 'a'.repeat(40);
  const proof = { schema: 'workflows-sync-review-resolution/v1', repository: 'stranske/Ready',
    pr: 1, head_sha: head, thread_id: 'PRRT_1', originating_reviewer: 'codex',
    source_fix_sha: 'b'.repeat(40), evidence_url: 'https://github.com/stranske/Workflows/pull/1',
    reviewer_acceptance_url: 'https://github.com/stranske/Workflows/issues/1836#issuecomment-1',
    acceptance_mode: 'independent-verification', reason: 'Specific source repair verified' };
  const record = { durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: 'plan', generation: 'gen', source_commit: 'c'.repeat(40) };
  const binding = { repository: proof.repository, pr: 1, head_sha: head, thread_id: proof.thread_id,
    originating_reviewer: 'codex', plan_id: 'plan', generation: 'gen', source_commit: record.source_commit };
  const original = { body: 'Specific finding, not generic PR approval', author: { login: 'origin' } };
  const request = { url: 'request', author: { login: 'stranske' },
    createdAt: '2026-10-04T01:00:00Z',
    body: `<!-- maint71-review-disposition:v1 ${JSON.stringify(binding)} -->` };
  const completion = { url: 'completion', author: { login: 'origin' }, commit: { oid: head },
    createdAt: '2026-10-04T01:01:00Z', body: 'Clean review.' };
  const thread = { id: proof.thread_id, isResolved: false,
    comments: { pageInfo: { hasNextPage: false }, nodes: [original, request, completion] } };
  const result = { ...binding, schema: 'workflows-sync-finding-verification/v1', verdict: 'PASS',
    status: 'completed', coverage: 'complete', verifier_profile: 'sol', assessment_id: 'd'.repeat(64),
    result_sha256: 'e'.repeat(64), rationale: 'Independent assessment reproduces this finding and confirms the contained source fix.',
    source_fix_sha: proof.source_fix_sha, evidence_url: proof.evidence_url,
    finding_sha256: sha256(original.body), completed_at: '2026-10-04T01:02:00Z',
    reassessment_request_url: 'request', originating_completion_url: 'completion',
    validation: [{ command: 'node regression', exit_code: 0, negative_control: 'failed-before-fix' }] };
  const comment = { id: 1, html_url: proof.reviewer_acceptance_url, user: { login: 'stranske' },
    created_at: '2026-10-04T01:03:00Z' };
  const args = { proof, record, thread, threads: { pageInfo: { hasNextPage: false }, nodes: [thread] },
    comment, policy: { finding_verification_fallback: { enabled: true,
      trusted_publishers: ['stranske'], verifier_profiles: ['sol'] } },
    reviewerProfiles: [{ id: 'codex', logins: ['origin'], disposition_completion_prefixes: ['Clean review.'] }],
    now: Date.parse('2026-10-04T01:04:00Z') };
  return { args, result, finish: () => {
    comment.body = `<!-- maint71-finding-verification:v1 ${JSON.stringify(result)} -->`;
    return args;
  } };
}

test('independent finding disposition is opt-in, authenticated, exact-binding, and terminal', () => {
  const f = fixture(); assert.equal(validate(f.finish()).ok, true);
  assert.equal(validateReviewResolutionProof(f.args.proof, { owner: 'stranske', repo: 'Ready',
    prNumber: 1, headSha: f.args.proof.head_sha, actor: 'stranske', trustedActors: ['stranske'] }).ok, true);
  f.args.policy.finding_verification_fallback.enabled = false;
  assert.equal(validate(f.finish()).ok, false);
});

for (const key of ['repository', 'pr', 'head_sha', 'thread_id', 'source_fix_sha', 'evidence_url',
  'plan_id', 'generation', 'source_commit', 'finding_sha256', 'originating_reviewer',
  'verdict', 'status', 'coverage', 'verifier_profile', 'assessment_id', 'result_sha256',
  'reassessment_request_url', 'originating_completion_url', 'completed_at']) {
  test(`reject changed or incomplete ${key}`, () => {
    const f = fixture(); f.result[key] = 'wrong'; assert.equal(validate(f.finish()).ok, false);
  });
}
test('generic review, forged publisher, stale receipt, missing regression, and partial inventories cannot authorize', () => {
  for (const mutate of [
    (f) => { f.args.comment.user.login = 'untrusted'; },
    (f) => { f.args.comment.html_url = 'https://evil.test'; },
    (f) => { f.args.record.durable_issue_url = 'https://github.com/stranske/Workflows/issues/99'; },
    (f) => { f.args.now += 25 * 60 * 60 * 1000; },
    (f) => { f.result.validation = []; },
    (f) => { f.result.validation[0].exit_code = 1; },
    (f) => { f.result.validation[0].negative_control = 'not-run'; },
    (f) => { f.args.threads.pageInfo.hasNextPage = true; },
    (f) => { f.args.thread.comments.pageInfo.hasNextPage = true; },
    (f) => { f.args.thread.comments.nodes[1].author.login = 'forged'; },
    (f) => { f.args.thread.comments.nodes[2].commit.oid = 'old'; },
    (f) => { f.args.thread.comments.nodes.push({ author: { login: 'origin' },
      createdAt: '2026-10-04T01:03:00Z', body: 'New finding' }); },
  ]) {
    const f = fixture(); mutate(f); assert.equal(validate(f.finish()).ok, false);
  }
  const f = fixture(); f.finish(); f.args.comment.body = 'Clean review.';
  assert.equal(validate(f.args).ok, false);
  f.finish(); f.args.comment.body += f.args.comment.body;
  assert.equal(validate(f.args).ok, false);
});
