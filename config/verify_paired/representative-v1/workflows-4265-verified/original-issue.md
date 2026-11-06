## Why (verified evidence)
The Maint Coverage Guard closes a baseline-breach issue only when the last `recovery_days` (default 3) history records are all at or above the baseline: `tools/coverage_guard.py:593` returns `False` when `len(records) < recovery_window`. The history it reads is the `gate-coverage-trend-history` artifact of ONE Gate run, and that artifact only ever holds one record: nothing restores the previous history before the append (`.github/workflows/reusable-10-ci-python.yml:3002-3010` appends to a workspace file that starts empty; `scripts/coverage_history_append.py:53` loads whatever exists, which is nothing), and the guard downloads it under a run-id-scoped cache key (`.github/workflows/maint-coverage-guard.yml:425`, `cache-key-base: gate-coverage-trend-history-${{ steps.discover.outputs.run_id }}`), so no earlier record can ever be restored. While `recovery_days` is above 1 the window cannot be satisfied.
- The five newest `gate-coverage-trend-history` artifacts of stranske/Workflows (ids 12609676623 to 12614843725, 2026-10-25 18:36 to 21:53 UTC): the two read (12614843725 and 12614304625) hold exactly 1 NDJSON record each.
- The guard's own log, run 40171029582 (2026-10-25 07:00Z): "Coverage 90.88% meets baseline 85.00% - no open issue needed", then "Coverage recovered, but configured recovery window is not satisfied; leaving any breach issue open".
- Workflows #4011 "[coverage] baseline breach" (opened 2026-10-17, 83.17% against a baseline of 85.0) is still open and has had no update since 2026-10-18, although the guard succeeded on all 8 daily runs since 10-18 and read 90.88%, almost six points above the baseline.
- Across the account the guard has filed 3 breach issues in a year (search `"baseline breach" in:title user:stranske`): Trend #2933 (open 2025-10-23 to 2026-05-25, 214 days), Orchestrator #180 (2026-08-31 to 2026-09-04) and Workflows #4011 (open, 8 days and counting). The long gaps are what a window that cannot fill produces: a person closes them.
The consequence is a gate whose clear path (N consecutive records) is fed by a source that holds one: every breach issue the guard opens stays open until someone closes it by hand.

## Tasks
- [ ] `.github/workflows/maint-coverage-guard.yml:425`: make the history cache key repository-scoped instead of producer-run-scoped, with a restore prefix, so the previous guard run's accumulated history is restored before the check.
- [ ] `tools/coverage_guard.py:593` (`_recovery_window_satisfied`) and its caller near `:763`: before the check, append the current trend record to the restored history (replacing a record with the same run id), keep at most 30 records, and write the file back so the cache saves it.
- [ ] `tools/coverage_guard.py:763`: say in the message how many records the window holds and how many it needs, for example "recovered, 2 of 3 records at or above the baseline".

## Acceptance Criteria
- Named test: `tests/test_coverage_guard.py::test_recovery_window_counts_records_accumulated_across_runs`: a restored history of two records at or above the baseline plus the current record satisfies a 3-record window; the current record alone does not; the same run id is not counted twice.
- Deliberate-break → revert: remove the append of the current record to the restored history, confirm the named test FAILS, then revert.
- Named test: `tests/test_coverage_guard.py::test_recovery_message_names_records_held_and_needed` asserts the "N of M records" text.

## Non-Goals
- Do NOT change any baseline value, `warn_drop`, the `recovery_days` default or any repository's coverage floor.
- Do NOT make the guard block anything: it stays a report that files and closes one issue.
- No scaffolding / TODO-only changes; every task is a concrete edit verified by the tests above.

_Surfaced by the coverage autopilot's fleet watch (2026-10-25) while checking the daily guard as a second signal; verified from the artifact contents, the guard's log and the files at the cited lines of main@2f66049fd4._
