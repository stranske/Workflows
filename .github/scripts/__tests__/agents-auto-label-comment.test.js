'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '../../..');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

for (const [surface, prefix] of [['Workflows', ''], ['consumer', 'templates/consumer-repo']]) {
  test(`${surface} issue labeler skips identical bot suggestions and preserves changed and fresh writes`, async () => {
    const workflow = fs.readFileSync(path.join(root, prefix, '.github/workflows/agents-auto-label.yml'), 'utf8');
    const commentStep = workflow.split('      - name: Post suggestion comment\n')[1];
    const script = commentStep.split('          script: |\n')[1];
    const fixture = require('../../../tests/fixtures/health85-20261106/issue-view-4284.json');
    const stored = fixture.comments.find(({ body }) => body.startsWith('### 🏷️ Label Suggestions\n'));
    const suggestions = [...stored.body.matchAll(/^- `([^`]+)` \((\d+%) confidence\)$/gm)]
      .map(([, name, score]) => ({ name, score }));
    assert.equal(suggestions.length, 5);

    const run = new AsyncFunction('context', 'github', 'core', 'require', 'process', script
      .replace('${{ steps.match.outputs.suggested_labels }}', JSON.stringify(suggestions))
      .replace('${{ steps.match.outputs.auto_apply_labels }}', '[]'));
    const context = { repo: { owner: 'stranske', repo: 'Workflows' }, issue: { number: 4284 } };
    const bot = { id: 42, body: stored.body, user: { type: 'Bot' } };
    const apiBase = { ...context.repo, body: stored.body };

    for (const [comments, expected] of [
      [[bot], []],
      [[{ ...bot, body: `${bot.body}\n` }], [['update', { ...apiBase, comment_id: 42 }]]],
      [[{ ...bot, user: { type: 'User' } }], [['create', { ...apiBase, issue_number: 4284 }]]],
      [[], [['create', { ...apiBase, issue_number: 4284 }]]],
    ]) {
      const writes = [];
      let paginated = false;
      const github = { rest: { issues: {
        listComments: async (params) => {
          assert.deepEqual(params, { ...context.repo, issue_number: 4284, per_page: 30 });
          return { data: comments };
        },
        updateComment: async (params) => { writes.push(['update', params]); },
        createComment: async (params) => { writes.push(['create', params]); },
      } } };
      github.paginate = async (method, params) => {
        assert.equal(method, github.rest.issues.listComments);
        paginated = true;
        return (await method(params)).data;
      };
      await run(context, github, { info() {} }, createRequire(path.join(root, 'package.json')), { env: {} });
      assert.equal(paginated, surface === 'consumer');
      assert.deepEqual(writes, expected);
    }
  });
}
