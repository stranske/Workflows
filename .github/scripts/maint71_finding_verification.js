'use strict';

const { createHash } = require('node:crypto');
const sha256 = (text) => createHash('sha256').update(text).digest('hex');

// An explicitly authorized owner attests an independent, completed assessment.
// This is NOT a fabricated originating-reviewer reply or a generic clean review.
function validateIndependentFindingVerification({
  proof, record, thread, threads, comment, policy, reviewerProfiles,
  topLevelComments, now = Date.now(),
}) {
  const deny = (reason) => ({ ok: false, reason });
  const fallback = policy?.finding_verification_fallback;
  if (fallback?.enabled !== true) return deny('fallback_disabled');
  if (!record || !proof || !thread || thread.isResolved !== false) return deny('missing_binding');
  if (!Array.isArray(fallback.trusted_publishers)
    || !fallback.trusted_publishers.includes(comment?.user?.login)) {
    return deny('untrusted_verification_publisher');
  }
  const url = `${record?.durable_issue_url}#issuecomment-${comment?.id}`;
  if (comment?.html_url !== url || proof.reviewer_acceptance_url !== url) {
    return deny('verification_url_mismatch');
  }
  if (!Array.isArray(threads?.nodes) || threads.pageInfo?.hasNextPage !== false
    || threads.nodes.some((item) => item.comments?.pageInfo?.hasNextPage !== false
      || !Array.isArray(item.comments?.nodes))) return deny('incomplete_thread_evidence');
  const original = thread?.comments?.nodes?.[0];
  const profile = reviewerProfiles.find((item) => item.id === proof.originating_reviewer);
  if (!profile?.logins?.includes(original?.author?.login)) return deny('originating_reviewer_mismatch');
  const matches = [...String(comment?.body || '').matchAll(
    /<!-- maint71-finding-verification:v1 ([\s\S]*?) -->/g,
  )];
  if (matches.length !== 1) return deny('missing_or_duplicate_verification');
  let result;
  try { result = JSON.parse(matches[0][1]); } catch { return deny('malformed_verification'); }
  if (result.schema !== 'workflows-sync-finding-verification/v1'
    || result.verdict !== 'PASS' || result.status !== 'completed'
    || result.coverage !== 'complete'
    || !fallback.verifier_profiles?.includes(result.verifier_profile)
    || !/^[a-f0-9]{64}$/.test(result.assessment_id || '')
    || !/^[a-f0-9]{64}$/.test(result.result_sha256 || '')
    || typeof result.rationale !== 'string' || result.rationale.trim().length < 40) {
    return deny('incomplete_or_nonpass_verification');
  }
  const binding = {
    repository: proof.repository, pr: proof.pr, head_sha: proof.head_sha,
    thread_id: proof.thread_id, originating_reviewer: proof.originating_reviewer,
    source_fix_sha: proof.source_fix_sha, evidence_url: proof.evidence_url,
    plan_id: record.plan_id, generation: record.generation, source_commit: record.source_commit,
    finding_sha256: sha256(String(original.body || '')),
  };
  for (const [key, value] of Object.entries(binding)) {
    if (!value || result[key] !== value) return deny(`verification_binding_mismatch:${key}`);
  }
  if (!Array.isArray(result.validation) || result.validation.length === 0
    || result.validation.some((item) => !item.command || item.exit_code !== 0
      || item.negative_control !== 'failed-before-fix')) return deny('regression_validation_missing');
  const request = thread.comments.nodes.find((item) =>
    item.url === result.reassessment_request_url
    && fallback.trusted_publishers.includes(item.author?.login));
  const requestMatches = [...String(request?.body || '').matchAll(
    /<!-- maint71-review-(?:reassessment|disposition):v1 ([\s\S]*?) -->/g,
  )];
  if (requestMatches.length !== 1) return deny('targeted_request_missing');
  let requestBinding;
  try { requestBinding = JSON.parse(requestMatches[0][1]); } catch { return deny('targeted_request_malformed'); }
  for (const key of ['repository', 'pr', 'head_sha', 'thread_id', 'plan_id',
    'generation', 'source_commit', 'originating_reviewer']) {
    if (requestBinding[key] !== binding[key]) return deny('targeted_request_binding_mismatch');
  }
  if (topLevelComments && topLevelComments.complete !== true) return deny('incomplete_completion_evidence');
  const completion = [...threads.nodes.flatMap((item) => item.comments.nodes),
    ...(topLevelComments?.nodes || [])].find((item) =>
    item.url === result.originating_completion_url && profile.logins.includes(item.author?.login)
    && item.commit?.oid === proof.head_sha
    && profile.disposition_completion_prefixes?.some((prefix) => item.body?.startsWith(prefix)));
  if (!completion) return deny('originating_completion_missing');
  const times = [request?.createdAt, completion?.createdAt, result.completed_at,
    comment?.created_at].map((value) => Date.parse(value || ''));
  if (times.some((value) => !Number.isFinite(value)) || times[1] < times[0]
    || times[2] < times[1] || times[3] < times[2] || times[3] > now
    || now - times[2] > 24 * 60 * 60 * 1000) return deny('failed_transport_or_freshness_unproven');
  const reviewerComments = [...threads.nodes.flatMap((item) => item.comments.nodes),
    ...(topLevelComments?.nodes || [])];
  if (reviewerComments.some((item) => profile.logins.includes(item.author?.login)
    && Date.parse(item.createdAt || '') > times[2])) return deny('reviewer_changed_after_verification');
  return { ok: true, assessment_id: result.assessment_id, binding };
}

