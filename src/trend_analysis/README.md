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
| `constants.py` | Shared constants for trend analysis fixtures |
| `selector.py` | Selector logic test fixture |
| `weighting.py` | Weighting algorithm test fixture |

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
