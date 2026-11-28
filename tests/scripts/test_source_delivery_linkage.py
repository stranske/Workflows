"""The delivered report-family source change keeps one exact-head delivery linkage.

The successful verifier run published a durable NON_PASS disposition.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

HEAD = "86a036ee03344e1d660fc7528bb21b06e7bea642"


_SHA_CHARS = frozenset("0123456789abcdef")
_CHANNELS = (
    "exact_head_review",
    "actual_ci",
    "guarded_merge",
    "durable_disposition",
)
_AUTO_MERGE_JOBS = frozenset({"success", "skipped", "failure"})
_DISPOSITIONS = frozenset({"PASS", "NON_PASS", "CONCERNS"})


def _sha(value: object) -> str | None:
    if isinstance(value, str) and len(value) == 40 and set(value) <= _SHA_CHARS:
        return value
    return None


def _https(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _review_gaps(review: object, head: str | None) -> tuple[str, ...]:
    if not isinstance(review, Mapping):
        return ("exact_head_review",)
    gaps: list[str] = []
    commit = _sha(review.get("commit_sha"))
    if commit is None or (head is not None and commit != head):
        gaps.append("exact_head_review.commit_sha")
    if not _text(review.get("reviewer")) or not _text(review.get("state")):
        gaps.append("exact_head_review.identity")
    if not _text(review.get("submitted_at")) or not _https(review.get("url")):
        gaps.append("exact_head_review.url")
    return tuple(gaps)


def _ci_gaps(runs: object, head: str | None) -> tuple[str, ...]:
    if not isinstance(runs, Sequence) or isinstance(runs, (str, bytes)) or not runs:
        return ("actual_ci",)
    gaps: list[str] = []
    for index, run in enumerate(runs):
        prefix = f"actual_ci[{index}]"
        if not isinstance(run, Mapping):
            gaps.append(prefix)
            continue
        run_head = _sha(run.get("head_sha"))
        run_id = run.get("run_id")
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
            gaps.append(f"{prefix}.run_id")
        if run.get("conclusion") != "success" or run_head is None or (head and run_head != head):
            gaps.append(f"{prefix}.head")
        if not _text(run.get("name")) or not _https(run.get("url")):
            gaps.append(f"{prefix}.url")
    return tuple(gaps)


def _merge_gaps(merge: object, head: str | None) -> tuple[str, ...]:
    if not isinstance(merge, Mapping):
        return ("guarded_merge",)
    gaps: list[str] = []
    merge_commit = _sha(merge.get("merge_commit"))
    if merge_commit is None or (head is not None and merge_commit == head):
        gaps.append("guarded_merge.merge_commit")
    if (
        not _text(merge.get("actor"))
        or not _text(merge.get("merged_at"))
        or not _https(merge.get("url"))
    ):
        gaps.append("guarded_merge.identity")
    run_id = merge.get("orchestrator_run_id")
    if (
        not isinstance(run_id, int)
        or isinstance(run_id, bool)
        or run_id <= 0
        or merge.get("auto_merge_job") not in _AUTO_MERGE_JOBS
    ):
        gaps.append("guarded_merge.auto_merge_job")
    return tuple(gaps)


def _disposition_gaps(disposition: object, head: str | None) -> tuple[str, ...]:
    if not isinstance(disposition, Mapping):
        return ("durable_disposition",)
    gaps: list[str] = []
    run_id = disposition.get("run_id")
    recorded = disposition.get("disposition")
    provider = disposition.get("provider_verdict")
    bound_head = _sha(disposition.get("head_sha"))
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        gaps.append("durable_disposition.run_id")
    if disposition.get("workflow_conclusion") not in {"success", "failure"}:
        gaps.append("durable_disposition.workflow_conclusion")
    if recorded not in _DISPOSITIONS or not _text(provider):
        gaps.append("durable_disposition.verdict")
    elif recorded == "PASS" and provider != "PASS":
        gaps.append("durable_disposition.overrides_provider")
    if bound_head is None or (head is not None and bound_head != head):
        gaps.append("durable_disposition.head_sha")
    if not _https(disposition.get("run_url")) or not _https(disposition.get("comparison_url")):
        gaps.append("durable_disposition.url")
    return tuple(gaps)


def _linkage_gaps(record: Mapping[str, object]) -> tuple[str, ...]:
    """Return why review, CI, merge, and disposition are not one exact-head delivery."""
    if not isinstance(record, Mapping):
        return ("record",)
    gaps: list[str] = []
    pull_request = record.get("pull_request")
    if not isinstance(pull_request, int) or isinstance(pull_request, bool) or pull_request <= 0:
        gaps.append("pull_request")
    if not _text(record.get("repository")):
        gaps.append("repository")
    head = _sha(record.get("head_sha"))
    if head is None:
        gaps.append("head_sha")
    for channel in _CHANNELS:
        if channel not in record:
            gaps.append(channel)
    if "exact_head_review" in record:
        gaps.extend(_review_gaps(record.get("exact_head_review"), head))
    if "actual_ci" in record:
        gaps.extend(_ci_gaps(record.get("actual_ci"), head))
    if "guarded_merge" in record:
        gaps.extend(_merge_gaps(record.get("guarded_merge"), head))
    if "durable_disposition" in record:
        gaps.extend(_disposition_gaps(record.get("durable_disposition"), head))
    return tuple(gaps)


# Delivered report-family source change. Inspected 2026-11-06 from PR #3902.
# The orchestrator auto-merge job was skipped; GitHub records an owner merge
# after the exact-head topology gates. Provider comparison stayed NON_PASS.
def _record() -> dict:
    fixture = Path(__file__).resolve().parents[1] / "fixtures/issue_3901/source_delivery_3902.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


def test_report_family_delivery_links_review_ci_merge_and_disposition() -> None:
    record = _record()
    assert _linkage_gaps(record) == ()
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
        assert channel in _linkage_gaps(record)


def test_ci_on_another_head_is_unlinked() -> None:
    record = _record()
    record["actual_ci"][0]["head_sha"] = "a" * 40
    assert "actual_ci[0].head" in _linkage_gaps(record)


def test_workflow_success_cannot_override_non_pass_disposition() -> None:
    record = _record()
    record["durable_disposition"]["disposition"] = "PASS"
    assert "durable_disposition.overrides_provider" in _linkage_gaps(record)

    preserved = _record()
    assert preserved["durable_disposition"]["workflow_conclusion"] == "success"
    assert _linkage_gaps(preserved) == ()


def test_merge_commit_must_differ_from_the_reviewed_head() -> None:
    record = _record()
    record["guarded_merge"]["merge_commit"] = HEAD
    assert "guarded_merge.merge_commit" in _linkage_gaps(record)


def test_unrecorded_auto_merge_job_state_is_unlinked() -> None:
    record = _record()
    record["guarded_merge"]["auto_merge_job"] = "assumed"
    assert "guarded_merge.auto_merge_job" in _linkage_gaps(record)
