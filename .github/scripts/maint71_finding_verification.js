'use strict';

const { createHash } = require('node:crypto');
const sha256 = (text) => createHash('sha256').update(text).digest('hex');

// An explicitly authorized owner attests an independent, completed assessment.
// This is NOT a fabricated originating-reviewer reply or a generic clean review.
function validateIndependentFindingVerification({
  proof, record, thread, threads, comment, policy, reviewerProfiles, now = Date.now(),
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
  const completion = threads.nodes.flatMap((item) => item.comments.nodes).find((item) =>
    item.url === result.originating_completion_url && profile.logins.includes(item.author?.login)
    && item.commit?.oid === proof.head_sha
    && profile.disposition_completion_prefixes?.some((prefix) => item.body?.startsWith(prefix)));
  const times = [request?.createdAt, completion?.createdAt, result.completed_at,
    comment?.created_at].map((value) => Date.parse(value || ''));
  if (times.some((value) => !Number.isFinite(value)) || times[1] < times[0]
    || times[2] < times[1] || times[3] < times[2] || times[3] > now
    || now - times[2] > 24 * 60 * 60 * 1000) return deny('failed_transport_or_freshness_unproven');
  if (!completion) return deny('originating_completion_missing');
  if (thread.comments.nodes.some((item) => profile.logins.includes(item.author?.login)
    && Date.parse(item.createdAt || '') > times[2])) return deny('reviewer_changed_after_verification');
  return { ok: true, assessment_id: result.assessment_id, binding };
}

module.exports = { sha256, validateIndependentFindingVerification };
