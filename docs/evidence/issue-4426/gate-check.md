# Issue #4426 Gate check and stop rule

## Per-target accounting follow-up, 2026-11-07

Before edits, `python -m pytest -q
tests/docs/test_issue_4426_coverage_measurement.py
tests/docs/test_issue_4426_ranking.py -m 'not slow' --tb=short` passes
50 tests in 0.81s, exit 0. Selected symbols: the new
`compare_target_snapshots`, `build_ranking_record`, and
`render_ranking_markdown`. The existing two-failure, 10-minute command,
20-minute step, and under-two-minute focused limits remain in force.

The connector reverified run 42287174423, head
`97fa3cdd6b198623db4adc86f16f0b3788320794`, merge checkout
`e4e584ea61852751c55749ab9ed6539fa10c9a31`, and artifact 13537639987's
recorded digest. Both `gh run download` and a bounded attempt to retrieve the
connector's archive reference fail locally (connection error / URLError).
No signed download URL is retained. This chunk exposes per-target log-derived
counters and denominator changes; it cannot establish comparable artifacts or
attribution. No task checkbox is advanced.

Results for this per-target chunk:

- `python docs/evidence/issue-4426/target-accounting-mutation-driver.txt`
  records six named mutation failures (exit 1) and restored passes (exit 0).
  `target-accounting-mutations.json` preserves immutable symbol/test fragments,
  source hashes and complete outputs. Every changed source is restored.
- The required four-module behavioral selection passes 156 tests in 2.84s.
  The same selection with `--cov=scripts.langchain.pr_verifier
  --cov-report=term-missing` passes 156 tests in 4.05s; the module's Cover column
  is 22.90% for this selection only. Neither run claims round-wide attribution.
  Commands and complete outputs are in `target-accounting-validation.json`.
- `python docs/evidence/issue-4426/follow-up-shallow-driver.txt
  docs/evidence/issue-4426/target-accounting-shallow-validation.json` passes
  all 68 evidence tests in 3.08s from a fresh depth-one checkout with network
  blocked and no credential copying, exit 0.
- Ruff passes for both changed Python modules, and `git diff --check` passes.
  The full `black --check --line-length 100 --exclude
  '(\.workflows-lib|node_modules)' .` check passes: 955 files unchanged, exit 0.
  It uses the installed CLI with serial scheduling through a temporary
  `sitecustomize` adapter equivalent to `black-serial-driver.txt`, preserving
  formatter and safety checks. Multi-worker startup raises sandbox
  `PermissionError`; the one-worker attempt was interrupted with exit 130.
- Active-checkout staging still fails to create `.git/index.lock` on the
  read-only metadata mount. Delivery is an isolated local commit/patch;
  the active branch is unchanged and no push or follow-up Gate run is claimed.
  PR #4520 was verified open with `draft=false`.

## Identity validation follow-up, 2026-11-07

