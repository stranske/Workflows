"""FULL consumer regeneration stays tied to one plan, its heads, and merged #3900."""

from __future__ import annotations

import copy
import os
import subprocess
from pathlib import Path

import pytest
from scripts.consumer_regeneration_linkage import (
    FULL_CONSUMER_REGENERATION_3900,
    regeneration_gaps,
)

REPO = Path(__file__).resolve().parents[2]
SOURCE = "306fc9e79d891030395211fdae8ae1387f2b37c3"
DEPENDENCY = "8ec052a1fdc32319165011a7e465d6710c7ef4b5"
PLAN = "sha256:1a22f551228736c4279b2b5434baffbb0e6d5b697dc43727bf5d7f808209dc0b"


def _record() -> dict:
    return copy.deepcopy(FULL_CONSUMER_REGENERATION_3900)


def test_full_regeneration_links_qualification_promotion_and_reconciliation() -> None:
    record = FULL_CONSUMER_REGENERATION_3900
    assert regeneration_gaps(record) == ()
    assert record["plan_id"] == PLAN
    assert record["plan_scope"] == "full"
    assert record["source_commit"] == SOURCE
    assert record["dependency"]["pull_request"] == 3900
    assert record["dependency"]["merge_commit"] == DEPENDENCY
    assert record["qualification"]["canaries_green"] == 3
    assert record["promotion"]["phase"] == "promote"
    assert record["promotion"]["reconciliation_run_id"] == 41128913051
    assert record["reconciliation"]["authorized"] is True
    assert record["reconciliation"]["merged"] == 16
    assert record["reconciliation"]["failed"] == 0
    assert record["reconciliation"]["pending"] == 0
    assert record["reconciliation"]["delivery_refresh"]["eligible"] is False
    assert record["reconciliation"]["delivery_refresh"]["errors"] == (
        "delivery report has no stable base refresh request",
    )
    assert "306fc9e79d891030395211fdae8ae1387f2b37c3" in record["qualification"]["notice"]
    assert "canaries green 3/3" in record["qualification"]["notice"]
    assert (
        record["reconciliation"]["continuation_run_ids"][-1] == record["reconciliation"]["run_id"]
    )
    qualified = {
        (head["repository"], head["pr"], head["head_sha"])
        for head in record["qualification"]["heads"]
    }
    delivered = {
        (head["repository"], head["pr"], head["head_sha"])
        for head in record["reconciliation"]["heads"]
    }
    assert qualified <= delivered
    assert len(delivered) == 16


def _commit_present(sha: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    return completed.returncode == 0


def test_source_commit_contains_merged_3900() -> None:
    # Required Python CI fetches the fixed historical source before pytest.
    # Ad hoc shallow checkouts may skip; required validation must fail closed.
    if not _commit_present(DEPENDENCY) or not _commit_present(SOURCE):
        if os.environ.get("WORKFLOWS_REQUIRE_3900_ANCESTRY") == "1":
            pytest.fail("required dependency and source history is absent")
        pytest.skip("dependency and source commits are absent from this checkout")
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", DEPENDENCY, SOURCE],
        cwd=REPO,
        check=False,
    )
    assert completed.returncode == 0


def test_commands_name_the_plan_source_dependency_and_runs() -> None:
    record = _record()
    rendered = "\n".join(record["commands"])
    assert record["plan_id"] == PLAN
    assert SOURCE in rendered
    assert DEPENDENCY in rendered
    for run_id in (41128486728, 41128622575, 41132061438):
        assert str(run_id) in rendered


def test_required_ancestry_cannot_skip_missing_history(monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOWS_REQUIRE_3900_ANCESTRY", "1")
    monkeypatch.setattr(f"{__name__}._commit_present", lambda _sha: False)
    with pytest.raises(pytest.fail.Exception, match="required dependency and source history"):
        test_source_commit_contains_merged_3900()


def test_missing_stage_is_unlinked() -> None:
    for stage in ("qualification", "promotion", "reconciliation"):
        record = _record()
        del record[stage]
        assert stage in regeneration_gaps(record)


def test_non_mapping_stage_is_unlinked() -> None:
    for stage in ("qualification", "promotion", "reconciliation"):
        record = _record()
        record[stage] = "success"
        assert stage in regeneration_gaps(record)


def test_boolean_and_float_zero_are_not_terminal_counts() -> None:
    for field, value in (
        ("failed", False),
        ("pending", False),
        ("failed", 0.0),
        ("pending", 0.0),
    ):
        record = _record()
        record["reconciliation"][field] = value
        assert "reconciliation.verdict" in regeneration_gaps(record)


def test_integer_eligibility_with_another_refresh_error_is_not_terminal() -> None:
    record = _record()
    record["reconciliation"]["delivery_refresh"] = {
        "eligible": 0,
        "errors": ("writer exited before authorization",),
    }
    assert "reconciliation.delivery_refresh" in regeneration_gaps(record)


def test_failed_reconciliation_is_unlinked() -> None:
    record = _record()
    record["reconciliation"]["failed"] = 1
    assert "reconciliation.verdict" in regeneration_gaps(record)


def test_qualified_head_must_survive_reconciliation() -> None:
    record = _record()
    record["qualification"]["heads"][0]["head_sha"] = "a" * 40
    assert "reconciliation.qualified_heads" in regeneration_gaps(record)


def test_source_delta_scope_is_not_a_full_regeneration() -> None:
    record = _record()
    record["plan_scope"] = "source-delta"
    assert "plan_scope" in regeneration_gaps(record)


def test_false_canary_hold_is_not_terminal_reconciliation() -> None:
    record = _record()
    record["reconciliation"]["delivery_refresh"]["errors"] = (
        "delivery report has no stable base refresh request",
        "missing_canary_evidence:stranske/Travel-Plan-Permission",
        "missing_or_mixed_canary_plan",
    )
    assert "reconciliation.delivery_refresh" in regeneration_gaps(record)


def test_dependency_merge_cannot_be_the_plan_source() -> None:
    record = _record()
    record["dependency"]["merge_commit"] = SOURCE
    assert "dependency" in regeneration_gaps(record)
