# Coverage Gap Analysis

> **Baseline**: 2025-12-31 (main branch, post-PR #374 + devcontainer fix)
> **Overall Coverage**: 71.60%
> **Tests**: 592 passed, 0 skipped, 3 xfailed
> **Target**: 95%

## Summary

| Metric | Value |
|--------|-------|
| Total Statements | 2,798 |
| Covered Statements | 2,086 |
| Missing Statements | 712 |
| Coverage | 71.60% |
| Gap to 95% | 23.40% (~654 statements) |

## Scripts by Coverage (Lowest to Highest)

### Tier 1: Zero Coverage (3 scripts, 234 statements)

| Script | Statements | Coverage | Missing |
|--------|------------|----------|---------|
| `sync_tool_versions.py` | 74 | 0.00% | 74 |
| `update_residual_history.py` | 25 | 0.00% | 25 |
| `validate_version_pins.py` | 135 | 0.00% | 135 |

### Tier 2: Very Low Coverage <50% (3 scripts, 265 statements missing)

| Script | Statements | Coverage | Missing |
|--------|------------|----------|---------|
| `sync_test_dependencies.py` | 163 | 15.32% | 128 |
| `auto_type_hygiene.py` | 139 | 34.78% | 81 |
| `keepalive_metrics_collector.py` | 108 | 46.48% | 56 |

### Tier 3: Medium Coverage 50-75% (5 scripts, 196 statements missing)

| Script | Statements | Coverage | Missing |
|--------|------------|----------|---------|
| `keepalive_metrics_dashboard.py` | 94 | 56.67% | 40 |
| `workflow_health_check.py` | 77 | 62.62% | 28 |
| `classify_test_failures.py` | 123 | 62.87% | 37 |
| `mypy_autofix.py` | 45 | 63.08% | 13 |
| `ledger_validate.py` | 205 | 65.32% | 63 |

### Tier 4: High Coverage 75-95% (6 scripts, 35 statements missing)

| Script | Statements | Coverage | Missing |
|--------|------------|----------|---------|
| `mypy_return_autofix.py` | 89 | 82.55% | 11 |
| `ledger_migrate_base.py` | 134 | 85.48% | 13 |
| `ci_failure_analyzer.py` | 108 | 87.35% | 11 |
| `fix_cosmetic_aggregate.py` | 20 | 92.31% | 1 |
| `coverage_history_append.py` | 53 | 92.75% | 2 |
| `update_autofix_expectations.py` | 37 | 93.88% | 1 |
| `workflow_validator.py` | 72 | 93.27% | 4 |

### Tier 5: At Target ≥95% (14 scripts)

| Script | Statements | Coverage |
|--------|------------|----------|
| `ci_coverage_delta.py` | 61 | 100.00% |
| `ci_history.py` | 77 | 100.00% |
| `ci_metrics.py` | 120 | 100.00% |
| `metrics_format_utils.py` | 16 | 100.00% |
| `sync_status_file_ignores.py` | 94 | 100.00% |
| `ci_cosmetic_repair.py` | 256 | 99.71% |
| `fix_numpy_asserts.py` | 38 | 98.15% |
| `aggregate_agent_metrics.py` | 201 | 97.23% |
| `build_autofix_pr_comment.py` | 105 | 97.04% |
| `generate_residual_trend.py` | 61 | 96.55% |
| `pr_metrics_tracker.py` | 68 | 95.65% |

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
