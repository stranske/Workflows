from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
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
    workflow_path = root / ".github" / "workflows" / "health-69-consumer-sync-shadow-evidence.yml"
    workflow_source = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_source)
    steps = workflow["jobs"]["produce"]["steps"]
    action_refs = [
        str(step["uses"])
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("uses"), str)
    ]
    third_party_action_refs = [ref for ref in action_refs if not ref.startswith("./")]
    setup_python_refs = [ref for ref in action_refs if ref.startswith("actions/setup-python@")]
    events = workflow.get("on", workflow.get(True))

    assert workflow["permissions"] == {"contents": "read"}
    assert "contents: write" not in workflow_source
    assert "pull-requests: write" not in workflow_source
    assert "git push" not in workflow_source
    assert "gh pr" not in workflow_source
    assert (
        "write_authority" not in workflow_source.lower()
        or "Write authority: false" in workflow_source
    )
    assert steps[0]["with"]["persist-credentials"] is False
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in action_refs
    assert len(setup_python_refs) == 1
    assert re.fullmatch(r"actions/setup-python@[0-9a-f]{40}", setup_python_refs[0])
    assert len(third_party_action_refs) == 3
    for action_ref in third_party_action_refs:
        assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action_ref)
        assert re.search(
            rf"^\s*uses:\s*{re.escape(action_ref)}\s+# v\d+(?:[.\w-]+)?\s*$",
            workflow_source,
            re.MULTILINE,
        )
    assert "pull_request" in events
    assert workflow_path.relative_to(root).as_posix() in events["pull_request"]["paths"]
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in action_refs
    assert "pyyaml==6.0.2" in workflow_source
    assert (
        "consumer-sync-shadow-evidence-${{ github.run_id }}-${{ github.run_attempt }}"
        in workflow_source
    )
    assert "github.run_id }}:${{ github.run_attempt" in workflow_source
