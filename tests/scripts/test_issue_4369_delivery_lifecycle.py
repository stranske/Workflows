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
FIX_PATHS = sorted(
    [
        ".github/scripts/__tests__/keepalive-loop.test.js",
        ".github/scripts/__tests__/maint71-delivery-receipts.test.js",
        ".github/scripts/__tests__/verifier-correction-artifacts.test.js",
        ".github/scripts/__tests__/verifier-correction-coding.test.js",
        ".github/scripts/maint71_merge_sync_prs.js",
        "tests/scripts/test_issue_4369_delivery_lifecycle.py",
        "tests/scripts/test_issue_4369_downstream_evidence.py",
        "tests/scripts/test_issue_pr_context.py",
        "tests/scripts/test_llm_client_shared.py",
    ]
)


def read(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def acceptance_revision_receipts() -> dict:
    return {
        "selection": read("4558-revision-selection.json"),
        "main": read("4558-main-observation.json"),
        "pull": read("4558-fixture-pr.json"),
        "ancestry": read("4558-ancestor-compare.json"),
        "repair": read("4558-repair-compare.json"),
        "fix_inventory": read("4558-round8-fix-inventory.json"),
        "node": read("4557-exact-main/node-full.json"),
        "python": read("4557-exact-main/python-full.json"),
    }


def assert_acceptance_revision_binding(receipts: dict) -> None:
    """Check retained revision evidence, without authorizing delivery or verification."""
    selection, main, pull = (receipts[key] for key in ("selection", "main", "pull"))
    selected, repaired = selection["selected_revision"], selection["repair_head"]
    required = "b21fae85fe4f79e72c4133c29a3814b9d5950c3a"
    assert re.fullmatch(r"[0-9a-f]{40}", selected)
    assert selection["required_ancestor"] == required
    assert main["name"] == "main"
    assert main["commit"]["sha"] == selection["observed_main"] == selected
    assert pull["number"] == 4551 and pull["merged"] is True
    assert pull["merge_commit_sha"] == selected
    assert pull["head"]["sha"] == repaired
    assert pull["base"]["ref"] == "main"
    assert pull["base"]["repo"]["full_name"] == "stranske/Workflows"

    for key, ancestor in (("ancestry", required), ("repair", repaired)):
        comparison = receipts[key]
        assert urlparse(comparison["url"]).path == (
            f"/repos/stranske/Workflows/compare/{ancestor}...{selected}"
        )
        assert comparison["base_commit"]["sha"] == ancestor
        assert comparison["merge_base_commit"]["sha"] == ancestor
        assert comparison["status"] == "ahead" and comparison["behind_by"] == 0
        assert comparison["commits"][-1]["sha"] == selected

    # Native tree equality binds every salvaged fix, rather than trusting only
    # the independently authored per-file equality claims in the selection JSON.
    repair = receipts["repair"]
    tree = main["commit"]["commit"]["tree"]["sha"]
    assert re.fullmatch(r"[0-9a-f]{40}", tree)
    assert repair["base_commit"]["commit"]["tree"]["sha"] == tree
    assert repair["commits"][-1]["commit"]["tree"]["sha"] == tree
    assert repair["files"] == []
    assert_fix_inventory_binding(selection, pull, receipts["fix_inventory"])
    for key, command in (
        ("node", "node --test .github/scripts/__tests__/*.test.js"),
        ("python", "python3 -m pytest -q tests/"),
    ):
        suite = receipts[key]
        # The executor's workflow SHA is deliberately different from its checkout.
        assert suite["checkout_sha"] == selected
        assert suite["command"] == command
        assert suite["exit_code"] == 0 and suite["timed_out"] is False


def assert_fix_inventory_binding(selection: dict, pull: dict, receipt: dict) -> None:
    """Bind every salvaged fix claim to retained native tree entries."""
    blobs = {}
    for role, revision in (
        ("before", pull["base"]["sha"]),
        ("repair", selection["repair_head"]),
        ("selected", selection["selected_revision"]),
    ):
        inventory = receipt["inventories"][role]
        assert inventory["argv"] == ["git", "ls-tree", "-r", revision, "--", *FIX_PATHS]
        assert inventory["exit_code"] == 0 and inventory["stderr"] == ""
        entries = {}
        for line in inventory["stdout"].splitlines():
            match = re.fullmatch(r"100644 blob ([0-9a-f]{40})\t(.+)", line)
            assert match is not None
            blob, path = match.groups()
            assert path in FIX_PATHS and path not in entries
            entries[path] = blob
        blobs[role] = entries

    claims = selection["fix_blobs"]
    assert sorted(row["path"] for row in claims) == FIX_PATHS
    for role in ("repair", "selected"):
        assert sorted(blobs[role]) == FIX_PATHS
    for claim in claims:
        path = claim["path"]
        for role in ("before", "repair", "selected"):
            assert claim[f"{role}_blob"] == blobs[role].get(path)
        assert claim["before_blob"] != claim["repair_blob"] == claim["selected_blob"]
        assert claim["comparison_argv"] == [
            "git",
            "diff",
            "--exit-code",
            selection["repair_head"],
            selection["selected_revision"],
            "--",
            path,
        ]
        assert claim["comparison_exit_code"] == 0


def test_published_acceptance_revision_contains_required_ancestor_and_salvaged_fixes() -> None:
    assert_acceptance_revision_binding(acceptance_revision_receipts())


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("selection", "selected_revision"), "main"),
        (("selection", "required_ancestor"), "0" * 40),
        (("main", "name"), "codex/issue-4550"),
        (("main", "commit", "sha"), "0" * 40),
        (("pull", "merged"), False),
        (("pull", "number"), 4558),
        (("pull", "merge_commit_sha"), "0" * 40),
        (("pull", "head", "sha"), "0" * 40),
        (("pull", "base", "ref"), "other"),
        (("pull", "base", "repo", "full_name"), "another/Workflows"),
        (("ancestry", "merge_base_commit", "sha"), "0" * 40),
        (("ancestry", "commits", -1, "sha"), "0" * 40),
        (("repair", "behind_by"), 1),
        (("repair", "base_commit", "commit", "tree", "sha"), "0" * 40),
        (("repair", "commits", -1, "commit", "tree", "sha"), "0" * 40),
        (("repair", "files"), [{"filename": "tests/scripts/test_issue_pr_context.py"}]),
        (("node", "checkout_sha"), "0" * 40),
        (("python", "checkout_sha"), "0" * 40),
        (("python", "command"), "python3 -m pytest -q tests/ -k claude_config_dir"),
        (("node", "exit_code"), 1),
        (("python", "timed_out"), True),
    ],
    ids=lambda value: ".".join(map(str, value)) if isinstance(value, tuple) else None,
)
def test_acceptance_revision_rejects_substituted_or_partial_evidence(
    path: tuple, replacement: object
) -> None:
    receipts = acceptance_revision_receipts()
    target = receipts
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(AssertionError):
        assert_acceptance_revision_binding(receipts)


