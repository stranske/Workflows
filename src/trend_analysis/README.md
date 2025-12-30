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

## Used By

- `tests/workflows/test_autofix_pipeline_diverse.py` - Creates temporary copies of these patterns for autofix testing
- CI autofix workflows that validate the repair pipeline works correctly

## Why Not in `tests/`?

These files need to be in a `src/` location because:
1. The autofix pipeline specifically targets `src/` directories
2. They simulate real project structure that autofix would encounter
3. Some tests copy these patterns into temporary workspaces

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
