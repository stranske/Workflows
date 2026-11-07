# Issue #4500 follow-up status, 2026-11-07

Latest behavioral chunk:

The ranked remainder file now includes five failure-path cases for
`_evaluate_chunked`. The same chunk suite before and after shows a five-unit
incremental gain: four statements and one branch outcome, all missing in the
recorded final Gate log. `chunk-failure-validation.json` binds the configuration,
source hashes, summaries and symbol-level missing inventories. This local gain
does not establish original-round attribution or close the approximately
180-unit contract. Five named mutants fail and pass after restoration in
`chunk-failure-mutations.json`; no production mutation remains. The required
behavioral selection passes 161 tests in 10.53s; all 68 evidence tests pass in
a shallow offline checkout. PR-body reconciliation was attempted but rejected
by the connector's approval policy, so the remote checked tasks 2 and 6 still
overstate the incomplete acceptance described below.

Prior per-target accounting chunk:

`coverage-measurement.json` and `ranking.json` now retain every selected
target's original-runtime and final counters, denominator changes and explicit
unresolved disposition. Historical snapshots remain intact. The totals are
402 original units and 238 final units, a 164-unit unattributed snapshot
difference. All six denominators changed. Even the sync dependency target's
zero snapshot difference is not a measured zero improvement. Comparable
execution/artifact attribution remains unavailable; no exclusion is claimed
and the first task remains unchecked.

Validation: 156 required behavioral tests pass; all 68 evidence tests pass in
a fresh shallow offline checkout. Six new accounting/rendering mutants fail
by name and pass after restoration. Ruff and the complete Black check pass
(serial scheduling for Black's sandbox-incompatible concurrency). Separate
`target-accounting-*` receipts retain these results and immutable symbol
evidence without replacing historical receipts. Active-checkout staging is
still read-only, so an isolated local commit/patch carries this chunk.

Local acceptance verified for this reconciliation chunk:

- [x] Required focused behavioral selection: 156 passed in 4.57s, exit 0.
- [x] Six documentation modules in a shallow offline checkout: 41 passed in 4.92s, exit 0.

The full Gate/artifact attribution acceptance criteria remain unchecked.

- [ ] Task 1: final-head identity and full merge checkout verified. Bounded pinned log excerpts now recover six-target original counters (402 units on both runtimes) and final counters (238 units), with an unattributed difference of 164. Historical snapshots are retained. Comparable execution/artifact attribution and final archive bytes remain unavailable, so attributable improvement stays null rather than measured zero. See `coverage-measurement.md` and `gate-report-inputs.json`.
- [ ] Task 2: added `tests/scripts/test_pr_verifier_ranked_remainder.py` for the selected repair callback; full target accounting and approximately 180 attributable units remain unverified. No target exclusions claimed.
- [x] Task 3: historical mutation receipts use immutable recorded source and test bytes; inventory assertions no longer require #4405 tests to stay absent in later checkouts. Verified by the six documentation modules in a shallow offline checkout.
- [x] Task 4: removed history fetching and extraheader copying from ranking tests; bounded pinned local ranking inputs regenerate both historical windows. Verified with a subprocess prohibition test and the shallow offline run.
- [x] Task 5: constructor-miss test injects resolved provider slots and proves the failing constructor ran. Blocked override fallback/consumption, shared model1 and explicit model2 run against both implementations. Final-version named mutations fail and restore, and actual pre-#4481 implementations both fail the blocked-override regression while fixed copies pass.
- [ ] Task 6: pre-edit real-input command, date and finite stop rule recorded; final-version mutation and original-code regression results retained with runnable driver. Exact-head full Gate artifact reconciliation remains incomplete.

`focused-validation.json` records the required four-module acceptance run.
`shallow-validation.json` records all six documentation modules from a local
file-transport depth-one clone, with network calls blocked and subprocesses
restricted to local read-only Git operations. No credentials were copied.
`mutation-receipts.json` keeps historical receipts and follow-up receipts separate.
The follow-up adds no permanent production changes; every mutant was restored.

Acceptance still requires comparable artifacts establishing the approximately
180-unit round-wide reduction (or substantive target-specific exclusions) and
passing full Gate results for the final follow-up head. Later repository-wide
coverage above 90% does not satisfy that contract.

Capacity mode: `local-only` for archive bytes and active-checkout commits.
The GitHub connector verified metadata and fetched logs, but the archive download
URL cannot resolve locally. `git add` in the working checkout fails creating
`.git/index.lock` with `Read-only file system`. Repository source edits remain
reviewable in the workspace; any isolated commit/patch is explicitly identified
in the final handoff and does not advance this checkout's branch.
