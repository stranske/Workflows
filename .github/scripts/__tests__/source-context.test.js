'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  SOURCE_TYPES,
  extractIssueNumberFromPull,
  normalizeSourceType,
  parseDependencyRepairPromotionSource,
  parseWorkflowSourceBlock,
  hasNoAutomationWorkflowContext,
  resolvePrSourceContext,
  sourceTypeFromCheckedTemplate,
  sourceTypeFromLabels,
} = require('../source_context.js');

const {
  resolvePrSourceContext: templateResolvePrSourceContext,
} = require('../../../templates/consumer-repo/.github/scripts/source_context.js');

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
  assert.equal(
    extractIssueNumberFromPull({
      body: 'Review follow-up from PR #956',
      head: { ref: 'feature' },
      title: 'stuff',
    }),
    null,
  );
  assert.equal(
    extractIssueNumberFromPull({
      body: 'Mentioned #77 without an issue keyword',
      head: { ref: 'feature' },
      title: 'stuff',
    }),
    null,
  );
});

test('extractIssueNumberFromPull prefers an explicit body link over inferred branch and title issues', () => {
  assert.equal(
    extractIssueNumberFromPull({
      body: 'Related to #222',
      head: { ref: 'codex/issue-111-stale-branch' },
      title: 'Resolve issue #333',
    }),
    222,
  );
});

test('extractIssueNumberFromPull prefers one closing link over secondary body references', () => {
  assert.equal(
    extractIssueNumberFromPull({
      body: 'Related to #111 for context.\nCloses #222',
      head: { ref: 'codex/issue-222-fix' },
      title: 'Resolve issue #222',
    }),
    222,
  );
});

test('extractIssueNumberFromPull rejects ambiguous non-closing body references', () => {
  assert.equal(
    extractIssueNumberFromPull({
      body: 'Related to #111.\nReferences issue #222.',
      head: { ref: 'codex/issue-333-fallback' },
      title: 'Resolve issue #333',
    }),
    null,
  );
});

test('extractIssueNumberFromPull rejects distinct meta issue markers', () => {
  assert.equal(
    extractIssueNumberFromPull({
      body: '<!-- meta:issue:111 -->\n<!-- meta:issue:222 -->',
      head: { ref: 'codex/issue-111-fallback' },
      title: 'Resolve issue #111',
    }),
    null,
  );
  assert.equal(
    extractIssueNumberFromPull({
      body: '<!-- meta:issue:111 -->\n<!-- meta:issue:111 -->',
    }),
    111,
  );
});

test('extractIssueNumberFromPull ignores PR references in workflow source templates', () => {
  const context = resolvePrSourceContext({
    body: `
## Workflow Source

Started from:
- [ ] GitHub issue: #
- [x] Review follow-up from PR #315
- [ ] Direct PR / remote GitHub work
`,
    head: { ref: 'review-followup/source-context' },
    title: 'fix: address review follow-up',
  });

  assert.equal(extractIssueNumberFromPull({ body: 'Review follow-up from PR #315' }), null);
  assert.equal(context.sourceType, SOURCE_TYPES.REVIEW_FOLLOWUP);
  assert.equal(context.issueNumber, null);
  assert.equal(context.requiresIssue, false);
});

test('extractIssueNumberFromPull ignores arbitrary PR number references', () => {
  for (const body of [
    'Review follow-up from PR #123',
    'Follow-up from PR #123',
    'Original PR: #123',
    'Related to PR #123',
    'See pull request #123 for details',
    'Source PR #123 supplied the verifier evidence',
  ]) {
    assert.equal(extractIssueNumberFromPull({ body }), null, body);
  }
});

test('extractIssueNumberFromPull ignores bare issue-number mentions in PR descriptions', () => {
  assert.equal(extractIssueNumberFromPull({ body: '#123' }), null);
  assert.equal(extractIssueNumberFromPull({ body: 'see #123' }), null);
});

test('extractIssueNumberFromPull skips PR references before later issue references', () => {
  assert.equal(
    extractIssueNumberFromPull({
      body: 'Review follow-up from PR #315. Source issue #1937 tracks the fix.',
    }),
    1937,
  );
});

