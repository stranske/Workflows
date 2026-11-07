"""The delivered report-family source change keeps one exact-head delivery linkage."""

from __future__ import annotations

import copy

from scripts.source_delivery_linkage import REPORT_FAMILY_DELIVERY_3902, linkage_gaps

HEAD = "86a036ee03344e1d660fc7528bb21b06e7bea642"


def _record() -> dict:
    return copy.deepcopy(REPORT_FAMILY_DELIVERY_3902)


def test_report_family_delivery_links_review_ci_merge_and_disposition() -> None:
    record = REPORT_FAMILY_DELIVERY_3902
    assert linkage_gaps(record) == ()
    assert record["head_sha"] == HEAD
    assert record["exact_head_review"]["commit_sha"] == HEAD
    assert {run["head_sha"] for run in record["actual_ci"]} == {HEAD}
    assert record["guarded_merge"]["merge_commit"] != HEAD
    assert record["guarded_merge"]["auto_merge_job"] == "skipped"
    assert record["durable_disposition"]["head_sha"] == HEAD
    assert record["durable_disposition"]["run_id"] == 38618948337
    assert record["durable_disposition"]["workflow_conclusion"] == "success"
    assert record["durable_disposition"]["disposition"] == "NON_PASS"
    assert record["durable_disposition"]["provider_verdict"] == "CONCERNS"


def test_missing_delivery_channel_is_unlinked() -> None:
    for channel in (
        "exact_head_review",
        "actual_ci",
        "guarded_merge",
        "durable_disposition",
    ):
        record = _record()
        del record[channel]
        assert channel in linkage_gaps(record)


def test_ci_on_another_head_is_unlinked() -> None:
    record = _record()
    record["actual_ci"][0]["head_sha"] = "a" * 40
    assert "actual_ci[0].head" in linkage_gaps(record)


def test_workflow_success_cannot_override_non_pass_disposition() -> None:
    record = _record()
    record["durable_disposition"]["disposition"] = "PASS"
    assert "durable_disposition.overrides_provider" in linkage_gaps(record)

    preserved = _record()
    assert preserved["durable_disposition"]["workflow_conclusion"] == "success"
    assert linkage_gaps(preserved) == ()


def test_merge_commit_must_differ_from_the_reviewed_head() -> None:
    record = _record()
    record["guarded_merge"]["merge_commit"] = HEAD
    assert "guarded_merge.merge_commit" in linkage_gaps(record)


def test_unrecorded_auto_merge_job_state_is_unlinked() -> None:
    record = _record()
    record["guarded_merge"]["auto_merge_job"] = "assumed"
    assert "guarded_merge.auto_merge_job" in linkage_gaps(record)
