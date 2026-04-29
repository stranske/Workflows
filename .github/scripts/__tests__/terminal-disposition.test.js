const test = require('node:test');
const assert = require('node:assert/strict');

const {
  normalizeTerminalDisposition,
  normalizeVerifierFollowupLedger,
  normalizeVerifierFollowupPolicy,
  normalizeLedgerDisposition,
  normalizeCliVersion,
  summarizeTerminalDispositionSources,
  formatTerminalDispositionMarkdown,
  sourceKey,
} = require('../terminal_disposition.js');

test('normalizes terminal disposition records with stable source keys', () => {
  const record = normalizeTerminalDisposition({
    sourceType: 'Source Issue',
    sourceId: 42,
    prNumber: '101',
    issueNumber: '42',
    disposition: 'follow-up-created',
    followupIssueNumber: 105,
    reason: '  Dispatch completed  ',
    dispatchOutcome: ' success ',
    artifactName: 'verifier-terminal-disposition-123',
    artifactFamily: 'verifier-terminal-disposition',
    llmModel: 'gpt-5.3-codex',
    modelSelectionReason: 'default',
    llmCliVersion: 'Codex CLI v0.125.0',
    verifierMode: 'checkbox',
    needsHuman: false,
    timestamp: '2026-04-25T00:00:00Z',
  });

  assert.equal(record.schema, 'workflows-terminal-disposition/v1');
  assert.equal(record.metric_type, 'verifier_terminal_disposition');
  assert.equal(record.source_type, 'source-issue');
  assert.equal(record.source_id, '42');
  assert.equal(record.source_key, 'source-issue:42');
  assert.equal(record.pr_number, 101);
  assert.equal(record.issue_number, 42);
  assert.equal(record.followup_issue_number, 105);
  assert.equal(record.reason, 'Dispatch completed');
  assert.equal(record.dispatch_outcome, 'success');
  assert.equal(record.artifact_name, 'verifier-terminal-disposition-123');
  assert.equal(record.artifact_family, 'verifier-terminal-disposition');
  assert.equal(record.llm_model, 'gpt-5.3-codex');
  assert.equal(record.model_selection_reason, 'default');
  assert.equal(record.llm_cli_version, 'codex-cli 0.125.0');
  assert.equal(record.verifier_mode, 'checkbox');
  assert.equal(record.needs_human, false);
});

test('normalizes Codex CLI version strings', () => {
  assert.equal(normalizeCliVersion('Codex CLI v0.125.0\n'), 'codex-cli 0.125.0');
  assert.equal(normalizeCliVersion('@openai/codex@0.126.1'), 'codex-cli 0.126.1');
  assert.equal(normalizeCliVersion('Codex CLI v0.127.0-BETA'), 'codex-cli 0.127.0-beta');
  assert.equal(normalizeCliVersion('custom tool 1.0.0'), 'custom tool 1.0.0');
});

test('normalizes boolean-like optional fields without stringifying them', () => {
  const terminal = normalizeTerminalDisposition({
    sourceId: 42,
    needsHuman: 'false',
  });
  const ledger = normalizeVerifierFollowupLedger({
    prNumber: 101,
    verificationRunId: 249,
    needsHuman: 'true',
    followupPolicy: {
      depthLimitExceeded: 'false',
    },
  });

  assert.equal(terminal.needs_human, false);
  assert.equal(ledger.needs_human, true);
  assert.equal(ledger.followup_policy.depth_limit_exceeded, false);
});

test('sourceKey falls back to unknown for blank values', () => {
  assert.equal(sourceKey('', ''), 'unknown:unknown');
});

