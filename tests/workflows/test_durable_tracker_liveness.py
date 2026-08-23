"""Offline gate: every durable tracker workflow has a Health 71 liveness assertion."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from scripts import check_durable_tracker_liveness
from scripts.check_durable_tracker_liveness import tracker_doc_workflows

TRACKER_DOC = Path("docs/ops/DURABLE_TRACKING_ISSUES.md")
LIVENESS_CONFIG = Path("config/durable_tracker_liveness.yml")
HEALTH_71 = Path(".github/workflows/health-71-sync-health-check.yml")


def _configured_workflows() -> set[str]:
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    return {str(entry["workflow"]) for entry in config["trackers"]}


def test_every_tracked_workflow_has_a_liveness_assertion() -> None:
    documented = tracker_doc_workflows()
    configured = _configured_workflows()
    missing = sorted(documented - configured)
    extra = sorted(configured - documented)
    assert not missing, f"tracker table workflows missing liveness config: {missing}"
    assert not extra, f"liveness config has undocumented workflows: {extra}"


def test_health_71_invokes_durable_tracker_liveness_check() -> None:
    text = HEALTH_71.read_text(encoding="utf-8")
    assert "check_durable_tracker_liveness.py" in text
    assert "--comment-on-failure" in text


def test_event_driven_tracker_is_not_subject_to_age_liveness() -> None:
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    tracker = next(
        entry
        for entry in config["trackers"]
        if entry["workflow"] == "maint-69-sync-integration-repo.yml"
    )

    assert tracker["event_driven"] is True
    assert "max_age_hours" not in tracker


def test_tracker_run_lookup_uses_get_for_query_parameters(monkeypatch) -> None:
    captured: list[str] = []

    def fake_check_output(command, **_kwargs):
        captured.extend(command)
        return "[]"

    monkeypatch.setattr(
        check_durable_tracker_liveness.subprocess, "check_output", fake_check_output
    )

    assert (
        check_durable_tracker_liveness._latest_executable_run(
            "stranske/Workflows", "health-68-consumer-sync-drift.yml", "token"
        )
        is None
    )
    method_index = captured.index("--method")
    assert captured[method_index + 1] == "GET"


def test_tracker_doc_table_links_match_config() -> None:
    text = TRACKER_DOC.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Current durable trackers\n\n\| Issue.*?\n\|[-| ]+\n(.*?)(?:\n\n|\n### )",
        text,
        re.DOTALL,
    )
    assert section_match
    issue_to_workflow: dict[int, str] = {}
    for row in section_match.group(1).splitlines():
        issue_match = re.search(r"\[#(\d+)\]", row)
        workflow_match = re.search(r"/([^/)]+?\.yml)\)", row)
        if issue_match and workflow_match:
            issue_to_workflow[int(issue_match.group(1))] = workflow_match.group(1)
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    for entry in config["trackers"]:
        issue = int(entry["issue"])
        workflow = str(entry["workflow"])
        assert issue_to_workflow.get(issue) == workflow, (
            f"config issue #{issue} maps to {workflow}, "
            f"tracker doc maps to {issue_to_workflow.get(issue)}"
        )
