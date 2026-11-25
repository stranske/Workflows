# Keepalive deliberate-break transcripts

These transcripts record the passing and deliberately failing runs used to validate three keepalive changes. Each section links to the original file at a fixed revision. Run the commands from the repository root when examining the historical controls.

- [Workflows #3658](#workflows-3658)
- [Workflows #3661](#workflows-3661)
- [Workflows #3662](#workflows-3662)

## Workflows 3658

[Original transcript at the recorded revision](https://github.com/stranske/Workflows/blob/fbb4e424d29f3f51058b247e2be390093dca299d/.github/scripts/__tests__/evidence/issue-3658-deliberate-break-transcript.md)

### Deliberate-break evidence for Workflows #3658 / #3630

Regression command:

```bash
node --test --test-name-pattern='same-generation recovery cannot overwrite' .github/scripts/__tests__/keepalive-state.test.js
```

The regression command **must** include the explicit test file. Running the same pattern from `__tests__/` without that path loads the whole tree (~33 tests, ~32 skipped) and is not the acceptance command.

#### Passing run (exact-attempt equality guard intact)

```
✔ same-generation recovery cannot overwrite a newer running owner attempt (127.77175ms)
ℹ tests 1
ℹ suites 0
ℹ pass 1
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 4591.876375
```

#### Failing run (guard removed: `state.running_owner_attempt === recoveredAttempt` disabled)

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

## Workflows 3661

[Original transcript at the recorded revision](https://github.com/stranske/Workflows/blob/fbb4e424d29f3f51058b247e2be390093dca299d/.github/scripts/__tests__/evidence/issue-3661-deliberate-break-transcript.md)

### Deliberate-break evidence for Workflows #3661 / #3643

Regression command:

```bash
node --test .github/scripts/__tests__/keepalive-loop.test.js
```

The proof was run from Workflows `main` at `59801eeee`. The temporary break
restored the former condition in `.github/scripts/keepalive_loop.js`:

```js
const preservePendingChallenge = attemptBoundRecoveryCandidate &&
  !Object.keys(attemptBoundRecoveryMarkers).length &&
  previousAttention.disposition === 'challenge-due' &&
  /^[a-f0-9]{64}$/.test(previousAttention.generation || '');
```

That extra condition was removed again before this evidence was committed.

#### Failing run with the old condition restored

```text
✖ summary input without exact job evidence cannot reopen or ordinarily retry a consumed authority receipt
ℹ tests 181
ℹ suites 0
ℹ pass 180
ℹ fail 1
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0

AssertionError [ERR_ASSERTION]: The input did not match the regular expression
/Independent Authority Challenge Required/.

The rendered summary instead contained:
### 🔁 Paused – Automation Recovery Required

The serialized attention state also regressed from `challenge-due` to
`automation-retry`, while retaining the earlier recovery generation and owner
attempt. This is the retry race covered by #3643.
```

#### Passing run after restoring the current condition

```text
✔ summary input without exact job evidence cannot reopen or ordinarily retry a consumed authority receipt
ℹ tests 181
ℹ suites 0
ℹ pass 181
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 284.984375
```

The test harness emits expected mock warnings about
`github.rest.actions.listWorkflowRunsForRepo` while exercising paths whose
GitHub stub omits that method; they appeared in both runs and did not affect the
named red/green result.

## Workflows 3662

[Original transcript at the recorded revision](https://github.com/stranske/Workflows/blob/fbb4e424d29f3f51058b247e2be390093dca299d/.github/scripts/__tests__/evidence/issue-3662-deliberate-break-transcript.md)

### Deliberate-break evidence for Workflows #3662 / #3645

Regression command:

```bash
node --test .github/scripts/__tests__/keepalive-reporter-applicability.test.js
```

The proof was run from Workflows `main` at `446b932ff`. The temporary break
replaced the ordinary-dispatch result in
`.github/scripts/keepalive_reporter_applicability.js` with:

```js
return { status: 'skip' };
```

The current `{ status: 'continue', prNumber, targetSource:
'ordinary-run-name' }` result was restored before this evidence was committed.

#### Failing run with the temporary skip result

```text
✖ .github/workflows/agents-keepalive-loop.yml: ordinary unassociated dispatch recovers its canonical PR target
✖ templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml: ordinary unassociated dispatch recovers its canonical PR target
ℹ tests 26
ℹ suites 0
ℹ pass 24
ℹ fail 2
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0

AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
+ actual - expected

  {
+   status: 'skip'
-   prNumber: 1738,
-   status: 'continue',
-   targetSource: 'ordinary-run-name'
  }
```

Both production workflow sources failed the same canonical PR-1738 assertion.

#### Passing run after restoring the current result

```text
✔ .github/workflows/agents-keepalive-loop.yml: ordinary unassociated dispatch recovers its canonical PR target
✔ templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml: ordinary unassociated dispatch recovers its canonical PR target
ℹ tests 26
ℹ suites 0
ℹ pass 26
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 79.473333
```
