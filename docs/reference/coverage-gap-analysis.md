# Coverage Gap Analysis

> **Baseline**: 2025-12-31 (Updated after PR #401)
> **Overall Coverage**: 94.03%
> **Tests**: 715 passed, 3 xfailed, 1 failed
> **Target**: 95%

## Summary

| Metric | Value |
|--------|-------|
| Total Statements | 2,798 |
| Covered Statements | 2,631 |
| Missing Statements | 167 |
| Coverage | 94.03% |
| Gap to 95% | 0.97% (~27 statements) |

## Scripts by Coverage (Lowest to Highest)

### Tier 3: Medium Coverage 50-75% (3 scripts, 128 statements missing)

| Script | Statements | Coverage | Missing |
|--------|------------|----------|---------|
| `workflow_health_check.py` | 77 | 63.64% | 28 |
| `ledger_validate.py` | 205 | 69.27% | 63 |
| `classify_test_failures.py` | 123 | 69.92% | 37 |

### Tier 4: High Coverage 75-95% (3 scripts, 28 statements missing)

| Script | Statements | Coverage | Missing |
|--------|------------|----------|---------|
| `mypy_return_autofix.py` | 89 | 87.64% | 11 |
| `ledger_migrate_base.py` | 134 | 90.30% | 13 |
| `workflow_validator.py` | 72 | 94.44% | 4 |

### Tier 5: At Target ≥95% (23 scripts)

| Script | Statements | Coverage |
|--------|------------|----------|
| `auto_type_hygiene.py` | 139 | 100.00% |
| `ci_coverage_delta.py` | 61 | 100.00% |
| `ci_history.py` | 77 | 100.00% |
| `ci_metrics.py` | 120 | 100.00% |
| `keepalive_metrics_dashboard.py` | 94 | 100.00% |
| `metrics_format_utils.py` | 16 | 100.00% |
| `sync_status_file_ignores.py` | 94 | 100.00% |
| `sync_test_dependencies.py` | 163 | 98.30% |
| `sync_tool_versions.py` | 74 | 100.00% |
| `update_residual_history.py` | 25 | 100.00% |
| `validate_version_pins.py` | 135 | 99.51% |
| `ci_cosmetic_repair.py` | 256 | 99.71% |
| `ci_failure_analyzer.py` | 108 | 99.40% |
| `fix_numpy_asserts.py` | 38 | 98.15% |
| `keepalive_metrics_collector.py` | 108 | 99.30% |
| `mypy_autofix.py` | 45 | 98.46% |
| `aggregate_agent_metrics.py` | 201 | 97.23% |
| `build_autofix_pr_comment.py` | 105 | 97.04% |
| `generate_residual_trend.py` | 61 | 96.55% |
| `pr_metrics_tracker.py` | 68 | 95.65% |
| `coverage_history_append.py` | 53 | 95.65% |
| `fix_cosmetic_aggregate.py` | 20 | 95.00% |
| `update_autofix_expectations.py` | 37 | 97.30% |

## Verification Command

```bash
pytest tests/ --cov=scripts --cov-report=term-missing
```

Check the `Cover` column in the output. A script meets its target when coverage ≥95%.

## Testing Patterns

### Reference Test Files (High Coverage)

- `tests/scripts/test_ci_metrics.py` — 100% coverage
- `tests/scripts/test_sync_status_file_ignores.py` — 100% coverage
- `tests/workflows/test_ci_cosmetic_repair.py` — 99.71% coverage
- `tests/scripts/test_ci_history.py` — 100% coverage
- `tests/scripts/test_aggregate_agent_metrics.py` — 97.23% coverage

### Mocking Guidelines

1. **File system**: Use `tmp_path` fixture, mock `Path` operations
2. **GitHub API**: Mock `requests` or use `responses` library
3. **Subprocess calls**: Mock `subprocess.run` / `subprocess.check_output`
4. **Environment variables**: Use `monkeypatch.setenv()`

### Test File Naming

- `scripts/foo.py` → `tests/scripts/test_foo.py`

## Progress History

| Date | Coverage | Tests | Delta | Notes |
|------|----------|-------|-------|-------|
| Baseline | 42.78% | 481 | — | Initial tracking |
| 2025-12-31 | 54.79% | 481 | +12.01% | Pre-PR work |
| 2025-12-31 | 58.87% | 538 | +4.08% | PR #363 |
| 2025-12-31 | 63.17% | 546 | +4.30% | PR #363 (branch) |
| 2025-12-31 | 64.12% | 558 | +0.95% | PR #366 merged |
| 2025-12-31 | 67.30% | 573 | +3.18% | PR #369 merged |
| 2025-12-31 | 69.35% | 589 | +2.05% | PR #374 merged |
| 2025-12-31 | 71.60% | 592 | +2.25% | devcontainer fix (0 skipped) |
