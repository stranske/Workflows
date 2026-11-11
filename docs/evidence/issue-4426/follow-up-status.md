# Issue #4500 follow-up status, 2026-11-07

## Evidence-fitting continuation, 2026-11-11

Seven tests (15 parameter cases) advance Task 2 for
`_fit_required_evidence_prompt`. Eight named mutants fail and pass after
restoration; no production mutation remains. The matched local suite gains
88 units (52 lines, 36 arcs), of which four map to historical Gate gaps using
exact-head symbol evidence. These gains do not establish original-round
attribution or satisfy the approximately 180-unit contract. All six target
dispositions retain null attribution and no exclusions.

Validation: 239 required behavioral tests pass in 5.39s; all 74 evidence tests
pass in a depth-one offline checkout in 4.65s without credential copying.
Ruff, diff checks and full-tree Black pass; Black uses the existing serial
scheduling adaptation and reports 1009 unchanged files. Commands, complete
mutation outputs, coverage artifacts and immutable symbol/test evidence are
linked from `evidence-fitting-validation.json` and `evidence-fitting-checks.json`.

The connector reverified final historical artifact 13537639987's head/digest,
while original-round run 38980711116 lists no artifacts. Comparable original
baseline and final follow-up-head Gate remain unverified. Tasks 1, 2 and 6
remain incomplete and no checkbox is advanced. Historical records are retained.

The active checkout cannot stage because `.git/index.lock` creation fails with
`Read-only file system` (exit 128). No commit, new branch or PR is created.
All changes remain in the workspace and are exported as
`/tmp/issue4426-evidence-fitting.patch`.

## Current continuation disposition, 2026-11-07

This section supersedes earlier live-state claims below; those remain historical.
Both authenticated real ZIPs are now accessible and verified. The existing
reconciler validates historical artifact 13537639987 against its advertised digest
and pinned term report (`historical-archive-reconciled.json`). Separately,
`--current-gate` validates artifact 13575534246, Gate run 42376857143, PR head
02130e674dc2c69e8976edc51771c8a2038bfbf1 and actual tested merge
c8e25743a017cc6ca41c8589b058b3fb36712ec0 against metadata, checkout logs, digest,
term counters and exact missing inventories (`current-gate-inputs.json` and
`current-gate-reconciled.json`). `final-head-gate.json` is unchanged historical
#4481 evidence. Subsequent pushed heads require fresh external Gate reconciliation;
these records must not be called evidence for an untested head.

Verified `coverage.json` bytes are retained as deterministic gzip files. Their
hashes match the archive reconciliation records. The comparable historical-to-current
inventory has 33 unique removed units and zero new missing units, all in
`pr_verifier.py`; the other five targets have unchanged gaps. Target source ASTs,
executable line/arc universes, exclusions, coverage settings and coverage.py 7.17.2
match. `verified-inventory-comparison.json` retains each line/arc set and source
AST hashes; `verified-inventory-driver.txt` reproduces it using local Git objects.
These two runs are both after the original round. They do not attribute the
original 164-unit difference or establish the approximately 180-unit round-wide
contract. None of the overlapping local gains is summed. Original-round unique
attribution and target exclusions remain null. No further behavioral cases were
selected on an unmeasured original-round remainder.

Receipt checks now bind original snapshot bytes, named red output, contiguous
`-m not slow` arguments and absence of remaining mutant snippets. The ranking
renderer derives attribution cells, aggregate totals and zero-difference claims
from the record. A changed-record case proves that the evidence changes with it.
`continuation-mutations.json` records four named failing adversarial probes and
restored passes, with the runnable bounded driver alongside it. The Gate command
now extracts the exact generated observer from the reusable workflow and sets
its resource directory. A focused test executes that extraction and checks hooks.

Current validation: required behavioral selection `180 passed in 11.47s`;
reconciliation/receipt/ranking selection `93 passed in 2.74s`; selection including
Gate observer tests `95 passed in 2.66s`. Each exits 0 within 120 seconds.
The six-module offline shallow run passes `73 passed in 2.57s`, exit 0,
with networking blocked and no credential copying (continuation-shallow-validation.json).

