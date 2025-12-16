'use strict';

const {
  extractInstructionSegment,
  computeInstructionByteLength,
} = require('./keepalive_instruction_segment.js');
const {
  extractScopeTasksAcceptanceSections: extractScopeTasksAcceptanceSectionsFromIssue,
  parseScopeTasksAcceptanceSections,
} = require('../.github/scripts/issue_scope_parser.js');
const {
  getKeepaliveInstructionWithMention,
} = require('../.github/scripts/keepalive_instruction_template.js');

function parseJson(value, fallback) {
  try {
    return value ? JSON.parse(value) : fallback;
  } catch (error) {
    return fallback;
  }
}

function coerceBool(value, fallback) {
  if (value === null || value === undefined) {
    return fallback;
  }

  const normalised = String(value).trim().toLowerCase();
  if (!normalised) {
    return fallback;
  }

  const truthy = new Set(['true', '1', 'yes', 'on']);
  const falsy = new Set(['false', '0', 'no', 'off']);
  if (truthy.has(normalised)) {
    return true;
  }
  if (falsy.has(normalised)) {
    return false;
  }
  return fallback;
}

function coerceNumber(value, fallback, { min } = { min: 0 }) {
  if (value === null || value === undefined) {
    return fallback;
  }
  const num = Number(value);
  if (!Number.isFinite(num) || num <= (min ?? 0)) {
    return fallback;
  }
  return num;
}

function dedupe(values) {
  const seen = new Set();
  const unique = [];
  for (const value of values) {
    if (!seen.has(value)) {
      seen.add(value);
      unique.push(value);
    }
  }
  return unique;
}

function normaliseLogin(login) {
  const base = String(login ?? '').trim().toLowerCase();
  if (!base) {
    return '';
  }
  return base.replace(/\[bot\]$/i, '');
}

const NON_ASSIGNABLE_LOGINS = new Set([
  'copilot',
  'chatgpt-codex-connector',
  'stranske-automation-bot',
  'github-actions',
  'dependabot'
]);

const KEEPALIVE_INSTRUCTION_REACTION = 'hooray';

function recordDispatchSummary({ summary, ok, reason, prNumber, commentId, agentAlias, bytes }) {
  if (!summary || typeof summary.addRaw !== 'function') {
    return;
  }
  const prValue = Number.isFinite(prNumber) && prNumber > 0 ? `#${prNumber}` : '#?';
  const commentValue = commentId ? String(commentId) : '<none>';
  const agentValue = (agentAlias || 'codex').trim() || 'codex';
  const byteValue = Number.isFinite(bytes) && bytes >= 0 ? String(bytes) : '0';
  const line = `DISPATCH: ok=${ok ? 'true' : 'false'} reason=${reason || 'unspecified'} pr=${prValue} comment=${commentValue} agent=${agentValue} bytes=${byteValue}`;
  summary.addRaw(line).addEOL();
}

function isAssignable(login) {
  const raw = String(login ?? '').trim();
  if (!raw) {
    return false;
  }

  if (/\[bot\]$/i.test(raw)) {
    return false;
  }

  const normalized = normaliseLogin(raw);
  if (!normalized || NON_ASSIGNABLE_LOGINS.has(normalized)) {
    return false;
  }

  return true;
}

