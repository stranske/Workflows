'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  SOURCE_TYPES,
  extractIssueNumberFromPull,
  normalizeSourceType,
  parseWorkflowSourceBlock,
  resolvePrSourceContext,
  sourceTypeFromCheckedTemplate,
  sourceTypeFromLabels,
} = require('../source_context.js');

test('normalizeSourceType maps human aliases to canonical origin types', () => {
  assert.equal(normalizeSourceType('GitHub Issue'), SOURCE_TYPES.GITHUB_ISSUE);
  assert.equal(normalizeSourceType('local Codex request'), SOURCE_TYPES.LOCAL_REQUEST);
  assert.equal(normalizeSourceType('workflow run'), SOURCE_TYPES.AUTOMATION_RUN);
  assert.equal(normalizeSourceType('maintenance sync'), SOURCE_TYPES.SYNC_CAMPAIGN);
  assert.equal(normalizeSourceType('dependency update'), SOURCE_TYPES.DEPENDABOT);
  assert.equal(normalizeSourceType('review follow-up'), SOURCE_TYPES.REVIEW_FOLLOWUP);
  assert.equal(normalizeSourceType('direct PR'), SOURCE_TYPES.MANUAL_REMOTE);
  assert.equal(normalizeSourceType(''), SOURCE_TYPES.UNKNOWN);
});

test('extractIssueNumberFromPull keeps existing issue resolution behavior', () => {
  assert.equal(
    extractIssueNumberFromPull({
      body: '<!-- meta:issue:42 --> Run #2615 timed out',
      head: { ref: 'feature' },
      title: 'stuff',
    }),
    42,
  );
  assert.equal(
    extractIssueNumberFromPull({
      body: 'Run #2615 timed out. Relates to #88',
      head: { ref: 'feature' },
      title: 'stuff',
    }),
    88,
  );
  assert.equal(
    extractIssueNumberFromPull({
      body: 'Run #2615 timed out after 45 minutes',
      head: { ref: 'feature' },
      title: 'stuff',
    }),
    null,
  );
});

test('parseWorkflowSourceBlock reads source-context fields from hidden block', () => {
  const block = parseWorkflowSourceBlock(`
<!-- workflow-source:start -->
origin: local_request
source_ref: codex-thread-abc
lifecycle: substantive_delivery
automation: verifier_required
<!-- workflow-source:end -->
`);

  assert.deepEqual(block, {
    origin: 'local_request',
    source_ref: 'codex-thread-abc',
    lifecycle: 'substantive_delivery',
    automation: 'verifier_required',
  });
});

test('sourceTypeFromCheckedTemplate reads direct GitHub PR source choice', () => {
  const body = `
## Workflow Source

Started from:
- [ ] GitHub issue: #
- [x] Direct PR / remote GitHub work
- [ ] Local Codex/user request
`;

  assert.equal(sourceTypeFromCheckedTemplate(body), SOURCE_TYPES.MANUAL_REMOTE);
});

test('sourceTypeFromCheckedTemplate treats human-only PRs as manual remote work', () => {
  const body = `
## Workflow Source

Started from:
- [ ] GitHub issue: #
- [x] Do not automate

Automation intent:
- [x] Human-only unless checks fail
`;

  assert.equal(sourceTypeFromCheckedTemplate(body), SOURCE_TYPES.MANUAL_REMOTE);
});

test('sourceTypeFromLabels accepts workflow source labels', () => {
  const pull = {
    labels: [{ name: 'workflow:source-local-request' }],
  };

  assert.equal(sourceTypeFromLabels(pull), SOURCE_TYPES.LOCAL_REQUEST);
});

test('resolvePrSourceContext prefers source issue when issue metadata exists', () => {
  const context = resolvePrSourceContext({
    body: '<!-- meta:issue:123 -->\n<!-- workflow-source:local_request -->',
    head: { ref: 'codex/feature' },
    title: 'Implement change',
  });

  assert.equal(context.sourceType, SOURCE_TYPES.GITHUB_ISSUE);
  assert.equal(context.issueNumber, 123);
  assert.equal(context.sourceRef, '#123');
  assert.equal(context.isValid, true);
  assert.equal(context.requiresIssue, true);
});

test('resolvePrSourceContext accepts explicit local request without issue', () => {
  const context = resolvePrSourceContext({
    body: '<!-- workflow-source:local_request -->\n<!-- workflow-source-ref:codex-thread-2026-04-26 -->',
    head: { ref: 'codex/source-context' },
    title: 'Add source context',
  });

  assert.equal(context.sourceType, SOURCE_TYPES.LOCAL_REQUEST);
  assert.equal(context.issueNumber, null);
  assert.equal(context.sourceRef, 'codex-thread-2026-04-26');
  assert.equal(context.isValid, true);
  assert.equal(context.requiresIssue, false);
});

test('resolvePrSourceContext infers sync and dependabot sources for maintenance PRs', () => {
  assert.equal(
    resolvePrSourceContext({
      body: '',
      head: { ref: 'sync/workflows-abcdef' },
      title: 'chore: sync template scripts',
    }).sourceType,
    SOURCE_TYPES.SYNC_CAMPAIGN,
  );

  assert.equal(
    resolvePrSourceContext({
      body: '',
      head: { ref: 'dependabot/pip/package-1.2.3' },
      title: 'deps: bump package',
      user: { login: 'dependabot[bot]' },
    }).sourceType,
    SOURCE_TYPES.DEPENDABOT,
  );
});

test('resolvePrSourceContext accepts explicit sync source markers from consumer sync PRs', () => {
  const context = resolvePrSourceContext({
    body: [
      '<!-- workflow-source:sync_campaign -->',
      '<!-- workflow-source-ref:stranske/Travel-Plan-Permission#956 -->',
      '## Sync Summary',
      '',
      '**Source:** stranske/Workflows',
      '**Template hash:** `863a67ed87f7`',
    ].join('\n'),
    head: { ref: 'sync/workflows-863a67ed87f7' },
    title: 'chore: sync workflow templates',
  });

  assert.equal(context.sourceType, SOURCE_TYPES.SYNC_CAMPAIGN);
  assert.equal(context.sourceRef, 'stranske/Travel-Plan-Permission#956');
  assert.equal(context.isValid, true);
  assert.equal(context.requiresIssue, false);
  assert.equal(context.isExplicit, true);
});

test('resolvePrSourceContext accepts direct-pr labels without issue metadata', () => {
  const context = resolvePrSourceContext({
    body: '',
    head: { ref: 'maint/manual-doc-update' },
    title: 'docs: clarify workflow source handling',
    labels: [{ name: 'workflow:source-direct-pr' }],
  });

  assert.equal(context.sourceType, SOURCE_TYPES.MANUAL_REMOTE);
  assert.equal(context.issueNumber, null);
  assert.equal(context.isValid, true);
  assert.equal(context.requiresIssue, false);
});

test('resolvePrSourceContext leaves unrelated PRs unknown', () => {
  const context = resolvePrSourceContext({
    body: 'No source fields here',
    head: { ref: 'feature/no-source' },
    title: 'Change code',
  });

  assert.equal(context.sourceType, SOURCE_TYPES.UNKNOWN);
  assert.equal(context.isValid, false);
});
