'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  parseCheckboxStates,
  mergeCheckboxStates,
  ensureChecklist,
  coalesceWrappedChecklist,
  extractBlock,
  fetchConnectorCheckboxStates,
  findUnauthorizedCompletionAuthors,
  buildCompletionAuthorWarningBody,
  upsertCompletionAuthorWarning,
  buildStatusBlock,
  buildPreamble,
  buildSourceContextRepairCommentBody,
  buildSourceContextResolvedCommentBody,
  resolveSourceContextRepairComment,
  resolveAgentType,
  stripPrTemplateContent,
  augmentContextWithRelatedIssues,
  extractIssueRefsFromText,
  extractContextSectionWithPython,
  upsertBlock,
} = require('../agents_pr_meta_update_body.js');

test('extractContextSectionWithPython returns trimmed stdout from python', () => {
  const childProcess = require('node:child_process');
  const original = childProcess.execFileSync;
  childProcess.execFileSync = () => '  ## Context for Agent\n- extracted\n';

  try {
    const result = extractContextSectionWithPython('Issue body', ['Comment body'], null);
    assert.strictEqual(result, '## Context for Agent\n- extracted');
  } finally {
    childProcess.execFileSync = original;
  }
});

test('extractContextSectionWithPython returns empty string on failure', () => {
  const childProcess = require('node:child_process');
  const original = childProcess.execFileSync;
  childProcess.execFileSync = () => {
    throw new Error('python missing');
  };

  const core = {
    warning: () => {},
  };

  try {
    const result = extractContextSectionWithPython('Issue body', [], core);
    assert.strictEqual(result, '');
  } finally {
    childProcess.execFileSync = original;
  }
});

test('parseCheckboxStates extracts checked items from a checkbox list', () => {
  const block = `
- [x] Task one completed
- [ ] Task two pending
- [x] Task three completed
- [ ] Task four pending
  `.trim();

  const states = parseCheckboxStates(block);

  assert.strictEqual(states.size, 2);
  assert.strictEqual(states.get('task one completed'), true);
  assert.strictEqual(states.get('task three completed'), true);
  assert.strictEqual(states.has('task two pending'), false);
});

test('parseCheckboxStates normalizes text by stripping leading dashes', () => {
  const block = `
- [x] - Tests fail if weight bounds...
- [ ] - Existing functionality remains
  `.trim();

  const states = parseCheckboxStates(block);

  assert.strictEqual(states.size, 1);
  assert.strictEqual(states.get('tests fail if weight bounds...'), true);
});

test('parseCheckboxStates handles case-insensitive matching', () => {
  const block = `
- [X] UPPERCASE checked
- [x] lowercase checked
  `.trim();

  const states = parseCheckboxStates(block);

  assert.strictEqual(states.size, 2);
  assert.strictEqual(states.get('uppercase checked'), true);
  assert.strictEqual(states.get('lowercase checked'), true);
});

test('parseCheckboxStates ignores fenced code blocks', () => {
  const block = `
- [x] Real task
\`\`\`md
- [x] Not real
- [ ] Also not real
\`\`\`
- [x] Another task
  `.trim();

  const states = parseCheckboxStates(block);

  assert.strictEqual(states.size, 2);
  assert.strictEqual(states.get('real task'), true);
  assert.strictEqual(states.get('another task'), true);
  assert.strictEqual(states.has('not real'), false);
});

test('parseCheckboxStates returns empty map for empty input', () => {
  assert.deepStrictEqual(parseCheckboxStates(''), new Map());
  assert.deepStrictEqual(parseCheckboxStates(null), new Map());
  assert.deepStrictEqual(parseCheckboxStates(undefined), new Map());
});

test('mergeCheckboxStates restores checked state for unchecked items', () => {
  const newContent = `
- [ ] Task one
- [ ] Task two
- [ ] Task three
  `.trim();

  const existingStates = new Map([
    ['task one', true],
    ['task three', true],
  ]);

  const result = mergeCheckboxStates(newContent, existingStates);

  assert.ok(result.includes('- [x] Task one'));
  assert.ok(result.includes('- [ ] Task two'));
  assert.ok(result.includes('- [x] Task three'));
});

