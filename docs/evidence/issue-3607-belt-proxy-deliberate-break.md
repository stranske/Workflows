# Belt proxy-invariant deliberate-break evidence

Issue [#3607](https://github.com/stranske/Workflows/issues/3607) records the evidence
gap left after [PR #3587](https://github.com/stranske/Workflows/pull/3587) merged as
`a8f1e458014b1a296702ccfe1fd5b7093289e5b8`. The production and test changes are
already on `main`; this document preserves the missing current RED/GREEN transcript and
the exact-head scheduled-workflow evidence without claiming that the transcript was
captured during the historical implementation run.

## Current deliberate break

On 2026-09-28, at base commit `0dd9fc8f2d530255758ca77beacd11b244008e5f`,
`.github/scripts/github-rate-limited-wrapper.js` was temporarily changed back to the
historical pass-through behavior: every function returned by the top-level proxy getter
was bound to the target. The descriptor-aware `readProxyProperty` path was temporarily
removed. No test or assertion was changed.

Command:

```text
node --test .github/scripts/__tests__/github-api-with-retry.test.js
```

Literal failing output for the named invariant test:

```text
✖ checkRateLimitStatus works on createRateLimitedGithub wrapped client (2.241959ms)
ℹ tests 29
ℹ suites 0
ℹ pass 28
ℹ fail 1
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 1004.064834

✖ failing tests:

test at .github/scripts/__tests__/github-api-with-retry.test.js:815:1
✖ checkRateLimitStatus works on createRateLimitedGithub wrapped client (2.241959ms)
  TypeError [Error]: 'get' on proxy: property '__getTokenSource' is a read-only and non-configurable data property on the proxy target but the proxy did not return its actual value (expected '() => currentTokenSource' but got 'function () { [native code] }')
      at TestContext.<anonymous> (<worktree>/.github/scripts/__tests__/github-api-with-retry.test.js:837:24)
      at async Test.run (node:internal/test_runner/test:1069:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:752:7)
```

`<worktree>` above replaces only the absolute automation checkout prefix from the raw
stack trace. The production implementation was then restored exactly. A source diff
check showed no residual change in `.github/scripts/github-rate-limited-wrapper.js`.

## Restored pass

The same command passed after restoration. Literal success output for the named test and
the Node test-runner summary:

```text
✔ checkRateLimitStatus works on createRateLimitedGithub wrapped client (4.618458ms)
ℹ tests 29
ℹ suites 0
ℹ pass 29
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 1406.70175
```

This is a current, falsifiable fail-to-pass proof that the descriptor-aware getter
prevents the `__getTokenSource` proxy-invariant regression.

## Exact merge-head scheduled workflow

Scheduled Agents 70 run
[`36289582514`](https://github.com/stranske/Workflows/actions/runs/36289582514)
started at `2026-09-27T02:48:34Z`, after PR #3587 merged, and ran at exact head
`a8f1e458014b1a296702ccfe1fd5b7093289e5b8`. The run completed successfully.

Its
[`Execute / Scan belt promotion queue`](https://github.com/stranske/Workflows/actions/runs/36289582514/job/108537139073)
job completed successfully, including the `Preflight API budget and identify ready belt
PRs` step. The exact merge-head scheduled run therefore exercised the repaired wrapper
without the historical `TypeError`.
