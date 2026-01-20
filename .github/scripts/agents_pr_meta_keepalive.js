'use strict';

const { createGithubApiCache } = require('./github-api-cache-client');
const { makeTrace } = require('./keepalive_contract.js');

const DEFAULT_INSTRUCTION_SIGNATURE =
  'keepalive workflow continues nudging until everything is complete';

/**
 * Sleep for a specified duration
 * @param {number} ms - Duration in milliseconds
 * @returns {Promise<void>}
 */
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function getGithubApiCache({ github, core }) {
  if (!github) {
    return createGithubApiCache({ core });
  }
  if (github.__agentsPrMetaApiCache) {
    return github.__agentsPrMetaApiCache;
  }
  const cache = createGithubApiCache({ core });
  Object.defineProperty(github, '__agentsPrMetaApiCache', {
    value: cache,
    enumerable: false,
    configurable: false,
    writable: false,
  });
  return cache;
}

async function fetchPullRequestCached({ github, owner, repo, prNumber, core, maxRetries = 3 }) {
  if (!github?.rest?.pulls?.get || !owner || !repo) {
    return null;
  }
  const number = Number(prNumber);
  if (!Number.isFinite(number) || number <= 0) {
    return null;
  }
  const cache = getGithubApiCache({ github, core });
  const key = cache.buildPrCacheKey({ owner, repo, number, resource: 'pulls.get' });
  return cache.getOrSet({
    key,
    fetcher: async () => {
      let lastError;
      for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
        try {
          const response = await github.rest.pulls.get({ owner, repo, pull_number: number });
          const data = response?.data;
          if (!data) {
            const dataError = new Error('pull request data unavailable');
            if (response && typeof response === 'object') {
              dataError.status = response.status;
            }
            throw dataError;
          }
          return data;
        } catch (error) {
          lastError = error;
          const message = error instanceof Error ? error.message : String(error);
          if (isTransientError(error) && attempt < maxRetries) {
            const delayMs = 1000 * Math.pow(2, attempt - 1);
            if (core?.warning) {
              core.warning(`PR fetch attempt ${attempt}/${maxRetries} failed (${message}), retrying in ${delayMs}ms...`);
            }
            await sleep(delayMs);
            continue;
          }
          if (error && typeof error === 'object') {
            error.attempts = attempt;
          }
          throw error;
        }
      }
      if (lastError && typeof lastError === 'object') {
        lastError.attempts = maxRetries;
      }
      throw lastError || new Error('pull request fetch failed');
    },
  });
}

/**
 * Check if an error is transient and retryable
 * @param {Error} error - The error to check
 * @returns {boolean}
 */
function isTransientError(error) {
  if (!error) return false;
  const status = Number(error?.status || 0);
  const message = String(error?.message || '').toLowerCase();
  // Secondary rate limit (429), server errors (5xx) are always retryable
  if (status === 429 || status >= 500) return true;
  // 403 is only retryable if message indicates rate limit or abuse detection
  if (status === 403 && (message.includes('rate limit') || message.includes('abuse detection'))) return true;
  // Check for rate limit keywords in any error message
  if (message.includes('rate limit') || message.includes('abuse detection') || message.includes('timeout')) return true;
  return false;
}

// Inlined from ../../scripts/keepalive_instruction_segment.js to avoid relative require issues in github-script
function normaliseNewlines(value) {
  return String(value || '').replace(/\r\n/g, '\n');
}

function findInstructionStart(body) {
  const markers = [
    /<!--\s*codex-keepalive-round[^>]*-->/i,
    /<!--\s*keepalive-round[^>]*-->/i,
    /<!--\s*keepalive-attempt[^>]*-->/i,
    /<!--\s*codex-keepalive-marker\s*-->/i,
  ];
  for (const marker of markers) {
    const index = body.search(marker);
    if (index >= 0) {
      return index;
    }
  }
  return 0;
}

const EXCLUSION_PATTERNS = [
  /\n\*\*\s*Head\s*SHA[^:]*:/i,
  /\n\*\*\s*Latest\s+Runs?[^:]*:/i,
  /\n\*\*\s*Required\s+Status\s+Checks[^:]*:/i,
  /\n\*\*\s*Workflow\s*\/\s*Job[^:]*:/i,
  /\n\*\*\s*Workflow\s*\/\s*Job\s*Result\s*Logs[^:]*:/i,
  /\n\*\*\s*Coverage[^:]*:/i,
  /\n\|\s*Workflow\s*\/\s*Job\s*\|/i,
];

