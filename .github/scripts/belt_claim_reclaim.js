'use strict';

const CLAIM_STALE_MS = 24 * 60 * 60 * 1000;

function parseTimestamp(value) {
  const timestamp = Date.parse(String(value || ''));
  return Number.isFinite(timestamp) ? timestamp : null;
}

function latestClaimTimestamp(events = []) {
  let latest = null;
  for (const event of events) {
    if (event?.event !== 'labeled' || event?.label?.name !== 'status:in-progress') {
      continue;
    }
    const timestamp = parseTimestamp(event.created_at);
    if (timestamp !== null && (latest === null || timestamp > latest)) {
      latest = timestamp;
    }
  }
  return latest === null ? null : new Date(latest).toISOString();
}

function blockingPullRequestsFromTimeline(events = []) {
  const blocking = [];
  const seen = new Set();
  for (const event of events) {
    if (event?.event !== 'cross-referenced') {
      continue;
    }
    const source = event?.source?.issue;
    if (!source?.pull_request) {
      continue;
    }
    const state = String(source.state || '').toLowerCase();
    const mergeStateKnown = Object.prototype.hasOwnProperty.call(
      source.pull_request,
      'merged_at'
    );
    const merged = Boolean(source.pull_request.merged_at);
    if (state === 'closed' && mergeStateKnown && !merged) {
      continue;
    }
    const reference = source.html_url || source.pull_request.html_url || source.pull_request.url;
    const key = reference || String(source.number || blocking.length);
    if (!seen.has(key)) {
      seen.add(key);
      blocking.push({
        number: source.number || null,
        state: state || 'unknown',
        merged,
        url: reference || null,
      });
    }
  }
  return blocking;
}

const LINKED_PULL_REQUESTS_QUERY = `
  query BeltClaimLinks($owner: String!, $repo: String!, $number: Int!, $after: String) {
    repository(owner: $owner, name: $repo) {
      issue(number: $number) {
        closedByPullRequestsReferences(
          first: 100
          after: $after
          includeClosedPrs: true
          userLinkedOnly: true
        ) {
          nodes { number url state mergedAt }
          pageInfo { hasNextPage endCursor }
        }
      }
    }
  }
`;

function normalizeLinkedPullRequest(node) {
  if (
    !node ||
    !Number.isInteger(node.number) ||
    typeof node.url !== 'string' ||
    !node.url ||
    !['OPEN', 'CLOSED', 'MERGED'].includes(node.state) ||
    !Object.prototype.hasOwnProperty.call(node, 'mergedAt')
  ) {
    throw new TypeError('malformed linked pull request response');
  }
  if (node.state === 'CLOSED' && node.mergedAt === null) {
    return null;
  }
  return {
    number: node.number,
    state: node.state.toLowerCase(),
    merged: node.state === 'MERGED' || node.mergedAt !== null,
    url: node.url,
  };
}

async function readLinkedPullRequests(withRetry, owner, repo, issueNumber) {
  const blocking = [];
  let after = null;
  const seenCursors = new Set();
  do {
    const response = await withRetry((client) =>
      client.graphql(LINKED_PULL_REQUESTS_QUERY, {
        owner,
        repo,
        number: issueNumber,
        after,
      })
    );
    const connection = response?.repository?.issue?.closedByPullRequestsReferences;
    if (
      !connection ||
      !Array.isArray(connection.nodes) ||
      typeof connection.pageInfo?.hasNextPage !== 'boolean'
    ) {
      throw new TypeError('incomplete linked pull request response');
    }
    for (const node of connection.nodes) {
      const normalized = normalizeLinkedPullRequest(node);
      if (normalized) {
        blocking.push(normalized);
      }
    }
    if (!connection.pageInfo.hasNextPage) {
      break;
    }
    const nextCursor = connection.pageInfo.endCursor;
    if (typeof nextCursor !== 'string' || !nextCursor || seenCursors.has(nextCursor)) {
      throw new TypeError('invalid linked pull request pagination cursor');
    }
    seenCursors.add(nextCursor);
    after = nextCursor;
  } while (true);
  return blocking;
}

function mergeBlockingPullRequests(...groups) {
  const merged = [];
  const seen = new Set();
  for (const group of groups) {
    for (const pullRequest of group) {
      const key = pullRequest.url;
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(pullRequest);
      }
    }
  }
  return merged;
}

function evaluateClaim({ claimTimestamp, linkedPullRequests = [], now = Date.now() } = {}) {
  const claimTime = parseTimestamp(claimTimestamp);
  const nowTime = typeof now === 'number' ? now : parseTimestamp(now);
  if (claimTime === null) {
    return {
      reclaim: false,
      stale: false,
      ageMs: null,
      reason: 'missing-claim-timestamp',
    };
  }
  if (nowTime === null) {
    throw new TypeError('now must be a timestamp or date string');
  }
  const ageMs = Math.max(0, nowTime - claimTime);
  const stale = ageMs > CLAIM_STALE_MS;
  if (linkedPullRequests.length > 0) {
    return { reclaim: false, stale, ageMs, reason: 'linked-pr-present' };
  }
  if (!stale) {
    return { reclaim: false, stale, ageMs, reason: 'inside-claim-window' };
  }
  return { reclaim: true, stale, ageMs, reason: 'stale-without-pr' };
}

function buildSweepSummary({ latchedCount = 0, reclaimableCount = 0 } = {}) {
  const counts = `Belt claim counts: in-progress=${latchedCount} reclaimable=${reclaimableCount}.`;
  if (latchedCount === 0) {
    return `Belt claim sweep: none latched.\n${counts}`;
  }
  return `${counts}\nThe belt claim sweep will reclaim only stale claims without a linked open or merged PR.`;
}

