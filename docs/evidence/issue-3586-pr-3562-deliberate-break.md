# PR #3562 deliberate-break and re-verification evidence

Issue [#3586](https://github.com/stranske/Workflows/issues/3586) records that merged
PR [#3562](https://github.com/stranske/Workflows/pull/3562) did not preserve the
deliberate-break transcript and live provider-comparison evidence required by source issue
[#3419](https://github.com/stranske/Workflows/issues/3419). The original reviewed head was
`1a951e8b39cfd2d3b2c63dc66366ef06dd5f9c3d`, and the squash merge was
`05d1d4fc109359738bb031ea6325703768a2c734`.

## Current deliberate-break reproduction

The sibling-contamination regression remains reproducible on `main`. On 2026-09-28, at
base commit `f07317b2de277d02c081580e4f93ec1f27bad224`, the merged-PR selector in
`.github/scripts/agents_verifier_context.js` was temporarily disabled. That deliberate
break restored the historical `baseSha...headSha` local-diff path for a merged PR. No test
assertion was changed.

Command:

```text
node --test .github/scripts/__tests__/agents-verifier-context.test.js
```

Raw failure summary with the deliberate break present:

```text
✖ buildVerifierContext uses the authoritative PR diff after the base advances
✖ buildVerifierContext file summary lists only files from the merged PR
✖ buildVerifierContext skips when the authoritative merged PR diff is unavailable
ℹ tests 34
ℹ suites 0
ℹ pass 31
ℹ fail 3
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0

AssertionError [ERR_ASSERTION]: merged PRs must not use a base...merge local range
1 !== 0

The input was expected to not match /src\/sibling\.js/. Input:
### File changes
- src/sibling.js (added) (+1/-0)
- src/pr-only.js (added) (+1/-0)

Error: merged PR verification must not fall back to a contaminated local range
```

The production selector was restored exactly. `git diff --exit-code` then proved both the
root and consumer-template verifier scripts had no residual source change, and the same
command passed:

```text
ℹ tests 34
ℹ suites 0
ℹ pass 34
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
```

This is a current fail-to-pass proof for the exact merged-PR contamination gates. It does
not claim that the output was captured during the historical PR #3562 implementation run.

## Advanced-base provider report

The post-merge provider comparison for PR #3562 is preserved at
[#3562 comment 5820810797](https://github.com/stranske/Workflows/pull/3562#issuecomment-5820810797).
The report explicitly evaluates the advanced-base sibling-commit case, states that the full
diff and file list contain only the subject PR files, and records an OpenAI `PASS` verdict
at 88% confidence. It names no unrelated file and raises no false scope-creep caveat.

The Anthropic row is `CONCERNS` only because its provider invocation hit an account usage
limit; the report records no code or scope finding from that provider. The available
provider evidence therefore satisfies the live re-verification criterion without
misrepresenting provider availability as a product defect.
