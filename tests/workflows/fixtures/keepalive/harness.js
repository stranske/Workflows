#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const Module = require('module');

class SummaryRecorder {
  constructor() {
    this.entries = [];
    this.written = false;
  }

  addHeading(text, level = 1) {
    this.entries.push({ type: 'heading', text: String(text), level });
    return this;
  }

  addRaw(text) {
    this.entries.push({ type: 'raw', text: String(text) });
    return this;
  }

  addEOL() {
    this.entries.push({ type: 'eol' });
    return this;
  }

  addDetails(title, items) {
    this.entries.push({ type: 'details', title: String(title), items: Array.from(items).map(String) });
    return this;
  }

  addLink(text, href) {
    this.entries.push({ type: 'link', text: String(text), href: String(href) });
    return this;
  }

  addList(items) {
    this.entries.push({ type: 'list', items: Array.from(items).map(String) });
    return this;
  }

  addTable(rows) {
    const normalised = Array.from(rows).map((row) =>
      Array.isArray(row)
        ? row.map((cell) => (typeof cell === 'object' && cell !== null ? cell.data ?? '' : String(cell)))
        : row
    );
    this.entries.push({ type: 'table', rows: normalised });
    return this;
  }

  async write() {
    this.written = true;
    return this;
  }

  toJSON() {
    return { entries: this.entries, written: this.written };
  }
}

function loadKeepaliveRunner() {
  const targetPath = path.resolve(__dirname, '../../../../scripts/keepalive-runner.js');
  const code = fs.readFileSync(targetPath, 'utf8');
  const sandbox = {
    module: { exports: {} },
    exports: {},
    require: Module.createRequire(targetPath),
    __dirname: path.dirname(targetPath),
    __filename: targetPath,
    process,
    console,
    Date,
  };
  vm.createContext(sandbox);
  const wrapper = Module.wrap(code);
  const script = new vm.Script(wrapper, { filename: targetPath });
  const compiled = script.runInContext(sandbox);
  compiled.call(sandbox.exports, sandbox.exports, sandbox.require, sandbox.module, sandbox.__filename, sandbox.__dirname);
  return sandbox.module.exports;
}

let commentSequence = 1;

const DEFAULT_SCOPE_BLOCK = `<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
For every keepalive round, create a new instruction comment (do not edit any prior bot comment).

Always include hidden markers at the top of the comment body:

<!-- keepalive-round: {N} -->

<!-- keepalive-attempt: {N} -->

<!-- codex-keepalive-marker -->

<!-- keepalive-trace: {TRACE} -->

Visible content must begin with @codex followed by the current scope / tasks / acceptance criteria the agent should act on.

Non-Goals

Changing Gate semantics, acceptance criteria, labels, or agent selection

Modifying the separate status/checklist updater (it may continue to edit the status block)

#### Tasks
- [ ] In the keepalive poster (Codex Keepalive Sweep):

- [ ] Generate a unique KEEPALIVE_TRACE (e.g., epoch-second + short random suffix).

- [ ] Compute the next round number; do not infer it from an edited comment.

- [ ] Use peter-evans/create-issue-comment@v3 (or Octokit issues.createComment) to create a new comment with body:

  <!-- keepalive-round: {N} -->
  <!-- keepalive-attempt: {N} -->
  <!-- codex-keepalive-marker -->
  <!-- keepalive-trace: {TRACE} -->
  @codex Use the scope, acceptance criteria, and task list to ship code and tests each round. Start implementing the next coding task instead of only reposting checklists, and update checkboxes only after real work and verification are done. Re-post the refreshed scope/tasks/acceptance once you've completed work.

  <Scope/Tasks/Acceptance…>
- [ ] Authenticate with the PAT that posts as stranske (ACTIONS_BOT_PAT).

- [ ] Write Round = N and TRACE = … into the step summary for correlation.

#### Acceptance criteria
- [ ] Each keepalive cycle adds exactly one new bot comment (no edits) whose body starts with the three hidden markers and an @codex instruction.

- [ ] An issue_comment.created run appears in Actions showing author = stranske when ACTIONS_BOT_PAT is configured (fallback to stranske-automation-bot only when required).

- [ ] The posted comment contains the current Scope/Tasks/Acceptance block.

- [ ] The poster’s step summary shows Round and TRACE values.
<!-- auto-status-summary:end -->`;

function allocateCommentId(existingId) {
  if (existingId !== undefined && existingId !== null) {
    return existingId;
  }
  const id = commentSequence;
  commentSequence += 1;
  return id;
}

function normaliseComment(comment) {
  if (!comment) {
    return null;
  }
  if (typeof comment !== 'object') {
    return null;
  }
  const login = comment.user && typeof comment.user === 'object' ? comment.user.login : undefined;
  const id = allocateCommentId(comment.id);
  return {
    id,
    body: comment.body || '',
    created_at: comment.created_at || comment.updated_at || new Date().toISOString(),
    updated_at: comment.updated_at || null,
    user: { login: login || '' },
  };
}