Before this chunk's edits, `python -m pytest -q
tests/docs/test_issue_4426_coverage_measurement.py
tests/docs/test_issue_4426_ranking.py -m 'not slow' --tb=short` reports
`26 passed in 0.70s`, exit 0. The existing two-failure, 10-minute command,
20-minute step, and under-two-minute focused limits remain in force.
Selected symbol: `reconcile_gate_reports`. This chunk pins the original and
final run identities independently of their agreement with supplied log excerpts,
including merge parents, runtime/job association, PR number, and archive digest.

The connector reverified run `42287174423` and artifact `13537639987` against
head `97fa3cdd6b198623db4adc86f16f0b3788320794`. The local retry
`gh run download 42287174423 --repo stranske/Workflows --name gate-coverage-3.14-1
--dir /tmp/issue-4426-gate-recheck` exits 1 with `error connecting to api.github.com`.
No archive bytes, comparable original-round execution, or attributable reduction
are claimed. Historical evidence and counters stay preserved.

Final results for this identity chunk:

- Required focused acceptance: `156 passed in 2.09s`, exit 0. The same selection
  with targeted `--cov=scripts.langchain.pr_verifier --cov-branch` passes 156
  tests in 3.78s; its coverage is 22.90%, not whole-suite coverage or attribution.
- `python docs/evidence/issue-4426/identity-mutation-driver.txt` records four
  named mutants: all 24 new parameter cases fail, exit 1, and pass after source
  restoration, exit 0. Immutable source and complete outputs are retained in
  `identity-validation-source.py.txt` and `identity-validation-mutations.json`.
  The prior reconciliation receipts are retained unchanged.
- `python docs/evidence/issue-4426/follow-up-shallow-driver.txt
  docs/evidence/issue-4426/identity-shallow-validation.json` runs all six evidence
  modules in a fresh depth-one checkout with network blocked and no credential
  copying. It passes 65 tests; the separate output preserves the historical run.
- Ruff passes on the changed Python module. Black formats it at line length 100.
  Default full-tree Black fails at sandbox process-pool startup; the one-worker
  retry stalls and is interrupted. The existing serial adapter, using the same
  installed formatter and full check flags, reports `955 files would be left
  unchanged`, exit 0:
  `python docs/evidence/issue-4426/black-serial-driver.txt --check --line-length 100
  --exclude '(\.workflows-lib|node_modules)' .`.
- Active-checkout `git add` fails because `.git/index.lock` is on a read-only
  filesystem. This chunk is packaged in an isolated local commit; no push or
  exact-head Gate execution is claimed. PR #4520 is open and ready for review.

The first task remains incomplete: pinned identities and defensible log counts
do not supply comparable original-round artifact counters or the attributable
approximately 180-unit reduction. No task checkbox is advanced by these guards.

Latest local reconciliation results, 2026-11-07: the required focused selection
passes 156 tests in 4.57s (exit 0); targeted verifier smoke coverage passes the
same 156 tests in 6.14s, reporting 22.90% for this selection only. All six
documentation modules pass 41 tests in 4.92s from a fresh depth-one clone with
network access blocked and no credential copying (exit 0). Four validator
mutations fail by name and all restored selections pass; reproduce with
`python docs/evidence/issue-4426/reconciliation-mutation-driver.txt`.

Ruff passes on both changed Python modules. Black formats them at line length
100; the full-tree check reports `955 files would be left unchanged`, exit 0,
using the installed CLI with the serial dispatcher retained in
`black-serial-driver.txt`. The unmodified default process-pool startup raises
`PermissionError` in this sandbox. This scheduling adaptation preserves all
formatting and safety checks. Active-checkout `git add` still fails because
`.git/index.lock` is read-only; an isolated local commit carries this chunk.
No push or exact-head Gate run for this follow-up is claimed.

## Second reconciliation check, 2026-11-07

Before this round's test edits, the repository-selected interpreter ran
`python -m pytest -q tests/docs/test_issue_4426_contract_record.py tests/docs/test_issue_4426_pr_inventory.py -m 'not slow' --tb=line`:
`6 passed in 1.09s`, exit 0. The finite stop rule below still applies.
Selected symbols for this chunk are `recover_missing_branches`,
`recover_report_targets`, and `reconcile_gate_reports` in the coverage evidence
tests. No production behavior or target exclusion is changed.

The connector reverified the final run/head, artifact/head, and full synthetic
merge SHA and parents. Original Gate logs for Python 3.12 and 3.13 are accessible;
their selected per-target reports are retained in `gate-report-inputs.json`.
The final archive still cannot resolve locally. A unique integer count recovered
from a small target's percentage is a log-derived counter, not a downloaded
coverage artifact or a branch-arc inventory. Repository-wide rounded totals
remain ambiguous. Cross-snapshot differences remain unattributed.

Recorded 2026-11-06T17:31:27Z, after the contract and inventory commits. This
stop rule binds the remaining coverage work. It was not in place before those
two commits.

## Stop rule

- Attempt limit: two failed runs of the same required check. The second failure
  is the stop.
- Elapsed-time limit: 10 minutes for one command, and 20 minutes for the whole
  step that contains it.
- The focused check below must finish in under two minutes. A run that exceeds
  two minutes is the first broken step.
- When a limit trips, report that step and stop. Do not start another fix in
  the same step.

## Real input

Command:

```bash
python3 -m pytest tests/docs/test_issue_4426_contract_record.py tests/docs/test_issue_4426_pr_inventory.py -q -m "not slow" --tb=line
```

Outcome at 2026-11-06T17:31:27Z: `6 passed in 0.30s`, exit 0. That is under
two minutes. Adding `tests/docs/test_issue_4426_gate_check.py` to that command
then printed `7 passed in 0.31s`, exit 0.

## Gate pytest and coverage command

`pr-00-gate.yml` job `python ci` calls
`.github/workflows/reusable-10-ci-python.yml` with:

- `primary-python-version` and `coverage-python-version`: `3.14`
- `python-versions`: `["3.13", "3.14"]`
- `pytest-workers`: `4`
- marker `not quarantine and not slow`
- `pytest_args`: `-n auto --dist load`
- `coverage-min`: `70`
- `artifact-prefix`: `gate-`

The reusable Pytest step builds arguments and runs
`pytest -p ci_test_growth "${args[@]}"`. When coverage is enabled and
`pyproject.toml` exists, the arguments include `--cov`,
`--cov-config=pyproject.toml`, `--cov-report=xml:coverage.xml`,
`--cov-report=term-missing`, and `--cov-report=json:coverage.json`. Coverage is
enabled only for the coverage Python version, so Gate's comparable artifact is
the Python 3.14 bundle. The xdist branch then appends `-n` with the worker
count and `--dist=loadgroup`.

`pyproject.toml` sets `branch = true` and
`source = ["scripts", "tools", "src"]`. Blended statement-plus-branch
accounting is covered lines plus covered branches over statements plus
branches. The coverage minimum step reads `coverage.xml` `line-rate`, which is
not that blended total.

## Follow-up check, 2026-11-07

Before further source edits, the repository-selected Python 3.14.10 ran:

```bash
python -m pytest -q tests/docs/test_issue_4426_contract_record.py tests/docs/test_issue_4426_pr_inventory.py -m 'not slow' --tb=line
```

Real-input outcome: `6 passed in 1.04s`, exit 0. The existing finite stop rule
continues to apply: two failed runs of the same required check, 10 minutes per
command, 20 minutes per step, and under two minutes for focused checks.
Deliberate mutation runs expect exit 1 and are not failed acceptance checks.

The GitHub connector verified PR #4481 head
`97fa3cdd6b198623db4adc86f16f0b3788320794` against run `42287174423`
and artifact `13537639987` (`gate-coverage-3.14-1`, archive digest
`sha256:c754151adf08a07da718d76b40da09c814ef2ae09e69b982c0635cd9e608c839`).
Job `128131232558` reports `49864 passed, 27 skipped, 3 xfailed in 712.92s`
and checks out merge `e4e584e` of that head into
`d216eaafb02c97ed5f1da16a10d46d9a967c616f`. This is the prior PR's Gate,
not a Gate run for this follow-up checkout.

Artifact metadata and logs are accessible through the connector, but downloading
the returned archive URL locally failed with `Temporary failure in name resolution`.
Missing branch outcomes cannot be reconstructed from partial-branch counts or
the rounded total percentage. Original-round per-target counters remain
unavailable. Tasks 1 and 2 remain blocked on comparable artifact recovery;
the historical snapshots are retained. Unknown attribution is not zero improvement.

The next independent chunk repairs historical receipt/inventory validation and
pins bounded ranking inputs, so evidence checks need no history fetch or HTTP
extraheader copying in shallow checkouts.

## Runnable checks for the follow-up payload

Focused acceptance (repository-selected Python):

```bash
python -m pytest -q tests/scripts/test_pr_verifier_ranked_remainder.py tests/scripts/test_pr_verifier_expanded_comparison_verdict.py tests/scripts/test_pr_verifier_evidence_cache_miss.py tests/tools/test_langchain_client.py -m 'not slow'
```

Observed before final receipt refresh: `156 passed in 3.95s`, exit 0.
The same selection with `--cov=scripts.langchain.pr_verifier --cov-branch
--cov-report=json:/tmp/issue-4426-focused-coverage.json --cov-report=term`
passed 156 tests in 5.75s. Module blended coverage is 22.90% for this focused
selection; `_build_verifier_repair_callback` has no missing lines or branch
arcs within lines 8201–8221. This is focused evidence, not whole-Gate coverage
or the attributable approximately 180-unit reduction.

Reproducible final-version mutation and original-code regression command:

```bash
python docs/evidence/issue-4426/follow-up-mutation-driver.txt
```

The driver uses bounded local source snapshots for original implementations,
runs each named test with a 110-second timeout, records exit 1 for the mutant
and exit 0 after restoration, and restores every source in a `finally` block.
`follow_up_receipts`, `follow_up_regressions`, and `follow_up_recorded_source` in
`mutation-receipts.json` preserve final test hashes and original/fixed hashes.
The earlier receipts and their original source bytes remain separate.

Whole-Gate coverage invocation, expanded from the recorded reusable step:

```bash
PYTHONPATH=scripts python -m pytest -p ci_test_growth -n auto --dist load --cov --cov-config=pyproject.toml --cov-report=xml:coverage.xml --cov-report=term-missing --cov-report=json:coverage.json -m 'not quarantine and not slow' -n 4 --dist=loadgroup
```

No whole-Gate run for this follow-up checkout is claimed. The recovered #4481
job lasted 712.92 seconds, exceeding this local step's 10-minute command
budget; the full run belongs in CI. The final-head artifact and comparable
original-round baseline still need recovery before claiming acceptance.

## Final local results and delivery constraint

On 2026-11-07 the final focused acceptance selection reports `156 passed in
3.97s`, exit 0 (`focused-validation.json`). All six documentation modules
report `31 passed in 3.87s`, exit 0 from a fresh shallow checkout with the
network guard enabled (`shallow-validation.json`). Reproduce the shallow
validation with `python docs/evidence/issue-4426/follow-up-shallow-driver.txt`.
The JSON records bind the tested source and test files by SHA-256.

All 14 final-version behavioral mutations report named failures, exit 1,
and restored passes, exit 0. Both actual original-code client regressions
report exit 1 and fixed-code passes exit 0. The runnable driver and complete
outputs are retained; no mutation remains and no permanent production fix
was needed in this follow-up.

Ruff on the five changed Python files passes. Default Black process-pool
startup fails with sandbox `PermissionError`; its one-worker thread path did
not finish promptly. The installed Black 26.10.1 CLI was also run with the
same complete source discovery and check flags using a serial per-file
dispatcher, retaining Black's formatter, safety checks and report exit code:

```bash
python docs/evidence/issue-4426/black-serial-driver.txt --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

That serial check reports `955 files would be left unchanged`, exit 0.
The adapter changes execution scheduling only and is retained for review.

Active-checkout staging is blocked: `git add` cannot create `.git/index.lock`
because the Git metadata mount is read-only. The workspace edits are preserved;
an isolated local commit/patch can carry the tested payload without changing
this checkout's branch or representing a remote Gate run.
