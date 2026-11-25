'use strict';

const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { join } = require('node:path');
const test = require('node:test');

const summaryScript = join(__dirname, '../write_dispatch_summary.sh');

function summary(reason, {
  path = 'comment',
  active = '0',
  pr = '4784',
  activation = '7144350369',
  head = '088aeb4c4acdc569001aa26ad6e0a43d34049878',
  agent = '',
} = {}) {
  return execFileSync('bash', [summaryScript], {
    encoding: 'utf8',
    env: {
      PATH: process.env.PATH,
      PATH_LABEL: path,
      DISPATCH: 'false',
      DISPATCH_REASON: reason,
      PR_NUMBER: pr,
      ACTIVATION_ID: activation,
      HEAD_SHA: head,
      DISPATCH_AGENT: agent,
      RUN_CAP: '1',
      ACTIVE_RUNS: active,
    },
  }).trim();
}

test('preserves the missing-label denial of the recorded PR #4784 comment', () => {
  assert.equal(summary('gate-blocked:keepalive-label-missing'),
    'DISPATCH: ok=false path=comment reason=missing-label pr=#4784 ' +
    'activation=7144350369 agent=? head=088aeb4 cap=1 active=0 trace=-');
});

test('separates a missing human activation on an otherwise green Gate from a Gate failure', () => {
  const receipt = {
    pr: '1099',
    activation: '7070107180',
    head: '145f93e5df1231ef623e1a4e0bb9cac35df43816',
    agent: 'codex',
  };
  const suffix = 'pr=#1099 activation=7070107180 agent=codex head=145f93e cap=1 active=0 trace=-';
  assert.equal(summary('gate-blocked:gate-not-success', receipt),
    'DISPATCH: ok=false path=comment reason=gate-failed ' + suffix);
  assert.equal(summary('gate-blocked:no-human-activation', receipt),
    'DISPATCH: ok=false path=comment reason=no-human-activation ' + suffix);
});

test('reports the same cap disposition from Comment and Gate', () => {
  assert.equal(summary('gate-blocked:run-cap-reached', { active: '1' }),
    'DISPATCH: ok=false path=comment reason=cap-reached pr=#4784 ' +
    'activation=7144350369 agent=? head=088aeb4 cap=1 active=1 trace=-');
  assert.match(summary('run-cap-reached', { path: 'gate', active: '1' }),
    /^DISPATCH: ok=false path=gate reason=cap-reached /);
});

test('retains the generic denial and existing rejected-comment disposition', () => {
  assert.match(summary('gate-blocked:keepalive-paused'),
    /^DISPATCH: ok=false path=comment reason=gate-failed /);
  assert.match(summary('gate-blocked:unrecognized'),
    /^DISPATCH: ok=false path=comment reason=gate-failed /);
  assert.match(summary('missing-round'),
    /^DISPATCH: ok=false path=comment reason=no-human-activation /);
});
