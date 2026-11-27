'use strict';

const { syncFindingFingerprint } = require('../../sync_pr_merge_contract');

function findingPacket(disposition = 'unrelated') {
  const binding = { repository: 'stranske/Ready', pr: 21, head_sha: 'a'.repeat(40),
    source_commit: 'b'.repeat(40), plan_id: 'plan-21', delivery_generation: 'generation-3' };
  const thread = { id: 'PRRT_finding', path: 'app/local.py', isResolved: false, isOutdated: false,
    comments: { pageInfo: { hasNextPage: false }, nodes: [{ id: 'PRRC_original',
      body: 'The consumer-only pre-existing optional export fails on an empty list.',
      updatedAt: '2026-10-18T01:00:00Z', author: { login: 'reviewer' },
      url: 'https://github.com/stranske/Ready/pull/21#discussion_r1' }] } };
  const proof = { schema: 'sync-finding-disposition/v1', ...binding,
    thread_id: thread.id, thread_fingerprint: syncFindingFingerprint(thread), disposition,
    rationale: 'The exact delivery does not change this consumer-only export or any of its callers.',
    evidence_urls: ['https://github.com/stranske/Ready/commit/' + 'c'.repeat(40)],
    remediation_owner: 'local-owner', handoff_url: 'https://github.com/stranske/Ready/issues/31',
    expires_at: '2099-01-01T00:00:00Z' };
  const comment = { id: 41, user: { login: 'stranske' },
    html_url: 'https://github.com/stranske/Ready/pull/21#issuecomment-41',
    updated_at: '2026-10-18T02:00:00Z',
    body: `<!-- sync-finding-disposition:v1 ${JSON.stringify(proof)} -->` };
  return { binding, reviewThreads: [thread], activeReviewThreadCount: 1,
    evidenceComplete: true, comments: [comment], handoffs: [{
      html_url: proof.handoff_url, title: 'Repair optional local export', state: 'open',
      assignees: [{ login: proof.remediation_owner }],
    }] };
}

function changeProof(packet, delta) {
  const comment = packet.comments[0];
  const proof = JSON.parse(comment.body.slice('<!-- sync-finding-disposition:v1 '.length, -4));
  comment.body = `<!-- sync-finding-disposition:v1 ${JSON.stringify({ ...proof, ...delta })} -->`;
  return packet;
}

module.exports = { findingPacket, changeProof };
