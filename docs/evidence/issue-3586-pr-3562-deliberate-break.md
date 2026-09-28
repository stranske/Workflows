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

Complete captured output with the deliberate break present (the absolute checkout prefix
in stack traces is normalized to `<worktree>`; no output lines are omitted):

```text
✔ buildVerifierContext skips when pull request is not merged (2.44475ms)
✔ buildVerifierContext resolves PR from VERIFIER_PR_NUMBER (5.783125ms)
✔ buildVerifierContext skips when VERIFIER_PR_NUMBER PR is not merged (0.211833ms)
✔ buildVerifierContext warns on invalid VERIFIER_PR_NUMBER and falls back (1.324375ms)
✔ buildVerifierContext allows non-default base branches when acceptance criteria exist (1.572709ms)
✔ buildVerifierContext skips forked pull requests (0.151375ms)
✔ buildVerifierContext skips when no acceptance criteria found (0.472625ms)
✔ buildVerifierContext skips bound recurring corpus data-job PRs despite stale closing issues (0.334292ms)
✔ buildVerifierContext runs when acceptance criteria exists in linked issue (2.286208ms)
✔ buildVerifierContext uses custom ciWorkflows when provided (1.374583ms)
✔ buildVerifierContext writes verifier context with linked issues (1.557083ms)
✔ buildVerifierContext writes diff summary for LLM context (1.654833ms)
✖ buildVerifierContext uses the authoritative PR diff after the base advances (1.541209ms)
✖ buildVerifierContext file summary lists only files from the merged PR (0.91725ms)
✖ buildVerifierContext skips when the authoritative merged PR diff is unavailable (0.846458ms)
✔ buildVerifierContext queries CI runs for merge and head SHAs (1.110791ms)
✔ buildVerifierContext queries CI runs with merge commit SHA (0.723667ms)
✔ buildVerifierContext selects CI results for the merge commit SHA (1.22475ms)
✔ buildVerifierContext uses API url when html_url is missing (0.8885ms)
✔ buildVerifierContext falls back to head SHA when merge runs are missing (0.634292ms)
✔ buildVerifierContext uses merge commit SHA for push events (1.383458ms)
✔ buildVerifierContext skips push events without a commit SHA (0.446834ms)
✔ buildVerifierContext skips push events with no associated PR (0.101375ms)
✔ buildVerifierContext skips push events when PR lookup fails (0.097792ms)
✔ formatDiffForContext truncates long diffs (0.039375ms)
✔ formatDiffForContext returns placeholder for empty diff (0.031625ms)
✔ isValidSha validates hex shas (0.092834ms)
✔ fetchLocalGitDiff skips invalid shas (0.038542ms)
✔ fetchLocalGitDiff returns diff output when exec succeeds (0.058416ms)
✔ buildVerifierContext extracts chain_depth from issue body marker (0.703959ms)
✔ buildVerifierContext outputs chain_depth 0 when no marker present (0.504625ms)
✔ buildVerifierContext detects follow-up label as depth 1 (0.441584ms)
✔ buildVerifierContext includes chain depth in context markdown (0.418083ms)
✔ buildVerifierContext flags ciFailed when a CI workflow concluded failure on the merge commit (0.643709ms)
ℹ tests 34
ℹ suites 0
ℹ pass 31
ℹ fail 3
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 108.262584

✖ failing tests:

test at .github/scripts/__tests__/agents-verifier-context.test.js:762:1
✖ buildVerifierContext uses the authoritative PR diff after the base advances (1.541209ms)
AssertionError [ERR_ASSERTION]: merged PRs must not use a base...merge local range

1 !== 0

    at TestContext.<anonymous> (<worktree>/.github/scripts/__tests__/agents-verifier-context.test.js:766:12)
    at async Test.run (node:internal/test_runner/test:1069:7)
    at async Test.processPendingSubtests (node:internal/test_runner/test:752:7) {
  generatedMessage: false,
  code: 'ERR_ASSERTION',
  actual: 1,
  expected: 0,
  operator: 'strictEqual'
}

test at .github/scripts/__tests__/agents-verifier-context.test.js:779:1
✖ buildVerifierContext file summary lists only files from the merged PR (0.91725ms)
AssertionError [ERR_ASSERTION]: The input was expected to not match the regular expression /src\/sibling\.js/. Input:

'## PR Diff Summary\n' +
  '\n' +
  '- Files changed: 2\n' +
  '- Total additions: 2\n' +
  '- Total deletions: 0\n' +
  '\n' +
  '### File changes\n' +
  '- src/sibling.js (added) (+1/-0)\n' +
  '- src/pr-only.js (added) (+1/-0)'

    at TestContext.<anonymous> (<worktree>/.github/scripts/__tests__/agents-verifier-context.test.js:783:12)
    at async Test.run (node:internal/test_runner/test:1069:7)
    at async Test.processPendingSubtests (node:internal/test_runner/test:752:7) {
  generatedMessage: true,
  code: 'ERR_ASSERTION',
  actual: '## PR Diff Summary\n\n- Files changed: 2\n- Total additions: 2\n- Total deletions: 0\n\n### File changes\n- src/sibling.js (added) (+1/-0)\n- src/pr-only.js (added) (+1/-0)',
  expected: /src\/sibling\.js/,
  operator: 'doesNotMatch'
}

test at .github/scripts/__tests__/agents-verifier-context.test.js:791:1
✖ buildVerifierContext skips when the authoritative merged PR diff is unavailable (0.846458ms)
Error: merged PR verification must not fall back to a contaminated local range
    at fetchLocalDiff (<worktree>/.github/scripts/__tests__/agents-verifier-context.test.js:823:13)
    at buildVerifierContext (<worktree>/.github/scripts/agents_verifier_context.js:657:16)
    at async TestContext.<anonymous> (<worktree>/.github/scripts/__tests__/agents-verifier-context.test.js:818:18)
    at async Test.run (node:internal/test_runner/test:1069:7)
    at async Test.processPendingSubtests (node:internal/test_runner/test:752:7)
```

