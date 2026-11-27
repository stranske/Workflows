"""Tests for Maint 66 workflow inventory classification."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.workflow_inventory_audit import (
    classify_audit_category,
    excluded_from_not_run_inventory,
    inspect_workflow_file,
    iter_workflow_inventory,
    not_run_candidates,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github/workflows"


def test_excluded_reusable_matches_maint66_shell_logic() -> None:
    reusable = (WORKFLOWS / "reusable-12-ci-docker.yml").read_text(encoding="utf-8")
    health42 = (WORKFLOWS / "health-42-actionlint.yml").read_text(encoding="utf-8")
    assert excluded_from_not_run_inventory(reusable) is True
    assert excluded_from_not_run_inventory(health42) is False


def test_reusable_autofix_not_excluded_by_pull_request_comment() -> None:
    """Whole-file Maint 66 grep false-positive; `on:` block scope is authoritative."""
    autofix = (WORKFLOWS / "reusable-18-autofix.yml").read_text(encoding="utf-8")
    assert excluded_from_not_run_inventory(autofix) is True


@pytest.mark.parametrize(
    "triggers,excluded,expected",
    [
        (("workflow_call",), True, "reusable_call_only"),
        (("workflow_call", "workflow_dispatch"), False, "reusable_with_independent_trigger"),
        (("workflow_dispatch",), False, "manual_utility"),
        (("schedule",), False, "scheduled"),
        (("pull_request", "push"), False, "event_driven"),
        ((), False, "unknown_trigger"),
    ],
)
def test_classify_audit_category(triggers: tuple[str, ...], excluded: bool, expected: str) -> None:
    assert classify_audit_category(triggers, excluded_from_not_run=excluded) == expected


def test_iter_workflow_inventory_covers_repo() -> None:
    rows = iter_workflow_inventory(WORKFLOWS)
    stems = {row.stem for row in rows}
    assert "pr-00-gate" in stems
    assert len(rows) == len(list(WORKFLOWS.glob("*.yml")))


def test_not_run_candidates_omit_call_only_reusables() -> None:
    rows = iter_workflow_inventory(WORKFLOWS)
    candidates = not_run_candidates(rows)
    # Every candidate must not be excluded
    assert all(not row.excluded_from_not_run for row in candidates)
    assert all(row.stem != "reusable-12-ci-docker" for row in candidates)


def test_inspect_workflow_file_reads_display_name(tmp_path: Path) -> None:
    path = tmp_path / "sample.yml"
    path.write_text(
        "name: Display title\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  noop:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo ok\n",
        encoding="utf-8",
    )
    row = inspect_workflow_file(path)
    assert row is not None
    assert row.display_name == "Display title"
    assert row.audit_category == "manual_utility"
