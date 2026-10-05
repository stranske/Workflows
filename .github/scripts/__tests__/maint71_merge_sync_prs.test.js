'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  devToolBaseRefreshResult, ensureExactHeadReviewRequest, hasCompleteReviewThreadEvidence,
  parseReviewReassessmentRequest, runReviewReassessment, run,
} = require('../maint71_merge_sync_prs');

test('failed reviewer retry is exact-head, terminal-only, once per binding and request-only', async () => {
  const request = { schema: 'maint71-review-reassessment/v1',
    repository: 'stranske/Ready', pr: 592, head_sha: 'a'.repeat(40),
    thread_id: 'PRRT_retry', plan_id: 'plan-1', generation: 'gen-1',
    source_commit: 'b'.repeat(40), originating_reviewer: 'codex' };
  const record = { schema: 'sync-pr-delivery-record/v1', repository: request.repository,
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: request.plan_id, generation: request.generation, desired_tree_hash: 'tree-1',
    source_commit: request.source_commit, head_observed_sha: request.head_sha,
    head_observed_at: '2026-09-24T22:00:00Z',
    lease_expires_at: '2099-01-01T00:00:00Z' };
  const canonical = JSON.stringify(request);
  const prior = { fullDatabaseId: '12', author: { login: 'stranske' },
    createdAt: '2026-09-24T22:00:00Z',
    body: '<!-- maint71-review-reassessment:v1 ' + canonical + ' -->' };
  const nodes = [{ fullDatabaseId: '11', author: { login: 'chatgpt-codex-connector' },
    body: 'Preserve required evidence' }, prior];
  const failedRow = '| 📝 **Code Review** | ⚠️ **Failed** <relative-time datetime="2026-09-24T22:01:00Z">2026-09-24T22:01:00Z</relative-time> | `aaaaaaa` | Manual request |';
  const summary = { user: { login: 'chatgpt-codex-connector[bot]' },
    updated_at: '2026-09-24T22:01:01Z',
    body: '<!-- codex-pull-request-review-summary -->\n| Review | Status | Commit | Review trigger |\n| --- | --- | --- | --- |\n' + failedRow };
  let summaries = [summary], resolvedSha = request.head_sha, posts = 0;
  let paginationRace = false, siblingComplete = true;
  const pr = { state: 'open', draft: false, auto_merge: null,
    user: { login: 'stranske-automation-bot' },
    head: { ref: 'sync/workflows-candidate', sha: request.head_sha },
    body: '<!-- sync-pr-delivery-record:v1 ' + JSON.stringify(record) + ' -->' };
  const github = { paginate: async () => {
    if (paginationRace) pr.head.sha = 'c'.repeat(40);
    return summaries;
  }, rest: {
    users: { getAuthenticated: async () => ({ data: { login: 'stranske' } }) },
    pulls: {
      get: async () => ({ data: pr }),
      createReplyForReviewComment: async ({ body }) => {
        posts++;
        const posted = { id: 13, body, created_at: '2026-09-24T22:02:00Z',
          html_url: 'https://github.com/stranske/Ready/pull/592#discussion_r13',
          user: { login: 'stranske' } };
        nodes.push({ fullDatabaseId: '13', author: posted.user, body,
          createdAt: posted.created_at, url: posted.html_url });
        return { data: posted };
      },
    },
    issues: { listComments: () => {} },
    repos: { getCommit: async () => ({ data: { sha: resolvedSha } }) },
  }, graphql: async () => ({ repository: { pullRequest: { reviewThreads: {
    pageInfo: { hasNextPage: false }, nodes: [{ id: request.thread_id,
      isResolved: false, isOutdated: false,
      comments: { pageInfo: { hasNextPage: false }, nodes } }, {
        id: 'PRRT_sibling', isResolved: false, isOutdated: false,
        comments: { pageInfo: { hasNextPage: !siblingComplete }, nodes: [] },
      }],
  } } } }) };
  const args = { context: { eventName: 'repository_dispatch', ref: 'refs/heads/main',
    payload: { action: 'maint71-review-reassessment' }, actor: 'stranske' },
    withRetry: (fn) => fn(github),
    rawRequest: JSON.stringify({ ...request, request_stage: 'retry' }),
    registeredRepos: [request.repository],
    policyPath: path.join(__dirname, '..', '..', '..', 'config', 'consumer_sync_review_policy.json') };
  for (const defect of ['missing-summary', 'duplicate-summary', 'forged-summary', 'pending',
    'completed', 'wrong-head', 'ambiguous-commit', 'stale-failure', 'future-failure',
    'stale-update', 'multiple-rows', 'missing-prior', 'duplicate-prior', 'changed-head',
    'subsequent-completion', 'explicit-acceptance', 'explicit-rejection',
    'partial-sibling', 'indented-running-row', 'pagination-head-race']) {
    const savedBody = summary.body, savedUpdate = summary.updated_at;
    summaries = [summary]; resolvedSha = request.head_sha;
    if (defect === 'missing-summary') summaries = [];
    if (defect === 'duplicate-summary') summaries.push({ ...summary });
    if (defect === 'forged-summary') summary.user.login = 'untrusted';
    if (defect === 'pending') summary.body = savedBody.replace('Failed', 'Running');
    if (defect === 'completed') summary.body = savedBody.replace('Failed', 'Completed');
    if (defect === 'wrong-head') summary.body = savedBody.replace('aaaaaaa', 'ccccccc');
    if (defect === 'ambiguous-commit') resolvedSha = 'c'.repeat(40);
    if (defect === 'stale-failure') summary.body = savedBody.replaceAll('22:01:00', '21:59:00');
    if (defect === 'future-failure') summary.body = savedBody.replaceAll('2026-09-24', '2099-09-24');
    if (defect === 'stale-update') summary.updated_at = '2026-09-24T22:00:30Z';
    if (defect === 'multiple-rows') summary.body += '\n' + failedRow;
    if (defect === 'missing-prior') nodes.pop();
    if (defect === 'duplicate-prior') nodes.push({ ...prior });
    if (defect === 'changed-head') pr.head.sha = 'c'.repeat(40);
    if (defect === 'subsequent-completion') summaries.push({
      user: { login: 'chatgpt-codex-connector' }, created_at: '2026-09-24T22:01:30Z',
      body: "Codex Review: Didn't find any major issues." });
    if (['explicit-acceptance', 'explicit-rejection'].includes(defect)) nodes.push({
      fullDatabaseId: '14', author: { login: 'chatgpt-codex-connector' },
      createdAt: '2026-09-24T22:01:30Z', commit: { oid: request.head_sha },
      body: defect === 'explicit-acceptance'
        ? `ACCEPT <!-- sync-review-accepted:${request.head_sha} -->` : 'REJECT: still invalid',
    });
    if (defect === 'partial-sibling') siblingComplete = false;
    if (defect === 'indented-running-row') summary.body += '\n  | Code Review | Running | `aaaaaaa` | Manual request |';
    if (defect === 'pagination-head-race') paginationRace = true;
    await assert.rejects(runReviewReassessment(args), /retry|delivery changed/i, defect);
    assert.equal(posts, 0, defect);
    summary.body = savedBody; summary.updated_at = savedUpdate;
    summary.user.login = 'chatgpt-codex-connector[bot]'; pr.head.sha = request.head_sha;
    paginationRace = false; siblingComplete = true;
    if (['explicit-acceptance', 'explicit-rejection'].includes(defect)) nodes.pop();
    if (defect === 'missing-prior') nodes.push(prior);
    if (defect === 'duplicate-prior') nodes.pop();
  }
  summaries = [summary]; resolvedSha = request.head_sha;
  const first = await runReviewReassessment(args);
  assert.equal(first.status, 'review_blocked_reassessment_requested');
  assert.equal(posts, 1);
  assert.match(nodes.at(-1).body, /maint71-review-retry:v1/);
  assert.match(nodes.at(-1).body, /No unrelated edits, resolution or merge actions/);
  summaries = []; // Recovery must reuse the durable request after summary updates.
  const second = await runReviewReassessment(args);
  assert.equal(second.status, 'review_blocked_reassessment_reused');
  assert.equal(posts, 1);
});