async function readTimeline(withRetry, owner, repo, issueNumber) {
  return withRetry((client) =>
    client.paginate(client.rest.issues.listEventsForTimeline, {
      owner,
      repo,
      issue_number: issueNumber,
      per_page: 100,
    })
  );
}

async function readClaimDecision(withRetry, owner, repo, issueNumber, now) {
  const timeline = await readTimeline(withRetry, owner, repo, issueNumber);
  const claimTimestamp = latestClaimTimestamp(timeline);
  const linkedPullRequests = mergeBlockingPullRequests(
    blockingPullRequestsFromTimeline(timeline),
    await readLinkedPullRequests(withRetry, owner, repo, issueNumber)
  );
  return {
    claimTimestamp,
    decision: evaluateClaim({ claimTimestamp, linkedPullRequests, now }),
  };
}

function errorStatus(error) {
  return error?.status ?? error?.response?.status ?? null;
}

function recordFailure(failures, issueNumber, phase, error) {
  failures.push({
    issueNumber,
    phase,
    status: errorStatus(error),
    message: String(error?.message || error || 'unknown error'),
  });
}

async function sweepClaims({ withRetry, owner, repo, now = Date.now() }) {
  if (typeof withRetry !== 'function') {
    throw new TypeError('withRetry from createTokenAwareRetry is required');
  }
  const candidates = await withRetry((client) =>
    client.paginate(client.rest.issues.listForRepo, {
      owner,
      repo,
      state: 'open',
      labels: 'status:in-progress',
      per_page: 100,
    })
  );
  const latched = candidates.filter((issue) => !issue.pull_request);
  const decisions = [];
  const failures = [];
  for (const issue of latched) {
    try {
      const claim = await readClaimDecision(withRetry, owner, repo, issue.number, now);
      decisions.push({ issue, ...claim });
    } catch (error) {
      recordFailure(failures, issue.number, 'assessment', error);
    }
  }

  const reclaimable = decisions.filter((entry) => entry.decision.reclaim);
  let reclaimedCount = 0;
  let alreadyReleasedCount = 0;
  const claimWindowHours = CLAIM_STALE_MS / (60 * 60 * 1000);
  for (const entry of reclaimable) {
    const issueNumber = entry.issue.number;
    let currentIssue;
    try {
      ({ data: currentIssue } = await withRetry((client) =>
        client.rest.issues.get({ owner, repo, issue_number: issueNumber })
      ));
    } catch (error) {
      recordFailure(failures, issueNumber, 'revalidation', error);
      continue;
    }
    const labels = (currentIssue.labels || []).map((label) =>
      typeof label === 'string' ? label : label.name
    );
    if (!labels.includes('status:in-progress')) {
      continue;
    }

    let currentClaimTimestamp;
    let currentDecision;
    try {
      ({ claimTimestamp: currentClaimTimestamp, decision: currentDecision } =
        await readClaimDecision(withRetry, owner, repo, issueNumber, now));
    } catch (error) {
      recordFailure(failures, issueNumber, 'revalidation', error);
      continue;
    }
    if (!currentDecision.reclaim || currentClaimTimestamp !== entry.claimTimestamp) {
      continue;
    }

    const marker = `<!-- belt-claim-reclaim:${currentClaimTimestamp} -->`;
    try {
      const comments = await withRetry((client) =>
        client.paginate(client.rest.issues.listComments, {
          owner,
          repo,
          issue_number: issueNumber,
          per_page: 100,
        })
      );
      if (!comments.some((comment) => String(comment.body || '').includes(marker))) {
        await withRetry((client) =>
          client.rest.issues.createComment({
            owner,
            repo,
            issue_number: issueNumber,
            body:
              `${marker}\nThe belt claim sweep intends to reclaim the stale ` +
              `\`status:in-progress\` claim from ${currentClaimTimestamp}: no linked open ` +
              `or merged PR was found after ${claimWindowHours} hours.`,
          })
        );
      }
    } catch (error) {
      recordFailure(failures, issueNumber, 'comments', error);
      continue;
    }

    try {
      ({ claimTimestamp: currentClaimTimestamp, decision: currentDecision } =
        await readClaimDecision(withRetry, owner, repo, issueNumber, now));
    } catch (error) {
      recordFailure(failures, issueNumber, 'final-check', error);
      continue;
    }
    if (!currentDecision.reclaim || currentClaimTimestamp !== entry.claimTimestamp) {
      continue;
    }

    try {
      await withRetry((client) =>
        client.rest.issues.removeLabel({
          owner,
          repo,
          issue_number: issueNumber,
          name: 'status:in-progress',
        })
      );
      reclaimedCount += 1;
    } catch (error) {
      if (errorStatus(error) === 404) {
        alreadyReleasedCount += 1;
      } else {
        recordFailure(failures, issueNumber, 'remove-label', error);
      }
    }
  }

  const baseSummary = buildSweepSummary({
    latchedCount: latched.length,
    reclaimableCount: reclaimable.length,
  });
  const failedIssues = [...new Set(failures.map((failure) => failure.issueNumber))];

  return {
    latchedCount: latched.length,
    reclaimableCount: reclaimable.length,
    reclaimedCount,
    alreadyReleasedCount,
    failures,
    summary:
      `${baseSummary}\nBelt claim outcomes: reclaimed=${reclaimedCount} ` +
      `already-released=${alreadyReleasedCount} failures=${failures.length}` +
      (failedIssues.length ? ` issues=${failedIssues.join(',')}.` : '.'),
  };
}

module.exports = {
  CLAIM_STALE_MS,
  blockingPullRequestsFromTimeline,
  buildSweepSummary,
  evaluateClaim,
  latestClaimTimestamp,
  readLinkedPullRequests,
  sweepClaims,
};
