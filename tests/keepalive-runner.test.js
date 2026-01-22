'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildOctokitInstance,
  countCheckboxes,
  extractLatestChecklist,
  resolveInstructionToken,
  resolveDispatchToken,
  coerceNumber,
  resolvePromptCheckboxCounts,
  runKeepalive,
} = require('../scripts/keepalive-runner.js');

test('resolveInstructionToken prefers service bot PAT over actions bot PAT', () => {
  const env = {
    ACTIONS_BOT_PAT: 'actions-token',
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveInstructionToken(env), 'service-token');
});

test('resolveInstructionToken falls back to actions bot PAT when service token missing', () => {
  const env = {
    ACTIONS_BOT_PAT: 'actions-token',
    SERVICE_BOT_PAT: '',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveInstructionToken(env), 'actions-token');
});

test('resolveInstructionToken accepts lower-case service_bot_pat', () => {
  const env = {
    service_bot_pat: 'service-token',
  };
  assert.equal(resolveInstructionToken(env), 'service-token');
});

test('resolveInstructionToken falls back to GITHUB_TOKEN', () => {
  const env = {
    GITHUB_TOKEN: 'github-token',
  };
  assert.equal(resolveInstructionToken(env), 'github-token');
});

test('resolveDispatchToken prefers actions bot PAT over instruction tokens', () => {
  const env = {
    ACTIONS_BOT_PAT: 'actions-token',
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveDispatchToken(env), 'actions-token');
});

test('resolveDispatchToken falls back to instruction token when actions token missing', () => {
  const env = {
    SERVICE_BOT_PAT: 'service-token',
    GH_TOKEN: 'gh-token',
  };
  assert.equal(resolveDispatchToken(env), 'service-token');
});

test('resolveDispatchToken accepts lower-case github_token', () => {
  const env = {
    github_token: 'github-token',
  };
  assert.equal(resolveDispatchToken(env), 'github-token');
});

test('buildOctokitInstance ignores plain object constructor fallbacks', () => {
  const core = { debug: () => {} };
  const github = {
    getOctokit: () => {
      throw new Error('missing token');
    },
  };

  const instance = buildOctokitInstance({ core, github, token: '' });
  assert.equal(instance, null);
});

test('countCheckboxes ignores fenced code blocks', () => {
  const markdown = `
- [ ] Task one
\`\`\`yaml
- [ ] Example checkbox
\`\`\`
- [x] Task two
`;

  assert.deepEqual(countCheckboxes(markdown), {
    total: 2,
    checked: 1,
    unchecked: 1,
  });
});

test('countCheckboxes ignores tilde-fenced code blocks', () => {
  const markdown = `
- [ ] Task one
~~~bash
- [x] Not a real task
~~~
- [ ] Task two
`;

  assert.deepEqual(countCheckboxes(markdown), {
    total: 2,
    checked: 0,
    unchecked: 2,
  });
});

test('extractLatestChecklist returns latest checklist even when all tasks are complete', () => {
  const botComments = [
    {
      body: '- [ ] Task one',
      updated_at: '2025-01-01T00:00:00Z',
      created_at: '2025-01-01T00:00:00Z',
    },
    {
      body: '- [x] Task one',
      updated_at: '2025-01-02T00:00:00Z',
      created_at: '2025-01-02T00:00:00Z',
    },
  ];

  const latest = extractLatestChecklist(botComments);
  assert.ok(latest);
  assert.equal(latest.total, 1);
  assert.equal(latest.unchecked, 0);
});

test('extractLatestChecklist ignores comments without checkboxes', () => {
  const botComments = [
    {
      body: 'No checklist here',
      updated_at: '2025-01-03T00:00:00Z',
      created_at: '2025-01-03T00:00:00Z',
    },
  ];

  assert.equal(extractLatestChecklist(botComments), null);
});

test('coerceNumber accepts zero when min is zero', () => {
  assert.equal(coerceNumber(0, 10, { min: 0 }), 0);
});

