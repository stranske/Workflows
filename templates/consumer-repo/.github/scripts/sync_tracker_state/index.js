'use strict';

// API guard: callers pass createTokenAwareRetry / github-api-with-retry.js
// `withRetry` wrappers into these helpers; tests use lightweight mock clients.
const DURABLE_TRACKER_LABEL = 'tracker:durable';
const AUTOMATED_LABEL = 'automated';
const DEFAULT_STUCK_WINDOW_SCHEMA = 'sync-tracker-stuck-window/v1';
const STUCK_WINDOW_MARKER_RE = /<!--\s*sync-tracker-stuck-window:v1\s+([\s\S]*?)\s*-->/;
const DURABLE_HEADER_RE = /^>\s*\*\*Durable tracker\*\*[\s\S]*?(?=\n(?!>)|\n*$)/im;

function cleanString(value) {
  return String(value || '').trim();
}

function cleanArray(value) {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}

function unique(values) {
  return [...new Set(cleanArray(values).map(cleanString).filter(Boolean))];
}

function labelNames(issue = {}) {
  return cleanArray(issue.labels).map((label) =>
    typeof label === 'string' ? label : cleanString(label?.name)
  );
}

function normaliseRepo(repoFullName, fallbackOwner = '') {
  const value = cleanString(repoFullName);
  if (!value) {
    return null;
  }
  const parts = value.split('/').map(cleanString).filter(Boolean);
  if (parts.length === 2) {
    return { owner: parts[0], repo: parts[1], fullName: `${parts[0]}/${parts[1]}` };
  }
  if (parts.length === 1 && fallbackOwner) {
    return { owner: fallbackOwner, repo: parts[0], fullName: `${fallbackOwner}/${parts[0]}` };
  }
  return null;
}

function patternMatches(value, pattern) {
  const text = cleanString(value);
  if (!pattern) {
    return true;
  }
  if (pattern instanceof RegExp) {
    pattern.lastIndex = 0;
    return pattern.test(text);
  }
  const patternText = cleanString(pattern);
  if (!patternText) {
    return true;
  }
  if (patternText.startsWith('/') && patternText.lastIndexOf('/') > 0) {
    const lastSlash = patternText.lastIndexOf('/');
    const source = patternText.slice(1, lastSlash);
    const flags = patternText.slice(lastSlash + 1);
    try {
      return new RegExp(source, flags).test(text);
    } catch {
      return text.includes(patternText);
    }
  }
  return text.includes(patternText);
}

async function callWithRetry(
  fn,
  label,
  { github = null, withRetry = null, core = console, allowNonIdempotentRetries = false } = {},
) {
  if (typeof withRetry === 'function') {
    return withRetry(
      (client) => fn(client || github),
      { github, maxRetries: 3, allowNonIdempotentRetries },
    );
  }
  try {
    return await fn(github);
  } catch (error) {
    if (core && typeof core.warning === 'function') {
      core.warning(`${label} failed: ${error.status || error.message}`);
    }
    throw error;
  }
}

async function listAllPages({
  github,
  methodForClient,
  params,
  label,
  core = console,
  withRetry = null,
  allowNonIdempotentRetries = true,
}) {
  const results = [];
  const perPage = params.per_page || 100;
  for (let page = 1; ; page += 1) {
    const response = await callWithRetry(
      (client = github) => methodForClient(client)({ ...params, page }),
      `${label} page ${page}`,
      { github, core, withRetry, allowNonIdempotentRetries },
    );
    const data = cleanArray(response?.data);
    results.push(...data);
    if (data.length < perPage) {
      return results;
    }
  }
}

async function paginateIssues({ github, owner, repo, labels = '', core, withRetry }) {
  const params = { owner, repo, state: 'open', per_page: 100 };
  if (labels) {
    params.labels = labels;
  }
  if (typeof github.paginate === 'function') {
    return cleanArray(await callWithRetry(
      (client = github) => client.paginate(client.rest.issues.listForRepo, params),
      `${owner}/${repo} open issues`,
      { github, core, withRetry, allowNonIdempotentRetries: true },
    ));
  }
  return listAllPages({
    github,
    methodForClient: (client = github) => client.rest.issues.listForRepo,
    params,
    label: `${owner}/${repo} open issues`,
    core,
    withRetry,
  });
}

