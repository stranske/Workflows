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
    if (!['connected', 'cross-referenced'].includes(event?.event)) {
      continue;
    }
    const source = event?.source?.issue || event?.subject?.issue || event?.subject;
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
  return `${counts}\nHealth 40 will reclaim only stale claims without a linked open or merged PR.`;
}

async function readTimeline(github, owner, repo, issueNumber) {
  return github.paginate(github.rest.issues.listEventsForTimeline, {
    owner,
    repo,
    issue_number: issueNumber,
    per_page: 100,
  });
}

async function sweepClaims({ github, owner, repo, now = Date.now() }) {
  const candidates = await github.paginate(github.rest.issues.listForRepo, {
    owner,
    repo,
    state: 'open',
    labels: 'status:in-progress',
    per_page: 100,
  });
  const latched = candidates.filter((issue) => !issue.pull_request);
  const decisions = [];
  for (const issue of latched) {
    const timeline = await readTimeline(github, owner, repo, issue.number);
    const claimTimestamp = latestClaimTimestamp(timeline);
    const linkedPullRequests = blockingPullRequestsFromTimeline(timeline);
    const decision = evaluateClaim({ claimTimestamp, linkedPullRequests, now });
    decisions.push({ issue, claimTimestamp, decision });
  }

  const reclaimable = decisions.filter((entry) => entry.decision.reclaim);
  let reclaimedCount = 0;
  const claimWindowHours = CLAIM_STALE_MS / (60 * 60 * 1000);
  for (const entry of reclaimable) {
    const issueNumber = entry.issue.number;
    const { data: currentIssue } = await github.rest.issues.get({
      owner,
      repo,
      issue_number: issueNumber,
    });
    const labels = (currentIssue.labels || []).map((label) =>
      typeof label === 'string' ? label : label.name
    );
    if (!labels.includes('status:in-progress')) {
      continue;
    }

    let currentTimeline = await readTimeline(github, owner, repo, issueNumber);
    let currentClaimTimestamp = latestClaimTimestamp(currentTimeline);
    let currentDecision = evaluateClaim({
      claimTimestamp: currentClaimTimestamp,
      linkedPullRequests: blockingPullRequestsFromTimeline(currentTimeline),
      now,
    });
    if (!currentDecision.reclaim || currentClaimTimestamp !== entry.claimTimestamp) {
      continue;
    }

    const marker = `<!-- belt-claim-reclaim:${currentClaimTimestamp} -->`;
    const comments = await github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: issueNumber,
      per_page: 100,
    });
    if (!comments.some((comment) => String(comment.body || '').includes(marker))) {
      await github.rest.issues.createComment({
        owner,
        repo,
        issue_number: issueNumber,
        body:
          `${marker}\nHealth 40 intends to reclaim the stale \`status:in-progress\` claim ` +
          `from ${currentClaimTimestamp}: no linked open or merged PR was found after ` +
          `${claimWindowHours} hours.`,
      });
    }

    currentTimeline = await readTimeline(github, owner, repo, issueNumber);
    currentClaimTimestamp = latestClaimTimestamp(currentTimeline);
    currentDecision = evaluateClaim({
      claimTimestamp: currentClaimTimestamp,
      linkedPullRequests: blockingPullRequestsFromTimeline(currentTimeline),
      now,
    });
    if (!currentDecision.reclaim || currentClaimTimestamp !== entry.claimTimestamp) {
      continue;
    }

    await github.rest.issues.removeLabel({
      owner,
      repo,
      issue_number: issueNumber,
      name: 'status:in-progress',
    });
    reclaimedCount += 1;
  }

  return {
    latchedCount: latched.length,
    reclaimableCount: reclaimable.length,
    reclaimedCount,
    summary: buildSweepSummary({
      latchedCount: latched.length,
      reclaimableCount: reclaimable.length,
    }),
  };
}

module.exports = {
  CLAIM_STALE_MS,
  blockingPullRequestsFromTimeline,
  buildSweepSummary,
  evaluateClaim,
  latestClaimTimestamp,
  sweepClaims,
};
