# Review repair progress under agent-standard

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