async function getIssue({ github, owner, repo, issueNumber, core, withRetry }) {
  const response = await callWithRetry(
    (client = github) => client.rest.issues.get({ owner, repo, issue_number: issueNumber }),
    `${owner}/${repo}#${issueNumber}`,
    { github, core, withRetry, allowNonIdempotentRetries: true },
  );
  return response?.data || null;
}

function issueHasMarker(issue = {}, markerPattern = null) {
  if (!markerPattern) {
    return false;
  }
  return patternMatches(issue.body || '', markerPattern);
}

function issueMatchesTracker(issue = {}, { label, titlePattern, markerPattern } = {}) {
  if (issue.pull_request) {
    return false;
  }
  const names = labelNames(issue);
  const requiredLabels = unique([label]).filter(Boolean);
  const hasRequiredLabel = requiredLabels.length === 0 ||
    requiredLabels.some((name) => names.includes(name));
  const hasDurableLabel = names.includes(DURABLE_TRACKER_LABEL);
  const hasTitle = patternMatches(issue.title || '', titlePattern);
  const hasMarker = issueHasMarker(issue, markerPattern);
  if (titlePattern && hasTitle) {
    return true;
  }
  if (markerPattern && hasTitle && !cleanString(issue.body)) {
    return true;
  }
  return (hasDurableLabel || hasRequiredLabel || hasMarker) && (hasTitle || hasMarker);
}

async function ensureLabels({
  github,
  owner,
  repo,
  issueNumber,
  labels = [],
  core,
  withRetry,
}) {
  const names = unique(labels);
  if (!names.length) {
    return;
  }
  await callWithRetry(
    (client = github) =>
      client.rest.issues.addLabels({ owner, repo, issue_number: issueNumber, labels: names }),
    `${owner}/${repo}#${issueNumber} add labels`,
    { github, core, withRetry, allowNonIdempotentRetries: true },
  );
}

async function findTracker({ github, owner, repo, label, titlePattern, markerPattern, core, withRetry }) {
  const labeledIssueGroups = await Promise.all(
    unique([DURABLE_TRACKER_LABEL, label]).map((labelName) =>
      paginateIssues({
        github,
        owner,
        repo,
        labels: labelName,
        core,
        withRetry,
      })
    )
  );
  const openIssues = titlePattern || markerPattern
    ? await paginateIssues({ github, owner, repo, core, withRetry })
    : [];
  const byNumber = new Map();
  for (const issueGroup of [...labeledIssueGroups, openIssues]) {
    for (const issue of issueGroup) {
      byNumber.set(issue.number, issue);
    }
  }
  for (const issue of byNumber.values()) {
    if (!issueMatchesTracker(issue, { label, titlePattern, markerPattern })) {
      continue;
    }
    const fullIssue = await getIssue({ github, owner, repo, issueNumber: issue.number, core, withRetry });
    if (issueMatchesTracker(fullIssue, { label, titlePattern, markerPattern })) {
      return fullIssue;
    }
  }
  return null;
}

