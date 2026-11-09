"""Replay issue 4581's terminal delivery evidence without network or workflow dispatch."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4369/runtime-4550/4557r2"


def read_receipt(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def chain() -> dict:
    return read_receipt("chain-receipt.json")


def test_model_table_blocker_resolution_has_a_passing_test_at_the_merged_revision(
    chain: dict,
) -> None:
    resolution = chain["blocker_resolution"]
    refresh = read_receipt("orchestrator-model-table-refresh.json")
    pr = read_receipt(resolution["checks_receipt"])
    test = read_receipt(resolution["test_receipt"])
    assert refresh["sha"] == resolution["model_table_refresh_commit"]
    assert "src/model_table.py" in {file["filename"] for file in refresh["files"]}
    assert pr["state"] == "MERGED" and pr["isDraft"] is False
    assert pr["mergeCommit"]["oid"] == resolution["orchestrator_merge_sha"]
    checks = pr["statusCheckRollup"]
    assert checks
    for check in checks:
        if check["__typename"] == "StatusContext":
            assert check["state"] == "SUCCESS"
        else:
            assert check["__typename"] == "CheckRun"
            assert check["status"] == "COMPLETED"
            assert check["conclusion"] in {"SUCCESS", "SKIPPED", "NEUTRAL"}
    assert any(
        check.get("workflowName") == "Gate"
        and check["name"] == "summary"
        and check["conclusion"] == "SUCCESS"
        for check in checks
    )
    assert test["source_repository"] == "stranske/Orchestrator"
    assert test["source_revision"] == pr["mergeCommit"]["oid"]
    assert test["command"].endswith(
        " -m pytest -q tests/test_model_table.py::test_copy_matches_workflows_source"
    )
    assert test["exit_code"] == 0 and test["skipped"] == 0
    assert test["result"].startswith("1 passed in ")
    assert test["result"] in (EVIDENCE / test["log"]).read_text(encoding="utf-8")


def test_terminal_merge_report_preserves_the_producer_plan_and_candidate(chain: dict) -> None:
    producer, plan, candidate = (chain[key] for key in ("producer", "plan", "candidate"))
    assert producer["event"] == "schedule" and producer["conclusion"] == "success"
    assert producer["head_sha"] == plan["source_commit"]
    for name in plan["bound_in"]:
        artifact = read_receipt(name)
        assert artifact["plan_id"] == plan["plan_id"]
    produced = read_receipt(plan["bound_in"][-1])
    assert produced["source_commit"] == plan["source_commit"]
    assert produced["repo"] == candidate["repository"]
    assert produced["pr"] == candidate["pr"]
    assert produced["status"] == "created_pr"
    assert produced["dry_run"] is False

    terminal = chain["terminal_merger"]
    run = read_receipt(terminal["run_receipt"])
    report = read_receipt(terminal["report"])
    authorization = read_receipt(terminal["authorization"])
    assert run["databaseId"] == report["run"]["run_id"] == terminal["run_id"]
    assert run["conclusion"] == "success"
    assert report["inputs"]["dry_run"] is False
    assert authorization["authorized"] is True and authorization["errors"] == []
    assert authorization["plan_id"] == plan["plan_id"]
    assert authorization["source_commit"] == plan["source_commit"]
    # Branch deletion is also reported for this PR. Only the merged row proves delivery.
    (merged,) = [
        row
        for row in report["results"]
        if f'{row["owner"]}/{row["repo"]}' == candidate["repository"]
        and row["pr"] == candidate["pr"]
        and row["status"] == "merged"
    ]
    handoff = terminal["handoff"]
    for key, expected in {
        "head_sha": candidate["head_sha"],
        "branch": candidate["branch"],
        "plan_id": plan["plan_id"],
        "source_commit": plan["source_commit"],
        "delivery_generation": plan["template_hash"],
    }.items():
        assert merged[key] == handoff[key] == expected
    assert handoff["disposition"] == "merged"
    merge = chain["consumer_merge"]
    pr = read_receipt(merge["pr_receipt"])
    commit = read_receipt(merge["commit_receipt"])
    assert merge["terminal_receipt"] is True
    assert merge["maint71_run_id"] == terminal["run_id"]
    assert merge["pr_state"] == pr["state"] == "MERGED"
    assert merge["isDraft"] is pr["isDraft"] is False
    assert merge["mergeCommit"] == pr["mergeCommit"]
    assert merge["mergeCommit"]["oid"] == commit["sha"]
    assert merge["mergedAt"] == pr["mergedAt"]
    assert merge["head_sha"] == pr["headRefOid"] == candidate["head_sha"]
    assert datetime.fromisoformat(run["createdAt"]) <= datetime.fromisoformat(pr["mergedAt"])
    assert datetime.fromisoformat(pr["mergedAt"]) <= datetime.fromisoformat(run["updatedAt"])
    main = read_receipt(merge["main_reachability_receipt"])
    assert main["base_commit"] == main["merge_base_commit"] == commit["sha"]
    assert main["status"] in {"identical", "ahead"}


def test_candidate_and_merged_payloads_match_the_source_and_merge_revision_blob(
    chain: dict,
) -> None:
    source = (EVIDENCE.parent / "4557-source-subscription_llm.py.txt").read_bytes()
    equality = chain["payload_equality"]
    candidate = (EVIDENCE / "candidate-795155aa-subscription_llm.py.txt").read_bytes()
    merged = (EVIDENCE / equality["eventual_merged_payload"]).read_bytes()
    blob = read_receipt("consumer-merge-subscription-blob.json")
    assert source == candidate == merged == base64.b64decode(blob["content"])
    assert blob["path"] == "tools/subscription_llm.py"
    assert blob["size"] == len(merged)
    assert parse_qs(urlparse(blob["url"]).query) == {
        "ref": [chain["consumer_merge"]["mergeCommit"]["oid"]]
    }
    git_object = f"blob {len(merged)}\0".encode() + merged
    assert hashlib.sha1(git_object).hexdigest() == blob["sha"]
    assert blob["sha"] == equality["candidate_blob"] == equality["consumer_merge_blob"]
    manifest = read_receipt(chain["plan"]["bound_in"][1])
    (entry,) = [entry for entry in manifest["entries"] if entry["target"] == blob["path"]]
    assert entry["content_sha256"] == "sha256:" + hashlib.sha256(source).hexdigest()


def test_terminal_evidence_still_matches_the_retained_provenance_hashes() -> None:
    provenance = read_receipt("4581-artifact-provenance.json")
    assert provenance["files"]
    assert "chain-receipt.json" in provenance["files"]
    for name, digest in provenance["files"].items():
        assert hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest() == digest, name
