from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from scripts.select_consumer_sync_phase import (
    PhaseSelectionError,
    _review_debt_is_clear,
    select_phase,
    validate_registered_scopes,
)
from scripts.sync_manifest_compiler import compile_manifest

ROOT = Path(__file__).parents[2]


def test_promotion_consumes_the_shared_finding_contract_and_fails_closed(monkeypatch) -> None:
    fixture = ROOT / ".github/scripts/__tests__/fixtures/sync_finding_disposition.js"
    program = (
        "const p=require(process.argv[1]).findingPacket();"
        "console.log(JSON.stringify({repo:p.binding.repository,pr:p.binding.pr,"
        "head_sha:p.binding.head_sha,source_commit:p.binding.source_commit,"
        "plan_id:p.binding.plan_id,delivery_generation:p.binding.delivery_generation,"
        "active_review_thread_count:1,required_check_state:'success',review_disposition:p}));"
    )
    row = json.loads(
        subprocess.run(
            ["node", "-e", program, str(fixture)], capture_output=True, text=True, check=True
        ).stdout
    )
    assert _review_debt_is_clear(row)
    row["head_sha"] = "f" * 40
    assert not _review_debt_is_clear(row)
    row["head_sha"] = "a" * 40
    row["review_disposition"]["handoffs"] = []
    assert not _review_debt_is_clear(row)
    monkeypatch.setenv("PATH", "")
    assert not _review_debt_is_clear(row)


REGISTERED = [
    "stranske/Travel-Plan-Permission",
    "stranske/trip-planner",
    "stranske/Manager-Database",
    "stranske/Ready",
    "stranske/Deliverable-Render",
    "stranske/Manager-Mosaic",
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


def test_owner_excluded_repositories_never_enter_phase_matrix_or_canaries() -> None:
    excluded = "STRANSKE/cOLLAB-aDMIN"
    result = select_phase(
        plan(),
        phase="canary",
        registered_repos=[*REGISTERED, excluded],
        canaries=[*CANARIES, {"repo": excluded, "capabilities": ["manual"]}],
        selected_repos=[*(item["repo"] for item in CANARIES), excluded],
    )
    assert result["selected_repos"] == [item["repo"] for item in CANARIES]
    assert all("collab-admin" not in item.casefold() for item in result["matrix"]["repo"])


def test_preview_never_constructs_a_write_matrix() -> None:
    result = select_phase(plan(), phase="preview", registered_repos=REGISTERED, canaries=CANARIES)

    assert result["selected_repos"] == []
    assert len(result["prospective_diffs"]) == len(REGISTERED)


def test_preview_paths_respect_scoped_packaged_schema_ownership() -> None:
    repos = REGISTERED
    result = select_phase(plan(), phase="preview", registered_repos=repos, canaries=CANARIES)
    paths = {row["repo"]: set(row["affected_paths"]) for row in result["prospective_diffs"]}
    render_path = "src/deliverable_render/store/evidence-object-v1.schema.json"
    mosaic_path = "src/manager_mosaic/schemas/evidence-object-v1.schema.json"

    assert render_path in paths["stranske/Deliverable-Render"]
    assert mosaic_path not in paths["stranske/Deliverable-Render"]
    assert mosaic_path in paths["stranske/Manager-Mosaic"]
    assert render_path not in paths["stranske/Manager-Mosaic"]
    assert all(
        render_path not in paths[repo] and mosaic_path not in paths[repo]
        for repo in REGISTERED
        if repo not in {"stranske/Deliverable-Render", "stranske/Manager-Mosaic"}
    )


def test_preview_rejects_unregistered_include_repo_before_plan_publication() -> None:
    compiled = plan()
    scoped = next(entry for entry in compiled["entries"] if entry["include_repos"])
    scoped["include_repos"] = ["stranske/Manager-Mosia"]

    with pytest.raises(
        PhaseSelectionError,
        match="include_repos_contains_unregistered_repository:stranske/Manager-Mosia",
    ):
        select_phase(compiled, phase="preview", registered_repos=REGISTERED, canaries=CANARIES)


def test_full_plan_scope_validation_precedes_source_delta_filtering() -> None:
    full_plan = plan()
    scoped = next(entry for entry in full_plan["entries"] if entry["include_repos"])
    scoped["include_repos"] = ["stranske/Manager-Mosia"]
    delta_plan = {
        **full_plan,
        "entries": [entry for entry in full_plan["entries"] if entry is not scoped],
    }

    with pytest.raises(
        PhaseSelectionError,
        match="include_repos_contains_unregistered_repository:stranske/Manager-Mosia",
    ):
        validate_registered_scopes(full_plan, REGISTERED)
    validate_registered_scopes(delta_plan, REGISTERED)

    workflow = (ROOT / ".github/workflows/maint-68-sync-consumer-repos.yml").read_text(
        encoding="utf-8"
    )
    assert workflow.index("- name: Validate full plan repository scopes") < workflow.index(
        "- name: Select full or exact source-delta plan"
    )


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


@pytest.mark.parametrize(
    "packet",
    [
        None,
        {},
        {"evidenceComplete": False, "reviewThreads": []},
        {
            "evidenceComplete": True,
            "reviewThreads": [{"isResolved": False, "isOutdated": False}],
        },
    ],
)
def test_promotion_rejects_zero_count_with_attached_invalid_finding_evidence(packet) -> None:
    compiled = plan()
    evidence = green_evidence(compiled["plan_id"])
    evidence[0]["review_disposition"] = packet

    with pytest.raises(PhaseSelectionError, match="active_review_debt"):
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

    assert result["selected_repos"] == [
        "stranske/Manager-Database",
        "stranske/Ready",
        "stranske/Deliverable-Render",
        "stranske/Manager-Mosaic",
    ]


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


@pytest.mark.parametrize("phase", ["preview", "canary", "promote"])
def test_owner_exclusion_applies_to_implicit_registered_targets(phase):
    compiled = plan()
    result = select_phase(
        compiled,
        phase=phase,
        registered_repos=[*REGISTERED, "STRANSKE/cOLLAB-aDMIN"],
        canaries=CANARIES,
        evidence=green_evidence(compiled["plan_id"]),
    )
    assert all("collab-admin" not in repo.casefold() for repo in result["selected_repos"])
    assert all("collab-admin" not in row["repo"].casefold() for row in result["prospective_diffs"])
