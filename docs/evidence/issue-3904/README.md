# Issue3904 current evidence

## Follow-up #4462 explicit branch-coverage receipts (2026-11-07)

The comparison harness now requires explicit boolean
`meta.branch_coverage: true` in both coverage JSON reports before comparing
executed verifier lines and arcs. Missing/malformed metadata, disabled branch
mode and truthy non-boolean values leave `verifier_coverage: null` with an UNKNOWN
diagnostic and fail the measurement. Empty arc lists alone cannot prove that
branch coverage ran. Existing valid-list, lost-line/branch, source-integrity,
exit-status, package-drift, outcome and timing checks remain required.

The unchanged harness baseline passed **151 tests in 17.35s**. Twelve metadata
controls failed against the previous implementation; two additional run-level
controls reproduced exit zero with line-only coverage and no reported branch
loss. After the fix, Python **3.14.10** validation reports **165 passed in 19.86s**,
with harness coverage **94.28%**:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_measure_verifier_runtime.py --cov=scripts.measure_verifier_runtime --cov-report=term-missing -q -m 'not slow'
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
ruff check scripts/measure_verifier_runtime.py tests/scripts/test_measure_verifier_runtime.py
```

The second command reports **2,207 passed in 12.41s**. Ruff and
`git diff --check` pass. No harness coverage percentage target is specified.
The real two-arm fixture still passes with actual branch coverage. These checks
validate the harness; they do not establish scoped production-verifier coverage
on Python 3.12/3.13 or controlled hosted phases. Existing archives and manifests
remain unchanged.

Both installed Python **3.12.16** and **3.13.18** still report
`No module named pytest`. A fresh isolated Python 3.12 venv install into `/tmp`
failed with `No matching distribution found for pytest`. Current-head
[Gate run 42391932142](https://github.com/stranske/Workflows/actions/runs/42391932142)
for `553a9448002bc48900d1e00bebd2dc1dab5ec910` succeeds, including Python 3.13
job `128461307727` and Python 3.14 job `128461307780`; the connector omits job
and step timestamps. This supplies no Python 3.12 job or matched phase comparison.

The final evidence task remains unchecked. An authorized workflow editor must
align the protected manual comparison's Python matrix and immutable source pair,
preserve the common dependency lock and existing checks, and retain successful
3.12/3.13 scoped coverage, branch/outcome comparisons and controlled hosted phase
receipts. No protected workflow was edited. Attempts to add `needs-human` and
post the concrete blocker on PR #4527 were rejected with
`MCP tool call requires approval, but approval policy is never`. The PR was
verified open with `draft=false`.

Both touched Python files were Black-formatted at line length 100. A serial check
honoring the configured exclusions populated the writable cache, then the
required repository-wide command passed with **959 files unchanged**, exit **0**:

```bash
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/issue-4462-branch-mode-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The requested commit was attempted after validation, but staging failed with
`Unable to create '.git/index.lock': Read-only file system`. The four source,
test and documentation changes remain uncommitted in the workspace.

## Follow-up #4462 prepared-source execution checks (2026-11-07)

The comparison harness now rehashes its six manifest inputs in each prepared
arm before execution and after both arms finish: the three scoped test files,
production verifier, `pyproject.toml` and `requirements.lock`. A changed or
missing input, missing hash or missing arm fails before package inspection or
pytest execution and retains a diagnostic `result.json`. Changes detected after
execution fail the measurement and withhold `verifier_coverage`; raw artifacts,
independently observed outcomes and worker timings remain available. The
`source_integrity` receipt records the observed hashes and gaps. This verifies
the selected manifest inputs at those boundaries, not every imported file or
the entire checkout. Existing exit, package, outcome, timing and branch-loss
checks remain required.

