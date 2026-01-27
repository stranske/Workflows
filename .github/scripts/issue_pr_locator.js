const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

const ISSUE_LABEL_PATTERN = /^agents?:/i;

function sanitizeArray(values) {
  return Array.from(new Set((values || []).map((value) => String(value || '').trim()).filter(Boolean)));
}

function issueMentionPatterns(issueNumber) {
  const num = Number(issueNumber);
  if (!Number.isFinite(num) || num <= 0) {
    return [];
  }
  const escaped = String(num).replace(/[-/\\^$*+?.()|\\[\\]{}]/g, (m) => `\\${m}`);
  return [
    new RegExp(`(^|[^0-9])#${escaped}(?![0-9])`, 'i'),
    new RegExp(`issue\\s*#?${escaped}`, 'i'),
  ];
}

function candidateScore(candidate, { issueNumber }) {
  if (!candidate || candidate.state !== 'open') {
    return { score: -1, updated: 0 };
  }

  let score = 0;
  if (candidate.branchMatch) {
    score += 100;
  }
  if (candidate.crossReference) {
    score += 60;
  }
  if (candidate.bodyMentionsIssue) {
    score += 40;
  }
  if (candidate.titleMentionsIssue) {
    score += 25;
  }
  if (candidate.labelMatch) {
    score += 10;
  }
  if (candidate.baseIsDefault) {
    score += 5;
  }
  if (candidate.draft) {
    score -= 5;
  }

  // Prefer newer updates when scores tie
  const updated = candidate.updatedAt ? new Date(candidate.updatedAt).getTime() : 0;
  return { score, updated };
}

function markIssueMentions(candidate, issueNumber) {
  const patterns = issueMentionPatterns(issueNumber);
  const mark = (text) => patterns.some((pattern) => pattern.test(text || ''));
  return {
    ...candidate,
    bodyMentionsIssue: mark(candidate.body || ''),
    titleMentionsIssue: mark(candidate.title || ''),
  };
}

function enrichCandidate(pr, overrides = {}) {
  const labels = (pr.labels || []).map((label) =>
    typeof label === 'string' ? label : label?.name || ''
  );
  const labelMatch = labels.some((label) => ISSUE_LABEL_PATTERN.test(label));
  return {
    number: pr.number,
    headRef: pr.head?.ref || '',
    baseRef: pr.base?.ref || '',
    body: pr.body || '',
    title: pr.title || '',
    draft: Boolean(pr.draft),
    state: pr.state || 'open',
    updatedAt: pr.updated_at || pr.created_at || null,
    labels,
    labelMatch,
    ...overrides,
    pr,
  };
}

function selectBestCandidate(candidates, { issueNumber }) {
  if (!Array.isArray(candidates) || !candidates.length) {
    return null;
  }
  let best = null;
  let bestScore = -Infinity;
  let bestUpdated = 0;
  for (const candidate of candidates) {
    const { score, updated } = candidateScore(candidate, { issueNumber });
    if (score > bestScore || (score === bestScore && updated > bestUpdated)) {
      best = candidate;
      bestScore = score;
      bestUpdated = updated;
    }
  }
  return best;
}

async function collectBranchCandidates({ github, core, owner, repo, branches }) {
  const candidates = [];
  const uniqueBranches = sanitizeArray(branches);
  for (const branch of uniqueBranches) {
    try {
      const { data } = await github.rest.pulls.list({
        owner,
        repo,
        state: 'open',
        head: `${owner}:${branch}`,
        per_page: 20,
      });
      for (const pr of data || []) {
        candidates.push(
          enrichCandidate(pr, {
            source: 'branch',
            branchMatch: true,
          })
        );
      }
    } catch (error) {
      core?.warning?.(`Branch lookup failed for ${branch}: ${error.message}`);
    }
  }
  return candidates;
}