test('extractIssueNumberFromPull requires explicit issue wording for body references', () => {
  assert.equal(extractIssueNumberFromPull({ body: 'See PR #456 for context' }), null);
  assert.equal(extractIssueNumberFromPull({ body: 'Related to issue #456' }), 456);
  assert.equal(extractIssueNumberFromPull({ body: 'Closes #789' }), 789);
  assert.equal(extractIssueNumberFromPull({ body: 'Issue #123' }), 123);
  assert.equal(extractIssueNumberFromPull({ body: 'Linked issue #125' }), 125);
  assert.equal(extractIssueNumberFromPull({ body: 'Task #124 is ready' }), null);
  assert.equal(extractIssueNumberFromPull({ body: 'Resolve issue #123' }), 123);
  assert.equal(extractIssueNumberFromPull({ body: '> **Source:** Issue #123' }), 123);
  assert.equal(extractIssueNumberFromPull({ body: 'Known issue #123 blocks this PR' }), null);
  assert.equal(extractIssueNumberFromPull({ body: 'No issue #123 is linked' }), null);
  assert.equal(extractIssueNumberFromPull({ body: 'No linked issue #123 is real' }), null);
});

test('extractIssueNumberFromPull requires explicit issue wording for title references', () => {
  assert.equal(extractIssueNumberFromPull({ title: 'fix: resolve #55' }), 55);
  assert.equal(extractIssueNumberFromPull({ title: 'bump dependency (#55)' }), null);
  assert.equal(extractIssueNumberFromPull({ title: 'sync from Counter_Risk #502' }), null);
});

test('resolvePrSourceContext does not classify bare and PR-only mentions as issue-sourced', () => {
  for (const body of ['#123', 'see #123', 'Review follow-up from PR #123']) {
    const context = resolvePrSourceContext({ body, head: { ref: 'feature/no-source' }, title: 'Update docs' });
    assert.equal(context.issueNumber, null, body);
    assert.equal(context.requiresIssue, false, body);
  }
});

