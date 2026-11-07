# Issue #4426 Gate check and stop rule

## Continuation acceptance, 2026-11-07

Outcome 1: verified archive inventories and unique attributable round-wide reduction
for real Gate artifacts 13537639987 and 13575534246; attribution remains null
until consistent-source/settings baseline evidence exists. Print the historical
inventory with `/opt/anaconda3/bin/python3 scripts/reconcile_issue_4426_coverage.py
/tmp/13537639987.zip`. Check date: 2026-11-07. Both real archives were retrieved
through authenticated GitHub artifact endpoints before code changes.

Finite stop rule: at most two failed attempts per acceptance command, each focused
command under 120 seconds; at most 20 minutes on a broken reconciliation step.
Stop that step at the first unmet provenance/comparability requirement and report
it; continue independent receipt/rendering repairs. Blocking/drainable pair:
missing comparable original-round inventories blocks attribution; archive validation
and independent evidence checks remain drainable. No full local suite or Gate replay.

Verified continuation outcome: both advertised ZIP digests match. The existing
historical command exits 0; `/opt/anaconda3/bin/python3
scripts/reconcile_issue_4426_coverage.py /tmp/13575534246.zip --current-gate`
separately exits 0 and identifies the requested merge/head. The retained matched
inventories remove 33 distinct units with zero newly missing; original-round
attribution remains null. Required tests print `180 passed in 11.47s`,
`93 passed in 2.74s`, and the shallow offline run prints `73 passed in 2.57s`.
Four adversarial probes fail by name (exit 1) and pass after restoration (exit 0).
No local full suite or Gate execution was run. Final pushed-head CI remains a
separate live verification step. See follow-up-status.md for open dispositions.

## Execution configuration reconciliation, 2026-11-07

Before source edits, `python -m pytest -q
tests/scripts/test_reconcile_issue_4426_coverage.py
tests/docs/test_issue_4426_coverage_measurement.py
tests/docs/test_issue_4426_ranking.py -m 'not slow' --tb=short` passes
109 tests in 1.13s, exit 0. Selected symbols for this chunk:
`reconcile_execution_configurations`, `_execution_settings`, and
`_configuration_differences` in `scripts/reconcile_issue_4426_coverage.py`.
The existing two-failure, 10-minute command, 20-minute step, and under-two-minute
focused stop rules apply. No verifier behavioral test duplicates paths already
covered by the existing chunk/evidence suites.

The GitHub connector reverified artifact 13537639987's run 42287174423 and head
97fa3cdd6b198623db4adc86f16f0b3788320794. One local archive-reference retrieval
fails with `URLError`; archive bytes remain inaccessible. Exact merge-checkout
`pyproject.toml` contents and bounded execution log excerpts are newly retained
in `gate-execution-inputs.json`. The final checkout adds
`tool.coverage.report.exclude_also` for `__main__` guards; the original checkout
has no such setting. Matching coverage.run sections alone cannot establish
comparable missing units. Runtime, pytest, coverage versions and the pytest
entrypoint also changed. Task 1 and the two unchecked acceptance criteria remain
incomplete; the historical 164-unit snapshot difference remains unattributed.

Reproduce the new comparison offline with:

```bash
python scripts/reconcile_issue_4426_coverage.py --reports-only
python docs/evidence/issue-4426/execution-configuration-mutation-driver.txt
```

The `execution_configuration_comparison` output is retained separately as
`execution-configuration-comparison.json`, and both measurement/ranking records
link it. The original snapshots and per-target counters remain unchanged.
Matching runner settings would still require controlled source/test executions
and accessible coverage artifacts before any attributable reduction is claimed.

Final validation is retained in `execution-configuration-validation.json`:

- The reconciler/measurement/ranking selection passes 115 tests in 1.25s,
  exit 0. Targeted coverage reports 98.31% for the reconciler utility only.
- The required four-module behavioral selection passes 180 tests in 3.55s,
  exit 0. All six documentation modules pass 68 tests in 3.79s from a fresh
  depth-one checkout with networking blocked and no credential copying.
  The final isolated delivery checkout also passes all 130 reconciler and
  documentation tests in 3.96s with the same offline guard, exit 0.
- Five named mutants produce six named failing parameter cases, exit 1;
  every restored selection passes, exit 0. Complete outputs and immutable
  source/test fragments are in `execution-configuration-mutations.json`.
  Source and test hashes match the restored receipt bytes.