function trimAfterExclusions(text) {
  let end = text.length;
  for (const pattern of EXCLUSION_PATTERNS) {
    const index = text.search(pattern);
    if (index >= 0 && index < end) {
      end = index;
    }
  }
  if (end < text.length) {
    return text.slice(0, end);
  }
  return text;
}

function extractInstructionSegment(body) {
  if (!body) {
    return '';
  }
  const normalised = normaliseNewlines(body).trimStart();
  if (!normalised) {
    return '';
  }
  const startIndex = findInstructionStart(normalised);
  const sliced = normalised.slice(startIndex);
  if (!sliced.trim()) {
    return '';
  }
  return trimAfterExclusions(sliced).trimEnd();
}

function computeInstructionByteLength(text) {
  return Buffer.byteLength(String(text || ''), 'utf8');
}

const AUTOMATION_LOGINS = new Set(['chatgpt-codex-connector', 'stranske-automation-bot']);
const INSTRUCTION_REACTION = 'hooray';
// Valid GitHub reactions: +1, -1, laugh, confused, heart, hooray, rocket, eyes
const LOCK_REACTION = 'rocket';

function normaliseLogin(login) {
  return String(login || '')
    .trim()
    .toLowerCase()
    .replace(/\[bot\]$/i, '');
}

function parseAllowedLogins(env) {
  const raw = String(env.ALLOWED_LOGINS || '')
    .split(',')
    .map((value) => normaliseLogin(value))
    .filter(Boolean);
  return new Set(raw);
}

