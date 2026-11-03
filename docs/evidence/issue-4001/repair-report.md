# Closer repair report — stranske/Workflows#4001

Implementation landed in PR #4012 (`c59f58c692`). This repair adds evidence only; production code is unchanged.

## Ranking provenance

Issue #4001 (coverage-autopilot lane C) lists three targets in Orchestrator order (escaped-defect priority, then churn, then uncovered mass):

1. `scripts/aggregate_agent_metrics.py` — 22 stated uncovered units  
2. `scripts/check_consumer_sync_drift.py` — 130  
3. `scripts/validate_run_contract.py` — 74  

No separate ranking artifact for #4001 is checked into this repository. Gate-equivalent measurement at parent `f8318e2a` (PR #4012 parent) reports **226** combined missing statements+branches across those files, matching the issue total. Target order matches the issue body; no selection deviation is claimed.

Later main commits added tests beyond PR #4012 before this repair head; after counts reflect cumulative fleet coverage on `3e513d30e`, not #4012 alone.

## Gate coverage (whole CI selection)

Command (from Gate + `reusable-10-ci-python.yml`):

```bash
/opt/anaconda3/bin/python3 -m pytest \
  -m 'not quarantine and not slow' \
  --cov --cov-config=pyproject.toml \
  --cov-report=json:<output> \
  -n auto --dist=loadgroup -q --tb=no
```

Local runs used Python **3.12.2**; Gate uses **3.14** for branch coverage. Artifacts:

| Head | Role | Log | coverage.json |
| --- | --- | --- | --- |
| `f8318e2a` | PR #4012 parent | `gate-coverage/before/pytest.log` | `gate-coverage/before/coverage.json` |
| `3e513d30e` | Repair head (main) | `gate-coverage/after/pytest.log` | `gate-coverage/after/coverage.json` |

Per-target missing statement / branch counts (from `extract_target_coverage.py`):

| Target | Before lines | Before branches | After lines | After branches | Units covered |
| --- | ---: | ---: | ---: | ---: | ---: |
| `scripts/aggregate_agent_metrics.py` | 5 | 17 | 0 | 3 | 19 |
| `scripts/check_consumer_sync_drift.py` | 73 | 57 | 0 | 0 | 130 |
| `scripts/validate_run_contract.py` | 47 | 27 | 0 | 0 | 74 |
| **Combined** | **125** | **101** | **0** | **3** | **223** |

The ~180-unit goal is exceeded (**223** covered). Remaining **3** branch gaps on `aggregate_agent_metrics.py` are documented in `verification.json`.

## Scoped pytest (judge command)

```bash
/opt/anaconda3/bin/python3 -m pytest \
  tests/contracts/test_validate_run_contract.py \
  tests/scripts/test_aggregate_agent_metrics.py \
  tests/scripts/test_check_consumer_sync_drift.py \
  -m 'not quarantine and not slow' -q
```

Result: **238 passed** (`scoped-pytest.log`).

## Break / revert / pass (six PR #4012 tests)

Automated probes: `run_break_revert_probes.py` → `break-revert-proof.json` (RED exit 1, restored GREEN exit 0 for each node).

| Test | Production surface |
| --- | --- |
| `test_document_identity_cross_checks_reject_conflicting_or_noncanonical_values` | `_check_document_page` |
| `test_standalone_validators_and_evidence_paths_fail_closed_on_unreadable_inputs` | `_safe_evidence_path` parent traversal |
| `test_metrics_helpers_preserve_empty_and_malformed_input_boundaries` | `_artifact_family` |
| `test_drift_cli_and_remote_read_boundaries` | `remote_blob_text` base64 decode |
| `test_drift_summary_renders_actionable_nested_report_data` | `write_summary_markdown` repo summary heading |
| `test_drift_network_helpers_fail_closed_without_readable_probe_targets` | `select_read_token` empty candidates |

## Gate CI

The repair PR triggers the repository **Gate** workflow; link and artifact paths are recorded in the PR body after the run completes.
