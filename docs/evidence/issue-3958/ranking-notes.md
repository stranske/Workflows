# Issue #3958 target ranking (repair evidence)

## Contemporaneous selection (recoverable)

Issue [#3958](https://github.com/stranske/Workflows/issues/3958) was opened by `coverage-autopilot.py` on **2026-10-16** for lane C. Its **Scope** section lists a single ranked target:

1. **`scripts/aggregate_agent_metrics.py`** — **92 uncovered statements+branches** (16 escaped-defect signals, churn 45, prior fix commit touched this file).

That text is the Orchestrator coverage-gap ranking at issue creation: escaped-defect priority, then churn, then uncovered mass (same contract repeated in the issue **Tasks** / initiative checklist). PR [#3962](https://github.com/stranske/Workflows/pull/3962) implemented tests only for this file; no other in-flight targets from the issue scope were touched.

## Historical artifacts (not fully recoverable locally)

- The **exact machine-readable ranking snapshot** (full ordered file list beyond the scoped target) that `coverage-autopilot.py` used when dispatching issue #3958 is **not present in this repository** at repair time. Only the issue body scope line above survives as contemporaneous evidence.
- PR #3962 Gate run artifacts from **2026-10-16** (`gate-coverage.json`, trend history) are **no longer downloadable** via the GitHub Actions artifacts API (retention expired). The run URL and head SHA remain valid references: [Gate run 38973627393](https://github.com/stranske/Workflows/actions/runs/38973627393) at `2a6586bec25b03535adcd218ebe0810a0f59ba9d`.
- Opener PR #3962 recorded **three** break-and-revert narratives in prose only; full pytest RED/GREEN transcripts for those three were **not archived** in-repo. This repair re-ran all four mutations locally (see `break-and-revert-proof.json`).

## Why this target

It was **#1 (and only)** in the issue’s ranked scope with the largest bundled gap (~92 units) under the fleet initiative’s “~60 units per PR” bundling rule, matching the repository’s stated ranking policy in the issue template.
