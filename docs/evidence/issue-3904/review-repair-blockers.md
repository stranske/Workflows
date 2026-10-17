# Review repair progress under agent-standard

## r4297488936: permanent real partial-collection control

At source head `77be45a0e1f0eb146ece1086a373178eb775b6e6`, the first actionable
review finding still requires a protected workflow edit. Two bounded controls
now exercise the actual embedded collection plugin in real serial subprocesses:

- `test_serial_collection_error_does_not_publish_complete_receipt` collects
  three good cases before a second module raises a syntax error. Pytest exits
  **2**, but the plugin publishes a complete-looking receipt containing the
  three-case subset. Running this control with `--runxfail` gives **1 failed**
  on that exact defect. The permanent control has a **strict** expected failure
  limited to `_PartialCollectionPublished`; fixture, subprocess and JSON errors
  still fail normally. An authorized workflow fix must remove this marker when
  the control starts passing; otherwise strict XPASS fails the suite.
- `test_serial_test_failure_preserves_complete_collection_receipt` completes
  collection and then fails one of three tests. It verifies exit **1** and the
  full receipt. A repair must distinguish collection errors from test failures.

On Python **3.14.8**, with pytest-xdist **3.8.0** installed, the existing focused
command reports **41 passed, 1 xfailed in 21.51s**, including both original serial
and two-worker xdist controls:

```sh
python -m pytest tests/workflows/test_ci_test_growth.py tests/workflows/test_reusable_ci_workflow.py -q -rx -m 'not slow'
python -m pytest tests/workflows/test_ci_test_growth.py::test_serial_collection_error_does_not_publish_complete_receipt --runxfail -q -m 'not slow'
```

The second command deliberately exits **1**; it is regression evidence, not a
passing implementation. The production repair and its task checkbox remain
pending. No protected file was edited. At inspection, PR #3950 is open with
`draft=false`, and closer-owned #3947 is still open and unmerged.

Staging the test changes failed with `.git/index.lock: Read-only file system`.
The requested `needs-human` label was rejected with `MCP tool call requires
approval, but approval policy is never`; the blocker comment was rejected with
the same reason. No label, comment or review thread was changed.

Black formatted the touched Python file, Ruff and `git diff --check` passed,
and the exact repository-wide Black check passed with **759 files unchanged**:

