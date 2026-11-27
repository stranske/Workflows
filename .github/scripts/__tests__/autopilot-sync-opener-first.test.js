'use strict';

const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const { evaluateEligibility } = require('../../actions/agent-event-eligibility/eligibility');

const root = path.resolve(__dirname, '../../..');
const current = '.github/workflows/agents-auto-pilot.yml';
const pilot = 'sync:opener-first';
const autopilot = 'agents:auto-pilot';
const issuer = { id: 23046322 };
const body = '<!-- sync-core opener-first/v1 -->\n<!-- sync-core/v1 handoff fp=b50b00ace19e26c4 -->\n## Why\n';
const event = (action, label, labels) => ({
  action,
  label: { name: label },
  sender: issuer,
  issue: { number: 1472, user: issuer, state: 'open', body, labels: labels.map(name => ({ name })) },
});

for (const relative of [current, `templates/consumer-repo/${current}`]) {
  test(`${relative} routes the authenticated handoff and preserves independent events`, async () => {
    const workflow = readFileSync(path.join(root, relative), 'utf8');
    const generic = workflow.match(/expected-actions: ([^\n]+)\n\s+custom-predicate: >-\n([\s\S]*?)\n\n/);
    const step = workflow.match(/id: sync_opener_first\n[\s\S]*?script: \|\n([\s\S]*?)\n\n  # ── Main auto-pilot job/);
    assert.ok(step, 'first-opportunity action is wired into the workflow');
    const control = new Function('context', 'process', 'core', step[1]);
    assert.match(workflow, /outputs:\n\s+proceed:.*sync_opener_first/);
    const checked = (name, payload) => evaluateEligibility({
      eventName: name, payload, expectedActions: generic[1], customPredicate: generic[2],
    }).shouldRun;
    const admitted = (payload, issuerId = issuer.id) => {
      let proceed = true;
      control({ payload }, { env: { SYNC_CORE_OPENER_FIRST_ISSUER_ID: String(issuerId || '') } }, {
        setOutput: (name, value) => {
          assert.equal(name, 'proceed');
          proceed = value === 'true';
        },
        info: () => {},
      });
      return checked('issues', payload) && proceed;
    };
    const first = event('labeled', autopilot, [autopilot, pilot, 'sync', 'automated']);
    assert.equal(admitted(first), false, 'enrolled producer receives the first opportunity');
    assert.equal(admitted({ ...first, issue: { ...first.issue, body: body.replace('b50b00ace19e26c4', 'abc123def456') } }),
      false, 'structural finding fingerprints also qualify');
    assert.equal(admitted({ ...first, issue: { ...first.issue, body: body.replace('b50b00ace19e26c4', 'wrong') } }),
      true, 'a malformed fingerprint does not reserve an issue');
    assert.equal(admitted(first, ''), true, 'a receiver outside the pilot keeps its legacy trigger');
    assert.equal(admitted({ ...first, issue: { ...first.issue, user: { id: 99 } } }), true, 'copied markers cannot opt in');
    assert.equal(admitted({ ...first, sender: { id: 99 } }), true, 'ordinary operator label activity retains legacy behavior');
    assert.equal(admitted({ ...first, issue: { ...first.issue, body: 'ordinary issue' } }), true);
    const fallback = event('unlabeled', pilot, [autopilot, 'sync', 'automated']);
    assert.equal(admitted(fallback), true, 'trusted pilot release reaches the original Auto-Pilot');
    assert.equal(admitted({ ...fallback, sender: { id: 99 } }), false);
    assert.equal(admitted(fallback, ''), false);
    assert.equal(admitted(event('unlabeled', pilot, ['sync', 'automated'])), false);
    assert.equal(admitted(event('unlabeled', pilot, [autopilot, 'sync', 'automated', 'agents:paused'])), false);
    assert.equal(admitted(event('unlabeled', 'agents:paused', [autopilot, 'sync', 'automated'])), false);
    assert.equal(checked('workflow_dispatch', { inputs: { issue_number: 1472 } }), true);
    assert.equal(checked('pull_request', { action: 'closed', pull_request: { labels: [{ name: autopilot }] } }), true);
  });
}
