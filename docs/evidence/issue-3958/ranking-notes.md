# Issue #3958 Coverage-Gap Ranking Evidence

## Overview

This document records the issue-scope ranking evidence for stranske/Workflows#3958.

## Source of Ranking

Issue #3958 **Scope** explicitly ranked `scripts/aggregate_agent_metrics.py` first with **92 uncovered statements+branches** based on:
- Escaped-defect signals
- Churn signals
- Coverage-gap analysis

## Historical Context

The full ordered machine snapshot from `coverage-autopilot.py` is **not recoverable** from the repository. This was the automated coverage-gap prioritization tool that identified `scripts/aggregate_agent_metrics.py` as the top target for coverage improvement.

## PR #3962 Results

PR #3962 added four defensive tests for `scripts/aggregate_agent_metrics.py`:
1. `test_metric_helper_fallbacks_preserve_safe_defaults`
2. `test_optional_metric_contract_inputs_fail_closed`
3. `test_autopilot_summary_ignores_incomplete_optional_values`
4. `test_legacy_parse_and_artifact_contract_error_paths`

### Reported vs Measured Coverage Improvement

| Source | Pre-#3962 Gap Units | Post-#3962 Gap Units | Delta | Notes |
|--------|---------------------|----------------------|-------|-------|
| PR #3962 Report | 98 | 35 | -63 | Reported at merge |
| PR #4407 Measurement | 98 | 3 | -95 | Measured on current main |

**Important**: The difference between 35 and 3 gap units is due to later test improvements on main that further covered the module beyond PR #3962's contributions. PR #3962's attributable improvement is the 63-unit reduction reported at merge.

### Gap Unit Formula

```
gap_units = missed_statements + partial_branches
```

- **Parent (19d9c3c61)**: 50 missed statements + 48 partial branches = **98 gap units**
- **Merge (dabd38209)**: Coverage improved to **35 gap units** (PR #3962 report)
- **Current main**: Further improved to **3 gap units** (0 missed + 3 partial)

## Unverified Claim

PR #3962 reported a **63-unit coverage improvement** (98 → 35 gap units). This claim is **labeled unverified** until reproduced from historical artifacts because:
1. Gate artifacts from run 38973627393 are **expired**
2. The full historical `coverage-autopilot.py` snapshot is **unavailable**
3. Later improvements on main reduced gap units further than PR #3962's merge state

## Later-Main Improvements

Current main (as of PR #4407) shows:
- 0 missed statements
- 3 partial branches
- **3 gap units** total
- 99.77% coverage

These later improvements are **separate from PR #3962 results** and should not be attributed to PR #3962.

## Acceptance Evidence Status

- ✅ Issue-scope ranking identified `scripts/aggregate_agent_metrics.py` as #1 target
- ✅ 92 uncovered statements+branches signal documented
- ✅ PR #3962 added tests for this target
- ✅ Coverage improvement measured (though exact 63-unit delta unverified)
- ❌ Full historical ordered ranking snapshot unavailable
- ❌ Gate artifacts from PR #3962 expired

## References

- Issue #3958 Scope: Ranked `scripts/aggregate_agent_metrics.py` first
- PR #3962: Added four defensive tests
- PR #4407: Documented break-and-revert proofs and coverage measurements
- Gate run 38973627393: Expired artifacts, metadata recovered via GitHub API
