'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { sha256, validateIndependentFindingVerification: validate } = require('../maint71_finding_verification');
const { validateReviewResolutionProof } = require('../maint71_merge_sync_prs');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

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

// Exercise the actual controller closure with API doubles, including both race
// checkpoints. Extracting the closure avoids a test-only production export.
for (const race of ['none', 'rest-head', 'graphql-head', 'graphql-plan', 'attestation-edited', 'attestation-deleted']) {
  test(`controller resolves only unchanged live verification: ${race}`, async () => {
    const f = fixture();
    const { args } = f;
    Object.assign(args.record, { schema: 'sync-pr-delivery-record/v1',
      repository: args.proof.repository, head_observed_sha: args.proof.head_sha,
      head_observed_at: '2026-10-04T00:00:00Z', desired_tree_hash: 'tree',
      lease_expires_at: '2099-01-01T00:00:00Z' });
    args.thread.isOutdated = false;
    f.finish();
    let reads = 0;
    let resolutions = 0;
    let attestationReads = 0;
    const body = (record) => `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`;
    const github = { paginate: async () => [],
      rest: { repos: { compareCommitsWithBasehead: async () => ({ data: { status: 'ahead' } }) },
        issues: { getComment: async () => {
          attestationReads++;
          if (attestationReads === 2 && race === 'attestation-deleted') throw new Error('404 deleted');
          return { data: attestationReads === 2 && race === 'attestation-edited'
            ? { ...args.comment, body: 'Acceptance withdrawn' } : args.comment };
        } },
        pulls: { get: async ({ repo }) => ({ data: repo === 'Workflows'
          ? { merged_at: '2026-10-04T00:00:00Z', merge_commit_sha: args.proof.source_fix_sha }
          : { state: 'open', head: { sha: race === 'rest-head' ? 'changed' : args.proof.head_sha },
            body: body(args.record) } }) } },
      graphql: async (query) => {
        if (query.includes('resolveReviewThread')) { resolutions++; return {}; }
        reads++;
        const record = { ...args.record };
        if (reads === 2 && race === 'graphql-plan') record.plan_id = 'changed-plan';
        return { repository: { pullRequest: {
          headRefOid: reads === 2 && race === 'graphql-head' ? 'changed' : args.proof.head_sha,
          body: body(record), reviewThreads: args.threads,
        } } };
      },
    };
    const controller = require('../maint71_merge_sync_prs');
    const source = fs.readFileSync(path.join(__dirname, '..', 'maint71_merge_sync_prs.js'), 'utf8');
    const start = source.indexOf('  async function resolveProvenReviewDebt(');
    const end = source.indexOf('  // Parse repos from previous step', start);
    assert.ok(start > 0 && end > start);
    const sandbox = {
      ...controller, ...require('../maint71_finding_verification'),
      parseDeliveryRecord: require('../sync_pr_lease_contract').parseDeliveryRecord,
      reviewResolutionProofs: [args.proof], reviewResolutionProofParseError: '',
      trustedResolutionActors: ['stranske'], reviewerProfiles: args.reviewerProfiles,
      reviewPolicy: args.policy, dryRun: false, resolutionOnly: true,
      context: { actor: 'stranske', repo: { owner: 'stranske', repo: 'Workflows' } },
      withRetry: (fn) => fn(github), withReviewReadRetry: (fn) => fn(github),
      console: { log() {} },
    };
    const resolve = vm.runInNewContext(`(function() { ${source.slice(start, end)} return resolveProvenReviewDebt; })()`, sandbox);
    const result = await resolve({ owner: 'stranske', repo: 'Ready',
      pr: { number: 1, head: { sha: args.proof.head_sha } }, deliveryRecord: args.record });
    assert.equal(resolutions, race === 'none' ? 1 : 0, JSON.stringify(result));
    assert.equal(result.errors.length, race === 'none' ? 0 : 1);
  });
}

test('stock top-level completion resolves its short ref to the exact full head', async () => {
  const { collectOriginatingCompletions } = require('../maint71_finding_verification');
  const f = fixture();
  const completion = f.args.thread.comments.nodes.pop();
  Object.assign(f.args.reviewerProfiles[0], { disposition_reviewed_commit_prefix: '**Reviewed commit:** ' });
  const item = { body: `Clean review.\n**Reviewed commit:** \`${f.args.proof.head_sha.slice(0, 10)}\``,
    user: completion.author, html_url: completion.url, created_at: completion.createdAt };
  let calls = 0;
  const github = { paginate: async () => [item], rest: { issues: { listComments() {} },
    repos: { getCommit: async () => { calls++; return { data: { sha: f.args.proof.head_sha } }; } } } };
  f.args.topLevelComments = await collectOriginatingCompletions({ owner: 'stranske', repo: 'Ready',
    number: 1, head: f.args.proof.head_sha, profiles: f.args.reviewerProfiles, read: (fn) => fn(github) });
  assert.equal(calls, 1);
  assert.equal(validate(f.finish()).ok, true);
  github.rest.repos.getCommit = async () => ({ data: { sha: 'different-full-head' } });
  f.args.topLevelComments = await collectOriginatingCompletions({ owner: 'stranske', repo: 'Ready',
    number: 1, head: f.args.proof.head_sha, profiles: f.args.reviewerProfiles, read: (fn) => fn(github) });
  assert.equal(validate(f.finish()).ok, false);
});

test('collect all outer thread and inner comment pages, rejecting interrupted or changed pages', async () => {
  const { collectFindingReviewState } = require('../maint71_finding_verification');
  for (const variant of ['complete', 'head-changed', 'cursor-missing']) {
    const calls = [];
    const github = { graphql: async (_query, vars) => {
      calls.push(vars);
      if (vars.id) return { node: { comments: {
        pageInfo: { hasNextPage: false }, nodes: [{ body: 'second-comment' }],
      } } };
      const second = Boolean(vars.after);
      return { repository: { pullRequest: {
        headRefOid: second && variant === 'head-changed' ? 'changed' : 'head',
        body: 'stable-body', reviewThreads: {
          pageInfo: { hasNextPage: !second, endCursor: variant === 'cursor-missing' ? null : 'outer-cursor' },
          nodes: [{ id: second ? 'thread2' : 'thread1', isResolved: false, isOutdated: false,
            comments: { pageInfo: { hasNextPage: !second, endCursor: 'inner-cursor' },
              nodes: [{ body: 'first-comment' }] } }],
        },
      } } };
    } };
    const run = () => collectFindingReviewState({ owner: 'owner', repo: 'repo', number: 1,
      read: (fn) => fn(github) });
    if (variant !== 'complete') { await assert.rejects(run); continue; }
    const result = await run();
    assert.equal(result.reviewThreads.nodes.length, 2);
    assert.equal(result.reviewThreads.nodes[0].comments.nodes.length, 2);
    assert.equal(result.reviewThreads.pageInfo.hasNextPage, false);
    assert.equal(calls.length, 3);
  }
});