test('coerceNumber rejects values below min', () => {
  assert.equal(coerceNumber(0, 5, { min: 1 }), 5);
});

test('resolvePromptCheckboxCounts prefers latest checklist when it has outstanding tasks', () => {
  const scopeCounts = { total: 3, unchecked: 0 };
  const latestChecklist = { total: 3, unchecked: 1 };
  assert.deepEqual(resolvePromptCheckboxCounts(scopeCounts, latestChecklist), {
    total: 3,
    unchecked: 1,
  });
});

test('resolvePromptCheckboxCounts uses latest checklist when scope has no tasks', () => {
  const scopeCounts = { total: 0, unchecked: 0 };
  const latestChecklist = { total: 2, unchecked: 0 };
  assert.deepEqual(resolvePromptCheckboxCounts(scopeCounts, latestChecklist), {
    total: 2,
    unchecked: 0,
  });
});

test('runKeepalive summarizes and fails when instruction token is missing', async () => {
  const summary = {
    lines: [],
    addHeading(value) {
      this.lines.push(String(value));
      return this;
    },
    addRaw(value) {
      this.lines.push(String(value));
      return this;
    },
    addEOL() {
      this.lines.push('\n');
      return this;
    },
    async write() {},
  };
  let failedMessage = '';
  const core = {
    summary,
    info() {},
    setFailed(message) {
      failedMessage = message;
    },
  };

  await assert.rejects(
    () => runKeepalive({ core, github: {}, context: {}, env: {} }),
    /GitHub token is required to author keepalive instructions/
  );

  const output = summary.lines.join('');
  assert.ok(output.includes('Codex Keepalive'));
  assert.ok(output.includes('Dry run: **disabled**'));
  assert.ok(
    output.includes(
      'Failure: GitHub token is required to author keepalive instructions (app token, PAT, or GITHUB_TOKEN).'
    )
  );
  assert.ok(output.includes('Triggered keepalive count: 0'));
  assert.ok(output.includes('Refreshed keepalive count: 0'));
  assert.ok(output.includes('Skipped keepalive count: 0'));
  assert.ok(output.includes('Skipped 0 paused PRs.'));
  assert.ok(output.includes('Evaluated pull requests: 0'));
  assert.equal(
    failedMessage,
    'GitHub token is required to author keepalive instructions (app token, PAT, or GITHUB_TOKEN).'
  );
});

test('runKeepalive summarizes and fails when octokit client cannot be initialized', async () => {
  const summary = {
    lines: [],
    addHeading(value) {
      this.lines.push(String(value));
      return this;
    },
    addRaw(value) {
      this.lines.push(String(value));
      return this;
    },
    addEOL() {
      this.lines.push('\n');
      return this;
    },
    async write() {},
  };
  let failedMessage = '';
  const core = {
    summary,
    info() {},
    debug() {},
    setFailed(message) {
      failedMessage = message;
    },
  };
  const github = {
    getOctokit() {
      return null;
    },
  };

  await assert.rejects(
    () =>
      runKeepalive({
        core,
        github,
        context: {},
        env: { SERVICE_BOT_PAT: 'token' },
      }),
    /Unable to initialise Octokit client for keepalive instruction author/
  );

  const output = summary.lines.join('');
  assert.ok(output.includes('Codex Keepalive'));
  assert.ok(output.includes('Dry run: **disabled**'));
  assert.ok(
    output.includes('Failure: Unable to initialise Octokit client for keepalive instruction author.')
  );
  assert.ok(output.includes('Triggered keepalive count: 0'));
  assert.ok(output.includes('Refreshed keepalive count: 0'));
  assert.ok(output.includes('Skipped keepalive count: 0'));
  assert.ok(output.includes('Skipped 0 paused PRs.'));
  assert.ok(output.includes('Evaluated pull requests: 0'));
  assert.equal(
    failedMessage,
    'Unable to initialise Octokit client for keepalive instruction author.'
  );
});
