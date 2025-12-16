'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  dispatchKeepaliveCommand,
} = require(path.join(__dirname, '../../../scripts/keepalive-runner.js'));

function createCore() {
  return {
    debugMessages: [],
    info() {},
    warning() {},
    setFailed() {},
    debug(message) {
      this.debugMessages.push(message);
    },
  };
}

test('dispatchKeepaliveCommand uses github.getOctokit when available', async () => {
  const events = [];
  const octokit = {
    rest: {
      repos: {
        async createDispatchEvent(input) {
          events.push(input);
        },
      },
    },
  };

  const github = {
    getOctokit(token) {
      assert.equal(token, 'token-123');
      return octokit;
    },
  };

  await dispatchKeepaliveCommand({
    core: createCore(),
    github,
    owner: 'stranske',
    repo: 'Trend_Model_Project',
    token: 'token-123',
    payload: { issue: 99, comment_id: 1, trace: 'tr123', round: 2 },
  });

  assert.equal(events.length, 1);
  assert.equal(events[0].owner, 'stranske');
  assert.equal(events[0].repo, 'Trend_Model_Project');
  // Verify nested structure to stay under 10 top-level property limit
  assert.deepEqual(events[0].client_payload, {
    issue: 99,
    base: '',
    head: '',
    agent: 'codex',
    instruction_body: '',
    meta: {
      comment_id: 1,
      comment_url: '',
      round: 2,
      trace: 'tr123',
    },
    quiet: true,
    reply: 'none',
  });
});

test('dispatchKeepaliveCommand falls back to github.constructor when getOctokit is unavailable', async () => {
  const events = [];
  function FakeOctokit({ auth }) {
    this.auth = auth;
    this.rest = {
      repos: {
        createDispatchEvent: async (input) => {
          events.push({ auth: this.auth, input });
        },
      },
    };
  }

  const github = {
    constructor: FakeOctokit,
  };

  await dispatchKeepaliveCommand({
    core: createCore(),
    github,
    owner: 'owner-co',
    repo: 'repo-co',
    token: 'token-abc',
    payload: { issue: 100, comment_id: 2, comment_url: 'https://example.com', trace: 'abc', round: 1 },
  });

  assert.equal(events.length, 1);
  assert.equal(events[0].auth, 'token-abc');
  assert.equal(events[0].input.owner, 'owner-co');
  assert.equal(events[0].input.repo, 'repo-co');
  assert.equal(events[0].input.client_payload.quiet, true);
  assert.equal(events[0].input.client_payload.reply, 'none');
  // Verify nested meta structure
  assert.equal(events[0].input.client_payload.meta.comment_id, 2);
  assert.equal(events[0].input.client_payload.meta.comment_url, 'https://example.com');
  assert.equal(events[0].input.client_payload.meta.trace, 'abc');
  assert.equal(events[0].input.client_payload.meta.round, 1);
});

test('dispatchKeepaliveCommand throws when token is missing', async () => {
  await assert.rejects(
    dispatchKeepaliveCommand({
      core: createCore(),
      github: {},
      owner: 'o',
      repo: 'r',
      token: '',
      payload: { issue: 1 },
    }),
    /ACTIONS_BOT_PAT is required/
  );
});

test('dispatchKeepaliveCommand throws when Octokit lacks createDispatchEvent', async () => {
  const octokit = { rest: { repos: {} } };
  const github = {
    getOctokit() {
      return octokit;
    },
  };

  await assert.rejects(
    dispatchKeepaliveCommand({
      core: createCore(),
      github,
      owner: 'o',
      repo: 'r',
      token: 'token',
      payload: { issue: 1 },
    }),
    /Octokit instance missing repos\.createDispatchEvent/
  );
});
