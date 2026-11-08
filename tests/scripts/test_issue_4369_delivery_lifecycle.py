"""Bind causal delivery receipts without mistaking a sealed candidate for a merge."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

EVIDENCE = Path(__file__).resolve().parents[2] / "docs/evidence/issue-4369/runtime-4550"
CONSUMER = "stranske/Portable-Alpha-Extension-Model"
FOLLOWING = 42485792262
RETRY = 42485974523


def read(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def protocol(body: str, marker: str) -> dict:
    (value,) = re.findall(rf"<!-- {re.escape(marker)} (.+?) -->", body)
    return json.loads(value)


def expected_binding() -> dict:
    pr = read("supported-live-observation.json")["consumer_pr"]
    delivery = protocol(pr["body"], "sync-pr-delivery-record:v1")
    assert pr["head"]["repo"]["full_name"] == delivery["repository"] == CONSUMER
    assert delivery["head_observed_sha"] == delivery["sealed_head_sha"] == pr["head"]["sha"]
    assert delivery["delivery_state"] == "sealed"
    return {
        "repository": CONSUMER,
        "pr": pr["number"],
        "head_sha": pr["head"]["sha"],
        "source_commit": delivery["source_commit"],
        "plan_id": delivery["plan_id"],
        "delivery_generation": delivery["generation"],
    }


def assert_finding_binding(report: dict) -> None:
    expected = expected_binding()
    (result,) = [row for row in report["results"] if f'{row["owner"]}/{row["repo"]}' == CONSUMER]
    assert {key: result[key] for key in expected if key != "repository"} == {
        key: value for key, value in expected.items() if key != "repository"
    }
    finding = result["review_finding_disposition"]
    assert finding["binding"] == expected
    assert finding["raw_active_count"] == 0
    assert finding["blocked"] is False
    assert finding["errors"] == finding["findings"] == []
    assert all(finding["aggregates"][key] == 0 for key in ("blocking", "nonblocking", "unknown"))
    assert all(ids == [] for ids in finding["disposition_thread_ids"].values())
    assert "4434491702" not in json.dumps(finding)


@pytest.mark.parametrize("run_id", [FOLLOWING, RETRY])
def test_causal_reports_bind_findings_to_the_selected_payload(run_id: int) -> None:
    report = read(f"maint71-{run_id}-sync-pr-merge-report.json")
    assert report["run"]["run_id"] == run_id
    assert_finding_binding(report)


@pytest.mark.parametrize("run_id", [FOLLOWING, RETRY])
@pytest.mark.parametrize("field", list(expected_binding()))
def test_causal_report_rejects_a_disposition_from_another_delivery(run_id: int, field: str) -> None:
    report = deepcopy(read(f"maint71-{run_id}-sync-pr-merge-report.json"))
    row = next(row for row in report["results"] if row.get("repo") == CONSUMER.split("/")[1])
    binding = row["review_finding_disposition"]["binding"]
    binding[field] = binding[field] + 1 if field == "pr" else binding[field] + "-substituted"
    with pytest.raises(AssertionError):
        assert_finding_binding(report)


def test_producer_dispatch_is_followed_by_the_retained_maint71_run() -> None:
    observation = read("supported-live-observation.json")
    producer_id = observation["producer_run"]
    producer = read(f"maint68-{producer_id}.json")
    pr = observation["consumer_pr"]
    metadata = protocol(pr["body"], "workflows-consumer-sync:v1")
    binding = expected_binding()
    assert metadata["run_id"] == str(producer_id)
    assert metadata["source_sha"] == metadata["source_commit"] == binding["source_commit"]
    assert metadata["plan_id"] == binding["plan_id"]
    assert metadata["consumer_repo"] == binding["repository"]
    assert producer["status"] == "completed" and producer["conclusion"] == "success"
    log = (EVIDENCE / f"maint68-{producer_id}.log").read_text(encoding="utf-8")
    assert f'SOURCE_COMMIT: {binding["source_commit"]}' in log
    assert f'PLAN_ID: {binding["plan_id"]}' in log
    # Dispatch creates the run before its completion notice and before the
    # producer itself completes. Ordering only by producer completion loses it.
    (notice,) = re.findall(
        r"(2026-\S+) ##\[notice\]Dispatched Maint 71 candidate reconciliation", log
    )
    fresh = read("delivery-lifecycle-refresh.json")
    following = fresh["following_maint71"]
    inventory = fresh["run_inventory"]
    runs = [run for page in inventory["pages"] for run in page["runs"]]
    candidates = [run for run in runs if run["path"].endswith("/maint-71-merge-sync-prs.yml")]
    assert datetime.fromisoformat(producer["createdAt"]) < datetime.fromisoformat(
        inventory["start"]
    )
    assert min(candidates, key=lambda run: run["created_at"])["id"] == following["id"] == FOLLOWING
    assert observation["following_run"] == FOLLOWING
    assert (
        datetime.fromisoformat(following["created_at"])
        <= datetime.fromisoformat(notice)
        <= datetime.fromisoformat(producer["updatedAt"])
    )


def test_final_template_bytes_reach_the_candidate_but_not_the_merged_consumer() -> None:
    observation = read("supported-live-observation.json")
    frozen = expected_binding()["source_commit"]
    template = read("downstream-followup.json")["payloads"]["template"]
    assert template["ref"] == frozen
    assert template["path"] == "templates/consumer-repo/tools/subscription_llm.py"
    assert template["repository"] == "stranske/Workflows"
    payloads = {**observation["payloads"], "template": template}
    for key, payload in payloads.items():
        content = payload["content"].encode("utf-8")
        assert (
            hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest() == payload["sha"]
        )
        owner = "stranske/Workflows" if key in {"source", "template"} else CONSUMER
        assert payload["repository"] == owner
        assert (
            payload["url"] == f'https://github.com/{owner}/blob/{payload["ref"]}/{payload["path"]}'
        )
    source, candidate, main = (
        payloads[key] for key in ("source", "consumer_candidate", "consumer_main")
    )
    assert source["ref"] == frozen
    assert source["content"] == template["content"] == candidate["content"]
    assert source["sha"] != main["sha"]
    assert candidate["ref"] == expected_binding()["head_sha"]
    assert main["ref"] == observation["consumer_main"]["commit"]["sha"]
    pr = observation["consumer_pr"]
    assert pr["state"] == "open" and pr["draft"] is False
    # GitHub can supply a prospective merge_commit_sha for an open PR.
    assert pr["merged"] is False and pr["merged_at"] is None
    assert observation["final_delivery_acceptance"] is False


def test_green_candidate_does_not_satisfy_campaign_merge_acceptance() -> None:
    report = read(f"maint71-{RETRY}-sync-pr-merge-report.json")
    (selected,) = [row for row in report["results"] if row.get("pr") == expected_binding()["pr"]]
    assert selected["status"] == "campaign_prepared"
    assert selected["next_command"] == "merge-current-delivery"
    assert report["summary"]["merged"] == 0
    missing = [row for row in report["results"] if row["status"] == "stable_base_refresh_required"]
    assert len(missing) == 2
    assert all(row["reason"] == "candidate_pr_and_no_change_evidence_missing" for row in missing)
    (canary,) = read(f"maint71-{RETRY}-sync-canary-evidence.json")["results"]
    assert canary["required_check_state"] == "success"
    assert canary["review_disposition"]["binding"] == expected_binding()
    assert canary["evidence_source"] == "open-candidate"
    job = next(
        job for job in read(f"maint71-{RETRY}.json")["jobs"] if job["name"] == "merge_sync_prs"
    )
    steps = {step["name"]: step["conclusion"] for step in job["steps"]}
    assert steps["Refresh stale candidate bases"] == "failure"
    assert steps["Commit prepared sync campaign"] == "skipped"


def test_fresh_inventory_and_all_comment_pages_preserve_the_observation_boundary() -> None:
    fresh = read("delivery-lifecycle-refresh.json")
    inventory = fresh["run_inventory"]
    pages, capacity = inventory["pages"], inventory["per_page"]
    total = pages[0]["total_count"]
    assert len(pages) == (total + capacity - 1) // capacity
    collected = []
    for number, page in enumerate(pages, start=1):
        assert page["page"] == number and page["total_count"] == total
        assert parse_qs(urlparse(page["url"]).query) == {
            "per_page": [str(capacity)],
            "page": [str(number)],
            "created": [f'{inventory["start"]}..{inventory["end"]}'],
        }
        assert len(page["runs"]) == min(capacity, total - (number - 1) * capacity)
        collected.extend(page["runs"])
    assert len({run["id"] for run in collected}) == total
    assert all(inventory["start"] <= run["created_at"] <= inventory["end"] for run in collected)
    collection = fresh["comments"]
    comments = [comment for page in collection["pages"] for comment in page]
    assert all(len(page) == collection["per_page"] for page in collection["pages"][:-1])
    assert len(collection["pages"][-1]) < collection["per_page"]
    assert [comment["id"] for comment in comments] == collection["all_pages_connector_ids"]
    assert len({comment["id"] for comment in comments}) == len(comments)
    through = datetime.fromisoformat(fresh["collection_started_at_utc"])
    assert all(datetime.fromisoformat(comment["updated_at"]) <= through for comment in comments)
    scoped = [
        comment
        for comment in comments
        if comment["body"].startswith("<!-- sync-core/v1 ")
        and re.search(r"#discussion_r4434491702(?!\d)", comment["body"])
    ]
    assert max(scoped, key=lambda comment: comment["created_at"])["id"] == 6649911684
    assert (
        fresh["historical_thread"]["is_resolved"]
        is fresh["historical_thread"]["is_outdated"]
        is True
    )
    assert fresh["consumer_pr"]["merged"] is False
    assert fresh["consumer_pr"]["draft"] is fresh["source_pr"]["draft"] is False
    assert fresh["consumer_main"]["sha"] == fresh["consumer_pr"]["base"]["sha"]
    assert fresh["final_delivery_acceptance"] is False