async function runScenario(scenario) {
  commentSequence = 1;
  const summary = new SummaryRecorder();
  const info = [];
  const warnings = [];
  const notices = [];
  let failedMessage = null;
  const dispatchEvents = [];

  const core = {
    summary,
    info: (message) => info.push(String(message)),
    warning: (message) => warnings.push(String(message)),
    notice: (message) => notices.push(String(message)),
    setFailed: (message) => {
      failedMessage = String(message);
    },
  };

  const pulls = Array.from(scenario.pulls || []).map((pull) => ({
    number: pull.number,
    head: {
      ref: pull.head?.ref || `codex/issue-${pull.number}`,
    },
    base: {
      ref: pull.base?.ref || 'main',
    },
    labels: Array.from(pull.labels || []).map((label) =>
      typeof label === 'string' ? { name: label } : label
    ),
    body: pull.body || DEFAULT_SCOPE_BLOCK,
  }));

  const commentMap = new Map();
  for (const pull of scenario.pulls || []) {
    const normalised = Array.from(pull.comments || []).map((comment) => normaliseComment(comment)).filter(Boolean);
    commentMap.set(pull.number, normalised);
  }

  const createdComments = [];
  const instructionReactions = [];
  const updatedComments = [];

  const listPulls = async ({ per_page = 50, page = 1 }) => {
    const start = (page - 1) * per_page;
    const slice = pulls.slice(start, start + per_page);
    return { data: slice };
  };

  const listComments = async ({ issue_number, per_page = 30, page = 1 }) => {
    const comments = commentMap.get(issue_number) || [];
    const start = (page - 1) * per_page;
    const slice = comments.slice(start, start + per_page);
    return { data: slice };
  };

  const commentAuthor = () => {
    const identity = scenario.identity || {};
    return identity.keepalive_author || identity.service_bot || 'stranske';
  };

  const createComment = async ({ issue_number, body }) => {
    const entry = { issue_number, body };
    entry.id = allocateCommentId();
    entry.html_url = `https://example.test/${issue_number}#comment-${entry.id}`;
    entry.user = { login: commentAuthor() };
    createdComments.push(entry);
    return { data: entry };
  };

  const updateComment = async ({ comment_id, body }) => {
    const entry = { comment_id, body };
    entry.user = { login: commentAuthor() };
    updatedComments.push(entry);
    return { data: entry };
  };

  const listCommits = async ({ owner, repo, pull_number, per_page = 100 }) => {
    // Mock: return empty commits array for tests
    // The keepalive logic will see no commits and proceed normally
    return { data: [] };
  };

  const listAssignees = async ({ owner, repo, issue_number }) => {
    // Mock: return empty assignees array for tests
    // The keepalive logic will add the required agent assignees
    return { data: [] };
  };

  const addAssignees = async ({ owner, repo, issue_number, assignees }) => {
    // Mock: no-op for tests, just return success
    return { data: {} };
  };

  const dispatchEvent = async ({ owner, repo, event_type, client_payload }) => {
    dispatchEvents.push({ owner, repo, event_type, client_payload });
    return { data: {} };
  };

  const github = {
    rest: {
      pulls: {
        list: listPulls,
        listCommits,
      },
      issues: {
        listComments,
        createComment,
        updateComment,
        listAssignees,
        addAssignees,
      },
      reactions: {
        createForIssueComment: async ({ comment_id, content }) => {
          instructionReactions.push({ comment_id, content });
          return { data: { content } };
        },
      },
      repos: {
        createDispatchEvent: dispatchEvent,
      },
    },
    paginate: {
      iterator: (method, params) => {
        if (method !== listPulls && method !== listComments) {
          throw new Error('Unsupported paginate target');
        }
        const defaultPerPage = method === listPulls ? 50 : 30;
        const perPage = params.per_page || defaultPerPage;
        return {
          async *[Symbol.asyncIterator]() {
            let page = 1;
            while (true) {
              const response = await method({ ...params, page, per_page: perPage });
              const data = Array.isArray(response.data) ? response.data : [];
              if (!data.length) {
                break;
              }
              yield response;
              if (data.length < perPage) {
                break;
              }
              page += 1;
            }
          },
        };
      },
    },
    getOctokit: (token) => {
      if (!token) {
        throw new Error('Token is required');
      }
      return {
        rest: {
          repos: {
            createDispatchEvent: dispatchEvent,
          },
          issues: {
            createComment,
          },
          reactions: {
            createForIssueComment: async ({ comment_id, content }) => {
              instructionReactions.push({ comment_id, content });
              return { data: { content } };
            },
          },
        },
      };
    },
  };

  const context = {
    repo: {
      owner: scenario.repo?.owner || 'owner',
      repo: scenario.repo?.repo || 'repo',
    },
  };

  const originalEnv = {};
  const envOverrides = {
    ACTIONS_BOT_PAT: 'dummy-token',
    SERVICE_BOT_PAT: 'service-token',
    ...(scenario.env || {}),
  };
  for (const [key, value] of Object.entries(envOverrides)) {
    originalEnv[key] = process.env[key];
    process.env[key] = String(value);
  }

  const originalNow = Date.now;
  if (scenario.now) {
    const fixed = new Date(scenario.now).getTime();
    Date.now = () => fixed;
  }

  try {
    const { runKeepalive } = loadKeepaliveRunner();
    await runKeepalive({ core, github, context, env: process.env });
  } finally {
    Date.now = originalNow;
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  }

  return {
    summary: summary.toJSON(),
    logs: { info, warnings, notices, failedMessage },
    created_comments: createdComments,
    updated_comments: updatedComments,
    dispatch_events: dispatchEvents,
    instruction_reactions: instructionReactions,
  };
}

async function main() {
  const scenarioPath = process.argv[2];
  if (!scenarioPath) {
    console.error('Usage: node harness.js <scenario.json>');
    process.exit(2);
  }

  let scenario;
  try {
    scenario = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'));
  } catch (error) {
    console.error('Failed to load scenario:', error.message);
    process.exit(2);
  }

  try {
    const result = await runScenario(scenario);
    process.stdout.write(JSON.stringify(result));
  } catch (error) {
    console.error('Harness execution failed:', error.stack || error.message);
    process.exit(1);
  }
}

main();