test('mergeCheckboxStates preserves already checked items in new content', () => {
  const newContent = `
- [x] Already checked in new content
- [ ] Unchecked in new
  `.trim();

  const existingStates = new Map([
    ['unchecked in new', true],
  ]);

  const result = mergeCheckboxStates(newContent, existingStates);

  // Already checked stays checked
  assert.ok(result.includes('- [x] Already checked in new content'));
  // Unchecked gets restored
  assert.ok(result.includes('- [x] Unchecked in new'));
});

test('mergeCheckboxStates handles items with leading dashes in text', () => {
  const newContent = `
- [ ] - Tests fail if bounds violated
- [ ] - Functionality remains unchanged
  `.trim();

  const existingStates = new Map([
    ['tests fail if bounds violated', true],
  ]);

  const result = mergeCheckboxStates(newContent, existingStates);

  assert.ok(result.includes('- [x] - Tests fail if bounds violated'));
  assert.ok(result.includes('- [ ] - Functionality remains unchanged'));
});

test('mergeCheckboxStates ignores fenced code blocks', () => {
  const newContent = `
- [ ] Task one
\`\`\`md
- [ ] Code task
\`\`\`
- [ ] Task two
  `.trim();

  const existingStates = new Map([
    ['task one', true],
    ['code task', true],
  ]);

  const result = mergeCheckboxStates(newContent, existingStates);

  assert.ok(result.includes('- [x] Task one'));
  assert.ok(result.includes('- [ ] Code task'));
  assert.ok(result.includes('- [ ] Task two'));
});

test('mergeCheckboxStates returns original content if no existing states', () => {
  const content = '- [ ] Task one\n- [ ] Task two';

  assert.strictEqual(mergeCheckboxStates(content, null), content);
  assert.strictEqual(mergeCheckboxStates(content, new Map()), content);
});

test('mergeCheckboxStates handles real-world acceptance criteria format', () => {
  const prBody = `
#### Acceptance criteria
- [ ] - Tests fail if weight bounds or turnover calculations allow negative weights
- [ ] - Existing functionality remains unchanged outside the stronger test coverage
  `.trim();

  // Agent completes first criterion and posts with checked box
  const agentReply = `
#### Acceptance criteria
- [x] - Tests fail if weight bounds or turnover calculations allow negative weights
- [ ] - Existing functionality remains unchanged outside the stronger test coverage
  `.trim();

  const existingStates = parseCheckboxStates(agentReply);
  assert.strictEqual(existingStates.size, 1);

  // PR-meta refreshes from issue (unchecked) and merges agent's checked state
  const merged = mergeCheckboxStates(prBody, existingStates);

  assert.ok(merged.includes('- [x] - Tests fail if weight bounds or turnover calculations allow negative weights'));
  assert.ok(merged.includes('- [ ] - Existing functionality remains unchanged outside the stronger test coverage'));
});

test('ensureChecklist adds checkbox prefix to plain text lines', () => {
  const text = 'Task one\nTask two\nTask three';
  const result = ensureChecklist(text);

  assert.strictEqual(result, '- [ ] Task one\n- [ ] Task two\n- [ ] Task three');
});

test('ensureChecklist preserves existing checkbox formatting', () => {
  const text = '- [x] Completed task\n- [ ] Pending task';
  const result = ensureChecklist(text);

  assert.strictEqual(result, '- [x] Completed task\n- [ ] Pending task');
});

test('ensureChecklist preserves HTML comments without adding checkboxes', () => {
  const text = '<!-- Incomplete tasks from original issue -->\n- [x] Completed task\n- [ ] Pending task';
  const result = ensureChecklist(text);

  assert.strictEqual(result, '<!-- Incomplete tasks from original issue -->\n- [x] Completed task\n- [ ] Pending task');
});

test('ensureChecklist preserves section headers without adding checkboxes', () => {
  const text = '## Tasks\n- [ ] Task one';
  const result = ensureChecklist(text);

  assert.strictEqual(result, '## Tasks\n- [ ] Task one');
});

test('ensureChecklist preserves wrapped list item lines', () => {
  const text = '- Task one with a long description\n  that continues here\n- [ ] Task two';
  const result = ensureChecklist(text);

  assert.strictEqual(result, '- [ ] Task one with a long description\n  that continues here\n- [ ] Task two');
});