@pytest.mark.parametrize("suite", ["node", "python"])
def test_exact_revision_suite_log_matches_its_retained_receipt(suite: str) -> None:
    receipt = read(f"4557-exact-main/{suite}-full.json")
    log = (EVIDENCE / f"4557-exact-main/{suite}-full.log").read_bytes()
    assert hashlib.sha256(log).hexdigest() == receipt["log_sha256"]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("path", "tests/unrelated.py"),
        ("before_blob", "0" * 40),
        ("repair_blob", "0" * 40),
        ("selected_blob", "0" * 40),
        ("comparison_argv", ["git", "diff", "--exit-code", "main", "main"]),
        ("comparison_exit_code", 1),
    ],
)
def test_fix_inclusion_rejects_unbound_per_file_claims(field: str, replacement: object) -> None:
    receipts = acceptance_revision_receipts()
    receipts["selection"]["fix_blobs"][0][field] = replacement
    with pytest.raises(AssertionError):
        assert_acceptance_revision_binding(receipts)


@pytest.mark.parametrize("role", ["before", "repair", "selected"])
@pytest.mark.parametrize("defect", ["revision", "exit", "missing", "duplicate", "blob"])
def test_fix_inclusion_rejects_incomplete_or_substituted_native_inventory(
    role: str, defect: str
) -> None:
    receipts = acceptance_revision_receipts()
    inventory = receipts["fix_inventory"]["inventories"][role]
    lines = inventory["stdout"].splitlines(keepends=True)
    if defect == "revision":
        inventory["argv"][3] = "main"
    elif defect == "exit":
        inventory["exit_code"] = 128
    elif defect == "missing":
        inventory["stdout"] = "".join(lines[1:])
    elif defect == "duplicate":
        inventory["stdout"] += lines[0]
    else:
        inventory["stdout"] = re.sub(r"blob [0-9a-f]{40}", "blob " + "0" * 40, lines[0])
        inventory["stdout"] += "".join(lines[1:])
    with pytest.raises(AssertionError):
        assert_acceptance_revision_binding(receipts)


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
    metadata = protocol(
        read("supported-live-observation.json")["consumer_pr"]["body"],
        "workflows-consumer-sync:v1",
    )
    (result,) = [row for row in report["results"] if f'{row["owner"]}/{row["repo"]}' == CONSUMER]
    assert {key: result[key] for key in expected if key != "repository"} == {
        key: value for key, value in expected.items() if key != "repository"
    }
    assert result["plan_scope"] == metadata["plan_scope"] == "source-delta"
    assert result["scope_base_sha"] == metadata["scope_base_sha"]
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


