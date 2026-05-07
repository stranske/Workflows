'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const commentsFixture = require('./fixtures/bot-comment-handler-comments.json');
const dispositionFixtures = require('./fixtures/bot-comment-terminal-dispositions.json');

const {
  DEFAULT_BOT_AUTHORS,
  buildBotCommentDispatchComment,
  buildBotCommentsPrompt,
  buildReviewThreadTerminalDisposition,
  buildWrapperTerminalDisposition,
  collectUnresolvedBotComments,
  getBotCommentAssignees,
  isBotAuthor,
  resolveBotCommentAgent,
} = require('../bot-comment-handler.js');

const REGISTRY_PATH = path.resolve(__dirname, '..', '..', 'agents', 'registry.yml');

test('default bot author allowlist recognizes canonical review bots', () => {
  for (const login of [
    'Copilot',
    'copilot[bot]',
    'github-actions[bot]',
    'coderabbitai[bot]',
    'chatgpt-codex-connector[bot]',
  ]) {
    assert.equal(isBotAuthor(login, DEFAULT_BOT_AUTHORS), true, login);
  }
});

test('default bot author allowlist rejects human users', () => {
  assert.equal(isBotAuthor('octocat', DEFAULT_BOT_AUTHORS), false);
});

test('custom bot author input replaces the default workflow allowlist', () => {
  const custom = 'custom-reviewer[bot]';

  assert.equal(isBotAuthor('custom-reviewer[bot]', custom), true);
  assert.equal(isBotAuthor('Copilot', custom), false);
});

test('comment collection skips bot threads where a human replied by default', () => {
  const collected = collectUnresolvedBotComments(commentsFixture, {
    ignoredPaths: 'docs/,.agents/',
  });

  assert.deepEqual(
    collected.map((comment) => comment.id),
    [1005],
  );
});

test('comment collection detects nested human replies in bot threads', () => {
  const collected = collectUnresolvedBotComments([
    {
      id: 1,
      user: { login: 'copilot[bot]' },
      path: 'src/app.js',
      line: 10,
      body: 'Please adjust this.',
    },
    {
      id: 2,
      in_reply_to_id: 1,
      user: { login: 'github-actions[bot]' },
      path: 'src/app.js',
      line: 10,
      body: 'Bot follow-up.',
    },
    {
      id: 3,
      in_reply_to_id: 2,
      user: { login: 'octocat' },
      path: 'src/app.js',
      line: 10,
      body: 'Handled manually.',
    },
  ]);

  assert.deepEqual(collected, []);
});

test('comment collection keeps human-replied bot threads when configured', () => {
  const collected = collectUnresolvedBotComments(commentsFixture, {
    skipIfHumanReplied: false,
    ignoredPaths: 'docs/,.agents/',
  });

  assert.deepEqual(
    collected.map((comment) => comment.id),
    [1001, 1005],
  );
});

test('comment collection filters ignored review paths by prefix', () => {
  const collected = collectUnresolvedBotComments(commentsFixture, {
    skipIfHumanReplied: false,
    ignoredPaths: '.agents/,docs/',
  });

  assert.ok(!collected.some((comment) => comment.path.startsWith('.agents/')));
  assert.ok(!collected.some((comment) => comment.path.startsWith('docs/')));
});

test('agent routing sends agent:codex PRs to the Codex reusable runner', () => {
  const route = resolveBotCommentAgent([{ name: 'agent:codex' }], {
    registryPath: REGISTRY_PATH,
  });

  assert.equal(route.agent, 'codex');
  assert.equal(route.workflow, 'reusable-codex-run.yml');
  assert.equal(route.mode, 'explicit');
  assert.equal(route.source, 'registry');
});

test('agent routing sends agent:claude PRs to the Claude reusable runner', () => {
  const route = resolveBotCommentAgent([{ name: 'agent:claude' }], {
    registryPath: REGISTRY_PATH,
  });

  assert.equal(route.agent, 'claude');
  assert.equal(route.workflow, 'reusable-claude-run.yml');
  assert.equal(route.mode, 'explicit');
  assert.equal(route.source, 'registry');
});

