'use strict';

const crypto = require('node:crypto');
const { parseStateComment } = require('../../keepalive_state.js');

const buildGithubStub = ({
  pr,
  comments = [],
  labels = [],
  workflowRuns = [],
  workflowJobs = [],
  workflowRun = null,
  annotationsByCheckRunId = {},
  jobLogsByJobId = {},
  failNeedsHumanLabel = false,
  failNeedsAttentionLabel = false,
  failNeedsAttentionRemoval = false,
  failRemoveLabelStatusByName = {},
  failStateCommentWriteAt = 0,
  failWorkflowDispatch = false,
  authorityReceipt = false,
  authorityLedger = false,
  failAuthorityConfirmWrite = false,
} = {}) => {
  const actions = [];
  const currentLabels = new Set(labels);
  let stateCommentWriteCount = 0;
  let remainingConfirmationFailures = failAuthorityConfirmWrite === true
    ? Number.POSITIVE_INFINITY : Number(failAuthorityConfirmWrite) || 0;
  const attention = comments.map((comment) => parseStateComment(comment.body)?.data?.attention)
    .find((candidate) => candidate?.disposition === 'challenge-due' && candidate.generation);
  let authorityBranch = Boolean(attention);
  let authorityContent = null;
  if (attention) {
    const claim = {
      generation: attention.generation,
      boundary_fingerprint: attention.boundary_fingerprint,
      due_at: attention.challenge_due_at,
      expires_at: attention.expires_at,
      head_sha: 'd'.repeat(40),
      nonce: 'a'.repeat(64),
      sweep_run_id: '987654321',
      sweep_run_attempt: '1',
    };
    const receipt = authorityReceipt ? {
      id: 'e'.repeat(64),
      claim_digest: crypto.createHash('sha256').update(JSON.stringify(claim)).digest('hex'),
      owner_attempt: 'octo/workflows:9001:1',
      provider: 'codex',
      head_sha: claim.head_sha,
      consumed_at: new Date().toISOString(),
    } : null;
    authorityContent = Buffer.from(JSON.stringify({
      version: 2, repository: 'octo/workflows', pr_number: 654,
      generation: attention.generation,
      boundary_fingerprint: attention.boundary_fingerprint,
      head_sha: claim.head_sha,
      due_at: attention.challenge_due_at,
      expires_at: attention.expires_at,
      status: receipt ? 'consumed' : 'available',
      receipt, revision: 1,
      consumed_claim: receipt ? claim : null,
    })).toString('base64');
  }
  const stub = {
    actions,
    async request(route, body = {}) {
      const [method, url] = route.split(' ');
      if (method === 'GET' && url === '/repos/octo/workflows') {
        return { data: { default_branch: 'main' } };
      }
      if (method === 'GET' && url.endsWith('/pulls/654')) {
        return { data: { state: 'open', head: { sha: 'd'.repeat(40) },
          labels: [...currentLabels].map((name) => ({ name })) } };
      }
      if (method === 'GET' && url.endsWith('/git/ref/heads/main')) {
        return { data: { object: { sha: '1'.repeat(40) } } };
      }
      if (method === 'GET' && url.endsWith('/git/ref/heads/keepalive-authority-state')) {
        if (!authorityBranch) throw Object.assign(new Error('not found'), { status: 404 });
        return { data: { object: { sha: '2'.repeat(40) } } };
      }
      if (method === 'POST' && url.endsWith('/git/refs')) {
        actions.push({ type: 'authority-ledger-write', url });
        authorityBranch = true;
        return { data: {} };
      }
      if (url.includes('/contents/.github/keepalive-authority/')) {
        if (method === 'GET') {
          if (!authorityContent) throw Object.assign(new Error('not found'), { status: 404 });
          return { data: {
            sha: crypto.createHash('sha1').update(authorityContent).digest('hex'),
            encoding: 'base64', content: authorityContent,
          } };
        }
        if (method === 'PUT') {
          actions.push({ type: 'authority-ledger-write', url });
          if (remainingConfirmationFailures > 0 &&
              JSON.parse(Buffer.from(body.content, 'base64').toString('utf8')).status === 'confirmed') {
            remainingConfirmationFailures--;
            throw Object.assign(new Error('simulated confirmation conflict'), { status: 409 });
          }
          const priorSha = authorityContent
            ? crypto.createHash('sha1').update(authorityContent).digest('hex')
            : undefined;
          if (body.sha !== priorSha) throw Object.assign(new Error('conflict'), { status: 409 });
          authorityContent = body.content;
          return { data: {} };
        }
      }
      throw new Error(`Unexpected authority request: ${route}`);
    },
    rest: {
      pulls: {
        async get() {
          return { data: { state: 'open', id: 100000 + (pr?.number || 0), node_id: `PR_fixture_${pr?.number || 0}`, ...pr, head: pr?.head || { sha: 'fixture-head' } } };
        },
        async update({ body }) {
          pr.body = body;
          actions.push({ type: 'pr-update', body });
          return { data: pr };
        },
      },
      actions: {
        async listWorkflowRuns(args = {}) {
          // Ordinary legacy fixtures have a complete empty native correction
          // inventory; their unrelated Gate workflowRuns are not correction runs.
          if (args.workflow_id === 'agents-verify-to-new-pr.yml' && args.event === 'workflow_dispatch') {
            return { data: { total_count: 0, workflow_runs: [] } };
          }
          return { data: { workflow_runs: workflowRuns } };
        },
        async getWorkflowRun() {
          return { data: workflowRun || {} };
        },
        async listJobsForWorkflowRun() {
          return { data: { jobs: workflowJobs } };
        },
        async downloadJobLogsForWorkflowRun({ job_id: jobId }) {
          const data = jobLogsByJobId[jobId] ?? '';
          const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data);
          return { data: buffer };
        },
        async createWorkflowDispatch(payload) {
          if (failWorkflowDispatch) {
            actions.push({ type: 'workflow-dispatch-failed', ...payload });
            throw new Error('simulated workflow dispatch failure');
          }
          actions.push({ type: 'workflow-dispatch', ...payload });
          return { data: {} };
        },
      },
      checks: {
        async listAnnotations({ check_run_id: checkRunId }) {
          return { data: annotationsByCheckRunId[checkRunId] || [] };
        },
      },
      issues: {
        async get() {
          return { data: { body: pr.body || '' } };
        },
        async listComments() {
          return {
            data: comments.map((comment) => ({
              user: { login: 'agents-workflows-bot[bot]', type: 'Bot' },
              ...comment,
            })),
          };
        },
        async listLabelsOnIssue() {
          return { data: [...currentLabels].map((name) => ({ name })) };
        },
        async updateComment({ body, comment_id: commentId }) {
          stateCommentWriteCount += 1;
          if (failStateCommentWriteAt === stateCommentWriteCount) {
            actions.push({ type: 'update-failed', body, commentId });
            throw new Error('simulated state comment failure');
          }
          actions.push({ type: 'update', body, commentId });
          return { data: { id: commentId } };
        },
        async createComment({ body }) {
          stateCommentWriteCount += 1;
          if (failStateCommentWriteAt === stateCommentWriteCount) {
            actions.push({ type: 'create-failed', body });
            throw new Error('simulated state comment failure');
          }
          actions.push({ type: 'create', body });
          return { data: { id: 101, html_url: 'https://example.com/101' } };
        },
        async addLabels({ labels }) {
          if (failNeedsHumanLabel && labels.includes('needs-human')) {
            actions.push({ type: 'label-failed', labels });
            throw new Error('simulated needs-human label failure');
          }
          if (failNeedsAttentionLabel && labels.includes('agent:needs-attention')) {
            actions.push({ type: 'label-failed', labels });
            throw new Error('simulated attention label failure');
          }
          actions.push({ type: 'label', labels });
          labels.forEach((name) => currentLabels.add(name));
          return { data: {} };
        },
        async removeLabel({ name }) {
          if (failNeedsAttentionRemoval && name === 'agent:needs-attention') {
            actions.push({ type: 'remove-label-failed', name });
            throw new Error('simulated attention label removal failure');
          }
          if (Object.prototype.hasOwnProperty.call(failRemoveLabelStatusByName, name)) {
            const status = failRemoveLabelStatusByName[name];
            actions.push({ type: 'remove-label-failed', name, status });
            throw Object.assign(new Error(`simulated removeLabel ${status}`), { status });
          }
          actions.push({ type: 'remove-label', name });
          currentLabels.delete(name);
          return { data: {} };
        },
      },
    },
    async paginate(fn, params) {
      const response = await fn(params);
      return Array.isArray(response?.data) ? response.data : [];
    },
  };
  if (!attention && !authorityLedger) delete stub.request;
  return stub;
};

const buildContext = (prNumber = 101, runId = 9001, overrides = {}) => ({
  eventName: overrides.eventName ?? 'pull_request',
  repo: { owner: 'octo', repo: 'workflows' },
  payload: overrides.payload ?? { pull_request: { number: prNumber } },
  runId,
  runAttempt: 1,
});

const buildCore = () => ({
  info() {},
  warning() {},
  setOutput() {},
});

module.exports = { buildGithubStub, buildContext, buildCore };
