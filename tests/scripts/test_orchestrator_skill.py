"""Tests for scripts/orchestrator_skill.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.orchestrator_skill import (
    OrchestratorSkillConfigError,
    build_orchestrator_skill_summary,
    load_orchestrator_skill,
    main,
    parse_orchestrator_skill_config,
    resolve_orchestrator_skill_plan,
)


def test_no_config_means_orchestrator_skill_disabled(tmp_path: Path) -> None:
    snapshot = load_orchestrator_skill(tmp_path)

    assert snapshot.exists is False
    assert snapshot.enabled is False
    assert snapshot.plan is None


def test_disabled_config_means_no_plan(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "orchestrator_skill.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(json.dumps({"enabled": False}), encoding="utf-8")

    snapshot = load_orchestrator_skill(tmp_path)

    assert snapshot.exists is True
    assert snapshot.enabled is False
    assert snapshot.plan is None


def test_inline_config_parses_exported_repo_paths(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "orchestrator_skill.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        json.dumps(
            {
                "enabled": True,
                "repo": "stranske/Workflows",
                "ref": "main",
                "paths": ["docs/exports/orchestrator-skill/SKILL.md"],
            }
        ),
        encoding="utf-8",
    )

    plan = resolve_orchestrator_skill_plan(tmp_path)

    assert plan is not None
    assert plan.repo == "stranske/Workflows"
    assert plan.ref == "main"
    assert plan.paths == ["docs/exports/orchestrator-skill/SKILL.md"]
    assert plan.checkout_path == ".reference/orchestrator-skill"


def test_pack_config_references_reference_pack_name(tmp_path: Path) -> None:
    config_file = tmp_path / ".github" / "orchestrator_skill.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(json.dumps({"enabled": True, "pack": "orchestrator"}), encoding="utf-8")

    plan = resolve_orchestrator_skill_plan(tmp_path)

    assert plan is not None
    assert plan.pack == "orchestrator"


def test_parse_rejects_local_runtime_paths() -> None:
    with pytest.raises(OrchestratorSkillConfigError, match="local Orchestrator runtime paths"):
        parse_orchestrator_skill_config(
            {
                "enabled": True,
                "repo": "owner/repo",
                "ref": "main",
                "paths": ["/Users/teacher/.codex/skills/orchestrator/SKILL.md"],
            }
        )


def test_parse_rejects_nested_repo_names() -> None:
    with pytest.raises(OrchestratorSkillConfigError, match="repo must use owner/name format"):
        parse_orchestrator_skill_config(
            {
                "enabled": True,
                "repo": "owner/repo/extra",
                "ref": "main",
                "paths": ["docs/exports/orchestrator-skill/SKILL.md"],
            }
        )


def test_enabled_override_can_enable_pack_without_repo_config(tmp_path: Path) -> None:
    plan = resolve_orchestrator_skill_plan(
        tmp_path,
        pack_override="orchestrator",
        enabled_override=True,
    )

    assert plan is not None
    assert plan.pack == "orchestrator"


def test_pack_override_enables_pack_without_repo_config(tmp_path: Path) -> None:
    plan = resolve_orchestrator_skill_plan(
        tmp_path,
        pack_override="orchestrator",
    )

    assert plan is not None
    assert plan.pack == "orchestrator"


def test_enabled_override_can_disable_pack_override_without_repo_config(tmp_path: Path) -> None:
    plan = resolve_orchestrator_skill_plan(
        tmp_path,
        pack_override="orchestrator",
        enabled_override=False,
    )

    assert plan is None


def test_summary_instructs_agent_to_read_exported_material(tmp_path: Path) -> None:
    checkout = tmp_path / ".reference" / "orchestrator-skill"
    checkout.mkdir(parents=True)
    skill = checkout / "SKILL.md"
    skill.write_text("# Exported skill\n", encoding="utf-8")

    summary = build_orchestrator_skill_summary(checkout, pack_name="orchestrator")

    assert "exported Orchestrator instructions" in summary
    assert "not** a live mount" in summary
    assert "Read and apply the materialized Orchestrator skill files" in summary
    assert "`SKILL.md`" in summary


@pytest.mark.parametrize("enabled", ["yes", "on", "1", True])
def test_enabled_values_enable_pack(enabled: object) -> None:
    is_enabled, plan = parse_orchestrator_skill_config({"enabled": enabled, "pack": "safe-pack"})

    assert is_enabled is True
    assert plan is not None and plan.pack == "safe-pack"


@pytest.mark.parametrize("value", ["maybe", 1, [], object()])
def test_invalid_enabled_values_are_rejected(value: object) -> None:
    with pytest.raises(OrchestratorSkillConfigError, match="enabled must be a boolean"):
        parse_orchestrator_skill_config({"enabled": value, "pack": "safe-pack"})


@pytest.mark.parametrize(
    "paths, message",
    [
        ([], "non-empty array"),
        (["../secret.md"], "traverse parent"),
        (["/absolute.md"], "relative"),
        (["docs/ORCHESTRATOR/brain.md"], "local Orchestrator runtime"),
    ],
)
def test_inline_paths_are_strictly_bounded(paths: list[str], message: str) -> None:
    with pytest.raises(OrchestratorSkillConfigError, match=message):
        parse_orchestrator_skill_config(
            {"enabled": True, "repo": "owner/repo", "ref": "main", "paths": paths}
        )


def test_config_rejects_mixed_sources_and_malformed_json(tmp_path: Path) -> None:
    with pytest.raises(OrchestratorSkillConfigError, match="either 'pack' or inline"):
        parse_orchestrator_skill_config(
            {"pack": "safe", "repo": "owner/repo", "ref": "main", "paths": ["README.md"]}
        )
    config = tmp_path / ".github" / "orchestrator_skill.json"
    config.parent.mkdir()
    config.write_text("{bad", encoding="utf-8")
    with pytest.raises(OrchestratorSkillConfigError, match="Malformed JSON"):
        load_orchestrator_skill(tmp_path)


def test_cli_self_check_and_json_report_config_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--workspace", str(tmp_path), "--format", "self-check"]) == 0
    assert "skipped" in capsys.readouterr().err

    config = tmp_path / ".github" / "orchestrator_skill.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"enabled": False}), encoding="utf-8")
    assert main(["--workspace", str(tmp_path), "--format", "self-check"]) == 0
    assert "disabled" in capsys.readouterr().err
    assert main(["--workspace", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["enabled"] is False