test('behind leased dev-tool delivery routes to producer before branch update', () => {
  const context = {
    owner: 'stranske', repo: 'Ready', pr: 591,
    branch: 'deps/sync-dev-versions-1234', delivery_lane: 'dev-tool-sync',
    head_sha: 'a'.repeat(40), plan_id: 'plan-1',
    source_commit: 'b'.repeat(40), delivery_generation: 'generation-1',
  };
  assert.deepEqual(devToolBaseRefreshResult(context), {
    ...context, delivery_disposition: 'awaiting-base-refresh',
    blocker_owner: 'maint-52', next_command: 'dispatch-maint-52-scoped',
    status: 'dev_tool_base_refresh_required',
  });
  assert.equal(devToolBaseRefreshResult({ ...context, delivery_lane: 'sync' }), null);
  const source = fs.readFileSync(path.join(__dirname, '..', 'maint71_merge_sync_prs.js'), 'utf8');
  assert.match(source, /if \(devToolRefresh\) \{\s*results\.push\(devToolRefresh\);\s*continue;\s*\}\s*await withRetry\(\(client\) => client\.rest\.pulls\.updateBranch/s);
});

test('review reassessment parser accepts only exact versioned identities', () => {
  const request = {
    schema: 'maint71-review-reassessment/v1', repository: 'stranske/Ready', pr: 592,
    head_sha: 'a'.repeat(40), thread_id: 'PRRT_test', plan_id: 'plan-1',
    generation: 'gen-1', source_commit: 'b'.repeat(40),
    originating_reviewer: 'codex',
  };
  assert.deepEqual(parseReviewReassessmentRequest(JSON.stringify(request)), request);
  assert.throws(() => parseReviewReassessmentRequest(JSON.stringify({ ...request, extra: true })),
    /missing or extra fields/);
  assert.throws(() => parseReviewReassessmentRequest(JSON.stringify({ ...request, head_sha: 'bad' })),
    /invalid identity/);
  assert.throws(() => parseReviewReassessmentRequest(JSON.stringify({ ...request, request_stage: 'unknown' })),
    /invalid identity/);
});

test('source-owned reviewer reassessment supports stable generated lanes without merge authority', async () => {
  const request = {
    schema: 'maint71-review-reassessment/v1', repository: 'stranske/Ready', pr: 592,
    head_sha: 'a'.repeat(40), thread_id: 'PRRT_test', plan_id: 'plan-1',
    generation: 'gen-1', source_commit: 'b'.repeat(40),
    originating_reviewer: 'codex',
  };
  const record = {
    schema: 'sync-pr-delivery-record/v1', repository: request.repository,
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: request.plan_id, generation: request.generation,
    desired_tree_hash: 'tree-1',
    source_commit: request.source_commit, head_observed_sha: request.head_sha,
    head_observed_at: '2026-09-24T22:00:00Z',
    lease_expires_at: '2099-01-01T00:00:00Z',
  };
  const pr = {
    state: 'open', draft: false, auto_merge: null,
    user: { login: 'stranske-automation-bot' },
    head: { ref: 'deps/sync-dev-versions-test', sha: request.head_sha },
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
  };
  const thread = {
    id: request.thread_id, isResolved: false, isOutdated: false,
    comments: { pageInfo: { hasNextPage: false }, nodes: [
      { fullDatabaseId: '4294967297', author: { login: 'chatgpt-codex-connector[bot]' }, body: 'Please fix' },
    ] },
  };
  const comments = [];
  const tasks = [];
  let taskPosts = 0;
  let posts = 0;
  let merges = 0;
  let resolutions = 0;
  const github = {
    paginate: async () => tasks,
    rest: {
      pulls: {
        get: async () => ({ data: pr }),
        merge: async () => { merges++; },
        createReplyForReviewComment: async ({ body, comment_id }) => {
          assert.equal(comment_id, thread.comments.nodes[0].fullDatabaseId);
          posts++;
          const comment = { id: posts, body, created_at: '2026-09-24T22:00:00Z',
            html_url: `https://github.com/stranske/Ready/pull/592#discussion_r${posts}`,
            user: { login: 'stranske' } };
          comments.push(comment);
          return { data: comment };
        },
      },
      users: { getAuthenticated: async () => ({ data: { login: 'stranske' } }) },
      issues: {
        listComments: async () => { throw new Error('must inspect the original thread'); },
        createComment: async ({ body }) => {
          taskPosts++;
          const task = { id: taskPosts, body, created_at: '2026-09-24T22:02:00Z',
            html_url: `https://github.com/stranske/Ready/pull/592#issuecomment-${taskPosts}`,
            user: { login: 'stranske' } };
          tasks.push(task);
          return { data: task };
        },
      },
    },
    graphql: async (query) => {
      if (/\bmutation\b/.test(query)) resolutions++;
      return { repository: { pullRequest: {
        reviewThreads: { pageInfo: { hasNextPage: false }, nodes: [{
          ...thread, comments: { ...thread.comments, nodes: [
            ...thread.comments.nodes,
            ...comments.map((comment) => ({
              fullDatabaseId: String(comment.id), body: comment.body, author: comment.user,
              createdAt: comment.created_at, url: comment.html_url,
            })),
          ] },
        }] },
      } } };
    },
  };
  const args = { context: { eventName: 'repository_dispatch', ref: 'refs/heads/main',
    payload: { action: 'maint71-review-reassessment' }, actor: 'stranske' },
    withRetry: (fn) => fn(github), rawRequest: JSON.stringify(request),
    registeredRepos: [request.repository],
    policyPath: path.join(__dirname, '..', '..', '..', 'config', 'consumer_sync_review_policy.json') };
  const first = await runReviewReassessment(args);
  assert.equal(first.status, 'review_blocked_reassessment_requested');
  assert.equal(first.request_url, comments[0].html_url);
  assert.match(comments[0].body, /@codex please reassess this specific finding/);
  assert.match(comments[0].body, /PRRT_test/);
  assert.match(comments[0].body,
    new RegExp(`<!-- sync-review-accepted:${request.head_sha} -->`));
  const second = await runReviewReassessment(args);
  assert.equal(second.status, 'review_blocked_reassessment_reused');
  assert.equal(second.writer, 'stranske');
  assert.equal(posts, 1);
  assert.equal(taskPosts, 0, 'default reassessment cannot dispatch a top-level task');
  const reordered = Object.fromEntries(Object.entries(request).reverse());
  const reorderedRetry = await runReviewReassessment({
    ...args, rawRequest: JSON.stringify(reordered),
  });
  assert.equal(reorderedRetry.status, 'review_blocked_reassessment_reused');
  assert.equal(posts, 1, 'field ordering must not bypass idempotency');
  const originalGraphql = github.graphql;
  let raceReads = 0;
  github.graphql = async (query) => {
    const result = await originalGraphql(query);
    if (++raceReads === 1) {
      result.repository.pullRequest.reviewThreads.nodes[0].comments.nodes =
        [...thread.comments.nodes];
    }
    return result;
  };
  const racedRetry = await runReviewReassessment(args);
  assert.equal(racedRetry.status, 'review_blocked_reassessment_reused');
  assert.equal(posts, 1, 'a request appearing on the second read must suppress POST');
  github.graphql = originalGraphql;
  for (const branch of ['sync/workflows-candidate', 'sync/workflows-delivery']) {
    pr.head.ref = branch;
    comments.length = 0;
    const postsBeforeBranch = posts;
    const workflowSync = await runReviewReassessment(args);
    assert.equal(workflowSync.status, 'review_blocked_reassessment_requested');
    assert.equal(posts, postsBeforeBranch + 1);
    assert.equal(comments.length, 1);
    assert.match(comments[0].body, /@codex please reassess this specific finding/);
    assert.equal(merges, 0);
    assert.equal(resolutions, 0);
  }
  pr.head.ref = 'sync/workflows-untrusted';
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.head.ref = 'deps/sync-dev-versions-test';
  pr.head.sha = 'c'.repeat(40);
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.head.sha = request.head_sha;
  pr.body = `<!-- sync-pr-delivery-record:v1 ${JSON.stringify({
    ...record, plan_id: 'other-plan',
  })} -->`;
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.body = `<!-- sync-pr-delivery-record:v1 ${JSON.stringify({
    ...record, lease_expires_at: '2000-01-01T00:00:00Z',
  })} -->`;
  await assert.rejects(runReviewReassessment(args), /delivery changed or lease is invalid/);
  pr.body = `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`;
  await assert.rejects(runReviewReassessment({
    ...args,
    rawRequest: JSON.stringify({ ...request, thread_id: 'PRRT_missing' }),
  }), /absent or incomplete/);
  thread.comments.nodes[0].author.login = 'coderabbitai[bot]';
  await assert.rejects(runReviewReassessment(args), /origin does not match/);
  thread.comments.nodes[0].author.login = 'chatgpt-codex-connector[bot]';
  thread.isResolved = true;
  await assert.rejects(runReviewReassessment(args), /absent or incomplete/);
  thread.isResolved = false;
  const originalId = thread.comments.nodes[0].fullDatabaseId;
  delete thread.comments.nodes[0].fullDatabaseId;
  comments.length = 0;
  await assert.rejects(runReviewReassessment(args), /verified original comment ID/);
  thread.comments.nodes[0].fullDatabaseId = '9007199254740993';
  await runReviewReassessment(args);
  assert.match(comments[0].body, /No unrelated edits/);
  thread.comments.nodes[0].fullDatabaseId = originalId;
  comments[0].user.login = 'untrusted';
  await runReviewReassessment(args);
  assert.equal(posts, 5, 'an untrusted marker is not a prior request');
  const dispositionArgs = { ...args,
    rawRequest: JSON.stringify({ ...request, request_stage: 'disposition' }) };
  await assert.rejects(runReviewReassessment(dispositionArgs), /completed originating review/);
  const completed = { fullDatabaseId: '9000000001',
    author: { login: 'chatgpt-codex-connector' },
    commit: { oid: request.head_sha }, createdAt: '2026-09-24T22:01:00Z',
    body: "Codex Review: Didn't find any major issues.",
    url: 'https://github.com/stranske/Ready/pull/592#discussion_r9000000001' };
  thread.comments.nodes.push(completed);
  completed.commit.oid = 'c'.repeat(40);
  await assert.rejects(runReviewReassessment(dispositionArgs), /completed originating review/);
  completed.commit.oid = request.head_sha;
  completed.author.login = 'coderabbitai';
  await assert.rejects(runReviewReassessment(dispositionArgs), /completed originating review/);
  completed.author.login = 'chatgpt-codex-connector';
  let siblingTruncated = true;
  github.graphql = async (query) => {
    const result = await originalGraphql(query);
    const nodes = result.repository.pullRequest.reviewThreads.nodes;
    nodes[0].comments.nodes = nodes[0].comments.nodes.filter((item) =>
      item.fullDatabaseId !== completed.fullDatabaseId);
    nodes.push({ id: 'PRRT_sibling', isResolved: false, isOutdated: false,
      comments: { pageInfo: { hasNextPage: siblingTruncated }, nodes: [completed] } });
    return result;
  };
  await assert.rejects(runReviewReassessment(dispositionArgs), /inventory is incomplete/);
  siblingTruncated = false;
  const disposition = await runReviewReassessment(dispositionArgs);
  assert.equal(disposition.status, 'review_blocked_reassessment_requested');
  assert.match(comments.at(-1).body, /@codex address that feedback/);
  assert.match(comments.at(-1).body, /disposition-only task/);
  assert.match(comments.at(-1).body, /maint71-review-disposition:v1/);
  assert.equal(disposition.task_status, 'disposition_task_requested');
  assert.equal(taskPosts, 1);
  assert.match(tasks[0].body, /^@codex answer this specific finding on exact head/);
  assert.match(tasks[0].body, /maint71-disposition-task:v1 [a-f0-9]{64}/);
  assert.doesNotMatch(tasks[0].body, /review/i, 'cloud task entry must not repeat review-command text');
  assert.match(tasks[0].body, /A top-level answer cannot authorize disposition/);
  assert.ok(tasks[0].body.includes(comments.at(-1).html_url));
  const postsAfterDisposition = posts;
  const reusedTask = await runReviewReassessment(dispositionArgs);
  assert.equal(posts, postsAfterDisposition, 'disposition stage is independently idempotent');
  assert.equal(taskPosts, 1, 'already-posted inline request reuses the task bridge');
  assert.equal(reusedTask.task_status, 'disposition_task_reused');
  tasks[0].user = { login: 'untrusted' };
  await runReviewReassessment(dispositionArgs);
  assert.equal(taskPosts, 2, 'forged marker cannot suppress authenticated task');
  assert.equal(posts, postsAfterDisposition, 'bridge recovery never reposts inline request');
  tasks.push({ ...tasks[1], id: 100 });
  await assert.rejects(runReviewReassessment(dispositionArgs), /Duplicate bound disposition task/);
  tasks.pop();
  const originalPaginate = github.paginate;
  github.paginate = async () => null;
  await assert.rejects(runReviewReassessment(dispositionArgs), /task inventory is incomplete/);
  github.paginate = originalPaginate;
  tasks.length = 0;
  const tasksBeforeRace = taskPosts;
  github.paginate = async () => {
    pr.head.sha = 'e'.repeat(40);
    return [];
  };
  await assert.rejects(runReviewReassessment(dispositionArgs), /delivery changed or lease is invalid/);
  assert.equal(taskPosts, tasksBeforeRace, 'head changed during task inventory must prevent POST');
  pr.head.sha = request.head_sha;
  github.paginate = originalPaginate;
  const siblingGraphql = github.graphql;
  let bridgeReads = 0;
  github.graphql = async (query) => {
    const result = await siblingGraphql(query);
    if (++bridgeReads === 3) {
      const currentThread = result.repository.pullRequest.reviewThreads.nodes[0];
      currentThread.comments.nodes = currentThread.comments.nodes.filter((item) =>
        !String(item.body).includes('maint71-review-disposition:v1'));
    }
    return result;
  };
  await assert.rejects(runReviewReassessment(dispositionArgs), /in-thread disposition request changed/);
  assert.equal(taskPosts, tasksBeforeRace, 'deleted bound request must prevent task POST');
  github.graphql = siblingGraphql;
  const originalCreateTask = github.rest.issues.createComment;
  let uncertainTaskPosts = 0;
  github.rest.issues.createComment = async () => {
    uncertainTaskPosts++;
    throw new Error('connection reset after task write');
  };
  await assert.rejects(runReviewReassessment(dispositionArgs), /task POST uncertain/);
  assert.equal(uncertainTaskPosts, 1, 'ambiguous task POST must not be retried');
  github.rest.issues.createComment = originalCreateTask;
  github.graphql = originalGraphql;
  thread.comments.nodes.pop();
  comments.length = 0;
  await runReviewReassessment(args);
  github.paginate = async () => [...tasks, { user: { login: completed.author.login },
    body: `${completed.body}\n\n**Reviewed commit:** \`${request.head_sha.slice(0, 10)}\``,
    created_at: completed.createdAt }];
  github.rest.repos = { getCommit: async () => ({ data: { sha: 'c'.repeat(40) } }) };
  await assert.rejects(runReviewReassessment(dispositionArgs), /completed originating review/);
  github.rest.repos.getCommit = async () => ({ data: { sha: request.head_sha } });
  const topLevel = await runReviewReassessment(dispositionArgs);
  assert.equal(topLevel.status, 'review_blocked_reassessment_requested');
  github.paginate = async () => [];
  comments.length = 0;
  github.rest.pulls.createReplyForReviewComment = async () => {
    posts++;
    throw new Error('connection reset after write');
  };
  await assert.rejects(runReviewReassessment(args), /POST uncertain; inspect exact marker/);
  await assert.rejects(runReviewReassessment({ ...args,
    context: { ...args.context, ref: 'refs/heads/untrusted' } }), /trusted main-branch/);
  assert.equal(merges, 0, 'request-only reassessment must never merge');
  assert.equal(resolutions, 0, 'request-only reassessment must never resolve a thread');
});

test('exact-head reviewer request is durable, trusted, and idempotent', async () => {
  const headSha = 'd'.repeat(40);
  const record = {
    schema: 'sync-pr-delivery-record/v1',
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: `sha256:${'a'.repeat(64)}`, generation: 'gen-1',
    repository: 'stranske/Ready', desired_tree_hash: 'tree',
    source_commit: 'c'.repeat(40), head_observed_sha: headSha,
    head_observed_at: '2026-09-24T00:00:00Z',
    lease_expires_at: '2099-01-01T00:00:00Z', delivery_state: 'staging',
  };
  const pr = { number: 10, head: { sha: headSha } };
  const comments = [];
  let posts = 0;
  const github = { rest: {
    users: { getAuthenticated: async () => ({ data: { login: 'stranske' } }) },
    pulls: { get: async () => ({ data: {
      state: 'open', draft: false, auto_merge: null, head: { sha: headSha },
      body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
    } }) },
    issues: {
      listComments: async () => ({ data: comments }),
      createComment: async ({ body }) => {
        posts++;
        const comment = { id: posts, body, created_at: '2026-09-24T01:00:00Z',
          user: { login: 'stranske' } };
        comments.push(comment);
        return { data: comment };
      },
    },
  } };
  const args = { owner: 'stranske', repo: 'Ready', pr, record,
    reviewerProfiles: [{ id: 'codex', request_comment: '@codex review' }],
    trustedActors: ['stranske'], withRetry: (fn) => fn(github) };
  const first = await ensureExactHeadReviewRequest(args);
  assert.equal(first.reused, false);
  assert.equal(first.requestedAt, '2026-09-24T01:00:00Z');
  assert.equal(first.draft, false);
  assert.equal(first.autoMerge, false);
  assert.match(comments[0].body, /@codex review/);
  assert.match(comments[0].body, new RegExp(headSha));
  const retry = await ensureExactHeadReviewRequest(args);
  assert.equal(retry.reused, true);
  assert.equal(retry.id, first.id);
  assert.equal(posts, 1);
  let readinessReads = 0;
  github.rest.pulls.get = async () => ({ data: {
    state: 'open', draft: ++readinessReads > 1,
    auto_merge: readinessReads > 1 ? { enabled_at: '2026-09-24T01:00:00Z' } : null,
    head: { sha: headSha },
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
  } });
  const unready = await ensureExactHeadReviewRequest({ ...args, allowUnready: true });
  assert.equal(readinessReads, 2, 'readiness must be rechecked after comment pagination');
  assert.equal(unready.draft, true);
  assert.equal(unready.autoMerge, true);
  readinessReads = 0;
  github.rest.pulls.get = async () => ({ data: {
    state: 'open', draft: false, auto_merge: null,
    head: { sha: ++readinessReads > 1 ? 'rotated-head' : headSha },
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
  } });
  await assert.rejects(ensureExactHeadReviewRequest({ ...args, allowUnready: true }),
    /changed before exact-head/);
  github.rest.pulls.get = async () => ({ data: {
    state: 'open', draft: false, auto_merge: null, head: { sha: headSha },
    body: `<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->`,
  } });
  comments[0].user.login = 'untrusted';
  await ensureExactHeadReviewRequest(args);
  assert.equal(posts, 2, 'a forged marker must not authorize review settlement');
  comments[1].body = comments[1].body.replace('@codex review', 'review not requested');
  await ensureExactHeadReviewRequest(args);
  assert.equal(posts, 3, 'a marker without the configured request command must not count');
  github.rest.issues.listComments = async () => ({ data: null });
  await assert.rejects(ensureExactHeadReviewRequest(args), /Incomplete review-request comments/);
  github.rest.issues.listComments = async () => ({ data: comments });
  pr.head.sha = 'e'.repeat(40);
  await assert.rejects(ensureExactHeadReviewRequest(args), /changed before exact-head/);
});

test('review-thread evidence fails closed on missing, partial, or paginated responses', () => {
  const complete = {
    pageInfo: { hasNextPage: false },
    nodes: [{ isResolved: true, isOutdated: false }],
  };
  assert.equal(hasCompleteReviewThreadEvidence(complete), true);
  assert.equal(hasCompleteReviewThreadEvidence(null), false);
  assert.equal(hasCompleteReviewThreadEvidence({ ...complete, nodes: null }), false);
  assert.equal(hasCompleteReviewThreadEvidence({ ...complete, pageInfo: null }), false);
  assert.equal(hasCompleteReviewThreadEvidence({ ...complete, pageInfo: { hasNextPage: true } }), false);
  assert.equal(hasCompleteReviewThreadEvidence({ ...complete, nodes: [{}] }), false);
});

test('review GraphQL reads rotate separately while mutations remain owner-pinned', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'maint71_merge_sync_prs.js'), 'utf8');
  assert.match(source, /const withRetry = \(fn, options = \{\}\) => retryHelpers\.withRetry/);
  assert.match(source, /task: 'maint71-review-thread-read'/);
  assert.match(source, /preferredSource: 'SERVICE_BOT_PAT'/);
  assert.match(source, /rateResource: 'graphql'/);
  assert.match(source, /const data = await withReviewReadRetry\(\(client\) => client\.graphql\(/);
  assert.match(source, /withRetry: withReviewReadRetry,/);
  assert.match(source, /if \(reviewerEvidence\.truncated\) \{/);
  assert.match(source, /reason: 'reviewer_evidence_incomplete'/);
  assert.doesNotMatch(source, /await github\.graphql\(/);
  assert.match(source, /reason: 'review_thread_query_incomplete'/);
  assert.match(source, /sha: pr\.head\.sha/);
});

async function reportSelection(t, { syncHash, withRecord }) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'maint71-selection-'));
  t.after(() => fs.rmSync(tempDir, { recursive: true, force: true }));
  const reportPath = path.join(tempDir, 'report.json');
  const repository = 'stranske/Travel-Plan-Permission';
  const headSha = 'd'.repeat(40);
  const sourceCommit = 'c'.repeat(40);
  const observedAt = new Date().toISOString();
  const metadata = {
    schema: 'workflows-consumer-sync-pr/v1', consumer_repo: repository,
    plan_id: `sha256:${'a'.repeat(64)}`, plan_scope: 'full',
    source_commit: sourceCommit, source_sha: sourceCommit,
    template_hash: 'candidate-generation', sync_phase: 'canary',
  };
  const record = {
    schema: 'sync-pr-delivery-record/v1',
    durable_issue_url: 'https://github.com/stranske/Workflows/issues/1836',
    plan_id: metadata.plan_id, generation: 'record-generation', repository,
    desired_tree_hash: 'tree-abc', source_commit: sourceCommit,
    head_observed_sha: headSha, head_observed_at: observedAt,
    lease_expires_at: '2099-08-14T00:00:00Z', predecessor_prs: [], successor_prs: [],
  };
  const candidate = {
    number: 1480, title: 'chore: sync workflow templates',
    body: `<!-- workflows-consumer-sync:v1 ${JSON.stringify(metadata)} -->` +
      (withRecord ? `\n<!-- sync-pr-delivery-record:v1 ${JSON.stringify(record)} -->` : ''),
    created_at: observedAt, updated_at: observedAt, state: 'open',
    base: { ref: 'main' }, head: { ref: 'sync/workflows-candidate', sha: headSha },
    user: { login: 'stranske' },
  };
  // Expose read methods only: an unexpected mutation fails the test.
  const github = {
    paginate: async (_method, params) => params.state === 'open' ? [candidate] : [],
    rest: {
      pulls: { list: async () => ({ data: [candidate] }), get: async () => ({ data: candidate }) },
      git: { getCommit: async () => ({ data: { tree: { sha: 'tree-abc' } } }) },
    },
  };
  const logs = [];
  const failures = [];
  const warnings = [];
  t.mock.method(console, 'log', (...args) => logs.push(args.join(' ')));
  const retryHelpers = require('../github-api-with-retry.js');
  t.mock.method(retryHelpers, 'createTokenAwareRetry', async () => null);
  const core = {
    notice: () => {}, warning: (message) => warnings.push(message),
    setFailed: (message) => failures.push(message),
    summary: { addRaw: () => ({ write: async () => {} }) },
  };
  const env = {
    REGISTERED_REPOS_INPUT: repository, REPOS_INPUT: repository,
    CLEANUP_BRANCHES_INPUT: 'false', DRY_RUN_INPUT: 'true', AUTO_MERGE_INPUT: 'false',
    ACTIVE_SYNC_HASH_INPUT: syncHash, SYNC_HASH_INPUT: '',
    EXPECTED_PLAN_ID_INPUT: '', EXPECTED_PLAN_SCOPE_INPUT: '',
    EXPECTED_SCOPE_BASE_SHA_INPUT: '', EXPECTED_SOURCE_COMMIT_INPUT: '',
    OWNER_PR_PAT: 'test-owner-token', TRUSTED_SYNC_ACTORS: 'stranske',
    SYNC_PR_MERGE_REPORT_JSON: reportPath,
  };
  const originalEnv = Object.fromEntries(Object.keys(env).map((key) => [key, process.env[key]]));
  const originalCwd = process.cwd();
  try {
    Object.assign(process.env, env);
    process.chdir(tempDir);
    await run({
      github, core,
      context: { eventName: 'workflow_dispatch',
        repo: { owner: 'stranske', repo: 'Workflows' }, payload: {},
        runId: 71, runNumber: 71, workflow: 'Maint 71',
        ref: 'refs/heads/main', sha: sourceCommit },
    });
    assert.deepEqual(failures, []);
    assert.deepEqual(warnings, []);
    return { report: JSON.parse(fs.readFileSync(reportPath, 'utf8')), logs: logs.join('\n') };
  } finally {
    process.chdir(originalCwd);
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test('Maint 71 reports no_active_sync_pr when a valid candidate does not match the active hash', async (t) => {
  const { report, logs } = await reportSelection(t, { syncHash: 'expected-hash', withRecord: true });
  assert.equal(report.results.length, 1);
  const row = report.results[0];
  assert.equal(row.status, 'target_missing');
  assert.equal(row.delivery_reason, 'no_active_sync_pr');
  assert.equal(row.expected_branch, 'sync/workflows-expected-hash');
  assert.equal(row.active_sync_hash, 'expected-hash');
  assert.equal(row.open_sync_prs[0].number, 1480);
  assert.match(logs, /no_active_sync_pr \(expected sync\/workflows-expected-hash, active hash 'expected-hash'\)/);
  assert.doesNotMatch(logs, /missing_delivery_record/);
  assert.deepEqual(report.handoff_records, []);
});

test('Maint 71 reports missing_delivery_record for a selected candidate with no record', async (t) => {
  const { report, logs } = await reportSelection(t, { syncHash: '', withRecord: false });
  assert.equal(report.results.length, 1);
  assert.equal(report.results[0].status, 'delivery_contract_blocked');
  assert.equal(report.results[0].pr, 1480);
  assert.equal(report.results[0].delivery_reason, 'missing_delivery_record');
  assert.match(logs, /Delivery contract blocks merge: missing_delivery_record/);
  assert.doesNotMatch(logs, /no_active_sync_pr/);
  assert.deepEqual(report.handoff_records, []);
});

test('Maint 71 empty-hash dispatch still selects a candidate with a valid delivery record', async (t) => {
  const { report, logs } = await reportSelection(t, { syncHash: '', withRecord: true });
  assert.equal(report.results.length, 1);
  assert.equal(report.results[0].status, 'review_window_pending');
  assert.equal(report.results[0].pr, 1480);
  assert.doesNotMatch(JSON.stringify(report), /no_active_sync_pr|missing_delivery_record/);
  assert.doesNotMatch(logs, /no_active_sync_pr|missing_delivery_record/);
});