- Ruff and `git diff --check` pass. The default full-tree Black command fails
  at sandbox process-pool startup with `PermissionError`; its serial scheduling
  adaptation uses the same installed formatter and safety checks. The required
  full-tree command with that adaptation passes: `957 files would be left
  unchanged`, exit 0. The validation record retains the command and outputs.
- Active-checkout staging fails creating `.git/index.lock` on the read-only
  metadata mount. Delivery uses an isolated local commit and exported patch;
  no push or follow-up exact-head Gate execution is claimed. PR #4520 was
  verified open with `draft=false`.

## Bounded review follow-up, 2026-11-07

Final results for this chunk:

- The required four-module behavioral command passes 165 tests in 3.06s,
  exit 0. The before/after coverage command passes 68/72 tests in
  4.43s/3.98s and reports 44.17%/44.77% for this focused selection only.
  `bounded-review-validation.json` retains complete command outputs,
  source/configuration/test hashes, missing inventories and artifact digests.
  The complete coverage JSON files are retained as deterministic gzip files
  `bounded-review-before.coverage.json.gz` and
  `bounded-review-after.coverage.json.gz`; decompress with
  `gzip -dc docs/evidence/issue-4426/bounded-review-after.coverage.json.gz`.
- The local incremental reduction is 27 units (18 statements, nine branches),
  with no lost lines or arcs. Four units are explicitly missing in the recorded
  final Gate report: statements 6688 and 8112 and arcs 6742->6733 and
  6901->6913. This local measurement does not establish original-round
  attribution or satisfy the approximately 180-unit contract.
- `python docs/evidence/issue-4426/bounded-review-mutation-driver.txt`
  records a named failure (exit 1) and restored pass (exit 0) for each of the
  four new tests. `bounded-review-mutations.json` retains immutable source
  symbols, final test bytes, commands and complete outputs. No production
  mutation remains; the production source hash is unchanged.
- `python docs/evidence/issue-4426/follow-up-shallow-driver.txt
  docs/evidence/issue-4426/bounded-review-shallow-validation.json` passes
  all 68 evidence tests in a depth-one offline checkout in 3.03s, exit 0,
  without credential copying. Ruff and `git diff --check` pass.
