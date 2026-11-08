"""Replay the published-main proof independently of partial full-suite results."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[2] / "docs/evidence/issue-4369/runtime-4550"
ANCESTOR = "b21fae85fe4f79e72c4133c29a3814b9d5950c3a"
REVISION = "0a06f1976db1dd7eb12853f493a3371ee4736bcf"
REPAIR_HEAD = "154858c48424d7aa30c9edaf22ee3edb90066c5d"
FIX_PATHS = {
    ".github/scripts/__tests__/keepalive-loop.test.js",
    ".github/scripts/__tests__/maint71-delivery-receipts.test.js",
    ".github/scripts/__tests__/verifier-correction-artifacts.test.js",
    ".github/scripts/__tests__/verifier-correction-coding.test.js",
    ".github/scripts/maint71_merge_sync_prs.js",
    "tests/scripts/test_issue_4369_delivery_lifecycle.py",
    "tests/scripts/test_issue_4369_downstream_evidence.py",
    "tests/scripts/test_issue_pr_context.py",
    "tests/scripts/test_llm_client_shared.py",
}


def read(name: str) -> dict:
    return json.loads((EVIDENCE / f"4558-{name}.json").read_text(encoding="utf-8"))


def assert_revision_binding(main: dict, pr: dict, ancestor: dict, repair: dict) -> None:
    """This selection uses the actual merge with an unchanged repair tree."""
    assert main["name"] == pr["base"]["ref"] == "main"
    assert main["commit"]["sha"] == pr["merge_commit_sha"] == REVISION
    assert pr["number"] == 4551
    assert pr["base"]["repo"]["full_name"] == "stranske/Workflows"
    assert pr["merged"] is True and pr["draft"] is False
    assert pr["merged_at"]
    assert pr["head"]["sha"] == REPAIR_HEAD
    assert {parent["sha"] for parent in main["commit"]["parents"]} == {
        pr["base"]["sha"],
        REPAIR_HEAD,
    }
    for comparison, base in ((ancestor, ANCESTOR), (repair, REPAIR_HEAD)):
        assert comparison["base_commit"]["sha"] == base
        assert comparison["merge_base_commit"]["sha"] == base
        assert comparison["status"] == "ahead"
        assert comparison["behind_by"] == 0
        assert comparison["commits"][-1]["sha"] == REVISION
    # An ancestor alone would accept a merge that reverted a fixture repair.
    # The identical Git tree proves every salvaged file survived unchanged.
    tree = repair["base_commit"]["commit"]["tree"]["sha"]
    assert main["commit"]["commit"]["tree"]["sha"] == tree
    assert repair["commits"][-1]["commit"]["tree"]["sha"] == tree
    assert repair["files"] == []


def test_selected_main_contains_required_ancestor_and_all_salvaged_fixes() -> None:
    assert_revision_binding(
        read("main-observation"),
        read("fixture-pr"),
        read("ancestor-compare"),
        read("repair-compare"),
    )


@pytest.mark.parametrize(
    ("receipt", "path", "replacement"),
    [
        ("main-observation", ("commit", "sha"), "f" * 40),
        ("fixture-pr", ("merged",), False),
        ("fixture-pr", ("draft",), True),
        ("fixture-pr", ("merge_commit_sha",), "f" * 40),
        ("fixture-pr", ("head", "sha"), "f" * 40),
        ("ancestor-compare", ("merge_base_commit", "sha"), "f" * 40),
        ("ancestor-compare", ("status",), "diverged"),
        ("ancestor-compare", ("behind_by",), 1),
        ("repair-compare", ("merge_base_commit", "sha"), "f" * 40),
        ("repair-compare", ("base_commit", "commit", "tree", "sha"), "f" * 40),
        ("repair-compare", ("files",), [{"filename": "tests/scripts/test_llm_client_shared.py"}]),
    ],
)
def test_rejects_unpublished_unmerged_or_altered_repair_proofs(
    receipt: str, path: tuple[str, ...], replacement: object
) -> None:
    names = ("main-observation", "fixture-pr", "ancestor-compare", "repair-compare")
    receipts = {name: deepcopy(read(name)) for name in names}
    target = receipts[receipt]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(AssertionError):
        assert_revision_binding(*(receipts[name] for name in names))


def test_each_changed_source_file_has_an_exact_merge_blob_receipt() -> None:
    receipt = read("revision-selection")
    assert receipt["selected_revision"] == REVISION
    assert receipt["repair_head"] == REPAIR_HEAD
    assert receipt["required_ancestor"] == ANCESTOR
    assert {row["path"] for row in receipt["fix_blobs"]} == FIX_PATHS
    for row in receipt["fix_blobs"]:
        assert re.fullmatch(r"[0-9a-f]{40}", row["repair_blob"])
        assert row["selected_blob"] == row["repair_blob"]
        assert row["before_blob"] != row["repair_blob"]
        assert row["comparison_exit_code"] == 0
    assert receipt["ancestry_checks"]
    assert all(row["exit_code"] == 0 for row in receipt["ancestry_checks"])
    # Revision selection is necessary, but must not imply suite acceptance.
    assert receipt["full_suite_acceptance"] is False
