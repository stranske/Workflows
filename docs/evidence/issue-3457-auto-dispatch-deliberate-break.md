# PR #3584 deliberate-break evidence disposition

Issue [#3594](https://github.com/stranske/Workflows/issues/3594) records that merged
PR [#3584](https://github.com/stranske/Workflows/pull/3584) did not preserve the
deliberate-break transcript required by source issue
[#3457](https://github.com/stranske/Workflows/issues/3457). The original PR head was
`b63778626ddcf42e8009400c750a9682615ae856`, and the squash merge was
`b4c0862874dea7ca4157c3e353f449f9be8387d6`.

## Historical record

The merged PR contains the MAINT-77 to MAINT-78 dispatch implementation and the
successful named test, but its body and comments do not contain the intentional
failure and restored-pass console output requested by #3457. That missing output
cannot be represented as evidence captured during PR #3584 without inventing
history.

## Current reproduction

The gate remains reproducible on `main`. On 2026-09-27, at base commit
`0ff1178a2`, the step name `Dispatch evaluation pilot on catalog drift` was
temporarily changed to `Deliberately disabled evaluation pilot dispatch` in
`.github/workflows/maint-77-model-registry-freshness.yml`. No test assertion or
other product behavior was changed.

Command:

```text
python3 -m pytest tests/workflows/test_model_eval_pilot_workflow.py -k auto_dispatch -q
```

Raw captured failure while the dispatch step was neutered (unmodified pytest
output):

```text
F                                                                        [100%]
=================================== FAILURES ===================================
________ test_auto_dispatch_maint77_chains_to_maint78_on_catalog_drift _________

    def test_auto_dispatch_maint77_chains_to_maint78_on_catalog_drift() -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load(
            (root / ".github/workflows/maint-77-model-registry-freshness.yml").read_text(
                encoding="utf-8"
            )
        )
        dispatch_job = workflow["jobs"]["dispatch-evaluation-pilot"]
        assert "discovery_drift == 'true'" in dispatch_job["if"]
        assert dispatch_job["concurrency"]["group"] == "maint-77-evaluation-pilot-dispatch"
        assert dispatch_job["permissions"]["actions"] == "write"
        needs = dispatch_job["needs"]
        assert needs == ["freshness"] or needs == "freshness"
        steps = dispatch_job["steps"]
        api_setup = next(step for step in steps if step.get("name") == "Setup API client")
        assert api_setup["uses"] == "./.github/actions/setup-api-client"
        dispatch_idx = next(i for i, step in enumerate(steps) if step.get("name") == "Setup API client")
        refresh_idx = next(
            i
            for i, step in enumerate(steps)
            if step.get("name") == "Refresh pilot candidates from registry"
        )
        assert dispatch_idx < refresh_idx
        refresh = steps[refresh_idx]
        assert "tools.refresh_model_eval_candidates --write" in refresh["run"]
        assert "--catalog-discovery catalog-discovery.json" in refresh["run"]
        upload = next(
            step for step in steps if step.get("name") == "Upload pilot candidates for MAINT-78"
        )
        assert upload["with"]["name"] == "maint-77-pilot-candidates"
>       dispatch = next(
            step for step in steps if step.get("name") == "Dispatch evaluation pilot on catalog drift"
        )
E       StopIteration

tests/workflows/test_model_eval_pilot_workflow.py:57: StopIteration
=========================== short test summary info ============================
FAILED tests/workflows/test_model_eval_pilot_workflow.py::test_auto_dispatch_maint77_chains_to_maint78_on_catalog_drift
1 failed, 3 deselected in 0.27s
```

The original step name was then restored with no residual workflow diff. The
exact command passed:

```text
.                                                                        [100%]
1 passed, 3 deselected in 0.24s
```

This is a current, reproducible fail-to-pass proof for the same named gate. It
closes the durable evidence gap without claiming that the output was captured
during the historical PR #3584 implementation run.
