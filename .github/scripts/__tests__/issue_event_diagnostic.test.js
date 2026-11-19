'use strict';

const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const workflow = readFileSync(path.join(__dirname, '../../workflows/agents-debug-issue-event.yml'), 'utf8');
const script = workflow.split('          script: |\n')[1];
const run = new (Object.getPrototypeOf(async function () {}).constructor)('github', 'context', 'core', 'process', 'require', script);

async function inspect(eventId, event) {
  let report;
  const github = {rest: {issues: {
    get: async () => ({data: {number: 4501, labels: [{name: 'priority:high'}]}}),
    getEvent: async () => {
      assert.ok(eventId);
      return {data: event};
    },
  }}};
  await run(github, {repo: {owner: 'stranske', repo: 'Workflows'}},
    {info: line => { report = JSON.parse(line); }},
    {env: {ISSUE_NUMBER: '4501', EVENT_ID: eventId}}, require('node:module').createRequire(path.resolve('package.json')));
  return report;
}

test('the original trigger label may already have been removed', async () => {
  const event = {id: 17, issue: {number: 4501}, event: 'labeled', label: {name: 'agents:debug'}};
  const historical = await inspect('17', event);
  assert.deepEqual(historical.current_agent_labels, []);
  assert.deepEqual(historical.label_event, {id: 17, action: 'labeled', label: 'agents:debug', agent_label: true});
  assert.deepEqual(await inspect(''), {issue: 4501, current_labels: ['priority:high'], current_agent_labels: []});
  await assert.rejects(inspect('17', {...event, issue: {number: 4701}}), /label change on issue #4501/);
  await assert.rejects(inspect('17', {...event, event: 'closed'}), /label change on issue #4501/);
});
