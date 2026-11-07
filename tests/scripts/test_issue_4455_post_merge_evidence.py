"""Replay #4455 live evidence without treating historical success as latest success."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[1] / "fixtures/issue_4455/post_merge_evidence.json"
LATEST_EVIDENCE = EVIDENCE.with_name("latest_runs_evidence.json")
WORKFLOW = ".github/workflows/maint-71-merge-sync-prs.yml"


@pytest.fixture(scope="module")
def receipt() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def latest_receipt() -> dict:
    return json.loads(LATEST_EVIDENCE.read_text(encoding="utf-8"))


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    assert parsed.utcoffset() is not None, "evidence timestamps must include their timezone"
    return parsed


def test_fix_was_merged_into_main(receipt: dict) -> None:
    fix = receipt["fix_pr"]
    assert fix["number"] == 4443
    assert fix["merged"] is True
    assert fix["base"] == {"ref": "main", "repo": "stranske/Workflows"}
    assert fix["merge_commit_sha"] == "81e575a008db219b8b63761014025d182d095128"
    assert utc(fix["merged_at"]) < utc(receipt["observed_at"])


def test_three_recent_maint71_runs_started_after_merge(receipt: dict) -> None:
    runs = receipt["recent_runs"]
    assert len(runs) == 3
    assert len({run["id"] for run in runs}) == 3
    starts = [utc(run["created_at"]) for run in runs]
    assert starts == sorted(starts, reverse=True)
    for run in runs:
        assert run["path"] == WORKFLOW
        assert run["head_branch"] == "main"
        assert utc(receipt["fix_pr"]["merged_at"]) < utc(run["created_at"])
        assert utc(run["created_at"]) <= utc(receipt["observed_at"])


def test_successful_historical_run_is_bound_to_the_merged_fix(receipt: dict) -> None:
    run = receipt["verified_run"]
    assert run["id"] == 41958285569
    assert run["path"] == WORKFLOW
    assert run["head_branch"] == "main"
    assert run["head_sha"] == receipt["fix_pr"]["merge_commit_sha"]
    assert run["status"] == "completed"
    assert run["conclusion"] == "success"
    assert utc(receipt["fix_pr"]["merged_at"]) < utc(run["created_at"])
    assert utc(run["created_at"]) <= utc(run["updated_at"]) < utc(receipt["observed_at"])


def test_consumer_report_has_no_original_subscription_findings(receipt: dict) -> None:
    report = receipt["consumer_report"]
    assert (report["owner"], report["repo"], report["pr"]) == (
        "stranske",
        "Portable-Alpha-Extension-Model",
        2454,
    )
    assert report["source_commit"] == receipt["fix_pr"]["merge_commit_sha"]
    review = report["review_finding_disposition"]
    assert review["binding"]["repository"] == "stranske/Portable-Alpha-Extension-Model"
    for key in ("pr", "head_sha", "source_commit"):
        assert review["binding"][key] == report[key]
    assert review["errors"] == []
    assert review["raw_active_count"] == len(review["findings"]) == 6
    for finding in review["findings"]:
        assert finding["path"] != "scripts/langchain/_llm_client.py"
        assert finding["url"].rsplit("_r", 1)[-1] not in {"4434482074", "4434491654"}
    # Other findings remain blocking; workflow success did not merge this PR.
    assert review["blocked"] is True


def test_no_sync_core_comment_after_the_verified_run(receipt: dict) -> None:
    comments = receipt["issue_comments"]
    assert len(comments) == receipt["collection"]["comments_returned"] == 39
    assert len(comments) < 100  # The API response fits one complete page.
    sync = [comment for comment in comments if comment["sync_core"]]
    assert len(sync) == 13
    for comment in sync:
        assert comment["body"].startswith("<!-- sync-core/v1 handoff ")
        assert utc(comment["created_at"]) < utc(receipt["verified_run"]["created_at"])
    assert max(comment["created_at"] for comment in sync) == "2026-11-04T06:00:32Z"


def test_historical_success_does_not_complete_the_latest_three_acceptance(receipt: dict) -> None:
    recent = receipt["recent_runs"]
    assert receipt["verified_run"]["id"] not in {run["id"] for run in recent}
    assert all(run["status"] == "completed" and run["conclusion"] == "failure" for run in recent)
    assert not any(run["conclusion"] == "success" for run in recent)


def test_latest_three_selection_retains_interleaved_workflows(latest_receipt: dict) -> None:
    inventory = latest_receipt["run_inventory_prefix"]
    assert len(inventory) <= latest_receipt["collection"]["runs_returned"] == 100
    assert len({run["id"] for run in inventory}) == len(inventory)
    assert [utc(run["created_at"]) for run in inventory] == sorted(
        (utc(run["created_at"]) for run in inventory), reverse=True
    )
    positions = [index for index, run in enumerate(inventory) if run["path"] == WORKFLOW]
    # Retain every row through match three so unrelated workflows cannot obscure
    # the latest successes or justify selecting an older success instead.
    assert positions == [0, 5, 12]
    assert positions[-1] == len(inventory) - 1
    assert [inventory[index]["id"] for index in positions] == [
        42346303152,
        42346256308,
        42346191321,
    ]


def test_latest_three_contains_completed_success_after_merge(
    receipt: dict, latest_receipt: dict
) -> None:
    recent = [run for run in latest_receipt["run_inventory_prefix"] if run["path"] == WORKFLOW]
    assert len(recent) == 3
    for run in recent:
        assert run["head_branch"] == "main"
        assert utc(receipt["fix_pr"]["merged_at"]) < utc(run["created_at"])
        assert utc(run["created_at"]) < utc(latest_receipt["observed_at"])
    successes = [
        run for run in recent if run["status"] == "completed" and run["conclusion"] == "success"
    ]
    assert successes
    verified = latest_receipt["verified_success"]
    assert {key: verified[key] for key in successes[0]} == successes[0]
    assert verified["id"] != receipt["verified_run"]["id"]
    assert utc(verified["created_at"]) <= utc(verified["run_started_at"])
    assert utc(verified["run_started_at"]) <= utc(verified["updated_at"])
    assert utc(verified["updated_at"]) < utc(latest_receipt["observed_at"])


def test_fresh_comments_have_no_sync_core_handoff_after_latest_success(
    receipt: dict, latest_receipt: dict
) -> None:
    comments = latest_receipt["issue_comments"]
    collection = latest_receipt["collection"]
    assert len(comments) == collection["comments_returned"] < collection["comments_page_capacity"]
    assert len({comment["id"] for comment in comments}) == len(comments)
    # The fresh full page confirms that no comments were added since the first
    # observation, rather than carrying the old absence claim forward unchecked.
    assert {comment["id"] for comment in comments} == {
        comment["id"] for comment in receipt["issue_comments"]
    }
    sync = [
        comment for comment in comments if comment["body_prefix"] == "<!-- sync-core/v1 handoff "
    ]
    assert {comment["id"] for comment in sync} == {
        comment["id"] for comment in receipt["issue_comments"] if comment["sync_core"]
    }
    assert sync
    for comment in sync:
        assert utc(comment["created_at"]) < utc(latest_receipt["verified_success"]["created_at"])
