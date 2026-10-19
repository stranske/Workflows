# Verifier and post-Gate failure/interruption evidence-path audit (F48)

Bounded audit of the seam between outcome resolution and durable evidence
(metrics, terminal-disposition records, tracker issues, snapshots). Reviewed
source `bbaff1e8c56f25750841e274b60835dc31d9e42f`; re-read at the current head.
No issues are filed and no provider policy changes here; additional findings
return for human review.

Dispositions: **confirmed** (defect, executable evidence), **intentional**,
**unknown** (no execution evidence; would need the named input).

| # | Entry | Contract / sink | Producer -> consumer | Evidence | Disposition |
|---|-------|-----------------|----------------------|----------|-------------|
| 1 | Verifier `Set unified verdict` (`if: should_run`) | settled verdict incl. CI-failure floor | step -> `Collect verifier metrics`, `Write verifier terminal disposition` | `tests/workflows/test_verifier_terminal_disposition.py::test_terminal_disposition_*` | **confirmed (F44), repaired here**: always-running writers fell back to raw `steps.verdict/llm_*` outputs when settlement was skipped; they now consume only the unified verdict plus `steps.unified_verdict.outcome` and record `error` / `verifier-error` when it is not `success`. |
| 2 | `Collect verifier metrics` (`always()`) | `agent-metrics` metrics JSON -> `verifier-metrics` artifact | step -> `Upload verifier metrics` | executable trace in the same test module | intentional (always-run); `settlement_interrupted` now recorded |
| 3 | `Write verifier terminal disposition` + `Upload verifier terminal disposition` (`always()`, `if-no-files-found: error`) | ndjson disposition + follow-up ledger artifact | step -> artifact | executable trace (interrupted, skipped, passing, CI-floored) | intentional |
| 4 | CI-floor comment steps (`Apply CI failure hard gate to ...`) | PR comment text | step -> comment posting | `test_reusable_verifier_floors_ci_failure_comments_before_posting` (source-string only) | unknown beyond ordering: comment steps are not `always()`; execution evidence needs a hosted run with a failed earlier step. Owned by the existing CI-floor settlement scope; not bundled. |
| 5 | `maint-post-ci.js` `updateFailureTracker`, `resolveFailureIssuesForRecoveredPR`, `autoHealFailureIssues`, `snapshotFailureIssues` | failure-tracker issues, snapshot artifact (`docs/ci-failure-tracker.md`) | helper -> `maint-46-post-ci.yml` `failure-tracker` job | helper + authored-script replay tests `.github/scripts/__tests__/maint-post-ci.test.js`; `test_post_gate_tracker_helpers_are_wired_in_maint46` | **confirmed (F45), repaired in Gate failure-tracker scope**: independent Maint46 job tracks failure/recovery and uploads `artifacts/ci_failures_snapshot.json`; summary recovery remains separate. |
| 6 | Maint 46 summary-recovery short-circuit (Gate summary success) | summary job may skip recovery; tracker still evaluates upstream legs | step -> `failure-tracker` | source read + authored replay (summary success + failed Python CI) | intentional after F45 repair |

Links: F44 = verifier settlement/CI floor scope; F45 = Gate failure-tracker
scope. Both remain owned by their existing work.

Failure matrix exercised (executable): settlement skipped with raw PASS;
settlement skipped with no raw verdict; settlement success PASS; settlement
success CI-floored CONCERNS; should_run false.
