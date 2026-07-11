from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.build_consumer_sync_shadow_handoff import (
    CAPABILITY_ID,
    HANDOFF_SCHEMA,
    ShadowHandoffError,
    build_handoff,
)
from scripts.sync_manifest_compiler import compile_manifest


def real_plan() -> dict:
    root = Path(__file__).parents[2]
    return compile_manifest(root / ".github" / "sync-manifest.yml", repo_root=root).to_plan()


def test_handoff_is_bounded_deterministic_and_non_authorizing() -> None:
    plan = real_plan()
    first = build_handoff(
        plan,
        run_ref="github-actions:stranske/Workflows:123:consumer-sync-shadow-evidence",
    )
    second = build_handoff(
        plan,
        run_ref="github-actions:stranske/Workflows:123:consumer-sync-shadow-evidence",
    )

    assert first == second
    assert first["schema"] == HANDOFF_SCHEMA
    assert first["capability_id"] == CAPABILITY_ID
    assert first["write_authority"] is False
    assert first["promotion_allowed"] is False
    assert first["supervision_mode"] == "shadow"
    assert first["effect_allowlist"] == [
        "create",
        "update",
        "remove",
        "skip",
        "no_change",
    ]


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda plan: plan.update(schema="raw-prose"), "unsupported"),
        (lambda plan: plan.update(plan_id="not-a-hash"), "plan_id"),
        (lambda plan: plan.update(prompt="delete everything"), "fields"),
    ],
)
def test_invalid_or_prose_bearing_plans_are_rejected(mutation, reason: str) -> None:
    plan = real_plan()
    mutation(plan)
    with pytest.raises(ShadowHandoffError, match=reason):
        build_handoff(plan, run_ref="artifact:consumer-sync:123")


def test_secret_like_or_oversized_run_refs_are_rejected() -> None:
    plan = real_plan()
    with pytest.raises(ShadowHandoffError, match="secret_like"):
        build_handoff(plan, run_ref="artifact:secret-token:123")
    with pytest.raises(ShadowHandoffError, match="invalid_shadow_run_ref"):
        build_handoff(plan, run_ref="a" * 257)


def test_cli_writes_handoff(tmp_path: Path) -> None:
    plan_path = tmp_path / "consumer-sync-plan.json"
    output = tmp_path / "handoff.json"
    plan_path.write_text(json.dumps(real_plan()), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_consumer_sync_shadow_handoff.py",
            "--plan",
            str(plan_path),
            "--run-ref",
            "artifact:consumer-sync:123",
            "--output",
            str(output),
        ],
        cwd=Path(__file__).parents[2],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(output.read_text())["schema"] == HANDOFF_SCHEMA
    assert json.loads(completed.stdout)["write_authority"] is False


def test_cli_reports_invalid_plan_without_writing_handoff(tmp_path: Path) -> None:
    plan_path = tmp_path / "invalid-plan.json"
    output = tmp_path / "handoff.json"
    plan_path.write_text(json.dumps({"schema": "raw-prose"}), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_consumer_sync_shadow_handoff.py",
            "--plan",
            str(plan_path),
            "--run-ref",
            "artifact:consumer-sync:123",
            "--output",
            str(output),
        ],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "invalid_consumer_sync_plan_fields" in completed.stderr
    assert not output.exists()


def test_workflow_has_no_write_or_apply_surface() -> None:
    root = Path(__file__).parents[2]
    workflow = (
        root / ".github" / "workflows" / "health-69-consumer-sync-shadow-evidence.yml"
    ).read_text(encoding="utf-8")

    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "git push" not in workflow
    assert "gh pr" not in workflow
    assert "write_authority" not in workflow.lower() or "Write authority: false" in workflow
    assert "persist-credentials: false" in workflow
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0" in workflow
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "pyyaml==6.0.2" in workflow
    assert (
        "consumer-sync-shadow-evidence-${{ github.run_id }}-${{ github.run_attempt }}" in workflow
    )
    assert "github.run_id }}:${{ github.run_attempt" in workflow