function parseAgentLoginEntries(source, fallbackEntries) {
  const rawEntries = String(source ?? '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);

  const entries = rawEntries.length ? rawEntries : fallbackEntries;
  const seen = new Set();
  const result = [];

  for (const entry of entries) {
    const login = entry.trim();
    if (!login) {
      continue;
    }

    const normalized = normaliseLogin(login);
    if (!normalized || seen.has(normalized)) {
      continue;
    }

    seen.add(normalized);
    result.push({ original: login, normalized });
  }

  return result;
}

function escapeRegExp(value) {
  return String(value ?? '').replace(/[\\^$.*+?()[\]{}|]/g, '\\$&');
}

function safeDebug(core, message) {
  if (core && typeof core.debug === 'function') {
    core.debug(message);
  }
}

function tryRequire(moduleName) {
  if (typeof require !== 'function') {
    return { ok: false, error: new Error('require not available in this runtime') };
  }

  try {
    return { ok: true, module: require(moduleName) };
  } catch (error) {
    return { ok: false, error };
  }
}

function buildOctokitInstance({ core, github, token }) {
  if (github && typeof github.getOctokit === 'function') {
    try {
      return github.getOctokit(token);
    } catch (error) {
      safeDebug(core, `github.getOctokit failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (github && typeof github.constructor === 'function') {
    try {
      return new github.constructor({ auth: token });
    } catch (error) {
      safeDebug(core, `github.constructor fallback failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const actionsGithubResult = tryRequire('@actions/github');
  if (actionsGithubResult.ok && actionsGithubResult.module) {
    const actionsGithub = actionsGithubResult.module;
    if (actionsGithub && typeof actionsGithub.getOctokit === 'function') {
      try {
        return actionsGithub.getOctokit(token);
      } catch (error) {
        safeDebug(core, `@actions/github.getOctokit failed: ${error instanceof Error ? error.message : String(error)}`);
      }
    }

    if (actionsGithub && typeof actionsGithub.Octokit === 'function') {
      try {
        return new actionsGithub.Octokit({ auth: token });
      } catch (error) {
        safeDebug(core, `@actions/github.Octokit constructor failed: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  } else if (actionsGithubResult.error) {
    safeDebug(core, `@actions/github not available: ${actionsGithubResult.error instanceof Error ? actionsGithubResult.error.message : String(actionsGithubResult.error)}`);
  }

  const octokitRestResult = tryRequire('@octokit/rest');
  if (octokitRestResult.ok && octokitRestResult.module && typeof octokitRestResult.module.Octokit === 'function') {
    try {
      return new octokitRestResult.module.Octokit({ auth: token });
    } catch (error) {
      safeDebug(core, `@octokit/rest Octokit constructor failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  } else if (octokitRestResult.error) {
    safeDebug(core, `@octokit/rest not available: ${octokitRestResult.error instanceof Error ? octokitRestResult.error.message : String(octokitRestResult.error)}`);
  }

  return null;
}

function hasScopeTasksAcceptanceContent(source) {
  const sections = parseScopeTasksAcceptanceSections(source);
  if (!sections || typeof sections !== 'object') {
    return false;
  }

  return Object.values(sections).some((value) => Boolean(String(value || '').trim()));
}

function extractScopeTasksAcceptanceSections(source, options = {}) {
  const includePlaceholders =
    options && Object.prototype.hasOwnProperty.call(options, 'includePlaceholders')
      ? options.includePlaceholders
      : true;
  return extractScopeTasksAcceptanceSectionsFromIssue(source, { includePlaceholders });
}

function findScopeTasksAcceptanceBlock({ prBody, comments, override }) {
  const overrideBlock = String(override || '').trim();
  if (overrideBlock) {
    const extractedOverride = extractScopeTasksAcceptanceSections(overrideBlock);
    if (extractedOverride) {
      return extractedOverride;
    }
  }

  const sources = [];
  if (hasScopeTasksAcceptanceContent(prBody)) {
    sources.push(prBody);
  }

  for (const comment of comments || []) {
    const body = comment?.body || '';
    if (body && hasScopeTasksAcceptanceContent(body)) {
      sources.push(body);
    }
  }

  for (const source of sources) {
    const extracted = extractScopeTasksAcceptanceSections(source);
    if (extracted) {
      return extracted;
    }
  }

  return '';
}

function detectKeepaliveSentinel(comments, { sentinelPattern, headerPattern, agentLogins }) {
  if (!Array.isArray(comments) || !comments.length) {
    return null;
  }

  const codexLogins = new Set(agentLogins.map(normaliseLogin));
  codexLogins.add('stranske-automation-bot');
  const codexMentionPattern = /@codex\b/i;

  const sorted = [...comments].sort(
    (a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at)
  );

  for (const comment of sorted) {
    const body = comment?.body || '';
    if (!body) {
      continue;
    }

    if (!(sentinelPattern.test(body) || headerPattern.test(body))) {
      continue;
    }

    const login = normaliseLogin(comment?.user?.login);
    if (codexLogins.has(login) || codexMentionPattern.test(body)) {
      return { comment, login };
    }
  }

  return null;
}

function detectExistingKeepalive(comments, { marker, agentLogins, headerPattern }) {
  if (!Array.isArray(comments) || !comments.length) {
    return [];
  }

  const markerToken = String(marker || '').trim();
  const automationLogins = new Set(agentLogins.map(normaliseLogin));
  automationLogins.add('stranske-automation-bot');

  const looksLikeKeepalive = (comment, body) => {
    const login = normaliseLogin(comment?.user?.login);
    if (!automationLogins.has(login)) {
      return false;
    }

    if (markerToken && body.includes(markerToken)) {
      return true;
    }

    if (headerPattern.test(body)) {
      return true;
    }

    const lower = body.toLowerCase();
    return (
      lower.includes('keepalive mode:') ||
      (lower.includes('@codex plan-and-execute') && lower.includes('checklist'))
    );
  };

  return comments
    .map((comment) => {
      const body = comment?.body || '';
      if (!body) {
        return null;
      }

      const markerPresent = markerToken && body.includes(markerToken);
      if (!(markerPresent || looksLikeKeepalive(comment, body))) {
        return null;
      }

      return {
        comment,
        id: comment.id,
        body,
        timestamp: new Date(comment.created_at).getTime(),
      };
    })
    .filter(Boolean)
    .sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
}

async function dispatchKeepaliveCommand({
  core,
  github,
  owner,
  repo,
  token,
  payload,
}) {
  const trimmedToken = String(token ?? '').trim();
  if (!trimmedToken) {
    throw new Error('ACTIONS_BOT_PAT is required for keepalive dispatch.');
  }

  const octokit = buildOctokitInstance({ core, github, token: trimmedToken });
  if (!octokit) {
    throw new Error('Unable to construct Octokit instance for keepalive dispatch.');
  }

  if (!octokit?.rest?.repos?.createDispatchEvent) {
    throw new Error('Octokit instance missing repos.createDispatchEvent for keepalive dispatch.');
  }

  // GitHub repository_dispatch limits client_payload to 10 top-level properties.
  // Nest auxiliary data under `meta` to stay within the limit while preserving
  // backward compatibility by keeping core routing properties at the top level.
  const clientPayload = {
    issue: payload.issue,
    base: payload.base || '',
    head: payload.head || '',
    agent: payload.agent || 'codex',
    instruction_body: payload.instruction_body || '',
    meta: {
      comment_id: payload.comment_id,
      comment_url: payload.comment_url || '',
      round: payload.round || 0,
      trace: payload.trace || '',
    },
    quiet: true,
    reply: 'none',
  };

  await octokit.rest.repos.createDispatchEvent({
    owner,
    repo,
    event_type: 'codex-pr-comment-command',
    client_payload: clientPayload,
  });

  core.info(
    `Emitted repository_dispatch codex-pr-comment-command for PR #${clientPayload.issue} (comment ${clientPayload.meta.comment_id}).`
  );
}

function extractKeepaliveRound(body) {
  const match = String(body || '').match(/<!--\s*keepalive-round:(\d+)\s*-->/i);
  if (match) {
    const round = Number(match[1]);
    if (Number.isFinite(round) && round > 0) {
      return round;
    }
  }
  return null;
}

function computeNextRound(candidates) {
  if (!Array.isArray(candidates) || !candidates.length) {
    return 1;
  }

  const identifiers = new Set();
  for (const candidate of candidates) {
    if (!candidate) {
      continue;
    }
    const id = candidate.id || candidate.comment?.id;
    if (id !== undefined && id !== null) {
      identifiers.add(id);
    }
  }

  const count = identifiers.size || candidates.length;
  return count + 1;
}

function summariseList(items, limit = 20) {
  if (items.length <= limit) {
    return items;
  }
  const hidden = items.length - limit;
  return [
    ...items.slice(0, limit),
    `${hidden} more entries not shown to avoid excessive summary noise.`
  ];
}

function generateTraceSeed(rawSeed) {
  const base = String(rawSeed || '').trim();
  if (base) {
    return base;
  }

  const random = Math.random().toString(36).slice(2, 10);
  return `${Date.now()}-${random}`;
}

function sanitiseTraceComponent(value) {
  return String(value || '')
    .trim()
    .replace(/[^a-zA-Z0-9_.-]/g, '')
    .slice(0, 64);
}

function buildTraceToken({ seed, prNumber, round }) {
  const safeSeed = sanitiseTraceComponent(seed) || `${Date.now()}`;
  const safePr = sanitiseTraceComponent(prNumber);
  const safeRound = sanitiseTraceComponent(round);
  const parts = [safeSeed];
  if (safePr) {
    parts.push(`pr${safePr}`);
  }
  if (safeRound) {
    parts.push(`r${safeRound}`);
  }
  return parts.join('-');
}

async function runKeepalive({ core, github, context, env = process.env }) {
  const rawOptions = env.OPTIONS_JSON || '{}';
  const dryRun = (env.DRY_RUN || '').trim().toLowerCase() === 'true';
  const options = parseJson(rawOptions, {});
  const summary = core.summary;
  const traceSeed = generateTraceSeed(env.KEEPALIVE_TRACE || env.keepalive_trace || '');
  const pausedLabel = 'agents:paused';

  const addHeading = () => {
    summary.addHeading('Codex Keepalive');
    summary.addRaw(`Dry run: **${dryRun ? 'enabled' : 'disabled'}**`).addEOL();
  };

  const keepaliveEnabled = coerceBool(
    options.enable_keepalive ?? options.keepalive_enabled,
    true
  );
  if (!keepaliveEnabled) {
    core.info('Codex keepalive disabled via options_json.');
    addHeading();
    summary.addRaw('Skip requested via options_json.').addEOL();
    summary.addRaw('Skipped 0 paused PRs.').addEOL();
    summary.addRaw('Evaluated pull requests: 0').addEOL();
    await summary.write();
    return;
  }

  const instructionAuthorToken = String(env.ACTIONS_BOT_PAT || env.actions_bot_pat || '').trim();
  if (!instructionAuthorToken) {
    throw new Error('ACTIONS_BOT_PAT is required to author keepalive instructions as stranske.');
  }

  const instructionAuthorOctokit = buildOctokitInstance({
    core,
    github,
    token: instructionAuthorToken,
  });

  if (
    !instructionAuthorOctokit?.rest?.issues?.createComment ||
    !instructionAuthorOctokit?.rest?.reactions?.createForIssueComment
  ) {
    throw new Error('Unable to initialise Octokit client for keepalive instruction author.');
  }

  const idleMinutes = coerceNumber(options.keepalive_idle_minutes, 10, { min: 0 });
  const repeatMinutes = coerceNumber(options.keepalive_repeat_minutes, 30, { min: 0 });

  // When orchestrator is triggered by Gate completion, we want immediate keepalive activation
  const triggeredByGate = coerceBool(options.triggered_by_gate, false);
  const effectiveIdleMinutes = triggeredByGate ? 0 : idleMinutes;
  // When checking for recent commands, always use the full idle period even if triggered by Gate
  // This prevents keepalive from interrupting fresh human commands

  const labelSource = options.keepalive_labels ?? options.keepalive_label ?? 'agents:keepalive,agent:codex';
  let targetLabels = String(labelSource)
    .split(',')
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
  if (!targetLabels.length) {
    targetLabels = ['agents:keepalive', 'agent:codex'];
  }
  targetLabels = dedupe(targetLabels);

  // Instruction loaded from .github/templates/keepalive-instruction.md
  const defaultCommand = getKeepaliveInstructionWithMention('codex');
  const commandRaw = options.keepalive_command ?? defaultCommand;
  const command = String(commandRaw).trim() || defaultCommand;

  const canonicalMarker = '<!-- codex-keepalive-marker -->';
  const markerRaw = options.keepalive_marker ?? canonicalMarker;
  const marker = String(markerRaw || '').trim() || canonicalMarker;

  const sentinelRaw = options.keepalive_sentinel ?? '[keepalive]';
  const sentinelPattern = new RegExp(escapeRegExp(sentinelRaw), 'i');
  const keepaliveHeaderPattern = /###\s*Keepalive:\s*(on|enabled)/i;

  const scopeOverrideRaw = options.keepalive_scope_block ?? '';
  const scopeOverride = String(scopeOverrideRaw).trim();

  const agentSource = options.keepalive_agent_logins ?? 'chatgpt-codex-connector[bot],stranske-automation-bot';
  const agentEntries = parseAgentLoginEntries(agentSource, [
    'chatgpt-codex-connector[bot]',
    'stranske-automation-bot',
  ]);
  let agentLogins = agentEntries.map(({ normalized }) => normalized);
  agentLogins = dedupe(agentLogins);

  const maxPrs = coerceNumber(options.keepalive_max_prs ?? env.KEEPALIVE_MAX_PRS, 40, { min: 1 });

  const allowedAuthorEntries = parseAgentLoginEntries(
    options.keepalive_allowed_authors ?? env.KEEPALIVE_ALLOWED_AUTHORS,
    ['stranske-automation-bot', 'stranske']
  );
  const allowedKeepaliveAuthors = new Set(
    allowedAuthorEntries.map(({ normalized }) => normalized)
  );

  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const now = Date.now();
  const triggered = [];
  const refreshed = [];
  const previews = [];
  const assignmentSummaries = [];
  const paused = [];
  const roundTraces = [];
  const skipped = [];
  const guardrailViolations = [];
  let skippedCount = 0;
  let scanned = 0;
  let limitReached = false;
  addHeading();
  summary
    .addRaw(`Target labels: ${targetLabels.map((label) => `**${label}**`).join(', ')}`)
    .addEOL();
  summary
    .addRaw(
      `Agent logins: ${agentLogins
        .map((login) => `**${login}**`)
        .join(', ')}`
    )
    .addEOL();
  summary.addRaw(`Trace seed: ${traceSeed}`).addEOL();
  summary
    .addRaw(
      `Dispatch allow-list: ${allowedAuthorEntries
        .map(({ normalized }) => `**${normalized}**`)
        .join(', ')}`
    )
    .addEOL();

  const paginatePulls = github.paginate.iterator(
    github.rest.pulls.list,
    { owner, repo, state: 'open', per_page: 50 }
  );

  const fetchIssueComments = async (issueNumber) => {
    const comments = [];
    const perPage = 100;
    const hasIterator = Boolean(github.paginate?.iterator);

    if (hasIterator) {
      const iterator = github.paginate.iterator(github.rest.issues.listComments, {
        owner,
        repo,
        issue_number: issueNumber,
        per_page: perPage,
      });

      for await (const page of iterator) {
        const data = Array.isArray(page.data) ? page.data : [];
        if (data.length) {
          comments.push(...data);
        }
      }
    } else {
      let page = 1;
      while (true) {
        const { data } = await github.rest.issues.listComments({
          owner,
          repo,
          issue_number: issueNumber,
          per_page: perPage,
          page,
        });
        if (!Array.isArray(data) || !data.length) {
          break;
        }
        comments.push(...data);
        if (data.length < perPage) {
          break;
        }
        page += 1;
      }
    }

    return comments;
  };

  for await (const page of paginatePulls) {
    for (const pr of page.data) {
      if (scanned >= maxPrs) {
        limitReached = true;
        break;
      }
      scanned += 1;
      const labelNames = (pr.labels || []).map((label) =>
        (typeof label === 'string' ? label : label?.name || '').toLowerCase()
      );

      const prNumber = pr.number;
      const headRef = String(pr.head?.ref || '').trim();
      const recordSkip = (reason, { paused: pausedEntry = false } = {}) => {
        const entry = `#${prNumber} – ${reason}`;
        skipped.push(entry);
        skippedCount += 1;
        if (pausedEntry) {
          paused.push(entry);
        }
        core.info(`#${prNumber}: skipped – ${reason}`);
      };

      if (labelNames.includes(pausedLabel)) {
        recordSkip('keepalive paused via agents:paused label', { paused: true });
        continue;
      }

      const comments = await fetchIssueComments(prNumber);
      if (!comments.length) {
        recordSkip('no timeline comments');
        continue;
      }

      const missingRequiredLabels = targetLabels.filter(
        (label) => !labelNames.includes(label)
      );

      if (missingRequiredLabels.length) {
        const sentinel = detectKeepaliveSentinel(comments, {
          sentinelPattern,
          headerPattern: keepaliveHeaderPattern,
          agentLogins,
        });

        if (!sentinel) {
          recordSkip('keepalive opt-in not detected');
          continue;
        }

        core.info(`#${prNumber}: keepalive opted-in via sentinel comment ${sentinel.comment?.html_url || ''}.`);
        guardrailViolations.push(
          `#${prNumber} – keepalive sentinel active while required labels (${missingRequiredLabels.join(', ')}) are missing.`
        );
        continue;
      }

      const botComments = comments
        .filter((comment) => agentLogins.includes(normaliseLogin(comment.user?.login)))
        .sort((a, b) => new Date(a.updated_at || a.created_at) - new Date(b.updated_at || b.created_at));
      if (!botComments.length) {
        recordSkip('Codex has not commented yet');
        continue;
      }

      const lastAgentComment = botComments[botComments.length - 1];
      const lastAgentTs = new Date(lastAgentComment.updated_at || lastAgentComment.created_at).getTime();
      if (!Number.isFinite(lastAgentTs)) {
        recordSkip('unable to parse Codex timestamp');
        continue;
      }

      const minutesSinceAgent = (now - lastAgentTs) / 60000;
      if (minutesSinceAgent < effectiveIdleMinutes) {
        recordSkip(`last Codex activity ${minutesSinceAgent.toFixed(1)} minutes ago (< ${effectiveIdleMinutes})`);
        continue;
      }

      // Skip the mention guard for Gate-triggered sweeps to keep responsiveness high.
      if (!triggeredByGate) {
        const agentMentionPattern = /@(codex|claude|agent)\b/i;
        const agentMentionComments = comments
          .filter((comment) => agentMentionPattern.test(comment.body || ''))
          .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

        if (agentMentionComments.length > 0) {
          const latestMentionComment = agentMentionComments[agentMentionComments.length - 1];
          const latestMentionTs = new Date(latestMentionComment.created_at).getTime();

          if (Number.isFinite(latestMentionTs)) {
            const minutesSinceMention = (now - latestMentionTs) / 60000;
            const mentionWindow = Math.max(idleMinutes, 1);

            if (minutesSinceMention <= mentionWindow) {
              let allCommits = [];
              let page = 1;
              let fetched;
              do {
                const { data: commitsPage } = await github.rest.pulls.listCommits({
                  owner,
                  repo,
                  pull_number: prNumber,
                  per_page: 100,
                  page,
                });
                fetched = commitsPage.length;
                allCommits = allCommits.concat(commitsPage);
                page += 1;
              } while (fetched === 100);

              const sortedCommits = allCommits.sort((a, b) => {
                const aDate = new Date(a.commit.committer?.date || a.commit.author?.date || 0);
                const bDate = new Date(b.commit.committer?.date || b.commit.author?.date || 0);
                return bDate - aDate;
              });

              if (sortedCommits.length > 0) {
                const latestCommit = sortedCommits[0];
                const latestCommitTs = new Date(latestCommit.commit.committer?.date || latestCommit.commit.author?.date).getTime();
                if (Number.isFinite(latestCommitTs) && latestMentionTs > latestCommitTs) {
                  recordSkip(`waiting for commit after @agent command (${minutesSinceMention.toFixed(1)} minutes ago)`);
                  continue;
                }
              } else {
                recordSkip(`waiting for first commit after @agent command (${minutesSinceMention.toFixed(1)} minutes ago)`);
                continue;
              }
            }
          }
        }
      }

      const checklistComments = botComments
        .map((comment) => {
          const body = comment.body || '';
          const unchecked = (body.match(/- \[ \]/g) || []).length;
          const checked = (body.match(/- \[x\]/gi) || []).length;
          const total = unchecked + checked;
          return { comment, unchecked, total };
        })
        .filter((entry) => entry.total > 0 && entry.unchecked > 0)
        .sort((a, b) => new Date(b.comment.updated_at || b.comment.created_at) - new Date(a.comment.updated_at || a.comment.created_at));

      const latestChecklist = checklistComments[0];
      if (!latestChecklist) {
        recordSkip('no Codex checklist with outstanding tasks');
        continue;
      }

      const keepaliveCandidates = detectExistingKeepalive(comments, {
        marker,
        agentLogins,
        headerPattern: keepaliveHeaderPattern,
      });
      const latestKeepalive = keepaliveCandidates[0];
      if (latestKeepalive && !triggeredByGate) {
        const lastKeepaliveTs = latestKeepalive.timestamp;
        const minutesSinceKeepalive = (now - lastKeepaliveTs) / 60000;
        if (minutesSinceKeepalive < repeatMinutes) {
          recordSkip(`keepalive sent ${minutesSinceKeepalive.toFixed(1)} minutes ago (< ${repeatMinutes})`);
          continue;
        }
      }

  const totalTasks = latestChecklist.total;
  const outstanding = latestChecklist.unchecked;
  const nextRound = computeNextRound(keepaliveCandidates);
  const roundMarker = `<!-- keepalive-round: ${nextRound} -->`;
  const attemptMarker = `<!-- keepalive-attempt: ${nextRound} -->`;
  const traceToken = buildTraceToken({ seed: traceSeed, prNumber, round: nextRound });
  const traceMarker = `<!-- keepalive-trace: ${traceToken} -->`;

      const scopeBlock = findScopeTasksAcceptanceBlock({
        prBody: pr.body || '',
        comments,
        override: scopeOverride,
      });

      if (!scopeBlock) {
        core.warning(`#${prNumber}: missing scope/tasks/acceptance block; keepalive comment skipped.`);
        recordSkip('scope/tasks/acceptance block unavailable');
        continue;
      }

  const bodyParts = [roundMarker, attemptMarker, canonicalMarker, traceMarker, command];
      bodyParts.push('', scopeBlock);
      if (marker && marker !== canonicalMarker) {
        bodyParts.push('', marker);
      }
      const body = bodyParts.join('\n');
      const instructionSegment = extractInstructionSegment(body);
      const instructionBytes = instructionSegment ? computeInstructionByteLength(instructionSegment) : 0;
      
      // Ensure agent connectors are assigned before posting keepalive
      // This is critical so the agent actually engages when mentioned
      // Ensure agent connectors are assigned before posting keepalive
      try {
        // Get the current assignees from the PR data we already have
        const currentLogins = (pr.assignees || []).map((a) => normaliseLogin(a.login));
        const desiredAssignees = agentEntries
          .filter(({ normalized }) => !currentLogins.includes(normalized))
          .map(({ original }) => original);

        if (desiredAssignees.length === 0) {
          assignmentSummaries.push(`#${prNumber} – assignment skipped (existing assignees ok)`);
        } else {
          const assignableAssignees = desiredAssignees.filter(isAssignable);
          const skippedAssignees = desiredAssignees.filter((login) => !isAssignable(login));

          if (skippedAssignees.length > 0) {
            core.info(`#${prNumber}: ignoring non-assignable logins: ${skippedAssignees.join(', ')}`);
          }

          if (assignableAssignees.length > 0) {
            core.info(`#${prNumber}: adding human assignees: ${assignableAssignees.join(', ')}`);
            await github.rest.issues.addAssignees({
              owner,
              repo,
              issue_number: prNumber,
              assignees: assignableAssignees,
            });
            assignmentSummaries.push(`#${prNumber} – ensured assignees: ${assignableAssignees.join(', ')}`);
          } else {
            core.info(`#${prNumber}: no assignable human assignees available; skipping assignment.`);
            assignmentSummaries.push(`#${prNumber} – assignment skipped (no human assignees)`);
          }
        }
      } catch (error) {
        core.warning(`#${prNumber}: failed to ensure agent assignees: ${error.message}`);
        assignmentSummaries.push(`#${prNumber} – assignee update failed: ${error.message}`);
      }
      
      if (dryRun) {
        previews.push(
          `#${prNumber} – keepalive preview (remaining tasks: ${outstanding}, round ${nextRound}, trace ${traceToken})`
        );
        core.info(
          `#${prNumber}: dry run – keepalive comment not posted (remaining tasks: ${outstanding}, round ${nextRound}, trace ${traceToken}).`
        );
      } else {
        const response = await instructionAuthorOctokit.rest.issues.createComment({
          owner,
          repo,
          issue_number: prNumber,
          body,
        });
        triggered.push(
          `#${prNumber} – keepalive posted (remaining tasks: ${outstanding}, round ${nextRound}, trace ${traceToken})`
        );
        roundTraces.push(`Round = ${nextRound}, Trace = ${traceToken} (#${prNumber})`);
        core.info(
          `#${prNumber}: keepalive posted (remaining tasks: ${outstanding}, round ${nextRound}, trace ${traceToken}).`
        );

        const commentData = response?.data || {};
        const commentId = commentData.id;
        const commentUrl = commentData.html_url || '';
        const commentAuthor = normaliseLogin(commentData.user?.login);
        const hasRoundMarker = typeof body === 'string' && body.includes(roundMarker);
        const hasKeepaliveMarker = typeof body === 'string' && body.includes(canonicalMarker);
        const hasTraceMarker = typeof body === 'string' && body.includes(traceMarker);

        if (!hasRoundMarker || !hasKeepaliveMarker || !hasTraceMarker) {
          core.warning(`#${prNumber}: keepalive comment missing required markers; connector dispatch skipped.`);
        } else if (!commentAuthor) {
          core.warning(`#${prNumber}: keepalive comment author could not be determined; connector dispatch skipped.`);
        } else if (!allowedKeepaliveAuthors.has(commentAuthor)) {
          core.warning(
            `#${prNumber}: keepalive comment author @${commentAuthor} not in dispatch allow list; connector dispatch skipped.`
          );
        } else {
          if (commentId) {
            try {
              await instructionAuthorOctokit.rest.reactions.createForIssueComment({
                owner,
                repo,
                comment_id: commentId,
                content: KEEPALIVE_INSTRUCTION_REACTION,
              });
              core.info(
                `#${prNumber}: keepalive instruction reaction ${KEEPALIVE_INSTRUCTION_REACTION} added to comment ${commentId}.`
              );
            } catch (reactionError) {
              if (reactionError && reactionError.status === 409) {
                core.info(
                  `#${prNumber}: keepalive instruction reaction already present on comment ${commentId}.`
                );
              } else {
                const reactionMessage =
                  reactionError instanceof Error ? reactionError.message : String(reactionError);
                core.warning(
                  `#${prNumber}: failed to add keepalive instruction reaction on comment ${commentId}: ${reactionMessage}`
                );
              }
            }
          }

          const agentAlias = 'codex';
          if (!instructionSegment) {
            core.warning(`#${prNumber}: unable to extract instruction segment; connector dispatch skipped.`);
            recordDispatchSummary({
              summary,
              ok: false,
              reason: 'no-instruction-segment',
              prNumber,
              commentId,
              agentAlias,
              bytes: 0,
            });
          } else {
            try {
              await dispatchKeepaliveCommand({
                core,
                github,
                owner,
                repo,
                token: env.ACTIONS_BOT_PAT || env.actions_bot_pat || '',
                payload: {
                  issue: prNumber,
                  agent: agentAlias,
                  comment_id: commentId,
                  comment_url: commentUrl,
                  base: pr.base?.ref || '',
                  head: pr.head?.ref || headRef,
                  trace: traceToken,
                  round: nextRound,
                  instruction_body: instructionSegment,
                },
              });
              recordDispatchSummary({
                summary,
                ok: true,
                reason: 'ok',
                prNumber,
                commentId,
                agentAlias,
                bytes: instructionBytes,
              });
            } catch (error) {
              const message = error instanceof Error ? error.message : String(error);
              core.setFailed(`#${prNumber}: failed to emit keepalive dispatch: ${message}`);
              throw error;
            }
          }
        }
      }
    }
    if (limitReached) {
      break;
    }
  }

  if (limitReached) {
    summary.addRaw(`Processing capped at first ${maxPrs} pull requests to respect API limits.`).addEOL();
  }

  if (guardrailViolations.length) {
    summary.addDetails('Guardrail violations', summariseList(guardrailViolations));
    core.setFailed('Keepalive guardrail violated: required labels missing on opted-in pull request(s).');
  }

  if (dryRun) {
    if (previews.length) {
      summary.addDetails('Previewed keepalive comments', summariseList(previews));
    } else {
      summary.addRaw('No unattended Codex tasks detected (dry run).');
    }
    summary.addRaw(`Previewed keepalive count: ${previews.length}`).addEOL();
  } else {
    if (triggered.length) {
      summary.addDetails('Triggered keepalive comments', summariseList(triggered));
    } else {
      summary.addRaw('No unattended Codex tasks detected.');
    }
    summary.addRaw(`Triggered keepalive count: ${triggered.length}`).addEOL();
    if (roundTraces.length) {
      summary.addDetails('Keepalive round traces', summariseList(roundTraces));
    }
    if (refreshed.length) {
      summary.addDetails('Refreshed keepalive comments', summariseList(refreshed));
    }
    summary.addRaw(`Refreshed keepalive count: ${refreshed.length}`).addEOL();
  }
  if (skipped.length) {
    summary.addDetails('Skipped pull requests', summariseList(skipped));
  }
  summary.addRaw(`Skipped keepalive count: ${skippedCount}`).addEOL();
  if (paused.length) {
    summary.addDetails('Paused pull requests', summariseList(paused));
  }
  if (assignmentSummaries.length) {
    summary.addDetails('Assignee enforcement', summariseList(assignmentSummaries));
  }
  const pausedLineTemplate = `Skipped ${paused.length} paused PRs.`;
  const pausedLine = paused.length === 1
    ? pausedLineTemplate.replace('PRs.', 'PR.')
    : pausedLineTemplate;
  summary.addRaw(pausedLine).addEOL();
  summary.addRaw(`Evaluated pull requests: ${scanned}`).addEOL();
  await summary.write();
}

module.exports = {
  runKeepalive,
  dispatchKeepaliveCommand,
  buildOctokitInstance,
  extractScopeTasksAcceptanceSections,
  findScopeTasksAcceptanceBlock,
};
