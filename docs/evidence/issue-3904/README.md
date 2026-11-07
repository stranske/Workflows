# Issue3904 current evidence

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