```sh
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

As in the prior run, the existing serial Black checker populated a writable
cache before the CLI check used
`BLACK_CACHE_DIR=/tmp/issue-3904-collection-black-cache BLACK_NUM_WORKERS=1`.

## Current r4297491917 preparation and checklist reconciliation

At head `54df2124f26295a8271369f24a38edad84a40fbd`, PR #3950 is open and
ready for review. The recent commits were reviewed before continuing:
`9c2812d5` adds the inventory audit, and `54df2124` adds heredoc diagnostics and
these blocker notes. Neither commit changes the embedded collection/summary
implementation or the Selftest dependency installer.

The checked recovery items for r4297488936, r4297491912, r4297491926, the combined
r4297491942/r4297491952 item, and the Selftest xdist environment fix are therefore
not established by this checkout. In particular, the combined item has only its
heredoc half implemented, the summary still consumes unchecked collection shapes,
and Selftest still installs pytest without xdist. The all-review-findings and
merge-gates item also cannot be considered complete while those review findings
are unresolved. The requested remote checkbox corrections and `needs-human`
label were attempted through the GitHub connector; both were rejected with
`MCP tool call requires approval, but approval policy is never`. No remote
checkbox was changed by this run. The remaining r4297491917 checkbox must stay
unchecked too.

Permitted source preparation is in `scripts/ci_test_growth.py::junit_report`,
with bounded tests in `tests/workflows/test_ci_test_growth.py`. The parser keeps
all JUnit case counts independently of duration parsing, records timed/untimed
case counts, and publishes `timing_status: UNKNOWN` with null timing rankings
when any duration is missing, empty, nonnumeric, nonfinite or negative. A real
zero remains measured zero. Empty reports and overflowing aggregate durations
cannot produce measured rankings either. With incomplete timings, withholding
rankings avoids presenting partial sums as comparable measurements.

This helper is **not yet called by the reusable workflow**. An authorized
`agent-high-privilege` editor must replace the embedded JUnit aggregation in
`Record CI summary` with this behavior, keeping XML/read errors UNKNOWN and
preserving the actual test/coverage outcomes. Keep the workflow self-contained
by embedding the parser logic, or first provide a reviewed source-owned helper
delivery path; adding an import of this unsynced file alone would break consumers.
Then extend the real-summary subprocess controls to exercise invalid/missing
durations and an explicit zero before marking r4297491917 complete. No template
or sync-manifest change is made for this currently local, unintegrated helper.

Direct controls against the unchanged real summary and the prepared parser show:

| Two-case JUnit input | Existing workflow | Prepared parser |
| --- | --- | --- |
| `time="2"`, `time="invalid"` | `reported: null`; case count lost | 2 cases; 1 timed, 1 untimed; timing UNKNOWN |
| `time="2"`, missing `time` | 2 cases; missing duration reported as `0.0` | 2 cases; 1 timed, 1 untimed; timing UNKNOWN |

Both actual summary controls still preserve `checks.tests.outcome: failure`.
These controls demonstrate the current defect and helper behavior, not a
verified workflow fix or hosted validation. No task was newly marked complete.

Validation on Python 3.14.8:

```sh
python -m pytest tests/workflows/test_ci_test_growth.py tests/workflows/test_reusable_ci_workflow.py -q -m 'not slow'
ruff check scripts/ci_test_growth.py tests/workflows/test_ci_test_growth.py
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
git diff --check
```

Results: **40 passed in 12.81s**, including the existing real serial/xdist
controls and 11 new parser controls; Ruff and diff checks pass; the exact Black
check passes with **759 files unchanged**. As in the preceding run, the existing
serial checker populated a writable Black cache first; the required CLI used
`BLACK_CACHE_DIR=/tmp/issue-3904-junit-black-cache` and `BLACK_NUM_WORKERS=1`.
The requested remote blocker comment was attempted after validation and rejected
by the same connector approval policy. No comment was published.
Staging the helper, tests and these notes also failed with
`Unable to create '.git/index.lock': Read-only file system`; the changes remain
uncommitted. No protected file was edited.

The earlier notes below describe the preceding run's validation and blockers.

The current run has no explicit `agent-high-privilege` approval. The receipt
plugin and summary implementation are embedded in
`.github/workflows/reusable-10-ci-python.yml`; the Selftest dependency installer
is in `.github/workflows/selftest-ci.yml`. Those files cannot be edited in this
run. GitHub API access also failed, preventing PR inspection and publication of
the requested `needs-human` label and blocker comment.

## First unchecked task: r4297488936

A real serial pytest control extracted the unchanged workflow plugin, created
one valid module with three parametrized cases and another module containing
`def test_broken(:`, then ran:

```sh
python -m pytest -p ci_test_growth -q -m 'not slow'
```

Pytest exited **2**, but `pytest-collection.json` still reported `total: 3`,
`per_file: {"test_good.py": 3}` and a controller collection source. This confirms
that an interrupted, partial collection is currently published as complete.
The task remains incomplete.

The authorized workflow repair must invalidate collection receipts after a
collection error and add a permanent real partial-collection failure control.
Preserve receipts for a complete collection followed by a test execution failure;
the test outcome alone cannot distinguish those cases. The adjacent stale-receipt
and controller-ownership finding r4297491912 must also be considered when choosing
where to reset and write the receipt.

## Permitted test changes

For r4297491942/r4297491952, the test harness now requires complete opening and
closing heredoc lines and reports the workflow step and missing delimiter in an
assertion. Five bounded controls cover missing openers/closers for both snippets
and delimiter-like Python text with trailing shell commands and another heredoc.
The wrong-shape summary controls and implementation remain pending, so the combined
task is not checked complete.

The unreadable-receipt test also writes `GITHUB_STEP_SUMMARY` inside its temporary
directory. Its initial run failed on an inherited read-only Actions summary path;
after isolation, the real summary process passes its existing UNKNOWN assertions.

Validation on Python 3.14.8 with pytest-xdist 3.8.0:

```sh
python -m pytest tests/workflows/test_ci_test_growth.py tests/workflows/test_reusable_ci_workflow.py -q -m 'not slow'
```

Result: **29 passed**, including both serial and real two-worker xdist receipt
controls. This local result does not establish the missing xdist dependency in
Selftest CI, hosted Python 3.12/3.13 results, remote review settlement, or merge
readiness. No remaining task checkbox has been marked complete.

Ruff and `git diff --check` passed. The required repository-wide Black check also
passed: **758 files would be left unchanged**. This sandbox prevents Black's
default process pool from starting, and its one-thread completion stalled after
checking the files. The existing
`docs/evidence/issue-3743/runtime-probes/revalidation/black_serial.py` checked the
same source set and populated a writable cache; the exact required CLI then
passed with `BLACK_CACHE_DIR=/tmp/issue-3904-black-cache` and `BLACK_NUM_WORKERS=1`:

```sh
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The subsequent `git add` failed before staging with `Unable to create
'.git/index.lock': Read-only file system`. This run's filesystem permissions make
`.git` read-only, so the validated changes remain uncommitted in the workspace.