test('coalesceWrappedChecklist merges continuation lines with joiners', () => {
  const text = '- [ ] Add unit tests for FallbackChainProvider that pass quality_context and\n' +
    '- [ ] assert it reaches the target provider.\n' +
    '- [ ] Add regression tests for analysis_text_length < 50 with has_work_evidence\n' +
    '- [ ] enabled so confidence does not exceed the cap.\n' +
    '- [ ] Tests verify quality_context is passed to active providers in\n' +
    '- [ ] FallbackChainProvider.';
  const result = coalesceWrappedChecklist(text);

  assert.strictEqual(
    result,
    '- [ ] Add unit tests for FallbackChainProvider that pass quality_context and assert it reaches the target provider.\n' +
      '- [ ] Add regression tests for analysis_text_length < 50 with has_work_evidence enabled so confidence does not exceed the cap.\n' +
      '- [ ] Tests verify quality_context is passed to active providers in FallbackChainProvider.'
  );
});

test('ensureChecklist returns placeholder for empty input', () => {
  assert.strictEqual(ensureChecklist(''), '- [ ] —');
  assert.strictEqual(ensureChecklist('   '), '- [ ] —');
  assert.strictEqual(ensureChecklist(null), '- [ ] —');
});

test('extractBlock extracts content between markers', () => {
  const body = `
Some preamble text

<!-- auto-status-summary:start -->
#### Tasks
- [ ] Task one
- [x] Task two
<!-- auto-status-summary:end -->

Some footer text
  `.trim();

  const block = extractBlock(body, 'auto-status-summary');

  assert.ok(block.includes('#### Tasks'));
  assert.ok(block.includes('- [ ] Task one'));
  assert.ok(block.includes('- [x] Task two'));
});

test('extractBlock returns empty string if markers not found', () => {
  assert.strictEqual(extractBlock('no markers here', 'auto-status-summary'), '');
  assert.strictEqual(extractBlock('', 'auto-status-summary'), '');
  assert.strictEqual(extractBlock(null, 'auto-status-summary'), '');
});

// ========== stripPrTemplateContent tests ==========

test('stripPrTemplateContent removes content before pr-preamble marker', () => {
  const body = `# Summary

One sentence.

## Checklist

- [ ] Does NOT touch protected paths

## Labels

Add labels.

<!-- pr-preamble:start -->
<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
<!-- auto-status-summary:end -->`;

  const result = stripPrTemplateContent(body);
  
  assert.ok(result.startsWith('<!-- pr-preamble:start -->'));
  assert.ok(!result.includes('# Summary'));
  assert.ok(!result.includes('Checklist'));
});

test('stripPrTemplateContent removes content before auto-status-summary if no preamble', () => {
  const body = `Template junk here

<!-- auto-status-summary:start -->
## Automated Status Summary
<!-- auto-status-summary:end -->`;

  const result = stripPrTemplateContent(body);
  
  assert.ok(result.startsWith('<!-- auto-status-summary:start -->'));
  assert.ok(!result.includes('Template junk'));
});

test('stripPrTemplateContent preserves body if no markers present', () => {
  const body = 'Just a normal PR body with no markers';
  const result = stripPrTemplateContent(body);
  assert.strictEqual(result, body);
});

test('stripPrTemplateContent preserves body if markers are at start', () => {
  const body = `<!-- pr-preamble:start -->
Content here
<!-- pr-preamble:end -->`;
  
  const result = stripPrTemplateContent(body);
  assert.strictEqual(result, body);
});

test('stripPrTemplateContent handles empty and null input', () => {
  assert.strictEqual(stripPrTemplateContent(''), '');
  assert.strictEqual(stripPrTemplateContent(null), '');
  assert.strictEqual(stripPrTemplateContent(undefined), '');
});

test('buildPreamble preserves source issue metadata and closing reference', () => {
  const result = buildPreamble({
    issueNumber: 1881,
    summary: 'Summary text',
  });

  assert.ok(result.includes('<!-- meta:issue:1881 -->'));
  assert.ok(result.includes('> **Source:** Issue #1881'));
  assert.ok(result.includes('Closes #1881'));
  assert.ok(result.includes('## Summary\nSummary text'));
});

test('buildPreamble does not close active campaign issues', () => {
  const result = buildPreamble({
    issueNumber: 1836,
    summary: 'Campaign source fix',
    sourceIssue: {
      labels: [
        { name: 'campaign:sync-dependabot' },
        { name: 'campaign:active' },
      ],
    },
  });

  assert.ok(result.includes('<!-- meta:issue:1836 -->'));
  assert.ok(result.includes('> **Source:** Issue #1836'));
  assert.ok(result.includes('Related to campaign issue #1836'));
  assert.ok(!result.includes('Closes #1836'));
});

