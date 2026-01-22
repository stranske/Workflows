# Issue 1011: Add rebalancer coverage and sanitize blank ranks

**Source**: https://github.com/stranske/Trend_Model_Project/issues/1011

## Why

The Rebalancer helper in the multi-period workflow lacks sufficient unit test coverage for critical entry, exit, and weighting paths. Additionally, blank or whitespace-only fund names can flow through the ranking system unchanged, leading to empty string selections that cause unexpected downstream behavior. Empty multi-period demo exports also need placeholder rows to prevent parsing errors.

## Scope

- Add comprehensive unit tests for the multi-period Rebalancer helper covering entry triggers, exit triggers, and weighting strategies
- Normalize blank or whitespace-only column labels in rank_selection before processing to avoid empty fund name selections
- Ensure empty multi-period period exports include placeholder rows with appropriate messages
- Update lockfile dependencies (hypothesis 6.138.16→6.138.17, xlsxwriter 3.2.8→3.2.9)

## Non-Goals

- Changing the core Rebalancer algorithm or trigger logic
- Refactoring existing multi-period workflow structure
- Adding new weighting strategies beyond existing score_prop_bayes
- Modifying the export file format structure

## Tasks

- [x] Add unit tests for Rebalancer consecutive soft strikes (exit path)
- [x] Add unit tests for Rebalancer hard exit threshold override
- [x] Add unit tests for hard entry candidates filling capacity first
- [x] Add unit tests for eligible candidates accumulating strikes
- [x] Add unit tests for score-proportional weighting behavior
- [x] Add unit tests for score-proportional fallback to equal weights
- [x] Add unit tests for empty holdings edge case
- [x] Sanitize blank/whitespace column names in rank_select_funds before processing
- [x] Add _ensure_periods_placeholder helper for empty period exports
- [x] Apply placeholder logic to phase1_multi and multi_period exports in empty demo
- [x] Update requirements.lock with hypothesis 6.138.17 and xlsxwriter 3.2.9
- [x] Verify all tests pass with ./scripts/run_tests.sh

## Acceptance Criteria

- [x] All unit tests in test_multi_period_rebalancer.py pass
- [x] Rebalancer correctly removes funds after consecutive soft strikes
- [x] Rebalancer immediately drops funds below hard exit threshold
- [x] Hard entry candidates consume capacity before auto entries
- [x] Eligible candidates join after accumulating required strikes
- [x] Score-proportional weighting produces normalized weights favoring higher scores
- [x] Score-proportional weighting falls back to equal weights when zscore column is missing
- [x] Empty holdings return empty Series without errors
- [x] rank_select_funds strips whitespace from column names and renames blank columns to Unnamed_N
- [x] Empty multi-period exports include placeholder rows with descriptive messages
- [x] All existing tests continue to pass after changes
- [x] Requirements lockfile reflects updated dependency versions

## Implementation Notes

Files modified:
- `tests/test_multi_period_rebalancer.py` - New comprehensive unit test suite (130 lines)
- `src/trend_analysis/core/rank_selection.py` - Column name sanitization logic in rank_select_funds
- `scripts/run_multi_demo.py` - Added _ensure_periods_placeholder helper and applied to empty exports
- `requirements.lock` - Updated hypothesis and xlsxwriter versions

The column sanitization in rank_select_funds ensures uniqueness after stripping by appending numeric suffixes when needed. The placeholder helper populates CSV, JSON, and TXT period exports with {"period": "N/A", "note": "<message>"} when empty.

Testing command: `./scripts/run_tests.sh`

**Status**: ✅ Completed
**ChatGPT Task**: https://chatgpt.com/codex/tasks/task_e_68c8c29578f08331969f58373bf6896a