test('resolvePrSourceContext still classifies explicit issue-sourced references', () => {
  const context = resolvePrSourceContext({ body: 'Closes #123', head: { ref: 'feature/fix' }, title: 'Fix bug' });
  assert.equal(context.issueNumber, 123);
  assert.equal(context.sourceType, SOURCE_TYPES.GITHUB_ISSUE);
  assert.equal(context.requiresIssue, true);
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

test('dependency repair promotion marker supplies explicit dependency source context', () => {
  const marker = [
    '<!-- dependency-repair-promotion:v1 ',
    JSON.stringify({
      source_pr: 2795,
      source_base_sha: 'a'.repeat(40),
      source_head_sha: 'b'.repeat(40),
      promotion_base_sha: 'c'.repeat(40),
      ignored_untrusted_field: '__proto__',
    }),
    ' -->',
  ].join('');
  const context = resolvePrSourceContext({
    body: marker,
    head: { ref: 'agent/deps-repair-2795' },
    title: 'fix(deps): repair setup-python v7 compatibility',
    labels: [
      { name: 'dependency:repair-promotion' },
      { name: 'workflow:source-dependabot' },
    ],
  });

  assert.deepEqual(parseDependencyRepairPromotionSource(marker), {
    source_pr: 2795,
    source_base_sha: 'a'.repeat(40),
    source_head_sha: 'b'.repeat(40),
    promotion_base_sha: 'c'.repeat(40),
  });
  assert.equal(context.sourceType, SOURCE_TYPES.DEPENDABOT);
  assert.equal(context.sourceRef, 'dependency-pr:#2795');
  assert.equal(context.isExplicit, true);
  assert.equal(context.isValid, true);
  assert.equal(context.requiresIssue, false);
});

test('underscore dependency source label authorizes a valid promotion marker', () => {
  const marker = `<!-- dependency-repair-promotion:v1 ${JSON.stringify({
    source_pr: 2795,
    source_base_sha: 'a'.repeat(40),
    source_head_sha: 'b'.repeat(40),
    promotion_base_sha: 'c'.repeat(40),
  })} -->`;
  const context = resolvePrSourceContext({
    body: `${marker}\nFixes #99`,
    labels: [
      { name: 'dependency:repair-promotion' },
      { name: 'workflow_source_dependabot' },
    ],
  });

  assert.equal(context.sourceType, SOURCE_TYPES.DEPENDABOT);
  assert.equal(context.issueNumber, null);
});

test('dependency repair promotion marker suppresses incidental issue references', () => {
  const marker = [
    '<!-- dependency-repair-promotion:v1 ',
    JSON.stringify({
      source_pr: 2795,
      source_base_sha: 'a'.repeat(40),
      source_head_sha: 'b'.repeat(40),
      promotion_base_sha: 'c'.repeat(40),
    }),
    ' -->',
  ].join('');
  const context = resolvePrSourceContext({
    body: `${marker}\nFixes #99`,
    head: { ref: 'agent/deps-repair-2795' },
    labels: [
      { name: 'dependency:repair-promotion' },
      { name: 'workflow:source-dependabot' },
    ],
  });

  assert.equal(context.sourceType, SOURCE_TYPES.DEPENDABOT);
  assert.equal(context.issueNumber, null);
  assert.equal(context.sourceRef, 'dependency-pr:#2795');
  assert.equal(context.requiresIssue, false);
});

test('untrusted dependency repair promotion marker preserves issue routing', () => {
  const marker = [
    '<!-- dependency-repair-promotion:v1 ',
    JSON.stringify({
      source_pr: 2795,
      source_base_sha: 'a'.repeat(40),
      source_head_sha: 'b'.repeat(40),
      promotion_base_sha: 'c'.repeat(40),
    }),
    ' -->',
  ].join('');
  const context = resolvePrSourceContext({
    body: `${marker}\nFixes #99`,
    head: { ref: 'feature/forged-promotion-marker' },
  });

  assert.equal(context.sourceType, SOURCE_TYPES.GITHUB_ISSUE);
  assert.equal(context.issueNumber, 99);
  assert.equal(context.sourceRef, '#99');
  assert.equal(context.requiresIssue, true);
});

test('malformed dependency repair promotion marker does not authorize source context', () => {
  const context = resolvePrSourceContext({
    body: '<!-- dependency-repair-promotion:v1 {"source_pr":2795} -->',
    head: { ref: 'agent/deps-repair-2795' },
    title: 'fix(deps): repair setup-python v7 compatibility',
  });

  assert.equal(context.sourceType, SOURCE_TYPES.UNKNOWN);
  assert.equal(context.isExplicit, false);
  assert.equal(context.isValid, false);
});

test('partial promotion label sets do not authorize suppression of issue routing', () => {
  const marker = [
    '<!-- dependency-repair-promotion:v1 ',
    JSON.stringify({
      source_pr: 2795,
      source_base_sha: 'a'.repeat(40),
      source_head_sha: 'b'.repeat(40),
      promotion_base_sha: 'c'.repeat(40),
    }),
    ' -->',
  ].join('');
  const partialLabelSets = [
    [{ name: 'dependency:repair-promotion' }],
    [{ name: 'workflow:source-dependabot' }],
    [{ name: 'dependency:repair-promotion' }, { name: 'workflow:source-sync' }],
  ];

  for (const labels of partialLabelSets) {
    const context = resolvePrSourceContext({
      body: `${marker}\nFixes #99`,
      head: { ref: 'agent/deps-repair-2795' },
      labels,
    });

    assert.equal(context.sourceType, SOURCE_TYPES.GITHUB_ISSUE);
    assert.equal(context.issueNumber, 99);
    assert.equal(context.sourceRef, '#99');
    assert.equal(context.requiresIssue, true);
  }
});

test('mismatched promotion payloads preserve issue routing even when both labels are present', () => {
  const mismatchedPayloads = [
    {
      source_pr: 0,
      source_base_sha: 'a'.repeat(40),
      source_head_sha: 'b'.repeat(40),
      promotion_base_sha: 'c'.repeat(40),
    },
    {
      source_pr: 2795,
      source_base_sha: 'a'.repeat(40),
      source_head_sha: 'not-a-sha',
      promotion_base_sha: 'c'.repeat(40),
    },
    {
      source_pr: 2795,
      source_base_sha: 'a'.repeat(40),
      source_head_sha: 'b'.repeat(40),
    },
  ];

  for (const payload of mismatchedPayloads) {
    const marker = `<!-- dependency-repair-promotion:v1 ${JSON.stringify(payload)} -->`;
    assert.equal(parseDependencyRepairPromotionSource(marker), null);

    const context = resolvePrSourceContext({
      body: `${marker}\nFixes #99`,
      head: { ref: 'agent/deps-repair-2795' },
      labels: [
        { name: 'dependency:repair-promotion' },
        { name: 'workflow:source-dependabot' },
      ],
    });

    assert.equal(context.sourceType, SOURCE_TYPES.GITHUB_ISSUE);
    assert.equal(context.issueNumber, 99);
    assert.equal(context.sourceRef, '#99');
    assert.equal(context.requiresIssue, true);

    const templateContext = templateResolvePrSourceContext({
      body: `${marker}\nFixes #99`,
      head: { ref: 'agent/deps-repair-2795' },
      labels: [
        { name: 'dependency:repair-promotion' },
        { name: 'workflow:source-dependabot' },
      ],
    });

    assert.equal(templateContext.sourceType, SOURCE_TYPES.GITHUB_ISSUE);
    assert.equal(templateContext.issueNumber, 99);
    assert.equal(templateContext.sourceRef, '#99');
    assert.equal(templateContext.requiresIssue, true);
  }
});

test('consumer template resolver stays behaviorally synchronized on promotion trust', () => {
  const marker = [
    '<!-- dependency-repair-promotion:v1 ',
    JSON.stringify({
      source_pr: 2795,
      source_base_sha: 'a'.repeat(40),
      source_head_sha: 'b'.repeat(40),
      promotion_base_sha: 'c'.repeat(40),
    }),
    ' -->',
  ].join('');
  const labelSets = [
    [{ name: 'dependency:repair-promotion' }, { name: 'workflow:source-dependabot' }],
    [{ name: 'dependency:repair-promotion' }],
    [{ name: 'workflow:source-dependabot' }],
    [],
  ];

  for (const labels of labelSets) {
    const pull = {
      body: `${marker}\nFixes #99`,
      head: { ref: 'agent/deps-repair-2795' },
      labels,
    };

    assert.deepEqual(
      templateResolvePrSourceContext(pull),
      resolvePrSourceContext(pull),
    );
  }
});

test('promotion marker casing must match the dependency repair contract', () => {
  const context = resolvePrSourceContext({
    body: [
      '<!-- Dependency-Repair-Promotion:v1 ',
      JSON.stringify({
        schema: 'dependency-repair-promotion/v1',
        source_repo: 'stranske/Workflows',
        source_pr: 2795,
        source_head_sha: 'a'.repeat(40),
        promotion_base_sha: 'b'.repeat(40),
        classification: 'coupled-repair',
      }),
      ' -->',
    ].join(''),
  });

  assert.equal(context.sourceType, SOURCE_TYPES.UNKNOWN);
  assert.equal(context.isExplicit, false);
  assert.equal(context.isValid, false);
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

test('sourceTypeFromCheckedTemplate accepts slash-separated local request wording', () => {
  const body = `
## Workflow Source

Started from:
- [ ] GitHub issue: #
- [x] Local Codex/user request

Automation intent:
- [ ] Human-only unless checks fail
`;

  assert.equal(sourceTypeFromCheckedTemplate(body), SOURCE_TYPES.LOCAL_REQUEST);
});

test('sourceTypeFromCheckedTemplate preserves source choice without automation intent opt-out', () => {
  const body = `
## Workflow Source

Started from:
- [ ] GitHub issue: #
- [x] Local Codex/user request

Automation intent:
- [x] Human-only unless checks fail
`;

  assert.equal(sourceTypeFromCheckedTemplate(body), SOURCE_TYPES.LOCAL_REQUEST);
  const context = resolvePrSourceContext({ body });
  assert.equal(context.sourceType, SOURCE_TYPES.LOCAL_REQUEST);
  assert.equal(context.noAutomation, false);
});

test('automation intent checkboxes do not disable automation without started-from source', () => {
  const body = `
## Workflow Source

Automation intent:
- [x] Human-only unless checks fail
`;

  const context = resolvePrSourceContext({ body });
  assert.equal(sourceTypeFromCheckedTemplate(body), SOURCE_TYPES.UNKNOWN);
  assert.equal(context.sourceType, SOURCE_TYPES.UNKNOWN);
  assert.equal(context.noAutomation, false);
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

test('resolvePrSourceContext marks no-automation sources without changing source type', () => {
  const context = resolvePrSourceContext({
    body: `
## Workflow Source

Started from:
- [x] Do not automate

Automation intent:
- [x] Human-only unless checks fail
`,
  });

  assert.equal(context.sourceType, SOURCE_TYPES.MANUAL_REMOTE);
  assert.equal(context.noAutomation, true);
  assert.equal(hasNoAutomationWorkflowContext({ labels: [{ name: 'workflow:no-automation' }] }), true);
  assert.equal(hasNoAutomationWorkflowContext({ body: '<!-- workflow-source:no_automation -->' }), true);
  assert.equal(hasNoAutomationWorkflowContext({
    body: `
<!-- workflow-source:start -->
origin: local_request
automation: no_automation
<!-- workflow-source:end -->
`,
  }), true);
});

test('resolvePrSourceContext normalizes explicit no-automation to a valid manual source', () => {
  const context = resolvePrSourceContext({
    body: `
<!-- workflow-source:start -->
automation: no_automation
<!-- workflow-source:end -->
`,
  });

  assert.equal(context.sourceType, SOURCE_TYPES.MANUAL_REMOTE);
  assert.equal(context.noAutomation, true);
  assert.equal(context.isExplicit, true);
  assert.equal(context.isValid, true);
  assert.equal(context.requiresIssue, false);
});

test('resolvePrSourceContext preserves legacy human-only no-automation wording', () => {
  const context = resolvePrSourceContext({
    body: `
## Workflow Source

Started from:
- [x] Human-only
`,
  });

  assert.equal(context.sourceType, SOURCE_TYPES.MANUAL_REMOTE);
  assert.equal(context.noAutomation, true);
});

test('sourceTypeFromCheckedTemplate rejects ambiguous checked source choices', () => {
  const body = `
## Workflow Source

Started from:
- [x] GitHub issue: #123
- [x] Direct PR / remote GitHub work
- [ ] Local Codex/user request
`;

  assert.equal(sourceTypeFromCheckedTemplate(body), SOURCE_TYPES.UNKNOWN);
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

test('resolvePrSourceContext infers local_request for conventional work-branch prefixes', () => {
  const local = resolvePrSourceContext({
    body: '',
    head: { ref: 'feat/retire-plan-v3' },
    title: 'Change code',
  });

  assert.equal(local.sourceType, SOURCE_TYPES.LOCAL_REQUEST);
  assert.equal(local.isValid, true);
  assert.equal(local.requiresIssue, false);
  assert.equal(local.isExplicit, false);

  const automated = resolvePrSourceContext({
    body: '',
    head: { ref: 'chore/ledger-base-sync' },
    title: 'chore: sync ledger base',
    user: { login: 'github-actions[bot]' },
  });
  assert.equal(automated.sourceType, SOURCE_TYPES.AUTOMATION_RUN);
  assert.equal(automated.isValid, true);
  assert.equal(automated.requiresIssue, false);

  for (const branch of ['codex/no-issue-link', 'closer/foo']) {
    const lane = resolvePrSourceContext({ body: '', head: { ref: branch }, title: 'Change code' });
    assert.equal(lane.sourceType, SOURCE_TYPES.UNKNOWN);
    assert.equal(lane.isValid, false);
  }

  assert.deepEqual(
    templateResolvePrSourceContext({ body: '', head: { ref: 'feat/retire-plan-v3' }, title: 'Change code' }),
    local,
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

test('resolvePrSourceContext does not treat review PR references as source issues', () => {
  const context = resolvePrSourceContext({
    body: [
      '## Workflow Source',
      '',
      'Started from:',
      '- [ ] GitHub issue: #',
      '- [x] Review follow-up from PR #956',
    ].join('\n'),
    head: { ref: 'review-followup/pr-956' },
    title: 'Address review feedback',
  });

  assert.equal(context.sourceType, SOURCE_TYPES.REVIEW_FOLLOWUP);
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
