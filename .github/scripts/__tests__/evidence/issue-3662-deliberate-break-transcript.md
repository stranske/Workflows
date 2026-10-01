# Deliberate-break evidence for Workflows #3662 / #3645

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

## Failing run with the temporary skip result

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

## Passing run after restoring the current result

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
