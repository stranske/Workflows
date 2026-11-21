# CI Autofix Test Fixtures

⚠️ **DO NOT DELETE** - These files are intentional CI test fixtures, not orphaned code.

## Purpose

This directory contains **sample Python modules used to test the CI autofix pipeline**. They are:

1. **Intentionally imperfect** - Some files contain formatting issues, type errors, or lint violations that the autofix workflows are designed to detect and fix
2. **Not production code** - They exist solely to exercise the autofix CI workflows
3. **Excluded from coverage** - See `pyproject.toml` `[tool.coverage.run].omit`

## Files

| File | Purpose |
|------|---------|
| `_autofix_trigger_sample.py` | Sample module with formatting to exercise autofix flows |
| `_autofix_violation_case2.py` | Test case for autofix violation detection |
| `_autofix_violation_case3.py` | Additional autofix violation test case |
| `_ci_probe_faults.py` | Fault injection samples for CI testing |
| `automation_multifailure.py` | Multi-failure scenario test fixture |

## Readers and placement

The default [return-annotation repair](../../scripts/mypy_return_autofix.py)
walks `src/` from the repository root. A move to `tests/fixtures/` puts the
samples outside that scan. The [path classifier](../../.github/path-classification.yml)
also treats a Python edit under `tests/` as test-only. A change to these
source samples follows the Python source route.

The [diverse-pipeline test](../../tests/workflows/test_autofix_pipeline_diverse.py)
writes its own damaged modules into a temporary project. To exercise the
[cosmetic repair](../../scripts/fix_cosmetic_aggregate.py) against the tracked
`automation_multifailure.py`, run it from this directory in a disposable
checkout with the repository's Python interpreter.

```sh
cd src/trend_analysis
python ../../scripts/fix_cosmetic_aggregate.py
```

The clean sample already joins with `" | "`. Changing the join separator to
a comma in the disposable copy and repeating the command restores the pipe.
The [developer guide](../../docs/metrics-developer-guide.md) also documents how
to import `trend_analysis` explicitly from a full checkout.

## Archived portfolio fixtures

The historical portfolio tests were retired in [PR #296](https://github.com/stranske/Workflows/pull/296).
The checkout still supports `import trend_analysis`. Direct imports of
`trend_analysis.constants`, `trend_analysis.selector`, and
`trend_analysis.weighting` now require the archived files below.

Run the following from a Workflows checkout using its selected Python. Set
`WORKFLOWS_PYTHON` to its absolute path if your
checkout has no `.venv`. The
[introduction revision](https://github.com/stranske/Workflows/tree/6f97a7bfd74d5b19f8d3765b75d08a0bb0113f0d)
contains the original source, score CSV, and four regression tests.

```sh
repo=$(pwd)
py=${WORKFLOWS_PYTHON:-"$repo/.venv/bin/python"}
scratch=$(mktemp -d)
git archive 6f97a7bfd74d5b19f8d3765b75d08a0bb0113f0d -- src/trend_analysis \
  tests/fixtures/score_frame_2025-06-30.csv \
  tests/workflows/test_autofix_repo_regressions.py > "$scratch/historical.tar" &&
  tar -xf "$scratch/historical.tar" -C "$scratch" &&
  (cd "$scratch" && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$scratch/src" \
    "$py" -B -m pytest -q -p no:cacheprovider tests/workflows/test_autofix_repo_regressions.py)
```

The [merged #296 source](https://github.com/stranske/Workflows/tree/a68b8585e295f9f74c36656871b8df19c2c17e97/src/trend_analysis)
contains the final versions formerly present here. From the Workflows checkout,
recover those exact three files into a separate directory.

```sh
scratch=$(mktemp -d)
git archive a68b8585e295f9f74c36656871b8df19c2c17e97 -- \
  src/trend_analysis/constants.py src/trend_analysis/selector.py src/trend_analysis/weighting.py \
  > "$scratch/portfolio.tar" &&
  tar -xf "$scratch/portfolio.tar" -C "$scratch"
```

## Coverage Exclusion

These files are excluded from coverage metrics in `pyproject.toml`:

```toml
[tool.coverage.run]
omit = [
    # ... other patterns ...
    "src/trend_analysis/*",
]
```

If you see 0% coverage warnings for these files, the exclusion may have been accidentally removed.
