# Issue #4170 closer evidence (repair of merged #4172)

Checked 2026-11-05. Refs [#4170](https://github.com/stranske/Workflows/issues/4170).
Implementation lives in merge commit
[`cbad3c6f`](https://github.com/stranske/Workflows/commit/cbad3c6f0f0f8e76b2dbaf382148ef4301de253d)
([#4172](https://github.com/stranske/Workflows/pull/4172)). This repair adds
validation evidence and an isolated restoration regression test; it does not
change production scripts.

Provisioned branch `closer-r2/issue-4170` started clean at current `main`. Local
branches `closer/issue-4170` and `closer-r1/issue-4170` had no commits ahead of
`main`; nothing was merged or discarded from prior closer attempts.

## New tests introduced by #4172 (22 functions)

| # | Test module | Function |
| --- | --- | --- |
| 1 | `tests/scripts/test_docs_drift_fix_agent.py` | `test_repo_detection_falls_back_when_git_is_unavailable` |
| 2 | `tests/scripts/test_docs_drift_fix_agent.py` | `test_config_and_scan_helpers_reject_bad_shapes_and_use_defaults` |
| 3 | `tests/scripts/test_docs_drift_fix_agent.py` | `test_plan_output_writer_and_batch_limit_are_executable` |
| 4 | `tests/scripts/test_docs_drift_fix_agent.py` | `test_default_docs_from_config_accepts_null_maps_and_skips_bad_items` |
| 5 | `tests/scripts/test_docs_drift_fix_agent.py` | `test_findings_helpers_and_scan_json_load_cover_skip_paths` |
| 6 | `tests/scripts/test_docs_drift_fix_agent.py` | `test_legacy_markers_and_apply_issue_failure_paths` |
| 7 | `tests/scripts/test_docs_drift_fix_agent.py` | `test_main_validation_and_json_output` |
| 8 | `tests/scripts/test_export_keepalive_durability.py` | `test_helpers_handle_invalid_metadata_and_reverts_before_the_merge` |
| 9 | `tests/scripts/test_export_keepalive_durability.py` | `test_build_records_skips_invalid_rows_and_can_include_pending` |
| 10 | `tests/scripts/test_export_keepalive_durability.py` | `test_registry_fetch_and_ndjson_helpers_cover_error_and_success_paths` |
| 11 | `tests/scripts/test_export_keepalive_durability.py` | `test_fetch_repo_payload_requests_the_merged_and_revert_views` |
| 12 | `tests/scripts/test_export_keepalive_durability.py` | `test_cli_rejects_invalid_numeric_limits` (parametrize; red-green uses `[--days-0]`) |
| 13 | `tests/scripts/test_export_keepalive_durability.py` | `test_helpers_cover_timezone_agent_and_closing_edge_cases` |
| 14 | `tests/scripts/test_export_keepalive_durability.py` | `test_gh_json_filters_non_dicts_and_rejects_non_list_payloads` |
| 15 | `tests/scripts/test_export_keepalive_durability.py` | `test_build_records_skips_explicit_skipped_classifications` |
| 16 | `tests/scripts/test_export_keepalive_durability.py` | `test_cli_human_summary_and_partial_fetch_paths` |
| 17 | `tests/scripts/test_workflow_startup_failure_diagnostic.py` | `test_token_pacing_and_list_api_paths` |
| 18 | `tests/scripts/test_workflow_startup_failure_diagnostic.py` | `test_sweep_helpers_dedupe_repositories_and_write_action_summary` |
| 19 | `tests/scripts/test_workflow_startup_failure_diagnostic.py` | `test_fork_inference_and_startup_classification_fallbacks` |
| 20 | `tests/scripts/test_workflow_startup_failure_diagnostic.py` | `test_iter_paginated_and_hold_onset_edge_paths` |
| 21 | `tests/scripts/test_workflow_startup_failure_diagnostic.py` | `test_sweep_repository_skips_inactive_non_workflow_sparse_and_threshold` |
| 22 | `tests/scripts/test_workflow_startup_failure_diagnostic.py` | `test_sweep_summary_step_summary_and_main_error_paths` |

The six `test_workflow_startup_failure_diagnostic.py` additions above are the
startup-diagnostic suite called out in the closer brief (token pacing, sweep
helpers, fork/classification fallbacks, pagination/hold-onset edges, repository
sweep skips, and summary/CLI error paths). They were part of the same #4172 diff
hunk series as the docs and durability tests.

## Target ranking and partial coverage (178 units)

Authoritative selection is [#4170](https://github.com/stranske/Workflows/issues/4170)
(Orchestrator ranking: escaped-defect signals, then churn, then uncovered mass):

| Rank | Target | Issue CI uncovered (stmt+branch) |
| ---: | --- | ---: |
| 1 | `scripts/docs_drift_fix_agent.py` | 79 |
| 2 | `scripts/export_keepalive_durability.py` | 74 |
| 3 | `scripts/workflow_startup_failure_diagnostic.py` | 69 |
| **Total** | | **222** |

[#4172](https://github.com/stranske/Workflows/pull/4172) reported a **178** unit
reduction on a like-for-like local whole-module baseline (200 → 22 missed
stmt+branch across the three targets), short of the issue’s 222-unit ranking
because CI counts modules under the full-suite context. Residual gaps called out
in #4172 remain: cold-import `sys.path` inserts and legacy apply-issue marker
edges that need heavy `gh` orchestration. This evidence PR does not claim new
coverage; it preserves that partial-result explanation.

## Hosted CI pytest (implementation PR #4172)

Gate workflow `reusable-10-ci-python.yml` on PR #4172 succeeded at run
[39513094058](https://github.com/stranske/Workflows/actions/runs/39513094058)
(`python ci / python 3.14` job
[118938918467](https://github.com/stranske/Workflows/actions/runs/39513094058/job/118938918467)):
`52135 passed, 27 skipped, 3 xfailed` with markers
`not quarantine and not slow`, pytest-xdist `-n 4 --dist=loadgroup`, and
coverage enabled via `pyproject.toml` (full `tests/` tree, not the three-file
focus command below).

Selftest aggregate check
[39513094018](https://github.com/stranske/Workflows/actions/runs/39513094018)
(`Python Tests`) also passed for the same PR head.

## Local focused validation (this repair)

Interpreter: `/opt/anaconda3/bin/python3` (no repo `.venv` in the provisioned
worktree). Mutations run transiently in the worktree; `validate-red-green.py`
wraps each mutation, red pytest run, and red-log write in `try/finally` and
restores production bytes in `finally` before the post-restore green rerun.
Isolated regression proof (no real checkout mutation):
`tests/scripts/test_issue_4170_red_green.py`.

```bash
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_issue_4170_red_green.py -q
```

Pre-fix (no `finally` restoration): `3 failed` — production stub retained the
deliberate break after injected `KeyboardInterrupt`, `subprocess.SubprocessError`,
and red-log `OSError`. Post-fix: `3 passed in 0.22s`.

```bash
/opt/anaconda3/bin/python3 docs/evidence/issue-4170/validate-red-green.py
```

```
{
  "ok": true,
  "cases": 22
}
```

(2026-11-05 closer continuation; ~62s wall time.) After the run,
`git diff -- scripts/docs_drift_fix_agent.py scripts/export_keepalive_durability.py
scripts/workflow_startup_failure_diagnostic.py` was empty.

Per-case logs: `acceptance.json`, `red/`, and `green/`.

```bash
/opt/anaconda3/bin/python3 -m pytest \
  tests/scripts/test_docs_drift_fix_agent.py \
  tests/scripts/test_export_keepalive_durability.py \
  tests/scripts/test_workflow_startup_failure_diagnostic.py -q
```

Green suite before mutations: `112 passed in 0.81s` (`green-suite.log`).

Regenerate the mutation table:

```bash
/opt/anaconda3/bin/python3 docs/evidence/issue-4170/validate-red-green.py
```