async function findOrCreateTracker({
  github,
  context = null,
  owner = context?.repo?.owner,
  repo = context?.repo?.repo,
  label = '',
  titlePattern = '',
  markerPattern = null,
  title = '',
  body = '',
  markerComment = '',
  labels = [],
  createIfMissing = true,
  core = console,
  withRetry = null,
} = {}) {
  if (!github || !owner || !repo) {
    throw new Error('findOrCreateTracker requires github, owner, and repo');
  }
  const tracker = await findTracker({ github, owner, repo, label, titlePattern, markerPattern, core, withRetry });
  if (tracker) {
    if (createIfMissing) {
      await ensureLabels({
        github,
        owner,
        repo,
        issueNumber: tracker.number,
        labels: [DURABLE_TRACKER_LABEL, AUTOMATED_LABEL, label, ...labels],
        core,
        withRetry,
      });
    }
    tracker.sync_tracker_created = false;
    return tracker;
  }

  if (!createIfMissing) {
    return null;
  }

  const issueTitle = cleanString(title) || cleanString(titlePattern);
  if (!issueTitle) {
    throw new Error('findOrCreateTracker requires title when no tracker exists');
  }
  const createBody = markerComment
    ? `${cleanString(body)}\n\n${cleanString(markerComment)}`.trim()
    : cleanString(body);
  const response = await callWithRetry(
    (client = github) => client.rest.issues.create({
      owner,
      repo,
      title: issueTitle,
      body: createBody,
      labels: unique([DURABLE_TRACKER_LABEL, AUTOMATED_LABEL, label, ...labels]),
    }),
    `${owner}/${repo} create durable tracker`,
    { github, core, withRetry },
  );
  const created = response?.data || null;
  if (created) {
    created.sync_tracker_created = true;
  }
  return created;
}

function extractDurableTrackerHeader(body = '') {
  const match = cleanString(body).match(DURABLE_HEADER_RE);
  return match ? match[0].trim() : '';
}

function bodyHasDurableHeader(body = '') {
  return Boolean(extractDurableTrackerHeader(body));
}

