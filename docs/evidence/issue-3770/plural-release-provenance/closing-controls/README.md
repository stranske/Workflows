# Release acceptance and closing-source controls

Both production fixtures were compared with GitHub PRs #3769 and #3787:
complete body, title, release branch and head SHA match (`fixture-parity.json`).
Trusted author/repository and transport responses remain synthetic test inputs.

The named suites now verify every fixture task and acceptance item survives in
the generated context. The acceptance inventory contains only the release PR
when no genuine issue source is declared. New #3787 controls append genuine
`Fix #123` and `Closes #123` directives, including an explicit local-request
declaration. Both source resolvers require issue #123; both real context builders
retrieve its acceptance or report required discovery unavailable for inaccessible
issues and PR-shaped responses. Body and title directives are covered by the
resolver controls. Existing Related-to, metadata, branch, ambiguity and malformed
source tests remain in the same suites.

The required command exits 0:

```sh
node --test .github/scripts/__tests__/source-context.test.js .github/scripts/__tests__/agents-verifier-context.test.js
```

Node 24 in this runner summarizes isolated files without individual test names.
The retained complete output adds `--test-isolation=none` to expose all 176 named
tests. Captured console lines have trailing whitespace removed. The same two
files are executed in both commands; `receipt.json` records
the commands and exit codes.

Independent root-only and consumer-only restoration of the merged `52712f28`
resolver reproduces `github_issue` #3782 and required discovery: 12 tests fail
in each experiment. Restoring the root resolver from `52712f28^` reproduces
required issue #3768 for release #3769: 22 tests fail. Each fixed-byte restoration
passes all 176 tests. RED/GREEN output, classifications and source hashes are
retained here; the fixed parser hash matches the preceding repair evidence.
Both parser and verifier-context `cmp` commands exit 0. Production code requires
no further change for these controls.

Template sync and completeness validation pass. Completeness uses
`GITHUB_STEP_SUMMARY=/tmp/release-template-summary.md` because the inherited
Actions summary path is read-only in the local sandbox. `git diff --check` passes.

Original runs 37400729553 and 37481681340 remain CONCERNS/NON_PASS. No provider
verdict or post-merge comparison is inferred from unit results. After merge,
Orphan Steward owns the single repaired-input comparison and complete artifact
inventory; source #3757 topology and observed provider verdicts remain required.