async function collectCrossReferenceCandidates({ github, core, owner, repo, issueNumber, maxEvents = 50 }) {
  const candidates = [];
  const seen = new Set();
  try {
    const iterator = github.paginate.iterator(github.rest.issues.listEvents, {
      owner,
      repo,
      issue_number: issueNumber,
      per_page: 100,
    });
    for await (const page of iterator) {
      for (const event of page.data || []) {
        if (event.event !== 'cross-referenced') {
          continue;
        }
        const sourceIssue = event?.source?.issue;
        if (!sourceIssue?.pull_request) {
          continue;
        }
        const repoName = sourceIssue?.repository?.name;
        const repoOwner = sourceIssue?.repository?.owner?.login;
        if (repoName && repoOwner) {
          const sameRepo = `${repoOwner}/${repoName}`.toLowerCase() === `${owner}/${repo}`.toLowerCase();
          if (!sameRepo) {
            continue;
          }
        }
        const prNumber = sourceIssue.number;
        if (!prNumber || seen.has(prNumber)) {
          continue;
        }
        seen.add(prNumber);
        try {
          const { data } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
          candidates.push(
            enrichCandidate(data, {
              source: 'cross-ref',
              crossReference: true,
            })
          );
        } catch (error) {
          core?.warning?.(`Failed to fetch cross-referenced PR #${prNumber}: ${error.message}`);
        }
        if (seen.size >= maxEvents) {
          break;
        }
      }
      if (seen.size >= maxEvents) {
        break;
      }
    }
  } catch (error) {
    core?.warning?.(`Failed to list issue events: ${error.message}`);
  }
  return candidates;
}

async function collectOpenPrCandidates({ github, core, owner, repo, issueNumber, maxPages = 3 }) {
  const candidates = [];
  try {
    const iterator = github.paginate.iterator(github.rest.pulls.list, {
      owner,
      repo,
      state: 'open',
      per_page: 50,
    });
    let pageCount = 0;
    for await (const page of iterator) {
      pageCount += 1;
      for (const pr of page.data || []) {
        candidates.push(
          enrichCandidate(pr, {
            source: 'open-list',
          })
        );
      }
      if (pageCount >= maxPages) {
        break;
      }
    }
  } catch (error) {
    core?.warning?.(`Failed to list open PRs: ${error.message}`);
  }
  const patterns = issueMentionPatterns(issueNumber);
  return candidates.map((candidate) => {
    const mark = (text) => patterns.some((pattern) => pattern.test(text || ''));
    return {
      ...candidate,
      bodyMentionsIssue: mark(candidate.body),
      titleMentionsIssue: mark(candidate.title),
    };
  });
}

async function findIssuePrCandidate({ github, core, owner, repo, issueNumber, branchCandidates = [], defaultBranch }) {
  const baseBranch = (defaultBranch || '').trim();
  const allCandidates = [];
  const branchMatches = await collectBranchCandidates({ github, core, owner, repo, branches: branchCandidates });
  allCandidates.push(...branchMatches);
  const crossRefs = await collectCrossReferenceCandidates({ github, core, owner, repo, issueNumber });
  allCandidates.push(...crossRefs);
  const openPrs = await collectOpenPrCandidates({ github, core, owner, repo, issueNumber });
  allCandidates.push(...openPrs);

  const deduped = new Map();
  for (const candidate of allCandidates) {
    if (!candidate || !candidate.number) {
      continue;
    }
    const existing = deduped.get(candidate.number);
    const enriched = markIssueMentions(
      {
        ...candidate,
        baseIsDefault: baseBranch && candidate.baseRef === baseBranch,
      },
      issueNumber
    );
    if (!existing) {
      deduped.set(candidate.number, enriched);
      continue;
    }
    const better = selectBestCandidate([existing, enriched], { issueNumber });
    deduped.set(candidate.number, better);
  }

  const best = selectBestCandidate(Array.from(deduped.values()), { issueNumber });
  return best;
}

module.exports = {
  findIssuePrCandidate: async function ({ github: rawGithub, core, owner, repo, issueNumber, branchCandidates = [], defaultBranch }) {
    const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
    return findIssuePrCandidate({ github, core, owner, repo, issueNumber, branchCandidates, defaultBranch });
  },
  issueMentionPatterns,
  candidateScore,
  selectBestCandidate,
};