- Black formats the changed test at line length 100. The full-tree
  `black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
  check passes (955 files unchanged), exit 0, with a temporary `sitecustomize`
  loading the existing `black-serial-driver.txt` scheduler. The default
  multiprocessing launch fails with sandbox `PermissionError`; the serial
  scheduler preserves the installed formatter and all safety checks.

- Active-checkout staging fails creating `.git/index.lock` on the read-only
  metadata mount. This chunk is delivered as an isolated local commit and
  `/tmp/issue4426-bounded-review.patch`; the active branch is unchanged and
  no push or exact-head Gate run is claimed. PR #4520 was verified open
  with `draft=false`.

Before edits, the required reconciliation selection passes 53 tests in 1.02s,
exit 0. The chunk coverage baseline command below passes 68 tests in 4.43s,
exit 0, with 44.17% coverage for this focused selection only:

```bash
python -m pytest -q tests/scripts/test_pr_verifier_file_chunks.py tests/scripts/test_pr_verifier_chunk_reconciliation.py tests/scripts/test_pr_verifier_ranked_remainder.py --cov=scripts.langchain.pr_verifier --cov-branch --cov-report=json:/tmp/issue4426-boundary-before.json --cov-report=term -m 'not slow'
```

Selected symbols before editing: `_evaluate_chunked` (unavailable changed-file
inventory, oversized-file request cap, and comparison-mode routing) and
`_coerce_response_content` (memory exhaustion during the second serialization
fallback). Artifact 13537639987 metadata was reverified against run
42287174423 and head `97fa3cdd6b198623db4adc86f16f0b3788320794` through
the GitHub connector. One bounded archive-reference download attempt fails
with `URLError` (DNS resolution). No archive bytes or original-round
attribution are available; task 1 remains unchecked. Continue with this
behavioral chunk toward the incomplete attributable-reduction acceptance
criterion. The existing two-failure, 10-minute command, 20-minute step and
under-two-minute focused stop rules remain in force. No full Gate execution
is claimed and no historical snapshot is replaced.

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
# Extract the generated observer verbatim from the reusable workflow (PyYAML).
growth_plugin_dir="$(/opt/anaconda3/bin/python3 - <<'PYOBSERVER'
from pathlib import Path
import tempfile
import yaml
workflow = yaml.safe_load(Path('.github/workflows/reusable-10-ci-python.yml').read_text())
step = next(step for job in workflow['jobs'].values() for step in job.get('steps', [])
            if 'cat > "${growth_plugin_dir}/ci_test_growth.py"' in step.get('run', ''))
observer = step['run'].split('cat > "${growth_plugin_dir}/ci_test_growth.py" <<\'PY\'\n', 1)[1].split('\nPY\n', 1)[0]
directory = Path(tempfile.mkdtemp(prefix='issue4426-observer-'))
(directory / 'ci_test_growth.py').write_text(observer + '\n')
print(directory)
PYOBSERVER
)"
export CI_TEST_RESOURCE_DIR="$(mktemp -d)"
rm -f pytest-collection.json
PYTHONPATH="${growth_plugin_dir}:scripts" /opt/anaconda3/bin/python3 -m pytest -p ci_test_growth -m 'not quarantine and not slow' --junitxml=pytest-junit.xml --cov --cov-config=pyproject.toml --cov-report=xml:coverage.xml --cov-report=term-missing --cov-report=json:coverage.json -n auto --dist load -n 4 --dist=loadgroup
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


## Chunk failure coverage selection, 2026-11-07

Before editing, the required four-module selection with targeted verifier
coverage passed 156 tests in 6.30s, exit 0 (Cover: 22.90%). The evidence and
ranked remainder selection passed 57 tests in 1.39s, exit 0. The existing
finite stop rule remains in force. Selected symbol: `_evaluate_chunked`,
specifically failed cross-file synthesis and per-chunk coverage rejection.
These are reachable failure paths; no feature
switch is enabled to reach disabled code. Other selected symbols considered
were `_coerce_response_content` and comparison rendering; existing tests already
cover their observed gaps, so this chunk adds no duplicate tests there.

Artifact 13537639987 still reports the recorded head and archive digest through
the connector. Local `gh run download` exits 1 with a connection error. Task 1
remains blocked on artifact bytes and comparable original-round execution.
The PR task reconciliation attempted to uncheck task 2 and task 6, matching
`follow-up-status.md`; the connector rejected that write because its approval
policy is `never`. No PR-body update is claimed. The current PR is open and
ready for review. No new checkbox is marked complete.


Results for the chunk failure selection:

- `python docs/evidence/issue-4426/chunk-failure-mutation-driver.txt`
  records five named failures, exit 1, and five restored passes, exit 0.
  The separate JSON receipt retains immutable symbol and test source evidence.
- The required four-module selection with targeted
  `--cov=scripts.langchain.pr_verifier --cov-branch --cov-report=term`
  passes 161 tests in 10.53s, exit 0. The target Cover column is 40.21% for
  this focused selection. No whole-suite coverage is claimed.
- The three-module chunk selection passes 68 tests in 5.72s, exit 0. Its
  identical baseline command passes 63 tests in 6.30s. The module counters
  change from 1635 missing lines / 869 missing branch outcomes to 1631 / 868.
  Both denominators stay 3188 statements / 1288 branch outcomes.
  `chunk-failure-validation.json` records the exact newly covered units and
  symbol-level inventories; this is a five-unit local incremental gain.
- `python docs/evidence/issue-4426/follow-up-shallow-driver.txt
  docs/evidence/issue-4426/chunk-failure-shallow-validation.json` passes all
  68 evidence tests in 7.84s from a fresh depth-one checkout with network
  calls blocked and no credential copying, exit 0.
- Ruff and `git diff --check` pass. The active checkout still rejects staging
  because `.git/index.lock` is on a read-only filesystem. No push or follow-up
  Gate execution is claimed.


The complete Black check with the retained serial adapter passes, exit 0:
`955 files would be left unchanged`. The normal CLI also passes for the changed
Python file alone. Process-pool startup is unavailable in this sandbox; the
adapter preserves formatter safety checks and source discovery. An earlier
serial attempt was interrupted while deliberate mutants were active and is
not the final formatting result. Mutation execution finished and restored
production source before the successful complete check.


## Offline archive reconciliation, 2026-11-07

Before source edits, the repository-selected Python ran
`python -m pytest -q tests/docs/test_issue_4426_contract_record.py tests/docs/test_issue_4426_pr_inventory.py -m 'not slow' --tb=line`:
`6 passed in 0.71s`, exit 0. The existing finite stop rule applies.
Selected symbols: `read_coverage_archive` and `reconcile_archive` in
`scripts/reconcile_issue_4426_coverage.py`. This chunk implements offline
artifact ingestion rather than another log-only counter reconstruction.

The connector again returned run 42287174423 as successful for the recorded
head and artifact 13537639987 with its unchanged digest. Downloading the
returned archive reference using Python failed with `URLError: Temporary
failure in name resolution`. No final artifact bytes are available locally.
The first task and both remaining acceptance criteria stay unchecked.

Final validation for this chunk is retained in
`archive-reconciliation-validation.json` and
`archive-reconciliation-shallow-validation.json`:

- Reconciler selection with targeted coverage: `21 passed in 0.59s`, exit 0;
  the Cover column for `scripts/reconcile_issue_4426_coverage.py` is 98.02%.
  This covers the ingestion utility, not the six-target reduction contract.
- Required focused acceptance: `165 passed in 2.50s`, exit 0.
- All six evidence modules in a fresh depth-one checkout with networking
  blocked and no credential copying: `68 passed`, exit 0.
- `python docs/evidence/issue-4426/archive-reconciliation-mutation-driver.txt`
  records 15 named mutation failures (exit 1) with restored passes (exit 0).
  Immutable source/test snapshots and complete outputs are retained in
  `archive-reconciliation-mutations.json`; no mutation remains. Mutation
  development exposed an assertion that accepted the wrong byte-limit error;
  the final test distinguishes compressed and expanded input limits.
- Ruff and `git diff --check` pass. The required full-tree Black command
  fails at process-pool startup with sandbox `PermissionError`. Running the
  installed CLI with serial scheduling from `black-serial-driver.txt` via
  temporary `sitecustomize` passes the same full-tree check and safety checks:
  `957 files would be left unchanged`, exit 0.

Reproduce offline reconciliation when the real archive is accessible:

```bash
python scripts/reconcile_issue_4426_coverage.py /tmp/issue-4426-final-gate.zip > /tmp/issue-4426-final-gate-reconciled.json
```

The implementation validates the recorded runtime layout
`runtimes/3.14/coverage.json`; fixtures are explicitly synthetic. It cannot
establish artifact availability or comparable original-round execution.
Historical snapshots and ranking counters remain intact, and no task checkbox
is advanced. No exact-head Gate run for this follow-up is claimed.
Active-checkout staging is still blocked by read-only `.git/index.lock`;
an isolated local clone carries the tested commit and exported patch.


## Native slot and package follow-up, 2026-11-07

Before source edits, the real-input contract/inventory selection passed six
tests in 0.93s, exit 0. The unchanged ranked-remainder and semantic-integration
selection with targeted coverage passed 61 tests in 6.26s, exit 0.
Selected symbols: `_semantic_slots_and_clients` and `_semantic_package_prompt`.
The final Gate log names statement 8454 (slot mismatch), statements 8463
and 8515 (native retry rejection and chain-depth handling), and arc
8464->8466 (unpaired execution). Tests will exercise both paired and unpaired
slot admission and prompt assembly without provider requests.
The existing two-failure, 10-minute command, 20-minute step and under-two-minute
focused limits apply.

Artifact metadata was reverified for run 42287174423, artifact 13537639987
and head 97fa3cdd6b198623db4adc86f16f0b3788320794. One local archive-reference
download attempt failed with URLError; no archive bytes were recovered.
The two historical merge checkout objects are absent from local Git, so
comparable original-round replay is unavailable here. The 164-unit historical
snapshot difference remains unattributed.

Reviewing the recent commits found task 2 and task 6 overstate completion:
their recorded follow-ups still lack the round-wide result and exact-head
artifact reconciliation. A PR-body write to restore their unchecked state
was rejected: the connector requires approval and the run policy is never.
No remote checkbox update is claimed; all remaining criteria stay incomplete.

Reproduce the local baseline with:

```bash
python -m pytest -q tests/scripts/test_pr_verifier_ranked_remainder.py tests/scripts/test_pr_verifier_semantic_integration.py --cov=scripts.langchain.pr_verifier --cov-branch --cov-report=json:/tmp/issue4426-semantic-before.json --cov-report=term -m 'not slow'
```


Results for the native slot/package chunk are retained in
`native-slot-validation.json`, its complete before/after coverage JSON gzip
artifacts, `native-slot-mutations.json`, and
`native-slot-shallow-validation.json`:

- The unchanged two-module selection passes 61 tests before and 73 after.
  Both denominators remain 3188 statements and 1288 branches. Missing lines
  fall from 1393 to 1369; missing branch outcomes fall from 766 to 756.
  The target Cover column changes from 51.76% to 52.52%. This is a local
  34-unit increment, with no lost coverage. It is not the required
  original-round attributable reduction.
- The required four-module behavioral selection passes 177 tests in 4.06s,
  exit 0, within the two-minute focused limit.
- Six deliberate mutations produce named failures, exit 1, and restored
  passes, exit 0. Immutable selected symbol, test and fixture source is
  retained with hashes, commands and outputs. No production mutation remains.
- All six evidence modules pass 68 tests in 4.00s, exit 0, from a fresh
  depth-one checkout with network calls blocked and no credential copying.
- Ruff and `git diff --check` pass. Active-checkout staging fails because
  `.git/index.lock` cannot be created on the read-only metadata mount.
  No push, remote branch advancement or exact-head Gate execution is claimed.

Reproduce the coverage comparison and focused acceptance run with:

```bash
python docs/evidence/issue-4426/native-slot-validation-driver.txt
python docs/evidence/issue-4426/native-slot-mutation-driver.txt
python docs/evidence/issue-4426/follow-up-shallow-driver.txt docs/evidence/issue-4426/native-slot-shallow-validation.json
```


Full-tree Black validation passes, exit 0: `957 files would be left unchanged`.
The normal CLI's process-pool launch fails with sandbox PermissionError; a
temporary sitecustomize uses the existing serial adapter's per-file scheduler
and preserves all Black formatting and safety checks. The passing command is
`PYTHONPATH=/tmp/issue4426-native-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`.
The changed Python file also passes the ordinary formatter. PR #4520 was
reverified open with draft=false. A temporary local clone is used for the
source/test commit and `/tmp/issue4426-native-slot.patch`; this cannot advance
the active checkout's read-only Git metadata or produce remote Gate results.

## Archive counter consistency follow-up, 2026-11-07

Before edits, the reconciler and coverage/ranking evidence selection passed
74 tests in 1.18s, exit 0. The connector reverified Gate run 42287174423,
head `97fa3cdd6b198623db4adc86f16f0b3788320794`, and artifact 13537639987
with its pinned digest. One bounded archive-reference download failed with
URLError (DNS resolution); no archive bytes were recovered or substituted.
Selected symbols before editing: `_match_report`, new `_validate_summary`,
and new `_validate_inventory` in `scripts/reconcile_issue_4426_coverage.py`.
The reconciler currently accepts contradictory branch counters and duplicate
missing-unit positions. This chunk will reject those inputs before reporting
artifact accounting. Historical evidence remains intact; attribution stays
unknown. No task checkbox is advanced.

Real-input reproduction when the archive is available:

```bash
python scripts/reconcile_issue_4426_coverage.py /tmp/issue4426-final-gate.zip
```

The existing two-failure, 10-minute command, 20-minute step and under-two-minute
focused limits remain in force. No further archive retrieval retries will be
made in this chunk. Fixtures remain explicitly synthetic.

Final results are retained in `archive-accounting-validation.json`,
`archive-accounting-shallow-validation.json`, and
`archive-accounting-mutations.json`:

- The targeted reconciler selection passes 42 tests in 0.94s, exit 0; its
  Cover column is 98.47%. This measures the ingestion utility, not the
  six-target approximately 180-unit contract.
- The required four-module behavioral selection passes 177 tests in 4.07s,
  exit 0. The coverage/ranking evidence selection passes 53 tests in 0.99s.
- All six evidence modules pass 68 tests in 4.24s in a fresh depth-one
  checkout with network access blocked and no credential copying, exit 0.
- Six named mutants produce named test failures with DID NOT RAISE, exit 1,
  and restored passes, exit 0. The receipts retain immutable source and test
  bytes, SHA-256 hashes, complete commands and outputs. The type tests use
  boolean/float values numerically equal to valid integer counters; ordinary
  arithmetic and inventory lengths would otherwise accept them. Duplicate
  tests preserve list lengths so completeness checks cannot mask the defect.
  No mutation remains. Prior mutation receipts are unchanged.
- Ruff and `git diff --check` pass. The normal multi-file Black formatter
  fails at process-pool startup with sandbox PermissionError. Both changed
  files pass the ordinary single-file formatter. The full-tree check uses
  the existing serial scheduler through temporary sitecustomize, preserving
  the installed formatter and safety checks:
  `PYTHONPATH=/tmp/issue4426-accounting-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`.

Reproduce the recorded checks with:

```bash
python docs/evidence/issue-4426/archive-accounting-validation-driver.txt
python docs/evidence/issue-4426/archive-accounting-mutation-driver.txt
python docs/evidence/issue-4426/follow-up-shallow-driver.txt docs/evidence/issue-4426/archive-accounting-shallow-validation.json
```

Active-checkout staging fails because `.git/index.lock` is read-only. The
verified source/test payload is delivered in an isolated local commit and
`/tmp/issue4426-archive-accounting.patch`; the active branch and remote PR
head are unchanged. PR #4520 was reverified open with draft=false. Artifact
bytes, comparable original-round execution, exact-head follow-up Gate results,
and attributable round-wide reduction remain unavailable. Historical
coverage-measurement.json and ranking.json snapshots remain unchanged, and
all incomplete task checkboxes remain unchecked.

The final full-tree Black check passes: `957 files would be left unchanged`,
exit 0. The isolated commit contains the same source/test bytes as the
validated active checkout; the exported patch includes the complete receipts.

## Runnable term-report reconciliation, 2026-11-07

Pre-edit real-input outcome: the connector reverified artifact 13537639987,
run 42287174423, head `97fa3cdd6b198623db4adc86f16f0b3788320794`
and digest `sha256:c754151adf08a07da718d76b40da09c814ef2ae09e69b982c0635cd9e608c839`.
The one bounded local download attempt failed with URLError; no archive bytes
were recovered. The existing reconciler and coverage/ranking selection passes
95 tests, exit 0. The PR is open with draft=false. PR-body corrections were
rejected because connector writes require approval under the never policy.

Selected symbols before editing: `reconcile_archive`, `main`, and new
`_read_inputs`, `_recover_report_targets`, `reconcile_reports` in
`scripts/reconcile_issue_4426_coverage.py`. Add a runnable offline log-only
mode so the real pinned original and final counters can be regenerated without
archive access or importing test helpers. Keep attribution null, expose changed
denominators, reject ambiguous rounded branch counts, and preserve historical
snapshots. No task is complete merely because this mode succeeds.

Command after implementation:

```bash
python scripts/reconcile_issue_4426_coverage.py --reports-only
```

Stop rule: no more archive retrieval attempts in this chunk; no remote fetches
or credential copying in validation; each focused command has a 110-second
limit. The existing full Gate command remains unexecuted locally. Finish after
focused coverage, required behavioral and shallow evidence checks, named
mutation failures/restoration passes, and the required Black gate. Leave the
artifact/comparable-execution acceptance criteria unchecked.

Final results for this chunk:

- The real-input `--reports-only` command passes, exit 0, and reproduces
  `term-report-reconciled.json` and both retained per-target records. It
  preserves unknown attribution and reports archive verification false.
- Targeted reconciler coverage passes 56 tests in 0.91s, exit 0. Its Cover
  column is 98.90%; this is utility coverage, not original-round credit.
- The required four-module behavioral selection passes 177 tests in 3.09s,
  exit 0. The coverage/ranking evidence selection passes 53 tests in 0.73s.
- All six evidence modules pass 68 tests in 2.96s, exit 0, in a fresh
  depth-one offline checkout with no credential copying.
- Nine named mutants fail with exit 1 and pass after restoration with
  exit 0. `term-report-mutations.json` retains immutable source/test symbols
  (including test decorators), hashes and complete outputs. No mutation
  remains. Historical receipts are retained separately.
- Ruff and `git diff --check` pass. The full-tree Black check passes, exit 0,
  with 957 files unchanged. The ordinary process-pool launch fails with
  sandbox PermissionError; the existing serial scheduler preserves Black's
  formatter and safety checks:
  `PYTHONPATH=/tmp/issue4426-log-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`.

Reproduce the named mutations and focused validations with
`python docs/evidence/issue-4426/term-report-validation-driver.txt`.
Reproduce the shallow documentation check with
`python docs/evidence/issue-4426/follow-up-shallow-driver.txt docs/evidence/issue-4426/term-report-shallow-validation.json`.

The active-checkout `git add` fails creating `.git/index.lock` because the
Git metadata mount is read-only. An isolated local commit and
`/tmp/issue4426-term-report.patch` preserve the payload without advancing the
active branch or remote head. PR-body corrections were rejected because the
connector requires approval under the never policy. No task is newly checked;
full archive reconciliation, comparable original execution, the approximately
180 attributable units and exact-head follow-up Gate results remain incomplete.


## Diagnostic and trace coverage follow-up, 2026-11-07

Before edits, the repository-selected Python ran:

```bash
python -m pytest -q tests/scripts/test_reconcile_issue_4426_coverage.py tests/docs/test_issue_4426_contract_record.py tests/docs/test_issue_4426_pr_inventory.py -m 'not slow' --tb=short
```

Real-input outcome: 62 passed in 1.56s, exit 0. Selected symbols before
editing: `_maybe_recover_partition_diagnostics` (the final Gate log misses
line 7836 and branch 7859->7861) and `format_comparison_report` (missing
lines 9190-9193). Test request revalidation before generation, diagnostic
findings without summaries, and provider-specific trace links. Compare the
existing `test_pr_verifier*.py` corpus before/after with identical source,
configuration and interpreter; this local increment cannot establish
original-round or whole-Gate attribution.

Stop after two consecutive failing attempts at one operation, 110 seconds per
focused selection, 10 minutes per command and 20 minutes for this step. Finish
this selected chunk after named mutation failures and restored passes; do not
claim archive verification or the approximately 180-unit contract. Metadata
for run 42287174423/artifact 13537639987 was reverified through the GitHub
connector. Its download call returned a remote file reference, but local
`gh run download` failed connecting to api.github.com (exit 1). The historical
merge checkout e4e584ea61852751c55749ab9ed6539fa10c9a31 is absent locally.
PR-body correction was attempted and rejected because approval policy is never;
Tasks 1, 2 and 6 remain incomplete in local reconciliation.


Final results for this chunk: the five-module coverage selection passes 166
baseline tests in 8.13s and 169 final tests in 8.35s (both exit 0). The target
`scripts/langchain/pr_verifier.py` changes from 57.55% to 57.75% in this local
selection; no percentage threshold is claimed. Missing units decrease by nine:
lines 7836 and 9190-9193 and arcs 7835->7836, 9189->9190, 9191->9192 and
9191->9193. Five of these lines were explicitly missing in the final Gate log.
No covered units are lost. Source/configuration/runtime and the four unchanged
test modules are identical across the two runs. The all-verifier corpus attempt
was interrupted (exit 130) because its generated cases exceeded the focused
budget; it supplies no measurement. The initial three-module comparison omitted
existing report tests and is superseded by the five-module measurement.

`diagnostic-trace-validation.json` retains complete outputs, coverage summaries,
artifact and configuration hashes, immutable new test source and three named
mutation failures (exit 1) with restored passes (exit 0). The original production
source remains byte-identical to `recorded-source/scripts/langchain/pr_verifier.py.txt`.
The two compressed `diagnostic-trace-*.coverage.json.gz` files retain the full
local before/after coverage JSON. Reproduce using:

```bash
python docs/evidence/issue-4426/diagnostic-trace-driver.txt
```

This nine-unit local gain is not original-round attribution. All six ranked
target dispositions and the historical Gate snapshots remain unchanged. The
required approximately 180 whole-Gate units and exact-head full Gate artifact
reconciliation are still incomplete. No new task is checked complete.


Required focused acceptance: 180 passed in 3.51s, exit 0. Shallow offline
acceptance: all six evidence modules pass, 68 tests in 4.05s, exit 0;
`diagnostic-trace-shallow-validation.json` retains the command/output and guards.
Ruff and `git diff --check` pass. PR #4520 was independently rechecked as open
with `isDraft=false`; its remote head remains c6c9145715032d14b5225197fb9bcd9097e5436c.
The active checkout's `.git` directory is read-only, so the source/test commit
is prepared in a separate shallow local clone without changing this branch.


The complete Black check passes with 957 files unchanged, exit 0, using the
repository's existing serial dispatcher with unchanged formatting and safety
checks:

```bash
python docs/evidence/issue-4426/black-serial-driver.txt --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The direct `BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude
'(\.workflows-lib|node_modules)' .` invocation stalled and was interrupted
(exit 130); the serial dispatcher completed the full tree without exclusions
beyond the required command. No Python formatting changes remain.
