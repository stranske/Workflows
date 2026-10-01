# Deliberate-break evidence for Workflows #3661 / #3643

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

## Failing run with the old condition restored

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

## Passing run after restoring the current condition

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