Review disposition: the receipt, observer and rendered-accounting findings are
repaired with focused evidence. Round-wide attribution remains a valid blocker.
The pre-push current Gate finding is reconciled, while final pushed-head Gate
validation remains pending. Ranking caching/rejection expansion and optimized
Python assert nits are deferred: no production behavior depends on this pytest
helper under `-O`, and this acceptance push does not expand into review-nit work.
Tasks 1, 2 and 6 remain incomplete for original-round/final-head portions. Prior
claims of inaccessible archives or inability to commit describe earlier runs.

## Current follow-up changes, 2026-11-07

Updated gate-check.md line 311 to remove redundant distribution flags and reproduce
Gate's generated observer setup correctly. The follow-up mutation driver now compares
the restored consumer template with its recorded fixed snapshot before setting
`follow_up_production_restored`. Test assertions for attributable_unit_reduction
fields were added to lock PR #4000 at None and PR #4405 at zero.

All required test suites continue to pass with the repository-selected Python:
- `177 passed in 8.40s` for the four-module behavioral selection
- `42 passed in 1.85s` for the reconciliation, mutation receipt, and ranking tests
- `68 passed in 2.37s` for all six documentation modules in a shallow offline checkout

Latest bounded-review chunk:

Four new cases cover oversized unparseable input, the request cap for oversized
files, comparison-mode chunk routing, and memory exhaustion on the second
response serialization fallback. The unchanged chunk suite/configuration gains
27 local missing units (18 statements and nine arcs), with no coverage lost.
Four units are explicitly missing in the recorded final Gate log. Complete
before/after coverage JSON artifacts and immutable source/test evidence are
retained in `bounded-review-*.coverage.json.gz`, `bounded-review-validation.json`
and `bounded-review-mutations.json`. Each new test has a named mutation failure
and restored pass; no production mutation remains. The required selection
passes 165 tests in 3.06s; the offline shallow evidence selection passes all
68 tests. This does not establish the original-round approximately 180-unit
reduction. Artifact metadata was reverified, but one bounded archive retrieval
attempt still fails with DNS resolution. The first task and outstanding
artifact/attribution acceptance criteria remain unchecked. No historical
measurement or ranking is changed.

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
- [ ] Task 6: pre-edit real-input command, date and finite stop rule recorded in gate-check.md; final-version mutation and original-code regression results retained with runnable driver. Exact-head full Gate artifact reconciliation remains incomplete.

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


Native slot follow-up, 2026-11-07: four behavioral tests add 12 parameter cases
for frozen slot identities, zero native retries, paired SDK checks, synthetic
provenance and reviewed package prompts. Six named mutation failures and
restored passes are retained in `native-slot-mutations.json`; production source
is restored. The matched local two-module run gains 34 units (24 lines and ten
branches); this is not attributable original-round credit.

Task reconciliation: Task 6 has verified command/date/stop-rule recording, but
its exact-head artifact reconciliation remains incomplete. Tasks 1, 2 and 6
remain unchecked locally for their unverified artifact and full-contract portions.
The connector rejected the requested PR-body correction because approval is required under
a never-approve run policy. The remote body remains unchanged. All local test suites
pass and all follow-up mutations are verified.

Runnable term-report reconciliation, 2026-11-07: `python
scripts/reconcile_issue_4426_coverage.py --reports-only` regenerates all six
original/final per-target counters and changed denominators from pinned real
logs. `term-report-reconciled.json` retains the result; coverage-measurement.json
and ranking.json link it without replacing historical snapshots. Archive
retrieval still fails with URLError, so attribution remains null and Tasks 1,
2 and 6 retain their incomplete artifact/full-contract portions. The attempted
PR-body correction was rejected because approval is unavailable in this run;
remote checkboxes still overstate completion. No new task is marked complete.


Diagnostic/trace follow-up, 2026-11-07: three behavioral tests in the ranked
remainder file protect changed-request rejection before diagnostic generation,
FAIL/findings/error retention across malformed responses and correctly labelled
provider trace links. The five-module selection gains nine local units (five
lines and four branches), with no coverage lost and unchanged production source.
Three named mutations fail and pass after restoration; immutable source and
complete local artifacts are in `diagnostic-trace-validation.json` and the
reproduction driver. This is not original-round whole-Gate attribution.
Tasks 1, 2 and 6 and both artifact/reduction acceptance criteria remain incomplete.
The PR is open and ready for review. PR-body corrections were again rejected by
the connector because approval is required under a never-approve policy.