async function collectFindingReviewState({ owner, repo, number, read }) {
  // The controller supplies read from createTokenAwareRetry; helpers never
  // create an unwrapped client or bypass the caller's capability/token policy.
  if (typeof read !== 'function') throw new TypeError('Wrapped review read is required');
  const fields = 'url body createdAt author { login } commit { oid }';
  let after = null;
  let snapshot;
  const nodes = [];
  do {
    const data = await read((client) => client.graphql(`
      query($owner:String!,$repo:String!,$number:Int!,$after:String) {
        repository(owner:$owner,name:$repo) { pullRequest(number:$number) {
          headRefOid body reviewThreads(first:100,after:$after) {
            pageInfo { hasNextPage endCursor } nodes { id isResolved isOutdated
              comments(first:100) { pageInfo { hasNextPage endCursor } nodes { ${fields} } }
            }
          }
        } }
      }`, { owner, repo, number, after }));
    const fresh = data?.repository?.pullRequest;
    if (!fresh?.headRefOid || !Array.isArray(fresh.reviewThreads?.nodes)
      || typeof fresh.reviewThreads?.pageInfo?.hasNextPage !== 'boolean') {
      throw new Error('Incomplete review-thread inventory');
    }
    if (snapshot && (snapshot.headRefOid !== fresh.headRefOid || snapshot.body !== fresh.body)) {
      throw new Error('Delivery changed during review pagination');
    }
    snapshot = fresh;
    for (const thread of fresh.reviewThreads.nodes) {
      if (!Array.isArray(thread.comments?.nodes)
        || typeof thread.comments?.pageInfo?.hasNextPage !== 'boolean') {
        throw new Error('Incomplete thread-comment inventory');
      }
      while (thread.comments.pageInfo.hasNextPage) {
        const cursor = thread.comments.pageInfo.endCursor;
        if (!cursor) throw new Error('Missing thread-comment cursor');
        const page = await read((client) => client.graphql(`
          query($id:ID!,$after:String!) { node(id:$id) { ... on PullRequestReviewThread {
            comments(first:100,after:$after) { pageInfo { hasNextPage endCursor } nodes { ${fields} } }
          } } }`, { id: thread.id, after: cursor }));
        const connection = page?.node?.comments;
        if (!Array.isArray(connection?.nodes)
          || typeof connection?.pageInfo?.hasNextPage !== 'boolean'
          || (connection.pageInfo.hasNextPage && connection.pageInfo.endCursor === cursor)) {
          throw new Error('Incomplete thread-comment page');
        }
        thread.comments.nodes.push(...connection.nodes);
        thread.comments.pageInfo = connection.pageInfo;
      }
      nodes.push(thread);
    }
    const info = fresh.reviewThreads.pageInfo;
    if (!info.hasNextPage) break;
    if (!info.endCursor || info.endCursor === after) throw new Error('Missing review-thread cursor');
    after = info.endCursor;
  } while (true);
  return { ...snapshot, reviewThreads: { pageInfo: { hasNextPage: false }, nodes } };
}

async function collectOriginatingCompletions({ owner, repo, number, head, profiles, read }) {
  // read is the owner's withRetry from createTokenAwareRetry.
  if (typeof read !== 'function') throw new TypeError('Wrapped completion read is required');
  const comments = await read((client) => client.paginate(client.rest.issues.listComments,
    { owner, repo, issue_number: number, per_page: 100 }));
  if (!Array.isArray(comments)) throw new Error('Incomplete top-level comment inventory');
  const nodes = [];
  for (const comment of comments) {
    const profile = profiles.find((item) => item.logins.includes(comment.user?.login));
    if (!profile) continue;
    const node = { url: comment.html_url, body: comment.body, createdAt: comment.created_at,
      author: comment.user };
    nodes.push(node);
    if (!profile.disposition_completion_prefixes?.some((prefix) => comment.body?.startsWith(prefix))) continue;
    const prefix = profile.disposition_reviewed_commit_prefix;
    if (!prefix) continue;
    const line = String(comment.body || '').split('\n').find((value) => value.startsWith(prefix));
    const ref = line?.slice(prefix.length).match(/`([0-9a-f]{10,40})`/)?.[1];
    if (!ref || !head.startsWith(ref)) continue;
    let commit;
    try {
      ({ data: commit } = await read((client) => client.rest.repos.getCommit({ owner, repo, ref })));
    } catch (error) {
      if ([404, 422].includes(error.status)) continue;
      throw error;
    }
    if (commit.sha !== head) continue;
    node.commit = { oid: commit.sha };
  }
  return { complete: true, nodes };
}

module.exports = { sha256, validateIndependentFindingVerification,
  collectFindingReviewState, collectOriginatingCompletions };