test('buildSourceContextRepairCommentBody explains non-issue source options', () => {
  const result = buildSourceContextRepairCommentBody(55);

  assert.ok(result.includes('<!-- missing-issue-warning -->'));
  assert.ok(result.includes('PR #55 does not need a GitHub issue'));
  assert.ok(result.includes('<!-- workflow-source:local_request -->'));
  assert.ok(result.includes('workflow:source-direct-pr'));
  assert.ok(result.includes('workflow:no-automation'));
});

test('buildSourceContextResolvedCommentBody retires stale source repair comments', () => {
  const result = buildSourceContextResolvedCommentBody(55, {
    sourceType: 'local_request',
    sourceRef: 'codex-thread-2026-04-26',
  });

  assert.ok(result.includes('<!-- missing-issue-warning -->'));
  assert.ok(result.includes('PR #55 now has valid workflow source context'));
  assert.ok(result.includes('local_request'));
  assert.ok(result.includes('codex-thread-2026-04-26'));
  assert.ok(result.includes('No linked GitHub issue is required'));
});

test('resolveSourceContextRepairComment updates an existing warning once', async () => {
  const calls = { update: 0, body: '' };
  const github = {
    rest: {
      issues: {
        updateComment: async ({ comment_id, body }) => {
          assert.strictEqual(comment_id, 99);
          calls.update += 1;
          calls.body = body;
        },
      },
    },
  };

  const updated = await resolveSourceContextRepairComment({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 55,
    comments: [{ id: 99, body: '<!-- missing-issue-warning -->\nold warning' }],
    sourceContext: { sourceType: 'local_request', sourceRef: 'codex-thread-2026-04-26' },
    core: { info: () => {} },
  });

  assert.strictEqual(updated, true);
  assert.strictEqual(calls.update, 1);
  assert.ok(calls.body.includes('Workflow source detected'));
});

test('resolveSourceContextRepairComment skips when no warning exists', async () => {
  const github = {
    rest: {
      issues: {
        updateComment: async () => {
          throw new Error('should not update');
        },
      },
    },
  };

  const updated = await resolveSourceContextRepairComment({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 55,
    comments: [],
    sourceContext: { sourceType: 'local_request' },
    core: { info: () => {} },
  });

  assert.strictEqual(updated, false);
});

// ========== fetchConnectorCheckboxStates tests ==========

test('fetchConnectorCheckboxStates extracts checked boxes from connector bot comments', async () => {
  const mockGithub = {
    paginate: async (method, params) => {
      assert.strictEqual(params.issue_number, 123);
      return [
        {
          user: { login: 'chatgpt-codex-connector[bot]' },
          body: `
## Work Summary

- [x] Implemented feature A
- [ ] Feature B pending
- [x] Added tests for feature A
          `.trim(),
        },
      ];
    },
    rest: {
      issues: {
        listComments: {},
      },
    },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 123, null);

  assert.strictEqual(states.size, 2);
  assert.strictEqual(states.get('implemented feature a'), true);
  assert.strictEqual(states.get('added tests for feature a'), true);
  assert.strictEqual(states.has('feature b pending'), false);
});

test('fetchConnectorCheckboxStates ignores non-connector comments', async () => {
  const mockGithub = {
    paginate: async () => [
      {
        user: { login: 'regular-user' },
        body: '- [x] User checked something',
      },
      {
        user: { login: 'chatgpt-codex-connector[bot]' },
        body: '- [x] Connector checked this',
      },
    ],
    rest: { issues: { listComments: {} } },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, null);

  assert.strictEqual(states.size, 1);
  assert.strictEqual(states.get('connector checked this'), true);
  assert.strictEqual(states.has('user checked something'), false);
});

test('fetchConnectorCheckboxStates returns empty map when no connector comments exist', async () => {
  const mockGithub = {
    paginate: async () => [
      { user: { login: 'user1' }, body: '- [x] Task done' },
      { user: { login: 'user2' }, body: 'LGTM!' },
    ],
    rest: { issues: { listComments: {} } },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, null);

  assert.strictEqual(states.size, 0);
});

