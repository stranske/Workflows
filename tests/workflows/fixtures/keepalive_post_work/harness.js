'use strict';

const fs = require('fs');
const path = require('path');

const { runKeepalivePostWork } = require('../../../../.github/scripts/keepalive_post_work.js');

function createSummary() {
  const entries = [];
  return {
    entries,
    addHeading(text) {
      entries.push({ type: 'heading', text: String(text) });
      return this;
    },
    addTable(rows) {
      entries.push({ type: 'table', rows });
      return this;
    },
    addRaw(text) {
      entries.push({ type: 'raw', text: String(text) });
      return this;
    },
    addList(items) {
      entries.push({ type: 'list', items });
      return this;
    },
    addEOL() {
      entries.push({ type: 'raw', text: '\n' });
      return this;
    },
    async write() {
      return entries;
    },
  };
}

function normaliseEnvValue(value) {
  if (value === undefined || value === null) {
    return undefined;
  }
  return String(value);
}

async function main() {
  const scenarioPath = process.argv[2];
  if (!scenarioPath) {
    throw new Error('Scenario path required');
  }
  const resolvedPath = path.resolve(process.cwd(), scenarioPath);
  const scenario = JSON.parse(fs.readFileSync(resolvedPath, 'utf8'));

  const info = [];
  const warnings = [];
  const outputs = {};
  const summary = createSummary();

  const core = {
    info: (message) => info.push(String(message)),
    warning: (message) => warnings.push(String(message)),
    setOutput: (name, value) => {
      outputs[name] = String(value);
    },
    summary,
  };

  const repo = scenario.repo || { owner: 'stranske', repo: 'Trend_Model_Project' };
  const prNumber = Number.isFinite(scenario.prNumber)
    ? scenario.prNumber
    : Number(scenario.env?.PR_NUMBER);
  const issueNumber = Number.isFinite(scenario.issueNumber)
    ? scenario.issueNumber
    : Number(scenario.env?.ISSUE_NUMBER);

  const headSequence = Array.isArray(scenario.headSequence)
    ? scenario.headSequence.slice()
    : [];
  const defaultHead = scenario.previousHead || headSequence[0] || 'sha-initial';
  let headIndex = 0;
  const takeHead = () => {
    if (headSequence.length === 0) {
      return defaultHead;
    }
    if (headIndex < headSequence.length) {
      const value = headSequence[headIndex];
      headIndex += 1;
      return value;
    }
    return headSequence[headSequence.length - 1];
  };

  const baseRepoFullName = scenario.baseRepo || `${repo.owner}/${repo.repo}`;
  const headRepoFullName =
    scenario.headRepo === null ? '' : scenario.headRepo || `${repo.owner}/${repo.repo}`;
  const headRepoFork =
    typeof scenario.headRepoFork === 'boolean'
      ? scenario.headRepoFork
      : headRepoFullName.toLowerCase() !== baseRepoFullName.toLowerCase();

  const defaultLabels = Array.isArray(scenario.labels)
    ? scenario.labels
    : ['agents:keepalive', 'agent:codex'];
  const labelsSequence = Array.isArray(scenario.labelsSequence) && scenario.labelsSequence.length
    ? scenario.labelsSequence.map((labels) =>
        labels.map((name) => ({ name }))
      )
    : [defaultLabels.map((name) => ({ name }))];
  let labelIndex = 0;

  const listResponses = Array.isArray(scenario.createPr?.listResponses)
    ? scenario.createPr.listResponses
    : [];
  let listIndex = 0;

  const commentPages = Array.isArray(scenario.commentPages)
    ? scenario.commentPages.map((page) =>
        page.map((comment) => ({
          id: Number.isFinite(comment?.id) ? comment.id : Math.floor(Math.random() * 10_000),
          body: comment?.body || '',
          user: comment?.user || { login: comment?.user?.login || 'stranske' },
        }))
      )
    : [
        Array.isArray(scenario.comments)
          ? scenario.comments.map((comment) => ({
              id: Number.isFinite(comment?.id) ? comment.id : Math.floor(Math.random() * 10_000),
              body: comment?.body || '',
              user: comment?.user || { login: comment?.user?.login || 'stranske' },
            }))
          : [],
      ];
  let commentPageIndex = 0;
  let nextCommentId = 40_000;

  const events = {
    dispatches: [],
    workflowDispatches: [],
    merges: [],
    deletedRefs: [],
    labelsAdded: [],
    labelsRemoved: [],
    comments: [],
    reactions: [],
    headFetches: [],
    commentListings: [],
    updateBranch: [],
  };

  const github = {
    rest: {
      pulls: {
        get: async () => {
          const sha = takeHead();
          events.headFetches.push(sha);
          return {
            data: {
              number: prNumber,
              head: {
                sha,
                ref:
                  scenario.prHeadRef ||
                  scenario.headBranch ||
                  scenario.env?.HEAD_BRANCH ||
                  'codex/issue-1',
                repo: {
                  full_name: headRepoFullName || undefined,
                  fork: headRepoFork,
                },
              },
              base: {
                ref:
                  scenario.prBaseRef ||
                  scenario.baseBranch ||
                  scenario.env?.BASE_BRANCH ||
                  'main',
                repo: {
                  full_name: baseRepoFullName,
                  fork: false,
                },
              },
              user: { login: scenario.prUser || 'stranske-automation-bot' },
            },
          };
        },
        list: async () => {
          const response = listResponses[listIndex] || [];
          listIndex += 1;
          return { data: response };
        },
        merge: async ({ pull_number, merge_method, commit_title }) => {
          if (scenario.createPr?.mergeError) {
            throw new Error(scenario.createPr.mergeError);
          }
          events.merges.push({ pull_number, merge_method, commit_title });
          const merged = scenario.createPr?.mergeResult !== false;
          return { data: { merged, sha: scenario.createPr?.mergedSha || 'merged-sha' } };
        },
        updateBranch: async ({ pull_number, expected_head_sha }) => {
          events.updateBranch.push({ pull_number, expected_head_sha });
          const plan = scenario.updateBranch || {};
          if (plan.error) {
            throw new Error(plan.error);
          }
          return { status: plan.status ?? 202, data: {} };
        },
      },
      repos: {
        createDispatchEvent: async ({ event_type, client_payload }) => {
          events.dispatches.push({ event_type, client_payload });
          if (scenario.dispatchError) {
            throw new Error(scenario.dispatchError);
          }
        },
      },
      actions: {
        createWorkflowDispatch: async ({ workflow_id, ref, inputs }) => {
          events.workflowDispatches.push({ workflow_id, ref, inputs });
          if (scenario.workflowDispatchError) {
            throw new Error(scenario.workflowDispatchError);
          }
        },
        listWorkflowRuns: async () => ({
          data: { workflow_runs: Array.isArray(scenario.workflowRuns) ? scenario.workflowRuns : [] },
        }),
      },
      issues: {
        listLabelsOnIssue: async () => {
          const labels = labelsSequence[Math.min(labelIndex, labelsSequence.length - 1)] || [];
          labelIndex += 1;
          return { data: labels };
        },
        updateComment: async ({ comment_id, body }) => {
          // Minimal updateComment mock to support code paths that edit existing comments.
          // Update existing comment body if present; otherwise record as an update event.
          const id = Number.isFinite(comment_id) ? comment_id : Number(comment_id);
          let found = false;
          for (const c of events.comments) {
            if (c.id === id) {
              c.body = body || '';
              found = true;
              break;
            }
          }
          if (!found) {
            // Record as an update event for visibility in tests if no original comment exists.
            events.comments.push({ id, body: body || '' });
          }
          return { data: { id, body: body || '' } };
        },
        addLabels: async ({ labels }) => {
          events.labelsAdded.push(labels);
          if (scenario.labelsAddError) {
            throw new Error(scenario.labelsAddError);
          }
          return { data: labels.map((name) => ({ name })) };
        },
        removeLabel: async ({ name }) => {
          events.labelsRemoved.push(name);
          if (scenario.labelsRemoveError) {
            throw new Error(scenario.labelsRemoveError);
          }
          return { data: {} };
        },
        createComment: async ({ body }) => {
          const id = nextCommentId;
          nextCommentId += 1;
          events.comments.push({ id, body });
          if (scenario.commentError) {
            throw new Error(scenario.commentError);
          }
          return { data: { id, body, user: { login: scenario.commentUser || 'stranske' } } };
        },
        listComments: async () => {
          const page = commentPages[Math.min(commentPageIndex, commentPages.length - 1)] || [];
          commentPageIndex += 1;
          events.commentListings.push(page);
          return { data: page };
        },
      },
      git: {
        deleteRef: async ({ ref }) => {
          events.deletedRefs.push(ref);
          if (scenario.deleteRefError) {
            throw new Error(scenario.deleteRefError);
          }
          return { data: {} };
        },
      },
      reactions: {
        createForIssueComment: async ({ comment_id, content }) => {
          events.reactions.push({ comment_id, content });
          if (scenario.reactionError) {
            throw new Error(scenario.reactionError);
          }
          return { data: { id: `${comment_id}-${content}` } };
        },
      },
    },
    paginate: async (method, params) => {
      if (method === github.rest.pulls.list) {
        const { data } = await method(params);
        return Array.isArray(data) ? data : [];
      }
      if (method === github.rest.issues.listLabelsOnIssue) {
        const { data } = await method(params);
        return Array.isArray(data) ? data : [];
      }
      if (method === github.rest.issues.listComments) {
        const { data } = await method(params);
        return Array.isArray(data) ? data : [];
      }
      return [];
    },
  };

  const context = { repo };

  const env = { ...(scenario.env || {}) };
  env.TRACE = normaliseEnvValue(env.TRACE) || 'trace-harness';
  env.ROUND = normaliseEnvValue(env.ROUND) || '1';
  env.PR_NUMBER = normaliseEnvValue(env.PR_NUMBER) || String(prNumber || 0);
  env.ISSUE_NUMBER = normaliseEnvValue(env.ISSUE_NUMBER) || String(issueNumber || 0);
  env.BASE_BRANCH = normaliseEnvValue(env.BASE_BRANCH) || scenario.baseBranch || 'main';
  env.PR_BASE_BRANCH = normaliseEnvValue(env.PR_BASE_BRANCH) || scenario.prBaseRef || '';
  env.HEAD_BRANCH = normaliseEnvValue(env.HEAD_BRANCH) || scenario.headBranch || 'codex/issue-1';
  env.PR_HEAD_BRANCH = normaliseEnvValue(env.PR_HEAD_BRANCH) || scenario.prHeadRef || '';
  env.PREVIOUS_HEAD = normaliseEnvValue(env.PREVIOUS_HEAD) || defaultHead;
  env.COMMENT_ID = normaliseEnvValue(env.COMMENT_ID) || '123456';
  env.COMMENT_URL = normaliseEnvValue(env.COMMENT_URL) || 'https://example.test/comment';
  env.COMMENT_TRACE = normaliseEnvValue(env.COMMENT_TRACE) || 'trace-existing';
  env.COMMENT_ROUND = normaliseEnvValue(env.COMMENT_ROUND) || '1';
  env.AGENT_ALIAS = normaliseEnvValue(env.AGENT_ALIAS) || 'codex';
  env.TTL_SHORT_MS = normaliseEnvValue(env.TTL_SHORT_MS) || '0';
  env.POLL_SHORT_MS = normaliseEnvValue(env.POLL_SHORT_MS) || '0';
  env.TTL_LONG_MS = normaliseEnvValue(env.TTL_LONG_MS) || '0';
  env.POLL_LONG_MS = normaliseEnvValue(env.POLL_LONG_MS) || '0';
  env.SYNC_LABEL = normaliseEnvValue(env.SYNC_LABEL) || 'agents:sync-required';
  env.DEBUG_LABEL = normaliseEnvValue(env.DEBUG_LABEL) || 'agents:debug';
  env.DISPATCH_EVENT_TYPE = normaliseEnvValue(env.DISPATCH_EVENT_TYPE) || 'codex-pr-comment-command';
  env.AUTOMATION_LOGINS = normaliseEnvValue(env.AUTOMATION_LOGINS) || 'stranske-automation-bot';
  env.MERGE_METHOD = normaliseEnvValue(env.MERGE_METHOD) || 'squash';
  env.DELETE_TEMP_BRANCH = normaliseEnvValue(env.DELETE_TEMP_BRANCH) || 'true';

  await runKeepalivePostWork({ core, github, context, env });

  const payload = {
    info,
    warnings,
    outputs,
    events,
    summary: summary.entries,
  };

  process.stdout.write(JSON.stringify(payload));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
