from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from scripts import validate_template_completeness as validator


def test_get_workflows_returns_top_level_yml_files_only(tmp_path: Path) -> None:
    (tmp_path / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "agents-80-pr-event-hub.yml").write_text("name: Agents\n", encoding="utf-8")
    (tmp_path / "workflow.yaml").write_text("name: YAML suffix\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "nested.yml").write_text("name: Nested\n", encoding="utf-8")

    assert validator.get_workflows(tmp_path) == {
        "agents-80-pr-event-hub.yml",
        "ci.yml",
    }
    assert validator.get_workflows(tmp_path / "missing") == set()


def test_get_manifest_workflows_extracts_only_workflow_sources(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sync-manifest.yml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "workflows": [
                    {"source": ".github/workflows/ci.yml"},
                    {"source": ".github/workflows/agents-80-pr-event-hub.yml"},
                    {"source": "templates/consumer-repo/AGENTS.md"},
                    {"source": ".github/scripts/error_classifier.js"},
                    {"target": ".github/workflows/missing-source.yml"},
                ],
                "docs": [{"source": "docs/LABELS.md"}],
            }
        ),
        encoding="utf-8",
    )

    assert validator.get_manifest_workflows(manifest_path) == {
        "agents-80-pr-event-hub.yml",
        "ci.yml",
    }
    assert validator.get_manifest_workflows(tmp_path / "missing.yml") == set()


@pytest.mark.parametrize(
    ("workflow_name", "expected"),
    [
        ("agents-issue-intake.yml", True),
        ("agents-80-pr-event-hub.yml", True),
        ("agents-81-gate-followups.yml", True),
        ("autofix.yml", True),
        ("autofix-repair.yml", True),
        ("ci.yml", True),
        ("pr-00-gate.yml", True),
        ("dependabot-updates.yml", True),
        ("list-llm-models.yml", True),
        ("reusable-10-ci-python.yml", False),
        ("reusable-20-pr-meta.yml", False),
        ("maint-68-sync-consumer-repos.yml", False),
        ("maint-83-bootstrap-consumer.yml", False),
        ("health-68-consumer-sync-drift.yml", False),
        ("health-73-template-completeness.yml", False),
        ("agents-debug-issue-event.yml", False),
        ("agents-weekly-metrics.yml", False),
        ("agents-moderate-connector.yml", False),
        ("agents-pr-meta-v4.yml", False),
        ("agents-autofix-loop.yml", False),
        ("agents-63-issue-intake.yml", False),
    ],
)
def test_is_consumer_workflow_classifies_expected_workflow_families(
    workflow_name: str, expected: bool
) -> None:
    assert validator.is_consumer_workflow(Path(workflow_name)) is expected


def _write_workflow(directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(f"name: {name}\n", encoding="utf-8")


def _write_manifest(manifest_path: Path, workflows: list[str]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump(
            {"workflows": [{"source": f".github/workflows/{workflow}"} for workflow in workflows]}
        ),
        encoding="utf-8",
    )


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    *,
    workflows_dir: Path,
    template_dir: Path,
    manifest_path: Path,
    strict: bool = False,
    source: str = "template-completeness",
    summary_path: Path | None = None,
) -> int:
    argv = [
        "validate_template_completeness.py",
        "--workflows-dir",
        str(workflows_dir),
        "--template-dir",
        str(template_dir),
        "--manifest",
        str(manifest_path),
        "--source",
        source,
    ]
    if strict:
        argv.append("--strict")

    monkeypatch.setattr(sys, "argv", argv)
    if summary_path is None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    else:
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    return validator.main()


def test_main_strict_returns_one_when_consumer_workflow_missing_from_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    workflows_dir = tmp_path / "workflows"
    template_dir = tmp_path / "template"
    manifest_path = tmp_path / "sync-manifest.yml"

    _write_workflow(workflows_dir, "agents-80-pr-event-hub.yml")
    template_dir.mkdir()
    _write_manifest(manifest_path, ["agents-80-pr-event-hub.yml"])

    result = _run_main(
        monkeypatch,
        workflows_dir=workflows_dir,
        template_dir=template_dir,
        manifest_path=manifest_path,
        strict=True,
    )

    assert result == 1
    output = capsys.readouterr().out
    assert "::warning::MISSING FROM TEMPLATE: agents-80-pr-event-hub.yml" in output
    assert "Total issues: 1" in output


def test_main_warns_and_writes_summary_when_template_workflow_missing_from_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    workflows_dir = tmp_path / "workflows"
    template_dir = tmp_path / "template"
    manifest_path = tmp_path / "sync-manifest.yml"
    summary_path = tmp_path / "summary.md"

    _write_workflow(workflows_dir, "agents-80-pr-event-hub.yml")
    _write_workflow(template_dir, "agents-80-pr-event-hub.yml")
    _write_manifest(manifest_path, [])

    result = _run_main(
        monkeypatch,
        workflows_dir=workflows_dir,
        template_dir=template_dir,
        manifest_path=manifest_path,
        source="health-73-template-completeness",
        summary_path=summary_path,
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "::warning::MISSING FROM MANIFEST: agents-80-pr-event-hub.yml" in output
    assert "Total issues: 1" in output

    summary = summary_path.read_text(encoding="utf-8")
    assert "## Template Completeness Check (health-73-template-completeness)" in summary
    assert "**Issues Found:** 1" in summary
    assert "- MISSING FROM MANIFEST: agents-80-pr-event-hub.yml - exists in template" in summary


def test_main_writes_no_issue_summary_when_template_and_manifest_are_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    workflows_dir = tmp_path / "workflows"
    template_dir = tmp_path / "template"
    manifest_path = tmp_path / "sync-manifest.yml"
    summary_path = tmp_path / "summary.md"

    _write_workflow(workflows_dir, "agents-80-pr-event-hub.yml")
    _write_workflow(template_dir, "agents-80-pr-event-hub.yml")
    _write_manifest(manifest_path, ["agents-80-pr-event-hub.yml"])

    result = _run_main(
        monkeypatch,
        workflows_dir=workflows_dir,
        template_dir=template_dir,
        manifest_path=manifest_path,
        source="sync-manifest",
        summary_path=summary_path,
    )

    assert result == 0
    assert "All consumer workflows are properly templated and manifested" in capsys.readouterr().out

    summary = summary_path.read_text(encoding="utf-8")
    assert "## Template Completeness Check (sync-manifest)" in summary
    assert "**Issues Found:** 0" in summary
