# Issue #3989 completion classification verification

Verified on 2026-10-17, starting from `ad0b61b088c3f883dc3ef137c2728f1363e70c40`.

The completion classifier already recognized the Codex quota message and Cursor
HTTP 429. This change removes retry timing as an independent quota signal:
connection resets and HTTP 503 messages containing "try again in/at" persist as
`failed`, without an immediate agent switch or an `agent:rate-limited` label.
Root and consumer script copies are identical. Their existing sync-manifest
ownership and file scope are unchanged.

The targeted command was identical for the deliberate break and restoration:

```sh
node --test .github/scripts/__tests__/agent-delegation-policy.test.js .github/scripts/__tests__/keepalive-loop.test.js
```

This restricted sandbox cannot reliably run Node's default child-process test
isolation or pipe input to synchronous Python subprocesses. Both runs used
`NODE_OPTIONS='--require=/tmp/keepalive-test-runtime.cjs --experimental-test-isolation=none'`
and an empty `GITHUB_OUTPUT`. The temporary runtime shim passed each subprocess's
existing input through a temporary regular file descriptor instead of a pipe;
assertions, provider output, Python completion writer, stored receipts, and
policy decisions were unchanged. Clearing `GITHUB_OUTPUT` prevented test CLI
calls from writing to the hosting action's read-only output file. The ordinary
command without this environment workaround still needs CI verification.

For the deliberate break, only the quota branch of root `classifyCompletion`
was temporarily changed to return `no_progress`. The full targeted run exited 1
with 232 passed and 2 failed. The integrated assertion failed before checking
the persisted classification:

```text
✖ persisted provider quota drives same-evaluate switch with zero stalled rounds and clears on progress (110.96725ms)
  AssertionError [ERR_ASSERTION]: persisted quota must switch in the same evaluate

  'codex' !== 'cursor'
```

After restoring `rate_limited`, the identical command and environment exited 0:

```text
✔ persisted provider quota drives same-evaluate switch with zero stalled rounds and clears on progress (634.819878ms)
ℹ tests 234
ℹ suites 0
ℹ pass 234
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 1399.322083
```

The passing replay exercises provider classification, the Python
`record-completion` CLI and comment receipt, same-evaluate routing with no prior
stalled rounds, rate-limit label addition and later progress cleanup, explicit
agent routing, and pool filtering. The added negative replay verifies that retry
advice alone does not rotate agents or add the rate-limit label. Syntax checks,
`git diff --check`, and byte comparison of root/consumer scripts also passed.

GitHub API access failed with `error connecting to api.github.com`, so these
outcomes could not be copied into the PR body. No PR checkbox was updated.
Post-merge live/replayed label-timeline evidence, the 48-hour fleet cleanup check,
and consumer sync remain unverified.

Publication: this evidence is committed in the PR history through `4584495a1d03db74bd9b49ae89472c435967a269`.