test('fetchConnectorCheckboxStates aggregates checked boxes from multiple connector comments', async () => {
  const mockGithub = {
    paginate: async () => [
      {
        user: { login: 'chatgpt-codex-connector[bot]' },
        body: '- [x] Task A completed',
      },
      {
        user: { login: 'github-actions[bot]' },
        body: '- [x] Task B done\n- [x] Task C done',
      },
      {
        user: { login: 'chatgpt-codex-connector[bot]' },
        body: '- [x] Task D finished',
      },
    ],
    rest: { issues: { listComments: {} } },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, null);

  assert.strictEqual(states.size, 4);
  assert.strictEqual(states.get('task a completed'), true);
  assert.strictEqual(states.get('task b done'), true);
  assert.strictEqual(states.get('task c done'), true);
  assert.strictEqual(states.get('task d finished'), true);
});

test('fetchConnectorCheckboxStates handles API errors gracefully', async () => {
  const mockGithub = {
    paginate: async () => {
      throw new Error('API rate limit exceeded');
    },
    rest: { issues: { listComments: {} } },
  };

  const mockCore = {
    warning: () => {},
    info: () => {},
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, mockCore);

  assert.strictEqual(states.size, 0);
});

test('fetchConnectorCheckboxStates handles comments with null user', async () => {
  const mockGithub = {
    paginate: async () => [
      { user: null, body: '- [x] Orphaned comment' },
      { user: { login: 'chatgpt-codex-connector[bot]' }, body: '- [x] Valid task' },
    ],
    rest: { issues: { listComments: {} } },
  };

  const states = await fetchConnectorCheckboxStates(mockGithub, 'owner', 'repo', 1, null);

  assert.strictEqual(states.size, 1);
  assert.strictEqual(states.get('valid task'), true);
});

test('findUnauthorizedCompletionAuthors detects completion checkpoint authors', () => {
  const comments = [
    {
      user: { login: 'custom-bot[bot]' },
      body: '<!-- codex-completion-checkpoint -->\n- [x] Done',
    },
    {
      user: { login: 'github-actions[bot]' },
      body: '<!-- codex-completion-checkpoint -->\n- [x] Done',
    },
  ];

  const result = findUnauthorizedCompletionAuthors(comments);

  assert.deepStrictEqual(result, ['custom-bot[bot]']);
});

test('buildCompletionAuthorWarningBody includes marker and logins', () => {
  const body = buildCompletionAuthorWarningBody(['custom-bot[bot]']);

  assert.ok(body.includes('<!-- completion-author-warning -->'));
  assert.ok(body.includes('custom-bot[bot]'));
});

test('upsertCompletionAuthorWarning creates comment for unauthorized authors', async () => {
  const calls = { create: 0, update: 0, lastBody: '' };
  const github = {
    rest: {
      issues: {
        createComment: async ({ body }) => {
          calls.create += 1;
          calls.lastBody = body;
        },
        updateComment: async () => {
          calls.update += 1;
        },
      },
    },
  };

  await upsertCompletionAuthorWarning({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 42,
    comments: [],
    unauthorizedLogins: ['custom-bot[bot]'],
    core: { info: () => {}, warning: () => {} },
  });

  assert.strictEqual(calls.create, 1);
  assert.strictEqual(calls.update, 0);
  assert.ok(calls.lastBody.includes('custom-bot[bot]'));
});

test('upsertCompletionAuthorWarning resolves existing warning comment', async () => {
  const calls = { create: 0, update: 0, lastBody: '' };
  const github = {
    rest: {
      issues: {
        createComment: async () => {
          calls.create += 1;
        },
        updateComment: async ({ body }) => {
          calls.update += 1;
          calls.lastBody = body;
        },
      },
    },
  };

  await upsertCompletionAuthorWarning({
    github,
    owner: 'octo',
    repo: 'demo',
    prNumber: 42,
    comments: [{ id: 99, body: '<!-- completion-author-warning -->' }],
    unauthorizedLogins: [],
    core: { info: () => {}, warning: () => {} },
  });

  assert.strictEqual(calls.create, 0);
  assert.strictEqual(calls.update, 1);
  assert.ok(calls.lastBody.includes('Completion Comment Authors Authorized'));
});

