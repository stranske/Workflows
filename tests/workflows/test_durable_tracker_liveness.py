"""Offline gate: every durable tracker workflow has a Health 71 liveness assertion."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

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
