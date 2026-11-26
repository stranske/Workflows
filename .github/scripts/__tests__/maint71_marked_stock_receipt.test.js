'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { runReviewReassessment } = require('../maint71_merge_sync_prs.js');

const repository = 'stranske/Trend_Model_Project';
const webPull = `https://github.com/${repository}/pull/6250`;
const head = '67492a53b310a27e3436d004c46b80333096343e';
const threadId = 'PRRT_kwDOO0LrSc68P4-l';
const reviewer = { login: 'chatgpt-codex-connector[bot]', id: 199175422, node_id: 'BOT_kgDOC98s_g', type: 'Bot' };
const operator = { login: 'stranske', id: 23046322, node_id: 'MDQ6VXNlcjIzMDQ2MzIy', type: 'User' };
const source = '1f7b9f46cc2db0865c9addd5601c63e10d9b1d99';
const plan = 'sha256:6b72242c32d8cbf728bcdb29b2b4f2f17bf1964b3aaad64f0ccfe6b5c9ea0e70';

async function replay(mutate = () => {}) {
  const request = {
    schema: 'maint71-review-reassessment/v1', repository, pr: 6250, head_sha: head,
    thread_id: threadId, plan_id: plan, generation: '6b72242c32d8',
    source_commit: source, originating_reviewer: 'codex',
  };
  const record = {
    schema: 'sync-pr-delivery-record/v1', repository, plan_id: plan, generation: request.generation,
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836', desired_tree_hash: '371bc72ee1e669ad29011ce38d168c5fea7863ee',
    source_commit: source, head_observed_sha: head, head_observed_at: '2026-11-26T15:30:55Z',
    lease_expires_at: '2099-01-01T00:00:00Z',
  };
  const pull = {
    number: 6250, state: 'open', draft: false, auto_merge: null,
    head: { ref: 'sync/workflows-delivery', sha: head }, user: operator,
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
  };
  // Compact native evidence for Trend #6250 r4704759618, r4710493432, and
  // r4710516766. The last reply keeps its exact visible text and hidden marker.
  const comment = (id, user, time, reviewId, body, parent) => ({
    id, user: { ...user }, body, created_at: time, updated_at: time, in_reply_to_id: parent,
    commit_id: head, path: 'tools/post_ci_summary.py', pull_request_review_id: reviewId,
    html_url: `${webPull}#discussion_r${id}`,
  });
  const origin = comment(4704759618, reviewer, '2026-11-26T06:44:34Z', 6069638057, 'Update the summary test when changing the footer');
  const ownerRequest = comment(4710493432, operator, '2026-11-26T15:32:36Z', 6076817976,
    `<!-- maint71-review-reassessment:v1 ${JSON.stringify(request)} -->`, origin.id);
  const receipt = comment(4710516766, reviewer, '2026-11-26T15:34:47Z', 6076846080,
    "<!-- codex-review-receipt:v1 -->\n\nCodex Review: Didn't find any major issues. Hooray!\n\n**Reviewed commit:** `67492a53b3`", origin.id);
  const comments = [origin, ownerRequest, receipt];
  const reviews = comments.slice(1).map(row => ({
    id: row.pull_request_review_id, user: { ...row.user }, state: 'COMMENTED', commit_id: head,
    submitted_at: row.created_at, html_url: `${webPull}#pullrequestreview-${row.pull_request_review_id}`,
  }));
  const config = { pull, origin, ownerRequest, receipt, reviews, afterCommitRead: () => {} };
  mutate(config);
  const node = row => ({
    fullDatabaseId: String(row.id), author: row.user, body: row.body, createdAt: row.created_at,
    updatedAt: row.updated_at, url: row.html_url, commit: { oid: row.commit_id },
  });
  const pages = nodes => ({ nodes, pageInfo: { hasNextPage: false } });
  const replies = [];
  const tasks = [];
  const client = {
    graphql: async query => {
      assert.doesNotMatch(query, /\bmutation\b/);
      return { repository: { pullRequest: { reviewThreads: pages([{
        id: threadId, path: origin.path, isResolved: false, isOutdated: false,
        comments: pages([...comments.map(node), ...replies.map(node)]),
      }]) } } };
    },
    paginate: async () => tasks,
    rest: {
      pulls: {
        get: async () => ({ data: pull }),
        getReviewComment: async ({ comment_id }) => ({ data: comments.find(row => String(row.id) === String(comment_id)) }),
        getReview: async ({ review_id }) => ({ data: reviews.find(row => row.id === review_id) }),
        createReplyForReviewComment: async ({ body, comment_id }) => {
          assert.equal(String(comment_id), String(origin.id));
          const reply = comment(4710520000, operator, '2026-11-26T15:35:40Z', 6076850000, body, origin.id);
          replies.push(reply);
          return { data: reply };
        },
      },
      users: { getAuthenticated: async () => ({ data: operator }) },
      repos: { getCommit: async ({ ref }) => {
        assert.equal(ref, '67492a53b3');
        config.afterCommitRead();
        return { data: { sha: head } };
      } },
      issues: {
        listComments: async () => tasks,
        createComment: async ({ body }) => {
          const task = { id: 7196900000, user: operator, body, created_at: '2026-11-26T15:35:40Z',
            html_url: `${webPull}#issuecomment-7196900000` };
          tasks.push(task);
          return { data: task };
        },
      },
    },
  };
  try {
    const result = await runReviewReassessment({
      context: { eventName: 'repository_dispatch', ref: 'refs/heads/main', actor: operator.login,
        payload: { action: 'maint71-review-reassessment' } },
      withRetry: operation => operation(client), rawRequest: JSON.stringify({ ...request, request_stage: 'disposition' }),
      registeredRepos: [repository], policyPath: path.join(__dirname, '../../../config/consumer_sync_review_policy.json'),
    });
    return { result, replies, tasks };
  } catch (error) {
    assert.deepEqual(replies, [], 'refused evidence cannot create a disposition reply');
    assert.deepEqual(tasks, [], 'refused evidence cannot create a disposition task');
    throw error;
  }
}