test('resolveAgentType prefers explicit inputs over labels', () => {
  const agentType = resolveAgentType({
    inputs: { agent_type: 'codex' },
    env: { AGENT_TYPE: 'claude' },
    pr: { labels: [{ name: 'agent:gemini' }] },
  });

  assert.strictEqual(agentType, 'codex');
});

test('resolveAgentType falls back to agent label when inputs are missing', () => {
  const agentType = resolveAgentType({
    inputs: {},
    env: {},
    pr: { labels: [{ name: 'priority:high' }, { name: 'agent:codex' }] },
  });

  assert.strictEqual(agentType, 'codex');
});

test('resolveAgentType returns empty string when no agent source is available', () => {
  const agentType = resolveAgentType({
    inputs: {},
    env: {},
    pr: { labels: [{ name: 'needs-human' }] },
  });

  assert.strictEqual(agentType, '');
});

test('buildStatusBlock hides workflow details for CLI agents', () => {
  const workflowRuns = new Map([
    ['gate', {
      name: 'Gate',
      created_at: '2024-01-02T00:00:00Z',
      status: 'completed',
      conclusion: 'success',
      html_url: 'https://example.com/run',
    }],
  ]);

  const output = buildStatusBlock({
    scope: '- [ ] Scope item',
    tasks: '- [ ] Task item',
    acceptance: '- [ ] Acceptance item',
    headSha: 'abc123',
    workflowRuns,
    requiredChecks: ['gate'],
    existingBody: '',
    connectorStates: new Map(),
    core: null,
    agentType: 'codex',
  });

  assert.ok(output.includes('## Automated Status Summary'));
  assert.ok(output.includes('#### Scope'));
  assert.ok(output.includes('#### Tasks'));
  assert.ok(output.includes('#### Acceptance criteria'));
  assert.ok(!output.includes('**Head SHA:**'));
  assert.ok(!output.includes('**Latest Runs:**'));
  assert.ok(!output.includes('**Required:**'));
  assert.ok(!output.includes('| Workflow / Job |'));
});

test('buildStatusBlock includes workflow details for non-CLI agents', () => {
  const workflowRuns = new Map([
    ['gate', {
      name: 'Gate',
      created_at: '2024-01-02T00:00:00Z',
      status: 'completed',
      conclusion: 'success',
      html_url: 'https://example.com/run',
    }],
  ]);

  const output = buildStatusBlock({
    scope: '- [ ] Scope item',
    tasks: '- [ ] Task item',
    acceptance: '- [ ] Acceptance item',
    headSha: 'abc123',
    workflowRuns,
    requiredChecks: ['gate'],
    existingBody: '',
    connectorStates: new Map(),
    core: null,
    agentType: '',
    owner: 'octo',
    repo: 'demo',
  });

  assert.ok(output.includes('**Head SHA:** abc123'));
  assert.ok(output.includes('**Required:** gate: ✅ success'));
  assert.ok(output.includes('| Workflow / Job |'));
});

test('buildStatusBlock omits PR meta manager self status', () => {
  const workflowRuns = new Map([
    ['agents pr meta manager', {
      name: 'Agents PR meta manager',
      created_at: '2024-01-03T00:00:00Z',
      status: 'in_progress',
      conclusion: null,
      html_url: 'https://example.com/meta-run',
    }],
    ['gate', {
      name: 'Gate',
      created_at: '2024-01-02T00:00:00Z',
      status: 'completed',
      conclusion: 'success',
      html_url: 'https://example.com/gate-run',
    }],
  ]);

  const output = buildStatusBlock({
    scope: '- [ ] Scope item',
    tasks: '- [ ] Task item',
    acceptance: '- [ ] Acceptance item',
    headSha: 'abc123',
    workflowRuns,
    requiredChecks: ['gate'],
    existingBody: '',
    connectorStates: new Map(),
    core: null,
    agentType: '',
    owner: 'octo',
    repo: 'demo',
  });

  assert.ok(output.includes('**Latest Runs:** ✅ success — Gate'));
  assert.ok(output.includes('| Gate | ✅ success | [View run](https://example.com/gate-run) |'));
  assert.ok(!output.includes('Agents PR meta manager'));
  assert.ok(!output.includes('https://example.com/meta-run'));
});

