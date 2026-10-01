# Deliberate-break evidence for Workflows #3658 / #3630

Regression command:

```bash
node --test --test-name-pattern='same-generation recovery cannot overwrite' .github/scripts/__tests__/keepalive-state.test.js
```

## Passing run (exact-attempt equality guard intact)

```
✔ same-generation recovery cannot overwrite a newer running owner attempt (224.099041ms)
ℹ tests 1
ℹ suites 0
ℹ pass 1
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 1100.776125
```

## Failing run (guard removed: `state.running_owner_attempt === recoveredAttempt` disabled)

```
✖ same-generation recovery cannot overwrite a newer running owner attempt (13.618584ms)
ℹ tests 1
ℹ suites 0
ℹ pass 0
ℹ fail 1
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 318.953542

✖ failing tests:

test at .github/scripts/__tests__/keepalive-state.test.js:454:1
✖ same-generation recovery cannot overwrite a newer running owner attempt (13.618584ms)
  AssertionError [ERR_ASSERTION]: Missing expected rejection.
      at async TestContext.<anonymous> (/Users/teacher/.codex/automations/pd-workloop-resume/worktrees/Workflows-issue-3658/.github/scripts/__tests__/keepalive-state.test.js:466:3)
      at async Test.run (node:internal/test_runner/test:1069:7)
      at async startSubtestAfterBootstrap (node:internal/test_runner/harness:332:3) {
    generatedMessage: false,
    code: 'ERR_ASSERTION',
    actual: undefined,
    expected: /does not match the recovered generation/,
    operator: 'rejects'
  }
```

Guard location: `summaryMatchesRecoveredAuthority` in `keepalive_state.js` (running summary requires recovered attempt to match `running_owner_attempt`).