test('authentic marked stock receipt requests exact Trend finding disposition', async () => {
  const { result, replies, tasks } = await replay();
  assert.equal(result.task_status, 'disposition_task_requested');
  assert.equal(replies.length, 1);
  assert.match(replies[0].body, /maint71-review-disposition:v1/);
  assert.match(replies[0].body, /explicit ACCEPT or REJECT/);
  assert.equal(tasks.length, 1);
});

test('marked stock receipt refuses drift, changed provenance, and hidden or non-stock wording', async (t) => {
  for (const [label, mutate] of [
    ['wrong native parent', ({ receipt }) => { receipt.in_reply_to_id = 123; }],
    ['wrong reviewer login', ({ receipt }) => { receipt.user.login = 'lookalike'; }],
    ['wrong bot ID', ({ receipt }) => { receipt.user.id = 123; }],
    ['untrusted requester', ({ ownerRequest }) => { ownerRequest.user.login = 'lookalike'; }],
    ['mismatched enclosing review head', ({ reviews }) => { reviews[1].commit_id = '7'.repeat(40); }],
    ['moved live head', ({ pull }) => { pull.head.sha = '7'.repeat(40); }],
    ['head moves during native proof', (inputs) => {
      inputs.afterCommitRead = () => { inputs.pull.head.sha = '7'.repeat(40); };
    }],
    ['wrong marker location', ({ receipt }) => { receipt.body = `<details>\n${receipt.body}\n</details>`; }],
    ['wrong visible wording', ({ receipt }) => { receipt.body = receipt.body.replace("Didn't find any major issues.", 'Needs attention.'); }],
  ]) {
    await t.test(label, async () => {
      await assert.rejects(replay(mutate), /completed originating review|delivery changed/);
    });
  }
});