test('buildStatusBlock inserts context between scope and tasks', () => {
  const result = buildStatusBlock({
    scope: 'Scope text',
    contextSection: '## Context for Agent\n- Related #123',
    tasks: '- [ ] Task one',
    acceptance: '- [ ] Done',
    headSha: 'abc123',
    workflowRuns: new Map(),
    requiredChecks: [],
    existingBody: '',
    connectorStates: new Map(),
    core: null,
    agentType: 'codex',
    owner: 'octo',
    repo: 'demo',
  });

  const scopeIndex = result.indexOf('#### Scope');
  const contextIndex = result.indexOf('<!-- Updated WORKFLOW_OUTPUTS.md context:start -->');
  const tasksIndex = result.indexOf('#### Tasks');

  assert.ok(scopeIndex !== -1, 'scope header missing');
  assert.ok(contextIndex !== -1, 'context markers missing');
  assert.ok(tasksIndex !== -1, 'tasks header missing');
  assert.ok(scopeIndex < contextIndex, 'context should appear after scope');
  assert.ok(contextIndex < tasksIndex, 'context should appear before tasks');
  assert.ok(result.includes('## Context for Agent'));
});

test('buildStatusBlock omits context markers when empty', () => {
  const result = buildStatusBlock({
    scope: 'Scope text',
    contextSection: '',
    tasks: '- [ ] Task one',
    acceptance: '- [ ] Done',
    headSha: 'abc123',
    workflowRuns: new Map(),
    requiredChecks: [],
    existingBody: '',
    connectorStates: new Map(),
    core: null,
    agentType: 'codex',
    owner: 'octo',
    repo: 'demo',
  });

  assert.ok(!result.includes('<!-- Updated WORKFLOW_OUTPUTS.md context:start -->'));
  assert.ok(!result.includes('<!-- Updated WORKFLOW_OUTPUTS.md context:end -->'));
});

test('buildStatusBlock linkifies related issue references in context', () => {
  const result = buildStatusBlock({
    scope: 'Scope text',
    contextSection: '## Context for Agent\n### Related Issues/PRs\n- #123\n- octo/demo#456',
    tasks: '- [ ] Task one',
    acceptance: '- [ ] Done',
    headSha: 'abc123',
    workflowRuns: new Map(),
    requiredChecks: [],
    existingBody: '',
    connectorStates: new Map(),
    core: null,
    agentType: 'codex',
    owner: 'octo',
    repo: 'demo',
  });

  assert.ok(result.includes('[#123](https://github.com/octo/demo/issues/123)'));
  assert.ok(result.includes('[octo/demo#456](https://github.com/octo/demo/issues/456)'));
});

test('extractIssueRefsFromText normalizes GitHub issue and pull URLs', () => {
  const refs = extractIssueRefsFromText(
    'See https://github.com/octo/demo/issues/12 and https://github.com/octo/demo/pull/34.'
  );

  assert.deepStrictEqual(refs, ['octo/demo#12', 'octo/demo#34']);
});

test('augmentContextWithRelatedIssues appends related refs when missing section', () => {
  const contextSection = '## Context for Agent\n### Design Decisions\n- Keep behavior stable.';
  const issueBody = 'Related to #123 and octo/demo#456 for background.';

  const augmented = augmentContextWithRelatedIssues(contextSection, issueBody);
  const result = buildStatusBlock({
    scope: 'Scope text',
    contextSection: augmented,
    tasks: '- [ ] Task one',
    acceptance: '- [ ] Done',
    headSha: 'abc123',
    workflowRuns: new Map(),
    requiredChecks: [],
    existingBody: '',
    connectorStates: new Map(),
    core: null,
    agentType: 'codex',
    owner: 'octo',
    repo: 'demo',
  });

  assert.ok(result.includes('### Related Issues/PRs'));
  assert.ok(result.includes('[#123](https://github.com/octo/demo/issues/123)'));
  assert.ok(result.includes('[octo/demo#456](https://github.com/octo/demo/issues/456)'));
});