The production selector was restored exactly. `git diff --exit-code` then proved both the
root and consumer-template verifier scripts had no residual source change. Complete
captured output from the restored run:

```text
✔ buildVerifierContext skips when pull request is not merged (2.193333ms)
✔ buildVerifierContext resolves PR from VERIFIER_PR_NUMBER (5.233875ms)
✔ buildVerifierContext skips when VERIFIER_PR_NUMBER PR is not merged (0.16925ms)
✔ buildVerifierContext warns on invalid VERIFIER_PR_NUMBER and falls back (1.450791ms)
✔ buildVerifierContext allows non-default base branches when acceptance criteria exist (0.894916ms)
✔ buildVerifierContext skips forked pull requests (0.115583ms)
✔ buildVerifierContext skips when no acceptance criteria found (0.565709ms)
✔ buildVerifierContext skips bound recurring corpus data-job PRs despite stale closing issues (0.480125ms)
✔ buildVerifierContext runs when acceptance criteria exists in linked issue (0.916417ms)
✔ buildVerifierContext uses custom ciWorkflows when provided (0.87775ms)
✔ buildVerifierContext writes verifier context with linked issues (1.929458ms)
✔ buildVerifierContext writes diff summary for LLM context (1.510542ms)
✔ buildVerifierContext uses the authoritative PR diff after the base advances (1.833833ms)
✔ buildVerifierContext file summary lists only files from the merged PR (0.946083ms)
✔ buildVerifierContext skips when the authoritative merged PR diff is unavailable (0.272625ms)
✔ buildVerifierContext queries CI runs for merge and head SHAs (0.601042ms)
✔ buildVerifierContext queries CI runs with merge commit SHA (0.556083ms)
✔ buildVerifierContext selects CI results for the merge commit SHA (0.630792ms)
✔ buildVerifierContext uses API url when html_url is missing (0.507791ms)
✔ buildVerifierContext falls back to head SHA when merge runs are missing (1.009291ms)
✔ buildVerifierContext uses merge commit SHA for push events (1.125041ms)
✔ buildVerifierContext skips push events without a commit SHA (0.104583ms)
✔ buildVerifierContext skips push events with no associated PR (0.076208ms)
✔ buildVerifierContext skips push events when PR lookup fails (0.701625ms)
✔ formatDiffForContext truncates long diffs (0.066084ms)
✔ formatDiffForContext returns placeholder for empty diff (0.031042ms)
✔ isValidSha validates hex shas (0.240667ms)
✔ fetchLocalGitDiff skips invalid shas (0.056958ms)
✔ fetchLocalGitDiff returns diff output when exec succeeds (0.068791ms)
✔ buildVerifierContext extracts chain_depth from issue body marker (0.667916ms)
✔ buildVerifierContext outputs chain_depth 0 when no marker present (0.899875ms)
✔ buildVerifierContext detects follow-up label as depth 1 (0.541708ms)
✔ buildVerifierContext includes chain depth in context markdown (0.46975ms)
✔ buildVerifierContext flags ciFailed when a CI workflow concluded failure on the merge commit (0.6495ms)
ℹ tests 34
ℹ suites 0
ℹ pass 34
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 100.381459
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