test('agent routing falls back to the registry default when no agent label is present', () => {
  const route = resolveBotCommentAgent([{ name: 'bug' }], {
    registryPath: REGISTRY_PATH,
  });

  assert.equal(route.agent, 'codex');
  assert.equal(route.workflow, 'reusable-codex-run.yml');
  assert.equal(route.mode, 'default');
  assert.equal(route.source, 'registry');
});

test('agent routing documents current multiple-label fallback precedence', () => {
  const route = resolveBotCommentAgent([{ name: 'agent:codex' }, { name: 'agent:claude' }], {
    registryPath: REGISTRY_PATH,
  });

  assert.equal(route.agent, 'claude');
  assert.equal(route.workflow, 'reusable-claude-run.yml');
  assert.equal(route.source, 'legacy-fallback');
  assert.match(route.registry_error, /Multiple agent labels present/);
});

test('prepare prompt fixture preserves collected review comment context', () => {
  const collected = collectUnresolvedBotComments(commentsFixture, {
    ignoredPaths: 'docs/,.agents/',
  });
  const prompt = buildBotCommentsPrompt(collected);

  assert.match(prompt, /# Fix Bot Review Comments/);
  assert.match(prompt, /### src\/service\.js:22/);
  assert.match(prompt, /Guard against missing input\./);
  assert.match(prompt, /```diff\n@@ -20,7 \+20,7 @@/);
});

test('prepare prompt uses longer fences when comment bodies contain fences', () => {
  const prompt = buildBotCommentsPrompt([
    {
      path: 'src/app.js',
      line: 10,
      author: 'copilot[bot]',
      body: 'Use this block:\n```js\nconst x = 1;\n```',
      diff_hunk: '```diff\n-old\n+new\n```',
    },
  ]);

  assert.match(prompt, /````\nUse this block:/);
  assert.match(prompt, /````diff\n```diff/);
});

test('dispatch fixture selects the assignee and stable marker comment for Codex', () => {
  const comment = buildBotCommentDispatchComment({ agent: 'codex', count: 2 });

  assert.deepEqual(getBotCommentAssignees('codex'), ['chatgpt-codex-connector']);
  assert.match(comment, /<!-- bot-comment-handler -->/);
  assert.match(comment, /- Agent: codex/);
  assert.match(comment, /- Bot comments to address: 2/);
});

test('dispatch assignee fallbacks match registry-owned automation users', () => {
  assert.deepEqual(getBotCommentAssignees('claude'), ['stranske-automation-bot']);
  assert.deepEqual(getBotCommentAssignees('gemini'), ['stranske-automation-bot']);
});

test('reusable terminal-disposition fixtures cover found and no-op collect outcomes', () => {
  const found = buildReviewThreadTerminalDisposition(dispositionFixtures.reusableFound);
  const noop = buildReviewThreadTerminalDisposition(dispositionFixtures.reusableNoop);

  assert.equal(found.schema, 'workflows-terminal-disposition/v1');
  assert.equal(found.source_key, 'review-thread:42');
  assert.equal(found.disposition, 'unresolved-bot-comments');
  assert.equal(found.artifact_family, 'review-thread-terminal-disposition');
  assert.equal(noop.source_key, 'review-thread:43');
  assert.equal(noop.disposition, 'no-unresolved-bot-comments');
});

test('caller terminal-disposition fixtures cover reusable dispatch and wrapper no-op outcomes', () => {
  const success = buildWrapperTerminalDisposition(dispositionFixtures.wrapperSuccess);
  const noop = buildWrapperTerminalDisposition(dispositionFixtures.wrapperNoop);

  assert.equal(success.schema, 'workflows-terminal-disposition/v1');
  assert.equal(success.source_key, 'review-thread:42');
  assert.equal(success.disposition, 'reusable-invocation-expected');
  assert.equal(success.dispatch_outcome, 'reusable-expected');
  assert.equal(noop.source_key, 'review-thread:44');
  assert.equal(noop.disposition, 'wrapper-skipped');
  assert.equal(noop.dispatch_outcome, 'wrapper-skipped');
  assert.equal(noop.reason, 'missing-agent-label');
});
