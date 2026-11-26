'use strict';

const { createHash } = require('node:crypto');
const sha256 = (text) => createHash('sha256').update(text).digest('hex');

function readSingleMarker(body, pattern) {
  const matches = [...String(body || '').matchAll(pattern)];
  if (matches.length !== 1) return null;
  try { return JSON.parse(matches[0][1]); } catch { return null; }
}

const findingVerification = (body) => readSingleMarker(body,
  /<!-- maint71-finding-verification:v1 ([\s\S]*?) -->/g);
const targetedRequest = (body) => readSingleMarker(body,
  /<!-- maint71-review-(?:reassessment|disposition):v1 ([\s\S]*?) -->/g);

// An explicitly authorized owner attests an independent, completed assessment.
// This is NOT a fabricated originating-reviewer reply or a generic clean review.
function validateIndependentFindingVerification({
  proof, record, thread, threads, comment, policy, reviewerProfiles,
  topLevelComments, inlineCompletion, now = Date.now(),
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
    && profile.disposition_completion_prefixes?.some((prefix) => item.body?.startsWith(prefix)))
    || (inlineCompletion && inlineCompletion.url === result.originating_completion_url
      && inlineCompletion.requestUrl === request.url && inlineCompletion.head === proof.head_sha
      && inlineCompletion.threadId === thread.id ? inlineCompletion : null);
  let completedAt = completion?.createdAt;
  if (!completion) {
    // Reviewer-unanswered path (owner decision 2026-11-06): a reviewer that is out of
    // capacity (Copilot most months) would otherwise latch its findings forever. When
    // the targeted request has stood for the policy window and the originating reviewer
    // has said nothing IN THIS THREAD since, the independent assessment stands on its
    // own; every other binding, validation and freshness check below still applies.
    // The window counts from the FIRST trusted reassessment request in this thread, on any
    // head: a busy canary is rebased to a new head every hour or two, and a window tied to
    // the current head's request could never elapse (trip-planner#1957, 2026-11-06). The
    // reviewer's silence since that first request is the signal; the current head still
    // needs its own bound request (checked above), and the assessment stays exact-head.
    const windowMinutes = Number(fallback.unanswered_reassessment_minutes);
    if (!(windowMinutes > 0) || result.reviewer_unanswered !== true
      || result.originating_completion_url !== null) return deny('originating_completion_missing');
    const sameFinding = (item) => {
      if (!fallback.trusted_publishers.includes(item?.author?.login)) return false;
      const found = [...String(item?.body || '').matchAll(
        /<!-- maint71-review-(?:reassessment|disposition):v1 ([\s\S]*?) -->/g)];
      if (found.length !== 1) return false;
      let earlier;
      try { earlier = JSON.parse(found[0][1]); } catch { return false; }
      return ['repository', 'pr', 'thread_id', 'originating_reviewer']
        .every((key) => earlier?.[key] === binding[key]);
    };
    const requestTimes = thread.comments.nodes.filter(sameFinding)
      .map((item) => Date.parse(item?.createdAt || ''))
      .filter((value) => Number.isFinite(value));
    const firstRequestedAt = requestTimes.length ? Math.min(...requestTimes) : NaN;
    if (!Number.isFinite(firstRequestedAt) || !Number.isFinite(Date.parse(request?.createdAt || ''))) {
      return deny('originating_completion_missing');
    }
    if (thread.comments.nodes.some((item) => profile.logins.includes(item?.author?.login)
      && Date.parse(item?.createdAt || '') > firstRequestedAt)) return deny('originating_reviewer_answered');
    if (Date.parse(result.completed_at || '') - firstRequestedAt < windowMinutes * 60 * 1000) {
      return deny('reassessment_window_open');
    }
    completedAt = request.createdAt;
  }
  const times = [request?.createdAt, completedAt, result.completed_at,
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

function stockReviewedCommit(body, profile) {
  const [marker, gap, summary, secondGap, reference, ...details] = String(body || '').trimEnd().split(/\r?\n/);
  if (marker !== profile.inline_targeted_stock_completion.marker || gap !== '' || secondGap !== ''
    || !profile.disposition_completion_prefixes?.some((item) => summary?.startsWith(item))) return null;
  const prefix = profile.disposition_reviewed_commit_prefix;
  if (!prefix || !reference?.startsWith(prefix) || details.some((line) => line.startsWith(prefix))) return null;
  const suffix = details.join('\n').trim();
  if (suffix && !/^<details>(?: <summary>[^<\n]+<\/summary>)?\n[\s\S]*\n<\/details>$/.test(suffix)) return null;
  return /^`([0-9a-f]{10,40})`$/.exec(reference.slice(prefix.length))?.[1] || null;
}

// This is completion evidence for the independent assessment only. The native
// inline commit is the diff anchor. The enclosing PR review records the head.
async function collectAuthenticatedInlineStockCompletion({
  proof, record, thread, comment, policy, reviewerProfiles, owner, repo, number, head, headRef, body, read,
}) {
  const result = findingVerification(comment?.body);
  const profile = reviewerProfiles.find((item) => item.id === proof.originating_reviewer);
  const provenance = profile?.inline_targeted_stock_completion;
  const publishers = policy.finding_verification_fallback?.trusted_publishers;
  if (!result?.originating_completion_url || result.reviewer_unanswered === true
    || !Number.isSafeInteger(provenance?.bot_id) || !provenance.bot_node_id || !provenance.marker
    || proof.repository !== `${owner}/${repo}` || proof.pr !== number || proof.head_sha !== head
    || !headRef || typeof body !== 'string' || record?.head_observed_sha !== head
    || thread?.id !== proof.thread_id || thread.isOutdated !== true
    || thread.isResolved !== false || thread.comments?.pageInfo?.hasNextPage !== false
    || !Array.isArray(thread.comments?.nodes) || !publishers?.includes(comment?.user?.login)) return null;
  const [original, ...replies] = thread.comments.nodes;
  if (!profile.logins?.includes(original?.author?.login)
    || result.finding_sha256 !== sha256(String(original.body || ''))) return null;
  const requests = replies.filter((item) => {
    if (!publishers.includes(item.author?.login)) return false;
    const binding = targetedRequest(item.body);
    return binding?.repository === proof.repository && binding.pr === number
      && binding.thread_id === thread.id && binding.originating_reviewer === profile.id;
  });
  const [request] = requests;
  if (requests.length !== 1 || request.url !== result.reassessment_request_url) return null;
  const binding = targetedRequest(request.body);
  if (binding.head_sha !== head || binding.plan_id !== record.plan_id
    || binding.generation !== record.generation || binding.source_commit !== record.source_commit) return null;
  const laterReplies = replies.filter((item) => profile.logins.includes(item.author?.login)
    && Date.parse(item.createdAt) > Date.parse(request.createdAt));
  const [reply] = laterReplies;
  if (laterReplies.length !== 1 || reply.url !== result.originating_completion_url
    || replies.indexOf(request) >= replies.indexOf(reply)) return null;
  return collectBoundInlineStockCompletion({
    original, request, reply, profile, threadId: thread.id, owner, repo, number, head, headRef, body, read,
  });
}

// Authenticates stock completion for a bound request. Callers separately decide
// whether the completed review can request a disposition or support an assessment.
async function collectBoundInlineStockCompletion({
  original, request, reply, profile, threadId, owner, repo, number, head, headRef, body, read,
}) {
  const provenance = profile?.inline_targeted_stock_completion;
  if (!Number.isSafeInteger(provenance?.bot_id) || !provenance.bot_node_id || !provenance.marker) return null;
  const ref = stockReviewedCommit(reply.body, profile);
  if (!ref || !head.startsWith(ref)) return null;

  const webPull = `https://github.com/${owner}/${repo}/pull/${number}`;
  const id = (item) => String(item.fullDatabaseId || '');
  if ([original, request, reply].some((item) => !/^[1-9]\d*$/.test(id(item))
    || item.url !== `${webPull}#discussion_r${id(item)}`)) return null;
  const scope = { owner, repo };
  const lookup = async (operation) => {
    try { return (await read(operation)).data; } catch (error) {
      if ([404, 422].includes(error.status)) return null;
      throw error;
    }
  };
  const nativeComment = (item) => lookup((client) => client.rest.pulls.getReviewComment({
    ...scope, comment_id: id(item),
  }));
  const [nativeOriginal, nativeRequest, nativeReply] = await Promise.all(
    [original, request, reply].map(nativeComment),
  );
  const sameComment = (native, item) => String(native?.id || '') === id(item)
    && native.html_url === item.url
    && native.body === item.body && native.created_at === item.createdAt && native.updated_at === item.updatedAt;
  const isOriginatingBot = (actor) => actor?.id === provenance.bot_id && actor.node_id === provenance.bot_node_id
    && actor.type === 'Bot' && profile.logins.includes(actor.login);
  if (!sameComment(nativeOriginal, original) || !sameComment(nativeRequest, request)
    || !sameComment(nativeReply, reply) || nativeOriginal.in_reply_to_id != null
    || !nativeOriginal.path || nativeRequest.path !== nativeOriginal.path || nativeReply.path !== nativeOriginal.path
    || String(nativeRequest.in_reply_to_id) !== id(original) || String(nativeReply.in_reply_to_id) !== id(original)
    || nativeRequest.user?.login !== request.author.login || !Number.isSafeInteger(nativeRequest.user?.id)
    || !nativeRequest.user.node_id || !isOriginatingBot(nativeOriginal.user) || !isOriginatingBot(nativeReply.user)
    || !(Date.parse(original.createdAt) < Date.parse(request.createdAt))
    || ![nativeRequest, nativeReply].every((item) => Number.isSafeInteger(item.pull_request_review_id)
      && item.pull_request_review_id > 0)) return null;
  const nativeReview = (item) => lookup((client) => client.rest.pulls.getReview({
    ...scope, pull_number: number, review_id: item.pull_request_review_id,
  }));
  const [requestReview, replyReview, commit] = await Promise.all([
    nativeReview(nativeRequest), nativeReview(nativeReply),
    lookup((client) => client.rest.repos.getCommit({ ...scope, ref })),
  ]);
  const exactReview = (review, native) => review?.id === native.pull_request_review_id
    && review.html_url === `${webPull}#pullrequestreview-${review.id}`
    && review.state === 'COMMENTED' && review.commit_id === head
    && review.submitted_at === native.created_at && review.user?.id === native.user.id
    && review.user.node_id === native.user.node_id && review.user.login === native.user.login;
  if (!exactReview(requestReview, nativeRequest) || !exactReview(replyReview, nativeReply)
    || !isOriginatingBot(replyReview.user) || commit?.sha !== head) return null;
  const current = await lookup((client) => client.rest.pulls.get({ ...scope, pull_number: number }));
  if (current?.state !== 'open' || current.number !== number || current.head?.sha !== head
    || current.head.ref !== headRef || current.body !== body) return null;
  return { url: reply.url, requestUrl: request.url, threadId, head, createdAt: reply.createdAt };
}

async function validateIndependentFindingFromNative(args) {
  const resolution = validateIndependentFindingVerification(args);
  if (resolution.reason !== 'originating_completion_missing') return resolution;
  const inlineCompletion = await collectAuthenticatedInlineStockCompletion(args);
  if (!inlineCompletion) return resolution;

  // Stock lookups happen after the initial conversation snapshot. Refresh any
  // originating reviewer activity before trusting that snapshot for resolution.
  const { owner, repo, number, head, read, reviewerProfiles } = args;
  const topLevelComments = await collectOriginatingCompletions({
    owner, repo, number, head, profiles: reviewerProfiles, read,
  });
  const latest = await collectFindingReviewState({ owner, repo, number, read });
  const threads = latest.reviewThreads;
  const thread = threads.nodes.find((item) => item.id === args.thread.id);
  const prior = args.thread.comments.nodes;
  const observed = thread?.comments?.nodes;
  if (latest.headRefOid !== head || latest.headRefName !== args.headRef || latest.body !== args.body
    || thread?.isOutdated !== true || thread.isResolved !== false || observed?.length !== prior.length
    || !observed.every((item, index) => item.fullDatabaseId === prior[index].fullDatabaseId
      && item.url === prior[index].url && item.body === prior[index].body
      && item.createdAt === prior[index].createdAt && item.updatedAt === prior[index].updatedAt
      && item.author?.login === prior[index].author?.login && item.commit?.oid === prior[index].commit?.oid)) {
    return { ok: false, reason: 'originating_completion_evidence_changed' };
  }
  return validateIndependentFindingVerification({ ...args, thread, threads, topLevelComments, inlineCompletion });
}

function nativeAnswerLines(body, markers) {
  if (String(body || '').includes('__MAINT71_MARKER_')) return null;
  const protectedLines = new Map(); let serial = 0;
  let input = String(body || '').split('\n').map((line) => {
    const marker = markers.find((value) => line.trim() === value);
    if (!marker) return line;
    const token = `__MAINT71_MARKER_${serial++}__`; protectedLines.set(token, marker);
    return line.replace(marker, token);
  }).join('\n');
  if (/<!--/.test(input) && !/-->/s.test(input.slice(input.indexOf('<!--')))) return null;
  input = input.replace(/<!--[\s\S]*?-->/g, '\n');
  if (/<!--|-->/.test(input)) return null;
  const lines = []; let fence = null; let quotedParagraph = false; const containers = [];
  for (const raw of input.split('\n')) {
    if (/`.*<!--/.test(raw) || /<!--.*`/.test(raw)) return null;
    if (!fence && containers.length === 0) {
      if (!raw.trim()) quotedParagraph = false;
      else if (/^\s*>/.test(raw)) quotedParagraph = true;
      if (quotedParagraph) continue;
    }
    if (fence) {
      const closer = raw.match(/^ {0,3}(`{3,}|~{3,})[ \t]*$/);
      if (closer && closer[1][0] === fence.char && closer[1].length >= fence.length) fence = null;
      continue;
    }
    const opener = raw.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (opener && !(opener[1][0] === '`' && opener[2].includes('`'))) {
      fence = { char: opener[1][0], length: opener[1].length };
      continue;
    }
    // The protocol permits known balanced containers, never raw processing,
    // declaration or CDATA blocks (CommonMark HTML block types 3-5).
    if (containers.length === 0 && /^(?: {4}|\t)/.test(raw)) continue;
    if (/<[!?]/.test(raw) || /<\/?[A-Za-z][^>]*$/.test(raw)) return null;
    const tags = [...raw.matchAll(/<(\/)?([A-Za-z][\w:-]*)\b[^>]*>/g)];
    const residual = tags.reduce((text, tag) => text.replace(tag[0], ''), raw);
    if (/<|(?<!-)>(?=\s*$)/.test(residual)) return null;
    let cursor = 0; let visible = '';
    for (const tag of tags) {
      if (containers.length === 0) visible += raw.slice(cursor, tag.index);
      const type = tag[2].toLowerCase();
      const valid = tag[1]
        ? new RegExp(`^</${type}\\s*>$`, 'i').test(tag[0])
        : new RegExp(`^<${type}(?:\\s+[A-Za-z_:][\\w:.-]*(?:\\s*=\\s*(?:"[^"]*"|'[^']*'|[^\\s"'=<>\\x60]+))?)*\\s*>$`, 'i').test(tag[0]);
      if (!valid) return null;
      if (!['details', 'blockquote', 'pre', 'code', 'script', 'style', 'textarea'].includes(type)) {
        if (containers.length === 0) return null;
        continue;
      }
      if (tag[1]) { if (containers.pop() !== type) return null; }
      else { if (containers.length >= 8) return null; containers.push(type); }
      cursor = tag.index + tag[0].length;
    }
    if (containers.length === 0) visible += raw.slice(cursor);
    // Keep every outside segment, even when this line opens a container.
    // Its Markdown delimiters must remain visible to the leading-prefix gate.
    if (visible) lines.push(visible);
  }
  if (fence || containers.length) return null;
  let text = lines.join('\n');
  for (const [token, marker] of protectedLines) text = text.replaceAll(token, marker);
  return text.split('\n').map((line) => line.trim()).filter(Boolean);
}

function validateNativeConversationDisposition({
  proof, record, thread, threads, comment, policy, reviewerProfiles, topLevelComments, now = Date.now(),
}) {
  const deny = (reason) => ({ ok: false, reason });
  const fallback = policy?.finding_verification_fallback;
  if (fallback?.enabled !== true || !Array.isArray(fallback.trusted_publishers)) return deny('native_conversation_disabled');
  const profile = reviewerProfiles.find((item) => item.id === proof?.originating_reviewer);
  const configured = profile?.conversation_disposition;
  if (!record || !thread || thread.isResolved !== false || !Array.isArray(threads?.nodes)
    || threads.pageInfo?.hasNextPage !== false || topLevelComments?.complete !== true
    || threads.nodes.some((item) => item.comments?.pageInfo?.hasNextPage !== false || !Array.isArray(item.comments?.nodes))
    || !['maint71-native-conversation-disposition/v1', 'maint71-native-conversation-disposition/v2'].includes(configured?.protocol)
    || !Array.isArray(configured.logins) || configured.logins.length === 0
    || configured.logins.some((login) => !profile.logins?.includes(login))) return deny('native_conversation_binding_incomplete');
  const original = thread.comments?.nodes?.[0];
  const expectedRequest = { repository: proof.repository, pr: proof.pr, head_sha: proof.head_sha,
    thread_id: proof.thread_id, plan_id: record.plan_id, generation: record.generation,
    source_commit: record.source_commit, originating_reviewer: proof.originating_reviewer };
  const candidates = [];
  for (const item of thread.comments?.nodes || []) {
    if (!fallback.trusted_publishers.includes(item?.author?.login)) continue;
    const matches = [...String(item?.body || '').matchAll(/<!-- maint71-review-conversation-disposition:v1 ([\s\S]*?) -->/g)];
    if (matches.length > 1) return deny('native_conversation_request_malformed');
    if (matches.length === 0) continue;
    let parsed; try { parsed = JSON.parse(matches[0][1]); } catch (_) { return deny('native_conversation_request_malformed'); }
    if (Object.keys(expectedRequest).every((key) => parsed[key] === expectedRequest[key])) candidates.push(item);
  }
  if (candidates.length !== 1) return deny('native_conversation_request_missing');
  const request = candidates[0];
  const requestId = String(request?.fullDatabaseId || request?.id || '');
  const requestUrl = String(request?.url || request?.html_url || '');
  const findingId = String(original?.fullDatabaseId || original?.id || '');
  if (!profile.logins?.includes(original?.author?.login) || !/^[1-9]\d*$/.test(requestId)
    || !/^[1-9]\d*$/.test(findingId) || !requestUrl) return deny('native_conversation_request_missing');
  const binding = { protocol: configured.protocol, repository: proof.repository, pr: proof.pr,
    head_sha: proof.head_sha, thread_id: proof.thread_id, plan_id: record.plan_id, generation: record.generation,
    source_commit: record.source_commit, originating_reviewer: proof.originating_reviewer, inline_request_id: requestId,
    inline_request_url: requestUrl, finding_id: findingId, finding_sha256: sha256(String(original.body || '')) };
  const requestJson = [...String(request.body || '').matchAll(/<!-- maint71-review-conversation-disposition:v1 ([\s\S]*?) -->/g)];
  if (requestJson.length !== 1) return deny('native_conversation_request_malformed');
  try {
    const parsed = JSON.parse(requestJson[0][1]);
    for (const key of Object.keys(expectedRequest)) {
      if (parsed[key] !== binding[key]) return deny('native_conversation_request_binding_mismatch');
    }
  } catch (_) { return deny('native_conversation_request_malformed'); }
  const markerVersion = configured.protocol === 'maint71-native-conversation-disposition/v2' ? 'v2' : 'v1';
  const marker = `<!-- maint71-native-conversation-disposition:${markerVersion} ${sha256(JSON.stringify(binding))} -->`;
  const acceptance = `<!-- sync-review-accepted:${proof.head_sha} -->`;
  const tasks = topLevelComments.nodes.filter((item) => fallback.trusted_publishers.includes(item?.author?.login)
    && String(item?.body || '').includes(marker));
  const lines = nativeAnswerLines(comment?.body, [acceptance, marker]);
  if (!lines) return deny('native_conversation_answer_malformed');
  const verdicts = lines.filter((line) => /^(?:ACCEPT|REJECT)$/.test(line));
  const accepted = lines.indexOf('ACCEPT');
  const taskAuthor = String(tasks[0]?.user?.login || tasks[0]?.author?.login || '');
  const taskMention = `@${taskAuthor}`;
  const v2 = configured.protocol === 'maint71-native-conversation-disposition/v2';
  const exactTaskMention = (line) => line === taskMention || line === `\`${taskMention}\``;
  const times = [request.createdAt, tasks[0]?.createdAt || tasks[0]?.created_at, comment?.created_at].map((value) => Date.parse(value || ''));
  if (tasks.length !== 1 || comment?.html_url !== proof.reviewer_acceptance_url
    || !configured.logins.includes(comment?.user?.login) || !taskAuthor || verdicts.length !== 1
    || (v2 ? (accepted !== 1 || !exactTaskMention(lines[0]) || lines[2] !== acceptance || lines[3] !== marker)
      : (accepted !== 0 || lines[1] !== acceptance || lines[2] !== marker))
    || !lines.slice(accepted).includes(acceptance) || !lines.slice(accepted).includes(marker)
    || times.some((value) => !Number.isFinite(value)) || times[1] < times[0] || times[2] <= times[1]
    || times[2] > now || now - times[2] > 24 * 60 * 60 * 1000) return deny('native_conversation_answer_mismatch');
  const reviewerComments = [...threads.nodes.flatMap((item) => item.comments.nodes), ...(topLevelComments.nodes || [])];
  if (reviewerComments.some((item) => {
    if (!configured.logins.includes(item?.author?.login || item?.user?.login)) return false;
    if (item?.url === comment?.html_url) return false;
    const created = Date.parse(item?.createdAt || item?.created_at || '');
    const updated = Date.parse(item?.updatedAt || item?.updated_at || '');
    const observed = Math.max(Number.isFinite(created) ? created : -Infinity, Number.isFinite(updated) ? updated : -Infinity);
    if (observed > times[2]) return true;
    // GitHub timestamps are second-granularity on some surfaces. Cross-domain
    // review/issue IDs have no stable ordering, so another same-second reviewer
    // comment is ambiguous and must block unless it is the acceptance itself.
    return observed === times[2] && item?.url !== comment?.html_url;
  })) return deny('native_conversation_changed_after_acceptance');
  return { ok: true, binding };
}

async function collectFindingReviewState({ owner, repo, number, read }) {
  // The controller supplies read from createTokenAwareRetry; helpers never
  // create an unwrapped client or bypass the caller's capability/token policy.
  if (typeof read !== 'function') throw new TypeError('Wrapped review read is required');
  const fields = 'fullDatabaseId url body createdAt updatedAt author { login } commit { oid }';
  let after = null;
  let snapshot;
  const nodes = [];
  do {
    const data = await read((client) => client.graphql(`
      query($owner:String!,$repo:String!,$number:Int!,$after:String) {
        repository(owner:$owner,name:$repo) { pullRequest(number:$number) {
          headRefOid headRefName body reviewThreads(first:100,after:$after) {
            pageInfo { hasNextPage endCursor } nodes { id isResolved isOutdated
              comments(first:100) { pageInfo { hasNextPage endCursor } nodes { ${fields} } }
            }
          }
        } }
      }`, { owner, repo, number, after }));
    const fresh = data?.repository?.pullRequest;
    if (!fresh?.headRefOid || !fresh?.headRefName || !Array.isArray(fresh.reviewThreads?.nodes)
      || typeof fresh.reviewThreads?.pageInfo?.hasNextPage !== 'boolean') {
      throw new Error('Incomplete review-thread inventory');
    }
    if (snapshot && (snapshot.headRefOid !== fresh.headRefOid
      || snapshot.headRefName !== fresh.headRefName || snapshot.body !== fresh.body)) {
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

async function collectOriginatingCompletions({ owner, repo, number, head, profiles, read, includeAuthors = [] }) {
  // read is the owner's withRetry from createTokenAwareRetry.
  if (typeof read !== 'function') throw new TypeError('Wrapped completion read is required');
  const comments = await read((client) => client.paginate(client.rest.issues.listComments,
    { owner, repo, issue_number: number, per_page: 100 }));
  if (!Array.isArray(comments)) throw new Error('Incomplete top-level comment inventory');
  const nodes = [];
  for (const comment of comments) {
    const profile = profiles.find((item) => item.logins.includes(comment.user?.login));
    if (!profile && !includeAuthors.includes(comment.user?.login)) continue;
    const node = { id: comment.id, url: comment.html_url, body: comment.body, createdAt: comment.created_at, updatedAt: comment.updated_at,
      author: comment.user };
    nodes.push(node);
    if (!profile || !profile.disposition_completion_prefixes?.some((prefix) => comment.body?.startsWith(prefix))) continue;
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

module.exports = { sha256, nativeAnswerLines, validateIndependentFindingVerification, validateNativeConversationDisposition,
  collectFindingReviewState, collectOriginatingCompletions, collectAuthenticatedInlineStockCompletion,
  collectBoundInlineStockCompletion, validateIndependentFindingFromNative };
