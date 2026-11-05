# Round 1 closer evidence recovery for #3995

Checked 2026-11-03. Refs #3995. Preserves merged implementation
[#3996](https://github.com/stranske/Workflows/pull/3996); this repair adds
evidence and reconciliation only. No production or test source changes.

Acceptance outcome: comparable Gate baseline/final arithmetic reconciled;
cumulative uncovered-unit reduction relative to the #3996 baseline exceeds 180
on current main; deliberate-break proof recorded for all five tests introduced
by #3996. Stop rule: two failed required evidence steps or 60 minutes elapsed.

## Partial local branch discarded

`closer/issue-3995` commit `8ea1feb8c` added three trivial helper tests and
claimed mutations without terminal output. It was **not** merged. This repair
discards that commit entirely and replaces it with the receipts below.

## Target selection (issue #3995 ranking)

| Rank | Target | Escaped-defect signals | Churn | Issue-listed units |
| --- | --- | ---: | ---: | ---: |
| 1 | `scripts/aggregate_agent_metrics.py` | 16 | 45 | 33 |
| 2 | `scripts/check_consumer_sync_drift.py` | 6 | 14 | 194 |

Selection follows escaped-defect priority, then churn, then uncovered mass.
No additional ranked target was added: later main revisions (#4012, #4021,
#4084, #4163) extended the same two modules within this issue scope.

## Comparable Gate measurements (Miss + BrPart from `term-missing`)

Source: recovered Python CI job logs embedded in Gate workflow runs. Artifacts
for run `38990764649` are expired (`total_count: 0`); log lines are used instead.

| Stage | Gate run | `aggregate_agent_metrics` | `check_consumer_sync_drift` | Combined |
| --- | --- | ---: | ---: | ---: |
| Baseline (pre-#3996) | [38938420079](https://github.com/stranske/Workflows/actions/runs/38938420079) | 42 + 48 = 90 | 115 + 49 = 164 | **254** |
| #3996 merged head | [38985614999](https://github.com/stranske/Workflows/actions/runs/38985614999) | 5 + 17 = 22 | 73 + 39 = 112 | **134** |
| Current main (Nov 2026) | [41653854062](https://github.com/stranske/Workflows/actions/runs/41653854062) | 0 + 3 = 3 | 0 + 0 = 0 | **3** |

Reconciliation notes:

- #3996 reported a **43**-unit target-only local reduction; recounting the PR's
  own before/after statement and partial-branch columns yields **61** units
  `(12+23)-(6+18)` plus `(114+48)-(73+39)`.
- Whole-suite Gate baseline→#3996 final is **120** units (`254 → 134`).
- Cumulative baseline→current main is **251** units (`254 → 3`), **71** above the
  ~180 goal. The shortfall against 180 was closed on main after #3996 merged,
  not by re-litigating #3996's diff.

Remaining on current main: three partial branches in
`scripts/aggregate_agent_metrics.py` (`492->481`, `954->910`, `1011->996`) under
whole-suite collection. Exercising the opposite branch arms in isolation would
require counterfactual inputs that other suite tests already saturate; no
production change or exclusion was applied.

## Named suite validation

```bash
/opt/anaconda3/bin/python3 -m pytest \
  tests/scripts/test_aggregate_agent_metrics.py \
  tests/scripts/test_check_consumer_sync_drift.py --no-cov
```

Output (2026-11-03): `146 passed`.

## Deliberate break and restore

See [mutation-receipt.md](mutation-receipt.md) for terminal output for all five
#3996 tests:

1. `test_uncovered_metric_helpers_preserve_legacy_and_error_contracts`
2. `test_main_writes_actionable_reports_for_early_preflight_failures`
3. `test_main_rejects_invalid_configuration_and_unusable_tokens`
4. `test_main_compares_manifest_files_and_writes_converged_summary`
5. `test_main_reports_body_drift_but_ignores_syncer_header_differences`

Each mutation was reverted before the next; restored greens are recorded there.