function extractIssueNumberFromPull(pull) {
  if (!pull) {
    return null;
  }

  const candidates = [];

  const bodyText = pull?.body || '';
  const metaMatch = bodyText.match(/<!--\s*meta:issue:([0-9]+)\s*-->/i);
  if (metaMatch) {
    candidates.push(metaMatch[1]);
  }

  const branch = pull?.head?.ref || '';
  // Match issue-XX, issue-#XX, or -issue-#XX patterns (handles Codex verbose branch names)
  const branchMatch = branch.match(/issue-#?([0-9]+)/i) || branch.match(/-issue-#([0-9]+)(?:$|[^0-9])/i);
  if (branchMatch) {
    candidates.push(branchMatch[1]);
  }

  const title = pull?.title || '';
  const titleMatch = title.match(/#([0-9]+)/);
  if (titleMatch) {
    candidates.push(titleMatch[1]);
  }

  for (const match of bodyText.matchAll(/#([0-9]+)/g)) {
    if (match[1]) {
      candidates.push(match[1]);
    }
  }

  for (const value of candidates) {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }

  return null;
}

async function detectKeepalive({ core, github, context, env = process.env }) {
  const allowedLogins = parseAllowedLogins(env);
  const keepaliveMarker = env.KEEPALIVE_MARKER || '';
  const toBool = (value) => String(value || '').trim().toLowerCase() === 'true';
  const allowReplay = toBool(env.ALLOW_REPLAY);
  const hasValue = (value) => typeof value === 'string' && value.trim() !== '';
  const gateOk = hasValue(env.GATE_OK) ? toBool(env.GATE_OK) : true;
  const gateReasonRaw = String(env.GATE_REASON || '').trim();
  const gatePending = hasValue(env.GATE_PENDING) ? toBool(env.GATE_PENDING) : false;

  let eventName = String(context?.eventName || context?.event_name || '').toLowerCase();
  if (!eventName && context?.payload?.comment) {
    eventName = 'issue_comment';
  }
  let actionName = String(context?.payload?.action || '').toLowerCase();
  if (!actionName && eventName === 'issue_comment') {
    actionName = 'created';
  }

  const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  const findFirstMatch = (source, patterns) => {
    for (const pattern of patterns) {
      const match = source.match(pattern);
      if (match) {
        return match;
      }
    }
    return null;
  };

  const canonicalMarkerPatterns = [];
  if (keepaliveMarker) {
    canonicalMarkerPatterns.push(new RegExp(escapeRegExp(keepaliveMarker), 'i'));
  }
  canonicalMarkerPatterns.push(/<!--\s*codex-keepalive-marker\s*-->/i);
  canonicalMarkerPatterns.push(/<!--\s*keepalive-marker\s*-->/i);

  const canonicalRoundPatterns = [
    /<!--\s*codex-keepalive-round\s*:?#?\s*(\d+)\s*-->/i,
    /<!--\s*keepalive-round\s*:?#?\s*(\d+)\s*-->/i,
  ];

  const canonicalTracePatterns = [
    /<!--\s*codex-keepalive-trace\s*:?#?\s*([^>]+?)\s*-->/i,
    /<!--\s*keepalive-trace\s*:?#?\s*([^>]+?)\s*-->/i,
  ];

  const outputs = {
    dispatch: 'false',
    reason: 'not-keepalive',
    issue: '',
    round: '',
    branch: '',
    base: '',
    trace: '',
    pr: '',
    author: '',
    comment_id: '',
    comment_url: '',
    processed_reaction: 'false',
    deduped: 'false',
    instruction_body: '',
    instruction_bytes: '0',
    agent_alias: '',
    head_sha: '',
  };

  const setBasicOutputs = () => {
    core.setOutput('dispatch', outputs.dispatch);
    core.setOutput('reason', outputs.reason);
  };

  const setAllOutputs = () => {
    setBasicOutputs();
    core.setOutput('issue', outputs.issue);
    core.setOutput('round', outputs.round);
    core.setOutput('branch', outputs.branch);
    core.setOutput('base', outputs.base);
    core.setOutput('trace', outputs.trace);
    core.setOutput('pr', outputs.pr);
    core.setOutput('author', outputs.author);
    core.setOutput('comment_id', outputs.comment_id);
    core.setOutput('comment_url', outputs.comment_url);
    core.setOutput('processed_reaction', outputs.processed_reaction);
    core.setOutput('deduped', outputs.deduped);
    core.setOutput('instruction_body', outputs.instruction_body || '');
    core.setOutput('instruction_bytes', outputs.instruction_bytes || '0');
    core.setOutput('agent_alias', outputs.agent_alias || '');
    core.setOutput('head_sha', outputs.head_sha || '');
  };

  const { comment, issue } = context.payload || {};
  // Resolve repository coordinates with robust fallbacks to avoid 404s in workflow_run
  const repoEnv = String(env.GITHUB_REPOSITORY || '').split('/');
  let owner = context?.repo?.owner || repoEnv[0] || '';
  let repo = context?.repo?.repo || repoEnv[1] || '';
  if ((!owner || !repo) && comment?.html_url) {
    const match = comment.html_url.match(/github\.com\/([^/]+)\/([^/]+)\//);
    if (match) {
      owner = owner || match[1];
      repo = repo || match[2];
    }
  }
  if (!owner || !repo) {
    outputs.reason = 'missing-repo';
    core.info('Keepalive dispatch skipped: unable to resolve repository owner/name for PR lookup.');
    // Early exit before finalise is defined - just return false
    return false;
  }
  const body = comment?.body || '';
  const authorRaw = comment?.user?.login || '';
  const author = normaliseLogin(authorRaw);
  const contextIssueNumber = issue?.number ? Number.parseInt(issue.number, 10) : NaN;
  const isAuthorAllowed = allowedLogins.has(author);

  let instructionSeen = false;
  let traceMatch;

  const normaliseBody = (value) => String(value || '').replace(/\r\n/g, '\n').trim();

  const isLikelyInstruction = (value) => {
    if (!value) {
      return false;
    }
    const normalised = normaliseBody(value);
    if (!normalised || !normalised.toLowerCase().startsWith('@codex')) {
      return false;
    }
    return normalised.toLowerCase().includes(DEFAULT_INSTRUCTION_SIGNATURE);
  };

  const resolveSummarySource = () => {
    if (author === 'stranske') {
      return 'stranske';
    }
    if (AUTOMATION_LOGINS.has(author)) {
      return 'bot';
    }
    if (author) {
      return author;
    }
    if (authorRaw) {
      return String(authorRaw);
    }
    return 'unknown';
  };

  const finalise = (seenOverride) => {
    const seenFlag = (typeof seenOverride === 'boolean' ? seenOverride : instructionSeen) ? 'true' : 'false';
    setAllOutputs();
    const commentId = outputs.comment_id || (comment?.id ? String(comment.id) : '') || 'unknown';
    const traceValueRaw = outputs.trace || (traceMatch && traceMatch[1] ? traceMatch[1].replace(/--+$/u, '').trim() : '');
    const traceValue = traceValueRaw || 'n/a';
    const dedupedFlag = outputs.deduped === 'true' ? 'true' : 'false';
    
    // Determine path for DISPATCH summary per Observability_Contract.md Section 6
    // path=comment for issue_comment.created (human activation)
    // path=gate for workflow_run (Gate replay activation)
    const dispatchPath = eventName === 'workflow_run' ? 'gate' : 'comment';
    
    // Emit DISPATCH summary line per Observability_Contract.md Section 6
    const dispatchOk = outputs.dispatch === 'true';
    // prValue is already formatted with # prefix
    const prValue = outputs.pr || (issue?.number ? `#${issue.number}` : '#?');
    const headSha = outputs.head_sha || (context?.payload?.pull_request?.head?.sha || '').slice(0, 7) || '-';
    const capValue = outputs.cap || 'n/a';
    const activeValue = outputs.active || 'n/a';
    const dispatchSummary = `DISPATCH: ok=${dispatchOk} path=${dispatchPath} reason=${outputs.reason || 'unknown'} pr=${prValue} activation=${commentId} agent=${outputs.agent_alias || 'codex'} head=${headSha} cap=${capValue} active=${activeValue} trace=${traceValue}`;
    core.info(dispatchSummary);
    
    // Also log the INSTRUCTION line for backwards compatibility
    core.info(
      `INSTRUCTION: comment_id=${commentId} trace=${traceValue} source=${resolveSummarySource()} seen=${seenFlag} deduped=${dedupedFlag}`
    );
    return outputs;
  };

  outputs.author = authorRaw;
  outputs.comment_id = comment?.id ? String(comment.id) : '';
  outputs.comment_url = comment?.html_url || '';

  if (eventName === 'issue_comment' && actionName !== 'created') {
    outputs.reason = 'ignored-comment-action';
    core.info(`Keepalive dispatch skipped: unsupported issue_comment action "${actionName || 'unknown'}".`);
    return finalise(false);
  }

  if (eventName !== 'issue_comment' && !allowReplay) {
    outputs.reason = 'unsupported-event';
    core.info(`Keepalive dispatch skipped: event ${eventName || 'unknown'} not eligible for keepalive detection.`);
    return finalise(false);
  }

  const roundMatch = findFirstMatch(body, canonicalRoundPatterns);

  traceMatch = findFirstMatch(body, canonicalTracePatterns);

  const hasKeepaliveMarker = Boolean(findFirstMatch(body, canonicalMarkerPatterns));

  const isAutomationStatusComment = () => {
    const trimmedBody = normaliseBody(body);
    if (!trimmedBody) {
      return false;
    }
    if (trimmedBody.includes('<!-- autofix-loop:')) {
      return true;
    }
    if (trimmedBody.toLowerCase().startsWith('autofix attempt')) {
      return true;
    }
    if (AUTOMATION_LOGINS.has(author) && !isLikelyInstruction(trimmedBody)) {
      return true;
    }
    return false;
  };

  const automationStatusComment = isAutomationStatusComment();

  if (automationStatusComment && !hasKeepaliveMarker) {
    outputs.reason = 'automation-comment';
    core.info('Keepalive dispatch skipped: automation status comment without keepalive markers.');
    return finalise(false);
  }

  if (!gateOk && isAuthorAllowed) {
    const gateDetail = gateReasonRaw || (gatePending ? 'gate-pending' : '');
    const reason = gateDetail ? `gate-blocked:${gateDetail}` : 'gate-blocked';
    outputs.reason = reason;
    outputs.dispatch = 'false';
    if (Number.isFinite(contextIssueNumber) && contextIssueNumber > 0) {
      outputs.pr = String(contextIssueNumber);
    }
    if (roundMatch) {
      const gateRound = Number.parseInt(roundMatch[1], 10);
      if (Number.isFinite(gateRound) && gateRound > 0) {
        outputs.round = String(gateRound);
      }
    }
    core.info(`Keepalive dispatch deferred: gate reported ${gateDetail || 'a blocking condition'}.`);
    return finalise(false);
  }

  // INITIAL ACTIVATION HANDLING:
  // If no round marker but comment is from an allowed author and starts with @codex,
  // treat it as initial activation (round 1). This handles the case where a human posts
  // "@codex <instructions>" without keepalive markers - we bootstrap the first round.
  // IMPORTANT: Only @codex triggers activation (not any @mention like @maintainer).
  // Do NOT treat comments that contain the keepalive instruction signature as initial
  // activation - those are manual re-posts of existing instructions and should be rejected.
  const normalisedBody = normaliseBody(body).toLowerCase();
  const startsWithCodexMention = normalisedBody.startsWith('@codex') &&
    (normalisedBody.length === 6 || /^@codex[\s,;:!?]/.test(normalisedBody));
  const isInitialActivation = !roundMatch && isAuthorAllowed && body &&
    startsWithCodexMention && !isLikelyInstruction(body);

  if (!roundMatch && !isInitialActivation) {
    outputs.reason = 'missing-round';
    core.info('Keepalive dispatch skipped: comment missing keepalive round marker and not initial activation.');
    return finalise(false);
  }

  // For non-initial activation (keepalive round > 1), require authorized author
  // (initial activation already checks author in isInitialActivation)
  if (!isInitialActivation && !isAuthorAllowed) {
    outputs.reason = 'unauthorised-author';
    core.info(`Keepalive dispatch skipped: author ${author || '(unknown)'} not in allow list.`);
    return finalise(false);
  }

  // For initial activation, we don't require keepalive marker or trace
  // (those are only in subsequent keepalive instruction comments posted by the orchestrator)
  if (!isInitialActivation && !hasKeepaliveMarker) {
    outputs.reason = 'missing-sentinel';
    core.info('Keepalive dispatch skipped: comment missing codex keepalive marker.');
    return finalise(false);
  }

  // Determine round: from marker if present, otherwise 1 for initial activation
  let round;
  if (roundMatch) {
    round = Number.parseInt(roundMatch[1], 10);
    if (!Number.isFinite(round) || round <= 0) {
      outputs.reason = 'invalid-round';
      core.info('Keepalive dispatch skipped: invalid round marker.');
      return finalise(false);
    }
  } else if (isInitialActivation) {
    round = 1;
    core.info('Initial human activation detected - bootstrapping round 1.');
  } else {
    outputs.reason = 'missing-round';
    core.info('Keepalive dispatch skipped: unable to determine round.');
    return finalise(false);
  }

  const commentId = comment?.id;
  if (!commentId) {
    outputs.reason = 'missing-comment-id';
    core.warning('Keepalive dispatch skipped: unable to determine comment id for dedupe.');
    return finalise(false);
  }

  const prNumber = issue?.number;

  outputs.pr = prNumber ? String(prNumber) : '';
  outputs.round = String(round);
  
  // For initial activation, generate a new trace; otherwise extract from comment
  let trace = traceMatch ? traceMatch[1].replace(/--+$/u, '').trim() : '';
  if (!trace && isInitialActivation) {
    trace = makeTrace();
    core.info(`Generated new trace for initial activation: ${trace}`);
  }
  if (!trace) {
    outputs.reason = 'missing-trace';
    core.info('Keepalive dispatch skipped: comment missing keepalive trace marker.');
    return finalise(false);
  }
  outputs.trace = trace;

  instructionSeen = true;

  let pull;
  const maxRetries = 3;
  try {
    pull = await fetchPullRequestCached({ github, owner, repo, prNumber, core, maxRetries });
    if (!pull) {
      throw new Error('pull request data unavailable');
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const attempts = error?.attempts || maxRetries;
    outputs.reason = 'pull-fetch-failed';
    core.warning(`Keepalive dispatch skipped: unable to load PR #${prNumber} after ${attempts} attempts (${message}).`);
    return finalise();
  }

  outputs.branch = pull?.head?.ref || '';
  outputs.base = pull?.base?.ref || '';
  outputs.head_sha = (pull?.head?.sha || '').slice(0, 7);
  outputs.agent_alias = 'codex'; // Default agent alias

  const instructionBody = extractInstructionSegment(body);
  if (!instructionBody) {
    outputs.reason = 'instruction-empty';
    outputs.dispatch = 'false';
    core.setFailed('instruction-empty');
    core.info('Keepalive dispatch blocked: instruction segment missing or empty.');
    return finalise(true);
  }
  outputs.instruction_body = instructionBody;
  outputs.instruction_bytes = String(computeInstructionByteLength(instructionBody));

  const headRepo = pull?.head?.repo;
  const baseRepo = pull?.base?.repo;
  if (
    headRepo &&
    baseRepo &&
    (headRepo.fork || (headRepo.owner?.login && baseRepo.owner?.login && headRepo.owner.login !== baseRepo.owner.login))
  ) {
    outputs.reason = 'fork-pr';
    core.info('Keepalive dispatch skipped: pull request originates from a fork.');
    return finalise();
  }

  const issueNumber = extractIssueNumberFromPull(pull);
  if (issueNumber) {
    outputs.issue = String(issueNumber);
  }

  let reactions = [];
  try {
    reactions = await github.paginate(github.rest.reactions.listForIssueComment, {
      owner,
      repo,
      comment_id: commentId,
      per_page: 100,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    core.warning(`Failed to read keepalive reactions for comment ${commentId}: ${message}`);
    reactions = [];
  }

  const hasInstructionReaction = reactions.some(
    (reaction) => (reaction?.content || '').toLowerCase() === INSTRUCTION_REACTION
  );

  let processedReaction = hasInstructionReaction;
  if (!processedReaction) {
    try {
      const response = await github.rest.reactions.createForIssueComment({
        owner,
        repo,
        comment_id: commentId,
        content: INSTRUCTION_REACTION,
      });
      const status = Number(response?.status || 0);
      const content = String(response?.data?.content || '').toLowerCase();
      if (status === 200 || status === 201 || content === INSTRUCTION_REACTION) {
        processedReaction = true;
      }
    } catch (error) {
      if (error && error.status === 409) {
        processedReaction = true;
      } else {
        const message = error instanceof Error ? error.message : String(error);
        outputs.reason = 'instruction-reaction-failed';
        core.warning(`Failed to add ${INSTRUCTION_REACTION} reaction for keepalive comment ${commentId}: ${message}`);
        return finalise();
      }
    }
  }

  if (!processedReaction) {
    outputs.reason = 'missing-instruction-reaction';
    core.info('Keepalive dispatch skipped: unable to confirm instruction reaction.');
    return finalise();
  }

  outputs.processed_reaction = 'true';

  const hasLockReaction = reactions.some(
    (reaction) => (reaction?.content || '').toLowerCase() === LOCK_REACTION
  );

  if (hasLockReaction) {
    outputs.reason = 'lock-held';
    outputs.dispatch = 'false';
    outputs.deduped = 'true';
    core.info(`Keepalive dispatch skipped: ${LOCK_REACTION} reaction already present on comment ${commentId}.`);
    return finalise(true);
  }

  try {
    const response = await github.rest.reactions.createForIssueComment({
      owner,
      repo,
      comment_id: commentId,
      content: LOCK_REACTION,
    });
    const status = Number(response?.status || 0);
    const content = String(response?.data?.content || '').toLowerCase();
    if (status === 200 || status === 201 || content === LOCK_REACTION) {
      outputs.processed_reaction = 'true';
    }
  } catch (error) {
    if (error && error.status === 409) {
      outputs.reason = 'lock-held';
      outputs.dispatch = 'false';
      outputs.deduped = 'true';
      core.info(
        `Keepalive dispatch skipped: ${LOCK_REACTION} reaction already present on comment ${commentId} (detected via conflict).`
      );
      return finalise(true);
    }

    const message = error instanceof Error ? error.message : String(error);
    outputs.reason = 'lock-held';
    outputs.dispatch = 'false';
    core.warning(`Failed to add ${LOCK_REACTION} reaction for keepalive comment ${commentId}: ${message}`);
    return finalise();
  }

  if (!issueNumber) {
    outputs.reason = 'missing-issue-reference';
    core.info('Keepalive dispatch skipped: unable to determine linked issue number.');
    return finalise();
  }

  // Add agents:activated label on first human activation per GoalsAndPlumbing.md Section 1
  if (isInitialActivation && prNumber) {
    try {
      await github.rest.issues.addLabels({
        owner,
        repo,
        issue_number: prNumber,
        labels: ['agents:activated'],
      });
      core.info(`Added agents:activated label to PR #${prNumber} on initial human activation.`);
    } catch (error) {
      // Don't fail the dispatch if label addition fails - it's informational
      const message = error instanceof Error ? error.message : String(error);
      core.warning(`Failed to add agents:activated label to PR #${prNumber}: ${message}`);
    }
  }

  outputs.dispatch = 'true';
  outputs.reason = 'keepalive-detected';

  return finalise(true);
}

module.exports = {
  detectKeepalive,
  normaliseLogin,
  parseAllowedLogins,
  extractIssueNumberFromPull,
};