function preserveDurableTrackerHeader(existingBody = '', newBody = '') {
  const nextBody = cleanString(newBody);
  const existingHeader = extractDurableTrackerHeader(existingBody);
  if (!existingHeader || bodyHasDurableHeader(nextBody)) {
    return nextBody;
  }

  const lines = nextBody.split(/\r?\n/);
  const headingIndex = lines.findIndex((line) => /^#{1,6}\s+\S/.test(line));
  if (headingIndex === -1) {
    return `${existingHeader}\n\n${nextBody}`.trim();
  }
  const insertAt = headingIndex + 1;
  const before = lines.slice(0, insertAt);
  const after = lines.slice(insertAt);
  return [...before, '', existingHeader, '', ...after].join('\n').trim();
}

async function updateTrackerBody({
  github,
  context = null,
  owner = context?.repo?.owner,
  repo = context?.repo?.repo,
  tracker,
  newBody,
  title = null,
  core = console,
  withRetry = null,
} = {}) {
  if (!github || !owner || !repo || !tracker?.number) {
    throw new Error('updateTrackerBody requires github, owner, repo, and tracker.number');
  }
  const body = preserveDurableTrackerHeader(tracker.body || '', newBody);
  const params = { owner, repo, issue_number: tracker.number, body };
  if (title) {
    params.title = title;
  }
  const response = await callWithRetry(
    (client = github) => client.rest.issues.update(params),
    `${owner}/${repo}#${tracker.number} update durable tracker`,
    { github, core, withRetry },
  );
  return response?.data || null;
}

async function appendTrackerComment({
  github,
  context = null,
  owner = context?.repo?.owner,
  repo = context?.repo?.repo,
  tracker,
  comment,
  core = console,
  withRetry = null,
} = {}) {
  if (!github || !owner || !repo || !tracker?.number) {
    throw new Error('appendTrackerComment requires github, owner, repo, and tracker.number');
  }
  const response = await callWithRetry(
    (client = github) => client.rest.issues.createComment({
      owner,
      repo,
      issue_number: tracker.number,
      body: cleanString(comment),
    }),
    `${owner}/${repo}#${tracker.number} append tracker comment`,
    { github, core, withRetry },
  );
  return response?.data || null;
}

async function isConsumerOpenPr({
  github,
  consumerRepo,
  branchPattern,
  state = 'open',
  core = console,
  withRetry = null,
  defaultOwner = '',
} = {}) {
  const parsed = normaliseRepo(consumerRepo, defaultOwner);
  if (!github || !parsed) {
    throw new Error('isConsumerOpenPr requires github and consumerRepo');
  }
  const params = { owner: parsed.owner, repo: parsed.repo, state, per_page: 100 };
  const pulls = typeof github.paginate === 'function'
    ? cleanArray(await callWithRetry(
        (client = github) => client.paginate(client.rest.pulls.list, params),
        `${parsed.fullName} open pulls`,
        { github, core, withRetry, allowNonIdempotentRetries: true },
      ))
    : await listAllPages({
        github,
        methodForClient: (client = github) => client.rest.pulls.list,
        params,
        label: `${parsed.fullName} open pulls`,
        core,
        withRetry,
      });
  if (!branchPattern) {
    return false;
  }
  return pulls.some((pull) => {
    const headRef = cleanString(pull?.head?.ref || pull?.headRefName || pull?.head_ref);
    return patternMatches(headRef, branchPattern);
  });
}

function formatStuckWindowMarker(sinceTimestamp, options = {}) {
  const payload = {
    schema: DEFAULT_STUCK_WINDOW_SCHEMA,
    since: cleanString(sinceTimestamp),
    updated_at: cleanString(options.updatedAt) || new Date().toISOString(),
  };
  if (options.reason) {
    payload.reason = cleanString(options.reason);
  }
  return `<!-- sync-tracker-stuck-window:v1 ${JSON.stringify(payload)} -->`;
}

function parseStuckWindow(body = '') {
  const match = cleanString(body).match(STUCK_WINDOW_MARKER_RE);
  if (!match) {
    return null;
  }
  try {
    const payload = JSON.parse(match[1]);
    return payload && payload.schema === DEFAULT_STUCK_WINDOW_SCHEMA ? payload : null;
  } catch {
    return null;
  }
}

function markStuckWindowBody(body = '', sinceTimestamp, options = {}) {
  const source = cleanString(body);
  const marker = formatStuckWindowMarker(sinceTimestamp, options);
  if (STUCK_WINDOW_MARKER_RE.test(source)) {
    return source.replace(STUCK_WINDOW_MARKER_RE, marker);
  }
  return `${source.trimEnd()}\n\n${marker}`.trim();
}

function clearStuckWindowBody(body = '') {
  return cleanString(body).replace(STUCK_WINDOW_MARKER_RE, '').replace(/\n{3,}/g, '\n\n').trim();
}

async function markStuckWindow({
  github,
  context = null,
  owner = context?.repo?.owner,
  repo = context?.repo?.repo,
  tracker,
  sinceTimestamp,
  core = console,
  withRetry = null,
  ...options
} = {}) {
  return updateTrackerBody({
    github,
    owner,
    repo,
    tracker,
    newBody: markStuckWindowBody(tracker?.body || '', sinceTimestamp, options),
    core,
    withRetry,
  });
}

async function clearStuckWindow({
  github,
  context = null,
  owner = context?.repo?.owner,
  repo = context?.repo?.repo,
  tracker,
  core = console,
  withRetry = null,
} = {}) {
  return updateTrackerBody({
    github,
    owner,
    repo,
    tracker,
    newBody: clearStuckWindowBody(tracker?.body || ''),
    core,
    withRetry,
  });
}

module.exports = {
  AUTOMATED_LABEL,
  DEFAULT_STUCK_WINDOW_SCHEMA,
  DURABLE_TRACKER_LABEL,
  appendTrackerComment,
  append_tracker_comment: appendTrackerComment,
  bodyHasDurableHeader,
  clearStuckWindow,
  clearStuckWindowBody,
  clear_stuck_window: clearStuckWindow,
  extractDurableTrackerHeader,
  findOrCreateTracker,
  find_or_create_tracker: findOrCreateTracker,
  formatStuckWindowMarker,
  isConsumerOpenPr,
  is_consumer_open_pr: isConsumerOpenPr,
  issueMatchesTracker,
  markStuckWindow,
  markStuckWindowBody,
  mark_stuck_window: markStuckWindow,
  parseStuckWindow,
  patternMatches,
  preserveDurableTrackerHeader,
  updateTrackerBody,
  update_tracker_body: updateTrackerBody,
};