The unchanged harness baseline passed **134 tests**. Seventeen new regression
cases failed against the old implementation, including two cases where changed
source still produced exit zero. After the repair, Python **3.14.10** validation
reports **151 passed in 22.39s**, with harness coverage **94.19%**:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_measure_verifier_runtime.py --cov=scripts.measure_verifier_runtime --cov-report=term-missing -q -m 'not slow'
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
ruff check scripts/measure_verifier_runtime.py tests/scripts/test_measure_verifier_runtime.py
```

The second command reports **2,207 passed in 16.00s**. Ruff and
`git diff --check` pass. No harness coverage percentage target is specified.
The real two-arm fixture verifies matching before/after input hashes and passing
outcomes/coverage; it does not establish production-verifier 3.12/3.13 evidence.
Existing archives and manifests remain unchanged.

Both installed Python **3.12.16** and **3.13.18** still return
`No module named pytest`. Cached compiled dependencies, including
`pydantic_core`, target CPython 3.14 and cannot supply those environments.
The successful current-head [Gate run 42385879330](https://github.com/stranske/Workflows/actions/runs/42385879330)
for `641baebfa2a3b947c24f8d91192d73cb67f7d4c7` has successful Python 3.13 and
3.14 jobs (`128443234951`, `128443234937`). The connector omits job/step clocks;
this run supplies neither a Python 3.12 job nor the requested matched scoped
coverage and controlled hosted phase comparison.

The remaining evidence task stays unchecked. An authorized workflow editor must
align the protected manual comparison's Python matrix and immutable source pair,
retain the common lock and existing checks, and collect the requested successful
3.12/3.13 scoped coverage, branch/outcome and hosted phase receipts. No protected
workflow was changed. Adding `needs-human` and posting the blocker comment to
PR #4527 were both rejected with
`MCP tool call requires approval, but approval policy is never`.

Black formatted both touched Python files at line length 100. After a serial
cache warmup honoring the configured exclusions, the required check passed,
exit **0**, with **959 files unchanged**:

```bash
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/issue-4462-integrity-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The requested source commit was then attempted, but `git add` failed with
`Unable to create '.git/index.lock': Read-only file system`. All four changed
source, test and documentation files remain uncommitted. PR #4527 was verified
open with `draft=false`; no task checkbox was changed.

## Follow-up #4462 observed-runtime reporting (2026-11-07)

The runtime reader previously accepted Python 3.12/3.13 receipts but hard-coded
3.13/3.14 and coverage Python 3.14 in its report metadata. It now lists the
uploaded runtime versions and each arm's explicitly ACTIVE coverage probes.
Absent coverage stays UNKNOWN. Tests cover both requested runtimes with both,
one or no active probes, the current Gate matrix, and an unmatched runtime;
existing source-identity, branch-loss and timing checks remain required. These
fixtures are synthetic reporting controls, not successful interpreter runs.