test('augmentContextWithRelatedIssues adds missing refs to existing section', () => {
  const contextSection = [
    '## Context for Agent',
    '### Related Issues/PRs',
    '- #123',
    '### References',
    '- https://example.com',
  ].join('\n');
  const issueBody = 'Follow-up in #124 and octo/demo#456.';

  const augmented = augmentContextWithRelatedIssues(contextSection, issueBody);

  assert.ok(augmented.includes('- #123'));
  assert.ok(augmented.includes('- #124'));
  assert.ok(augmented.includes('- octo/demo#456'));
  assert.strictEqual(augmented.match(/### Related Issues\/PRs/g).length, 1);
});

// ========== upsertBlock tests ==========

test('upsertBlock replaces content between existing markers', () => {
  const body = `Preamble text

<!-- my-block:start -->
Old content here
<!-- my-block:end -->

Footer text`;

  const result = upsertBlock(body, 'my-block', '<!-- my-block:start -->\nNew content\n<!-- my-block:end -->');

  assert.ok(result.includes('New content'));
  assert.ok(!result.includes('Old content'));
  assert.ok(result.includes('Preamble text'));
  assert.ok(result.includes('Footer text'));
});

test('upsertBlock appends when no markers exist', () => {
  const body = 'Just a PR body with no markers';

  const result = upsertBlock(body, 'my-block', '<!-- my-block:start -->\nNew block\n<!-- my-block:end -->');

  assert.ok(result.startsWith('Just a PR body'));
  assert.ok(result.includes('New block'));
});

test('upsertBlock appends to empty body', () => {
  const result = upsertBlock('', 'my-block', '<!-- my-block:start -->\nContent\n<!-- my-block:end -->');

  assert.ok(result.includes('Content'));
  assert.ok(!result.startsWith('\n'));
});

test('upsertBlock removes duplicate marker pairs from race conditions', () => {
  const body = `Preamble

<!-- status:start -->
First copy (stale)
<!-- status:end -->

Middle content

<!-- status:start -->
Second copy (also stale)
<!-- status:end -->

Footer`;

  const replacement = '<!-- status:start -->\nFresh content\n<!-- status:end -->';
  const result = upsertBlock(body, 'status', replacement);

  // Should contain exactly one pair of markers
  const startCount = (result.match(/<!-- status:start -->/g) || []).length;
  const endCount = (result.match(/<!-- status:end -->/g) || []).length;
  assert.strictEqual(startCount, 1, 'should have exactly one start marker');
  assert.strictEqual(endCount, 1, 'should have exactly one end marker');

  // Should contain the fresh content
  assert.ok(result.includes('Fresh content'));
  assert.ok(!result.includes('First copy'));
  assert.ok(!result.includes('Second copy'));

  // Should preserve surrounding content including text between duplicates
  assert.ok(result.includes('Preamble'));
  assert.ok(result.includes('Middle content'));
  assert.ok(result.includes('Footer'));
});

test('upsertBlock removes three duplicate marker pairs', () => {
  const body = [
    '<!-- b:start -->\nCopy 1\n<!-- b:end -->',
    '<!-- b:start -->\nCopy 2\n<!-- b:end -->',
    '<!-- b:start -->\nCopy 3\n<!-- b:end -->',
  ].join('\n\n');

  const result = upsertBlock(body, 'b', '<!-- b:start -->\nFinal\n<!-- b:end -->');

  const startCount = (result.match(/<!-- b:start -->/g) || []).length;
  assert.strictEqual(startCount, 1);
  assert.ok(result.includes('Final'));
  assert.ok(!result.includes('Copy 1'));
  assert.ok(!result.includes('Copy 2'));
  assert.ok(!result.includes('Copy 3'));
});

test('upsertBlock collapses excessive newlines after removing duplicates', () => {
  const body = `Before

<!-- s:start -->
Old
<!-- s:end -->



<!-- s:start -->
Dup
<!-- s:end -->

After`;

  const result = upsertBlock(body, 's', '<!-- s:start -->\nNew\n<!-- s:end -->');

  // No triple+ newlines should remain
  assert.ok(!result.match(/\n{3,}/), 'should not have triple+ newlines');
  assert.ok(result.includes('After'));
});

test('upsertBlock preserves triple newlines in single-pair case (no duplicates)', () => {
  const body = `Before\n\n\n<!-- m:start -->\nOld\n<!-- m:end -->\n\n\nAfter`;

  const result = upsertBlock(body, 'm', '<!-- m:start -->\nNew\n<!-- m:end -->');

  // Triple newlines outside the managed block should be preserved
  // when no duplicate removal occurred
  assert.ok(result.includes('Before'));
  assert.ok(result.includes('New'));
  assert.ok(result.includes('After'));
  assert.ok(result.includes('\n\n\n'), 'should preserve existing triple newlines when no duplicates removed');
});