@pytest.mark.parametrize("run_id", [FOLLOWING, RETRY])
@pytest.mark.parametrize("field", ["plan_scope", "scope_base_sha"])
def test_causal_report_rejects_a_substituted_payload_scope(run_id: int, field: str) -> None:
    report = deepcopy(read(f"maint71-{run_id}-sync-pr-merge-report.json"))
    row = next(row for row in report["results"] if row.get("repo") == CONSUMER.split("/")[1])
    # Preserve source, plan, consumer head and finding disposition. The finite
    # source-delta shipment must still reject a widened scope or another base.
    row[field] = "full" if field == "plan_scope" else "0" * 40
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


def assert_payload_binding(observation: dict, template: dict) -> None:
    frozen = expected_binding()["source_commit"]
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
        expected_path = (
            "templates/consumer-repo/tools/subscription_llm.py"
            if key == "template"
            else "tools/subscription_llm.py"
        )
        assert payload["path"] == expected_path
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


def test_final_template_bytes_reach_the_candidate_but_not_the_merged_consumer() -> None:
    observation = read("supported-live-observation.json")
    template = read("downstream-followup.json")["payloads"]["template"]
    assert_payload_binding(observation, template)
    pr = observation["consumer_pr"]
    assert pr["state"] == "open" and pr["draft"] is False
    # GitHub can supply a prospective merge_commit_sha for an open PR.
    assert pr["merged"] is False and pr["merged_at"] is None
    assert observation["final_delivery_acceptance"] is False


@pytest.mark.parametrize("role", ["source", "template", "consumer_candidate", "consumer_main"])
def test_payload_binding_rejects_an_unrelated_file_with_identical_bytes(role: str) -> None:
    observation = read("supported-live-observation.json")
    template = read("downstream-followup.json")["payloads"]["template"]
    payload = template if role == "template" else observation["payloads"][role]
    payload["path"] = "unrelated/subscription_llm.py"
    # Keep the URL internally consistent and the content/hash untouched. Blob
    # equality alone cannot bind the requested source and destination paths.
    payload["url"] = (
        f'https://github.com/{payload["repository"]}/blob/{payload["ref"]}/{payload["path"]}'
    )
    with pytest.raises(AssertionError):
        assert_payload_binding(observation, template)


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
