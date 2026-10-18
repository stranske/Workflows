'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { verifierPlanSourceFingerprint } = require('../verifier_plan_fingerprint.js');

function pull(body, extra = {}) {
  return {
    number: 711,
    title: 'Staged verifier pipeline',
    body,
    labels: [{ name: 'verify:compare' }],
    head: { ref: 'feature/staged-verifier' },
    ...extra,
  };
}

const localBody = (acceptance, status = 'green') => `
<!-- workflow-source: local_request -->
<!-- workflow-source-ref: owner-request:closer-evidence-pipeline-2026-10-17 -->

## Scope
Prepare complete, current evidence before selecting lifecycle work.

## Tasks
- [ ] Collect retained evidence at admission.

## Acceptance Criteria
- [ ] ${acceptance}

## Automated Status Summary
Latest status: ${status}
`;

function githubMock(issues = []) {
  return {
    graphql: async () => ({
      repository: {
        pullRequest: {
          repository: { nameWithOwner: 'stranske/Orchestrator' },
          closingIssuesReferences: {
            totalCount: issues.length,
            pageInfo: { hasNextPage: false },
            nodes: issues,
          },
        },
      },
    }),
    rest: { issues: { get: async () => { throw new Error('unexpected source issue lookup'); } } },
  };
}

test('plan fingerprint ignores unrelated volatile PR body text', async () => {
  const first = await verifierPlanSourceFingerprint({
    github: githubMock(), owner: 'stranske', repo: 'Orchestrator', pull: pull(localBody('All criteria are covered.')),
  });
  const statusOnly = await verifierPlanSourceFingerprint({
    github: githubMock(), owner: 'stranske', repo: 'Orchestrator', pull: pull(localBody('All criteria are covered.', 'checks refreshed')),
  });
  assert.equal(first, statusOnly);
});

test('criteria-only change produces a different plan fingerprint', async () => {
  const first = await verifierPlanSourceFingerprint({
    github: githubMock(), owner: 'stranske', repo: 'Orchestrator', pull: pull(localBody('All criteria are covered.')),
  });
  const changed = await verifierPlanSourceFingerprint({
    github: githubMock(), owner: 'stranske', repo: 'Orchestrator', pull: pull(localBody('All criteria are covered with a current-head receipt.')),
  });
  assert.notEqual(first, changed);
  assert.equal(changed, await verifierPlanSourceFingerprint({
    github: githubMock(), owner: 'stranske', repo: 'Orchestrator', pull: pull(localBody('All criteria are covered with a current-head receipt.')),
  }));
});

test('linked source issue criteria and lineage participate in the fingerprint', async () => {
  const issue = (body) => ({
    number: 675, title: 'Evidence contract', body,
    repository: { nameWithOwner: 'stranske/Orchestrator' },
  });
  const basePull = pull('<!-- meta:issue:675 -->\n\n## Tasks\n- [ ] Follow source requirements.\n\n## Acceptance Criteria\n- [ ] Source criteria verified.');
  const first = await verifierPlanSourceFingerprint({
    github: githubMock([issue('## Tasks\n- [ ] Keep the original task.\n\n## Acceptance Criteria\n- [ ] Verify current evidence.')]),
    owner: 'stranske', repo: 'Orchestrator', pull: basePull,
  });
  const changedSource = await verifierPlanSourceFingerprint({
    github: githubMock([issue('## Tasks\n- [ ] Keep the original task.\n\n## Acceptance Criteria\n- [ ] Verify current evidence and provenance.')]),
    owner: 'stranske', repo: 'Orchestrator', pull: basePull,
  });
  assert.notEqual(first, changedSource);
});

test('a known non-closing source issue is included and validated', async () => {
  const pullBody = '## Tasks\n- [ ] Follow source issue.\n\n## Acceptance Criteria\n- [ ] Verify the source requirements.';
  const github = githubMock();
  github.rest.issues.get = async () => ({
    data: { number: 675, title: 'Source requirements', body: '## Tasks\n- [ ] Build it.\n\n## Acceptance Criteria\n- [ ] Prove it.' },
  });
  const first = await verifierPlanSourceFingerprint({
    github, owner: 'stranske', repo: 'Orchestrator',
    pull: pull(pullBody, { body: `${pullBody}\n\n<!-- meta:issue:675 -->` }),
  });
  github.rest.issues.get = async () => ({
    data: { number: 675, title: 'Source requirements', body: '## Tasks\n- [ ] Build it.\n\n## Acceptance Criteria\n- [ ] Prove current-head behavior.' },
  });
  const changed = await verifierPlanSourceFingerprint({
    github, owner: 'stranske', repo: 'Orchestrator',
    pull: pull(pullBody, { body: `${pullBody}\n\n<!-- meta:issue:675 -->` }),
  });
  assert.notEqual(first, changed);
});

test('incomplete linked-issue pagination fails closed instead of hashing a partial source set', async () => {
  const github = githubMock();
  github.graphql = async () => ({
    repository: {
      pullRequest: {
        repository: { nameWithOwner: 'stranske/Orchestrator' },
        closingIssuesReferences: {
          totalCount: 21,
          pageInfo: { hasNextPage: true },
          nodes: Array.from({ length: 20 }, (_, index) => ({
            number: index + 1,
            title: `Issue ${index + 1}`,
            body: '## Tasks\n- [ ] Work\n\n## Acceptance Criteria\n- [ ] Verify',
            repository: { nameWithOwner: 'stranske/Orchestrator' },
          })),
        },
      },
    },
  });

  await assert.rejects(
    verifierPlanSourceFingerprint({
      github,
      owner: 'stranske',
      repo: 'Orchestrator',
      pull: pull('## Tasks\n- [ ] Work\n\n## Acceptance Criteria\n- [ ] Verify'),
    }),
    /cannot prove complete linked-issue coverage/,
  );
});