Task reconciliation found all other verified tasks already checked in PR #4527.
The final evidence task remains unchecked. Python 3.12.16 and 3.13.18 still lack
pytest. A fresh 3.12 installation attempt into `/tmp` returned
`No matching distribution found for pytest` from the available package source.
The [latest inspected Gate](https://github.com/stranske/Workflows/actions/runs/42384099448)
for head `0d6ff502b34dddd5a43fddbcce13ac0020fec07f` completed successfully,
including Python 3.13 job `128437871617` and Python 3.14 job `128437871614`.
This is not a successful scoped 3.12/3.13 comparison or controlled phase evidence;
the connector job response omits wall and step timestamps.

An authorized workflow editor must align the protected manual comparison's
Python matrix and immutable source pair, preserve the common dependency lock
and existing checks, and retain the required successful scoped coverage,
branch/outcome comparison and hosted phase receipts. No protected workflow was
edited. Attempts to label PR #4527 `needs-human` and post this blocker were
rejected with `MCP tool call requires approval, but approval policy is never`.

Validation on Python 3.14.10:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_gate_runtime_evidence.py --cov=scripts.gate_runtime_evidence --cov-report=term-missing -q -m 'not slow'
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
```

Results: **153 passed in 0.91s**, reader coverage **94.20%**; **2,054 passed in
9.48s** for the verifier integration regressions. The unmodified measurement
harness baseline also passed **134 tests in 13.94s** before editing the reader.
No percentage target is specified for this reporting change. Existing evidence
archives and manifests are unchanged.

Ruff and `git diff --check` pass. Black formatted the touched Python files at
line length 100; a serial check populated the writable cache, then the exact
required command passed with **959 files unchanged**, exit **0**:

```bash
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/issue-4462-runtime-labels-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The requested source commit was attempted after validation, but staging failed
with `Unable to create '.git/index.lock': Read-only file system`. The four
source/test/documentation files remain uncommitted in the workspace.

The archive retains two real production-mutant assertion RED/restored GREEN pairs,
raw one-node JUnit and console, original/mutated source bytes, and the exhaustive
projection map audit. Its adjacent manifest binds each archive member by bytes
and SHA256. Production caller bytes are unchanged. The scripts retain the actual
local interpreter and private checkout path as invocation evidence.

This proves the two named causal checks and explicit projection witnesses. It
does not prove all deleted lexical tuples equivalent. Full matched coverage,
local runtime, both hosted Python jobs and controlled hosted timing remain
separate acceptance. See docs/ci/verifier-grammar-matrices.md and the PR's live
validation record. Source #3904 remains open until that evidence is dispositioned.


Current candidate validation: **40,836 PASS**, exit0, 962.25s, Python3.12.2,
four xdist workers/loadgroup, repository coverage configuration. Raw candidate
JUnit, coverage JSON, console and exact runtime versions are retained in
candidate-validation.tar.gz with a member manifest. The CI collection behavior
also has actual base RED (two assertions) / current GREEN from the canonical
Gate deliberate-break checker. Twenty-four focused workflow tests pass.

The matched local baseline remains in progress in the opener run directory at
handoff. Because the two local runs overlap, elapsed times are observational,
not a controlled speedup measurement. No unchanged branch-coverage/equivalence,
Python3.13, full Gate, provider acceptance or under-ten-minute claim is made.
The original source issue stays open until those remaining results are assessed.

The complete per-function inventory is now checked by two focused tests in
`tests/scripts/test_pr_verifier_grammar_inventory.py`. Their audit-specific
deliberate breaks (a stale inventory count and a missing emitted lexical witness)
each produce assertion RED and restored GREEN. Console output is retained in
`inventory-audit-validation.txt`; `inventory-audit-validation.json` records the
command, Python version, exit codes and byte-identical restoration hashes.
These audit checks are separate from the production classifier/floor mutations
in the existing archive and do not close the outstanding coverage/hosted gates.

## Follow-up #4462 runtime-reader validation (2026-11-07)

The removed `scripts/gate_runtime_evidence.py` and its tests were recovered from
pre-reduction commit `d5c12fec48816701c24635dcc83ce1032d88c4b2`. The restored
six-test baseline passed before changes. The reader now requires explicit
successful job conclusions, complete runtime walls, scheduled-versus-observed
JUnit counts and valid executed-line/branch lists. It validates full lowercase
40/64-character object IDs before Git, handles missing pytest invocation markers,
and verifies source identity inside `build_report`. CLI tests exercise omitted,
matching and mismatched `--repo` identity. See the [reader contract and commands](../../ci/verifier-grammar-matrices.md#controlled-hosted-comparison).

On Python 3.14.10:

```bash
python -m pytest tests/scripts/test_gate_runtime_evidence.py --cov=scripts.gate_runtime_evidence --cov-report=term-missing -m 'not slow' -q
ruff check scripts/gate_runtime_evidence.py tests/scripts/test_gate_runtime_evidence.py
```

Results: **109 passed**, reader coverage **91.04%**, Ruff passed. No coverage
percentage target is specified for this reader task. This is local reader
validation, not the outstanding scoped verifier Python 3.12/3.13 coverage or
controlled hosted phase-timing evidence. Both installed older interpreters lack
pytest; no successful run on either is claimed.
The existing `tests/scripts/test_pr_verifier_body_overall_integration.py` suite
also passes: **2,054 passed in 15.22s**, using `-q -m 'not slow'`.

The next summary task still requires explicit `agent-high-privilege` approval:
update `format_growth_summary` and the embedded summary in
`.github/workflows/reusable-10-ci-python.yml` together so unknown collection
budgets and unreadable JUnit timing render as UNKNOWN. Keep existing checks and
bounded workflow controls. No protected workflow was edited. Attempts to add
`needs-human` and post a blocker comment on PR #4527 were rejected with
`MCP tool call requires approval, but approval policy is never`.

Touched Python files were formatted individually. A serial Black check that
honors all configured exclusions reports **958 files would be left unchanged**.
After populating the writable cache with that source set, the exact required
Black command passed with **958 files unchanged** and exit **0**:

```bash
BLACK_CACHE_DIR=/tmp/issue-4462-black-cache BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

Staging the four changed files failed with
`Unable to create '.git/index.lock': Read-only file system`. The validated
changes remain uncommitted in the workspace. No remote task checkbox has been
changed and no hosted acceptance is claimed. PR #4527 was verified open with
`draft=false` at handoff.

## Follow-up #4462 growth-summary preparation (2026-11-07)

`scripts/ci_test_growth.py::format_growth_summary` now renders missing or
incomplete collection budgets as **UNKNOWN**, including a null review decision
in its rendered JSON. A default `review_required: false` is not evidence of a
within-budget collection when the collection receipt is absent. The formatter
also explicitly renders missing, unreadable or incomplete JUnit timing as
**UNKNOWN**, retaining independently reported case counts and real zero timings.
It preserves receipt diagnostics and does not mutate the input.

Twenty bounded tests cover absent, unreadable, malformed and incomplete
collection receipts, known zero/within-budget/over-budget signals, unknown review
flags, absent/unreadable JUnit receipts and real parsed JUnit with missing,
invalid, zero and positive durations.

This is source preparation, not a deployed workflow fix. The current run has no
explicit `agent-high-privilege` approval. The paired task and missing-runtime
acceptance criterion therefore remain unchecked. An authorized editor must:

1. Embed the formatter in `Record CI summary` in
   `.github/workflows/reusable-10-ci-python.yml`, retaining consumer portability.
2. Initialize `growth["review_required"]` to `None` until a valid complete
   collection establishes its boolean value, so `summary.json` also preserves
   the unknown budget decision.
3. Replace the Markdown/JSON write block with
   `handle.write(format_growth_summary(growth))`.
4. Add bounded actual-summary subprocess controls for absent and unreadable
   collection/JUnit receipts and invalid durations; assert explicit UNKNOWN text,
   null budget decisions, retained counts and unchanged failed gate outcomes.
   Preserve the existing embedded-helper parity and real serial/xdist controls.

Local validation on Python 3.14.10:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_ci_test_growth.py tests/workflows/test_ci_test_growth.py tests/workflows/test_reusable_ci_workflow.py -q -m 'not slow'
python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
ruff check scripts/ci_test_growth.py tests/scripts/test_ci_test_growth.py
git diff --check
```

Results: **105 passed in 62.71s**, **2,054 passed in 25.27s**, Ruff passed, and
the diff check passed. The initial existing-workflow run had nine failures caused
by an inherited read-only `GITHUB_STEP_SUMMARY` path; clearing only that environment
variable allowed all existing tests to pass without changing or skipping them.
These local tests do not establish Python 3.12/3.13 coverage or controlled hosted
phase timings. Existing evidence archives and their manifests are unchanged.

Black formatted both touched Python files at line length 100, and individual
checks pass. The auxiliary serial checker initially reported an unrelated frozen
evidence file, but it omits the configured `force-exclude` for
`config/verify_paired/representative-v1/`. After warming the cache, the actual
required CLI command passed with **959 files unchanged**, exit **0**:

```bash
BLACK_CACHE_DIR=/tmp/issue-4462-growth-black-cache BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

No unrelated formatting was changed. The subsequent requested commit was blocked
at `git add` with `Unable to create '.git/index.lock': Read-only file system`.
This session cannot write the repository's Git metadata, so the validated source,
tests and notes remain uncommitted.

The requested `needs-human` label and blocker comment on PR #4527 were each
rejected with `MCP tool call requires approval, but approval policy is never`.
Neither remote mutation succeeded. The implementation and tests remain local,
with the protected workflow follow-up listed above.

## Follow-up #4462 incomplete phase evidence (2026-11-07)

The runtime reader now withholds `timing_controlled` when either arm lacks
measured startup, pytest, summary/post-test, collection, controller, worker,
in-pytest reporting or scoped JUnit time. It lists missing measurements, unknown
CPU models and incomplete cache flags in `timing_gaps` as **UNKNOWN**. Resource
clocks reject booleans, strings, negative and nonfinite values; one invalid worker
clock invalidates the extrema and reporting remainder instead of measuring only
the surviving workers. Real zero remains measured zero. These finer phase gaps
do not override independently known job-wall target status or test outcomes.

Unavailable active verifier coverage now leaves `verifier_branch_loss` null,
with explicit per-runtime UNKNOWN Markdown. An available loss remains true even
when another comparison is unavailable. Available loss-free coverage remains
false. This prevents missing comparisons from appearing to prove no branch loss.

The original reader baseline passed **109 tests**. New regressions initially
produced **34 failed, 112 passed** against the prior implementation. After the
repair and positive zero/loss-free/measured-loss controls, validation on Python
**3.14.10** reports **148 passed**, reader coverage **93.85%**, using:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_gate_runtime_evidence.py --cov=scripts.gate_runtime_evidence --cov-report=term-missing -q -m 'not slow'
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
ruff check scripts/gate_runtime_evidence.py tests/scripts/test_gate_runtime_evidence.py
```

The existing verifier integration suite reports **2,054 passed in 15.16s**;
Ruff passes. No coverage percentage target is specified for the reader.
These are local reader/verifier checks, not scoped Python 3.12/3.13 coverage.
The installed `/opt/hostedtoolcache/Python/3.12.16/x64/bin/python` and
`/opt/hostedtoolcache/Python/3.13.18/x64/bin/python` both return
`No module named pytest` for `-m pytest --version`.

Read-only GitHub inspection found successful current-head
[Gate run 42373778829](https://github.com/stranske/Workflows/actions/runs/42373778829)
for source head `c21d2347a1f2c26508079e51ab5277c0ec937248`. Its Python jobs
`128407235324` (3.14) and `128407235375` (3.13) both report success; retained
artifacts include `gate-coverage-3.14-1` (`13574094465`) and
`gate-coverage-3.13-1` (`13575615846`). The connector's job response omits wall and
step timestamps, so it cannot establish phase timings. No Python 3.12 job or
matched baseline/current candidate comparison is established by this run.

The existing manual comparison workflow also currently schedules **3.13/3.14**
and pins candidate `999ffe5fa00ac9c8ae8a807447f053277032b670`. It cannot collect
the requested current-candidate 3.12/3.13 evidence unchanged. An authorized
`agent-high-privilege` editor must update
`.github/workflows/maint-88-verifier-runtime-comparison.yml` and its immutable
source selection in the harness together, retain admissible baseline/candidate
source identity, run both requested interpreters, and retain successful scoped
coverage, branch/outcome comparisons and measured hosted phase receipts.
Preserve existing checks and thresholds. No protected workflow was edited.

The remaining evidence task and missing-runtime acceptance checkbox stay
unchecked. The requested `needs-human` label and blocker comment on PR #4527
were both rejected with `MCP tool call requires approval, but approval policy
is never`; neither mutation succeeded. Existing evidence archives and manifests
are unchanged.

A Python 3.12 venv dependency-install attempt using the existing
`requirements.lock` and the public PyPI index failed at
`aiohappyeyeballs==2.7.1` with `No matching distribution found`; no successful
older-interpreter environment or scoped coverage is claimed.

Black formatted both touched Python files individually. The exact required
repository-wide check passed, exit **0**, with **959 files unchanged**, after
the serial checker populated a writable cache while honoring configured
exclusions:

```bash
BLACK_CACHE_DIR=/tmp/issue-4462-phase-black-cache BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

`git diff --check` also passed. The requested source commit was attempted after
these checks, but `git add` failed with `Unable to create '.git/index.lock':
Read-only file system`. These four changed source/test/doc files remain
uncommitted. PR #4527 was rechecked as open with `draft=false` at handoff.

## Follow-up #4462 comparison-harness validation (2026-11-07)

`scripts/measure_verifier_runtime.py` now requires observed passing JUnit cases
in all three scoped suites for both arms, independently of pytest's exit status.
It retains per-suite passed/failure/error/skipped counts and an explicit
`outcome_comparison` decision. Missing or empty scope, skipped cases, failures,
errors and conflicting outcomes withhold successful scoped execution. Unreadable
JUnit records an UNKNOWN diagnostic and preserves the remaining evidence.
Coverage set comparisons now validate executed-line/branch lists in both arms;
missing, unreadable or invalid coverage produces a null comparison and an UNKNOWN
diagnostic instead of losing the final result receipt to a parser exception.
Both arms still run, and raw artifacts remain hashed. Existing nonzero-exit,
package-drift and lost-line/branch checks remain required and have explicit
regressions. The real two-arm pytest/coverage fixture still passes.

The new controls first reported **47 failed, 8 passed** against the prior harness.
After the repair and additional malformed-XML/existing-check controls, local
Python **3.14.10** validation reports **63 passed**, harness coverage **92.23%**:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_measure_verifier_runtime.py --cov=scripts.measure_verifier_runtime --cov-report=term-missing -q -m 'not slow'
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
ruff check scripts/measure_verifier_runtime.py tests/scripts/test_measure_verifier_runtime.py
```

The second command reports **2,202 passed in 11.96s**, and Ruff passes. No harness
coverage percentage target is specified. This measures the harness using small
fixture source arms; it is not scoped production-verifier coverage or hosted
phase timing. All existing evidence archives and manifests remain unchanged.

The installed Python **3.12.16** and **3.13.18** interpreters lack pytest. An
isolated Python 3.12 venv dependency-install attempt failed because the public
PyPI hostname could not resolve. No repository dependency pin was changed.
The current hosted [Gate run 42375394733](https://github.com/stranske/Workflows/actions/runs/42375394733)
for head `45cca3adf933e424c5ba99a0b87df33a18772da1` is successful, with successful
Python 3.13 and 3.14 jobs (`128411953756` and `128411953784`). This supplies no
Python 3.12 job, matched scoped comparison or controlled hosted phase timing.

The remaining task stays unchecked. The manual workflow still schedules
3.13/3.14 and pins the historical candidate. Collecting the requested evidence
requires an authorized `agent-high-privilege` editor to align
`.github/workflows/maint-88-verifier-runtime-comparison.yml` and its immutable
source selection with an admissible reviewed baseline/current-candidate pair,
then retain successful 3.12/3.13 scoped coverage, branch/outcome comparisons and
measured hosted phase receipts. Production-source/configuration identity and
existing acceptance checks must remain intact. No protected workflow was edited.

The requested `needs-human` label and concrete blocker comment on PR #4527 were
each rejected with `MCP tool call requires approval, but approval policy is never`;
neither remote mutation succeeded.

Black formatted both touched Python files individually. After the serial checker
validated the full source set with the root configuration and populated a writable
cache, the exact required CLI check passed, exit **0**, with **959 files unchanged**:

```bash
BLACK_CACHE_DIR=/tmp/issue-4462-harness-black-cache BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

`git diff --check` also passes. The requested commit was blocked at staging:
`git add` returned `Unable to create '.git/index.lock': Read-only file system`.
The four source/test/documentation changes remain uncommitted in the workspace.
PR #4527 was verified open with `draft=false`; no task checkbox was changed.

## Follow-up #4462 JUnit timing validity (2026-11-07)

The comparison harness no longer substitutes zero for missing testcase durations
or discards valid outcome counts when a duration is unreadable. It preserves
per-suite outcomes independently of `timed_cases`, `untimed_cases` and
`timing_status`. Missing, invalid, negative or nonfinite durations and overflowing
suite totals produce `worker_seconds: null`. Explicit finite zero remains known.
The separate `timing_comparison` names incomplete scoped timing as UNKNOWN and
fails the measurement, while retaining both arms, raw artifact hashes and valid
outcome/coverage comparisons. Existing exit-status, package-drift and executed
line/branch-loss checks remain required.

The unchanged harness baseline passed **63 tests**. The 23 new timing controls
failed against the old implementation. After repair, local Python **3.14.10**
validation reports **86 passed in 16.21s**, harness coverage **93.59%**:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_measure_verifier_runtime.py --cov=scripts.measure_verifier_runtime --cov-report=term-missing -q -m 'not slow'
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
ruff check scripts/measure_verifier_runtime.py tests/scripts/test_measure_verifier_runtime.py
```

The second command reports **2,202 passed in 14.02s**; Ruff passes. These checks
validate fixture timing receipts and the real small two-arm execution, not scoped
production coverage or controlled hosted phases. No harness coverage percentage
target is specified. The existing evidence archives and manifests are unchanged.

Both installed Python **3.12.16** and **3.13.18** interpreters still report
`No module named pytest`. An isolated Python 3.12 venv install using the unchanged
`requirements.lock` and public PyPI failed with `No matching distribution found`
for `aiohappyeyeballs==2.7.1`. No successful older-interpreter run is claimed.
Read-only inspection of [Gate run 42377677149](https://github.com/stranske/Workflows/actions/runs/42377677149)
for head `32258a8f93b671b6bbcdd525fe57c43bcf123c5b` found successful Python
3.13/3.14 jobs (`128418780559` / `128418780512`); this does not supply a Python
3.12 job or a matched baseline/candidate phase comparison. The connector's job
payload omits wall and step timestamps.

The remaining evidence task stays unchecked. The authorized workflow/source-pair
follow-up described above is still needed; this run has no explicit
`agent-high-privilege` approval and edited no protected workflow. Requests to add
`needs-human` and post the concrete follow-up on PR #4527 were both rejected:
`MCP tool call requires approval, but approval policy is never`. Neither remote
mutation succeeded.

Both changed Python files were formatted with Black at line length 100. A serial
check honoring the repository configuration populated a writable cache; the exact
required check then passed with **959 files unchanged**, exit **0**:

```bash
BLACK_CACHE_DIR=/tmp/issue-4462-junit-black-cache BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

`git diff --check` passes. The requested commit was blocked at staging:
`git add` failed with `Unable to create '.git/index.lock': Read-only file system`.
The four source/test/documentation files remain uncommitted. PR #4527 was checked
again as open with `draft=false`; no task checkbox was changed.

## Follow-up #4462 JUnit total reconciliation (2026-11-07)

The comparison harness now reconciles every declared `tests`, `failures`,
`errors` and `skipped` counter on suite and enclosing suite-group elements with
their actual descendant testcase rows. A truncated but well-formed report could
previously pass when it retained at least one passing row in each scoped file.
Malformed counters or mismatched totals now leave outcomes/timing UNKNOWN and
fail the measurement. Both source arms, valid coverage comparisons and raw
artifact hashes remain available. Matching XML totals alone do not establish
complete intended collection or branch equivalence.

Validation on Python **3.14.10**:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_measure_verifier_runtime.py --cov=scripts.measure_verifier_runtime --cov-report=term-missing -q -m 'not slow'
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
ruff check scripts/measure_verifier_runtime.py tests/scripts/test_measure_verifier_runtime.py
```

Results: **107 passed in 12.38s**, harness coverage **94.14%**; **2,202 passed
in 9.93s** for the verifier integration/reader regressions; Ruff passes. The
harness checks include the real two-arm pytest execution, nested suite-group
totals, invalid counters and both-arm truncated-report controls. The existing
overflow timing fixture now declares its actual four rows, preserving its
independent passing-outcome/unknown-timing assertions. No coverage target is
specified for the harness. Existing evidence archives/manifests are unchanged.

The remaining evidence task stays unchecked. Both installed Python **3.12.16**
and **3.13.18** still return `No module named pytest`; no successful requested
interpreter coverage run is claimed. The protected manual workflow still
schedules 3.13/3.14 and selects the historical candidate. An authorized workflow
editor must align that matrix and the immutable harness source pair, preserve
source/configuration identity and existing checks, and retain actual successful
3.12/3.13 scoped coverage, branch/outcome comparisons and hosted phase receipts.
No protected workflow was edited. PR #4527 was verified open with `draft=false`.

Both touched Python files were formatted at line length 100. The serial Black
checker honored the root configuration, including the frozen-evidence exclusion,
and populated a writable cache; the required CLI then passed with **959 files
unchanged**, exit **0**:

```bash
BLACK_CACHE_DIR=/tmp/issue-4462-totals-black-cache BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

Staging the four source/test/documentation changes failed with
`Unable to create '.git/index.lock': Read-only file system`, preventing the
requested commit. Automatic approval review rejected both the `needs-human`
label and concrete workflow-blocker comment with `MCP tool call requires
approval, but approval policy is never`. Neither remote mutation succeeded.

## Follow-up #4462 explicit immutable source preparation (2026-11-07)

Recent commits and PR #4527's live body were reconciled: the verified tasks are
already checked, and scoped Python 3.12/3.13 coverage plus controlled hosted
timings remain unchecked. The harness now accepts paired `prepare --baseline`
and `--candidate` arguments, allowing a reviewed current source pair without
changing historical defaults. Both IDs must name full lowercase 40/64-character
commit objects. Mutable/partial inputs, non-commit objects and selection during
`run` are refused. Existing verifier/configuration identity and measurement
failure checks remain required.

The [preparation receipt](selected-source-preparation.json) retains a successful
real extraction of PR base `00f43f81e51c4f8b9a057ac51f7e3c2d870d7769` and then-head
`c3403284867e5091594cebed68cddafd3da78517`, including tree IDs and file hashes.
Verifier, configuration and lock hashes match. This is preparation only:
`runtime_evidence` remains **UNKNOWN**, and neither source arm was measured.

Validation on Python **3.14.10**:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_measure_verifier_runtime.py --cov=scripts.measure_verifier_runtime --cov-report=term-missing -q -m 'not slow'
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
ruff check scripts/measure_verifier_runtime.py tests/scripts/test_measure_verifier_runtime.py
```

Results: **134 passed in 19.31s**, harness coverage **93.09%**; **2,202 passed
in 14.62s** for integration/reader regressions; Ruff passes. Tests include real
SHA-1/SHA-256 CLI preparation and refusal of source/configuration differences.
The initial 20 source-selection controls failed against the prior implementation.
No harness coverage percentage target is specified; these fixture checks do not
establish production-verifier coverage or hosted timing.

An authorized workflow editor must still align the protected manual workflow's
Python matrix, fetches and preparation arguments with the reviewed source pair,
then retain the requested successful coverage, branch/outcome and hosted phase
receipts. No protected workflow was edited. Automatic approval review rejected
both the requested `needs-human` label and blocker comment with
`MCP tool call requires approval, but approval policy is never`.

Both touched Python files were Black-formatted at line length 100. After a
serial check populated a writable cache, the required repository-wide command
passed, exit **0**, with **959 files unchanged**:

```bash
BLACK_CACHE_DIR=/tmp/issue-4462-source-pair-black-cache BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

`git diff --check` passes. Staging the five changed/new files failed with
`Unable to create '.git/index.lock': Read-only file system`, preventing the
requested commit. Automatic approval review also rejected the PR-body validation
update with the same approval-policy error. No remote metadata changed; PR #4527
was verified open with `draft=false`. The remaining task stays unchecked.


## PR #4527 closer continuation (2026-11-07)

The [closer record](closer-4527-2026-11-07.md) retains strict growth JSON,
exact suite totals, Git isolation/timeout and independent output-parent repairs,
focused passing checks, all review dispositions, the historical 3.12 experiment
policy exception, and actual hosted 3.13 receipts. The selected-source comparison
ran as [42401537967](https://github.com/stranske/Workflows/actions/runs/42401537967).
Python 3.13 passed both scoped arms with zero lost verifier lines/branches.
Python 3.12 terminal receipts, complete phase evidence and final current-head Gate
conclusions remain UNKNOWN after REST rate limiting. The evidence task remains
unchecked; resume the original run after **19:15:34 UTC**, without redispatch.

## Closer remainder: original receipts and measured phases (2026-11-07)

The original [run 42401537967](https://github.com/stranske/Workflows/actions/runs/42401537967)
completed successfully on both Python 3.12.16 and 3.13.18. The earlier UNKNOWN
3.12 status above records the rate-limited handoff, not the terminal outcome.
The actual [3.12 archive](hosted-42401537967/verifier-runtime-3.12.zip), manifest,
result, terminal run/artifact API responses and [independent reconciliation](hosted-42401537967/verified-3.12-summary.json)
now accompany the existing 3.13 receipts. The archive digest matches GitHub:
`a233e756308c0305182671a169abefb090464eb7ba50192e57e69336f1484e2e`.
Both arms cover 2,144 verifier lines and 759 arcs with zero loss. Every scoped
JUnit case passed; source manifests were rehashed against immutable Git objects
and required uploaded coverage/JUnit/console hashes were verified. Four inherited
source-tree log hash entries were not uploaded and remain UNKNOWN. The original
run did not measure per-arm collection or reporting boundaries.

The separate new manual measurement uses the same reviewed immutable source
pair, common lock, four workers and coverage settings. An identical external
`verifier_phase_probe` plugin records raw `time.monotonic` boundaries in
`phase-clocks/{controller,gw0,gw1,gw2,gw3}.json` for each arm. Intervals cover
session hooks, collection hooks, the controller/worker execution-loop hooks and
final reporting hooks. `reporting` is the directly measured
`pytest_sessionfinish` hook interval, enclosing JUnit and terminal reporting.
`coverage_reporting` directly measures the controller pytest-cov `summary` call
inside the execution loop. Per-test report handling and coverage finalization
remain inside that loop, without invented separate intervals. Controller
collection is its own hook invocation; actual xdist collection occurs separately
in each worker. The controller loop overlaps worker collection and execution.
Sessions include reporting; all four workers overlap each other. These intervals
must never be added across processes or subtracted to invent exclusive overhead.
Startup and teardown outside these hooks and exclusive overhead remain UNKNOWN.
Missing, malformed, non-finite, boolean, negative or reversed boundaries produce
null intervals and explicit UNKNOWN gaps. Phase availability is reported
separately from the existing outcome and JUnit timing refusal checks.

The raw archives and phase reconciliations for the new run will be retained
separately from the original run. No causal speedup claim follows from one pair
per interpreter; OS page cache remains uncontrolled and arm order is recorded.

Reproduce independent validation from the repository root:

```bash
/opt/anaconda3/bin/python3 docs/evidence/issue-3904/validate_hosted_receipts.py docs/evidence/issue-3904/hosted-42401537967/verifier-runtime-3.12.zip docs/evidence/issue-3904/hosted-42401537967/artifacts-readback-2026-11-07.json
```

See [the acceptance record](closer-r2-acceptance.md) for the stop rule, retained
prior-branch work and validation results. PR #4527's source, dependency, outcome,
coverage and timing refusal checks remain in force. No dependency pins changed.
