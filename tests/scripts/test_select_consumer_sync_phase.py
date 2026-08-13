from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.select_consumer_sync_phase import PhaseSelectionError, select_phase
from scripts.sync_manifest_compiler import compile_manifest

ROOT = Path(__file__).parents[2]
REGISTERED = [
    "stranske/Travel-Plan-Permission",
    "stranske/trip-planner",
    "stranske/Manager-Database",
    "stranske/Ready",
]
CANARIES = [
    {"repo": "stranske/Travel-Plan-Permission", "capabilities": ["custom-gate"]},
    {"repo": "stranske/trip-planner", "capabilities": ["lock-heavy"]},
]


def plan() -> dict:
    return compile_manifest(ROOT / ".github" / "sync-manifest.yml", repo_root=ROOT).to_plan()


def green_evidence(plan_id: str) -> list[dict]:
    return [
        {
            "repo": canary["repo"],
            "plan_id": plan_id,
            "pr": 100 + index,
            "required_check_state": "success",
            "active_review_thread_count": 0,
        }
        for index, canary in enumerate(CANARIES)
    ]


def test_canary_phase_selects_only_representative_repos() -> None:
    result = select_phase(plan(), phase="canary", registered_repos=REGISTERED, canaries=CANARIES)

    assert result["selected_repos"] == [item["repo"] for item in CANARIES]
    assert len(result["prospective_diffs"]) == len(REGISTERED)
    assert result["matrix"] == {"repo": result["selected_repos"]}
    assert all(item["desired_hash"] == result["plan_id"] for item in result["prospective_diffs"])


def test_preview_never_constructs_a_write_matrix() -> None:
    result = select_phase(plan(), phase="preview", registered_repos=REGISTERED, canaries=CANARIES)

    assert result["selected_repos"] == []
    assert len(result["prospective_diffs"]) == len(REGISTERED)


def test_promotion_rejects_stale_canary_evidence() -> None:
    compiled = plan()
    stale = green_evidence("sha256:" + "0" * 64)

    with pytest.raises(PhaseSelectionError, match="stale_or_mixed_plan"):
        select_phase(
            compiled,
            phase="promote",
            registered_repos=REGISTERED,
            canaries=CANARIES,
            evidence=stale,
        )


def test_promotion_requires_green_review_clear_evidence_for_each_canary() -> None:
    compiled = plan()
    evidence = green_evidence(compiled["plan_id"])
    evidence[0]["required_check_state"] = "failure"
    evidence[1]["active_review_thread_count"] = 1

    with pytest.raises(PhaseSelectionError, match="required_checks_not_green"):
        select_phase(
            compiled,
            phase="promote",
            registered_repos=REGISTERED,
            canaries=CANARIES,
            evidence=evidence,
        )


def test_promotion_rejects_missing_or_duplicate_canary_evidence() -> None:
    compiled = plan()
    evidence = green_evidence(compiled["plan_id"])

    with pytest.raises(PhaseSelectionError, match="missing_canary_evidence"):
        select_phase(
            compiled,
            phase="promote",
            registered_repos=REGISTERED,
            canaries=CANARIES,
            evidence=evidence[:-1],
        )

    with pytest.raises(PhaseSelectionError, match="duplicate_canary_evidence"):
        select_phase(
            compiled,
            phase="promote",
            registered_repos=REGISTERED,
            canaries=CANARIES,
            evidence=[*evidence, evidence[0]],
        )


def test_promotion_targets_only_non_canary_repos() -> None:
    compiled = plan()
    result = select_phase(
        compiled,
        phase="promote",
        registered_repos=REGISTERED,
        canaries=CANARIES,
        evidence=green_evidence(compiled["plan_id"]),
    )

    assert result["selected_repos"] == ["stranske/Manager-Database", "stranske/Ready"]


def test_filtered_manual_canary_run_can_narrow_the_configured_canaries() -> None:
    result = select_phase(
        plan(),
        phase="canary",
        registered_repos=REGISTERED,
        selected_repos=["stranske/Travel-Plan-Permission"],
        canaries=CANARIES,
    )

    assert result["selected_repos"] == ["stranske/Travel-Plan-Permission"]


def test_filtered_manual_canary_run_cannot_expand_into_the_fleet() -> None:
    with pytest.raises(PhaseSelectionError, match="canary_selection_contains_non_canary"):
        select_phase(
            plan(),
            phase="canary",
            registered_repos=REGISTERED,
            selected_repos=["stranske/Travel-Plan-Permission", "stranske/Ready"],
            canaries=CANARIES,
        )


def test_manual_selection_cannot_target_an_unregistered_repository() -> None:
    # A manual filtered run must not become a fan-out escape hatch: one unregistered
    # entry alongside valid ones has to reject the whole selection, not silently drop it.
    with pytest.raises(PhaseSelectionError, match="selected_repos_must_be_registered"):
        select_phase(
            plan(),
            phase="canary",
            registered_repos=REGISTERED,
            selected_repos=["stranske/Ready", "stranske/Not-A-Consumer"],
            canaries=CANARIES,
        )


def test_checked_in_canary_config_covers_distinct_consumer_shapes() -> None:
    config = json.loads((ROOT / "config" / "consumer_sync_canaries.json").read_text())
    covered = {tag for canary in config["canaries"] for tag in canary["capabilities"]}

    assert {
        "standard",
        "custom-gate",
        "lock-heavy",
        "python-consumer",
        "codex-review",
        "legacy-precommit",
    } <= covered
    assert any(
        "codex-review" in canary["capabilities"] for canary in config["canaries"]
    ), "At least one canary must exercise the fleet's Codex review profile before promotion"
