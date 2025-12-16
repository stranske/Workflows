#!/usr/bin/env node
'use strict';

const fs = require('fs');
const { detectKeepalive } = require('../../../../.github/scripts/agents_pr_meta_keepalive.js');

async function main() {
  const [, , scenarioPath] = process.argv;
  if (!scenarioPath) {
    throw new Error('Scenario path is required');
  }

  const scenario = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'));

  const info = [];
  const warnings = [];
  const outputs = {};
  const calls = {
    reactionsCreated: [],
    commentsUpdated: [],
  };

  const core = {
    info: (message) => info.push(String(message)),
    warning: (message) => warnings.push(String(message)),
    setOutput: (name, value) => {
      outputs[name] = String(value);
    },
  };

  const repo = scenario.repo || { owner: 'stranske', repo: 'Trend_Model_Project' };

  const comment = scenario.comment || {};
  const issueNumber = scenario.issue?.number ?? scenario.pull?.number ?? 0;

  const context = {
    payload: {
      comment: {
        id: comment.id || undefined,
        body: comment.body || '',
        user: { login: comment.user?.login || 'stranske' },
        html_url: comment.html_url || undefined,
      },
      issue: { number: issueNumber },
      repository: scenario.repository || { default_branch: 'phase-2-dev' },
    },
    repo,
  };

  const pull = scenario.pull || {};
  const pullError = scenario.pullError;

  const issueNumberKey = String(issueNumber || '0');
  const commentStore = new Map();
  const baseComments = Array.isArray(scenario.comments) ? scenario.comments : [];
  commentStore.set(
    issueNumberKey,
    baseComments.map((entry) => ({
      id: entry.id,
      body: entry.body,
    }))
  );

  const reactionsByComment = (() => {
    const raw = scenario.reactions;
    if (Array.isArray(raw)) {
      return new Map([[String(comment?.id || '0'), raw]]);
    }
    if (raw && typeof raw === 'object') {
      return new Map(
        Object.entries(raw).map(([key, value]) => [String(key), Array.isArray(value) ? value : []])
      );
    }
    return new Map();
  })();

  const github = {
    rest: {
      pulls: {
        get: async ({ pull_number }) => {
          if (pullError) {
            throw new Error(pullError);
          }
          const data = {
            number: pull.number ?? pull_number,
            title: pull.title || '',
            body: pull.body || '',
            head: { ref: pull.head?.ref || '' },
            base: { ref: pull.base?.ref || '' },
          };
          return { data };
        },
      },
      issues: {
        listComments: async ({ issue_number }) => {
          const key = String(issue_number || '0');
          const existing = commentStore.get(key) || [];
          return { data: existing.map((item) => ({ ...item })) };
        },
        updateComment: async ({ comment_id, body }) => {
          const key = String(issueNumber || '0');
          const comments = commentStore.get(key) || [];
          for (const entry of comments) {
            if (String(entry.id) === String(comment_id)) {
              entry.body = body;
            }
          }
          calls.commentsUpdated.push({ comment_id, body });
          return { data: { id: comment_id, body } };
        },
      },
      reactions: {
        listForIssueComment: async ({ comment_id }) => {
          if (scenario.reactionsListError) {
            throw new Error(scenario.reactionsListError);
          }
          const key = String(comment_id ?? '');
          const data = reactionsByComment.get(key) || [];
          return { data };
        },
        createForIssueComment: async ({ comment_id, content }) => {
          calls.reactionsCreated.push({ comment_id, content });
          if (scenario.reactionsCreateError) {
            const error = new Error(scenario.reactionsCreateError);
            if (scenario.reactionsCreateStatus) {
              error.status = scenario.reactionsCreateStatus;
            }
            throw error;
          }
          const key = String(comment_id ?? '');
          const existing = reactionsByComment.get(key) || [];
          reactionsByComment.set(key, existing.concat({ content }));
          return { data: { content } };
        },
      },
    },
    paginate: async (method, params) => {
      const response = await method(params);
      if (response && Array.isArray(response.data)) {
        return response.data;
      }
      return [];
    },
  };

  const env = {
    ALLOWED_LOGINS: scenario.env?.ALLOWED_LOGINS || 'stranske',
    KEEPALIVE_MARKER: scenario.env?.KEEPALIVE_MARKER || '<!-- codex-keepalive-marker -->',
  };

  const result = await detectKeepalive({ core, github, context, env });

  const payload = {
    outputs,
    info,
    warnings,
    result,
    calls,
  };

  process.stdout.write(JSON.stringify(payload));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
