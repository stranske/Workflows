"""Tests for Maint 66 workflow inventory classification."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.workflow_concurrency_audit import normalize_triggers
from scripts.workflow_inventory_audit import (
    EXIT_CALL_ONLY_SKIP,
    EXIT_INDEPENDENT_TRIGGER,
    EXIT_INSPECTION_ERROR,
    WorkflowInventoryError,
    classify_audit_category,
    excluded_from_not_run_inventory,
    inspect_workflow_file,
    iter_workflow_inventory,
    load_workflow_document,
    main,
    not_run_candidates,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github/workflows"


def test_excluded_reusable_matches_maint66_shell_logic() -> None:
    worker = load_workflow_document(WORKFLOWS / "agents-72-codex-belt-worker.yml")
    health42 = load_workflow_document(WORKFLOWS / "health-42-actionlint.yml")
    assert excluded_from_not_run_inventory(normalize_triggers(worker.get("on"))) is True
    assert excluded_from_not_run_inventory(normalize_triggers(health42.get("on"))) is False


def test_reusable_autofix_not_excluded_by_pull_request_comment() -> None:
    """Whole-file grep would false-match `pull_request` in job scripts; triggers win."""
    row = inspect_workflow_file(WORKFLOWS / "reusable-18-autofix.yml")
    assert row.excluded_from_not_run is True
    assert row.audit_category == "reusable_call_only"


def test_workflow_call_plus_issues_not_excluded() -> None:
    triggers = normalize_triggers(
        {
            "workflow_call": {"inputs": {}},
            "issues": {"types": ["opened"]},
        }
    )
    assert excluded_from_not_run_inventory(triggers) is False


def test_workflow_dispatch_in_description_not_counted(tmp_path: Path) -> None:
    path = tmp_path / "call-only-false-grep.yml"
    path.write_text(
        "name: Callable\n"
        "on:\n"
        "  workflow_call:\n"
        "    inputs:\n"
        "      mode:\n"
        '        description: "workflow_dispatch: optional helper text"\n'
        "jobs:\n"
        "  noop:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo ok\n",
        encoding="utf-8",
    )
    row = inspect_workflow_file(path)
    assert row.triggers == ("workflow_call",)
    assert row.excluded_from_not_run is True


def test_invalid_yaml_raises_and_main_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "broken.yml").write_text("on: [\n", encoding="utf-8")
    (workflows / "ok.yml").write_text(
        "on:\n  workflow_dispatch:\njobs:\n  j:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkflowInventoryError, match="broken.yml"):
        iter_workflow_inventory(workflows)

    monkeypatch.setattr(
        sys,
        "argv",
        ["workflow_inventory_audit.py", "--workflows-dir", str(workflows)],
    )
    assert main() == 1


def test_check_call_only_skip_distinct_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "call-only.yml").write_text(
        "name: Call only\non:\n  workflow_call:\njobs:\n  j:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    (workflows / "mixed-trigger.yml").write_text(
        "name: Mixed trigger\n"
        "on:\n"
        "  workflow_call:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  j:\n"
        "    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    (workflows / "broken.yml").write_text("on: [\n", encoding="utf-8")

    # Callable-only (repo file and fixture) -> EXIT_CALL_ONLY_SKIP (0)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workflow_inventory_audit.py",
            "--workflows-dir",
            str(WORKFLOWS),
            "--check-call-only-skip",
            "agents-72-codex-belt-worker",
        ],
    )
    assert main() == EXIT_CALL_ONLY_SKIP
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workflow_inventory_audit.py",
            "--workflows-dir",
            str(workflows),
            "--check-call-only-skip",
            "call-only",
        ],
    )
    assert main() == EXIT_CALL_ONLY_SKIP

    # Mixed trigger (workflow_call + independent trigger) -> EXIT_INDEPENDENT_TRIGGER
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workflow_inventory_audit.py",
            "--workflows-dir",
            str(WORKFLOWS),
            "--check-call-only-skip",
            "health-42-actionlint",
        ],
    )
    assert main() == EXIT_INDEPENDENT_TRIGGER
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workflow_inventory_audit.py",
            "--workflows-dir",
            str(workflows),
            "--check-call-only-skip",
            "mixed-trigger",
        ],
    )
    assert main() == EXIT_INDEPENDENT_TRIGGER

    # Malformed YAML -> EXIT_INSPECTION_ERROR (distinct from 0 and EXIT_INDEPENDENT_TRIGGER)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "workflow_inventory_audit.py",
            "--workflows-dir",
            str(workflows),
            "--check-call-only-skip",
            "broken",
        ],
    )
    status = main()
    assert status == EXIT_INSPECTION_ERROR
    assert status not in {EXIT_CALL_ONLY_SKIP, EXIT_INDEPENDENT_TRIGGER}
    assert "broken.yml" in capsys.readouterr().err


def test_check_call_only_skip_unexpected_helper_failure_is_distinct(tmp_path: Path) -> None:
    """An uncaught failure (e.g. missing PyYAML) must not match valid independent-trigger code."""
    blocker = tmp_path / "blocker"
    blocker.mkdir()
    (blocker / "yaml.py").write_text(
        "raise ModuleNotFoundError(\"No module named 'yaml'\")\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PYTHONPATH": f"{blocker}{os.pathsep}{REPO_ROOT}",
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/workflow_inventory_audit.py"),
            "--workflows-dir",
            str(WORKFLOWS),
            "--check-call-only-skip",
            "pr-00-gate",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert proc.returncode not in {EXIT_CALL_ONLY_SKIP, EXIT_INDEPENDENT_TRIGGER}
    assert "No module named 'yaml'" in proc.stderr


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
    assert all(not row.excluded_from_not_run for row in candidates)
    assert all(row.stem != "agents-72-codex-belt-worker" for row in candidates)


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
    assert row.display_name == "Display title"
    assert row.audit_category == "manual_utility"
