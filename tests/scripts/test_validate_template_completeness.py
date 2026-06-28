from __future__ import annotations

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
