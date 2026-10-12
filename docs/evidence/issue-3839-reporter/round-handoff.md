This round added 36 authored-resolver regressions for invalid/empty manual inputs, immutable-index targets, and run/attempt/head/event/producer mismatches. Output snapshots verify that every unresolved PR lock is empty before summary publication and at resolution failure.

Validation: 56 resolver cases passed; 139 focused workflow cases passed; 29 classifier/replay cases passed; Ruff/template checks passed; full Black 26.10.0 passed for 698 files using a sandbox event-loop wakeup workaround. Fresh logs, JUnit, hashes and launcher source are retained in docs/evidence/issue-3839-reporter/round-validation.json. The original production mutation artifacts were verified unchanged, including six failing cases and six restored passes; workflow files were only read this round.

Delivery blocker: the workspace .git directory is read-only (git add fails creating index.lock). The meaningful source commit bbd6d5d2 was created in /tmp/issue-3839-reporter-commit.git, and its patch is available in the shared workspace at docs/evidence/issue-3839-reporter/round-commit.patch. Apply it to the PR branch in a writable checkout, then run current-head CI. The latest PR body already has all 17 original items checked; no checklist edit was needed. The PR remains open and ready for review.

GitHub delivery note: the label and comment tools each returned `MCP tool call requires approval, but approval policy is never`. Neither mutation was applied. Latest readiness check: PR #3841 is open with draft=false.