test('normalizes verifier follow-up ledger records with stable PR/run key', () => {
  const record = normalizeVerifierFollowupLedger({
    prNumber: '101',
    verificationRunId: '24950000001',
    runAttempt: '2',
    verdict: 'CONCERNS',
    terminalState: 'follow-up-created',
    concernsHash: 'abc123',
    followupIssueNumber: '105',
    followupIssueUrl: 'https://github.example/issues/105',
    sourceIssueNumbers: ['42', '42', 43],
    chainDepth: '1',
    workflow: 'Reusable Agents Verifier',
    actor: 'github-actions[bot]',
    terminalDispositionArtifact: 'verifier-terminal-disposition-24950000001',
    dispatchOutcome: 'success',
    needsHuman: false,
    followupPolicy: {
      action: 'create-follow-up',
      trigger: 'verifier-concerns',
      reason: 'Verifier concerns require another implementation pass.',
      maxChainDepth: '2',
      nextChainDepth: '2',
      depthLimitExceeded: false,
    },
    timestamp: '2026-04-25T00:00:00Z',
  });

  assert.equal(record.schema, 'workflows-verifier-followup-ledger/v1');
  assert.equal(record.metric_type, 'verifier_followup_ledger');
  assert.equal(record.state_key, 'pr:101:run:24950000001');
  assert.equal(record.pr_number, 101);
  assert.equal(record.verification_run_id, '24950000001');
  assert.equal(record.verification_run_attempt, 2);
  assert.equal(record.verdict, 'CONCERNS');
  assert.equal(record.disposition, 'follow-up');
  assert.equal(record.concerns_hash, 'abc123');
  assert.equal(record.followup_issue_number, 105);
  assert.deepEqual(record.source_issue_numbers, [42, 43]);
  assert.equal(record.chain_depth, 1);
  assert.deepEqual(record.followup_policy, {
    schema: 'workflows-verifier-followup-policy/v1',
    action: 'create-follow-up',
    reason: 'Verifier concerns require another implementation pass.',
    trigger: 'verifier-concerns',
    chain_depth: 1,
    max_chain_depth: 2,
    next_chain_depth: 2,
    depth_limit_exceeded: false,
  });
  assert.equal(record.terminal_disposition_artifact, 'verifier-terminal-disposition-24950000001');
  assert.equal(record.needs_human, false);
});

test('normalizes verifier follow-up policy records from flat workflow fields', () => {
  assert.deepEqual(
    normalizeVerifierFollowupPolicy({
      terminalState: 'needs-human-depth-limit',
      needsHuman: 'true',
      chainDepth: '2',
      maxChainDepth: '2',
      followupPolicyReason: 'Chain depth limit was reached.',
      followupPolicyTrigger: 'chain-depth-limit',
      depthLimitExceeded: 'true',
    }),
    {
      schema: 'workflows-verifier-followup-policy/v1',
      action: 'needs-human',
      reason: 'Chain depth limit was reached.',
      trigger: 'chain-depth-limit',
      chain_depth: 2,
      max_chain_depth: 2,
      depth_limit_exceeded: true,
    }
  );
});

test('maps verifier terminal states to ledger disposition contract values', () => {
  assert.equal(normalizeLedgerDisposition({ terminalState: 'verified-pass' }), 'merge');
  assert.equal(normalizeLedgerDisposition({ terminalState: 'follow-up-created' }), 'follow-up');
  assert.equal(normalizeLedgerDisposition({ terminalState: 'needs-human-depth-limit' }), 'needs-human');
  assert.equal(normalizeLedgerDisposition({ disposition: 'accept_risk' }), 'accept-risk');
  assert.equal(normalizeLedgerDisposition({ verdict: 'fail' }), 'needs-human');
});

test('summarizes terminal dispositions by source', () => {
  const summary = summarizeTerminalDispositionSources([
    { source_type: 'source-issue', source_id: 7, disposition: 'follow-up-created', pr_number: 11 },
    { source_type: 'source-issue', source_id: 7, disposition: 'needs-human', pr_number: 12 },
    { source_type: 'review-thread', source_id: 12, disposition: 'unresolved-bot-comments', pr_number: 12 },
  ]);

  assert.deepEqual(summary, [
    {
      source_type: 'review-thread',
      source_id: '12',
      total: 1,
      dispositions: { 'unresolved-bot-comments': 1 },
      pr_numbers: [12],
      issue_numbers: [],
    },
    {
      source_type: 'source-issue',
      source_id: '7',
      total: 2,
      dispositions: { 'follow-up-created': 1, 'needs-human': 1 },
      pr_numbers: [11, 12],
      issue_numbers: [],
    },
  ]);
});

test('formats terminal disposition summary as markdown', () => {
  const markdown = formatTerminalDispositionMarkdown([
    { source_type: 'source-issue', source_id: 7, disposition: 'follow-up-created', pr_number: 11 },
  ]);

  assert.match(markdown, /Source/);
  assert.match(markdown, /source-issue:7/);
  assert.match(markdown, /follow-up-created \(1\)/);
  assert.match(markdown, /#11/);
});
